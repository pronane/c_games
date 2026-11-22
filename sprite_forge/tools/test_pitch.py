#!/usr/bin/env python3
"""Turf masks for field sports (v11.33, fed back from Arena FC).

    python tools/test_pitch.py

  1 soccer markings: touchlines, goal lines, halfway, centre circle radius 9.15 m, both boxes, spots
  2 Gaelic markings: the 13 / 20 / 45 m lines from each end
  3 every mowing style gives two directions in roughly equal parts; checker differs from stripes
  4 wear is heaviest in the goalmouths and lightest in the middle of each half's wide areas
  5 export writes the texture and its layout"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import pitch as P  # noqa: E402

R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def at(mask, sport, x, z):
    L = P.layout(sport)
    ex, ez = L["extent"]
    return float(mask[int(round((z + ez) * P.PX_PER_M)), int(round((x + ex) * P.PX_PER_M))])


def main():
    m = P.markings("soccer")
    checks = {"touchline": (10, 34), "goal line": (52.5, 10), "halfway": (0, 20), "centre circle": (9.15, 0),
              "box front": (52.5 - 16.5, 5), "six-yard": (52.5 - 5.5, 3), "spot": (52.5 - 11, 0)}
    rec("soccer markings painted", all(at(m, "soccer", x, z) > .5 for x, z in checks.values()),
        str({k: round(at(m, "soccer", *v), 2) for k, v in checks.items()}))
    rec("soccer: no paint in open grass", at(m, "soccer", 20, 15) < .1 and at(m, "soccer", -25, -20) < .1)
    g = P.markings("gaelic")
    rec("Gaelic: 13 / 20 / 45 m lines from each end",
        all(at(g, "gaelic", s * (72.5 - d), 30) > .5 for d in (13, 20, 45) for s in (-1, 1)))
    styles = {s: P.mowing("soccer", s) for s in P.MOW}
    rec("every mowing style has two directions", all(.3 < v.mean() < .7 for v in styles.values()),
        str({k: round(float(v.mean()), 2) for k, v in styles.items()}))
    rec("checker differs from stripes", np.abs(styles["checker"] - styles["stripes"]).mean() > .3)
    w = P.wear("soccer")
    rec("wear: goalmouths worn, wide areas lush", at(w, "soccer", 50, 0) > .4 and at(w, "soccer", 25, 25) < .15,
        "goalmouth %.2f, wide %.2f" % (at(w, "soccer", 50, 0), at(w, "soccer", 25, 25)))
    with tempfile.TemporaryDirectory() as td:
        meta = P.export(os.path.join(td, "p.png"), "soccer", "rings")
        rec("export writes the texture and layout", os.path.exists(os.path.join(td, "p.png"))
            and json.load(open(os.path.join(td, "p.json")))["extent"] == meta["extent"])
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
