"""Score Riley on a local GOAT tree. The tree is not part of the git checkout.

Point ``--root`` at a directory that contains ``GOAT/data/item_N``. Cropped
test items are scored from ``audio_and_midi_crop`` and that directory's
time-adjusted fine MIDI. Files under ``original_full_references`` are the
uncropped chart and are not the timing reference.

The fine MIDI's 120 BPM and 220 ticks per quarter are the file's timebase.
They are not the musical tempo. Note F1 ignores offsets. ``offset_f1`` also
requires the offset to land within 20% of the reference duration.

``--split train`` refuses official test ids. ``--frame-join`` applies
``frame_join.join_frame_dips`` after the published decoder so that comparison
can be repeated. The app decoder does not call it: the rule drops EGSet12
below the locked floor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from benchmarks.goat.frame_join import join_frame_dips
from benchmarks.goat.split import DIAGNOSTIC_TEST, primary, require_development, split_of
from benchmarks.regression.metrics import score_notes

REAL_SIGNALS = ('di', 'amp_1', 'amp_2', 'amp_3', 'amp_4', 'amp_5')


def _item_id(path: Path):
    for part in path.parts:
        if part.startswith('item_') and part[5:].isdigit():
            return int(part[5:])
    return None


def _audio(folder: Path, stem: str):
    for ext in ('.wav', '.flac'):
        path = folder / f'{stem}{ext}'
        if path.is_file():
            return path
    return None


def discover(root: Path):
    """Yield ``(item_id, folder, fine_midi)`` for cropped or full items.

    The uncropped chart directory is skipped, so a crop is not scored against
    the original MIDI clock.
    """
    found = {}
    for midi in Path(root).rglob('*_fine_aligned.mid'):
        if 'original_full_references' in midi.parts:
            continue
        item = _item_id(midi)
        if item is None:
            continue
        # Prefer the MIDI that sits beside the audio. A crop directory wins
        # over a full-item MIDI when both are present.
        rank = 1 if midi.parent.name == 'audio_and_midi_crop' else 0
        previous = found.get(item)
        if previous is None or rank >= previous[0]:
            found[item] = (rank, midi.parent, midi)
    for item, (_rank, folder, midi) in sorted(found.items()):
        yield item, folder, midi


def reference_notes(midi_path: Path, duration_s: float):
    """Sounding notes whose onset is inside the audio. The tempo meta is only a clock."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for note in inst.notes:
            start = float(note.start)
            if start < 0 or start >= duration_s:
                continue
            dur = float(note.end - note.start)
            if dur <= 0:
                continue
            notes.append({'time': start, 'duration': dur, 'midi': int(note.pitch)})
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def offset_f1(est, ref, onset_tol=0.05, offset_ratio=0.2):
    """Note F1 that also requires the offset, unlike the regression gate's onset-only F1."""
    import mir_eval
    if not est or not ref:
        return 0.0

    def intervals(notes):
        return np.asarray([[n['time'], n['time'] + max(float(n['duration']), 0.01)] for n in notes], dtype=float)

    def hz(notes):
        return np.asarray([440.0 * 2 ** ((int(n['midi']) - 69) / 12) for n in notes], dtype=float)

    _precision, _recall, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
        intervals(ref), hz(ref), intervals(est), hz(est),
        offset_ratio=offset_ratio, onset_tolerance=onset_tol)
    return float(f1)


def _signals(folder: Path, item: int, include_rse: bool):
    stem = f'item_{item}'
    found = []
    di = _audio(folder, stem)
    if di is not None:
        found.append(('di', di, False))
    for index in range(1, 6):
        path = _audio(folder, f'{stem}_amp_{index}')
        if path is not None:
            found.append((f'amp_{index}', path, False))
    if include_rse:
        rendered = _audio(folder, f'{stem}_gp')
        if rendered is not None:
            found.append(('rse', rendered, True))
    return found


def score_item(item: int, folder: Path, midi: Path, frame_join: bool, include_rse: bool = False):
    import librosa
    from server import riley

    rows = []
    for name, audio_path, synthetic in _signals(folder, item, include_rse):
        duration = float(sf.info(audio_path).duration)
        ref = reference_notes(midi, duration)
        y, sr = sf.read(audio_path, always_2d=False, dtype='float32')
        if getattr(y, 'ndim', 1) == 2:
            y = y.mean(axis=1)
        if sr != riley.SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=riley.SAMPLE_RATE)
        post = riley.posteriors(y, 'riley')
        notes, info = riley.decode(post)
        joined = 0
        if frame_join:
            notes, joined = join_frame_dips(notes, post['frame_output'])
        onset = score_notes(notes, ref, onset_tol=0.05)
        wide = score_notes(notes, ref, onset_tol=0.10)
        rows.append({
            'item': item,
            'split': split_of(item),
            'primary': primary(item) and not synthetic,
            'signal': name,
            'synthetic': synthetic,
            'frame_join': frame_join,
            'audio_s': round(duration, 3),
            'n_ref': len(ref),
            'n_est': len(notes),
            'joined': joined,
            'f1_50': round(onset['note_f1'], 4),
            'precision_50': round(onset['note_precision'], 4),
            'recall_50': round(onset['note_recall'], 4),
            'onset_f1_50': round(onset['onset_f1'], 4),
            'pitch_recall_300': round(onset['pitch_recall_300ms'], 4),
            'f1_100': round(wide['note_f1'], 4),
            'offset_f1_50': round(offset_f1(notes, ref), 4),
            'reverb_flag': info.get('reverb'),
        })
    return rows


def mean_primary(rows):
    kept = [row['f1_50'] for row in rows if row['primary'] and row['signal'] != 'rse']
    wide = [row['f1_100'] for row in rows if row['primary'] and row['signal'] != 'rse']
    off = [row['offset_f1_50'] for row in rows if row['primary'] and row['signal'] != 'rse']
    def avg(values):
        return None if not values else round(float(np.mean(values)), 4)
    return {'f1_50': avg(kept), 'f1_100': avg(wide), 'offset_f1_50': avg(off), 'n': len(kept)}


def score_split(root: Path, which: str, frame_join: bool, include_rse: bool = False):
    chosen = [
        (item, folder, midi) for item, folder, midi in discover(root)
        if which == 'all' or split_of(item) == which
    ]
    if which == 'train':
        require_development(item for item, _folder, _midi in chosen)
    rows = []
    for item, folder, midi in chosen:
        rows.extend(score_item(item, folder, midi, frame_join=frame_join, include_rse=include_rse))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description='Score a local GOAT tree. Research only. CC BY-NC 4.0.')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--split', choices=('train', 'test', 'all'), default='train')
    parser.add_argument('--frame-join', action='store_true',
                        help='Repeat the rejected frame-dip comparison. Does not change the app decoder.')
    parser.add_argument('--include-rse', action='store_true',
                        help='Also score the Guitar Pro synthetic render. It is not a real amplifier.')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    if args.split == 'test':
        print('Held-out evaluation. Do not choose a threshold from this output.')
        print(f'Diagnostic item(s) left out of the primary mean: {DIAGNOSTIC_TEST}')
    rows = score_split(args.root, args.split, frame_join=args.frame_join, include_rse=args.include_rse)
    summary = {'split': args.split, 'frame_join': args.frame_join, 'primary': mean_primary(rows), 'rows': rows}
    text = json.dumps(summary, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + '\n')
        print(f'wrote {args.out}')
    print(text)


if __name__ == '__main__':
    main()
