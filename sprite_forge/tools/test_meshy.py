#!/usr/bin/env python3
"""v11.41: Meshy integration - client, Text to Motion -> library -> pack, the Meshy skeleton, the shipped clips.

    python tools/test_meshy.py

No network and no credits: a fake Meshy answers the API and serves a BVH made on Meshy's own 77-joint skeleton
(Spine1/Spine2/Chest/Neck1/Neck2, {S}Leg = thigh, {S}Shin = shin). The shipped motion_library_owned/ clips are
checked too, when they are there.
"""
from __future__ import annotations
import glob
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from sforge import bonemap as BM, meshy as MZ, meshy_cli as MC, motionlib  # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok: passed += 1; print("  PASS  " + name)
    else: failed += 1; print("  FAIL  " + name + ("  " + str(detail) if detail else ""))


MESHY_BONES = ("Root Hips Spine1 Spine2 Chest Neck1 Neck2 Head HeadEnd Jaw LeftEye RightEye LeftShoulder LeftArm "
               "LeftForeArm LeftHand LeftHandThumb1 LeftHandIndex1 RightShoulder RightArm RightForeArm RightHand "
               "RightHandThumb1 RightHandIndex1 LeftLeg LeftShin LeftFoot LeftToeBase LeftToeEnd RightLeg RightShin "
               "RightFoot RightToeBase RightToeEnd").split()

# -- 1-3: the Meshy skeleton ------------------------------------------------------------------------------------
conv, m, sc = BM.detect_convention(MESHY_BONES)
check("Meshy BVH skeleton detected as meshy", conv == "meshy", "%s %s" % (conv, sc))
check("{S}Leg is the thigh and {S}Shin the shin (Mixamo would read {S}Leg as the shin)",
      m.get("thigh_L") == "LeftLeg" and m.get("shin_L") == "LeftShin" and m.get("thigh_R") == "RightLeg", m)
MIXAMO = ["mixamorig:" + b for b in "Hips Spine Spine1 Spine2 Neck Head LeftShoulder LeftArm LeftForeArm LeftHand "
          "RightShoulder RightArm RightForeArm RightHand LeftUpLeg LeftLeg LeftFoot LeftToeBase RightUpLeg RightLeg "
          "RightFoot RightToeBase".split()]
mc, mm, _ = BM.detect_convention(MIXAMO)
check("a Mixamo rig (Meshy's rigging output with skeleton_template=mixamo) is still Mixamo", mc == "mixamo" and mm.get("shin_L") == "mixamorig:LeftLeg")


# -- a BVH on the Meshy skeleton: a figure standing, then swinging the right leg forward ---------------------------
def meshy_bvh(frames=60):
    import math
    off = {"Root": (0, 0, 0), "Hips": (0, 100, 0), "Spine1": (0, 5, 0), "Spine2": (0, 7, 0), "Chest": (0, 7.5, 0),
           "Neck1": (0, 26, 0), "Neck2": (0, 7.7, 0), "Head": (0, 6, 2), "HeadEnd": (0, 16, 0),
           "LeftShoulder": (2, 23, 5), "LeftArm": (15, 0, -5), "LeftForeArm": (28, 0, 0), "LeftHand": (27, 0, 0),
           "RightShoulder": (-2, 23, 5), "RightArm": (-15, 0, -5), "RightForeArm": (-28, 0, 0), "RightHand": (-27, 0, 0),
           "LeftLeg": (9, -5, 0), "LeftShin": (0, -45, 0), "LeftFoot": (0, -43, 0), "LeftToeBase": (0, -6, 12),
           "RightLeg": (-9, -5, 0), "RightShin": (0, -45, 0), "RightFoot": (0, -43, 0), "RightToeBase": (0, -6, 12)}
    tree = {"Root": ["Hips"], "Hips": ["Spine1", "LeftLeg", "RightLeg"], "Spine1": ["Spine2"], "Spine2": ["Chest"],
            "Chest": ["Neck1", "LeftShoulder", "RightShoulder"], "Neck1": ["Neck2"], "Neck2": ["Head"], "Head": ["HeadEnd"],
            "LeftShoulder": ["LeftArm"], "LeftArm": ["LeftForeArm"], "LeftForeArm": ["LeftHand"],
            "RightShoulder": ["RightArm"], "RightArm": ["RightForeArm"], "RightForeArm": ["RightHand"],
            "LeftLeg": ["LeftShin"], "LeftShin": ["LeftFoot"], "LeftFoot": ["LeftToeBase"],
            "RightLeg": ["RightShin"], "RightShin": ["RightFoot"], "RightFoot": ["RightToeBase"]}
    order, lines = [], ["HIERARCHY"]

    def emit(j, d):
        order.append(j)
        ind = "  " * d
        lines.append("%s%s %s" % (ind, "ROOT" if j == "Root" else "JOINT", j))
        lines.append(ind + "{")
        lines.append(ind + "  OFFSET %g %g %g" % off[j])
        six = j in ("Root", "Hips")
        lines.append(ind + "  CHANNELS %s" % ("6 Xposition Yposition Zposition Zrotation Yrotation Xrotation" if six
                                              else "3 Zrotation Yrotation Xrotation"))
        for c in tree.get(j, []):
            emit(c, d + 1)
        if not tree.get(j):
            lines.append(ind + "  End Site")
            lines.append(ind + "  {")
            lines.append(ind + "    OFFSET 0 -5 0")
            lines.append(ind + "  }")
        lines.append(ind + "}")
    emit("Root", 0)
    lines += ["MOTION", "Frames: %d" % frames, "Frame Time: 0.0333333"]
    for f in range(frames):
        ph = f / (frames - 1)
        swing = -70 * math.sin(math.pi * min(1, max(0, (ph - 0.3) / 0.4)))   # right thigh forward (rotation about X)
        vals = []
        for j in order:
            if j in ("Root", "Hips"):
                vals += [0, 0, 0, 0, 0, 0]
            elif j == "RightLeg":
                vals += [0, 0, swing]
            elif j == "LeftArm":
                vals += [-75, 0, 0]
            elif j == "RightArm":
                vals += [75, 0, 0]
            else:
                vals += [0, 0, 0]
        lines.append(" ".join("%.4f" % v for v in vals))
    return "\n".join(lines) + "\n"


