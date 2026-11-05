"""Synthetic guitar-effect renderers for building template libraries.

CPU-light NumPy/SciPy implementations. Not plugin-accurate; good enough to make
separable feature signatures for a prototype matcher.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

EFFECT_NAMES = (
    'clean',
    'overdrive',
    'distortion',
    'fuzz',
    'compressor',
    'chorus',
    'flanger',
    'phaser',
    'tremolo',
    'delay',
    'reverb',
    'wah',
)


def _mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=-1)
    return x


def _norm(x: np.ndarray, ref_peak: float | None = None) -> np.ndarray:
    peak = np.max(np.abs(x)) + 1e-12
    target = ref_peak if ref_peak is not None else min(0.95, peak)
    return x * (target / peak)


def overdrive(x, drive=3.0):
    x = _mono(x)
    y = np.tanh(drive * x) / np.tanh(drive)
    return _norm(y, np.max(np.abs(x)) + 1e-12)


def distortion(x, drive=8.0):
    x = _mono(x)
    # Pre-emphasis then hard-ish clip (asymmetric).
    b, a = signal.butter(1, 0.15, btype='highpass')
    xp = signal.lfilter(b, a, x)
    y = np.clip(drive * xp, -0.7, 1.0)
    y = np.tanh(1.5 * y)
    # Mild cab-ish lowpass.
    b2, a2 = signal.butter(2, 0.35)
    y = signal.lfilter(b2, a2, y)
    return _norm(y, np.max(np.abs(x)) + 1e-12)


def fuzz(x, drive=15.0):
    x = _mono(x)
    y = np.sign(x) * (1.0 - np.exp(-drive * np.abs(x)))
    y = np.where(x >= 0, y, 0.7 * y)  # asymmetric
    return _norm(y, np.max(np.abs(x)) + 1e-12)


def compressor(x, threshold=0.2, ratio=4.0, attack=0.005, release=0.05, sr=44100):
    x = _mono(x)
    env = np.abs(x)
    at = np.exp(-1.0 / (attack * sr))
    rt = np.exp(-1.0 / (release * sr))
    smooth = np.zeros_like(env)
    prev = 0.0
    for i, e in enumerate(env):
        coeff = at if e > prev else rt
        prev = coeff * prev + (1 - coeff) * e
        smooth[i] = prev
    gain = np.ones_like(smooth)
    over = smooth > threshold
    gain[over] = (threshold + (smooth[over] - threshold) / ratio) / (smooth[over] + 1e-12)
    return _norm(x * gain, np.max(np.abs(x)) + 1e-12)


def _mod_delay(x, sr, delay_ms=8.0, depth_ms=2.0, rate_hz=0.8, feedback=0.0, mix=0.5):
    x = _mono(x)
    n = len(x)
    base = int(delay_ms * 1e-3 * sr)
    depth = int(depth_ms * 1e-3 * sr)
    buf = np.zeros(base + depth + 4)
    y = np.zeros(n)
    phase = 0.0
    dphi = 2 * np.pi * rate_hz / sr
    fb = 0.0
    for i in range(n):
        d = base + int(depth * (0.5 + 0.5 * np.sin(phase)))
        phase += dphi
        delayed = buf[d] if d < len(buf) else 0.0
        out = (1 - mix) * x[i] + mix * delayed
        y[i] = out
        buf[1:] = buf[:-1]
        buf[0] = x[i] + feedback * fb
        fb = delayed
    return _norm(y, np.max(np.abs(x)) + 1e-12)


def chorus(x, sr=44100):
    return _mod_delay(x, sr, delay_ms=12.0, depth_ms=3.0, rate_hz=0.9, feedback=0.0, mix=0.45)


def flanger(x, sr=44100):
    return _mod_delay(x, sr, delay_ms=2.0, depth_ms=1.5, rate_hz=0.4, feedback=0.55, mix=0.5)


def phaser(x, sr=44100, rate_hz=0.35, stages=4, mix=0.5):
    x = _mono(x)
    y = x.copy()
    # Cascaded one-pole allpass with modulated coefficient.
    n = len(x)
    z = np.zeros(stages)
    phase = 0.0
    dphi = 2 * np.pi * rate_hz / sr
    out = np.zeros(n)
    for i in range(n):
        coeff = 0.3 + 0.6 * (0.5 + 0.5 * np.sin(phase))
        phase += dphi
        s = y[i]
        for k in range(stages):
            xh = s
            s = -coeff * xh + z[k]
            z[k] = xh + coeff * s
        out[i] = (1 - mix) * x[i] + mix * s
    return _norm(out, np.max(np.abs(x)) + 1e-12)


def tremolo(x, sr=44100, rate_hz=5.0, depth=0.7):
    x = _mono(x)
    t = np.arange(len(x)) / sr
    mod = (1 - depth) + depth * (0.5 + 0.5 * np.sin(2 * np.pi * rate_hz * t))
    return _norm(x * mod, np.max(np.abs(x)) + 1e-12)


def delay(x, sr=44100, delay_ms=95.0, feedback=0.35, mix=0.4):
    x = _mono(x)
    d = max(1, int(delay_ms * 1e-3 * sr))
    buf = np.zeros(d)
    out = np.zeros(len(x))
    for i in range(len(x)):
        delayed = buf[-1]
        out[i] = (1 - mix) * x[i] + mix * delayed
        new = x[i] + feedback * delayed
        buf[1:] = buf[:-1]
        buf[0] = new
    return _norm(out, np.max(np.abs(x)) + 1e-12)


def _synth_ir(sr, rt60=1.2, length_s=None):
    length_s = length_s or min(3.0, rt60 * 2.5)
    n = int(length_s * sr)
    t = np.arange(n) / sr
    # Noise burst with exponential envelope; mild early reflections.
    noise = np.random.randn(n)
    env = np.exp(-6.91 * t / max(rt60, 0.05))  # approx -60 dB at rt60
    ir = noise * env
    # A few early taps
    for ms, g in ((12, 0.45), (28, 0.3), (47, 0.2)):
        k = int(ms * 1e-3 * sr)
        if k < n:
            ir[k] += g
    return ir / (np.max(np.abs(ir)) + 1e-12)


def reverb(x, sr=44100, rt60=1.2, mix=0.35):
    x = _mono(x)
    ir = _synth_ir(sr, rt60=rt60)
    wet = signal.fftconvolve(x, ir, mode='full')[: len(x)]
    y = (1 - mix) * x + mix * wet
    return _norm(y, np.max(np.abs(x)) + 1e-12)


def wah(x, sr=44100, rate_hz=1.2):
    x = _mono(x)
    # Time-varying bandpass (biquad coeffs updated in blocks).
    n = len(x)
    out = np.zeros(n)
    block = 256
    z = np.zeros(2)
    for start in range(0, n, block):
        end = min(n, start + block)
        mid = (start + end) // 2
        sweep = 0.5 + 0.5 * np.sin(2 * np.pi * rate_hz * mid / sr)
        f0 = 400 + 1600 * sweep
        w0 = 2 * np.pi * f0 / sr
        Q = 4.0
        alpha = np.sin(w0) / (2 * Q)
        b0 = alpha
        b1 = 0
        b2 = -alpha
        a0 = 1 + alpha
        a1 = -2 * np.cos(w0)
        a2 = 1 - alpha
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        seg, z = signal.lfilter(b, a, x[start:end], zi=z)
        out[start:end] = seg
    return _norm(0.5 * x + 0.5 * out, np.max(np.abs(x)) + 1e-12)


def apply_effect(name: str, x, sr=44100, **kwargs):
    name = name.lower()
    if name == 'clean':
        return _mono(x).astype(np.float64)
    fn = {
        'overdrive': overdrive,
        'distortion': distortion,
        'fuzz': fuzz,
        'compressor': compressor,
        'chorus': chorus,
        'flanger': flanger,
        'phaser': phaser,
        'tremolo': tremolo,
        'delay': delay,
        'reverb': reverb,
        'wah': wah,
    }.get(name)
    if fn is None:
        raise ValueError(f'unknown effect {name!r}')
    if name in ('compressor', 'chorus', 'flanger', 'phaser', 'tremolo', 'delay', 'reverb', 'wah'):
        return fn(x, sr=sr, **kwargs)
    return fn(x, **kwargs)
