"""Two playback voices for one note list: acoustic/unplugged, and a distorted-amp approximation.

Both read the same notes (the transcription, the uploaded tab, or a reconciled mix of both), so
what the player hears in either mode is the same notation: same pitches, onsets, durations,
palm mutes, let-ring and bends. Only the "instrument" changes.

Note dicts accept:
  start | onset | time          onset in seconds (``time`` is what tab/score notes carry)
  end | duration                note end, or held length (default 0.3 s)
  midi | pitch                  MIDI pitch
  velocity | amplitude          0..1 (amplitude > 1.5 treated as a loudness score / 5)
  damping | palm_mute | palmMute   palm mute: short, darker note
  let_ring | letRing            keep ringing past the written length
  bend                          [[fraction of note, semitones], ...]
  string, track                 a re-pick on the same string (in the same track) stops the
                                previous note: a real string can't sound twice.

Voice: tuned Karplus-Strong. Loop delay = N + all-pass fraction + the averaging filter's half
sample, so pitch is exact (the old voice truncated the period to an int and ignored the half
sample: C5 ~14 cents flat, C6 ~35 cents flat). Loss per period follows a guitar-like decay
curve (low E ~4 s to 60 dB, ~1.2-1.6 s by the top frets) with the loop filter's own loss
compensated, instead of one fixed per-sample factor, which made notes above ~C6 die in ~0.15 s.

"Original sound" is an APPROXIMATION: the same plucked strings (plus a pick click) through a
waveshaper amp and a cabinet stand-in (or a cab IR file if one is given). It is not a model of
the record's real amp. When the song's separated guitar stem is supplied, the gain is
automated from the stem's clean/crunch/distorted reading per window (effect classifier), and
the render's tone colour can be matched to the stem's spectral envelope over time (see ``stem_match_eq``).
"""
from __future__ import annotations

import numpy as np
from scipy import signal

DRIVES = {  # pre-gain into the clipper; same table as the UI's guitarTone.ts AMP
    'clean': 1.0,
    'crunch': 12.0,
    'distorted': 150.0,
}


# ---------------------------------------------------------------- note field helpers

def note_start(n) -> float:
    for k in ('start', 'onset', 'time'):
        if n.get(k) is not None:
            return float(n[k])
    return 0.0


def note_length(n) -> float:
    s = note_start(n)
    if n.get('end') is not None:
        return max(0.0, float(n['end']) - s)
    return max(0.0, float(n.get('duration', 0.3)))


def note_midi(n):
    m = n.get('midi', n.get('pitch'))
    return None if m is None else float(m)


def note_velocity(n, default=0.7) -> float:
    v = n.get('velocity', n.get('amplitude'))
    if v is None:
        return default
    v = float(v)
    if v > 1.5:  # loudness-score-like
        v = v / 127.0 if v > 10 else v / 5.0
    return float(np.clip(v, 0.05, 1.0))


def is_palm_mute(n) -> bool:
    return bool(n.get('damping') or n.get('palm_mute') or n.get('palmMute'))


def is_let_ring(n) -> bool:
    return bool(n.get('let_ring') or n.get('letRing'))


def _string_key(n):
    s = n.get('string')
    if s is not None:
        return (n.get('track'), 's', int(s))
    return (n.get('track'), 'p', note_midi(n))


def natural_t60(freq: float) -> float:
    """Seconds to fall 60 dB for an unmuted string, by pitch (low E ~4 s, top frets ~1.2-1.6 s)."""
    o = np.log2(max(freq, 20.0) / 82.41)
    return float(np.interp(o, [0, 2, 4, 5], [4.0, 2.6, 1.6, 1.2]))


# ---------------------------------------------------------------- the string

