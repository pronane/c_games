"""Non-destructive, frame-accurate audio editing and streaming export."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

import numpy as np

from .recorder import AudioFile, _sf, fix_wav_header, write_wav_header

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

    def _write(self, output_path: str, spans: List[Span]) -> str:
        path = os.path.abspath(output_path)
        if os.path.abspath(self.audio.path) == path:
            raise ValueError("Choose a new filename; the original recording is never overwritten")
        frames = sum(b - a for a, b in spans)
        if frames <= 0:
            raise ValueError("The selected edit is empty")
        ext = Path(path).suffix.lower()
        channels, rate = self.audio.channels, self.audio.samplerate
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if ext == ".flac":
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

    def export(self, output_path: str) -> str:
        return self._write(output_path, self.segments.copy())

    def export_selection(self, output_path: str, start_seconds: float, end_seconds: float) -> str:
        start, end = self._frame(start_seconds), self._frame(end_seconds)
        if end <= start:
            raise ValueError("Select a time range longer than zero")
        return self._write(output_path, self._extract(start, end))
