"""Accuracy on real guitar recordings: GuitarSet (CC BY 4.0, Xi et al., ISMIR 2018).

360 excerpts, 6 players, 5 styles (bossa nova, funk, jazz, rock, singer-songwriter), comping
and soloing, recorded with a hexaphonic pickup so every note's string, fret and timing is
known. This scores what the app produces from the microphone recording:

- notes: Basic Pitch at the app's thresholds (and the library default for reference),
  onset within 50 ms and correct pitch (mir_eval, offsets ignored)
- tab: for correctly detected notes, how often our fingering picks the player's string+fret;
  also the fingering alone on the true notes, which isolates the fingering algorithm
- chords (comping files): majmin and root accuracy, duration-weighted (MIREX style)
- key and tempo

Download from https://zenodo.org/records/3371780 : annotation.zip and audio_mono-mic.zip.
Run from guitar-lab/:
  python -m benchmarks.guitarset /path/to/annotation_dir /path/to/mic_dir results.jsonl [--limit N]
then:
  python -m benchmarks.guitarset --report results.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from server import song_analysis as sa

STANDARD = [64, 59, 55, 50, 45, 40]
QUALITY = {'': 'maj', 'm': 'min', '7': '7', 'maj7': 'maj7', 'm7': 'min7', 'sus2': 'sus2', 'sus4': 'sus4', '5': 'maj'}


def harte(label):
    """App chord name -> Harte syntax for mir_eval ('Ebm7' -> 'Eb:min7', 'N' -> 'N')."""
    if label == 'N':
        return 'N'
    root = label[:2] if len(label) > 1 and label[1] in '#b' else label[:1]
    return f'{root}:{QUALITY.get(label[len(root):], "maj")}'


def truth(jams_path):
    d = json.loads(Path(jams_path).read_text())
    notes, chords, key, tempo = [], None, None, None
    for a in d['annotations']:
        ns = a['namespace']
        if ns == 'note_midi':
            idx = int(a['annotation_metadata']['data_source'])       # 0 = low E string
            for n in a['data']:
                midi = int(round(n['value']))
                notes.append({'time': n['time'], 'duration': n['duration'], 'midi': midi,
                              'string': 6-idx, 'fret': midi-STANDARD[5-idx]})
        elif ns == 'chord' and a['annotation_metadata'].get('data_source'):
            chords = a['data']                                        # performed chords
        elif ns == 'key_mode':
            key = a['data'][0]['value']
        elif ns == 'tempo':
            tempo = a['data'][0]['value']
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes, chords, key, tempo


def note_scores(est, ref):
    import mir_eval
    if not est or not ref:
        return 0.0, 0.0, 0.0, []
    ri = np.array([[n['time'], n['time']+max(n['duration'], .01)] for n in ref])
    rp = np.array([440*2**((n['midi']-69)/12) for n in ref])
    ei = np.array([[n['time'], n['time']+max(n['duration'], .01)] for n in est])
    ep = np.array([440*2**((n['midi']-69)/12) for n in est])
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None, onset_tolerance=.05)
    pairs = mir_eval.transcription.match_notes(ri, rp, ei, ep, offset_ratio=None, onset_tolerance=.05)
    return p, r, f, pairs


def tab_agreement(est_tabbed, ref, pairs):
    if not pairs:
        return None
    same = sum(1 for i, j in pairs if est_tabbed[j].get('string') == ref[i]['string'] and est_tabbed[j].get('fret') == ref[i]['fret'])
    return same/len(pairs)


def evaluate(jams_path, wav_path):
    import librosa
    import mir_eval
    import soundfile as sf
    from server import models
    ref, chords_ref, key_ref, tempo_ref = truth(jams_path)
    out = {'file': Path(wav_path).name, 'style': Path(wav_path).name.split('_')[1].split('-')[0],
           'kind': 'comp' if '_comp' in Path(wav_path).name else 'solo', 'truth_notes': len(ref)}
    # Notes at the app's thresholds and at the library default.
    for label, (onset, frame) in (('app', (models.ONSET_THRESHOLD, models.FRAME_THRESHOLD)), ('default', (.5, .3))):
        models.ONSET_THRESHOLD, models.FRAME_THRESHOLD = onset, frame
        est = models.transcribe(wav_path, midi_min=36, midi_max=88)
        p, r, f, pairs = note_scores(est, ref)
        out[f'notes_{label}'] = {'p': p, 'r': r, 'f1': f, 'count': len(est)}
        if label == 'app':
            tabbed = sa.fingering(est, STANDARD, 24)
            # fingering() keeps order by (time, midi) like est; map pairs through identity of order
            out['tab_on_detected'] = tab_agreement(tabbed, ref, pairs)
    models.ONSET_THRESHOLD, models.FRAME_THRESHOLD = .7, .5
    # Fingering alone, on the true notes: did we pick the player's string and fret?
    oracle = sa.fingering([{k: n[k] for k in ('time', 'duration', 'midi')} for n in ref], STANDARD, 24)
    same = sum(1 for a, b in zip(oracle, ref) if a['string'] == b['string'] and a['fret'] == b['fret'])
    out['tab_on_true_notes'] = same/len(ref) if ref else None
    out['tab_on_true_notes_within_2_frets'] = (sum(1 for a, b in zip(oracle, ref)
                                                   if a['fret'] is not None and abs(a['fret']-b['fret']) <= 2) / len(ref)) if ref else None

    # Key, tempo, chords from the guitar audio alone (no band to lean on).
    y, sr = sf.read(wav_path, dtype='float32')
    y = librosa.resample(y if y.ndim == 1 else y.mean(axis=1), orig_sr=sr, target_sr=22050)
    grid = sa.beat_grid(y, 22050, None, y)
    out['tempo'] = {'est': grid['bpm'], 'ref': tempo_ref,
                    'ok': bool(tempo_ref and abs(grid['bpm']-tempo_ref)/tempo_ref <= .04),
                    'ok_octave': bool(tempo_ref and min(abs(grid['bpm']*k-tempo_ref)/tempo_ref for k in (.5, 1, 2)) <= .04)}
    cents = sa.estimate_tuning_cents(y, 22050)
    chroma = librosa.feature.chroma_cqt(y=y, sr=22050, hop_length=512, tuning=cents/100)
    key = sa.estimate_key(chroma.sum(axis=1))
    beats = [b for b in grid['beats'] if 0 <= b < len(y)/22050]
    frames = np.clip(librosa.time_to_frames(beats, sr=22050, hop_length=512), 0, chroma.shape[1]-1)
    bounds = list(frames)+[chroma.shape[1]]
    synced = np.stack([np.median(chroma[:, a:max(b, a+1)], axis=1) for a, b in zip(bounds[:-1], bounds[1:])], axis=1)
    segs = sa.chord_segments(sa.chords_per_beat(synced, key), beats)
    key = sa.resolve_mode(key, segs)
    if key_ref and key:
        est_key = f"{sa.NAMES_SHARP[key['tonic']]} {key['mode']}"
        ref_tonic, ref_mode = key_ref.split(':')
        out['key'] = {'est': key['key'], 'ref': key_ref.replace(':', ' '),
                      'weighted': float(mir_eval.key.weighted_score(f"{ref_tonic.replace('#', '#')} {ref_mode}", est_key))}
    if chords_ref and out['kind'] == 'comp' and segs:
        ref_int = np.array([[c['time'], c['time']+c['duration']] for c in chords_ref])
        ref_lab = [c['value'] for c in chords_ref]
        est_int = np.array([[s['start'], s['end']] for s in segs])
        est_lab = [harte(s['chord']) for s in segs]
        est_int, est_lab = mir_eval.util.adjust_intervals(est_int, est_lab, ref_int.min(), ref_int.max(),
                                                          mir_eval.chord.NO_CHORD, mir_eval.chord.NO_CHORD)
        merged, r, e = mir_eval.util.merge_labeled_intervals(ref_int, ref_lab, est_int, est_lab)
        dur = mir_eval.util.intervals_to_durations(merged)
        out['chords'] = {
            'majmin': float(mir_eval.chord.weighted_accuracy(mir_eval.chord.majmin(r, e), dur)),
            'root': float(mir_eval.chord.weighted_accuracy(mir_eval.chord.root(r, e), dur)),
        }
    return out


def report(path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    def mean(vals):
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else float('nan')
    print(f'{len(rows)} recordings')
    for group, sel in [('all', rows)]+[(s, [r for r in rows if r['style'] == s]) for s in ('BN', 'Funk', 'Jazz', 'Rock', 'SS')] \
            + [(k, [r for r in rows if r['kind'] == k]) for k in ('comp', 'solo')]:
        if not sel:
            continue
        comp = [r for r in sel if 'chords' in r]
        print(f"{group:6} n={len(sel):3}  notes F1 {mean(r['notes_app']['f1'] for r in sel):.2f} "
              f"(P {mean(r['notes_app']['p'] for r in sel):.2f} R {mean(r['notes_app']['r'] for r in sel):.2f}; "
              f"library default F1 {mean(r['notes_default']['f1'] for r in sel):.2f})  "
              f"tab exact {mean(r['tab_on_detected'] for r in sel):.2f} (true notes {mean(r['tab_on_true_notes'] for r in sel):.2f}, ±2 frets {mean(r['tab_on_true_notes_within_2_frets'] for r in sel):.2f})  "
              f"chords majmin {mean(r['chords']['majmin'] for r in comp):.2f} root {mean(r['chords']['root'] for r in comp):.2f}  "
              f"key exact {mean(float(r['key']['weighted'] == 1) for r in sel if 'key' in r):.2f} weighted {mean(r['key']['weighted'] for r in sel if 'key' in r):.2f}  "
              f"tempo ±4% {mean(float(r['tempo']['ok']) for r in sel):.2f} (allowing ½/2× {mean(float(r['tempo']['ok_octave']) for r in sel):.2f})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('annotations', nargs='?')
    parser.add_argument('audio', nargs='?')
    parser.add_argument('results', nargs='?')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--report')
    args = parser.parse_args()
    if args.report:
        report(args.report)
        return
    done = set()
    out = Path(args.results)
    if out.exists():
        done = {json.loads(l)['file'] for l in out.read_text().splitlines() if l.strip()}
    wavs = sorted(Path(args.audio).glob('*_mic.wav'))[:args.limit]
    for i, wav in enumerate(wavs):
        if wav.name in done:
            continue
        jams = Path(args.annotations)/wav.name.replace('_mic.wav', '.jams')
        try:
            row = evaluate(jams, wav)
        except Exception as exc:                       # keep going; record the failure
            row = {'file': wav.name, 'error': str(exc)}
        with out.open('a') as f:
            f.write(json.dumps(row)+'\n')
        print(f'{i+1}/{len(wavs)} {wav.name} notes F1 {row.get("notes_app", {}).get("f1", float("nan")):.2f}', flush=True)


if __name__ == '__main__':
    sys.exit(main())
