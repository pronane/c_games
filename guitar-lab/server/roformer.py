"""BS-RoFormer SW six-source separation (bass, drums, other, vocals, guitar, piano).

Measured on real recordings it gives the guitar transcriber a much better guitar than Demucs
htdemucs_6s: 24 MoisesDB multitrack songs, note F1 0.566 -> 0.718 (ahead on every song); the
user's seven tabbed songs 0.229 -> 0.261 (benchmarks/regression/RESULTS.md). It is slow on
processors alone, so the app uses it with a graphics card and keeps Demucs on CPU
(models.choose_separator).

The checkpoint is published without a stated licence: fine for private use, check before
distributing it. It is run with ``audio-separator`` (pip install 'audio-separator[gpu]'),
downloaded by that package into the model folder and then pinned here by SHA-256.

    python -m server.roformer install      # download and verify the checkpoint
    python -m server.roformer check
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL = 'BS-Roformer-SW.ckpt'
NAME = 'BS-RoFormer SW'
EXPECTED_SHA256 = os.getenv('FRETWORK_ROFORMER_SHA256', '')
SAMPLE_RATE = 44100


def model_dir() -> Path:
    configured = os.getenv('FRETWORK_ROFORMER_DIR')
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1] / '.cache/models/roformer'


@lru_cache(maxsize=4)
def _digest(path, size, mtime):
    from .model_store import digest_file
    return digest_file(path)


def status():
    """(usable, detail). Never downloads."""
    if importlib.util.find_spec('audio_separator') is None:
        return False, "Install audio-separator: pip install 'audio-separator[gpu]'."
    path = model_dir() / MODEL
    if not path.is_file():
        return False, f'The {NAME} checkpoint is not installed: python -m server.roformer install'
    if EXPECTED_SHA256:
        stat = path.stat()
        if _digest(str(path), stat.st_size, stat.st_mtime_ns) != EXPECTED_SHA256:
            return False, f'The {NAME} checkpoint does not match the pinned SHA-256.'
    return True, f'{NAME} installed.'


@lru_cache(maxsize=1)
def _separator(output_dir):
    from audio_separator.separator import Separator
    sep = Separator(model_file_dir=str(model_dir()), output_dir=output_dir, output_format='WAV')
    sep.load_model(model_filename=MODEL)
    return sep


def separate(audio, sr):
    """({stem: (n, 2) float32}, 44100, provenance) for a (n, channels) float array."""
    import librosa
    import soundfile as sf
    good, detail = status()
    if not good:
        from .models import ModelUnavailable
        raise ModelUnavailable(detail)
    y = np.asarray(audio, dtype=np.float32)
    y = y[:, None] if y.ndim == 1 else y
    y = np.repeat(y, 2, axis=1) if y.shape[1] == 1 else y[:, :2]
    if sr != SAMPLE_RATE:
        y = np.stack([librosa.resample(y[:, c], orig_sr=sr, target_sr=SAMPLE_RATE) for c in range(2)], axis=1)
    with tempfile.TemporaryDirectory(prefix='roformer-') as tmp:
        src = Path(tmp) / 'input.wav'
        sf.write(src, y, SAMPLE_RATE)
        sep = _separator(str(Path(tempfile.gettempdir()) / 'fretwork-roformer-out'))
        stems = {}
        for f in sep.separate(str(src)):
            path = Path(f) if Path(f).is_absolute() else Path(sep.output_dir) / f
            name = path.name.split('_(')[1].split(')')[0].lower()
            data, rate = sf.read(path, dtype='float32', always_2d=True)
            stems[name] = data if data.shape[1] == 2 else np.repeat(data[:, :1], 2, axis=1)
            path.unlink(missing_ok=True)
    return stems, SAMPLE_RATE, {'model': NAME, 'sources': sorted(stems), 'device': 'cuda' if _cuda() else 'cpu',
                                'warning': None, 'checkpoint': MODEL, 'sha256': EXPECTED_SHA256 or None,
                                'quality': 'Measured on real multitracks: see RESULTS.md.'}


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def install():
    """Download through audio-separator, then check the digest."""
    model_dir().mkdir(parents=True, exist_ok=True)
    from audio_separator.separator import Separator
    Separator(model_file_dir=str(model_dir()), output_dir=tempfile.gettempdir()).load_model(model_filename=MODEL)
    good, detail = status()
    print(detail)
    return 0 if good else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'install':
        raise SystemExit(install())
    print(status()[1])
    raise SystemExit(0 if status()[0] else 1)
