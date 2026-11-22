#!/usr/bin/env python3
"""Import real motion capture (CMU Graphics Lab database) for Arena FC through Sprite Forge.

The CMU database is free to use, including inside commercially sold products; the raw
data may not be resold, even converted (mocap.cs.cmu.edu FAQ).  The BVH copy used here
is the cgspeed conversion mirrored at github.com/meshula/cmu-mocap.

This picks the football-relevant takes (soccer kicks, runs and jogs, cuts, veers and
sudden stops), runs each through Sprite Forge's importer - BVH -> retarget onto the
shared skeleton -> canonical keys (the calibration T-pose dropped, a running take cut
to its best loop, a kick cut around the strike and turned to face forward) - and
saves them as Sprite Forge library moves in Data/mocap/cmu/ with their licence record.
Tools/soccer_motions.py then bakes them into the player GLB like any other clip, and
the motion-matching table picks them up.

    python3 Tools/import_cmu_football.py --cmu /path/to/cmu-mocap   [--only NAME ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)

OUT = os.path.join(ARENA, "Data", "mocap", "cmu")

LICENCE = dict(
    spdx="custom",
    custom_text=("CMU Graphics Lab Motion Capture Database: free for all uses; may be included in "
                 "commercially-sold products; the data may not be resold directly, even in converted form."),
    author="Carnegie Mellon University Graphics Lab",
    source_url="http://mocap.cs.cmu.edu/",
    redistribution="yes", ml_training="yes",  # v11.40: CMU: free for all uses
    attribution=("The data used in this project was obtained from mocap.cs.cmu.edu. "
                 "The database was created with funding from NSF EIA-0196217."),
    notes="BVH conversion by B. Hahne (cgspeed), mirrored at github.com/meshula/cmu-mocap.",
)

# name, take, loop, category, cut: ("cycle",) | ("peak", bone, before_s, after_s) | ("span", start_s, end_s) | None
TAKES = [
    # soccer kicks (subjects 10 and 11): one strike each, cut around the kicking foot's peak
    ("mocap_kick_a", "10_01", False, "Kick", ("peak", "foot_R", .55, .55)),
    ("mocap_kick_b", "10_02", False, "Kick", ("peak", "foot_R", .55, .55)),
    ("mocap_kick_c", "10_03", False, "Kick", ("peak", "foot_R", .55, .55)),
    ("mocap_kick_d", "10_05", False, "Kick", ("peak", "foot_R", .55, .55)),
    ("mocap_kick_e", "10_06", False, "Kick", ("peak", "foot_R", .55, .55)),
    ("mocap_kick_f", "11_01", False, "Kick", ("peak", "foot_R", .55, .55)),
    # running and jogging: the best loop in each take
    ("mocap_run_a", "09_01", True, "Locomotion", ("cycle",)),
    ("mocap_run_b", "09_02", True, "Locomotion", ("cycle",)),
    ("mocap_run_c", "09_06", True, "Locomotion", ("cycle",)),
    ("mocap_run_d", "16_55", True, "Locomotion", ("cycle",)),
    ("mocap_jog_a", "16_35", True, "Locomotion", ("cycle",)),
    ("mocap_jog_b", "16_36", True, "Locomotion", ("cycle",)),
    ("mocap_jog_c", "02_03", True, "Locomotion", ("cycle",)),
    # direction changes and stops: whole takes (approach, plant, away)
    ("mocap_cut_left", "16_41", False, "Cut", None),
    ("mocap_cut_right", "16_43", False, "Cut", None),
    ("mocap_cut_left_fast", "16_51", False, "Cut", None),
    ("mocap_cut_right_fast", "16_53", False, "Cut", None),
    ("mocap_stop_a", "16_08", False, "Recovery", None),
    ("mocap_stop_b", "16_57", False, "Recovery", None),
]


def take_path(cmu: str, take: str) -> str:
    subject = int(take.split("_")[0])
    return os.path.join(cmu, "data", "%03d" % subject, take + ".bvh")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cmu", required=True, help="folder of the cmu-mocap BVH mirror (has data/NNN/NN_NN.bvh)")
    ap.add_argument("--only", nargs="*", help="import just these names")
    args = ap.parse_args()
    from sforge import motionlib as ML
    os.makedirs(OUT, exist_ok=True)
    report = []
    for name, take, loop, category, cut in TAKES:
        if args.only and name not in args.only:
            continue
        path = take_path(args.cmu, take)
        if not os.path.isfile(path):
            print("  missing %s (%s) - skipped" % (take, path))
            continue
        kw = dict(name=name, library=OUT, licence=LICENCE, loop=loop, category=category)
        if cut and cut[0] == "cycle":
            kw["cycle"] = True
        elif cut and cut[0] == "peak":
            kw["peak"] = cut[1:]
            kw["cycle"] = False
        elif cut and cut[0] == "span":
            kw["start"], kw["end"] = cut[1], cut[2]
            kw["cycle"] = False
        else:
            kw["cycle"] = False
        rec, out, problems = ML.import_file(path, **kw)
        imp = rec.get("import", {})
        line = "%-22s %s  %5.2fs  %3d keys  retarget err %.1f deg  projection %.3f m%s" % (
            name, take, rec["duration"], len(rec["keys"]), imp.get("retarget_mean_dir_err_deg") or 0.0,
            imp.get("projection_mean_m") or 0.0, ("  LICENCE: " + "; ".join(problems)) if problems else "")
        print("  " + line)
        report.append(dict(name=name, take=take, loop=loop, category=category, duration=rec["duration"],
                           keys=len(rec["keys"]), retarget_err_deg=imp.get("retarget_mean_dir_err_deg"),
                           projection_m=imp.get("projection_mean_m")))
    with open(os.path.join(OUT, "_import.json"), "w") as f:
        json.dump(dict(source="CMU Graphics Lab Motion Capture Database", licence=LICENCE, takes=report), f, indent=1)
    print("wrote %d moves to %s" % (len(report), os.path.relpath(OUT, ARENA)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
