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


def linear_fit(X: np.ndarray, Y: np.ndarray, ratios=np.arange(0.5, 2.01, 0.01), max_offset_s: float = 90.0):
    """Coarse map audio = offset + ratio * tab by chroma correlation (unit-norm frames).
    Ratios down to 0.5 and up to 2 cover a chart written at double or half the record's tempo."""
    best = (-1.0, 1.0, 0.0)
    span = int(max_offset_s * FPS)
    for ratio in ratios:
        idx = (np.arange(X.shape[1]) * ratio).astype(int)
        for off in range(-span, span + 1):
            j = idx + off
            ok = (j >= 0) & (j < Y.shape[1])
            if ok.sum() < 0.6 * len(j):
                continue
            score = float((X[:, ok] * Y[:, j[ok]]).sum() / ok.sum())
            if score > best[0]:
                best = (score, float(ratio), off / FPS)
    return {'similarity': best[0], 'ratio': best[1], 'offset': best[2]}


def align(notes: list, audio: np.ndarray, sr: int, tab_duration: float | None = None) -> dict:
    """Map from tab seconds to recording seconds.

    Two stages: a straight-line fit (start offset and overall tempo ratio, by chroma
    correlation), then dynamic time warping in a band around that line to follow tempo drift
    and changes. Returns monotonic anchor pairs {'tab': [...], 'audio': [...]}, the line,
    and how well the chroma matched (cosine similarity on the warped path; 1 = identical)."""
    import librosa
    if not notes:
        raise ValueError('The tab has no notes to line up.')
    end = tab_duration or max(n['time'] + n['duration'] for n in notes)
    X = _unit(tab_chroma(notes, end))
    Y = _unit(audio_chroma(audio, sr))
    if not np.any(Y > 0):
        raise ValueError('The recording has no pitched sound to line up with.')
    line = linear_fit(X, Y)
    ratio, offset = line['ratio'], line['offset']
    # The tab redrawn on the recording's clock along the line, then warped locally (±BAND s).
    n_audio = Y.shape[1]
    src = (np.arange(n_audio) / FPS - offset) / ratio * FPS
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
            'line': {k: round(v, 3) for k, v in line.items()}, 'tempo_ratio': round(ratio, 3)}


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
    for n in notes:
        k = int(n['midi']) - low
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


def place_tracks(tracks: list, mapping: dict) -> list:
    """Each tab track's notes moved onto the recording's clock, plus the stretches (bars) where
    the track plays, for naming parts like 'Guitar Solo, 2:31-3:40'."""
    out = []
    for tr in tracks:
        notes = []
        for n in tr['notes']:
            a = float(to_audio_time(mapping, n['time']))
            b = float(to_audio_time(mapping, n['time'] + n['duration']))
            notes.append(dict(n, time=a, duration=max(0.03, b - a), tab_time=n['time']))
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
