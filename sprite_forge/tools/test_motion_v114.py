#!/usr/bin/env python3
"""v11.4 motion library + character types. Synthetic only: no photos, no video, no people.

  python tools/test_motion_v114.py [OUT_DIR]

Proves:
  1. a recorded keys clip and an imported BVH / GLB / FBX land in the library and retarget onto another rig
  2. the same move on two character types differs in timing, stance, reach and weight
  3. a fighter profile and a sports profile both consume the library
  4. clean-up reduces foot slide on the shared skeleton
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image

OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_m114_")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="sfs_m114lib_")
R = []


def rec(sec, name, ok, detail=""):
    R.append(dict(section=sec, name=name, ok=bool(ok), detail=str(detail)))
    print("%-5s %-8s %-52s %s" % ("PASS" if ok else "FAIL", sec, name, detail))
    sys.stdout.flush()


def forge(*args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    e["SFS_MOTIONS"] = TMP
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(args),
                       capture_output=True, text=True, env=e, cwd=TMP)
    return p.returncode, p.stdout + p.stderr


# ---------------------------------------------------------------- library + syntax
from sforge.moves import split_spec
from sforge.motions import find_motion
from sforge.motionlib import (BUILTIN, as_motion, clean_keys, import_file, list_moves, load_move,
                              open_library, retarget_motion)
from sforge import chartypes

nm, mot, fr, fps, loop = split_spec("punch=lib:punch:6:12:once")
rec("syntax", "lib: motion is not split on the colon", nm == "punch" and mot == "lib:punch" and fr == "6" and fps == "12" and loop == "once", mot)
nm, mot, fr, fps, loop = split_spec("dash=sprint:8:14:loop")
rec("syntax", "old move spec still parses", nm == "dash" and mot == "sprint" and fr == "8" and loop == "loop", mot)
nm, mot, fr, fps, loop = split_spec("idle:8:8:loop")
rec("syntax", "name:frames:fps:loop still parses", nm == "idle" and mot == "" and fr == "8" and fps == "8", nm)

names = list_moves()
rec("library", "starter has generic moves", set(["punch", "kick", "walk", "tackle", "shoot", "drive", "wave"]) <= set(names),
    "%d moves" % len(names))
lic = json.load(open(os.path.join(BUILTIN, "licence.json"), encoding="utf-8"))
rec("library", "starter licence is CC0", lic.get("spdx") == "CC0-1.0" and lic.get("redistribution") == "yes", lic.get("spdx"))
punch = load_move("punch")
rec("library", "punch is not a bundled third-party clip", str(punch.get("source", "")).startswith("procedural:"), punch.get("source"))
total = sum(os.path.getsize(os.path.join(BUILTIN, f)) for f in os.listdir(BUILTIN))
rec("library", "starter is small text", total < 500_000, "%d bytes" % total)
plain = find_motion("punch")
libm = find_motion("lib:punch")
rec("library", "lib:punch is the library clip, punch stays procedural",
    plain is not None and libm is not None and getattr(plain, "library", None) is None and getattr(libm, "library", None),
    getattr(plain, "desc", "")[:40])

# ---------------------------------------------------------------- character types
def axes(motion, a, b):
    return chartypes.measure(chartypes.wrap(find_motion(motion), a)), chartypes.measure(chartypes.wrap(find_motion(motion), b))

heavy, quick = axes("punch", "heavy_brawler", "quick_striker")
rec("type", "fighter: heavy stance wider than quick", heavy["stance_m"] > quick["stance_m"] + 0.1,
    "%.3f vs %.3f" % (heavy["stance_m"], quick["stance_m"]))
rec("type", "fighter: heavy reach shorter than quick", heavy["reach_m"] < quick["reach_m"] - 0.08,
    "%.3f vs %.3f" % (heavy["reach_m"], quick["reach_m"]))
rec("type", "fighter: heavy timing peaks later", heavy["peak_t"] > quick["peak_t"] + 0.1,
    "%.3f vs %.3f" % (heavy["peak_t"], quick["peak_t"]))
rec("type", "fighter: heavy weighs more", heavy["weight"] > quick["weight"] + 30,
    "%.1f vs %.1f" % (heavy["weight"], quick["weight"]))
keeper, play = axes("tackle", "keeper", "playmaker")
rec("type", "sports: keeper stance wider than playmaker", keeper["stance_m"] > play["stance_m"] + 0.1,
    "%.3f vs %.3f" % (keeper["stance_m"], play["stance_m"]))
rec("type", "sports: keeper reach longer than playmaker", keeper["reach_m"] > play["reach_m"] + 0.04,
    "%.3f vs %.3f" % (keeper["reach_m"], play["reach_m"]))
rec("type", "sports: keeper timing peaks later", keeper["peak_t"] > play["peak_t"] + 0.05,
    "%.3f vs %.3f" % (keeper["peak_t"], play["peak_t"]))
rec("type", "sports: keeper weighs more", keeper["weight"] > play["weight"] + 3,
    "%.1f vs %.1f" % (keeper["weight"], play["weight"]))
raw = chartypes.measure(find_motion("punch"))
bal = chartypes.measure(chartypes.wrap(find_motion("punch"), "balanced"))
rec("type", "balanced matches the untyped clip",
    abs(raw["stance_m"] - bal["stance_m"]) < 1e-6 and abs(raw["peak_t"] - bal["peak_t"]) < 1e-6, "")

custom = os.path.join(TMP, "wide_custom.json")
json.dump({"name": "wide_custom", "label": "Wide custom", "timing": 1.0, "stance": 2.0, "reach": 1.0, "weight": 1.0,
           "notes": "added as data, no engine change"}, open(custom, "w"))
wide = chartypes.measure(chartypes.wrap(find_motion("punch"), custom))
rec("type", "a new JSON file is picked up with no code change", wide["stance_m"] > heavy["stance_m"] + 0.05,
    "%.3f vs heavy %.3f" % (wide["stance_m"], heavy["stance_m"]))

# procedural preset (not the library) still takes a type
proc = chartypes.measure(chartypes.wrap(find_motion("kick"), "small_agile"))
boss = chartypes.measure(chartypes.wrap(find_motion("kick"), "big_boss"))
rec("type", "procedural kick: big boss later and wider than small agile",
    boss["peak_t"] > proc["peak_t"] + 0.1 and boss["stance_m"] > proc["stance_m"] + 0.1,
    "peak %.2f/%.2f stance %.2f/%.2f" % (boss["peak_t"], proc["peak_t"], boss["stance_m"], proc["stance_m"]))

# ---------------------------------------------------------------- clean
keys = []
for i in range(12):
    t = i / 11.0
    s = math.sin(2 * math.pi * t)
    keys.append((t, {"leg_L": (22 * s, 6, 0), "leg_R": (-22 * s, 6, 0), "knee_L": 6, "knee_R": 6, "flat": 1.0}))
cleaned, crep = clean_keys(keys, loop=True)
foot = crep.get("foot") or {}
rec("clean", "foot slide drops on a skating cycle",
    foot.get("after_cm", 99) < foot.get("before_cm", 0) * 0.5 and foot.get("after_cm", 99) < 3,
    "%.2f -> %.2f cm" % (foot.get("before_cm", -1), foot.get("after_cm", -1)))
rec("clean", "weight shift is written into a loop", crep.get("weight_shift_m", 0) > 0.02, crep.get("weight_shift_m"))

pk = load_move("punch")["keys"]
ck, prep = clean_keys(pk, loop=False)

def _fwd(keys_, ch="arm_R"):
    out = []
    for t, p in keys_:
        v = p.get(ch, (0, 0, 0))
        out.append((t, float(v[0] if isinstance(v, (tuple, list)) else v)))
    return out

before_f = _fwd(pk)
after_f = _fwd(ck)
early_b = min(v for t, v in before_f if t <= 0.22)
early_a = min(v for t, v in after_f if t <= 0.22)
rec("clean", "anticipation pulls the strike back", early_a < early_b - 4, "%.1f -> %.1f deg" % (early_b, early_a))
rec("clean", "follow-through goes past the old peak", max(v for _, v in after_f) > max(v for _, v in before_f) + 3,
    "peak %.1f -> %.1f" % (max(v for _, v in before_f), max(v for _, v in after_f)))
rec("clean", "GLB re-solve is not claimed", crep.get("glb_resolved") is False and "not re-solved" in crep.get("note", ""), "")

# ---------------------------------------------------------------- record + import + retarget
from sforge import mocap, rigrec as RR
from sforge.samplerigs import build as build_rig

src_motion = find_motion("punch")
synth = [(t, dict(p)) for t, p in src_motion.keys]
kj = os.path.join(TMP, "synth_punch.json")
mocap.save_keys(kj, "synth_punch", synth, False, {"note": "synthetic keys, not a person"})
rc, log = forge("motion", "record", "--keys", kj, "--name", "rec_punch", "--spdx", "CC0-1.0", "--author", "test",
                "--redistribution", "yes", "--library", TMP)
got = open_library(TMP).has("rec_punch")
rec("record", "mocap keys JSON lands in the library", rc == 0 and got, log.strip().splitlines()[-1] if log.strip() else rc)

lanky = build_rig("sample_lanky")
tgt, cl, rp = retarget_motion("rec_punch", lanky, path=TMP, plant=True)
err = rp.get("mean_dir_err_deg")
rec("retarget", "recorded clip retargets onto another rig",
    cl is not None and cl.frames >= 2 and (rp.get("common_bones") or 0) >= 12 and err is not None and err < 5,
    "err %s deg, %s bones, plant %s" % (err, rp.get("common_bones"), (rp.get("plant") or {}).get("after_cm")))

man, _, clip = __import__("sforge.motionlib", fromlist=["bake_on_mannequin"]).bake_on_mannequin(as_motion("kick"), frames=6)
glb = os.path.join(TMP, "kick.glb")
RR.write_glb(man, glb, ["kick"])
fbx = os.path.join(TMP, "kick.fbx")
from sforge import fbx as FBX
FBX.write_fbx_from_glb(glb, fbx)
glib = os.path.join(TMP, "imp")
os.makedirs(glib, exist_ok=True)
cc0 = dict(spdx="CC0-1.0", author="test", redistribution="yes", attribution="", source_url="", custom_text="", notes="synthetic")
gret, _, _ = import_file(glb, name="kick_glb", library=glib, licence=cc0)
fret, _, _ = import_file(fbx, name="kick_fbx", clip="kick", library=glib, licence=cc0)
rec("import", "GLB clip projects onto the shared skeleton",
    gret["import"]["projection_mean_m"] < 0.08 and gret["import"]["retarget_mean_dir_err_deg"] < 1 and gret["import"]["common_bones"] >= 12,
    "projection mean %.3f m, dir err %s deg" % (gret["import"]["projection_mean_m"], gret["import"]["retarget_mean_dir_err_deg"]))
rec("import", "FBX clip projects onto the shared skeleton",
    fret["import"]["projection_mean_m"] < 0.06 and fret["import"]["reader"] == "fbx",
    "mean %.3f m" % fret["import"]["projection_mean_m"])

# BVH with Unity-style names so the bone map is doing real work. Motion is synthetic.
def _bvh(path):
    joints = [
        ("Hips", None, (0, 0.95, 0), True),
        ("Spine", "Hips", (0, 0.20, 0), False),
        ("Chest", "Spine", (0, 0.20, 0), False),
        ("RightUpperArm", "Chest", (-0.20, 0.15, 0), False),
        ("RightLowerArm", "RightUpperArm", (0, -0.28, 0), False),
        ("LeftUpperArm", "Chest", (0.20, 0.15, 0), False),
        ("LeftLowerArm", "LeftUpperArm", (0, -0.28, 0), False),
        ("RightUpperLeg", "Hips", (-0.10, -0.10, 0), False),
        ("RightLowerLeg", "RightUpperLeg", (0, -0.42, 0), False),
        ("LeftUpperLeg", "Hips", (0.10, -0.10, 0), False),
        ("LeftLowerLeg", "LeftUpperLeg", (0, -0.42, 0), False),
    ]
    lines = ["HIERARCHY"]

    def emit(name, depth):
        j = next(x for x in joints if x[0] == name)
        _, parent, off, root = j
        pad = "  " * depth
        lines.append("%s%s %s" % (pad, "ROOT" if root else "JOINT", name))
        lines.append("%s{" % pad)
        lines.append("%s  OFFSET %.4f %.4f %.4f" % (pad, off[0], off[1], off[2]))
        ch = "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation" if root else "3 Zrotation Xrotation Yrotation"
        lines.append("%s  CHANNELS %s" % (pad, ch))
        kids = [c[0] for c in joints if c[1] == name]
        if not kids:
            lines.append("%s  End Site" % pad)
            lines.append("%s  {" % pad)
            lines.append("%s    OFFSET 0 %.4f 0" % (pad, -0.25))
            lines.append("%s  }" % pad)
        for k in kids:
            emit(k, depth + 1)
        lines.append("%s}" % pad)
    emit("Hips", 0)
    nch = 6 + 3 * (len(joints) - 1)
    lines += ["MOTION", "Frames: 3", "Frame Time: 0.1"]
    # channel order is the joint order above. RightUpperArm is index 3 -> rotation channels start at 6+3+3=12
    for ax in (0.0, -40.0, -80.0):
        row = [0.0] * nch
        row[1] = 0.95
        row[12] = ax          # RightUpperArm Xrotation (Z, X, Y) so index 12 is Z, 13 is X
        row[13] = ax
        lines.append(" ".join("%.4f" % v for v in row))
    open(path, "w").write("\n".join(lines) + "\n")

bvh = os.path.join(TMP, "arm.bvh")
_bvh(bvh)
bret, bout, _ = import_file(bvh, name="arm_swing", library=glib, licence=cc0)
a0 = bret["keys"][0][1]
a1 = bret["keys"][-1][1]
changed = json.dumps(a0, sort_keys=True) != json.dumps(a1, sort_keys=True)
rec("import", "BVH clip lands in the library and is not a still pose",
    changed and len(bret["keys"]) == 3 and bret["import"]["reader"] == "bvh",
    "bones %s" % bret["import"].get("common_bones"))
tgt2, cl2, rp2 = retarget_motion("arm_swing", lanky, path=glib, plant=False)
rec("retarget", "imported BVH retargets onto the lanky rig",
    cl2.frames >= 2 and (rp2.get("common_bones") or 0) >= 8 and rp2.get("mean_dir_err_deg") is not None,
    "%d frames, bones %s, err %s deg" % (cl2.frames, rp2.get("common_bones"), rp2.get("mean_dir_err_deg")))

rc, log = forge("motion", "import", glb, "--name", "kick_cli", "--spdx", "CC0-1.0", "--author", "test",
                "--redistribution", "yes", "--library", glib)
rec("cli", "motion import from the command line", rc == 0 and open_library(glib).has("kick_cli"), log.strip().splitlines()[-1] if log.strip() else "")
rc, log = forge("motion", "types")
rec("cli", "motion types lists the shipped types", rc == 0 and "heavy_brawler" in log and "keeper" in log, "")
rc, log = forge("help", "motion")
rec("cli", "help motion documents commands and limits", rc == 0 and "forge.py motion import" in log and "not re-solved" in log, "")
rc, log = forge("profile", "validate", "motion_demo")
rec("cli", "motion_demo profile validates", rc == 0, log.strip().splitlines()[-1] if log.strip() else "")

# ---------------------------------------------------------------- both game profiles build from the library
def build(profile, move, mot, ctype, name):
    rc, log = forge("build", "--mannequin", "--profile", profile,
                    "--moves", "%s=lib:%s:4:12:once" % (move, mot),
                    "--character-type", ctype, "--frame", "96x96", "--no-glb", "--no-fbx", "--no-qa",
                    "--quality", "draft", "--no-cache", "--name", name, "--out", OUT)
    cfg = os.path.join(OUT, name, "sprites.cfg")
    png = os.path.join(OUT, name, "moves", "%s_02.png" % move)
    return rc, log, cfg, png

rh, logh, cfgh, pngh = build("fighter14", "punch", "punch", "heavy_brawler", "fighter_heavy")
rq, logq, cfgq, pngq = build("fighter14", "punch", "punch", "quick_striker", "fighter_quick")
rk, logk, cfgk, pngk = build("gaelic36", "tackle", "tackle", "keeper", "sport_keeper")
rp_, logp, cfgp, pngp = build("gaelic36", "tackle", "tackle", "playmaker", "sport_play")
rec("profile", "fighter profile builds a library punch", rh == 0 and os.path.isfile(pngh) and "character type heavy_brawler" in logh, "")
rec("profile", "sports profile builds a library tackle", rk == 0 and os.path.isfile(pngk) and "character type keeper" in logk, "")

def fps_of(cfg, move):
    for line in open(cfg):
        if line.startswith("move %s " % move):
            return int(line.split()[6])
    return None

fh, fq = fps_of(cfgh, "punch"), fps_of(cfgq, "punch")
rec("profile", "fighter timing changes playback fps", fh is not None and fq is not None and fh < fq,
    "heavy %s fps, quick %s fps" % (fh, fq))
kh, kp = fps_of(cfgk, "tackle"), fps_of(cfgp, "tackle")
rec("profile", "sports timing changes playback fps", kh is not None and kp is not None and kh < kp,
    "keeper %s fps, playmaker %s fps" % (kh, kp))
ah = np.asarray(Image.open(pngh).convert("RGBA"))
aq = np.asarray(Image.open(pngq).convert("RGBA"))
rec("profile", "same fighter move, two types, different pixels", int(np.abs(ah.astype(int) - aq.astype(int)).max()) > 20, "")
ak = np.asarray(Image.open(pngk).convert("RGBA"))
ap = np.asarray(Image.open(pngp).convert("RGBA"))
rec("profile", "same sports move, two types, different pixels", int(np.abs(ak.astype(int) - ap.astype(int)).max()) > 20, "")

npass = sum(r["ok"] for r in R)
md = ["# Sprite Forge v11.4 motion library tests", "",
      "%d / %d passed  (%s)" % (npass, len(R), sys.platform), "",
      "| section | test | result | detail |", "|---|---|---|---|"]
md += ["| %s | %s | %s | %s |" % (r["section"], r["name"], "PASS" if r["ok"] else "**FAIL**",
                                  str(r["detail"]).replace("|", "/").replace("\n", " ")[:180]) for r in R]
open(os.path.join(OUT, "RESULTS_v114.md"), "w").write("\n".join(md) + "\n")
json.dump(R, open(os.path.join(OUT, "results_v114.json"), "w"), indent=1)
print("\n%d / %d passed -> %s" % (npass, len(R), OUT))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if npass == len(R) else 1)
