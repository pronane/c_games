"""Guitar inside a band mix, with exact notes: Slakh2100 as test and training material.

Slakh2100 (Manilow et al. 2019; CC BY 4.0) is 2,100 multitrack songs rendered from MIDI with
sampled instruments. Every guitar stem comes with its MIDI, so the notes are exact, and the
other stems make a real band arrangement around it. Not real recordings: results on Slakh
show what the engine does with a band mix, and are checked on real records separately
(benchmarks/fullband).

Two uses:

    # How much does the band mix cost? Riley on the true guitar stem, on the app's separated
    # guitar, and on the unseparated mix, against the true notes.
    python -m training.slakh_data eval <slakh dir> [--tracks 20]

    # Training segments in the format training/finetune_riley.py reads: what the app's
    # separation leaves of the guitar (and, with --also-mix, the raw mix), with the true notes.
    python -m training.slakh_data build <slakh dir> <out dir> [--tracks N] [--also-mix]

<slakh dir> holds TrackNNNNN folders (mix.flac or mix.wav, metadata.yaml, MIDI/, stems/),
e.g. slakh2100_flac_redux/train, or babyslakh_16k.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SR = 16000          # Riley's rate
SEG_S = 10.0


def read(path, sr=None):
    import librosa
    y, got = librosa.load(str(path), sr=sr, mono=True)
    return y.astype(np.float32), got


def audio_file(folder: Path, name: str):
    for ext in ('.flac', '.wav'):
        if (folder / f'{name}{ext}').is_file():
            return folder / f'{name}{ext}'
    return None


def guitar_stems(track: Path) -> list:
    """Ids of the rendered pitched guitar stems of one track."""
    import yaml
    meta = yaml.safe_load((track / 'metadata.yaml').read_text())
    return [sid for sid, s in meta['stems'].items()
            if s.get('inst_class') == 'Guitar' and not s.get('is_drum')
            and audio_file(track / 'stems', sid) and (track / 'MIDI' / f'{sid}.mid').is_file()]


def stem_notes(track: Path, sid: str) -> list:
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(track / 'MIDI' / f'{sid}.mid'))
    return [{'time': float(n.start), 'duration': float(n.end - n.start), 'midi': int(n.pitch)}
            for inst in pm.instruments if not inst.is_drum for n in inst.notes]


def load_track(track: Path):
    """(true guitar audio at SR, notes, mix at its own rate, rate) or None when no guitar plays."""
    ids = guitar_stems(track)
    if not ids:
        return None
    notes = sorted((n for sid in ids for n in stem_notes(track, sid)), key=lambda n: n['time'])
    if len(notes) < 20:
        return None
    parts = [read(audio_file(track / 'stems', sid), SR)[0] for sid in ids]
    true = np.zeros(max(len(p) for p in parts), np.float32)
    for p in parts:
        true[:len(p)] += p
    import soundfile as sf
    mix, sr = sf.read(audio_file(track, 'mix'), dtype='float32', always_2d=True)
    return true, notes, mix, sr


def separated_guitar(mix, sr):
    """The guitar stem as the app makes it (htdemucs_6s at 44.1 kHz), mono at SR."""
    import librosa
    from server import models
    if sr != 44100:
        mix = np.stack([librosa.resample(mix[:, c], orig_sr=sr, target_sr=44100) for c in range(mix.shape[1])], axis=1)
    stems, got, _ = models.run_demucs(mix, 44100)
    return librosa.resample(stems['guitar'].mean(axis=1), orig_sr=got, target_sr=SR).astype(np.float32)


def tracks_in(folder, limit):
    found = sorted(p for p in Path(folder).glob('Track*') if (p / 'metadata.yaml').is_file())
    return found[:limit] if limit else found


def evaluate(folder, limit):
    import librosa
    from server import riley
    from benchmarks.regression import score as S
    rows = []
    for track in tracks_in(folder, limit):
        got = load_track(track)
        if got is None:
            continue
        true, notes, mix, sr = got
        sources = {'true_stem': true, 'separated': separated_guitar(mix, sr),
                   'mix': librosa.resample(mix.mean(axis=1), orig_sr=sr, target_sr=SR)}
        row = {'track': track.name, 'notes': len(notes)}
        for name, y in sources.items():
            m = S.score_notes(riley.decode(riley.posteriors(y))[0], notes)
            row[name] = {'f1': round(m['note_f1'], 3), 'precision': round(m['note_precision'], 3), 'recall': round(m['note_recall'], 3)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    summary = {'tracks': len(rows), **{k: round(float(np.mean([r[k]['f1'] for r in rows])), 3) for k in ('true_stem', 'separated', 'mix')}}
    print('SUMMARY', json.dumps(summary))
    return summary


def build(folder, out, limit, also_mix):
    import librosa
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    k = len(list(out.glob('seg_*.npz')))
    for track in tracks_in(folder, limit):
        got = load_track(track)
        if got is None:
            continue
        _, notes, mix, sr = got
        versions = {'separated': separated_guitar(mix, sr)}
        if also_mix:
            versions['mix'] = librosa.resample(mix.mean(axis=1), orig_sr=sr, target_sr=SR)
        times = np.array([n['time'] for n in notes])
        for name, y in versions.items():
            peak = float(np.abs(y).max()) or 1.0
            for a in np.arange(0, len(y) / SR - SEG_S, SEG_S):
                inside = [n for n in notes if a <= n['time'] < a + SEG_S]
                if len(inside) < 4:
                    continue
                seg = y[int(a * SR):int((a + SEG_S) * SR)] / peak * 0.9
                np.savez_compressed(out / f'seg_{k:05d}.npz', audio=(np.clip(seg, -1, 1) * 32767).astype(np.int16),
                                    notes=json.dumps([[n['time'] - a, n['duration'], n['midi']] for n in inside]),
                                    source=f'slakh:{name}:{track.name}')
                k += 1
        print(track.name, 'segments so far', k, flush=True)
    return k


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['eval', 'build'])
    ap.add_argument('slakh')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--tracks', type=int, default=0)
    ap.add_argument('--also-mix', action='store_true')
    a = ap.parse_args()
    evaluate(a.slakh, a.tracks) if a.mode == 'eval' else build(a.slakh, a.out, a.tracks, a.also_mix)
