#!/usr/bin/env python3
"""Build a LOCAL, non-shipping Gaelic jog candidate from one CMU BVH take.

Requires Sprite Forge's optional numpy/scipy/Pillow dependencies. Input is
provided by the caller; this script does not download or install assets, and
never overwrites the shipped player. See shared/arena_motion/RESEARCH.md.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "Gaelic_Football_3d"
sys.path.insert(0, str(ROOT / "sprite_forge"))

EXPECTED_SHA256 = "d20d54a9ccebd7aaf4aa6c4d7662c4905d47009401895de216a914edecf287be"
LICENCE = {
    "spdx": "custom",
    "custom_text": "CMU data may be used in research and commercial products, but may not be resold directly, even converted.",
    "author": "Carnegie Mellon University Graphics Lab",
    "source_url": "http://mocap.cs.cmu.edu/",
    "redistribution": "yes",
    "attribution": "The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.",
    "notes": "B. Hahne cgspeed BVH conversion; meshula/cmu-mocap mirror, commit 09a07f54f3bbb58797325f009282d0b2048a2871.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bvh", type=Path, help="the exact CMU 16_35 BVH from the documented mirror")
    parser.add_argument("out", type=Path, help="new local output directory; must not exist")
    args = parser.parse_args()
    bvh = args.bvh.resolve()
    out = args.out.resolve()
    if hashlib.sha256(bvh.read_bytes()).hexdigest() != EXPECTED_SHA256:
        parser.error("input is not the expected CMU 16_35 BVH (SHA-256 mismatch)")
    forbidden = (GAME / "assets", ROOT / "arena-fc")
    if out == ROOT or out == GAME or any(out == p or p in out.parents for p in forbidden):
        parser.error("output must be outside game assets and arena-fc")
    out.mkdir(parents=True, exist_ok=False)

    from sforge import motionlib, rigrec
    from sforge.gaelic_clip import read_glb, inspect_animation

    lib = out / "motion_library"
    lib.mkdir()
    rec, _, problems = motionlib.import_file(
        str(bvh), name="cmu_jog_16_35", library=str(lib), licence=LICENCE,
        loop=True, cycle=True, category="Locomotion")
    if problems:
        raise RuntimeError("licence metadata validation: " + str(problems))
    target = GAME / "assets/source/makehuman_template.glb"
    rig, clip, report = motionlib.retarget_motion(
        "cmu_jog_16_35", str(target), path=str(lib), root_motion="inplace",
        plant=False, out_name="cmu_jog")
    clip_file = out / "cmu_jog.glb"
    rigrec.write_glb(rig, str(clip_file), [clip.name], root_motion="inplace")
    doc, buf = read_glb(str(clip_file))
    animation = next(a for a in doc["animations"] if a.get("name") == "cmu_jog")
    errors, info = inspect_animation(doc, buf, animation)
    span = info.get("pelvis", {}).get("xz_span_m", [])
    if errors or len(span) != 2 or max(span) > .01:
        raise RuntimeError(f"candidate clip is invalid or contains horizontal root travel: {errors} {info}")
    subprocess.run([
        sys.executable, "-m", "sforge.gaelic_clip", "merge",
        str(GAME / "assets/models/gaelic_player.glb"), str(clip_file),
        "--source", "cmu_jog", "--name", "jog", "--replace-clip",
        "--out", str(out / "candidate"),
        "--parts", str(GAME / "assets/models/gaelic_player.parts"),
        "--textures", str(GAME / "assets/textures"),
    ], check=True, env={**os.environ, "PYTHONPATH": str(ROOT / "sprite_forge") + os.pathsep + os.environ.get("PYTHONPATH", "")})
    result = {
        "purpose": "experimental local candidate, not installed or visually approved",
        "take": "16_35", "bvh_sha256": EXPECTED_SHA256, "licence": LICENCE,
        "import": rec["import"], "retarget": report, "root_motion": "inplace",
        "runtime_replaced_clip": "jog", "clip_validation": info,
    }
    (out / "research-provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Candidate:", out / "candidate/gaelic_player.glb")
    print("Not a production asset: inspect movement, contact, skinning, rights and provenance before use.")


if __name__ == "__main__":
    main()
