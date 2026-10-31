#!/usr/bin/env python3
"""Restyle a Sprite Forge character to match a game's own sprites (v9.4; sforge/stylematch.py).

    python tools/style_match.py REF SRC_OUT DST_OUT [--analyse-only]
REF = folder of the game's sprite PNGs (or one sheet).  SRC_OUT / DST_OUT = Sprite Forge output folders."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sforge import stylematch as SM

ap = argparse.ArgumentParser()
ap.add_argument("ref"); ap.add_argument("src", nargs="?"); ap.add_argument("dst", nargs="?")
ap.add_argument("--analyse-only", action="store_true")
a = ap.parse_args()
st = SM.analyse(a.ref)
print(json.dumps({k: v for k, v in st.items() if k != "palette"}), "%d palette colours" % len(st["palette"]))
if not a.analyse_only:
    SM.restyle_build(a.src, a.dst, st)
