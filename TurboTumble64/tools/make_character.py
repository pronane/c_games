#!/usr/bin/env python3
"""
make_character.py - turn a photo / drawing into a Turbo Tumble 64 racer (HD billboard driver).

    python tools/make_character.py my_photo.jpg --name "Auntie Jo"
    python tools/make_character.py photo.jpg --name "Baby Eabha" --crop 500,760,1140,1430 --neck 0.49 \\
           --weight light --speed 2.5 --accel 5 --handling 4.5 --voice 1.75 --kart 255,170,205 --kartstyle rattle
    python tools/make_character.py front.png --back back.png --name Duo      (real rear image)

What it does
  1. removes the background. With `rembg` installed (pip install "rembg[cpu]") it uses a
     neural cut-out model (default isnet-general-use; --model u2net_human_seg for people).
     Without rembg it uses a colour-key flood fill from the border (needs a plain background).
  2. --crop x0,y0,x1,y1 keeps just the head + upper body (pixels of the original photo); only the
     largest connected blob is kept, so bits of furniture or toys are dropped. The bottom edge
     fades out because the kart body hides the driver's lower half.
  3. scales it to an HD sprite (default 512 px tall), sharpens it slightly, lifts the colours a
     touch and adds a thin dark outline, like the N64 pre-rendered racers.
  4. builds the rear view: the same silhouette mirrored, with the head above --neck re-textured
     from the top of the head (hair / towel / hat) and the body re-textured from the clothes, so
     the chase camera sees a believable back of the head instead of a mirrored face. Use --back
     for a real rear photo instead.
  5. writes a sprite sheet with 8 or 16 angles (frame 0 = facing the camera, rotating clockwise,
     frame N/2 = seen from behind), laid out in --rows rows to stay under 4096 px, plus
     portrait.png (square head shot for the character-select grid), preview.png and character.ini.

Output goes to assets/characters/<slug>/. The game loads every folder in assets/characters/ at
start-up - no code changes needed. Only the processed sprites are written: the original photo is
never copied into the game folder.
Requires: Python 3 + Pillow + numpy (rembg optional but strongly recommended for photos).
"""
import argparse, os, re, sys, colorsys, math, unicodedata
from collections import deque
try:
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageChops
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")
try:
    import numpy as np
except ImportError:
    np = None

# ------------------------------------------------------------------ background removal
def remove_background(img, tol, model):
    img = img.convert("RGBA")
    try:
        from rembg import remove, new_session
        print(f"background: rembg ({model})")
        return remove(img, session=new_session(model), alpha_matting=True,
                      alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=15,
                      alpha_matting_erode_size=8)
    except ImportError:
        pass
    print("background: colour-key flood fill (install rembg for photos with busy backgrounds)")
    w, h = img.size
    px = img.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    samples = border[:: max(1, len(border) // 64)]
    def close(a, b, t):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 <= t * t
    mask = Image.new("L", (w, h), 255)
    mk = mask.load()
    seen = bytearray(w * h)
    q = deque([(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)])
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        if c[3] < 10 or any(close(c, b, tol) for b in samples):
            mk[x, y] = 0
            if x > 0: q.append((x - 1, y))
            if x < w - 1: q.append((x + 1, y))
            if y > 0: q.append((x, y - 1))
            if y < h - 1: q.append((x, y + 1))
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    img.putalpha(mask)
    return img

def keep_largest_blob(img):
    """drop everything that isn't connected to the biggest blob (furniture, toys, strays)"""
    if np is None:
        return img
    a = np.array(img.split()[3])
    solid = a > 100
    h, w = solid.shape
    lab = np.zeros((h, w), np.int32)
    best, bestn, cur = 0, 0, 0
    for sy in range(0, h, 2):
        row = solid[sy]
        for sx in np.nonzero(row & (lab[sy] == 0))[0]:
            if lab[sy, sx]:
                continue
            cur += 1
            n = 0
            q = deque([(sy, sx)]); lab[sy, sx] = cur
            while q:
                y, x = q.popleft(); n += 1
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and solid[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur; q.append((ny, nx))
            if n > bestn:
                best, bestn = cur, n
    keep = (lab == best)
    # grow the kept region a little so the soft matte edge survives
    keepimg = Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))
    a2 = np.minimum(a, np.array(keepimg))
    out = img.copy(); out.putalpha(Image.fromarray(a2.astype(np.uint8)))
    return out

def crop_and_scale(img, height, fade):
    a = img.split()[3].point(lambda v: 255 if v > 24 else 0)
    box = a.getbbox()
    if not box:
        sys.exit("could not find the character - try --tol, --crop or a plainer background")
    img = img.crop(box)
    w, h = img.size
    pad = int(h * 0.03)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad), (0, 0, 0, 0))   # no pad at the bottom (sits in the kart)
    canvas.paste(img, (pad, pad), img)
    s = height / canvas.size[1]
    out = canvas.resize((max(1, int(canvas.size[0] * s)), height), Image.LANCZOS)
    if fade > 0:   # fade the bottom edge: the kart cowl covers it
        al = out.split()[3]
        ramp = Image.linear_gradient("L").resize(out.size)            # 0 at top .. 255 at bottom
        f0 = 1.0 - fade
        ramp = ramp.point(lambda v: 255 if v / 255.0 < f0 else int(255 * max(0.0, 1.0 - (v / 255.0 - f0) / fade)))
        out.putalpha(ImageChops.multiply(al, ramp))
    return out

