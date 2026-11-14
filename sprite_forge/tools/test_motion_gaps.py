#!/usr/bin/env python3
"""Motion clips for any game: the import puts every take right, and the checker catches a bad clip (v11.11).

    python tools/test_motion_gaps.py

Synthetic, no downloads (CMU clips may not be shipped). Takes are made from the CC0 starter's poses, shaped like
the real takes that went wrong, and imported with the same code as `forge.py motion import`:
  1 a walk that turns a corner part-way: the loop kept still walks forward (walk_casual walked sideways)
  2 a kick whose furthest reach is the backswing still faces the opponent (soccer_kick came in backwards)
  3 a spinning kick that faces away on average is not turned round: it still kicks forward
  4 a take that lies down and then stands with the feet 13 cm higher than the body lay: the standing part stands
    on the floor and the lying part lies on it (get_up's standing part floated 13 cm)
Then tools/check_motion.py, the gate for any clip, on records built to break one rule each:
  5 good clips pass (the starter's walk, kick and wave)
  6 each broken clip fails for its own reason: a glitch jump between keys (pops), a clip floating off the floor,
    a clip turned away from the opponent, a walk loop that turns, a "block" with the hands down, a "fall" that
    stays standing, a "celebration" with no hand over the head, a "dodge" that does not duck
  7 a game pack's clips can be checked by pack name (--pack), and a clip name like "swing" is not read as "win"."""
from __future__ import annotations
import copy
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-60s %s" % ("PASS" if ok else "FAIL", name, detail))


def ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    M = np.eye(4); M[0, 0], M[0, 2], M[2, 0], M[2, 2] = c, s, -s, c
    return M


