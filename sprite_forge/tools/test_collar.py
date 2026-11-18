#!/usr/bin/env python3
"""The collar stays below the jaw (v11.16). Needs MakeHuman's CC0 base mesh (human --setup); no videos.

    python tools/test_collar.py

A collar is worn up the neck to the height most views agree on (at most 6 cm), measured from the bottom of the
neck. At the front the bottom of the neck is close under the chin, so a 6 cm collar ran up under the jaw, where no
frame sees it (white under Mike's chin). For a man, a woman and a smaller body, with clothes voted up the whole
neck (the worst case) and only at its base:
  1 no worn neck face comes within JAW_GAP below the head's surface above it
  2 at the back the collar still goes up as far as the neck allows (to the 6 cm cap or 1.5 cm below the skull)
  3 a low collar (clothes voted only at the base of the neck) stays low
  4 the head, hands and feet are never worn"""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    from sforge import capture_layers as CL
    try:
        from sforge import capture_body as CB
        bm = CB.BodyModel()
    except Exception as e:                                                   # noqa: BLE001
        print("skipped (no MakeHuman assets): %s" % e)
        return 0
    nk_b, hd_b = bm.bi["neck01"], bm.bi["head"]
    for label, macro, ht in (("man", dict(gender=1.0), 1.8), ("woman", dict(gender=0.0), 1.65),
                             ("smaller body", dict(gender=0.5, age=0.1), 1.3)):
        sh = bm.shape(macro, {}, ht)
        V = sh.V
        nk = (bm.J[:, 0] == nk_b) & (bm.W[:, 0] > 0.5)
        y = V[:, 1] - V[nk, 1].min()
        torso = ~np.isin(bm.J[:, 0], [hd_b])
        for kind in ("whole neck", "base only"):
            votes = np.zeros((len(V), 6)); votes[:, 2] = 1.0                 # skin everywhere ...
            worn = torso & (V[:, 1] < V[nk, 1].min() + (0.2 if kind == "whole neck" else 0.015))
            votes[worn, 2] = 0.0; votes[worn, 4] = 1.0                       # ... clothes over the body and neck
            fsel = CL.clothes_faces(bm, votes, shape=sh, log=lambda *a: None)
            wv = np.zeros(len(V), bool); wv[bm.F[fsel].ravel()] = True
            col = wv & nk
            bad = col & CL.under_jaw(V, bm, nk)
            rec("%s, %s: 1 nothing worn under the jaw" % (label, kind), not bad.any(),
                "%d neck vertices within %.1f cm of the jaw" % (bad.sum(), 100 * CL.JAW_GAP))
            back = col & (V[:, 2] < np.median(V[nk, 2]) - 0.02)
            top = float(y[back].max()) if back.any() else 0.0
            if kind == "whole neck":
                bn = nk & (V[:, 2] < np.median(V[nk, 2]) - 0.02) & ~CL.under_jaw(V, bm, nk)
                room = min(0.06, float(y[bn].max())) if bn.any() else 0.0      # what the neck allows at the back
                rec("%s, %s: 2 at the back the collar still goes up" % (label, kind), top > room - 0.012,
                    "%.1f cm up the back of the neck (room %.1f cm)" % (100 * top, 100 * room))
            else:
                hi_ = float(y[col].max()) if col.any() else 0.0
                rec("%s, %s: 3 a low collar stays low" % (label, kind), hi_ < 0.03, "%.1f cm" % (100 * hi_))
            never = np.isin(bm.J[:, 0], [hd_b] + [bm.bi[b] for b in ("wrist.L", "wrist.R", "foot.L", "foot.R")
                                                   if b in bm.bi]) & (bm.W[:, 0] > 0.5)
            rec("%s, %s: 4 head, hands and feet never worn" % (label, kind), not (wv & never).any(),
                "%d" % (wv & never).sum())
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
