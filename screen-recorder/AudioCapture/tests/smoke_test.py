"""Smoke test: fake audio backend -> record -> trim -> analyse.

This runs the real Recorder/Player/WAV code paths without audio hardware.
"""

import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audiocapture.recorder import (  # noqa: E402
    AudioFile,
    Recorder,
    fix_wav_header,
    wav_duration,
    write_silent_wav,
)


class FakeDevice:
    """Pretends to be a soundcard microphone (e.g. WASAPI loopback)."""

    def __init__(self, samplerate=48000, channels=2, freq=440.0):
        self.samplerate = samplerate
        self.channels = channels
        self.freq = freq
        self.phase = 0.0

    def recorder(self, samplerate, channels=None, blocksize=None):
        return FakeRecorder(self, samplerate, channels)


class FakeRecorder:
    def __init__(self, dev, samplerate, channels):
        self.dev, self.samplerate, self.channels = dev, samplerate, channels

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def record(self, numframes, **_kw):
        time.sleep(numframes / float(self.samplerate))  # behave like real hardware
        t = np.arange(numframes) / self.samplerate + self.dev.phase
        self.dev.phase += numframes / self.samplerate
        sig = 0.5 * np.sin(2 * np.pi * self.dev.freq * t)
        data = np.stack([sig, sig * 0.5], axis=1)
        return data.astype(np.float32)


def test_record_and_read():
    tmp = "/tmp/test_rec"
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for container in ("WAV", "FLAC"):
        path = os.path.join(tmp, f"smoke_{container.lower()}"
                                 + (".wav" if container == "WAV" else ".flac"))
        for p in (path,):
            if os.path.exists(p):
                os.remove(p)
        rec = Recorder(FakeDevice(), path, 48000, 2, container)
        rec.start()
        time.sleep(1.2)
        info = rec.stop()
        assert os.path.exists(info.path), f"{container}: file missing"
        assert info.frames > 40000, f"{container}: too few frames {info.frames}"
        print(f"{container}: {info.frames} frames, {info.duration:.2f}s, "
              f"peak {info.peak_db:.1f} dBFS, {info.size_bytes/1e6:.2f} MB, "
              f"fallback={info.fallback_reason}")
        paths.append(info.path)
        # read it back the way the player does
        audio = AudioFile(info.path)
        assert audio.data is not None, audio.error
        print(f"   read back: {audio.samplerate} Hz, {audio.channels} ch, "
              f"{audio.duration:.2f}s, peak={np.max(np.abs(audio.data)):.3f}")
        assert abs(audio.duration - info.duration) < 0.1, "duration mismatch"
        assert audio.samplerate == 48000 and audio.channels == 2
        assert np.max(np.abs(audio.data)) > 0.3, "signal lost"
        # header sanity for WAV
        if info.path.endswith(".wav"):
            with open(info.path, "rb") as fh:
                head = fh.read(64)
            assert head[:4] == b"RIFF" and head[8:12] == b"WAVE"
            data_size = int.from_bytes(head[40:44], "little")
            assert data_size == os.path.getsize(info.path) - 44, "bad data chunk size"
            fmt = int.from_bytes(head[20:22], "little")
            assert fmt == 3, f"expected IEEE float, got {fmt}"
            print(f"   WAV: float32, data chunk {data_size} bytes OK")
        # duration helper
        d = wav_duration(info.path)
        assert abs(d - info.duration) < 0.1, f"wav_duration mismatch {d} vs {info.duration}"
    return paths


def test_pause_resume_excludes_paused_interval():
    path = "/tmp/test_rec/pause_resume.wav"
    if os.path.exists(path):
        os.remove(path)
    rec = Recorder(FakeDevice(), path, 48000, 2, "WAV")
    rec.start()
    time.sleep(0.35)
    rec.pause()
    assert rec.paused
    before = rec.frames
    time.sleep(0.45)
    after = rec.frames
    assert after - before < 48000 * 0.12, "capture kept advancing while paused"
    rec.resume()
    assert not rec.paused
    time.sleep(0.35)
    info = rec.stop()
    assert 0.45 < info.duration < 0.9, f"paused time included: {info.duration:.2f}s"
    print(f"pause/resume test: {info.duration:.2f}s captured around a 0.45s pause")


def test_silent_file():
    path = "/tmp/test_rec/silent.wav"
    write_silent_wav(path, 44100, 2)
    audio = AudioFile(path)
    assert audio.data is not None and audio.samplerate == 44100
    print(f"silent file: {audio.duration:.2f}s OK")


