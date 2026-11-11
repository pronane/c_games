"""The user's recordings lock the song-path decoder. No ground-truth tab.

The check skips when the private AAC files are absent, and fails when they
are present but the transcription moves. Take A, B, and C are not a confirmed
dry/wet pair. The file packaged as the latest upload is the same bytes as take C.
"""
import json

import numpy as np
import pytest

from benchmarks.recordings.gate import SLACK, lock_problems, recordings_gate_action, run_recordings_gate
from benchmarks.recordings.score import LOCK, pitch_class_cosine, playback_onset_lag_s, timing_summary


def _note(time, midi, duration=0.3):
    return {'time': time, 'duration': duration, 'midi': midi, 'amplitude': 0.8}


def _row(name, n_notes, sha='abc'):
    notes = [_note(0.5 + i * 0.4, 60 + (i % 5)) for i in range(n_notes)]
    summary = timing_summary(notes, duration_s=20.0)
    summary['playback_onset_lag_s'] = 0.004
    return {'id': name, 'sha256': sha, **summary}


def test_there_is_no_ground_truth_and_a_move_fails():
    locked = {
        'ground_truth': False,
        'rows': [_row('take_a_4m51.aac', 10)],
        'pairs': [{
            'src': 'take_a_4m51.aac', 'dst': 'take_c_synth_4m58.aac',
            'note_f1_50': 0.40, 'onset_f1_50': 0.50, 'pitch_class_cosine': 0.80,
        }],
    }
    same = {'rows': [_row('take_a_4m51.aac', 10)], 'pairs': list(locked['pairs'])}
    assert lock_problems(same, locked) == []
    moved = {'rows': [_row('take_a_4m51.aac', 40)], 'pairs': list(locked['pairs'])}
    problems = lock_problems(moved, locked)
    assert any(item['key'] == 'n_notes' for item in problems)
    claimed = dict(locked, ground_truth=True)
    assert any(item.get('problem', '').startswith('lock file claims') for item in lock_problems(same, claimed))


def test_pitch_class_and_playback_lag_are_measured_without_a_chart():
    notes = [_note(0.4, 64), _note(1.2, 67), _note(2.0, 71), _note(2.8, 74)]
    assert pitch_class_cosine(notes, notes) == 1.0
    summary = timing_summary(notes, 4.0)
    assert summary['n_notes'] == 4
    assert abs(summary['notes_per_second'] - 1.0) < 1e-6
    lag = playback_onset_lag_s(notes)
    assert lag is not None and lag < 0.02


def test_recordings_gate_skips_when_the_audio_is_absent(tmp_path):
    assert recordings_gate_action(tmp_path) == 'skip'


def test_recordings_gate_fails_a_different_file(tmp_path):
    for name in (
        'current_upload.aac', 'take_a_4m51.aac', 'take_b_1m44.aac', 'take_c_synth_4m58.aac',
    ):
        (tmp_path / name).write_bytes(b'not the recording')
    assert recordings_gate_action(tmp_path) == 'checksum'


def test_locked_recording_file_does_not_invent_a_ground_truth():
    if not LOCK.is_file():
        pytest.skip('recording lock has not been written')
    payload = json.loads(LOCK.read_text())
    assert payload['ground_truth'] is False
    ids = {row['id'] for row in payload['rows']}
    assert ids == {
        'current_upload.aac', 'take_a_4m51.aac', 'take_b_1m44.aac', 'take_c_synth_4m58.aac',
    }
    current = next(row for row in payload['rows'] if row['id'] == 'current_upload.aac')
    take_c = next(row for row in payload['rows'] if row['id'] == 'take_c_synth_4m58.aac')
    assert current['sha256'] == take_c['sha256']
    identical = next(pair for pair in payload['pairs'] if pair['src'] == 'current_upload.aac')
    assert identical['note_f1_50'] == 1.0
    for row in payload['rows']:
        assert row['n_notes'] > 0
        assert len(row['pitch_class']) == 12
        assert abs(sum(row['pitch_class']) - 1) < 0.02


def test_user_recordings_do_not_move(monkeypatch):
    action = recordings_gate_action()
    if action == 'skip':
        pytest.skip('Private user AAC files are not on disk. They are not in git.')
    if action == 'no-transcriber':
        pytest.skip('Riley is not installed')
    if action == 'checksum':
        raise AssertionError('private recordings are present but do not match the locked checksums')
    problems = run_recordings_gate()
    assert problems == [], problems
    assert SLACK == 0.02


def test_a_one_bin_pitch_shift_is_outside_the_slack():
    locked_row = _row('take_a_4m51.aac', 8)
    shifted = dict(locked_row)
    shifted['pitch_class'] = list(locked_row['pitch_class'])
    shifted['pitch_class'][0] = round(shifted['pitch_class'][0] + 0.05, 4)
    shifted['pitch_class'][1] = round(max(0.0, shifted['pitch_class'][1] - 0.05), 4)
    problems = lock_problems(
        {'rows': [shifted], 'pairs': []},
        {'ground_truth': False, 'rows': [locked_row], 'pairs': []},
    )
    assert any(str(item.get('key', '')).startswith('pitch_class') for item in problems)
