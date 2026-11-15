"""Rejected ungated sustain experiment. It is not the app decoder.

The app rule is ``server.riley.sustain``: distorted audio only, gap 0.10 s,
and the second onset must be at least 0.05 weaker. This module is the wider
0.12 s comparison that missed the EGSet12 and user-recording floors.
``--sustain`` repeats it.

On GOAT train, two different mistakes were mixed together by the reverb rule.

* Item 4 amplifier 3 split sustained notes into ~90 ms repeats. The frame
  posterior between those onsets dipped to about 0.66. Joining a same-pitch
  onset inside 0.12 s whose frame floor is below 0.80 raised that file from
  0.736 to 0.955 and did not move the four DI files.
* Items 46 and 101, several amplifiers: the reverb ratio called the stretch
  wet and the 0.65 onset threshold deleted notes that were not same-pitch
  retriggers. Keeping the 0.5 list when fewer than 40% of the 0.5-only notes
  are same-pitch neighbours raised those files (item 101 amplifier 4,
  0.270 to 0.673). A pile of same-pitch neighbours (share >= 0.70) still uses
  0.65, which is what item 5's amplifiers need.

Train means, note F1, offsets ignored, this rule versus the published decoder:

| | F1@50 before | F1@50 after | F1@100 before | F1@100 after |
| --- | ---: | ---: | ---: | ---: |
| DI (4) | 0.877 | 0.877 | 0.908 | 0.908 |
| amplifiers (20) | 0.517 | 0.589 | 0.536 | 0.610 |
| all 24 | 0.577 | 0.637 | 0.598 | 0.660 |

Item 5's amplifiers did not move. Their false onsets keep the frame posterior
up (median floor about 0.92), so a dip join cannot see them, and the stricter
onset threshold is already the better of the two lists.

The rule was not adopted. With it in the decoder, EGSet12 clip 04 pitch
recall inside 300 ms fell from 0.8765 to 0.8471, past the 0.02 floor. The
user-recording lock moved as well: the current upload and take C went from
238 notes to 261, and take B from 565 to 536. ``server.riley.decode`` does
not call this module.
"""
from __future__ import annotations

import numpy as np

from server import riley
from server.riley import DRY_ONSET, WET_ONSET, WET_RATIO, config

REPEAT_GAP_S = 0.30
REPEAT_STRICT = 0.70
REPEAT_KEEP_DRY = 0.40
REPEAT_MIN_EXTRA = 8
DIP_GAP_S = 0.12
DIP_CUT = 0.80


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


def join_short_dips(notes, frame, max_gap=DIP_GAP_S, cut=DIP_CUT):
    """Join a same-pitch onset only when the frame posterior dips inside ``max_gap``."""
    if frame is None or len(notes) < 2:
        return list(notes), 0
    frames = np.asarray(frame)
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
                    if floor < cut:
                        end = max(float(keep[-1]['time']) + float(keep[-1]['duration']),
                                  float(note['time']) + float(note['duration']))
                        keep[-1]['duration'] = end - float(keep[-1]['time'])
                        joined += 1
                        continue
        keep.append(note)
    keep.sort(key=lambda n: (n['time'], n.get('midi') or 0))
    return keep, joined


def experimental_decode(out: dict, window_s: float = 20.0):
    """The measured sustain rule. Not used by ``server.riley.decode``."""
    loose = riley.notes_from_posteriors(out)
    strict = riley.notes_from_posteriors(out, onset=WET_ONSET)
    dry = riley.notes_from_posteriors(out, onset=DRY_ONSET)
    end = max([n['time'] + n['duration'] for n in loose] + [window_s])
    edges = np.arange(0.0, end + window_s, window_s)

    def count(notes, a, b):
        return sum(1 for n in notes if a <= n['time'] < b)

    def _in(notes, a, b):
        return [n for n in notes if a <= n['time'] < b]

    notes = []
    for a, b in zip(edges[:-1], edges[1:]):
        ratio = count(loose, a, b) / max(count(strict, a, b), 1)
        wet = ratio > WET_RATIO and count(loose, a, b) >= 8
        fraction = same_pitch_repeat_fraction(_in(dry, a, b), _in(strict, a, b))
        use_strict = wet
        if fraction is not None and fraction >= REPEAT_STRICT:
            use_strict = True
        elif wet and fraction is not None and fraction < REPEAT_KEEP_DRY:
            use_strict = False
        notes += _in(strict if use_strict else dry, a, b)
    notes, n_joined = join_short_dips(notes, out.get('frame_output'))
    return notes, {'sustain_joins': n_joined, 'experimental': True,
                   'onset_threshold_constants': (DRY_ONSET, WET_ONSET)}
