#!/usr/bin/env python3
"""Put a Sprite Forge fighter build into Egyptian Fighter's own sheet format.

    python tools/to_egyptian_fighter.py BUILD_DIR GAME_ASSETS/char_NAME [--projectile ball]

BUILD_DIR is the folder `forge.py build --profile fighter14 | library_fighter ... --strips` wrote (sprites.cfg in
Sprite Forge's "move" format + strips/<move>.png). Egyptian Fighter reads one strip per move and a sprites.cfg of
    cell W H / baseline Y / stand_height H / anim <state> <file> <frames> <seconds per frame>
(egyptian_fighter/src/player.c, LoadSpritesGrid). This copies the strips under the game's state names
(special1 -> pyramid_blast, special2 -> bum_fireball, jumpattack -> jump_attack) and writes that file.

For a character captured from a video (`forge.py capture`), the whole route is:
    forge.py library --library LIB add OUT/NAME.glb --name NAME --kind rig
    forge.py build --profile library_fighter --library LIB --rig NAME --set kit= --set clip_map= --name NAME \\
        --frame 624x800 --figure-h 560 --ground-y 788 --root-motion inplace --strips --out BUILD
    python tools/to_egyptian_fighter.py BUILD/NAME path/to/egyptian_fighter/assets/char_NAME
Render at the game's cell size (624x800, figure 560 px): the game draws fighters ~300 px tall at 720p and scales
the sheet down with mipmaps, so a 256 px build looks soft."""
from __future__ import annotations
import argparse
import os
import shutil
import sys

from PIL import Image

RENAME = {"special1": "pyramid_blast", "special2": "bum_fireball", "jumpattack": "jump_attack"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build"); ap.add_argument("out")
    ap.add_argument("--projectile", choices=["ball", "book", "card", "bubble", "fire", "fire_blue"])
    a = ap.parse_args(argv)
    # v11.5: a manifest-only folder still has the move list. A normal build already has sprites.cfg.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from sforge.gamemanifest import ensure_sprites_cfg
        ensure_sprites_cfg(a.build)
    except Exception:
        pass
    cfg = os.path.join(a.build, "sprites.cfg")
    frame = ground = height = None
    moves = []
    for line in open(cfg):
        t = line.split("#")[0].split()
        if not t:
            continue
        if t[0] == "frame":
            frame = (int(t[1]), int(t[2]))
        elif t[0] == "ground":
            ground = int(t[1])
        elif t[0] == "height":
            height = int(t[1])
        elif t[0] == "move":
            moves.append((t[1], int(t[3]), float(t[6]), int(t[7])))       # name, frames, fps, loop
    if not (frame and ground and height and moves):
        sys.exit("not a Sprite Forge fighter build: %s" % cfg)
    os.makedirs(a.out, exist_ok=True)
    L = ["# written by sprite_forge/tools/to_egyptian_fighter.py - uniform grid sheets",
         "cell %d %d" % frame, "baseline %d" % ground, "stand_height %d" % height]
    loops = []
    for name, n, fps, loop in moves:
        src = os.path.join(a.build, "strips", name + ".png")
        if not os.path.isfile(src):
            print("  ! no strip for %s (build with --strips)" % name); continue
        w, h = Image.open(src).size
        if w != n * frame[0] or h != frame[1]:
            print("  ! %s: strip is %dx%d, expected %dx%d - skipped" % (name, w, h, n * frame[0], frame[1])); continue
        state = RENAME.get(name, name)
        shutil.copy(src, os.path.join(a.out, state + ".png"))
        L.append("anim %s %s.png %d %.3f" % (state, state, n, 1.0 / max(1.0, fps)))
        if state == "victory":
            loops.append("loop victory %d" % max(0, n - 1))               # hold the last frame
    L += loops
    if a.projectile:
        L.append("projectile " + a.projectile)
    open(os.path.join(a.out, "sprites.cfg"), "w").write("\n".join(L) + "\n")
    pv = os.path.join(a.build, "moves", "idle_00.png")
    if os.path.isfile(pv):                                                # a portrait: the head and chest of idle
        im = Image.open(pv).convert("RGBA")
        box = im.getbbox()
        if box:
            w = box[2] - box[0]; top = box[1]
            s = int(max(w * 0.9, (box[3] - box[1]) * 0.3))
            cx = (box[0] + box[2]) // 2
            im.crop((cx - s // 2, top - s // 12, cx + s // 2, top - s // 12 + s)).resize((256, 256), Image.LANCZOS).save(
                os.path.join(a.out, "portrait.png"))
    print("wrote %s: %d moves, cell %dx%d, figure %d px" % (a.out, len(L) - 4 - len(loops) - bool(a.projectile), frame[0], frame[1], height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
