"""Same-pitch frame-dip join. It is not part of the app decoder.

A second onset of the same pitch is a dip when the frame posterior falls below
0.85 inside 0.20 s. On the locked 16th-note chug that floor is 0.91. False
onsets on one amplifier render of GOAT train item 4 dipped to 0.80 or below.
0.85 sits between those two train measurements. It was not chosen on a
held-out item.

The rule raises that one train file and then drops EGSet12 below the locked
Riley floor, so ``server.riley.decode`` does not call it. This module only
repeats the comparison.
"""
from __future__ import annotations

import numpy as np

from server.riley import config

FRAME_DIP = 0.85
FRAME_DIP_GAP_S = 0.20


def join_frame_dips(notes, frame, cut=FRAME_DIP, max_gap=FRAME_DIP_GAP_S):
    """Join a same-pitch onset that is only a dip in an ongoing note.

    The second onset is dropped and the first note is extended to the later
    offset. A repeated note whose frame stays at or above ``cut`` is left
    alone. Returns ``(notes, n_joined)``.
    """
    ordered = sorted((dict(n) for n in notes), key=lambda n: (n['midi'], n['time'], n.get('duration') or 0))
    keep = []
    joined = 0
    frames = np.asarray(frame)
    for note in ordered:
        if keep and keep[-1]['midi'] == note['midi']:
            gap = float(note['time']) - float(keep[-1]['time'])
            if 0 < gap <= max_gap:
                col = int(note['midi']) - config.begin_note
                start = int(round(float(keep[-1]['time']) * config.frames_per_second))
                stop = int(round(float(note['time']) * config.frames_per_second))
                if 0 <= col < frames.shape[1]:
                    sl = frames[max(0, start):min(frames.shape[0], stop + 1), col]
                    floor = float(sl.min()) if len(sl) else 1.0
                    if floor < cut:
                        end = max(float(keep[-1]['time']) + float(keep[-1]['duration']),
                                  float(note['time']) + float(note['duration']))
                        keep[-1]['duration'] = end - float(keep[-1]['time'])
                        joined += 1
                        continue
        keep.append(note)
    keep.sort(key=lambda n: (n['time'], n['midi']))
    return keep, joined
