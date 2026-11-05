"""The render-and-revise loop on a known Karplus–Strong line.

The target audio is the guitar voice itself, so a correct transcription renders
back to the target. Pass 1 is that line with notes dropped, added, and shifted.
The loop has to recover them from the audio. A re-transcription that invents
pitches must not be kept, and the returned score must not fall below pass 1.
"""
import time

import pytest
import soundfile as sf

from server.refine import (
    refine_transcription, render_guitar, refinement_gate, skipped_refinement,
)


SR = 22050
LINE = [
    {'midi': 52, 'time': 0.30, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 55, 'time': 0.75, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 59, 'time': 1.20, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 62, 'time': 1.65, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 64, 'time': 2.10, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 67, 'time': 2.55, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 64, 'time': 3.00, 'duration': 0.34, 'amplitude': 0.75},
    {'midi': 59, 'time': 3.45, 'duration': 0.40, 'amplitude': 0.75},
]


def f1(est, ref, tol=0.05):
    used, tp = set(), 0
    for n in est:
        for i, r in enumerate(ref):
            if i in used:
                continue
            if int(n['midi']) == int(r['midi']) and abs(float(n['time']) - float(r['time'])) <= tol:
                used.add(i)
                tp += 1
                break
    precision = tp / max(1, len(est))
    recall = tp / max(1, len(ref))
    if precision + recall == 0:
        return 0.0, tp
    return 2 * precision * recall / (precision + recall), tp


def corrupt(notes):
    """Drop two notes, add one that is not in the line, and push one onset late."""
    out = [dict(n) for i, n in enumerate(notes) if i not in (2, 6)]
    out.append({'midi': 72, 'time': 1.85, 'duration': 0.28, 'amplitude': 0.8})
    for n in out:
        if n['midi'] == 64 and abs(n['time'] - 2.10) < 1e-6:
            n['time'] = 2.26
    return out


def write_target(path):
    y = render_guitar(LINE, sr=SR, length_s=4.1, seed=0)
    sf.write(path, y, SR)
    return y


def test_gate_matrix(monkeypatch):
    monkeypatch.delenv('FRETWORK_REFINE', raising=False)
    assert refinement_gate('guitar', False) == 'not requested'
    assert refinement_gate('guitar', True, notation=True) == 'notation reference is exact'
    assert refinement_gate('bass', True) == 'refinement is guitar-only'
    assert refinement_gate('guitar', True) == 'FRETWORK_REFINE is not set'
    monkeypatch.setenv('FRETWORK_REFINE', '1')
    assert refinement_gate('guitar', True) is None
    skipped = skipped_refinement('not requested')
    assert skipped['enabled'] is False and skipped['iterations'] == []


def test_loop_recovers_dropped_added_and_shifted_notes(tmp_path):
    path = tmp_path / 'line.wav'
    write_target(path)
    bad = corrupt(LINE)
    before, _ = f1(bad, LINE)
    calls = []

    def transcribe(path, thresholds=None, midi_min=40, midi_max=88):
        # Region retries keep offering the corrupted list. Recovery has to come
        # from comparing the rendering to the target, not from a better model.
        calls.append(thresholds)
        return [dict(n) for n in bad]

    started = time.perf_counter()
    out = refine_transcription(path, notes=bad, transcribe=transcribe, max_iterations=5, max_seconds=15)
    elapsed = time.perf_counter() - started
    got = out['notes']
    score, tp = f1(got, LINE)
    log = out['refinement']
    assert log['final_score'] + 1e-9 >= log['original_score']
    assert log['best_score'] + 1e-9 >= log['original_score']
    assert log['final_score'] >= before or score + 1e-9 >= before
    assert score + 1e-9 >= before
    assert tp >= 6  # most of the eight notes, including the ones pass 1 lost
    assert score >= 0.8
    assert all(n['midi'] != 72 for n in got)
    assert log['enabled'] is True and log['skipped'] is None
    assert log['iterations'][0]['action'] == 'first pass'
    assert log['iterations'][0]['changes'] == 0
    assert any(step['changes'] > 0 for step in log['iterations'])
    assert all('score' in step and 'changed' in step for step in log['iterations'])
    # Usable on a short line: the whole recovery stays under a few seconds.
    assert elapsed < 12
    assert log['elapsed_seconds'] < 12
    assert calls  # region re-transcription was attempted and not simply trusted


def test_never_returns_worse_than_pass_one(tmp_path):
    path = tmp_path / 'line.wav'
    write_target(path)
    bad = corrupt(LINE)

    def transcribe(path, thresholds=None, midi_min=40, midi_max=88):
        if thresholds is None:
            return [dict(n) for n in bad]
        # A looser threshold that invents a pitch the line does not contain.
        return [{'time': 0.05, 'duration': 0.2, 'midi': 80, 'amplitude': 0.95}]

    out = refine_transcription(path, notes=bad, transcribe=transcribe, max_iterations=4, max_seconds=15)
    log = out['refinement']
    assert log['final_score'] + 1e-9 >= log['original_score']
    first, _ = f1(bad, LINE)
    after, _ = f1(out['notes'], LINE)
    assert after + 1e-9 >= first
    assert all(n['midi'] != 80 for n in out['notes'])
    # The invented region transcription is not in the kept change list.
    assert not any('midi 80' in text or 'G#5' in text for step in log['iterations'] for text in step['changed'])


def test_time_cap_keeps_the_first_pass(tmp_path):
    path = tmp_path / 'line.wav'
    write_target(path)
    bad = corrupt(LINE)
    out = refine_transcription(path, notes=bad, transcribe=lambda *a, **k: bad, max_seconds=0, max_iterations=5)
    log = out['refinement']
    assert log['stopped'] == 'time cap'
    assert log['final_score'] == log['original_score']
    assert [(n['midi'], round(n['time'], 2)) for n in out['notes']] == [
        (n['midi'], round(n['time'], 2)) for n in sorted(bad, key=lambda n: (n['time'], n['midi']))
    ]
    assert log['iterations'][0]['action'] == 'first pass'


def test_options_dict_is_the_script_entry_point(tmp_path):
    path = tmp_path / 'line.wav'
    write_target(path)
    out = refine_transcription(str(path), {'notes': LINE, 'max_iterations': 1, 'max_seconds': 8, 'seed': 0})
    assert out['refinement']['original_score'] >= 0.9
    assert out['refinement']['final_score'] + 1e-9 >= out['refinement']['original_score']
    assert len(out['notes']) == len(LINE)


def test_benchmark_midi_loader_matches_pretty_midi(tmp_path):
    pretty_midi = pytest.importorskip('pretty_midi')
    from benchmarks.refine_eval import load_notes, note_f1, _parse_midi
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=24)
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0.5, end=0.9))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=64, start=1.0, end=1.4))
    pm.instruments.append(inst)
    mid = tmp_path / 'n.mid'
    pm.write(str(mid))
    via_lib = [(n['midi'], round(n['time'], 2)) for n in load_notes(mid)]
    via_parser = [(n['midi'], round(n['time'], 2)) for n in _parse_midi(mid)]
    assert via_lib == [(60, 0.5), (64, 1.0)]
    assert via_parser == via_lib
    assert note_f1(load_notes(mid), load_notes(mid)) == 1.0
