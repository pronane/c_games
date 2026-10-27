#!/usr/bin/env python3
"""
make_character.py - turn a photo / drawing into a Turbo Tumble 64 racer.

    python tools/make_character.py my_photo.jpg --name "Auntie Jo"
    python tools/make_character.py hero.png --name Hero --angles 1          (single front billboard)
    python tools/make_character.py front.png --back back.png --name Duo     (better rear view)
    python tools/make_character.py pic.jpg --name Zed --speed 4.5 --accel 2 --handling 3 --weight heavy

What it does
  1. removes the background  (uses `rembg` if it is installed: pip install rembg;
     otherwise a colour-key flood fill from the image border - works best on a
     plain / evenly lit background)
  2. crops to the character, pads it and scales it to an HD sprite (default 256 px tall)
  3. writes an N64-style sprite sheet with 8 (or 16) pre-rendered angles in one row:
     frame 0 = facing the camera, then rotating clockwise (frame N/2 = seen from behind).
     From one photo the side/back views are approximations (squashed + a shaded
     back silhouette); pass --back to use a real rear image.
  4. writes character.ini (name, stats, kart colours picked from the image)

Output goes to assets/characters/<slug>/ (sprite.png, character.ini, preview.png).
The game loads every folder in assets/characters/ at start-up - no code changes needed.
Requires: Python 3 + Pillow (pip install pillow). numpy optional.
"""
import argparse, os, re, sys, colorsys
from collections import deque
try:
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

def remove_background(img, tol):
    img = img.convert("RGBA")
    try:
        from rembg import remove   # optional, much better on real photos
        print("background: rembg")
        return remove(img)
    except Exception:
        pass
    print("background: colour-key flood fill (install rembg for photos with busy backgrounds)")
    w, h = img.size
    px = img.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    def close(a, b, t):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 <= t * t
    mask = Image.new("L", (w, h), 255)
    mk = mask.load()
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        # background if close to a border colour sample nearby in colour space
        if c[3] < 10 or any(close(c, b, tol) for b in border[:: max(1, len(border) // 64)]):
            mk[x, y] = 0
            if x > 0: q.append((x - 1, y))
            if x < w - 1: q.append((x + 1, y))
            if y > 0: q.append((x, y - 1))
            if y < h - 1: q.append((x, y + 1))
    # clean up: close small holes, then soften the edge by one pixel
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    img.putalpha(mask)
    return img

def crop_and_scale(img, height):
    a = img.split()[3].point(lambda v: 255 if v > 24 else 0)
    box = a.getbbox()
    if not box:
        sys.exit("could not find the character - try --tol or a plainer background")
    img = img.crop(box)
    w, h = img.size
    pad = int(h * 0.04)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    canvas.paste(img, (pad, pad), img)
    s = height / canvas.size[1]
    return canvas.resize((max(1, int(canvas.size[0] * s)), height), Image.LANCZOS)

def dominant_colours(img):
    small = img.resize((48, 48))
    cols = [p for p in (small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()) if p[3] > 200]
    if not cols:
        return (200, 60, 60), (250, 220, 60)
    # most saturated frequent colour -> kart, its complement -> trim
    best, score = cols[0], -1
    buckets = {}
    for c in cols:
        k = (c[0] // 32, c[1] // 32, c[2] // 32)
        buckets.setdefault(k, []).append(c)
    for k, v in buckets.items():
        r = sum(c[0] for c in v) / len(v); g = sum(c[1] for c in v) / len(v); b = sum(c[2] for c in v) / len(v)
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        sc = len(v) * (0.3 + ss) * (0.4 + vv)
        if sc > score:
            score, best = sc, (int(r), int(g), int(b))
    hh, ss, vv = colorsys.rgb_to_hsv(*[c / 255 for c in best])
    kart = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hh, max(ss, 0.55), max(vv, 0.75)))
    trim = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hh + 0.5) % 1.0, 0.6, 0.95))
    return kart, trim

