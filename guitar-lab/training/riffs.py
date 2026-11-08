"""Original heavy riffs with known notes: power chords, palm-muted chugs, fast 16ths,
gallops and single-note lines, often double-tracked (two takes, a few ms and cents apart).
Rendered with a plucked-string model, then re-amped. All material is generated here."""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

SR = 16000
TUNINGS = {'E': [40, 45, 50, 55, 59, 64], 'Eb': [39, 44, 49, 54, 58, 63], 'D': [38, 45, 50, 55, 59, 64],
           'C#': [37, 44, 49, 54, 58, 63]}


def pluck(midi: float, dur: float, rng, palm: bool, sr=SR) -> np.ndarray:
    hz = 440 * 2 ** ((midi - 69) / 12)
    n_total = int((dur + (0.08 if palm else 0.6)) * sr)
    N = max(2, int(round(sr / hz)))
    burst = rng.standard_normal(N + 1)
    burst = lfilter([0.5 if palm else 0.65], [1, -(0.5 if palm else 0.35)], burst)
    x = np.zeros(n_total); x[:N + 1] = burst
    loss = 0.94 if palm else min(0.9995, 0.9985 - 1.2e-6 * hz)
    a = np.zeros(N + 2); a[0] = 1; a[N] = -loss * 0.5; a[N + 1] = -loss * 0.5
    y = lfilter([1.0], a, x)
    held = int(dur * sr)
    if held < n_total:
        y[held:] *= np.exp(-np.arange(n_total - held) / (0.03 * sr))
    return y


def riff(rng, bars=4):
    """One riff as notes: (time, duration, midi, palm). Tempo 90-220 BPM, 4/4."""
    bpm = float(rng.uniform(90, 220))
    beat = 60 / bpm
    tuning = TUNINGS[rng.choice(list(TUNINGS))]
    low = tuning[0]
    kind = rng.choice(['chug', 'gallop', 'power', 'lead', 'mixed'])
    notes, t = [], 0.0
    sub = {'chug': 4, 'gallop': 4, 'power': 2, 'lead': 4, 'mixed': 4}[kind]
    step = beat / sub
    scale = [0, 2, 3, 5, 7, 8, 10, 12, 14, 15, 17, 19]
    for i in range(bars * 4 * sub):
        if kind == 'gallop' and i % 4 == 1:
            t += step; continue
        r = rng.random()
        if kind in ('chug', 'gallop') or (kind == 'mixed' and r < 0.6):
            if rng.random() < 0.8:
                notes.append((t, step * 0.9, low, True))
            else:
                root = low + int(rng.choice([0, 1, 3, 5, 6, 7]))
                for iv in (0, 7, 12):
                    notes.append((t, step * 1.8, root + iv, False))
        elif kind == 'power' or (kind == 'mixed' and r < 0.85):
            root = tuning[int(rng.integers(0, 2))] + int(rng.integers(0, 8))
            for iv in (0, 7, 12) if rng.random() < 0.7 else (0, 7):
                notes.append((t, step * 0.95, root, False) if iv == 0 else (t, step * 0.95, root + iv, False))
        else:
            if rng.random() < 0.85:
                notes.append((t, step * 0.9, tuning[2] + int(rng.choice(scale)), False))
        t += step
    return bpm, notes, t


def render(notes, length, rng, takes: int):
    """Mono mix of `takes` performances of the same notes (double tracking)."""
    out = np.zeros(int((length + 1) * SR))
    for k in range(takes):
        cents = rng.normal(0, 6)
        for (t, d, m, palm) in notes:
            jitter = rng.normal(0, 0.006) if takes > 1 else 0.0
            a = int(max(0, t + jitter) * SR)
            y = pluck(m + cents / 100, d, rng, palm) * rng.uniform(0.6, 1.0) * (1.3 if palm else 1.0)
            out[a:a + len(y)] += y[: len(out) - a]
    return out.astype(np.float32)
