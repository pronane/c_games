"""Note F1 of a guitar transcription against a MIDI key, with and without refinement.

    python -m benchmarks.refine_eval stem.wav notes.mid
    python -m benchmarks.refine_eval stem.wav notes.json --max-seconds 20
    python -m benchmarks.refine_eval --self-check

`stem.wav` is the guitar stem or a clean single-guitar take, not a full mix.
`notes.mid` / `notes.json` is the MIDI key (`time`, `duration`, `midi`).

The self-check renders eight known notes with the Karplus–Strong voice, corrupts
the first pass (two dropped, one added, one shifted), and prints note F1 and
seconds. That is the only measurement stored here.

What is not measured: real MIDI-keyed recordings, amplifier tone, bends,
chords, or full-band separation. A later job runs this script on those takes.
The match score compares a Karplus–Strong rendering with the target, so on a
real amp take the absolute score stays well below the synthetic ceiling; only
the change in score, and the note F1 against the MIDI key, are the result.

Note F1 ignores offsets and counts an onset within 50 ms at the same pitch.
With mir_eval installed, that is `precision_recall_f1_overlap`. Otherwise a
local matcher with the same rule is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

# guitar-lab/ on the path when launched as `python -m benchmarks.refine_eval`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _simple_f1(est, ref, tol=0.05):
    used, tp = set(), 0
    for n in est:
        for i, r in enumerate(ref):
            if i in used:
                continue
            if int(n['midi']) == int(r['midi']) and abs(float(n['time']) - float(r['time'])) <= tol:
                used.add(i)
                tp += 1
                break
    if not est and not ref:
        return 1.0
    precision = tp / max(1, len(est))
    recall = tp / max(1, len(ref))
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def note_f1(est, ref, tol=0.05):
    """Onset F1 at `tol` seconds. Offsets are ignored."""
    est, ref = list(est or []), list(ref or [])
    try:
        import mir_eval
        import numpy as np
    except ImportError:
        return _simple_f1(est, ref, tol)
    if not est or not ref:
        return 0.0
    ri = np.array([[n['time'], n['time'] + max(float(n.get('duration', 0.1)), 0.01)] for n in ref])
    ei = np.array([[n['time'], n['time'] + max(float(n.get('duration', 0.1)), 0.01)] for n in est])
    rp = np.array([440 * 2 ** ((int(n['midi']) - 69) / 12) for n in ref])
    ep = np.array([440 * 2 ** ((int(n['midi']) - 69) / 12) for n in est])
    _p, _r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ri, rp, ei, ep, offset_ratio=None, onset_tolerance=tol)
    return float(f)


def _vlq(data, i):
    value = 0
    while True:
        byte = data[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i


def _parse_midi(path):
    """Format 0/1 note-on/note-off to seconds. Enough for a single-tempo key."""
    data = Path(path).read_bytes()
    if data[:4] != b'MThd':
        raise ValueError(f'{path} is not a standard MIDI file.')
    div = int.from_bytes(data[12:14], 'big')
    if div & 0x8000:
        raise ValueError('SMPTE time-division MIDI is not supported.')
    ntrks = int.from_bytes(data[10:12], 'big')
    pos, tempos, pending, finished = 14, [(0, 500000)], {}, []
    for _ in range(ntrks):
        if data[pos:pos + 4] != b'MTrk':
            raise ValueError(f'{path} has a truncated track.')
        length = int.from_bytes(data[pos + 4:pos + 8], 'big')
        pos += 8
        end, tick, status = pos + length, 0, 0
        while pos < end:
            delta, pos = _vlq(data, pos)
            tick += delta
            if data[pos] & 0x80:
                status = data[pos]
                pos += 1
            if status == 0xFF:
                kind = data[pos]
                pos += 1
                size, pos = _vlq(data, pos)
                payload, pos = data[pos:pos + size], pos + size
                if kind == 0x51 and size == 3:
                    tempos.append((tick, int.from_bytes(payload, 'big')))
                continue
            if status in (0xF0, 0xF7):
                size, pos = _vlq(data, pos)
                pos += size
                continue
            kind = status & 0xF0
            if kind in (0xC0, 0xD0):
                pos += 1
                continue
            if kind not in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                break
            data1, data2 = data[pos], data[pos + 1]
            pos += 2
            key = (status & 0x0F, data1)
            if kind == 0x90 and data2:
                pending[key] = tick
            elif kind in (0x80, 0x90):
                start = pending.pop(key, None)
                if start is not None and tick > start:
                    finished.append((start, tick, data1))
        pos = end
    tempos.sort()

    def seconds(tick):
        last_tick, last_us, acc = 0, 500000, 0.0
        for at, us in tempos:
            if at >= tick:
                break
            acc += (at - last_tick) * last_us / div / 1e6
            last_tick, last_us = at, us
        return acc + (tick - last_tick) * last_us / div / 1e6

    notes = [{'time': seconds(a), 'duration': max(0.04, seconds(b) - seconds(a)), 'midi': m}
             for a, b, m in finished]
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def load_notes(path):
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = data.get('notes', [])
        return sorted(data, key=lambda n: (n['time'], n['midi']))
    try:
        import pretty_midi
    except ImportError:
        return _parse_midi(path)
    pm = pretty_midi.PrettyMIDI(str(path))
    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            notes.append({'time': float(n.start), 'duration': max(0.04, float(n.end - n.start)), 'midi': int(n.pitch)})
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def evaluate(audio_path, midi_path, *, refine=True, midi_min=40, midi_max=88, **options):
    """First-pass note F1, and the refined F1 when `refine` is set.

    Requires the Basic Pitch runtime for a real audio file. The returned dict
    is what a measurement job should record.
    """
    from server import models
    ref = load_notes(midi_path)
    first = models.transcribe(audio_path, midi_min=midi_min, midi_max=midi_max)
    report = {
        'audio': str(audio_path), 'midi': str(midi_path), 'reference_notes': len(ref),
        'first_pass_notes': len(first), 'first_pass_f1': round(note_f1(first, ref), 4),
        'refined_f1': None, 'refined_notes': None, 'seconds': None, 'refinement': None,
    }
    if refine:
        from server.refine import refine_transcription
        started = time.perf_counter()
        out = refine_transcription(audio_path, notes=first, midi_min=midi_min, midi_max=midi_max, **options)
        report['seconds'] = round(time.perf_counter() - started, 3)
        report['refined_notes'] = len(out['notes'])
        report['refined_f1'] = round(note_f1(out['notes'], ref), 4)
        report['refinement'] = out['refinement']
    return report


def self_check():
    """Synthetic timing and F1. Does not load Basic Pitch or a real recording."""
    import soundfile as sf
    import tempfile
    from server.refine import refine_transcription, render_guitar
    from server.tests.test_refine import LINE, corrupt
    bad = corrupt(LINE)

    def transcribe(path, thresholds=None, midi_min=40, midi_max=88):
        return [dict(n) for n in bad]

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'line.wav'
        sf.write(path, render_guitar(LINE, length_s=4.1, seed=0), 22050)
        started = time.perf_counter()
        out = refine_transcription(path, notes=bad, transcribe=transcribe, max_iterations=5, max_seconds=15)
        elapsed = time.perf_counter() - started
    return {
        'kind': 'synthetic Karplus-Strong, not a real recording',
        'first_pass_f1': round(note_f1(bad, LINE), 4),
        'refined_f1': round(note_f1(out['notes'], LINE), 4),
        'original_score': out['refinement']['original_score'],
        'final_score': out['refinement']['final_score'],
        'stopped': out['refinement']['stopped'],
        'seconds': round(elapsed, 3),
        'iterations': len(out['refinement']['iterations']),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Note F1 with and without guitar-transcription refinement.')
    parser.add_argument('audio', nargs='?', help='Guitar stem or clean guitar take.')
    parser.add_argument('midi', nargs='?', help='MIDI key (.mid) or a JSON note list.')
    parser.add_argument('--self-check', action='store_true', help='Synthetic Karplus–Strong timing run.')
    parser.add_argument('--no-refine', action='store_true', help='Score the first pass only.')
    parser.add_argument('--max-seconds', type=float, default=20)
    parser.add_argument('--max-iterations', type=int, default=5)
    parser.add_argument('--midi-min', type=int, default=40)
    parser.add_argument('--midi-max', type=int, default=88)
    parser.add_argument('--json', type=Path, help='Write the report JSON here.')
    args = parser.parse_args(argv)
    if args.self_check:
        report = self_check()
    else:
        if not args.audio or not args.midi:
            parser.error('pass AUDIO MIDI, or --self-check')
        report = evaluate(
            args.audio, args.midi, refine=not args.no_refine,
            midi_min=args.midi_min, midi_max=args.midi_max,
            max_seconds=args.max_seconds, max_iterations=args.max_iterations)
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
