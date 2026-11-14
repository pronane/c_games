"""Does the take comparison catch real playing mistakes? Planted mistakes on GuitarSet.

The player's take is a real recording from GuitarSet (player 05, held out of every training run;
CC BY 4.0), transcribed by the app exactly as a practice take is. The reference it is compared
with is the recording's true notes, with known mistakes planted in it. From the comparison's
point of view a planted change is exactly a playing mistake:

- a note added to the reference      -> the player *missed* it      (expected: missing)
- a note removed from the reference  -> the player added a note     (expected: extra)
- a reference pitch moved 1-3 frets  -> the player hit a wrong note (expected: wrong_pitch)
- a reference chord moved 150 ms     -> the player was early / late (expected: early / late)

Every other note in the reference was really played as written, so any mistake the app reports
on those is a false alarm. The same take with the unchanged reference measures false alarms on
a perfect performance.

    python -m benchmarks.take_compare_eval <guitarset audio dir> <annotation dir> <riley posteriors dir> [--odd] [--no-heard]

The even half of player 05's files is the rhythm (comp) parts, the odd half the solos.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from server import compare as C

PER_KIND = 3
SHIFT_S = 0.15


def groups(notes):
    out = []
    for n in sorted(notes, key=lambda n: n['time']):
        if out and abs(n['time'] - out[-1][0]['time']) < 0.03:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def plant(truth, rng):
    """Reference with planted mistakes, and the list of what was planted."""
    ref = [dict(n, _id=i) for i, n in enumerate(truth)]
    g = groups(ref)
    order = list(rng.permutation(len(g)))
    used, planted = set(), []

    def take_group(min_gap=1.0):
        while order:
            k = int(order.pop())
            t = g[k][0]['time']
            if all(abs(t - u) >= min_gap for u in used) and 1.0 < t:
                used.add(t)
                return g[k]
        return None

    for _ in range(PER_KIND):                                     # player adds a note
        grp = take_group()
        if grp:
            victim = grp[int(rng.integers(len(grp)))]
            ref = [n for n in ref if n['_id'] != victim['_id']]
            planted.append({'kind': 'extra', 'time': victim['time'], 'midi': victim['midi']})
    for _ in range(PER_KIND):                                     # player hits a wrong note
        grp = take_group()
        if grp:
            victim = grp[int(rng.integers(len(grp)))]
            new = int(victim['midi']) + int(rng.choice([-3, -2, -1, 1, 2, 3]))
            for n in ref:
                if n['_id'] == victim['_id']:
                    n['midi'] = new
            planted.append({'kind': 'wrong_pitch', 'time': victim['time'], 'midi': new})
    for _ in range(PER_KIND):                                     # player early / late
        grp = take_group()
        if grp:
            sign = float(rng.choice([-1, 1]))
            start = grp[0]['time']
            ids = {n['_id'] for n in grp}
            for n in ref:
                if n['_id'] in ids:
                    n['time'] += sign * SHIFT_S
            # Reference earlier than played -> the player is late.
            planted.append({'kind': 'late' if sign < 0 else 'early', 'time': start + sign * SHIFT_S,
                            'midi': [n['midi'] for n in grp]})
    times = np.array([n['time'] for n in truth])
    for _ in range(PER_KIND):                                     # player misses a note
        for _ in range(100):
            t = float(rng.uniform(1.0, times.max()))
            if np.min(np.abs(times - t)) > 0.35 and all(abs(t - u) >= 1.0 for u in used):
                break
        else:
            continue
        used.add(t)
        midi = int(rng.integers(45, 76))
        ref.append({'time': t, 'duration': 0.3, 'midi': midi, '_id': -1})
        planted.append({'kind': 'missing', 'time': t, 'midi': midi})
    for n in ref:
        n.pop('_id', None)
    return sorted(ref, key=lambda n: n['time']), planted


def score(findings, planted):
    """Which planted mistakes were reported as the right kind, and the false alarms."""
    caught = []
    hit = set()
    for p in planted:
        ok = False
        for i, f in enumerate(findings):
            if f['kind'] != p['kind']:
                continue
            if p['kind'] == 'extra':
                when, midi = f['take_time'], f['take_midi']
            else:
                when, midi = f['target_time'], f['target_midi']
            if when is None or abs(when - p['time']) > 0.06:
                continue
            if isinstance(p['midi'], list) or midi == p['midi']:
                ok = True
                hit.add(i)
        caught.append(ok)
    near = lambda f: any(abs(((f['target_time'] if f['target_time'] is not None else f['take_time']) or 0) - p['time']) < 0.25
                         for p in planted)
    alarms = Counter(f['kind'] for i, f in enumerate(findings) if f['kind'] != 'correct' and i not in hit and not near(f))
    return caught, alarms


def main(audio_dir, ann_dir, post_dir, half='even'):
    from benchmarks.regression import electric as el
    from server import riley
    from server.tab_check import widen
    from server.instruments import resolve_profile
    profile = resolve_profile('guitar')
    rng = np.random.default_rng(20261114)
    clips = sorted(Path(audio_dir).glob('05_*_mix.wav'))
    clips = clips[1::2] if half == 'odd' else clips[::2]
    by_kind, alarms_planted, alarms_perfect, n_ref = Counter(), Counter(), Counter(), 0
    totals = Counter()
    for wav in clips:
        stem = wav.name.replace('_mix.wav', '')
        truth = [{'time': n['time'], 'duration': n['duration'], 'midi': int(n['midi'])}
                 for n in el.jams_note_midi(Path(ann_dir) / f'{stem}.jams')]
        z = np.load(Path(post_dir) / f'{stem}.npz')
        # The practice-take path with Riley: decode, then the guitar range.
        take = [n for n in riley.decode({k: z[k].astype(np.float32) for k in z.files})[0]
                if profile['midi_min'] <= n['midi'] <= profile['midi_max']]
        bpm = float(stem.split('-')[1])
        heard = widen(z['reg_onset_output'].astype(np.float32))
        perfect = C.compare_take(take, [{'source': 'file', 'notes': truth, 'bpm': bpm}], heard=heard)['reports'][0]['notes']
        _, a0 = score(perfect, [])
        alarms_perfect += a0
        ref, planted = plant(truth, rng)
        findings = C.compare_take(take, [{'source': 'file', 'notes': ref, 'bpm': bpm}], heard=heard)['reports'][0]['notes']
        caught, a1 = score(findings, planted)
        alarms_planted += a1
        n_ref += len(truth)
        for p, ok in zip(planted, caught):
            kind = 'early/late' if p['kind'] in ('early', 'late') else p['kind']
            totals[kind] += 1
            by_kind[kind] += ok
        print(json.dumps({'clip': stem, 'caught': f'{sum(caught)}/{len(caught)}', 'false_alarms_planted': dict(a1),
                          'false_alarms_perfect': dict(a0)}), flush=True)
    result = {'clips': len(clips), 'reference_notes': n_ref,
              'caught': {k: f'{by_kind[k]}/{totals[k]} ({by_kind[k] / totals[k]:.0%})' for k in totals},
              'caught_overall': f'{sum(by_kind.values())}/{sum(totals.values())} ({sum(by_kind.values()) / sum(totals.values()):.0%})',
              'false_alarms_per_100_correct_notes': {k: round(100 * v / n_ref, 1) for k, v in alarms_perfect.most_common()},
              'false_alarms_per_100_excluding_duration': round(100 * sum(v for k, v in alarms_perfect.items() if k != 'wrong_duration') / n_ref, 1)}
    print('SUMMARY', json.dumps(result))
    return result


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--no-heard' in sys.argv:
        C.HEARD_ONSET = float('inf')        # the comparison as it was before the onset check
    main(*args, half='odd' if '--odd' in sys.argv else 'even')
