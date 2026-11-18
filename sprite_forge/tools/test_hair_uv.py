#!/usr/bin/env python3
"""The hair shell's texture map (v11.14). Needs MakeHuman's CC0 base mesh (human --setup); no videos.

    python tools/test_hair_uv.py

Every texel of the atlas must belong to one place on the body. The hair shell used to be mapped straight down
from above: the back and sides of the head below its widest point folded under the top, so a fifth of the shell's
texels were claimed by two triangles in different places and the bake painted each with the other's colour - the
tiled, blotchy heads. capture_layers.shell_uv now flattens the shell onto a disc. For heads of several shapes and
for hair from a cap to the nape, from patchy votes, and from a shaved head (the thin cap):
  1 no texel of the atlas is claimed by two triangles (uv_overlap, the whole body + clothes + hair atlas)
  2 no shell triangle is folded over (all the same way round in the map) or squashed to nothing
  3 the shell stays in the hair quarter's left half (the curtain has the right half)
  4 the front of the head is at the top of the map, the back at the bottom, left and right on their own sides
  5 the map is not starved: under 2% of the shell's area gets less than a tenth of its fair share of texels
  6 the old top-down map fails check 1 on the same head (the check sees the fault it is there for)
Also uv_overlap on two synthetic layouts (two squares overlapping by a known area, and two side by side)."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-66s %s" % ("PASS" if ok else "FAIL", name, detail))


def overlap_checks(CL):
    sq = np.array([[0, 1, 2], [0, 2, 3]])
    def quad(x0, y0, s):
        return np.array([[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s]])
    a = quad(0.1, 0.1, 0.4); b = quad(0.3, 0.3, 0.4); c = quad(0.55, 0.1, 0.4)
    F = np.r_[sq, sq + 4]
    n_ab = CL.uv_overlap(F, np.r_[a[sq], b[sq]], res=200)
    n_ac = CL.uv_overlap(F, np.r_[a[sq], c[sq]], res=200)
    rec("uv_overlap counts a known overlap (0.2 x 0.2 of a 200 px map)", abs(n_ab - 40 * 40) <= 2 * 40 + 4,
        "%d texels (want about 1600)" % n_ab)
    rec("uv_overlap: squares side by side share nothing", n_ac == 0, "%d" % n_ac)


def votes_for(bm, sh, kind, rng):
    """per-vertex label votes (none, hair, skin, face, clothes, other) for a head with hair of one kind. The
    hairline is as on a person: high over the forehead, lower round the sides and back, never over the ears"""
    V = sh.V
    hi = bm.bi["head"]
    head = (bm.J[:, 0] == hi) & (bm.W[:, 0] > 0.6)
    top = V[head, 1].max(); low = V[head, 1].min()
    cx = np.median(V[head, 0]); cz = np.median(V[head, 2])
    votes = np.zeros((len(V), 6)); votes[:, 2] = 1.0
    h = top - V[:, 1]
    back = np.clip((cz + 0.03 - V[:, 2]) / 0.1, 0, 1)                         # 0 at the forehead, 1 at the back
    ear = np.abs(V[:, 0] - cx) > 0.068
    if kind == "cap":
        hairy = h < 0.07
    elif kind == "short":
        hairy = (h < 0.06 + 0.07 * back) & ~ear
    elif kind == "nape":                                  # down the back of the head to the hairline at the neck
        hairy = ((h < 0.06 + 0.07 * back) | ((back > 0.9) & (V[:, 1] > low + 0.02))) & ~ear
    elif kind == "split":                                 # a parting of skin across the crown: two pieces
        hairy = (h < 0.06 + 0.07 * back) & ~ear & (np.abs(V[:, 2] - cz + 0.01) > 0.012)
    elif kind == "patchy":
        hairy = (h < 0.06 + 0.07 * back) & ~ear & (rng.random(len(V)) > 0.12)
    else:                                                 # shaved: no hair votes (the thin cap)
        hairy = np.zeros(len(V), bool)
    votes[hairy & head, 1] = 3.0
    return votes


def shell_checks(CL, bm, sh, label, votes, length=0.0):
    hi = bm.bi["head"]
    hc = np.median(sh.V[(bm.J[:, 0] == hi) & (bm.W[:, 0] > 0.6)], 0)        # the middle of the head
    M = CL.build_hair(sh, votes, 0.01, length)
    q0 = CL.to_quarter(np.zeros((1, 1, 2)), "hair")[0, 0]
    loc = (M.fuv - q0) / 0.5                                                  # within the hair quarter
    shell = loc[:, :, 0].max(1) < 0.5 + 1e-9
    F, fuv = M.F[shell], M.fuv[shell]
    n = CL.uv_overlap(M.F, M.fuv, res=2048)
    u = fuv
    a = (u[:, 1, 0] - u[:, 0, 0]) * (u[:, 2, 1] - u[:, 0, 1]) - (u[:, 2, 0] - u[:, 0, 0]) * (u[:, 1, 1] - u[:, 0, 1])
    # folded: against the way round of its own piece (a piece laid out mirrored is not folded)
    pid = CL._pieces(F)
    s = np.ones(len(F))
    for k in np.unique(pid):
        s[pid == k] = np.sign(np.median(a[pid == k]))
    flipped = int((np.sign(a) != s).sum()); flat = int((np.abs(a) < 1e-12).sum())
    inside = bool((loc[shell, :, 0] >= -1e-9).all() and (loc[shell, :, 0] <= 0.5).all() and
                  (loc[shell, :, 1] >= 0).all() and (loc[shell, :, 1] <= 1).all())
    # where the front / back / left / right of the head land (rig: +z forward, +x the figure's left)
    P = M.V[F].mean(1); c = hc; uvc = loc[shell].mean(1)
    def mean_uv(sel):
        return uvc[sel].mean(0) if sel.any() else np.array([np.nan, np.nan])
    fr = mean_uv(P[:, 2] > c[2] + 0.04); bk = mean_uv(P[:, 2] < c[2] - 0.04)
    lf = mean_uv(P[:, 0] > c[0] + 0.04); rt = mean_uv(P[:, 0] < c[0] - 0.04)
    orient = bool(fr[1] > bk[1] and lf[0] > rt[0]) if not np.isnan(np.r_[fr, bk, lf, rt]).any() else True
    # stretch: each triangle's share of the map against its share of the surface
    A3 = 0.5 * np.linalg.norm(np.cross(M.V[F[:, 1]] - M.V[F[:, 0]], M.V[F[:, 2]] - M.V[F[:, 0]]), axis=1)
    share = (np.abs(a) / np.abs(a).sum()) / (A3 / A3.sum() + 1e-12)
    starved = float(A3[share < 0.1].sum() / A3.sum())                       # by area: the ear's folds are many
    folded_area = float(A3[(np.sign(a) != s) | (np.abs(a) < 1e-12)].sum() / A3.sum())
    rec("%s: 1 no texel claimed twice" % label, n == 0, "%d texels" % n)
    rec("%s: 2 no shell triangle folded or squashed" % label, flipped == 0 and flat == 0,
        "%d folded, %d flat of %d (%.3f%% of the area)" % (flipped, flat, len(F), 100 * folded_area))
    rec("%s: 3 inside the hair quarter's left half" % label, inside, "")
    rec("%s: 4 front at the top, figure's left on the right of the map" % label, orient,
        "front v %.2f back v %.2f, left u %.2f right u %.2f" % (fr[1], bk[1], lf[0], rt[0]))
    rec("%s: 5 the map is not starved anywhere" % label, starved < 0.02,
        "%.1f%% of the shell gets under a tenth of its share" % (100 * starved))
    return M


def main():
    from sforge import capture_layers as CL
    overlap_checks(CL)
    from sforge import capture_body as CB
    try:
        bm = CB.BodyModel()
    except Exception as e:                                                   # noqa: BLE001
        print("shell checks skipped (no MakeHuman assets): %s" % e)
        return 0 if all(ok for _, ok, _ in R) else 1
    rng = np.random.default_rng(7)
    bodies = [("man", dict(gender=1.0), 1.8), ("woman", dict(gender=0.0), 1.65),
              ("child-sized", dict(gender=0.5, age=0.1), 1.3)]
    for bname, macro, ht in bodies:
        sh = bm.shape(macro, {}, ht)
        for kind in ("cap", "short", "nape", "split", "patchy", "shaved"):
            M = shell_checks(CL, bm, sh, "%s, %s" % (bname, kind), votes_for(bm, sh, kind, rng),
                             length=0.15 if kind == "nape" else 0.0)
    # 6 the old top-down map on the same head claims texels twice
    sh = bm.shape(dict(gender=1.0), {}, 1.8)
    M = CL.build_hair(sh, votes_for(bm, sh, "nape", rng), 0.01, 0.0)
    xz = M.V[:, [0, 2]]; lo, hi_ = xz.min(0), xz.max(0)
    old = (xz - lo) / np.maximum(hi_ - lo, 1e-6) * [0.48, 0.95] + [0.01, 0.025]
    n_old = CL.uv_overlap(M.F, CL.to_quarter(old[M.F], "hair"), res=2048)
    rec("6 the old top-down map fails check 1 on the same head", n_old > 0, "%d texels claimed twice" % n_old)
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
