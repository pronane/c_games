#!/usr/bin/env python3
"""Build Arena FC's grounds, crowd and pitch-side boards with Sprite Forge (v11.32).

    python3 Tools/build_stadiums.py

  Data/stadiums/stadium_<preset>.glb / .json / .seats   sforge.stadium: bowl (two tiers, curved corners,
                                                          masts), classic (four stands, open corners, roof
                                                          lights), ground (one tier, partial roof)
  Data/stadiums/crowd.glb                                sforge.crowd: seated / standing spectators, flag, scarf
  Data/stadiums/ad_boards.png                            sforge.adboards: original fictional sponsors

World3D.Stadium picks the preset from the home club's ground (capacity / roof) and falls back to its old
procedural stands when these files are missing.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))

from sforge import adboards as AB  # noqa: E402
from sforge import crowd as CR  # noqa: E402
from sforge import stadium as ST  # noqa: E402

OUT = os.path.join(ARENA, "Data", "stadiums")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for name in ST.PRESETS:
        info = ST.export(ST.PRESETS[name], os.path.join(OUT, "stadium_%s.glb" % name))
        print("  %-8s %6d tris %6d seats  %d lights" % (name, info["tris"], info["seats"], len(info["lights"])))
    print("  crowd   ", CR.export(os.path.join(OUT, "crowd.glb")))
    AB.atlas(os.path.join(OUT, "ad_boards.png"))
    print("  boards   %d panels" % len(AB.SPONSORS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