# -- a fake Meshy ------------------------------------------------------------------------------------------------
class FakeMeshy:
    def __init__(self, balance=500):
        self.calls, self.bal, self.n = [], balance, 0

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, json.loads(body) if body else None, headers.get("Authorization")))
        if url.endswith("/openapi/v1/balance"):
            return 200, json.dumps({"balance": self.bal}).encode()
        if method == "POST" and url.endswith("/text-to-motion"):
            self.n += 1
            self.bal -= 3
            return 200, json.dumps({"result": "task-%d" % self.n}).encode()
        if method == "GET" and "/text-to-motion/task-" in url:
            return 200, json.dumps({"id": url.rsplit("/", 1)[1], "status": "SUCCEEDED", "progress": 100, "consumed_credits": 3,
                                    "result": {"motion_url": "https://assets.example/m.bvh", "motion_format": "bvh"}}).encode()
        if url == "https://assets.example/m.bvh":
            return 200, meshy_bvh().encode()
        return 404, b'{"message":"not found"}'


fake = FakeMeshy()
cl = MZ.Client(key="msy_test", transport=fake, sleep=lambda s: None)

SMPL = ("Pelvis L_Hip R_Hip Spine1 L_Knee R_Knee Spine2 L_Ankle R_Ankle Spine3 L_Foot R_Foot Neck L_Collar R_Collar "
        "Head L_Shoulder R_Shoulder L_Elbow R_Elbow L_Wrist R_Wrist").split()
sc_, sm_, _ = BM.detect_convention(SMPL)
check("Meshy prime's SMPL-H skeleton: L_Hip is the thigh, L_Knee the shin, L_Collar the shoulder",
      sc_ == "smpl" and sm_.get("thigh_L") == "L_Hip" and sm_.get("shin_L") == "L_Knee" and sm_.get("foot_L") == "L_Ankle"
      and sm_.get("upperarm_L") == "L_Shoulder" and sm_.get("shoulder_L") == "L_Collar", (sc_, sm_))
rec = json.load(open(os.path.join(motionlib.OWNED, "mz_soccer_long_throw.json"))) if os.path.isfile(
    os.path.join(motionlib.OWNED, "mz_soccer_long_throw.json")) else None
if rec:
    ev = MC.clip_events(rec, "Set piece", "long_throw")
    check("clip_events: an overhead throw releases with the hands above the head, not on the lift", 0.35 < ev["ball_contact"] < 0.65, ev)

# -- 4-5: client ---------------------------------------------------------------------------------------------------
check("balance is read with the bearer key", cl.balance()["balance"] == 500 and fake.calls[-1][3] == "Bearer msy_test")
errs = []
for bad in ((5, "x" * 401), (1.5, "ok"), (10.5, "ok"), (2.25, "ok")):
    try:
        cl.text_to_motion(bad[1], bad[0]); errs.append(False)
    except MZ.MeshyError:
        errs.append(True)
