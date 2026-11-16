#!/usr/bin/env python3
"""Add Mixamo animations you downloaded to your motion library (v11.12).

    python tools/import_mixamo.py FOLDER_OR_ZIP --library ~/sprite_forge_motions

Download from mixamo.com (your Adobe sign-in): FBX Binary, Without Skin, 30 fps, no keyframe reduction, "In Place"
unticked. Each .fbx in the folder (sub-folders too) is imported onto the shared skeleton. Files whose Mixamo name
is in MOVES get the library name the game packs look for (e.g. "Goalkeeper Diving Save (1).fbx" -> keeper_dive_left,
the direction measured, not guessed); any other file is imported as mx_<its name>, ready to use with --prefer or a
motion set. Every clip goes through tools/check_motion.py; the report lists the ones that fail and why.

Licence: Mixamo animations are free to use in games and other projects, commercial included, but the files may
not be redistributed on their own. They go to your library only - never commit them."""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

# Mixamo file name (without " (1)" etc.) -> library name, loop. A name used twice gets the better / first file.
MOVES = {
    "fighting idle": ("idle_fighting", True),
    "boxing idle": ("idle_guard", True),
    "lead jab": ("jab_lead", False),
    "jab cross": ("jab_cross", False),
    "hook": ("hook_punch", False),
    "combo punch": ("combo_punch", False),
    "punch combo": ("combo_punch_2", False),
    "center block": ("block_center", False),
    "left block": ("block_left_arm", False),
    "receive punch to the face": ("hit_face", False),
    "head hit": ("hit_head", False),
    "hit to body": ("hit_body", False),
    "stomach hit": ("hit_stomach", False),
    "big stomach hit": ("hit_stomach_big", False),
    "livershot knockdown": ("knockdown", False),
    "defeat": ("defeat", False),
    "fallen idle": ("fallen_idle", True),
    "standing up": ("stand_up", False),
    "taunt": ("taunt_gesture", False),
    "victory": ("victory", False),
    "sitting victory": ("victory_kneel", False),
    "illegal headbutt": ("headbutt", False),
    "illegal knee": ("knee_strike", False),
    "goalkeeper catch": ("keeper_catch", False),
    "goalkeeper diving save": ("keeper_dive", False),          # left or right: measured
    "soccer header": ("header_jump", False),
    "header soccerball": ("header_stand", False),
    "header": ("header_glance", False),
    "soccer penalty kick": ("penalty_kick", False),
    "soccer tackle": ("slide_tackle_mx", False),
    "soccer trip": ("trip_fall", False),
    "step backward": ("step_back", False),
    "long step forward": ("step_forward_long", False),
    "left pivot": ("pivot_left", False),
    "idle": ("idle_mx", True),
    # common Mixamo names not in the first batch
    "tennis forehand": ("forehand_mx", False), "tennis backhand": ("backhand", False), "tennis serve": ("serve", False),
    "goalkeeper drop kick": ("keeper_punt", False), "soccer pass": ("pass_mx", False), "throw in": ("throw_in", False),
    "cheering": ("cheer", False), "fist pump": ("fist_pump", False), "knocked down": ("knockdown_2", False),
    "falling back death": ("fall_back_death", False), "getting up": ("stand_up_2", False),
}


def files_in(path):
    if os.path.isfile(path) and path.lower().endswith(".fbx"):
        return [path]
    if zipfile.is_zipfile(path):
        d = tempfile.mkdtemp(prefix="mixamo_")
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n.replace("\\", "/").split("/"):
                    sys.exit("unsafe path in zip: %s" % n)
            z.extractall(d)
        path = d
    return sorted(glob.glob(os.path.join(path, "**", "*.fbx"), recursive=True))


def base_name(f):
    b = os.path.splitext(os.path.basename(f))[0].lower()
    return re.sub(r"\s*\(\d+\)\s*$", "", b).strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="a folder or .zip of Mixamo .fbx files, or one .fbx")
    ap.add_argument("--library", required=True)
    a = ap.parse_args(argv)
    lib = os.path.abspath(os.path.expanduser(a.library))
    import check_motion as CM
    from sforge import rig
    used, rows, fails = set(), [], 0
    for f in files_in(a.src):
        b = base_name(f)
        name, loop = MOVES.get(b, ("mx_" + re.sub(r"[^a-z0-9]+", "_", b).strip("_"), "idle" in b))
        cmd = [sys.executable, os.path.join(HERE, "forge.py"), "motion", "import", "--library", lib, f, "--name", "zz_mixamo_import_tmp",
               "--loop" if loop else "--once", "--spdx", "LicenseRef-Mixamo", "--author", "Adobe Mixamo",
               "--source-url", "https://www.mixamo.com (%s)" % os.path.basename(f), "--redistribution", "no",
               "--notes", "Mixamo: free to use in games; the files may not be redistributed"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        tmp = os.path.join(lib, "zz_mixamo_import_tmp.json")
        if r.returncode or not os.path.isfile(tmp):
            rows.append((os.path.basename(f), "-", "import failed: %s" % (r.stderr or r.stdout).strip().splitlines()[-1:]))
            fails += 1
            continue
        rec = json.load(open(tmp))
        if name == "keeper_dive":
            # which way: the hips' sideways travel (+x is the figure's left)
            a0 = rig.evaluate(rec["keys"][0][1]).world["hips"][0, 3]
            a1 = rig.evaluate(rec["keys"][-1][1]).world["hips"][0, 3]
            name = "keeper_dive_left" if a1 > a0 else "keeper_dive_right"
        if name in used:
            k = 2
            while "%s_%d" % (name, k) in used:
                k += 1
            name = "%s_%d" % (name, k)
        used.add(name)
        rec["name"] = name
        out = os.path.join(lib, name + ".json")
        json.dump(rec, open(out, "w"))
        os.remove(tmp)
        res = CM.check_clip(rec, name)
        bad = [x for x in res if x[1] is False]
        fails += bool(bad)
        rows.append((os.path.basename(f), name, "ok" if not bad else "; ".join("%s: %s" % (x[0], x[2]) for x in bad)))
    for f, n, s in rows:
        print("%-40s -> %-22s %s" % (f[:40], n, s))
    print("\n%d files, %d with a problem. Build with --motion-library %s" % (len(rows), fails, lib))
    return 0


if __name__ == "__main__":
    sys.exit(main())
