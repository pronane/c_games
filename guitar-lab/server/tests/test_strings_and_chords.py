"""String heard from the recording, and the trained chord model's labels."""
import numpy as np
import pytest

from server import chord_model, song_analysis as sa, string_timbre as st


def pluck(midi, sr=22050, seconds=.6, brightness=.6):
    t = np.arange(int(sr*seconds))/sr
    f0 = 440*2**((midi-69)/12)
    y = sum((brightness**k)*np.sin(2*np.pi*f0*k*t) for k in range(1, 12) if f0*k < sr/2)
    return (y*np.exp(-t*4)).astype(np.float32)/4


def test_model_ships_as_plain_arrays():
    assert st.available()
    m = st._model()
    assert int(m['n_classes']) == 6 and len(m['tree_offsets']) > 100


def test_probs_cover_only_strings_that_reach_the_note():
    audio = np.concatenate([np.zeros(2205, np.float32), pluck(40), pluck(76)])
    notes = [{'time': .1, 'duration': .5, 'midi': 40}, {'time': .7, 'duration': .5, 'midi': 76}]
    probs = st.string_probs(audio, 22050, notes, st.STANDARD)
    assert probs[0] == pytest.approx([0, 0, 0, 0, 0, 1], abs=1e-6)        # low E open: only string 6
    assert sum(probs[1]) == pytest.approx(1, abs=1e-3)
    assert probs[1][5] == 0 and probs[1][4] == 0                          # E5 is out of reach on the low E and A strings
    assert st.string_probs(audio, 22050, notes, [64, 59, 55, 50, 45, 38]) == [None, None]   # drop D: not used
    assert st.uniform_shift([63, 58, 54, 49, 44, 39]) == 1 and st.uniform_shift([66, 61, 57, 52, 47, 42]) == -2


def test_fingering_follows_a_clearly_heard_string():
    # G3 (55): open G string or 5th fret on D. Heard clearly on the D string -> fret 5 on string 4.
    notes = [{'time': 0, 'duration': .5, 'midi': 55, 'string_probs': [0, 0, .02, .95, .03, 0]}]
    out = sa.fingering(notes, st.STANDARD, 22)
    assert (out[0]['string'], out[0]['fret']) == (4, 5)
    plain = sa.fingering([{'time': 0, 'duration': .5, 'midi': 55}], st.STANDARD, 22)
    assert (plain[0]['string'], plain[0]['fret']) == (3, 0)


def test_chord_labels():
    assert chord_model.label(14*0+1) == 'C'
    assert chord_model.label(14*9+0) == 'Am'
    assert chord_model.label(14*10+9, flats=True) == 'Bb7'
    assert chord_model.label(14*7+13) == 'Gsus4'
    assert chord_model.label(169) == 'N'


@pytest.mark.skipif(not chord_model.status()[0], reason='chord model weights not installed')
def test_chord_model_hears_a_c_major_triad():
    sr = 22050
    t = np.arange(sr*12)/sr
    y = sum(np.sin(2*np.pi*440*2**((m-69)/12)*t) for m in (48, 52, 55, 60, 64, 67)).astype(np.float32)/6
    labels = chord_model.chords_per_beat(y, [0, 3, 6, 9], 12.0)
    assert labels.count('C') >= 3, labels
