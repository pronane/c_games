"""Non-destructive, frame-accurate audio editing and streaming export."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Tuple

import numpy as np

from .recorder import AudioFile, _sf, fix_wav_header, write_wav_header
from .ffmpeg_support import encode_float32_pcm

Span = Tuple[int, int]  # half-open source frame interval


class AudioEditSession:
    """An edit decision list over an immutable source recording."""

    def __init__(self, audio: AudioFile):
        if not audio.samplerate or audio.duration <= 0:
            raise ValueError("The recording could not be read or is empty")
        self.audio = audio
        self.total_frames = len(audio.data) if audio.data is not None else round(audio.duration * audio.samplerate)
        self.segments: List[Span] = [(0, self.total_frames)]
        self._undo: List[List[Span]] = []
        self._redo: List[List[Span]] = []

    @property
    def duration_frames(self) -> int:
        return sum(b - a for a, b in self.segments)

    @property
    def duration(self) -> float:
        return self.duration_frames / self.audio.samplerate

    def _frame(self, seconds: float) -> int:
        return max(0, min(self.duration_frames, round(float(seconds) * self.audio.samplerate)))

    def _extract(self, start: int, end: int) -> List[Span]:
        out: List[Span] = []
        cursor = 0
        for a, b in self.segments:
            lo, hi = max(start, cursor), min(end, cursor + b - a)
            if hi > lo:
                out.append((a + lo - cursor, a + hi - cursor))
            cursor += b - a
            if cursor >= end:
                break
        return out

    def _commit(self, segments: List[Span]) -> None:
        if not segments:
            raise ValueError("An edit cannot leave an empty recording")
        self._undo.append(self.segments.copy())
        self._redo.clear()
        self.segments = segments

    def trim(self, start_seconds: float, end_seconds: float) -> None:
        start, end = self._frame(start_seconds), self._frame(end_seconds)
        if end <= start:
            raise ValueError("Select a time range longer than zero")
        self._commit(self._extract(start, end))

    def remove(self, start_seconds: float, end_seconds: float) -> None:
        start, end = self._frame(start_seconds), self._frame(end_seconds)
        if end <= start:
            raise ValueError("Select a time range longer than zero")
        self._commit(self._extract(0, start) + self._extract(end, self.duration_frames))

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.segments.copy())
        self.segments = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.segments.copy())
        self.segments = self._redo.pop()
        return True

    def suspected_breaks(self, *, window_seconds: float = 1.0,
                         jump_db: float = 12.0, minimum_level_db: float = -45.0,
                         context_seconds: float = 2.0) -> list[tuple[float, float]]:
        """Return review-only ranges around abrupt loudness changes (not ad identification)."""
        window_frames = max(1, int(window_seconds * self.audio.samplerate))
        levels: list[float] = []
        times: list[float] = []
        for start in range(0, self.total_frames, window_frames):
            count = min(window_frames, self.total_frames - start)
            block = self.audio.read_block(start, count)
            if block is None or len(block) == 0:
                levels.append(-120.0)
            else:
                values = np.asarray(block, dtype=np.float64)
                rms = float(np.sqrt(np.mean(values * values)))
                levels.append(20.0 * np.log10(max(rms, 1e-6)))
            times.append((start + count / 2) / self.audio.samplerate)
        points = []
        for i in range(1, len(levels)):
            before, after = levels[i - 1], levels[i]
            if min(before, after) >= minimum_level_db and abs(after - before) >= jump_db:
                point = (times[i - 1] + times[i]) / 2
                if not points or point - points[-1] >= 8.0:
                    points.append(point)
        ranges = []
        for point in points:
            a, b = max(0.0, point - context_seconds), min(self.duration, point + context_seconds)
            if b > a:
                ranges.append((a, b))
        return ranges

    def overview_peaks(self, columns: int = 700):
        columns = max(1, int(columns))
        mins = np.zeros(columns, dtype=np.float32)
        maxs = np.zeros(columns, dtype=np.float32)
        total = self.duration_frames
        for i in range(columns):
            lo = i * total // columns
            hi = max(lo + 1, (i + 1) * total // columns)
            pieces = self._extract(lo, min(hi, total))
            blocks = [self.audio.read_block(a, b - a) for a, b in pieces]
            if blocks:
                joined = np.concatenate(blocks, axis=0)
                mono = joined if joined.ndim == 1 else joined.mean(axis=1)
                if len(mono):
                    mins[i], maxs[i] = float(mono.min()), float(mono.max())
        return mins, maxs

    def _write(self, output_path: str, spans: List[Span], bitrate_kbps: int = 320) -> str:
        path = os.path.abspath(output_path)
        if os.path.abspath(self.audio.path) == path:
            raise ValueError("Choose a new filename; the original recording is never overwritten")
        frames = sum(b - a for a, b in spans)
        if frames <= 0:
            raise ValueError("The selected edit is empty")
        ext = Path(path).suffix.lower()
        channels, rate = self.audio.channels, self.audio.samplerate
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        def pcm_chunks():
            for a, b in spans:
                pos = a
                while pos < b:
                    block = self.audio.read_block(pos, min(65536, b - pos))
                    if not len(block):
                        break
                    yield np.asarray(block, dtype="<f4").tobytes(order="C")
                    pos += len(block)

        if ext in (".m4a", ".mp3"):
            encoder = "aac" if ext == ".m4a" else "mp3"
            encode_float32_pcm(path, rate, channels, encoder, int(bitrate_kbps), pcm_chunks())
        elif ext == ".flac":
            if _sf is None:
                raise RuntimeError("Saving FLAC requires the soundfile package")
            with _sf.SoundFile(path, mode="w", samplerate=rate, channels=channels,
                               format="FLAC", subtype="PCM_24") as out:
                for a, b in spans:
                    pos = a
                    while pos < b:
                        block = self.audio.read_block(pos, min(65536, b - pos))
                        if not len(block):
                            break
                        out.write(block)
                        pos += len(block)
        else:
            with open(path, "w+b") as out:
                write_wav_header(out, rate, channels, frames)
                for a, b in spans:
                    pos = a
                    while pos < b:
                        block = self.audio.read_block(pos, min(65536, b - pos))
                        if not len(block):
                            break
                        out.write(np.asarray(block, dtype="<f4").tobytes(order="C"))
                        pos += len(block)
            fix_wav_header(path)
        return path

    def export(self, output_path: str, bitrate_kbps: int = 320) -> str:
        return self._write(output_path, self.segments.copy(), bitrate_kbps)

    def export_selection(self, output_path: str, start_seconds: float, end_seconds: float,
                         bitrate_kbps: int = 320) -> str:
        start, end = self._frame(start_seconds), self._frame(end_seconds)
        if end <= start:
            raise ValueError("Select a time range longer than zero")
        return self._write(output_path, self._extract(start, end), bitrate_kbps)


def remove_audio_ranges_in_place(path: str, ranges: List[Tuple[float, float]],
                                 bitrate_kbps: int = 320) -> int:
    """Remove time ranges from a newly captured file, atomically replacing it.

    Ranges use the file's original timeline and are removed latest-to-earliest,
    so earlier timestamps remain valid after each cut.
    """
    source = os.path.abspath(path)
    audio = AudioFile(source)
    if audio.data is None and not audio.streaming:
        raise RuntimeError(audio.error or "Could not read the captured file for auto-trimming")
    session = AudioEditSession(audio)
    temp_path = None
    try:
        for start, end in sorted(ranges, key=lambda item: item[0], reverse=True):
            start = max(0.0, float(start))
            end = min(session.duration, float(end))
            if end > start and end - start < session.duration:
                session.remove(start, end)
        if session.duration_frames <= 0:
            raise ValueError("Auto-trimming would remove the entire recording")
        rate, remaining = audio.samplerate, session.duration_frames
        ext = Path(source).suffix or ".wav"
        fd, temp_path = tempfile.mkstemp(prefix=".audiocapture-trim-", suffix=ext,
                                         dir=os.path.dirname(source) or ".")
        os.close(fd)
        session.export(temp_path, bitrate_kbps=bitrate_kbps)
        audio.close()
        os.replace(temp_path, source)
        return remaining
    except Exception:
        audio.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise
