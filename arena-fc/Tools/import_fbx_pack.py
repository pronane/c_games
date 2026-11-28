#!/usr/bin/env python3
"""Import a studio mocap pack (FBX, via Sprite Forge's fbx_to_moves) as game moves.

First pack: Anderson Rohr's free "Mocap Pack 05 - Soccer" (21 Rokoko takes at 60 fps,
free for personal and commercial projects; no redistribution as a standalone pack).

    GODOT=... python3 ../sprite_forge/tools/fbx_to_moves.py /tmp/rr Mocap/Rokoko_Default/*.fbx --prefix rr
    python3 Tools/import_fbx_pack.py /tmp/rr

Long takes are cut into the moves the game plays:
  * kicks / penalties: the strike (fastest thigh swing) from 1.0 s before to 0.7 s after
  * keeper saves: the dive (fastest whole-body change) from 0.8 s before to 1.2 s after
  * defending: the lunge, 0.8 s before to 0.9 s after
  * dribbles: the cleanest stride loop (0.5-1.1 s)
  * celebrations: whole
Juggling and the referee card gestures stay in Sprite Forge's library only (no game use yet).
Writes Data/mocap/rohr/ (rr_*), the clip-manifest rows, and the moves' licence.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF); sys.path.insert(0, os.path.join(SF, "tools")); sys.path.insert(0, HERE)
OUT = os.path.join(ARENA, "Data", "mocap", "rohr")
MANIFEST = os.path.join(ARENA, "Data", "clips", "clip_manifest.json")
PREFIX = "rr_"
LICENCE = dict(spdx="LicenseRef-AndersonRohr-MocapPack05",
               author="Anderson Rohr (Mocap Pack 05 - Soccer)",
               source_url="https://andersonrohr.gumroad.com/l/mocap_pack5",
               redistribution="no - not as a standalone pack; use inside a game is allowed", ml_training="unknown",  # v11.40: the pack's terms say nothing about training models
               text="Free for personal and commercial projects. Do not redistribute, resell or repackage the "
                    "pack as a standalone product.",
               attribution="Soccer motion capture by Anderson Rohr.")

# take (file stem) -> (kind, game category, ball state, cut, sub)
PLAN = {
    "08_side_foot_kick": ("pass", "Pass", "Possessed", "strike", "side_foot"),
    "09_power_kick": ("shot", "Kick", "Possessed", "strike", "power"),
    "10_penalty_kick_01": ("shot", "Kick", "Possessed", "strike", "penalty"),
    "11_penalty_kick_02": ("shot", "Kick", "Possessed", "strike", "penalty"),
    "15_goalkeeper_save_01": ("save", "KeeperDive", "Approaching", "dive", "save"),
    "16_goalkeeper_save_02": ("save", "KeeperDive", "Approaching", "dive", "save"),
    "17_goalkeeper_save_03": ("save", "KeeperDive", "Approaching", "dive", "save"),
    "18_defending_01": ("tackle", "Tackle", "None", "lunge", "tackle"),
    "19_defending_02": ("tackle", "Tackle", "None", "lunge", "tackle"),
    "01_dribble_01": ("carry", "Locomotion", "Possessed", "loop", "dribble"),
    "02_dribble_02": ("carry", "Locomotion", "Possessed", "loop", "dribble"),
    "03_dribble_03": ("carry", "Locomotion", "Possessed", "loop", "dribble"),
    "12_goal_celebration_01": ("celebrate", "Celebrate", "None", "whole", "celebration"),
    "13_goal_celebration_02": ("celebrate", "Celebrate", "None", "whole", "celebration"),
    "14_goal_celebration_03": ("celebrate", "Celebrate", "None", "whole", "celebration"),
}
WINDOWS = {"strike": (1.0, .7), "dive": (.8, 1.2), "lunge": (.8, .9)}


def series(keys, ch, c=None):
    return np.array([float(k[1][ch][c] if c is not None else k[1][ch]) for k in keys])


def peak_time(rec, cut):
    """index of the cut's moment: fastest thigh swing (strike / lunge) or fastest whole-body change (dive)."""
    K = rec["keys"]
    if cut == "dive":
        chans = [("hips", 0), ("hips", 1), ("hips", 2), ("chest", 0), ("chest", 2), ("leg_L", 0), ("leg_R", 0)]
    else:
        chans = [("leg_L", 0), ("leg_R", 0), ("knee_L", None), ("knee_R", None)]
    speed = sum(np.abs(np.gradient(series(K, ch, c))) for ch, c in chans)
    speed[:3] = 0; speed[-3:] = 0
    return int(np.argmax(speed))


