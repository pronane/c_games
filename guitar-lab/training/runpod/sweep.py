"""Score one model on Slakh songs at a range of onset thresholds.

A retrained model can need a different onset threshold from the released one (the pilot model
did: it was more cautious, and looked worse at the app's fixed threshold while being better at
its own). This prints, per song, note F1 / precision / recall at each threshold for the guitar
alone, the separated guitar and the raw mix. ``pick.py`` then chooses the threshold on half the
songs and reports the other half.

    [FRETWORK_RILEY_CHECKPOINT=<ckpt>] python training/runpod/sweep.py <tag> <slakh folder> <cache dir> [--tracks N]

The separated audio and the notes are cached, so only the first model pays for separation.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from training import slakh_data as D  # noqa: E402

THRESHOLDS = [0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6]


def sources(track, cache):
    f = cache / f'{track.name}.npz'
    if f.is_file():
        z = np.load(f, allow_pickle=False)
        return json.loads(str(z['notes'])), {k: z[k] for k in ('true_stem', 'separated', 'mix')}
    got = D.load_track(track)
    if got is None:
        np.savez(f, notes=json.dumps([]), true_stem=np.zeros(1, np.float32), separated=np.zeros(1, np.float32), mix=np.zeros(1, np.float32))
        return [], {}
    import librosa
    true, notes, mix, sr = got
    src = {'true_stem': true, 'separated': D.separated_guitar(mix, sr),
           'mix': librosa.resample(mix.mean(axis=1), orig_sr=sr, target_sr=D.SR)}
    np.savez(f, notes=json.dumps(notes), **src)
    return notes, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('slakh')
    ap.add_argument('cache')
    ap.add_argument('--tracks', type=int, default=30)
    a = ap.parse_args()
    from server import riley
    from benchmarks.regression import score as S
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    for track in D.tracks_in(a.slakh, a.tracks):
        notes, src = sources(track, cache)
        if not notes:
            continue
        row = {'track': track.name, 'model': a.tag}
        for name, y in src.items():
            out = riley.posteriors(y, device=D._device())
            row[name] = {}
            for th in THRESHOLDS:
                m = S.score_notes(riley.notes_from_posteriors(out, onset=th), notes)
                row[name][str(th)] = [round(m['note_f1'], 3), round(m['note_precision'], 3), round(m['note_recall'], 3)]
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