def ks_pluck(freq, n_samples, sr=44100, velocity=0.7, t60=None, darkness=0.5, seed=None):
    """Tuned Karplus-Strong string, ``n_samples`` long.

    darkness 0..1 low-passes the pick burst (palm mute / neck pickup darker, bridge brighter).
    Fast: the loop is run one period at a time with lfilter, which is exact because the
    feedback delay is at least one period.
    """
    n = int(n_samples)
    if n < 2 or freq <= 0:
        return np.zeros(max(n, 1))
    t60 = float(t60 or natural_t60(freq))
    # Loop filter (1-S) + S z^-1: S=0.5 is the classic 2-tap average, smaller S loses less top
    # end per period (Jaffe-Smith "decay stretching") so high strings aren't killed by the filter.
    S = float(np.interp(np.log2(max(freq, 20.0) / 82.41), [0, 3, 5], [0.5, 0.25, 0.1]))
    w = 2 * np.pi * freq / sr
    r = 10 ** (-3.0 * (1.0 / freq) / max(t60, 1e-3))  # wanted loss per period
    # if the filter alone would lose more than r per period, use a smaller S (keeps g < 1)
    q = 0.9 * (1 - r * r) / (4 * np.sin(w / 2) ** 2 + 1e-18)
    if q < 0.25:
        S = min(S, (1 - np.sqrt(1 - 4 * q)) / 2)
    d_loop = np.arctan2(S * np.sin(w), (1 - S) + S * np.cos(w)) / w
    P = sr / freq - d_loop
    N = int(np.floor(P))
    frac = P - N
    if frac < 0.1 and N > 2:  # keep the all-pass coefficient away from -1
        N, frac = N - 1, frac + 1
    if N < 2:
        N, frac = 2, 0.0
    c = (1 - frac) / (1 + frac)
    h_mag = abs((1 - S) + S * np.exp(-1j * w))
    # loss per period so the fundamental falls 60 dB in t60 (filter loss compensated, g < 1)
    g = min(0.99995, r / h_mag)
    rng = np.random.default_rng(int(freq * 1000 + (seed or 0)) % 2**32)
    exc = rng.uniform(-1, 1, N)
    if darkness > 0:
        a = float(np.clip(darkness, 0, 0.97))
        exc = signal.lfilter([1 - a], [1, -a], exc)
    exc -= exc.mean()
    exc *= velocity / (np.max(np.abs(exc)) + 1e-12)
    b = g * np.convolve([1.0 - S, S], [c, 1.0])
    a_ = np.array([1.0, c])
    zi = np.zeros(2)
    out = np.zeros(n + N)
    out[:N] = exc
    fb = np.zeros(N)
    for k in range(0, n, N):
        blk = out[k:k + N]
        if k:
            blk += fb[:len(blk)]
        fb, zi = signal.lfilter(b, a_, blk, zi=zi)
        if len(fb) < N:
            break
    y = out[:n]
    atk = min(n, int(0.002 * sr))
    if atk > 1:
        y[:atk] *= np.linspace(0, 1, atk)
    return y


def _bend_read(y, bend, held_samples):
    """Read a rendered string faster as it is bent up (pitch follows the bend curve)."""
    pts = np.asarray(bend, dtype=float)
    if pts.ndim != 2 or len(pts) < 2:
        return y
    i = np.arange(len(y), dtype=float)
    f = np.clip(i / max(1, held_samples), 0, 1)
    semis = np.interp(f, pts[:, 0], pts[:, 1])
    pos = np.concatenate([[0.0], np.cumsum(2 ** (semis / 12))[:-1]])
    return np.interp(pos, np.arange(len(y)), y, right=0.0)


def plan(notes):
    """Sorted notes with their sounding length: written length, then a fret-hand release
    (~60 ms) unless let-ring; palm mutes capped at 0.25 s; cut at the next pick on that string."""
    ns = sorted((n for n in notes if note_midi(n) is not None), key=note_start)
    nxt_on = {}
    out = []
    for n in reversed(ns):
        s = note_start(n)
        key = _string_key(n)
        nxt = nxt_on.get(key)
        held = max(0.04, note_length(n))
        if is_palm_mute(n):
            ring = min(held + 0.05, 0.25)
        elif is_let_ring(n):
            ring = min(held + 2.5, 8.0)
        else:
            ring = held + 0.25  # release tail (damped below)
        if nxt is not None and nxt > s + 1e-3:
            ring = min(ring, nxt - s + 0.008)  # tiny overlap so the cut isn't a click
            held = min(held, nxt - s)
        out.append((n, s, held, ring))
        nxt_on[key] = s
    out.reverse()
    return out


