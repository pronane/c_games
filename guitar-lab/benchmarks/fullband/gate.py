"""The frozen full-band test: does a candidate model read guitar inside a band mix better?

    python -m benchmarks.fullband.gate baseline                 # score the current model, save it
    python -m benchmarks.fullband.gate check <checkpoint.pth>   # score a candidate against it

Every item (benchmarks/fullband/items.py) is separated exactly as the app does it, the guitar
stem is transcribed, and the notes are scored against the item's reference (note F1, 50 ms).
A candidate passes only if the mean improves by at least MIN_GAIN and no item falls by more
than ITEM_DROP. Passing this gate is necessary, not sufficient: the candidate must also pass
the locked regression baselines (benchmarks/regression) before it replaces the released model.
"""
from __future__ import annotations

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


def separated(folder: Path):
    """The item's guitar stem as the app separates it (cached beside the mix)."""
    cache = folder / 'guitar.wav'
    if not cache.is_file():
        from server import models
        mix, sr = sf.read(folder / 'mix.wav', dtype='float32', always_2d=True)
        stems, got, _ = models.run_demucs(mix, sr)
        sf.write(cache, stems['guitar'], got)
    return cache


def score_items(checkpoint=None):
    if checkpoint:
        os.environ['FRETWORK_RILEY_CHECKPOINT'] = str(checkpoint)
    import librosa
    from server import riley
    from benchmarks.regression import score as S
    rows = {}
    for folder in sorted(p for p in DATA.iterdir() if (p / 'reference.json').is_file()):
        ref = json.loads((folder / 'reference.json').read_text())
        lo, hi = ref.get('scored_from_s', 0.0), ref.get('scored_to_s', 1e9)
        y, _ = librosa.load(str(separated(folder)), sr=riley.SAMPLE_RATE, mono=True)
        heard = [n for n in riley.decode(riley.posteriors(y))[0] if lo <= n['time'] < hi]
        target = [n for n in ref['notes'] if lo <= n['time'] < hi]
        m = S.score_notes(heard, target)
        rows[folder.name] = {'f1': round(m['note_f1'], 4), 'precision': round(m['note_precision'], 4),
                             'recall': round(m['note_recall'], 4), 'reference_notes': len(target)}
        print(folder.name, json.dumps(rows[folder.name]), flush=True)
    if not rows:
        raise SystemExit(f'No items in {DATA}. Make some with benchmarks/fullband/items.py.')
    return {'items': rows, 'mean_f1': round(float(np.mean([r['f1'] for r in rows.values()])), 4)}


def verdict(base, cand):
    drops = {k: round(cand['items'][k]['f1'] - v['f1'], 4) for k, v in base['items'].items()
             if k in cand['items'] and cand['items'][k]['f1'] < v['f1'] - ITEM_DROP}
    missing = sorted(set(base['items']) - set(cand['items']))
    gain = round(cand['mean_f1'] - base['mean_f1'], 4)
    ok = gain >= MIN_GAIN and not drops and not missing
    return {'passes': ok, 'mean_gain': gain, 'needed_gain': MIN_GAIN, 'items_that_fell': drops, 'items_missing': missing}


if __name__ == '__main__':
    if sys.argv[1] == 'baseline':
        result = score_items()
        BASELINE.write_text(json.dumps(result, indent=1))
        print('BASELINE', json.dumps({'mean_f1': result['mean_f1'], 'items': len(result['items'])}))
    else:
        if not BASELINE.is_file():
            raise SystemExit('Run `baseline` first: the bar is fixed before any candidate is scored.')
        base = json.loads(BASELINE.read_text())
        cand = score_items(sys.argv[2])
        v = verdict(base, cand)
        print('VERDICT', json.dumps(v))
        sys.exit(0 if v['passes'] else 1)
