import numpy as np

from server import fingerprint as fp
from server import songs

SR = 22050


def melody(seed, seconds=20):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(seconds * SR), np.float32)
    t = np.arange(int(0.4 * SR)) / SR
    for s in np.arange(0, seconds - 0.5, 0.25):
        f = 110 * 2 ** (rng.integers(0, 36) / 12)
        note = sum(0.5 ** k * np.sin(2 * np.pi * f * (k + 1) * t) for k in range(4)) * np.exp(-6 * t)
        i = int(s * SR); y[i:i + len(t)] += note.astype(np.float32)
    return y / np.abs(y).max()


def test_same_recording_matches_with_offset_through_noise_and_clipping():
    ref = melody(1)
    q = ref[int(6 * SR):int(14 * SR)].copy()
    q = np.clip(q + np.random.default_rng(0).normal(0, 0.05, len(q)), -0.3, 0.3)
    r = fp.match(q, SR, ref, SR)
    assert r['matched'] and r['status'] == 'match'
    assert abs(r['offset_s'] - 6.0) < 0.06 and r['tempo_ratio'] == 1.0


def test_different_performance_is_no_match_not_error():
    r = fp.match(melody(2)[:8 * SR], SR, melody(3), SR)
    assert not r['matched'] and r['status'] == fp.NO_MATCH == 'no match - not an error'
    assert r['offset_s'] is None and r['advisory'] is True


def test_reference_check_is_optional_and_never_raises(tmp_path):
    assert songs.reference_check(melody(1), SR, None) is None
    bad = songs.reference_check(melody(1), SR, str(tmp_path / 'missing.wav'))
    assert bad['status'] == 'error' and bad['matched'] is False


def test_verify_reference_midi_rendering(tmp_path):
    import pretty_midi
    import soundfile as sf
    pm = pretty_midi.PrettyMIDI(); inst = pretty_midi.Instrument(0)
    rng = np.random.default_rng(4)
    for i in range(60):
        inst.notes.append(pretty_midi.Note(100, int(rng.integers(45, 80)), i * 0.25, i * 0.25 + 0.4))
    pm.instruments.append(inst); pm.write(str(tmp_path / 'ref.mid'))
    y, sr = fp.render_midi(tmp_path / 'ref.mid', SR)
    sf.write(tmp_path / 'q.wav', y[3 * SR:11 * SR], SR)
    r = fp.verify_reference(tmp_path / 'q.wav', tmp_path / 'ref.mid')
    assert r['matched'] and r['reference_kind'] == 'midi_rendering' and abs(r['offset_s'] - 3) < 0.06


def test_run_song_only_adds_reference_check_after_outputs():
    import inspect
    src = inspect.getsource(songs.run_song)
    # computed after the result dict is final, and only adds one key
    assert src.index("song.result['reference_check']") > src.index('song.result = {')
    assert src.count('song.reference') == 1
