#!/usr/bin/env python3
"""Does a real mocap take import cleanly onto the shared skeleton? (v11.6, synthetic, no downloads)

    python tools/test_mocap_import.py

A BVH is written here the way the free CMU database ships its takes: its own unit (a person ~22 units tall,
not metres or centimetres), 120 fps, the figure facing sideways (+x), hips well off the origin, a long take with
a T-pose first and one right-hand punch in the middle. `forge.py motion import --peak hand_R` must:
  * scale it to a person (not a 0.2 m doll),
  * turn it so the strike goes forward (+z), at the opponent,
  * put the feet on the floor and start at the origin,
  * cut the one strike out of the take and resample it to 30 fps,
  * keep the pose: joints within 2 cm of the take, measured from the hips.
Then a game pack's `prefer` list picks that clip over the generic one, and the old --raw path still works."""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
PY = sys.executable
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-58s %s" % ("PASS" if ok else "FAIL", name, detail))


U = 1.0 / 0.077          # one metre in this file's unit (a 1.7 m person is ~22 units)

JOINTS = [  # name, parent, offset in metres (x = the figure's left, y up, z forward)
    ("Hips", None, (0, 0, 0)),
    ("Spine", "Hips", (0, 0.10, 0)), ("Spine1", "Spine", (0, 0.20, 0)), ("Neck", "Spine1", (0, 0.20, 0)),
    ("Head", "Neck", (0, 0.10, 0)),
    ("LeftShoulder", "Spine1", (0.05, 0.15, 0)), ("LeftArm", "LeftShoulder", (0.15, 0, 0)),
    ("LeftForeArm", "LeftArm", (0.28, 0, 0)), ("LeftHand", "LeftForeArm", (0.26, 0, 0)),
    ("RightShoulder", "Spine1", (-0.05, 0.15, 0)), ("RightArm", "RightShoulder", (-0.15, 0, 0)),
    ("RightForeArm", "RightArm", (-0.28, 0, 0)), ("RightHand", "RightForeArm", (-0.26, 0, 0)),
    ("LeftUpLeg", "Hips", (0.10, -0.05, 0)), ("LeftLeg", "LeftUpLeg", (0, -0.42, 0)),
    ("LeftFoot", "LeftLeg", (0, -0.41, 0)), ("LeftToeBase", "LeftFoot", (0, -0.06, 0.14)),
    ("RightUpLeg", "Hips", (-0.10, -0.05, 0)), ("RightLeg", "RightUpLeg", (0, -0.42, 0)),
    ("RightFoot", "RightLeg", (0, -0.41, 0)), ("RightToeBase", "RightFoot", (0, -0.06, 0.14)),
]
FPS = 120
SECONDS = 4.0
PUNCH_AT = 2.5             # seconds: the right hand is furthest forward here


def _channels(t):
    """per joint (Z, Y, X) degrees for time t, root position in metres"""
    ang = {j[0]: [0.0, 0.0, 0.0] for j in JOINTS}
    pos = np.array([3.0, 0.93, -1.5])                       # hips off the origin, standing height
    yaw = 90.0                                                 # the figure faces +x the whole take
    if t > 0.8:                                                # after the T-pose: arms down to a guard
        ang["LeftArm"] = [-70.0, 0.0, 0.0]; ang["RightArm"] = [70.0, 0.0, 0.0]
        ang["LeftForeArm"] = [0.0, -100.0, 0.0]; ang["RightForeArm"] = [0.0, 100.0, 0.0]
        ang["LeftUpLeg"] = [0, 0, -12.0]; ang["LeftLeg"] = [0, 0, 18.0]
        ang["RightUpLeg"] = [0, 0, -12.0]; ang["RightLeg"] = [0, 0, 18.0]
        pos[1] -= 0.03
        # the punch: right arm swings to point straight forward, elbow straightens
        a = math.exp(-((t - PUNCH_AT) / 0.12) ** 2)
        ang["RightArm"] = [70.0 * (1 - a), 90.0 * a, 0.0]
        ang["RightForeArm"] = [0.0, 100.0 * (1 - a), 0.0]
    return ang, pos, yaw


def write_bvh(path):
    kids = {}
    for n, p, o in JOINTS:
        kids.setdefault(p, []).append((n, o))
    L = ["HIERARCHY"]

    def emit(n, o, depth, root=False):
        ind = "\t" * depth
        L.append("%s%s %s" % (ind, "ROOT" if root else "JOINT", n))
        L.append(ind + "{")
        L.append("%s\tOFFSET %.5f %.5f %.5f" % (ind, o[0] * U, o[1] * U, o[2] * U))
        L.append("%s\tCHANNELS %s" % (ind, "6 Xposition Yposition Zposition Zrotation Yrotation Xrotation" if root
                                      else "3 Zrotation Yrotation Xrotation"))
        if n in kids:
            for c, co in kids[n]:
                emit(c, co, depth + 1)
        else:
            L.append("%s\tEnd Site" % ind); L.append("%s\t{" % ind)
            L.append("%s\t\tOFFSET 0 %.5f 0" % (ind, -0.05 * U)); L.append("%s\t}" % ind)
        L.append(ind + "}")
    emit("Hips", (0, 0, 0), 0, root=True)
    n = int(SECONDS * FPS)
    L += ["MOTION", "Frames: %d" % n, "Frame Time: %.7f" % (1.0 / FPS)]
    for f in range(n):
        ang, pos, yaw = _channels(f / FPS)
        row = [pos[0] * U, pos[1] * U, pos[2] * U]
        for nm, _, _ in JOINTS_ORDER:
            z, y, x = ang[nm]
            if nm == "Hips":
                y += yaw
            row += [z, y, x]
        L.append(" ".join("%.4f" % v for v in row))
    open(path, "w").write("\n".join(L) + "\n")


