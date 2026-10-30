#!/usr/bin/env python3
"""
SpriteForge - generic character sprite pipeline for raylib / C games.

Turns EXISTING images of a character (one photo, per-move sprite strips, or per-move
frame folders) into clean, game-ready sprite sheets:

  * background removal: transparent PNGs are cleaned (alpha noise, colour fringe /
    halo decontamination); opaque images get a smooth background model fitted from the
    borders, flood-filled from the edges (white shirts are NOT keyed out) and a soft,
    colour-decontaminated alpha edge (no white/black halo)
  * every pose found by connected components; small detached bits (a hand, a prop)
    merged into the nearest figure; touching poses split at the thinnest column;
    exact repeats and cut-off slivers dropped; multi-row grids read row by row
  * ONE scale per source sheet, estimated from the figure's body area (pose
    independent), so the character is the SAME height in every move
  * fixed canvas for the whole character, feet on ONE common ground line, body centre
    (mass median column) on the cell centre
  * missing moves filled procedurally from the character's own frames (FALLBACK table)
  * writes <out>/<move>.png (one strip per move) or combined.png, <out>/frames/*.png,
    <out>/sprites.cfg and <out>/contact.png (preview)

No new imagery of any person is generated: every output pixel comes from the input
images through cut-out, scale, rotate, shear, tint or glow.

Usage:
  python tools/spriteforge.py --name dec --src path/to/sheets_dir --out assets/dec
  python tools/spriteforge.py --name me  --src photo.png          --out assets/me
Options: --height 480  --layout per-move|combined|both  --choke 0  --no-preview
Per-character overrides: <src>/spriteforge.json (see README)
Needs: pip install pillow numpy scipy
"""
import argparse, glob, json, math, os, re, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

VERSION = 1
MOVES = ['idle', 'walk', 'crouch', 'jump', 'punch', 'kick', 'special1', 'special2',
         'block', 'hit', 'throw', 'jumpattack', 'taunt', 'victory']
# file / folder names accepted for each move (lower case, without extension)
ALIASES = {
    'idle': ['idle', 'stand', 'stance', 'ready', 'ready_stance'],
    'walk': ['walk', 'run', 'walk_cycle'],
    'crouch': ['crouch', 'duck'],
    'jump': ['jump'],
    'punch': ['punch', 'attack'],
    'kick': ['kick'],
    'special1': ['special1', 'special_1', 'special', 'pyramid_blast', 'fireball'],
    'special2': ['special2', 'special_2', 'bum_fireball', 'super'],
    'block': ['block', 'guard'],
    'hit': ['hit', 'hurt', 'stun', 'damage'],
    'throw': ['throw', 'grab'],
    'jumpattack': ['jumpattack', 'jump_attack', 'jumpkick', 'jump_kick', 'air_attack'],
    'taunt': ['taunt'],
    'victory': ['victory', 'win', 'celebrate'],
}
# default timing: fps, loop (1 = loop forever, 0 = play once and hold the last frame)
TIMING = {
    'idle': (8, 1), 'walk': (12, 1), 'crouch': (16, 0), 'jump': (10, 0), 'punch': (15, 0),
    'kick': (14, 0), 'special1': (12, 0), 'special2': (12, 0), 'block': (12, 0),
    'hit': (10, 0), 'throw': (12, 0), 'jumpattack': (14, 0), 'taunt': (8, 1), 'victory': (7, 1),
}
# Missing-move fallback table: first source move that exists wins.  (source, op)
# ops: same=copy frames, glow=copy + aura on the middle frames, first2=first two frames,
#      bob=breathing squash of frame 0, legswing=procedural walk (legs cut at the crotch
#      and swung about the hip), squash=legs compressed into a crouch, stretch=jump
#      stretch/tuck, lunge=lean-forward strike, legkick=front leg rotated up about the hip,
#      leanback=guard lean, hitflash=red flash + recoil, taunt=lean/pulse with aura,
#      cheer=bounce, rev=frames reversed
FALLBACK = {
    'idle':       [('walk', 'bob'), ('block', 'bob'), ('hit', 'bob'), ('*', 'bob')],
    'walk':       [('idle', 'legswing')],
    'crouch':     [('idle', 'squash')],
    'jump':       [('idle', 'stretch')],
    'punch':      [('throw', 'same'), ('kick', 'same'), ('idle', 'lunge')],
    'kick':       [('idle', 'legkick'), ('punch', 'same')],
    'special1':   [('throw', 'glow'), ('punch', 'glow')],
    'special2':   [('kick', 'glow'), ('punch', 'glow'), ('special1', 'same')],
    'block':      [('punch', 'first2'), ('idle', 'leanback')],
    'hit':        [('idle', 'hitflash')],
    'throw':      [('punch', 'same'), ('special1', 'same')],
    'jumpattack': [('kick', 'same'), ('punch', 'same'), ('jump', 'same')],
    'taunt':      [('idle', 'taunt'), ('victory', 'same')],
    'victory':    [('taunt', 'same'), ('jump', 'same'), ('idle', 'cheer')],
}
GLOW_RGB = (120, 200, 255)
IMG_EXT = ('.png', '.webp', '.jpg', '.jpeg', '.bmp', '.tga')


def log(*a):
    print(*a, flush=True)

# ============================================================= background removal ====
def load_rgba(path, choke=0):
    a = np.array(Image.open(path).convert('RGBA'))
    if (a[..., 3] < 20).mean() > 0.05:          # already has transparency
        a = clean_transparent(a)
    else:
        a = remove_opaque_bg(a)
    if choke > 0:
        m = ndi.binary_erosion(a[..., 3] > 0, iterations=choke)
        a[~m] = 0
    return a


