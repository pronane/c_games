"""Error taxonomy helpers for Guitar Lab note F1 vs MIDI.

Used by local evaluation under /workspace/guitar-lab-test/accuracy_errors/.
Categories: wrong_octave, semitone, other_pitch, extra_ghost, missed_onset,
merged_notes, split_notes, onset_timing_only, missed_due_to_timing.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import numpy as np

try:
    import mir_eval
except ImportError:  # pragma: no cover
    mir_eval = None


def onset_deltas_ms(est, ref, pairs, shift=0.0):
    return [(float(est[j]['time']) + shift - float(ref[i]['time'])) * 1000 for i, j in pairs]


def classify_errors(est, ref, tol=0.05, tol_loose=0.10, shift=0.0):
    """Return category counts for unmatched est/ref notes after mir_eval matching."""
    if mir_eval is None:
        raise ImportError('mir_eval required')
    if not est or not ref:
        return Counter(), []
    hz = lambda p: 440 * 2 ** ((np.asarray(p, float) - 69) / 12)
    r_on = np.array([n['time'] for n in ref])
    e_on = np.maximum(np.array([n['time'] for n in est]) + shift, 0)
    r_iv = np.c_[r_on, r_on + np.maximum([n.get('duration', .05) for n in ref], .05)]
    e_iv = np.c_[e_on, e_on + np.maximum([n.get('duration', .05) for n in est], .05)]
    r_midi = np.array([n['midi'] for n in ref], int)
    e_midi = np.array([n['midi'] for n in est], int)
    pairs = mir_eval.transcription.match_notes(
        r_iv, hz(r_midi), e_iv, hz(e_midi), onset_tolerance=tol, offset_ratio=None)
    matched_r = {i for i, _ in pairs}
    matched_e = {j for _, j in pairs}
    cat = Counter()
    for j in range(len(est)):
        if j in matched_e:
            continue
        near = [i for i in range(len(ref)) if abs(e_on[j] - r_on[i]) <= tol]
        if not near:
            near_l = [i for i in range(len(ref)) if abs(e_on[j] - r_on[i]) <= tol_loose]
            if near_l:
                i = min(near_l, key=lambda i: (abs(e_on[j] - r_on[i]), abs(e_midi[j] - r_midi[i])))
                d = int(e_midi[j] - r_midi[i])
                if d == 0:
                    cat['onset_timing_only'] += 1
                elif d % 12 == 0:
                    cat['wrong_octave'] += 1
                elif abs(d) == 1:
                    cat['semitone'] += 1
                else:
                    cat['other_pitch'] += 1
            else:
                cat['extra_ghost'] += 1
            continue
        near_u = [i for i in near if i not in matched_r] or near
        i = min(near_u, key=lambda i: (abs(e_midi[j] - r_midi[i]), abs(e_on[j] - r_on[i])))
        d = int(e_midi[j] - r_midi[i])
        if d % 12 == 0 and d != 0:
            cat['wrong_octave'] += 1
        elif abs(d) == 1:
            cat['semitone'] += 1
        elif d != 0:
            cat['other_pitch'] += 1
        else:
            cat['dup_or_offset_fail'] += 1
    for i in range(len(ref)):
        if i in matched_r:
            continue
        near_e = [j for j in range(len(est)) if abs(e_on[j] - r_on[i]) <= tol]
        if not near_e:
            near_l = [j for j in range(len(est)) if abs(e_on[j] - r_on[i]) <= tol_loose]
            if near_l and any(e_midi[j] == r_midi[i] for j in near_l):
                cat['missed_due_to_timing'] += 1
            else:
                cat['missed_onset'] += 1
    return cat, pairs
