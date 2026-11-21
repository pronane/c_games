"""v11.21: keep every move inside its sprite cell.

A dive, a slide tackle, a fall or a leaping catch reached past the cell (128x160 by default) and was cut off at the
edge: the QA's "clipped" FAIL. The moves are now drawn on a padded canvas first, then cut back to the cell size:

1. one shared window for the whole character, moved as little as possible from the usual place (feet on the
   ground line, body on the pivot) so that every move fits. The pivot and ground line move with it, for every move
   alike, so every engine format (atlas, manifest, sprites.cfg, Unity / Godot / raylib loaders) stays right.
2. a move that still cannot fit with the others (a lying-down KO next to a leaping catch) gets its own window and
   its own pivot / ground line, which game_character.json and atlas.json carry per move.
3. a move larger than the cell itself keeps the window that loses least, and the QA still reports it.
"""
from __future__ import annotations
import copy


def pad_rs(rs, pad):
    """RenderSettings with `pad` px more on every side, figure in the same place relative to the padded cell"""
    r = copy.copy(rs)
    r.cell_w = rs.cell_w + 2 * pad
    r.cell_h = rs.cell_h + 2 * pad
    r.anchor_x = rs.anchor_x + pad
    r.baseline = rs.baseline + pad
    return r


def pad_for(cfg):
    return int(max(cfg.frame_w, cfg.frame_h) // 2)


def body_box(im):
    """bbox of the character itself: the largest connected blob (limbs joined by a small dilation). A ball or other
    prop flying off on its own is left out of the fit - it may leave the cell, as a thrown ball does."""
    import numpy as np
    from scipy import ndimage
    a = np.asarray(im.getchannel("A")) > 8
    if not a.any():
        return None
    lab, n = ndimage.label(ndimage.binary_dilation(a, iterations=3))
    if n > 1:
        sizes = ndimage.sum(a, lab, range(1, n + 1))
        keep = lab == (1 + int(np.argmax(sizes)))
        a = a & keep
    ys, xs = np.nonzero(a)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _union(ims):
    box = None
    for im in ims:
        b = body_box(im)
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


def _window(lo, hi, size, default, margin=3):
    """start of a `size` window over [0, ...) containing [lo, hi) with a margin, as close to `default` as possible.
    -> (start, fits)"""
    need_lo, need_hi = lo - margin, hi + margin
    if need_hi - need_lo > size:                       # cannot fit: centre it (the QA reports the clip)
        return int(round((need_lo + need_hi - size) / 2.0)), False
    s = default
    if need_lo < s:
        s = need_lo
    if need_hi > s + size:
        s = need_hi - size
    return int(s), True


def scale_needed(frames, cfg, margin=3):
    """< 1 when some move is larger than the cell on its own: the factor the whole character must be drawn at so the
    largest move fits (one scale for every move, so the character keeps one size in the game)"""
    k = 1.0
    for v in frames.values():
        b = _union(v[0])
        if b is None:
            continue
        w, h = b[2] - b[0] + 2 * margin, b[3] - b[1] + 2 * margin
        k = min(k, cfg.frame_w / float(w), cfg.frame_h / float(h))
    return k


def fit(frames, cfg, pad, report=None):
    """frames: {move: (padded images, tag, note)} -> same with cell-sized images. Updates cfg.pivot_x / cfg.ground_y
    (shared shift) and sets cfg.move_pivots {move: (pivot_x, ground_y)} for moves that needed their own window."""
    W, H = cfg.frame_w, cfg.frame_h
    M = 3                                              # margin: the ground lock may still shift the set by a pixel or two
    # v11.22: put the feet on the ground line first (what the ground lock does after), so the fit allows for it -
    # otherwise the lock's shift afterwards pushed a fitted leap back out of the top of the cell
    off = _ground_offset(frames, cfg.ground_y + pad)
    if off and abs(off) < pad // 2:
        frames = {m: ([_shift(im, off) for im in v[0]],) + tuple(v[1:]) for m, v in frames.items()}
    boxes = {m: _union(v[0]) for m, v in frames.items()}
    have = {m: b for m, b in boxes.items() if b is not None}
    cfg.move_pivots = {}
    if not have:
        return {m: ([im.crop((pad, pad, pad + W, pad + H)) for im in v[0]],) + tuple(v[1:]) for m, v in frames.items()}
    lo_x = min(b[0] for b in have.values()); hi_x = max(b[2] for b in have.values())
    lo_y = min(b[1] for b in have.values()); hi_y = max(b[3] for b in have.values())
    x0, okx = _window(lo_x, hi_x, W, pad)
    y0, oky = _window(lo_y, hi_y, H, pad)
    if not (okx and oky):
        # the moves together do not fit: the shared window fits the most moves, the rest get their own
        x0, y0 = pad, pad
        best = -1
        for cx in sorted({pad} | {_window(b[0], b[2], W, pad)[0] for b in have.values()}):
            for cy in sorted({pad} | {_window(b[1], b[3], H, pad)[0] for b in have.values()}):
                n = sum(1 for b in have.values() if b[0] - M >= cx and b[2] + M <= cx + W and b[1] - M >= cy and b[3] + M <= cy + H)
                if n > best or (n == best and abs(cx - pad) + abs(cy - pad) < abs(x0 - pad) + abs(y0 - pad)):
                    best, x0, y0 = n, cx, cy
    out = {}
    px0, gy0 = cfg.pivot_x, cfg.ground_y
    cfg.pivot_x = px0 + (pad - x0)
    cfg.ground_y = gy0 + (pad - y0)
    moved = []
    for m, v in frames.items():
        b = boxes.get(m)
        wx, wy = x0, y0
        if b is not None and not (b[0] - M >= x0 and b[2] + M <= x0 + W and b[1] - M >= y0 and b[3] + M <= y0 + H):
            wx, fx = _window(b[0], b[2], W, x0)
            wy, fy = _window(b[1], b[3], H, y0)
            cfg.move_pivots[m] = (px0 + (pad - wx), gy0 + (pad - wy))
            moved.append("%s%s" % (m, "" if fx and fy else " (still larger than the cell)"))
        cells = [im.crop((wx, wy, wx + W, wy + H)) for im in v[0]]
        note = v[2] if len(v) > 2 else ""
        note = ", ".join(x for x in (note or "").replace("clipped at cell edge", "").split(", ") if x.strip())
        if _clipped(cells):
            note = ("clipped at cell edge; " + note) if note else "clipped at cell edge"
        out[m] = (cells, v[1], note) + tuple(v[3:])
    if report is not None:
        if (cfg.pivot_x, cfg.ground_y) != (px0, gy0):
            report.note("cell fit: pivot moved from (%d, %d) to (%d, %d) so every move stays inside the %dx%d cell"
                        % (px0, gy0, cfg.pivot_x, cfg.ground_y, W, H))
        if moved:
            report.note("cell fit: own pivot for %s (in game_character.json and atlas.json)" % ", ".join(moved))
    return out


def _lowest(im, thr=40):
    import numpy as np
    a = np.asarray(im.getchannel("A"))
    rows = np.nonzero((a > thr).any(1))[0]
    return int(rows.max()) + 1 if len(rows) else None


def _shift(im, dy):
    from PIL import Image
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, int(dy)))
    return out


def ground_ref(frames):
    """where the feet are planted: each of idle / walk / run's most planted frame, then the median (None if none)"""
    lows = []
    for mv in ("idle", "walk", "run", "fight_idle", "idle_athletic"):
        if mv in frames:
            ls = [v for v in (_lowest(im) for im in frames[mv][0]) if v]
            if ls:
                lows.append(max(ls))
    return int(sorted(lows)[len(lows) // 2]) if lows else None


def _ground_offset(frames, line):
    ref = ground_ref(frames)
    return 0 if ref is None else line - ref


def _clipped(ims):
    for im in ims:
        bb = body_box(im)
        if bb and (bb[0] <= 0 or bb[1] <= 0 or bb[2] >= im.width or bb[3] >= im.height):
            return True
    return False


def pivot_of(cfg, move):
    """(pivot_x, ground_y) of a move"""
    return (getattr(cfg, "move_pivots", None) or {}).get(move, (cfg.pivot_x, cfg.ground_y))
