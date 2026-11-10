"""Line a tab file up with a recording, so the tab's own parts (Guitar 1, Riff A, Guitar Solo...)
can name and split what the app hears.

The tab's notes become a chroma "piano roll", the recording a CENS chroma, and dynamic time
warping finds the monotonic map from tab seconds to recording seconds. It bends with the band
(tempo drift, a chart written at the wrong tempo, tempo changes) and does not need the tab's
guitar sound to resemble the record. Repeats must already be played out in the tab notes.
"""
from __future__ import annotations

import numpy as np

SR = 22050
HOP = 2048                        # ~93 ms frames: coarse, but DTW over a whole song stays small
FPS = SR / HOP


def _unit(M):
    norms = np.linalg.norm(M, axis=0, keepdims=True)
    return np.divide(M, norms, out=np.zeros_like(M), where=norms > 1e-9)


def tab_chroma(notes: list, duration: float) -> np.ndarray:
    """12 x frames chroma of the tab: each note's pitch class while it sounds, its attack
    weighted up (attacks are what the recording's chroma shows most clearly)."""
    frames = max(1, int(np.ceil(duration * FPS)) + 1)
    C = np.zeros((12, frames))
    for n in notes:
        a = int(n['time'] * FPS)
        b = max(a + 1, int((n['time'] + max(n['duration'], 0.05)) * FPS))
        if a >= frames:
            continue
        pc = int(n['midi']) % 12
        C[pc, a:min(b, frames)] += 1.0
        C[pc, a] += 1.0
    # CENS-style: log-ish compression and temporal smoothing, like the audio side.
    C = np.log1p(C)
    kernel = np.hanning(9)
    C = np.array([np.convolve(row, kernel / kernel.sum(), mode='same') for row in C])
    return C


def audio_chroma(audio: np.ndarray, sr: int) -> np.ndarray:
    import librosa
    y = audio if audio.ndim == 1 else audio.mean(axis=1 if audio.shape[0] > audio.shape[-1] else 0)
    if sr != SR:
        y = librosa.resample(np.asarray(y, dtype=np.float32), orig_sr=sr, target_sr=SR)
    return librosa.feature.chroma_cens(y=y, sr=SR, hop_length=HOP)


RATIO_PRIOR = 0.03


def linear_fit(X: np.ndarray, Y: np.ndarray, ratios=np.arange(0.5, 2.01, 0.01), max_offset_s: float = 90.0,
               min_overlap: float = 0.6):
    """Coarse map audio = offset + ratio * tab by chroma correlation (unit-norm frames).
    Ratios down to 0.5 and up to 2 cover a chart written at double or half the record's tempo.

    The recording may be the whole song or only part of it (a clip, or a take that starts at
    the solo): the tab may start up to max_offset_s into the recording, or the recording may
    start anywhere inside the tab, as long as min_overlap of the shorter of the two is covered.
    Every offset is scored at once per ratio with an FFT cross-correlation. A short clip of a
    repeating riff fits nearly as well at double speed, so ties go to the tempo nearest the
    chart's (RATIO_PRIOR per octave away)."""
    from scipy.signal import fftconvolve
    best = (-1.0, 1.0, 0.0)
    span = int(max_offset_s * FPS)
    ny = Y.shape[1]
    Yr = Y[:, ::-1]
    for ratio in ratios:
        nx = int(X.shape[1] * ratio)
        if nx < 8:
            continue
        Xr = X[:, np.minimum((np.arange(nx) / ratio).astype(int), X.shape[1] - 1)]
        # corr[k] = sum over frames of Xr[:, i] . Y[:, i + off], with off = k - (nx - 1)
        corr = sum(fftconvolve(Yr[c], Xr[c], mode='full') for c in range(X.shape[0]))[::-1]
        offs = np.arange(-(nx - 1), ny)
        overlap = np.minimum(nx, ny - offs) - np.maximum(0, -offs)
        ok = (overlap >= min_overlap * min(nx, ny)) & (offs <= span)
        if not ok.any():
            continue
        score = np.where(ok, corr / np.maximum(overlap, 1), -1.0)
        k = int(np.argmax(score))
        ranked = float(score[k]) - RATIO_PRIOR * abs(np.log2(ratio))
        if ranked > best[0]:
            best = (ranked, float(ratio), float(offs[k]) / FPS, float(score[k]))
    return {'similarity': best[3] if len(best) > 3 else -1.0, 'ratio': best[1], 'offset': best[2]}