def render_note(n, held, ring, sr=44100, tuning_cents=0.0, darkness=None, t60_scale=1.0, seed=0):
    midi = note_midi(n)
    freq = 440.0 * 2 ** ((midi - 69 + tuning_cents / 100.0) / 12)
    pm = is_palm_mute(n)
    t60 = natural_t60(freq) * t60_scale
    if pm:
        t60 = min(t60, 0.18)
    dark = darkness if darkness is not None else (0.85 if pm else 0.45)
    n_samp = int(ring * sr) + 1
    bend = n.get('bend')
    extra = 1.0
    if bend:
        try:
            extra = 2 ** (max(0.0, max(float(p[1]) for p in bend)) / 12)
        except Exception:
            bend = None
    y = ks_pluck(freq, int(n_samp * extra) + 4, sr, velocity=note_velocity(n), t60=t60,
                 darkness=dark, seed=seed)
    if bend:
        y = _bend_read(y, bend, int(held * sr))
    y = y[:n_samp]
    # fret-hand release after the written length (not for let-ring / palm mute)
    rel = int(held * sr)
    if not is_let_ring(n) and not pm and rel < len(y):
        y[rel:] *= np.exp(-np.arange(len(y) - rel) / (0.06 * sr))
    r = min(len(y), int(0.008 * sr))
    if r > 1:
        y[-r:] *= np.linspace(1, 0, r)
    return y


def _pan_gains(p):
    p = float(np.clip(p, -1, 1))
    th = (p + 1) * np.pi / 4
    return np.cos(th), np.sin(th)


def default_pans(notes):
    """Mild spread: lead/solo tracks centre, rhythm tracks alternate left/right."""
    tracks = []
    names = {}
    for n in notes:
        t = n.get('track')
        if t not in names:
            tracks.append(t)
            names[t] = str(n.get('track_name', '') or '').lower()
    pans, side = {}, -1
    for t in tracks:
        if any(w in names[t] for w in ('solo', 'lead')):
            pans[t] = 0.0
        else:
            pans[t] = 0.35 * side
            side = -side
    return pans


def _length(notes, plans, length_s):
    if length_s:
        return float(length_s)
    return max((s + ring for _, s, _, ring in plans), default=1.0) + 0.5


def _render_tracks(notes, sr, tuning_cents, length_s, darkness=None, t60_scale=1.0, pick_click=0.0):
    """Dry string bus per track: {track: mono array}."""
    plans = plan(notes)
    total = int(_length(notes, plans, length_s) * sr) + 1
    buses = {}
    rng = np.random.default_rng(7)
    click = None
    if pick_click > 0:
        k = int(0.004 * sr)
        b, a = signal.butter(2, 2000 / (sr / 2), 'high')
        click = signal.lfilter(b, a, rng.standard_normal(k)) * np.exp(-np.arange(k) / (0.0008 * sr))
        click /= np.max(np.abs(click)) + 1e-12
    for i, (n, s, held, ring) in enumerate(plans):
        y = render_note(n, held, ring, sr, tuning_cents, darkness, t60_scale, seed=i)
        bus = buses.setdefault(n.get('track'), np.zeros(total))
        i0 = int(round(s * sr))
        if i0 >= total:
            continue
        i1 = min(total, i0 + len(y))
        bus[i0:i1] += y[:i1 - i0]
        if click is not None:
            j1 = min(total, i0 + len(click))
            bus[i0:j1] += pick_click * note_velocity(n) * click[:j1 - i0] * (0.6 if is_palm_mute(n) else 1.0)
    return buses, total


