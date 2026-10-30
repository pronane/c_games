"""VIDEO -> sprite moves.

Turns the user's OWN clip(s) of a move (walk, run, jump, punch ...) into clean,
aligned RGBA frames in the studio's per-move layout, then hands them to the
normal FRAMES build (atlas, profiles, console presets).

Pipeline per clip (all CPU):
  1. decode            ffmpeg (native) -> numpy frames, optional trim / slow-mo
  2. camera motion     phase correlation: static / hand-held (one shift per
                       frame) / tracking pan (one shift per horizontal band,
                       which models parallax: far rows move slowly, ground fast)
  3. background        temporal median of the aligned frames (a mosaic for a
                       tracking pan), or a clean plate, or chroma key, or rembg
  4. matte             colour difference + shadow suppression + morphology +
                       largest-blob keep + soft edge, green-spill removal
  5. analyse           per-frame silhouette descriptor, sharpness, motion energy
  6. select            cyclic moves: loop period from frame self-similarity
                       (full stride = two steps); one-shot moves: action span
                       from motion energy; frames spaced by time / motion,
                       sharpest candidate preferred; slow-motion in-betweens by
                       optical flow when the clip has too few frames
  7. normalise         one standing height for all clips, common ground line,
                       in-place root (loops) or kept root offset (one-shots)

Nothing here creates a likeness: it only cuts the user's own pixels out of the
user's own footage.  Honest limits are in README / help topic 'video'."""
from __future__ import annotations
import json, math, os, shutil, subprocess, time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

try:
    import cv2  # optional: faster + optical-flow in-betweens
    cv2.setNumThreads(max(1, (os.cpu_count() or 2)))
except Exception:  # pragma: no cover
    cv2 = None
try:
    from scipy import ndimage as ndi
except Exception:  # pragma: no cover
    ndi = None

LOCO = ("walk", "run", "sprint", "jog", "fight_walk", "sneak", "carry", "dribble", "swim", "fly")


# ------------------------------------------------------------------ decode
def probe(path):
    from . import media
    return media.probe(path)


def decode(path, max_h=720, start=None, end=None, slowmo=1.0, log=print):
    """-> frames (N,H,W,3) uint8, fps.  Heavy lifting = ffmpeg (C)."""
    info = probe(path)
    h = min(max_h, info["h"]) if max_h else info["h"]
    h -= h % 2
    w = int(round(info["w"] * h / info["h"])); w -= w % 2
    vf = ["scale=%d:%d" % (w, h)]
    fps = info["fps"]
    if slowmo and slowmo > 1.0:
        vf.append("minterpolate=fps=%g:mi_mode=mci:mc_mode=aobmc:me_mode=bidir" % (fps * slowmo))
        fps = fps * slowmo
    from . import media
    if slowmo and slowmo > 1.0 and not media.can_interpolate():
        log("  slow-mo needs ffmpeg (pip install imageio-ffmpeg) - decoding at normal speed")
        vf = vf[:1]; fps = info["fps"]; slowmo = 1.0
    t0 = time.time()
    fr = media.read_frames(path, w, h, start, end, vf[1:])
    n = len(fr)
    dt = time.time() - t0
    log("  decode %s: %d frames %dx%d @ %.1f fps in %.2fs (%.0f frames/s)%s" % (
        os.path.basename(path), n, w, h, fps, dt, n / max(dt, 1e-6), "  [slow-mo x%g via ffmpeg minterpolate]" % slowmo if slowmo > 1 else ""))
    return fr, fps, dict(decode_s=dt, decode_fps=n / max(dt, 1e-6), w=w, h=h, n=n, src=info)


# ------------------------------------------------------------------ helpers
def _gray(f):
    return (f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114).astype(np.float32)


_WIN = {}


def _phase(a, b, second=False):
    """shift (dx, dy) of b relative to a + peak confidence.  Own implementation:
    integer peak + 3-point parabolic sub-pixel fit (a tight fit does not get
    pulled towards a second layer moving at a different speed, unlike a
    centroid over a 5x5 window)."""
    h, w = a.shape
    win = _WIN.get((h, w))
    if win is None:
        win = _WIN[(h, w)] = (np.hanning(h)[:, None] * np.hanning(w)[None, :]).astype(np.float32)
    A = np.fft.rfft2(a * win); B = np.fft.rfft2(b * win)
    R = B * np.conj(A); R /= np.abs(R) + 1e-6
    r = np.fft.irfft2(R, s=(h, w))
    iy, ix = np.unravel_index(int(np.argmax(r)), r.shape)
    peak = float(r[iy, ix])

    def sub(c, l, rr):
        den = l - 2 * c + rr
        return 0.5 * (l - rr) / den if abs(den) > 1e-9 else 0.0
    fx = sub(peak, r[iy, (ix - 1) % w], r[iy, (ix + 1) % w])
    fy = sub(peak, r[(iy - 1) % h, ix], r[(iy + 1) % h, ix]) if h > 2 else 0.0
    dy = iy if iy <= h // 2 else iy - h
    dx = ix if ix <= w // 2 else ix - w
    res = (float(dx + max(-0.5, min(0.5, fx))), float(dy + max(-0.5, min(0.5, fy))), peak)
    if not second:
        return res
    # second motion layer: best peak in the x-correlation profile at least 2.5 px away from the first
    prof = r.max(axis=0)
    xs = np.arange(w); xs = np.where(xs <= w // 2, xs, xs - w)
    far = np.abs(xs - dx) >= 2.5
    if not far.any():
        return res + (None,)
    k = int(np.argmax(np.where(far, prof, -1)))
    if prof[k] < 0.3 * peak or prof[k] < 0.05:
        return res + (None,)
    fx2 = sub(prof[k], prof[(k - 1) % w], prof[(k + 1) % w])
    return res + ((float(xs[k] + max(-0.5, min(0.5, fx2))), float(prof[k])),)


def _xprofile(a, b, maxs):
    """phase-correlation profile over x shifts -maxs..maxs (max over small dy)."""
    h, w = a.shape
    win = _WIN.get((h, w))
    if win is None:
        win = _WIN[(h, w)] = (np.hanning(h)[:, None] * np.hanning(w)[None, :]).astype(np.float32)
    A = np.fft.rfft2(a * win); B = np.fft.rfft2(b * win)
    R = B * np.conj(A); R /= np.abs(R) + 1e-6
    r = np.fft.irfft2(R, s=(h, w))
    rows = np.concatenate([r[:3], r[-3:]]) if h > 6 else r
    prof = rows.max(axis=0)
    idx = np.arange(-maxs, maxs + 1) % w
    return prof[idx]


def _phase_x_excluding(a, b, x0, x1, second=True, maxs=48):
    """x shift of the background of b vs a, ignoring columns x0..x1 (the subject).
    Left and right segments are correlated separately and their profiles summed."""
    h, w = a.shape
    segs = [(0, int(x0)), (int(x1), w)] if x1 > x0 else [(0, w)]
    prof = None; n = 0
    for s0, s1 in segs:
        if s1 - s0 < 2 * maxs + 8 and s1 - s0 < 96:
            continue
        m = min(maxs, (s1 - s0) // 2 - 2)
        p = _xprofile(a[:, s0:s1], b[:, s0:s1], m)
        if m < maxs:
            p = np.pad(p, (maxs - m, maxs - m))
        prof = p if prof is None else prof + p; n += 1
    if prof is None:
        return None
    prof = prof / n
    k = int(np.argmax(prof)); pk = float(prof[k])

    def sub(i):
        if 0 < i < len(prof) - 1:
            l, c, r = prof[i - 1], prof[i], prof[i + 1]
            den = l - 2 * c + r
            return max(-0.5, min(0.5, 0.5 * (l - r) / den)) if abs(den) > 1e-9 else 0.0
        return 0.0
    dx = k - maxs + sub(k)
    sec = None
    if second:
        far = np.abs(np.arange(len(prof)) - k) >= 3
        k2 = int(np.argmax(np.where(far, prof, -1)))
        if prof[k2] >= 0.25 * pk and prof[k2] > 0.04:
            sec = (k2 - maxs + sub(k2), float(prof[k2]))
    return dx, pk, sec


def _shift(img, dx, dy, border=None):
    """translate an image by (dx, dy) px (sub-pixel)."""
    if cv2 is not None:
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        bm = cv2.BORDER_REPLICATE if border is None else cv2.BORDER_CONSTANT
        return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderMode=bm,
                              borderValue=0 if border is None else border)
    ix, iy = int(round(dx)), int(round(dy))
    return np.roll(np.roll(img, iy, axis=0), ix, axis=1)


def _open_close(m, o=3, c=7):
    if cv2 is not None:
        k1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (o, o)); k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (c, c))
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k1)
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, k2) > 0
    im = Image.fromarray((m * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(o)).filter(ImageFilter.MaxFilter(o))
    im = im.filter(ImageFilter.MaxFilter(c)).filter(ImageFilter.MinFilter(c))
    return np.asarray(im) > 127


def _components(m):
    if cv2 is not None:
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        return lab, [(i, st[i, 4], (st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3])) for i in range(1, n)]
    if ndi is None:
        ys, xs = np.nonzero(m)
        if not len(xs):
            return m.astype(int), []
        return m.astype(int), [(1, len(xs), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))]
    lab, n = ndi.label(m)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        area = int((lab[sl] == i).sum())
        out.append((i, area, (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)))
    return lab, out