def clean_transparent(a):
    """alpha noise off, colour of fully transparent pixels zeroed, and edge pixels that are
    much lighter/different from the body next to them (left-over matte = halo) recoloured"""
    a = a.copy()
    a[a[..., 3] < 16] = 0
    al = a[..., 3]
    vis = al > 0
    core = al >= 250
    dist_out = ndi.distance_transform_edt(vis)          # distance to transparency
    core_in = core & (dist_out > 3)
    if core_in.any():
        _, idx = ndi.distance_transform_edt(~core_in, return_indices=True)
        ref = a[idx[0], idx[1], :3].astype(int)
        rgb = a[..., :3].astype(int)
        diff = np.abs(rgb - ref).sum(-1)
        lum, rl = rgb.mean(-1), ref.mean(-1)
        edge = vis & (dist_out <= 2.5)
        # partial-alpha fringe always takes the body colour; opaque rim pixels only when
        # they look like a light matte (much lighter, low saturation)
        sat = rgb.max(-1) - rgb.min(-1)
        matte = edge & (((al < 235) & (diff > 40)) | ((diff > 120) & (sat < 40) & ((lum > rl + 60) | (lum > 225))))
        a[matte, :3] = ref[matte]
    a[a[..., 3] == 0, :3] = 0
    return a


