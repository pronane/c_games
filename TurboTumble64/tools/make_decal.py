#!/usr/bin/env python3
"""
make_decal.py - kart side/rear decal for a racer (written as <character folder>/decal.png).

    python tools/make_decal.py "MILKIES" --style bubbly --out assets/characters/baby_eabha
    python tools/make_decal.py "I'M ANNOYING" --style comic --out assets/characters/towelhead_qanna

Styles
  bubbly : cute rounded letters (Fredoka, OFL) in soft pastel pink with a white rounded outline,
           a rose outer rim, little hearts and milk drops.
  comic  : chunky slanted comic letters (Bangers, OFL), wonky per-letter tilt, hot pink / yellow
           with a thick black outline, zigzag doodles and a tongue-out face. Two frames with the
           colours swapped, so the game makes it blink.
Then add  `decal = decal.png`  (and `decalframes = 2` for comic) to the character.ini.
Fonts live in tools/fonts/ with their SIL Open Font License texts.
"""
import argparse, math, os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1024, 200

def font(name, size, weight=None):
    f = ImageFont.truetype(os.path.join(HERE, "fonts", name), size)
    if weight:
        try:
            f.set_variation_by_axes([weight, 100])
        except Exception:
            pass
    return f

def fit_font(text, name, weight, maxw, maxh, stroke):
    size = maxh
    while size > 10:
        f = font(name, size, weight)
        b = f.getbbox(text, stroke_width=stroke)
        if b[2] - b[0] <= maxw and b[3] - b[1] <= maxh:
            return f
        size -= 2
    return font(name, 10, weight)

def heart(d, cx, cy, r, fill, outline):
    for ox in (-r * 0.5, r * 0.5):
        d.ellipse([cx + ox - r * 0.55, cy - r * 0.55, cx + ox + r * 0.55, cy + r * 0.45], fill=fill, outline=outline, width=3)
    d.polygon([(cx - r * 1.02, cy), (cx + r * 1.02, cy), (cx, cy + r * 1.15)], fill=fill)

def drop(d, cx, cy, r, fill, outline):
    d.ellipse([cx - r, cy - r * 0.2, cx + r, cy + r * 1.8], fill=fill, outline=outline, width=3)
    d.polygon([(cx - r * 0.82, cy + r * 0.3), (cx + r * 0.82, cy + r * 0.3), (cx, cy - r * 1.3)], fill=fill)

def bubbly(text):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = fit_font(text, "Fredoka-Variable.ttf", 700, W - 260, H - 50, 16)
    b = d.textbbox((0, 0), text, font=f, stroke_width=16)
    x = (W - (b[2] - b[0])) // 2 - b[0]
    y = (H - (b[3] - b[1])) // 2 - b[1]
    rose, pink, white = (226, 98, 156, 255), (255, 178, 214, 255), (255, 255, 255, 255)
    d.text((x, y), text, font=f, fill=rose, stroke_width=20, stroke_fill=rose)          # outer rose rim
    d.text((x, y), text, font=f, fill=white, stroke_width=13, stroke_fill=white)        # rounded white outline
    d.text((x, y), text, font=f, fill=pink)                                             # pastel letters
    # glossy highlight on the top half of the letters
    hl = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hl).text((x, y - 6), text, font=f, fill=150)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((x, y), text, font=f, fill=255)
    hl = Image.composite(hl, Image.new("L", (W, H), 0), mask.filter(ImageFilter.MinFilter(9)))
    top = Image.linear_gradient("L").rotate(180).resize((W, H)).point(lambda v: 255 if v > 150 else 0)
    hl = Image.composite(hl, Image.new("L", (W, H), 0), top)
    img.alpha_composite(Image.merge("RGBA", (Image.new("L", (W, H), 255),) * 3 + (hl.point(lambda v: v // 2),)))
    heart(d, 70, 90, 34, (255, 140, 190, 255), white)
    drop(d, W - 75, 70, 28, (255, 255, 255, 255), (170, 210, 255, 255))
    heart(d, W - 150, 140, 18, (190, 225, 255, 255), white)
    return img

def comic(text, swap):
    rnd = random.Random(7)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pink, yellow, black = (255, 40, 165, 255), (255, 232, 0, 255), (12, 10, 14, 255)
    cols = (yellow, pink) if swap else (pink, yellow)
    size = H - 40
    while size > 20:
        f = font("Bangers-Regular.ttf", size)
        total = sum((f.size * 0.42) if ch == " " else (f.getlength(ch) + 14) for ch in text) + 30
        if total <= W - 215:
            break
        size -= 2
    # zigzag doodles behind the letters
    d = ImageDraw.Draw(img)
    for row, (yy, c) in enumerate(((22, cols[1]), (H - 22, cols[0]))):
        pts = [(x, yy + (12 if (x // 30) % 2 else -12)) for x in range(10, W - 200, 30)]
        d.line(pts, fill=black, width=14, joint="curve")
        d.line(pts, fill=c, width=7, joint="curve")
    # letters one by one: wonky tilt, alternating colours, thick black outline, italic shear
    x = 30
    for i, ch in enumerate(text):
        if ch == " ":
            x += int(f.size * 0.42)
            continue
        cw = f.getbbox(ch, stroke_width=10)
        gw, gh = cw[2] - cw[0] + 30, cw[3] - cw[1] + 30
        g = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.text((15 - cw[0], 15 - cw[1]), ch, font=f, fill=cols[i % 2], stroke_width=10, stroke_fill=black)
        g = g.transform(g.size, Image.AFFINE, (1, 0.22, -0.22 * gh / 2, 0, 1, 0), Image.BICUBIC)   # slant
        g = g.rotate(rnd.uniform(-11, 11), Image.BICUBIC, expand=True)
        yoff = (H - g.size[1]) // 2 + rnd.randint(-8, 8)
        img.alpha_composite(g, (x, max(0, yoff)))
        x += int(f.getlength(ch)) + 14
    # tongue-out face
    cx, cy, r = min(W - 90, x + 100), H // 2, 72
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8], fill=black)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cols[1])
    d.ellipse([cx - 40, cy - 34, cx - 14, cy - 2], fill=black)                       # open eye
    d.line([(cx + 12, cy - 18), (cx + 42, cy - 18)], fill=black, width=9)             # winking eye
    d.arc([cx - 46, cy - 10, cx + 46, cy + 46], 10, 170, fill=black, width=9)         # grin
    d.rounded_rectangle([cx - 4, cy + 26, cx + 32, cy + 66], radius=16, fill=(255, 90, 120, 255), outline=black, width=6)  # tongue
    d.line([(cx + 14, cy + 32), (cx + 14, cy + 52)], fill=(200, 40, 70, 255), width=4)
    return img

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text")
    ap.add_argument("--style", choices=["bubbly", "comic"], default="bubbly")
    ap.add_argument("--out", required=True, help="character folder")
    a = ap.parse_args()
    if a.style == "bubbly":
        frames = [bubbly(a.text)]
    else:
        frames = [comic(a.text, False), comic(a.text, True)]
    sheet = Image.new("RGBA", (W, H * len(frames)), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (0, i * H))
    os.makedirs(a.out, exist_ok=True)
    sheet.save(os.path.join(a.out, "decal.png"), optimize=True)
    print(f"wrote {os.path.join(a.out, 'decal.png')} ({len(frames)} frame{'s' if len(frames) > 1 else ''})")

if __name__ == "__main__":
    main()
