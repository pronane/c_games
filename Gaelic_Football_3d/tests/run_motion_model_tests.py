#!/usr/bin/env python3
"""Exercise the actual model without leaving a generated motion cache in the tree."""
import os
import subprocess
import sys
import tempfile

if len(sys.argv) != 3:
    raise SystemExit("usage: run_motion_model_tests.py TOOL MODEL.glb")
with tempfile.TemporaryDirectory(prefix="gaelic-motion-model-") as directory:
    subprocess.run([sys.argv[1], sys.argv[2], os.path.join(directory, "motion.gfmotion")], check=True)
