"""Does the transcription check point at the right places? Planted errors on GuitarSet.

For held-out GuitarSet performances (player 05, CC BY 4.0) the true notes are known. Each
transcription (the true notes, and Riley's) is checked as is, then again with one planted
error stretch: four seconds of notes removed, or moved to wrong pitches. A good check flags
the planted stretch and little else.

    python -m benchmarks.transcription_check_eval <guitarset audio dir> <annotation dir> [riley posteriors dir]
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from server import transcription_check as tc


def plant(notes, rng, kind, length):
    times = np.array([n['time'] for n in notes])
    for _ in range(50):
        a = float(rng.uniform(2, max(2.1, length - 6)))
        inside = (times >= a) & (times < a + 4)
        if inside.sum() >= 6:
            break
    else:
        return None, None
    if kind == 'removed':
        out = [n for n, i in zip(notes, inside) if not i]
    else:
        out = [dict(n, midi=int(n['midi']) + int(rng.choice([-5, -4, -3, 3, 4, 5]))) if i else n for n, i in zip(notes, inside)]
    return out, (a, a + 4)


def flagged(report, window=None):
    """Seconds flagged inside and outside a window."""
    inside = outside = 0.0
    for f in report['stretches']:
        a, b = f['start'], f['end']
        if window:
            ov = max(0.0, min(b, window[1]) - max(a, window[0]))
            inside += ov
            outside += (b - a) - ov
        else:
            outside += b - a
    return inside, outside


GRID = [(below, floor, above, mfloor) for below in (0.12, 0.15) for floor in (0.45,) for above in (0.15, 0.2, 0.3, 9) for mfloor in (0.35, 0.45, 0.6)]


def with_params(params, fn):
    old = (tc.DIFFERS_BELOW, tc.DIFFERS_FLOOR, tc.MISSING_ABOVE, tc.MISSING_FLOOR)
    tc.DIFFERS_BELOW, tc.DIFFERS_FLOOR, tc.MISSING_ABOVE, tc.MISSING_FLOOR = params
    try:
        return fn()
    finally:
        tc.DIFFERS_BELOW, tc.DIFFERS_FLOOR, tc.MISSING_ABOVE, tc.MISSING_FLOOR = old


def main(audio_dir, ann_dir, post_dir=None, grid=None):
    from benchmarks.regression import electric as el
    rng = np.random.default_rng(20261114)
    rows = []
    for wav in sorted(Path(audio_dir).glob('05_*_mix.wav'))[::2]:
        stem = wav.name.replace('_mix.wav', '')
        audio, sr = sf.read(wav, dtype='float32')
        original = tc.mono22(audio, sr)
        length = len(original) / tc.SR
        truth = [{'time': n['time'], 'duration': n['duration'], 'midi': int(n['midi'])} for n in el.jams_note_midi(Path(ann_dir) / f'{stem}.jams')]
        versions = {'true notes': truth}
        if post_dir and (Path(post_dir) / f'{stem}.npz').exists():
            from server import riley
            z = np.load(Path(post_dir) / f'{stem}.npz')
            versions['Riley'] = riley.decode({k: z[k].astype(np.float32) for k in z.files})[0]
        for name, notes in versions.items():
            base = tc.compare(original, tc.playback(notes, length), notes)
            row = {'clip': stem, 'transcription': name, 'baseline_flagged_share': base['summary']['flagged_share']}
            for kind in ('removed', 'wrong pitch'):
                planted, window = plant(notes, rng, kind, length)
                if planted is None:
                    continue
                rep = tc.compare(original, tc.playback(planted, length), planted)
                inside, outside = flagged(rep, window)
                row[kind] = {'caught': inside >= 1.0, 'inside_s': round(inside, 1),
                             'false_share': round(outside / max(1e-9, rep['summary']['sounding_seconds'] - 4), 3)}
            rows.append(row)
            print(json.dumps(row), flush=True)
    summary = {}
    for name in ('true notes', 'Riley'):
        r = [x for x in rows if x['transcription'] == name]
        if not r:
            continue
        summary[name] = {'clips': len(r), 'baseline_flagged_share': round(float(np.mean([x['baseline_flagged_share'] for x in r])), 3)}
        for kind in ('removed', 'wrong pitch'):
            k = [x[kind] for x in r if kind in x]
            summary[name][kind] = {'caught': round(float(np.mean([x['caught'] for x in k])), 3),
                                   'false_flag_share': round(float(np.mean([x['false_share'] for x in k])), 3)}
    print('SUMMARY', json.dumps(summary))
    return summary


if __name__ == '__main__':
    main(*sys.argv[1:])
