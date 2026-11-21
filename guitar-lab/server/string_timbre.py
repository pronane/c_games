"""Which string a note was played on, heard from the recording.

The same pitch sounds different on different strings: a wound low string fretted high is darker
and less harmonic than an open or low-fret note on a thinner string. This measures each note's
harmonic profile just after it starts (levels of harmonics 2-16 against the fundamental, and how
far the upper harmonics sit from exact multiples) and a small gradient-boosted tree model turns
that, with the pitch, into a probability for each string. The fingering search
(song_analysis.fingering) weighs it against hand movement.

Trained on GuitarSet (CC BY 4.0, Xi et al. 2018: 6 players, hexaphonic string annotations) by
``training/string_timbre_train.py``. Tested on players it never saw (leave one player out): the
right string for 77% of notes from timbre and pitch, against 63% from pitch alone (81% vs 62% on
single-note lines). Standard tuning only: the model is not used for other tunings.

The model is stored as plain arrays (server/data/string_timbre.npz) and evaluated with NumPy;
nothing is unpickled.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 22050
HARMONICS = 16
STANDARD = [64, 59, 55, 50, 45, 40]       # string 1 (high e) first
MAX_FRET = 20
MODEL = Path(__file__).resolve().parent/'data'/'string_timbre.npz'


def note_features(audio, sr, note):
    """Harmonic profile of one note, or None when the note is too short to measure."""
    f0 = 440.0*2**((note['midi']-69)/12)
    a = int((note['time']+.03)*sr)
    b = int((note['time']+min(.15, max(.06, note['duration'])))*sr)
    seg = audio[max(0, a):b]
    if len(seg) < 512 or a < 0:
        return None
    spec = np.abs(np.fft.rfft(seg*np.hanning(len(seg)), n=16384))
    freqs = np.fft.rfftfreq(16384, 1/sr)
    levels, cents = [], []
    for k in range(1, HARMONICS+1):
        fk = f0*k
        if fk > sr/2-200:
            levels.append(-80.0)
            cents.append(0.0)
            continue
        lo, hi = np.searchsorted(freqs, fk*.97), np.searchsorted(freqs, fk*1.03)
        i = lo+int(np.argmax(spec[lo:hi])) if hi > lo else lo
        levels.append(20*np.log10(spec[i]+1e-9))
        cents.append((freqs[i]/fk-1)*1200 if k > 1 else 0.0)
    levels = np.array(levels)-levels[0]
    midi = note['midi']
    frets = np.array([midi-o for o in STANDARD], dtype=float)
    return np.concatenate([levels[1:], np.array(cents[1:9]), [midi], frets])


def features(audio, sr, notes):
    """Feature rows for the notes (None where a note cannot be measured)."""
    import librosa
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    return [note_features(audio, SR, n) for n in notes]


def load(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


@lru_cache(maxsize=1)
def _model():
    return load(MODEL) if MODEL.is_file() else None


def available():
    return _model() is not None


def _raw(m, X):
    """Sum of the trees' outputs per class (HistGradientBoosting layout, numeric splits only)."""
    n_classes = int(m['n_classes'])
    raw = np.tile(m['baseline'].reshape(1, -1), (len(X), 1)).astype(float)
    offsets = m['tree_offsets']
    for t in range(len(offsets)-1):
        lo = offsets[t]
        feature, threshold = m['feature'][lo:offsets[t+1]], m['threshold'][lo:offsets[t+1]]
        left, right, leaf = m['left'][lo:offsets[t+1]], m['right'][lo:offsets[t+1]], m['is_leaf'][lo:offsets[t+1]]
        missing_left, value = m['missing_left'][lo:offsets[t+1]], m['value'][lo:offsets[t+1]]
        node = np.zeros(len(X), dtype=int)
        active = ~leaf[node]
        while active.any():
            idx = np.nonzero(active)[0]
            nd = node[idx]
            x = X[idx, feature[nd]]
            go_left = np.where(np.isnan(x), missing_left[nd], x <= threshold[nd])
            node[idx] = np.where(go_left, left[nd], right[nd])
            active = ~leaf[node]
        raw[:, t % n_classes] += value[node]
    return raw


def string_probs(audio, sr, notes, open_strings=None, model=None):
    """Per note: probabilities for strings 1..6 (high e first), or None where not measured.

    Only for standard tuning; returns all None for other tunings or when the model is missing.
    """
    m = model if model is not None else _model()
    if m is None or (open_strings is not None and list(open_strings) != STANDARD) or not notes:
        return [None]*len(notes)
    rows = features(audio, sr, notes)
    keep = [i for i, r in enumerate(rows) if r is not None]
    out = [None]*len(notes)
    if not keep:
        return out
    X = np.array([rows[i] for i in keep], dtype=float)
    raw = _raw(m, X)
    p = np.exp(raw-raw.max(axis=1, keepdims=True))
    p /= p.sum(axis=1, keepdims=True)
    classes = m['classes']
    frets = X[:, -6:]
    for row, i in enumerate(keep):
        full = np.zeros(6)
        for c, s in enumerate(classes):
            full[int(s)-1] = p[row, c]
        full *= (frets[row] >= 0) & (frets[row] <= MAX_FRET+4)
        total = full.sum()
        out[i] = [round(float(v/total), 4) for v in full] if total > 0 else None
    return out