def _fill_holes(m):
    if cv2 is not None:
        h, w = m.shape
        inv = np.ones((h + 2, w + 2), np.uint8); inv[1:-1, 1:-1] = (~m).astype(np.uint8)
        mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(inv, mask, (0, 0), 2)
        return m | (inv[1:-1, 1:-1] == 1)
    if ndi is not None:
        return ndi.binary_fill_holes(m)
    return m


def _keep_subject(m, prior=None):
    """largest blob (closest to the prior box) + nearby big pieces (separated limbs)."""
    lab, comps = _components(m)
    if not comps:
        return m, None
    def score(c):
        i, a, bb = c
        if prior is None:
            return a
        cx = (bb[0] + bb[2]) / 2; pcx = (prior[0] + prior[2]) / 2; pw = max(8, prior[2] - prior[0])
        return a / (1 + (abs(cx - pcx) / (1.5 * pw)) ** 2)
    main = max(comps, key=score)
    bx0, by0, bx1, by1 = main[2]
    mw, mh = bx1 - bx0, by1 - by0
    keep = [main[0]]
    for i, a, bb in comps:
        if i == main[0] or a < max(30, 0.05 * main[1]):
            continue
        if bb[2] > bx0 - 0.2 * mw and bb[0] < bx1 + 0.2 * mw and bb[3] > by0 - 0.15 * mh and bb[1] < by1 + 0.5 * mh:
            keep.append(i)
    out = np.isin(lab, keep)
    ys, xs = np.nonzero(out)
    return out, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _blur(a, r):
    if cv2 is not None:
        k = int(r * 3) | 1
        return cv2.GaussianBlur(a, (k, k), r)
    return np.asarray(Image.fromarray(a).filter(ImageFilter.GaussianBlur(r))) if a.dtype == np.uint8 else \
        np.asarray(Image.fromarray(a, "F").filter(ImageFilter.GaussianBlur(r)))


def _sharpness(gray, mask):
    if cv2 is not None:
        lap = cv2.Laplacian(gray, cv2.CV_32F)
    else:
        lap = (np.roll(gray, 1, 0) + np.roll(gray, -1, 0) + np.roll(gray, 1, 1) + np.roll(gray, -1, 1) - 4 * gray)
    sel = lap[mask] if mask.any() else lap.ravel()
    return float(sel.var())


