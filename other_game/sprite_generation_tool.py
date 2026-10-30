#!/usr/bin/env python3
"""
Sprite & HD Asset Generation Tool
=================================
Best-in-class local tool for:
  - Proper background removal (preserves alpha / transparency)
  - Cartoonify / stylize while keeping transparency
  - Style conversion helpers (N64 pixel art, PS2-era soft shading look)
  - Simple multi-frame sprite sheet assembly helpers

Why true single-image → full animation (walk/run/punch/kick/jump) is hard:
  The classic Street Fighter 2-style HD sprites and the Meshy Gaelic footballer
  sequences you saw were produced with generative AI pipelines
  (image-to-image diffusion + pose ControlNet / 3D mesh + animation retargeting).
  A pure local script cannot replicate that quality without multi-GB models and a GPU.
  This tool gives you production-ready transparent sprites + style transfer so you
  can feed the results into Meshy, Kaedim, Tripo, or a Stable Diffusion webUI
  for the animation step.

Usage:
  python sprite_generation_tool.py input.png [--cartoon] [--n64] [--ps2] [--out dir]
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageDraw
except ImportError:
    print("Please: pip install Pillow")
    sys.exit(1)

try:
    from rembg import remove, new_session
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False
    print("Warning: rembg not installed. Background removal will be a simple chroma/threshold fallback.")
    print("  pip install rembg")

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("Warning: OpenCV not installed. Cartoonify will use a lighter PIL filter.")
    print("  pip install opencv-python-headless")


def remove_background(img: Image.Image, model: str = "u2netp") -> Image.Image:
    """Remove background and return RGBA image. Uses lightweight u2netp by default."""
    if img.mode != "RGB":
        img = img.convert("RGB")

    if HAS_REMBG:
        session = new_session(model)
        result = remove(img, session=session)
        return result  # already RGBA
    else:
        # Fallback: simple white/near-white background removal
        img = img.convert("RGBA")
        datas = img.getdata()
        new_data = []
        for item in datas:
            # Treat near-white as transparent
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
        return img


def cartoonify(img: Image.Image, strength: int = 9) -> Image.Image:
    """
    Apply a classic cartoon / cel-shading look while preserving alpha channel.
    """
    has_alpha = img.mode == "RGBA"
    if has_alpha:
        alpha = img.split()[-1]
        rgb = img.convert("RGB")
    else:
        alpha = None
        rgb = img.convert("RGB")

    if HAS_CV2:
        bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            strength, 9
        )
        color = cv2.bilateralFilter(bgr, d=9, sigmaColor=300, sigmaSpace=300)
        cartoon = cv2.bitwise_and(color, color, mask=edges)
        cartoon_rgb = cv2.cvtColor(cartoon, cv2.COLOR_BGR2RGB)
        out = Image.fromarray(cartoon_rgb)
    else:
        # PIL-only fallback
        out = rgb.filter(ImageFilter.MedianFilter(size=3))
        out = ImageOps.posterize(out, bits=4)
        edges = rgb.convert("L").filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.invert(edges)
        edges = edges.point(lambda x: 0 if x < 40 else 255)
        out = Image.composite(out, Image.new("RGB", out.size, (0, 0, 0)), edges)

    if has_alpha and alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out


def to_n64_style(img: Image.Image, pixel_size: int = 64) -> Image.Image:
    """Classic N64 / PS1 low-poly billboard look: nearest-neighbour downscale then up."""
    has_alpha = img.mode == "RGBA"
    small = img.resize((pixel_size, pixel_size), Image.NEAREST)
    out = small.resize(img.size, Image.NEAREST)
    if has_alpha:
        # Re-apply a slightly softened alpha so edges aren't too harsh
        alpha = out.split()[-1]
        alpha = alpha.filter(ImageFilter.MinFilter(3))
        out.putalpha(alpha)
    return out


def to_ps2_style(img: Image.Image, target_size: int = 256) -> Image.Image:
    """Softer, higher-res look reminiscent of early 2000s 2.5D / PS2 sprites."""
    has_alpha = img.mode == "RGBA"
    out = img.resize((target_size, target_size), Image.LANCZOS)
    enhancer = ImageEnhance.Contrast(out)
    out = enhancer.enhance(1.15)
    enhancer = ImageEnhance.Color(out)
    out = enhancer.enhance(1.1)
    # Slight edge softening
    if has_alpha:
        alpha = out.split()[-1]
        rgb = out.convert("RGB")
        rgb = rgb.filter(ImageFilter.SMOOTH_MORE)
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
    else:
        out = out.filter(ImageFilter.SMOOTH)
    return out


def make_sprite_sheet(frames: list[Image.Image], cols: int = 6, padding: int = 4) -> Image.Image:
    """Assemble a horizontal or grid sprite sheet from a list of RGBA frames."""
    if not frames:
        raise ValueError("No frames supplied")
    w, h = frames[0].size
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (w + padding) - padding, rows * (h + padding) - padding), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        r, c = divmod(i, cols)
        sheet.paste(frame, (c * (w + padding), r * (h + padding)), frame if frame.mode == "RGBA" else None)
    return sheet


def process(input_path: str, out_dir: str, do_cartoon: bool = False,
            do_n64: bool = False, do_ps2: bool = False, model: str = "u2netp"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    img = Image.open(input_path)
    stem = Path(input_path).stem

    print(f"[+] Loaded {input_path}  size={img.size} mode={img.mode}")

    # 1. Always produce a clean transparent version
    print("[+] Removing background (this may take a few seconds on first run)...")
    nobg = remove_background(img, model=model)
    nobg_path = out_path / f"{stem}_nobg.png"
    nobg.save(nobg_path)
    print(f"    → {nobg_path}")

    results = {"nobg": nobg}

    if do_cartoon:
        print("[+] Cartoonify...")
        cart = cartoonify(nobg)
        p = out_path / f"{stem}_cartoon.png"
        cart.save(p)
        print(f"    → {p}")
        results["cartoon"] = cart

    if do_n64:
        print("[+] N64 pixel style...")
        n64 = to_n64_style(nobg)
        p = out_path / f"{stem}_n64.png"
        n64.save(p)
        print(f"    → {p}")
        results["n64"] = n64

    if do_ps2:
        print("[+] PS2-era soft style...")
        ps2 = to_ps2_style(nobg)
        p = out_path / f"{stem}_ps2.png"
        ps2.save(p)
        print(f"    → {p}")
        results["ps2"] = ps2

    print("\nDone. Transparent PNGs are ready for use in game engines or further AI animation tools.")
    return results


def main():
    parser = argparse.ArgumentParser(description="Sprite / HD asset tool with proper transparency")
    parser.add_argument("input", help="Input image (any format)")
    parser.add_argument("--out", default="output", help="Output directory")
    parser.add_argument("--cartoon", action="store_true", help="Also produce cartoon version")
    parser.add_argument("--n64", action="store_true", help="Also produce N64-style pixel version")
    parser.add_argument("--ps2", action="store_true", help="Also produce PS2-style soft version")
    parser.add_argument("--model", default="u2netp",
                        choices=["u2netp", "u2net", "u2net_human_seg", "silueta", "isnet-general-use"],
                        help="rembg model (u2netp is lightest & fastest)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    process(args.input, args.out, args.cartoon, args.n64, args.ps2, args.model)


if __name__ == "__main__":
    main()
