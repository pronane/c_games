"""Unit tests for server.fx effects library prototype."""
from __future__ import annotations

import numpy as np
import pytest

from server.fx.renderers import apply_effect, EFFECT_NAMES
from server.fx.features import extract_features, features_vector, FEATURE_NAMES
from server.fx.classify import EffectMatcher
from server.fx.undo import undo_effects, acoustic_playback, dereverb_spectral, damping_from_decay


SR = 44100


def _pluck(freq=220.0, dur=0.6, sr=SR):
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.exp(-3.5 * t)
    return (0.4 * env * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def test_all_effects_render_same_length():
    x = _pluck()
    for name in EFFECT_NAMES:
        y = apply_effect(name, x, sr=SR)
        assert len(y) == len(x)
        assert np.isfinite(y).all()
        assert np.max(np.abs(y)) > 0


def test_feature_vector_fixed_size():
    feats = extract_features(_pluck(), SR)
    assert list(feats.keys()) == list(FEATURE_NAMES)
    v = features_vector(feats)
    assert v.shape == (len(FEATURE_NAMES),)


def test_distortion_lowers_crest_vs_clean():
    x = _pluck()
    # add a few more notes so crest is meaningful
    x2 = np.concatenate([x, np.zeros(int(0.2 * SR)), 0.7 * _pluck(330), np.zeros(int(0.2 * SR)), 0.3 * _pluck(110)])
    c = extract_features(x2, SR)['crest_factor']
    d = extract_features(apply_effect('distortion', x2, sr=SR), SR)['crest_factor']
    assert d < c


def test_reverb_raises_late_energy_or_rt60():
    x = _pluck(dur=0.4)
    x = np.concatenate([x, np.zeros(int(1.5 * SR))])
    clean = extract_features(x, SR)
    wet = extract_features(apply_effect('reverb', x, sr=SR, rt60=1.4, mix=0.5), SR)
    assert wet['rt60_est_s'] >= clean['rt60_est_s'] * 0.8 or wet['late_energy_ratio'] > clean['late_energy_ratio']


def test_matcher_centroids_prefer_true_label():
    rng = np.random.default_rng(0)
    # Tiny synthetic set: clean vs distortion vs tremolo
    rows_x, rows_y = [], []
    for _ in range(5):
        base = _pluck(freq=float(rng.uniform(110, 440)))
        for name in ('clean', 'distortion', 'tremolo'):
            y = apply_effect(name, base, sr=SR) if name != 'clean' else base
            rows_x.append(features_vector(extract_features(y, SR)))
            rows_y.append(name)
    m = EffectMatcher()
    m.labels = list(EFFECT_NAMES)
    m.fit_centroids(np.stack(rows_x), rows_y)
    m.threshold = 0.3
    # Probe a new distortion
    probe = apply_effect('distortion', _pluck(196.0), sr=SR)
    out = m.predict(probe, SR)
    names = [e['name'] for e in out['effects']]
    assert 'distortion' in names or out['scores'].get('distortion', 0) >= out['scores'].get('clean', 0)


def test_undo_dereverb_runs():
    x = np.concatenate([_pluck(dur=0.5), np.zeros(int(1.0 * SR))])
    wet = apply_effect('reverb', x, sr=SR, rt60=1.2, mix=0.45)
    dry = dereverb_spectral(wet, SR, rt60=1.2)
    assert len(dry) == len(wet)
    assert np.isfinite(dry).all()


def test_acoustic_playback_keeps_damping_shorter():
    notes = [
        {'midi': 60, 'start': 0.0, 'end': 0.5, 'velocity': 0.8, 'damping': False},
        {'midi': 64, 'start': 0.55, 'end': 0.9, 'velocity': 0.8, 'damping': True},
    ]
    y = acoustic_playback(notes, sr=SR, length_s=1.2)
    assert len(y) >= int(1.1 * SR)
    # Muted note should have less late energy in its window
    i0 = int(0.55 * SR)
    i1 = int(0.9 * SR)
    seg = np.abs(y[i0:i1])
    w = int(0.03 * SR)
    assert np.mean(seg[-w:]) < np.mean(seg[:w])


def test_damping_heuristic():
    # Sharp decay pluck
    t = np.arange(int(0.25 * SR)) / SR
    x = 0.5 * np.exp(-25 * t) * np.sin(2 * np.pi * 220 * t)
    assert damping_from_decay(x, 0.0, 0.25, SR) is True
