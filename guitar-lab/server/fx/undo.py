"""Undo non-performance effects and render acoustic-style playback.

Strategy (honest limits documented in EFFECTS_RESEARCH.md / DESIGN.md):
- Reverb: single-channel spectral subtraction guided by a crude RT60 estimate.
- Distortion/OD/fuzz: inverse soft-clip only for mild OD; otherwise rely on
  note list → acoustic playback (server/fx/playback.py: tuned Karplus–Strong, player
  damping / let-ring / bends kept). The same notes can be played through a distorted-amp
  approximation with playback.render_distorted.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from .features import extract_features
from .renderers import overdrive


def estimate_rt60(audio, sr=44100) -> float:
    return float(extract_features(audio, sr)['rt60_est_s'])


def dereverb_spectral(audio, sr=44100, rt60=None, reduction_db=10.0):
    """Lebart-style-ish late reverberation attenuation via spectral subtraction.

    Not WPE. Works best on sparse mono lines; can thin polyphonic material.
    """
    x = np.asarray(audio, dtype=np.float64)
    mono = False
    if x.ndim > 1:
        # process mid
        mid = x.mean(axis=-1)
        mono = False
    else:
        mid = x
        mono = True
    rt60 = rt60 or estimate_rt60(mid, sr)
    n_fft = 2048
    hop = 512
    f, t, Z = signal.stft(mid, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window='hann')
    mag = np.abs(Z)
    phase = np.angle(Z)
    # Late reverb estimate: smoothed past magnitude * decay factor.
    # Frame lag corresponding to ~50 ms early/late split.
    lag = max(1, int(0.05 * sr / hop))
    decay = np.exp(-6.91 * (hop / sr) / max(rt60, 0.05))
    rev = np.zeros_like(mag)
    for i in range(mag.shape[1]):
        src = mag[:, max(0, i - lag)]
        rev[:, i] = src * (decay ** lag)
    # Smooth rev in time
    rev = signal.lfilter([0.2], [1, -0.8], rev, axis=1)
    alpha = 10 ** (-reduction_db / 20)
    cleaned = np.maximum(mag - rev, alpha * mag)
    Zc = cleaned * np.exp(1j * phase)
    _, y = signal.istft(Zc, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window='hann')
    y = y[: len(mid)]
    # Match loudness roughly
    y *= (np.sqrt(np.mean(mid ** 2)) + 1e-12) / (np.sqrt(np.mean(y ** 2)) + 1e-12)
    return y if mono else y


def inverse_soft_clip(audio, drive=3.0):
    """Approximate inverse of tanh(drive*x)/tanh(drive) — only valid for mild OD."""
    x = np.asarray(audio, dtype=np.float64)
    # clip domain of atanh
    scale = np.tanh(drive)
    z = np.clip(x * scale, -0.999, 0.999)
    return np.arctanh(z) / drive


# Measured on real recordings (FX_RESULTS.md): de-reverb triggered by a low-confidence
# 'feedback_delay' guess on CLEAN amp takes (Guitar-TECHS) shortened sustained notes and cost
# note F1 (vibrato clip .706 -> .638). Delay/reverb undo now needs a confident detection.
TIME_FX_MIN_CONFIDENCE = 0.6


def undo_effects(audio, sr=44100, effects=None, features=None):
    """Apply best-effort undo for playback.

    `effects` = names, or the matcher's [{'name', 'confidence'}] list (confidence-gated for
    reverb/delay). Not used in the transcription path: on real amp recordings de-FX audio did
    not raise note F1 (FX_RESULTS.md), so it only feeds the 'clean version' playback.
    """
    raw = list(effects or [])
    effects = []
    for e in raw:
        if isinstance(e, dict):
            name, conf = str(e.get('name', '')).lower(), float(e.get('confidence', 1.0))
            if ('delay' in name or name == 'reverb') and conf < TIME_FX_MIN_CONFIDENCE:
                continue
            effects.append(name)
        else:
            effects.append(str(e).lower())
    features = features or extract_features(audio, sr)
    y = np.asarray(audio, dtype=np.float64)
    if y.ndim > 1:
        y = y.mean(axis=-1)

    if any(e == 'reverb' or 'delay' in e for e in effects) or features.get('rt60_est_s', 0) > 1.5:
        y = dereverb_spectral(y, sr, rt60=features.get('rt60_est_s'))

    # Mild OD inverse only; hard distortion left for acoustic_playback path.
    if 'overdrive' in effects and 'distortion' not in effects and 'fuzz' not in effects:
        try:
            y = inverse_soft_clip(y, drive=3.0)
            peak = np.max(np.abs(y)) + 1e-12
            y = y / peak * min(0.95, peak)
        except Exception:
            pass

    # Light high-shelf cut to tame remaining distortion HF grit (non-destructive-ish).
    if any(e in effects for e in ('distortion', 'fuzz', 'overdrive')):
        b, a = signal.butter(2, 0.45)
        y = signal.lfilter(b, a, y)

    return y.astype(np.float64)


def _karplus_strong(freq, duration, sr, velocity=0.7, damp=0.995):
    """Simple plucked-string synth. Higher damp ⇒ longer sustain; lower ⇒ muted."""
    period = max(2, int(sr / max(freq, 40.0)))
    n = int(duration * sr)
    buf = (np.random.rand(period) * 2 - 1) * velocity
    out = np.zeros(n)
    idx = 0
    for i in range(n):
        out[i] = buf[idx]
        avg = damp * 0.5 * (buf[idx] + buf[(idx - 1) % period])
        buf[idx] = avg
        idx = (idx + 1) % period
    # Soft attack envelope
    atk = min(n, int(0.005 * sr))
    if atk > 1:
        out[:atk] *= np.linspace(0, 1, atk)
    return out


def acoustic_playback(notes, sr=44100, length_s=None, voice='tuned', **kwargs):
    """Render an acoustic-style version from transcribed notes.

    Each note dict supports: midi|pitch, start|onset|time, end|duration, velocity|amplitude,
    damping|palm_mute|palmMute, let_ring|letRing, bend, string/track. Player articulation is
    kept via duration, damping, let-ring and bends.

    voice='tuned' (default) uses :func:`server.fx.playback.render_acoustic` (pitch-exact
    Karplus-Strong, guitar-like sustain by pitch, re-pick stops the string). voice='legacy'
    is the old per-sample loop, kept for comparison.
    """
    if voice != 'legacy':
        from .playback import render_acoustic
        return render_acoustic(notes, sr=sr, length_s=length_s, **kwargs)
    from .playback import note_start
    if not notes:
        return np.zeros(int(sr * (length_s or 1.0)))
    ends = []
    for n in notes:
        start = note_start(n)
        if 'end' in n:
            end = float(n['end'])
        else:
            end = start + float(n.get('duration', 0.3))
        ends.append(end)
    total = length_s or max(ends) + 0.5
    out = np.zeros(int(total * sr) + 1)
    for n in notes:
        midi = n.get('midi', n.get('pitch'))
        if midi is None:
            continue
        freq = 440.0 * (2 ** ((float(midi) - 69) / 12))
        start = note_start(n)
        if 'end' in n:
            dur = max(0.04, float(n['end']) - start)
        else:
            dur = max(0.04, float(n.get('duration', 0.3)))
        vel = float(n.get('velocity', n.get('amplitude', 0.6)))
        if vel > 1.5:  # amplitude-like
            vel = min(1.0, vel / 5.0)
        vel = float(np.clip(vel, 0.05, 1.0))
        damp_flag = bool(n.get('damping', n.get('palm_mute', n.get('palmMute', False))))
        decay = float(n.get('decay', 0.992 if damp_flag else 0.9975))
        if damp_flag:
            dur = min(dur, 0.18)
            decay = min(decay, 0.985)
        sig = _karplus_strong(freq, dur, sr, velocity=vel, damp=decay)
        i0 = int(start * sr)
        i1 = min(len(out), i0 + len(sig))
        out[i0:i1] += sig[: i1 - i0]
    peak = np.max(np.abs(out)) + 1e-12
    return (out / peak * 0.9).astype(np.float64)


def damping_from_decay(audio, onset, end, sr=44100) -> bool:
    """Heuristic palm-mute / damp flag from local amplitude decay."""
    x = np.asarray(audio, dtype=np.float64)
    i0 = max(0, int(onset * sr))
    i1 = min(len(x), int(end * sr))
    if i1 - i0 < 64:
        return False
    seg = np.abs(x[i0:i1])
    # Compare first 30 ms energy to last 30 ms
    w = int(0.03 * sr)
    early = np.mean(seg[:w]) + 1e-12
    late = np.mean(seg[-w:]) + 1e-12
    return bool(20 * np.log10(early / late) > 18 and (end - onset) < 0.35)
