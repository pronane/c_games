"""Fixed-length feature vector for effect template matching."""
from __future__ import annotations

import numpy as np
from scipy import signal

FEATURE_NAMES = (
    'crest_factor',
    'loudness_spread_db',
    'rms_db',
    'spec_centroid_mean',
    'spec_centroid_std',
    'spec_flatness_mean',
    'spec_rolloff_mean',
    'zcr_mean',
    'hf_ratio',
    'th_proxy',
    'odd_even_ratio',
    'flux_ac_peak',
    'flux_ac_lag_s',
    'onset_ac_peak',
    'onset_ac_lag_s',
    'rt60_est_s',
    'late_energy_ratio',
    'stereo_corr',
)


def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        return x.mean(axis=-1), float(np.corrcoef(x[:, 0], x[:, 1])[0, 1]) if x.shape[1] >= 2 else 1.0
    return x, 1.0


def _frame_rms(x, win, hop):
    if len(x) < win:
        return np.array([np.sqrt(np.mean(x ** 2) + 1e-16)])
    n = 1 + (len(x) - win) // hop
    out = np.empty(n)
    for i in range(n):
        seg = x[i * hop: i * hop + win]
        out[i] = np.sqrt(np.mean(seg ** 2) + 1e-16)
    return out


def _stft_mag(x, sr, n_fft=2048, hop=512):
    _, _, z = signal.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window='hann', padded=False)
    return np.abs(z)


