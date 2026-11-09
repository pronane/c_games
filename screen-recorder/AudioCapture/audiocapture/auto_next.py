"""Silence-based auto-advance policy for web URL playlists."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SilenceAutoAdvance:
    """Trigger once after a per-URL grace period plus continuous silence."""
    delay_seconds: float = 150.0
    silence_seconds: float = 5.0
    threshold_rms: float = 0.002
    url_started_at: Optional[float] = None
    audio_started_at: Optional[float] = None
    silence_started_at: Optional[float] = None
    paused_at: Optional[float] = None
    triggered: bool = False

    def reset(self, now: float) -> None:
        self.url_started_at = float(now)
        self.audio_started_at = None
        self.silence_started_at = None
        self.paused_at = None
        self.triggered = False

    def pause(self, now: Optional[float] = None) -> None:
        # Paused wall time is not playback time or playback silence.
        if self.paused_at is None and now is not None:
            self.paused_at = float(now)
        self.silence_started_at = None

    def update(self, now: float, rms: float, *, enabled: bool = True,
               paused: bool = False) -> bool:
        if not enabled or self.url_started_at is None or self.triggered:
            return False
        now = float(now)
        if paused:
            self.pause(now)
            return False
        if self.paused_at is not None:
            paused_duration = max(0.0, now - self.paused_at)
            self.url_started_at += paused_duration
            if self.audio_started_at is not None:
                self.audio_started_at += paused_duration
            self.paused_at = None
        if float(rms) >= self.threshold_rms:
            if self.audio_started_at is None:
                self.audio_started_at = now
            self.silence_started_at = None
            return False
        baseline = self.audio_started_at if self.audio_started_at is not None else self.url_started_at
        if now - baseline < self.delay_seconds:
            self.silence_started_at = None
            return False
        if self.silence_started_at is None:
            self.silence_started_at = now
            return False
        if now - self.silence_started_at >= self.silence_seconds:
            self.triggered = True
            return True
        return False
