#!/usr/bin/env python3
"""Add Sprite Forge's match-officials pack (v11.31, sforge.officials) to Arena FC.

  * the officials' signal clips (whistle, cards, advantage, penalty, free kicks, the assistant's flag
    signals, the fourth official's board), retargeted from the Sprite Forge mannequin onto Arena's
    18-bone skeleton and appended to Data/models/soccer_player.glb - every clip already in the GLB
    (procedural, CMU, SkillCorner, Veo) is kept;
  * their entries and action aliases in Data/soccer_player_manifest.json;
  * the props (flag, cards, whistle, board) as Data/models/officials_props.glb.

Idempotent: running it again replaces the officials clips with freshly baked ones.

    python3 Tools/add_official_clips.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))
sys.path.insert(0, HERE)

from sforge import bonemap as BM  # noqa: E402
from sforge import officials as O  # noqa: E402
from sforge import retarget as RT  # noqa: E402
from sforge import rigrec as RR  # noqa: E402

import build_soccer_player as BSP  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
PROPS = os.path.join(ARENA, "Data", "models", "officials_props.glb")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")
RIG = os.path.join(ARENA, "Data", "rig_default.json")

# engine/presentation action -> clip (OfficialsView sets these on its officials' PlayerState.Action)
ALIASES = {"off_" + n: n for n in O.CLIPS}


def main() -> int:
    O.register()
    errs = {n: e for n, e in O.qa_all().items() if e}
    if errs:
        print("officials QA failed:", errs)
        return 1
    rig_json = json.load(open(RIG))
    tgt = BSP.arena_rig(rig_json)
    tgt_rec = BSP.arena_bonemap(tgt)
    src = RR.from_mannequin(name="officials_src", clips=list(O.CLIPS))
    src_rec = BM.detect(src)
    clips = {}
    for name in O.CLIPS:
        cl, rep = RT.retarget(src, src_rec, name, tgt, tgt_rec, root_motion="inplace", name=name)
        clips[name] = cl
        print("  %-15s %3d frames  dir err %.2f deg" % (name, cl.frames, rep["mean_dir_err_deg"] or 0))
    n = O.append_clips(GLB, GLB, tgt, clips)
    print("wrote %s (%.1f MB)" % (GLB, n / 1e6))
    O.props_glb(PROPS)
    print("wrote %s" % PROPS)
    man = json.load(open(MANIFEST))
    man["clips"] = [c for c in man["clips"] if c["name"] not in O.CLIPS]
    for name, cl in clips.items():
        ev = O.EVENTS[name]
        man["clips"].append({"name": name, "loop": False, "category": "Official", "source": "sforge.officials v11.31",
                             "frames": int(cl.frames), "fps": float(cl.fps),
                             "events": {"ball_contact": -1, "ball_contact_frac": -1.0, "footsteps": [],
                                        "hit_start": -1, "hit_end": -1,
                                        "signal": int(round(ev["signal"] * (cl.frames - 1)))}})
    man["action_aliases"].update(ALIASES)
    man["officials"] = {"pack": "sforge.officials v11.31", "props": "models/officials_props.glb",
                        "kits": O.KITS, "roles": O.ROLES}
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    print("manifest: %d clips" % len(man["clips"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
