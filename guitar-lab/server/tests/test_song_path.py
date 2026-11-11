"""Upload, stems, transcription, and playback for a whole song.

The neural separator and, in the wiring checks, the note model are test
doubles. Everything around them is the real song path: decode, stem files,
which guitar is which (from the pan, not from a label), the score, and the
audio the player presses play on. A separate check runs the real decoder on
a short stem when Riley is installed.
"""
import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from server import songs
from server.fx.playback import render_acoustic

HEADERS = {'X-Fretwork-Client': 'studio'}
SR = 44100
SECONDS = 6.5


def _configured():
    return {'separation': {'configured': True}, 'transcription': {'configured': True}}


def _wav_bytes(audio, sr=SR):
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format='WAV', subtype='PCM_16')
    return buf.getvalue()


def _tone(freq, n, sr=SR, amp=0.2):
    t = np.arange(n) / sr
    # A few plucked bursts so the file is a performance, not a steady hum.
    env = np.zeros(n, np.float32)
    for start in np.arange(0.4, SECONDS - 0.4, 0.7):
        i0 = int(start * sr)
        length = int(0.35 * sr)
        env[i0:i0 + length] += np.exp(-np.linspace(0, 4, length)).astype(np.float32)
    return (amp * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _stereo(left, right):
    return np.stack([left, right], axis=1).astype(np.float32)


def _quiet(n):
    return np.zeros((n, 2), np.float32)


def _provenance(names):
    return {
        'model': 'test double', 'device': 'cpu', 'sources': list(names),
        'warning': None, 'sha256': '0' * 64, 'shifts': 1, 'overlap': 0.25,
        'quality': 'test double',
    }


def _notes():
    return [
        {'id': 0, 'time': 0.50, 'duration': 0.40, 'midi': 64, 'amplitude': 0.8},
        {'id': 1, 'time': 1.50, 'duration': 0.40, 'midi': 67, 'amplitude': 0.8},
        {'id': 2, 'time': 2.50, 'duration': 0.40, 'midi': 71, 'amplitude': 0.8},
        {'id': 3, 'time': 3.50, 'duration': 0.40, 'midi': 74, 'amplitude': 0.8},
    ]


def _run_inline(monkeypatch):
    monkeypatch.setattr(songs.EXECUTOR, 'submit', lambda fn, *args, **kwargs: fn(*args))
    monkeypatch.setattr(songs.models, 'capabilities', _configured)


def _post(client, audio, **form):
    data = {'consent': 'true', 'instrument': 'guitar', 'processing': 'cpu', 'tone': 'auto', **form}
    return client.post(
        '/api/songs', headers=HEADERS, data=data,
        files={'file': ('song.wav', _wav_bytes(audio), 'audio/wav')},
    )


def _attacks_follow_the_notes(notes):
    """Playback energy starts at the transcribed time, not earlier and not late."""
    rendered = np.asarray(render_acoustic(notes, sr=SR, length_s=notes[-1]['time'] + 1.0), dtype=float)
    if rendered.ndim == 2:
        rendered = rendered.mean(axis=1)
    for note in notes:
        start = int(round(note['time'] * SR))
        before = rendered[max(0, start - int(0.03 * SR)):max(0, start - int(0.005 * SR))]
        after = rendered[start:start + int(0.03 * SR)]
        assert float(np.max(np.abs(after))) > 0.01
        if len(before):
            assert float(np.max(np.abs(after))) > 5 * float(np.max(np.abs(before)) + 1e-8)


def test_upload_requires_consent_and_refuses_a_streaming_link(monkeypatch):
    from server import app as module
    monkeypatch.setattr(songs.models, 'capabilities', _configured)
    client = TestClient(module.app)
    n = int(SECONDS * SR)
    audio = _stereo(_tone(220, n), _tone(220, n))
    missing = client.post(
        '/api/songs', headers=HEADERS, data={'consent': 'false', 'instrument': 'guitar'},
        files={'file': ('song.wav', _wav_bytes(audio), 'audio/wav')},
    )
    assert missing.status_code == 422
    refused = client.post(
        '/api/songs', headers=HEADERS,
        data={'consent': 'true', 'url': 'https://www.youtube.com/watch?v=abc', 'instrument': 'guitar'},
    )
    assert refused.status_code == 422


def test_band_upload_writes_stems_transcribes_the_guitar_and_plays_back(monkeypatch):
    from server import app as module
    _run_inline(monkeypatch)
    n = int(SECONDS * SR)
    guitar = _stereo(_tone(330, n, amp=0.25), _tone(330, n, amp=0.25))
    drums = _stereo(_tone(80, n, amp=0.2), _tone(80, n, amp=0.2))
    mix = np.clip(guitar + drums, -1, 1).astype(np.float32)
    seen = []

    def separate(audio, sr, policy=None):
        stems = {name: _quiet(len(audio)) for name in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')}
        stems['guitar'] = guitar[:len(audio)]
        stems['drums'] = drums[:len(audio)]
        return stems, sr, _provenance(stems)

    def transcribe(path, **kwargs):
        y, _sr = sf.read(path, always_2d=True)
        seen.append({'rms': float(np.sqrt(np.mean(np.square(y)))), 'backend': kwargs.get('backend')})
        return _notes()

    monkeypatch.setattr(songs.models, 'run_demucs', separate)
    monkeypatch.setattr(songs.models, 'transcribe', transcribe)
    client = TestClient(module.app)
    response = _post(client, mix, transcriber='basic_pitch')
    assert response.status_code == 202, response.text
    key = response.json()['id']
    try:
        body = client.get(f'/api/songs/{key}').json()
        assert body['status'] == 'complete', body
        assert body['result']['tone']['chosen'] == 'auto'
        assert 'effects_detected' in body['result']
        parts = body['result']['parts']
        assert len(parts) == 1 and parts[0]['id'] == 'guitar'
        guitar_bytes = client.get(f'/api/songs/{key}/tracks/guitar', params={'format': 'flac'}).content
        mix_bytes = client.get(f'/api/songs/{key}/tracks/mix', params={'format': 'mp3'}).content
        assert len(guitar_bytes) > 1000 and len(mix_bytes) > 100
        guitar_audio, guitar_sr = sf.read(io.BytesIO(guitar_bytes), always_2d=True)
        assert abs(len(guitar_audio) / guitar_sr - SECONDS) < 0.05
        # The guitar stem, not the drum-heavy mix, is what was transcribed.
        assert seen and seen[0]['rms'] == pytest.approx(float(np.sqrt(np.mean(np.square(guitar)))), rel=0.05)
        score = client.post(
            f'/api/songs/{key}/score', headers=HEADERS,
            json={'part': 'guitar', 'role': 'any', 'tuning': 'standard', 'capo': 0},
        )
        assert score.status_code == 200, score.text
        scored = score.json()
        assert [round(n['time'], 2) for n in scored['notes']] == [0.5, 1.5, 2.5, 3.5]
        assert '<score-partwise' in scored['musicxml']
        _attacks_follow_the_notes(scored['notes'])
    finally:
        songs.SONGS.pop(key, None)


def test_two_guitars_are_split_from_the_pan_without_being_told(monkeypatch):
    from server import app as module
    _run_inline(monkeypatch)
    n = int(SECONDS * SR)
    left = _tone(196, n, amp=0.3)
    right = _tone(494, n, amp=0.3)
    guitar = _stereo(left, right)
    drums = _stereo(np.full(n, 0.05, np.float32), np.full(n, 0.05, np.float32))
    seen = []

    def separate(audio, sr, policy=None):
        stems = {name: _quiet(len(audio)) for name in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')}
        stems['guitar'] = guitar[:len(audio)]
        stems['drums'] = drums[:len(audio)]
        return stems, sr, _provenance(stems)

    def transcribe(path, **kwargs):
        y, _sr = sf.read(path, always_2d=True)
        side = 'left' if float(np.sqrt(np.mean(np.square(y[:, 0])))) >= float(np.sqrt(np.mean(np.square(y[:, 1])))) else 'right'
        seen.append(side)
        midi = 55 if side == 'left' else 71
        return [{'id': 0, 'time': 0.8, 'duration': 0.4, 'midi': midi, 'amplitude': 0.8}]

    monkeypatch.setattr(songs.models, 'run_demucs', separate)
    monkeypatch.setattr(songs.models, 'transcribe', transcribe)
    client = TestClient(module.app)
    response = _post(client, guitar, transcriber='basic_pitch')
    assert response.status_code == 202, response.text
    key = response.json()['id']
    try:
        body = client.get(f'/api/songs/{key}').json()
        assert body['status'] == 'complete', body
        positions = {part['position'] for part in body['result']['parts']}
        assert positions >= {'left', 'right'}
        assert 'left' in seen and 'right' in seen
        # No request field names guitar 1 or guitar 2. The pan did.
        left_score = client.post(
            f'/api/songs/{key}/score', headers=HEADERS,
            json={'part': 'guitar_left', 'role': 'any', 'tuning': 'standard', 'capo': 0},
        )
        right_score = client.post(
            f'/api/songs/{key}/score', headers=HEADERS,
            json={'part': 'guitar_right', 'role': 'any', 'tuning': 'standard', 'capo': 0},
        )
        assert left_score.status_code == 200 and right_score.status_code == 200
        assert {n['midi'] for n in left_score.json()['notes']} == {55}
        assert {n['midi'] for n in right_score.json()['notes']} == {71}
        played = client.get(f'/api/songs/{key}/tracks/guitar_left', params={'format': 'flac'})
        assert played.status_code == 200 and played.headers['content-type'].startswith('audio/')
    finally:
        songs.SONGS.pop(key, None)


def test_a_solo_split_across_guitar_and_other_is_transcribed_whole(monkeypatch):
    from server import app as module
    _run_inline(monkeypatch)
    n = int(SECONDS * SR)
    mix = _stereo(_tone(247, n, amp=0.3), _tone(247, n, amp=0.3))
    seen = []

    def separate(audio, sr, policy=None):
        stems = {name: _quiet(len(audio)) for name in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')}
        # Separator kept only a quiet slice in 'guitar' and put the rest in 'other'.
        stems['guitar'] = (mix[:len(audio)] * 0.05).astype(np.float32)
        stems['other'] = (mix[:len(audio)] * 0.9).astype(np.float32)
        return stems, sr, _provenance(stems)

    def transcribe(path, **kwargs):
        y, _sr = sf.read(path, always_2d=True)
        seen.append(float(np.sqrt(np.mean(np.square(y)))))
        return _notes()

    monkeypatch.setattr(songs.models, 'run_demucs', separate)
    monkeypatch.setattr(songs.models, 'transcribe', transcribe)
    client = TestClient(module.app)
    response = _post(client, mix, transcriber='basic_pitch')
    assert response.status_code == 202, response.text
    key = response.json()['id']
    try:
        body = client.get(f'/api/songs/{key}').json()
        assert body['status'] == 'complete', body
        assert any('solo' in warning.lower() for warning in body['result']['warnings'])
        mix_rms = float(np.sqrt(np.mean(np.square(mix))))
        assert seen and seen[0] == pytest.approx(mix_rms, rel=0.15)
    finally:
        songs.SONGS.pop(key, None)


@pytest.mark.skipif(
    not __import__('server.transcribers', fromlist=['availability']).availability().get('riley', {}).get('installed'),
    reason='Riley is not installed',
)
def test_real_decoder_on_a_short_stem_reaches_playback(monkeypatch):
    """The note list playback schedules is the list the real decoder returned."""
    from server import app as module
    _run_inline(monkeypatch)
    n = int(SECONDS * SR)
    guitar = _stereo(_tone(330, n, amp=0.3), _tone(330, n, amp=0.3))
    drums = _stereo(np.full(n, 0.04, np.float32), np.full(n, 0.04, np.float32))

    def separate(audio, sr, policy=None):
        stems = {name: _quiet(len(audio)) for name in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')}
        stems['guitar'] = guitar[:len(audio)]
        stems['drums'] = drums[:len(audio)]
        return stems, sr, _provenance(stems)

    monkeypatch.setattr(songs.models, 'run_demucs', separate)
    client = TestClient(module.app)
    response = _post(client, guitar, transcriber='riley')
    assert response.status_code == 202, response.text
    key = response.json()['id']
    try:
        body = client.get(f'/api/songs/{key}').json()
        assert body['status'] == 'complete', body
        assert 'Riley' in body['result']['provenance']['transcription']
        song = songs.SONGS[key]
        heard = song.notes.get('guitar') or []
        assert heard, body['result']
        score = client.post(
            f'/api/songs/{key}/score', headers=HEADERS,
            json={'part': 'guitar', 'role': 'any', 'tuning': 'standard', 'capo': 0},
        )
        assert score.status_code == 200, score.text
        scored = score.json()['notes']
        assert [round(n['time'], 3) for n in scored] == [round(n['time'], 3) for n in heard]
        playable = [n for n in scored if n.get('string')]
        assert playable
        _attacks_follow_the_notes(playable[:6])
        track = client.get(f'/api/songs/{key}/tracks/guitar', params={'format': 'flac'})
        assert track.status_code == 200
    finally:
        songs.SONGS.pop(key, None)
