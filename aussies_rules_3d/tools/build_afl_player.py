#!/usr/bin/env python3
"""Build the NEW AFL squad for Aussie Rules 3D (v10.2 pipeline, MakeHuman).

Same identities pipeline as Sprite Forge's gaelic_squad.py — the nine looks in
squad.txt are identity traits (skin, hair, build), nothing GAA-specific — but
the kits are baked as AFL guernseys (sleeveless cut, contrasting yoke, lace-up
collar) via the `sf_*@guernsey` kit styles, and the result is a NEW asset:

    public/assets/afl_player.glb   (never overwrites gaelic_player.glb)

Runtime does the club colours: guernsey.ts paints each club's stripes/hoops/sash
+ squad number at load time (chest/back projection), so the baked kit atlas is a
fallback only.

Requires the MakeHuman CC0 library, which downloads ~hundreds of MB from
files.makehumancommunity.org — NOT reachable from the CI/sandbox this repo's
tools are developed in. Run this on a machine with network access:

    python3 sprite_forge/forge.py human --setup --full     # one-time, needs network
    ../sfvenv/bin/python tools/build_afl_player.py --out tools/out            # build
    ../sfvenv/bin/python tools/build_afl_player.py --out tools/out --install  # + copy to public/assets

Output contract (same as gaelic_player.glb, gated by scripts/check.mjs):
single skin, 52 joints, 32 clips, v0_..v8_ look prefixes, kit garments suffixed.
"""
from __future__ import annotations
import argparse, io, json, os, re, shutil, sys, time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                  # aussies_rules_3d/
REPO = os.path.dirname(ROOT)                  # repo root
sys.path.insert(0, os.path.join(REPO, "sprite_forge"))

from sforge import mhlib, mhchar, glbpack, footballer as FB  # noqa: E402

GAME = os.path.join(REPO, "Gaelic_Football_3d")
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")
SQUAD = os.path.join(GAME, "assets", "source", "squad.txt")
GLB = os.path.join(ROOT, "public", "assets", "afl_player.glb")

# AFL guernsey kits: sleeveless cut + contrasting yoke + lace-up collar (fallback atlas only)
AFL_KITS = ("sf_blue@guernsey", "sf_red@guernsey")
AFL_HOME = AFL_KITS[0]


def read_squad(path):
    from sforge.appearance import Appearance
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


def main() -> int:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--out", default=os.path.join(HERE, "out"))
    ap_.add_argument("--squad", default=SQUAD)
    ap_.add_argument("--template", default=TEMPLATE)
    ap_.add_argument("--variants", type=int, default=0, help="only the first N looks (0 = all nine)")
    ap_.add_argument("--skin-res", type=int, default=1024)
    ap_.add_argument("--install", action="store_true", help="copy afl_player.glb to public/assets/")
    a = ap_.parse_args()
    os.makedirs(a.out, exist_ok=True)

    lib = mhlib.Library()
    if not lib.available():
        sys.stderr.write(
            "MakeHuman library missing. It downloads from files.makehumancommunity.org "
            "(not reachable from this repo's CI sandbox).\n"
            "Run on a networked machine:  python3 sprite_forge/forge.py human --setup --full\n"
        )
        return 2
    for p in (a.template, a.squad):
        if not os.path.isfile(p):
            sys.stderr.write("missing %s\n" % p)
            return 2

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

    # bake the fallback kit atlas with AFL guernsey paints (sleeveless + yoke + laces)
    for kit in AFL_KITS:
        im = None
        # reuse the FB paint machinery against the template's kit UV layout
        from sforge import gamemesh as GM  # noqa
        try:
            kits = mhchar.kit_textures(tm, [kit], lambda k: FB.paints(k))
        except Exception as e:      # kit-atlas baking unavailable for sf_ kits on this layout
            print("  kit bake skipped for %s (%s) — runtime paints guernseys anyway" % (kit, e))
            continue
        im = kits[kit]
        name = "kit_%s.png" % ("home" if kit == AFL_HOME else "away")
        im.save(os.path.join(a.out, name), optimize=True)
        if kit == AFL_HOME:
            bio = io.BytesIO(); im.save(bio, "PNG"); images["kit"] = bio.getvalue()

    if "kit" not in images:
        # minimal fallback atlas: solid club-neutral grey, replaced at runtime regardless
        tiny = io.BytesIO(); Image.new("RGB", (64, 64), (120, 120, 120)).save(tiny, "PNG")
        images["kit"] = tiny.getvalue()

    glb = os.path.join(a.out, "afl_player.glb")
    images = mhchar.engine_images(images)
    size = glbpack.pack_parts(a.template, glb, parts, images,
                              alpha_keys=("hair_", "eyebrows_", "eyelashes_", "facial_hair", "beard_shell"),
                              extras={"generator": "sprite_forge tools/build_afl_player.py",
                                      "variants": len(looks), "kit": "guernsey"})
    stats = {"variants": len(looks), "meshes": len(parts), "glb_bytes": size,
             "tris": int(sum(len(p.F) for p in parts)),
             "tris_per_player": int(sum(len(p.F) for p in parts) / max(1, len(looks))),
             "seconds": round(time.time() - t0, 1)}
    json.dump(stats, open(os.path.join(a.out, "afl_player_stats.json"), "w"), indent=1)
    print(json.dumps(stats))
    if a.install:
        shutil.copyfile(glb, GLB)
        print("installed -> %s (game prefers afl_player.glb at runtime)" % GLB)
    return 0


if __name__ == "__main__":
    sys.exit(main())
