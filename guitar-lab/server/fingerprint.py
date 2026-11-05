"""Shazam-style audio fingerprint check (advisory only).

Spectrogram peak constellation -> anchor/target peak pairs hashed as (f1, f2, dt) ->
offset-histogram voting (Wang 2003, "An Industrial-Strength Audio Search Algorithm").

This is ONLY a side check that a supplied reference (a known recording, or a rendering of
a MIDI file) is the same recording as the input, and at what time offset / tempo ratio.
It never gates or changes transcription, notation or tab. A non-match is the expected
outcome for cover versions, live versions, re-recordings, other instruments or tunings,
and is reported as ``'no match - not an error'``.

CLI:  python -m server.fingerprint INPUT REFERENCE   (REFERENCE may be .wav/.mp3/... or .mid)
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

SR = 11025
N_FFT = 1024
HOP = 256                 # 23.2 ms per frame
PEAK_NEIGHBOURHOOD = (15, 11)   # (freq bins, frames) for local-max picking
PEAKS_PER_SECOND = 30
FAN_OUT = 10
DT_MIN, DT_MAX = 1, 64    # frames between anchor and target
DF_MAX = 80               # bins
MIN_VOTES = 12            # absolute aligned-hash votes for a match
MIN_RATIO = 4.0           # best offset bin vs. 2nd-best (non-adjacent) bin
TEMPO_RATIOS = tuple(np.round(np.arange(0.90, 1.1001, 0.02), 2))
NO_MATCH = 'no match - not an error'


def _mono(y):
    y = np.asarray(y, dtype=np.float32)
    return y.mean(axis=1) if y.ndim == 2 else y


def peaks(y, sr):
    """Return (frame, bin) constellation peaks of a mono signal."""
    import librosa
    from scipy.ndimage import maximum_filter
    y = _mono(y)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    if len(y) < N_FFT:
        return np.zeros((0, 2), dtype=np.int32)
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP, window='hann'))
    S = np.log1p(1000 * S / (S.max() + 1e-12))
    S[:4] = 0                                   # drop DC / sub-bass rumble bins
    local = maximum_filter(S, size=PEAK_NEIGHBOURHOOD, mode='constant') == S
    floor = np.median(S) + 0.5 * S.std()
    f, t = np.nonzero(local & (S > floor))
    if not len(t):
        return np.zeros((0, 2), dtype=np.int32)
    amp = S[f, t]
    # keep the strongest peaks per 1-second block so density is level-independent
    fps = SR / HOP
    block = (t / fps).astype(int)
    keep = []
    for b in np.unique(block):
        idx = np.nonzero(block == b)[0]
        keep.extend(idx[np.argsort(-amp[idx])[:PEAKS_PER_SECOND]])
    keep = np.array(sorted(keep, key=lambda i: (t[i], f[i])))
    return np.c_[t[keep], f[keep]].astype(np.int32)


def hashes(pk, tempo=1.0):
    """[(hash, anchor_frame)] for a peak list; ``tempo`` rescales time (query side)."""
    out = []
    n = len(pk)
    for i in range(n):
        t1, f1 = pk[i]
        c = 0
        for j in range(i + 1, n):
            t2, f2 = pk[j]
            dt = t2 - t1
            if dt < DT_MIN:
                continue
            if dt > DT_MAX:
                break
            if abs(int(f2) - int(f1)) > DF_MAX:
                continue
            dts = int(round(dt * tempo))
            out.append(((int(f1) << 20) | (int(f2) << 8) | dts, int(round(t1 * tempo))))
            c += 1
            if c >= FAN_OUT:
                break
    return out


class Index:
    def __init__(self, y, sr):
        self.n_frames = int(len(_mono(y)) * SR / sr / HOP)
        self.table = defaultdict(list)
        for h, t in hashes(peaks(y, sr)):
            self.table[h].append(t)


def match(query, q_sr, reference, r_sr=None, tempo_ratios=TEMPO_RATIOS):
    """Compare a query clip with a reference recording. Returns an advisory dict."""
    idx = reference if isinstance(reference, Index) else Index(reference, r_sr)
    qp = peaks(query, q_sr)
    best = None
    for r in tempo_ratios:
        qh = hashes(qp, tempo=r)
        offs = [rt - qt for h, qt in qh for rt in idx.table.get(h, ())]
        if not offs:
            cand = (0, 0, 0.0, r, len(qh))
        else:
            o = np.asarray(offs)
            bins, counts = np.unique(o, return_counts=True)
            # tolerate +-1 frame jitter
            c3 = counts.copy()
            c3[1:] += counts[:-1] * (np.diff(bins) == 1)
            c3[:-1] += counts[1:] * (np.diff(bins) == 1)
            k = int(np.argmax(c3))
            far = np.abs(bins - bins[k]) > 2
            second = int(c3[far].max()) if far.any() else 0
            cand = (int(c3[k]), int(bins[k]), c3[k] / max(second, 1), r, len(qh))
        if best is None or cand[0] > best[0]:
            best = cand
    votes, off, ratio, tempo, nq = best
    matched = votes >= MIN_VOTES and ratio >= MIN_RATIO
    res = {
        'matched': bool(matched),
        'status': 'match' if matched else NO_MATCH,
        'votes': int(votes),
        'query_hashes': int(nq),
        'peak_to_next_ratio': round(float(ratio), 2),
        'offset_s': round(off * HOP / SR, 3) if matched else None,
        'tempo_ratio': float(tempo) if matched else None,
        'advisory': True,
    }
    if not matched:
        res['detail'] = ('The reference is not the same recording (expected for covers, live or re-recorded '
                         'versions, other instruments or tunings). Transcription is unaffected.')
    return res


def render_midi(path, sr=22050):
    """Simple harmonic rendering of a MIDI file (no soundfont needed)."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(path))
    end = pm.get_end_time() + 1.0
    y = np.zeros(int(end * sr), dtype=np.float32)
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            d = max(n.end - n.start, 0.05) + 0.3
            t = np.arange(int(d * sr)) / sr
            f0 = 440 * 2 ** ((n.pitch - 69) / 12)
            env = np.exp(-3.0 * t) * (n.velocity / 127)
            tone = sum((0.6 ** k) * np.sin(2 * np.pi * f0 * (k + 1) * t) for k in range(6) if f0 * (k + 1) < sr / 2)
            s = int(n.start * sr)
            seg = (env * tone).astype(np.float32)[: len(y) - s]
            y[s:s + len(seg)] += seg
    return y / (np.abs(y).max() + 1e-9), sr


def _load(path):
    path = Path(path)
    if path.suffix.lower() in ('.mid', '.midi'):
        return render_midi(path)
    import librosa
    y, sr = librosa.load(str(path), sr=None, mono=True)
    return y, sr


def verify_reference(audio_path, reference_path):
    """Advisory check: is ``reference_path`` (recording or MIDI) the same recording as the input?

    Never raises: failures are reported as ``status='error'`` and must be ignored by callers.
    """
    try:
        q, qs = _load(audio_path)
        r, rs = _load(reference_path)
        out = match(q, qs, r, rs)
        out['reference'] = Path(reference_path).name
        out['reference_kind'] = 'midi_rendering' if Path(reference_path).suffix.lower() in ('.mid', '.midi') else 'recording'
        return out
    except Exception as exc:  # noqa: BLE001 - advisory only
        return {'matched': False, 'status': 'error', 'advisory': True, 'detail': f'check skipped: {exc}'}


if __name__ == '__main__':
    import json
    import sys
    print(json.dumps(verify_reference(sys.argv[1], sys.argv[2]), indent=1))
