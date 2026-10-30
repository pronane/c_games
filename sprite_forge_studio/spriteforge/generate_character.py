#!/usr/bin/env python3
"""
Print the 14 per-move sprite-sheet prompts for a new character (generalised from the
Padel Wars / Egyptian Fighter generate_character.py).

This script does NOT generate any images.  It prepares a source folder and prints one
prompt per move for you to run in an image tool of your choice with your OWN reference
photo, ideally of yourself or someone who has agreed to it.  Save each result into the
source folder under the printed file name, then build the sprites:

    python tools/spriteforge.py --name NAME --src sources/NAME --out assets/NAME

Usage:
    python generate_character.py --name "Dec" --desc "man in a navy suit and patterned tie"
    python generate_character.py --name "Flame" --desc "martial artist in a red gi" \\
        --style "16-bit arcade fighting game" --frames 6 --photo me.jpg --src sources
    python generate_character.py ... --json prompts.json      (also write them as JSON)
"""
import argparse, json, re, shutil
from pathlib import Path

# move id (= file name spriteforge.py looks for), what the strip shows
MOVES = [
    ("idle",       "idle fighting stance, subtle breathing and weight shift"),
    ("walk",       "walk cycle forward, natural alternating steps, a full stride"),
    ("crouch",     "going from standing into a low crouch, the last frames held low"),
    ("jump",       "vertical jump: crouch, take-off, tuck at the top, landing"),
    ("punch",      "straight punch: wind-up, full extension, recovery"),
    ("kick",       "high front kick: chamber, full extension, recovery"),
    ("special1",   "special attack 1 ({special1}), wind-up, release, recovery"),
    ("special2",   "special attack 2 ({special2}), wind-up, release, recovery"),
    ("block",      "guarding / blocking with forearms raised"),
    ("hit",        "being hit: recoiling backwards, stunned, recovering"),
    ("throw",      "grab and throw: reach, grab, turn and throw"),
    ("jumpattack", "airborne flying kick, as seen mid-air"),
    ("taunt",      "taunting the opponent, confident gesture"),
    ("victory",    "victory celebration, arms raised"),
]

RULES = ("Horizontal sprite strip of exactly {frames} separate full-body poses of the SAME "
         "{who}, left to right, evenly spaced with clear empty space between poses (poses must "
         "not touch or overlap). Full body visible head to feet in every pose, nothing cropped. "
         "Character faces RIGHT. Same scale and same camera distance in every pose, feet on one "
         "common floor line. Plain flat {bg} background (or transparent), no floor, no shadow, "
         "no text, no border. {style}")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "character"


def prompts(name, desc, frames=6, style="Photorealistic, matching the reference photo.",
            bg="light grey", special1="energy blast from the hands", special2="spinning attack"):
    who = f"person ({desc})" if desc else "person"
    if name:
        who = f"character {name}, {who}"
    out = []
    for mv, what in MOVES:
        what = what.format(special1=special1, special2=special2)
        p = (f"{frames} frames: {what}. " + RULES.format(frames=frames, who=who, bg=bg, style=style)
             + " Use the attached reference image for the face, body, hair and clothing.")
        out.append(dict(move=mv, file=f"{mv}.png", prompt=p))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="character name, e.g. Dec")
    ap.add_argument("--desc", default="", help="short look description (clothes, hair, props)")
    ap.add_argument("--style", default="Photorealistic, matching the reference photo.")
    ap.add_argument("--frames", type=int, default=6, help="poses per strip (default 6)")
    ap.add_argument("--bg", default="light grey", help="background colour to ask for (contrast with the clothes!)")
    ap.add_argument("--special1", default="energy blast from the hands")
    ap.add_argument("--special2", default="spinning attack")
    ap.add_argument("--photo", help="reference photo to copy into the source folder")
    ap.add_argument("--src", default="sources", help="parent folder for source images (default sources/)")
    ap.add_argument("--json", help="also write the prompts to this JSON file")
    a = ap.parse_args()

    folder = Path(a.src) / slug(a.name)
    folder.mkdir(parents=True, exist_ok=True)
    if a.photo:
        shutil.copy(a.photo, folder / ("reference" + Path(a.photo).suffix.lower()))
    ps = prompts(a.name, a.desc, a.frames, a.style, a.bg, a.special1, a.special2)
    print(f"Source folder: {folder}")
    print(f"Run these {len(ps)} prompts with your reference photo; save each result as the file name shown.\n")
    for i, p in enumerate(ps, 1):
        print(f"[{i:2d}/{len(ps)}] {folder / p['file']}")
        print(f"    {p['prompt']}\n")
    print("Missing a few? That's fine: spriteforge.py fills missing moves from the existing ones")
    print("(see the fallback table in README.md).  You can also drop per-frame PNGs into")
    print(f"{folder}/<move>/ or name them <move>_01.png, <move>_02.png ...\n")
    print("Then build:")
    print(f"    python tools/spriteforge.py --name {slug(a.name)} --src {folder} --out assets/{slug(a.name)}")
    if a.json:
        Path(a.json).write_text(json.dumps(dict(name=a.name, folder=str(folder), prompts=ps), indent=2))
        print(f"\nPrompts written to {a.json}")


if __name__ == "__main__":
    main()
