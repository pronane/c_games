#!/usr/bin/env python3
"""
Egyptian Fighter - sprite sheet rebuilder.

Takes raw AI-generated sprite strips (unevenly spaced, overlapping, tiled/duplicated,
drawn at different scales, sometimes on an opaque background) and rebuilds them into
clean uniform-grid strips that the game can slice exactly:

  * background -> alpha (flood fill from the edges against a fitted background model,
    so white shirts / white gis are never keyed out)
  * every pose found by connected components (small detached bits such as a racket,
    a book or a hand are merged into the nearest figure; touching poses are split at
    the thinnest column)
  * exact duplicates (tiled strips) and cut-off slivers dropped
  * every pose scaled with ONE scale per source sheet so the character keeps the same
    size in every animation, then placed in a fixed cell, feet on a common baseline,
    body centre on the cell centre
  * optional procedural walk: when a walk strip has no leg movement (the same stride
    copied N times) the two legs are cut apart at the crotch and swung past each other
    with a hip-pivot shear, giving a real alternating step from the existing art
  * writes <out>/<folder>/<anim>.png and <out>/<folder>/sprites.cfg

Usage:  python tools/build_sprites.py            (uses SPEC below, writes ./assets)
        python tools/build_sprites.py --preview  (also writes contact sheets to ./preview)
Needs:  pip install pillow numpy scipy
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'sprite_sources')

# --------------------------------------------------------------------------------------
# What to build.  stand_h = height in SOURCE pixels that a fully upright figure has in
# that sheet (used to give every sheet of a character the same scale).
#   pick   : which detected poses to use, in order (after duplicate removal)
#   pwalk  : build an 8-frame procedural walk from pose index `pwalk`
#   fill_shirt : repaint enclosed see-through holes in the torso (shirt keyed out
#                by an earlier background removal) with an off-white shirt colour
#   ft     : seconds per frame
# --------------------------------------------------------------------------------------
SPEC = {
    'char_mike': {            # PADEL MIKE - black "I love HYROX" vest
        'idle':  dict(src='mike_hyrox/idle.png',          stand_h=912, fill_print=True, ft=0.14),
        'walk':  dict(src='mike_hyrox/walk.png',          stand_h=925, fill_print=True, pwalk=0, ft=0.085),
        'block': dict(src='mike_hyrox/ready_stance.png',  stand_h=1010, fill_print=True, pick=[0, 1, 2, 3, 4, 5], ft=0.12),
    },
    'char_dec': {             # navy suit / patterned tie (see README: Dec or Daragh?)
        'idle':   dict(src='suit_man/idle.png',   stand_h=912, fill_shirt=True, ft=0.16),
        'walk':   dict(src='suit_man/walk.png',   stand_h=925, fill_shirt=True, pwalk=0, ft=0.085),
        'crouch': dict(src='suit_man/crouch.png', stand_h=800, fill_shirt=True, pick=[0, 2, 4, 5], ft=0.06),
        'jump':   dict(src='suit_man/jump.png',   stand_h=640, fill_shirt=True, ft=0.11),
        'punch':  dict(src='suit_man/punch.png',  stand_h=925, fill_shirt=True, pick=[0, 1, 2, 3, 4, 5], ft=0.06),
        'kick':   dict(src='suit_man/kick.png',   stand_h=925, fill_shirt=True, pick=[0, 1, 2, 3, 4, 5], ft=0.07),
        'block':  dict(src='suit_man/punch.png',  stand_h=925, fill_shirt=True, pick=[0, 1], ft=0.2),
        'throw':  dict(src='suit_man/throw.png',  stand_h=850, ft=0.08),
        'hit':    dict(src='suit_man/hit.png',    stand_h=835, fill_shirt=True, pick=[0, 2, 4, 5], ft=0.09,
                       xform=[dict(i=0, tint=(255, 40, 40, 0.45)), dict(i=1, tint=(255, 40, 40, 0.3)), dict(i=2), dict(i=3)]),
        # extra moves made from his REAL frames (re-timed, transformed, purple magic glow;
        # the book / card projectile itself is drawn by the game)
        'pyramid_blast': dict(src='suit_man/throw.png', stand_h=850, ft=0.08,
                              xform=[dict(i=0), dict(i=1), dict(i=2, glow=(170, 70, 255)), dict(i=3, glow=(170, 70, 255)),
                                     dict(i=4, glow=(170, 70, 255)), dict(i=5)]),
        'bum_fireball': dict(src='suit_man/punch.png', stand_h=925, fill_shirt=True, ft=0.07,
                             xform=[dict(i=0), dict(i=1), dict(i=2, glow=(200, 90, 255)), dict(i=3, glow=(200, 90, 255)),
                                    dict(i=4), dict(i=5)]),
        'jump_attack': dict(src='suit_man/kick.png', stand_h=925, fill_shirt=True, pick=[1, 2, 3, 4], ft=0.08),
        'taunt': dict(src='suit_man/punch.png', stand_h=925, fill_shirt=True, pick=[0, 1], ft=0.12,
                      xform=[dict(i=0), dict(i=1, lean=-5, glow=(170, 70, 255)), dict(i=0, sy=1.02),
                             dict(i=1, lean=-5, glow=(170, 70, 255)), dict(i=0, sy=1.02), dict(i=1, glow=(170, 70, 255))]),
        'victory': dict(src='suit_man/jump.png', stand_h=640, fill_shirt=True, ft=0.14,
                        xform=[dict(i=4), dict(i=5, sy=1.02), dict(i=6, sy=1.03), dict(i=5, sy=0.98), dict(i=6, sy=1.03), dict(i=6)]),
    },
}
SPEC['char_daragh'] = {      # white "LONDON" t-shirt, navy shorts, padel racket
    # his source idle/block strip (mike_london/block.png) is cut off at the knees (no feet),
    # so every move is posed from the full-length walk frame (see RIGS / tools/poses.py)
    'idle': dict(proc='idle_bob', ft=0.18),
    'walk': dict(src='mike_london/walk.png', stand_h=900, fill_shirt=True, pwalk=0, pwalk_crotch=0.64, pwalk_prop=True, pwalk_clone=True, ft=0.085),
}
# procedural moves (poses.py) for the two padel players; Mike keeps his real ready-stance block
PROC_MOVES = dict(crouch=('crouch', 0.06), jump=('jump', 0.11), punch=('punch', 0.06), kick=('kick', 0.07),
                  pyramid_blast=('special1', 0.08), bum_fireball=('special2', 0.08), block=('block', 0.15),
                  hit=('hit', 0.09), throw=('throw', 0.08), jump_attack=('jump_attack', 0.08),
                  taunt=('taunt', 0.12), victory=('victory', 0.14))
for _ch in ('char_mike', 'char_daragh'):
    for _anim, (_mv, _ft) in PROC_MOVES.items():
        if _anim not in SPEC[_ch]:
            SPEC[_ch][_anim] = dict(proc=_mv, ft=_ft)
# racket swing glow on Mike's specials (padel-ball yellow)
SPEC['char_mike']['pyramid_blast']['glow'] = (220, 255, 70)
SPEC['char_mike']['bum_fireball']['glow'] = (220, 255, 70)
# Mike: FRONT-ON double-biceps from his front photo, turns round, flexes from behind, turns
# back; frames 1.. loop (tools/front_flex.py).  The old side-on version: proc='flex'
SPEC['char_mike']['victory'] = dict(front='mike_hyrox/idle.png', stand_h=912, ft=0.13, loop=1)
# Daragh: turns round, bends over and a speech bubble comes out of his backside
SPEC['char_daragh']['pyramid_blast'] = dict(proc='bum1', ft=0.075)
SPEC['char_daragh']['bum_fireball'] = dict(proc='bum2', ft=0.075)
# base frame each rig is cut from (first pose of the walk strip, scaled)
RIG_BASE = {
    'char_mike': dict(src='mike_hyrox/walk.png', stand_h=925, base=0, fill_print=True),
    'char_daragh': dict(src='mike_london/walk.png', stand_h=900, fill_shirt=True, base=0),
}
# projectile drawn by the game for the specials (see sprites.cfg 'projectile')
PROJECTILE = {'char_mike': 'ball', 'char_daragh': 'bubble', 'char_dec': 'book'}

# Part maps for the procedural moves (coordinates are in the scaled base frame: the first
# walk pose after scaling to TARGET_STAND, trimmed).  box = x0,y0,x1,y1 of the arm,
# pivot = shoulder, ellipses = extra areas (e.g. a racket head).  See tools/poses.py.
RIGS = {
    'char_mike': dict(arms={
        'arm_f': dict(box=(140, 165, 224, 300), pivot=(138, 170), elbow=(163, 224), behind=True),
        'arm_r': dict(box=(22, 150, 62, 312), pivot=(50, 150), elbow=(46, 230), ellipses=[(106, 324, 52, 50)],
                      cut_legs=True, fill_rgb=(30, 30, 33),
                      # outline of his shorts where the racket head hangs over them
                      cloth_poly=[(58, 262), (142, 262), (149, 300), (149, 356), (82, 374), (60, 368)]),
    }),
    'char_daragh': dict(crotch=0.64, prop=True, clone_leg=True, waist=282, arms={
        'arm_f': dict(box=(190, 175, 270, 312), pivot=(188, 178), behind=True),
        'arm_r': dict(box=(55, 160, 101, 330), pivot=(92, 165), with_prop=True),
    }),
}

TARGET_STAND = 560     # upright figure height in the rebuilt cells (px)
CELL_H = 800
BASELINE = 788         # feet line inside the cell
SHIRT_RGB = (232, 234, 230)
# sheets are composed at TARGET_STAND and then saved at OUT_SCALE.  1.0 = full resolution
# (a fighter is ~560 px tall in the sheet; on a 4K TV he is drawn ~900 px tall, on 1080p
# ~450 px, so full-res frames keep him sharp on a big screen).  0.75 halves the zip size.
OUT_SCALE = 1.0

# ---------------------------------------------------------------- background removal --
def load_rgba(path):
    a = np.array(Image.open(path).convert('RGBA'))
    if (a[..., 3] < 20).mean() > 0.2:
        a[..., :3][a[..., 3] == 0] = 0
        return a
    return remove_opaque_bg(a)

def remove_opaque_bg(a):
    rgb = a[..., :3].astype(float)
    h, w, _ = rgb.shape
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    design = lambda y, x: np.stack([np.ones_like(y), x, y, x * x, y * y, x * y], -1)
    sel = np.zeros((h, w), bool); sel[:30] = 1; sel[:, :10] = 1; sel[:, -10:] = 1
    for _ in range(3):        # fit a smooth background, re-select pixels that match it
        coef, *_ = np.linalg.lstsq(design(yy[sel], xx[sel]), rgb[sel], rcond=None)
        res = np.abs(rgb - design(yy, xx) @ coef).sum(-1)
        sel = res < 25
    lab, n = ndi.label(res < 30)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(border))
    lab2, n2 = ndi.label(res < 16)            # enclosed background pockets (arm/body gaps)
    if n2:
        sz = ndi.sum(np.ones_like(res), lab2, range(1, n2 + 1))
        bg |= np.isin(lab2, np.where(sz > 600)[0] + 1)
    out = a.copy()
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    ring = ndi.binary_dilation(bg) & ~bg
    alpha[ring] = 150
    out[..., 3] = alpha
    out[..., :3][alpha == 0] = 0
    return out

# -------------------------------------------------------------------- segmentation ----
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
        mask = np.isin(lab, [k + 1 for k in mem])
        frames.append(_frame(mask))
    frames.sort(key=lambda f: f['x0'])
    return frames

def _frame(mask):
    ys, xs = np.nonzero(mask)
    return dict(mask=mask, x0=xs.min(), x1=xs.max() + 1, y0=ys.min(), y1=ys.max() + 1, size=int(mask.sum()))

def split_wide(frames):
    """Split blobs that are two (or more) touching poses at the thinnest column."""
    if not frames:
        return frames
    ws = np.array([f['x1'] - f['x0'] for f in frames], float)
    # typical single-pose width = the most common width cluster (ties -> narrower)
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
            if mk.sum() > 0.2 * f['size'] / k:
                out.append(_frame(mk))
    out.sort(key=lambda f: f['x0'])
    return out

def crop(a, f):
    sub = a[f['y0']:f['y1'], f['x0']:f['x1']].copy()
    keep = f['mask'][f['y0']:f['y1'], f['x0']:f['x1']]
    sub[~keep] = 0
    return sub

def dedupe_and_clean(subs):
    """Drop pixel-identical repeats (tiled strips) and cut-off slivers."""
    if not subs:
        return subs
    hs = np.array([s.shape[0] for s in subs]); ws = np.array([s.shape[1] for s in subs])
    medw = np.median(ws)
    keep, sigs = [], []
    for s in subs:
        if s.shape[1] < 0.62 * medw and s.shape[0] > 0.8 * hs.max():
            continue                       # vertical sliver of a neighbouring pose
        sig = np.asarray(Image.fromarray(s).resize((32, 64), Image.BILINEAR), float)
        if any(np.abs(sig - o).mean() < 2.0 for o in sigs):
            continue                       # exact repeat
        sigs.append(sig); keep.append(s)
    return keep

def fill_shirt_holes(sub):
    """Enclosed transparent pockets in the upper torso were a white shirt that an earlier
    colour-key removed.  Paint them back in an off-white shirt tone."""
    m = sub[..., 3] > 40
    holes = ndi.binary_fill_holes(m) & ~m
    lab, n = ndi.label(holes)
    h, w = m.shape
    ys, xs = np.nonzero(m)
    top = ys.min(); hgt = ys.max() - top
    for i, sl in enumerate(ndi.find_objects(lab)):
        reg = lab[sl] == i + 1
        cy = (sl[0].start + sl[0].stop) / 2
        if reg.sum() < 12:
            sub[sl][reg] = sub[sl][reg]; continue
        if top + 0.08 * hgt < cy < top + 0.48 * hgt:
            px = sub[sl]
            shade = np.linspace(1.0, 0.9, reg.shape[0])[:, None]
            for c in range(3):
                px[..., c] = np.where(reg, (SHIRT_RGB[c] * shade).astype(np.uint8), px[..., c])
            px[..., 3] = np.where(reg, 255, px[..., 3])
    # semi-transparent shirt fringe -> make opaque light
    return sub

def body_anchor_x(sub):
    """Weighted median column of the figure's mass: stays on the body when an arm,
    a leg, a racket or a thrown object sticks out."""
    col = (sub[..., 3] > 40).sum(0).astype(float)
    c = np.cumsum(col)
    return float(np.searchsorted(c, c[-1] / 2)) + 0.5

# ---------------------------------------------------------------- procedural walk -----
def leg_rig(sub, hip_frac=0.07, crotch_frac=None, prop_overlay=False):
    """Find the crotch by following the gap between the legs upwards, then split the figure
    into: far (back) leg, near (front) leg, the rest of the body, and an optional hand-held
    prop overlay.  Used by the walk cycle and by the procedural moves (tools/poses.py)."""
    a = sub
    solid = a[..., 3] > 40
    anyp = a[..., 3] > 0
    h, w = solid.shape
    # 1) follow the gap between the legs from the ankles upwards -> crotch apex
    y = int(h * 0.88)
    runs = sorted([r for r in _runs(solid[y]) if r[1] - r[0] > 3], key=lambda r: r[1] - r[0])[-2:]
    if len(runs) < 2:
        return None
    runs.sort()
    gx = (runs[0][1] + runs[1][0]) / 2.0
    centers = {}
    while y > h * 0.3:
        row = solid[y]
        xi = int(round(gx))
        if row[xi]:
            # look for the nearest background column within a small window
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
        if l == 0 or r == w - 1:      # gap opened to the outside -> not between legs
            break
        gx = (l + r) / 2.0
        centers[y] = gx
        y -= 1
    if not centers:
        return None
    crotch = min(centers)
    cx = centers[crotch]
    if crotch_frac is not None and int(crotch_frac * h) < crotch:
        # gap is occluded (e.g. a racket hangs in front of the thighs): extend it upwards
        for yy_ in range(int(crotch_frac * h), crotch):
            centers[yy_] = cx
        crotch = int(crotch_frac * h)
    pivot = max(0, crotch - int(hip_frac * h))
    # continue split line below the tracked gap (ankles/feet)
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
    overlay = None
    if prop_overlay:
        # a hand-held prop (padel racket: near-black + neon yellow) hanging over the thighs
        # must not swing with the legs; lift it into an overlay drawn on top of everything
        rgb = a[..., :3].astype(int)
        lum = rgb.mean(-1)
        yel = (rgb[..., 0] > 140) & (rgb[..., 1] > 140) & (rgb[..., 2] < 110)
        prop = (back | front) & (YY < int(h * 0.80)) & (((lum < 75) & (rgb[..., 2] - rgb[..., 0] < 14)) | yel)
        prop = ndi.binary_closing(prop, iterations=2) & anyp & (YY < int(h * 0.80))
        lab2, n2 = ndi.label(prop)
        if n2:
            sz = ndi.sum(prop, lab2, range(1, n2 + 1))
            prop = np.isin(lab2, 1 + np.nonzero(sz > 0.2 * sz.max())[0])
            overlay = np.zeros_like(a); overlay[prop] = a[prop]
            back &= ~prop; front &= ~prop
    # below the crotch the legs are separate blobs: assign by connected component so a
    # raised heel or angled shoe that crosses the split line stays with its own leg
    below = (YY > crotch + 1) & anyp
    if overlay is not None:
        below &= overlay[..., 3] == 0
    lab, nl = ndi.label(below, structure=np.ones((3, 3)))
    if nl >= 2:
        sizes = ndi.sum(below, lab, range(1, nl + 1))
        order = np.argsort(sizes)[::-1][:2] + 1
        if sizes[order[1] - 1] > 0.15 * sizes[order[0] - 1]:
            cxs = [np.nonzero(lab == k)[1].mean() for k in order]
            kb, kf = (order[0], order[1]) if cxs[0] < cxs[1] else (order[1], order[0])
            back[lab == kb] = True; front[lab == kb] = False
            front[lab == kf] = True; back[lab == kf] = False
            # remaining small pieces (e.g. a knee peeking out beside a racket) follow the
            # nearer main leg
            db = ndi.distance_transform_edt(lab != kb)
            df = ndi.distance_transform_edt(lab != kf)
            for k in range(1, nl + 1):
                if k in (kb, kf):
                    continue
                m = lab == k
                to_back = db[m].min() < df[m].min()
                back[m] = to_back; front[m] = not to_back
    lo = int(h * 0.85)
    bx = np.nonzero(back[lo:] & solid[lo:])[1]
    fx = np.nonzero(front[lo:] & solid[lo:])[1]
    if len(bx) == 0 or len(fx) == 0:
        return None
    B = bx.mean() - cx; F = fx.mean() - cx
    mid, amp = (F + B) / 2, (F - B) / 2
    if prop_overlay:
        # shorts stay with the body; only the bare thighs/shins/shoes swing
        rgb = a[..., :3].astype(int)
        navy = (rgb[..., 2] - rgb[..., 0] > 14) & (rgb.mean(-1) < 90) & (YY < crotch + int(0.1 * h))
        back &= ~navy; front &= ~navy
    base = a.copy(); base[back | front] = 0
    fy = h - 1
    return dict(a=a, back=back, front=front, base=base, overlay=overlay, pivot=pivot, cx=cx,
                crotch=crotch, B=B, F=F, mid=mid, amp=amp, h=h, w=w, fy=fy)


def procedural_walk(sub, n=8, hip_frac=0.07, crotch_frac=None, prop_overlay=False, clone_front=False):
    """Cut the two legs apart below the crotch and swing them past each other about a
    hip pivot, so the near leg and far leg genuinely alternate.  Feet stay on the floor."""
    r = leg_rig(sub, hip_frac, crotch_frac, prop_overlay)
    if r is None:
        return [sub] * n
    a, back, front, base, overlay = r['a'], r['back'], r['front'], r['base'], r['overlay']
    pivot, cx, B, F, mid, amp, h, w = r['pivot'], r['cx'], r['B'], r['F'], r['mid'], r['amp'], r['h'], r['w']
    src_b, B_use = a, B
    if clone_front:
        # far leg is mostly hidden in the source (behind a prop): use a slightly darker copy
        # of the complete near leg as the far leg instead
        src_b = a.copy(); src_b[..., :3] = (src_b[..., :3] * 0.82).astype(np.uint8)
        back, B_use = front, F
    pad = int(abs(amp) * 2 + 12)
    fy = h - 1
    frames = []
    for k in range(n):
        ph = 2 * math.pi * k / n
        c = math.cos(ph)
        off_f = mid + amp * c - F
        off_b = mid - amp * c - B_use
        out = np.zeros((h, w + 2 * pad, 4), np.uint8)
        img = Image.new('RGBA', (w + 2 * pad, h))

        def leg(layer, srcimg, off, foot, lift):
            L = np.zeros_like(out)
            L[:, pad:pad + w][layer] = srcimg[layer]
            hx, hy = cx + pad, pivot
            fx_, fy_ = cx + foot + pad, fy - 0.04 * h
            dy = fy_ - hy
            a0 = math.atan2(fx_ - hx, dy)
            ln = math.hypot(fx_ - hx, dy)
            a1 = math.asin(max(-0.95, min(0.95, (fx_ + off - hx) / ln)))
            # ROTATE about the hip (shape-preserving: shin and shoe stay rigid)
            li = Image.fromarray(L).rotate(math.degrees(a1 - a0), resample=Image.BICUBIC,
                                           center=(hx, hy))
            ly = int(round(lift * 0.035 * h))
            if ly:
                li = li.transform(li.size, Image.AFFINE, (1, 0, 0, 0, 1, ly), resample=Image.BICUBIC)
            return li
        # draw order: body, far leg, near leg -- or, with a prop, far leg behind the body
        bimg = np.zeros_like(out); bimg[:, pad:pad + w] = base
        bimg = Image.fromarray(bimg)
        bl = leg(back, src_b, off_b, B_use, max(0.0, math.sin(ph)))
        if prop_overlay:
            img.alpha_composite(bl); img.alpha_composite(bimg)
        else:
            img.alpha_composite(bimg); img.alpha_composite(bl)
        img.alpha_composite(leg(front, a, off_f, F, max(0.0, -math.sin(ph))))
        if overlay is not None:
            ov = np.zeros_like(out); ov[:, pad:pad + w] = overlay
            img.alpha_composite(Image.fromarray(ov))
        out = np.asarray(img).copy()
        frames.append(out)
    return frames

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

# ---------------------------------------------------------------------- building ------
_RIGS = {}

def get_rig(folder):
    if folder not in _RIGS:
        import poses
        b = RIG_BASE[folder]
        frames = extract(dict(src=b['src'], stand_h=b['stand_h'], fill_shirt=b.get('fill_shirt', False),
                              fill_print=b.get('fill_print', False)))
        base = frames[b['base']]
        rig = poses.Rig(base, RIGS[folder], leg_rig)
        rest, _ = rig.pose()
        # anchor every posed frame on the same body column the walk frames use
        t, anc_t = poses.trim_with_anchor(rest, rig.anchor)
        rig.ref_anchor = rig.anchor + (body_anchor_x(t) - anc_t)
        _RIGS[folder] = rig
    return _RIGS[folder]

def extract_proc(folder, spec):
    """frames posed from the base photo (no new imagery): list of (frame, anchor_x)"""
    import poses
    rig = get_rig(folder)
    out = []
    keys = poses.moves()[spec['proc']]
    for i, k in enumerate(keys):
        k = dict(k)
        if spec.get('glow') and 1 <= i < len(keys) - 1:
            k['glow'] = spec['glow']
        arr, anc = rig.pose(**k)
        anc = anc - rig.anchor + rig.ref_anchor     # same body column as the walk
        if k.get('flip'):                           # pose() mirrored the frame
            anc = arr.shape[1] - 1 - anc
        out.append(poses.trim_with_anchor(arr, anc))
    return out

def xform_frame(f, x):
    """re-use a REAL frame with a small transform: lean (deg, + forward, about the feet),
    sx/sy squash about the feet, tint=(r,g,b,k) flash, glow=(r,g,b) magic aura"""
    import poses
    pad = 120
    a = np.pad(f, ((pad, 4), (pad, pad), (0, 0)))
    im = Image.fromarray(a)
    fx, fy = pad + body_anchor_x(f), float(pad + f.shape[0] - 1)
    sx, sy = x.get('sx', 1.0), x.get('sy', 1.0)
    if (sx, sy) != (1.0, 1.0):
        im = im.transform(im.size, Image.AFFINE, (1 / sx, 0, fx - fx / sx, 0, 1 / sy, fy - fy / sy), resample=Image.BICUBIC)
    if x.get('lean'):
        im = im.rotate(-x['lean'], resample=Image.BICUBIC, center=(fx, fy))
    a = np.asarray(im).copy()
    if 'tint' in x:
        r, g, b, k = x['tint']
        m = a[..., 3] > 0
        a[m, :3] = (a[m, :3] * (1 - k) + np.array([r, g, b]) * k).astype(np.uint8)
    if 'glow' in x:
        a = poses.add_glow(a, x['glow'])
    return trim(a)

def split_even(frames, n):
    """sheets whose poses touch each other (one big blob): cut the widest blob at the
    emptiest column near the expected boundary until there are n poses"""
    frames = list(frames)
    total = sum(f['x1'] - f['x0'] for f in frames)
    ew = total / float(n)
    while len(frames) < n:
        f = max(frames, key=lambda f: f['x1'] - f['x0'])
        w = f['x1'] - f['x0']
        k = max(2, int(round(w / ew)))
        col = f['mask'][:, f['x0']:f['x1']].sum(0).astype(float)
        c = int(w / k); r = int(ew * 0.35)
        lo, hi = max(1, c - r), min(w - 1, c + r)
        cut = lo + int(np.argmin(col[lo:hi]))
        frames = [g for g in frames if g is not f]
        for s, e in ((0, cut), (cut, w)):
            mk = np.zeros_like(f['mask'])
            mk[:, f['x0'] + s:f['x0'] + e] = f['mask'][:, f['x0'] + s:f['x0'] + e]
            # keep only the main body of each half (drops slivers of the neighbour)
            lab, nn = ndi.label(mk, structure=np.ones((3, 3)))
            if nn > 1:
                sz = ndi.sum(mk, lab, range(1, nn + 1))
                mk = np.isin(lab, 1 + np.nonzero(sz >= 0.05 * sz.max())[0])
            frames.append(_frame(mk))
        frames.sort(key=lambda f: f['x0'])
    return frames

def extract(spec):
    a = load_rgba(os.path.join(SRC, spec['src']))
    fr = split_wide(segment(a))
    if 'nsplit' in spec:
        fr = split_even(fr, spec['nsplit'])
    subs = dedupe_and_clean([crop(a, f) for f in fr])
    if 'pick' in spec:
        subs = [subs[i] for i in spec['pick'] if i < len(subs)]
    if spec.get('fill_shirt'):
        subs = [fill_shirt_holes(s) for s in subs]
    if spec.get('fill_print'):      # see-through vest print (keyed-out white letters / bib)
        import front_flex
        subs = [front_flex.fill_print_holes(s) for s in subs]
    s = TARGET_STAND / float(spec['stand_h'])
    scaled = []
    for sub in subs:
        im = Image.fromarray(sub)
        im = im.resize((max(1, round(sub.shape[1] * s)), max(1, round(sub.shape[0] * s))), Image.LANCZOS)
        scaled.append(np.asarray(im))
    if 'pwalk' in spec:
        base = scaled[spec['pwalk']]
        scaled = procedural_walk(trim(base), crotch_frac=spec.get('pwalk_crotch'),
                                     prop_overlay=spec.get('pwalk_prop', False),
                                     clone_front=spec.get('pwalk_clone', False))
        if 'pwalk_pick' in spec:
            scaled = [scaled[i] for i in spec['pwalk_pick']]
    scaled = [trim(x) for x in scaled]
    if 'xform' in spec:
        scaled = [xform_frame(scaled[x['i']], x) for x in spec['xform']]
    return scaled

def trim(sub):
    m = sub[..., 3] > 8
    ys, xs = np.nonzero(m)
    return sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

def build_character(folder, anims, out_root):
    data = {}
    for name, spec in anims.items():
        if 'front' in spec:
            import front_flex
            base = extract(dict(src=spec['front'], stand_h=spec['stand_h'], fill_print=True))[0]
            fr, _ = front_flex.build(base)
        else:
            fr = extract_proc(folder, spec) if 'proc' in spec else extract(spec)
        data[name] = [x if isinstance(x, tuple) else (x, body_anchor_x(x)) for x in fr]
    # one cell width for the whole character (widest half-extent around the anchor)
    half = 0
    for frames in data.values():
        for f, ax in frames:
            half = max(half, ax, f.shape[1] - ax)
    cell_w = int(math.ceil((2 * half + 16) / 16.0) * 16)
    os.makedirs(os.path.join(out_root, folder), exist_ok=True)
    cfg = ['# generated by tools/build_sprites.py - uniform grid sheets',
           f'cell {round(cell_w * OUT_SCALE)} {round(CELL_H * OUT_SCALE)}',
           f'baseline {round(BASELINE * OUT_SCALE)}', f'stand_height {round(TARGET_STAND * OUT_SCALE)}']
    sheets = {}
    for name, frames in data.items():
        sheet = Image.new('RGBA', (cell_w * len(frames), CELL_H), (0, 0, 0, 0))
        for i, (f, ax) in enumerate(frames):
            x = int(round(i * cell_w + cell_w / 2 - ax))
            y = BASELINE - f.shape[0]
            if y < 0:   # taller than the cell (arms up): keep feet, clip top
                f = f[-y:]; y = 0
            sheet.alpha_composite(Image.fromarray(f), (x, y))
        if OUT_SCALE != 1.0:
            sheet = sheet.resize((round(sheet.width * OUT_SCALE), round(CELL_H * OUT_SCALE)), Image.LANCZOS)
        sheet.save(os.path.join(out_root, folder, name + '.png'), optimize=True)
        cfg.append(f'anim {name} {name}.png {len(frames)} {anims[name].get("ft", 0.1):.3f}')
        if 'loop' in anims[name]:
            cfg.append(f'loop {name} {anims[name]["loop"]}')
        sheets[name] = (sheet, len(frames))
    if folder in PROJECTILE:
        cfg.append(f'projectile {PROJECTILE[folder]}')
    with open(os.path.join(out_root, folder, 'sprites.cfg'), 'w') as fh:
        fh.write('\n'.join(cfg) + '\n')
    print(f'{folder}: cell {cell_w}x{CELL_H}  ' + '  '.join(f'{k}:{v[1]}' for k, v in sheets.items()))
    return cell_w, sheets

# head-and-shoulders picture for the PADEL WARS face-off, cut from a real frame at the
# photo's own resolution (sharper than the game sprites).  The game looks for
# assets/<folder>/portrait.png and otherwise cuts one from the idle sheet itself.
PORTRAIT = {
    'char_mike':   dict(src='mike_hyrox/idle.png', i=0, fill_print=True),
    'char_daragh': dict(src='mike_london/walk.png', i=0, fill_shirt=True),
    'char_dec':    dict(src='suit_man/idle.png', i=0, fill_shirt=True),
}

def build_portrait(folder, out_root):
    if folder not in PORTRAIT:
        return
    p = PORTRAIT[folder]
    a = load_rgba(os.path.join(SRC, p['src']))
    subs = dedupe_and_clean([crop(a, f) for f in split_wide(segment(a))])
    sub = subs[p.get('i', 0)]
    if p.get('fill_shirt'):
        sub = fill_shirt_holes(sub)
    if p.get('fill_print'):
        import front_flex
        sub = front_flex.fill_print_holes(sub)
    sub = trim(sub)
    if p.get('fill_shirt'):
        # close the see-through specks left in a white shirt by the background keying
        import poses
        m0 = sub[..., 3] > 60
        yy, xx = np.mgrid[-6:7, -6:7]
        closed = ndi.binary_fill_holes(ndi.binary_closing(np.pad(m0, 8), structure=(xx * xx + yy * yy) <= 36))[8:-8, 8:-8]
        solid = sub[..., 3] >= 250
        new = ndi.binary_erosion(closed, iterations=2) & ~solid
        m0 = solid
        if new.any():
            sub = sub.copy()
            sub[..., :3] = poses._diffuse_fill(sub[..., :3], m0, new, iters=30)
            sub[new, 3] = 255
    m = sub[..., 3] > 60
    ys, xs = np.nonzero(m)
    y0, H = ys.min(), ys.max() - ys.min() + 1
    head = m[y0:y0 + int(H * 0.12)]
    hx = np.nonzero(head)[1].mean()
    ch = int(H * 0.36); cw = int(ch * 0.82)
    x0 = int(round(hx - cw / 2)); top = max(0, int(y0 - H * 0.03))
    canvas = np.zeros((ch, cw, 4), np.uint8)
    sx0, sx1 = max(0, x0), min(sub.shape[1], x0 + cw)
    piece = sub[top:top + ch, sx0:sx1]
    canvas[:piece.shape[0], sx0 - x0:sx0 - x0 + piece.shape[1]] = piece
    Image.fromarray(canvas).save(os.path.join(out_root, folder, 'portrait.png'), optimize=True)
    print(f'{folder}: portrait {cw}x{ch}')

def contact_sheet(folder, cell_w, sheets, path):
    th = 200; tw = int(cell_w * th / CELL_H)
    rows = list(sheets.items()); maxn = max(n for _, (_, n) in rows)
    W = 110 + maxn * (tw + 4); H = len(rows) * (th + 6) + 30
    out = Image.new('RGB', (W, H), (48, 52, 60)); d = ImageDraw.Draw(out)
    d.text((6, 8), f'{folder} - rebuilt frames (red line = feet baseline, blue = body centre)', fill=(255, 255, 255))
    for r, (name, (sheet, n)) in enumerate(rows):
        y = 30 + r * (th + 6)
        d.text((6, y + th // 2), f'{name} ({n})', fill=(255, 230, 120))
        for i in range(n):
            cw = sheet.width // n
            c = sheet.crop((i * cw, 0, (i + 1) * cw, sheet.height)).resize((tw, th), Image.LANCZOS)
            bg = Image.new('RGBA', (tw, th), (150, 160, 175, 255)); bg.alpha_composite(c)
            x = 110 + i * (tw + 4); out.paste(bg.convert('RGB'), (x, y))
            by = y + int(BASELINE * th / CELL_H)
            d.line([(x, by), (x + tw, by)], fill=(255, 0, 0)); d.line([(x + tw // 2, y), (x + tw // 2, y + th)], fill=(0, 90, 255))
    out.save(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'assets'))
    ap.add_argument('--preview', default=None, help='folder for contact sheets')
    ap.add_argument('--only', default=None)
    ap.add_argument('--portraits-only', action='store_true', help='only (re)write portrait.png files')
    args = ap.parse_args()
    done = {}
    for folder, anims in SPEC.items():
        if args.only and folder != args.only:
            continue
        key = id(anims)
        if key in done:   # identical spec (e.g. Daragh = Dec): copy files
            import shutil
            shutil.copytree(os.path.join(args.out, done[key]), os.path.join(args.out, folder), dirs_exist_ok=True)
            print(f'{folder}: copied from {done[key]}')
            continue
        if not args.portraits_only:
            cell_w, sheets = build_character(folder, anims, args.out)
        build_portrait(folder, args.out)
        done[key] = folder
        if args.portraits_only:
            continue
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            contact_sheet(folder, cell_w, sheets, os.path.join(args.preview, f'contact_{folder}.png'))

if __name__ == '__main__':
    main()
