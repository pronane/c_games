#!/usr/bin/env python3
"""Add CC0 game moves from Quaternius' Universal Animation Library 1 and 2 to a motion library (v11.11).

    python tools/import_quaternius.py --library ~/sprite_forge_motions [--zip-dir DIR]

Downloads the two free "Standard" packs from OpenGameArt (or uses the zips you put in --zip-dir), then imports the
moves below with `forge.py motion import`, onto the shared skeleton. Each clip was looked at and passes
tools/check_motion.py; clips that did not import cleanly are left out (UAL2's Hit_Knockback ends upside down, its
LayToIdle runs standing to lying, its Melee_Hook breaks mid-swing; UAL1's Hit_Head / Hit_Chest are too small to
read as hits at sprite size).

Licence: CC0 1.0 (public domain) - "Models by @Quaternius" (quaternius.com). Free for any use, commercial
included; these clips may be shipped. Credit is not required but is kept in each clip's licence record."""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = {
    "ual1": ("https://opengameart.org/sites/default/files/universal_animation_librarystandard.zip",
             "Godot/AnimationLibrary_Godot_Standard.glb"),
    "ual2": ("https://opengameart.org/sites/default/files/universal_animation_library_2standard.zip",
             "Unreal-Godot/UAL2_Standard.glb"),
}
# name, pack, clip, options
TAKES = [
    ("death_fall", "ual1", "Death01", ["--once"]),
    ("roll", "ual1", "Roll", ["--once"]),
    ("sprint", "ual1", "Sprint_Loop", ["--loop"]),
    ("drive_seated", "ual1", "Driving_Loop", ["--loop"]),
    ("pistol_shoot", "ual1", "Pistol_Shoot", ["--once"]),
    ("pistol_reload", "ual1", "Pistol_Reload", ["--once"]),
    ("cast_spell", "ual1", "Spell_Simple_Shoot", ["--once"]),
    ("dance", "ual1", "Dance_Loop", ["--loop"]),
    ("slide_tackle", "ual2", "Slide_Start", ["--once"]),
    ("throw_overhand_q", "ual2", "OverhandThrow", ["--once"]),
    ("idle_arms_folded", "ual2", "Idle_FoldArms_Loop", ["--loop"]),
]


def fetch(zdir):
    os.makedirs(zdir, exist_ok=True)
    out = {}
    for key, (url, inner) in PACKS.items():
        z = os.path.join(zdir, os.path.basename(url))
        if not os.path.isfile(z):
            print("downloading", url)
            urllib.request.urlretrieve(url, z)
        dest = os.path.join(zdir, key)
        with zipfile.ZipFile(z) as zf:
            names = [n for n in zf.namelist() if n.replace("\\", "/").endswith(inner)]
            if not names:
                sys.exit("%s: %s not found in the zip" % (z, inner))
            zf.extract(names[0], dest)
            out[key] = os.path.join(dest, names[0])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, help="motion library folder to add the clips to")
    ap.add_argument("--zip-dir", help="where the downloaded zips are kept (default: <library>/_quaternius)")
    ap.add_argument("--only", nargs="*", help="import just these move names")
    a = ap.parse_args(argv)
    lib = os.path.abspath(os.path.expanduser(a.library))
    files = fetch(os.path.abspath(os.path.expanduser(a.zip_dir or os.path.join(lib, "_quaternius"))))
    bad = 0
    todo = [t for t in TAKES if not a.only or t[0] in a.only]
    for name, pack, clip, opts in todo:
        cmd = [sys.executable, os.path.join(HERE, "forge.py"), "motion", "import", "--library", lib, files[pack],
               "--clip", clip, "--name", name, "--spdx", "CC0-1.0", "--author", "Quaternius",
               "--source-url", "https://quaternius.com (Universal Animation Library %s: %s)" % (pack[-1], clip),
               "--redistribution", "yes", "--attribution", "Animations by @Quaternius (CC0)"] + opts
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]
        print("%-18s %s" % (name, line[0][:110] if line else "?"))
        bad += r.returncode != 0
    print("\n%d moves in %s. Build with --motion-library %s" % (len(todo) - bad, lib, lib))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