def remove_opaque_bg(a):
    """smooth background model from the borders; flood fill from the edges; soft matte"""
    rgb = a[..., :3].astype(float)
    h, w, _ = rgb.shape
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    design = lambda y, x: np.stack([np.ones_like(y), x, y, x * x, y * y, x * y], -1)
    bw = max(6, min(h, w) // 40)
    sel = np.zeros((h, w), bool); sel[:bw] = 1; sel[:, :bw] = 1; sel[:, -bw:] = 1
    for _ in range(3):            # fit a smooth background, re-select pixels that match it
        coef, *_ = np.linalg.lstsq(design(yy[sel], xx[sel]), rgb[sel], rcond=None)
        bgc = design(yy, xx) @ coef
        res = np.abs(rgb - bgc).sum(-1)
        sel = res < 25
    lab, n = ndi.label(res < 30)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(border))
    lab2, n2 = ndi.label(res < 16)            # enclosed background pockets (arm/body gaps)
    if n2:
        sz = ndi.sum(np.ones_like(res), lab2, range(1, n2 + 1))
        bg |= np.isin(lab2, np.where(sz > max(600, h * w // 4000))[0] + 1)
    fg = ~bg
    frac = fg.mean()
    if frac > 0.9 or frac < 0.005:
        rb = _try_rembg(a)
        if rb is not None:
            return clean_transparent(rb)
        log(f'  ! background not plain (foreground {frac:.0%}); cut the figure out first '
            '(transparent PNG) or pip install rembg')
    # soft alpha in a 2px band around the cut, from the colour distance to the bg model,
    # and colour decontamination F = (C - (1-a) B) / a   -> no halo of the old background
    inner = ndi.binary_erosion(fg, iterations=2)
    band = fg & ~inner
    alpha = np.where(fg, 1.0, 0.0)
    soft = np.clip((res - 14) / 70.0, 0, 1)
    alpha[band] = soft[band]
    aa = np.maximum(alpha, 0.25)[..., None]
    F = np.clip((rgb - (1 - aa) * bgc) / aa, 0, 255)
    out = a.copy()
    out[..., :3] = np.where(band[..., None], F, rgb).astype(np.uint8)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    out[out[..., 3] < 40] = 0
    return clean_transparent(out)


def _try_rembg(a):
    try:
        from rembg import remove          # optional
    except Exception:
        return None
    log('  using rembg for a non-plain background')
    return np.array(remove(Image.fromarray(a)).convert('RGBA'))

# ================================================================== segmentation ====
def segment(a, alpha_thr=40, min_comp=150, seed_frac=0.12):
    m = a[..., 3] > alpha_thr
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return []
    sizes = ndi.sum(m, lab, range(1, n + 1))
    objs = ndi.find_objects(lab)
    big = sizes.max()
    seeds = [i for i in range(n) if sizes[i] >= seed_frac * big]
    groups = {s: [s] for s in seeds}
    for i in range(n):
        if i in groups or sizes[i] < min_comp:
            continue
        sl = objs[i]
        cx = (sl[1].start + sl[1].stop) / 2; cy = (sl[0].start + sl[0].stop) / 2
        best, bd = None, 1e9
        for s in seeds:
            ss = objs[s]
            dx = max(ss[1].start - cx, 0, cx - ss[1].stop)
            dy = max(ss[0].start - cy, 0, cy - ss[0].stop)
            d = dx + 0.3 * dy
            if d < bd:
                bd, best = d, s
        if bd < 120:
            groups[best].append(i)
    frames = []
    for s, mem in groups.items():
        frames.append(_frame(np.isin(lab, [k + 1 for k in mem])))
    return order_frames(frames)


def order_frames(frames):
    """reading order: rows (by vertical overlap) top to bottom, then left to right"""
    frames = sorted(frames, key=lambda f: (f['y0'] + f['y1']) / 2)
    rows = []
    for f in frames:
        for r in rows:
            ov = min(r['y1'], f['y1']) - max(r['y0'], f['y0'])
            if ov > 0.4 * min(r['y1'] - r['y0'], f['y1'] - f['y0']):
                r['f'].append(f); r['y0'] = min(r['y0'], f['y0']); r['y1'] = max(r['y1'], f['y1'])
                break
        else:
            rows.append(dict(y0=f['y0'], y1=f['y1'], f=[f]))
    rows.sort(key=lambda r: r['y0'])
    return [f for r in rows for f in sorted(r['f'], key=lambda f: f['x0'])]


def _frame(mask):
    ys, xs = np.nonzero(mask)
    return dict(mask=mask, x0=xs.min(), x1=xs.max() + 1, y0=ys.min(), y1=ys.max() + 1, size=int(mask.sum()))


def _drop_neighbour_bits(mk, cut_cols):
    """after a split: small pieces touching a cut column belong to the neighbouring pose"""
    lab, nn = ndi.label(mk, structure=np.ones((3, 3)))
    if nn <= 1:
        return mk
    sz = ndi.sum(mk, lab, range(1, nn + 1))
    keep = np.zeros(nn + 1, bool)
    for k in range(1, nn + 1):
        touches = any(lab[:, max(0, c - 1):c + 1].__eq__(k).any() for c in cut_cols)
        keep[k] = sz[k - 1] >= 0.25 * sz.max() or not touches
    return keep[lab] & mk


def split_wide(frames):
    """split blobs that are two or more touching poses at the thinnest column"""
    if len(frames) < 2:
        return frames
    ws = np.array([f['x1'] - f['x0'] for f in frames], float)
    best = None
    for w0 in sorted(ws):
        cnt = int(((ws >= 0.85 * w0) & (ws <= 1.2 * w0)).sum())
        if best is None or cnt > best[0]:
            best = (cnt, w0)
    ew = float(np.median(ws[(ws >= 0.85 * best[1]) & (ws <= 1.2 * best[1])]))
    out = []
    for f in frames:
        w = f['x1'] - f['x0']
        k = int(round(w / ew))
        if w < 1.6 * ew or k < 2:
            out.append(f); continue
        col = f['mask'][:, f['x0']:f['x1']].sum(0).astype(float)
        cuts = []
        for j in range(1, k):
            c = int(j * w / k); r = int(ew * 0.3)
            lo, hi = max(1, c - r), min(w - 1, c + r)
            cuts.append(lo + int(np.argmin(col[lo:hi])))
        edges = [0] + cuts + [w]
        for s, e in zip(edges[:-1], edges[1:]):
            mk = np.zeros_like(f['mask'])
            mk[:, f['x0'] + s:f['x0'] + e] = f['mask'][:, f['x0'] + s:f['x0'] + e]
            mk = _drop_neighbour_bits(mk, [f['x0'] + s, f['x0'] + e])
            if mk.sum() > 0.2 * f['size'] / k:
                out.append(_frame(mk))
    return order_frames(out)


def split_even(frames, n):
    """poses that touch each other (one blob): cut the widest blob at the emptiest column
    near the expected boundary until there are n poses"""
    frames = list(frames)
    if not frames:
        return frames
    total = sum(f['x1'] - f['x0'] for f in frames)
    ew = total / float(n)
    guard = 0
    while len(frames) < n and guard < 4 * n:
        guard += 1
        f = max(frames, key=lambda f: f['x1'] - f['x0'])
        w = f['x1'] - f['x0']
        k = max(2, int(round(w / ew)))
        col = f['mask'][:, f['x0']:f['x1']].sum(0).astype(float)
        c = int(w / k); r = int(ew * 0.35)
        lo, hi = max(1, c - r), min(w - 1, c + r)
        if hi <= lo:
            break
        cut = lo + int(np.argmin(col[lo:hi]))
        frames = [g for g in frames if g is not f]
        for s, e in ((0, cut), (cut, w)):
            mk = np.zeros_like(f['mask'])
            mk[:, f['x0'] + s:f['x0'] + e] = f['mask'][:, f['x0'] + s:f['x0'] + e]
            lab, nn = ndi.label(mk, structure=np.ones((3, 3)))
            if nn > 1:
                sz = ndi.sum(mk, lab, range(1, nn + 1))
                mk = np.isin(lab, 1 + np.nonzero(sz >= 0.05 * sz.max())[0])
            if mk.any():
                frames.append(_frame(mk))
        frames = order_frames(frames)
    return frames


def drop_stray(mask):
    """secondary pieces that are small AND mostly beside the main body (a neighbouring
    pose's foot or hand) are removed; pieces over the body (a held prop) stay"""
    lab, nn = ndi.label(mask, structure=np.ones((3, 3)))
    if nn <= 1:
        return mask
    sz = ndi.sum(mask, lab, range(1, nn + 1))
    main = int(np.argmax(sz)) + 1
    xs = np.nonzero(lab == main)[1]
    mx0, mx1 = xs.min(), xs.max()
    keep = mask.copy()
    for k, sl in enumerate(ndi.find_objects(lab), 1):
        if k == main or sz[k - 1] >= 0.15 * sz[main - 1]:
            continue
        x0, x1 = sl[1].start, sl[1].stop
        inside = max(0, min(x1, mx1) - max(x0, mx0)) / float(x1 - x0)
        if inside < 0.5:
            keep[lab == k] = False
    return keep


def crop(a, f, stray=True):
    sub = a[f['y0']:f['y1'], f['x0']:f['x1']].copy()
    keep = f['mask'][f['y0']:f['y1'], f['x0']:f['x1']]
    if stray:
        keep = drop_stray(keep)
    # keep the soft edge: grow the hard mask by 2px into the partial-alpha fringe
    keep = ndi.binary_dilation(keep, iterations=2) & (sub[..., 3] > 0)
    sub[~keep] = 0
    return sub


def dedupe_and_clean(subs):
    """drop pixel-identical repeats (tiled strips) and cut-off slivers"""
    if not subs:
        return subs
    hs = np.array([s.shape[0] for s in subs]); ws = np.array([s.shape[1] for s in subs])
    medw = np.median(ws)
    areas = np.array([(s[..., 3] > 40).sum() for s in subs], float)
    meda = np.median(areas)
    keep, sigs = [], []
    for s, ar in zip(subs, areas):
        if len(subs) > 2 and s.shape[1] < 0.62 * medw and s.shape[0] > 0.8 * hs.max():
            continue                       # vertical sliver of a neighbouring pose
        if len(subs) > 2 and ar < 0.45 * meda:
            continue                       # cut-off fragment (a leg / arm of a pose)
        sig = np.asarray(Image.fromarray(s).resize((32, 64), Image.BILINEAR), float)
        if any(np.abs(sig - o).mean() < 2.0 for o in sigs):
            continue
        sigs.append(sig); keep.append(s)
    return keep


def fill_light_holes(sub, max_frac=0.06):
    """pinholes (<= 12 px) and enclosed see-through pockets whose rim is light and unsaturated (a white shirt that
    an earlier colour key removed) are filled from the rim colour.  Dark-rimmed pockets
    (real gaps between arm and body) are left alone."""
    m = sub[..., 3] > 40
    holes = ndi.binary_fill_holes(m) & ~m
    lab, n = ndi.label(holes)
    if n == 0:
        return sub
    sub = sub.copy()
    area = m.sum()
    rgb = sub[..., :3].astype(float)
    filled = np.zeros_like(m)
    for i, sl in enumerate(ndi.find_objects(lab)):
        sl2 = tuple(slice(max(0, q.start - 3), q.stop + 3) for q in sl)
        reg = lab[sl2] == i + 1
        if reg.sum() > max_frac * area:
            continue
        rim = ndi.binary_dilation(reg, iterations=2) & ~reg & m[sl2]
        if not rim.any():
            continue
        c = rgb[sl2][rim]
        lum = c.mean(); sat = (c.max(1) - c.min(1)).mean()
        if (lum > 165 and sat < 45) or reg.sum() <= 12:     # light rim, or a pinhole
            filled[sl2] |= reg
    if filled.any():
        core = m & ~filled
        _, idx = ndi.distance_transform_edt(~core, return_indices=True)
        src = sub[idx[0], idx[1]]
        sm = ndi.uniform_filter(src[..., :3].astype(float), size=(5, 5, 1))
        sub[filled, :3] = sm[filled].astype(np.uint8)
        sub[filled, 3] = 255
    return sub


def fill_shirt_holes(sub, rgb=(232, 234, 230), band=(0.08, 0.48)):
    """opt-in ("fill_shirt" in spriteforge.json / --fill-shirt): enclosed see-through
    pockets in the upper torso were a light shirt that an earlier colour key removed.
    Paint them back in a shaded shirt tone (from Padel Wars build_sprites.py)."""
    m = sub[..., 3] > 40
    holes = ndi.binary_fill_holes(m) & ~m
    lab, n = ndi.label(holes)
    if n == 0:
        return sub
    sub = sub.copy()
    ys = np.nonzero(m)[0]
    top = ys.min(); hgt = ys.max() - top
    for i, sl in enumerate(ndi.find_objects(lab)):
        reg = lab[sl] == i + 1
        cy = (sl[0].start + sl[0].stop) / 2
        if top + band[0] * hgt < cy < top + band[1] * hgt and reg.sum() >= 12:
            px = sub[sl]
            shade = np.linspace(1.0, 0.9, reg.shape[0])[:, None]
            for c in range(3):
                px[..., c] = np.where(reg, (rgb[c] * shade).astype(np.uint8), px[..., c])
            px[..., 3] = np.where(reg, 255, px[..., 3])
    return sub


def trim(sub, thr=8):
    m = sub[..., 3] > thr
    if not m.any():
        return sub[:1, :1]
    ys, xs = np.nonzero(m)
    return sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def body_anchor_x(sub):
    """weighted median column of the figure's mass (stays on the body when a limb or a
    prop sticks out)"""
    col = (sub[..., 3] > 40).sum(0).astype(float)
    c = np.cumsum(col)
    return float(np.searchsorted(c, c[-1] / 2)) + 0.5


def size_metric(sub):
    """pose-independent size: sqrt of the solid body area"""
    return math.sqrt(max(1, int((sub[..., 3] > 40).sum())))

# ============================================================ procedural helpers ====
def _runs(row):
    r, x, W = [], 0, len(row)
    while x < W:
        if row[x]:
            s = x
            while x < W and row[x]:
                x += 1
            r.append((s, x))
        else:
            x += 1
    return r


def leg_rig(sub, hip_frac=0.07):
    """find the crotch by following the gap between the legs upwards; split the figure
    into back leg, front leg and the rest of the body"""
    a = sub
    solid = a[..., 3] > 40
    anyp = a[..., 3] > 0
    h, w = solid.shape
    for frac in (0.88, 0.84, 0.92, 0.8, 0.76):
        y = int(h * frac)
        runs = sorted([r for r in _runs(solid[y]) if r[1] - r[0] > 3], key=lambda r: r[1] - r[0])[-2:]
        if len(runs) == 2:
            break
    else:
        return None
    runs.sort()
    gx = (runs[0][1] + runs[1][0]) / 2.0
    centers = {}
    while y > h * 0.3:
        row = solid[y]
        xi = int(round(gx))
        if row[xi]:
            win = [x for x in range(max(0, xi - 6), min(w, xi + 7)) if not row[x]]
            if not win:
                break
            xi = min(win, key=lambda x: abs(x - gx))
        l = xi
        while l > 0 and not row[l - 1]:
            l -= 1
        r = xi
        while r < w - 1 and not row[r + 1]:
            r += 1
        if l == 0 or r == w - 1:
            break
        gx = (l + r) / 2.0
        centers[y] = gx
        y -= 1
    if not centers or min(centers) > h * 0.75:
        return None
    crotch = min(centers)
    cx = centers[crotch]
    pivot = max(0, crotch - int(hip_frac * h))
    last = centers[max(centers)]
    split = np.full(h, cx, float)
    for yy_ in range(h):
        if yy_ in centers:
            split[yy_] = centers[yy_]
        elif yy_ > max(centers):
            split[yy_] = last
    YY, XX = np.mgrid[0:h, 0:w]
    leg_rows = YY >= pivot
    back = leg_rows & (XX < split[:, None]) & anyp
    front = leg_rows & (XX >= split[:, None]) & anyp
    below = (YY > crotch + 1) & anyp
    lab, nl = ndi.label(below, structure=np.ones((3, 3)))
    if nl >= 2:
        sizes = ndi.sum(below, lab, range(1, nl + 1))
        order = np.argsort(sizes)[::-1][:2] + 1
        if sizes[order[1] - 1] > 0.15 * sizes[order[0] - 1]:
            cxs = [np.nonzero(lab == k)[1].mean() for k in order]
            kb, kf = (order[0], order[1]) if cxs[0] < cxs[1] else (order[1], order[0])
            back[lab == kb] = True; front[lab == kb] = False
            front[lab == kf] = True; back[lab == kf] = False
    def foot_x(leg):                      # mean x of the lowest 15% of that leg
        ys, xs = np.nonzero(leg & solid)
        if len(ys) == 0:
            return None
        lo = ys.max() - 0.15 * (ys.max() - ys.min() + 1)
        return xs[ys >= lo]
    bx, fx = foot_x(back), foot_x(front)
    if bx is None or fx is None or len(bx) == 0 or len(fx) == 0:
        return None
    B = bx.mean() - cx; F = fx.mean() - cx
    base = a.copy(); base[back | front] = 0
    return dict(a=a, back=back, front=front, base=base, pivot=pivot, cx=cx, crotch=crotch,
                B=B, F=F, mid=(F + B) / 2, amp=(F - B) / 2, h=h, w=w)


def _layer(a, mask, pad):
    L = np.zeros((a.shape[0] + 2 * pad, a.shape[1] + 2 * pad, 4), np.uint8)
    L[pad:pad + a.shape[0], pad:pad + a.shape[1]][mask] = a[mask]
    return Image.fromarray(L)


def procedural_walk(sub, n=8):
    """legs cut apart below the crotch and swung past each other about the hip"""
    r = leg_rig(sub)
    if r is None:
        return None
    a, h, w, cx, pivot = r['a'], r['h'], r['w'], r['cx'], r['pivot']
    amp = max(abs(r['amp']), 0.07 * h)
    pad = int(amp * 2 + 16)
    fy = h - 1 - 0.04 * h
    frames = []
    for k in range(n):
        ph = 2 * math.pi * k / n
        c = math.cos(ph)
        img = Image.new('RGBA', (w + 2 * pad, h + 2 * pad))
        def leg(mask, foot, target, lift):
            ln = math.hypot(foot, fy - pivot)
            a0 = math.atan2(foot, fy - pivot)
            a1 = math.asin(max(-0.95, min(0.95, target / ln)))
            li = _layer(a, mask, pad).rotate(math.degrees(a1 - a0), resample=Image.BICUBIC,
                                             center=(cx + pad, pivot + pad))
            ly = int(round(lift * 0.035 * h))
            if ly:
                li = li.transform(li.size, Image.AFFINE, (1, 0, 0, 0, 1, ly), resample=Image.BICUBIC)
            return li
        img.alpha_composite(_layer(a, r['base'][..., 3] > 0, pad))
        img.alpha_composite(leg(r['back'], r['B'], r['mid'] - amp * c, max(0.0, math.sin(ph))))
        img.alpha_composite(leg(r['front'], r['F'], r['mid'] + amp * c, max(0.0, -math.sin(ph))))
        frames.append(trim(np.asarray(img)))
    return frames


def leg_kick(sub, angles=(0, 25, 55, 80, 80, 40)):
    """front leg rotated forward/up about the hip, body leans back a little"""
    r = leg_rig(sub)
    if r is None:
        return None
    a, h, w, cx, pivot = r['a'], r['h'], r['w'], r['cx'], r['pivot']
    pad = int(h * 0.6)
    out = []
    for ang in angles:
        img = Image.new('RGBA', (w + 2 * pad, h + 2 * pad))
        body = Image.new('RGBA', img.size)
        body.alpha_composite(_layer(a, r['base'][..., 3] > 0, pad))
        body.alpha_composite(_layer(a, r['back'], pad))
        lean = -ang * 0.12
        body = body.rotate(-lean, resample=Image.BICUBIC, center=(cx + pad, h - 1 + pad))
        img.alpha_composite(body)
        leg = _layer(a, r['front'], pad).rotate(ang, resample=Image.BICUBIC, center=(cx + pad, pivot + pad))
        img.alpha_composite(leg)
        out.append(trim(np.asarray(img)))
    return out


def leg_squash(sub, factors=(0.9, 0.78, 0.7, 0.7)):
    """crouch: everything below the hip line compressed vertically and slightly widened"""
    h, w = sub.shape[:2]
    r = leg_rig(sub)
    hip = r['pivot'] if r else int(h * 0.5)
    out = []
    for f in factors:
        top = sub[:hip]
        low = Image.fromarray(np.ascontiguousarray(sub[hip:]))
        nh = max(1, int(round(low.height * f)))
        nw = int(round(w * (1 + (1 - f) * 0.35)))
        low = np.asarray(low.resize((nw, nh), Image.LANCZOS))
        W = max(w, nw)
        canvas = np.zeros((hip + nh, W, 4), np.uint8)
        ox = (W - nw) // 2
        canvas[hip:, ox:ox + nw] = low
        L = Image.fromarray(canvas)
        L.alpha_composite(Image.fromarray(np.pad(top, ((0, nh), ((W - w) // 2, W - w - (W - w) // 2), (0, 0)))))
        out.append(trim(np.asarray(L)))
    return out


def add_glow(arr, color, radius=11, strength=0.75):
    p = radius * 2
    arrp = np.pad(arr, ((p, p), (p, p), (0, 0)))
    al = arrp[..., 3].astype(float) / 255
    g = ndi.gaussian_filter(ndi.grey_dilation(al, size=(radius, radius)), radius / 2)
    g = (g * strength).clip(0, 1)
    out = np.zeros_like(arrp)
    out[..., :3] = color
    out[..., 3] = (g * 255).astype(np.uint8)
    o = Image.fromarray(out)
    o.alpha_composite(Image.fromarray(arrp))
    return np.asarray(o).copy()


def xform(f, lean=0.0, sx=1.0, sy=1.0, tint=None, glow=None):
    """re-use a real frame with a small transform about the feet: lean (deg, + = forward),
    sx/sy squash, tint=(r,g,b,k) flash, glow=(r,g,b) aura"""
    pad = int(max(f.shape) * 0.35) + 8
    a = np.pad(f, ((pad, 4), (pad, pad), (0, 0)))
    im = Image.fromarray(a)
    fx, fy = pad + body_anchor_x(f), float(pad + f.shape[0] - 1)
    if (sx, sy) != (1.0, 1.0):
        im = im.transform(im.size, Image.AFFINE, (1 / sx, 0, fx - fx / sx, 0, 1 / sy, fy - fy / sy),
                          resample=Image.BICUBIC)
    if lean:
        im = im.rotate(-lean, resample=Image.BICUBIC, center=(fx, fy))
    a = np.asarray(im).copy()
    if tint is not None:
        r, g, b, k = tint
        m = a[..., 3] > 0
        a[m, :3] = (a[m, :3] * (1 - k) + np.array([r, g, b]) * k).astype(np.uint8)
    if glow is not None:
        a = add_glow(a, glow)
    return trim(a)


def apply_fallback(op, frames, glow_rgb=GLOW_RGB):
    f0 = frames[0]
    n = len(frames)
    if op == 'same':
        return list(frames)
    if op == 'rev':
        return list(frames[::-1])
    if op == 'first2':
        return list(frames[:2]) if n >= 2 else [f0, xform(f0, lean=-3)]
    if op == 'glow':
        return [xform(f, glow=glow_rgb) if (0 < i < n - 1 or n <= 2) else f for i, f in enumerate(frames)]
    if op == 'bob':
        return [xform(f0, sx=sx, sy=sy) for sx, sy in ((1, 1), (1.004, 0.993), (1.008, 0.986), (1.004, 0.993))]
    if op == 'legswing':
        w = procedural_walk(f0)
        return w if w else [xform(f0, lean=l, sy=s) for l, s in ((2, 1), (3, 0.985), (2, 1), (1, 0.985))]
    if op == 'squash':
        return leg_squash(f0)
    if op == 'stretch':
        sq = leg_squash(f0, (0.82,))[0]
        return [sq, xform(f0, sx=0.96, sy=1.05), xform(f0, sx=0.97, sy=1.03, lean=4),
                leg_squash(f0, (0.75,))[0], xform(f0, sy=1.02, lean=2), sq]
    if op == 'lunge':
        return [xform(f0, lean=l, sx=sx) for l, sx in ((-3, 1), (4, 1.02), (9, 1.05), (10, 1.06), (4, 1.02))]
    if op == 'legkick':
        k = leg_kick(f0)
        return k if k else apply_fallback('lunge', frames)
    if op == 'leanback':
        return [xform(f0, lean=-4, sx=0.98), xform(f0, lean=-6, sx=0.97)]
    if op == 'hitflash':
        return [xform(f0, lean=-8, tint=(255, 40, 40, 0.45)), xform(f0, lean=-12, tint=(255, 40, 40, 0.3)),
                xform(f0, lean=-9), xform(f0, lean=-4)]
    if op == 'taunt':
        return [xform(f0), xform(f0, lean=-5, glow=glow_rgb), xform(f0, sy=1.02),
                xform(f0, lean=-5, glow=glow_rgb), xform(f0, sy=1.02), xform(f0, glow=glow_rgb)]
    if op == 'cheer':
        return [xform(f0), xform(f0, sy=1.03), xform(f0, sy=1.05, sx=0.98), xform(f0, sy=1.03)]
    raise ValueError(op)

# ======================================================================= inputs ====
def _canon(stem):
    s = re.sub(r'[\s\-]+', '_', stem.lower())
    for mv, names in ALIASES.items():
        if s in names:
            return mv
    return None


def _frame_key(path):
    nums = re.findall(r'\d+', os.path.basename(path))
    return (int(nums[-1]) if nums else 0, path)


def discover(src):
    """-> {move: dict(kind='sheet'|'frames', paths=[...])}"""
    found = {}
    if os.path.isfile(src):
        return {'idle': dict(kind='sheet', paths=[src], photo=True)}
    entries = sorted(os.listdir(src))
    for e in entries:
        p = os.path.join(src, e)
        stem, ext = os.path.splitext(e)
        if os.path.isdir(p):
            mv = _canon(e)
            if mv:
                fr = sorted([os.path.join(p, x) for x in os.listdir(p) if x.lower().endswith(IMG_EXT)], key=_frame_key)
                if fr and mv not in found:
                    found[mv] = dict(kind='frames', paths=fr)
            continue
        if ext.lower() not in IMG_EXT:
            continue
        mv = _canon(stem)
        if mv:
            if mv not in found or found[mv]['kind'] == 'frames':
                found[mv] = dict(kind='sheet', paths=[p])
            continue
        m = re.match(r'(.+?)[_\-\s]?(\d+)$', stem)        # punch_01.png, walk-3.png
        if m and _canon(m.group(1)):
            mv = _canon(m.group(1))
            d = found.setdefault(mv, dict(kind='frames', paths=[]))
            if d['kind'] == 'frames':
                d['paths'].append(p)
    for d in found.values():
        if d['kind'] == 'frames':
            d['paths'].sort(key=_frame_key)
    if not found:
        imgs = [os.path.join(src, e) for e in entries if e.lower().endswith(IMG_EXT)]
        if len(imgs) == 1:
            return {'idle': dict(kind='sheet', paths=imgs, photo=True)}
    return found


def extract_raw(item, ov, choke):
    """unscaled cut-out frames of one source (sheet or frame folder)"""
    subs = []
    for p in item['paths']:
        a = load_rgba(p, ov.get('choke', choke))
        fr = split_wide(segment(a))
        if 'frames' in ov and item['kind'] == 'sheet':
            fr = split_even(fr, int(ov['frames']))
        if (item['kind'] == 'frames' or item.get('photo')) and len(fr) > 1:
            # one figure per frame file / photo: pieces split apart by the cut-out (an arm
            # separated by a keyed-out shirt) are merged into one figure.  A photo that
            # holds 3+ similar figures is treated as a sprite strip instead.
            sizes = sorted(f['size'] for f in fr)
            if item['kind'] == 'frames' or len(fr) < 3 or sizes[0] < 0.5 * sizes[-1]:
                mk = np.zeros_like(fr[0]['mask'])
                for f in fr:
                    mk |= f['mask']
                fr = [_frame(mk)]
        subs += [crop(a, f, ov.get('drop_stray', True)) for f in fr]
    if ov.get('fill_light_holes', True):
        subs = [fill_light_holes(x) for x in subs]
    if ov.get('fill_shirt'):
        col = ov['fill_shirt'] if isinstance(ov['fill_shirt'], list) else (232, 234, 230)
        subs = [fill_shirt_holes(x, tuple(col)) for x in subs]
    if item['kind'] == 'sheet':
        subs = dedupe_and_clean(subs)
    if 'pick' in ov:
        subs = [subs[i] for i in ov['pick'] if i < len(subs)]
    return [trim(s) for s in subs]

# ======================================================================= build =====
def build(name, src, out, height=480, layout='per-move', choke=0, preview=True, glow=None, fill_shirt=False):
    name = re.sub(r'[^A-Za-z0-9_.-]+', '_', name.strip()) or 'character'
    cfgj = {}
    if os.path.isdir(src) and os.path.exists(os.path.join(src, 'spriteforge.json')):
        cfgj = json.load(open(os.path.join(src, 'spriteforge.json')))
        log(f'overrides: {os.path.join(src, "spriteforge.json")}')
    height = int(cfgj.get('height', height))
    glow_rgb = tuple(cfgj.get('glow', glow or GLOW_RGB))
    movov = cfgj.get('moves', {})
    glob_ov = {k: cfgj[k] for k in ('fill_shirt', 'fill_light_holes', 'choke') if k in cfgj}
    if fill_shirt:
        glob_ov['fill_shirt'] = True
    movov = {m: dict(glob_ov, **movov.get(m, {})) for m in MOVES}
    found = discover(src)
    for mv, o in movov.items():                  # per-move "src" / "skip" overrides
        if o.get('skip'):
            found.pop(mv, None)
        elif 'src' in o and os.path.isdir(src):
            ps = o['src'] if isinstance(o['src'], list) else [o['src']]
            ps = [os.path.join(src, q) for q in ps]
            if len(ps) == 1 and os.path.isdir(ps[0]):
                ps = sorted([os.path.join(ps[0], x) for x in os.listdir(ps[0]) if x.lower().endswith(IMG_EXT)], key=_frame_key)
                found[mv] = dict(kind='frames', paths=ps)
            else:
                found[mv] = dict(kind='sheet' if len(ps) == 1 else 'frames', paths=ps)
    if not found:
        sys.exit(f'no usable images in {src} (expected e.g. idle.png, punch.png ... or one photo)')
    log(f'{name}: sources for ' + ', '.join(f'{m}({found[m]["kind"]})' for m in MOVES if m in found))
    raw = {}
    for mv in MOVES:
        if mv in found:
            subs = extract_raw(found[mv], movov.get(mv, {}), choke)
            if subs:
                raw[mv] = subs
                log(f'  {mv:10s} {len(subs)} poses from {", ".join(os.path.basename(p) for p in found[mv]["paths"][:3])}'
                    + (' ...' if len(found[mv]['paths']) > 3 else ''))
    if not raw:
        sys.exit('no figure found in the sources')
    # ---- one scale per source: body-area metric calibrated on an upright reference move
    ref_mv = next((m for m in ('idle', 'walk', 'block', 'hit', 'taunt', 'punch') if m in raw), next(iter(raw)))
    ref = raw[ref_mv]
    stand_ref = float(movov.get(ref_mv, {}).get('stand_h', max(s.shape[0] for s in ref)))
    K = np.median([size_metric(s) for s in ref]) / stand_ref       # sqrt(area) per px of height
    scaled, scale_of = {}, {}
    for mv, subs in raw.items():
        o = movov.get(mv, {})
        if 'stand_h' in o:
            st = float(o['stand_h'])
        elif mv == ref_mv:
            st = stand_ref
        else:
            # 35th percentile: attack effects / extended limbs only ever ADD area
            st = float(np.percentile([size_metric(s) for s in subs], 35)) / K
            if mv not in ('crouch', 'jump', 'jumpattack'):
                # upright move: the tallest pose is usually the standing height; trust it
                # while it agrees with the area estimate to within 10%
                st = float(np.clip(max(x.shape[0] for x in subs), 0.9 * st, 1.1 * st))
        s = height / st
        scale_of[mv] = s
        scaled[mv] = [trim(np.asarray(Image.fromarray(x).resize(
            (max(1, round(x.shape[1] * s)), max(1, round(x.shape[0] * s))), Image.LANCZOS))) for x in subs]
    # ---- fill missing moves (real sources preferred; chains allowed on later passes)
    origin = {m: 'real' for m in scaled}
    for mv in ('idle', 'taunt', 'victory', 'walk'):
        if mv in scaled and len(scaled[mv]) == 1:        # a single still: give it life
            scaled[mv] = apply_fallback({'walk': 'legswing'}.get(mv, 'bob'), scaled[mv], glow_rgb)
            origin[mv] = 'real+' + {'walk': 'legswing'}.get(mv, 'bob')
    for p in range(3):
        for mv in MOVES:
            if mv in scaled:
                continue
            for srcmv, op in FALLBACK[mv]:
                if srcmv == '*':
                    srcmv = next(iter(scaled))
                if srcmv in scaled and (origin[srcmv].startswith('real') or p == 2 or srcmv == 'idle'):
                    scaled[mv] = apply_fallback(op, scaled[srcmv], glow_rgb)
                    origin[mv] = f'{srcmv}:{op}'
                    break
    for mv in MOVES:
        if mv not in scaled:
            scaled[mv] = apply_fallback('same', scaled['idle'])
            origin[mv] = 'idle:same'
    for mv in MOVES:
        if not origin[mv].startswith('real'):
            log(f'  {mv:10s} <- {origin[mv]}  ({len(scaled[mv])} frames)')
    # ---- fixed canvas: common height, feet on one ground line, body centre on the cell centre
    data = {}
    for mv in MOVES:
        fr = []
        for f in scaled[mv]:
            rows = np.nonzero((f[..., 3] > 40).any(1))[0]   # feet = lowest SOLID row
            if len(rows):
                f = f[:int(rows.max()) + 1]
            fr.append((f, body_anchor_x(f)))
        data[mv] = fr
    half = max(max(ax, f.shape[1] - ax) for fr in data.values() for f, ax in fr)
    cell_w = int(math.ceil((2 * half + 8) / 8.0) * 8)
    tallest = max(f.shape[0] for fr in data.values() for f, _ in fr)
    margin = max(4, height // 40)
    cell_h = int(math.ceil((min(tallest, height * 1.6) + 2 * margin) / 8.0) * 8)
    ground = cell_h - margin
    os.makedirs(out, exist_ok=True)
    fdir = os.path.join(out, 'frames'); os.makedirs(fdir, exist_ok=True)
    for old in glob.glob(os.path.join(fdir, '*.png')):
        os.remove(old)
    sheets = {}
    for mv in MOVES:
        frames = data[mv]
        sheet = Image.new('RGBA', (cell_w * len(frames), cell_h), (0, 0, 0, 0))
        for i, (f, ax) in enumerate(frames):
            x = int(round(cell_w / 2 - ax))
            y = ground - f.shape[0]
            if y < 0:                       # taller than the cell (arms up): keep feet, clip top
                f = f[-y:]; y = 0
            if x < 0:
                f = f[:, -x:]; x = 0
            cell = Image.new('RGBA', (cell_w, cell_h))
            cell.alpha_composite(Image.fromarray(np.ascontiguousarray(f[:, :cell_w - x])), (x, y))
            sheet.alpha_composite(cell, (i * cell_w, 0))
            cell.save(os.path.join(fdir, f'{mv}_{i:02d}.png'), optimize=True)
        sheets[mv] = sheet
    lines = [f'# sprites.cfg - generated by spriteforge.py v{VERSION}',
             '# move <name> <file> <frames> <frame_w> <frame_h> <fps> <loop> <row>',
             '#   row  = which row of <file> holds the strip (0 when each move has its own file)',
             '#   loop = 1 loop forever, 0 play once and hold the last frame',
             '#   feet of every frame stand on y = ground; body centre is x = anchor_x',
             f'version {VERSION}', f'name {name}', f'frame {cell_w} {cell_h}',
             f'height {height}', f'ground {ground}', f'anchor_x {cell_w // 2}']
    if layout in ('combined', 'both'):
        maxn = max(len(data[m]) for m in MOVES)
        comb = Image.new('RGBA', (cell_w * maxn, cell_h * len(MOVES)))
        for r, mv in enumerate(MOVES):
            comb.alpha_composite(sheets[mv], (0, r * cell_h))
        comb.save(os.path.join(out, 'combined.png'), optimize=True)
    if layout in ('per-move', 'both'):
        for mv in MOVES:
            sheets[mv].save(os.path.join(out, f'{mv}.png'), optimize=True)
    for r, mv in enumerate(MOVES):
        fps, loop = TIMING[mv]
        o = movov.get(mv, {})
        fps, loop = float(o.get('fps', fps)), int(o.get('loop', loop))
        file, row = ('combined.png', r) if layout == 'combined' else (f'{mv}.png', 0)
        lines.append(f'move {mv} {file} {len(data[mv])} {cell_w} {cell_h} {fps:g} {loop} {row}'
                     f'   # {origin[mv]}' + (f', scale {scale_of[mv]:.3f}' if mv in scale_of else ''))
    with open(os.path.join(out, 'sprites.cfg'), 'w', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    if preview:
        contact_sheet(name, sheets, data, cell_w, cell_h, ground, origin, os.path.join(out, 'contact.png'))
    log(f'{name}: frame {cell_w}x{cell_h}, height {height}, ground {ground} -> {out}')
    return dict(cell_w=cell_w, cell_h=cell_h, ground=ground, origin=origin)


def contact_sheet(name, sheets, data, cell_w, cell_h, ground, origin, path, th=180):
    tw = max(1, int(cell_w * th / cell_h))
    maxn = max(len(data[m]) for m in MOVES)
    W = 150 + maxn * (tw + 4); H = len(MOVES) * (th + 6) + 30
    out = Image.new('RGB', (W, H), (48, 52, 60)); d = ImageDraw.Draw(out)
    d.text((6, 8), f'{name} - red = ground line, blue = body centre, grey = filled from', fill=(255, 255, 255))
    for r, mv in enumerate(MOVES):
        y = 30 + r * (th + 6); n = len(data[mv])
        d.text((6, y + th // 2 - 8), f'{mv} ({n})', fill=(255, 230, 120))
        if origin[mv] != 'real':
            d.text((6, y + th // 2 + 6), '<- ' + origin[mv], fill=(170, 170, 170))
        for i in range(n):
            c = sheets[mv].crop((i * cell_w, 0, (i + 1) * cell_w, cell_h)).resize((tw, th), Image.LANCZOS)
            bg = Image.new('RGBA', (tw, th), (150, 160, 175, 255)); bg.alpha_composite(c)
            x = 150 + i * (tw + 4); out.paste(bg.convert('RGB'), (x, y))
            by = y + int(ground * th / cell_h)
            d.line([(x, by), (x + tw, by)], fill=(255, 0, 0)); d.line([(x + tw // 2, y), (x + tw // 2, y + th)], fill=(0, 90, 255))
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description='SpriteForge: character sprite sheets from existing images')
    ap.add_argument('--name', required=True, help='character name (written to sprites.cfg)')
    ap.add_argument('--src', required=True, help='folder of per-move sheets/frames, or one photo')
    ap.add_argument('--out', required=True, help='output folder (e.g. assets/<name>)')
    ap.add_argument('--height', type=int, default=480, help='standing character height in px (default 480)')
    ap.add_argument('--layout', choices=['per-move', 'combined', 'both'], default='per-move')
    ap.add_argument('--choke', type=int, default=0, help='erode the cut-out edge by N px (extra halo kill)')
    ap.add_argument('--glow', default=None, help='aura colour for filled specials, e.g. 255,120,40')
    ap.add_argument('--fill-shirt', action='store_true', help='paint see-through holes in the upper torso (keyed-out white shirt)')
    ap.add_argument('--no-preview', action='store_true')
    a = ap.parse_args()
    glow = tuple(int(v) for v in a.glow.split(',')) if a.glow else None
    build(a.name, a.src, a.out, a.height, a.layout, a.choke, not a.no_preview, glow, a.fill_shirt)


if __name__ == '__main__':
    main()
