#!/usr/bin/env python3
"""
Generate HD sprite sheets for a new character from a source photo.
Usage: python generate_character.py --name "My Name" --folder char_myname --photo path/to/photo.jpg

This prepares the folder and prints prompts for all 14 required sheets.
Generate each sheet with a reference-image model, then drop the PNGs into assets/<folder>/.
All sheets must be horizontal strips of exactly 6 frames, transparent background, feet aligned at bottom.
"""
import argparse, shutil
from pathlib import Path

SHEETS = [
    ("idle.png",          "6 idle frames, subtle breathing and weight shift"),
    ("walk.png",          "6 walk cycle frames, natural walking"),
    ("crouch.png",        "6 crouch frames, progressive crouch"),
    ("jump.png",          "6 jump frames, jump up and land"),
    ("punch.png",         "6 punch frames, progressive punch"),
    ("kick.png",          "6 kick frames, progressive kick"),
    ("pyramid_blast.png", "6 special attack frames"),
    ("bum_fireball.png",  "6 special frames, turn and fireball"),
    ("block.png",         "6 block frames"),
    ("hit.png",           "6 hit/stun frames, recoiling"),
    ("throw.png",         "6 throw frames"),
    ("jump_attack.png",   "6 jump attack frames"),
    ("taunt.png",         "6 taunt frames"),
    ("victory.png",       "6 victory pose frames"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--assets", default="assets")
    args = ap.parse_args()

    dest = Path(args.assets) / args.folder
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.photo, dest / "reference.png")
    print(f"Created {dest}")
    print("Generate these 14 sheets (exactly 6 frames each, transparent, feet aligned):")
    for sheet, desc in SHEETS:
        print(f"\n{sheet}: {desc}")
        print(f"  Prompt: Horizontal sprite sheet of {desc} of this exact person. Transparent background. Facing right. Consistent scale. Realistic photo quality matching reference.")
    print(f"\nDrop finished PNGs into {dest}/")
    print(f"Add to game.c:")
    print(f'  g->characters[N] = (CharacterDef){{ "{args.name}", "{args.folder}", "assets/stages/street.png", "assets/portraits/{args.folder}.png" }};')

if __name__ == "__main__":
    main()
