"""MULTI-VIEW sprites: front / back / side / 3/4 views of one character, aligned to ONE figure
height, ground line and pivot, plus an optional 8-direction billboard set.

View names say which way the character FACES ON SCREEN (angle = camera yaw around the character):
    front 0 | front_right 45 | right 90 | back_right 135 | back 180 | back_left 225 | left 270 | front_left 315
  'right' = side profile facing image-right, 'front_right' = 3/4 view turned towards image-right,
  'back_right' = seen from behind, head turned towards image-right.   (Same order as TurboTumble64's
  8-angle sheets: 0 front, 90 = side facing image-right, 180 back.)

Sources per view: one image, a folder of frames, or a video (ffmpeg).  Only the supplied pixels are
used (cut-out, crop, scale, mirror, squash).  A view with no source is FILLED - by mirroring its
opposite-side view, or by squashing the nearest available view ('interpolated') - and every filled
view is flagged as such in atlas.json / sprites.cfg / character.ini / build_report.txt.
SPEC / mannequin builds render every view for real (camera yaw = view angle)."""
from __future__ import annotations
import os
from PIL import Image, ImageDraw

VIEWS = [("front", 0), ("front_right", 45), ("right", 90), ("back_right", 135),
         ("back", 180), ("back_left", 225), ("left", 270), ("front_left", 315)]
ANGLE = dict(VIEWS)
NAME_AT = {a: n for n, a in VIEWS}
MIRROR = {"front": "front", "back": "back", "right": "left", "left": "right", "front_right": "front_left",
          "front_left": "front_right", "back_right": "back_left", "back_left": "back_right"}
ALIASES = {"side": "right", "side_right": "right", "profile": "right", "side_left": "left",
           "three_quarter": "front_right", "threequarter": "front_right", "3/4": "front_right", "34": "front_right",
           "front34": "front_right", "front_34": "front_right", "front34_left": "front_left", "back34": "back_right",
           "back_34": "back_right", "rear": "back", "behind": "back", "n": "back", "s": "front", "e": "right", "w": "left",
           "se": "front_right", "sw": "front_left", "ne": "back_right", "nw": "back_left"}
BILLBOARD8 = [n for n, _ in VIEWS]


def norm_view(s):
    s = str(s).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ANGLE:
        return s
    if s in ALIASES:
        return ALIASES[s]
    try:
        a = int(round(float(s))) % 360
        if a in NAME_AT:
            return NAME_AT[a]
    except ValueError:
        pass
    raise ValueError("unknown view '%s' - use one of: %s (or an angle 0,45,...,315; side = right)" % (s, ", ".join(ANGLE)))


def parse_views(items):
    """['back=b.jpg', 'side=s.png', 'left=clip.mp4'] -> {view: source}"""
    out = {}
    for it in items or []:
        for part in str(it).split(";"):
            if not part.strip():
                continue
            if "=" not in part:
                raise ValueError("--view needs NAME=FILE, got '%s'" % part)
            k, v = part.split("=", 1)
            out[norm_view(k)] = v.strip()
    return out


def parse_view_list(s):
    if not s:
        return []
    if isinstance(s, (list, tuple)):
        items = list(s)
    else:
        items = [x for x in str(s).replace(";", ",").split(",") if x.strip()]
    if len(items) == 1 and str(items[0]).strip().lower() in ("billboard8", "8", "all", "8dir"):
        return list(BILLBOARD8)
    res = []
    for x in items:
        v = norm_view(x)
        if v not in res:
            res.append(v)
    return sorted(res, key=lambda n: ANGLE[n])


# ------------------------------------------------------------------ geometry: one transform per view
def _bbox(im, thr=8):
    return im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()


def _centroid_x(im, box):
    import numpy as np
    a = np.asarray(im.getchannel("A").crop(box), dtype=float)
    s = a.sum()
    return box[0] + (float((a.sum(0) * np.arange(a.shape[1])).sum() / s) if s > 0 else (box[2] - box[0]) / 2)


def measure(ref, cut):
    """-> dict(top, line, ax, w): the figure's top row, the crop/ground line (bottom of the figure, or
    cut*height below the top for busts), its centre x and its width above the line."""
    b = _bbox(ref)
    if not b:
        return None
    top, bot = b[1], b[3]
    line = bot if not cut or cut >= 0.999 else int(round(top + cut * (bot - top)))
    upper = (b[0], top, b[2], max(top + 1, line))
    ub = _bbox(ref.crop(upper))
    w = (ub[2] - ub[0]) if ub else (b[2] - b[0])
    ax = _centroid_x(ref, upper)
    if ub:   # keep the box symmetric around the centroid so the figure fits after flipping too
        w = 2 * max(ax - (upper[0] + ub[0]), (upper[0] + ub[2]) - ax)
    return dict(top=top, line=line, ax=ax, w=w, h=max(1, line - top))


