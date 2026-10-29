#!/usr/bin/env python3
"""Sprite Forge Studio GUI launcher (same as `python forge.py gui`)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sforge.gui import main
if __name__ == "__main__":
    sys.exit(main() or 0)
