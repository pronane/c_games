"""Build the Gaelic Football 3D player with Sprite Forge (v10.1): sculpted footballer fitted to the game skeleton,
one watertight mesh, polygon budget, UVs, skin weights, baked kit textures, packed into the game's GLB.

    python3 tools/gaelic_forge.py --out /tmp/gf_forge [--tris 22000] [--install]

Reads the skeleton + 32 animation clips from Gaelic_Football_3d/assets/models/gaelic_player.glb (kept unchanged) and
writes <out>/gaelic_player.glb + <out>/kit_<name>.png (home, away, gk_home, gk_away, referee, umpire)."""
from __future__ import annotations
import argparse, io, json, os, shutil, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sforge import footballer as FB, gamemesh as GM, glbpack  # noqa: E402

GAME = os.path.abspath(os.path.join(HERE, "..", "..", "Gaelic_Football_3d"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=os.path.join(GAME, "assets", "models", "gaelic_player.glb"))
    ap.add_argument("--tris", type=int, default=22000)
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--h", type=float, default=0.0045, help="sculpt grid step (m)")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    T = {}
    t0 = time.time()
    tmpl = a.template
    if os.path.abspath(tmpl) == os.path.abspath(os.path.join(GAME, "assets", "models", "gaelic_player.glb")):
        # never read our own output back as the template: keep a pristine copy of the shipped skeleton + clips
        keep = os.path.join(a.out, "_template.glb")
        if not os.path.exists(keep):
            shutil.copyfile(tmpl, keep)
        tmpl = keep
    sk = FB.Skeleton.from_glb(tmpl)
    prims, paints = FB.design(sk, "home")
    print("design: %d shapes on %d joints" % (len(prims), len(sk.names)))
    hi, field = GM.surface(prims, h=a.h); T["surface"] = time.time() - t0
    t = time.time(); lo = GM.decimate(hi, a.tris); T["decimate"] = time.time() - t
    print("  decimate: %d -> %d tris" % (len(hi.F), len(lo.F)))
    # weights on the welded mesh, THEN split at UV seams: seam copies must carry identical weights or they crack
    t = time.time(); J0, W0, _ = GM.weights(lo, prims, sk); T["weights"] = time.time() - t
    t = time.time(); uvm, vmap = GM.unwrap(lo, a.res); T["unwrap"] = time.time() - t
    J, W = J0[vmap], W0[vmap]
    print("  unwrap: %d verts (%d before seams)" % (len(uvm.V), len(lo.V)))
    t = time.time(); bd = GM.bake_prepare(uvm, prims, field, a.res); T["bake_prep"] = time.time() - t
    t = time.time()
    pngs = {}
    for kit in FB.KITS:
        img = GM.bake(bd, prims, FB.paints(kit), a.res)
        im = Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")
        im.save(os.path.join(a.out, "kit_%s.png" % kit), optimize=True)
        bio = io.BytesIO(); im.save(bio, "PNG", optimize=True); pngs[kit] = bio.getvalue()
    T["bake_kits"] = time.time() - t
    size = glbpack.pack(tmpl, os.path.join(a.out, "gaelic_player.glb"), uvm.V, uvm.N, uvm.UV, uvm.F, J, W, pngs["home"],
                        name="gaelic_footballer", extras={"generator": "sprite_forge tools/gaelic_forge.py",
                                                          "tris": int(len(uvm.F)), "verts": int(len(uvm.V))})
    T["total"] = time.time() - t0
    stats = {"tris": int(len(uvm.F)), "verts": int(len(uvm.V)), "glb_bytes": size, "hi_tris": int(len(hi.F)),
             "max_influences": int((W > 0).sum(1).max()), "mean_influences": float((W > 0).sum(1).mean()),
             "uv_coverage": float(len(bd.P)) / (a.res * a.res), "seconds": {k: round(v, 1) for k, v in T.items()}}
    json.dump(stats, open(os.path.join(a.out, "stats.json"), "w"), indent=1)
    np.savez_compressed(os.path.join(a.out, "mesh.npz"), V=uvm.V, F=uvm.F, N=uvm.N, UV=uvm.UV, J=J, W=W)
    print(json.dumps(stats))
    if a.install:
        shutil.copyfile(os.path.join(a.out, "gaelic_player.glb"), os.path.join(GAME, "assets", "models", "gaelic_player.glb"))
        for kit in FB.KITS:
            shutil.copyfile(os.path.join(a.out, "kit_%s.png" % kit), os.path.join(GAME, "assets", "textures", "kit_%s.png" % kit))
        print("installed into", GAME)


if __name__ == "__main__":
    main()
