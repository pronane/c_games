#!/usr/bin/env python3
"""Turf masks for Arena FC from Sprite Forge sforge.pitch (v11.33): one texture per mowing pattern.

    python3 Tools/build_pitch.py        # Data/pitch/pitch_soccer_<mow>.png + .json
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(ARENA, "..", "sprite_forge")))

from sforge import pitch as P  # noqa: E402


def main() -> int:
    out = os.path.join(ARENA, "Data", "pitch")
    for mow in P.MOW:
        P.export(os.path.join(out, "pitch_soccer_%s.png" % mow), "soccer", mow)
        print("  soccer", mow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
