"""Phone-camera proportion correction (v9.4): photo cut-out + landmarks -> anatomically plausible proportions.

A phone held close and above chest height makes the head big and the legs short (Mike's photo: head 0.178 of his
height against an adult ~0.13, hip-to-floor 0.40 against ~0.47).  Every view and move inherits that, so the
correction runs on the cut-out once, before any rig is built:

  * landmark rows: head top, chin, shoulders, hips, knees, ankles, floor  (MediaPipe Pose 33 order)
  * each row moves `strength` of the way towards adult norms (fractions of standing height measured from the
    floor; MediaPipe's hip points sit high on the pelvis, so their norm is ~0.53, not the anatomical 0.50)
  * the HEAD is scaled uniformly (x and y) about the chin, so the face keeps its own shape; below the chin the body
    is remapped row by row (vertical only), so clothes and limbs keep their widths
  * the landmarks go through exactly the same mapping

auto: only when the photo is clearly distorted (head > 0.15 of height or legs < 0.44) - a well-taken photo or a
rendered mannequin is left alone.  The correction is reported in the build notes."""
from __future__ import annotations
import numpy as np
from PIL import Image

# adult norms, fraction of standing height above the floor, for the MediaPipe landmark rows used here
NORM = {"top": 1.0, "chin": 0.870, "shoulder": 0.818, "hip": 0.530, "knee": 0.285, "ankle": 0.040, "floor": 0.0}


def measure(cut, lms):
    a = np.asarray(cut.convert("RGBA"))[..., 3] > 100
    rows = np.nonzero(a.any(1))[0]
    top, floor = float(rows.min()), float(rows.max())
    L = [(float(p[0]), float(p[1])) for p in lms]
    eye = (L[2][1] + L[5][1]) / 2; mouth = (L[9][1] + L[10][1]) / 2
    chin = mouth + 0.85 * (mouth - eye)
    r = {"top": top, "chin": chin, "shoulder": (L[11][1] + L[12][1]) / 2, "hip": (L[23][1] + L[24][1]) / 2,
         "knee": (L[25][1] + L[26][1]) / 2, "ankle": (L[27][1] + L[28][1]) / 2, "floor": floor}
    H = floor - top
    frac = {k: (floor - v) / H for k, v in r.items()}
    return r, frac, H


def needs(frac):
    return (1.0 - frac["chin"]) > 0.15 or frac["hip"] < 0.44


def correct(cut, lms, strength=0.65, mode="auto", log=print):
    """-> (cut, lms, info).  mode: auto | on | off"""
    if mode == "off":
        return cut, lms, None
    cut = cut.convert("RGBA")
    rows, frac, H = measure(cut, lms)
    if mode == "auto" and not needs(frac):
        return cut, lms, None
    keys = ["top", "chin", "shoulder", "hip", "knee", "ankle", "floor"]
    tgt = {k: frac[k] + strength * (NORM[k] - frac[k]) for k in keys}
    # keep the total standing height: new row of each key, measured from the same floor
    floor = rows["floor"]
    new = {k: floor - tgt[k] * H for k in keys}
    # head: uniform scale about the chin, so the head keeps its shape
    old_head = rows["chin"] - rows["top"]; new_head = new["chin"] - new["top"]
    sh = new_head / max(1.0, old_head)
    A = np.asarray(cut).astype(np.float32)
    h0, w0 = A.shape[:2]
    L = [list(p) for p in lms]
    cx = (L[11][0] + L[12][0]) / 2.0
    # ---- body below the chin: piecewise-linear row map (new y -> old y)
    by = ["chin", "shoulder", "hip", "knee", "ankle", "floor"]
    ny = np.array([new[k] for k in by]); oy = np.array([rows[k] for k in by])
    out_h = int(round(floor)) + 1 + max(0, h0 - int(round(floor)) - 1)
    out = np.zeros((out_h, w0, 4), np.float32)
    ys = np.arange(out_h, dtype=np.float32)
    src_y = np.interp(ys, ny, oy, left=np.nan, right=np.nan)
    below = ys > floor
    src_y[below] = ys[below]                         # under the feet: unchanged (shadow / nothing)
    yi = np.clip(np.nan_to_num(src_y, nan=0.0), 0, h0 - 1)
    y0 = np.floor(yi).astype(int); y1 = np.minimum(y0 + 1, h0 - 1); t = (yi - y0)[:, None, None]
    body = A[y0] * (1 - t) + A[y1] * t
    ok = ~np.isnan(src_y)
    out[ok] = body[ok]
    # ---- head: uniformly scaled crop above the chin (+ a short overlap for a seamless join)
    ov = int(max(3, 0.02 * H))
    c0 = int(round(rows["chin"])) + ov
    head = Image.fromarray(np.asarray(cut)[:c0])
    nh = max(1, int(round(c0 * sh))); nw = max(1, int(round(w0 * sh)))
    hs = np.asarray(head.resize((nw, nh), Image.LANCZOS)).astype(np.float32)
    # place: chin row maps to new["chin"], the neck centre stays at cx
    oy_ = int(round(new["chin"] - rows["chin"] * sh)); ox_ = int(round(cx - cx * sh))
    yA, yB = max(0, oy_), min(out_h, oy_ + nh); xA, xB = max(0, ox_), min(w0, ox_ + nw)
    patch = hs[yA - oy_:yB - oy_, xA - ox_:xB - ox_]
    # blend over the overlap rows (head above the chin wins, fades into the body over the neck)
    rr = np.arange(yA, yB, dtype=np.float32)
    wgt = np.clip((new["chin"] + ov * sh - rr) / max(1.0, ov * sh), 0, 1)[:, None, None]
    region = out[yA:yB, xA:xB]
    pa = patch[..., 3:4] / 255.0
    w_ = wgt * pa
    region[..., :3] = region[..., :3] * (1 - w_) + patch[..., :3] * w_
    region[..., 3:4] = region[..., 3:4] * (1 - wgt) + patch[..., 3:4] * wgt
    above = rr < new["chin"]                         # rows fully inside the head: nothing from the body survives
    region[above] = patch[above]
    out[yA:yB, xA:xB] = region
    # ---- landmarks through the same mapping
    def map_y(y):
        return float(np.interp(y, oy, ny))
    newL = []
    for i, p in enumerate(L):
        x, y = p[0], p[1]
        if i <= 10 or y < rows["chin"]:              # face points: uniform head scale
            nx, nyy = ox_ + x * sh, oy_ + y * sh
        else:
            nx, nyy = x, map_y(y)
        newL.append([nx, nyy] + list(p[2:]))
    res = Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")
    info = dict(head_before=1 - frac["chin"], head_after=1 - measure(res, newL)[1]["chin"],
                hip_before=frac["hip"], hip_after=measure(res, newL)[1]["hip"], strength=strength, head_scale=sh)
    log("proportions: head %.3f -> %.3f of height, hip height %.3f -> %.3f (strength %.2f; phone perspective)" % (
        info["head_before"], info["head_after"], info["hip_before"], info["hip_after"], strength))
    return res, newL, info
