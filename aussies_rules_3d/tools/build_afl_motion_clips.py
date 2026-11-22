#!/usr/bin/env python3
"""Build the candidate AFL squad GLB: GAA player + 11 AFL clips, into a COPY.

Writes aussies_rules_3d/tools/out/gaelic_player.afl.glb — NEVER overwrites the
shipped public/assets/gaelic_player.glb. Run:

    ../sfvenv/bin/python tools/build_afl_motion_clips.py
"""
from __future__ import annotations
import json
import math
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(REPO, "sprite_forge"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import afl_motions  # noqa: E402

GLB = os.path.join(ROOT, "public", "assets", "gaelic_player.glb")
OUT_DIR = os.path.join(ROOT, "tools", "out")
OUT = os.path.join(OUT_DIR, "gaelic_player.afl.glb")


def main() -> int:
    afl_motions.register()
    failures = {n: e for n, e in afl_motions.qa_all().items() if e}
    if failures:
        print("QA failed:")
        for name, errs in failures.items():
            for e in errs:
                print("  %s: %s" % (name, e))
        return 1
    print("QA: %d clips pass" % len(afl_motions.AFL_CLIPS))

    from sforge import bonemap as BM, gltfread, retarget as RT, glbpack
    from sforge.rigrec import from_mannequin, strip_root_motion

    src = from_mannequin(name="afl_src", clips=list(afl_motions.AFL_CLIPS))
    tgt = gltfread.load(GLB)
    src_rec = BM.detect(src)
    tgt_rec = BM.detect(tgt)
    clips = {}
    for name in afl_motions.AFL_CLIPS:
        cl, rep = RT.retarget(src, src_rec, name, tgt, tgt_rec, root_motion="inplace", name=name)
        clips[name] = cl
        print("  %-26s %3d frames  dir err %.2f deg" % (name, cl.frames, rep.get("mean_dir_err_deg") or 0.0))

    os.makedirs(OUT_DIR, exist_ok=True)
    n = append_clips(GLB, OUT, tgt, clips)
    print("wrote %s (%.1f MB)" % (OUT, n / 1e6))

    # Round-trip the candidate: every required + new clip must load and bake.
    rig = gltfread.load(OUT)
    names = list(rig.clips)
    req = set(afl_motions.AFL_CLIPS)
    missing = req - set(names)
    if missing:
        print("FATAL: candidate is missing clips", sorted(missing))
        return 1
    for name in afl_motions.AFL_CLIPS:
        w = rig.clip_worlds(name)
        if not np.all(np.isfinite(w)):
            print("FATAL: non-finite world transforms in", name)
            return 1
    print("candidate round-trip OK: %d clips total" % len(names))
    return 0


def append_clips(glb_in, glb_out, rig, clips):
    """Append clips to a skinned GLB by BONE NAME (nodes are not in bone order).
    Mirrors sforge.officials.append_clips, keeping meshes/materials/images intact."""
    from sforge import glbpack
    from sforge.rigrec import strip_root_motion
    j, buf = glbpack.read_glb(glb_in)
    node_names = [nd.get("name") for nd in j["nodes"]]
    dst_index = {n: i for i, n in enumerate(node_names)}
    missing = [b for b in rig.bones if b not in dst_index]
    if missing:
        raise ValueError("GLB nodes do not cover bones: %s" % missing[:8])
    out = glbpack._Out()
    amap = {}

    def keep(i):
        if i not in amap:
            amap[i] = out.copy_acc(j, buf, i)
        return amap[i]

    meshes = []
    for m in j.get("meshes", []):
        prs = []
        for pr in m["primitives"]:
            p2 = dict(pr)
            p2["attributes"] = {k: keep(v) for k, v in pr["attributes"].items()}
            if "indices" in pr:
                p2["indices"] = keep(pr["indices"])
            p2.pop("targets", None)
            prs.append(p2)
        meshes.append(dict(m, primitives=prs))
    materials = j.get("materials", [])
    # Keep material references unchanged: material order preserved because we copy primitives as-is.
    skins = []
    for sk in j.get("skins", []):
        s2 = dict(sk)
        if "inverseBindMatrices" in sk:
            s2["inverseBindMatrices"] = keep(sk["inverseBindMatrices"])
        skins.append(s2)
    new = set(clips)
    anims = []
    for an in j.get("animations", []):
        if an.get("name") in new:
            continue  # replace
        sm = [{"input": keep(s["input"]), "output": keep(s["output"]),
               "interpolation": s.get("interpolation", "LINEAR")} for s in an["samplers"]]
        anims.append({"name": an.get("name", "anim"), "channels": an["channels"], "samplers": sm})
    hips = rig.meta.get("hips_index", 0)
    for cn, c in clips.items():
        t = (np.arange(c.frames) / c.fps).astype(np.float32)
        ta = out.add(t, 5126, "SCALAR", minmax=True)
        T = strip_root_motion(rig, c) if c.T is not None else c.T
        ch, sm = [], []
        for i in range(rig.nb):
            node = dst_index[rig.bones[i]]
            sm.append({"input": ta, "output": out.add(c.R[:, i].astype(np.float32), 5126, "VEC4"),
                       "interpolation": "LINEAR"})
            ch.append({"sampler": len(sm) - 1, "target": {"node": node, "path": "rotation"}})
            if i == hips or rig.parent[i] < 0:
                sm.append({"input": ta, "output": out.add(T[:, i].astype(np.float32), 5126, "VEC3"),
                           "interpolation": "LINEAR"})
                ch.append({"sampler": len(sm) - 1, "target": {"node": node, "path": "translation"}})
        anims.append({"name": cn, "channels": ch, "samplers": sm})
    imgs = []
    for im in j.get("images", []):
        im2 = dict(im)
        if "bufferView" in im:
            bv = j["bufferViews"][im["bufferView"]]
            o = bv.get("byteOffset", 0)
            im2["bufferView"] = out.view(bytes(buf[o:o + bv["byteLength"]]))
        imgs.append(im2)
    gl = dict(j)
    gl.update({"meshes": meshes, "skins": skins, "animations": anims,
               "accessors": out.acc, "bufferViews": out.views,
               "buffers": [{"byteLength": 0}]})
    if imgs:
        gl["images"] = imgs
    from sforge import officials as _officials
    return _officials._write(gl, out.b, glb_out)


if __name__ == "__main__":
    sys.exit(main())
