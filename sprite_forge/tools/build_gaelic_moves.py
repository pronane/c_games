#!/usr/bin/env python3
"""Gaelic football moves from key poses (v11.12): hand pass, kick pass, solo, high catch, toe-lift pick-up, carry.

    python tools/pose_from_image.py hand_pass.png kick_strike.png ... --out poses.json --sheet check.png
    python tools/build_gaelic_moves.py poses.json --library ~/sprite_forge_motions

The key poses come from stills of each move (one picture per key moment, named after it - see KEYS). Between the
key poses the rig interpolates; the run-up and recovery come from the run stride and the carry. Each pose is
turned to face forward (the camera angle of the picture is not the player's). Any key pose missing from the file
falls back to the next best; a move whose poses are all missing is skipped. Every move written is put through
tools/check_motion.py.

The pictures are references: the clips keep only joint angles (no likeness, kit or logos), and are written to
your own library, marked as derived from your reference images."""
from __future__ import annotations
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

# key pose names (the picture file names) and what each move is made of: (time 0..1, pose, extra)
KEYS = ["hand_pass", "kick_strike", "kick_follow", "solo", "run_stride", "carry", "toe_lift", "vertical_catch"]
MOVES = {
    "gaa_hand_pass": dict(dur=0.6, loop=False, desc="hand pass: ball held in one hand, struck with the other",
                          keys=[(0.0, "carry", {}), (0.45, "hand_pass", {}), (0.7, "hand_pass", {}), (1.0, "carry", {})]),
    "gaa_kick": dict(dur=0.9, loop=False, desc="kick pass / point: plant, swing through, follow-through high",
                     keys=[(0.0, "carry", {}), (0.35, "kick_strike", {}), (0.6, "kick_follow", {}),
                           (0.8, "kick_follow", {"knee_R": 30.0}), (1.0, "carry", {})]),
    "gaa_solo": dict(dur=0.7, loop=True, desc="solo run: drop the ball onto the foot and toe it back to the hands",
                     keys=[(0.0, "run_stride", {}), (0.5, "solo", {}), (1.0, "run_stride", {})]),
    "gaa_high_catch": dict(dur=1.0, loop=False, desc="high catch: crouch, jump, take it overhead, land",
                           keys=[(0.0, "carry", {"knee_L": 40.0, "knee_R": 40.0}), (0.25, "vertical_catch", {"lift": 0.15}),
                                 (0.5, "vertical_catch", {"lift": 0.45}), (0.75, "vertical_catch", {"lift": 0.15}),
                                 (1.0, "carry", {"knee_L": 35.0, "knee_R": 35.0})]),
    "gaa_toe_lift": dict(dur=0.8, loop=False, desc="pick-up: the toe flicks the ball from the ground to the hands",
                         keys=[(0.0, "run_stride", {}), (0.45, "toe_lift", {}), (1.0, "carry", {})]),
    "gaa_carry": dict(dur=0.7, loop=True, desc="running with the ball held in one hand",
                      keys=[(0.0, "carry", {}), (0.5, "run_stride", {"arms_from": "carry"}), (1.0, "carry", {})]),
}
FALLBACK = {"carry": ["carry_b", "run_stride"], "vertical_catch": ["vertical_catch_b", "high_catch"],
            "kick_strike": ["run_stride"], "run_stride": ["carry", "carry_b"]}
ARMS = ("arm_L", "arm_R", "elbow_L", "elbow_R")


def facing_forward(pose):
    p = copy.deepcopy(pose)
    h = list(p.get("hips") or [0.0, 0.0, 0.0]); h[1] = 0.0; p["hips"] = h
    return p


def get(poses, name):
    for n in [name] + FALLBACK.get(name, []):
        if n in poses:
            return facing_forward(poses[n]["pose"])
    return None


def build(poses, name, spec):
    keys = []
    for t, pn, extra in spec["keys"]:
        p = get(poses, pn)
        if p is None:
            return None
        extra = dict(extra)
        src = extra.pop("arms_from", None)
        if src:
            q = get(poses, src)
            if q:
                for k in ARMS:
                    if k in q:
                        p[k] = copy.deepcopy(q[k])
        p.update(extra)
        p["ground"] = "lift" not in extra
        keys.append([t, p])
    return dict(name=name, category="Gaelic football", desc=spec["desc"], loop=spec["loop"], duration=spec["dur"],
                source="keyed from reference stills (tools/pose_from_image.py)", origin="user",
                licence=dict(spdx="LicenseRef-user-reference", author="you", redistribution="no",
                             notes="joint angles from your own reference images; kept in your library"),
                keys=keys)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poses")
    ap.add_argument("--library", required=True)
    a = ap.parse_args(argv)
    import check_motion as CM
    poses = json.load(open(a.poses))
    lib = os.path.abspath(os.path.expanduser(a.library)); os.makedirs(lib, exist_ok=True)
    bad = 0
    for name, spec in MOVES.items():
        rec = build(poses, name, spec)
        if rec is None:
            print("%-16s skipped (no key poses)" % name); continue
        json.dump(rec, open(os.path.join(lib, name + ".json"), "w"), indent=1)
        res = [x for x in CM.check_clip(rec, name) if x[1] is False]
        bad += bool(res)
        print("%-16s %s" % (name, "ok" if not res else "; ".join("%s: %s" % (x[0], x[2]) for x in res)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