def apply(im, m, s, cfg):
    """Map raw image -> cell: measure line -> ground_y, centre -> pivot_x, scale s."""
    fw, fh, gy, px = cfg.frame_w, cfg.frame_h, cfg.ground_y, cfg.pivot_x
    x0 = m["ax"] - px / s; y0 = m["line"] - gy / s
    box = (int(round(x0)), int(round(y0)), int(round(x0 + fw / s)), int(round(y0 + fh / s)))
    c = im.crop(box).resize((fw, fh), Image.LANCZOS)
    if gy < fh - 1:     # busts: nothing below the cut line
        a = c.getchannel("A"); d = ImageDraw.Draw(a); d.rectangle([0, gy + 1, fw, fh], fill=0); c.putalpha(a)
    return c


# ------------------------------------------------------------------ fill missing views
def squash(cell, k, pivot_x):
    """Horizontal squash around the pivot (a cheap 'turned a little' approximation)."""
    w, h = cell.size
    nw = max(1, int(round(w * k)))
    s = cell.resize((nw, h), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(s, (int(round(pivot_x - pivot_x * k)), 0), s)
    return out


def fill_views(have, wanted, pivot_x):
    """have: {view: [cells]} real views.  -> {view: (cells, source)} for every wanted view.
    Order of preference: real > mirrored opposite > squashed nearest (interpolated)."""
    res = {v: (c, "real") for v, c in have.items()}
    for v in wanted:
        if v in res:
            continue
        m = MIRROR[v]
        if m in have and m != v:
            res[v] = ([c.transpose(Image.FLIP_LEFT_RIGHT) for c in have[m]], "mirrored:" + m)
    avail = dict(res)
    for v in wanted:
        if v in res:
            continue
        if not avail:
            break
        a = ANGLE[v]
        def dist(n):
            d = abs(ANGLE[n] - a) % 360
            return min(d, 360 - d)
        near = sorted(avail, key=lambda n: (dist(n), 0 if avail[n][1] == "real" else 1, ANGLE[n]))[0]
        d = dist(near)
        k = 1.0 if d == 0 else (0.86 if d <= 45 else 0.75 if d <= 90 else 0.7)
        cells = [squash(c, k, pivot_x) if k < 1 else c.copy() for c in avail[near][0]]
        res[v] = (cells, "filled:interpolated(squashed %s)" % near)
    return res


# ------------------------------------------------------------------ outputs
def turnaround(view_sets, moves, fw, fh, labels=None, label=True):
    """view_sets: [(view, {move: [cells]}, source)] -> exact grid (rows = views, cols = moves, frame 0)
    and a labelled preview."""
    ncol = max(1, len(moves))
    grid = Image.new("RGBA", (ncol * fw, len(view_sets) * fh), (0, 0, 0, 0))
    for r, (v, mv, src) in enumerate(view_sets):
        for c, m in enumerate(moves):
            if m in mv and mv[m]:
                k = mv[m][min(len(mv[m]) - 1, len(mv[m]) // 2)]
                grid.paste(k, (c * fw, r * fh))
    if not label:
        return grid, None
    from .build import checker, _font
    th = 120; tw = int(th * fw / fh); lw = 170; top = 34
    W = lw + ncol * (tw + 4) + 6; H = top + len(view_sets) * (th + 4) + 6
    pv = Image.new("RGB", (W, H), (24, 30, 38)); d = ImageDraw.Draw(pv); f = _font(12)
    for c, m in enumerate(moves):
        d.text((lw + c * (tw + 4) + 2, 10), (labels or {}).get(m, m)[:max(6, tw // 7)], fill=(230, 230, 230), font=f)
    for r, (v, mv, src) in enumerate(view_sets):
        y = top + r * (th + 4)
        col = (120, 230, 140) if src.startswith("real") else (250, 200, 90) if src.startswith("mirrored") else (250, 120, 110)
        d.text((6, y + 8), "%s (%d)" % (v, ANGLE[v]), fill=(255, 255, 255), font=_font(14))
        d.text((6, y + 30), src.replace("filled:", "FILLED ")[:26], fill=col, font=f)
        for c, m in enumerate(moves):
            bg = checker(tw, th, 8)
            if m in mv and mv[m]:
                k = mv[m][min(len(mv[m]) - 1, len(mv[m]) // 2)].resize((tw, th), Image.LANCZOS)
                bg.paste(k, (0, 0), k)
            pv.paste(bg, (lw + c * (tw + 4), y))
    return grid, pv


def billboard_strip(view_sets, fw, fh, move="idle"):
    """8 cells in one row, angle order 0..315 (frame 0 of `move`, else the view's first move)."""
    order = sorted(view_sets, key=lambda t: ANGLE[t[0]])
    im = Image.new("RGBA", (fw * len(order), fh), (0, 0, 0, 0))
    for i, (v, mv, _) in enumerate(order):
        fr = mv.get(move) or next(iter(mv.values()))
        im.paste(fr[0], (i * fw, 0))
    return im
