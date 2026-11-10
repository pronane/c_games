#!/usr/bin/env python3
"""Fill a private motion library with real motion capture from the CMU Graphics Lab database (v11.6).

    python tools/import_cmu.py --library ~/sprite_forge_motions [--bvh-dir DIR]

Downloads only the takes listed below (BVH conversion: github.com/sfd158/cmu-mocap, a git sparse checkout)
into DIR (default: <library>/_cmu_bvh), then imports each move with `forge.py motion import`: cut out of the
long take, turned to face forward, put on the floor, resampled to 30 fps. Build with
`--motion-library <library>`; the game packs' `prefer` lists pick these clips by name (jab, roundhouse,
soccer_kick, jump_shot, ...) and fall back to the CC0 starter when a clip is not there.

Terms (mocap.cs.cmu.edu): "This data is free for use in research projects. You may include this data in
commercially-sold products, but you may not resell this data directly, even in converted form." So: sprites,
games and builds made with these clips are fine; the clip files themselves are not redistributed. That is why
they go into your own library folder and are never added to motion_library/ or to git. Acknowledgement CMU asks
for: "The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding
from NSF EIA-0196217." (stored in each clip's licence record)."""
from __future__ import annotations
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "https://github.com/sfd158/cmu-mocap.git"

# name, CMU take, import options. Times are seconds into the take; --peak cuts one strike around the frame where
# that bone is furthest from the hips.
TAKES = [
    ("idle_boxing", "13_17", ["--loop", "--start", "0.3", "--end", "2.0"]),
    ("jab", "13_17", ["--once", "--start", "2.6", "--end", "3.5", "--peak", "hand_L:0.3:0.35"]),
    ("cross", "13_17", ["--once", "--start", "1.6", "--end", "2.4", "--peak", "hand_R:0.3:0.35"]),
    ("punch_power", "13_17", ["--once", "--start", "8.4", "--end", "9.4", "--peak", "hand_R:0.35:0.4"]),
    ("punch_straight", "144_20", ["--once", "--start", "4.3", "--end", "5.3", "--peak", "hand_R:0.3:0.35"]),
    ("kick_front", "144_05", ["--once", "--start", "2.5", "--end", "3.5", "--peak", "foot_R:0.45:0.45"]),
    ("roundhouse", "135_07", ["--once", "--start", "0.5", "--end", "1.5", "--peak", "foot_R:0.45:0.45"]),
    ("side_kick", "135_11", ["--once", "--start", "2.5", "--end", "3.4", "--peak", "foot_R:0.45:0.45"]),
    ("jump_kick", "90_05", ["--once", "--start", "1.5", "--end", "3.0", "--peak", "foot_L:0.8:0.5"]),
    ("soccer_kick", "10_01", ["--once", "--start", "4.0", "--end", "5.5", "--peak", "foot_R:0.6:0.4"]),
    ("soccer_shoot", "11_01", ["--once", "--start", "2.8", "--end", "4.3", "--peak", "foot_R:0.7:0.45"]),
    ("jog", "09_01", ["--loop"]),
    ("walk_casual", "141_19", ["--loop", "--start", "1.5", "--end", "5"]),
    ("throw_overhand", "124_01", ["--once", "--peak", "hand_R:0.7:0.4"]),
    ("jump_hop", "16_01", ["--once", "--start", "0.5", "--end", "2.2"]),
    ("jump_vertical", "118_10", ["--once", "--start", "0.8", "--end", "2.5"]),
    ("long_jump", "141_04", ["--once", "--start", "1.2", "--end", "2.6"]),
    ("block_high", "144_26", ["--once", "--start", "0.8", "--end", "1.9"]),
    ("basketball_shoot", "124_03", ["--once", "--start", "3.4", "--end", "5.0"]),
    ("jump_shot", "124_05", ["--once", "--start", "2.5", "--end", "4.2"]),
    ("layup", "124_06", ["--once", "--start", "2.0", "--end", "4.3"]),
    ("get_up", "140_01", ["--once", "--start", "1.2", "--end", "6.0"]),
    ("dribble", "06_02", ["--loop"]),
]
ACK = ("The data used in this project was obtained from mocap.cs.cmu.edu. "
       "The database was created with funding from NSF EIA-0196217.")
NOTE = ("CMU terms: may be included in products; do not redistribute or resell the data itself, even converted. "
        "Keep out of the public repo.")


def _path(take):
    subj = take.split("_")[0]
    return "data/%03d/%s.bvh" % (int(subj), take)


def fetch(dest, takes):
    if not os.path.isdir(os.path.join(dest, ".git")):
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, dest], check=True)
    subprocess.run(["git", "-C", dest, "sparse-checkout", "set", "--no-cone", "/READMEFIRST.txt",
                    "/cmu-mocap-index-text.txt"] + ["/" + _path(t) for t in takes], check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, help="your private motion library folder (not this repo)")
    ap.add_argument("--bvh-dir", help="where the BVH takes are kept (default: <library>/_cmu_bvh)")
    ap.add_argument("--only", nargs="*", help="import just these move names")
    a = ap.parse_args(argv)
    lib = os.path.abspath(os.path.expanduser(a.library))
    if os.path.commonpath([lib, HERE]) == HERE:
        sys.exit("refusing: %s is inside the Sprite Forge folder; CMU clips may not be redistributed, keep them "
                 "in a folder of your own" % lib)
    bvh = os.path.abspath(os.path.expanduser(a.bvh_dir or os.path.join(lib, "_cmu_bvh")))
    todo = [t for t in TAKES if not a.only or t[0] in a.only]
    fetch(bvh, sorted({t[1] for t in todo}))
    bad = 0
    for name, take, opts in todo:
        f = os.path.join(bvh, _path(take))
        cmd = [sys.executable, os.path.join(HERE, "forge.py"), "motion", "import", "--library", lib, f, "--name", name,
               "--spdx", "LicenseRef-CMU-Graphics-Lab-Mocap", "--author", "CMU Graphics Lab Motion Capture Database",
               "--source-url", "http://mocap.cs.cmu.edu/ (take %s)" % take, "--redistribution", "no",
               "--attribution", ACK, "--notes", NOTE] + opts
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = (r.stdout or r.stderr).strip().splitlines()
        print("%-16s %s" % (name, line[0] if line else "?"))
        bad += r.returncode != 0
    print("\n%d moves in %s. Build with --motion-library %s" % (len(todo) - bad, lib, lib))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
