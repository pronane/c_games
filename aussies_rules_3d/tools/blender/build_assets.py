"""Run every asset generator in its own Blender (bpy) process.

Run:  .venv/bin/python build_assets.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATORS = ["gen_player.py", "gen_ball.py", "gen_stadium.py"]


def main():
    only = set(sys.argv[1:]) or None
    for gen in GENERATORS:
        if only and gen not in only and gen[:-3] not in only:
            continue
        print(f"=== {gen} ===", flush=True)
        res = subprocess.run([sys.executable, os.path.join(HERE, gen)])
        if res.returncode != 0:
            sys.exit(res.returncode)
    print("=== all assets built ===")


if __name__ == "__main__":
    main()
