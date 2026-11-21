"""Train the string-from-timbre model (server/string_timbre.py) on GuitarSet and export it.

GuitarSet (CC BY 4.0) gives every note's string from a hexaphonic pickup; features come from
the microphone recording at the true note times. Prints a leave-one-player-out score, then
trains on all six players and writes server/data/string_timbre.npz (plain arrays).

    python -m training.string_timbre_train <guitarset mic dir> <annotation dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from benchmarks.guitarset import truth
from server import string_timbre as st


def dataset(audio_dir, ann_dir):
    X, Y, P = [], [], []
    for wav in sorted(Path(audio_dir).glob('*_mic.wav')):
        ref, *_ = truth(Path(ann_dir)/wav.name.replace('_mic.wav', '.jams'))
        audio, sr = sf.read(wav, dtype='float32', always_2d=True)
        for n, row in zip(ref, st.features(audio.mean(axis=1), sr, ref)):
            if row is not None:
                X.append(row)
                Y.append(n['string'])
                P.append(int(wav.name[:2]))
    return np.array(X), np.array(Y), np.array(P)


def fit(X, Y):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=.08, max_leaf_nodes=48, l2_regularization=1.0,
                                          random_state=0).fit(X, Y)


def export(clf, path):
    """The fitted trees as flat arrays: iteration-major, one tree per class per iteration."""
    if any(p.nodes['is_categorical'].any() for it in clf._predictors for p in it):
        raise ValueError('categorical splits are not supported by the exporter')
    nodes, offsets = [], [0]
    for iteration in clf._predictors:
        for tree in iteration:
            nodes.append(tree.nodes)
            offsets.append(offsets[-1]+len(tree.nodes))
    allnodes = np.concatenate(nodes)
    np.savez_compressed(path, n_classes=np.array(len(clf.classes_)), classes=clf.classes_.astype(np.int64),
                        baseline=np.asarray(clf._baseline_prediction, dtype=float).reshape(-1),
                        tree_offsets=np.array(offsets, dtype=np.int64),
                        feature=allnodes['feature_idx'].astype(np.int64), threshold=allnodes['num_threshold'].astype(float),
                        left=allnodes['left'].astype(np.int64), right=allnodes['right'].astype(np.int64),
                        is_leaf=allnodes['is_leaf'].astype(bool), missing_left=allnodes['missing_go_to_left'].astype(bool),
                        value=allnodes['value'].astype(float))


def main(audio_dir, ann_dir):
    X, Y, P = dataset(audio_dir, ann_dir)
    print('notes', len(X), flush=True)
    feasible = (X[:, -6:] >= 0) & (X[:, -6:] <= st.MAX_FRET+4)
    scores = []
    for p in sorted(set(P)):
        clf = fit(X[P != p], Y[P != p])
        prob = np.zeros((int((P == p).sum()), 6))
        prob[:, clf.classes_-1] = clf.predict_proba(X[P == p])
        prob *= feasible[P == p]
        scores.append(float(np.mean(prob.argmax(1)+1 == Y[P == p])))
        print('player', p, 'string accuracy', round(scores[-1], 3), flush=True)
    print('leave-one-player-out mean', round(float(np.mean(scores)), 3))
    clf = fit(X, Y)
    export(clf, st.MODEL)
    st._model.cache_clear()
    check = st._raw(st._model(), X[:200])
    ref = clf._raw_predict(X[:200])
    assert np.allclose(check, ref, atol=1e-6), 'exported model disagrees with scikit-learn'
    print('wrote', st.MODEL, st.MODEL.stat().st_size, 'bytes')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
