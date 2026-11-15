"""The sustain comparison is repeatable and is not the app decoder."""
import inspect

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


def test_the_app_decoder_does_not_run_the_experiment(monkeypatch):
    assert 'sustain' not in inspect.getsource(riley.decode)
    assert 'join_short_dips' not in inspect.getsource(riley.decode)
    frame = np.zeros((20, 88), np.float32)
    pair = [_note(0.0, 40, 0.04), _note(0.09, 40, 0.04)]

    def fake(out, onset=None, offset=None, frame=None):
        return list(pair)

    monkeypatch.setattr(riley, 'notes_from_posteriors', fake)
    notes, info = riley.decode({'frame_output': frame})
    assert len(notes) == 2 and 'sustain_joins' not in info
    experimental, exp = experimental_decode({'frame_output': frame})
    assert len(experimental) == 1 and exp['sustain_joins'] == 1 and exp['experimental'] is True
