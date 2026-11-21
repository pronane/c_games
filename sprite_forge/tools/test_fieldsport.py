#!/usr/bin/env python3
"""v11.21 field-sport pack and bind conform (fed back from Arena FC).

    python tools/test_fieldsport.py

  1 every field-sport clip registers in the motion library, samples to finite joints, and passes `qa()`
  2 qa() really catches the two Arena bugs it exists for: a hands-up pose in a ground clip, and a ball
    clip with no ball at its contact frame
  3 the soccer game pack offers the new moves, each pointing at a real clip, with events inside the clip
  4 bindconform: a mesh built in an A-pose and conformed to a hanging-arm bind pose ends up with its
    arm vertices where the target skeleton's arm is; aligned bones are left untouched
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sforge import fieldsport_motions as fs          # noqa: E402
from sforge.bindconform import conform_to_bind, minrot  # noqa: E402
from sforge.motions import LIB, K, P, STAND          # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1; print("  PASS  " + name)
    else:
        failed += 1; print("  FAIL  %s %s" % (name, detail))


print("== 1 clips ==")
fs.register()
check("15 field-sport clips registered", all(n in LIB for n in fs.CLIPS) and len(fs.CLIPS) == 15, str(len(fs.CLIPS)))
check("every clip has events", set(fs.EVENTS) == set(fs.CLIPS))
bad = []
for n in fs.CLIPS:
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        pose, _ = LIB[n].sample(t)
        for k, v in pose.items():
            vals = v if isinstance(v, (tuple, list)) else (v,)
            if any(isinstance(x, (int, float)) and not math.isfinite(x) for x in vals):
                bad.append("%s@%.2f %s" % (n, t, k))
check("every clip samples to finite joints", not bad, ", ".join(bad[:5]))
report = fs.qa_all()
check("every clip passes the field-sport QA", all(not e for e in report.values()),
      "; ".join(e for es in report.values() for e in es))

print("== 2 the QA catches the bugs it is for ==")
LIB.pop("fs_test_handsup", None); LIB.pop("fs_test_noball", None)
from sforge.motions import M  # noqa: E402
M("fs_test_handsup", "Skill", "test", keys=K((0, P(STAND)), (0.5, P(STAND, arm_L=(150, 10, 0), arm_R=(150, 10, 0))), (1, P(STAND))))
M("fs_test_noball", "Ball", "test", keys=K((0, P(STAND)), (0.5, P(STAND)), (1, P(STAND))))
fs.EVENTS["fs_test_handsup"] = fs._ev()
fs.EVENTS["fs_test_noball"] = fs._ev(ball_contact=0.5)
check("a hands-up pose in a ground clip is flagged", any("arm raised" in e for e in fs.qa("fs_test_handsup")))
check("a ball clip without the ball at contact is flagged", any("ball not placed" in e for e in fs.qa("fs_test_noball")))
fs.EVENTS.pop("fs_test_handsup"); fs.EVENTS.pop("fs_test_noball")
LIB.pop("fs_test_handsup"); LIB.pop("fs_test_noball")

print("== 3 soccer game pack ==")
pack = json.load(open(os.path.join(ROOT, "game_packs", "soccer.json")))
moves = {m["name"]: m for m in pack["moves"]}
want = ["stepover", "roulette", "elastico", "drag_back", "rainbow_flick", "fake_shot",
        "thigh_control", "chip_shot", "trivela", "bicycle_kick"]
check("the pack offers the new moves", all(w in moves for w in want), str([w for w in want if w not in moves]))
check("each new move's own clip is the field-sport clip", all(moves[w].get("own") and moves[w]["own"][0] in LIB for w in want if w in moves))
ok = True
for w in want:
    m = moves.get(w)
    if not m:
        continue
    for key in ("hit_start", "hit_end", "ball_contact"):
        if not (m["events"][key] == -1 or 0 <= m["events"][key] < m["frames"]):
            ok = False
    if any(not 0 <= f < m["frames"] for f in m["events"]["footsteps"]):
        ok = False
check("their events land inside the clip", ok)

print("== 4 bind conform ==")
# A 3-bone arm chain: shoulder -> elbow -> hand.  Source rest: arm out at 45 deg
# (A-pose).  Target bind: hanging straight down.
src = np.array([[0, 1.4, 0], [0.25, 1.15, 0], [0.5, 0.9, 0]], float)
tgt = np.array([[0, 1.4, 0], [0, 1.05, 0], [0, 0.7, 0]], float)
parents = [-1, 0, 1]
t = np.linspace(0, 1, 9)[:, None]
V = np.vstack([src[0] + t * (src[1] - src[0]), src[1] + t * (src[2] - src[1])])
N = np.tile([0.0, 0.0, 1.0], (len(V), 1))
J = np.array([[0]] * 9 + [[1]] * 9, np.uint16)
W = np.ones((18, 1), np.float32)
V2, N2, rep = conform_to_bind(V, N, J, W, src, tgt, parents, names=["upper", "fore", "hand"])
# After conform, the upper-arm vertices lie on the vertical line below the shoulder.
check("conformed arm hangs where the target bind arm is", np.allclose(V2[:9, 0], 0, atol=1e-6) and V2[8, 1] < V2[0, 1],
      str(V2[:9, :2].round(3).tolist()))
check("the report names the bones it turned", rep and rep[0].startswith("upper 45"), str(rep))
same, _, rep2 = conform_to_bind(V, N, J, W, src, src, parents)
check("an already-aligned skeleton is left exactly as it is", np.allclose(same, V) and not rep2)
R = minrot([1, 0, 0], [0, -1, 0])
check("minrot maps a onto b", np.allclose(R @ [1, 0, 0], [0, -1, 0]))

print("\nRESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
