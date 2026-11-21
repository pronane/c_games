"""Tab positions with and without the string heard in the recording, on GuitarSet.

Leave one player out: the string model is trained on the other five players, then the held-out
player's recordings are written as tab two ways (fingering search alone; fingering search plus
server.string_timbre) and compared with the strings and frets they actually played.

- ``true notes``: every recording, notes from the annotations (isolates the fingering),
- ``transcribed``: a spread of recordings (first 30 s), notes from the app's own transcription,
  as "your take to tab" does.

    python -m benchmarks.string_eval <guitarset mic dir> <annotation dir> [files per player]
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from benchmarks.guitarset import note_scores, tab_agreement, truth
from server import song_analysis as sa
from server import string_timbre as st
from training.string_timbre_train import dataset, export, fit

SECONDS = 30


def same_position(tabbed, ref):
    by_key = {(round(n['time'], 4), n['midi']): n for n in tabbed}
    hits = [by_key.get((round(r['time'], 4), r['midi'])) for r in ref]
    return sum(1 for h, r in zip(hits, ref) if h and h.get('string') == r['string'] and h.get('fret') == r['fret']), len(ref)


def main(audio_dir, ann_dir, per_player=4):
    X, Y, P = dataset(audio_dir, ann_dir)
    wavs = sorted(Path(audio_dir).glob('*_mic.wav'))
    totals = {'true_base': [0, 0], 'true_heard': [0, 0], 'tx_base': [], 'tx_heard': []}
    for player in sorted(set(P)):
        with tempfile.TemporaryDirectory() as tmp:
            export(fit(X[P != player], Y[P != player]), Path(tmp)/'m.npz')
            model = st.load(Path(tmp)/'m.npz')
        mine = [w for w in wavs if int(w.name[:2]) == player]
        for i, wav in enumerate(mine):
            ref, *_ = truth(Path(ann_dir)/wav.name.replace('_mic.wav', '.jams'))
            audio, sr = sf.read(wav, dtype='float32', always_2d=True)
            audio = audio.mean(axis=1)
            plain = [{k: n[k] for k in ('time', 'duration', 'midi')} for n in ref]
            probs = st.string_probs(audio, sr, plain, st.STANDARD, model=model)
            heard = [dict(n, string_probs=p) if p else n for n, p in zip(plain, probs)]
            for key, notes in (('true_base', plain), ('true_heard', heard)):
                hit, n = same_position(sa.fingering(notes, st.STANDARD, 22), ref)
                totals[key][0] += hit
                totals[key][1] += n
            if i % max(1, len(mine)//per_player) == 0:
                from server import compare as take_diff
                clip = audio[:SECONDS*sr]
                ref30 = [n for n in ref if n['time'] < SECONDS-.2]
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp)/'t.wav'
                    sf.write(path, clip, sr)
                    est = take_diff.transcribe_take(path)
                est = [{k: n[k] for k in ('time', 'duration', 'midi')} for n in est]
                eprobs = st.string_probs(clip, sr, est, st.STANDARD, model=model)
                for key, notes in (('tx_base', est), ('tx_heard', [dict(n, string_probs=p) if p else n for n, p in zip(est, eprobs)])):
                    tabbed = sorted(sa.fingering(notes, st.STANDARD, 22), key=lambda n: (n['time'], n['midi']))
                    _, _, _, pairs = note_scores(tabbed, ref30)
                    totals[key].append(tab_agreement(tabbed, ref30, pairs) or 0)
                print(json.dumps({'file': wav.name, 'tx_base': round(totals['tx_base'][-1], 3), 'tx_heard': round(totals['tx_heard'][-1], 3)}), flush=True)
        print('player', player, {k: round(v[0]/v[1], 3) for k, v in totals.items() if k.startswith('true')}, flush=True)
    print('SUMMARY', json.dumps({
        'true_notes_fingering_only': round(totals['true_base'][0]/totals['true_base'][1], 3),
        'true_notes_with_heard_string': round(totals['true_heard'][0]/totals['true_heard'][1], 3),
        'transcribed_files': len(totals['tx_base']),
        'transcribed_fingering_only': round(float(np.mean(totals['tx_base'])), 3),
        'transcribed_with_heard_string': round(float(np.mean(totals['tx_heard'])), 3)}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