def piecewise_guide(X: np.ndarray, Y: np.ndarray, line: dict, seg_s: float = 40.0, hop_s: float = 20.0,
                    search_s: float = 6.0):
    """Follow tempo changes that one straight line cannot: knots (tab frame, audio frame).

    A band that slips from 101 to 112 BPM half-way through drifts 20 s off any single line, far
    outside the warping band. The tab is cut into 40 s stretches. The stretch that fits best
    near the overall line is the seed; its neighbours are then fitted one after another, each
    searched ±search_s around where the previous stretch's own tempo says it should fall, with
    its tempo free to move ±15%. A stretch with nothing to hold on to (silence in the tab, or a
    weak fit) carries the previous tempo on. Returns None for tabs too short to need it."""
    from scipy.signal import fftconvolve
    nx, ny = X.shape[1], Y.shape[1]
    seg, hop = int(seg_s * FPS), int(hop_s * FPS)
    if nx < 2 * seg:
        return None

    def local(i0, centre, ratio0, search):
        Xs, best = X[:, i0:i0 + seg], None
        for r in ratio0 * np.arange(0.86, 1.161, 0.02):
            m = int(seg * r)
            lo, hi = max(0, int(centre - m / 2 - search * FPS)), min(ny - m, int(centre - m / 2 + search * FPS))
            if hi < lo or m < 8:
                continue
            Xr = Xs[:, np.minimum((np.arange(m) / r).astype(int), seg - 1)]
            corr = sum(fftconvolve(Y[c, lo:hi + m], Xr[c, ::-1], mode='valid') for c in range(X.shape[0])) / m
            k = int(np.argmax(corr))
            ranked = float(corr[k]) - RATIO_PRIOR * abs(np.log2(r / ratio0))
            if best is None or ranked > best[0]:
                best = (ranked, float(r), lo + k + m / 2, float(corr[k]))
        return best

    starts = list(range(0, nx - seg + 1, hop))
    mid = lambda i0: i0 + seg / 2
    first = [local(i0, line['offset'] * FPS + line['ratio'] * mid(i0), line['ratio'], BAND_S) for i0 in starts]
    scored = [(f[3], k) for k, f in enumerate(first) if f]
    if not scored:
        return None
    top, seed = max(scored)
    fits = {seed: (first[seed][2], first[seed][1])}             # index -> (audio centre, ratio)
    for step in (1, -1):
        k = seed + step
        while 0 <= k < len(starts):
            c0, r0 = fits[k - step]
            pred = c0 + step * hop * r0
            if not (-seg * r0 / 2 < pred < ny + seg * r0 / 2):
                break                                           # this stretch is outside the recording
            got = local(starts[k], pred, r0, search_s)
            fits[k] = (got[2], got[1]) if got and got[3] >= 0.5 * top else (pred, r0)
            k += step
    ks = sorted(fits)
    tab_k = [mid(starts[k]) for k in ks]
    aud_k = [fits[k][0] for k in ks]
    # Run the first and last stretch's own tempo out to the ends of the tab.
    r_first, r_last = fits[ks[0]][1], fits[ks[-1]][1]
    tab_k = [0.0] + tab_k + [float(nx)]
    aud_k = [aud_k[0] - r_first * tab_k[1]] + aud_k + [aud_k[-1] + r_last * (nx - tab_k[-2])]
    aud_k = np.maximum.accumulate(np.asarray(aud_k) + np.arange(len(aud_k)) * 1e-6)
    return np.asarray(tab_k), aud_k


TRANSPOSE_MARGIN = 0.03


