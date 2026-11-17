"""Which separator a request gets: Demucs on CPU, BS-RoFormer SW with a graphics card."""
import numpy as np

from server import models, roformer


def _gpu(monkeypatch, available):
    monkeypatch.setattr(models, 'gpu_info', lambda: {'available': available, 'kind': 'cuda' if available else None,
                                                    'name': 'card' if available else None, 'detail': ''})


def test_cpu_requests_use_demucs(monkeypatch):
    monkeypatch.delenv('FRETWORK_SEPARATOR', raising=False)
    _gpu(monkeypatch, True)
    monkeypatch.setattr(roformer, 'status', lambda: (True, 'ok'))
    assert models.choose_separator('cpu') == 'demucs'


def test_graphics_card_uses_roformer_when_installed(monkeypatch):
    monkeypatch.delenv('FRETWORK_SEPARATOR', raising=False)
    _gpu(monkeypatch, True)
    monkeypatch.setattr(roformer, 'status', lambda: (True, 'ok'))
    assert models.choose_separator('auto') == 'roformer'
    monkeypatch.setattr(roformer, 'status', lambda: (False, 'not installed'))
    assert models.choose_separator('auto') == 'demucs'


def test_no_card_means_demucs(monkeypatch):
    monkeypatch.delenv('FRETWORK_SEPARATOR', raising=False)
    _gpu(monkeypatch, False)
    monkeypatch.setattr(roformer, 'status', lambda: (True, 'ok'))
    assert models.choose_separator('auto') == 'demucs'


def test_environment_forces_a_separator(monkeypatch):
    _gpu(monkeypatch, False)
    monkeypatch.setenv('FRETWORK_SEPARATOR', 'roformer')
    assert models.choose_separator('cpu') == 'roformer'
    monkeypatch.setenv('FRETWORK_SEPARATOR', 'demucs')
    assert models.choose_separator('auto') == 'demucs'


def test_separate_stem_uses_the_chosen_separator(monkeypatch):
    monkeypatch.delenv('FRETWORK_SEPARATOR', raising=False)
    _gpu(monkeypatch, True)
    monkeypatch.setattr(roformer, 'status', lambda: (True, 'ok'))
    stems = {k: np.zeros((10, 2), np.float32) for k in ('bass', 'drums', 'other', 'vocals', 'guitar', 'piano')}
    monkeypatch.setattr(roformer, 'separate', lambda audio, sr: (stems, 44100, {'model': roformer.NAME}))
    monkeypatch.setattr(models, 'run_demucs', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Demucs was used')))
    guitar, rate, provenance = models.separate_stem(np.zeros((10, 2), np.float32), 44100, 'guitar', 'auto')
    assert provenance['model'] == roformer.NAME and provenance['stem'] == 'guitar' and rate == 44100


def test_roformer_status_without_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setenv('FRETWORK_ROFORMER_DIR', str(tmp_path))
    good, detail = roformer.status()
    assert not good
