#!/usr/bin/env python3
"""The head's look (v11.13): the head turned towards the camera, and the hair as one colour. No assets needed.

    python tools/test_head_look.py

In a turnaround video people follow the camera with their head. Where the face is tracked, the bake has the head's
own pose. Elsewhere it used the body's camera, so a face turned to the camera was painted on the side of the head:
a ghost face in profile. capture_texture.head_turn_model carries the person's turn into those frames. Checks:
  1 inside the tracked range it follows the straight line through the tracked frames
  2 just past the range it holds the line's value at that end (each side its own, no jump at the edge)
  3 seen from behind (150 degrees and more) the head is not turned - it cannot face the camera there
  4 between 90 and 150 degrees it fades smoothly, with no jump
  5 too few tracked frames: no turn is guessed
  6 the pose it builds turns the head about the neck: the neck stays where it was, the nose moves round
Hair (capture_clean): the back of a head is often seen only in frames lit by a window, so the hair shell came out
brown with blue patches (Tmon). Checks:
  7 a patch of the hair far off its colour is dropped and filled from the hair round it
  8 the hair keeps its own colour - dark brown, blonde, red or dyed purple hair is not pulled to anything else
  9 the strands' light and dark (lightness) are kept
 10 SF_HAIR_EVEN=0 leaves the hair as it was baked
 11 the bare scalp: a blue patch on skin is dropped and filled; a dark fringe beside a skin-coloured ear (two video
    labels) keeps both colours"""
from __future__ import annotations
import math
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def hair_checks():
    from sforge import capture_clean as CC
    rng = np.random.default_rng(5)
    N = 6000
    th = rng.uniform(0, 2 * np.pi, N); ph = rng.uniform(0.1, 1.4, N)        # a hair cap of 10 cm radius
    X = np.c_[0.1 * np.sin(ph) * np.cos(th), 1.65 + 0.1 * np.cos(ph), 0.1 * np.sin(ph) * np.sin(th)]
    back = (X[:, 2] < -0.04) & (X[:, 0] > 0.0)                              # the patch lit by the window
    strands = 1.0 + 0.25 * np.sin(X[:, 0] * 400)                            # light and dark along the strands
    seen = np.ones(N, bool); layer = np.full(N, 3); label = np.ones(N, int); bone = np.zeros(N, int)
    protect = np.zeros(N, bool)
    errs, keepL, cols = [], [], {}
    for name, rgb in (("dark brown", [70, 50, 38]), ("blonde", [200, 170, 110]), ("red", [150, 70, 40]),
                      ("purple (dyed)", [110, 60, 140])):
        mix = np.clip(np.array(rgb, float)[None] * strands[:, None] + rng.normal(0, 3, (N, 3)), 0, 255)
        mix[back] = np.clip(mix[back] * [0.6, 0.75, 1.6], 0, 255)
        o, keep, info = CC.clean(mix, seen, X, layer, label, bone, protect, [], (), log=lambda *a: None)
        lo = CC._lab(o); want = np.median(CC._lab(mix[~back]), 0)
        errs.append(float(np.linalg.norm(np.median(lo[back], 0)[1:] - want[1:])))
        cols[name] = float(np.linalg.norm(np.median(lo[~back], 0)[1:] - want[1:]))
        Lm = CC._lab(mix[~back])[:, 0]; Lo = lo[~back, 0]
        keepL.append(float(np.corrcoef(Lm, Lo)[0, 1]))
    rec("7 an off-colour patch of hair takes the hair's colour", max(errs) < 6.0,
        "colour step on the patch %s" % ", ".join("%.1f" % e for e in errs))
    rec("8 each hair colour stays its own", max(cols.values()) < 3.0,
        ", ".join("%s %.1f" % kv for kv in cols.items()))
    rec("9 the strands keep their light and dark", min(keepL) > 0.95, "correlation %.3f" % min(keepL))
    os.environ["SF_HAIR_EVEN"] = "0"
    try:
        o, _, info = CC.clean(mix, seen, X, layer, label, bone, protect, [], (), log=lambda *a: None)
    finally:
        os.environ.pop("SF_HAIR_EVEN")
    rec("10 SF_HAIR_EVEN=0 leaves the hair alone", "hair_dropped" not in info and
        np.abs(CC._lab(o) - CC._lab(mix)).max() < 1.0, "")

    # 11 the scalp (body layer, head bone): skin with a blue patch, and a fringe labelled hair
    layer0 = np.zeros(N, int)
    fringe = X[:, 2] > 0.05
    lab_ = np.where(fringe, 1, 2)
    mix = np.where(fringe[:, None], [[60, 42, 30]], [[190, 140, 115]]).astype(float) + rng.normal(0, 3, (N, 3))
    mix[back] = mix[back] * [0.6, 0.75, 1.6]
    o, _, info = CC.clean(np.clip(mix, 0, 255), seen, X, layer0, lab_, bone, protect, [], (), log=lambda *a: None,
                          scalp=np.ones(N, bool), flatten=0)
    lo = CC._lab(o); skin_ref = np.median(CC._lab(mix[~fringe & ~back]), 0); fr_ref = np.median(CC._lab(mix[fringe]), 0)
    e_patch = float(np.linalg.norm(np.median(lo[back & ~fringe], 0)[1:] - skin_ref[1:]))
    e_fr = float(np.linalg.norm(np.median(lo[fringe], 0) - fr_ref))
    rec("11 scalp: a blue patch on skin is filled, a fringe keeps its colour", e_patch < 6.0 and e_fr < 3.0,
        "patch off by %.1f, fringe moved %.1f" % (e_patch, e_fr))


