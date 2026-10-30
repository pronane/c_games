# HD Fighter 2 — Original HD Fighting Game (F2 to toggle graphics)

> **F2 toggles CLASSIC (procedural V2 — fully original, no Capcom assets) ↔ HD (AI backgrounds + portraits)**

Both modes share the same 6 fighters, 16 states each (idle/walk/crouch/jump/lp/hp/lk/hk/block/throw/special1/special2/super/hit/win/lose), hitstop+shake+sparks+combo+blockstun+throw+super, 3 parallax stages, gamepad+keyboard, best-of-3. All tested headless (36 matchups, 300-frame stress, frozen path).

## What changed (you asked for SF2 look)
- **Procedural V2:** fighters now *fill* the 192×256 canvas (70%, was 40%), black outlines, CEL shading, ground shadow, neck fix (head was floating 30px above). Stages have proper parallax: neon rooftop now has ARCADE sign + dragon + moon; temple has torii + blossoms; industrial has crane/sparks.
- **HD (F2):** AI-generated `assets_hd/` backgrounds (1280×720 moon-city, temple sunset, factory) + 128×128 portraits (KAIRO/ LYRA/ BRUTUS/ NAOMI/ ZAP/ VOID). Fighter bodies are still procedural V2 in this build — next step is AI fighter sheets (say “do fighters” and I will generate 96×12 HD sprite sheets and wire F2 to swap those too).

## Controls
P1: A/D move, S crouch, W jump, Z/X/C/V = LP/HP/LK/HK, F throw, R super (meter full)
P2: arrows + J/K/N/M + H/U + same  |  Gamepads: first 2 joysticks
Global: **F2** = toggle CLASSIC/HD (in select or fight)  **Esc** = quit  **R** = replay

## Build (Windows)
Double-click `build_release.bat` → `dist\HD_Fighter_2\HD_Fighter_2.exe`
It bundles both `assets/` and `assets_hd/` and copies them next to the exe (fix for your `_internal/assets` crash).

## Run from source
```
pip install -r requirements.txt
python game.py        # or python generate_assets.py to regen CLASSIC
python generate_assets_v2.py  # V2 is now default generate_assets.py
```

## Gallery
`screenshots/gallery_both.html` — side-by-side CLASSIC vs HD for select, 3 stages, VS, combat.
`screenshots/gallery.html` — 93-frame full moveset dump.
