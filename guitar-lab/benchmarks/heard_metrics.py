"""Heard-only note metrics. The reference may be a chart or a MIDI key.

Doubled tab tracks (two guitars playing the same pitch together) collapse into one
audible event, so a single correct detection is one hit and a miss is one miss.
Onset F1 at ±50 ms is the note-and-timing score. A second, looser match (default
±300 ms, closest pair wins) is pitch recall when timing is allowed to slip, and the
onset error of those pairs is the timing score. Nothing here edits the prediction.
"""
from __future__ import annotations

import numpy as np


def collapse_unisons(notes, window=0.03):
    """One event per pitch when several notes attack together (doubled GP tracks)."""
    kept = []
    for n in sorted(notes, key=lambda n: (float(n['time']), int(n['midi']))):
        if kept and int(kept[-1]['midi']) == int(n['midi']) and float(n['time']) - float(kept[-1]['time']) <= window:
            if float(n.get('amplitude') or 0) > float(kept[-1].get('amplitude') or 0):
                kept[-1] = dict(n)
            continue
        kept.append(dict(n))
    return kept


def match_pairs(est, ref, tol=0.05):
    """Greedy exact-pitch pairs, closest onset first, each note used once."""
    cands = []
    for i, r in enumerate(ref):
        rt, rm = float(r['time']), int(r['midi'])
        for j, e in enumerate(est):
            if int(e['midi']) != rm:
                continue
            d = abs(float(e['time']) - rt)
            if d <= tol:
                cands.append((d, i, j))
    cands.sort()
    used_r, used_e, pairs = set(), set(), []
    for d, i, j in cands:
        if i in used_r or j in used_e:
            continue
        used_r.add(i)
        used_e.add(j)
        pairs.append((i, j, d))
    return pairs


def score_heard(est, ref, tol=0.05, loose=0.30, unison_window=0.03):
    """Return onset F1 plus a pitch-recall / timing split. Offsets are ignored."""
    est_u = collapse_unisons(est or [], unison_window)
    ref_u = collapse_unisons(ref or [], unison_window)
    pairs = match_pairs(est_u, ref_u, tol)
    hits = len(pairs)
    precision = hits / len(est_u) if est_u else 0.0
    recall = hits / len(ref_u) if ref_u else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    loose_pairs = match_pairs(est_u, ref_u, loose)
    errs = [d for _, _, d in loose_pairs]
    return {
        'f1': f1,
        'precision': precision,
        'recall': recall,
        'hits': hits,
        'n_ref': len(ref_u),
        'n_est': len(est_u),
        'n_ref_raw': len(ref or []),
        'pitch_recall_loose': (len(loose_pairs) / len(ref_u)) if ref_u else 0.0,
        'median_abs_onset_s': None if not errs else float(np.median(errs)),
        'timing_given_pitch': None if not errs else float(np.mean([d <= tol for d in errs])),
        'loose_s': loose,
        'tol_s': tol,
    }
