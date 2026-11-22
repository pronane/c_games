#!/usr/bin/env python3
"""Bake two levels of detail for every squad identity into Data/models/soccer_player.glb (Sprite Forge
skinlod v11.38).  Each part gets `<part>_lod1` / `<part>_lod2` nodes on the same skin and material; the
manifest records which levels exist per part and the switch distances per quality tier, and SoccerClipRig
sets the visibility ranges.

    python3 Tools/add_lods.py          (after tailor_soccer_player.py / add_identities.py)
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))

from sforge import skinlod as SL  # noqa: E402
from sforge import tailor as T  # noqa: E402

GLB = os.path.join(ARENA, "Data", "models", "soccer_player.glb")
MANIFEST = os.path.join(ARENA, "Data", "soccer_player_manifest.json")


def main() -> int:
    man = json.load(open(MANIFEST))
    by_prefix, table = {}, {}
    t0 = time.time()
    for pre in man.get("variant_prefixes", ["v0_"]):
        parts = {k: v for k, v in T.read_parts(GLB, pre).items() if "_lod" not in k}
        lods = SL.lod_parts(parts)
        add = {}
        for name, levels in lods.items():
            row = []
            for k, q in enumerate(levels, start=1):
                if q is None:
                    row.append(-1)                       # dropped from this level on
                elif q is parts[name]:
                    row.append(0)                        # the full part carries on
                else:
                    add["%s_lod%d" % (name, k)] = q
                    row.append(1)
            table[name] = row
        by_prefix[pre] = add
        tri0 = sum(len(p.F) for p in parts.values())
        tri = [sum(len(q[k].F) for q in lods.values() if q[k] is not None) for k in range(len(SL.LOD_PLAN["ratios"]))]
        print("  %s %d -> %s tris (%.0fs)" % (pre, tri0, " / ".join(map(str, tri)), time.time() - t0))
    n = T.replace_parts(GLB, GLB, by_prefix)
    print("wrote %s (%.1f MB)" % (GLB, n / 1e6))
    man["lod"] = {"sprite_forge": "v11.38 sforge.skinlod", "parts": table,
                  "distances_m": {k: list(v) for k, v in SL.LOD_PLAN["distances_m"].items()}}
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
