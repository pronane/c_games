"""Background capture + WAV writing.

Design notes
------------
* A dedicated capture thread pulls blocks from the OS at the requested sample
  rate.  The *only* job of that thread is to move audio into the writer queue so
  an I/O hiccup can never stall the audio stream.
* A writer thread encodes either *WAV* or *FLAC* to disk.  If the codec fails
  mid-recording (e.g. an optional dependency vanished) the engine transparently
  falls back to WAV until the recording is stopped, and reports it via
  ``RecordingInfo.fallback_reason``.
* WAV retains captured float32 samples. FLAC is encoded as lossless 24-bit PCM;
  the FLAC bitstream is lossless for those PCM values, though converting the
  float samples to 24-bit integer PCM can quantize below that precision.
"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .audio import Device, downmix_block, ensure_com_initialized
from .ffmpeg_support import decode_audio_to_temp_wav, ffmpeg_executable, pcm_encoder_command

SAMPLE_WIDTH_FLOAT = 4  # bytes per float32 sample

try:  # optional lossless FLAC writer
    import soundfile as _sf
except Exception:  # pragma: no cover - depends on environment
    _sf = None


# --------------------------------------------------------------------------- #
#  WAV helpers
# --------------------------------------------------------------------------- #
def write_wav_header(fh, samplerate: int, channels: int, frames: int) -> None:
    """Write a WAVE_FORMAT_IEEE_FLOAT header with ``frames`` already known."""
    data_bytes = int(frames) * channels * SAMPLE_WIDTH_FLOAT
    riff_size = 36 + data_bytes
    fh.write(b"RIFF")
    fh.write(int(min(riff_size, 0xFFFFFFFF)).to_bytes(4, "little"))
    fh.write(b"WAVE")
    fh.write(b"fmt ")
    fh.write((16).to_bytes(4, "little"))
    fh.write((3).to_bytes(2, "little"))  # WAVE_FORMAT_IEEE_FLOAT
    fh.write(int(channels).to_bytes(2, "little"))
    fh.write(int(samplerate).to_bytes(4, "little"))
    fh.write(int(samplerate * channels * SAMPLE_WIDTH_FLOAT).to_bytes(4, "little"))
    fh.write(int(channels * SAMPLE_WIDTH_FLOAT).to_bytes(2, "little"))
    fh.write((32).to_bytes(2, "little"))  # bits per sample
    fh.write(b"data")
    fh.write(int(min(data_bytes, 0xFFFFFFFF)).to_bytes(4, "little"))


def write_silent_wav(path: str, samplerate: int, channels: int, seconds: float = 0.05) -> None:
    frames = max(1, int(seconds * samplerate))
    with open(path, "wb") as fh:
        write_wav_header(fh, samplerate, channels, frames)
        fh.write(b"\x00" * (frames * channels * SAMPLE_WIDTH_FLOAT))


def fix_wav_header(path: str) -> None:
    """Correct RIFF/data sizes after streaming (cheap, tolerant)."""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as fh:
            head = fh.read(44)
            if len(head) < 44 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return
            if head[12:16] != b"fmt " or int.from_bytes(head[20:22], "little") != 3:
                return  # not our float32 layout; leave alone
            fh.seek(4)
            fh.write(int(size - 8).to_bytes(4, "little"))
            fh.seek(40)
            fh.write(int(size - 44).to_bytes(4, "little"))
    except OSError:
        pass


def wav_duration(path: str, samplerate_hint: Optional[int] = None) -> float:
    """Duration in seconds (soundfile, then the stdlib header reader)."""
    if _sf is not None:
        try:
            info = _sf.info(path)
            if info.samplerate:
                return info.frames / float(info.samplerate)
        except Exception:
            pass
    try:
        with wave.open(path, "rb") as wf:
            rate = wf.getframerate() or samplerate_hint
            return wf.getnframes() / float(rate) if rate else 0.0
    except Exception:
        pass
    if not path.lower().endswith(".wav"):
        return 0.0  # no reliable size -> duration guess for compressed formats
    try:
        size = os.path.getsize(path)
        return max(0.0, (size - 44) / (4.0 * 2 * (samplerate_hint or 48000)))
    except OSError:
        return 0.0


# --------------------------------------------------------------------------- #
#  Result objects
# --------------------------------------------------------------------------- #
@dataclass
class RecordingInfo:
    path: str
    samplerate: int
    channels: int
    container: str  # "WAV" | "FLAC"
    frames: int = 0
    duration: float = 0.0
    started: float = field(default_factory=time.time)
    peak_db: float = -120.0
    fallback_reason: Optional[str] = None

    @property
    def size_bytes(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    @property
    def is_silent(self) -> bool:
        return self.frames > 0 and self.duration > 0.3 and self.peak_db < -60.0


# --------------------------------------------------------------------------- #
#  Recorder
# --------------------------------------------------------------------------- #
class Recorder:
    """One active recording.  Create, ``start()``, then ``stop()``."""

    def __init__(
        self,
        source,
        out_path: str,
        samplerate: int,
        channels: int,
        container: str = "WAV",
        blocksize: Optional[int] = None,
        device_name: str = "",
    ) -> None:
        self.source = source
        self.out_path = out_path
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.container = container.upper()
        self.device_name = device_name
        self.blocksize = int(blocksize or max(1024, self.samplerate // 50))

        self._q: "queue.Queue[Optional[np.ndarray]]" = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._frames = 0        # frames confirmed written to disk
        self._captured = 0      # frames handed to the writer (incl. silence)
        self._peak = 0.0
        self._level = 0.0
        self._level_peak = 0.0
        self._preview: "deque[np.ndarray]" = deque(maxlen=200)
        self._start_error: Optional[Exception] = None
        self._last_block_t: Optional[float] = None
        self._writer_error: Optional[Exception] = None
        self.fallback_reason: Optional[str] = None
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None

    # ----------------------------------------------------------- properties
    @property
    def is_running(self) -> bool:
        return not self._stop.is_set()

    @property
    def frames(self) -> int:
        """Frames recorded so far (captured count while running, else written)."""
        with self._lock:
            return self._captured if not self._stop.is_set() else self._frames

    @property
    def duration(self) -> float:
        return self.frames / float(self.samplerate) if self.samplerate else 0.0

    def level(self):
        """Current RMS level (0..1) and peak since last call - for the meter."""
        with self._lock:
            rms = self._level
            peak = self._level_peak
            self._level_peak *= 0.72  # decay between UI polls
        return rms, peak

    def drain_preview(self, max_frames: int = 24000):
        """Pop recent captured audio for the live waveform (UI thread)."""
        with self._lock:
            blocks = list(self._preview)
            self._preview.clear()
        if not blocks:
            return None
        data = np.concatenate(blocks, axis=0)
        return data[-max_frames:] if len(data) > max_frames else data

    # --------------------------------------------------------------- control
    def start(self) -> None:
        self.started_at = time.time()
        self._threads = [
            threading.Thread(target=self._writer_loop, name="ac-writer", daemon=True),
            threading.Thread(target=self._capture_loop, name="ac-capture", daemon=True),
        ]
        for t in self._threads:
            t.start()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def pause(self) -> None:
        """Temporarily omit audio from the file; wall-clock pause time is excluded."""
        if not self._stop.is_set():
            self._paused.set()
            with self._lock:
                # Do not pad a pause as a device stall when recording resumes.
                self._last_block_t = None

    def resume(self) -> None:
        """Continue capture after a user pause."""
        if not self._stop.is_set():
            with self._lock:
                self._last_block_t = None
            self._paused.clear()

    def stop(self, timeout: float = 6.0) -> RecordingInfo:
        self.ended_at = time.time()
        # If the device went quiet right before stop was pressed, pad that final
        # gap too, so the file ends at the moment of stopping (only real stalls
        # trigger this - a device that is simply delivering buffered audio has a
        # fresh timestamp and is never padded).
        try:
            with self._lock:
                last_t = self._last_block_t
            if last_t is not None:
                gap = time.monotonic() - last_t
                stall = max(0.15, 1.5 * self.blocksize / self.samplerate)
                if gap > stall:
                    missing = min(int(gap * self.samplerate),
                                  10 * 60 * self.samplerate)
                    if missing > 0:
                        with self._lock:
                            self._captured += missing
                        self._q.put(
                            np.zeros((missing, self.channels), dtype=np.float32),
                            timeout=1.0)
        except (queue.Full, Exception):
            pass
        self._stop.set()
        # signal end-of-stream: the writer drains everything queued before this
        # sentinel, so any trailing silence above is always written
        while True:
            try:
                self._q.put(None, timeout=0.5)
                break
            except queue.Full:
                if self._writer_error is not None:
                    break
        deadline = time.time() + timeout
        for t in self._threads:
            t.join(max(0.05, deadline - time.time()))
        if self._writer_error:
            raise self._writer_error
        if self._start_error and self._frames == 0:
            raise self._start_error
        return self.info()

    def info(self) -> RecordingInfo:
        frames = self.frames
        return RecordingInfo(
            path=self.out_path,
            samplerate=self.samplerate,
            channels=self.channels,
            container=self.container,
            frames=frames,
            duration=frames / float(self.samplerate) if self.samplerate else 0.0,
            started=self.started_at or time.time(),
            peak_db=20.0 * float(np.log10(self._peak)) if self._peak > 0 else -120.0,
            fallback_reason=self.fallback_reason,
        )

    # --------------------------------------------------------------- threads
    def _capture_loop(self) -> None:
        try:
            ensure_com_initialized()
            with self.source.recorder(
                samplerate=self.samplerate, channels=self.channels
            ) as recorder:
                while not self._stop.is_set():
                    while self._paused.is_set() and not self._stop.wait(0.05):
                        pass
                    if self._stop.is_set():
                        break
                    block = recorder.record(numframes=self.blocksize)
                    if self._paused.is_set():
                        # A read can be in flight when Pause is clicked; omit it.
                        with self._lock:
                            self._last_block_t = None
                        continue
                    if block is None or len(block) == 0:
                        continue
                    block = downmix_block(block, self.channels)
                    if len(block) == 0:
                        continue
                    block = self._keep_timeline(block)
                    rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
                    peak = float(np.max(np.abs(block))) if block.size else 0.0
                    with self._lock:
                        self._level = rms
                        if peak > self._level_peak:
                            self._level_peak = peak
                        if peak > self._peak:
                            self._peak = peak
                        self._preview.append(block)
                    while not self._stop.is_set():
                        try:
                            self._q.put(block, timeout=0.25)
                            break
                        except queue.Full:
                            continue
        except Exception as exc:  # keep the UI alive, report on stop
            if self._start_error is None:
                self._start_error = exc
            self._stop.set()
            try:
                self._q.put_nowait(None)
            except queue.Full:
                pass

    def _keep_timeline(self, block: np.ndarray) -> np.ndarray:
        """Keep the file's timeline honest without ever discarding audio.

        Two rules, in order of importance:

        1. **Never throw captured audio away.**  Devices sometimes deliver a
           burst of buffered frames after a hiccup; those frames are real audio
           and throwing them away would silently cut the recording.  So every
           block the OS hands us is written, in order.
        2. **Fill genuine stalls with silence.**  If the device stops delivering
           for longer than ``STALL_SECONDS`` (WASAPI loopback when nothing is
           playing, a device that fell asleep, a suspended stream), insert
           exactly as much digital silence as time passed, so the file length
           keeps matching the wall clock and audio stays in sync with reality.
        """
        now = time.monotonic()
        with self._lock:
            last_t = self._last_block_t
            self._last_block_t = now
        out = block
        if last_t is not None:
            gap = now - last_t
            # anything clearly longer than a normal block interval counts as a
            # stall (0.15 s floor keeps healthy devices from ever being padded)
            stall = max(0.15, 1.5 * self.blocksize / self.samplerate)
            if gap > stall:
                missing = int((gap - self.blocksize / self.samplerate) * self.samplerate)
                # cap a single insert at 10 minutes of virtual silence
                missing = max(0, min(missing, 10 * 60 * self.samplerate))
                if missing > 0:
                    out = np.concatenate(
                        [np.zeros((missing, self.channels), dtype=np.float32), block],
                        axis=0)
        with self._lock:
            self._captured += len(out)
        return out

    def _writer_loop(self) -> None:
        base, _ext = os.path.splitext(self.out_path)
        use_flac = self.container == "FLAC" and _sf is not None
        encoder = "aac" if self.container.startswith("M4A") else "mp3" if self.container.startswith("MP3") else None
        bitrate = 320
        ffmpeg_proc = None
        if self.container == "FLAC" and _sf is None:
            self.fallback_reason = "FLAC encoder (soundfile) unavailable - saved as WAV instead."
            self.container, self.out_path, use_flac = "WAV", base + ".wav", False
        if self.container == "FLAC" and not use_flac:
            self.fallback_reason = "FLAC encoder unavailable - saved as WAV instead."
            self.container, self.out_path = "WAV", base + ".wav"
        use_ffmpeg = encoder is not None
        if use_ffmpeg:
            try:
                bitrate = 320
                ffmpeg_proc = subprocess.Popen(
                    pcm_encoder_command(self.out_path, self.samplerate, self.channels, encoder, bitrate),
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except Exception as exc:
                self.fallback_reason = f"{self.container} encoder unavailable ({exc}) - saved as WAV instead."
                self.container, self.out_path, use_ffmpeg = "WAV", base + ".wav", False
                ffmpeg_proc = None
        wav_handle = None
        sf_handle = None
        pending: List[np.ndarray] = []
        frames_written = 0
        try:
            if use_flac:
                try:
                    sf_handle = _sf.SoundFile(
                        self.out_path, mode="w", samplerate=self.samplerate,
                        channels=self.channels, subtype="PCM_24", format="FLAC")
                except Exception as exc:
                    self.fallback_reason = f"FLAC unavailable ({exc}) - saved as WAV instead."
                    use_flac = False
                    sf_handle = None
                    self.container, self.out_path = "WAV", base + ".wav"
            if not use_flac and not use_ffmpeg:
                wav_handle = open(self.out_path, "wb")
                write_wav_header(wav_handle, self.samplerate, self.channels, 0)

            while True:
                item = self._q.get()
                if item is None:
                    break
                if isinstance(item, np.ndarray):
                    pending.append(item)
                    if sum(len(p) for p in pending) < self.samplerate // 4:
                        continue  # batch ~0.5 s for fewer syscalls
                    pending = [np.concatenate(pending, axis=0)]
                # flush
                if pending:
                    data = pending[0]
                    pending = []
                    if len(data):
                        if use_flac and sf_handle is not None:
                            sf_handle.write(data)
                        elif use_ffmpeg and ffmpeg_proc is not None and ffmpeg_proc.stdin:
                            ffmpeg_proc.stdin.write(data.astype("<f4", copy=False).tobytes())
                        else:
                            wav_handle.write(data.astype("<f4", copy=False).tobytes())
                        frames_written += len(data)
                        with self._lock:
                            self._frames = frames_written
            # drain whatever is left
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, np.ndarray):
                    pending.append(item)
            if pending:
                data = np.concatenate(pending, axis=0)
                if len(data):
                    if use_flac and sf_handle is not None:
                        sf_handle.write(data)
                    elif use_ffmpeg and ffmpeg_proc is not None and ffmpeg_proc.stdin:
                        ffmpeg_proc.stdin.write(data.astype("<f4", copy=False).tobytes())
                    else:
                        wav_handle.write(data.astype("<f4", copy=False).tobytes())
                    frames_written += len(data)
                    with self._lock:
                        self._frames = frames_written
        except Exception as exc:
            self._writer_error = exc
        finally:
            try:
                if sf_handle is not None:
                    sf_handle.close()
            except Exception:
                pass
            try:
                if wav_handle is not None:
                    wav_handle.close()
            except Exception:
                pass
            if ffmpeg_proc is not None:
                try:
                    if ffmpeg_proc.stdin and not ffmpeg_proc.stdin.closed:
                        ffmpeg_proc.stdin.close()
                    err = ffmpeg_proc.stderr.read() if ffmpeg_proc.stderr else b""
                    if ffmpeg_proc.stderr:
                        ffmpeg_proc.stderr.close()
                    code = ffmpeg_proc.wait(timeout=30)
                    if code and self._writer_error is None:
                        self._writer_error = RuntimeError(
                            "FFmpeg recording encoder failed: " + err.decode("utf-8", "replace")[-1200:])
                except Exception as exc:
                    if self._writer_error is None:
                        self._writer_error = exc
            if not use_flac and not use_ffmpeg:
                fix_wav_header(self.out_path)
            if frames_written == 0 and not self._writer_error:
                if use_ffmpeg:
                    self._writer_error = RuntimeError("No audio samples were captured by the encoder.")
                else:
                    try:
                        write_silent_wav(self.out_path, self.samplerate, self.channels)
                    except Exception:
                        pass


# --------------------------------------------------------------------------- #
#  Playback
# --------------------------------------------------------------------------- #
# Files larger than this are streamed from disk instead of being held in RAM
# (an hour of 32-bit float 96 kHz stereo is ~2.8 GB; nobody wants that in memory).
IN_MEMORY_LIMIT = 256 * 1024 * 1024


class AudioFile:
    """Audio file ready for playback.

    Small/medium files are decoded into ``data`` for instant seeking and
    waveform drawing.  Large files are *streamed* (``streaming=True``): only
    metadata lives in memory and the player reads blocks on demand.
    """

    def __init__(self, path: str, stream_large: bool = True) -> None:
        self.path = path
        self._decode_path = path
        self._temporary_decode_path = None
        self.data = None
        self.samplerate = 0
        self.channels = 1
        self.duration = 0.0
        self.error: Optional[str] = None
        self.streaming = False
        self._sf_info = None
        self._load(stream_large)

    # ------------------------------------------------------------ streaming
    def read_block(self, start_frame: int, frames: int) -> np.ndarray:
        """Random-access read, used by the streaming player."""
        if self.data is not None:
            return np.ascontiguousarray(self.data[start_frame:start_frame + frames])
        if _sf is None:
            raise RuntimeError("streaming playback needs the 'soundfile' package")
        if self._sf_info is None:
            self._sf_info = _sf.info(self._decode_path)
        with _sf.SoundFile(self._decode_path) as fh:
            fh.seek(min(start_frame, len(fh)))
            block = fh.read(frames, dtype="float32", always_2d=True)
        return np.ascontiguousarray(block, dtype=np.float32)

    def overview_peaks(self, cols: int = 900):
        """Coarse min/max pairs for the waveform without loading everything."""
        cols = max(32, int(cols))
        mins = np.zeros(cols, dtype=np.float32)
        maxs = np.zeros(cols, dtype=np.float32)
        total = max(1, int(self.duration * self.samplerate))
        if self.data is not None:
            mono = self.data if self.data.ndim == 1 else self.data.mean(axis=1)
            chunk = max(1, len(mono) // cols)
            for i in range(cols):
                seg = mono[i * chunk:(i + 1) * chunk]
                if len(seg):
                    mins[i], maxs[i] = float(seg.min()), float(seg.max())
            return np.stack([mins, maxs], axis=1)
        if _sf is None:
            return None
        step = total / cols
        win = max(256, int(step))
        try:
            with _sf.SoundFile(self._decode_path) as fh:
                for i in range(cols):
                    fh.seek(min(int(i * step), max(0, total - 1)))
                    block = fh.read(win, dtype="float32", always_2d=True)
                    if len(block):
                        mono = block.mean(axis=1)
                        mins[i], maxs[i] = float(mono.min()), float(mono.max())
        except Exception:
            return None
        return np.stack([mins, maxs], axis=1)

    def _load(self, stream_large: bool = True) -> None:
        # FFmpeg handles common compressed containers and extracts audio-only
        # from video inputs such as MP4; the source file is never modified.
        if os.path.splitext(self.path)[1].lower() in {".mp3", ".m4a", ".mp4", ".m4v", ".mov", ".aac"}:
            try:
                self._temporary_decode_path = decode_audio_to_temp_wav(self.path)
                self._decode_path = self._temporary_decode_path
            except Exception as exc:
                self.error = str(exc)
                return
        # Decide up-front whether to stream, and remember the metadata
        if _sf is not None and stream_large:
            try:
                info = _sf.info(self._decode_path)
                size = os.path.getsize(self._decode_path)
                if size > IN_MEMORY_LIMIT:
                    self.samplerate = int(info.samplerate)
                    self.channels = int(info.channels)
                    self.duration = info.frames / float(info.samplerate or 1)
                    self.streaming = True
                    self._sf_info = info
                    return
            except Exception:
                pass
        if _sf is not None:
            try:
                data, sr = _sf.read(self._decode_path, dtype="float32", always_2d=True)
                self.data = np.ascontiguousarray(data, dtype=np.float32)
                self.samplerate = int(sr)
                self.channels = int(self.data.shape[1])
                self.duration = len(self.data) / float(sr) if sr else 0.0
                return
            except Exception as exc:
                self.error = str(exc)
        # wave-module fallback (16/24/32-bit PCM or float)
        try:
            with wave.open(self._decode_path, "rb") as wf:
                self.channels = wf.getnchannels()
                self.samplerate = wf.getframerate()
                width = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())
            if width == 2:
                arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            elif width == 4:
                arr = np.frombuffer(raw, dtype="<f4").astype(np.float32)
            elif width == 3:
                b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
                ints = (b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16))
                ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
                arr = (ints / float(1 << 23)).astype(np.float32)
            elif width == 1:
                arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                raise RuntimeError(f"Unsupported WAV sample width {width}")
            self.data = np.ascontiguousarray(arr.reshape(-1, self.channels))
            self.duration = len(self.data) / float(self.samplerate) if self.samplerate else 0.0
            self.error = None
        except Exception as exc:
            if not self.error:
                self.error = str(exc)

    def close(self) -> None:
        """Remove any temporary decoded audio once no longer needed."""
        temp_path = self._temporary_decode_path
        self._temporary_decode_path = None
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def __del__(self):
        self.close()


class Player:
    """Streams an ``AudioFile`` to the default output with pause/seek/volume."""

    def __init__(self, on_finish=None, on_error=None) -> None:
        self.audio: Optional[AudioFile] = None
        self.on_finish = on_finish
        self.on_error = on_error
        self.volume = 0.85
        self._pos = 0  # frame index
        self._lock = threading.Lock()
        self._play_event = threading.Event()
        self._quit = threading.Event()
        self._finished_ok = False
        self._failed = False
        self._thread: Optional[threading.Thread] = None
        self._generation = 0

    # ------------------------------------------------------------- queries
    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._play_event.is_set()

    @property
    def loaded(self) -> bool:
        return self.audio is not None and (self.audio.data is not None
                                           or self.audio.streaming)

    @property
    def position(self) -> float:
        if not self.audio or not self.audio.samplerate:
            return 0.0
        with self._lock:
            return self._pos / float(self.audio.samplerate)

    # ------------------------------------------------------------- control
    def load(self, audio: AudioFile) -> None:
        self.stop()
        self.audio = audio
        with self._lock:
            self._pos = 0

    def play(self) -> None:
        if not self.loaded:
            return
        if self._thread is not None and self._thread.is_alive():
            self._play_event.set()
            return
        if self.position >= (self.audio.duration - 0.01):
            with self._lock:
                self._pos = 0
        self._play_event.set()
        self._quit.clear()
        self._finished_ok = False
        self._failed = False
        self._generation += 1
        gen = self._generation
        self._thread = threading.Thread(target=self._run, args=(gen,), name="ac-player", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._play_event.clear()

    def toggle(self) -> bool:
        """Returns True if now playing."""
        if self.playing:
            self.pause()
            return False
        self.play()
        return True

    def stop(self) -> None:
        self._quit.set()
        self._play_event.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(1.5)
        self._thread = None
        with self._lock:
            self._pos = 0

    def seek(self, seconds: float) -> None:
        if not self.loaded:
            return
        rate = self.audio.samplerate
        with self._lock:
            self._pos = int(max(0.0, min(seconds, self.audio.duration)) * rate)

    def seek_relative(self, delta: float) -> None:
        self.seek(self.position + delta)

    # ---------------------------------------------------------------- thread
    def _run(self, gen: int) -> None:
        audio = self.audio
        data = audio.data
        rate = audio.samplerate
        channels = audio.channels
        total = (len(data) if data is not None
                 else int(audio.duration * rate))
        try:
            ensure_com_initialized()
            import soundcard

            spk_channels = 1 if channels == 1 else channels
            with soundcard.default_speaker().player(samplerate=rate,
                                                   channels=spk_channels,
                                                   blocksize=2048) as spk:
                block_frames = max(512, int(rate * 0.05))
                while not self._quit.is_set() and gen == self._generation:
                    if not self._play_event.wait(0.2):
                        continue
                    if self._quit.is_set() or gen != self._generation:
                        break
                    with self._lock:
                        start = self._pos
                    if start >= total:
                        self._finished_ok = True
                        break
                    end = min(total, start + block_frames)
                    if data is not None:
                        chunk = data[start:end]
                    else:  # large file: read just this slice from disk
                        chunk = audio.read_block(start, end - start)
                        if len(chunk) == 0:
                            self._finished_ok = True
                            break
                        end = start + len(chunk)
                    # always hand the backend its own contiguous buffer
                    chunk = np.array(chunk, dtype=np.float32, copy=True,
                                     order="C")
                    if self.volume != 1.0:
                        chunk *= float(self.volume)
                    spk.play(chunk)
                    with self._lock:
                        if gen == self._generation:
                            self._pos = end
        except Exception as exc:
            self._failed = True
            if self.on_error:
                try:
                    self.on_error(str(exc))
                except Exception:
                    pass
        finally:
            if gen == self._generation:
                self._play_event.clear()
                if self.on_finish and (self._finished_ok or self._failed):
                    try:
                        self.on_finish(self._finished_ok)
                    except Exception:
                        pass
