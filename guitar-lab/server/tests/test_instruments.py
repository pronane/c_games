import io
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from server.instruments import resolve_profile
from server import app as module
from server import models


def test_catalogue_ranges_and_tunings():
    assert resolve_profile('bass')['midi_min'] == 28
    assert len(resolve_profile('bass')['open_strings']) == 4
    guitar = resolve_profile('guitar', 'drop_d', 2)
    assert guitar['open_strings'][-1] == 40 and guitar['max_fret'] == 22
    piano = resolve_profile('piano', 'none')
    assert piano['midi_min'] == 21 and piano['midi_max'] == 108 and piano['open_strings'] == []


@pytest.mark.parametrize('args', [('flute',), ('bass', 'standard', 2), ('guitar', 'invalid'), ('piano', 'none', 0, 'tablature')])
def test_invalid_profiles_rejected(args):
    with pytest.raises(ValueError):
        resolve_profile(*args)


def wav():
    b = io.BytesIO()
    sf.write(b, .1*np.sin(2*np.pi*220*np.arange(22050*2)/22050), 22050, format='WAV')
    return b.getvalue()


def test_bass_profile_used_for_separation_and_transcription(monkeypatch):
    calls = []
    monkeypatch.setattr(module.models, 'capabilities', lambda: {'separation': {'configured': True}, 'transcription': {'configured': True}})
    monkeypatch.setattr(module.models, 'separate_instrument', lambda a, sr, stem, policy=None: (calls.append(stem) or a, sr, {'stem': stem}))
    def transcribe(path, **kwargs):
        calls.append(kwargs)
        return [{'id': 0, 'time': .3, 'duration': .4, 'midi': 28, 'amplitude': .6}]
    monkeypatch.setattr(module.models, 'transcribe', transcribe)
    client = TestClient(module.app)
    headers = {'X-Fretwork-Client': 'studio'}
    r = client.post('/api/jobs', headers=headers, data={'consent': 'true', 'kind': 'mix', 'instrument': 'bass'}, files={'reference': ('r.wav', wav()), 'take': ('t.wav', wav())})
    assert r.status_code == 202
    import time
    def wait_job(key, target):
        for _ in range(3000):
            data = client.get('/api/jobs/'+key).json()
            if data['status'] == target:
                return data
            assert data['status'] != 'failed', data
            time.sleep(.02)
        raise AssertionError('Job timed out')
    key = r.json()['id']
    wait_job(key, 'review')
    assert calls == ['bass']
    client.post(f'/api/jobs/{key}/approve', headers=headers, json={'approved': True})
    complete = wait_job(key, 'complete')
    assert calls[1:] == [{'midi_min': 28, 'midi_max': 67}]*2
    assert complete['instrument_profile']['separation_stem'] == 'bass'
    valid = {'notes': [{'id': 0, 'time': .3, 'duration': .4, 'midi': 28, 'string': 4, 'fret': 0}]}
    assert client.put(f'/api/jobs/{key}/notes', headers=headers, json=valid).status_code == 200
    valid['notes'][0]['string'] = 6
    assert client.put(f'/api/jobs/{key}/notes', headers=headers, json=valid).status_code == 422
    client.delete(f'/api/jobs/{key}', headers=headers)


def test_bad_profile_rejected_before_model_gates_or_storage():
    client = TestClient(module.app)
    before = set(module.ROOT.iterdir())
    r = client.post('/api/jobs', headers={'X-Fretwork-Client': 'studio'}, data={'consent': 'true', 'kind': 'isolated', 'instrument': 'flute'}, files={'reference': ('r.wav', wav()), 'take': ('t.wav', wav())})
    assert r.status_code == 422 and set(module.ROOT.iterdir()) == before
