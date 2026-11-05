"""Train the effect classifier on IDMT-SMT-Audio-Effects (local copy) and export templates.json.

IDMT-SMT-Audio-Effects is CC BY-NC-ND 4.0: the audio is never copied into the repo. Only
derived statistics (feature mean/std, class centroids, and a small random forest over the
z-scored 67-D feature vector) are written to fx/data/templates.json.

Usage:
  python -m server.fx.train_idmt --features idmt_mono.npz            # cached features only; audio stays outside the repo

Evaluation is guitar-held-out: train on the Schecter clips (settings 6/7), test on the
Stratocaster clips (8/9), and vice versa; the two folds' confusion matrices are summed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .features import FEATURE_NAMES

IDMT_TO_LABEL = {
    'NoFX': 'clean', 'Distortion': 'distortion', 'Overdrive': 'overdrive', 'Chorus': 'chorus',
    'Flanger': 'flanger', 'Phaser': 'phaser', 'Tremolo': 'tremolo', 'Vibrato': 'vibrato',
    'Reverb': 'reverb', 'FeedbackDelay': 'feedback_delay', 'SlapbackDelay': 'slapback_delay', 'EQ': 'eq',
}
LABELS = list(IDMT_TO_LABEL.values())
OUT = Path(__file__).resolve().parent / 'data' / 'templates.json'


def export_tree(est, n_classes):
    t = est.tree_
    leaf = []
    for i in range(t.node_count):
        if t.children_left[i] < 0:
            v = t.value[i][0]
            v = v / (v.sum() + 1e-12)
            # Map the tree's class subset onto the full label set; integer percent keeps JSON small.
            full = np.zeros(n_classes)
            full[est.classes_.astype(int)] = v
            leaf.append([int(round(100 * p)) for p in full])
        else:
            leaf.append(0)
    return {'f': t.feature.tolist(), 't': [round(float(x), 4) for x in t.threshold],
            'l': t.children_left.tolist(), 'r': t.children_right.tolist(), 'v': leaf}


def fit_forest(Xn, y, n_trees=60, leaves=256, seed=0):
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_trees, max_leaf_nodes=leaves, max_features='sqrt',
                                  n_jobs=-1, random_state=seed).fit(Xn, y)


def evaluate(X, y, guitar, poly=None):
    """Guitar-held-out 2-fold. Returns (top1, per_class, confusion, subset_top1)."""
    from sklearn.metrics import confusion_matrix
    poly = np.zeros(len(y), bool) if poly is None else poly
    schecter = np.isin(guitar, ['6', '7'])
    cm = np.zeros((len(LABELS), len(LABELS)), int)
    hits = np.zeros(len(y), bool)
    for tr in (schecter, ~schecter):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-8
        m = fit_forest((X[tr] - mu) / sd, y[tr])
        p = m.predict((X[~tr] - mu) / sd)
        hits[~tr] = p == y[~tr]
        cm += confusion_matrix(y[~tr], p, labels=range(len(LABELS)))
    per = {LABELS[i]: round(float(cm[i, i] / max(1, cm[i].sum())), 3) for i in range(len(LABELS))}
    sub = {'mono': round(float(hits[~poly].mean()), 3) if (~poly).any() else None,
           'poly': round(float(hits[poly].mean()), 3) if poly.any() else None}
    return round(float(np.trace(cm) / cm.sum()), 3), per, cm, sub


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--features', required=True, nargs='+', help='npz file(s) with X, labels, names')
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--report', default=None)
    args = ap.parse_args(argv)
    ds = [np.load(f) for f in args.features]
    X = np.nan_to_num(np.concatenate([d['X'] for d in ds])).astype(np.float64)
    assert X.shape[1] == len(FEATURE_NAMES), 'features cache is from a different feature set'
    labels = np.concatenate([d['labels'] for d in ds]); names = np.concatenate([d['names'] for d in ds])
    y = np.array([LABELS.index(IDMT_TO_LABEL[l]) for l in labels])
    guitar = np.array([n[1] for n in names])
    poly = np.array([n[0] == 'P' for n in names])
    top1, per, cm, sub = evaluate(X, y, guitar, poly)
    print('subset top1', sub)
    mu, sd = X.mean(0), X.std(0) + 1e-8
    Xn = (X - mu) / sd
    rf = fit_forest(Xn, y)
    payload = {
        'source': 'IDMT-SMT-Audio-Effects guitar monophonic (derived features only; CC BY-NC-ND audio not included)',
        'labels': LABELS, 'threshold': 0.55, 'forest_threshold': 0.3, 'window_s': 2.0,
        'feature_names': list(FEATURE_NAMES),
        'mean': [round(float(v), 5) for v in mu], 'std': [round(float(v), 5) for v in sd],
        'centroids': {LABELS[k]: [round(float(v), 4) for v in Xn[y == k].mean(0)] for k in range(len(LABELS))},
        'eval': {'split': 'guitar-held-out 2-fold (Schecter <-> Strat)', 'top1': top1, 'per_class': per,
                 'subset_top1': sub, 'n_clips': int(len(y))},
        'forest': {'labels': LABELS, 'trees': [export_tree(e, len(LABELS)) for e in rf.estimators_]},
    }
    Path(args.out).write_text(json.dumps(payload, separators=(',', ':')))
    print('top1', top1, per)
    print('wrote', args.out, Path(args.out).stat().st_size // 1024, 'KB')
    if args.report:
        Path(args.report).write_text(json.dumps({'top1': top1, 'per_class': per, 'labels': LABELS, 'subset_top1': sub,
                                                 'confusion': cm.tolist()}, indent=1))


if __name__ == '__main__':
    main()