def _order():
    kids = {}
    for n, p, o in JOINTS:
        kids.setdefault(p, []).append((n, p, o))
    out = []

    def walk(n):
        out.append(next(j for j in JOINTS if j[0] == n))
        for c in kids.get(n, []):
            walk(c[0])
    walk("Hips")
    return out


JOINTS_ORDER = _order()


def main():
    tmp = tempfile.mkdtemp(prefix="sf_mocap_")
    try:
        bvh = os.path.join(tmp, "take_01.bvh")
        write_bvh(bvh)
        lib = os.path.join(tmp, "motions")
        cmd = [PY, os.path.join(HERE, "forge.py"), "motion", "import", "--library", lib, bvh, "--name", "test_cross",
               "--once", "--peak", "hand_R:0.3:0.3", "--spdx", "CC0-1.0", "--author", "test", "--redistribution", "yes"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        rec("import runs", r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[0][:90] if (r.stdout + r.stderr).strip() else "")
        d = json.load(open(os.path.join(lib, "test_cross.json")))
        imp = d["import"]; c = imp["canonical"]
        rec("cut around the strike", abs(c["peak_s"] - PUNCH_AT) < 0.1 and abs(c["cut_s"][0] - (c["peak_s"] - 0.3)) < 0.05,
            "peak %.2fs cut %s" % (c["peak_s"], c["cut_s"]))
        rec("resampled to 30 fps", abs(c["fps"] - 30) < 0.5 and 17 <= len(d["keys"]) <= 20, "%d keys" % len(d["keys"]))
        rec("turned from the take's sideways facing", abs(c["turned_deg"]) > 45, "turned %+.0f deg" % c["turned_deg"])
        rec("pose kept (joints within 2 cm)", imp["projection_mean_m"] < 0.02, "mean %.3f m" % imp["projection_mean_m"])
        from sforge.rig import evaluate
        keys = [(t, p) for t, p in d["keys"]]
        peak = max(keys, key=lambda k: evaluate(k[1]).world["hand_R"][2, 3] - evaluate(k[1]).world["hips"][2, 3])[1]
        st = evaluate(peak)
        reach = st.world["hand_R"][:3, 3] - st.world["hips"][:3, 3]
        rec("the punch goes forward, not sideways", reach[2] > 0.45 and abs(reach[0]) < 0.25, "hand from hips %s" % np.round(reach, 2))
        h = st.world["head"][1, 3] - min(st.world["foot_L"][1, 3], st.world["foot_R"][1, 3])
        rec("a person-sized figure (not a 0.2 m doll)", 1.2 < h < 1.9, "feet to head %.2f m" % h)
        low = min(evaluate(p).world["foot_L"][1, 3] for _, p in keys)
        rec("starts at the origin, feet on the floor", abs(keys[0][1]["pos"][0]) < 1e-6 and abs(keys[0][1]["pos"][1]) < 1e-6
            and low < 0.15, "pos0 %s, lowest foot %.2f" % (keys[0][1]["pos"], low))
        # the old path is still there
        r2 = subprocess.run([PY, os.path.join(HERE, "forge.py"), "motion", "import", "--library", lib, bvh, "--name",
                             "raw_take", "--raw", "--spdx", "CC0-1.0", "--author", "t", "--redistribution", "yes"],
                            capture_output=True, text=True)
        raw = json.load(open(os.path.join(lib, "raw_take.json")))
        rec("--raw keeps the whole take", r2.returncode == 0 and len(raw["keys"]) == int(SECONDS * FPS), "%d keys" % len(raw["keys"]))
        # a game pack prefers the specific clip, then falls back to the generic one
        from sforge import gamepack as GP, motionset as MS
        from sforge.build import BuildConfig
        pk = GP.load("boxing")
        pk_path = os.path.join(tmp, "box.json")
        raw_pack = json.load(open(pk["path"]))
        for m in raw_pack["moves"]:
            if m["name"] == "cross":
                m["prefer"] = ["test_cross"]
            if m["name"] == "jab":
                m["prefer"] = ["no_such_clip"]
        json.dump(raw_pack, open(pk_path, "w"))
        cfg = BuildConfig()
        GP.apply(cfg, pk_path)
        cfg.motion_library = lib
        MS.apply_cfg(cfg)
        mv = {m.name: m for m in cfg.moves}
        rec("pack prefer picks the specific clip", mv["cross"].motion == "lib:test_cross" and mv["cross"].motion_source == "library",
            "%s (%s)" % (mv["cross"].motion, mv["cross"].motion_source))
        rec("missing preferred clip falls back to the generic", mv["jab"].motion == "lib:punch", mv["jab"].motion)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
