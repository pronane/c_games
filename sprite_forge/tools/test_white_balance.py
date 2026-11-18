#!/usr/bin/env python3
"""White balance from a neutral garment, and the face's colour against the person's other skin (v11.17). No assets.

    python tools/test_white_balance.py

A video's colour is the room's light as much as the clothes' (Tmon: lamps and a window, the phone's white balance
swinging between them - his grey hoodie came out brown). No automatic method can tell a warm room from a warm
jumper; the person can: `forge.py capture --neutral upper|lower|shoes`. Checks, on a small atlas of four parts
(an upper garment, trousers, shoes, skin) under a warm cast:
  1 --neutral upper: the upper garment comes out grey (R = G = B) with its lightness kept
  2 every other part gets the same correction (their colours relative to each other are kept)
  3 --neutral lower / shoes use those parts; an unknown part is refused
  4 too little of the garment seen (under 200 texels): nothing is changed
  5 blown-out and black texels (a logo's white, a shadow) do not steer it
Face against skin (face_to_skin):
  6 a blue-cast face on a warm body moves most of the way to the body's skin colour; its lightness is kept
  7 how far each texel moves follows how much it is face; the rest of the body is untouched
  8 a face already the skin's colour (within 3) is left alone; a huge step is capped"""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))


def atlas(res=256):
    """four squares of the atlas, two triangles each: (F, fuv, layer, J, bi, region masks of the texture)"""
    bi = {"spine03": 0, "upperleg01.L": 1, "foot.L": 2, "head": 3}
    boxes = [(0.0, 0.0, "spine03", 1), (0.5, 0.0, "upperleg01.L", 1), (0.0, 0.5, "foot.L", 0), (0.5, 0.5, "head", 0)]
    F, fuv, layer, J = [], [], [], []
    for k, (u0, v0, b, lay) in enumerate(boxes):
        base = 4 * k
        q = np.array([[u0, v0], [u0 + 0.5, v0], [u0 + 0.5, v0 + 0.5], [u0, v0 + 0.5]])
        q = (q - [u0, v0]) * 0.96 + [u0, v0] + 0.01                     # a small gap between squares
        F += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
        fuv += [q[[0, 1, 2]], q[[0, 2, 3]]]
        layer += [lay] * 4; J += [[bi[b]]] * 4
    F, fuv = np.array(F), np.array(fuv)
    layer, J = np.array(layer), np.array(J)
    yy, xx = np.mgrid[0:res, 0:res]
    u = (xx + 0.5) / res; v = 1.0 - (yy + 0.5) / res
    reg = {}
    for (u0, v0, b, lay) in boxes:
        reg[b] = (u > u0 + 0.03) & (u < u0 + 0.47) & (v > v0 + 0.03) & (v < v0 + 0.47)
    return F, fuv, layer, J, bi, reg