def _mix(buses, total, pans, stereo):
    if not stereo:
        out = np.zeros(total)
        for y in buses.values():
            out += y
        return out
    out = np.zeros((total, 2))
    for t, y in buses.items():
        gl, gr = _pan_gains(pans.get(t, 0.0))
        out[:, 0] += gl * y
        out[:, 1] += gr * y
    return out


def _normalize(x, peak=0.9):
    return (x / (np.max(np.abs(x)) + 1e-12) * peak)


# ---------------------------------------------------------------- 1. acoustic / unplugged

def _peak(f0, gain_db, q, sr):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    b = np.array([1 + al * A, -2 * np.cos(w), 1 - al * A])
    a = np.array([1 + al / A, -2 * np.cos(w), 1 - al / A])
    return b / a[0], a / a[0]


def body_eq(x, sr=44100):
    """Flat-top acoustic body stand-in: air (~100 Hz) and top-plate (~200 Hz) resonances,
    a slight 2.5 kHz presence and gentle top roll-off. A colour, not a measured body IR."""
    y = np.asarray(x, dtype=float)
    for f0, g, q in ((100, 4.0, 2.0), (210, 3.0, 2.5), (2500, 2.0, 1.0)):
        b, a = _peak(f0, g, q, sr)
        y = signal.lfilter(b, a, y, axis=0)
    b, a = signal.butter(2, min(0.99, 9000 / (sr / 2)))
    return signal.lfilter(b, a, y, axis=0)


def render_acoustic(notes, sr=44100, length_s=None, tuning_cents=0.0, stereo=False, pans=None, body=True):
    """Acoustic / unplugged playback: every note, the player's damping, let-ring and bends,
    on a plucked steel string with a body colour. No amp, no effects."""
    if not notes:
        return np.zeros((int(sr * (length_s or 1.0)), 2) if stereo else int(sr * (length_s or 1.0)))
    buses, total = _render_tracks(notes, sr, tuning_cents, length_s)
    out = _mix(buses, total, pans or default_pans(notes), stereo)
    if body:
        out = body_eq(out, sr)
    return _normalize(out).astype(np.float64)


# ---------------------------------------------------------------- 2. distorted (amp approximation)

def find_cab_ir(paths=()):
    """First readable cab IR among ``paths`` (wav). None when there is none: the
    cabinet stand-in filter is used instead."""
    from pathlib import Path
    for p in paths:
        p = Path(p)
        if p.is_file() and p.suffix.lower() == '.wav':
            try:
                from scipy.io import wavfile
                r, ir = wavfile.read(str(p))
                ir = ir.astype(float)
                if ir.ndim > 1:
                    ir = ir.mean(axis=1)
                return r, ir / (np.max(np.abs(ir)) + 1e-12)
            except Exception:
                continue
    return None


def cab_standin(x, sr=44100):
    """Closed-back 4x12 + close mic stand-in: tight low end, ~110 Hz thump, upper-mid
    presence ~2.3 kHz, steep roll-off above ~5 kHz. Generic; not any real cabinet."""
    y = np.asarray(x, dtype=float)
    b, a = signal.butter(2, 75 / (sr / 2), 'high')
    y = signal.lfilter(b, a, y, axis=0)
    for f0, g, q in ((110, 3.0, 1.2), (2300, 4.0, 1.4), (400, -2.0, 1.0)):
        b, a = _peak(f0, g, q, sr)
        y = signal.lfilter(b, a, y, axis=0)
    sos = signal.butter(4, 5200 / (sr / 2), output='sos')
    return signal.sosfilt(sos, y, axis=0)


