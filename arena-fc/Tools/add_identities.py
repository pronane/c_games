#!/usr/bin/env python3
"""Add the squad identities Arena FC was not shipping (v3, v4, v7, v8 of the Sprite Forge squad) to
Data/models/soccer_player.glb, tailored like the rest, plus the close-up shading maps (Sprite Forge v11.36).

The squad GLB carried five of the nine MakeHuman identities, so every match was the same five faces.  This
conforms the other four onto Arena's skeleton (build_soccer_player.realistic_parts), tailors their kit
(sforge.tailor) and adds them with their skin / hair / eye textures (tailor.replace_parts with images) -
every clip in the GLB is kept; eye maps are graded (skinshade.grade_iris).  sforge.skinshade writes the tiling skin-detail maps and material presets
SoccerClipRig applies.

    python3 Tools/add_identities.py
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

from sforge import skinshade as SS  # noqa: E402
from sforge import tailor as T  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402

import build_soccer_player as BSP  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")
RIG = os.path.join(ARENA, "Data", "rig_default.json")
SHADE = os.path.join(ARENA, "Data", "textures", "skin")
NEW = ("v3", "v4", "v7", "v8")


def main() -> int:
    man = json.load(open(MANIFEST))
    have = set(p.rstrip("_") for p in man.get("variant_prefixes", []))
    todo = tuple(v for v in NEW if v not in have)
    SS.export(SHADE)
    print("wrote", SHADE)
    if not todo:
        print("identities already present:", sorted(have))
        return 0
    rig = json.load(open(RIG))
    heads = np.array([b["h"] for b in rig["bones"]], float)
    bones = T.bones_from_rig(rig)
    parts, mats, images, _h = BSP.realistic_parts(rig, heads, variants=todo)
    mat_by_name = {m["name"]: m for m in mats}
    by_prefix = {}
    for v in todo:
        mine = {p["name"][len(v) + 1:]: T.Part(p["name"], p["V"], p["N"], p["UV"], p["J"], p["W"], p["F"], p["material"])
                for p in parts if p["name"].startswith(v + "_")}
        kit = T.tailor(mine, bones, garments=T.soccer_garments() + T.keeper_garments(), log=lambda *a: None)
        errs = T.qa(kit, bones)
        if errs:
            print(v, "kit QA failed:", errs)
            return 1
        mine.update(kit)
        by_prefix[v + "_"] = mine
        print("  %s: %d parts" % (v, len(mine)))
    materials = {n: m for n, m in mat_by_name.items() if n not in ("jersey", "shorts", "socks", "boots")}
    # MakeHuman's brown irises are red-brown (red on a broadcast grade): grade every eye map, old and new
    for nm, m in materials.items():
        if nm.startswith("eyes_") and m.get("image") in images:
            images[m["image"]] = SS.grade_iris(images[m["image"]])
    j, _b = read_glb(GLB)
    eye_imgs = {j["textures"][m["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]
                for m in j.get("materials", []) if m.get("name", "").startswith("eyes_")
                and "baseColorTexture" in m.get("pbrMetallicRoughness", {})}
    n = T.replace_parts(GLB, GLB, by_prefix, materials=materials, images=images,
                        image_filter=lambda k, im, raw: SS.grade_iris(raw) if k in eye_imgs else None)
    print("wrote %s (%.1f MB)" % (GLB, n / 1e6))
    man["variants"] = sorted(have | set(todo))
    man["variant_prefixes"] = [v + "_" for v in man["variants"]]
    man["skin_shading"] = "textures/skin/materials.json"
    man["materials"] = [m.get("name") for m in read_glb(GLB)[0].get("materials", [])]   # the new skins and eyes
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
