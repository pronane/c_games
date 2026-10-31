import hashlib
import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server import model_store as store
from server.app import app


def test_missing_checkpoint_never_ready(tmp_path):
    valid, detail = store.checkpoint_status(tmp_path)
    assert not valid and 'not been installed' in detail


def test_lfs_pointer_not_accepted(tmp_path):
    pointer = b'version https://git-lfs.github.com/spec/v1\noid sha256:34c22ccb\n'
    with pytest.raises(store.InvalidCheckpoint, match='Git LFS'):
        store.install_stream(io.BytesIO(pointer), tmp_path)
    assert not (tmp_path/store.CHECKPOINT).exists()
    assert not list(tmp_path.glob('*.part'))


def test_oversize_stream_bounded_and_existing_model_preserved(tmp_path, monkeypatch):
    (tmp_path/store.CHECKPOINT).write_bytes(b'existing')
    monkeypatch.setattr(store, 'EXPECTED_SIZE', 3)
    with pytest.raises(store.InvalidCheckpoint, match='exceeds'):
        store.install_stream(io.BytesIO(b'1234567890'), tmp_path)
    assert (tmp_path/store.CHECKPOINT).read_bytes() == b'existing'
    assert not list(tmp_path.glob('*.part'))


def test_hash_rejection_and_atomic_publication(tmp_path, monkeypatch):
    # Tiny test fixture only. Never masquerades as installed production weights.
    data = b'unit test fixture'
    monkeypatch.setattr(store, 'EXPECTED_SIZE', len(data))
    monkeypatch.setattr(store, 'EXPECTED_SHA256', hashlib.sha256(data).hexdigest())
    with pytest.raises(store.InvalidCheckpoint, match='SHA-256'):
        store.install_stream(io.BytesIO(b'x'*len(data)), tmp_path)
    assert not (tmp_path/store.CHECKPOINT).exists()
    result = store.install_stream(io.BytesIO(data), tmp_path)
    assert result['bytes'] == len(data)
    assert store.checkpoint_status(tmp_path)[0]
    assert (tmp_path/(store.MODEL_NAME+'.yaml')).read_text() == store.BAG_CONTENT
    assert json.loads((tmp_path/'provisioning.json').read_text())['sha256'] == hashlib.sha256(data).hexdigest()
    # A modified YAML cannot choose arbitrary model weights.
    (tmp_path/(store.MODEL_NAME+'.yaml')).write_text('models: [untrusted]')
    assert not store.checkpoint_status(tmp_path)[0]
    store._check_file.cache_clear()


def test_browser_installer_requires_operator_flag(monkeypatch):
    monkeypatch.delenv('FRETWORK_ALLOW_MODEL_INSTALL', raising=False)
    client = TestClient(app)
    response = client.post('/api/models/separation', headers={'X-Fretwork-Client': 'studio'},
                           files={'checkpoint': ('model.th', b'fake')})
    assert response.status_code == 403


def test_browser_installer_rejects_fake_model(monkeypatch, tmp_path):
    monkeypatch.setenv('FRETWORK_ALLOW_MODEL_INSTALL', '1')
    monkeypatch.setenv('FRETWORK_DEMUCS_REPO', str(tmp_path))
    response = TestClient(app).post('/api/models/separation', headers={'X-Fretwork-Client': 'studio'},
                                   files={'checkpoint': ('model.th', b'fake')})
    assert response.status_code == 422
    assert not (tmp_path/store.CHECKPOINT).exists()
