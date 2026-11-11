#!/usr/bin/env python3
"""Feet in socks or shoes lose their toes, keep their size (v11.8, needs the MakeHuman assets).

    python tools/test_feet.py

MakeHuman's body has five modelled toes; a white sock painted on them shows five white toes. When the video's
labels call the feet something worn, capture_layers.shod_feet turns the front of each foot into one toe box.
Checks: the gaps between the toes (dips in the top surface across the foot) shrink by at least a fifth, the
foot keeps its length, width and height (within 6%), the sole stays on the floor, and bare feet (skin votes) are
left exactly as they were."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main():
    from sforge import capture_body as CB, capture_layers as CL
    try:
        bm = CB.BodyModel()
    except Exception as e:                                                   # noqa: BLE001
        print("skipped (no MakeHuman assets): %s" % e)
        return 0
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
         ("bare feet untouched", bool(np.array_equal(Vb, sh.V)), "")]
    for n, ok, d in R:
        print("%-5s %-44s %s" % ("PASS" if ok else "FAIL", n, d))
    print("\n%d / %d passed" % (sum(ok for _, ok, _ in R), len(R)))
    return 0 if all(ok for _, ok, _ in R) else 1


if __name__ == "__main__":
    sys.exit(main())
