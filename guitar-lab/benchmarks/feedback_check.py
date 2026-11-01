"""How trustworthy is "check my take against the tab"? Measured on GuitarSet's real performances.

Each GuitarSet recording comes with exactly the notes the player played. Used as the tab,
a perfect checker would call every note correct, so anything it flags is a false alarm.
Then mistakes are planted by editing the tab (the recording stays as played):

- wrong note: a tab note moved 1 or 2 semitones (the player "played the wrong note")
- missed note: a note added to the tab that the player never played
- late note: a tab note moved 150 ms earlier (the player "came in late")

and we measure how often each is caught. Run from guitar-lab/:
  python -m benchmarks.feedback_check /path/to/ann /path/to/mic [--limit 60] [--cache dir]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import random

import numpy as np

from benchmarks.guitarset import truth
from server import analysis, models


def planted(ref, rng, rate=.05):
    tab = [dict(n) for n in ref]
    expect = []
    picks = rng.sample(range(len(tab)), max(3, int(len(tab)*rate)))
    for k, i in enumerate(picks):
        n = tab[i]
        kind = ('wrong', 'missed', 'late')[k % 3]
        if kind == 'wrong':
            n['midi'] += rng.choice((-2, -1, 1, 2))
            expect.append(('pitch_difference', n['time'], n['midi']))
        elif kind == 'missed':
            # A note the player never played: a fourth above, between this note and the next.
            t = n['time']+.08
            fake = {'time': t, 'duration': .2, 'midi': n['midi']+5}
            tab.append(fake)
            expect.append(('unmatched_reference', t, fake['midi']))
        else:
            n['time'] -= .15
            expect.append(('timing_difference', n['time'], n['midi']))
    return sorted(tab, key=lambda n: (n['time'], n['midi'])), expect


def judge(findings, expect):
    caught = {k: [0, 0] for k in ('pitch_difference', 'unmatched_reference', 'timing_difference')}
    for kind, t, midi in expect:
        caught[kind][1] += 1
        hit = [f for f in findings if f.get('reference_time') is not None and abs(f['reference_time']-t) < 1e-6
               and f.get('reference_midi') == midi]
        if hit and (hit[0]['kind'] == kind or (kind != 'timing_difference' and hit[0]['kind'] != 'matched'
                                                and hit[0]['kind'] != 'timing_difference')):
            caught[kind][0] += 1
    return caught


def run(ann, mic, limit, cache, params):
    files = sorted(Path(ann).glob('*.jams'))
    if limit:
        # Balanced: every style, comping and solo.
        files = [f for i, f in enumerate(files) if i % max(1, len(files)//limit) == 0][:limit]
    rng = random.Random(7)
    totals = {'notes': 0, 'ok': 0, 'false_wrong': 0, 'false_missed': 0, 'false_timing': 0, 'extra': 0, 'minutes': 0.0,
              'caught': {k: [0, 0] for k in ('pitch_difference', 'unmatched_reference', 'timing_difference')}}
    for f in files:
        wav = Path(mic)/f.name.replace('.jams', '_mic.wav')
        cached = Path(cache)/(f.stem+'.pkl') if cache else None
        if cached and cached.exists():
            take_notes, post = pickle.loads(cached.read_bytes())
        else:
            take_notes, post = models.transcribe(wav, midi_min=36, midi_max=88, posteriors=True)
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(pickle.dumps((take_notes, post)))
        ref = [{'time': n['time'], 'duration': n['duration'], 'midi': n['midi']} for n in truth(f)[0]]
        if not ref:
            continue
        clean = analysis.score_informed(ref, take_notes, post, **params)['findings']
        totals['notes'] += len(ref)
        totals['ok'] += sum(x['kind'] in ('matched',) for x in clean)
        totals['false_wrong'] += sum(x['kind'] == 'pitch_difference' for x in clean)
        totals['false_missed'] += sum(x['kind'] == 'unmatched_reference' for x in clean)
        totals['false_timing'] += sum(x['kind'] == 'timing_difference' for x in clean)
        totals['extra'] += sum(x['kind'] == 'unmatched_take' for x in clean)
        totals['minutes'] += post['onset'].shape[0]*post['hop']/60
        tab, expect = planted(ref, rng)
        for k, (a, b) in judge(analysis.score_informed(tab, take_notes, post, **params)['findings'], expect).items():
            totals['caught'][k][0] += a
            totals['caught'][k][1] += b
    n = totals['notes']
    return {'recordings': len(files), 'notes': n,
            'correct_notes_called_correct': round(totals['ok']/n, 3),
            'false_alarm_wrong_note': round(totals['false_wrong']/n, 3),
            'false_alarm_missed_note': round(totals['false_missed']/n, 3),
            'false_alarm_timing': round(totals['false_timing']/n, 3),
            'extra_notes_flagged_per_minute': round(totals['extra']/max(totals['minutes'], 1e-9), 1),
            'caught_wrong_note': round(totals['caught']['pitch_difference'][0]/max(1, totals['caught']['pitch_difference'][1]), 3),
            'caught_missed_note': round(totals['caught']['unmatched_reference'][0]/max(1, totals['caught']['unmatched_reference'][1]), 3),
            'caught_late_note': round(totals['caught']['timing_difference'][0]/max(1, totals['caught']['timing_difference'][1]), 3),
            'params': params}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('annotations')
    p.add_argument('audio')
    p.add_argument('--limit', type=int, default=60)
    p.add_argument('--cache')
    p.add_argument('--params', default='{}', help='JSON of score_informed keyword arguments')
    a = p.parse_args()
    print(json.dumps(run(a.annotations, a.audio, a.limit, a.cache, json.loads(a.params)), indent=1))
