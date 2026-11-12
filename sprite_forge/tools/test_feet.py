#!/usr/bin/env python3
"""Feet in socks or shoes lose their toes, keep their size (v11.8, needs the MakeHuman assets).

    python tools/test_feet.py

MakeHuman's body has five modelled toes; a white sock painted on them shows five white toes. When the video's
labels call the feet something worn, capture_layers.shod_feet turns the front of each foot into one toe box.
Checks: the gaps between the toes (dips in the top surface across the foot) shrink by at least a fifth, the
foot keeps its length, width and height (within 6%), the sole stays on the floor, and bare feet (skin votes) are
left exactly as they were.
v11.10, the texture (no assets needed): footwear keeps the colour it was filmed in through the clean - dark socks
that fall in one colour cluster with the skin are not pulled to the skin's colour (PR's navy socks came out
skin-pale), white trainers under black trousers stay white - and bare feet are still cleaned as skin."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def texture_checks():
    """a body-layer surface small enough to be one colour cluster: skin on the legs, feet that are dark shoes
    (labelled worn) or bare skin (labelled skin)"""
    from sforge import capture_clean as CC
    rng = np.random.default_rng(3)
    n_leg, n_foot = 6000, 2000
    N = n_leg + n_foot
    X = rng.uniform(-0.2, 0.2, (N, 3)); X[n_leg:, 1] = rng.uniform(-0.05, 0.0, n_foot)   # feet at the bottom
    X[:n_leg, 1] = rng.uniform(0.0, 0.9, n_leg)
    LEG, FOOT = 1, 2
    bone = np.r_[np.full(n_leg, LEG), np.full(n_foot, FOOT)]
    layer = np.zeros(N, int); seen = np.ones(N, bool); protect = np.zeros(N, bool)
    skin = np.array([196.0, 150.0, 128.0]); shoe = np.array([60.0, 62.0, 74.0])
    out = []
    for feet in ("shoes", "bare"):
        mix = np.r_[np.tile(skin, (n_leg, 1)), np.tile(shoe if feet == "shoes" else skin * 0.8, (n_foot, 1))]
        mix += rng.normal(0, 3, mix.shape)
        label = np.r_[np.full(n_leg, 2), np.full(n_foot, 4 if feet == "shoes" else 2)]
        res = {}
        for fb in ((), (FOOT,)):
            # all of it one leg (limb 2), s along the leg from the hip (0) to the toes
            o, _, info = CC.clean(mix, seen, X, layer, label, bone, protect, [], (), log=lambda *a: None,
                                  limb=np.full(N, 2), s=0.95 - X[:, 1], foot_bones=fb)
            res[bool(fb)] = np.linalg.norm((CC._lab(o[n_leg:]).mean(0) - CC._lab(mix[n_leg:]).mean(0))[1:])
        out.append((feet, res))
    (_, sh), (_, br) = out
    # white trainers under black trousers: the leg is trousers (clothes) to the hem, the foot worn and white
    mix = np.r_[np.tile([25.0, 25.0, 30.0], (n_leg, 1)), np.tile([215.0, 215.0, 210.0], (n_foot, 1))] + rng.normal(0, 3, (N, 3))
    label = np.r_[np.full(n_leg, 3), np.full(n_foot, 4)]
    layer2 = np.r_[np.ones(n_leg, int), np.zeros(n_foot, int)]
    tr = {}
    for fb in ((), (FOOT,)):
        o, _, _ = CC.clean(mix, seen, X, layer2, label, bone, protect, [], (), log=lambda *a: None,
                           limb=np.full(N, 2), s=0.95 - X[:, 1], foot_bones=fb)
        tr[bool(fb)] = float(o[n_leg:].mean())
    return [("white trainers under black trousers stay white", tr[True] > 180, "mean %.0f (%.0f without the rule)" % (tr[True], tr[False])),
            ("shoes in the skin's cluster keep their colour", sh[True] < 3.0 and sh[True] < sh[False],
             "colour shift %.1f (was %.1f without the rule)" % (sh[True], sh[False])),
            ("bare feet cleaned as skin, as before", abs(br[True] - br[False]) < 0.5, "%.1f vs %.1f" % (br[True], br[False]))]


def main():
    T = texture_checks()
    from sforge import capture_body as CB, capture_layers as CL
    try:
        bm = CB.BodyModel()
    except Exception as e:                                                   # noqa: BLE001
        print("geometry checks skipped (no MakeHuman assets): %s" % e)
        for n, ok, d in T:
            print("%-5s %-44s %s" % ("PASS" if ok else "FAIL", n, d))
        return 0 if all(ok for _, ok, _ in T) else 1
    sh = bm.shape(dict(gender=1.0), {}, 1.8)
    worn = np.zeros((len(sh.V), 6)); worn[:, 5] = 1.0
    bare = np.zeros((len(sh.V), 6)); bare[:, 2] = 1.0
    V = CL.shod_feet(bm, sh, worn, log=lambda *a: None)
    Vb = CL.shod_feet(bm, sh, bare, log=lambda *a: None)
    tb = [bm.bi[b] for b in ("toe1-1.L", "toe1-1.R")]
    toe = np.isin(bm.J[:, 0], tb) & (bm.W[:, 0] > 0.2)

    def bumpy(P):
        """the gaps between the toes: in slices across the front of the foot, how far the top surface dips
        below its own upper envelope"""
        from scipy.ndimage import maximum_filter1d
        q = P[toe & (P[:, 0] > 0)]
        d = []
        for z0 in np.linspace(q[:, 2].min(), q[:, 2].max(), 8)[1:-1]:
            sl = q[np.abs(q[:, 2] - z0) < 0.004]
            if len(sl) < 5:
                continue
            xs = np.linspace(sl[:, 0].min(), sl[:, 0].max(), 20)
            t = np.array([sl[(sl[:, 0] >= a) & (sl[:, 0] < b), 1].max() if ((sl[:, 0] >= a) & (sl[:, 0] < b)).any()
                          else np.nan for a, b in zip(xs[:-1], xs[1:])])
            t = np.where(np.isnan(t), np.nanmin(t), t)
            d.append(float((maximum_filter1d(t, 5) - t)[2:-2].mean()))
        return float(np.mean(d))
    b0, b1 = bumpy(sh.V), bumpy(V)
    foot = np.isin(bm.J[:, 0], [bm.bi[b] for b in ("foot.L", "toe1-1.L")]) & (bm.W[:, 0] > 0.3)
    ext = lambda P: P[foot].max(0) - P[foot].min(0)
    e0, e1 = ext(sh.V), ext(V)
    R = [("gaps between the toes reduced (>= 20%)", b1 < 0.8 * b0, "%.2f -> %.2f mm" % (1000 * b0, 1000 * b1)),
         ("foot length / width / height kept (6%)", bool(np.all(np.abs(e1 / e0 - 1) < 0.06)), "%s" % np.round(e1 / e0, 3)),
         ("sole on the floor (within 1 mm)", abs(V[foot, 1].min() - sh.V[foot, 1].min()) < 1e-3, ""),
         ("bare feet untouched", bool(np.array_equal(Vb, sh.V)), "")] + T
    for n, ok, d in R:
        print("%-5s %-44s %s" % ("PASS" if ok else "FAIL", n, d))
    print("\n%d / %d passed" % (sum(ok for _, ok, _ in R), len(R)))
    return 0 if all(ok for _, ok, _ in R) else 1


if __name__ == "__main__":
    sys.exit(main())
