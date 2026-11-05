"""Second-stage note filter for processed (crunch/distorted) guitar.

Basic Pitch is run at low candidate thresholds with posteriors; a small gradient-boosted
tree model (JSON, no audio) scores every candidate on posterior, harmonic-relation and
effect-detector features and keeps the ones predicted to be real notes. This recovers
notes the strict distorted thresholds miss and drops ghosts / octave artefacts.

Tone-aware and opt-in: only used for crunch/distorted audio, and only when
FRETWORK_CLEAN_MODEL=1 (see README accuracy notes for why it is off by default).
Training/eval harness: benchmarks/clean_model.py.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

CANDIDATE_THRESHOLDS = (0.3, 0.2)
MODEL_PATH = Path(__file__).with_name('fx') / 'data' / 'clean_model.json'
FX_LABELS = ('clean', 'distortion', 'overdrive', 'chorus', 'flanger', 'phaser', 'tremolo', 'vibrato',
             'reverb', 'feedback_delay', 'slapback_delay', 'eq')
REL = (-24, -19, -12, -7, 7, 12, 19, 24)
FEATURE_NAMES = (['midi', 'dur', 'log_dur', 'amp', 'on_post', 'note_post', 'on_post_prev', 'n_sim', 'amp_rank',
                  'amp_rel', 'poly_post', 'gap_prev_same']
                 + [f'note_post_{r:+d}' for r in REL] + [f'sim_{r:+d}' for r in REL]
                 + [f'fx_{k}' for k in FX_LABELS] + ['amp_norm', 'on_post_norm', 'note_post_norm'])


def enabled() -> bool:
    return os.environ.get('FRETWORK_CLEAN_MODEL', '0') == '1' and MODEL_PATH.exists()


def active_for(tone: str | None) -> bool:
    return enabled() and tone in ('crunch', 'distorted')


def clip_fx_vector(det: dict | None) -> np.ndarray:
    sc = (det or {}).get('scores') or {}
    return np.array([float(sc.get(k, 0.0)) for k in FX_LABELS])


def candidate_features(cand, post, fxv) -> np.ndarray:
    on, note, hop = np.asarray(post['onset']), np.asarray(post['note']), float(post['hop'])
    T = len(on)
    rows = []
    times = np.array([n['time'] for n in cand]) if cand else np.zeros(0)
    for i, n in enumerate(cand):
        k = n['midi'] - 21
        f0 = min(int(round(n['time'] / hop)), T - 1)
        f1 = min(max(int(round((n['time'] + n['duration']) / hop)), f0 + 1), T)
        sl = slice(max(f0 - 2, 0), min(f0 + 3, T))
        def npost(kk):
            return float(note[f0:f1, kk].mean()) if 0 <= kk < 88 else 0.0
        sim = [j for j in np.nonzero(np.abs(times - n['time']) <= 0.05)[0] if j != i]
        amps = [cand[j]['amplitude'] for j in sim]
        simp = {cand[j]['midi'] - n['midi'] for j in sim}
        same = [cand[j]['time'] for j in range(i) if cand[j]['midi'] == n['midi']]
        rows.append([n['midi'], n['duration'], np.log(max(n['duration'], 1e-3)), n['amplitude'],
                     float(on[sl, k].max()), npost(k), float(on[max(f0 - 6, 0):max(f0 - 2, 1), k].max()) if f0 > 2 else 0.0,
                     len(sim), sum(a > n['amplitude'] for a in amps), n['amplitude'] / max([n['amplitude']] + amps),
                     float((note[f0] > 0.5).sum()), (n['time'] - same[-1]) if same else 5.0]
                    + [npost(k + r) for r in REL] + [float(r in simp) for r in REL] + list(fxv))
    X = np.asarray(rows, dtype=np.float32).reshape(len(cand), len(FEATURE_NAMES) - 3)
    return add_clip_normalised(X)


def add_clip_normalised(X):
    """Append amplitude / posteriors relative to the clip median (level-independent cues)."""
    if not len(X):
        return np.zeros((0, X.shape[1] + 3), np.float32)
    med = np.median(X[:, 3:6], axis=0) + 1e-6
    return np.c_[X, X[:, 3:6] / med].astype(np.float32)


def label_candidates(cand, ref, shift=0.0, tol=0.05) -> np.ndarray:
    """1 where a candidate is matched (onset +-tol, same semitone) to a reference note, greedy by closeness."""
    y = np.zeros(len(cand), dtype=np.int8)
    used = set()
    order = sorted(range(len(cand)), key=lambda i: cand[i]['time'])
    for i in order:
        t = cand[i]['time'] + shift
        best, bd = None, tol + 1e-9
        for j, r in enumerate(ref):
            if j in used or r['midi'] != cand[i]['midi']:
                continue
            d = abs(r['time'] - t)
            if d <= bd:
                best, bd = j, d
        if best is not None:
            used.add(best); y[i] = 1
    return y


# ---- tiny GBDT (sklearn GradientBoostingClassifier exported to JSON) -------------------------
def export_gbdt(clf, threshold, meta) -> dict:
    trees = []
    for est in clf.estimators_[:, 0]:
        t = est.tree_
        trees.append({'f': t.feature.tolist(), 't': np.round(t.threshold, 5).tolist(), 'l': t.children_left.tolist(),
                      'r': t.children_right.tolist(), 'v': np.round(t.value[:, 0, 0], 5).tolist()})
    init = float(clf.init_.class_prior_[1])
    return {'features': FEATURE_NAMES, 'lr': clf.learning_rate, 'init_logodds': float(np.log(init / (1 - init))),
            'trees': trees, 'threshold': threshold, 'meta': meta}


def predict_proba(model: dict, X: np.ndarray) -> np.ndarray:
    z = np.full(len(X), model['init_logodds'])
    for tr in model['trees']:
        f, th, L, R, v = tr['f'], tr['t'], tr['l'], tr['r'], tr['v']
        for i, x in enumerate(X):
            n = 0
            while L[n] != -1:
                n = L[n] if x[f[n]] <= th[n] else R[n]
            z[i] += model['lr'] * v[n]
    return 1 / (1 + np.exp(-z))


@lru_cache(maxsize=1)
def load_model():
    return json.loads(MODEL_PATH.read_text())


def refine(cand, post, fx_det, model=None):
    """Keep candidates scored as real notes. Returns (notes, info)."""
    model = model or load_model()
    if not cand:
        return [], {'kept': 0, 'candidates': 0}
    X = candidate_features(cand, post, clip_fx_vector(fx_det))
    if model.get('meta', {}).get('feature_mask'):
        X = X * np.asarray(model['meta']['feature_mask'], dtype=np.float32)
    p = predict_proba(model, X)
    keep = [dict(n, clean_model_p=round(float(pp), 3)) for n, pp in zip(cand, p) if pp >= model['threshold']]
    return keep, {'kept': len(keep), 'candidates': len(cand), 'threshold': model['threshold']}
