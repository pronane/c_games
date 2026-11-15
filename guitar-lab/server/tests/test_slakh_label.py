import numpy as np
import pretty_midi
import soundfile as sf
import yaml

from training.slakh_data import SR, label_check, load_track


def _tone(midi, seconds=1.0, amp=1.0):
    count = int(seconds * SR)
    frequency = 440.0 * 2 ** ((midi - 69) / 12)
    time = np.arange(count) / SR
    return (amp * np.sin(2 * np.pi * frequency * time)).astype(np.float32)


def _notes(midi, count=25):
    return [{'time': 0.12, 'duration': 0.4, 'midi': midi} for _ in range(count)]


def test_written_octave_survives_a_louder_harmonic_and_a_true_octave_shift_still_applies():
    fundamental = _tone(60, amp=0.15)
    harmonic = _tone(72, amp=1.0)
    mixed = fundamental + harmonic
    shift, present = label_check(mixed, _notes(60))
    assert shift == 0 and present >= 0.6
    pure = label_check(_tone(60), _notes(60))
    assert pure[0] == 0 and pure[1] >= 0.6
    up = label_check(_tone(72), _notes(60))
    assert up[0] == 12 and up[1] >= 0.6


def test_only_the_failing_stem_is_skipped(tmp_path):
    good = _tone(60, amp=0.2)
    bad = _tone(30, amp=0.2)
    mix = np.stack([good + bad, good + bad], axis=1)
    track = tmp_path / 'Track00001'
    (track / 'stems').mkdir(parents=True)
    (track / 'MIDI').mkdir()
    sf.write(track / 'stems' / 'S0.wav', good, SR)
    sf.write(track / 'stems' / 'S1.wav', bad, SR)
    sf.write(track / 'mix.wav', mix, SR)
    (track / 'metadata.yaml').write_text(yaml.safe_dump({'stems': {
        'S0': {'inst_class': 'Guitar', 'is_drum': False},
        'S1': {'inst_class': 'Guitar', 'is_drum': False},
    }}))
    for sid, pitch in (('S0', 60), ('S1', 60)):
        midi = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=24)
        for _ in range(25):
            instrument.notes.append(pretty_midi.Note(velocity=100, pitch=pitch, start=0.12, end=0.5))
        midi.instruments.append(instrument)
        midi.write(str(track / 'MIDI' / f'{sid}.mid'))
    true, notes, cleaned, rate = load_track(track)
    assert rate == SR
    assert notes and {note['midi'] for note in notes} == {60}
    # The unmatched stem is gone from the mix; the matched sine remains.
    residual = cleaned.mean(axis=1)[:len(good)] - good
    assert float(np.max(np.abs(residual))) < 0.05
    assert len(true) == len(good)
