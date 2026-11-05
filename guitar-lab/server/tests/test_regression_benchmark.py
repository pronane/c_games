"""Fast regression subset. Full clips are `python -m benchmarks.regression`.

Charts are not fed to the transcriber. The numeric guard replays the public
fast clips (one GuitarSet excerpt, rendered clean, rendered distorted, and a
reverb/clear pair) and compares them to the committed Basic Pitch reference.
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
    assert INTRO_ORIGIN_S == 19.3
    assert INTRO_TAB_END_S == 16.5
    assert ONE_FROZEN['origin_s'] == 19.3
    assert ONE_FROZEN['historical_f1_max_map']['used'] is False
    assert ONE_FROZEN['whole_song_linear_map'] is None


def test_default_backend_is_basic_pitch(monkeypatch):
    monkeypatch.delenv('FRETWORK_TRANSCRIBER', raising=False)
    assert backend_name() == 'basic_pitch'
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
    categories.add('clean_electric')
    categories.add('full_band_intro')
    assert categories >= {'solo_acoustic', 'clean_electric', 'rendered', 'reverb_clear', 'full_band_intro'}


@pytest.mark.skipif(not capabilities()['transcription']['configured'], reason='Install optional ONNX transcription runtime')
def test_fast_public_clips_match_basic_pitch_reference():
    if not REF.is_file():
        pytest.skip('committed fast reference is missing')
    from benchmarks.regression.score import score_backend
    got = {row['id']: row for row in score_backend('basic_pitch', 'fast') if row.get('status') == 'ok'}
    payload = json.loads(REF.read_text())
    rows = payload['backends']['basic_pitch']['rows'] if 'backends' in payload else payload.values()
    expected = {row['id']: row for row in rows if row.get('status') == 'ok'}
    assert set(expected) <= set(got)
    for clip_id, ref_row in expected.items():
        row = got[clip_id]
        for key in ('note_f1', 'onset_f1', 'pitch_recall_300ms'):
            if ref_row.get(key) is None:
                continue
            assert abs(row[key] - ref_row[key]) <= 0.02, (clip_id, key, row[key], ref_row[key])
        if 'cross_f1' in ref_row:
            assert abs(row['cross_f1'] - ref_row['cross_f1']) <= 0.02
