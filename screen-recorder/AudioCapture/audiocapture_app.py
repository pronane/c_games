#!/usr/bin/env python3
"""Audio Capture Studio - double-click / ``python audiocapture_app.py`` to run.

Records what your speakers are playing (default) or a microphone, in HD
quality, and plays recordings back.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audiocapture.__main__ import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
