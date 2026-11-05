"""Template matcher + optional sklearn multilabel classifier for guitar effects."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .features import FEATURE_NAMES, extract_features, features_vector
from .renderers import EFFECT_NAMES

DEFAULT_TEMPLATES = Path(__file__).resolve().parent / 'data' / 'templates.json'


def _zscore(mat, mean=None, std=None):
    mean = mat.mean(axis=0) if mean is None else mean
    std = mat.std(axis=0) if std is None else std
    std = np.where(std < 1e-8, 1.0, std)
    return (mat - mean) / std, mean, std


class EffectMatcher:
    """Nearest-centroid template matcher with multi-label thresholding.

    Optionally wraps a fitted sklearn classifier stored in the templates JSON
    as coefficients (we keep it sklearn-free at inference if only centroids exist).
    """

    def __init__(self, templates_path: str | Path | None = None):
        path = Path(templates_path) if templates_path else DEFAULT_TEMPLATES
        self.path = path
        self.labels = list(EFFECT_NAMES)
        self.centroids = {}
        self.mean = np.zeros(len(FEATURE_NAMES))
        self.std = np.ones(len(FEATURE_NAMES))
        self.threshold = 0.55  # cosine similarity
        self.rf = None  # optional sklearn model
        if path.is_file():
            self.load(path)

    def load(self, path: str | Path):
        data = json.loads(Path(path).read_text())
        self.labels = data.get('labels', list(EFFECT_NAMES))
        self.threshold = float(data.get('threshold', 0.55))
        self.mean = np.array(data['mean'], dtype=np.float64)
        self.std = np.array(data['std'], dtype=np.float64)
        self.centroids = {k: np.array(v, dtype=np.float64) for k, v in data['centroids'].items()}
        # optional joblib-less: store RF as None; training script may attach .rf externally
        self._data = data

    def save(self, path: str | Path, extra=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'labels': self.labels,
            'threshold': self.threshold,
            'feature_names': list(FEATURE_NAMES),
            'mean': self.mean.tolist(),
            'std': self.std.tolist(),
            'centroids': {k: v.tolist() for k, v in self.centroids.items()},
        }
        if extra:
            payload.update(extra)
        path.write_text(json.dumps(payload, indent=2))

    def fit_centroids(self, X: np.ndarray, y_labels: list[str]):
        """X: (n, F) raw features; y_labels: one primary label per row."""
        Xn, self.mean, self.std = _zscore(X)
        self.centroids = {}
        for lab in self.labels:
            idx = [i for i, L in enumerate(y_labels) if L == lab]
            if not idx:
                continue
            self.centroids[lab] = Xn[idx].mean(axis=0)

    def _cosine(self, a, b):
        return float(np.dot(a, b) / ((np.linalg.norm(a) + 1e-12) * (np.linalg.norm(b) + 1e-12)))

    def predict_scores(self, feats: dict) -> dict[str, float]:
        v = features_vector(feats)
        vn = (v - self.mean) / np.where(self.std < 1e-8, 1.0, self.std)
        scores = {}
        for lab, c in self.centroids.items():
            scores[lab] = self._cosine(vn, c)
        if self.rf is not None:
            proba = self.rf.predict_proba(v.reshape(1, -1))
            # MultiOutputClassifier returns list of arrays
            if isinstance(proba, list):
                for i, lab in enumerate(self.labels):
                    if i < len(proba) and proba[i].shape[1] == 2:
                        scores[lab] = max(scores.get(lab, 0.0), float(proba[i][0, 1]))
        return scores

    def predict(self, audio, sr=44100, top_k=3) -> dict:
        feats = extract_features(audio, sr)
        scores = self.predict_scores(feats)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        active = [(lab, sc) for lab, sc in ranked if sc >= self.threshold and lab != 'clean']
        if not active:
            # fall back to best label
            best = ranked[0] if ranked else ('clean', 0.0)
            if best[0] == 'clean' or best[1] < 0.2:
                active = [('clean', float(best[1]))]
            else:
                active = [best]
        return {
            'effects': [{'name': n, 'confidence': round(float(c), 3)} for n, c in active[:top_k]],
            'scores': {k: round(float(v), 3) for k, v in ranked},
            'features': {k: round(float(feats[k]), 4) for k in FEATURE_NAMES},
        }


def match_effects(audio, sr=44100, templates_path=None) -> dict:
    return EffectMatcher(templates_path).predict(audio, sr)