def test_16bit_and_24bit_wav():
    """Player must read ordinary 16/24-bit WAVs too (e.g. files you already have)."""
    import struct
    for width, fmt in ((2, 1), (3, 1)):
        path = f"/tmp/test_rec/pcm{width*8}.wav"
        n = 4800
        t = np.arange(n) / 48000
        sig = (0.5 * np.sin(2 * np.pi * 220 * t))
        if width == 2:
            raw = (sig * 32767).astype("<i2").tobytes()
        else:
            ints = (sig * 8388607).astype(np.int32)
            raw = b"".join(int(v & 0xFFFFFF).to_bytes(3, "little") for v in ints)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(width)
            wf.setframerate(48000)
            wf.writeframes(raw)
        audio = AudioFile(path)
        assert audio.data is not None, audio.error
        assert abs(np.max(np.abs(audio.data)) - 0.5) < 0.02, "amplitude wrong"
        print(f"pcm{width*8}.wav read: peak {np.max(np.abs(audio.data)):.3f} OK")




class BurstDevice(FakeDevice):
    """Mimics a device that delivers buffered audio in bursts (PulseAudio).

    Real behaviour observed on Linux: the monitor source hands back several
    blocks instantly, then pauses.  No audio may ever be dropped in that case -
    the file must grow by exactly the frames delivered.
    """

    def recorder(self, samplerate, channels=None, blocksize=None):
        return BurstRecorder(self, samplerate, channels, blocksize)


class BurstRecorder(FakeRecorder):
    def __init__(self, dev, samplerate, channels, blocksize):
        super().__init__(dev, samplerate, channels)
        self.bs = blocksize or 1024
        self.n = 0

    def record(self, numframes, **_kw):
        self.n += 1
        if self.n % 10 == 0:
            time.sleep(0.5)          # buffers up
            return np.full((numframes * 8, 2), 0.1, dtype=np.float32)  # burst!
        time.sleep(numframes / float(self.samplerate))
        return np.zeros((numframes, 2), dtype=np.float32)


def test_bursts_are_never_dropped():
    path = "/tmp/test_rec/burst.wav"
    if os.path.exists(path):
        os.remove(path)
    rec = Recorder(BurstDevice(), path, 48000, 2, "WAV", blocksize=1024)
    rec.start()
    time.sleep(2.2)
    info = rec.stop()
    audio = AudioFile(info.path)
    peak = float(np.max(np.abs(audio.data)))
    print(f"burst test: {info.frames} frames kept, peak {peak:.2f} (burst audio kept)")
    # the 0.1-amplitude bursts must still be present in the file
    assert peak > 0.09, "burst audio was dropped!"
    assert info.frames > 48000 * 1.5, "too little audio captured"


class StallingDevice(FakeDevice):
    """Delivers nothing for gaps (like WASAPI loopback when idle)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0

    def recorder(self, samplerate, channels=None, blocksize=None):
        return StallingRecorder(self, samplerate, channels)


class StallingRecorder(FakeRecorder):
    def record(self, numframes, **_kw):
        self.dev.calls += 1
        # every third pull: stall for 0.5 s and return empty (silence)
        if self.dev.calls % 3 == 0:
            time.sleep(0.5)
            return np.zeros((0, 2), dtype=np.float32)
        return super().record(numframes)


def test_silence_gap_timeline():
    path = "/tmp/test_rec/gap.wav"
    if os.path.exists(path):
        os.remove(path)
    rec = Recorder(StallingDevice(), path, 48000, 2, "WAV")
    t0 = time.time()
    rec.start()
    time.sleep(2.0)
    info = rec.stop()
    wall = time.time() - t0
    print(f"gap test: recorded {info.duration:.2f}s over {wall:.2f}s wall clock "
          f"({info.frames} frames)")
    # Stalls get padded with silence, so the file length must stay close to the
    # wall clock (a small undershoot is expected for the final partial stall,
    # which is not padded once stop() is pressed).
    assert wall - 0.4 < info.duration <= wall + 0.1, (
        f"timeline mismatch: file {info.duration:.2f}s vs wall {wall:.2f}s")
    audio = AudioFile(info.path)
    assert audio.data is not None
    print(f"gap test read back: {audio.duration:.2f}s, "
          f"silent fraction {(np.abs(audio.data).max(axis=1) < 1e-6).mean()*100:.0f}%")


if __name__ == "__main__":
    test_record_and_read()
    test_pause_resume_excludes_paused_interval()
    test_silent_file()
    test_16bit_and_24bit_wav()
    test_silence_gap_timeline()
    test_bursts_are_never_dropped()
    print("ALL SMOKE TESTS PASSED")
