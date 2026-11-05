"""Synthetic take-vs-target diffs. Mistakes are planted in a note list, and one take is
rendered to MIDI and parsed back, so the assertion does not depend on Basic Pitch."""
import io
import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from server import app as module
from server import song_analysis as sa
from server.compare import (
    compare_take, compare_to_target, notes_from_midi, notes_from_musicxml, notes_to_midi,
    target_from_upload, transcribe_take,
)
from server.instruments import resolve_profile
from server.songs import SONGS, Song

HEADERS = {'X-Fretwork-Client': 'studio'}
STANDARD = [64, 59, 55, 50, 45, 40]


def at(bar, beat, midi, **extra):
    """120 BPM, 4/4. Bar 1 beat 1 is t = 0; bar 12 beat 3 is t = 23."""
    return {'time': (bar - 1) * 2.0 + (beat - 1) * 0.5, 'duration': 0.4, 'midi': midi, **extra}


def phrase():
    """Three bars whose pitches do not repeat, so a missing bar cannot attach to an earlier copy."""
    rows = {11: [60, 62, 64, 63], 12: [67, 69, 65, 71], 13: [72, 74, 76, 77]}
    return [at(bar, beat, midi) for bar, pitches in rows.items() for beat, midi in enumerate(pitches, 1)]


def target(notes, source='stem', **extra):
    return {'source': source, 'label': source, 'notes': notes, 'bpm': 120, 'beats_per_bar': 4, **extra}


def kinds(report):
    return [n['kind'] for n in report['notes']]


def test_wrong_pitch_is_named_in_the_bar():
    notes = phrase()
    take = [dict(n) for n in notes]
    planted = next(n for n in take if abs(n['time'] - 23) < 1e-9)
    planted['midi'] = 64  # E4 where bar 12 beat 3 writes F4
    report = compare_to_target(take, target(notes))
    wrong = [n for n in report['notes'] if n['kind'] == 'wrong_pitch']
    assert [n['message'] for n in wrong] == ['bar 12 beat 3: played E4, expected F4']
    assert kinds(report).count('correct') == len(notes) - 1
    assert set(kinds(report)) == {'correct', 'wrong_pitch'}
    assert report['worst_bars'][0]['bar'] == 12
    assert report['worst_bars'][0]['messages'] == ['bar 12 beat 3: played E4, expected F4']
    assert report['summary']['pitch_accuracy'] == pytest.approx(11 / 12, abs=1e-3)
    assert report['summary']['timing_accuracy'] == 1
    assert report['summary']['completeness'] == 1
    assert report['summary']['overall'] == 96


def test_one_late_note_is_late_in_ms_and_beats():
    notes = phrase()
    take = [dict(n) for n in notes]
    next(n for n in take if abs(n['time'] - 23) < 1e-9)['time'] = 23.25
    report = compare_to_target(take, target(notes))
    late = [n for n in report['notes'] if n['kind'] == 'late']
    assert len(late) == 1
    assert late[0]['message'] == 'bar 12 beat 3: F4 was 250 ms late (0.50 beats)'
    assert late[0]['delta_ms'] == 250
    assert late[0]['delta_beats'] == pytest.approx(0.5, abs=0.01)
    assert kinds(report).count('correct') == len(notes) - 1
    assert set(kinds(report)) == {'correct', 'late'}


def test_a_missing_bar_is_only_those_notes():
    notes = phrase()
    take = [n for n in notes if not 22 <= n['time'] < 24]
    report = compare_to_target(take, target(notes))
    missing = [n for n in report['notes'] if n['kind'] == 'missing']
    assert len(missing) == 4
    assert {n['message'] for n in missing} == {
        'bar 12 beat 1: missed G4',
        'bar 12 beat 2: missed A4',
        'bar 12 beat 3: missed F4',
        'bar 12 beat 4: missed B4',
    }
    assert kinds(report).count('correct') == len(notes) - 4
    assert set(kinds(report)) == {'correct', 'missing'}
    assert report['summary']['completeness'] == pytest.approx(8 / 12, abs=1e-3)


def test_slower_take_with_a_little_jitter_is_not_a_timing_mistake():
    notes = phrase()
    take = []
    for i, n in enumerate(notes):
        jitter = 0.02 if i % 2 else -0.015
        take.append({**n, 'time': n['time'] * 1.5 + jitter, 'duration': n['duration'] * 1.5})
    report = compare_to_target(take, target(notes))
    assert set(kinds(report)) == {'correct'}
    assert report['summary']['speed_ratio'] == pytest.approx(1 / 1.5, abs=0.05)
    assert report['summary']['overall'] == 100