check("bad durations and over-long prompts are refused before any credit is spent",
      all(errs) and not any(c[0] == "POST" for c in fake.calls), errs)

# -- 6-10: motion -> owned library -> pack -------------------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="meshy_test_")
try:
    pdir, gdir, out = os.path.join(tmp, "prompts"), os.path.join(tmp, "packs"), os.path.join(tmp, "owned")
    os.makedirs(pdir); os.makedirs(gdir)
    json.dump({"pack": "testpack", "mode": "swift", "clip_prefix": "mz_test_", "moves": {
        "shoot_point": {"duration": 2.0, "loop": False, "prompt": "a player kicks the ball high over the bar"},
        "hand_pass": {"duration": 2.0, "loop": False, "prompt": "a player punches the ball off the open palm"}}},
        open(os.path.join(pdir, "testpack.json"), "w"))
    json.dump({"name": "testpack", "moves": [{"name": "shoot_point", "library": "kick", "prefer": ["old_kick"]},
                                             {"name": "hand_pass", "library": "pass"}, {"name": "idle", "library": "idle"}]},
              open(os.path.join(gdir, "testpack.json"), "w"))
    base = ["motion", "--pack", "testpack", "--prompts", pdir, "--packs-dir", gdir, "--out", out]
    logs = []
    MC.main(base + ["--dry-run"], client=MZ.Client(key="x", transport=fake, sleep=lambda s: None))
    check("--dry-run spends nothing", not any(c[0] == "POST" for c in fake.calls))
    try:
        MC.main(base + ["--max-credits", "5"], client=cl); over = False
    except SystemExit:
        over = True
    check("--max-credits stops a run that would cost more (2 moves x 3 > 5)", over and not any(c[0] == "POST" for c in fake.calls))
    MC.main(base, client=cl)
    recs = sorted(glob.glob(os.path.join(out, "mz_test_*.json")))
    src = sorted(glob.glob(os.path.join(out, "src", "meshy", "testpack", "*.bvh")))
    check("each move is generated, its BVH kept and imported as mz_test_<move>", len(recs) == 2 and len(src) == 2,
          (recs, src))
    rec = json.load(open(os.path.join(out, "mz_test_shoot_point.json")))
    lic = rec.get("licence", {})
    check("clips carry the owned-Meshy licence (redistributable, not CC0) and the prompt",
          lic.get("spdx") == "LicenseRef-Owned-Meshy" and lic.get("redistribution") == "yes" and "over the bar" in rec["meshy"]["prompt"], lic)
    from sforge import rig
    import numpy as np
    w0 = rig.evaluate(rec["keys"][0][1]).world
    knees = [w0["shin_L"][1, 3], w0["shin_R"][1, 3]]
    hips_y = w0["hips"][1, 3]
    check("imported legs are the right way up: knees half-way between hips and feet",
          all(0.3 * hips_y < k < 0.75 * hips_y for k in knees), (hips_y, knees))
    pk = json.load(open(os.path.join(gdir, "testpack.json")))
    pref = {mv["name"]: mv.get("prefer") for mv in pk["moves"]}
    check("the pack prefers the new clips after its existing (human-derived) preferences",
          pref["shoot_point"] == ["old_kick", "mz_test_shoot_point"] and pref["hand_pass"] == ["mz_test_hand_pass"]
          and pref["idle"] is None, pref)
    n_posts = sum(c[0] == "POST" for c in fake.calls)
    MC.main(base, client=cl)
    check("a second run skips moves that already have a clip (no credits)", sum(c[0] == "POST" for c in fake.calls) == n_posts)
    MC.main(["import", "--pack", "testpack", "--prompts", pdir, "--packs-dir", gdir, "--out", out])
    check("meshy import re-imports from the saved BVH without the API", os.path.isfile(os.path.join(out, "mz_test_hand_pass.json"))
          and sum(c[0] == "POST" for c in fake.calls) == n_posts)
    spec = json.load(open(os.path.join(pdir, "testpack.json")))
    spec["moves"]["idle"] = {"reuse": "mz_test_hand_pass"}
    spec["moves"]["walk"] = {"reuse": "mz_missing_clip"}
    json.dump(spec, open(os.path.join(pdir, "testpack.json"), "w"))
    n_posts = sum(c[0] == "POST" for c in fake.calls)
    MC.main(base, client=cl)
    pref = {mv["name"]: mv.get("prefer") for mv in json.load(open(os.path.join(gdir, "testpack.json")))["moves"]}
    check("a {\"reuse\": CLIP} move is wired with no credits; a missing reuse clip is left out",
          pref["idle"] == ["mz_test_hand_pass"] and sum(c[0] == "POST" for c in fake.calls) == n_posts, pref)
    # -- a full catalogue: base pack + catalogue, also_packs wiring, coverage --------------------------------------
    json.dump({"pack": "testpack_full", "base": "testpack", "also_packs": ["testpack"], "mode": "swift",
               "clip_prefix": "mz_test_", "moves": {
                   "hand_pass": {"category": "Passing", "duration": 2.0, "loop": False, "library": "pass", "prompt": "x"},
                   "rabona": {"category": "Shooting", "duration": 2.5, "loop": False, "library": "kick",
                              "prompt": "a player strikes the ball with the right leg wrapped behind the left"},
                   "jockey": {"category": "Locomotion", "duration": 3.0, "loop": True, "library": "walk", "prompt": "a player shuffles"}}},
              open(os.path.join(pdir, "testpack_full.json"), "w"))
    MC.main(["pack", "--pack", "testpack_full", "--prompts", pdir, "--packs-dir", gdir])
    full = json.load(open(os.path.join(gdir, "testpack_full.json")))
    names = [mv["name"] for mv in full["moves"]]
    check("meshy pack: the base pack's moves first, then the catalogue's new ones by category (Locomotion before Shooting)",
          names[:3] == ["shoot_point", "hand_pass", "idle"] and names[3:] == ["jockey", "rabona"]
          and full["moves"][3]["loop"] and full["moves"][4]["events"]["ball_contact"] == 5, names)
    n_posts = sum(c[0] == "POST" for c in fake.calls)
    MC.main(["motion", "--pack", "testpack_full", "--prompts", pdir, "--packs-dir", gdir, "--out", out], client=cl)
    full = {mv["name"]: mv.get("prefer") for mv in json.load(open(os.path.join(gdir, "testpack_full.json")))["moves"]}
    core = {mv["name"]: mv.get("prefer") for mv in json.load(open(os.path.join(gdir, "testpack.json")))["moves"]}
    check("a catalogue generates only what is missing and wires the full pack and its also_packs",
          sum(c[0] == "POST" for c in fake.calls) == n_posts + 2 and full["rabona"] == ["mz_test_rabona"]
          and full["jockey"] == ["mz_test_jockey"] and "mz_test_hand_pass" in full["hand_pass"]
          and core.get("rabona") is None, (full, core))
    cov = MC.coverage(json.load(open(os.path.join(pdir, "testpack_full.json"))), gdir, out)
    check("meshy catalogue counts, per category, the moves with a Meshy clip",
          cov["Shooting"] == [1, 1, []] and cov["Locomotion"] == [1, 1, []] and cov["Game"][0] == 3, cov)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# -- 14-16: the shipped clips ----------------------------------------------------------------------------------------
