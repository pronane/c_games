"""Waveform display + simple RMS-peak cache for fast drawing."""

from __future__ import annotations

import numpy as np
import tkinter as tk


class Waveform:
    """Draws either a live scrolling waveform or a whole-file overview."""

    #: how much recent audio the live view shows across its full width
    TOTAL_SPAN_SECONDS = 4.0

    def __init__(self, canvas: tk.Canvas, bg: str, color: str, midline: str,
                 empty_text: str = "No recording yet") -> None:
        self.canvas = canvas
        self.bg = bg
        self.color = color
        self.live_color = color
        self.midline = midline
        self.empty_text = empty_text
        self.canvas.configure(bg=bg, highlightthickness=0, bd=0)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self._mode = "empty"  # empty | live | file
        self._live: list = []  # list of (min,max) per column chunk
        self._live_cols = 0
        self._peaks = None  # np.array shape (cols, 2) for whole file
        self._peaks_key = None
        self._progress = 0.0
        self._duration = 0.0
        self._width_hint = 0
        self.live_follow = False  # True once real data arrives
        self._fill = 0.0          # seconds accumulated in the current column
        self._cur_min = 0.0
        self._cur_max = 0.0
        self.slice_seconds = 0.015

    # ------------------------------------------------------------ live mode
    def set_width_hint(self, px: int) -> None:
        self._width_hint = max(200, int(px))

    def reset_live(self) -> None:
        self._mode = "live"
        self._live = []
        self.live_follow = False
        self._fill = 0.0
        self._cur_min = self._cur_max = 0.0
        width = self.canvas.winfo_width()
        if width <= 10:
            width = self._width_hint or 600
        self._live_cols = max(40, int(width) // 2)
        # spread the last TOTAL_SPAN_SECONDS of audio over the full width
        self.slice_seconds = self.TOTAL_SPAN_SECONDS / float(self._live_cols)
        self._fill = 0.0
        self._redraw()

    def add_tick(self, frames: int, samplerate: int = 48000) -> None:
        """Advance the live view by ``frames`` worth of silence."""
        if self._mode != "live" or frames <= 0:
            return
        self._advance(frames / float(samplerate or 48000), 0.0, 0.0)

    def _advance(self, seconds: float, lo: float, hi: float) -> None:
        """Accumulate ``seconds`` of audio into pixel columns."""
        slice_s = max(0.0005, self.slice_seconds)
        remaining = seconds
        while remaining > 0:
            take = min(remaining, slice_s - self._fill)
            if lo < self._cur_min:
                self._cur_min = lo
            if hi > self._cur_max:
                self._cur_max = hi
            self._fill += take
            remaining -= take
            if self._fill >= slice_s - 1e-9:
                self._live.append((self._cur_min, self._cur_max))
                self._fill = 0.0
                self._cur_min = self._cur_max = 0.0
        if len(self._live) > self._live_cols:
            self._live = self._live[-self._live_cols:]

    def add_block(self, block: np.ndarray, samplerate: int = 48000) -> None:
        """Feed a mono or multi-channel float block of captured audio."""
        if block is None or len(block) == 0:
            return
        mono = block if block.ndim == 1 else block.mean(axis=1)
        self._advance(len(mono) / float(samplerate or 48000),
                      float(mono.min()), float(mono.max()))

    def tick(self) -> None:
        """Repaint the live view (throttled to ~8 fps by the caller)."""
        if self._mode == "live":
            self._redraw_live()

    # ----------------------------------------------------------- file mode
    def show_file(self, data, samplerate: int, peaks=None) -> None:
        """Draw a whole-file overview.

        ``data`` may be a decoded array (small files) or ``None`` for streamed
        files, in which case pre-computed ``peaks`` are used.
        """
        self._mode = "file"
        width = max(60, int(self.canvas.winfo_width() or 600))
        cols = width
        if peaks is not None:
            self._peaks = np.asarray(peaks, dtype=np.float32)
            self._duration = float(getattr(self, "_duration", 0.0))
            self._redraw()
            return
        if data is None:
            self._peaks = None
            self._redraw()
            return
        mono = data if data.ndim == 1 else data.mean(axis=1)
        if len(mono) == 0:
            self._peaks = None
            self._redraw()
            return
        # very short recordings: one bar per sample, repeated, not one bar total
        chunk = max(1, len(mono) // cols)
        usable = (len(mono) // chunk) * chunk
        blocks = mono[:usable].reshape(-1, chunk)
        mins = blocks.min(axis=1)
        maxs = blocks.max(axis=1)
        self._peaks = np.stack([mins, maxs], axis=1)
        self._duration = len(mono) / float(samplerate) if samplerate else 0.0
        self._redraw()

    def set_duration(self, seconds: float) -> None:
        self._duration = max(0.0, float(seconds))

    def set_progress(self, seconds: float) -> None:
        if self._duration:
            self._progress = max(0.0, min(1.0, seconds / self._duration))
            if self._mode == "file":
                self._redraw()

    def clear(self) -> None:
        self._mode = "empty"
        self._live = []
        self._peaks = None
        self._redraw()

    # -------------------------------------------------------------- drawing
    def _redraw(self) -> None:
        if self._mode == "live":
            self._redraw_live()
        else:
            self._redraw_file()

    def _redraw_live(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        mid = h / 2
        c.create_line(0, mid, w, mid, fill=self.midline)
        cols = self._live_cols
        data = self._live[-cols:]
        if not data:
            return
        x_step = w / float(max(1, cols - 1))
        # newest audio sits at the right edge; the trace scrolls leftwards
        x_start = x_step * (cols - len(data))
        for idx, (lo, hi) in enumerate(data):
            x = x_start + idx * x_step
            y1 = mid - hi * (h / 2 - 3)
            y2 = mid - lo * (h / 2 - 3)
            if abs(y2 - y1) < 1.2:
                y1 -= 0.6
                y2 += 0.6
            c.create_line(x, y1, x, y2, fill=self.live_color)
        # playhead marker at the right edge
        c.create_line(w - 1, 0, w - 1, h, fill="#334155")

    def _redraw_file(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        mid = h / 2
        if self._peaks is None:
            c.create_line(0, mid, w, mid, fill=self.midline)
            if self._mode == "empty":
                c.create_text(w / 2, mid, text=self.empty_text, fill="#6b7280",
                              font=("Segoe UI", 11))
            return
        # baseline
        c.create_line(0, mid, w, mid, fill=self.midline)
        peaks = self._peaks
        n = len(peaks)
        if n == 0:
            return
        played_cols = int(round(n * self._progress))
        for i in range(n):
            lo, hi = float(peaks[i][0]), float(peaks[i][1])
            x = (i + 0.5) * w / n
            y1 = mid - hi * (h / 2 - 3)
            y2 = mid - lo * (h / 2 - 3)
            if abs(y2 - y1) < 1.0:
                y1 -= 0.5
                y2 += 0.5
            color = self.color if i < played_cols else "#4b5563"
            c.create_line(x, y1, x, y2, fill=color)
        if 0 < self._progress < 1.0:
            xp = self._progress * w
            c.create_line(xp, 0, xp, h, fill="#22d3ee", width=2)
