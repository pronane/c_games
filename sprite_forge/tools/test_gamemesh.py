"""v10.1 game-mesh checks (CI): build the Gaelic Football player at a coarse grid and verify what an engine needs.

watertight + outward winding, triangle budget, < 65535 vertices (16-bit indices), unit normals, UVs in [0,1],
weights summing to 1 with valid joints (unused slots on joint 0), all template animations carried into the GLB,
and every kit texture baked."""
from __future__ import annotations
import json, os, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from sforge import footballer as FB, gamemesh as GM, glbpack  # noqa: E402

TEMPLATE = os.path.join(ROOT, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")


def main():
    fails = []
    sk = FB.Skeleton.from_glb(TEMPLATE)
    prims, paints = FB.design(sk, "home")
    hi, field = GM.surface(prims, h=0.008, log=lambda *a: None)
    lo = GM.decimate(hi, 12000)
    _, inv = np.unique(np.round(lo.V * 1e5).astype(np.int64), axis=0, return_inverse=True)
    Fw = inv.ravel()[lo.F]
    E = np.sort(np.concatenate([Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(E, axis=0, return_counts=True)
    if (cnt == 1).sum():
        fails.append("%d boundary edges (mesh not watertight)" % (cnt == 1).sum())
    if GM.signed_volume(lo.V, lo.F) <= 0:
        fails.append("winding points inward")
    J, W, _ = GM.weights(lo, prims, sk)
    m, vmap = GM.unwrap(lo, 512)
    J, W = J[vmap], W[vmap]
    if len(m.F) > 12500:
        fails.append("triangle budget exceeded: %d" % len(m.F))
    if len(m.V) >= 65535:
        fails.append("%d vertices need 32-bit indices" % len(m.V))
    if m.UV.min() < 0 or m.UV.max() > 1:
        fails.append("UVs outside [0,1]")
    if np.abs(W.sum(1) - 1).max() > 1e-3:
        fails.append("weights do not sum to 1")
    if J.max() >= len(sk.names) or ((W == 0) & (J != 0)).any():
        fails.append("bad joint indices")
    bd = GM.bake_prepare(m, prims, field, 256, log=lambda *a: None)
    for kit in FB.KITS:
        img = GM.bake(bd, prims, FB.paints(kit), 256)
        if not np.isfinite(img).all() or img.std() < 0.05:
            fails.append("kit %s bake looks empty" % kit)
    out = os.path.join(tempfile.mkdtemp(), "p.glb")
    glbpack.pack(TEMPLATE, out, m.V, m.N, m.UV, m.F, J, W, b"\x89PNG\r\n\x1a\n", name="t")
    j, buf = glbpack.read_glb(out)
    jt, _ = glbpack.read_glb(TEMPLATE)
    if len(j["animations"]) != len(jt["animations"]):
        fails.append("animations lost: %d of %d" % (len(j["animations"]), len(jt["animations"])))
    if len(j["skins"][0]["joints"]) != len(sk.names):
        fails.append("skin joints changed")
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]]
    bv = j["bufferViews"][acc["bufferView"]]
    N = np.frombuffer(buf[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]], np.float32).reshape(-1, 3)
    if np.abs(np.linalg.norm(N, axis=1) - 1).max() > 1e-3:
        fails.append("non-unit normals in the GLB")
    print(json.dumps({"tris": int(len(m.F)), "verts": int(len(m.V)), "clips": len(j["animations"])}))
    for f in fails:
        print("FAIL", f)
    print("%d problem(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
