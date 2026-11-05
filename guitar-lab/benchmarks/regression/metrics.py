"""Note metrics for the regression library.

Note F1 and the loose pitch match use mir_eval (exact MIDI pitch, offsets
ignored). Onset-only F1 uses mir_eval's onset F-measure. Doubled unisons
collapse so two guitars playing the same pitch once count as one event.
"""
from __future__ import annotations

import numpy as np

from benchmarks.heard_metrics import collapse_unisons


def _hz(notes):
    return np.asarray([440.0 * 2 ** ((int(n['midi']) - 69) / 12) for n in notes], dtype=float)


def _intervals(notes):
    rows = []
    for n in notes:
        start = float(n['time'])
        dur = max(float(n.get('duration') or 0.05), 0.01)
        rows.append([start, start + dur])
    return np.asarray(rows, dtype=float)


def _empty_scores(est, ref):
    if not est and not ref:
        return 1.0, 1.0, 1.0
    return 0.0, 0.0, 0.0


def score_notes(est, ref, onset_tol=0.05, loose=0.30, unison_window=0.03):
    """mir_eval note F1 (±50 ms), onset-only F1, and pitch recall at ±300 ms."""
    import mir_eval

    est_u = collapse_unisons(est or [], unison_window)
    ref_u = collapse_unisons(ref or [], unison_window)
    if not est_u or not ref_u:
        p, r, f = _empty_scores(est_u, ref_u)
        note = {'precision': p, 'recall': r, 'f1': f}
        onset_f = f
        pitch_recall = r
        n_match = 0
    else:
        ref_i, est_i = _intervals(ref_u), _intervals(est_u)
        ref_h, est_h = _hz(ref_u), _hz(est_u)
        p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
            ref_i, ref_h, est_i, est_h, offset_ratio=None, onset_tolerance=onset_tol)
        note = {'precision': float(p), 'recall': float(r), 'f1': float(f)}
        matches = mir_eval.transcription.match_notes(
            ref_i, ref_h, est_i, est_h, offset_ratio=None, onset_tolerance=loose)
        n_match = len(matches)
        pitch_recall = n_match / len(ref_u)
        onset_f, _, _ = mir_eval.onset.f_measure(
            np.asarray([n['time'] for n in ref_u], dtype=float),
            np.asarray([n['time'] for n in est_u], dtype=float),
            window=onset_tol)
        onset_f = float(onset_f)
    return {
        'note_f1': note['f1'],
        'note_precision': note['precision'],
        'note_recall': note['recall'],
        'onset_f1': float(onset_f),
        'pitch_recall_300ms': float(pitch_recall),
        'n_ref': len(ref_u),
        'n_est': len(est_u),
        'n_pitch_match_300ms': int(n_match) if est_u and ref_u else 0,
        'onset_tol_s': onset_tol,
        'loose_s': loose,
    }


def _mono(y):
    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 2:
        return y.mean(axis=1)
    return y


def chroma_time_map(y_src, sr_src, y_dst, sr_dst, target_sr=22050, hop=2048):
    """Map source times onto the destination recording using chroma DTW.

    The path is audio only. Note F1 is not an input.
    Returns (src_seconds, dst_seconds) along the path, both increasing in src time.
    """
    import librosa

    def chroma(y, sr):
        y = _mono(y)
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        if len(y) < hop * 8:
            y = np.pad(y, (0, hop * 8 - len(y)))
        c = librosa.feature.chroma_cqt(y=y, sr=target_sr, hop_length=hop)
        return c

    cs, cd = chroma(y_src, sr_src), chroma(y_dst, sr_dst)
    _costs, wp = librosa.sequence.dtw(X=cs, Y=cd, metric='cosine')
    wp = np.asarray(wp)[::-1]
    hop_s = hop / target_sr
    src_t = wp[:, 0].astype(float) * hop_s
    dst_t = wp[:, 1].astype(float) * hop_s
    # One destination time per source frame (median if DTW revisits a frame).
    order = np.argsort(src_t, kind='mergesort')
    src_t, dst_t = src_t[order], dst_t[order]
    uniq_src, uniq_dst = [], []
    for s, d in zip(src_t, dst_t):
        if uniq_src and abs(s - uniq_src[-1]) < 1e-6:
            uniq_dst[-1] = (uniq_dst[-1] + d) / 2
            continue
        uniq_src.append(float(s))
        uniq_dst.append(float(d))
    return np.asarray(uniq_src), np.asarray(uniq_dst)


def warp_times(times, src_t, dst_t):
    times = np.asarray(list(times), dtype=float)
    if len(src_t) < 2:
        return times.copy()
    return np.interp(times, src_t, dst_t)


def src_span_for_dst_window(src_t, dst_t, t0, t1, pad=1.0):
    """Source-time span that the path sends into ``[t0, t1]`` on the destination."""
    if len(dst_t) == 0:
        return 0.0, 0.0
    mask = (dst_t >= t0) & (dst_t <= t1)
    if not np.any(mask):
        # Nearest path point, then a padded neighbourhood.
        mid = 0.5 * (t0 + t1)
        i = int(np.argmin(np.abs(dst_t - mid)))
        return max(0.0, float(src_t[i]) - pad), float(src_t[i]) + pad
    lo = max(0.0, float(src_t[mask].min()) - pad)
    hi = float(src_t[mask].max()) + pad
    return lo, hi