def align(notes: list, audio: np.ndarray, sr: int, tab_duration: float | None = None,
          transposes=(0,), piecewise: bool = True) -> dict:
    """Map from tab seconds to recording seconds.

    Three stages: a straight-line fit (start offset and overall tempo ratio, by chroma
    correlation), a piecewise fit that follows tempo changes between sections, then dynamic
    time warping in a band around that guide to follow drift within a phrase. Returns monotonic anchor pairs {'tab': [...], 'audio': [...]}, the line,
    and how well the chroma matched (cosine similarity on the warped path; 1 = identical).

    transposes: semitone shifts to try, for a chart written in a different tuning from the
    record (standard-tuning tab of a song played a half step down). A shift other than 0 is
    only taken when it fits clearly better (TRANSPOSE_MARGIN); it is returned as 'transpose'
    and place_tracks applies it, so placed notes carry the pitch that sounds."""
    import librosa
    if not notes:
        raise ValueError('The tab has no notes to line up.')
    end = tab_duration or max(n['time'] + n['duration'] for n in notes)
    X = _unit(tab_chroma(notes, end))
    Y = _unit(audio_chroma(audio, sr))
    if not np.any(Y > 0):
        raise ValueError('The recording has no pitched sound to line up with.')
    line, transpose = linear_fit(X, Y), 0
    for shift in transposes:
        if shift:
            other = linear_fit(np.roll(X, shift, axis=0), Y)
            if other['similarity'] > line['similarity'] + (TRANSPOSE_MARGIN if not transpose else 0):
                line, transpose = other, int(shift)
    if transpose:
        X = np.roll(X, transpose, axis=0)
    ratio, offset = line['ratio'], line['offset']
    # The tab redrawn on the recording's clock along the guide, then warped locally (±BAND s).
    n_audio = Y.shape[1]
    guide = piecewise_guide(X, Y, line) if piecewise else None
    if guide is None:
        src = (np.arange(n_audio) / FPS - offset) / ratio * FPS
    else:
        tab_k, aud_k = guide
        j = np.arange(n_audio, dtype=float)
        src = np.interp(j, aud_k, tab_k)
        src = np.where(j < aud_k[0], tab_k[0] - (aud_k[0] - j) / ratio, src)       # before/after the tab:
        src = np.where(j > aud_k[-1], tab_k[-1] + (j - aud_k[-1]) / ratio, src)    # outside, dropped below
    inside = (src >= 0) & (src < X.shape[1] - 1)
    if inside.sum() < 10:
        raise ValueError('The tab and the recording do not overlap.')
    a0, a1 = int(np.argmax(inside)), int(n_audio - np.argmax(inside[::-1]))
    Xw = X[:, np.clip(src[a0:a1].astype(int), 0, X.shape[1] - 1)]
    Ya = Y[:, a0:a1]
    C = 1 - Xw.T @ Ya
    band = min(1.0, BAND_S * FPS / max(1, Ya.shape[1]))
    D, path = librosa.sequence.dtw(C=C, global_constraints=True, band_rad=band)
    path = path[::-1]
    tab_t, audio_t = [], []
    rows = {}
    for i, j in path:
        rows.setdefault(int(i), []).append(int(j))
    for i in sorted(rows):
        tab_t.append(float(src[a0 + i]) / FPS)
        audio_t.append((a0 + float(np.median(rows[i]))) / FPS)
    audio_t = np.maximum.accumulate(np.asarray(audio_t))
    similarity = float(1 - np.mean([C[i, j] for i, j in path]))
    return {'tab': tab_t, 'audio': list(map(float, audio_t)), 'similarity': round(similarity, 3),
            'line': {k: round(v, 3) for k, v in line.items()}, 'tempo_ratio': round(ratio, 3),
            'transpose': transpose, 'piecewise': guide is not None}


BAND_S = 8.0


