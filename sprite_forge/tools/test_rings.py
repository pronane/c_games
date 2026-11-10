#!/usr/bin/env python3
"""Garment edges as rings round the limbs (v11.7, synthetic, no assets needed).

    python tools/test_rings.py

Legs are points with a distance s down the limb (hip 0 -> toes 0.95 m), left and right. The truth: shorts to 0.30,
bare skin to 0.75, a white sock below. The evidence is what a video gives: the edges jitter by 3 cm, 10% of the
points are labelled at random, and the feet are seen by few frames (90% of their points have no evidence).
Checks: the rings recover the truth (>= 97% of points), both edges sit within 2 cm of the truth on both sides,
a sock that the floor makes look like skin at its far end is still a sock (`bare`), a garment can be forbidden
on a limb (a shirt's colour on the legs), and MediaPipe's "other" class inside the person (socks, shoes) is its own
label instead of being thrown away."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-60s %s" % ("PASS" if ok else "FAIL", name, detail))


def legs(seed=0, n=30000):
    rng = np.random.default_rng(seed)
    limb = rng.choice([2, 3], n)
    s = rng.uniform(0, 0.95, n)
    true = np.where(s < 0.30, 1, np.where(s < 0.75, 0, 2))           # 1 shorts, 0 skin, 2 sock
    jit = s + rng.normal(0, 0.03, n)
    mat = np.where(jit < 0.30, 1, np.where(jit < 0.75, 0, 2))
    flip = rng.random(n) < 0.10
    mat[flip] = rng.integers(0, 3, flip.sum())
    mat[(s > 0.75) & (rng.random(n) < 0.9)] = -1
    return limb, s, true, mat


def edges(limb, s, ring, side):
    on = limb == side
    o = np.argsort(s[on]); ss, rr = s[on][o], ring[on][o]
    ch = np.nonzero(rr[1:] != rr[:-1])[0]
    return [float(0.5 * (ss[i] + ss[i + 1])) for i in ch]


def main():
    from sforge import capture_rings as CR
    from sforge import capture_texture as CT
    limb, s, true, mat = legs()
    ring, share, edge = CR.segment(limb, s, mat, 3)
    acc = float((ring == true).mean())
    rec("rings recover shorts / skin / sock", acc >= 0.97, "%.1f%% of points" % (100 * acc))
    eL, eR = edges(limb, s, ring, 2), edges(limb, s, ring, 3)
    ok = len(eL) == 2 and len(eR) == 2 and all(abs(a - b) < 0.02 for a, b in zip(eL, [0.30, 0.75])) \
        and all(abs(a - b) < 0.011 for a, b in zip(eL, eR))
    rec("one clean edge per garment, same both sides", ok, "left %s right %s" % (np.round(eL, 3), np.round(eR, 3)))
    # the far end of a sock reads as skin (white sock on a wooden floor): still the sock
    mat2 = mat.copy()
    far = (s > 0.85) & (mat2 >= 0)
    mat2[far & (np.random.default_rng(1).random(len(s)) < 0.6)] = 0
    ring2, _, _ = CR.segment(limb, s, mat2, 3)
    ring3, _, _ = CR.segment(limb, s, mat2, 3, bare=0)
    feet = s > 0.88
    rec("a sock's far end is not bare skin (bare=)", (ring3[feet] == 2).mean() > 0.95,
        "sock on the toes: %.0f%% without, %.0f%% with" % (100 * (ring2[feet] == 2).mean(), 100 * (ring3[feet] == 2).mean()))
    # a shirt's colour is not allowed on the legs
    mat4 = mat.copy()
    mat4[(s > 0.2) & (s < 0.4)] = 3                                     # shirt tails hanging over the thighs
    ring4, _, _ = CR.segment(limb, s, mat4, 4, forbid={CR.LEGS: [3]})
    rec("a forbidden garment never wins a ring", not (ring4 == 3).any(), "%d points" % int((ring4 == 3).sum()))
    # labels: MediaPipe 5 "other" is its own class (worn), 4 clothes, 2 / 3 skin, 1 hair
    lab = CT._label_class(np.array([0, 1, 2, 3, 4, 5]))
    rec("MediaPipe 'other' (socks, shoes) is the worn label", lab.tolist() == [0, 1, 2, 2, 3, 4], str(lab.tolist()))
    # limb coordinates follow the chain through the knee
    head = np.array([[0.1, 0.9, 0], [0.1, 0.5, 0], [0.1, 0.08, 0], [0.1, 0.0, 0.12]])
    bi = {"upperleg01.L": 0, "lowerleg01.L": 1, "foot.L": 2, "toe1-1.L": 3}
    X = np.array([[0.1, 0.7, 0.0], [0.1, 0.3, 0.0]])
    lb, sc = CR.limb_coords(head, X, np.array([0, 1]), bi)
    rec("limb coordinate runs hip -> knee -> ankle", lb.tolist() == [2, 2] and np.allclose(sc, [0.2, 0.6], atol=1e-6),
        "s %s" % np.round(sc, 3))
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
