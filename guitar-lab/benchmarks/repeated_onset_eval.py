"""Heard-only F1 on a rendered guitar whose MIDI is known.

Renders repeated palm-muted notes and a slow control with the app's own
Karplus-Strong voice, then transcribes them. The chart is not fed back into
the note list. `--self-check` asserts the dense-onset fix beats the decoder
alone on fast chugs and does not lose the slow line.

    python -m benchmarks.repeated_onset_eval --self-check
"""
from __future__ import annotations

import argparse
import os
import tempfile

import numpy as np
import soundfile as sf

from benchmarks.heard_metrics import score_heard
from server.fx.playback import render_acoustic, render_distorted
from server import models, song_analysis as sa


def _power_chords():
    notes = []
    for i, root in enumerate([40, 40, 43, 45, 40, 38, 40, 45]):
        for midi in (root, root + 7, root + 12):
            notes.append({'time': 0.5 + i * 0.5, 'duration': 0.4, 'midi': midi,
                          'amplitude': 0.8, 'velocity': 0.8})
    return notes


def _notes(midi, n, ioi, dur, start=0.5, palm=False):
    pitch = midi if isinstance(midi, int) else None
    seq = midi if pitch is None else [pitch] * n
    return [{'time': start + i * ioi, 'duration': dur, 'midi': int(seq[i]),
             'amplitude': 0.85, 'velocity': 0.85, 'palm_mute': palm, 'damping': palm}
            for i in range(len(seq))]


def _transcribe(y, sr, thresholds, resegment):
    prev = os.environ.get('FRETWORK_RESEGMENT')
    os.environ['FRETWORK_RESEGMENT'] = '1' if resegment else '0'
    path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    path.close()
    try:
        sf.write(path.name, np.asarray(y, dtype=np.float32), sr, subtype='PCM_16')
        notes = models.transcribe(path.name, midi_min=40, midi_max=88, thresholds=thresholds)
        return notes
    finally:
        os.unlink(path.name)
        if prev is None:
            os.environ.pop('FRETWORK_RESEGMENT', None)
        else:
            os.environ['FRETWORK_RESEGMENT'] = prev


def evaluate(resegment=True):
    """Score a few rendered clips. Returns a list of result dicts."""
    sr = 44100
    scale = [40, 45, 50, 55, 59, 64, 69, 72, 76, 72, 69, 64, 59, 55, 50, 45]
    mel = [52, 55, 59, 62] * 8
    cases = [
        ('scale', _notes(scale, len(scale), 0.5, 0.4), 'clean', (0.6, 0.4), 'clean'),
        ('melody16', _notes(mel, len(mel), 60 / 108 / 4, 0.08), 'clean', (0.6, 0.4), 'clean'),
        ('chug108', _notes(40, 24, 60 / 108 / 4, 0.07, palm=True), 'distorted', (0.6, 0.4), 'distorted'),
        ('chug160', _notes(40, 24, 60 / 160 / 4, 0.05, palm=True), 'distorted', (0.6, 0.4), 'distorted'),
        ('chug216', _notes(40, 32, 60 / 216 / 4, 0.04, palm=True), 'distorted', (0.6, 0.4), 'distorted'),
        ('chug160_clean', _notes(40, 24, 60 / 160 / 4, 0.05, palm=True), 'clean', (0.6, 0.4), 'clean'),
        ('power', _power_chords(), 'distorted', (0.6, 0.4), 'distorted'),
    ]
    rows = []
    for name, ref, voice, thr, tone in cases:
        end = max(n['time'] + n['duration'] for n in ref) + 0.6
        render = render_acoustic if voice == 'clean' else render_distorted
        y = render(ref, sr=sr, length_s=end)
        if getattr(y, 'ndim', 1) == 2:
            y = y.mean(axis=1)
        raw = _transcribe(y, sr, thr, resegment=False)
        got = _transcribe(y, sr, thr, resegment=resegment)
        # Same cleanup the song path runs after transcription.
        raw_s = sa.suppress_harmonic_ghosts(raw, tone=tone, window=.15)
        got_s = sa.suppress_harmonic_ghosts(got, tone=tone, window=.15)
        before = score_heard(raw_s, ref)
        after = score_heard(got_s, ref)
        rows.append({
            'name': name, 'voice': voice, 'thresholds': thr,
            'before_f1': round(before['f1'], 4), 'after_f1': round(after['f1'], 4),
            'before_pitch': round(before['pitch_recall_loose'], 4),
            'after_pitch': round(after['pitch_recall_loose'], 4),
            'before_timing': None if before['timing_given_pitch'] is None else round(before['timing_given_pitch'], 4),
            'after_timing': None if after['timing_given_pitch'] is None else round(after['timing_given_pitch'], 4),
            'before_median_onset_ms': None if before['median_abs_onset_s'] is None else round(before['median_abs_onset_s'] * 1000, 1),
            'after_median_onset_ms': None if after['median_abs_onset_s'] is None else round(after['median_abs_onset_s'] * 1000, 1),
            'n_ref': before['n_ref'], 'n_before': before['n_est'], 'n_after': after['n_est'],
        })
    return rows


def self_check():
    rows = evaluate(resegment=True)
    by = {r['name']: r for r in rows}
    # Fast same-pitch chugs are the bug. Changing-pitch and slow lines must not regress.
    assert by['chug160']['after_f1'] >= by['chug160']['before_f1'] + 0.10, by['chug160']
    assert by['chug216']['after_f1'] >= by['chug216']['before_f1'] + 0.10, by['chug216']
    assert by['scale']['after_f1'] >= by['scale']['before_f1'] - 0.02, by['scale']
    assert by['melody16']['after_f1'] >= 0.95, by['melody16']
    assert by['chug108']['after_f1'] >= by['chug108']['before_f1'] - 0.02, by['chug108']
    assert by['chug160_clean']['after_f1'] >= by['chug160_clean']['before_f1'] + 0.10, by['chug160_clean']
    assert by['power']['after_f1'] >= by['power']['before_f1'] - 0.02, by['power']
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    rows = self_check() if args.self_check else evaluate(True)
    for r in rows:
        print(f"{r['name']:10} F1 {r['before_f1']:.3f} -> {r['after_f1']:.3f}  "
              f"pitch@300 {r['before_pitch']:.3f} -> {r['after_pitch']:.3f}  "
              f"timing|pitch {r['before_timing']} -> {r['after_timing']}  "
              f"median {r['before_median_onset_ms']} -> {r['after_median_onset_ms']} ms  "
              f"n {r['n_before']} -> {r['n_after']} / {r['n_ref']}")


if __name__ == '__main__':
    main()
