#!/usr/bin/env python3
"""Install a Sprite Forge Studio kart-set build as a TurboTumble64 racer.

  python tools/export_tt64.py out/<name> <TurboTumble64>/assets/characters/<name> \
         --display "Nova Vance" [--tagline ...] [--weight medium] [--speed 3.5 ...]

The folder keeps the Studio layout (sprites.cfg, atlas.png, atlas.json, moves/, preview.png)
and the Studio character.ini gets a trailing [turbotumble64] block with the keys the game
reads (name, stats, kart colours, sprite, size, seat, portrait, anims = sprites.cfg).
TurboTumble64's loader skips '[section]' lines and the last value of a key wins, so ONE
character.ini serves both.  Also written: sprite.png (cropped idle frame = static fallback
for a game build without the Sprite Forge patch) and portrait.png (select-grid head shot).
"""
import argparse, configparser, os, shutil, sys
from PIL import Image


def hexrgb(v, dflt):
    v = (v or "").strip().lstrip("#")
    if len(v) == 6:
        return "%d,%d,%d" % tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return dflt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--display", default=None); ap.add_argument("--tagline", default="Forged in Sprite Forge Studio.")
    ap.add_argument("--weight", default="medium")
    for k, d in (("speed", 3.5), ("accel", 3.5), ("handling", 3.5), ("mass", 3.0), ("voice", 1.2), ("size", 2.4), ("seat", 0.0)):
        ap.add_argument("--" + k, type=float, default=d)
    ap.add_argument("--kart", default=None); ap.add_argument("--trim", default=None)
    a = ap.parse_args()
    src, dst = os.path.abspath(a.src), os.path.abspath(a.dst)
    if src != dst:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.glb", "*.fbx", "previews"))
    ini = configparser.ConfigParser(interpolation=None, strict=False); ini.optionxform = str
    ini.read(os.path.join(dst, "character.ini"))
    if ini.has_section("turbotumble64"):
        ini.remove_section("turbotumble64")
    ch = ini["character"]
    spec = ini["spec"] if ini.has_section("spec") else {}
    extra = ini["spec_extra"] if ini.has_section("spec_extra") else {}
    kart = a.kart or hexrgb(extra.get("kart_colour", ""), hexrgb(spec.get("shirt", ""), "220,60,60"))
    trim = a.trim or hexrgb(spec.get("trim", ""), "240,240,240")
    idle = Image.open(os.path.join(dst, "moves", "idle_00.png")).convert("RGBA")
    bb = idle.getchannel("A").getbbox()
    idle.crop(bb).save(os.path.join(dst, "sprite.png"))
    top = bb[1]; hh = int((bb[3] - bb[1]) * 0.45); cx = (bb[0] + bb[2]) // 2
    por = idle.crop((cx - hh // 2, top - 4, cx + hh // 2, top - 4 + hh))
    bg = Image.new("RGBA", por.size, (40, 46, 70, 255)); bg.alpha_composite(por)
    bg.resize((256, 256), Image.LANCZOS).save(os.path.join(dst, "portrait.png"))
    name = a.display or ch.get("name", os.path.basename(dst)).replace("_", " ").title()
    ini["turbotumble64"] = {
        "name": name, "tagline": a.tagline, "weight": a.weight,
        "speed": "%g" % a.speed, "accel": "%g" % a.accel, "handling": "%g" % a.handling, "mass": "%g" % a.mass,
        "kart": kart, "trim": trim, "voice": "%g" % a.voice,
        "sprite": "sprite.png", "angles": "1", "size": "%g" % a.size, "seat": "%g" % a.seat,
        "portrait": "portrait.png", "anims": "sprites.cfg"}
    with open(os.path.join(dst, "character.ini"), "w", encoding="utf-8") as f:
        f.write("; character.ini - Sprite Forge Studio + TurboTumble64 (the game reads the last [turbotumble64] block;\n"
                "; 'anims = sprites.cfg' needs the Sprite Forge driver patch, otherwise sprite.png is shown still)\n")
        ini.write(f, space_around_delimiters=True)
    print("TT64 racer '%s' -> %s" % (name, dst))


if __name__ == "__main__":
    sys.exit(main())
