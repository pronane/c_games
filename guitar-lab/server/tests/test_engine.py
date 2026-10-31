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
