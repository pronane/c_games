#!/usr/bin/env python3
"""v11.23 match capture (video -> moves) - the parts that run without the big detector /
2D-pose downloads.

    python tools/test_matchcapture.py

  1 tracker links boxes across frames and splits two players
  2 2D kick detector: a synthetic swing (knee bending then straightening, foot whipping
    through) is found on the right foot; a jog is not a kick
  3 the committed 2D -> 3D lifter: a known clip seen from a camera, lifted and fitted
    back onto the skeleton, keeps its knee flexion
  4 merge renumbers parallel per-clip folders into one library folder
  5 the model registry lists a licence for every model
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

from sforge import matchcapture as M   # noqa: E402
from sforge import jointtrack as JT    # noqa: E402
from sforge import rig                 # noqa: E402
from sforge.motions import LIB         # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok: passed += 1; print("  PASS  " + name)
    else: failed += 1; print("  FAIL  " + name + ("  " + detail if detail else ""))


print("1 tracker")
tr = M.Tracker()
for f in range(30):
    tr.update(f, [(100 + f * 3, 200, 140 + f * 3, 300, .9), (600 - f * 2, 210, 640 - f * 2, 310, .9)])
tracks = [t for t in tr.finish() if len(t["frames"]) >= 25]
check("two players, two continuous tracks", len(tracks) == 2, str([len(t["frames"]) for t in tr.done]))

# Halpe-26 2D skeleton generator (image px, y down) for tests 2-3
REST = {5: (-12, -60), 6: (12, -60), 11: (-8, 0), 12: (8, 0), 0: (0, -78), 3: (-5, -76), 4: (5, -76),
        7: (-16, -35), 8: (16, -35), 9: (-18, -12), 10: (18, -12)}


def skeleton(knee_angle_r, swing_r, t_leg_l=0.0):
    K = np.zeros((26, 3)); K[:, 2] = .9
    for j, (x, y) in REST.items(): K[j, :2] = (300 + x, 400 + y)
    for side, hip, kn, an, toe, heel, sw, ka in (("L", 11, 13, 15, 20, 24, t_leg_l, 170.0), ("R", 12, 14, 16, 21, 25, swing_r, knee_angle_r)):
        hx, hy = K[hip, :2]
        th = math.radians(sw)                                   # thigh angle from vertical (+ forward)
        kx, ky = hx + 40 * math.sin(th), hy + 40 * math.cos(th)
        sh = th - math.radians(180 - ka)                        # shin bends back by (180 - knee)
        ax, ay = kx + 40 * math.sin(sh), ky + 40 * math.cos(sh)
        K[kn, :2] = (kx, ky); K[an, :2] = (ax, ay); K[toe, :2] = (ax + 10, ay + 3); K[heel, :2] = (ax - 4, ay + 2)
    return K


print("2 kick detector")
fps = 15.0
seq = []
for i in range(30):
    if 10 <= i < 14:   seq.append(skeleton(95, -35 + (i - 10) * 3))           # back-swing, knee bent
    elif 14 <= i < 17: seq.append(skeleton(110 + (i - 14) * 30, -20 + (i - 14) * 35))  # whip through, knee opens
    else:              seq.append(skeleton(168, 0))
ks = M.strikes_2d(np.array(seq), fps)
check("synthetic kick found on the right foot", len(ks) == 1 and ks[0][1] == "R", str(ks))
jog = [skeleton(140 + 20 * math.sin(i * .9), 18 * math.sin(i * .9), -18 * math.sin(i * .9)) for i in range(45)]
check("a jog is not a kick", M.strikes_2d(np.array(jog), fps) == [], str(M.strikes_2d(np.array(jog), fps)))

print("3 lifter round trip")
models = os.path.join(ROOT, "sforge", "models")
try:
    lifter = M.Lifter(models)
except Exception as e:  # onnxruntime missing
    lifter = None
    check("lifter loads (onnxruntime installed)", False, str(e))
if lifter is not None:
    run = LIB["run"]
    JN = {"nose": "head", "lEar": "head", "rEar": "head", "lShoulder": "upperarm_L", "rShoulder": "upperarm_R",
          "lElbow": "forearm_L", "rElbow": "forearm_R", "lWrist": "hand_L", "rWrist": "hand_R", "lHip": "thigh_L",
          "rHip": "thigh_R", "lKnee": "shin_L", "rKnee": "shin_R", "lAnkle": "foot_L", "rAnkle": "foot_R"}
    az, el = math.radians(70), math.radians(15)
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    Ks, knees = [], []
    for i in range(30):
        pose = run.sample(i / 29)[0]
        W = rig._fk(rig.local_rotations(pose), np.zeros(3))
        P = {n: W[b][:3, 3] for n, b in JN.items()}
        fwd = np.array([0, 0, 1.0])
        for s in "lr":
            P[s + "Heel"] = P[s + "Ankle"] - .05 * fwd + np.array([0, -.06, 0])
            P[s + "BigToe"] = P[s + "Ankle"] + .16 * fwd + np.array([0, -.07, 0])
        K = np.zeros((26, 3)); K[:, 2] = .9
        meta = json.load(open(os.path.join(models, "lifter_v1.json")))
        for n, hidx in zip(meta["joints"], meta["halpe_index"]):
            p = P[n]
            x = ca * p[0] - sa * p[2]; zc = sa * p[0] + ca * p[2]; y = ce * p[1] - se * zc
            K[hidx, :2] = (500 + 200 * x, 500 - 200 * y)
        Ks.append(K); knees.append((pose.get("knee_L", 0.0), pose.get("knee_R", 0.0)))
    Y = lifter(np.array(Ks))
    L = np.full((30, 33, 3), np.nan); L[:, M.LIFT_SLOTS] = Y
    keys, rep = JT.fit_landmarks(L, fps=25)
    got = np.array([(k[1]["knee_L"], k[1]["knee_R"]) for k in keys])
    err = float(np.abs(got - np.array(knees)).mean())
    check("lifted + fitted run keeps knee flexion within 20 deg", err < 20, "%.1f deg" % err)
    check("fit error under 6 deg", rep["mean_bone_err_deg"] < 6, str(rep["mean_bone_err_deg"]))

print("4 merge")
with tempfile.TemporaryDirectory() as d:
    for c in ("a", "b"):
        os.makedirs(os.path.join(d, c))
        rec = {"name": "x_strike_001", "keys": [], "duration": 1.0}
        json.dump(rec, open(os.path.join(d, c, "x_strike_001.json"), "w"))
        json.dump({"takes": [{"name": "x_strike_001", "kind": "strike", "duration": 1.0}]}, open(os.path.join(d, c, "_import.json"), "w"))
    idx = M.merge([os.path.join(d, "a"), os.path.join(d, "b")], os.path.join(d, "out"))
    names = sorted(t["name"] for t in idx["takes"])
    check("two clips' moves renumbered without clashing", names == ["mc_strike_001", "mc_strike_002"]
          and all(os.path.isfile(os.path.join(d, "out", n + ".json")) for n in names), str(names))

print("5 registry")
reg = M.registry()["models"]
check("every model has a licence and a file", all(m.get("licence") and m.get("file") for m in reg.values()))
check("our own lifter is committed and registered", os.path.isfile(os.path.join(models, reg["lifter_v1"]["file"])))

print("6 labelled events (SoccerTrack v2 adapter)")
sys.path.insert(0, HERE)
import soccertrack_capture as ST  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    bas = {"actions": [
        {"gameTime": "1 - 00:10", "position": "10000", "label": "PASS", "team": "left", "player_id": "117093_L_9", "visibility": "visible"},
        {"gameTime": "2 - 45:04", "position": str(45 * 60000 + 4000), "label": "Shot", "team": "right", "player_id": 170959},
        {"gameTime": "1 - 00:20", "position": "20000", "label": "HEADER", "team": "left", "player_id": None, "visibility": "not shown"}]}
    json.dump(bas, open(os.path.join(d, "b.json"), "w"))
    ev = ST.parse_bas(os.path.join(d, "b.json"))
    check("labels case-folded, 'not shown' dropped, half-2 time made in-half",
          [(e["half"], e["frame"], e["label"]) for e in ev] == [(1, 250, "pass"), (2, 100, "shot")], str(ev))
    check("player ids: jersey form and numeric form", ST.player_key("117093_L_9", "left") == ("jersey", "left", "9")
          and ST.player_key(170959, "right") == ("pid", 170959))
    gsr = {"info": {}, "images": [{"image_id": "3000001"}, {"image_id": "3000002"}],
           "annotations": [{"image_id": "3000002", "supercategory": "object", "attributes": {"team": "left", "jersey": "9", "player_id": 5},
                            "bbox_image": {"x": 10, "y": 20, "w": 30, "h": 70}},
                           {"image_id": "3000002", "supercategory": "pitch"}]}
    json.dump(gsr, open(os.path.join(d, "g.json"), "w"))
    bx = ST.boxes_for(os.path.join(d, "g.json"), {("jersey", "left", "9"): {1}})
    check("GSR streamed: box found by team + jersey at frame = image_id - first", bx.get(("jersey", "left", "9")) == {1: (10.0, 20.0, 40.0, 90.0)}, str(dict(bx)))
K = np.array(seq)
cf, ft = M.contact_frame(K, 13)
check("labelled contact refined onto the kicking foot within the swing", ft == "R" and 10 <= cf <= 17, "%d %s" % (cf, ft))
check("every label maps to a kind with a window", all(len(v) == 4 and v[2] + v[3] > 1 for v in M.EVENT_KINDS.values()))

print("RESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
