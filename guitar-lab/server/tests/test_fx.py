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


# --- IDMT-trained library (derived features only) ---------------------------------------

def test_templates_json_is_small_and_has_the_trained_forest():
    import json
    from server.fx.classify import DEFAULT_TEMPLATES
    assert DEFAULT_TEMPLATES.stat().st_size < 5 * 1024 * 1024
    data = json.loads(DEFAULT_TEMPLATES.read_text())
    assert data['feature_names'] == list(FEATURE_NAMES)
    assert len(data['forest']['labels']) == 12 and 'clean' in data['forest']['labels']
    assert data['eval']['top1'] >= 0.85  # guitar-held-out IDMT score recorded at export time
    assert len(data['mean']) == len(FEATURE_NAMES)


def test_forest_probabilities_are_a_distribution():
    m = EffectMatcher()
    p = m.forest_proba(features_vector(extract_features(_pluck(), SR)))
    assert p.shape == (12,) and abs(p.sum() - 1) < 1e-6 and (p >= 0).all()


def test_hard_clipping_raises_the_distortion_score():
    # Synthetic sine plucks are out of the IDMT training domain (their top label is often
    # feedback_delay), so only the direction of the distortion score is asserted here.
    m = EffectMatcher()
    dry = _pluck(196.0, dur=2.0)
    wet = np.tanh(25 * dry) * 0.5
    assert m.predict(wet, SR)['scores']['distortion'] > m.predict(dry, SR)['scores']['distortion']


def test_exported_tree_matches_sklearn():
    pytest.importorskip('sklearn')
    from server.fx.train_idmt import export_tree, fit_forest
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, len(FEATURE_NAMES)))
    y = (X[:, 0] > 0).astype(int) + 2 * (X[:, 3] > 0.5)
    rf = fit_forest(X, y, n_trees=5, leaves=16)
    m = EffectMatcher()
    m.mean, m.std = np.zeros(len(FEATURE_NAMES)), np.ones(len(FEATURE_NAMES))
    m.forest = {'labels': list('abcd') + ['x'] * 8, 'trees': [export_tree(e, 12) for e in rf.estimators_]}
    ok = np.mean([np.argmax(m.forest_proba(v)) == p for v, p in zip(X[:50], rf.predict(X[:50]))])
    assert ok >= 0.95


def test_long_audio_is_classified_in_windows():
    m = EffectMatcher()
    x = np.concatenate([_pluck(220.0, dur=2.0) for _ in range(5)])
    out = m.predict(x, SR)
    assert out['model'] == 'forest' and out['windows'] >= 3


def test_low_confidence_delay_guess_does_not_dereverb():
    # Real clean amp takes were mislabelled feedback_delay at low confidence; de-reverb then
    # shortened sustained notes. Undo is now gated on confidence.
    x = _pluck(220.0, dur=1.5)
    y = undo_effects(x, SR, effects=[{'name': 'feedback_delay', 'confidence': 0.3}], features={'rt60_est_s': 0.3})
    assert np.allclose(y, x)
    z = undo_effects(x, SR, effects=[{'name': 'reverb', 'confidence': 0.9}], features={'rt60_est_s': 0.3})
    assert not np.allclose(z, x)