owned = sorted(glob.glob(os.path.join(motionlib.OWNED, "mz_*.json")))
lib = motionlib.open_library(tempfile.mkdtemp(prefix="meshy_lib_"))
check("motion_library_owned/ is searched after your library and before the CC0 starter",
      not os.path.isdir(motionlib.OWNED) or lib.dirs.index(os.path.abspath(motionlib.OWNED)) == len(lib.dirs) - 2, lib.dirs)
starter_lic = json.load(open(os.path.join(motionlib.BUILTIN, "licence.json")))
check("the starter stays CC0 with no Meshy clips in it", starter_lic.get("spdx") == "CC0-1.0"
      and not glob.glob(os.path.join(motionlib.BUILTIN, "mz_*.json")))
if owned:
    import check_motion as CM
    gp = json.load(open(os.path.join(HERE, "game_packs", "gaelic.json")))
    names = {os.path.splitext(os.path.basename(p))[0] for p in owned}
    missing = [(pk, c) for pk in ("gaelic", "aussie_rules", "hurling", "rugby")
               for mv in json.load(open(os.path.join(HERE, "game_packs", pk + ".json")))["moves"]
               for c in (mv.get("prefer") or []) if c.startswith("mz_") and c not in names]
    bad = []
    for p in owned:
        r = json.load(open(p))
        res = [x for x in CM.check_clip(r, r.get("meshy", {}).get("move") or r["name"]) if x[1] is False]
        if res or r.get("licence", {}).get("spdx") != "LicenseRef-Owned-Meshy":
            bad.append((r["name"], res))
    check("every shipped Meshy clip passes check_motion and is licensed (%d clips)" % len(owned), not bad, bad)
    check("every mz_ clip a pack prefers is shipped", not missing, missing)

print("RESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