def main():
    from sforge import capture_texture as CT
    F, fuv, layer, J, bi, reg = atlas()
    rng = np.random.default_rng(2)
    warm = np.array([1.25, 1.0, 0.75])
    truth = {"spine03": [120, 120, 120], "upperleg01.L": [40, 40, 60], "foot.L": [200, 200, 200],
             "head": [200, 150, 125]}
    tex = np.full((256, 256, 3), 210.0)
    for b, c in truth.items():
        tex[reg[b]] = np.array(c) * warm + rng.normal(0, 3, (reg[b].sum(), 3))
    tex = np.clip(tex, 0, 255).astype(np.uint8)
    g, info = CT.neutral_gain(tex, F, fuv, layer, J, bi, "upper")
    out = CT.white_balance(tex, g)
    up = np.median(out[reg["spine03"]].astype(float), 0)
    rec("1 --neutral upper: the upper garment comes out grey, lightness kept",
        np.ptp(up) < 3 and abs(up.mean() - np.median(tex[reg["spine03"]].astype(float), 0).mean()) < 3,
        "RGB %s" % np.round(up))
    leg = np.median(out[reg["upperleg01.L"]].astype(float), 0)
    want = np.array(truth["upperleg01.L"], float) * (up.mean() / 120.0)
    rec("2 the other parts get the same correction", np.abs(leg - want).max() < 4,
        "trousers %s (want %s)" % (np.round(leg), np.round(want)))
    g2, i2 = CT.neutral_gain(tex, F, fuv, layer, J, bi, "lower")
    g3, i3 = CT.neutral_gain(tex, F, fuv, layer, J, bi, "shoes")
    try:
        CT.neutral_gain(tex, F, fuv, layer, J, bi, "hat"); refused = False
    except ValueError:
        refused = True
    rec("3 lower / shoes use their parts; an unknown part is refused",
        i2["applied"] and i3["applied"] and abs(i3["before"][0] / i3["before"][2] - 1.25 / 0.75) < 0.1 and refused,
        "shoes before %s" % np.round(i3["before"]))
    small = tex.copy()
    quad = np.zeros(reg["spine03"].shape, bool); quad[128:, :128] = True   # the upper garment's square
    keep = np.zeros_like(quad); keep[200:210, 50:65] = True                # 150 texels of it seen
    small[quad & ~keep] = 0                                               # the rest black (unseen)
    g4, i4 = CT.neutral_gain(small, F, fuv, layer, J, bi, "upper")
    rec("4 too little of the garment seen: nothing changed", not i4["applied"] and np.allclose(g4, 1),
        "%d texels" % i4["texels"])
    logo = tex.copy()
    m = reg["spine03"] & (rng.random(reg["spine03"].shape) < 0.3)
    logo[m] = 255                                                         # a white print over 30% of it
    g5, _ = CT.neutral_gain(logo, F, fuv, layer, J, bi, "upper")
    rec("5 a blown-out print does not steer it", np.abs(g5 - g).max() < 0.03, "gains %s vs %s" % (np.round(g5, 2), np.round(g, 2)))
    # face against skin
    from sforge.capture_clean import _lab
    n = 4000
    col = np.zeros((n, 3)); fw = np.zeros(n); ref = np.zeros(n, bool)
    col[:1500] = [190, 158, 150]; fw[:1500] = 1.0                          # a face with a cooler cast
    col[1500:2000] = [180, 150, 140]; fw[1500:2000] = np.linspace(1, 0, 500)   # its edge
    col[2000:3000] = [200, 150, 125]; ref[2000:3000] = True               # the neck and hands
    col[3000:] = [90, 90, 90]                                             # clothes
    col = col + rng.normal(0, 2, col.shape)
    o, inf = CT.face_to_skin(col, fw, ref, log=lambda *a: None)
    Lc, Lo = _lab(col.astype(np.float32)), _lab(o.astype(np.float32))
    sk = np.median(Lc[ref], 0)
    before = np.linalg.norm(np.median(Lc[:1500], 0)[1:] - sk[1:]); after = np.linalg.norm(np.median(Lo[:1500], 0)[1:] - sk[1:])
    dL = float(np.abs(np.median(Lo[:1500, 0]) - np.median(Lc[:1500, 0])))
    rec("6 a blue-cast face moves most of the way to the skin's colour", after < 0.35 * before and dL < 2,
        "a/b step %.1f -> %.1f, lightness moved %.1f" % (before, after, dL))
    mv = np.linalg.norm(Lo[1500:2000, 1:] - Lc[1500:2000, 1:], axis=1)
    untouched = np.abs(o[2000:] - col[2000:]).max()
    rec("7 the move follows how much it is face; the rest untouched",
        mv[:50].mean() > 3 * mv[-50:].mean() and untouched == 0, "edge %.1f -> %.1f, rest %.1f" % (mv[:50].mean(), mv[-50:].mean(), untouched))
    same = col.copy(); same[:2000] = [200, 150, 125]
    o2, i8 = CT.face_to_skin(same, fw, ref, log=lambda *a: None)
    big = col.copy(); big[:1500] = [120, 160, 250]
    o3, i9 = CT.face_to_skin(big, fw, ref, log=lambda *a: None)
    rec("8 a face already the skin's colour is left alone; a huge step is capped",
        np.abs(o2 - same).max() == 0 and i9["moved_ab"] <= 15.0 * 0.8 + 1e-6, "moved %.1f" % i9["moved_ab"])
    bad = [nm for nm, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
