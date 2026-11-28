#!/usr/bin/env python3
"""Add Sprite Forge's Meshy soccer clips (v11.42) to Arena FC.

  * every Meshy Text to Motion soccer clip in sprite_forge/motion_library_owned (catalogue:
    sprite_forge/game_packs/meshy/soccer_full.json), retargeted from the Sprite Forge mannequin onto
    Arena's 18-bone skeleton and appended to Data/models/soccer_player.glb as soccer_mz_<move> -
    every clip already in the GLB (procedural, CMU, SkillCorner, Veo, officials) is kept;
  * their entries in Data/soccer_player_manifest.json, with events measured from each clip
    (ball contact at the fastest foot / hand or the head's peak, a tackle's hit window);
  * the action aliases from Tools/soccer_motions.py, so game actions (pass, shoot, throw_in,
    keeper_dive_left, skill_<move>, ...) play the Meshy clips, and mz_<move> names every other move.

Idempotent: running it again replaces the Meshy clips with freshly baked ones.

    python3 Tools/add_meshy_clips.py [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))
sys.path.insert(0, HERE)

from sforge import bonemap as BM  # noqa: E402
from sforge import officials as O  # noqa: E402  (append_clips)
from sforge import retarget as RT  # noqa: E402
from sforge import rigrec as RR  # noqa: E402

import build_soccer_player as BSP  # noqa: E402
import soccer_motions as SM  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")
RIG = os.path.join(ARENA, "Data", "rig_default.json")


def manifest_entry(name, cl):
    ev = SM.CLIP_EVENTS[name]
    fr = int(cl.frames)
    to_f = lambda x: -1 if x is None or x < 0 else int(round(x * (fr - 1)))
    return {"name": name, "loop": name in SM.LOOP_CLIPS, "category": SM.CLIP_CATEGORIES[name],
            "source": "meshy:" + SM.CLIP_SOURCES[name].split(":", 1)[-1], "frames": fr, "fps": float(cl.fps),
            "events": {"ball_contact": to_f(ev["ball_contact"]),
                       "ball_contact_frac": float(ev["ball_contact"]) if ev["ball_contact"] >= 0 else -1.0,
                       "footsteps": [to_f(x) for x in ev.get("footsteps", [])],
                       "hit_start": to_f(ev["hit_start"]), "hit_end": to_f(ev["hit_end"])},
            "licence": "LicenseRef-Owned-Meshy"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check that the GLB and manifest are up to date")
    a = ap.parse_args(argv)
    SM.register()
    names = sorted(SM.MESHY_CLIPS)
    man = json.load(open(MANIFEST))
    if a.check:
        have = {c["name"] for c in man["clips"]}
        missing = [n for n in names if n not in have]
        stale = {k: v for k, v in SM.ACTION_ALIASES.items() if man["action_aliases"].get(k) != v and v in SM.MESHY_CLIPS}
        print("%d Meshy clips; %d missing from the manifest, %d action aliases out of date" % (len(names), len(missing), len(stale)))
        return 1 if missing or stale else 0
    rig_json = json.load(open(RIG))
    tgt = BSP.arena_rig(rig_json)
    tgt_rec = BSP.arena_bonemap(tgt)
    src = RR.from_mannequin(name="meshy_src", clips=names)
    src_rec = BM.detect(src)
    clips, errs = {}, []
    for name in names:
        cl, rep = RT.retarget(src, src_rec, name, tgt, tgt_rec, root_motion="inplace", name=name)
        clips[name] = cl
        e = rep["mean_dir_err_deg"] or 0.0
        if e > 8.0:
            errs.append("%s %.1f deg" % (name, e))
    print("retargeted %d Meshy clips (worst bone-direction errors: %s)" % (len(clips), ", ".join(errs) or "none over 8 deg"))
    n = O.append_clips(GLB, GLB, tgt, clips)
    print("wrote %s (%.1f MB)" % (GLB, n / 1e6))
    man["clips"] = [c for c in man["clips"] if c["name"] not in clips] + [manifest_entry(nm, cl) for nm, cl in clips.items()]
    changed = {k: v for k, v in SM.ACTION_ALIASES.items() if man["action_aliases"].get(k) != v}
    man["action_aliases"].update(SM.ACTION_ALIASES)
    man["meshy"] = {"pack": "sprite_forge v11.42 meshy (Text to Motion, owner-held)", "clips": len(clips),
                    "catalogue": "sprite_forge/game_packs/meshy/soccer_full.json"}
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    print("manifest: %d clips, %d action aliases (%d changed)" % (len(man["clips"]), len(man["action_aliases"]), len(changed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