def test_constant_latency_is_not_called_late():
    notes = phrase()
    take = [{**n, 'time': n['time'] + 0.03} for n in notes]
    report = compare_to_target(take, target(notes))
    assert set(kinds(report)) == {'correct'}


def test_extra_note_and_wrong_duration_and_wrong_string():
    notes = phrase()
    extra = [dict(n) for n in notes]
    extra.append({'time': 20.25, 'duration': 0.2, 'midi': 50})  # not an octave of either neighbour
    report = compare_to_target(extra, target(notes))
    assert [n['message'] for n in report['notes'] if n['kind'] == 'extra'] == ['bar 11 beat 1: extra D3']
    assert kinds(report).count('correct') == len(notes)

    long = [dict(n) for n in notes]
    next(n for n in long if abs(n['time'] - 23) < 1e-9)['duration'] = 1.2
    report = compare_to_target(long, target(notes))
    held = [n for n in report['notes'] if n['kind'] == 'wrong_duration']
    assert len(held) == 1
    assert 'held too long' in held[0]['message']
    assert 'played 1200 ms, expected 400 ms' in held[0]['message']
    assert kinds(report).count('correct') == len(notes) - 1

    tab = [
        {**at(1, 1, 64), 'string': 1, 'fret': 0},
        {**at(1, 2, 65), 'string': 1, 'fret': 1},
        {**at(1, 3, 67), 'string': 1, 'fret': 3},
    ]
    played = [dict(n) for n in tab]
    played[1] = {**played[1], 'string': 2, 'fret': 6}  # same F4, wrong place on the neck
    report = compare_to_target(played, target(tab, source='notation'))
    wrong = [n for n in report['notes'] if n['kind'] == 'wrong_string']
    assert [n['message'] for n in wrong] == ['bar 1 beat 2: played string 2 fret 6, expected string 1 fret 1']
    assert kinds(report).count('correct') == 2


def test_a_wrong_chord_tone_does_not_spoil_the_others():
    notes = [
        {'time': 0, 'duration': .5, 'midi': 60},
        {'time': 0, 'duration': .5, 'midi': 64},
        {'time': 0, 'duration': .5, 'midi': 67},
        {'time': 1, 'duration': .5, 'midi': 62},
        {'time': 2, 'duration': .5, 'midi': 69},
    ]
    take = [dict(n) if n['midi'] != 64 else dict(n, midi=65) for n in notes]
    report = compare_to_target(take, target(notes))
    assert [n['message'] for n in report['notes'] if n['kind'] != 'correct'] == [
        'bar 1 beat 1: played F4, expected E4']
    assert kinds(report).count('correct') == 4


def test_stem_and_notation_are_scored_separately_and_combined():
    notes = phrase()
    take = [dict(n) for n in notes]
    next(n for n in take if abs(n['time'] - 23) < 1e-9)['midi'] = 64
    both = compare_take(take, [target(notes, 'stem'), target(notes, 'notation')])
    assert [r['source'] for r in both['reports']] == ['stem', 'notation']
    assert both['reports'][0]['summary']['overall'] == both['reports'][1]['summary']['overall'] == 96
    assert both['combined']['overall'] == 96
    assert both['combined']['pitch_accuracy'] == pytest.approx(11 / 12, abs=1e-3)
    assert 'stem' in both['combined']['detail'] and 'notation' in both['combined']['detail']
    only = compare_take(take, [target(notes, 'file')])
    assert only['combined'] is None


def test_midi_rendered_take_finds_the_planted_wrong_note():
    notes = phrase()
    take = [dict(n) for n in notes]
    next(n for n in take if abs(n['time'] - 23) < 1e-9)['midi'] = 64
    parsed = notes_from_midi(notes_to_midi(take, bpm=120))
    assert [n['midi'] for n in parsed['notes']] == [n['midi'] for n in take]
    for got, want in zip(parsed['notes'], take):
        assert got['time'] == pytest.approx(want['time'], abs=0.01)
    report = compare_to_target(parsed['notes'], target(notes, source='file'))
    assert [n['message'] for n in report['notes'] if n['kind'] == 'wrong_pitch'] == [
        'bar 12 beat 3: played E4, expected F4']
    assert kinds(report).count('correct') == len(notes) - 1


