#!/usr/bin/env python3
"""Add Sprite Forge's touchline pack (v11.39) to Arena FC.

  * the pitch-side clips (sforge.pitchside: subs on the bench, managers, staff, ball kids, photographers),
    retargeted onto Arena's 18-bone skeleton and appended to Data/models/soccer_player.glb - every clip
    already in it is kept;
  * their manifest entries (looping), plus a "pitchside" section with the role looks;
  * the camera prop as Data/models/pitchside_props.glb;
  * the goal (posts, bar, stanchions, deformable net) and corner flag as Data/models/goal_soccer.glb
    (sforge.goalnet);
  * where everyone goes round each ground: Data/stadiums/stadium_<preset>.pitchside.json
    (sforge.pitchside.placements on the ground's .json - run Tools/build_stadiums.py first).

Idempotent: running it again replaces the pitch-side clips.

    python3 Tools/add_pitchside.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))
sys.path.insert(0, HERE)

from sforge import bonemap as BM  # noqa: E402
from sforge import goalnet as G  # noqa: E402
from sforge import officials as O  # noqa: E402
from sforge import pitchside as PS  # noqa: E402
from sforge import retarget as RT  # noqa: E402
from sforge import rigrec as RR  # noqa: E402

import build_soccer_player as BSP  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
PROPS = os.path.join(ARENA, "Data", "models", "pitchside_props.glb")
GOAL = os.path.join(ARENA, "Data", "models", "goal_soccer.glb")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")
RIG = os.path.join(ARENA, "Data", "rig_default.json")


def main() -> int:
    PS.register()
    bad = PS.qa_all()
    if bad:
        print("pitchside QA failed:", bad)
        return 1
    tgt = BSP.arena_rig(json.load(open(RIG)))
    tgt_rec = BSP.arena_bonemap(tgt)
    src = RR.from_mannequin(name="pitchside_src", clips=list(PS.CLIPS))
    src_rec = BM.detect(src)
    clips = {}
    for name in PS.CLIPS:
        cl, rep = RT.retarget(src, src_rec, name, tgt, tgt_rec, root_motion="inplace", name=name)
        clips[name] = cl
        print("  %-19s %3d frames  dir err %.2f deg" % (name, cl.frames, rep["mean_dir_err_deg"] or 0))
    n = O.append_clips(GLB, GLB, tgt, clips)
    print("wrote %s (%.1f MB)" % (GLB, n / 1e6))
    PS.props_glb(PROPS)
    G.export(GOAL, "soccer")
    print("wrote %s, %s" % (PROPS, GOAL))
    sd = os.path.join(ARENA, "Data", "stadiums")
    for f in sorted(os.listdir(sd)):
        if f.startswith("stadium_") and f.endswith(".json") and ".pitchside" not in f:
            st = json.load(open(os.path.join(sd, f)))
            spots = PS.placements(st, *st["pitch_half"])
            out = os.path.join(sd, f[:-5] + ".pitchside.json")
            with open(out, "w") as fh:
                json.dump({"pack": "sforge.pitchside v11.39", "spots": spots}, fh, indent=1)
            print("wrote %s (%d people)" % (out, len(spots)))
    man = json.load(open(MANIFEST))
    man["clips"] = [c for c in man["clips"] if c["name"] not in PS.CLIPS]
    for name, cl in clips.items():
        ev = PS.EVENTS[name]
        man["clips"].append({"name": name, "loop": bool(PS.CLIPS[name]["loop"]), "category": "Pitchside",
                             "source": "sforge.pitchside v11.39", "frames": int(cl.frames), "fps": float(cl.fps),
                             "events": {"ball_contact": -1, "ball_contact_frac": -1.0, "footsteps": [],
                                        "hit_start": -1, "hit_end": -1,
                                        **({"peak": int(round(ev["peak"] * (cl.frames - 1)))} if "peak" in ev else {})}})
    man["pitchside"] = {"pack": "sforge.pitchside v11.39", "props": "models/pitchside_props.glb",
                        "goal": "models/goal_soccer.glb", "looks": PS.LOOKS}
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    print("manifest: %d clips" % len(man["clips"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