def amp(x, sr=44100, gain=150.0, cab_ir=None, scoop_db=-5.0):
    """Waveshaper amp: tight HP + mid push into two asymmetric tanh stages, a mid-scooped tone
    stack, then the cab (IR convolution if given, else :func:`cab_standin`).

    ``gain`` may be a scalar or a per-sample array (automation). gain <= 1.5 is passed clean.
    """
    y = np.asarray(x, dtype=float)
    g = np.broadcast_to(np.asarray(gain, dtype=float), y.shape).copy()
    # input conditioning: tighten lows, push mids (TS-style) before clipping
    b, a = signal.butter(1, 110 / (sr / 2), 'high')
    pre = signal.lfilter(b, a, y)
    b, a = _peak(750, 6.0, 0.8, sr)
    pre = signal.lfilter(b, a, pre)
    sos = signal.butter(2, 6500 / (sr / 2), output='sos')  # limit aliasing into the clipper
    pre = signal.sosfilt(sos, pre)
    pre /= np.max(np.abs(pre)) + 1e-12
    bias = 0.25
    s1 = np.tanh(g * pre + bias) - np.tanh(bias)
    b, a = signal.butter(1, 40 / (sr / 2), 'high')  # coupling cap removes the DC from the bias
    s1 = signal.lfilter(b, a, s1)
    s2 = np.tanh(np.minimum(g, 3.0) * s1) / np.tanh(np.minimum(g, 3.0))
    drive_mix = np.clip((g - 1.0) / 4.0, 0.0, 1.0)  # clean below ~1.5: blend back to dry
    y = drive_mix * s2 + (1 - drive_mix) * pre
    b, a = _peak(500, scoop_db, 0.7, sr)
    y = signal.lfilter(b, a, y)
    if cab_ir is not None:
        ir_sr, ir = cab_ir
        if ir_sr != sr:
            ir = signal.resample_poly(ir, sr, ir_sr)
        y = signal.fftconvolve(y, ir)[:len(y)]
    else:
        y = cab_standin(y, sr)
    return y


_GAIN_FX = ('distortion', 'overdrive', 'fuzz')


def stem_window_tone(seg, sr, method='fx'):
    """'clean' | 'crunch' | 'distorted' | 'uncertain' for one stem window.

    method='fx' (default): the IDMT-trained effect forest (``classify.match_effects``). Top label
    distortion/fuzz -> distorted, overdrive -> crunch, a gain effect present at >= 0.3 but not top
    -> crunch, otherwise clean. On One this keeps the intro/verses clean (the forest calls them
    'feedback_delay', i.e. echoey clean) and the machine-gun/solo sections distorted.
    method='tone': ``song_analysis.tone_estimate`` (whole-song heuristic; on 4 s windows of One it
    called the clean intro 'distorted', so it is not the default here)."""
    x = np.asarray(seg, dtype=float)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if len(x) < sr or np.sqrt(np.mean(x ** 2)) < 1e-3:
        return 'uncertain'
    if method == 'tone':
        from ..song_analysis import tone_estimate
        return tone_estimate(x, sr)['tone']
    from .classify import match_effects
    fx = match_effects(x, sr).get('effects') or []
    if not fx:
        return 'clean'
    top = str(fx[0].get('name', ''))
    gain = max((float(e.get('confidence', 0)) for e in fx if e.get('name') in _GAIN_FX), default=0.0)
    if top in ('distortion', 'fuzz'):
        return 'distorted'
    if top == 'overdrive' or gain >= 0.3:
        return 'crunch'
    return 'clean'


