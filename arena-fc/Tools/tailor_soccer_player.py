#!/usr/bin/env python3
"""Tailor the squad's kit and boots and export the kit atlas (Sprite Forge v11.30).

The MakeHuman clothes in Data/models/soccer_player.glb hug every muscle and end in a staircase of
triangles, and the boots are bare feet.  This runs Sprite Forge's `sforge.tailor` on every identity
(v0_, v1_ ...): straight hems, cloth that drapes instead of clinging, a turned-in lip at each
opening, boots with a flat sole, all laid out on one kit atlas - and `sforge.kitdesign` writes the
masks, the lettering glyphs and the layout the kit shader (Shaders/kit.gdshader) reads.

Skeleton, skin and every clip in the GLB are kept, so it can run after any of the clip importers.
build_soccer_player.py runs it on every fresh build.  A GLB that is already tailored (asset extras
"kit_atlas") is left alone: tailoring cut garments twice would loosen them twice.

    python3 Tools/tailor_soccer_player.py                 # tailor Data/models/soccer_player.glb in place
    python3 Tools/tailor_soccer_player.py --src OLD.glb   # tailor from an untailored GLB
    python3 Tools/tailor_soccer_player.py --check         # QA only
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))

from sforge import kitdesign as KD  # noqa: E402
from sforge import tailor as T  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
KIT = os.path.join(ARENA, "Data", "textures", "kit")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")
RIG = os.path.join(ARENA, "Data", "rig_default.json")


def is_tailored(path):
    from sforge.glbpack import read_glb
    j, _ = read_glb(path)
    return "kit_atlas" in j.get("asset", {}).get("extras", {})


def tailor_glb(src, dst=GLB, check=False, log=print):
    """Tailor every identity of `src` into `dst` and export the kit atlas.  -> list of QA errors."""
    man = json.load(open(MANIFEST))
    bones = T.bones_from_rig(json.load(open(RIG)))
    out, errs = {}, []
    for pre in man.get("variant_prefixes", ["v0_"]):
        parts = T.read_parts(src, pre)
        log(pre)
        # the keeper's base layer and gloves, and staff trousers, ride along hidden; SoccerClipRig shows them per role
        out[pre] = T.tailor(parts, bones, garments=T.soccer_garments() + T.keeper_garments() + T.staff_garments(), log=log)
        errs += ["%s%s" % (pre, e) for e in T.qa(out[pre], bones)]
    if errs or check:
        return errs
    n = T.replace_parts(src, dst, out, extras={"kit_atlas": T.layout_json()})
    log("wrote %s (%.1f MB)" % (dst, n / 1e6))
    KD.export(KIT)
    log("wrote %s" % KIT)
    man["kit_atlas"] = "textures/kit/kit_layout.json"
    man["sprite_forge_tailor"] = "v11.37 sforge.tailor (flutter, keeper garments) + sforge.kitdesign"
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", help="an untailored GLB (default: the game's GLB, if it is not tailored yet)")
    ap.add_argument("--check", action="store_true", help="tailor in memory and run the QA, write nothing")
    a = ap.parse_args()
    src = a.src or GLB
    if is_tailored(src):
        print("%s is already tailored (asset extras kit_atlas); pass --src with an untailored GLB" % src)
        return 0 if a.check or not a.src else 1
    errs = tailor_glb(src, check=a.check)
    if errs:
        print("QA FAILED:", errs)
        return 1
    print("QA ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
