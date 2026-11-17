"""The frozen full-band test: does a candidate model read guitar inside a band mix better?

    python -m benchmarks.fullband.gate baseline                 # score the current model, save it
    python -m benchmarks.fullband.gate check <checkpoint.pth> [--onset T]   # score a candidate against it

Every item (benchmarks/fullband/items.py) is separated exactly as the app does it. The guitar
stem is transcribed with the app's Riley path and the guitar MIDI range, and the notes are
scored against the item's reference (note F1, 50 ms).

A candidate passes only if, on the frozen item ids alone, the mean improves by at least
MIN_GAIN and no frozen item falls by more than ITEM_DROP. Extra items, missing items, and
any mix or reference whose bytes changed after the baseline was written all fail. The baseline
file is written once; a second `baseline` run stops instead of moving the bar.

Passing this gate is necessary, not sufficient: the candidate must also pass the locked
regression baselines (benchmarks/regression) before it replaces the released model.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

DATA = Path(__file__).resolve().parent / 'data'
BASELINE = DATA / 'baseline.json'
MIN_GAIN = 0.05
ITEM_DROP = 0.02


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def model_sha256() -> str:
    """sha256 of the Riley checkpoint this process will load (released file, or the env override)."""
    from huggingface_hub import hf_hub_download
    from server import riley
    custom = os.environ.get('FRETWORK_RILEY_CHECKPOINT')
    path = Path(custom) if custom else Path(hf_hub_download(repo_id=riley.REPO, filename=riley.CHECKPOINTS['riley']))
    return file_sha256(path)


def separated(folder: Path):
    """The item's guitar stem as the app separates it (cached beside the mix)."""
    cache = folder / 'guitar.wav'
    if not cache.is_file():
        from server import models
        mix, sr = sf.read(folder / 'mix.wav', dtype='float32', always_2d=True)
        stems, got, _ = models.run_demucs(mix, sr)
        sf.write(cache, stems['guitar'], got)
    return cache


def transcribe_guitar(path, onset=None):
    """Notes from the app's Riley path, limited to the guitar profile's MIDI range.

    ``onset`` replaces the app's decoding with one fixed onset threshold. A retrained model
    can need a different threshold from the released one; choose it on the Slakh validation
    songs (training/runpod/pick.py), never on these items.
    """
    from server.instruments import resolve_profile
    profile = resolve_profile('guitar')
    if onset is None:
        from server.models import transcribe
        return transcribe(path, midi_min=profile['midi_min'], midi_max=profile['midi_max'], backend='riley')
    import librosa
    from server import riley
    y, _ = librosa.load(str(path), sr=riley.SAMPLE_RATE, mono=True)
    device = 'cuda' if _cuda() else 'cpu'
    notes = riley.notes_from_posteriors(riley.posteriors(y, device=device), onset=onset)
    return [n for n in notes if profile['midi_min'] <= n['midi'] <= profile['midi_max']]


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def score_items(checkpoint=None, data: Path | None = None, onset=None):
    if checkpoint:
        os.environ['FRETWORK_RILEY_CHECKPOINT'] = str(Path(checkpoint).resolve())
    else:
        os.environ.pop('FRETWORK_RILEY_CHECKPOINT', None)
    from benchmarks.regression import score as S
    root = Path(data) if data is not None else DATA
    rows = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and (p / 'reference.json').is_file()):
        ref = json.loads((folder / 'reference.json').read_text())
        lo, hi = ref.get('scored_from_s', 0.0), ref.get('scored_to_s', 1e9)
        heard = [n for n in transcribe_guitar(separated(folder), onset) if lo <= n['time'] < hi]
        target = [n for n in ref['notes'] if lo <= n['time'] < hi]
        metrics = S.score_notes(heard, target)
        rows[folder.name] = {
            'f1': round(metrics['note_f1'], 4),
            'precision': round(metrics['note_precision'], 4),
            'recall': round(metrics['note_recall'], 4),
            'reference_notes': len(target),
            'mix_sha256': file_sha256(folder / 'mix.wav'),
            'reference_sha256': file_sha256(folder / 'reference.json'),
        }
        print(folder.name, json.dumps(rows[folder.name]), flush=True)
    if not rows:
        raise SystemExit(f'No items in {root}. Make some with benchmarks/fullband/items.py.')
    return {
        'items': rows,
        'mean_f1': round(float(np.mean([row['f1'] for row in rows.values()])), 4),
        'model_sha256': model_sha256(),
        'onset': onset,
    }


def _mean(items, keys):
    values = [items[key]['f1'] for key in keys]
    return round(sum(values) / len(values), 4)


def verdict(base, cand):
    """Pass/fail using only the frozen item ids. Extra ids and changed audio fail closed."""
    frozen = list(base['items'])
    extra = sorted(set(cand['items']) - set(frozen))
    missing = sorted(set(frozen) - set(cand['items']))
    common = [key for key in frozen if key in cand['items']]
    changed = []
    drops = {}
    for key in common:
        before, after = base['items'][key], cand['items'][key]
        for field in ('mix_sha256', 'reference_sha256'):
            if before.get(field) and after.get(field) and before[field] != after[field]:
                changed.append({'item': key, 'field': field})
        delta = round(after['f1'] - before['f1'], 4)
        if delta < -ITEM_DROP:
            drops[key] = delta
    gain = round(_mean(cand['items'], common) - _mean(base['items'], frozen), 4) if common else None
    ok = (gain is not None and gain >= MIN_GAIN and not drops and not missing and not extra and not changed)
    return {
        'passes': bool(ok),
        'mean_gain': gain,
        'needed_gain': MIN_GAIN,
        'items_that_fell': drops,
        'items_missing': missing,
        'items_extra': extra,
        'items_changed': changed,
        'baseline_model_sha256': base.get('model_sha256'),
        'candidate_model_sha256': cand.get('model_sha256'),
    }


def write_baseline(result, path: Path = BASELINE):
    path = Path(path)
    if path.is_file():
        raise SystemExit(
            f'{path} already exists. The bar stays where it was first written. '
            'Delete that file yourself only when you mean to throw the frozen test away.'
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python -m benchmarks.fullband.gate baseline | check <checkpoint.pth> [--onset T]')
    if sys.argv[1] == 'baseline':
        if BASELINE.is_file():
            raise SystemExit(
                f'{BASELINE} already exists. Refusing to overwrite the frozen bar.'
            )
        result = score_items()
        write_baseline(result, BASELINE)
        print('BASELINE', json.dumps({
            'mean_f1': result['mean_f1'], 'items': len(result['items']), 'model_sha256': result['model_sha256'],
        }))
    elif sys.argv[1] == 'check':
        if len(sys.argv) < 3:
            raise SystemExit('Usage: python -m benchmarks.fullband.gate check <checkpoint.pth> [--onset T]')
        onset = float(sys.argv[sys.argv.index('--onset') + 1]) if '--onset' in sys.argv else None
        if not BASELINE.is_file():
            raise SystemExit('Run `baseline` first: the bar is fixed before any candidate is scored.')
        base = json.loads(BASELINE.read_text())
        cand = score_items(sys.argv[2], onset=onset)
        decision = verdict(base, cand)
        print('VERDICT', json.dumps(decision))
        sys.exit(0 if decision['passes'] else 1)
    else:
        raise SystemExit(f'Unknown command {sys.argv[1]!r}. Use baseline or check.')
