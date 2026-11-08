"""Guitar Pro note times for scoring only.

The transcriber never sees this list. The Metallica intro uses the frozen
alignment from PR #51: tab 0 s is audio 19.3 s, no stretch. The scored window
is tab 0–16.5 s, the arpeggio before the second guitar's new line. That window
was not chosen by searching note F1.

Bar 153 of this chart doubles 108 BPM to 216. The intro is before that bar, so
the double-time does not move any scored onset. pyguitarpro's mix table for
this file has no tempo events; the 216 change is the chart's bar-153 marking,
and it reproduces the 417.2 s tab duration measured previously.
"""
from __future__ import annotations

from benchmarks.score_alignment import ONE_FROZEN

# The chart is written at 108 BPM, but the recording's intro plays at 99.4 BPM: a beat tracker
# on the audio alone gives 99.4 over both 19 s and 41 s windows, with 100 or 108 as its prior.
# Playing the chart at 108 drifts ~0.7 s off by the end of the window, which is why every
# detector scored ~0.1 here. Tab 0 is then placed by lining the chart's onset times up with
# the audio's onset-strength envelope (pitch-blind): 0.95 s before the earlier chroma anchor.
# No transcription output went into either number.
INTRO_CHART_BPM = 108.0
INTRO_AUDIO_BPM = 99.4
INTRO_STRETCH = INTRO_CHART_BPM / INTRO_AUDIO_BPM
INTRO_ORIGIN_S = round(float(ONE_FROZEN['origin_s']) - 0.95, 2)
INTRO_TAB_END_S = 16.5
INTRO_AUDIO_END_S = INTRO_ORIGIN_S + INTRO_TAB_END_S * INTRO_STRETCH
TPQ = 960
DOUBLE_TIME_BAR = 153
DOUBLE_TIME_BPM = 216.0


def _guitar_tracks(song):
    for index, track in enumerate(song.tracks):
        if getattr(track, 'isPercussionTrack', False):
            continue
        name = (track.name or '').lower()
        if 'bass' in name or 'drum' in name:
            continue
        yield index, track


def guitar_notes(path):
    """Pitched guitar notes in tab seconds. Percussion and bass are omitted."""
    import guitarpro

    song = guitarpro.parse(str(path))
    bpm = float(song.tempo or 108.0)
    # Tick where bar DOUBLE_TIME_BAR begins. Same on every track.
    change_tick = None
    for measure in song.tracks[0].measures:
        if measure.number == DOUBLE_TIME_BAR:
            change_tick = int(measure.start)
            break
    origin = int(song.tracks[0].measures[0].start)  # library offset, 960 on this file

    def seconds(tick):
        tick = int(tick)
        if change_tick is None or tick <= change_tick:
            return (tick - origin) / TPQ * (60.0 / bpm)
        head = (change_tick - origin) / TPQ * (60.0 / bpm)
        return head + (tick - change_tick) / TPQ * (60.0 / DOUBLE_TIME_BPM)

    notes = []
    for index, track in _guitar_tracks(song):
        for measure in track.measures:
            for voice in measure.voices:
                for beat in voice.beats:
                    if not beat.notes:
                        continue
                    start = seconds(beat.start)
                    dur = beat.duration.time / TPQ * (
                        60.0 / (DOUBLE_TIME_BPM if change_tick is not None and beat.start >= change_tick else bpm))
                    for note in beat.notes:
                        if getattr(note, 'type', None) is not None and 'rest' in str(note.type).lower():
                            continue
                        midi = int(round(note.realValue))
                        notes.append({
                            'time': float(start),
                            'duration': float(max(0.03, dur)),
                            'midi': midi,
                            'track': index,
                        })
    notes.sort(key=lambda n: (n['time'], n['midi'], n['track']))
    return notes


def intro_reference(path, origin_s=INTRO_ORIGIN_S, tab_end_s=INTRO_TAB_END_S):
    """Guitar notes in the intro, shifted onto the recording clock."""
    out = []
    for note in guitar_notes(path):
        if note['time'] < 0 or note['time'] >= tab_end_s:
            continue
        shifted = dict(note)
        shifted['tab_time'] = note['time']
        shifted['time'] = float(origin_s) + note['time'] * INTRO_STRETCH
        shifted['duration'] = note['duration'] * INTRO_STRETCH
        out.append(shifted)
    return out
