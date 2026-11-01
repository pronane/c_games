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
    monkeypatch.setattr(module.models, 'separate_guitar', lambda a, sr, *_: (a, sr, {'model': 'test double', 'device': 'cpu'}))
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
    monkeypatch.setattr(module.models, 'separate_guitar', lambda a, sr, *_: (a, sr, {}))
    key = upload().json()['id']
    wait_job(key, 'review')
    job = module.JOBS[key]
    assert client.put(f'/api/jobs/{key}/notes', headers=HEADERS, json={'notes': []}).status_code == 409
    job.created -= module.TTL_SECONDS+1
    module.cleanup()
    assert client.get('/api/jobs/'+key).status_code == 404
    assert not job.folder.exists()


def test_processing_defaults_to_cpu_and_gpu_needs_a_card(monkeypatch):
    from server import devices
    configured(monkeypatch)
    assert devices.default_policy() == 'cpu' or devices.os.getenv('FRETWORK_DEVICE')
    monkeypatch.setattr(devices, 'gpu_info', lambda: {'available': False, 'detail': 'none'})
    r = upload(processing='gpu')
    assert r.status_code == 422 and 'graphics card' in r.json()['detail']
    assert upload(processing='tpu').status_code == 422
    seen = []
    monkeypatch.setattr(devices, 'gpu_info', lambda: {'available': True, 'kind': 'cuda'})
    monkeypatch.setattr(module.models, 'separate_guitar', lambda a, sr, policy=None: (seen.append(policy) or a, sr, {'device': 'cuda'}))
    key = upload(processing='gpu').json()['id']
    wait_job(key, 'review')
    key2 = upload().json()['id']
    wait_job(key2, 'review')
    assert seen == ['auto', 'cpu']
    for k in (key, key2):
        client.delete('/api/jobs/'+k, headers=HEADERS)


def test_tab_reference_notes_skip_review_and_reference_transcription(monkeypatch):
    import json
    configured(monkeypatch)
    calls = []
    def transcribe(path, posteriors=False, **kw):
        calls.append(str(path))
        notes = [{'id': 0, 'time': .5, 'duration': .4, 'midi': 57, 'amplitude': .7}]
        if not posteriors:
            return notes
        hop = .01
        onset = np.zeros((200, 88))
        onset[50, 57-21] = .9                     # A3 struck at 0.5 s; B3 at 1.0 s never played
        return notes, {'onset': onset, 'note': onset, 'hop': hop}
    monkeypatch.setattr(module.models, 'transcribe', transcribe)
    tab = [{'time': .5, 'duration': .4, 'midi': 57, 'string': 3, 'fret': 2},
           {'time': 1.0, 'duration': .4, 'midi': 59, 'string': 2, 'fret': 0}]
    r = upload(kind='isolated', reference_notes=json.dumps(tab))
    assert r.status_code == 202
    done = wait_job(r.json()['id'], 'complete')
    res = done['result']
    assert [n['midi'] for n in res['reference_notes']] == [57, 59]
    assert len(calls) == 1 and calls[0].endswith('take.wav')          # only the take is transcribed
    assert {f['kind'] for f in res['comparison']['findings']} == {'matched', 'unmatched_reference'}
    assert 'uploaded tab' in res['provenance']['transcription']
    assert res['comparison']['method'].startswith('score-informed')
    bad = upload(kind='isolated', reference_notes=json.dumps([{'time': .1, 'duration': .2, 'midi': 30}]))
    assert bad.status_code == 422 and 'outside' in bad.json()['detail']
    assert upload(kind='mix', reference_notes=json.dumps(tab)).status_code == 422
    assert upload(kind='isolated', reference_notes='not json').status_code == 422
    client.delete('/api/jobs/'+r.json()['id'], headers=HEADERS)
