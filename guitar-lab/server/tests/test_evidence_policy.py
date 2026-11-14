import numpy as np
import pytest

from server.evidence_policy import guarded_level
from server.compare import compare_take


def test_quiet_dynamic_signal_lift_is_bounded_and_does_not_mutate():
    sr = 16000
    y = np.sin(np.arange(sr*2)*.08).astype(np.float32)*.005
    y[:sr//2] = 0
    original = y.copy()
    lifted, info = guarded_level(y, sr)
    np.testing.assert_array_equal(y, original)
    assert 0 < info['gain_db'] <= 24.00001
    assert np.max(np.abs(lifted)) <= .95
    assert len(lifted) == len(y)


@pytest.mark.parametrize('mode', ['silence', 'noise', 'normal', 'empty'])
def test_guard_does_not_boost_unqualified_audio(mode):
    rng = np.random.default_rng(1)
    y = {'silence': np.zeros(16000), 'noise': rng.normal(0,.002,16000),
         'normal': np.sin(np.arange(16000)*.08)*.2, 'empty': np.zeros(0)}[mode]
    got, info = guarded_level(y,16000)
    np.testing.assert_array_equal(got,y.astype(np.float32))
    assert info['gain_db'] == 0


def test_nonfinite_input_is_rejected():
    with pytest.raises(ValueError):
        guarded_level(np.array([np.nan]),16000)


def test_duration_review_is_audio_only_and_preserves_diagnostics(monkeypatch):
    ref = [{'time':i*.5,'duration':.4,'midi':60+i} for i in range(12)]
    take = [dict(n) for n in ref]
    take[6]['duration'] = .05
    targets = [{'source':'file','notes':ref}]
    monkeypatch.delenv('FRETWORK_DURATION_REVIEW',raising=False)
    base = compare_take(take,targets,transcription='clean-guitar Riley')
    monkeypatch.setenv('FRETWORK_DURATION_REVIEW','1')
    review = compare_take(take,targets,transcription='clean-guitar Riley')
    assert review['reports'][0]['summary'] == base['reports'][0]['summary']
    assert review['reports'][0]['duration_policy'] == 'review_only'
    warning = next(n for n in review['reports'][0]['notes'] if n['kind']=='wrong_duration')
    assert 'not a confirmed playing mistake' in warning['message']
    assert any('review by ear' in msg for bar in review['reports'][0]['bars'] for msg in bar['messages'])
    supplied = compare_take(take,targets)
    assert 'duration_policy' not in supplied['reports'][0]
    assert 'held too short' in next(n for n in supplied['reports'][0]['notes'] if n['kind']=='wrong_duration')['message']
