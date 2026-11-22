#!/usr/bin/env python3
"""v11.40: motion categories, sub-type tags and the ml_training licence field."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from sforge import motiontags as MT  # noqa: E402
from sforge import library as L  # noqa: E402
from sforge import jointtrack as JT  # noqa: E402

fails = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


# 1. catch-alls are filed into real categories; the action is a tag
r = MT.retag(dict(name="st_lofted_19", category="Mocap", desc="lofted from match video", loop=False,
                  source="soccertrack-v2", licence=dict(spdx="CC-BY-4.0", author="SoccerTrack v2")))
check(r["category"] == "Kicking" and r["tags"]["action"] == "lofted", "Mocap lofted -> Kicking, action=lofted")
check(r["tags"]["source"] == "soccertrack" and r["tags"]["capture"] == "match_video", "source + capture tags")
check(r["import"]["category_was"] == "Mocap", "old category kept in import.category_was")
for name, want in [("free_kick_curl", "free_kick"), ("penalty_left", "penalty"), ("cross_right", "cross"),
                   ("clearance_hoof", "clearance"), ("header_jump", "header"), ("first_touch_chest", "first_touch"),
                   ("sc_win_ball_03", "tackle"), ("block", "block")]:
    check(MT.retag(dict(name=name, category="Imported", desc="block a pass"))["tags"].get("action") == want,
          "%s -> action %s" % (name, want))

# 2. locomotion: gait + direction from the root velocity, style from the name
r = MT.retag(dict(name="ss_sidestep_proud", category="Imported", loop=True, source="bvh:Proud_SR.bvh",
                  licence=dict(spdx="CC-BY-4.0", author="Ian Mason (100STYLE)"), **{"import": dict(root_velocity=[1.9, 0.2])}))
check(r["category"] == "Locomotion" and r["tags"]["gait"] == "jog" and r["tags"]["direction"] == "side",
      "sidestep loop -> Locomotion, gait jog, direction side")
check(r["tags"].get("style") == "proud" and r["tags"]["source"] == "100style", "style + 100style source")
check(MT.gait_of(1.0) == "walk" and MT.gait_of(6.5) == "sprint", "gait thresholds")
r = MT.retag(dict(name="backrun", category="Mocap", loop=True, **{"import": dict(root_velocity=[0.0, -2.5])}))
check(r["tags"]["direction"] == "back", "negative forward speed -> back")

# 3. a game's own categories are kept unless asked; already-canonical ones always kept
check(MT.retag(dict(name="st_pass_01", category="Kick"))["category"] == "Kick", "game category kept by default")
check(MT.retag(dict(name="st_pass_01", category="Kick"), refile=True)["category"] == "Kicking", "refile=True maps Kick")
check(MT.retag(dict(name="sc_receive_02", category="FirstTouch"), refile=True)["category"] == "Ball", "FirstTouch -> Ball")
check(MT.retag(dict(name="shoot_goal", category="Kicking"), refile=True)["category"] == "Kicking", "canonical kept")
r = MT.retag(dict(name="xyz_take_7", category="Mocap", loop=False))
check(r["category"] == "Mocap" and r["tags"].get("needs_category"), "untellable move flagged needs_category")

# 4. training rights
check(MT.training_allowed(dict(spdx="CC-BY-4.0")) == "yes", "CC-BY -> yes")
check(MT.training_allowed(dict(spdx="CC-BY-NC-4.0")) == "no", "CC-BY-NC -> no")
check(MT.training_allowed(dict(spdx="MIT")) == "yes", "MIT -> yes")
check(MT.training_allowed(dict(spdx="LicenseRef-Proprietary", author="Adobe Mixamo")) == "no", "Mixamo -> no")
check(MT.training_allowed(dict(spdx="LicenseRef-AndersonRohr-MocapPack05")) == "unknown", "silent EULA -> unknown")
check(MT.training_allowed(dict(spdx="LicenseRef-AndersonRohr", ml_training="yes")) == "yes", "explicit field wins")
check(MT.training_allowed("CC0-1.0") == "yes", "string licence (old records)")
ok, out = MT.training_set([dict(licence=dict(spdx="CC0-1.0")), dict(licence=dict(spdx="custom"))])
check(len(ok) == 1 and len(out) == 1 and "unknown" in out[0][1], "training_set splits and gives the reason")

# 5. the licence record has the field, validated
lic = L.blank_licence()
check(lic["ml_training"] == "unknown", "blank_licence has ml_training=unknown")
lic.update(spdx="CC0-1.0", author="me")
check(not L.validate_licence(lic), "complete licence validates")
lic["ml_training"] = "maybe"
check(any("ml_training" in p for p in L.validate_licence(lic)), "bad ml_training rejected")
old = dict(spdx="CC0-1.0", custom_text="", author="me", source_url="", redistribution="yes", attribution="")
check(not L.validate_licence(old), "older record without the field still validates")
check(all(p.get("ml_training") in L.ML_TRAINING for p in L.LICENCE_PRESETS.values()), "presets set ml_training")
check("ML training" in L.licence_text(old), "licence summary shows ML training")

# 6. imports are tagged at the source (jointtrack records)
rep = dict(duration=1.0, fps=25.0, frames=26, mean_bone_err_deg=1.0, heading_deg=0.0)
rec = JT.keys_record("vo_run_05", [(0.0, {}), (1.0, {})], rep, dict(spdx="LicenseRef-owner-footage"),
                     category="Mocap", loop=True, source="veo:own-footage", desc="run loop")
check(rec["category"] == "Locomotion" and rec["tags"]["source"] == "veo", "keys_record files Mocap + tags")
rec = JT.keys_record("st_pass_01", [(0.0, {}), (1.0, {})], rep, {}, category="Kick", source="soccertrack-v2")
check(rec["category"] == "Kick" and rec["tags"]["action"] == "pass", "keys_record keeps game category, tags action")

# 7. the retag tool: report, write, keep-category
tmp = tempfile.mkdtemp()
try:
    d = os.path.join(tmp, "cmu")
    os.makedirs(d)
    json.dump(dict(name="mocap_kick_b", category="Mocap", keys=[], licence=dict(spdx="custom", author="CMU")),
              open(os.path.join(d, "mocap_kick_b.json"), "w"))
    json.dump(dict(name="mocap_run", category="Locomotion", keys=[], loop=True, licence=dict(spdx="custom")),
              open(os.path.join(d, "mocap_run.json"), "w"))
    tool = os.path.join(HERE, "retag_motions.py")
    o = subprocess.run([sys.executable, tool, d], capture_output=True, text=True)
    check(o.returncode == 0 and "would change" in o.stdout, "tool dry run")
    check(json.load(open(os.path.join(d, "mocap_kick_b.json")))["category"] == "Mocap", "dry run writes nothing")
    o = subprocess.run([sys.executable, tool, d, "--write", "--ml-training", "cmu=yes"], capture_output=True, text=True)
    k = json.load(open(os.path.join(d, "mocap_kick_b.json")))
    check(k["category"] == "Kicking" and k["licence"]["ml_training"] == "yes" and k["tags"]["source"] == "cmu",
          "tool --write re-files, tags and sets ml_training per folder")
    json.dump(dict(name="st_pass_9", category="Kick", keys=[], licence=dict(spdx="CC-BY-4.0")),
              open(os.path.join(d, "st_pass_9.json"), "w"))
    subprocess.run([sys.executable, tool, d, "--write", "--keep-category"], capture_output=True, text=True)
    k = json.load(open(os.path.join(d, "st_pass_9.json")))
    check(k["category"] == "Kick" and k["tags"]["action"] == "pass" and k["licence"]["ml_training"] == "yes",
          "--keep-category only adds tags + ml_training")
finally:
    shutil.rmtree(tmp)

# 8. the shipped library has no catch-alls left and every move is tagged
lib = os.path.join(HERE, "..", "motion_library")
bad = []
for f in os.listdir(lib):
    if f.endswith(".json") and f not in ("index.json", "licence.json"):
        r = json.load(open(os.path.join(lib, f)))
        if "keys" in r and (r.get("category") not in MT.CATEGORIES or "tags" not in r):
            bad.append(f)
check(not bad, "motion_library: every move in a real category and tagged %s" % (bad or ""))

print("\n%d failed" % len(fails) if fails else "\nall motiontags checks passed")
sys.exit(1 if fails else 0)
