#!/usr/bin/env python3
"""v11.22 joint-track fitter (fed back from Arena FC's SkillCorner body-pose import).

    python tools/test_jointtrack.py

  1 a known clip, turned into named 3D joint tracks (SkillCorner naming, Z-up, facing an
    arbitrary way across the pitch), fits back onto the shared skeleton: low bone error,
    knee angles recovered, the player turned to face forward
  2 a frame missing a limb joint is filled from its neighbours; too few frames is an error
  3 keys_record writes a library move the motion library loads and samples
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sforge import jointtrack as JT   # noqa: E402
from sforge import rig                # noqa: E402
from sforge import motionlib as ML    # noqa: E402
from sforge.motions import LIB        # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1; print("  PASS  " + name)
    else:
        failed += 1; print("  FAIL  " + name + ("  " + detail if detail else ""))


JOINTS = {"lShoulder": "upperarm_L", "rShoulder": "upperarm_R", "lElbow": "forearm_L", "rElbow": "forearm_R",
          "lWrist": "hand_L", "rWrist": "hand_R", "lHip": "thigh_L", "rHip": "thigh_R",
          "lKnee": "shin_L", "rKnee": "shin_R", "lAnkle": "foot_L", "rAnkle": "foot_R"}


def tracks_from(motion, n=30, heading=math.radians(130), drop=None):
    """sample a library motion through FK and write SkillCorner-style named joints (Z up)."""
    c, s = math.cos(heading), math.sin(heading)
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    frames, knees = [], []
    for i in range(n):
        pose = motion.sample(i / (n - 1))[0]
        W = rig._fk(rig.local_rotations(pose), np.zeros(3))
        P = {nm: R @ W[b][:3, 3] for nm, b in JOINTS.items()}
        head = R @ W["head"][:3, 3]
        side = P["lShoulder"] - P["rShoulder"]
        P["lEar"] = head + .08 * side / np.linalg.norm(side); P["rEar"] = head - .08 * side / np.linalg.norm(side)
        P["nose"] = head
        fwd = R @ np.array([0, 0, 1.0])
        for sd in "lr":
            P[sd + "Heel"] = P[sd + "Ankle"] - .05 * fwd + np.array([0, -.06, 0])
            P[sd + "BigToe"] = P[sd + "Ankle"] + .16 * fwd + np.array([0, -.07, 0])
        fr = {k: (float(v[0]), float(-v[2]), float(v[1])) for k, v in P.items()}   # rig -> source (Z up)
        if drop and i == drop:
            fr.pop("lKnee")
        frames.append(fr)
        knees.append((pose.get("knee_L", 0.0), pose.get("knee_R", 0.0)))
    return frames, np.array(knees, float)


print("1 known clip -> joint tracks -> fit")
run = LIB["run"]
frames, knees = tracks_from(run)
keys, rep = JT.fit_tracks(frames, fps=25)
check("fit error under 4 deg", rep["mean_bone_err_deg"] < 4.0, str(rep["mean_bone_err_deg"]))
got = np.array([(k[1]["knee_L"], k[1]["knee_R"]) for k in keys])
err = float(np.abs(got - knees).mean())
check("knee flexion recovered within 8 deg", err < 8.0, "%.1f deg" % err)
check("player turned to face forward (heading found)", abs(abs(rep["heading_deg"]) - 130) < 20 or abs(abs(rep["heading_deg"]) - 230) < 20,
      str(rep["heading_deg"]))
check("root in place, on the ground", all(k[1]["pos"] == (0.0, 0.0) and k[1]["ground"] for k in keys))

print("2 gaps")
frames2, _ = tracks_from(run, drop=12)
keys2, rep2 = JT.fit_tracks(frames2, fps=25)
check("a frame missing a knee is filled", len(keys2) == 30 and rep2["frames_complete"] == 29)
try:
    JT.fit_tracks([None] * 10 + frames[:2], fps=25)
    check("too few complete frames is an error", False)
except ValueError:
    check("too few complete frames is an error", True)

print("3 library record")
lic = dict(spdx="MIT", custom_text="", author="test", source_url="https://example.org", redistribution="yes",
           attribution="test", notes="")
rec = JT.keys_record("jt_run", keys, rep, lic, category="Mocap", loop=True, source="test")
with tempfile.TemporaryDirectory() as d:
    with open(os.path.join(d, "jt_run.json"), "w") as f:
        json.dump(rec, f)
    m = ML.as_motion("jt_run", path=d)
    ok = m is not None
    if ok:
        p = m.sample(.5)[0]
        ok = all(math.isfinite(float(np.ravel(v)[0])) for v in p.values() if isinstance(v, (int, float, tuple, list)) and not isinstance(v, bool))
    check("record loads as a library motion and samples", ok)

print("RESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
