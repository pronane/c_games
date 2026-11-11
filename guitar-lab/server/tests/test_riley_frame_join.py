"""The frame-dip comparison stays out of the decoder, and a held frame is not joined."""
import numpy as np

from benchmarks.goat.frame_join import join_frame_dips
from server import riley


def _note(time, midi, duration=0.08):
    return {'time': time, 'duration': duration, 'midi': midi, 'amplitude': 0.5}


def test_a_dipped_frame_joins_and_a_held_frame_does_not():
    # Two onsets 90 ms apart. Column for MIDI 40 is begin_note 21, so column 19.
    frame = np.ones((30, 88), np.float32)
    frame[1:9, 19] = 0.2
    dipped = [_note(0.0, 40, 0.05), _note(0.09, 40, 0.05)]
    joined, n = join_frame_dips(dipped, frame)
    assert n == 1 and len(joined) == 1
    assert joined[0]['duration'] == 0.14
    held = np.ones_like(frame)
    kept, n_held = join_frame_dips(dipped, held)
    assert n_held == 0 and len(kept) == 2


def test_a_different_pitch_is_not_joined():
    frame = np.zeros((30, 88), np.float32)
    notes = [_note(0.0, 40), _note(0.09, 41)]
    kept, n = join_frame_dips(notes, frame)
    assert n == 0 and len(kept) == 2


def test_decode_does_not_join_even_if_the_old_flag_is_set(monkeypatch):
    monkeypatch.setenv('FRETWORK_RILEY_FRAME_JOIN', '1')
    frame = np.zeros((20, 88), np.float32)
    pair = [_note(0.0, 40, 0.04), _note(0.09, 40, 0.04)]

    def fake(out, onset=None, offset=None, frame=None):
        return list(pair)

    monkeypatch.setattr(riley, 'notes_from_posteriors', fake)
    notes, info = riley.decode({'frame_output': frame})
    assert len(notes) == 2 and 'frame_dip_joins' not in info