def main():
    from sforge import capture_texture as CT
    # a person who turns their head 0.35 x the body's angle, a little more to one side (as Declan does)
    pts = [(y, 0.35 * y - 6.0) for y in range(-60, 61, 10)]
    turn = CT.head_turn_model(pts)
    rec("1 inside the range: the line through the tracked frames", abs(turn(30) - (0.35 * 30 - 6)) < 0.5 and
        abs(turn(-45) - (0.35 * -45 - 6)) < 0.5, "%.1f, %.1f" % (turn(30), turn(-45)))
    lo = 0.35 * -60 - 6; hi = 0.35 * 60 - 6
    rec("2 past the range: each side holds its own end", abs(turn(-80) - lo) < 0.5 and abs(turn(85) - hi) < 0.5,
        "%.1f (%.1f), %.1f (%.1f)" % (turn(-80), lo, turn(85), hi))
    rec("3 from behind the head is not turned", turn(150) == 0 and turn(180) == 0 and turn(-170) == 0, "")
    ys = np.arange(60, 181, 1.0)
    jumps = np.abs(np.diff([turn(y) for y in ys])).max()
    rec("4 it fades with no jump", jumps < 1.0, "largest step %.2f deg per degree" % jumps)
    rec("5 too few tracked frames: no turn", CT.head_turn_model(pts[:3])(70) == 0.0, "")
    # 6 the pose: a fake fitter with four tracked frames (head turned half the body angle) and one untracked at 80
    # degrees -> held at about 15 degrees; the nose, 10 cm in front of the neck, moves about 2.6 cm
    import cv2

    class Cams:
        def __init__(self):
            self.par = {0: np.array([0.0, 0, 0, 0, 0, 3.0]), 1: np.array([10.0, 0, 0, 0, 0, 3.0]),
                        2: np.array([20.0, 0, 0, 0, 0, 3.0]), 3: np.array([30.0, 0, 0, 0, 0, 3.0]),
                        4: np.array([80.0, 0, 0, 0, 0, 3.0])}

        @staticmethod
        def rot(a, b, c):
            t = math.radians(a)
            return np.array([[math.cos(t), 0, math.sin(t)], [0, 1, 0], [-math.sin(t), 0, math.cos(t)]])
    cams = Cams()
    fitter = types.SimpleNamespace(cams=cams, bm=types.SimpleNamespace(bi={"neck01": 1}))
    # three vertices: neck (bone 1), nose (bone 2, 10 cm in front of the neck, 15 cm up), crown
    P = np.array([[0.0, 1.5, 0.0], [0.0, 1.65, 0.10], [0.0, 1.75, -0.02]])
    Jm = np.array([[1], [2], [2]])
    poses = {}
    for i in range(4):
        th = math.radians(0.5 * cams.par[i][0])                       # head turned half the body's angle
        Ry = np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
        Rh = cams.rot(*cams.par[i][:3]) @ Ry
        rv, _ = cv2.Rodrigues(Rh)
        poses[i] = (rv.reshape(3), np.array([0, 0, 3.0]))
    out = CT.turned_head_poses(fitter, P, Jm, poses, [{"i": i} for i in range(5)])
    ok = 4 in out and 0 not in out
    if ok:
        rv, th = out[4]
        Rh, _ = cv2.Rodrigues(np.asarray(rv, float))
        R_ = cams.rot(*cams.par[4][:3]); t = cams.par[4][3:6]
        neck_body, neck_head = R_ @ P[0] + t, Rh @ P[0] + th
        nose_body, nose_head = R_ @ P[1] + t, Rh @ P[1] + th
        ok = np.linalg.norm(neck_body - neck_head) < 1e-6 and np.linalg.norm(nose_body - nose_head) > 0.01
        d = "neck moved %.1e m, nose moved %.3f m" % (np.linalg.norm(neck_body - neck_head), np.linalg.norm(nose_body - nose_head))
    else:
        d = "frames given a pose: %s" % sorted(out)
    rec("6 the head turns about the neck in an untracked frame", ok, d)
    hair_checks()
    bad = [n for n, ok_, _ in R if not ok_]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