def cut_keys(rec, i0, i1):
    K = rec["keys"][i0:i1 + 1]
    t0, t1 = K[0][0], K[-1][0]
    dur = rec["duration"] * (t1 - t0)
    return [[(k[0] - t0) / max(1e-9, t1 - t0), k[1]] for k in K], dur


def main() -> int:
    src = sys.argv[1]
    from sforge.matchcapture import best_loop_keys
    import check_motion as CM
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".json"):
            os.remove(os.path.join(OUT, f))
    takes, count = [], {}
    for stem, (kind, gcat, ball, cut, sub) in PLAN.items():
        p = os.path.join(src, "rr_%s.json" % stem)
        if not os.path.isfile(p):
            print("  missing", stem); continue
        rec = json.load(open(p))
        n = len(rec["keys"]); fps = (n - 1) / rec["duration"]
        contact, loop = -1.0, False
        if cut in WINDOWS:
            c = peak_time(rec, cut)
            pre, post = WINDOWS[cut]
            i0, i1 = max(0, c - int(pre * fps)), min(n - 1, c + int(post * fps))
            keys, dur = cut_keys(rec, i0, i1)
            contact = round((c - i0) / max(1, i1 - i0), 4) if cut == "strike" else -1.0
        elif cut == "loop":
            lk = best_loop_keys(rec["keys"], int(.5 * fps), int(1.1 * fps), max_seam=6.0)
            if lk is None:
                print("  no clean loop in", stem); continue
            keys, L = lk; dur = L / fps; loop = True
        else:
            keys, dur = rec["keys"], rec["duration"]
        count[kind] = count.get(kind, 0) + 1
        name = "%s%s_%02d" % (PREFIX, kind, count[kind])
        out = dict(rec, name=name, keys=keys, duration=round(dur, 4), loop=loop, licence=LICENCE,
                   source="mocap:anderson-rohr-pack05:" + stem, desc="%s (studio mocap, Anderson Rohr)" % sub.replace("_", " "))
        out["import"] = dict(rec.get("import", {}), contact=contact, sub=sub, from_take=stem)
        bad = [c for c, ok, _ in CM.check_clip(out, name) if ok is False]
        if bad and not (loop is False and bad == ["loop"]):
            print("  %-14s rejected by checks: %s" % (name, bad)); count[kind] -= 1; continue
        json.dump(out, open(os.path.join(OUT, name + ".json"), "w"), indent=0)
        from import_matchcapture import stride_speed
        speed = stride_speed(keys, dur) if loop else 0.0
        takes.append(dict(name=name, take=stem, kind=kind, loop=loop, category=gcat, ball_state=ball, duration=round(dur, 4),
                          contact=contact, fit_err_deg=rec["import"]["mean_bone_err_deg"], speed=round(speed, 3)))
        print("  %-14s <- %-24s %4.2fs%s" % (name, stem, dur, "  contact %.2f" % contact if contact >= 0 else ("  loop %.1f m/s" % speed if loop else "")))
    json.dump(dict(source="Anderson Rohr Mocap Pack 05 - Soccer via sforge fbx_to_moves", licence=LICENCE, takes=takes),
              open(os.path.join(OUT, "_import.json"), "w"), indent=1)
    man = json.load(open(MANIFEST))
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("soccer_" + PREFIX)]
    for t in takes:
        tags = ["mocap", "studio", "rohr"]
        if t["ball_state"] == "Possessed": tags.append("ball_possessed")
        if t["contact"] >= 0: tags.append("ball_contact")
        speed = t.get("speed", 0.0)                            # a dribble loop at its own stride pace
        man["clips"].append(dict(id="soccer_" + t["name"], poseDataKey="soccer_" + t["name"], category=t["category"],
                                 duration=t["duration"], contactFraction=t["contact"], footPlantFrames=[],
                                 rootVelocityX=0.0, rootVelocityZ=speed, preferredSpeed=speed, preferredTurnRate=0.0,
                                 ballState=t["ball_state"], tags=tags, boneCount=18, loop=t["loop"], footPlantSides=[]))
    json.dump(man, open(MANIFEST, "w"), indent=2)
    print("kept %d moves %s" % (len(takes), count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
