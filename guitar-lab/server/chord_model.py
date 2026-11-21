"""Chords from a trained model: BTC (bi-directional transformer, Park et al., ISMIR 2019, MIT).

Measured against chords read from the player's own tabs (benchmarks/chords_eval.py, 5 songs,
1,508 beats), on the whole mix: right root and major/minor on 60% of beats (root 70%), where the
template matcher in song_analysis gets 53% (59%). The app uses it when its weights are installed
and falls back to the template matcher otherwise.

The weights (12 MB) are downloaded from the authors' repository at a pinned commit and checked
by SHA-256:

    python -m server.chord_model install
    python -m server.chord_model check
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

COMMIT = '2682317be668032e6e4b269ded36adaa2ad57df0'
URL = f'https://raw.githubusercontent.com/jayg996/BTC-ISMIR19/{COMMIT}/test/btc_model_large_voca.pt'
SHA256 = '1673d23f8f9a55ae7f9e8b80a51da616debb22675b8d8b67ea6ce0ef37b0ab51'
NAME = 'BTC (trained chord model)'
SR = 22050
CONFIG = {'feature_size': 144, 'timestep': 108, 'num_chords': 170, 'input_dropout': .2, 'layer_dropout': .2,
          'attention_dropout': .2, 'relu_dropout': .2, 'num_layers': 8, 'num_heads': 4, 'hidden_size': 128,
          'total_key_depth': 128, 'total_value_depth': 128, 'filter_size': 128, 'loss': 'ce', 'probs_out': False}
SECONDS_PER_CHUNK = 10.0
ROOTS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# The model's 14 qualities, as the app writes them (chord boxes exist for each).
QUALITIES = ['m', '', 'dim', 'aug', 'm', '', 'm7', 'm', 'maj7', '7', 'dim', 'dim', 'sus2', 'sus4']


def weights_path() -> Path:
    configured = os.getenv('FRETWORK_CHORD_MODEL_DIR')
    folder = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1]/'.cache/models/chords'
    return folder/'btc_model_large_voca.pt'


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=1)
def status():
    """(installed, detail)."""
    import importlib.util
    if importlib.util.find_spec('torch') is None:
        return False, 'Needs torch.'
    path = weights_path()
    if not path.is_file():
        return False, f'Weights not installed (python -m server.chord_model install puts them in {path.parent}).'
    if _sha256(path) != SHA256:
        return False, 'Weights file does not match the pinned checksum; reinstall it.'
    return True, f'{NAME}, weights verified.'


def install():
    path = weights_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.part')
    urllib.request.urlretrieve(URL, tmp)
    if _sha256(tmp) != SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError('Downloaded chord model does not match the pinned checksum.')
    tmp.replace(path)
    status.cache_clear()
    return path


@lru_cache(maxsize=1)
def _model():
    try:
        from numpy._core import multiarray
    except ImportError:  # NumPy 1
        from numpy.core import multiarray
    import torch
    from .btc.btc_model import BTC_model
    # The checkpoint stores its normalisation as NumPy scalars; allow just those when loading.
    torch.serialization.add_safe_globals([(multiarray.scalar, 'numpy.core.multiarray.scalar'), np.dtype,
                                          type(np.dtype('float64')), type(np.dtype('float32'))])
    checkpoint = torch.load(weights_path(), map_location='cpu', weights_only=True)
    model = BTC_model(config=CONFIG)
    model.load_state_dict(checkpoint['model'])
    model.eval()
    return model, float(checkpoint['mean']), float(checkpoint['std'])


def frame_chords(y, sr=SR):
    """Chord label per model frame, and the frame length in seconds."""
    import librosa
    import torch
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    model, mean, std = _model()
    feature = np.log(np.abs(librosa.cqt(y, sr=SR, n_bins=144, bins_per_octave=24, hop_length=2048)) + 1e-6).T
    feature = (feature-mean)/std
    T = CONFIG['timestep']
    pad = (-feature.shape[0]) % T
    x = torch.tensor(np.pad(feature, ((0, pad), (0, 0))), dtype=torch.float32).unsqueeze(0)
    out = []
    with torch.no_grad():
        for t in range(x.shape[1]//T):
            attended, _ = model.self_attn_layers(x[:, T*t:T*(t+1)])
            prediction, _ = model.output_layer(attended)
            out.extend(prediction.reshape(-1).tolist())
    return np.array(out[:feature.shape[0]], dtype=int), SECONDS_PER_CHUNK/T


FLATS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']


def label(index, flats=False):
    if index >= 168:
        return 'N'
    return (FLATS if flats else ROOTS)[index//14]+QUALITIES[index % 14]


def chords_per_beat(y, beats, duration, sr=SR, flats=False):
    """One chord label per beat: the label the model gives most of that beat."""
    frames, step = frame_chords(y, sr)
    edges = list(beats)+[duration]
    labels = []
    for a, b in zip(edges[:-1], edges[1:]):
        lo, hi = int(a/step), max(int(b/step), int(a/step)+1)
        part = frames[lo:hi]
        labels.append(label(int(np.bincount(part).argmax()), flats) if len(part) else 'N')
    return labels


if __name__ == '__main__':
    if sys.argv[1:] == ['install']:
        print('Installed', install())
    print(status())
