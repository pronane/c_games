"""Audio↔score alignment that does not look at a transcriber.

The score is a pitch-class sequence on the chart's own clock. The recording is
its chroma. An early template locks the lag; a later template is scored only at
the position that lag and tempo predict, so the tempo ratio is whatever makes
both templates land on the audio together. Note F1 is not an input.

`ONE_FROZEN` is that map for one commercial remaster. Re-running it needs the
local audio and Guitar Pro file; they are not in the repo.
"""
from __future__ import annotations

import numpy as np
from scipy import signal


def stretch_chroma(chroma, alpha):
    """Resample score frames so one score frame becomes `alpha` audio frames."""
    chroma = np.asarray(chroma, dtype=float)
    n = max(8, int(round(chroma.shape[1] * float(alpha))))
    idx = np.linspace(0, chroma.shape[1] - 1, n)
    i0 = np.floor(idx).astype(int)
    i1 = np.minimum(i0 + 1, chroma.shape[1] - 1)
    frac = idx - i0
    return chroma[:, i0] * (1 - frac) + chroma[:, i1] * frac


def place_chroma(chroma, lag_frames, pad=4):
    """Score chroma starting at `lag_frames` in a longer recording."""
    lag = int(round(lag_frames))
    out = np.zeros((chroma.shape[0], lag + chroma.shape[1] + pad))
    out[:, lag:lag + chroma.shape[1]] = chroma
    return out


def _norm_cols(c):
    n = np.maximum(np.linalg.norm(c, axis=0, keepdims=True), 1e-9)
    return c / n


def _cosine(template, audio, lag):
    lag = int(lag)
    width = template.shape[1]
    if lag < 0 or lag + width > audio.shape[1] or width < 2:
        return -1.0
    tn = _norm_cols(template)
    an = _norm_cols(audio[:, lag:lag + width])
    return float(np.mean(np.sum(tn * an, axis=0)))


def lag_curve(template, audio):
    """Cosine of `template` at every lag where it sits fully inside `audio`."""
    template = np.asarray(template, dtype=float)
    audio = np.asarray(audio, dtype=float)
    if template.shape[1] < 4 or audio.shape[1] < template.shape[1] + 1:
        raise ValueError('template and audio chroma are too short to align')
    tn = _norm_cols(template)
    corr = np.zeros(audio.shape[1] + tn.shape[1] - 1)
    for pc in range(tn.shape[0]):
        corr += signal.fftconvolve(audio[pc], tn[pc][::-1], mode='full')
    lags = np.arange(len(corr)) - (tn.shape[1] - 1)
    valid = (lags >= 0) & (lags + tn.shape[1] <= audio.shape[1])
    # fftconvolve against a column-normalised template is a dot product per lag,
    # but the audio columns are not normalised yet. Recompute on a coarse grid
    # with true column cosine — templates here are a couple of seconds, so this
    # stays cheap and does not prefer louder bars.
    scores = np.full(len(lags), -np.inf)
    step = max(1, tn.shape[1] // 40)
    candidates = np.where(valid)[0][::step]
    for i in candidates:
        scores[i] = _cosine(tn, audio, int(lags[i]))
    # refine around the best coarse lags
    order = np.argsort(np.where(np.isfinite(scores), scores, -np.inf))[::-1][:8]
    for i in order:
        lo = max(0, i - step)
        hi = min(len(lags), i + step + 1)
        for j in range(lo, hi):
            if valid[j] and not np.isfinite(scores[j]):
                scores[j] = _cosine(tn, audio, int(lags[j]))
    return lags, scores


def top_lags(lags, scores, k=4, separation=4):
    """Highest local peaks, at least `separation` frames apart."""
    finite = np.where(np.isfinite(scores))[0]
    peaks = []
    for i in finite:
        s = scores[i]
        if i > 0 and np.isfinite(scores[i - 1]) and scores[i - 1] > s:
            continue
        if i + 1 < len(scores) and np.isfinite(scores[i + 1]) and scores[i + 1] > s:
            continue
        peaks.append((float(s), int(lags[i])))
    peaks.sort(reverse=True)
    kept = []
    for s, lag in peaks:
        if all(abs(lag - prev) >= separation for _, prev in kept):
            kept.append((s, lag))
        if len(kept) >= k:
            break
    return kept


def align_linear(score_chroma, audio_chroma, hop_s, anchor_a, anchor_b, alphas):
    """Lock an early score anchor, then keep the tempo that also lands a later one.

    anchor_a / anchor_b are (start_frame, length_frames) on the unstretched score.
    Returns the best map and the per-alpha attempts.
    """
    audio = np.asarray(audio_chroma, dtype=float)
    attempts = []
    for alpha in alphas:
        alpha = float(alpha)
        warped = stretch_chroma(score_chroma, alpha)

        def slc(anchor):
            a0 = int(round(anchor[0] * alpha))
            a1 = min(warped.shape[1], a0 + max(4, int(round(anchor[1] * alpha))))
            return a0, warped[:, a0:a1]

        a0, template_a = slc(anchor_a)
        b0, template_b = slc(anchor_b)
        lags, scores = lag_curve(template_a, audio)
        for cos_a, lag in top_lags(lags, scores):
            origin = lag - a0
            cos_b = _cosine(template_b, audio, origin + b0)
            attempts.append({
                'alpha': alpha,
                'origin_frames': int(origin),
                'origin_s': float(origin * hop_s),
                'cosine_a': float(cos_a),
                'cosine_b': float(cos_b),
            })
    if not attempts:
        raise ValueError('no alignment attempt succeeded')
    # The later anchor is the tempo evidence. Break ties toward the early lock.
    best = max(attempts, key=lambda r: (r['cosine_b'], r['cosine_a']))
    return best, attempts


# One remaster, measured from the chart and the mix alone. Not fit to note F1.
# Intro: harmonic chroma of tab 0.5–16.5 s (the arpeggio, before the second guitar's
# new line at 17.5 s) against the mix, 50 ms frames. The peak puts that template at
# 19.8 s. The same riff's next loop is at 37.8 s and scores lower, so the earliest
# peak is the lock. A 0.5 s frame of the same intro had agreed (tab 1 s → 20.5 s).
# Body tempo, beats from 30–220 s: median 103.36 BPM (10th–90th 99.4–107.7) against
# the chart's 108, ratio 1.045. Later chart templates are not unique (second peak
# within about 3%), and carrying 1.045 out from the intro runs past the end of the
# file, so no whole-song linear map is frozen. The 23.45 s + 1.005 line was the one
# that maximised transcription F1; it is not this anchor.
ONE_FROZEN = {
    'piece': 'intro anchor only; body tempo is a separate estimate',
    'method': 'chart chroma template and beat tracker; transcription F1 was not an input',
    'intro_anchor': {'tab_s': 0.5, 'audio_s': 19.8, 'next_loop_audio_s': 37.8},
    'origin_s': 19.3,  # audio time of tab 0 s, from the intro anchor with no stretch
    'body_bpm_median': 103.36,
    'body_bpm_p10': 99.38,
    'body_bpm_p90': 107.67,
    'body_tempo_ratio_vs_chart': 1.045,  # 108 / 103.36, first half of the recording
    'chart_bpm': [108.0, 216.0],
    'chart_tempo_change_tab_s': 290.0,
    'whole_song_linear_map': None,
    'historical_f1_max_map': {
        'origin_s': 23.45, 'alpha': 1.005, 'used': False,
        'why_not': 'chosen to maximise heard-note F1; the intro chroma peak is at 19.8 s',
    },
}
