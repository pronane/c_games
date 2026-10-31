"""Side-by-side comparison of HD Fighter sprite sets (portrait vs. any number of renderers) and a stage lineup.

    python3 tools/compare_hd.py --portraits ../HD_Fighter/assets_hd/select \
        --set "Blender=/tmp/bl/{c}_{s}.png" --set "Forge=/tmp/forge/{c}/strips/{s}.png" --out /tmp/cmp

Writes compare_<char>.png (portrait + key frames per renderer), compare_all.png and lineup_<set>.png (the six
fighters on a game stage at the game's own scale, 1.4x, feet on GROUND_Y=560)."""
from __future__ import annotations
import argparse, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CHARS = ["kairo", "lyra", "naomi", "brutus", "void", "zap"]
KEY = [("idle", 0), ("walk", 2), ("hp", 1), ("hk", 1), ("special1", 1), ("special2", 1), ("super", 1), ("win", 1)]
STAGE = "../HD_Fighter/assets_hd/stages/stage_%s_%s.png"


def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def frame(path, i, fw=192):
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGBA")
    n = max(1, im.width // fw)
    i = min(i, n - 1)
    return im.crop((i * fw, 0, (i + 1) * fw, im.height))


def checker(w, h, a=(58, 60, 70), b=(66, 68, 80), s=16):
    im = Image.new("RGBA", (w, h), a + (255,))
    d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range((y // s % 2) * s, w, 2 * s):
            d.rectangle([x, y, x + s - 1, y + s - 1], fill=b + (255,))
    return im


def compare_char(c, portraits, sets, out):
    lab = 120
    W = lab + 256 + 8 + len(KEY) * 192
    H = 26 + 256 * len(sets)
    im = Image.new("RGBA", (W, H), (30, 30, 38, 255))
    d = ImageDraw.Draw(im)
    d.text((lab, 4), "portrait", font=font(14), fill=(230, 230, 230))
    for k, (s, i) in enumerate(KEY):
        d.text((lab + 264 + k * 192 + 4, 4), "%s %d" % (s, i), font=font(14), fill=(230, 230, 230))
    p = Image.open(os.path.join(portraits, "portrait_%s.png" % c)).convert("RGBA").resize((256, 256), Image.LANCZOS)
    im.paste(p, (lab, 26))
    for r, (name, pat) in enumerate(sets):
        y = 26 + r * 256
        d.text((6, y + 110), name, font=font(16), fill=(255, 220, 120))
        row = checker(len(KEY) * 192, 256)
        for k, (s, i) in enumerate(KEY):
            f = frame(pat.format(c=c, s=s), i)
            if f is not None:
                row.alpha_composite(f, (k * 192, 0))
        im.paste(row, (lab + 264, y))
    im.save(os.path.join(out, "compare_%s.png" % c))
    return im


def lineup(name, pat, out, stage="temple", state="idle", fi=0, scale=1.4):
    bg = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    for layer in ("bg", "mid"):
        pth = STAGE % (stage, layer)
        if os.path.exists(pth):
            bg.alpha_composite(Image.open(pth).convert("RGBA").resize((1280, 720)))
    xs = [150, 345, 540, 740, 935, 1130]
    for k, c in enumerate(CHARS):
        f = frame(pat.format(c=c, s=state), fi)
        if f is None:
            continue
        sw, sh = int(192 * scale), int(256 * scale)
        f = f.resize((sw, sh), Image.LANCZOS)
        if k >= 3:
            f = f.transpose(Image.FLIP_LEFT_RIGHT)
        sh_a = f.getchannel("A").filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.6))
        shadow = Image.new("RGBA", f.size, (0, 0, 0, 0)); shadow.putalpha(sh_a)
        x = int(xs[k] - sw / 2); y = int(560 - sh + 12)
        bg.alpha_composite(shadow, (x + 3, y + 4))
        bg.alpha_composite(f, (x, y))
    pth = STAGE % (stage, "fg")
    if os.path.exists(pth):
        bg.alpha_composite(Image.open(pth).convert("RGBA").resize((1280, 720)))
    d = ImageDraw.Draw(bg)
    d.text((16, 12), name, font=font(28), fill=(255, 230, 140))
    bg.convert("RGB").save(os.path.join(out, "lineup_%s.png" % name.lower().replace(" ", "_")))
    return bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portraits", required=True)
    ap.add_argument("--set", action="append", required=True, help="Name=path pattern with {c} and {s}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", default="temple")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sets = [tuple(x.split("=", 1)) for x in a.set]
    rows = [compare_char(c, a.portraits, sets, a.out) for c in CHARS]
    W = max(r.width for r in rows); H = sum(r.height for r in rows)
    allim = Image.new("RGBA", (W, H), (30, 30, 38, 255))
    y = 0
    for r in rows:
        allim.paste(r, (0, y)); y += r.height
    allim.convert("RGB").save(os.path.join(a.out, "compare_all.png"))
    for name, pat in sets:
        lineup(name, pat, a.out, a.stage)


if __name__ == "__main__":
    main()
