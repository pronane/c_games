# Console Asset Pipeline v2 – Transparent Sheets for Every Console

Fully transparent (RGBA, Alpha = 0) sprite sheets and turnaround atlases constrained to the hardware rules of every major console from the Atari 2600 to the PlayStation 5.

## Two clear modes

### OPTION A – Chronological Action Sheet (2D Flipbook)
- Each action (walk, run, kick, solo…) gets its own horizontal row
- Frames progress left → right so a delta-time loop plays the action fluidly
- Perfect for classic 2D / sprite-based engines

### OPTION B – Directional Turnaround Atlas (2.5D / Faux-3D)
- Pose stays locked
- Camera rotates around the character at 0°, 45°, 90° … 315° + top-down
- Engine code selects the correct visual slice according to the player’s angle

## All consoles supported

| Console                    | Frame size   | Palette      | Style notes                          |
|----------------------------|--------------|--------------|--------------------------------------|
| Atari 2600                 | 8×32         | 2 colours    | Hard 1-bit look                      |
| NES                        | 16×16        | 4 colours    | Classic tiled sprites                |
| SNES / Genesis             | 64×64        | 16 colours   | Indexed + dithering                  |
| PlayStation 1              | 64×64        | Full RGBA    | Jagged / unfiltered                  |
| Nintendo 64                | 64×64        | Full RGBA    | Heavy bilinear filtering             |
| PlayStation 2 / GameCube   | 128×128      | Full RGBA    | Clean mid-poly Phong look            |
| PS3 / Xbox 360             | 256×256      | Full RGBA    | Pre-baked lighting style             |
| PS4 / Xbox One             | 512×512      | Full RGBA    | PBR-ready surface                    |
| PlayStation 5              | 1024×1024    | Full RGBA    | Cinematic target                     |

Every output has a **completely transparent background**.

## How to run (Windows / any OS)

```bash
# Only required package
pip install Pillow

# Optional – better background removal (can be skipped if it fails on Windows)
pip install rembg
```

Then:

```bash
python console_asset_pipeline.py
```

1. Browse → load your static character image
2. Choose the Target Console
3. Choose OPTION A or OPTION B
4. Edit the state list if needed
5. Click **Generate Transparent Sheet**

Files appear in `pipeline_output/`:
- `*_action_sheet.png` + `*_action_meta.json`   (OPTION A)
- `*_turnaround_atlas.png` + `*_turnaround_meta.json`  (OPTION B)

## Background removal note for Windows

If `pip install rembg` fails with the `lsm2bin.exe` error, simply ignore it.  
The tool has a built-in fallback that samples the corner colours of the image and removes the studio/grey background without any extra packages. All example sheets in this zip were generated with that fallback and are fully transparent.

## Example assets included

- NES, SNES, PS2/GameCube, PS5 → OPTION A action sheets of the Gaelic footballer
- N64, PS1, PS4/Xbox One → OPTION B turnaround atlases of the same character

All verified transparent (corner pixel = 0,0,0,0).