def refine_pass(mapping: dict, notes: list, audio: np.ndarray, sr: int, window_s: float = 6.0, step_s: float = 1.0,
                search_s: float = 1.6) -> dict:
    """Sharpen a chroma alignment to note level with pitched attacks.

    Chroma frames are ~93 ms and sparse passages drift by a second or more. For each 6 s
    stretch of tab, slide its notes within ±search_s over the recording's per-pitch onset map
    (positive change in a constant-Q spectrogram, at each note's own pitch and an octave up)
    and keep the shift where those pitches start together. Matching pitches as well as times
    stops a steady riff from snapping a whole beat out. Shifts are median-smoothed across
    stretches so one noisy window cannot tear the map."""
    import librosa
    y = audio if audio.ndim == 1 else audio.mean(axis=1 if audio.shape[0] > audio.shape[-1] else 0)
    y = np.asarray(y, dtype=np.float32)
    hop, low = 256, 28                                  # CQT from E1, one bin per semitone
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    Cq = np.abs(librosa.cqt(y, sr=SR, hop_length=hop, fmin=librosa.midi_to_hz(low), n_bins=84))
    Cq = np.log1p(20 * Cq / (Cq.max() + 1e-9))
    flux = np.maximum(0.0, np.diff(Cq, axis=1, prepend=Cq[:, :1]))
    flux = np.maximum.reduce([np.roll(flux, -1, 1), flux, np.roll(flux, 1, 1)])     # ±1 frame
    flux /= np.percentile(flux[flux > 0], 99) + 1e-9 if np.any(flux > 0) else 1.0
    fps = SR / hop
    rows = []
    for n in covered(mapping, notes):
        k = int(n['midi']) + int(mapping.get('transpose', 0)) - low
        if 0 <= k < 84:
            rows.append((float(n['time']), k))
    rows.sort()
    times = np.array([r[0] for r in rows])
    bins = np.array([r[1] for r in rows])
    up = np.minimum(bins + 12, 83)
    tab_end = float(times[-1]) if len(times) else 0.0
    shifts = np.arange(-search_s, search_s + 1e-9, 1 / fps)
    centres, deltas, strengths = [], [], []
    t = 0.0
    while t <= tab_end:
        sel = (times >= t) & (times < t + window_s)
        if sel.sum() >= 4:
            base = to_audio_time(mapping, times[sel])
            b, u = bins[sel], up[sel]
            scores = []
            for d in shifts:
                idx = np.round((base + d) * fps).astype(int)
                ok = (idx >= 0) & (idx < flux.shape[1])
                scores.append((flux[b[ok], idx[ok]] + 0.5 * flux[u[ok], idx[ok]]).mean() if ok.any() else 0.0)
            scores = np.asarray(scores) - 0.03 * np.abs(shifts)   # small pull towards no change
            k = int(np.argmax(scores))
            centres.append(t + window_s / 2)
            deltas.append(float(shifts[k]))
            strengths.append(float(scores[k]))
        t += step_s
    if not deltas:
        return dict(mapping, refined=False)
    deltas = np.asarray(deltas)
    smooth = np.array([np.median(deltas[max(0, i - 2): i + 3]) for i in range(len(deltas))])
    # The fine map runs through the refined window centres only, so small wiggles of the
    # chroma path inside a window do not survive; beyond the first/last centre it follows the
    # chroma path with the edge correction.
    tab = np.asarray(mapping['tab'])
    centres = np.asarray(centres)
    anchors = to_audio_time(mapping, centres) + smooth
    fine = np.interp(tab, centres, anchors)
    before, after = tab < centres[0], tab > centres[-1]
    fine[before] = np.asarray(mapping['audio'])[before] + smooth[0]
    fine[after] = np.asarray(mapping['audio'])[after] + smooth[-1]
    fine = np.maximum.accumulate(fine)
    return dict(mapping, audio=list(map(float, fine)), refined=True,
                attack_match=round(float(np.mean(strengths)), 3))

def to_audio_time(mapping: dict, t: float | np.ndarray):
    """Recording time for tab time(s), interpolated along the alignment."""
    return np.interp(t, mapping['tab'], mapping['audio'])


def covered(mapping: dict, notes: list, margin: float = 0.5) -> list:
    """The tab notes that fall inside the stretch of tab the recording covers. A clip or a take
    of one section lines up with only part of the chart; the rest is not in the recording."""
    lo, hi = mapping['tab'][0] - margin, mapping['tab'][-1] + margin
    return [n for n in notes if lo <= n['time'] <= hi]


def place_tracks(tracks: list, mapping: dict) -> list:
    """Each tab track's notes moved onto the recording's clock, plus the stretches (bars) where
    the track plays, for naming parts like 'Guitar Solo, 2:31-3:40'. Notes outside the stretch
    the recording covers are left out, and a chart in another tuning is moved to the pitch
    that sounds."""
    out = []
    shift = int(mapping.get('transpose', 0))
    for tr in tracks:
        notes = []
        for n in covered(mapping, tr['notes']):
            a = float(to_audio_time(mapping, n['time']))
            b = float(to_audio_time(mapping, n['time'] + n['duration']))
            notes.append(dict(n, midi=int(n['midi']) + shift, time=a, duration=max(0.03, b - a), tab_time=n['time']))
        out.append({'name': tr['name'], 'track': tr.get('track'), 'notes': notes, 'sections': sections(notes)})
    return out