# ------------------------------------------------------------------ camera
def camera_motion(frames, mode="auto", bands=24, log=print, exclude=None):
    """-> (mode, offsets) offsets: (N, bands, 2) cumulative shift of each band
    relative to frame 0 (x, y), in pixels."""
    N, H, W = frames.shape[:3]
    sc = 0.5 if W > 960 else 1.0
    g = [_gray(f) for f in frames]
    if sc != 1.0:
        g = [np.asarray(Image.fromarray(x).resize((int(W * sc), int(H * sc)), Image.BILINEAR)) for x in g]
    if mode == "static":
        return "static", np.zeros((N, bands, 2), np.float32), {}
    # one global estimate per frame pair
    glob = np.zeros((N, 2), np.float32); conf = np.zeros(N, np.float32)
    for i in range(1, N):
        dx, dy, r = _phase(g[i - 1], g[i]); glob[i] = (dx / sc, dy / sc); conf[i] = r
    cum = np.cumsum(glob, axis=0)
    step = np.median(np.abs(glob[1:, 0])) if N > 1 else 0
    span = float(np.ptp(cum[:, 0])) if N > 1 else 0
    direct = np.zeros((N, 2), np.float32); dconf = np.ones(N, np.float32)
    for i in range(1, N):
        dx, dy, r = _phase(g[0], g[i]); direct[i] = (dx / sc, dy / sc); dconf[i] = r
    dmax = float(np.abs(direct).max()) if N > 1 else 0.0
    if mode == "auto":
        if dmax < 1.0:
            mode = "static"
        elif step >= 1.5 or np.median(dconf[1:]) < 0.05:
            mode = "tracking"
        else:
            mode = "handheld"
    info = dict(global_step_px=float(step), global_span_px=span, max_offset_vs_first_px=dmax)
    if mode == "static":
        return mode, np.zeros((N, bands, 2), np.float32), info
    if mode == "handheld":
        # re-estimate against frame 0 (no drift accumulation) when the shake is small
        off = direct.copy()
        bad = dconf < 0.05
        off[bad] = cum[bad]
        return mode, np.repeat(off[:, None, :], bands, axis=1), info
    # tracking: per band x-shift (parallax), global y
    gh = g[0].shape[0]; edges = np.linspace(0, gh, bands + 1).astype(int)
    bx = np.zeros((N, bands), np.float32); bc = np.zeros((N, bands), np.float32)
    bx2 = np.full((N, bands), np.nan, np.float32)
    for i in range(1, N):
        for b in range(bands):
            y0, y1 = edges[b], edges[b + 1]
            pad = max(0, (8 - (y1 - y0)) // 2)
            y0, y1 = max(0, y0 - pad - 2), min(gh, y1 + pad + 2)
            if exclude is not None:
                ex0 = min(exclude[i - 1][0], exclude[i][0]) * sc; ex1 = max(exclude[i - 1][1], exclude[i][1]) * sc
                res = _phase_x_excluding(g[i - 1][y0:y1], g[i][y0:y1], ex0, ex1)
                if res is None:
                    dx, r, sec = _phase(g[i - 1][y0:y1], g[i][y0:y1])[0], 0.0, None
                else:
                    dx, r, sec = res
            else:
                dx, dy, r, sec = _phase(g[i - 1][y0:y1], g[i][y0:y1], second=True)
            bx[i, b] = dx / sc; bc[i, b] = r
            if sec is not None and exclude is not None:
                bx2[i, b] = sec[0] / sc
    # textureless bands (clear sky, plain walls): their x-shift is unobservable and the subject
    # would dominate the estimate (-> background model containing the subject).  Any shift is
    # consistent with a flat band, so give them the FASTEST measured pan: that moves the
    # subject furthest through the band's mosaic and lets the median drop it.
    tex = np.zeros(bands, np.float32)
    for b in range(bands):
        y0, y1 = edges[b], edges[b + 1]
        vals = []
        for i in np.linspace(0, N - 1, min(N, 12)).round().astype(int):
            row = g[i][y0:y1]
            gx = np.abs(np.diff(row, axis=1))
            if exclude is not None:
                c0, c1 = int(exclude[i][0] * sc), int(exclude[i][1] * sc)
                rest = np.concatenate([gx[:, :max(0, c0 - 1)], gx[:, c1:]], axis=1)
                if rest.shape[1] >= 0.2 * gx.shape[1]:
                    gx = rest
                else:
                    continue
            if gx.size:
                vals.append(float(np.percentile(gx, 99)))
        tex[b] = np.median(vals) if vals else 0
    flat = tex < 6.0
    if flat.any() and (~flat).any():
        fastest = int(np.argmax(np.where(flat, -1, np.abs(np.median(bx[1:], axis=0)))))
        bx[:, flat] = bx[:, fastest:fastest + 1]
        bc[:, flat] = 1.0
    # low-confidence bands -> interpolate from confident neighbours
    for i in range(1, N):
        ok = bc[i] > 0.08
        if ok.sum() >= 2 and (~ok).any():
            bx[i, ~ok] = np.interp(np.nonzero(~ok)[0], np.nonzero(ok)[0], bx[i, ok])
        elif ok.sum() < 2:
            bx[i, :] = glob[i, 0]
    # temporal smoothing of the per-band velocity (a pan is smooth)
    k = np.ones(3) / 3
    for b in range(bands):
        v = bx[1:, b]
        if len(v) >= 3:
            bx[1:, b] = np.convolve(np.pad(v, 1, mode="edge"), k, mode="valid")
    off = np.zeros((N, bands, 2), np.float32)
    off[:, :, 0] = np.cumsum(bx, axis=0)
    off[:, :, 1] = cum[:, 1:2]
    info["band_speed_px"] = [float(np.median(bx[1:, b])) for b in range(bands)]
    info["flat_bands"] = int(flat.sum())
    # parallax: a band that mixes two depths (hills behind houses) shows a 2nd stable peak -> 2nd layer
    v2 = np.zeros(bands, np.float32); has2 = np.zeros(bands, bool)
    for b in range(bands):
        col = bx2[1:, b]; ok = ~np.isnan(col)
        if ok.mean() > 0.4:
            v = float(np.median(col[ok]))
            if abs(v - np.median(bx[1:, b])) >= 2.0 and np.std(col[ok]) < 1.5:
                v2[b] = v; has2[b] = True
    if has2.any():
        off2 = off.copy()
        for b in np.nonzero(has2)[0]:
            off2[:, b, 0] = np.arange(N) * v2[b]
        info["offsets2"] = off2
        info["layer2_bands"] = [int(b) for b in np.nonzero(has2)[0]]
        info["layer2_speed_px"] = [float(v2[b]) for b in np.nonzero(has2)[0]]
    return mode, off, info


def subject_columns(frames, offsets, cinfo, pad_frac=0.12):
    """rough per-frame x-range of a tracked subject, from the fastest (= nearest, ground) bands,
    where a single-layer background model is accurate."""
    N, H, W = frames.shape[:3]
    sp = np.abs(np.array(cinfo.get("band_speed_px", [0])))
    if sp.max() < 1.0:
        return None
    bands = offsets.shape[1]; e = _band_edges(H, bands)
    fast = [b for b in range(bands) if sp[b] >= 0.7 * sp.max()]
    y0, y1 = e[min(fast)], e[max(fast) + 1]
    sub = frames[:, y0:y1]
    o = offsets[:, min(fast):max(fast) + 1]
    bf, _ = background_mosaic(sub, o, "tracking", max_frames=40)
    out = np.zeros((N, 2), np.float32); pad = pad_frac * W
    for i in range(N):
        d = np.abs(sub[i].astype(np.int16) - bf(i).astype(np.int16)).max(axis=2) > 40
        cols = np.convolve(d.sum(axis=0), np.ones(9), mode="same") >= max(6, 0.6 * d.shape[0])
        xs = np.nonzero(cols)[0]
        if not len(xs):
            out[i] = (W / 2 - pad, W / 2 + pad); continue
        # largest run
        runs = np.split(xs, np.nonzero(np.diff(xs) > 12)[0] + 1)
        r = max(runs, key=len)
        out[i] = (max(0, r[0] - pad), min(W, r[-1] + pad))
    return out


def _band_edges(H, bands):
    return np.linspace(0, H, bands + 1).astype(int)


def align(frame, off_b, H, inverse=True):
    """warp a frame so band b moves by -off_b (into frame-0 coordinates)."""
    bands = off_b.shape[0]
    if np.allclose(off_b, off_b[0]):
        dx, dy = off_b[0]
        return _shift(frame, -dx, -dy) if inverse else _shift(frame, dx, dy)
    out = np.empty_like(frame); e = _band_edges(H, bands)
    for b in range(bands):
        dx, dy = off_b[b]
        s = _shift(frame, -dx if inverse else dx, -dy if inverse else dy)
        out[e[b]:e[b + 1]] = s[e[b]:e[b + 1]]
    return out


# ------------------------------------------------------------------ background
def _med_iqr(acc):
    """acc (K,h,w,3) float32 with NaN = not seen -> median (h,w,3) uint8, spread (h,w) uint8.
    spread = inter-quartile range: high where the background itself changes / is misaligned."""
    srt = np.sort(acc, axis=0)                        # NaN sorts last
    n = (~np.isnan(acc[..., 0])).sum(axis=0)          # (h,w)
    def q(f):
        k = np.clip(np.round(f * (n - 1)).astype(int), 0, acc.shape[0] - 1)
        return np.take_along_axis(srt, k[None, ..., None].repeat(3, axis=-1), axis=0)[0]
    med = np.nan_to_num(q(0.5)); iqr = np.nan_to_num(q(0.75) - q(0.25)).max(axis=-1)
    iqr[n < 3] = 255
    return np.clip(med, 0, 255).astype(np.uint8), np.clip(iqr, 0, 255).astype(np.uint8)


def background_mosaic(frames, offsets, mode, max_frames=60, log=print, masks=None):
    """temporal median in background coordinates.  Returns a function
    bg_for(i) -> background image in frame i's coordinates."""
    N, H, W = frames.shape[:3]
    idx = np.linspace(0, N - 1, min(N, max_frames)).round().astype(int)
    if mode in ("static", "handheld"):
        if masks is not None:
            st = []
            for i in idx:
                a = align(frames[i], offsets[i], H).astype(np.float32)
                if masks[i] is not None:
                    a[align(masks[i].astype(np.uint8), offsets[i], H) > 0] = np.nan
                st.append(a)
            bg, sp = _med_iqr(np.stack(st))
        else:
            stack = np.stack([align(frames[i], offsets[i], H) for i in idx])
            bg = np.median(stack, axis=0).astype(np.uint8)
            q = np.percentile(stack[::2], (25, 75), axis=0)
            sp = np.clip((q[1] - q[0]).max(axis=-1), 0, 255).astype(np.uint8)
        if mode == "static":
            f = lambda i: bg
            f.spread = lambda i: sp
        else:
            f = lambda i: align(bg, offsets[i], H, inverse=False)
            f.spread = lambda i: align(sp, offsets[i], H, inverse=False)
        return f, bg
    bands = offsets.shape[1]; e = _band_edges(H, bands)
    wx = -offsets[:, :, 0]                      # world x of frame column 0 = -offset
    minx = wx.min(axis=0); maxx = wx.max(axis=0)
    pad = int(math.ceil(max(maxx - minx))) + 4
    MW = W + pad
    mosaic = np.zeros((H, MW, 3), np.uint8); spread = np.zeros((H, MW), np.uint8)
    unseen = np.zeros((H, MW), bool)
    for b in range(bands):
        y0, y1 = e[b], e[b + 1]
        acc = np.full((len(idx), y1 - y0, MW, 3), np.nan, np.float32)
        for k, i in enumerate(idx):
            ox = wx[i, b] - minx[b]
            ix = int(math.floor(ox)); fx = ox - ix
            strip = frames[i, y0:y1].astype(np.float32)
            if masks is not None and masks[i] is not None:
                strip[masks[i][y0:y1]] = np.nan
            if fx > 1e-3:
                strip = strip[:, :-1] * (1 - fx) + strip[:, 1:] * fx
                acc[k, :, ix:ix + W - 1] = strip
            else:
                acc[k, :, ix:ix + W] = strip
        mosaic[y0:y1], spread[y0:y1] = _med_iqr(acc)
        if masks is not None:
            unseen[y0:y1] = (~np.isnan(acc[..., 0])).sum(axis=0) < 3
    if masks is not None and unseen.any():
        # never-seen background (always behind the subject, e.g. a far layer moving with the camera):
        # fill it from its surroundings so the subject is compared against a plausible background
        # instead of being forgiven by an "unknown = huge spread" rule
        holes = unseen.copy()
        holes[:, :2] = False; holes[:, -2:] = False
        if cv2 is not None and holes.any():
            mosaic = cv2.inpaint(mosaic, holes.astype(np.uint8), 5, cv2.INPAINT_TELEA)
            spread[holes] = 10

    def bg_for(i):
        out = np.empty((H, W, 3), np.uint8)
        for b in range(bands):
            y0, y1 = e[b], e[b + 1]
            ox = -offsets[i, b, 0] - minx[b]
            ix = int(math.floor(ox)); fx = ox - ix
            s = mosaic[y0:y1, ix:ix + W + 1].astype(np.float32)
            if s.shape[1] < W + 1:
                s = np.pad(s, ((0, 0), (0, W + 1 - s.shape[1]), (0, 0)), mode="edge")
            out[y0:y1] = (s[:, :W] * (1 - fx) + s[:, 1:W + 1] * fx).astype(np.uint8)
        return out

    def spread_for(i):
        out = np.empty((H, W), np.uint8)
        for b in range(bands):
            y0, y1 = e[b], e[b + 1]
            ix = int(round(-offsets[i, b, 0] - minx[b]))
            sl = spread[y0:y1, ix:ix + W]
            if sl.shape[1] < W:
                sl = np.pad(sl, ((0, 0), (0, W - sl.shape[1])), mode="edge")
            out[y0:y1] = sl
        return out
    bg_for.spread = spread_for
    return bg_for, mosaic


def plate_from(path_or_frames, size, log=print):
    if isinstance(path_or_frames, np.ndarray):
        return np.median(path_or_frames, axis=0).astype(np.uint8)
    p = path_or_frames
    if os.path.splitext(p)[1].lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        im = Image.open(p).convert("RGB").resize(size, Image.BILINEAR)
        return np.asarray(im)
    fr, _, _ = decode(p, max_h=size[1], log=log)
    return np.median(fr[:: max(1, len(fr) // 30)], axis=0).astype(np.uint8)


_BG_CACHE = {}


def diff_matte(f, bg, thr=None, shadows=True, extra=(), spread=None):
    """-> foreground mask: colour distance to background + shadow suppression.
    Shadow test runs only on candidate pixels (cheap)."""
    if cv2 is not None:
        key = (id(bg), bg.shape)
        b8 = _BG_CACHE.get(key)
        if b8 is None:
            if len(_BG_CACHE) > 4:
                _BG_CACHE.clear()
            b8 = _BG_CACHE[key] = (cv2.GaussianBlur(bg, (3, 3), 1.0), bg)
        b8 = b8[0]
        a8 = cv2.GaussianBlur(f, (3, 3), 1.0)
        d8 = cv2.absdiff(a8, b8)
        d = cv2.max(cv2.max(d8[..., 0], d8[..., 1]), d8[..., 2])
        for e in extra:      # other parallax layer: a pixel is background if it matches ANY layer
            e8 = cv2.absdiff(a8, cv2.GaussianBlur(e, (3, 3), 1.0))
            d = cv2.min(d, cv2.max(cv2.max(e8[..., 0], e8[..., 1]), e8[..., 2]))
    else:
        a8 = _blur(f, 1.0); b8 = _blur(bg, 1.0)
        d = np.abs(a8.astype(np.int16) - b8.astype(np.int16)).max(axis=2).astype(np.uint8)
    if thr is None:
        sub = d[::4, ::4].astype(np.float32) / 255
        med = float(np.median(sub)); mad = float(np.median(np.abs(sub - med))) + 1e-4
        thr = min(0.22, max(0.07, med + 8 * mad))
    if spread is not None:
        # per-pixel threshold: background that flickers / is misaligned (parallax) needs a bigger difference
        lim = np.minimum(int(thr * 255) + (spread.astype(np.int16) * 3) // 2, 200)
        fg = d.astype(np.int16) > lim
    else:
        fg = d > int(thr * 255)
    if shadows:
        ys, xs = np.nonzero(fg)
        if len(xs):
            pa = a8[ys, xs].astype(np.float32) / 255; pb = b8[ys, xs].astype(np.float32) / 255
            la = pa.mean(axis=1) + 1e-3; lb = pb.mean(axis=1) + 1e-3
            ratio = la / lb
            chroma = np.abs(pa / la[:, None] - pb / lb[:, None]).max(axis=1)
            sh = (ratio > 0.35) & (ratio < 0.97) & (chroma < 0.10)
            fg[ys[sh], xs[sh]] = False
    return fg, thr


_DEBUG_RAW = None


def diff_matte_layers(f, layers, thr, shadows=True):
    """several background hypotheses (parallax depth layers): a pixel is background if it
    matches ANY of them (each with its own per-pixel spread)."""
    a8 = cv2.GaussianBlur(f, (3, 3), 1.0) if cv2 is not None else _blur(f, 1.0)
    best = None; bestbg = None
    for k, (bg, sp) in enumerate(layers):
        b8 = cv2.GaussianBlur(bg, (3, 3), 1.0) if cv2 is not None else _blur(bg, 1.0)
        d8 = np.abs(a8.astype(np.int16) - b8.astype(np.int16)).max(axis=2)
        s16 = sp.astype(np.int16)
        eff = d8 - (np.minimum(s16, 60) * 3) // 2
        if k > 0:
            # another depth layer only explains a pixel where that layer is temporally consistent
            eff[s16 > 14] = 32767
        if best is None:
            best = eff; bestbg = b8.copy()
        else:
            m = eff < best
            best = np.where(m, eff, best); bestbg[m] = b8[m]
    fg = best > int(thr * 255)
    if shadows:
        ys, xs = np.nonzero(fg)
        if len(xs):
            pa = a8[ys, xs].astype(np.float32) / 255; pb = bestbg[ys, xs].astype(np.float32) / 255
            la = pa.mean(axis=1) + 1e-3; lb = pb.mean(axis=1) + 1e-3
            chroma = np.abs(pa / la[:, None] - pb / lb[:, None]).max(axis=1)
            sh = (la / lb > 0.35) & (la / lb < 0.97) & (chroma < 0.10)
            fg[ys[sh], xs[sh]] = False
    return fg


def layer_candidates(offsets, cinfo, max_layers=3, min_speed=2.0):
    """one offset track per distinct pan speed seen across the bands (= depth layers)."""
    sp = np.array(cinfo.get("band_speed_px", []))
    if not len(sp):
        return []
    order = np.argsort(sp)
    groups = []
    for b in order:
        if groups and abs(sp[b] - sp[groups[-1][-1]]) < 1.0:
            groups[-1].append(b)
        else:
            groups.append([b])
    groups = sorted(groups, key=len, reverse=True)[:max_layers]
    out = []
    for gr in groups:
        b = gr[len(gr) // 2]
        if abs(sp[b]) < min_speed:
            continue          # ~ moves with the camera like the subject: its median would learn the subject
        out.append((float(sp[b]), np.repeat(offsets[:, b:b + 1, :], offsets.shape[1], axis=1)))
    return out


def decontaminate(f, bg, alpha):
    """edge pixels: remove the background colour that bled in (I = a*F + (1-a)*B)."""
    edge = (alpha > 0.02) & (alpha < 0.98)
    if not edge.any():
        return f
    out = f.copy()
    a = alpha[edge][:, None]
    F = (f[edge].astype(np.float32) - (1 - a) * bg[edge].astype(np.float32)) / np.maximum(a, 0.15)
    out[edge] = np.clip(F, 0, 255).astype(np.uint8)
    return out


def chroma_matte(f, key=None):
    """green/blue screen: distance in CbCr from the key colour (auto = border median)."""
    x = f.astype(np.float32)
    Y = 0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2]
    cb = 128 - 0.168736 * x[..., 0] - 0.331264 * x[..., 1] + 0.5 * x[..., 2]
    cr = 128 + 0.5 * x[..., 0] - 0.418688 * x[..., 1] - 0.081312 * x[..., 2]
    if key is None:
        bd = np.concatenate([f[:6].reshape(-1, 3), f[-6:].reshape(-1, 3), f[:, :6].reshape(-1, 3), f[:, -6:].reshape(-1, 3)])
        key = np.median(bd, axis=0)
    k = np.asarray(key, np.float32)
    kcb = 128 - 0.168736 * k[0] - 0.331264 * k[1] + 0.5 * k[2]
    kcr = 128 + 0.5 * k[0] - 0.418688 * k[1] - 0.081312 * k[2]
    d = np.hypot(cb - kcb, cr - kcr)
    border = np.concatenate([d[:6].ravel(), d[-6:].ravel(), d[:, :6].ravel(), d[:, -6:].ravel()])
    t0 = float(np.percentile(border, 99.5)) * 1.25 + 4; t1 = t0 + 14
    alpha = np.clip((d - t0) / (t1 - t0), 0, 1)
    return alpha, key


def despill(rgb, alpha, key):
    k = np.asarray(key, np.float32)
    ch = int(np.argmax(k))  # 1 = green screen, 2 = blue screen
    if ch not in (1, 2):
        return rgb
    x = rgb.astype(np.float32)
    others = [c for c in range(3) if c != ch]
    lim = np.maximum(x[..., others[0]], x[..., others[1]])
    edge = alpha < 0.999
    x[..., ch] = np.where(edge | (x[..., ch] > lim * 1.15), np.minimum(x[..., ch], lim * 1.05), x[..., ch])
    return np.clip(x, 0, 255).astype(np.uint8)


_REMBG = None


def rembg_matte(f):
    global _REMBG
    from rembg import remove, new_session  # optional dependency (downloads a model on first use)
    if _REMBG is None:
        _REMBG = new_session("u2netp")
    out = remove(Image.fromarray(f), session=_REMBG)
    return np.asarray(out)[..., 3].astype(np.float32) / 255


# ------------------------------------------------------------------ analysis
def descriptor(rgba, box, size=(40, 64)):
    """in-place silhouette+shading thumbnail, anchored at feet / torso centre."""
    x0, y0, x1, y1 = box
    crop = rgba[y0:y1, x0:x1]
    h = y1 - y0
    a = crop[..., 3].astype(np.float32) / 255
    up = a[: max(1, int(h * 0.6))]
    cols = up.sum(axis=0)
    cx = (cols * np.arange(len(cols))).sum() / max(1e-6, cols.sum())
    s = size[1] / max(1, h)
    im = Image.fromarray(crop, "RGBA").resize((max(1, int(crop.shape[1] * s)), size[1]), Image.BILINEAR)
    can = Image.new("RGBA", size, (0, 0, 0, 0))
    can.paste(im, (int(round(size[0] / 2 - cx * s)), 0), im)
    arr = np.asarray(can).astype(np.float32) / 255
    g = arr[..., :3].mean(axis=2) * arr[..., 3]
    return np.concatenate([arr[..., 3].ravel(), g.ravel() * 0.7])


def dist_matrix(D):
    X = np.stack(D)
    out = np.zeros((len(X), len(X)), np.float32)
    for i in range(len(X)):
        out[i] = np.abs(X - X[i]).mean(axis=1)
    return out


def find_period(Dm, fps, loco=True, override=None):
    N = len(Dm)
    if override:
        return float(override), {"source": "user"}
    pmin = max(4, int(0.22 * fps)); pmax = min(N - 3, int(2.6 * fps))
    if pmax <= pmin:
        return None, {"error": "clip too short for loop detection (need > %.1f s)" % (2 * pmin / fps)}
    s = np.array([Dm[np.arange(N - p), np.arange(N - p) + p].mean() for p in range(pmin, pmax + 1)])
    ps = np.arange(pmin, pmax + 1)
    med = float(np.median(s))
    lo = float(s.min())
    # local minima that are clearly below the typical (unaligned) similarity
    mins = [k for k in range(1, len(s) - 1) if s[k] <= s[k - 1] and s[k] <= s[k + 1]
            and s[k] <= lo + 0.45 * (med - lo)]
    if not mins:
        mins = [int(np.argmin(s))]
    k1 = mins[0]

    def refine(k):
        if 0 < k < len(s) - 1:
            a, b, c = s[k - 1], s[k], s[k + 1]
            den = a - 2 * b + c
            return ps[k] + (0.5 * (a - c) / den if abs(den) > 1e-9 else 0.0)
        return float(ps[k])
    p1 = refine(k1)
    info = {"curve": [float(v) for v in s], "pmin": int(pmin), "step_period": p1, "score": float(s[k1] / max(med, 1e-6))}
    full = p1
    if loco:
        # a side-on walk/run silhouette repeats every STEP; a sprite loop needs the full STRIDE (left + right step)
        near = [k for k in mins if abs(ps[k] - 2 * p1) <= max(2, 0.15 * 2 * p1)]
        if near:
            full = refine(min(near, key=lambda k: s[k])); info["stride_from"] = "detected minimum at 2 x step"
        elif 2 * p1 <= N - 3:
            full = 2 * p1; info["stride_from"] = "2 x step (no clear 2nd minimum)"
        else:
            info["warning"] = "clip holds only one step; loop uses a single step (legs will not alternate)"
    info["period"] = float(full)
    return float(full), info


def action_span(E, pad=1):
    if len(E) < 3:
        return 0, len(E) - 1, {}
    e = np.convolve(np.pad(E, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    base = float(np.percentile(e, 25)); top = float(e.max())
    thr = base + 0.2 * (top - base)
    act = np.nonzero(e > thr)[0]
    if not len(act):
        return 0, len(E) - 1, {"thr": thr}
    a, b = max(0, act[0] - pad), min(len(E), act[-1] + 1 + pad)
    return int(a), int(b), {"thr": thr, "base": base, "top": top}


# ------------------------------------------------------------------ in-betweens
def interp_rgba(A, B, t):
    """A, B: aligned RGBA float/uint8 crops of equal size -> in-between at t."""
    if cv2 is None:
        return (A.astype(np.float32) * (1 - t) + B.astype(np.float32) * t).astype(np.uint8), "blend"
    ga = cv2.cvtColor(np.ascontiguousarray(A[..., :3]), cv2.COLOR_RGB2GRAY); gb = cv2.cvtColor(np.ascontiguousarray(B[..., :3]), cv2.COLOR_RGB2GRAY)
    ga = (ga.astype(np.float32) * (A[..., 3] / 255.0) + 128 * (1 - A[..., 3] / 255.0)).astype(np.uint8)
    gb = (gb.astype(np.float32) * (B[..., 3] / 255.0) + 128 * (1 - B[..., 3] / 255.0)).astype(np.uint8)
    fab = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 4, 21, 5, 7, 1.5, 0)
    fba = cv2.calcOpticalFlowFarneback(gb, ga, None, 0.5, 4, 21, 5, 7, 1.5, 0)
    t = float(t); fab = fab.astype(np.float32); fba = fba.astype(np.float32)
    h, w = ga.shape
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    wa = cv2.remap(A, (gx + t * fba[..., 0]).astype(np.float32), (gy + t * fba[..., 1]).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    wb = cv2.remap(B, (gx + (1 - t) * fab[..., 0]).astype(np.float32), (gy + (1 - t) * fab[..., 1]).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    out = wa.astype(np.float32) * (1 - t) + wb.astype(np.float32) * t
    return np.clip(out, 0, 255).astype(np.uint8), "flow"


# ------------------------------------------------------------------ main per-clip
class ClipOptions:
    def __init__(self, **k):
        self.camera = k.get("camera", "auto")        # auto static handheld tracking
        self.bg = k.get("bg", "auto")                 # auto median chroma rembg plate
        self.plate = k.get("plate", "")               # image / clip of the empty scene
        self.plate_start = float(k.get("plate_start", 0) or 0)  # first N seconds of the clip are the empty scene
        self.key = k.get("key", None)                 # chroma key colour (r,g,b) or None = auto
        self.thr = k.get("thr", None)
        self.shadows = k.get("shadows", True)
        self.max_h = int(k.get("max_h", 720))
        self.slowmo = float(k.get("slowmo", 1.0) or 1.0)   # ffmpeg minterpolate factor before analysis
        self.interp = k.get("interp", "auto")         # auto flow blend none
        self.spacing = k.get("spacing", "mix")        # time motion mix
        self.root = k.get("root", "auto")             # auto inplace keep
        self.period = k.get("period", None)           # loop period in source frames (override)
        self.flip = bool(k.get("flip", False))
        self.debug_dir = k.get("debug_dir", "")
        self.layers = bool(k.get("layers", True))     # tracking shots: multi-layer parallax background


def process_clip(path, move, n_out, loop, opts: ClipOptions, start=None, end=None, log=print):
    t_all = time.time(); tm = {}
    frames, fps, dinfo = decode(path, opts.max_h, start, end, opts.slowmo, log)
    tm["decode_s"] = dinfo["decode_s"]
    N, H, W = frames.shape[:3]
    if N < 3:
        raise ValueError("%s: only %d frames decoded" % (path, N))
    if opts.flip:
        frames = frames[:, :, ::-1].copy()
    plate_n = int(round(opts.plate_start * fps)) if opts.plate_start else 0
    # ---- chroma screen?  (decided first: a keyed shot needs no camera model at all)
    is_key = False
    if opts.bg == "auto" and not (opts.plate or plate_n):
        sel = np.linspace(0, N - 1, min(N, 6)).round().astype(int)
        bd = np.concatenate([np.concatenate([frames[i, :6].reshape(-1, 3), frames[i, :, :6].reshape(-1, 3),
                                             frames[i, :, -6:].reshape(-1, 3)]) for i in sel]).astype(np.float32)
        r, g, b = bd[:, 0], bd[:, 1], bd[:, 2]
        green = (g > 1.3 * np.maximum(r, b)) & (g > 60)
        blue = (b > 1.3 * np.maximum(r, g)) & (b > 60)
        frac = max(green.mean(), blue.mean())
        is_key = frac > 0.85
        if is_key:
            log("  chroma screen detected (%.0f%% of the border is %s)" % (100 * frac, "green" if green.mean() > blue.mean() else "blue"))
    # ---- camera
    t0 = time.time()
    if is_key or opts.bg == "chroma":
        cam, offsets, cinfo = "static", np.zeros((N, 1, 2), np.float32), {"note": "chroma key: camera motion irrelevant"}
    else:
        cam, offsets, cinfo = camera_motion(frames, opts.camera, log=log)
    if cam == "tracking" and opts.bg in ("auto", "median"):
        # pass 2: locate the subject's columns from the (reliable, fast) ground rows, then re-measure
        # every band WITHOUT the subject -> unbiased pan per depth band
        ex = subject_columns(frames, offsets, cinfo)
        if ex is not None:
            cam, offsets, cinfo = camera_motion(frames, "tracking", log=log, exclude=ex)
    tm["camera_s"] = time.time() - t0
    log("  camera: %s %s" % (cam, ("(pan %.1f px/frame)" % cinfo.get("global_step_px", 0)) if cam == "tracking" else ""))
    # ---- background model
    t0 = time.time()
    bgmode = opts.bg
    if bgmode == "auto":
        if opts.plate or plate_n:
            bgmode = "plate"
        else:
            bgmode = "chroma" if is_key else "median"
    log("  background: %s" % bgmode)
    bg_for, bg_img = None, None
    bg_for2 = None; spread_for = None
    if bgmode == "median":
        bg_for, bg_img = background_mosaic(frames[plate_n:], offsets[plate_n:] - offsets[plate_n], cam, log=log)
        _bf = bg_for
        spread_for = (lambda i, _bf=_bf: _bf.spread(i - plate_n))
        bg_for = (lambda i, _bf=_bf: _bf(i - plate_n))
    elif bgmode == "plate":
        if plate_n:
            plate = np.median(np.stack([align(frames[i], offsets[i], H) for i in range(plate_n)]), axis=0).astype(np.uint8)
        else:
            plate = plate_from(opts.plate, (W, H), log)
        bg_img = plate
        bg_for = (lambda i: plate if cam == "static" else align(plate, offsets[i], H, inverse=False))
    tm["background_s"] = time.time() - t0
    # ---- mattes
    t0 = time.time()
    rgba, boxes, prior = [None] * N, [None] * N, None
    thr_used = None
    rng = range(plate_n, N)
    for i in rng:
        f = frames[i]
        if bgmode in ("median", "plate"):
            bgi = bg_for(i)
            fg, thr_used = diff_matte(f, bgi, opts.thr if opts.thr is not None else thr_used, opts.shadows,
                                      (bg_for2(i),) if bg_for2 is not None else (),
                                      spread_for(i) if spread_for is not None else None)
            fg = _fill_holes(_open_close(fg))
            fg, box = _keep_subject(fg, prior)
            alpha = _blur((fg * 255).astype(np.uint8), 0.8).astype(np.float32) / 255
            rgb = decontaminate(f, bgi, alpha)
        elif bgmode == "chroma":
            alpha, key = chroma_matte(f, opts.key)
            hard, box = _keep_subject(_fill_holes(_open_close(alpha > 0.5, 3, 5)), prior)
            alpha = alpha * _blur((hard * 255).astype(np.uint8), 1.0).astype(np.float32) / 255
            rgb = despill(f, alpha, key)
        elif bgmode == "rembg":
            alpha = rembg_matte(f)
            hard, box = _keep_subject(alpha > 0.5, prior)
            alpha = alpha * hard
            rgb = f
        else:
            raise ValueError("unknown background mode " + bgmode)
        if box is None:
            continue
        prior = box
        a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
        im = np.dstack([rgb, a8])
        if cam == "handheld":       # stabilise the output, too
            im = align(im, offsets[i], H)
            ys, xs = np.nonzero(im[..., 3] > 127)
            if not len(xs):
                continue
            box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        rgba[i] = im; boxes[i] = box
    if cam == "tracking" and bgmode == "median" and opts.layers:
        # pass B: rebuild the background WITHOUT the subject (pass-A masks, dilated) for the band's own
        # pan AND for every other depth layer's pan, then matte against all of them
        msk = [None] * N
        for i in range(N):
            if rgba[i] is not None:
                m = rgba[i][..., 3] > 20
                msk[i] = (cv2.dilate(m.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0) if cv2 is not None else m
                # in bands that pan slower than 2 px/frame the subject hardly moves against the background:
                # hide its whole (padded) column range there, the hidden part gets inpainted
                bsp = np.array(cinfo.get("band_speed_px", []))
                if len(bsp) and boxes[i] is not None:
                    e = _band_edges(H, len(bsp)); x0, y0b, x1, y1b = boxes[i]
                    pw = int(0.25 * (x1 - x0)) + 6
                    for b in np.nonzero(np.abs(bsp) < 2.0)[0]:
                        msk[i][e[b]:e[b + 1], max(0, int(x0) - pw):int(x1) + pw] = True
        sub = msk[plate_n:]
        base = offsets[plate_n:] - offsets[plate_n]
        tracks = [("own", base)] + [("%.1f" % v, o[plate_n:] - o[plate_n]) for v, o in layer_candidates(offsets, cinfo)]
        layers = [background_mosaic(frames[plate_n:], o, cam, masks=sub) for _, o in tracks]
        log("  parallax layers: own band pan + %s px/frame (subject masked out of the background)" % ", ".join(n for n, _ in tracks[1:]))
        prior = None
        for i in rng:
            f = frames[i]
            fg = diff_matte_layers(f, [(bf(i - plate_n), bf.spread(i - plate_n)) for bf, _ in layers], thr_used, opts.shadows)
            if _DEBUG_RAW is not None:
                _DEBUG_RAW[i] = fg.copy()
            fg = _open_close(fg, 3, 11)
            if cv2 is not None:   # bridge the seams between depth bands (thin horizontal gaps)
                fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 3), np.uint8)) > 0
            fg = _fill_holes(fg)
            fg, box = _keep_subject(fg, prior)
            if box is None:
                rgba[i] = None; boxes[i] = None; continue
            prior = box
            alpha = _blur((fg * 255).astype(np.uint8), 0.8).astype(np.float32) / 255
            rgb = decontaminate(f, layers[0][0](i - plate_n), alpha)
            rgba[i] = np.dstack([rgb, (alpha * 255).astype(np.uint8)]); boxes[i] = box
        bg_img = layers[0][1]
    tm["matte_s"] = time.time() - t0
    valid = [i for i in range(N) if rgba[i] is not None and (boxes[i][3] - boxes[i][1]) > 0.08 * H]
    if len(valid) < 3:
        raise ValueError("%s: could not separate the subject from the background (try --bg chroma / --plate / --bg rembg)" % path)
    tm["matte_fps"] = len(valid) / max(tm["matte_s"], 1e-6)
    # subject must move against the background for a median plate
    warn = []
    if bgmode == "median":
        cxs = np.array([(boxes[i][0] + boxes[i][2]) / 2 - (offsets[i, len(offsets[i]) // 2, 0] if cam == "tracking" else 0) for i in valid])
        ws = np.median([boxes[i][2] - boxes[i][0] for i in valid])
        if np.ptp(cxs) < 1.2 * ws:
            warn.append("subject barely moves against the background (%.0f px vs %.0f px wide): the median background "
                        "may contain the subject. Film 1-2 s of the empty scene first (--plate-start 1) or use --plate / "
                        "--bg chroma / --bg rembg" % (np.ptp(cxs), ws))
    # ---- analysis
    t0 = time.time()
    desc = {i: descriptor(rgba[i], boxes[i]) for i in valid}
    sharp = {}
    for i in valid:
        x0, y0, x1, y1 = boxes[i]
        sharp[i] = _sharpness(_gray(rgba[i][y0:y1, x0:x1, :3]), rgba[i][y0:y1, x0:x1, 3] > 200)
    # treat the valid frames as a contiguous sequence (drop gaps)
    seq = valid
    Dm = dist_matrix([desc[i] for i in seq])
    E = np.array([Dm[k, k + 1] for k in range(len(seq) - 1)] + [0.0])
    tm["analyse_s"] = time.time() - t0
    sv = np.array([sharp[i] for i in seq]); sn = (sv - sv.min()) / max(1e-6, np.ptp(sv))
    sel_info = {}
    is_loco = any(k in move for k in LOCO)
    if loop:
        P, pinf = find_period(Dm, fps, is_loco, opts.period)
        sel_info.update(pinf)
        if P is None:
            raise ValueError("%s: %s" % (path, pinf.get("error")))
        L = len(seq)
        cand = [k for k in range(0, int(L - P - 1))]
        if not cand:
            cand = [0]
        def seam(k):
            j = min(L - 1, int(round(k + P)))
            mid = abs((k + P / 2) - L / 2) / L
            return Dm[k, j] + 0.04 * (1 - sn[k]) + 0.02 * mid
        k0 = min(cand, key=seam)
        times = [k0 + P * j / n_out for j in range(n_out)]
        sel_info.update(start=int(k0), seam_error=float(Dm[k0, min(L - 1, int(round(k0 + P)))]), period_s=P / fps)
        log("  loop: period %.1f frames (%.2f s)%s, start frame %d, seam error %.3f" % (
            P, P / fps, " [step %.1f]" % pinf.get("step_period", P) if is_loco and opts.period is None else "", seq[k0], sel_info["seam_error"]))
    else:
        a, b, ainf = action_span(E)
        sel_info.update(span=[int(seq[a]), int(seq[min(b, len(seq) - 1)])], **{k: float(v) for k, v in ainf.items()})
        b = max(a + 1, min(b, len(seq) - 1))
        tu = np.linspace(a, b, n_out)
        if opts.spacing in ("motion", "mix") and b - a >= 2:
            cum = np.concatenate([[0], np.cumsum(E[a:b] + 1e-4)]); cum /= cum[-1]
            tmo = np.interp(np.linspace(0, 1, n_out), cum, np.arange(a, b + 1))
            tu = tmo if opts.spacing == "motion" else 0.5 * (tu + tmo)
        times = list(tu)
        log("  action: frames %d-%d of %d (%.2f s) -> %d sprite frames%s" % (
            seq[a], seq[b], N, (b - a) / fps, n_out, "  (needs %.1fx slow-motion)" % ((n_out - 1) / max(1, b - a)) if b - a < n_out - 1 else ""))
    # ---- pick / interpolate
    picks = []
    spacing = (times[1] - times[0]) if len(times) > 1 else 1
    interp_mode = opts.interp
    n_interp = 0
    for t in times:
        lo = int(math.floor(t)); hi = min(len(seq) - 1, lo + 1); fr = t - lo
        near = lo if fr < 0.5 or lo == hi else hi
        if interp_mode == "none" or lo == hi or min(fr, 1 - fr) < 0.02:
            picks.append(("frame", seq[near], 0.0)); continue
        want_interp = interp_mode in ("flow", "blend") and min(fr, 1 - fr) > 0.25 or \
            interp_mode == "auto" and spacing < 1.5 and min(fr, 1 - fr) > 0.2
        if want_interp:
            picks.append(("interp", (seq[lo], seq[hi]), fr)); n_interp += 1
            continue
        # close enough to a real frame: prefer the sharper neighbour if the timing error stays small
        c = [(lo, fr), (hi, 1 - fr)]
        c = [x for x in c if x[1] <= max(0.5, 0.2 * spacing)] or [min(c, key=lambda x: x[1])]
        k = max(c, key=lambda x: sn[x[0]] - 1.5 * x[1] / max(spacing, 1))[0]
        picks.append(("frame", seq[k], 0.0))
    # ---- normalise: scale, ground, root
    def tc(i):  # torso centre x, bottom y, height
        x0, y0, x1, y1 = boxes[i]
        a = rgba[i][y0:y0 + max(1, int((y1 - y0) * 0.6)), x0:x1, 3].astype(np.float32)
        cols = a.sum(axis=0)
        return x0 + (cols * np.arange(len(cols))).sum() / max(1e-6, cols.sum()), y1, y1 - y0
    used = sorted({p[1] for p in picks if p[0] == "frame"} | {x for p in picks if p[0] == "interp" for x in p[1]})
    hs = np.array([tc(i)[2] for i in used]); bots = np.array([tc(i)[1] for i in used])
    if loop:
        ref_h = float(np.median(hs)); ground = float(np.percentile(bots, 80))
    else:
        pre = [i for i in seq[: max(1, seq.index(used[0]) + 1)]][-3:] or used[:1]
        ref_h = float(np.median([tc(i)[2] for i in pre])); ground = float(np.median([tc(i)[1] for i in pre]))
    # expected height of this move relative to standing (from the procedural motion library)
    ratio = expected_height_ratio(move)
    stand_h = ref_h / ratio
    # tracking shot: the feet stand on the ground band -> its shift is the camera pan the subject is measured against
    gb = int(min(offsets.shape[1] - 1, max(0, (ground - 3) * offsets.shape[1] / H)))
    # root x per pick
    pts = []
    for p in picks:
        if p[0] == "frame":
            pts.append(tc(p[1])[0] - (offsets[p[1], gb, 0] if cam == "tracking" else 0))
        else:
            (i, j), t = p[1], p[2]
            xa = tc(i)[0] - (offsets[i, gb, 0] if cam == "tracking" else 0)
            xb = tc(j)[0] - (offsets[j, gb, 0] if cam == "tracking" else 0)
            pts.append(xa * (1 - t) + xb * t)
    pts = np.array(pts)
    root = opts.root if opts.root != "auto" else ("inplace" if loop else "keep")
    if root == "inplace":
        if loop and len(pts) >= 3:
            k = np.arange(len(pts)); A = np.vstack([k, np.ones_like(k)]).T
            fit = np.linalg.lstsq(A, pts, rcond=None)[0]
            anchor = A @ fit
            travel = fit[0] * len(pts)
        else:
            anchor = pts; travel = float(pts[-1] - pts[0])
    else:
        anchor = np.full(len(pts), pts[0]); travel = float(pts[-1] - pts[0])
    # ---- render normalised frames
    HS = 400.0; s = HS / stand_h
    CW, CH = int(HS * 1.6), int(HS * 1.9); GY = int(CH - HS * 0.06)
    out_frames = []
    for k, p in enumerate(picks):
        if p[0] == "frame":
            i = p[1]
            im = rgba[i]
            cam_dx = offsets[i, gb, 0] if cam == "tracking" else 0
            out_frames.append(_place(im, boxes[i], s, anchor[k] + cam_dx, ground, CW, CH, GY))
        else:
            (i, j), t = p[1], p[2]
            ca = offsets[i, gb, 0] if cam == "tracking" else 0
            cb = offsets[j, gb, 0] if cam == "tracking" else 0
            A = _place(rgba[i], boxes[i], s, anchor[k] + ca, ground, CW, CH, GY)
            B = _place(rgba[j], boxes[j], s, anchor[k] + cb, ground, CW, CH, GY)
            m, how = interp_rgba(np.asarray(A), np.asarray(B), t) if interp_mode != "blend" else \
                ((np.asarray(A).astype(np.float32) * (1 - t) + np.asarray(B).astype(np.float32) * t).astype(np.uint8), "blend")
            out_frames.append(Image.fromarray(m, "RGBA"))
    tm["total_s"] = time.time() - t_all
    rep = dict(file=path, move=move, frames_out=len(out_frames), fps=fps, decoded=N, camera=cam, camera_info={k: v for k, v in cinfo.items() if k not in ("band_speed_px", "offsets2")},
               background=bgmode, threshold=thr_used, selection=sel_info, interpolated=n_interp, root=root,
               travel_px_per_cycle=float(travel), ref_h_px=ref_h, height_ratio=ratio, standing_h_px=stand_h,
               scale=s, times=tm, warnings=warn, picks=[(p[0], p[1] if p[0] == "frame" else list(p[1]), p[2]) for p in picks])
    if "curve" in sel_info:
        rep["selection"] = {k: v for k, v in sel_info.items() if k != "curve"}
    for w in warn:
        log("  ! " + w)
    dbg = dict(frames=frames, rgba=rgba, boxes=boxes, valid=valid, bg=bg_img, E=E, seq=seq, curve=sel_info.get("curve"),
               pmin=sel_info.get("pmin"), picks=picks, out=out_frames, cam=cam, offsets=offsets)
    return out_frames, rep, dbg


def _place(rgba, box, s, anchor_x, ground, CW, CH, GY):
    im = Image.fromarray(rgba, "RGBA")
    # map source (x, y) -> canvas: X = (x - anchor_x) * s + CW/2 ; Y = (y - ground) * s + GY
    inv = (1 / s, 0, anchor_x - (CW / 2) / s, 0, 1 / s, ground - GY / s)
    return im.transform((CW, CH), Image.AFFINE, inv, Image.BICUBIC)


_RATIO_CACHE = {}


def expected_height_ratio(move):
    """bbox height of the mannequin performing `move` / standing height (1.0 if unknown)."""
    if move in _RATIO_CACHE:
        return _RATIO_CACHE[move]
    r = 1.0
    try:
        from .motions import find_motion
        from .rig import evaluate, JOINT_NAMES
        mo = find_motion(move)
        if mo is not None:
            def h_of(st):
                ys = [st.world[j][1, 3] for j in JOINT_NAMES if j != "ball"]
                return (max(ys) + 0.12) - max(0.0, min(ys) - 0.08)
            st0 = evaluate(find_motion("idle").sample(0.0)[0])
            ts = [i / 12 for i in range(12)]
            hs = [h_of(evaluate(mo.sample(t)[0])) for t in ts]
            r = float(np.median(hs) if mo.loop else h_of(evaluate(mo.sample(0.0)[0]))) / h_of(st0)
            r = min(1.15, max(0.6, r))
    except Exception:
        r = 1.0
    _RATIO_CACHE[move] = r
    return r


# ------------------------------------------------------------------ debug sheet
def debug_sheet(dbg, rep, path, thumb_h=150):
    from .build import checker, _font
    frames, rgba, boxes = dbg["frames"], dbg["rgba"], dbg["boxes"]
    N, H, W = frames.shape[:3]
    tw = int(W * thumb_h / H)
    picks = dbg["picks"]
    src_idx = [p[1] if p[0] == "frame" else p[1][0] for p in picks]
    cols = min(8, len(src_idx))
    show = [src_idx[int(round(k * (len(src_idx) - 1) / max(1, cols - 1)))] for k in range(cols)]
    font = _font(14); small = _font(12)
    out_w = max(cols * (tw + 6) + 10, 900)
    ot = dbg["out"]; oh = 170; ow = int(ot[0].width * oh / ot[0].height) if ot else 0
    ocols = max(1, (out_w - 10) // (ow + 4))
    orows = int(math.ceil(len(ot) / ocols))
    sheet_h = 34 + (thumb_h + 22) * 2 + 140 + orows * (oh + 6) + 20
    sheet = Image.new("RGB", (out_w, sheet_h), (32, 34, 40)); d = ImageDraw.Draw(sheet)
    title = "%s  <-  %s   camera=%s  background=%s  fps=%.0f  frames=%d" % (rep["move"], os.path.basename(rep["file"]), rep["camera"], rep["background"], rep["fps"], N)
    d.text((10, 8), title, fill=(240, 240, 240), font=font)
    y = 34
    d.text((10, y), "source frames used (red = matte)", fill=(200, 200, 200), font=small); y += 16
    for k, i in enumerate(show):
        f = Image.fromarray(frames[i]).convert("RGBA")
        if rgba[i] is not None:
            m = Image.fromarray(rgba[i][..., 3])
            if dbg["cam"] == "handheld":
                m = Image.fromarray(align(rgba[i], -dbg["offsets"][i], H)[..., 3])
            red = Image.new("RGBA", f.size, (255, 40, 40, 0)); red.putalpha(m.point(lambda v: int(v * 0.45)))
            f = Image.alpha_composite(f, red)
        sheet.paste(f.convert("RGB").resize((tw, thumb_h)), (10 + k * (tw + 6), y))
        d.text((12 + k * (tw + 6), y + 2), "#%d" % i, fill=(255, 255, 0), font=small)
    y += thumb_h + 6
    d.text((10, y), "cut-outs", fill=(200, 200, 200), font=small); y += 16
    for k, i in enumerate(show):
        cb = checker(tw, thumb_h).convert("RGBA")
        if rgba[i] is not None:
            im = Image.fromarray(rgba[i], "RGBA").resize((tw, thumb_h))
            cb.alpha_composite(im)
        sheet.paste(cb.convert("RGB"), (10 + k * (tw + 6), y))
    y += thumb_h + 6
    # background + curve
    if dbg["bg"] is not None:
        bg = Image.fromarray(dbg["bg"]); bh = 120; bw = min(out_w // 2, int(bg.width * bh / bg.height))
        sheet.paste(bg.resize((bw, bh)), (10, y)); d.text((14, y + 2), "background model", fill=(255, 255, 0), font=small)
        gx = 20 + bw
    else:
        gx = 10
    gw = out_w - gx - 10; gh = 120
    d.rectangle([gx, y, gx + gw, y + gh], outline=(90, 90, 100))
    curve = dbg.get("curve")
    if curve:
        v = np.array(curve); v = (v - v.min()) / max(1e-6, np.ptp(v))
        pts = [(gx + k * gw / max(1, len(v) - 1), y + gh - 8 - (gh - 16) * vv) for k, vv in enumerate(v)]
        d.line(pts, fill=(120, 200, 255), width=2)
        P = rep["selection"].get("period"); st = rep["selection"].get("step_period")
        for val, colr, lab in ((st, (255, 200, 80), "step"), (P, (120, 255, 120), "loop")):
            if val:
                x = gx + (val - dbg["pmin"]) * gw / max(1, len(v) - 1)
                d.line([(x, y), (x, y + gh)], fill=colr, width=1); d.text((x + 3, y + 3), "%s %.1f" % (lab, val), fill=colr, font=small)
        d.text((gx + 4, y + gh - 16), "self-similarity vs lag (frames) - dips = repeats", fill=(200, 200, 200), font=small)
    else:
        E = dbg["E"]; v = E / max(1e-6, E.max())
        pts = [(gx + k * gw / max(1, len(v) - 1), y + gh - 8 - (gh - 16) * vv) for k, vv in enumerate(v)]
        d.line(pts, fill=(255, 160, 80), width=2)
        a, b = rep["selection"].get("span", [0, 0])
        seq = dbg["seq"]
        try:
            xa = gx + seq.index(a) * gw / max(1, len(v) - 1); xb = gx + seq.index(b) * gw / max(1, len(v) - 1)
            d.rectangle([xa, y, xb, y + gh], outline=(120, 255, 120))
        except ValueError:
            pass
        d.text((gx + 4, y + gh - 16), "motion energy per frame - green box = detected action", fill=(200, 200, 200), font=small)
    y += gh + 14
    d.text((10, y - 2), "sprite frames (normalised: common height, ground line, %s root)%s" % (
        rep["root"], ("  - %d in-betweens by optical flow" % rep["interpolated"]) if rep["interpolated"] else ""), fill=(200, 200, 200), font=small)
    y += 14
    for k, im in enumerate(ot):
        r, c = divmod(k, ocols)
        cb = checker(ow, oh).convert("RGBA"); cb.alpha_composite(im.resize((ow, oh), Image.LANCZOS))
        dd = ImageDraw.Draw(cb); gyy = int((im.height - 400 * 0.06) * oh / im.height)
        dd.line([(0, gyy), (ow, gyy)], fill=(0, 160, 255, 255))
        p = picks[k]
        dd.text((3, 2), ("%02d #%d" % (k, p[1])) if p[0] == "frame" else ("%02d ~%d+%.2f" % (k, p[1][0], p[2])), fill=(0, 0, 0), font=small)
        sheet.paste(cb.convert("RGB"), (10 + c * (ow + 4), y + r * (oh + 6)))
    sheet.save(path)
    return path


# ------------------------------------------------------------------ project
CLIP_KEYS = {"camera": str, "bg": str, "plate": str, "plate_start": float, "thr": float, "slowmo": float,
             "interp": str, "period": float, "flip": int, "shadows": int, "key": str, "spacing": float}


def parse_clip(spec):
    """'walk=clip.mp4'  'walk:8=clip.mp4'  'jump=clip.mp4@1.2-2.6'  'jump:12=clip.mp4#plate_start=0.5,camera=handheld'
    -> (move, frames|None, path, start, end, overrides)"""
    lhs, _, rhs = spec.partition("=")
    if not rhs:
        raise ValueError("--clip needs MOVE=path (got %r)" % spec)
    mv, _, n = lhs.partition(":")
    over = {}
    if "#" in rhs:
        rhs, _, ov = rhs.partition("#")
        for kv in ov.split(","):
            k, _, v = kv.partition("=")
            k = k.strip()
            if k not in CLIP_KEYS:
                raise ValueError("unknown per-clip option %r (allowed: %s)" % (k, ", ".join(CLIP_KEYS)))
            if k == "key":
                v = tuple(int(x) for x in v.replace("#", "").split("/")) if "/" in v else v
            over[k] = CLIP_KEYS[k](v) if k != "key" else v
    path, start, end = rhs, None, None
    if "@" in rhs:
        path, _, rng = rhs.rpartition("@")
        a, _, b = rng.partition("-")
        start = float(a) if a else None; end = float(b) if b else None
    return mv.strip(), (int(n) if n else None), path.strip(), start, end, over


def run_clips(clips, moves, work, opts: ClipOptions, log=print):
    """clips: list of parse_clip tuples; moves: list of MoveSpec (frames / loop used).
    Writes work/<move>/NN.png + work/video_meta.json + work/_debug/<move>.png"""
    from .moves import MoveSpec, slug
    from .motions import find_motion
    os.makedirs(work, exist_ok=True)
    dbg_dir = os.path.join(work, "_debug"); os.makedirs(dbg_dir, exist_ok=True)
    meta = {"standing_h": 400.0, "clips": []}
    by = {m.name: m for m in moves}
    import copy
    for c in clips:
        mv, n, path, start, end = c[:5]
        over = c[5] if len(c) > 5 else {}
        copts = copy.copy(opts)
        for k, v in over.items():
            setattr(copts, k, bool(v) if k in ("flip", "shadows") else v)
        key = slug(mv)
        m = by.get(key)
        if m is None:
            mo = find_motion(key)
            m = MoveSpec(key, mv, "Video", n or 8, 12, bool(mo and mo.loop) or any(k in key for k in LOCO), "", "from video")
            moves.append(m); by[key] = m
        if n:
            m.frames = n
        log("clip %s -> %s (%d frames, %s)" % (os.path.basename(path), key, m.frames, "loop" if m.loop else "one-shot"))
        out, rep, dbg = process_clip(path, key, m.frames, m.loop, copts, start, end, log)
        rep["options"] = {k: v for k, v in vars(copts).items() if not k.startswith("_")}
        d = os.path.join(work, key)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for k, im in enumerate(out):
            im.save(os.path.join(d, "%s_%02d.png" % (key, k)))
        rep["debug_sheet"] = debug_sheet(dbg, rep, os.path.join(dbg_dir, key + ".png"))
        if m.loop and rep["selection"].get("period_s"):
            m.fps = max(4, min(30, int(round(m.frames / rep["selection"]["period_s"]))))
            rep["sprite_fps"] = m.fps
        elif not m.loop and rep["selection"].get("span"):
            a, b = rep["selection"]["span"]
            m.fps = max(4, min(30, int(round((m.frames - 1) / max(1e-3, (b - a) / rep["fps"])))))
            rep["sprite_fps"] = m.fps
        meta["clips"].append(rep)
        log("  -> %d frames, %.2fs total (decode %.2fs, camera %.2fs, background %.2fs, matte %.2fs = %.0f frames/s)" % (
            len(out), rep["times"]["total_s"], rep["times"]["decode_s"], rep["times"]["camera_s"], rep["times"]["background_s"],
            rep["times"]["matte_s"], rep["times"].get("matte_fps", 0)))
    with open(os.path.join(work, "video_meta.json"), "w") as f:
        json.dump(meta, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return meta
