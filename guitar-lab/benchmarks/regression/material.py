"""Deterministic audio for the fast regression clips.

The chart is the note list that was rendered. It is not passed to the
transcriber. Reverb is a fixed comb, so the wet file is the same performance
as the dry file.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from server.fx.playback import render_acoustic, render_distorted


def _scale():
    midi = [40, 45, 50, 55, 59, 64, 67, 64]
    return [{'time': 0.25 + i * 0.45, 'duration': 0.35, 'midi': m,
             'velocity': 0.8, 'amplitude': 0.8} for i, m in enumerate(midi)]


def _chug():
    ioi = 60 / 160 / 4  # 16ths at 160, the dense-onset case from PR #51
    return [{'time': 0.2 + i * ioi, 'duration': 0.05, 'midi': 40,
             'velocity': 0.85, 'amplitude': 0.85, 'palmMute': True, 'palm_mute': True}
            for i in range(12)]


def _phrase():
    midi = [64, 67, 71, 72, 71, 67]
    return [{'time': 0.3 + i * 0.4, 'duration': 0.32, 'midi': m, 'velocity': 0.8}
            for i, m in enumerate(midi)]


def apply_reverb(y, sr, mix=0.4):
    """One comb and one all-pass. No randomness."""
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 2:
        return np.stack([apply_reverb(y[:, c], sr, mix=mix) for c in range(y.shape[1])], axis=1)
    delay = max(8, int(0.029 * sr))
    b = np.zeros(delay + 1)
    b[0] = 1.0
    b[-1] = 0.62
    wet = signal.lfilter(b, [1.0], y)
    # First-order all-pass, coefficient fixed.
    wet = signal.lfilter([0.6, 1.0], [1.0, 0.6], wet)
    out = (1 - mix) * y + mix * wet
    peak = np.max(np.abs(out)) + 1e-12
    return (out / peak * 0.8).astype(np.float32)


def render_case(name, sr=22050):
    """Return (audio float32 mono, notes, voice)."""
    if name == 'ks_clean_scale':
        notes = _scale()
        y = render_acoustic(notes, sr=sr, length_s=notes[-1]['time'] + 1.2, stereo=False, body=True)
        return np.asarray(y, dtype=np.float32), notes, 'clean'
    if name == 'ks_dist_chug':
        notes = _chug()
        y = render_distorted(notes, sr=sr, length_s=notes[-1]['time'] + 0.8, stereo=False, drive='distorted')
        if getattr(y, 'ndim', 1) == 2:
            y = y.mean(axis=1)
        return np.asarray(y, dtype=np.float32), notes, 'distorted'
    if name in ('ks_clear', 'ks_reverb'):
        notes = _phrase()
        dry = render_acoustic(notes, sr=sr, length_s=notes[-1]['time'] + 1.4, stereo=False, body=True)
        dry = np.asarray(dry, dtype=np.float32)
        if name == 'ks_clear':
            return dry, notes, 'clean'
        return apply_reverb(dry, sr, mix=0.45), notes, 'reverb'
    raise KeyError(name)