def extract_features(audio, sr=44100) -> dict:
    x, stereo_corr = _mono(audio)
    if len(x) < 256:
        return {k: 0.0 for k in FEATURE_NAMES}

    peak = float(np.max(np.abs(x)) + 1e-12)
    rms = float(np.sqrt(np.mean(x ** 2) + 1e-16))
    crest = peak / rms

    frame_rms = _frame_rms(x, win=2048, hop=512)
    active = frame_rms[frame_rms > np.percentile(frame_rms, 20)]
    if len(active) < 2:
        active = frame_rms
    loud_spread = float(20 * np.log10((active.max() + 1e-12) / (active.min() + 1e-12)))

    mag = _stft_mag(x, sr)
    freqs = np.fft.rfftfreq(2048, 1 / sr)
    # avoid empty
    mag = np.maximum(mag, 1e-12)
    spec_sum = mag.sum(axis=0, keepdims=True)
    centroid = (freqs[:, None] * mag).sum(axis=0) / spec_sum.ravel()
    flatness = np.exp(np.mean(np.log(mag), axis=0)) / (np.mean(mag, axis=0) + 1e-12)
    # rolloff 85%
    csum = np.cumsum(mag, axis=0)
    thresh = 0.85 * csum[-1]
    rolloff = np.array([freqs[np.searchsorted(csum[:, i], thresh[i])] for i in range(mag.shape[1])])

    zc = np.mean(np.abs(np.diff(np.signbit(x).astype(np.float64))))

    hf = freqs >= 1500
    hf_ratio = float(mag[hf].sum() / (mag.sum() + 1e-12))

    # Rough THD proxy: energy outside the strongest spectral peak's local neighbourhood.
    mean_mag = mag.mean(axis=1)
    fund_bin = int(np.argmax(mean_mag[1:200]) + 1)  # skip DC; limit search
    mask = np.ones_like(mean_mag, dtype=bool)
    lo = max(1, fund_bin - 2)
    hi = min(len(mean_mag), fund_bin + 3)
    mask[lo:hi] = False
    # also mute first few harmonics narrowly
    for h in (2, 3, 4, 5):
        b = fund_bin * h
        if b < len(mask):
            mask[max(0, b - 1): b + 2] = False
    th_proxy = float(mean_mag[mask].sum() / (mean_mag.sum() + 1e-12))

    # Odd/even harmonic energy around estimated fundamental.
    odd = even = 0.0
    for h in range(1, 9):
        b = fund_bin * h
        if b >= len(mean_mag):
            break
        e = float(mean_mag[max(0, b - 1): b + 2].sum())
        if h % 2:
            odd += e
        else:
            even += e
    odd_even = float(odd / (even + 1e-12))

    # Spectral flux + autocorrelation → modulation / delay hint.
    flux = np.sqrt(np.sum(np.diff(mag, axis=1) ** 2, axis=0))
    flux = flux - flux.mean()
    flux_ac_peak = 0.0
    flux_ac_lag_s = 0.0
    if len(flux) > 16:
        ac = np.correlate(flux, flux, mode='full')[len(flux) - 1:]
        ac = ac / (ac[0] + 1e-12)
        # search lags ~0.05–1.5 s
        hop_s = 512 / sr
        lo_i = max(1, int(0.05 / hop_s))
        hi_i = min(len(ac) - 1, int(1.5 / hop_s))
        if hi_i > lo_i:
            k = lo_i + int(np.argmax(ac[lo_i:hi_i]))
            flux_ac_peak = float(ac[k])
            flux_ac_lag_s = float(k * hop_s)

    # Onset strength via half-wave rectified flux for delay taps.
    onset = np.maximum(flux, 0)
    onset = onset - onset.mean()
    onset_ac_peak = 0.0
    onset_ac_lag_s = 0.0
    if len(onset) > 16:
        ac = np.correlate(onset, onset, mode='full')[len(onset) - 1:]
        ac = ac / (ac[0] + 1e-12)
        hop_s = 512 / sr
        lo_i = max(1, int(0.04 / hop_s))
        hi_i = min(len(ac) - 1, int(0.5 / hop_s))
        if hi_i > lo_i:
            k = lo_i + int(np.argmax(ac[lo_i:hi_i]))
            onset_ac_peak = float(ac[k])
            onset_ac_lag_s = float(k * hop_s)

    # Blind RT60-ish: energy envelope decay slope on active→quiet transitions.
    env = _frame_rms(x, win=2048, hop=512)
    env_db = 20 * np.log10(env + 1e-12)
    # Find best linear fit over decaying stretches.
    rt60 = 0.3
    hop_s = 512 / sr
    best = None
    for i in range(len(env_db) - 8):
        seg = env_db[i:i + 12]
        if seg[0] < -35:
            continue
        t = np.arange(len(seg)) * hop_s
        slope = np.polyfit(t, seg, 1)[0]
        if slope < -5:  # dB/s decaying
            est = -60.0 / slope
            if 0.05 < est < 4.0:
                score = seg[0] - seg[-1]
                if best is None or score > best[0]:
                    best = (score, est)
    if best:
        rt60 = float(best[1])

    # Late energy ratio: last 40% of frames vs first 30% (reverb lifts late energy).
    n_fr = mag.shape[1]
    early = mag[:, : max(1, int(0.3 * n_fr))].sum()
    late = mag[:, int(0.6 * n_fr):].sum()
    late_ratio = float(late / (early + 1e-12))

    feats = {
        'crest_factor': float(crest),
        'loudness_spread_db': float(loud_spread),
        'rms_db': float(20 * np.log10(rms + 1e-12)),
        'spec_centroid_mean': float(np.mean(centroid)),
        'spec_centroid_std': float(np.std(centroid)),
        'spec_flatness_mean': float(np.mean(flatness)),
        'spec_rolloff_mean': float(np.mean(rolloff)),
        'zcr_mean': float(zc),
        'hf_ratio': hf_ratio,
        'th_proxy': th_proxy,
        'odd_even_ratio': odd_even,
        'flux_ac_peak': flux_ac_peak,
        'flux_ac_lag_s': flux_ac_lag_s,
        'onset_ac_peak': onset_ac_peak,
        'onset_ac_lag_s': onset_ac_lag_s,
        'rt60_est_s': rt60,
        'late_energy_ratio': late_ratio,
        'stereo_corr': float(stereo_corr) if np.isfinite(stereo_corr) else 1.0,
    }
    return feats


def features_vector(feats: dict) -> np.ndarray:
    return np.array([float(feats[k]) for k in FEATURE_NAMES], dtype=np.float64)
