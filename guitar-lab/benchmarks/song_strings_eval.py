"""Does hearing the string help on band recordings? Tab positions from the separated guitar.

For each song the reference is the player's own tab (string and fret of every note), lined up
with the recording by a saved line-up. Notes are written as tab two ways, the fingering search
alone and the fingering search plus server.string_timbre measured on the separated guitar stem,
and compared with the tab's string and fret:

- ``tab notes``: the tab's own notes, per guitar track (isolates the fingering),
- ``transcribed``: the app's transcription of the guitar stem, all parts at once as the song
  breakdown writes them, scored on the notes that match a tab note (same pitch, within 50 ms).

The stem holds every guitar at once and is often distorted, so this is harder than GuitarSet.

    python -m benchmarks.song_strings_eval <manifest.json>

Manifest: [{"name", "stem": guitar stem wav, "tab": tab json with string/fret per note,
"map": line-up json, "tracks": [guitar track indices], "transcription": notes json}]. The songs
are the player's own and stay private; only aggregate scores are reported.

Result (21 Nov 2026, 5 songs, 7,897 tab notes, 1,629 matched transcribed notes): tab notes
0.765 with the fingering search alone, 0.704 with the heard string; transcribed 0.490 -> 0.503.
The string model alone is right on 0.541 of tab notes on the stems (0.77 on GuitarSet). Weights
0.25-1 and confidence cut-offs were all at or below the fingering search alone, so the song
breakdown does not use it.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import soundfile as sf

from server import song_analysis as sa
from server import string_timbre as st
from server import tab_align as ta


def same(tabbed, ref):
    return sum(1 for t, r in zip(tabbed, ref) if t.get('string') == r['string'] and t.get('fret') == r['fret'])


def with_probs(notes, probs):
    return [dict(n, string_probs=p) if p else n for n, p in zip(notes, probs)]


def main(manifest):
    songs = json.load(open(manifest))
    total = {'tab_base': 0, 'tab_heard': 0, 'tab_n': 0, 'tab_measured': 0, 'tx_base': 0, 'tx_heard': 0, 'tx_n': 0}
    for s in songs:
        audio, sr = sf.read(s['stem'], dtype='float32', always_2d=True)
        audio = audio.mean(axis=1)
        tab = json.load(open(s['tab']))
        mapping = json.load(open(s['map']))
        shift = int(mapping.get('transpose', 0))
        chosen = [t for t in tab['tracks'] if t['index'] in s['tracks']]
        placed = ta.place_tracks([{'name': t['name'], 'track': t['index'], 'notes': t['notes']} for t in chosen], mapping)
        row = {'song': s['name']}
        all_ref = []
        open_real = None
        for t, part in zip(chosen, placed):
            open_strings = [o+shift for o in t['tuning']]
            open_real = open_real or open_strings
            ref = [n for n in part['notes'] if n.get('string') and n.get('fret') is not None]
            if not ref:
                continue
            plain = [{'time': n['time'], 'duration': n['duration'], 'midi': n['midi']} for n in ref]
            probs = st.string_probs(audio, sr, plain, open_strings)
            base = sa.fingering(plain, open_strings, 22)
            heard = sa.fingering(with_probs(plain, probs), open_strings, 22)
            key = lambda n: (round(n['time'], 4), n['midi'])
            bmap, hmap = {key(n): n for n in base}, {key(n): n for n in heard}
            total['tab_base'] += same([bmap[key(n)] for n in plain], ref)
            total['tab_heard'] += same([hmap[key(n)] for n in plain], ref)
            total['tab_n'] += len(ref)
            total['tab_measured'] += sum(p is not None for p in probs)
            all_ref.extend(ref)
        if s.get('transcription') and all_ref and open_real:
            est = [{'time': n['time'], 'duration': n['duration'], 'midi': int(n['midi'])} for n in json.load(open(s['transcription']))]
            est.sort(key=lambda n: (n['time'], n['midi']))
            probs = st.string_probs(audio, sr, est, open_real)
            for name, notes in (('tx_base', est), ('tx_heard', with_probs(est, probs))):
                tabbed = sa.fingering(notes, open_real, 22)
                times = np.array([r['time'] for r in all_ref])
                hits = n_matched = 0
                for n in tabbed:
                    near = np.nonzero(np.abs(times-n['time']) < .05)[0]
                    match = [all_ref[i] for i in near if all_ref[i]['midi'] == n['midi']]
                    if not match:
                        continue
                    n_matched += 1
                    hits += any(n.get('string') == r['string'] and n.get('fret') == r['fret'] for r in match)
                total[name] += hits
                if name == 'tx_base':
                    total['tx_n'] += n_matched
                row[name] = round(hits/max(1, n_matched), 3)
            row['tx_matched'] = n_matched
        print(json.dumps(row), flush=True)
    print('SUMMARY', json.dumps({
        'tab_notes': total['tab_n'], 'tab_measured': total['tab_measured'],
        'tab_fingering_only': round(total['tab_base']/max(1, total['tab_n']), 3),
        'tab_with_heard_string': round(total['tab_heard']/max(1, total['tab_n']), 3),
        'transcribed_matched': total['tx_n'],
        'transcribed_fingering_only': round(total['tx_base']/max(1, total['tx_n']), 3),
        'transcribed_with_heard_string': round(total['tx_heard']/max(1, total['tx_n']), 3)}))


if __name__ == '__main__':
    main(sys.argv[1])
