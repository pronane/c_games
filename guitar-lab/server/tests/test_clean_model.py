import numpy as np

from server import clean_model as cm


def test_off_by_default_and_tone_gated(monkeypatch):
    monkeypatch.delenv('FRETWORK_CLEAN_MODEL', raising=False)
    assert not cm.active_for('distorted')
    monkeypatch.setenv('FRETWORK_CLEAN_MODEL', '1')
    assert cm.active_for('distorted') and cm.active_for('crunch')
    assert not cm.active_for('clean') and not cm.active_for(None)


def test_shipped_model_is_small_json_and_scores():
    assert cm.MODEL_PATH.stat().st_size < 5_000_000
    m = cm.load_model()
    assert m['features'] == cm.FEATURE_NAMES
    cand = [{'time': .5, 'duration': .3, 'midi': 52, 'amplitude': .8}, {'time': .5, 'duration': .3, 'midi': 64, 'amplitude': .2}]
    on = np.zeros((200, 88)); note = np.zeros((200, 88))
    on[43, 31] = .9; note[43:70, 31] = .8; on[43, 43] = .3; note[43:70, 43] = .3
    keep, info = cm.refine(cand, {'onset': on, 'note': note, 'hop': 256 / 22050}, {'scores': {'distortion': .9}}, m)
    assert info['candidates'] == 2 and all(0 <= n['clean_model_p'] <= 1 for n in keep)


def test_label_candidates_matches_pitch_and_onset():
    cand = [{'time': 1.0, 'midi': 60}, {'time': 1.0, 'midi': 72}, {'time': 2.2, 'midi': 60}]
    ref = [{'time': 1.02, 'midi': 60}, {'time': 2.0, 'midi': 60}]
    assert cm.label_candidates(cand, ref).tolist() == [1, 0, 0]
