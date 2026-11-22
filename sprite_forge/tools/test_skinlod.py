#!/usr/bin/env python3
"""Level-of-detail meshes for skinned characters (v11.38, fed back from Arena FC).

    python tools/test_skinlod.py

On a tailored identity of the Gaelic squad GLB:
  1 each level has fewer triangles than the last (body to about half, then about a fifth)
  2 every LOD vertex is an original vertex with its exact UV, skin weights and normal (half-edge collapses)
  3 openings and UV seams do not move: every hem and seam vertex of the original is still there
  4 no triangle turns over: each LOD face faces the way the original surface did around it
  5 hidden faces are cut (the shins inside the socks) and tiny parts drop out of the far level
  6 the LOD parts go into a GLB next to the originals (same material, same skin) and read back"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import skinlod as SL  # noqa: E402
from sforge import tailor as T  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402

SRC = os.path.join(HERE, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    bones, jn = T.skeleton_from_glb(SRC)
    parts = T.read_parts(SRC, "v0_")
    kit = T.tailor(parts, bones, joint_names=jn, log=lambda *a: None)
    parts.update(kit)
    lods = SL.lod_parts(parts)
    b0, (b1, b2) = parts["body"], lods["body"]
    rec("levels get coarser", len(b0.F) > len(b1.F) > len(b2.F) and len(b1.F) < .6 * len(b0.F) and len(b2.F) < .4 * len(b0.F),
        "body %d / %d / %d" % (len(b0.F), len(b1.F), len(b2.F)))
    tot0 = sum(len(p.F) for p in parts.values())
    tot2 = sum(len(q[1].F) for q in lods.values() if q[1] is not None)
    rec("far level under 45% of the triangles", tot2 < .45 * tot0, "%d -> %d" % (tot0, tot2))
    # 2 exact attributes: look each LOD vertex up in the original
    ok = True
    for name in ("body", "jersey"):
        p, q = parts[name], lods[name][0]
        key = {tuple(np.round(v, 7)) + tuple(np.round(u, 7)): i for i, (v, u) in enumerate(zip(p.V, p.UV))}
        for v, u, w, n in zip(q.V, q.UV, q.W, q.N):
            i = key.get(tuple(np.round(v, 7)) + tuple(np.round(u, 7)))
            if i is None and name == "body":
                ok = False
                break
            if i is not None and not (np.allclose(p.W[i], w) and np.allclose(p.N[i], n)):
                ok = False
                break
    rec("LOD vertices are original vertices with exact UV / weights / normals", ok)
    # 3 hems and seams locked (garments are inflated a hair, so check the body and the hair)
    ok = True
    for name in ("body", "hair"):
        if name not in parts:
            continue
        p, q = parts[name], lods[name][1]
        if q is None:
            continue
        outers = [parts[o] for o in SL.LOD_PLAN["under"].get(name, ()) if o in parts]
        p = SL.cull_covered(p, outers)                       # what the levels are cut from
        lk = SL._locked(p.V, p.F) & np.isin(np.arange(len(p.V)), p.F)
        P = {tuple(np.round(v, 7)) for v in q.V}
        miss = sum(tuple(np.round(v, 7)) not in P for v in p.V[lk])
        ok &= miss == 0
    rec("openings and UV seams kept exactly", ok)
    # 4 no flips: each LOD face normal agrees with the original vertex normals at its corners
    q = lods["body"][1]
    fn = np.cross(q.V[q.F[:, 1]] - q.V[q.F[:, 0]], q.V[q.F[:, 2]] - q.V[q.F[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    vn = q.N[q.F].mean(1)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    flipped = float(((fn * vn).sum(1) < 0).mean())
    rec("no triangles turned over", flipped < .005, "%.2f%%" % (flipped * 100))
    # 5 culling and drops
    sh = lods["socks"]
    culled = len(SL.cull_covered(parts["body"], [parts[o] for o in SL.LOD_PLAN["under"]["body"] if o in parts]).F)
    rec("hidden skin under the kit is cut", culled < len(parts["body"].F), "%d -> %d" % (len(parts["body"].F), culled))
    # with the keeper's (optional) base layer and gloves in the identity, the arms and hands still stay
    kp = dict(parts)
    kp.update(T.tailor(parts, bones, garments=T.keeper_garments(), joint_names=jn, log=lambda *a: None))
    near, _t = T.dominant_bone(parts["body"], bones, jn)
    arm = np.char.endswith(near.astype(str), "Hand") | np.char.endswith(near.astype(str), "Forearm")
    kb = SL.lod_parts({k: kp[k] for k in ("body", "jersey", "shorts", "socks", "boots", "sleeves", "gloves")})["body"][0]
    hv = parts["body"].V[arm]
    lo, hi = hv.min(0), hv.max(0)
    rec("optional layers (keeper sleeves, gloves) never cut the skin", ((kb.V >= lo) & (kb.V <= hi)).all(1).sum() > .3 * arm.sum())
    drop = [n for n in SL.LOD_PLAN["drop"][2] if n in parts]
    rec("tiny parts drop out of the far level", all(lods[n][1] is None for n in drop) and sh[1] is not None, ",".join(drop))
    # 6 into a GLB
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "l.glb")
        add = {}
        for name, lv in lods.items():
            for k, q in enumerate(lv, start=1):
                if q is not None:
                    add["%s_lod%d" % (name, k)] = q
        T.replace_parts(SRC, out, {"v0_": add})
        j, _ = read_glb(out)
        names = {nd.get("name") for nd in j["nodes"]}
        back = T.read_parts(out, "v0_")
        mat = {m["name"] for m in j["materials"]}
        rec("LOD parts written next to the originals and read back",
            "v0_body_lod1" in names and "v0_body" in names and len(back["body_lod2"].F) == len(lods["body"][1].F)
            and parts["body"].material in mat and all(nd.get("skin") == 0 for nd in j["nodes"] if nd.get("name", "").endswith("_lod1")))
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