def drive_curve_from_stem(stem, stem_sr, tab_to_stem, total_s, sr=44100, win_s=4.0, hop_s=2.0, method='fx'):
    """Gain automation (per output sample, note-list time) from the separated guitar stem.

    Each window of the stem at the aligned time gets :func:`stem_window_tone`; a 3-window
    majority vote removes flicker; 'uncertain' (silence) keeps the previous setting. The
    DRIVES gain is interpolated in log-gain and smoothed over ~0.5 s.
    ``tab_to_stem(t)`` maps a note-list time to the stem's time (e.g. 23.45 + 1.005 t)."""
    x = np.asarray(stem, dtype=float)
    if x.ndim > 1:
        x = x.mean(axis=1)
    centres = np.arange(0.0, total_s + hop_s, hop_s)
    raw = []
    for c in centres:
        m = tab_to_stem(c)
        i0, i1 = int((m - win_s / 2) * stem_sr), int((m + win_s / 2) * stem_sr)
        raw.append(stem_window_tone(x[max(0, i0):max(0, i1)], stem_sr, method))
    rank = {'clean': 0, 'crunch': 1, 'distorted': 2}
    tones, gains, prev = [], [], 'distorted'
    for i, t in enumerate(raw):
        nb = [r for r in raw[max(0, i - 1):i + 2] if r in rank]
        if nb:
            prev = sorted(nb, key=rank.get)[len(nb) // 2]  # median of the neighbourhood
        tones.append(prev)
        gains.append(DRIVES[prev])
    t = np.arange(int(total_s * sr) + 1) / sr
    lg = np.interp(t, centres, np.log(gains))
    k = int(0.5 * sr)
    lg = np.convolve(lg, np.ones(k) / k, mode='same') if len(lg) > k else lg
    return np.exp(lg), list(zip(centres.tolist(), tones))


def stem_match_eq(y, sr, stem, stem_sr, tab_to_stem, n_bands=20, max_db=9.0, smooth_s=2.0, chunk_s=30.0):
    """Shape ``y``'s tone colour over time toward the stem's spectral envelope.

    Per ~0.1 s frame, log-spaced band energies (80 Hz-10 kHz) of the stem (at the aligned time)
    and of the render are smoothed over ``smooth_s``; the render gets the per-band dB difference,
    clamped to +/-``max_db``, with the overall level difference removed (loudness is not copied).
    Frames where the stem is near-silent are left alone. This copies average tone colour only:
    not the real amp's dynamics, not notes (bleed from other guitars/drums in the stem colours it
    too), and it cannot add what the render doesn't play."""
    import librosa
    mono_y = y.mean(axis=1) if y.ndim > 1 else y
    s = np.asarray(stem, dtype=float)
    s = s.mean(axis=1) if s.ndim > 1 else s
    hop = 2048
    n_fft = 4096
    edges = np.geomspace(80, 10000, n_bands + 1)
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    band_of = np.digitize(freqs, edges) - 1  # -1 / n_bands = outside

    def bands(S):
        P = np.abs(S) ** 2
        E = np.zeros((n_bands, P.shape[1]))
        for b in range(n_bands):
            m = band_of == b
            E[b] = P[m].sum(axis=0) if m.any() else 0
        return E

    Yr = librosa.stft(mono_y.astype(np.float32), n_fft=n_fft, hop_length=hop)
    Er = bands(Yr)
    times = np.arange(Er.shape[1]) * hop / sr
    # stem frames at the aligned times
    s_res = s if stem_sr == sr else librosa.resample(s, orig_sr=stem_sr, target_sr=sr)
    Ss = librosa.stft(s_res.astype(np.float32), n_fft=n_fft, hop_length=hop)
    Es_all = bands(Ss)
    stem_times = np.arange(Es_all.shape[1]) * hop / sr
    mapped = np.array([tab_to_stem(t) for t in times])
    idx = np.clip(np.searchsorted(stem_times, mapped), 0, Es_all.shape[1] - 1)
    Es = Es_all[:, idx]
    k = max(1, int(smooth_s * sr / hop))
    ker = np.ones(k) / k
    sm = lambda E: np.apply_along_axis(lambda r: np.convolve(r, ker, mode='same'), 1, E)
    Ls, Lr = 10 * np.log10(sm(Es) + 1e-12), 10 * np.log10(sm(Er) + 1e-12)
    d = Ls - Lr
    d -= d.mean(axis=0, keepdims=True)
    tot_s = 10 * np.log10(Es.sum(axis=0) + 1e-12)
    tot_r = 10 * np.log10(Er.sum(axis=0) + 1e-12)
    quiet = (tot_s < np.percentile(tot_s, 95) - 45) | (tot_r < np.percentile(tot_r, 95) - 45)
    d[:, quiet] = 0.0
    d = np.clip(d, -max_db, max_db)
    centres = np.sqrt(edges[:-1] * edges[1:])
    gain_db = np.empty((len(freqs), d.shape[1]))
    lf = np.log(np.maximum(freqs, 1.0))
    for j in range(d.shape[1]):
        gain_db[:, j] = np.interp(lf, np.log(centres), d[:, j])
    G = (10 ** (gain_db / 20)).astype(np.float32)
    del Ss, Es_all, s_res

    def apply(ch):
        # pad by a frame each side: the inverse STFT divides by a tiny window sum at the very
        # edges, which turned per-frame gain changes into a click at the end of the clip
        padded = np.pad(ch.astype(np.float32), (n_fft, n_fft))
        Z = librosa.stft(padded, n_fft=n_fft, hop_length=hop)
        Gp = np.pad(G, ((0, 0), (n_fft // hop, 0)), mode='edge')
        Gp = np.pad(Gp, ((0, 0), (0, max(0, Z.shape[1] - Gp.shape[1]))), mode='edge')
        Z *= Gp[:, :Z.shape[1]]
        return librosa.istft(Z, hop_length=hop, length=len(padded))[n_fft:n_fft + len(ch)]

    if y.ndim > 1:
        return np.stack([apply(y[:, c]) for c in range(y.shape[1])], axis=1), d
    return apply(y), d


def render_distorted(notes, sr=44100, length_s=None, tuning_cents=0.0, drive='distorted',
                     cab_ir=None, stem=None, stem_sr=None, tab_to_stem=None, match_eq=True,
                     stereo=True, pans=None, report=None):
    """"Original sound" approximation: the same note list through a distorted amp.

    drive: 'clean' | 'crunch' | 'distorted' | number | per-sample array.
    If ``stem`` (+ ``stem_sr`` and ``tab_to_stem``) is given: drive follows the stem's
    clean/crunch/distorted reading per window (overrides ``drive``) and, with ``match_eq``,
    tone colour is matched to the stem.
    ``report`` (dict) receives what was used. Label results "distorted playback approximation".
    """
    rep = report if report is not None else {}
    rep['label'] = 'distorted playback approximation'
    if not notes:
        n = int(sr * (length_s or 1.0))
        return np.zeros((n, 2) if stereo else n)
    # DI-like strings: brighter pick (bridge pickup), a bit more sustain, a pick click
    buses, total = _render_tracks(notes, sr, tuning_cents, length_s, darkness=None, t60_scale=1.3,
                                  pick_click=0.25)
    total_s = total / sr
    if stem is not None and tab_to_stem is not None:
        g, tones = drive_curve_from_stem(stem, stem_sr, tab_to_stem, total_s, sr)
        g = g[:total] if len(g) >= total else np.pad(g, (0, total - len(g)), mode='edge')
        rep['drive'] = 'from stem (effect forest per 4 s window, 3-window median)'
        rep['drive_windows'] = tones
    elif isinstance(drive, str):
        g = DRIVES.get(drive, DRIVES['distorted'])
        rep['drive'] = drive
    else:
        g = drive
        rep['drive'] = 'custom'
    names = {}
    for n in notes:
        names.setdefault(n.get('track'), str(n.get('track_name', '') or '').lower())
    amped = {}
    for t, y in buses.items():
        # leads get a little less low end and more presence: different scoop
        lead = any(w in names.get(t, '') for w in ('solo', 'lead'))
        amped[t] = amp(y, sr, gain=g, cab_ir=cab_ir, scoop_db=-2.0 if lead else -5.0)
    rep['cab'] = 'impulse response' if cab_ir is not None else 'cab_standin filter (no IR found)'
    out = _mix(amped, total, pans or default_pans(notes), stereo)
    if stem is not None and tab_to_stem is not None and match_eq:
        out, d = stem_match_eq(out, sr, stem, stem_sr, tab_to_stem)
        rep['match_eq'] = {'bands': 20, 'max_db': 9.0, 'mean_abs_db': float(np.mean(np.abs(d)))}
    # 0.8, not 0.9: dense clipped material overshoots after lossy encoding
    return _normalize(out, 0.8).astype(np.float64)
