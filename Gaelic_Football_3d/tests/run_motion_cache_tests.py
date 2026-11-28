#!/usr/bin/env python3
"""Run the C cache test with isolated temporary filenames."""
import os
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix="gaelic-motion-test-") as directory:
    subprocess.run([sys.argv[1], *(os.path.join(directory, name) for name in
                   ("model.glb", "motion.bin", "other.glb", "./model.glb"))], check=True)
