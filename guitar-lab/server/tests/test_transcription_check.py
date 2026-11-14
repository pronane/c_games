import numpy as np

from server import compare as C
from server import transcription_check as tc


def _song(seconds=24.0):
    """A strummed progression and a melody, every note known."""
    notes, t = [], 0.5
    chords = [(45, 52, 57, 61, 64), (40, 47, 52, 56, 59), (50, 57, 62, 66), (43, 50, 55, 59, 62)]
    k = 0
    while t < seconds - 1:
        for m in chords[k % 4]:
            notes.append({'time': t, 'duration': 0.9, 'midi': m})
        notes.append({'time': t + 0.5, 'duration': 0.4, 'midi': 69 + (k * 5) % 12})
        t += 1.0
        k += 1
    return notes


def test_a_transcription_of_its_own_audio_is_not_marked_and_a_dropped_stretch_is():
    notes = _song()
    audio = tc.playback(notes, 24.0)
    report, played = tc.check(audio, tc.SR, notes)
    assert report['summary']['flagged_share'] < 0.1
    # The transcription loses 8-12 s: that stretch is marked as no note written.
    dropped = [n for n in notes if not 8 <= n['time'] < 12]
    report, _ = tc.check(audio, tc.SR, dropped)
    gaps = [s for s in report['stretches'] if s['status'] == 'gap']
    assert gaps and any(s['start'] <= 9 and s['end'] >= 11 for s in gaps)
    assert sum(s['end'] - s['start'] for s in report['stretches'] if s['end'] < 7 or s['start'] > 13) < 3


def test_wrong_pitches_in_a_stretch_are_marked_as_differing():
    notes = _song()
    audio = tc.playback(notes, 24.0)
    # 14-18 s written as the wrong thing entirely: a high single-note line instead of the chords.
    wrong = [n for n in notes if not 14 <= n['time'] < 18]
    wrong += [{'time': 14.0 + i * 0.5, 'duration': 0.45, 'midi': 79 + (i % 4)} for i in range(8)]
    report, _ = tc.check(audio, tc.SR, sorted(wrong, key=lambda n: n['time']))
    assert any(s['start'] < 18 and s['end'] > 14 and s['status'] == 'differs' for s in report['stretches'])
    lack = report['missing_per_stretch']
    assert max(lack[7:9]) == max(x for x in lack if x is not None)
    roll = report['roll']
    assert roll['frames'] > 200 and len(roll['level']) > 0


def test_a_note_the_detector_dropped_is_not_called_missing_when_the_recording_shows_it():
    target = [{'time': 1.0 + i * 0.5, 'duration': 0.4, 'midi': 60 + i} for i in range(8)]
    take = [n for i, n in enumerate(target) if i != 4]               # the detector dropped note 4
    plain = C.compare_take(take, [{'source': 'file', 'notes': target, 'bpm': 120}])['reports'][0]['notes']
    assert [f['kind'] for f in plain].count('missing') == 1
    heard = np.zeros((600, 88), np.float32)
    heard[int(round(target[4]['time'] * 100)), target[4]['midi'] - 21] = 0.4
    checked = C.compare_take(take, [{'source': 'file', 'notes': target, 'bpm': 120}], heard=heard)['reports'][0]['notes']
    assert [f['kind'] for f in checked].count('missing') == 0
    assert any(f.get('heard_faintly') for f in checked)
    # A note that is not in the recording at all is still reported.
    empty = C.compare_take(take, [{'source': 'file', 'notes': target, 'bpm': 120}], heard=np.zeros((600, 88), np.float32))
    assert [f['kind'] for f in empty['reports'][0]['notes']].count('missing') == 1
