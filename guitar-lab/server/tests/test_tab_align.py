import numpy as np

from server import tab_align as ta

SR = 22050


def _tracks(seed=3):
    """Two made-up parts: a chord part every half beat and a single-note line over it."""
    rng = np.random.default_rng(seed)
    chords, line = [], []
    roots = [45, 48, 43, 50]
    for bar in range(24):
        root = roots[bar % 4]
        for k in range(4):
            t = bar * 2.0 + k * 0.5
            for iv in (0, 7, 12):
                chords.append({'time': t, 'duration': 0.45, 'midi': root + iv, 'bar': bar + 1})
        if bar >= 8:
            for k in range(8):
                line.append({'time': bar * 2.0 + k * 0.25, 'duration': 0.22,
                             'midi': int(root + 24 + rng.choice([0, 2, 3, 5, 7, 10])), 'bar': bar + 1})
    return [{'name': 'Rhythm', 'notes': chords}, {'name': 'Lead', 'notes': line}]


def _render(notes, warp, length):
    """Plucked sines on the recording's clock warp(t)."""
    y = np.zeros(int(length * SR), np.float32)
    for n in notes:
        a = warp(n['time'])
        i = int(a * SR)
        k = np.arange(int(0.4 * SR))
        hz = 440 * 2 ** ((n['midi'] - 69) / 12)
        tone = np.sin(2 * np.pi * hz * k / SR) * np.exp(-k / (0.15 * SR)) * 0.2
        tone += 0.5 * np.sin(4 * np.pi * hz * k / SR) * np.exp(-k / (0.1 * SR)) * 0.2
        y[i:i + len(k)] += tone[: max(0, len(y) - i)]
    return y


def test_aligns_offset_tempo_and_drift_then_assigns_parts():
    tracks = _tracks()
    notes = [n for t in tracks for n in t['notes']]
    # Recording: 3.2 s of lead-in, 8% slower than the chart, plus a slow tempo wobble.
    warp = lambda t: 3.2 + 1.08 * t + 0.25 * np.sin(t / 9)
    audio = _render(notes, warp, warp(48) + 3)
    m = ta.refine(ta.align(notes, audio, SR), notes, audio, SR)
    err = [abs(float(ta.to_audio_time(m, t)) - warp(t)) for t in np.arange(1, 46, 3)]
    assert np.median(err) < 0.06 and max(err) < 0.3, err
    placed = ta.place_tracks(tracks, m)
    assert placed[1]['sections'][0]['first_bar'] == 9            # the lead enters at bar 9
    # Heard notes = the true notes on the recording's clock: each lands in its own part.
    heard = [dict(n, id=i, time=float(warp(n['time']))) for i, n in enumerate(notes)]
    res = ta.assign(heard, placed)
    assert res['match']['Rhythm']['f1'] > 0.85 and res['match']['Lead']['f1'] > 0.85, res['match']
    assert len(res['unassigned']) < 0.15 * len(heard)


def test_rejects_an_empty_tab_and_silence():
    import pytest
    with pytest.raises(ValueError):
        ta.align([], np.zeros(SR * 5, np.float32), SR)
    with pytest.raises(ValueError):
        ta.align(_tracks()[0]['notes'], np.zeros(SR * 60, np.float32), SR)


def test_tab_parts_endpoint_names_the_song_parts(tmp_path):
    import soundfile as sf
    from fastapi.testclient import TestClient
    from server import app as module
    from server.songs import SONGS, Song
    tracks = _tracks()
    notes = [n for t in tracks for n in t['notes']]
    warp = lambda t: 2.0 + 1.05 * t
    audio = _render(notes, warp, warp(48) + 2)
    folder = tmp_path / 'tab-song'
    (folder / 'tracks').mkdir(parents=True)
    sf.write(folder / 'tracks' / 'mix.flac', np.stack([audio, audio], 1), SR)
    song = Song('tab-song', folder, 'guitar', 'Made-up song', status='complete', active=False)
    # What the app heard: the lead only (as if the rhythm guitar had been missed).
    song.notes = {'guitar': [dict(n, id=i, time=float(warp(n['time'])), amplitude=0.7)
                             for i, n in enumerate(tracks[1]['notes'])]}
    song.result = {'duration': len(audio) / SR, 'parts': [{'id': 'guitar', 'label': 'Guitar', 'roles': []}]}
    SONGS[song.id] = song
    client = TestClient(module.app)
    r = client.post('/api/songs/tab-song/tab-parts', headers={'X-Fretwork-Client': 'studio'}, json={'tracks': [
        {'name': t['name'], 'track': i, 'notes': t['notes']} for i, t in enumerate(tracks)]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert abs(body['alignment']['tempo_ratio'] - 1.05) < 0.03 and abs(body['alignment']['start'] - 2.0) < 0.3
    parts = {p['name']: p for p in body['parts']}
    assert parts['Lead']['match']['recall'] > 0.85 and parts['Rhythm']['match']['recall'] == 0
    assert parts['Lead']['sections'][0]['first_bar'] == 9
    bad = client.post('/api/songs/tab-song/tab-parts', headers={'X-Fretwork-Client': 'studio'}, json={'tracks': [{'name': 'x', 'notes': []}]})
    assert bad.status_code == 422
    del SONGS[song.id]
