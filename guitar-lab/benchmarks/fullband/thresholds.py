"""Every frozen item at several onset thresholds, from one pass of the model per item.

    [FRETWORK_RILEY_CHECKPOINT=<ckpt>] python -m benchmarks.fullband.thresholds <tag> [--app] [--out file.json]

For reading only: the threshold a candidate is judged at must be chosen beforehand on the Slakh
validation songs (training/runpod/pick.py), then passed to ``gate.py check --onset``. Looking
at this table to choose it would tune the model to the test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = [0.2, 0.25, 0.3, 0.4, 0.5, 0.6]


def main():
    import librosa
    from benchmarks.fullband.gate import DATA, _cuda, separated, transcribe_guitar
    from benchmarks.regression import score as S
    from server import riley
    from server.instruments import resolve_profile
    data = Path(sys.argv[sys.argv.index('--data') + 1]) if '--data' in sys.argv else DATA
    profile = resolve_profile('guitar')
    tag = sys.argv[1]
    rows = {}
    for folder in sorted(p for p in data.iterdir() if p.is_dir() and (p / 'reference.json').is_file()):
        ref = json.loads((folder / 'reference.json').read_text())
        lo, hi = ref.get('scored_from_s', 0.0), ref.get('scored_to_s', 1e9)
        target = [n for n in ref['notes'] if lo <= n['time'] < hi]
        y, _ = librosa.load(str(separated(folder)), sr=riley.SAMPLE_RATE, mono=True)
        out = riley.posteriors(y, device='cuda' if _cuda() else 'cpu')
        rows[folder.name] = {}
        for th in THRESHOLDS:
            heard = [n for n in riley.notes_from_posteriors(out, onset=th)
                     if profile['midi_min'] <= n['midi'] <= profile['midi_max'] and lo <= n['time'] < hi]
            m = S.score_notes(heard, target)
            rows[folder.name][str(th)] = [round(m['note_f1'], 3), round(m['note_precision'], 3), round(m['note_recall'], 3)]
        if '--app' in sys.argv:          # the app's own decoding as well (slower on processors)
            m = S.score_notes([n for n in transcribe_guitar(separated(folder)) if lo <= n['time'] < hi], target)
            rows[folder.name]['app'] = [round(m['note_f1'], 3), round(m['note_precision'], 3), round(m['note_recall'], 3)]
        print(folder.name, json.dumps(rows[folder.name]), flush=True)
    result = {'model': tag, 'items': rows,
              'mean_f1': {k: round(sum(r[k][0] for r in rows.values()) / len(rows), 4) for k in next(iter(rows.values()))}}
    print('MEAN', json.dumps(result['mean_f1']))
    if '--out' in sys.argv:
        Path(sys.argv[sys.argv.index('--out') + 1]).write_text(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
