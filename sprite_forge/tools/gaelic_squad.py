"""Build the Gaelic Football squad (v10.2): realistic MakeHuman footballers with different looks, one GLB.

    python3 tools/gaelic_squad.py --out /tmp/squad [--install]

Reads Gaelic_Football_3d/assets/source/squad.txt (one [variant] block of appearance keys per look) and the
MakeHuman template Gaelic_Football_3d/assets/source/makehuman_template.glb (the game's rigged MakeHuman player:
skeleton + 32 clips).  Writes <out>/gaelic_player.glb (every variant's body, kit garments, hair, brows, lashes and
eyes on the shared skeleton + clips), <out>/gaelic_player.parts (mesh index -> variant + role, read by the game)
and <out>/kit_<name>.png (kit atlases: left half jersey / socks / boots, right half shorts).
Needs the MakeHuman library: python3 forge.py human --setup --full"""
from __future__ import annotations
import argparse, io, json, os, re, shutil, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sforge import mhlib, mhchar, glbpack, footballer as FB  # noqa: E402
from sforge.appearance import Appearance  # noqa: E402

GAME = os.path.abspath(os.path.join(HERE, "..", "..", "Gaelic_Football_3d"))
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")
SQUAD = os.path.join(GAME, "assets", "source", "squad.txt")


def read_squad(path):
    vs, cur = [], None
    for ln in open(path, encoding="utf-8"):
        s = re.split(r"\s#\s", ln.rstrip("\n"), maxsplit=1)[0].strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[(.+?)\]", s)
        if m:
            cur = Appearance(); vs.append(cur); continue
        if "=" in s and cur is not None:
            k, v = [x.strip() for x in s.split("=", 1)]
            cur.set(k, v)
    return vs


def make_template(src_glb, out):
    """strip a rigged MakeHuman player GLB to mesh 0 + skeleton + clips (no textures, no eye mesh)"""
    j, b = glbpack.read_glb(src_glb)
    pr = j["meshes"][0]["primitives"][0]; a = pr["attributes"]
    acc = lambda i: mhchar._acc(j, b, i)
    V = acc(a["POSITION"]); N = acc(a["NORMAL"]); UV = acc(a["TEXCOORD_0"]); F = acc(pr["indices"]).reshape(-1, 3)
    J = acc(a["JOINTS_0"]); W = acc(a["WEIGHTS_0"])
    tiny = io.BytesIO(); Image.new("RGB", (1, 1), (200, 160, 140)).save(tiny, "PNG")
    return glbpack.pack(src_glb, out, V, N, UV, F, J, W, tiny.getvalue(), name="makehuman_template",
                        extras={"source": "MakeHuman (CC0) player of Gaelic Football 3D v3.2: mesh + 52-bone skeleton + 32 clips"})


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--out", required=True)
    ap_.add_argument("--squad", default=SQUAD)
    ap_.add_argument("--template", default=TEMPLATE)
    ap_.add_argument("--variants", type=int, default=0, help="only the first N variants (0 = all)")
    ap_.add_argument("--skin-res", type=int, default=1024)
    ap_.add_argument("--install", action="store_true")
    a = ap_.parse_args()
    os.makedirs(a.out, exist_ok=True)
    lib = mhlib.Library()
    if not lib.available():
        print("MakeHuman library missing: python3 forge.py human --setup --full"); return 2
    t0 = time.time()
    tm = mhchar.Template.load(a.template, lib)
    looks = read_squad(a.squad)
    if a.variants:
        looks = looks[:a.variants]
    parts, images, table = [], {}, []
    for v, ap in enumerate(looks):
        ch = mhchar.build(tm, ap, lib, name="v%d" % v, skin_res=a.skin_res)
        for p in ch.parts:
            key = p.image
            if key == "skin":
                key = "skin_v%d" % v
            p.image = key
            parts.append(p); table.append((len(parts) - 1, v, p.role))
        for k, png in ch.images.items():
            images["skin_v%d" % v if k == "skin" else k] = png
        print("  variant %d: %s, %s hair, %s" % (v, ap.skin, ap.hair_style, ap.facial_hair))
    kits = mhchar.kit_textures(tm, list(FB.KITS), lambda k: FB.paints(k))
    for k, im in kits.items():
        im.save(os.path.join(a.out, "kit_%s.png" % k), optimize=True)
    bio = io.BytesIO(); kits["home"].save(bio, "PNG"); images["kit"] = bio.getvalue()
    glb = os.path.join(a.out, "gaelic_player.glb")
    size = glbpack.pack_parts(a.template, glb, parts, images, alpha_keys=("hair_", "eyebrows_", "eyelashes_", "facial_hair"),
                              extras={"generator": "sprite_forge tools/gaelic_squad.py", "variants": len(looks)})
    with open(os.path.join(a.out, "gaelic_player.parts"), "w") as f:
        f.write("# mesh variant role  (Sprite Forge squad; roles: body kit hair brows lashes eyes)\n")
        for i, v, r in table:
            f.write("%d %d %s\n" % (i, v, r))
    stats = {"variants": len(looks), "meshes": len(parts), "glb_bytes": size, "tris": int(sum(len(p.F) for p in parts)),
             "tris_per_player": int(sum(len(p.F) for p in parts) / max(1, len(looks))), "seconds": round(time.time() - t0, 1)}
    json.dump(stats, open(os.path.join(a.out, "stats.json"), "w"), indent=1)
    print(json.dumps(stats))
    if a.install:
        shutil.copyfile(glb, os.path.join(GAME, "assets", "models", "gaelic_player.glb"))
        shutil.copyfile(os.path.join(a.out, "gaelic_player.parts"), os.path.join(GAME, "assets", "models", "gaelic_player.parts"))
        for k in FB.KITS:
            shutil.copyfile(os.path.join(a.out, "kit_%s.png" % k), os.path.join(GAME, "assets", "textures", "kit_%s.png" % k))
        print("installed into", GAME)


if __name__ == "__main__":
    sys.exit(main())
