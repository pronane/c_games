"""Distorted-guitar sustain handling, and the rejected ungated comparison."""
import numpy as np

from benchmarks.goat.sustain import experimental_decode, join_short_dips, same_pitch_repeat_fraction
from server import riley


def _note(time, midi, duration=0.08):
    return {'time': time, 'duration': duration, 'midi': midi, 'amplitude': 0.5}


def test_a_short_dip_joins_and_a_held_frame_or_a_longer_gap_does_not():
    frame = np.ones((30, 88), np.float32)
    # MIDI 40 is column 19 (begin_note 21).
    frame[0:12, 19] = 0.2
    dipped = [_note(0.0, 40, 0.05), _note(0.09, 40, 0.05)]
    joined, n = join_short_dips(dipped, frame)
    assert n == 1 and len(joined) == 1
    held = np.ones_like(frame)
    kept, n_held = join_short_dips(dipped, held)
    assert n_held == 0 and len(kept) == 2
    wider = [_note(0.0, 40, 0.05), _note(0.18, 40, 0.05)]
    kept_wide, n_wide = join_short_dips(wider, frame)
    assert n_wide == 0 and len(kept_wide) == 2


def test_repeat_fraction_sees_a_pile_and_ignores_other_pitches():
    assert same_pitch_repeat_fraction([_note(0.0, 40), _note(0.2, 40)], [_note(0.0, 40)]) is None
    dry = [_note(i * 0.2, 52, 0.1) for i in range(16)]
    fraction = same_pitch_repeat_fraction(dry, dry[::2])
    assert fraction is not None and fraction >= 0.70
    other = [_note(i * 0.5, 40 + i, 0.2) for i in range(12)]
    assert same_pitch_repeat_fraction(other, other[:2]) == 0.0


def _post(frame, onset):
    return {'frame_output': frame, 'reg_onset_output': onset}


def test_the_decoder_joins_only_a_distorted_short_weak_dip(monkeypatch):
    frame = np.ones((20, 88), np.float32)
    frame[0:12, 19] = 0.2  # MIDI 40, column 19
    onset = np.zeros((20, 88), np.float32)
    onset[0, 19] = 0.90
    onset[9, 19] = 0.50
    pair = [_note(0.0, 40, 0.04), _note(0.09, 40, 0.04)]
    late = [_note(0.0, 40, 0.04), _note(0.115, 40, 0.04)]
    strong = [_note(0.0, 40, 0.04), _note(0.09, 40, 0.04)]
    strong_onset = onset.copy()
    strong_onset[9, 19] = 0.88

    def fake(out, onset=None, offset=None, frame=None):
        return list(pair)

    monkeypatch.setattr(riley, 'notes_from_posteriors', fake)
    # No audio: the reverb rule alone, so a 90 ms dip is not joined.
    plain, info = riley.decode(_post(frame, onset))
    assert len(plain) == 2 and 'sustain_joins' not in info

    def distorted(audio, sr):
        return {'tone': 'distorted'}

    def clean(audio, sr):
        return {'tone': 'clean'}

    monkeypatch.setattr('server.song_analysis.tone_estimate', distorted)
    audio = np.zeros(1600, np.float32)
    joined, jinfo = riley.decode(_post(frame, onset), audio=audio, sr=16000)
    assert len(joined) == 1 and jinfo['sustain_joins'] == 1
    monkeypatch.setattr('server.song_analysis.tone_estimate', clean)
    kept, cinfo = riley.decode(_post(frame, onset), audio=audio, sr=16000)
    assert len(kept) == 2 and 'sustain_joins' not in cinfo

    # 115 ms is a real repeat on EGSet12 clip 04. Distorted or not, it stays.
    def fake_late(out, onset=None, offset=None, frame=None):
        return list(late)

    monkeypatch.setattr(riley, 'notes_from_posteriors', fake_late)
    monkeypatch.setattr('server.song_analysis.tone_estimate', distorted)
    kept_late, _ = riley.decode(_post(frame, onset), audio=audio, sr=16000)
    assert len(kept_late) == 2

    # A second onset almost as strong as the first is a re-pick, not a dip.
    def fake_strong(out, onset=None, offset=None, frame=None):
        return list(strong)

    monkeypatch.setattr(riley, 'notes_from_posteriors', fake_strong)
    kept_strong, sinfo = riley.decode(_post(frame, strong_onset), audio=audio, sr=16000)
    assert len(kept_strong) == 2 and sinfo['sustain_joins'] == 0

    # The old ungated 0.12 s comparison still joins a 90 ms dip. It is not the app path.
    monkeypatch.setattr(riley, 'notes_from_posteriors', fake)
    experimental, exp = experimental_decode({'frame_output': np.zeros((20, 88), np.float32)})
    assert len(experimental) == 1 and exp['experimental'] is True
