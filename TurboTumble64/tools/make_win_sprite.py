#!/usr/bin/env python3
"""
make_win_sprite.py - "victory mood" variant of a photo racer's front frame (writes win.png).

    python tools/make_win_sprite.py assets/characters/towelhead_qanna --style grumpy \\
           --eyes 141,218,197,214 --eyew 21 --mouth 177,271 --mouthw 42 --vein 238,140

grumpy : droopy half-closed eyelids, dark under-eye shadows, furrowed angry brows, a frown and
         a red anger-vein mark (used for "I didn't sleep last night").
happy  : rosy cheeks + sparkles (eyes and mouth untouched).
Coordinates are pixels in the folder's preview.png (the unrotated front frame). Only the
processed sprite is edited; no photo is needed. Add  `winsprite = win.png`  to character.ini.
"""
import argparse, os
from PIL import Image, ImageDraw, ImageFilter, ImageChops

def pts(s):
    return [int(v) for v in s.split(",")]

def skin_tone(img, x, y):
    px = [img.getpixel((x + dx, y + dy)) for dx in range(-4, 5, 2) for dy in range(-4, 5, 2)]
    return tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3)) + (255,)

def grumpy(img, a):
    W, H = img.size
    ex1, ey1, ex2, ey2 = pts(a.eyes)
    ew = a.eyew
    mx, my = pts(a.mouth)
    skin = skin_tone(img, (ex1 + ex2) // 2, min(ey1, ey2) - 26)
    # dark under-eye shadows (multiply)
    sh = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(sh)
    for ex, ey in ((ex1, ey1), (ex2, ey2)):
        d.ellipse([ex - ew * 0.8, ey + ew * 0.15, ex + ew * 0.8, ey + ew * 0.75], fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(ew * 0.18))
    tint = Image.new("RGB", (W, H), (120, 80, 125))
    rgb = img.convert("RGB")
    mult = ImageChops.multiply(rgb, tint)
    rgb = Image.composite(mult, rgb, sh)
    out = rgb.convert("RGBA"); out.putalpha(img.split()[3])
    # droopy half-closed lids: curved skin-coloured lids over the top ~60% of each eye with a lash line
    import numpy as np
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    o = np.array(out).astype(np.float32)
    for i, (ex, ey) in enumerate(((ex1, ey1), (ex2, ey2))):
        outer = -1 if i == 0 else 1
        lidskin = np.array(skin_tone(img, ex, int(ey - ew * 0.95))[:3], np.float32) * 0.9
        inside = ((xx - ex) / (ew * 0.9)) ** 2 + ((yy - ey) / (ew * 0.62)) ** 2 <= 1.0
        t = np.clip((xx - ex) * outer / (ew * 0.9), -1, 1)            # -1 inner corner .. 1 outer corner
        lidline = ey + ew * (0.02 + 0.16 * (t + 1) / 2) + ew * 0.05 * (1 - t * t)
        m = (inside & (yy < lidline)).astype(np.float32)
        m = np.array(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32) / 255
        shade = 0.92 + 0.12 * np.clip((yy - (ey - ew * 0.6)) / (ew * 0.7), 0, 1)   # lid slightly darker at its rim
        for c in range(3):
            o[:, :, c] = o[:, :, c] * (1 - m) + lidskin[c] * shade * m
        lash = inside & (np.abs(yy - lidline) < max(1.2, ew / 12.0))
        o[lash, 0], o[lash, 1], o[lash, 2] = 55, 32, 28
    out = Image.fromarray(np.clip(o, 0, 255).astype(np.uint8), "RGBA")
    # furrowed angry brows (slanting down towards the nose)
    d = ImageDraw.Draw(out)
    bw = max(3, ew // 5)
    by1, by2 = ey1 - ew * 0.7, ey2 - ew * 0.7
    d.line([(ex1 - ew * 0.85, by1 - ew * 0.3), (ex1 + ew * 0.7, by1 + ew * 0.15)], fill=(55, 38, 32, 255), width=bw)
    d.line([(ex2 + ew * 0.85, by2 - ew * 0.3), (ex2 - ew * 0.7, by2 + ew * 0.15)], fill=(55, 38, 32, 255), width=bw)
    # crease between the brows
    cx = (ex1 + ex2) / 2
    d.line([(cx - 2, by1 - ew * 0.1), (cx - 1, by1 + ew * 0.35)], fill=(160, 105, 92, 255), width=2)
    d.line([(cx + 3, by1 - ew * 0.1), (cx + 2, by1 + ew * 0.35)], fill=(160, 105, 92, 255), width=2)
    # grumpy frown: soften the old mouth with skin, draw a downturned mouth
    mw = a.mouthw
    patch = Image.new("L", (W, H), 0)
    ImageDraw.Draw(patch).ellipse([mx - mw * 0.6, my - mw * 0.16, mx + mw * 0.6, my + mw * 0.2], fill=200)
    patch = patch.filter(ImageFilter.GaussianBlur(mw * 0.08))
    out = Image.composite(Image.new("RGBA", (W, H), tuple(int(c * 0.93) for c in skin_tone(img, mx, my + mw // 3)[:3]) + (255,)), out, patch)
    d = ImageDraw.Draw(out)
    d.arc([mx - mw * 0.45, my - mw * 0.02, mx + mw * 0.45, my + mw * 0.45], 200, 340, fill=(110, 45, 45, 255), width=max(3, mw // 12))
    # anger vein mark
    if a.vein:
        vx, vy = pts(a.vein)
        r = ew * 1.25
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            box = [vx + sx * r * 0.62 - r * 0.5, vy + sy * r * 0.62 - r * 0.5, vx + sx * r * 0.62 + r * 0.5, vy + sy * r * 0.62 + r * 0.5]
            start = {(-1, -1): -15, (1, -1): 75, (1, 1): 165, (-1, 1): 255}[(sx, sy)]
            d.arc(box, start, start + 120, fill=(255, 255, 255, 255), width=max(4, int(r * 0.26)))
            d.arc(box, start, start + 120, fill=(235, 25, 35, 255), width=max(2, int(r * 0.14)))
    return out

def happy(img, a):
    W, H = img.size
    ex1, ey1, ex2, ey2 = pts(a.eyes)
    ew = a.eyew
    blush = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(blush)
    for ex, ey in ((ex1, ey1), (ex2, ey2)):
        d.ellipse([ex - ew, ey + ew * 0.8, ex + ew * 0.7, ey + ew * 1.5], fill=110)
    blush = blush.filter(ImageFilter.GaussianBlur(ew * 0.3))
    out = img.copy()
    out = Image.composite(Image.new("RGBA", (W, H), (255, 110, 140, 255)), out, ImageChops.multiply(blush, img.split()[3]))
    out.putalpha(img.split()[3])
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--style", choices=["grumpy", "happy"], default="grumpy")
    ap.add_argument("--eyes", required=True, help="x1,y1,x2,y2 eye centres in preview.png")
    ap.add_argument("--eyew", type=int, default=20, help="eye width in pixels")
    ap.add_argument("--mouth", default="0,0")
    ap.add_argument("--mouthw", type=int, default=40)
    ap.add_argument("--vein", default="")
    a = ap.parse_args()
    img = Image.open(os.path.join(a.folder, "preview.png")).convert("RGBA")
    out = grumpy(img, a) if a.style == "grumpy" else happy(img, a)
    out.save(os.path.join(a.folder, "win.png"), optimize=True)
    print("wrote", os.path.join(a.folder, "win.png"))

if __name__ == "__main__":
    main()
