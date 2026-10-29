#!/usr/bin/env python3
"""Game adapter: Sprite Forge output folder -> Egyptian Fighter / Padel Wars ("SF") fighter folder.

  python tools/export_ef.py out/<name> <game>/assets/char_<name> [--projectile ball]

Writes one horizontal strip per move (idle.png, walk.png, ... pyramid_blast.png = special_1,
bum_fireball.png = special_2), the game's own sprites.cfg grid format
(cell / baseline / stand_height / anim <state> <file> <frames> <frame_time>) and portrait.png.
Pure Pillow; the pixels are copied unchanged from moves/<move>_<NN>.png."""
import json, os, sys, argparse
from PIL import Image

EF_NAMES = {"special1": "pyramid_blast", "special_1": "pyramid_blast", "special2": "bum_fireball", "special_2": "bum_fireball", "jumpattack": "jump_attack"}
EF_STATES = ["idle", "walk", "crouch", "jump", "punch", "kick", "pyramid_blast", "bum_fireball",
             "block", "hit", "throw", "jump_attack", "taunt", "victory"]


def export(src, dst, projectile=None):
    js = json.load(open(os.path.join(src, "atlas.json")))
    meta, an = js["meta"], js["animations"]
    fw, fh, gy = meta["frame_w"], meta["frame_h"], meta["ground_y"]
    os.makedirs(dst, exist_ok=True)
    idle0 = Image.open(os.path.join(src, "moves", "idle_00.png"))
    bb = idle0.getchannel("A").getbbox()
    stand_h = (gy - bb[1]) if bb else int(fh * 0.62)
    lines = ["# exported from Sprite Forge Studio (%s) by tools/export_ef.py" % meta.get("name", ""),
             "cell %d %d" % (fw, fh), "baseline %d" % gy, "stand_height %d" % stand_h]
    done = []
    for mv, a in an.items():
        st = EF_NAMES.get(mv, mv)
        if st not in EF_STATES:
            continue
        n = a["count"]
        strip = Image.new("RGBA", (fw * n, fh), (0, 0, 0, 0))
        for i in range(n):
            strip.paste(Image.open(os.path.join(src, "moves", "%s_%02d.png" % (mv, i))), (i * fw, 0))
        strip.save(os.path.join(dst, st + ".png"))
        lines.append("anim %s %s.png %d %.3f" % (st, st, n, 1.0 / max(1, a["fps"])))
        done.append(st)
    if projectile:
        lines.append("projectile " + projectile)
    open(os.path.join(dst, "sprites.cfg"), "w").write("\n".join(lines) + "\n")
    if bb:   # portrait: upper part of the idle frame
        top = bb[1]; h = int((gy - top) * 0.55)
        cx = (bb[0] + bb[2]) // 2; w = int(h * 0.82)
        por = idle0.crop((cx - w // 2, top - 6, cx + w // 2, top - 6 + h))
        por.resize((268, int(268 * por.height / por.width)), Image.LANCZOS).save(os.path.join(dst, "portrait.png"))
    missing = [s for s in EF_STATES if s not in done]
    print("EF export -> %s : %d anims%s" % (dst, len(done), ("  (missing: %s - game falls back)" % ", ".join(missing)) if missing else ""))
    return done, missing


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--projectile", default=None)
    a = ap.parse_args()
    export(a.src, a.dst, a.projectile)
