"""Random amp chains for re-amping clean guitar into crunch / high-gain tones (pedalboard).

Each chain: tighten lows -> drive (clipping or distortion) -> amp-style EQ (mid scoop or push)
-> speaker-cabinet roll-off -> optional compressor and short room. Settings are drawn per clip
so the model hears many amps, not one."""
from __future__ import annotations

import numpy as np


def chain(rng: np.random.Generator, style: str):
    from pedalboard import (Compressor, Distortion, HighpassFilter, LowpassFilter, Pedalboard, PeakFilter,
                            Reverb, Gain)
    drive = {'crunch': rng.uniform(12, 22), 'high_gain': rng.uniform(28, 45)}[style]
    boards = [HighpassFilter(cutoff_frequency_hz=rng.uniform(70, 160)),
              Gain(gain_db=rng.uniform(0, 6)),
              Distortion(drive_db=drive),
              PeakFilter(cutoff_frequency_hz=rng.uniform(400, 900), gain_db=rng.uniform(-8, 3), q=rng.uniform(0.5, 1.5)),
              PeakFilter(cutoff_frequency_hz=rng.uniform(1800, 3500), gain_db=rng.uniform(0, 6), q=rng.uniform(0.7, 2)),
              LowpassFilter(cutoff_frequency_hz=rng.uniform(4000, 7000)),
              LowpassFilter(cutoff_frequency_hz=rng.uniform(5000, 9000))]
    if rng.random() < 0.6:
        boards.append(Compressor(threshold_db=rng.uniform(-24, -10), ratio=rng.uniform(2, 6)))
    if rng.random() < 0.35:
        boards.append(Reverb(room_size=rng.uniform(0.05, 0.35), wet_level=rng.uniform(0.05, 0.2), dry_level=0.9))
    return Pedalboard(boards)


def reamp(y: np.ndarray, sr: int, rng: np.random.Generator, style: str) -> np.ndarray:
    """The clip through a fresh random chain. Input is normalised first (DI level); a chain
    that produces non-finite or silent output (rare filter blow-ups) is redrawn."""
    x = np.nan_to_num(y.astype(np.float32))
    x = x / (np.abs(x).max() + 1e-9) * 0.5
    for _ in range(5):
        out = np.asarray(chain(rng, style)(x[None, :], sr)[0], dtype=np.float32)
        peak = np.abs(out).max() if np.isfinite(out).all() else 0.0
        if peak > 1e-4:
            return (out / peak * rng.uniform(0.3, 0.9)).astype(np.float32)
    raise RuntimeError('No working amp chain for this clip.')