def back_view(front):
    """approximate rear view: the silhouette filled with the character's own
    darker average colours, with a soft vertical shade (reads as 'back of head/body')."""
    w, h = front.size
    mirrored = ImageOps.mirror(front)
    blur = mirrored.filter(ImageFilter.GaussianBlur(max(2, w // 14)))
    out = Image.new("RGBA", (w, h))
    fp, bp, op = mirrored.load(), blur.load(), out.load()
    for y in range(h):
        shade = 0.62 + 0.18 * (1 - y / h)
        for x in range(w):
            a = fp[x, y][3]
            if a:
                c = bp[x, y]
                op[x, y] = (int(c[0] * shade), int(c[1] * shade), int(c[2] * shade), a)
    return out

def squash(img, f):
    w, h = img.size
    nw = max(2, int(w * f))
    s = img.resize((nw, h), Image.LANCZOS)
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c.paste(s, ((w - nw) // 2, 0), s)
    return c

def blend(a, b, t):
    return Image.blend(a, b, t)

def make_sheet(front, back, n):
    if n == 1:
        return front
    frames = []
    for i in range(n):
        ang = i * 360.0 / n                     # 0 = front, 180 = back
        rel = ang if ang <= 180 else 360 - ang
        view = front if rel < 90 else back
        if rel >= 90:
            view = back
        # width of a flat card seen at this angle (never quite zero - sprites stay readable)
        f = abs(__import__("math").cos(__import__("math").radians(rel)))
        f = 0.55 + 0.45 * f
        v = squash(view, f)
        if ang > 180:                            # left-hand side: mirror
            v = ImageOps.mirror(v)
        frames.append(v)
    w, h = front.size
    sheet = Image.new("RGBA", (w * n, h), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (i * w, 0), fr)
    return sheet

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--name", required=True)
    ap.add_argument("--tagline", default="Fresh off the photo booth and ready to race.")
    ap.add_argument("--back", help="optional image of the character from behind")
    ap.add_argument("--angles", type=int, default=8, choices=[1, 8, 16])
    ap.add_argument("--height", type=int, default=256, help="sprite height in pixels (HD)")
    ap.add_argument("--tol", type=float, default=60, help="background colour tolerance for the fallback remover")
    ap.add_argument("--speed", type=float, default=3.5)
    ap.add_argument("--accel", type=float, default=3.5)
    ap.add_argument("--handling", type=float, default=3.5)
    ap.add_argument("--weight", choices=["light", "medium", "heavy"], default="medium")
    ap.add_argument("--voice", type=float, default=1.2, help="voice pitch of the chirps (0.6 deep .. 1.8 squeaky)")
    ap.add_argument("--size", type=float, default=1.35, help="driver height in game units")
    ap.add_argument("--out", help="output folder (default assets/characters/<slug>)")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    slug = re.sub(r"[^a-z0-9]+", "_", a.name.lower()).strip("_") or "racer"
    out = a.out or os.path.join(root, "assets", "characters", slug)
    os.makedirs(out, exist_ok=True)

    src = Image.open(a.image)
    src.thumbnail((900, 900))
    front = crop_and_scale(remove_background(src, a.tol), a.height)
    if a.back:
        back = crop_and_scale(remove_background(Image.open(a.back), a.tol), a.height).resize(front.size, Image.LANCZOS)
    else:
        back = back_view(front)
    sheet = make_sheet(front, back, a.angles)
    sheet.save(os.path.join(out, "sprite.png"))
    front.save(os.path.join(out, "preview.png"))
    kart, trim = dominant_colours(front)
    mass = {"light": 1.5, "medium": 3.0, "heavy": 4.5}[a.weight]
    with open(os.path.join(out, "character.ini"), "w") as f:
        f.write("; Turbo Tumble 64 character - made by tools/make_character.py\n")
        f.write(f"name = {a.name}\n")
        f.write(f"tagline = {a.tagline}\n")
        f.write(f"weight = {a.weight}\n")
        f.write(f"speed = {a.speed}\naccel = {a.accel}\nhandling = {a.handling}\nmass = {mass}\n")
        f.write(f"kart = {kart[0]},{kart[1]},{kart[2]}\ntrim = {trim[0]},{trim[1]},{trim[2]}\n")
        f.write(f"voice = {a.voice}\n")
        f.write("sprite = sprite.png\n")
        f.write(f"angles = {a.angles}\n")
        f.write(f"size = {a.size}\n")
    print(f"wrote {out}  ({a.angles} angle{'s' if a.angles > 1 else ''}, frame {front.size[0]}x{front.size[1]}, kart {kart}, trim {trim})")

if __name__ == "__main__":
    main()
