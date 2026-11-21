"""Your take to tab: a riff recorded on its own -> notes and a tempo guess (audio not kept)."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from server import app as module

client = TestClient(module.app)
HEADERS = {'X-Fretwork-Client': 'studio'}


def clicks(bpm=120, seconds=6, sr=22050, first=0.5):
    """Plucks on every beat: a decaying tone, so the tempo guess has something to lock on to."""
    y = np.zeros(int(sr*seconds))
    t = np.arange(int(sr*.3))/sr
    pluck = .5*np.sin(2*np.pi*196*t)*np.exp(-t*12)
    for k in range(int((seconds-first)*bpm/60)):
        at = int((first+k*60/bpm)*sr)
        y[at:at+len(pluck)] += pluck[:len(y)-at]
    buf = io.BytesIO()
    sf.write(buf, y, sr, format='WAV')
    return buf.getvalue()


def test_take_to_notes_with_tempo(monkeypatch, tmp_path):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.models, 'capabilities', lambda: {'separation': {'configured': True}, 'transcription': {'configured': True}})
    seen = {}

    def transcribe(path, **kwargs):
        seen['path'] = path
        return [{'id': i, 'time': .5+i*.5, 'duration': .4, 'midi': 55, 'amplitude': .7} for i in range(10)]
    monkeypatch.setattr(module.models, 'transcribe', transcribe)
    r = client.post('/api/takes/transcribe', headers=HEADERS, data={'consent': 'true'},
                    files={'take': ('t.wav', clicks(), 'audio/wav')})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body['notes']) == 10 and body['notes'][0]['midi'] == 55
    assert abs(body['bpm']-120) < 6
    assert abs(body['first_beat']-.5) < .08
    assert not list(tmp_path.iterdir()), 'the take is deleted after transcription'


def test_take_needs_consent():
    r = client.post('/api/takes/transcribe', headers=HEADERS, data={'consent': 'false'},
                    files={'take': ('t.wav', clicks(), 'audio/wav')})
    assert r.status_code == 422