def test_musicxml_and_text_tab_and_guitar_pro_refusal():
    written = [{'time': i * .5, 'duration': .45, 'midi': m, 'string': 1, 'fret': i}
               for i, m in enumerate([64, 65, 67, 69])]
    beats = [i * .5 for i in range(16)]
    xml = sa.musicxml(written, beats, {'fifths': 0, 'mode': 'major'}, STANDARD, title='Line', voices=1)
    parsed = notes_from_musicxml(xml)
    assert [n['midi'] for n in parsed['notes']] == [64, 65, 67, 69]
    assert parsed['notes'][1]['time'] == pytest.approx(0.5, abs=0.02)
    assert parsed['notes'][0]['string'] == 1 and parsed['notes'][0]['fret'] == 0
    chart = target_from_upload('line.musicxml', xml.encode())
    take = [dict(n) for n in chart['notes']]
    take[2] = dict(take[2], midi=take[2]['midi'] + 1)
    report = compare_to_target(take, chart)
    assert kinds(report).count('wrong_pitch') == 1
    tab = "e|--0--1--3--|\nB|----------|\nG|----------|\nD|----------|\nA|----------|\nE|----------|\n"
    text = target_from_upload('riff.txt', tab.encode(), bpm=120)
    assert [n['midi'] for n in text['notes']][:3] == [64, 65, 67]
    assert text['source'] == 'file'
    with pytest.raises(ValueError, match='Guitar Pro'):
        target_from_upload('solo.gp5', b'not a guitar pro file')


def _wav():
    buf = io.BytesIO()
    t = np.arange(22050 * 2) / 22050
    sf.write(buf, (.2 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), 22050, format='WAV')
    return buf.getvalue()


def test_clean_guitar_transcription_path(monkeypatch):
    from server import models
    seen = {}

    def fake(path, midi_min=40, midi_max=88, thresholds=None, **kwargs):
        seen.update(midi_min=midi_min, midi_max=midi_max, thresholds=thresholds)
        return [{'id': 0, 'time': 0.2, 'duration': 0.3, 'midi': 64, 'amplitude': 0.6}]

    monkeypatch.setattr(models, 'transcribe', fake)
    notes = transcribe_take('ignored.wav')
    assert notes[0]['midi'] == 64
    assert seen['thresholds'] == models.thresholds_for('clean', True)
    assert seen['midi_min'] == resolve_profile('guitar')['midi_min']


def test_compare_api_scores_both_targets_and_an_uploaded_midi(monkeypatch):
    client = TestClient(module.app)
    notes = [at(1, 1, 64), at(1, 2, 65), at(1, 3, 67), at(1, 4, 69)]
    take = [dict(n) for n in notes]
    take[1] = dict(take[1], midi=64)
    body = {
        'take_notes': json.dumps(take),
        'targets': json.dumps([target(notes, 'stem'), target(notes, 'notation')]),
    }
    assert client.post('/api/compare', data=body).status_code == 403
    got = client.post('/api/compare', headers=HEADERS, data=body)
    assert got.status_code == 200, got.text
    payload = got.json()
    assert payload['transcription'] == 'notes supplied'
    assert payload['combined']['overall'] < 100
    assert {r['source'] for r in payload['reports']} == {'stem', 'notation'}
    assert any(n['message'] == 'bar 1 beat 2: played E4, expected F4' for n in payload['reports'][0]['notes'])

    seen = {}

    def fake(path, **kwargs):
        seen['thresholds'] = kwargs.get('thresholds')
        seen['path'] = str(path)
        return [{'time': 0.0, 'duration': 0.4, 'midi': 64, 'amplitude': 0.7},
                {'time': 0.5, 'duration': 0.4, 'midi': 64, 'amplitude': 0.7}]

    monkeypatch.setattr(module.models, 'transcribe', fake)
    audio = client.post('/api/compare', headers=HEADERS,
                        data={'targets': json.dumps([target(notes[:2], 'stem')])},
                        files={'take': ('take.wav', _wav(), 'audio/wav')})
    assert audio.status_code == 200, audio.text
    assert audio.json()['transcription'] == 'clean-guitar Basic Pitch'
    assert seen['thresholds'] == module.models.thresholds_for('clean', True)
    assert seen['path'].endswith('.wav')
    assert any(n['kind'] == 'wrong_pitch' for n in audio.json()['reports'][0]['notes'])

    midi = notes_to_midi(take, bpm=120)
    uploaded = client.post('/api/compare', headers=HEADERS, data={'take_notes': json.dumps(notes)},
                           files={'score_file': ('chart.mid', midi, 'audio/midi')})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()['reports'][0]['source'] == 'file'
    assert kinds_of(uploaded.json()) == ['correct', 'wrong_pitch', 'correct', 'correct']
    refused = client.post('/api/compare', headers=HEADERS, data={'take_notes': json.dumps(notes)},
                          files={'score_file': ('solo.gpx', b'GP', 'application/octet-stream')})
    assert refused.status_code == 422 and 'Guitar Pro' in refused.json()['detail']


