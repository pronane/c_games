"""Regression gate. Full clips are `python -m benchmarks.regression`.

Charts are not fed to the transcriber. The numeric guard replays the public
fast clips (one GuitarSet excerpt, rendered clean, rendered distorted, and a
reverb/clear pair) and compares them to the committed Basic Pitch reference.
EGSet12 and the Guitar-TECHS excerpts use the same no-drop check when those
files are on disk, and skip when they are not.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.regression.metrics import score_notes
from benchmarks.regression.tab_notes import INTRO_ORIGIN_S, INTRO_TAB_END_S
from benchmarks.score_alignment import ONE_FROZEN
from server.models import ModelUnavailable, capabilities, transcribe
from server.transcribers import backend_name, normalize_backend

REF = Path(__file__).resolve().parents[2] / 'benchmarks' / 'regression' / 'reference' / 'basic_pitch_fast.json'


def test_metrics_separate_pitch_from_onset():
    ref = [{'time': 0.0, 'duration': 0.3, 'midi': 60}, {'time': 0.5, 'duration': 0.3, 'midi': 64}]
    same = score_notes(ref, ref)
    assert same['note_f1'] == 1.0 and same['onset_f1'] == 1.0 and same['pitch_recall_300ms'] == 1.0
    wrong_pitch = [{'time': 0.0, 'duration': 0.3, 'midi': 61}, {'time': 0.5, 'duration': 0.3, 'midi': 65}]
    bad = score_notes(wrong_pitch, ref)
    assert bad['note_f1'] == 0.0
    assert bad['onset_f1'] == 1.0
    late = [{'time': 0.2, 'duration': 0.3, 'midi': 60}, {'time': 0.7, 'duration': 0.3, 'midi': 64}]
    slipped = score_notes(late, ref)
    assert slipped['note_f1'] == 0.0
    assert slipped['pitch_recall_300ms'] == 1.0


def test_intro_alignment_is_the_frozen_anchor():
    assert INTRO_ORIGIN_S == 18.35
    assert INTRO_TAB_END_S == 16.5
    assert ONE_FROZEN['origin_s'] == 19.3
    assert ONE_FROZEN['historical_f1_max_map']['used'] is False
    assert ONE_FROZEN['whole_song_linear_map'] is None


def test_default_backend_is_riley_or_basic_pitch(monkeypatch):
    from server.transcribers import default_backend
    monkeypatch.delenv('FRETWORK_TRANSCRIBER', raising=False)
    assert backend_name() == default_backend() in ('riley', 'basic_pitch')
    assert normalize_backend('guitar_fl') == 'riley'
    assert normalize_backend('gaps') == 'gaps'


def test_optional_backend_is_not_the_default_path(monkeypatch, tmp_path):
    import soundfile as sf
    path = tmp_path / 'a.wav'
    sf.write(path, np.zeros(22050, dtype=np.float32), 22050)
    monkeypatch.setenv('FRETWORK_TRANSCRIBER', 'riley')
    seen = {}

    def fake(name, audio_path, midi_min=40, midi_max=88):
        seen['name'] = name
        return [{'id': 0, 'time': 0.1, 'duration': 0.2, 'midi': 64, 'amplitude': 0.5}]

    monkeypatch.setattr('server.transcribers.transcribe_file', fake)
    notes = transcribe(path)
    assert seen['name'] == 'riley'
    assert notes[0]['midi'] == 64
    monkeypatch.undo()
    with pytest.raises(ModelUnavailable):
        transcribe(path, backend='not-a-model')


def test_catalog_covers_the_required_categories():
    from benchmarks.regression import catalog
    categories = {c['category'] for c in catalog.GUITARSET_CLIPS}
    categories |= {c['category'] for c in catalog.RENDERED}
    categories |= {c['category'] for c in catalog.EGSET12_CLIPS}
    categories |= {c['category'] for c in catalog.GUITAR_TECHS_CLIPS}
    categories.add('clean_electric')
    categories.add('full_band_intro')
    assert categories >= {
        'solo_acoustic', 'clean_electric', 'rendered', 'reverb_clear', 'full_band_intro',
        'amp_solo', 'amp_excerpt',
    }
    assert len(catalog.EGSET12_CLIPS) == 12
    assert len(catalog.GUITAR_TECHS_CLIPS) == 12


@pytest.mark.skipif(not capabilities()['transcription']['configured'], reason='Install optional ONNX transcription runtime')
def test_fast_public_clips_match_basic_pitch_reference():
    if not REF.is_file():
        pytest.skip('committed fast reference is missing')
    from benchmarks.regression.gate import CLIP_SLACK, assert_within
    from benchmarks.regression.score import score_backend
    got = [row for row in score_backend('basic_pitch', 'fast') if row.get('status') == 'ok']
    payload = json.loads(REF.read_text())
    rows = payload['backends']['basic_pitch']['rows'] if 'backends' in payload else payload.values()
    expected = [row for row in rows if row.get('status') == 'ok']
    assert {row['id'] for row in expected} <= {row['id'] for row in got}
    assert_within(got, expected, ('note_f1', 'onset_f1', 'pitch_recall_300ms'), slack=CLIP_SLACK)


def test_yourmt3_notes_drop_drums_dedupe_and_filter_programs():
    from server.transcribers import yourmt3_notes
    raw = [
        {'time': 0.0, 'duration': 0.5, 'midi': 52, 'program': 29, 'drum': False},
        {'time': 0.01, 'duration': 0.5, 'midi': 52, 'program': 30, 'drum': False},  # same note, other channel
        {'time': 0.0, 'duration': 0.1, 'midi': 36, 'program': 128, 'drum': True},
        {'time': 0.5, 'duration': 0.5, 'midi': 40, 'program': 33, 'drum': False},  # bass
        {'time': 1.0, 'duration': 0.002, 'midi': 64, 'program': 0, 'drum': False},  # labelled piano
    ]
    every = yourmt3_notes(raw, 28, 88)
    assert [(n['time'], n['midi']) for n in every] == [(0.0, 52), (0.5, 40), (1.0, 64)]
    assert every[2]['duration'] == 0.03
    assert [n['midi'] for n in yourmt3_notes(raw, 28, 88, 'guitar')] == [52]


def test_yourmt3_reports_missing_packages(monkeypatch):
    from server import transcribers, yourmt3
    from server.models import ModelUnavailable
    import pytest
    monkeypatch.setattr(yourmt3, 'available', lambda: False)
    with pytest.raises(ModelUnavailable, match='transformers'):
        transcribers._transcribe_yourmt3_path(transcribers.Path('x.wav'), 40, 88)
    assert transcribers.availability()['yourmt3']['installed'] is False


def test_studio_choice_of_transcriber_is_checked(monkeypatch):
    from server import transcribers
    assert transcribers.checked_backend('basic_pitch') == 'basic_pitch'
    import pytest
    with pytest.raises(ValueError, match='Unknown transcriber'):
        transcribers.checked_backend('magic')
    from server import yourmt3
    monkeypatch.setattr(yourmt3, 'available', lambda: False)
    with pytest.raises(ValueError, match='not installed'):
        transcribers.checked_backend('yourmt3')


def test_riley_reverb_rule_picks_threshold_per_stretch(monkeypatch):
    from server import riley
    # Notes per onset threshold, spread over 0-40 s: the first 20 s dry, the next 20 s wet.
    def notes(n, a, b):
        return [{'time': a + (b - a) * k / n, 'duration': 0.1} for k in range(n)]
    table = {0.3: notes(11, 0, 20) + notes(30, 20, 40), 0.65: notes(10, 0, 20) + notes(10, 20, 40),
             0.5: notes(12, 0, 20) + notes(25, 20, 40)}
    monkeypatch.setattr(riley, 'notes_from_posteriors', lambda out, onset=None, **k: table[onset or 0.3])
    out, info = riley.decode({})
    first = [n for n in out if n['time'] < 20]
    second = [n for n in out if n['time'] >= 20]
    assert len(first) == 12 and len(second) == 10       # dry stretch at 0.5, wet stretch at 0.65
    assert info['reverb'] == 'mixed' and info['wet_share'] == 0.5


def test_no_drop_gate_rejects_a_lower_score_and_keeps_an_improvement():
    from benchmarks.regression.gate import assert_no_drop, assert_within, drop_problems, match_problems
    locked = [{'id': 'egset_01', 'status': 'ok', 'category': 'amp_solo',
               'note_f1': 0.80, 'note_f1_100': 0.84, 'onset_f1': 0.81, 'pitch_recall_300ms': 0.90}]
    better = [{'id': 'egset_01', 'status': 'ok', 'category': 'amp_solo', 'sha256_ok': True,
               'note_f1': 0.91, 'note_f1_100': 0.93, 'onset_f1': 0.92, 'pitch_recall_300ms': 0.95}]
    assert drop_problems(better, locked) == []
    assert_no_drop(better, locked, got_means={'amp_solo': 0.91}, locked_means={'amp_solo': 0.80})
    worse = [dict(better[0], note_f1=0.70)]
    found = drop_problems(worse, locked)
    assert found and found[0]['key'] == 'note_f1' and found[0]['delta'] < 0
    with pytest.raises(AssertionError, match='dropped'):
        assert_no_drop(worse, locked)
    # The public fast clips are two-sided: a drop and a large jump both fail.
    moved = match_problems(worse, locked, ('note_f1',), slack=0.02)
    assert moved and moved[0]['id'] == 'egset_01'
    with pytest.raises(AssertionError, match='locked baseline'):
        assert_within(worse, locked, ('note_f1',))
    # A category-wide slip under the per-clip slack still fails the mean.
    slipped = [dict(better[0], note_f1=0.785)]
    assert drop_problems(slipped, locked) == []
    with pytest.raises(AssertionError, match='dropped'):
        assert_no_drop(slipped, locked, got_means={'amp_solo': 0.785}, locked_means={'amp_solo': 0.80})


def test_onset_lag_is_pitch_blind_and_recovers_a_known_delay():
    from benchmarks.regression.electric import onset_lag_seconds
    sr = 22050
    hop = 128
    delay = 0.04
    times = [0.30, 0.62, 0.95, 1.28, 1.60]
    y = np.zeros(int(2.2 * sr), dtype=np.float32)
    for start in times:
        index = int(round((start + delay) * sr))
        y[index:index + 16] += np.linspace(0.9, 0.0, 16, dtype=np.float32)
    notes = [{'time': start, 'duration': 0.08, 'midi': 40 + i} for i, start in enumerate(times)]
    shift, peak = onset_lag_seconds(y, sr, notes, limit_s=0.1, hop=hop)
    assert peak > 0.2
    assert abs(shift - delay) <= (hop / sr) + 0.01, (shift, peak)
    early = np.zeros_like(y)
    for start in times:
        index = int(round((start - delay) * sr))
        early[index:index + 16] += np.linspace(0.9, 0.0, 16, dtype=np.float32)
    back, _peak = onset_lag_seconds(early, sr, notes, limit_s=0.1, hop=hop)
    assert abs(back - (-delay)) <= (hop / sr) + 0.01, back


def test_jams_note_midi_keeps_every_string_and_drops_contours(tmp_path):
    from benchmarks.regression.electric import jams_note_midi
    payload = {
        'annotations': [
            {'namespace': 'note_midi', 'data': [{'time': 0.0, 'duration': 0.2, 'value': 40}]},
            {'namespace': 'note_midi', 'data': [{'time': 0.5, 'duration': 0.2, 'value': 45}]},
            {'namespace': 'pitch_contour', 'data': {'time': [0.0], 'duration': [1.0], 'value': [40.2], 'confidence': [1.0]}},
            {'namespace': 'tempo', 'data': [{'time': 0.0, 'duration': 1.0, 'value': 120}]},
        ],
    }
    path = tmp_path / 'clip.jams'
    path.write_text(json.dumps(payload))
    notes = jams_note_midi(path)
    assert [(n['time'], n['midi']) for n in notes] == [(0.0, 40), (0.5, 45)]


def test_electric_download_lists_only_the_two_open_sets():
    from benchmarks.regression.download import planned_downloads
    rows = planned_downloads()
    names = [name for _dataset, name, url, _md5, _size in rows]
    urls = [url for _dataset, name, url, _md5, _size in rows]
    assert sum(name == 'P3_music.zip' for name in names) == 1
    assert any(name == '01.wav' for name in names)
    assert any(name == '12.gp' for name in names)
    joined = ' '.join(names + urls)
    for banned in ('P1_chords', 'P2_chords', 'P1_scales', 'P2_scales', 'P1_techniques',
                   'P2_techniques', 'P1_singlenotes', 'P2_singlenotes', 'best_TabCNN',
                   'EGDB', 'cambridge', 'goat'):
        assert banned.lower() not in joined.lower()
    for url in urls:
        assert url.startswith('https://zenodo.org/api/records/')
        assert url.endswith('/content')
        assert ('11406378' in url) or ('14963133' in url)


def test_negative_reference_lag_stays_inside_the_file():
    from benchmarks.regression.score import _shift
    notes = _shift([
        {'time': 0.01, 'duration': 0.20, 'midi': 40},
        {'time': 0.00, 'duration': 0.01, 'midi': 41},
    ], -0.02)
    assert len(notes) == 1
    assert notes[0]['time'] == 0.0 and notes[0]['midi'] == 40 and notes[0]['duration'] > 0
    same = _shift([{'time': 1.0, 'duration': 0.5, 'midi': 60}], 0.25)
    assert same == [{'time': 1.25, 'duration': 0.5, 'midi': 60}]


def test_electric_rows_are_missing_when_the_audio_is_absent(tmp_path, monkeypatch):
    from benchmarks.regression import catalog
    from benchmarks.regression.gate import electric_gate_action
    from benchmarks.regression.score import score_egset12, score_guitar_techs
    monkeypatch.setattr(catalog, 'PRIVATE', tmp_path)
    assert electric_gate_action() == 'skip'
    assert score_egset12('basic_pitch')[0]['status'] == 'missing'
    assert score_guitar_techs('basic_pitch')[0]['status'] == 'missing'


def test_locked_electric_baselines_cover_both_sets():
    from benchmarks.regression.electric import ALIGNMENT, BASELINE, MANIFEST
    manifest = json.loads(MANIFEST.read_text())
    assert len(manifest['egset12']['files']) == 36
    assert manifest['guitar_techs']['archive']['name'] == 'P3_music.zip'
    assert manifest['licence'] == 'CC BY 4.0'
    for name, item in manifest['egset12']['files'].items():
        assert len(item['md5']) == 32 and len(item['sha256']) == 64
        if name.endswith(('.wav', '.jams')):
            assert item['size'] > 0
    extracted = manifest['guitar_techs']['extracted']
    assert len(extracted) == 36
    assert 'P3_music/audio/micamp/micamp_01.wav' in extracted
    assert 'P3_music/midi/midi_12.mid' in extracted
    alignment = json.loads(ALIGNMENT.read_text())
    assert alignment['guitar_techs_signal'] in ('micamp', 'directinput')
    assert alignment['limit_s'] == 0.1
    ids = {f'egset_{i:02d}' for i in range(1, 13)} | {f'techs_{i:02d}' for i in range(1, 13)}
    assert set(alignment['clips']) == ids
    baseline = json.loads(BASELINE.read_text())
    assert set(baseline['backends']) >= {'basic_pitch', 'riley'}
    for name, body in baseline['backends'].items():
        rows = {row['id']: row for row in body['rows']}
        assert set(rows) == ids
        for row in rows.values():
            assert row['status'] == 'ok'
            assert row['sha256_ok'] is True
            for key in ('note_f1', 'note_f1_100', 'onset_f1', 'pitch_recall_300ms'):
                assert 0.0 <= row[key] <= 1.0
        assert set(body['categories']) >= {'amp_solo', 'amp_excerpt'}


def test_electric_sets_do_not_drop_below_the_locked_baseline():
    from benchmarks.regression.gate import DOWNLOAD_HINT, electric_gate_action, run_electric_gate
    action = electric_gate_action()
    if action == 'skip':
        pytest.skip('EGSet12 and Guitar-TECHS are not on disk. ' + DOWNLOAD_HINT)
    if action == 'no-transcriber':
        pytest.skip('No transcriber is installed for the electric gate')
    problems = run_electric_gate()
    assert problems == []


def test_riley_is_the_default_when_installed(monkeypatch):
    from server import transcribers
    monkeypatch.delenv('FRETWORK_TRANSCRIBER', raising=False)
    monkeypatch.setattr(transcribers, '_spec_available', lambda m: True)
    assert transcribers.normalize_backend('') == 'riley'
    assert transcribers.normalize_backend('default') == 'riley'
    assert transcribers.availability()['riley']['default'] is True
    monkeypatch.setattr(transcribers, '_spec_available', lambda m: False)
    assert transcribers.normalize_backend(None) == 'basic_pitch'
    monkeypatch.setenv('FRETWORK_TRANSCRIBER', 'basic_pitch')
    monkeypatch.setattr(transcribers, '_spec_available', lambda m: True)
    assert transcribers.normalize_backend('') == 'basic_pitch'
