"""Sustain handling for a distorted guitar. Clean audio is left alone.

Chosen on GOAT train items 4, 5, 46 and 101. The useful joins on item 4
amplifiers 2 and 3 are about 90 ms apart, the second onset is weaker than the
first, and the frame posterior dips below 0.80. Five real repeats on EGSet12
clip 04 sit at 115–118 ms, so the gap stops at 0.10 s. That clip, and the
locked current upload, are not judged distorted, so the rule does not run
on them at all.

A wet reverb decision uses onset 0.65. On some distorted amplifiers that
deletes notes which are not same-pitch retriggers. When fewer than 40% of the
notes present at 0.5 and missing at 0.65 are same-pitch neighbours, the 0.5
list is kept. When at least 70% are, 0.65 is used even if the reverb ratio
stayed quiet. Item 5's amplifiers already want 0.65; their false onsets keep
the frame up, and this dip join does not see them.
"""
from __future__ import annotations

import numpy as np

from . import config

DIP_GAP_S = 0.10
DIP_CUT = 0.80
ONSET_MARGIN = 0.05
REPEAT_GAP_S = 0.30
REPEAT_STRICT = 0.70
REPEAT_KEEP_DRY = 0.40
REPEAT_MIN_EXTRA = 8


def tone_is_distorted(audio, sr) -> bool:
    """True only for the automatic 'distorted' guess. Clean, crunch and uncertain stay off."""
    from server.song_analysis import tone_estimate
    return tone_estimate(audio, sr).get('tone') == 'distorted'


def _near(notes, note, tol=0.05):
    midi = note.get('midi')
    if midi is None:
        return False
    t = float(note['time'])
    return any(n.get('midi') == midi and abs(float(n['time']) - t) <= tol for n in notes)


def same_pitch_repeat_fraction(dry, strict, gap=REPEAT_GAP_S, min_extra=REPEAT_MIN_EXTRA):
    """Share of onset-0.5 notes missing at 0.65 that sit beside another same pitch.

    ``None`` when there are not enough pitched extras to decide.
    """
    extra = [n for n in dry if n.get('midi') is not None and not _near(strict, n)]
    if len(extra) < min_extra:
        return None
    close = 0
    for note in extra:
        midi = note['midi']
        t = float(note['time'])
        if any(n is not note and n.get('midi') == midi and 0 < abs(float(n['time']) - t) <= gap for n in dry):
            close += 1
    return close / len(extra)


def _onset_peak(onset, midi, time):
    if onset is None or midi is None:
        return None
    col = int(midi) - config.begin_note
    if not 0 <= col < onset.shape[1]:
        return None
    c = int(round(float(time) * config.frames_per_second))
    sl = onset[max(0, c - 2):c + 3, col]
    return float(sl.max()) if len(sl) else 0.0


def join_short_dips(notes, frame, onset=None, max_gap=DIP_GAP_S, cut=DIP_CUT, onset_margin=ONSET_MARGIN):
    """Join a same-pitch onset inside ``max_gap`` when the frame dips and the new onset is weaker.

    A missing onset posterior skips the weakness check. A held frame, or a gap
    longer than ``max_gap``, is left alone. Returns ``(notes, n_joined)``.
    """
    if frame is None or len(notes) < 2:
        return list(notes), 0
    frames = np.asarray(frame)
    peaks = None if onset is None else np.asarray(onset)
    ordered = sorted((dict(n) for n in notes), key=lambda n: (n.get('midi'), n['time']))
    keep = []
    joined = 0
    fps = config.frames_per_second
    for note in ordered:
        if keep and keep[-1].get('midi') is not None and keep[-1]['midi'] == note.get('midi'):
            gap = float(note['time']) - float(keep[-1]['time'])
            if 0 < gap <= max_gap:
                col = int(note['midi']) - config.begin_note
                start = int(round(float(keep[-1]['time']) * fps))
                stop = int(round(float(note['time']) * fps))
                if 0 <= col < frames.shape[1]:
                    sl = frames[max(0, start):min(frames.shape[0], max(start + 1, stop + 1)), col]
                    floor = float(sl.min()) if len(sl) else 1.0
                    weaker = True
                    if peaks is not None and onset_margin is not None:
                        first = _onset_peak(peaks, note['midi'], keep[-1]['time'])
                        second = _onset_peak(peaks, note['midi'], note['time'])
                        weaker = first is not None and second is not None and second < first - onset_margin
                    if floor < cut and weaker:
                        end = max(float(keep[-1]['time']) + float(keep[-1]['duration']),
                                  float(note['time']) + float(note['duration']))
                        keep[-1]['duration'] = end - float(keep[-1]['time'])
                        joined += 1
                        continue
        keep.append(note)
    keep.sort(key=lambda n: (n['time'], n.get('midi') or 0))
    return keep, joined