def polish(img, outline):
    """slight sharpen + colour lift + thin dark outline (N64 pre-rendered sprite look)"""
    rgb = img.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))
    rgb = ImageEnhance.Color(rgb).enhance(1.10)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.04)
    al = img.split()[3]
    out = rgb.convert("RGBA"); out.putalpha(al)
    if outline <= 0:
        return out
    hard = al.point(lambda v: 255 if v > 110 else 0)
    ring = hard.filter(ImageFilter.MaxFilter(outline * 2 + 1)).filter(ImageFilter.GaussianBlur(0.7))
    ring = ring.point(lambda v: int(v * 0.85))
    ol = Image.new("RGBA", img.size, (22, 16, 34, 0)); ol.putalpha(ring)
    ol.alpha_composite(out)
    return ol

# ------------------------------------------------------------------ colours + rear view
def dominant_colours(img):
    small = img.resize((48, 48))
    cols = [p for p in (small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()) if p[3] > 200]
    if not cols:
        return (200, 60, 60), (250, 220, 60)
    best, score = cols[0], -1
    buckets = {}
    for c in cols:
        buckets.setdefault((c[0] // 32, c[1] // 32, c[2] // 32), []).append(c)
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

def _median_colour(arr, alpha, y0, y1, w):
    reg = arr[y0:y1, w // 6:5 * w // 6, :3][alpha[y0:y1, w // 6:5 * w // 6] > 230]
    if len(reg) < 20:
        reg = arr[:, :, :3][alpha > 128]
    return np.median(reg, axis=0)

def _noise(h, w, cells_y, cells_x, rng):
    """smooth value noise in 0..1 (bicubic-upscaled random grid)"""
    g = (rng.random((max(2, cells_y), max(2, cells_x))) * 255).astype(np.uint8)
    return np.array(Image.fromarray(g).resize((w, h), Image.BICUBIC)).astype(np.float32) / 255.0

def _material(kind, h, w, rng):
    """luminance pattern (around 1.0) for hair, towel (terry cloth) or knit clothing"""
    if kind == "hair":        # strands falling downwards + soft clumps
        strands = _noise(h, w, h // 60 + 2, w // 3, rng) * 0.6 + _noise(h, w, h // 25 + 2, w // 7, rng) * 0.4
        clumps = _noise(h, w, 6, 6, rng)
        return 0.78 + 0.32 * strands + 0.12 * (clumps - 0.5)
    if kind == "towel":       # fluffy loops + twisted folds
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        warp = _noise(h, w, 5, 5, rng) * 40
        folds = 0.5 + 0.5 * np.sin((xx * 0.8 + yy) / (w / 9.0) + warp / 6.0)
        fluff = _noise(h, w, h // 3, w // 3, rng)
        return 0.72 + 0.22 * folds + 0.22 * fluff
    # knit / cotton
    fine = _noise(h, w, h // 3, w // 3, rng)
    broad = _noise(h, w, 8, 8, rng)
    return 0.86 + 0.18 * fine + 0.10 * (broad - 0.5)

def back_view(front, neck, headkind="hair"):
    """rear view: mirrored silhouette; head filled with the hair / towel colour taken from the top
    of the head, body with the clothing colour, both with a procedural material texture and the
    photo's broad light and shade (no face, no prints)."""
    w, h = front.size
    mir = ImageOps.mirror(front)
    if np is None:
        blur = mir.filter(ImageFilter.GaussianBlur(max(2, w // 14)))
        out = Image.new("RGBA", (w, h)); fp, bp, op = mir.load(), blur.load(), out.load()
        for y in range(h):
            for x in range(w):
                if fp[x, y][3]:
                    c = bp[x, y]; op[x, y] = (int(c[0] * .7), int(c[1] * .7), int(c[2] * .7), fp[x, y][3])
        return out
    rng = np.random.default_rng(64)
    arr = np.array(mir).astype(np.float32)
    al = arr[:, :, 3]
    ys = np.nonzero(al.max(1) > 128)[0]
    top = int(ys[0]) if len(ys) else 0
    ny = int(neck * h)
    hair_c = _median_colour(arr, al, top + 2, top + max(12, (ny - top) // 4), w)
    cloth_c = _median_colour(arr, al, ny + (h - ny) // 5, ny + (h - ny) * 2 // 3, w)
    head = hair_c[None, None, :] * _material(headkind, h, w, rng)[:, :, None]
    body = cloth_c[None, None, :] * _material("knit", h, w, rng)[:, :, None]
    lum = np.array(mir.convert("L").filter(ImageFilter.GaussianBlur(max(3, w // 14)))).astype(np.float32)
    lum_mean = lum[al > 128].mean() if (al > 128).any() else 128
    shade = np.clip(0.97 + 0.30 * (lum / max(lum_mean, 1) - 1.0), 0.75, 1.15)[:, :, None]
    yy = np.arange(h)[:, None, None]
    bw = max(4, h // 40)
    t = np.clip((yy - (ny - bw)) / (2.0 * bw), 0, 1)
    rgb = (head * (1 - t) + body * t) * shade
    # a soft shadow under the hairline / towel and darker, rounder edges
    nape = np.exp(-((yy - ny - bw) / (1.5 * bw)) ** 2) * 0.18
    rgb *= (1.0 - nape)
    edge = np.array(Image.fromarray(al.astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(2, w // 30)))).astype(np.float32) / 255.0
    rgb *= (0.84 + 0.16 * edge)[:, :, None]
    out = np.dstack([np.clip(rgb, 0, 255), al]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def squash(img, f):
    w, h = img.size
    nw = max(2, int(w * f))
    s = img.resize((nw, h), Image.LANCZOS)
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c.paste(s, ((w - nw) // 2, 0), s)
    return c

def make_sheet(front, back, n, rows):
    if n == 1:
        return front
    frames = []
    for i in range(n):
        ang = i * 360.0 / n                     # 0 = front, 180 = back
        rel = ang if ang <= 180 else 360 - ang
        view = front if rel < 80 else back      # side-on shows the back of the head, not a squashed face
        f = 0.55 + 0.45 * abs(math.cos(math.radians(rel)))   # a card seen at an angle (never vanishes)
        v = squash(view, f)
        if ang > 180:
            v = ImageOps.mirror(v)
        frames.append(v)
    w, h = front.size
    cols = (n + rows - 1) // rows
    sheet = Image.new("RGBA", (w * cols, h * rows), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        sheet.paste(fr, ((i % cols) * w, (i // cols) * h), fr)
    return sheet

def portrait(front, neck, size=256):
    """square head-and-shoulders shot centred on the head, for the character-select grid"""
    w, h = front.size
    al = front.split()[3]
    ny = int(neck * h)
    head = al.crop((0, 0, w, ny)).point(lambda v: 255 if v > 128 else 0)
    box = head.getbbox() or (0, 0, w, ny)
    cx = (box[0] + box[2]) / 2
    side = int((ny - box[1]) * 1.35)
    y0 = max(0, box[1] - side // 14)
    x0 = int(cx - side / 2)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(front.crop((x0, y0, x0 + side, y0 + side)), (0, 0))
    return sq.resize((size, size), Image.LANCZOS)

def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "racer"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--name", required=True, help="display name (UTF-8, accents fine: \"Baby Éabha\")")
    ap.add_argument("--tagline", default="Fresh off the photo booth and ready to race.")
    ap.add_argument("--back", help="optional image of the character from behind")
    ap.add_argument("--crop", help="x0,y0,x1,y1 in photo pixels: keep head + upper body")
    ap.add_argument("--neck", type=float, default=0.45, help="neck line as a fraction of the cropped height (for the rear view)")
    ap.add_argument("--model", default="isnet-general-use", help="rembg model (isnet-general-use, u2net_human_seg, u2net ...)")
    ap.add_argument("--angles", type=int, default=16, choices=[1, 8, 16])
    ap.add_argument("--rows", type=int, default=0, help="sheet rows (default: auto, keeps the sheet <= 4096 px wide)")
    ap.add_argument("--height", type=int, default=512, help="sprite height in pixels (HD)")
    ap.add_argument("--outline", type=int, default=2, help="dark outline thickness in pixels (0 = none)")
    ap.add_argument("--fade", type=float, default=0.10, help="fade out the bottom fraction (hidden by the kart)")
    ap.add_argument("--tol", type=float, default=60, help="background colour tolerance for the fallback remover")
    ap.add_argument("--speed", type=float, default=3.5)
    ap.add_argument("--accel", type=float, default=3.5)
    ap.add_argument("--handling", type=float, default=3.5)
    ap.add_argument("--weight", choices=["light", "medium", "heavy"], default="medium")
    ap.add_argument("--voice", type=float, default=1.2, help="voice pitch of the chirps (0.6 deep .. 1.8 squeaky)")
    ap.add_argument("--size", type=float, default=1.45, help="driver height in game units")
    ap.add_argument("--seat", type=float, default=0.0, help="raise the driver in the kart (game units), e.g. 0.12 keeps a bib above the cowl")
    ap.add_argument("--kart", help="kart colour r,g,b (default: picked from the image)")
    ap.add_argument("--trim", help="trim colour r,g,b")
    ap.add_argument("--headback", default="hair", choices=["hair", "towel", "knit"], help="material for the back of the head")
    ap.add_argument("--kartstyle", default="", help="kart decoration: rattle, spa or empty")
    ap.add_argument("--quip", default="", help="victory speech bubble text, e.g. \"Car!\"")
    ap.add_argument("--quipstyle", default="", choices=["", "happy", "sleepy"], help="how the winner acts the quip out")
    ap.add_argument("--face", default="", help="face centre in the front frame as fractions x,y (bubble / Zzz anchor)")
    ap.add_argument("--winsprite", default="", help="victory-mood front frame (made by tools/make_win_sprite.py), e.g. win.png")
    ap.add_argument("--decal", default="", help="kart decal image (made by tools/make_decal.py), e.g. decal.png")
    ap.add_argument("--decalframes", type=int, default=0, help="frames stacked vertically in the decal (blinks)")
    ap.add_argument("--out", help="output folder (default assets/characters/<slug>)")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = a.out or os.path.join(root, "assets", "characters", slugify(a.name))
    os.makedirs(out, exist_ok=True)

    src = ImageOps.exif_transpose(Image.open(a.image)).convert("RGB")
    if max(src.size) > 2400:
        src.thumbnail((2400, 2400))
    cut = remove_background(src, a.tol, a.model)
    if a.crop:
        x0, y0, x1, y1 = [int(v) for v in a.crop.split(",")]
        cut = cut.crop((x0, y0, x1, y1))
    cut = keep_largest_blob(cut)
    front = polish(crop_and_scale(cut, a.height, a.fade), a.outline)
    if a.back:
        bk = ImageOps.exif_transpose(Image.open(a.back)).convert("RGB")
        back = polish(crop_and_scale(keep_largest_blob(remove_background(bk, a.tol, a.model)), a.height, a.fade), a.outline).resize(front.size, Image.LANCZOS)
    else:
        back = polish(back_view(crop_and_scale(cut, a.height, a.fade), a.neck, a.headback), a.outline)
    rows = a.rows or max(1, math.ceil(front.size[0] * a.angles / 4096))
    while a.angles % rows:
        rows += 1
    sheet = make_sheet(front, back, a.angles, rows)
    sheet.save(os.path.join(out, "sprite.png"), optimize=True)
    front.save(os.path.join(out, "preview.png"), optimize=True)
    portrait(front, a.neck).save(os.path.join(out, "portrait.png"), optimize=True)
    kart, trim = dominant_colours(front)
    if a.kart: kart = tuple(int(v) for v in a.kart.split(","))
    if a.trim: trim = tuple(int(v) for v in a.trim.split(","))
    mass = {"light": 1.5, "medium": 3.0, "heavy": 4.5}[a.weight]
    with open(os.path.join(out, "character.ini"), "w", encoding="utf-8") as f:
        f.write("; Turbo Tumble 64 character - made by tools/make_character.py (UTF-8)\n")
        f.write(f"name = {a.name}\ntagline = {a.tagline}\nweight = {a.weight}\n")
        f.write(f"speed = {a.speed}\naccel = {a.accel}\nhandling = {a.handling}\nmass = {mass}\n")
        f.write(f"kart = {kart[0]},{kart[1]},{kart[2]}\ntrim = {trim[0]},{trim[1]},{trim[2]}\n")
        f.write(f"voice = {a.voice}\nsprite = sprite.png\nangles = {a.angles}\nrows = {rows}\n")
        f.write(f"size = {a.size}\nportrait = portrait.png\n")
        if a.kartstyle: f.write(f"kartstyle = {a.kartstyle}\n")
        if a.seat: f.write(f"seat = {a.seat}\n")
        for key in ("quip", "quipstyle", "face", "winsprite", "decal"):
            if getattr(a, key): f.write(f"{key} = {getattr(a, key)}\n")
        if a.decalframes: f.write(f"decalframes = {a.decalframes}\n")
    print(f"wrote {out}  ({a.angles} angles in {rows} rows, frame {front.size[0]}x{front.size[1]}, sheet {sheet.size[0]}x{sheet.size[1]}, kart {kart}, trim {trim})")

if __name__ == "__main__":
    main()
