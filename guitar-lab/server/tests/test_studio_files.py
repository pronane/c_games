import importlib
from fastapi.testclient import TestClient


def test_built_studio_is_served_without_shadowing_the_api(tmp_path, monkeypatch):
    (tmp_path/'index.html').write_text('<!doctype html><title>Studio</title>')
    (tmp_path/'assets').mkdir()
    (tmp_path/'assets'/'app.js').write_text('console.log(1)')
    monkeypatch.setenv('FRETWORK_UI_DIR', str(tmp_path))
    from server import app as module
    module = importlib.reload(module)
    client = TestClient(module.app)
    assert 'Studio' in client.get('/').text
    assert client.get('/assets/app.js').headers['content-type'].startswith(('application/javascript', 'text/javascript'))
    assert client.get('/api/health').json()['service'] == 'Fretwork Python engine'
    assert client.get('/api/jobs/nope').status_code == 404
    monkeypatch.delenv('FRETWORK_UI_DIR')
    importlib.reload(module)


def test_shutdown_only_for_the_local_launcher(monkeypatch):
    import signal
    from server import app as module
    client = TestClient(module.app)
    h = {'X-Fretwork-Client': 'studio'}
    monkeypatch.delenv('FRETWORK_LOCAL_APP', raising=False)
    assert client.post('/api/shutdown', headers=h).status_code == 403
    monkeypatch.setenv('FRETWORK_LOCAL_APP', '1')
    assert client.post('/api/shutdown').status_code == 403            # needs the studio header
    raised = []
    monkeypatch.setattr(signal, 'raise_signal', lambda s: raised.append(s))
    # TestClient's peer is 'testclient', not this computer: refused.
    assert client.post('/api/shutdown', headers=h).status_code == 403
    local = TestClient(module.app, client=('127.0.0.1', 50000))
    assert local.post('/api/shutdown', headers=h).status_code == 202
    import time
    time.sleep(.4)
    assert raised == [signal.SIGINT]
