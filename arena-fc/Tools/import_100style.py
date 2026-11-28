#!/usr/bin/env python3
"""Import locomotion variety from the 100STYLE dataset (Ian Mason, CC BY 4.0) through Sprite Forge.

100STYLE is about 4 million frames of 60 fps studio motion capture: 100 locomotion styles, each in
forward / backward / sidestep walks and runs, idles and transitions
(https://www.ianxmason.com/100style/, zenodo.org/records/8127870).  Most styles are novelty walks;
this takes the ones a footballer could plausibly move like, in the gaits football needs:

  * forward runs and walks          -> gait loops (the bulk of on-pitch movement)
  * backward runs / walks           -> backpedalling (defenders holding a line)
  * sidestep runs / walks           -> jockeying and shuffling across
  * Neutral / Rushed / BigSteps / Proud / Heavyset for build and urgency variety,
    BentKnees / Crouched for a defender's low stance (sidesteps and backpedals only)

Each take goes through Sprite Forge's importer (motionlib.import_file: BVH -> retarget onto the
shared skeleton -> the cleanest loop inside the dataset's own Frame_Cuts span), then the loop's
speed and direction are measured from the hips' travel in the body's own frame, so a backpedal
is filed as moving backwards and a sidestep sideways.  Writes Data/mocap/100style/ (ss_*) and the
clip-manifest rows; Tools/soccer_motions.py bakes them into the player GLB.

    python3 Tools/import_100style.py --root /path/to/100STYLE   [--only Neutral ...]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)
OUT = os.path.join(ARENA, "Data", "mocap", "100style")
MANIFEST = os.path.join(ARENA, "Data", "clips", "clip_manifest.json")
PREFIX = "ss_"
LICENCE = dict(spdx="CC-BY-4.0", custom_text="Creative Commons Attribution 4.0 International",
               author="Ian Mason, Sebastian Starke, Taku Komura (100STYLE)",
               source_url="https://www.ianxmason.com/100style/", redistribution="yes", ml_training="yes",  # v11.40: CC BY 4.0
               attribution="The 100STYLE Dataset - Ian Mason",
               notes="Retargeted onto the Arena FC skeleton; loops cut from the dataset's Frame_Cuts spans.")

STYLES = {   # style -> gaits taken
    "Neutral": ("FR", "FW", "BR", "BW", "SR", "SW"),
    "Rushed": ("FR", "FW", "BR", "SR"),
    "BigSteps": ("FR", "FW", "BR", "SR"),
    "Proud": ("FR", "FW", "BR"),
    "Heavyset": ("FR", "FW", "BR"),
    "BentKnees": ("SR", "SW", "BR", "BW"),
    "Crouched": ("SR", "SW", "BW"),
}
GAIT_NAME = {"FR": "run", "FW": "walk", "BR": "backrun", "BW": "backwalk", "SR": "siderun", "SW": "sidewalk"}


def bvh_root(path):
    """-> (fps, (N, 3) root positions in metres, (N,) yaw in degrees) from a BVH whose root has
    Xposition Yposition Zposition Yrotation ... channels (100STYLE's layout)."""
    with open(path) as f:
        lines = f.read().splitlines()
    i = lines.index("MOTION")
    ft = float(lines[i + 2].split(":")[1])
    rows = np.array([[float(v) for v in ln.split()[:4]] for ln in lines[i + 3:] if ln.strip()])
    return 1.0 / ft, rows[:, :3] / 100.0, rows[:, 3]


def local_velocity(path, t0, t1):
    """mean root velocity over [t0, t1] s in the body frame: (sideways x, forward z) m/s.  100STYLE actors
    move in tight curves, so each frame's step is turned into that frame's body frame and the steps are
    averaged (a start-to-end displacement would cut the corner and read slow)."""
    fps, P, yaw = bvh_root(path)
    a, b = int(t0 * fps), min(len(P) - 1, int(t1 * fps))
    if b <= a + 1:
        return 0.0, 0.0
    d = np.diff(P[a:b + 1], axis=0)
    yw = np.radians(yaw[a:b])
    side = d[:, 0] * np.cos(yw) - d[:, 2] * np.sin(yw)       # body faces +Z at yaw 0; +x = its left/right axis
    fwd = d[:, 0] * np.sin(yw) + d[:, 2] * np.cos(yw)
    return float(side.mean() * fps), float(fwd.mean() * fps)


def best_window(path, s0, s1, gait, win=2.0):
    """the dataset's actors move in curves inside a small capture area (and sidestep back and forth):
    the most usable `win` seconds of the take - straightest heading for forward / backward gaits, the
    steadiest one-way travel for sidesteps."""
    fps, P, yaw = bvh_root(path)
    a0, a1, n = int(s0 * fps), int(s1 * fps), int(win * fps)
    yw = np.unwrap(np.radians(yaw))
    d = np.diff(P, axis=0); y = np.radians(yaw[:-1])
    side = (d[:, 0] * np.cos(y) - d[:, 2] * np.sin(y)) * fps
    fwd = (d[:, 0] * np.sin(y) + d[:, 2] * np.cos(y)) * fps
    best, arg = None, (s0, min(s1, s0 + win))
    for a in range(a0, max(a0 + 1, a1 - n), int(.25 * fps)):
        b = a + n
        turn = abs(math.degrees(yw[b] - yw[a]))
        if gait.startswith("S"):
            score = -abs(side[a:b].mean()) + .01 * turn
        else:
            score = turn / 30.0 - abs(fwd[a:b].mean())
        if best is None or score < best:
            best, arg = score, (a / fps, b / fps)
    return arg


def straighten(rec):
    """take the steady heading drift out of a loop (the actor was walking a curve): the hips' yaw
    ramps back so the loop ends facing where it started, centred on straight ahead."""
    K = rec["keys"]
    yaw = np.unwrap(np.radians([float(k[1]["hips"][1]) for k in K]))
    t = np.array([float(k[0]) for k in K])
    ramp = yaw[0] + (yaw[-1] - yaw[0]) * t
    new = yaw - ramp
    new -= new.mean()
    for k, y in zip(K, new):
        h = list(k[1]["hips"]); h[1] = float(np.degrees(y)); k[1]["hips"] = h
    return float(np.degrees(yaw[-1] - yaw[0]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="the unzipped 100STYLE folder (style folders + Frame_Cuts.csv)")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    from sforge import motionlib as ML
    sys.path.insert(0, os.path.join(SF, "tools"))
    import check_motion as CM
    cuts = {r["STYLE_NAME"]: r for r in csv.DictReader(open(os.path.join(a.root, "Frame_Cuts.csv")))}
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".json"):
            os.remove(os.path.join(OUT, f))
    takes = []
    for style, gaits in STYLES.items():
        if a.only and style not in a.only:
            continue
        for g in gaits:
            path = os.path.join(a.root, style, "%s_%s.bvh" % (style, g))
            c = cuts.get(style, {})
            if not os.path.isfile(path) or c.get(g + "_START") in (None, "N/A"):
                print("  missing", style, g); continue
            fps, _, _ = bvh_root(path)
            s0, s1 = int(c[g + "_START"]) / fps, int(c[g + "_STOP"]) / fps
            s0, s1 = best_window(path, s0, s1, g)
            name = "%s%s_%s" % (PREFIX, GAIT_NAME[g], style.lower())
            try:
                rec, out, _ = ML.import_file(path, name=name, library=OUT, licence=LICENCE, loop=True,
                                             category="Locomotion", start=s0, end=s1, cycle=True)
            except Exception as e:  # noqa: BLE001
                print("  %-26s failed: %s" % (name, e)); continue
            canon = rec["import"]["canonical"] or {}
            cyc = canon.get("cycle_s") or [s0, s1]
            vx, vz = local_velocity(path, cyc[0], cyc[1])
            drift = straighten(rec)
            rec["import"]["straightened_deg"] = round(drift, 1)
            bad = [k for k, ok, _ in CM.check_clip(rec, name) if ok is False]
            mismatch = float(canon.get("cycle_mismatch") or 0)
            if bad or mismatch > 1.0 or rec["import"]["retarget_mean_dir_err_deg"] > 6:
                os.remove(out)
                print("  %-26s rejected: checks %s, loop seam %.2f, drift %+.0f deg" % (name, bad, mismatch, drift)); continue
            rec["desc"] = "%s %s (100STYLE studio mocap)" % (style, GAIT_NAME[g])
            rec["import"]["root_velocity"] = [round(vx, 3), round(vz, 3)]
            json.dump(rec, open(out, "w"), indent=0)
            takes.append(dict(name=name, take="%s %s" % (style, GAIT_NAME[g]), style=style, gait=g, loop=True,
                              category="Locomotion", duration=rec["duration"], root_velocity=[round(vx, 3), round(vz, 3)],
                              retarget_err_deg=rec["import"]["retarget_mean_dir_err_deg"], loop_seam=round(mismatch, 3)))
            print("  %-26s %4.2fs  v=(%+.2f, %+.2f) m/s  seam %.2f  straightened %+.0f deg" % (name, rec["duration"], vx, vz, mismatch, drift))
    json.dump(dict(source="100STYLE (Mason, Starke, Komura 2022) via sforge.motionlib", licence=LICENCE, takes=takes),
              open(os.path.join(OUT, "_import.json"), "w"), indent=1)
    man = json.load(open(MANIFEST))
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("soccer_" + PREFIX)]
    for t in takes:
        vx, vz = t["root_velocity"]
        man["clips"].append(dict(id="soccer_" + t["name"], poseDataKey="soccer_" + t["name"], category="Locomotion",
                                 duration=t["duration"], contactFraction=-1.0, footPlantFrames=[],
                                 rootVelocityX=vx, rootVelocityZ=vz, preferredSpeed=round(math.hypot(vx, vz), 3),
                                 preferredTurnRate=0.0, ballState="None", tags=["mocap", "studio", "100style", t["style"].lower()],
                                 boneCount=18, loop=True, footPlantSides=[]))
    json.dump(man, open(MANIFEST, "w"), indent=2)
    print("kept %d loops" % len(takes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
