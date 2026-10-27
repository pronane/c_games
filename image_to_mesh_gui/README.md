# Image → 3D Model / Classic Sprite Generator

Convert a photo into either:

1. **3D Extruded Model** with live preview and Run Bob / Lean animation
2. **Classic Console Sprite** (NES, SNES, Mega Drive, N64, PS1, Dreamcast, GameCube, PS2)

## New in this version

- Live 3D preview of the extruded model
- **Run Bob / Lean** procedural animation (preview only)
  - Adjustable speed, bob amount, and lean angle
- Right-mouse drag to orbit the camera
- Mouse wheel to zoom

## Features

- Drag & drop image loading
- 3D mode: Depth + Step controls, OBJ export, live animated preview
- Sprite mode: Platform presets with resolution + colour reduction
- Side-by-side previews

## Requirements

- Raylib (https://www.raylib.com)
- C compiler (MinGW / w64devkit / MSYS2 recommended)

## Build & Run (Windows)

1. Make sure `gcc` and raylib are available
2. Double-click **build.bat**
3. Program compiles and launches

## Controls (3D Preview)

| Input              | Action                  |
|--------------------|-------------------------|
| Right-mouse drag   | Orbit camera            |
| Mouse wheel        | Zoom                    |
| Bob / Lean checkbox| Toggle run animation    |
| Sliders            | Speed / Amount / Lean   |

Note: The Run Bob / Lean animation is **preview only**. The exported OBJ file is static.

## Limitations

- Bob/Lean is a simple procedural effect, not real limb animation
- Sprite mode uses resolution + colour reduction (not AI style transfer)
- Video input is not supported in this version
