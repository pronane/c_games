#!/usr/bin/env python3
"""Gaelic clip merge. Same command as `python3 forge.py gaelic-clip`. See sforge/gaelic_clip.py."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sforge.gaelic_clip import main
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