def kinds_of(payload):
    return [n['kind'] for n in payload['reports'][0]['notes']]


def _guitar_song(tmp_path, instrument='guitar', key='cmp-song'):
    folder = tmp_path / key
    folder.mkdir()
    song = Song(key, folder, instrument, 'Riff', status='complete', active=False)
    song.notes = {'g': [
        {'time': 0.0, 'duration': 0.4, 'midi': 64, 'amplitude': 0.8},
        {'time': 0.5, 'duration': 0.4, 'midi': 65, 'amplitude': 0.8},
        {'time': 1.0, 'duration': 0.4, 'midi': 67, 'amplitude': 0.8},
        {'time': 1.5, 'duration': 0.4, 'midi': 69, 'amplitude': 0.8},
    ]}
    song.result = {
        'duration': 4.0,
        'parts': [{'id': 'g', 'label': 'Guitar', 'roles': [
            {'bar': 1, 'start': 0.0, 'end': 2.0, 'role': 'lead'},
            {'bar': 2, 'start': 2.0, 'end': 4.0, 'role': 'rest'},
        ]}],
        'tempo': {'bpm': 120, 'beats': [i * 0.5 for i in range(8)], 'bars': [0.0, 2.0], 'time_signature': '4/4'},
    }
    SONGS[song.id] = song
    return song


def test_song_compare_scores_stem_and_notation_and_keeps_five_takes(tmp_path, monkeypatch):
    song = _guitar_song(tmp_path)
    monkeypatch.setattr('server.compare.transcribe_take', lambda path: [
        {'time': 0.0, 'duration': 0.4, 'midi': 64},
        {'time': 0.5, 'duration': 0.4, 'midi': 64},  # F4 written, E4 played
        {'time': 1.0, 'duration': 0.4, 'midi': 67},
        {'time': 1.5, 'duration': 0.4, 'midi': 69},
    ])
    client = TestClient(module.app)
    try:
        _song_compare_body(client, song, tmp_path)
    finally:
        SONGS.pop(song.id, None)
        SONGS.pop('bass-song', None)


def _song_compare_body(client, song, tmp_path):
    def post():
        return client.post(f'/api/songs/{song.id}/compare', headers=HEADERS,
                           data={'parts': 'g', 'role': 'any', 'tuning': 'standard', 'capo': '0',
                                 'start': '0', 'end': '2', 'speed': '1'},
                           files={'take': ('take.wav', _wav(), 'audio/wav')})
    first = post()
    assert first.status_code == 200, first.text
    body = first.json()
    assert {r['source'] for r in body['reports']} == {'stem', 'notation'}
    assert body['transcription'] == 'clean-guitar Basic Pitch'
    assert body['combined'] is not None and body['combined']['overall'] < 100
    for report in body['reports']:
        assert any(n['message'] == 'bar 1 beat 2: played E4, expected F4' for n in report['notes'])
        assert sum(n['kind'] == 'correct' for n in report['notes']) == 3
    assert body['history'][-1]['label'] == 'Take 1'
    for _ in range(5):
        assert post().status_code == 200
    assert [h['label'] for h in song.comparisons] == ['Take 2', 'Take 3', 'Take 4', 'Take 5', 'Take 6']
    assert len(client.get(f'/api/songs/{song.id}').json())  # song status still the old shape
    assert 'comparisons' not in client.get(f'/api/songs/{song.id}').json()
    bass = _guitar_song(tmp_path, instrument='bass', key='bass-song')
    refused = client.post(f'/api/songs/{bass.id}/compare', headers=HEADERS,
                          data={'parts': 'g', 'start': '0', 'end': '2'},
                          files={'take': ('take.wav', _wav(), 'audio/wav')})
    assert refused.status_code == 422 and 'guitar' in refused.json()['detail']
