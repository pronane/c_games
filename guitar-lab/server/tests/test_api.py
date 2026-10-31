import io
import time
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from server import app as module

client = TestClient(module.app)
HEADERS = {'X-Fretwork-Client': 'studio'}


def audio():
    buf = io.BytesIO()
    t = np.arange(22050*2)/22050
    sf.write(buf, .2*np.sin(2*np.pi*220*t), 22050, format='WAV')
    return buf.getvalue()


def upload(**extra):
    return client.post('/api/jobs', headers=HEADERS, data={'kind': 'mix', 'consent': 'true', **extra},
                       files={'reference': ('r.wav', audio(), 'audio/wav'), 'take': ('t.wav', audio(), 'audio/wav')})


def configured(monkeypatch):
    monkeypatch.setattr(module.models, 'capabilities', lambda: {'separation': {'configured': True}, 'transcription': {'configured': True}})


def wait_job(key, target):
    deadline = time.monotonic()+60
    while time.monotonic() < deadline:
        data = client.get('/api/jobs/'+key).json()
        if data['status'] == target:
            return data
        assert data['status'] != 'failed', data
        time.sleep(.02)
    raise AssertionError('job timed out')


def test_consent_and_client_header():
    assert upload(consent='false').status_code == 422
    assert client.post('/api/jobs', data={'kind': 'mix', 'consent': 'true'},
                       files={'reference': ('r.wav', audio()), 'take': ('t.wav', audio())}).status_code == 403


def test_missing_models_does_not_save_audio(monkeypatch):
    monkeypatch.setattr(module.models, 'capabilities', lambda: {'separation': {'configured': False}, 'transcription': {'configured': False}})
    before = set(module.ROOT.iterdir())
    assert upload().status_code == 503
    assert set(module.ROOT.iterdir()) == before


def test_review_gate_edit_and_delete(monkeypatch):
    # Mocks validate orchestration, not model quality. Real feature alignment runs.
    configured(monkeypatch)
    monkeypatch.setattr(module.models, 'separate_guitar', lambda a, sr: (a, sr, {'model': 'test double', 'device': 'cpu'}))
    monkeypatch.setattr(module.models, 'transcribe', lambda _, **kwargs: [{'id': 0, 'time': .3, 'duration': .4, 'midi': 57, 'amplitude': .7}])
    response = upload(original_offset='33')
    assert response.status_code == 202
    key = response.json()['id']
    review = wait_job(key, 'review')
    assert review['result'] is None
    assert client.get(review['guitar_url']).headers['content-type'].startswith('audio/wav')
    assert client.post(f'/api/jobs/{key}/approve', headers=HEADERS, json={'approved': False}).status_code == 422
    assert client.post(f'/api/jobs/{key}/approve', headers=HEADERS, json={'approved': True}).status_code == 202
    data = wait_job(key, 'complete')
    assert data['original_offset'] == 33
    assert data['result']['comparison']['pitch_difference_candidates'] == 0
    edits = {'notes': [{'id': 0, 'time': .3, 'duration': .4, 'midi': 58}]}
    changed = client.put(f'/api/jobs/{key}/notes', headers=HEADERS, json=edits).json()
    assert changed['result']['comparison']['pitch_difference_candidates'] == 1
    assert changed['result']['provenance']['edited'] is True
    assert client.delete(f'/api/jobs/{key}', headers=HEADERS).status_code == 204
    assert client.get(f'/api/jobs/{key}').status_code == 404
    assert not (module.ROOT/key).exists()


def test_invalid_duration_and_non_audio(monkeypatch):
    configured(monkeypatch)
    assert upload(original_offset='nan').status_code == 422
    r = client.post('/api/jobs', headers=HEADERS, data={'kind': 'isolated', 'consent': 'true'},
                    files={'reference': ('bad.wav', b'not audio'), 'take': ('ok.wav', audio())})
    assert r.status_code == 422


def test_inference_failure_is_visible_and_never_substituted(monkeypatch):
    configured(monkeypatch)
    def failed(*_):
        raise RuntimeError('Official checkpoint failed to load')
    monkeypatch.setattr(module.models, 'separate_guitar', failed)
    key = upload().json()['id']
    data = wait_job(key, 'failed')
    assert data['result'] is None and data['guitar_url'] is None
    assert 'checkpoint' in data['error']
    client.delete('/api/jobs/'+key, headers=HEADERS)


def test_no_edit_before_transcription_and_expiry(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(module.models, 'separate_guitar', lambda a, sr: (a, sr, {}))
    key = upload().json()['id']
    wait_job(key, 'review')
    job = module.JOBS[key]
    assert client.put(f'/api/jobs/{key}/notes', headers=HEADERS, json={'notes': []}).status_code == 409
    job.created -= module.TTL_SECONDS+1
    module.cleanup()
    assert client.get('/api/jobs/'+key).status_code == 404
    assert not job.folder.exists()
