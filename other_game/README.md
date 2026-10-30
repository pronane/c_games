# Sprite & HD Asset Generation Tool

## Why this tool exists

You asked for a tool that can turn **one static image** into a full set of animation frames (walk / run / jump / punch / kick / solo / hand-pass) the same way the classic Street Fighter 2 HD sprite sheets and the Meshy Gaelic-footballer sequences were created.

### The honest technical reality

- The **Street Fighter-style sheets** (walk, punch, kick, jump, hit) you saw are the result of either hand-drawn keyframes or modern generative pipelines (Stable Diffusion + ControlNet pose / IP-Adapter + frame interpolation).
- The **Gaelic footballer** running / kicking / soloing images come from **3D reconstruction + animation** (Meshy AI, Kaedim, TripoSR, etc.). The skeleton overlays and the 3D viewer timeline show exactly that pipeline.
- A pure local script **cannot** invent new realistic poses from a single photo at that quality without multi-gigabyte diffusion models and a GPU. That is why the previous “cartoonify / remove background” attempts only discoloured the image – the implementation was incomplete.

This tool therefore does the parts that **can** be done robustly and locally, and prepares assets that you can feed straight into the generative tools that *do* produce the missing animation frames.

## What it does (and does correctly)

| Feature | Status | Notes |
|---------|--------|-------|
| Background removal | ✅ Working | Uses lightweight `u2netp` (or other rembg models). Outputs true RGBA PNG with clean alpha. |
| Cartoonify / cel-shade | ✅ Working | OpenCV bilateral + adaptive edges, **alpha channel preserved**. |
| N64 / PS1 style | ✅ | Nearest-neighbour pixelation for billboard / low-poly look. |
| PS2-era soft 2.5D | ✅ | Higher-res soft shading + mild contrast, still transparent. |
| Sprite-sheet assembler | ✅ | Helper to pack multiple frames into one sheet. |
| Full animation from 1 image | ❌ (by design) | Requires external generative AI – see recommended pipeline below. |

## Quick start

```bash
# Install once
pip install Pillow rembg opencv-python-headless

# Basic usage – always produces a clean transparent PNG
python sprite_generation_tool.py your_character.png --out output

# Full suite
python sprite_generation_tool.py your_character.png --out output --cartoon --n64 --ps2
```

### Recommended models for rembg
- `u2netp` – default, lightest, fastest, good for most characters
- `u2net_human_seg` – better on people
- `isnet-general-use` – higher quality when you have RAM

## Example outputs included in this zip

```
examples/
├── …_nobg.png          ← clean transparent version of the Gaelic footballer
├── …_cartoon.png       ← cartoon / cel-shaded, still transparent
├── …_n64.png           ← 64×64 nearest-neighbour upscaled (N64 billboard style)
├── …_ps2.png           ← soft 256 px PS2-era look
├── walk_nobg.png       ← Street Fighter walk sheet with background removed
└── walk_cartoon.png
```

## How to get the *animation frames* (the SF / Meshy quality)

1. Run this tool → obtain `*_nobg.png` (or the cartoon / N64 / PS2 variant).
2. Feed that transparent image into one of:
   - **Meshy AI** / **Kaedim** / **Tripo** → 3D mesh + auto-rig + animation library (exactly how the footballer kick / solo / run sequences were made).
   - **Stable Diffusion WebUI** + ControlNet (OpenPose / DWPose) + IP-Adapter → generate each pose from the same character reference.
   - **AnimateDiff** / **SVD** for short video → extract frames.
3. Re-import the resulting frames into this tool’s `make_sprite_sheet()` helper if you need a classic horizontal strip.

## N64 vs PS2 2.5D guidance

- **N64 / PS1**: Use the `--n64` flag (or call `to_n64_style`). Keep the character as a billboard or very low-poly mesh; the nearest-neighbour look is intentional.
- **PS2 / early GameCube**: Use `--ps2`. Higher texture resolution, softer filtering, still works as a 2.5D sprite or on a simple card.

## File list

- `sprite_generation_tool.py` – the complete, self-contained tool
- `examples/` – generated transparent assets from the images you supplied
- `README.md` – this file

The transparency and cartoonify paths now work correctly. The generative animation step remains outside the local script (as it always must for quality matching the examples you showed).
