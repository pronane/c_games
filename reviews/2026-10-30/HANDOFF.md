# Handoff from the review conversation (30 Oct 2026)

## Files in this bundle
- TurboTumble64_review.md / .xlsx, EgyptianFighter_review.md / .xlsx, ArenaFC_review.md / .xlsx — code reviews (static reads; nothing was run)
- SpriteForge_review.md, sprite_forge_v9.1_patch.zip, sprite_forge_classic_vs_skin.png — Sprite Forge review and opt-in patch (`--puppet-engine skin`, `--motion-style polish`)
- padel_wars_stage1_analysis.md — independent check of the Stage 1 deterministic-sim package, with a paste-ready prompt

## Where things stand
- Reviews: done. Spreadsheets recalculated with 0 formula errors; counts match the markdown tables.
- Sprite Forge patch: tested on the project's own mannequin render with hand-placed landmarks. Regression: test_v9 44/44 and test_v8 6/6 pass; test_v7 is inconclusive (9/22 on original and patched code in my sandbox).
- Padel Wars Stage 1: patch applies cleanly and compiles; I could not run `--sim-test` or reproduce the hashes. The Egyptian Fighter bugs (block exploit, arrow keys drive both fighters, double KO gives P2 the win) are still present.

## Open item: real-photo test of Sprite Forge (blocked)
`forge.py cutout photo.jpg --person largest` fails in my sandbox: no pose model (download blocked by network policy) and no `rembg`. To continue, run this on a machine with network access:
    python tools/setup_pose.py
    python forge.py cutout photo.jpg --person largest --out cut
    python forge.py build --photo cut/cutout.png --landmarks cut/landmarks.json --fill puppet --preset fighter14 --puppet-engine skin --name test --out out
    python forge.py build --photo cut/cutout.png --landmarks cut/landmarks.json --turn 90 --preset fighter14 --puppet-engine skin --name side --out out_side
Then compare against the same builds without `--puppet-engine skin`, and view the sheets.

## Notes on 3D / side view (from reading the code, not tested on a real person)
- `--turn 90` side view is an estimate (front photo + generic body template), labelled as such.
- GLB/FBX export is not available for photo sources; a real 3D model of a person needs the `scan` command with an orbit video.
- The pose detector is trained on humans, so cartoon characters (e.g. Mango Mo) will probably need manual landmarks.
