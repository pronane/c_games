#!/usr/bin/env python3
"""v11.34: FBX motion capture -> Sprite Forge moves (any skeleton Godot can read).

    GODOT=/path/to/godot python tools/fbx_to_moves.py OUT a.fbx b.fbx ... [--fps 30] [--licence JSON]

Godot 4.3+ reads the FBX (tools/fbx_dump.gd samples named joints in world space), then the
joints are fitted onto the shared skeleton with the same IK as every other mocap source
(sforge.jointtrack).  Leading T-pose frames (a bind pose many exporters put on frame 0) are
dropped.  Writes one move per file plus _import.json; long takes are kept whole - a game cuts
them into its own moves.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sforge import jointtrack as JT  # noqa: E402


def dump(fbx_paths, out_dir, godot=None):
    godot = godot or os.environ.get("GODOT", "godot")
    with tempfile.TemporaryDirectory() as proj:
        with open(os.path.join(proj, "project.godot"), "w") as f:
            f.write('config_version=5\n[application]\nconfig/name="fbx_dump"\n')
        subprocess.run([godot, "--headless", "--path", proj, "--script", os.path.join(HERE, "fbx_dump.gd"), "--", out_dir]
                       + [os.path.abspath(p) for p in fbx_paths], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tracks(path):
    """dumped joints -> (frames for jointtrack.fit_tracks, fps, frames skipped).  Ears come from the
    head and the shoulder line; leading T-pose frames are dropped."""
    d = json.load(open(path))
    fr = d["frames"]
    k = 0
    while k < len(fr) - 1 and all(abs(fr[k][w][1] - fr[k][s][1]) < .03 for w, s in (("lWrist", "lShoulder"), ("rWrist", "rShoulder"))):
        k += 1
    out = []
    for f in fr[k:]:
        g = dict(f)
        n = np.array(f["nose"]); sh = np.array(f["lShoulder"]) - np.array(f["rShoulder"]); sh /= np.linalg.norm(sh) + 1e-9
        g["lEar"] = list(n + .08 * sh); g["rEar"] = list(n - .08 * sh)
        out.append(g)
    return out, float(d["fps"]), k


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out"); ap.add_argument("fbx", nargs="+")
    ap.add_argument("--licence", default="{}", help="licence record (JSON) written into every move")
    ap.add_argument("--prefix", default="fbx")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    lic = json.loads(a.licence)
    with tempfile.TemporaryDirectory() as tmp:
        dump(a.fbx, tmp)
        index = dict(source="sforge fbx_to_moves", licence=lic, takes=[])
        for p in sorted(os.listdir(tmp)):
            fr, fps, skipped = tracks(os.path.join(tmp, p))
            keys, rep = JT.fit_tracks(fr, fps=fps, up="y")
            name = "%s_%s" % (a.prefix, os.path.splitext(p)[0].lower())
            rec = JT.keys_record(name, keys, rep, lic, category="Mocap", source="fbx:" + p[:-5], desc=p[:-5].replace("_", " "))
            rec["import"]["frames_skipped"] = skipped
            json.dump(rec, open(os.path.join(a.out, name + ".json"), "w"), indent=0)
            index["takes"].append(dict(name=name, file=p[:-5], duration=rep["duration"], fit_err_deg=rep["mean_bone_err_deg"]))
            print("  %-40s %5.1fs  fit %.1f deg" % (name, rep["duration"], rep["mean_bone_err_deg"]))
        json.dump(index, open(os.path.join(a.out, "_import.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