def rx(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    M = np.eye(4); M[1, 1], M[1, 2], M[2, 1], M[2, 2] = c, -s, s, c
    return M


def main():
    from sforge import motionlib as ML, rig, rigrec as RR
    import check_motion as CM
    man = RR.from_mannequin(clips=[])
    starter = ML.MotionLibrary(os.path.join(HERE, "_no_user_library_"))

    def worlds(pose, M=np.eye(4)):
        w = rig.evaluate(pose).world
        return np.stack([M @ w[b] for b in man.bones])

    def poses(name, n):
        """n evenly spaced poses through a starter clip (interpolated by the rig)"""
        d = starter.load(name)
        ks = d["keys"]
        out = []
        for i in range(n):
            t = i / max(1, n - 1) if not d.get("loop") else (i % n) / n
            j = max(0, np.searchsorted([k[0] for k in ks], t) - 1)
            out.append(copy.deepcopy(ks[min(j, len(ks) - 1)][1]))
        return out

    def hips_heading(keys):
        h = [rig.evaluate(k[1]).world["hips"][:3, 2] for k in keys]
        h = np.degrees([math.atan2(z[0], z[2]) for z in h])
        return float(np.degrees(math.atan2(np.sin(np.radians(h)).mean(), np.cos(np.radians(h)).mean()))), h

    fps = 30.0
    # 1 a walk: two cycles straight ahead, then the walker turns a corner and walks four cycles at 90 degrees
    cyc = poses("walk", 12)
    W = []
    pos = np.zeros(3)
    for c in range(6):
        for i, p in enumerate(cyc):
            ang = 0.0 if c < 2 else 90.0
            p = copy.deepcopy(p); p["pos"] = (0.0, 0.0)
            M = ry(ang); M[:3, 3] = pos; pos = pos + M[:3, :3] @ np.array([0, 0, 0.11])
            W.append(worlds(p, M))
    keys, _, info = ML.canonical_keys(man, np.stack(W), fps, cycle=True)
    mh, _ = hips_heading(keys)
    rec("1 a walk cut where the walker had turned faces forward", abs(mh) < 15, "faces %+.0f deg" % mh)
    # 2 a kick whose furthest reach is the backswing: the leg swings far back, then kicks forward a little
    W = []
    for i in range(30):
        p = copy.deepcopy(starter.load("idle")["keys"][0][1])
        sw = -75.0 * math.sin(math.pi * i / 14) if i < 14 else 40.0 * math.sin(math.pi * (i - 14) / 16)
        p["leg_R"] = [sw, 0.0, 0.0]; p["pos"] = (0.0, 0.0)
        W.append(worlds(p, ry(37.0)))
    keys, _, info = ML.canonical_keys(man, np.stack(W), fps, peak=("foot_R", 0.4, 0.4))
    mh, _ = hips_heading(keys)
    rec("2 a kick peaking on the backswing still faces the opponent", abs(mh) < 90, "faces %+.0f deg" % mh)
    # 3 a spinning kick: the body turns 300 degrees through it
    W = []
    for i in range(30):
        p = copy.deepcopy(starter.load("idle")["keys"][0][1])
        p["leg_R"] = [75.0 * math.sin(math.pi * i / 29), 0.0, 0.0]; p["pos"] = (0.0, 0.0)
        W.append(worlds(p, ry(150.0 + 300.0 * i / 29)))
    keys, _, info = ML.canonical_keys(man, np.stack(W), fps, peak=("foot_R", 0.5, 0.5))
    reach = max(((rig.evaluate(k[1]).world["foot_R"][:3, 3] - rig.evaluate(k[1]).world["hips"][:3, 3]) for k in keys),
                key=lambda v: v[0] ** 2 + v[2] ** 2)
    rec("3 a spinning kick is not turned round: it still kicks forward", reach[2] > 0.2, "foot from hips %s" % np.round(reach, 2))
    # 4 lying, then standing with the feet 13 cm higher than the lying body's floor (get_up: markers on the back,
    # a soft mat - the take's floors differ)
    idle = copy.deepcopy(starter.load("idle")["keys"][0][1]); idle["pos"] = (0.0, 0.0)
    W = []
    for i in range(30):
        M = rx(-90.0); M[1, 3] = 0.25
        W.append(worlds(idle, M))
    lying = np.stack(W)
    low_lying = min(float(np.min([(lying[f, man.bones.index(j)] @ np.r_[o, 1])[1] for j, o in rig._CONTACT])) for f in range(30))
    lying[:, :, 1, 3] -= low_lying                                   # the body rests at y = 0
    standing = np.stack([worlds(idle) for _ in range(30)])
    standing[:, :, 1, 3] += 0.13                                     # the feet stand 13 cm up
    keys, Wk, info = ML.canonical_keys(man, np.concatenate([lying, standing]), fps, start=0.0)
    fl = man.bones.index("foot_L")
    feet_end = float(np.mean([(Wk[f, fl] @ np.r_[0, -0.08, -0.06, 1])[1] for f in range(-8, 0)]))
    body_start = float(np.min([[(Wk[f, man.bones.index(j)] @ np.r_[o, 1])[1] for j, o in rig._CONTACT] for f in range(5, 12)]))
    rec("4 standing after lying down: feet on the floor", abs(feet_end) < 0.03, "heel at %.3f m" % feet_end)
    rec("4 ... and the lying part lies on the floor", abs(body_start) < 0.03, "lowest at %.3f m" % body_start)

    # 5/6 the checker
    def record(name, keys, loop=False, dur=1.0):
        return dict(name=name, keys=[[t, p] for t, p in keys], loop=loop, duration=dur)
    good = []
    for n in ("walk", "kick", "wave"):
        d = starter.load(n)
        res = CM.check_clip(record(n, d["keys"], d.get("loop", False), d.get("duration") or 1.0), n)
        good.append((n, [a for a, ok, _ in res if ok is False]))
    rec("5 good clips pass", all(not f for _, f in good), str(good))
    walk = starter.load("walk"); idle_k = starter.load("idle")["keys"]
    stand = [(i / 9, copy.deepcopy(idle_k[0][1])) for i in range(10)]

    def mutate(keys, fn):
        ks = [(t, copy.deepcopy(p)) for t, p in keys]
        for i, (t, p) in enumerate(ks):
            fn(i, p)
        return ks

    def yaw(p, d):
        h = list(p.get("hips") or [0.0, 0.0, 0.0])
        return [h[0], h[1] + d, h[2]]

    def lift_at(i_bad, h):
        return lambda i, p: p.__setitem__("lift", h if i == i_bad else p.get("lift", 0.0))
    cases = [
        ("pops", record("idle_pop", mutate(stand, lift_at(5, 1.2)), dur=1.0)),
        ("floor", record("idle_float", mutate(stand, lambda i, p: p.__setitem__("lift", 0.4)), dur=1.0)),
        ("facing", record("idle_back", mutate(stand, lambda i, p: p.__setitem__("hips", yaw(p, 180.0))), dur=1.0)),
        (("loop", "turning"), record("walk_turn", mutate(walk["keys"], lambda i, p: p.__setitem__("hips", yaw(p, 25.0 * i))), loop=True, dur=1.0)),
        ("move", record("block_down", stand, dur=1.0)),
        ("move", record("fall_standing", stand, dur=1.0)),
        ("move", record("celebrate_still", stand, dur=1.0)),
        ("move", record("dodge_upright", stand, dur=1.0)),
    ]
    for want, r in cases:
        res = CM.check_clip(r, r["name"])
        fails = sorted(set(a for a, ok, _ in res if ok is False))
        want = sorted(want) if isinstance(want, tuple) else [want]
        rec("6 caught: %s" % r["name"], fails == want, "failed on %s" % fails)
    # 7 --pack, and names
    tmp = tempfile.mkdtemp(prefix="sf_motion_")
    try:
        rc = CM.main(["--pack", "boxing", "--library", tmp])
        pc = CM.pack_clips("boxing", tmp)
        ko = [r for mv, f, r in pc if mv == "ko"]
        rec("7 --pack checks every move of a pack, procedural fallbacks too", rc == 0 and len(pc) == 9 and ko and
            not [x for x in CM.check_clip(ko[0], "ko") if x[1] is False], "%d moves, exit %d" % (len(pc), rc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rec("7 'swing' is a swing, not a win", CM.kind_of("swing_forehand") == "swing" and CM.kind_of("victory_win") == "celebrate", "")
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
