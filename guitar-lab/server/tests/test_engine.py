from types import SimpleNamespace
from server.devices import select_device, run_with_fallback
from server.analysis import observations, align
import numpy as np
import pytest


def hardware(cuda=False, mps=False):
    return SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda, empty_cache=lambda: None),
                           backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)))


def test_device_policies():
    assert select_device(hardware(), 'auto') == 'cpu'
    assert select_device(hardware(True), 'auto') == 'cuda'
    assert select_device(hardware(mps=True), 'auto') == 'mps'
    assert select_device(hardware(True), 'cpu') == 'cpu'
    with pytest.raises(RuntimeError):
        select_device(hardware(), 'cuda')


def test_known_gpu_failure_retries_same_operation(monkeypatch):
    monkeypatch.setenv('FRETWORK_DEVICE', 'auto')
    calls = []
    def operation(device):
        calls.append(device)
        if device == 'cuda':
            raise RuntimeError('CUDA out of memory')
        return 'same model output'
    value, device, warning = run_with_fallback(operation, hardware(True))
    assert calls == ['cuda', 'cpu'] and device == 'cpu' and warning
    assert value == 'same model output'


def test_no_fallback_for_unrelated_bug():
    with pytest.raises(RuntimeError, match='bad input'):
        run_with_fallback(lambda _: (_ for _ in ()).throw(RuntimeError('bad input')), hardware(True))


def test_one_to_one_matching_and_no_false_certainty():
    ref = [{'time': 1., 'midi': 60, 'duration': .5}]
    take = [{'time': 1.1, 'midi': 60, 'duration': .4}, {'time': 1.15, 'midi': 60, 'duration': .4}]
    result = observations(ref, take, {'map': [[0, 0], [2, 2]]})
    assert [f['kind'] for f in result['findings']] == ['matched', 'unmatched_take']
    assert result['mean_absolute_timing_seconds'] == pytest.approx(.1)
    assert 'No calibrated' in result['uncertainty']


def test_late_correct_note_is_timing_not_pitch():
    ref = [{'time': 1., 'midi': 60, 'duration': .3}, {'time': 1.3, 'midi': 64, 'duration': .3}]
    take = [{'time': 1.25, 'midi': 60, 'duration': .3}, {'time': 1.3, 'midi': 64, 'duration': .3}]
    result = observations(ref, take, {'map': [[0, 0], [2, 2]]})
    assert [f['kind'] for f in result['findings']] == ['timing_difference', 'matched']
    assert result['findings'][0]['latency_compensated_seconds'] == pytest.approx(.25)


def test_latency_is_compensated_for_labels_but_reported_raw():
    ref = [{'time': 1., 'midi': 60, 'duration': .3}]
    take = [{'time': 1.06, 'midi': 60, 'duration': .3}]
    result = observations(ref, take, {'map': [[0, 0], [2, 2]], 'median_offset_seconds': -.06})
    assert result['findings'][0]['kind'] == 'matched'
    assert result['findings'][0]['raw_timing_seconds'] == pytest.approx(.06)


def test_alignment_on_identical_musical_signal():
    sr = 22050
    t = np.arange(sr*2)/sr
    y = (.2*np.sin(2*np.pi*220*t)+.1*np.sin(2*np.pi*330*t)).astype(np.float32)
    result = align(y, y, sr)
    assert abs(result['median_offset_seconds']) < .04
    assert result['mean_chroma_cost'] < .05


def test_silence_abstains():
    with pytest.raises(ValueError, match='silent'):
        align(np.zeros(22050), np.zeros(22050))


def test_explicit_gpu_policy_does_not_fallback(monkeypatch):
    monkeypatch.setenv('FRETWORK_DEVICE', 'cuda')
    with pytest.raises(RuntimeError, match='out of memory'):
        run_with_fallback(lambda _: (_ for _ in ()).throw(RuntimeError('out of memory')), hardware(True))


def test_score_informed_finds_wrong_missed_late_and_extra_notes():
    from server.analysis import score_informed
    hop = .01
    onset = np.zeros((600, 88))
    def hit(t, midi, s=.9):
        onset[int(round(t/hop)), midi-21] = s
    refs = [{'time': t, 'duration': .3, 'midi': m} for t, m in
            [(0, 50), (.5, 52), (1, 54), (1.5, 55), (2, 57), (2.5, 59), (3, 50), (3, 57), (3, 62)]]
    lat = .04
    hit(0+lat, 50); hit(.5+lat, 52)
    hit(1+lat, 55)                 # wrong: 55 played instead of 54
    # 1.5 (55) missed entirely
    hit(2+lat+.18, 57)             # late by 180 ms
    hit(2.5+lat, 59, .4)           # quiet but present
    hit(3+lat, 50); hit(3+lat, 57); hit(3+lat, 62)   # chord, all there
    take_notes = [{'time': 4.2, 'duration': .2, 'midi': 64, 'amplitude': .8},     # extra
                  {'time': 3.04, 'duration': .3, 'midi': 74, 'amplitude': .8}]    # overtone of 62: ignored
    out = score_informed(refs, take_notes, {'onset': onset, 'note': onset, 'hop': hop})
    kinds = [(f['kind'], f.get('reference_midi'), f.get('take_midi')) for f in out['findings']]
    assert abs(out['estimated_latency_seconds']-lat) < .011
    assert ('pitch_difference', 54, 55) in kinds
    assert ('unmatched_reference', 55, None) in kinds
    assert ('timing_difference', 57, 57) in kinds
    assert ('unmatched_take', None, 64) in kinds
    assert sum(k[0] == 'matched' for k in kinds) == 6
    assert not any(k == ('unmatched_take', None, 74) for k in kinds)
