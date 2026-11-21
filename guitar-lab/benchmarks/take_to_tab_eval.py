"""Your take to tab, measured on GuitarSet (solo guitar, hexaphonic annotations, known tempo).

For each recording (first 30 s, as a riff would be) this runs what the app runs: the take
transcription, the tempo guess for a take played without a click, and the fingering that
writes the tab. Reported per file and overall:

- notes: note F1 (onset within 50 ms, right pitch),
- tempo: the guess within 4% of the true tempo; ``x2`` counts a double or half guess, which the
  player fixes with one click (the panel says so),
- tab: of the matched notes, the share written on the same string and fret the player used.

    python -m benchmarks.take_to_tab_eval <guitarset mic dir> <annotation dir> [count]

Result (21 Nov 2026, 24 recordings, 6 players, 4 styles, first 30 s): notes 0.91 F1; tempo guess
right 54%, right or exactly double/half 71%; with the panel's x1.5 and x2/3 fixes too, 88% are one
click away. Tab position: 55% of matched notes on the same string and fret as the player (the
same note can be played in several places; the rest are playable, just not where they were
played). Played to the app's click, the tempo is known and only the note and position figures apply.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from benchmarks.guitarset import note_scores, tab_agreement, truth

SECONDS = 30


def main(audio_dir, ann_dir, count=24):
    from server import compare as take_diff
    from server import song_analysis as sa
    from server.app import take_tempo
    from server.instruments import resolve_profile
    profile = resolve_profile('guitar')
    wavs = sorted(Path(audio_dir).glob('*_mic.wav'))
    # Spread across players, styles and solo/comp.
    step = max(1, len(wavs)//count)
    rows = []
    for wav in wavs[::step][:count]:
        ref, _, _, tempo = truth(Path(ann_dir)/wav.name.replace('_mic.wav', '.jams'))
        audio, sr = sf.read(wav, dtype='float32', always_2d=True)
        audio = audio[:SECONDS*sr].mean(axis=1)
        ref = [n for n in ref if n['time'] < SECONDS-.2]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'take.wav'
            sf.write(path, audio, sr)
            est = take_diff.transcribe_take(path)
            bpm, first = take_tempo(path, est)
        tabbed = sa.fingering([{k: n[k] for k in ('time', 'duration', 'midi')} for n in est],
                              profile['open_strings'], profile['max_fret'])
        tabbed.sort(key=lambda n: (n['time'], n['midi']))
        est_sorted = sorted(est, key=lambda n: (n['time'], n['midi']))
        p, r, f, pairs = note_scores(est_sorted, ref)
        ratio = bpm/float(tempo)
        row = {'file': wav.name.replace('_mic.wav', ''), 'f1': round(f, 3), 'true_bpm': round(float(tempo), 1), 'bpm': bpm,
               'tempo_ok': abs(ratio-1) < .04, 'tempo_x2': min(abs(ratio-2), abs(ratio-.5)) < .08,
               'tab_same': None if not pairs else round(tab_agreement(tabbed, ref, pairs), 3)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    n = len(rows)
    tab = [r['tab_same'] for r in rows if r['tab_same'] is not None]
    print('SUMMARY', json.dumps({'files': n, 'note_f1': round(float(np.mean([r['f1'] for r in rows])), 3),
                                 'tempo_right': round(sum(r['tempo_ok'] for r in rows)/n, 3),
                                 'tempo_right_or_x2': round(sum(r['tempo_ok'] or r['tempo_x2'] for r in rows)/n, 3),
                                 'tab_same_position': round(float(np.mean(tab)), 3) if tab else None}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 24)
