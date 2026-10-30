# Image → 3D Model / Classic Sprite Generator

## New features in this version

- **JPEG + GIF support** (in addition to PNG/BMP)
- **Remove Background** button (lower-left under the image preview)
- **Cartoonify** button (next to it)
- **Multi-action sprite generation** with checkboxes:
  Walk, Idle, Hunch, Punch, Kick, Throw, Run, Roll,
  KickLeft, KickRight, PunchLeft, PunchRight, Kneel, BendOver
- **Frames per action** selector: 6 / 8 / 10 / 12

## Important note about action sprites

The action checkboxes generate **styled versions of the current image** named by action (e.g. `player_SNES_Walk.png`).

True different poses (walking cycle frames, actual kick, etc.) **cannot** be created from a single static photo with classical image processing. That requires AI pose/image generation tools (Meshy, video models, etc.).

The frame count is stored and shown so the UI is ready for future multi-frame support.

## How to use

1. Drag a PNG, JPG, JPEG, GIF or BMP onto the window.
2. (Optional) Click **Remove BG** or **Cartoonify** under the preview.
3. Choose **Sprite** mode → pick platform + which actions + frame count.
4. Click **Generate Selected Sprites**.
5. Or switch to **3D Model** mode for extruded mesh + live Bob/Lean preview.

## Build

Double-click `build.bat` (requires Raylib + gcc/MinGW).
