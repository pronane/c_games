"""Check a tab against the recording, note by note.

Finding notes from nothing is hard; confirming a note someone already wrote down is much
easier. Once a tab is lined up with the recording (tab_align), each tab note is looked up in
Riley's onset map: does that pitch start there? On guitar with known notes this confirms
most real notes and almost no wrong-pitch ones (benchmarks/regression/RESULTS.md).

Each stretch of the song also gets a control: the same notes moved a fraction of a second
off. Where the real positions score no better than the moved ones, the tab and the recording
do not agree there (wrong line-up, a different arrangement, or a sound the detector cannot
hear), and the stretch is reported as not confirmed instead of guessed at.
"""
from __future__ import annotations

import numpy as np

FPS = 100                 # Riley's frame rate
LOW = 21                  # MIDI pitch of column 0
ONSET = 0.3               # onset probability that counts as "this pitch starts here"
REACH = 5                 # frames either side (±50 ms, the benchmark onset tolerance)
STRETCH_S = 20.0
# A stretch is confirmed when most notes are found and clearly more than in the control.
CONFIRMED, MARGIN, NO_MARGIN = 0.6, 0.3, 0.15


def onset_map(audio: np.ndarray, sr: int) -> np.ndarray:
    """Riley's onset probabilities (frames x 88), each widened by ±REACH frames."""
    import librosa
    from . import riley
    y = audio if audio.ndim == 1 else audio.mean(axis=1)
    y = np.asarray(y, dtype=np.float32)
    if sr != riley.SAMPLE_RATE:
        y = librosa.resample(y, orig_sr=sr, target_sr=riley.SAMPLE_RATE)
    return widen(riley.posteriors(y)['reg_onset_output'])


def widen(onset: np.ndarray) -> np.ndarray:
    out = onset.copy()
    for d in range(1, REACH + 1):
        out[d:] = np.maximum(out[d:], onset[:-d])
        out[:-d] = np.maximum(out[:-d], onset[d:])
    return out


def evidence(onsets: np.ndarray, times, midi) -> np.ndarray:
    """Onset probability at each (time, pitch); 0 outside the map."""
    i = np.round(np.asarray(times, float) * FPS).astype(int)
    k = np.asarray(midi, int) - LOW
    ok = (i >= 0) & (i < len(onsets)) & (k >= 0) & (k < onsets.shape[1])
    out = np.zeros(len(i), np.float32)
    out[ok] = onsets[i[ok], k[ok]]
    return out


def check(placed: list, onsets: np.ndarray, stretch_s: float = STRETCH_S, seed: int = 0) -> dict:
    """Mark every placed tab note confirmed or not, and say where the tab holds.

    placed: tab_align.place_tracks output (notes on the recording's clock, sounding pitch).
    Adds 'confirmed' to each note in place. Returns per-part shares and per-stretch verdicts:
    {'parts': [{'name', 'notes', 'confirmed'}] (same order as placed), 'stretches': [{'start', 'end', 'notes',
    'confirmed', 'control', 'status'}], 'confirmed': overall share}."""
    rng = np.random.default_rng(seed)
    parts, rows = [], []
    for tr in placed:
        notes = tr['notes']
        got = evidence(onsets, [n['time'] for n in notes], [n['midi'] for n in notes]) > ONSET if notes else np.zeros(0, bool)
        for n, g in zip(notes, got):
            n['confirmed'] = bool(g)
            rows.append((n['time'], n['midi'], bool(g)))
        parts.append({'name': tr['name'], 'notes': len(notes), 'confirmed': round(float(got.mean()), 3) if len(got) else 0.0})
    if not rows:
        return {'parts': parts, 'stretches': [], 'confirmed': 0.0}
    t = np.array([r[0] for r in rows]); m = np.array([r[1] for r in rows]); g = np.array([r[2] for r in rows])
    # Control: the same notes 150-400 ms early or late.
    moved = evidence(onsets, t + rng.choice([-1.0, 1.0], len(t)) * rng.uniform(0.15, 0.4, len(t)), m) > ONSET
    stretches = []
    for a in np.arange(np.floor(t.min() / stretch_s) * stretch_s, t.max() + 1e-6, stretch_s):
        sel = (t >= a) & (t < a + stretch_s)
        if sel.sum() < 8:
            continue
        real, control = float(g[sel].mean()), float(moved[sel].mean())
        status = ('confirmed' if real >= CONFIRMED and real - control >= MARGIN
                  else 'not_confirmed' if real - control < NO_MARGIN else 'partly')
        stretches.append({'start': float(a), 'end': float(a + stretch_s), 'notes': int(sel.sum()),
                          'confirmed': round(real, 3), 'control': round(control, 3), 'status': status})
    return {'parts': parts, 'stretches': merge(stretches), 'confirmed': round(float(g.mean()), 3)}


def merge(stretches: list) -> list:
    """Neighbouring stretches with the same verdict become one (note-weighted shares)."""
    out = []
    for s in stretches:
        last = out[-1] if out else None
        if last and last['status'] == s['status'] and abs(last['end'] - s['start']) < 1e-6:
            n = last['notes'] + s['notes']
            for key in ('confirmed', 'control'):
                last[key] = round((last[key] * last['notes'] + s[key] * s['notes']) / n, 3)
            last['notes'], last['end'] = n, s['end']
        else:
            out.append(dict(s))
    return out