def sections(notes: list, gap: float = 4.0) -> list:
    """Stretches of playing separated by at least `gap` seconds of rest."""
    if not notes:
        return []
    times = sorted((n['time'], n['time'] + n['duration'], n.get('bar')) for n in notes)
    spans = [[times[0][0], times[0][1], times[0][2], times[0][2]]]
    for a, b, bar in times[1:]:
        if a - spans[-1][1] > gap:
            spans.append([a, b, bar, bar])
        else:
            spans[-1][1] = max(spans[-1][1], b)
            spans[-1][3] = bar if bar is not None else spans[-1][3]
    return [{'start': round(a, 2), 'end': round(b, 2), 'first_bar': fb, 'last_bar': lb} for a, b, fb, lb in spans]


def assign(heard: list, tracks: list, onset: float = 0.08) -> dict:
    """Which tab track each heard note belongs to: same pitch within `onset` seconds of one of
    the track's (aligned) notes. Each tab note claims at most one heard note.

    Returns {'by_track': {name: [heard ids]}, 'unassigned': [ids], 'match': {name: {...}}} where
    match gives precision/recall/F1 of the heard notes against that track over its sections."""
    import bisect
    claimed = set()
    by_track = {t['name']: [] for t in tracks}
    owner = {}
    candidates = []
    for ti, tr in enumerate(tracks):
        for k, n in enumerate(tr['notes']):
            candidates.append((n['time'], int(n['midi']), ti, k))
    candidates.sort()
    starts = [c[0] for c in candidates]
    for h in sorted(heard, key=lambda n: n['time']):
        lo = bisect.bisect_left(starts, h['time'] - onset)
        best = None
        for c in candidates[lo:]:
            if c[0] > h['time'] + onset:
                break
            if c[1] == int(h['midi']) and (c[2], c[3]) not in claimed:
                d = abs(c[0] - h['time'])
                if best is None or d < best[0]:
                    best = (d, c)
        if best:
            _, c = best
            claimed.add((c[2], c[3]))
            owner[h['id']] = tracks[c[2]]['name']
            by_track[tracks[c[2]]['name']].append(h['id'])
    unassigned = [h['id'] for h in heard if h['id'] not in owner]
    match = {}
    for tr in tracks:
        ref = len(tr['notes'])
        hits = len(by_track[tr['name']])
        # Heard notes inside this track's sections that nobody's tab explains count against it.
        inside = sum(1 for h in heard if h['id'] not in owner and
                     any(s['start'] - onset <= h['time'] <= s['end'] + onset for s in tr['sections']))
        p = hits / max(1, hits + inside)
        r = hits / max(1, ref)
        match[tr['name']] = {'tab_notes': ref, 'heard_matched': hits, 'precision': round(p, 3),
                             'recall': round(r, 3), 'f1': round(2 * p * r / max(1e-9, p + r), 3)}
    return {'by_track': by_track, 'unassigned': unassigned, 'match': match}


def refine(mapping: dict, notes: list, audio: np.ndarray, sr: int) -> dict:
    """Coarse to fine: long windows with a wide search first (sparse intros can be a second or
    more out, and long windows are hard to fool with a repeating riff), then short windows with
    a narrow search to follow the band within a phrase."""
    first = refine_pass(mapping, notes, audio, sr, window_s=12.0, step_s=3.0, search_s=1.6)
    if not first.get('refined'):
        return first
    return refine_pass(first, notes, audio, sr, window_s=5.0, step_s=1.0, search_s=0.3)


PIECEWISE_GAIN = 0.005


def line_up(notes: list, audio: np.ndarray, sr: int, transposes=(0,)) -> dict:
    """The refined map from tab time to recording time, with or without the piecewise stage.

    Following tempo changes section by section rescues songs whose tempo shifts part-way
    through, but on short clips it can chase the wrong repeat. Both maps are made, and the
    piecewise one is kept only when the recording's pitched attacks agree with it measurably
    better (attack_match, which uses no transcription)."""
    plain = refine(align(notes, audio, sr, transposes=transposes, piecewise=False), notes, audio, sr)
    pieces = align(notes, audio, sr, transposes=(plain['transpose'],) if plain['transpose'] else (0,), piecewise=True)
    if not pieces['piecewise']:
        return plain
    pieces = refine(pieces, notes, audio, sr)
    better = (pieces.get('attack_match') or 0) > (plain.get('attack_match') or 0) + PIECEWISE_GAIN
    return pieces if better else plain
