"""A take scored against the player's own tab (lined up with the song) comes first and sets the score."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from server import songs
from server.tests.test_song_path import HEADERS, SECONDS, SR, _notes, _post, _provenance, _quiet, _run_inline, _stereo, _tone


def _song(monkeypatch):
    from server import app as module
    _run_inline(monkeypatch)
    n = int(SECONDS * SR)
    guitar = _stereo(_tone(330, n, amp=0.25), _tone(330, n, amp=0.25))

    def separate(audio, sr, policy=None):
        stems = {name: _quiet(len(audio)) for name in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')}
        stems['guitar'] = guitar[:len(audio)]
        return stems, sr, _provenance(stems)

    monkeypatch.setattr(songs.models, 'run_demucs', separate)
    monkeypatch.setattr(songs.models, 'transcribe', lambda path, **kw: _notes())
    client = TestClient(module.app)
    response = _post(client, guitar.astype(np.float32), transcriber='basic_pitch')
    assert response.status_code == 202, response.text
    return client, response.json()['id']


def _take_bytes():
    buf = io.BytesIO()
    sf.write(buf, np.zeros(int(SECONDS * SR), np.float32), SR, format='WAV', subtype='PCM_16')
    return buf.getvalue()


def test_tab_part_is_scored_first_and_sets_the_score(monkeypatch):
    client, key = _song(monkeypatch)
    try:
        song = songs.SONGS[key]
        # The tab has one wrong note (E5 where the app heard D5); the player played the tab.
        tab = [dict(n) for n in _notes()]
        tab[3]['midi'] = 76
        song.tab_parts = {'parts': [{'name': 'Lead', 'track': 0, 'sections': [], 'notes': tab}], 'assigned': {}}
        played = [{'time': n['time'], 'duration': n['duration'], 'midi': n['midi'], 'amplitude': 0.8} for n in tab]
        monkeypatch.setattr(songs.take_diff, 'transcribe_take_heard', lambda path, backend=None: (played, None))
        form = {'parts': 'guitar', 'role': 'any', 'tuning': 'standard', 'capo': '0', 'start': '0',
                'end': str(SECONDS), 'speed': '1', 'transcriber': 'basic_pitch'}
        got = client.post(f'/api/songs/{key}/compare', headers=HEADERS, data={**form, 'tab_part': 'Lead'},
                          files={'take': ('take.wav', _take_bytes(), 'audio/wav')})
        assert got.status_code == 200, got.text
        body = got.json()
        assert [r['source'] for r in body['reports']] == ['tab', 'stem', 'notation']
        assert body['reports'][0]['label'] == 'Your tab: Lead'
        tab_score = body['reports'][0]['summary']['overall']
        assert body['history'][-1]['overall'] == tab_score
        assert tab_score > body['reports'][1]['summary']['overall']     # the stem disagrees on one note
        missing = client.post(f'/api/songs/{key}/compare', headers=HEADERS, data={**form, 'tab_part': 'Rhythm'},
                              files={'take': ('take.wav', _take_bytes(), 'audio/wav')})
        assert missing.status_code == 404
    finally:
        songs.SONGS.pop(key, None)
