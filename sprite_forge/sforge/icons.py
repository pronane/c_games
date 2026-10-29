"""v8 UI icons, drawn procedurally with Pillow (no image files to ship, no licences to track).
icon(name, size=20) -> PIL RGBA image;  tk_icon(name, size) -> cached ImageTk.PhotoImage (needs a Tk root)."""
from __future__ import annotations
from PIL import Image, ImageDraw

BLUE, GREEN, ORANGE, RED, PURPLE, GREY, DARK = "#1a5fb4", "#26a269", "#e66100", "#c01c28", "#813d9c", "#77767b", "#241f31"
_cache = {}


def _person(d, s, col, x=0.5):
    cx = s * x
    d.ellipse([cx - s * .11, s * .08, cx + s * .11, s * .30], fill=col)
    d.rounded_rectangle([cx - s * .17, s * .33, cx + s * .17, s * .66], radius=s * .06, fill=col)
    d.line([cx - s * .08, s * .64, cx - s * .12, s * .92], fill=col, width=max(2, int(s * .09)))
    d.line([cx + s * .08, s * .64, cx + s * .12, s * .92], fill=col, width=max(2, int(s * .09)))


def _draw(name, s):
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    w = max(2, s // 12)
    if name == "photo":
        d.rounded_rectangle([s * .06, s * .22, s * .94, s * .86], radius=s * .1, fill=BLUE)
        d.rectangle([s * .3, s * .12, s * .55, s * .24], fill=BLUE)
        d.ellipse([s * .3, s * .32, s * .7, s * .76], fill="white"); d.ellipse([s * .39, s * .41, s * .61, s * .67], fill=BLUE)
    elif name == "video":
        d.rounded_rectangle([s * .04, s * .24, s * .68, s * .78], radius=s * .08, fill=RED)
        d.polygon([(s * .7, s * .5), (s * .96, s * .26), (s * .96, s * .76)], fill=RED)
    elif name == "frames":
        for i, c in enumerate((GREY, BLUE, GREEN)):
            o = i * s * .14
            d.rectangle([s * .06 + o, s * .14 + o, s * .58 + o, s * .62 + o], fill=c, outline="white")
    elif name == "mannequin":
        _person(d, s, ORANGE)
    elif name == "library":
        for i, c in enumerate((BLUE, PURPLE, GREEN, ORANGE)):
            d.rectangle([s * (.08 + i * .22), s * .14, s * (.24 + i * .22), s * .86], fill=c)
        d.line([s * .04, s * .9, s * .96, s * .9], fill=DARK, width=w)
    elif name == "spec":
        d.rounded_rectangle([s * .16, s * .06, s * .84, s * .94], radius=s * .06, fill="white", outline=GREY, width=w)
        for i in range(4):
            d.line([s * .28, s * (.26 + i * .17), s * (.72 - (i % 2) * .16), s * (.26 + i * .17)], fill=BLUE, width=w)
    elif name == "hd":
        n = 3
        for i in range(n):
            for j in range(2):
                x0, y0 = s * (.04 + i * .32), s * (.14 + j * .38)
                d.rectangle([x0, y0, x0 + s * .28, y0 + s * .34], fill="#deddda", outline=GREY)
                _mini(d, x0 + s * .14, y0 + s * .04, s * .3, [BLUE, GREEN, ORANGE][i])
    elif name == "retro":
        px = s // 8 or 1
        pat = ["..XXXX..", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX", "XX.XX.XX", ".X....X.", "X.X..X.X", "........"]
        for j, row in enumerate(pat):
            for i, ch in enumerate(row):
                if ch == "X":
                    d.rectangle([i * px, j * px, i * px + px - 1, j * px + px - 1], fill=GREEN if j < 4 else PURPLE)
    elif name == "3d":
        a, b, c, e = (s * .5, s * .08), (s * .92, s * .3), (s * .5, s * .52), (s * .08, s * .3)
        d.polygon([a, b, c, e], fill="#99c1f1")
        d.polygon([e, c, (s * .5, s * .94), (s * .08, s * .72)], fill=BLUE)
        d.polygon([c, b, (s * .92, s * .72), (s * .5, s * .94)], fill="#1c3f6e")
    elif name == "turn":
        d.arc([s * .1, s * .1, s * .9, s * .9], 200, 500, fill=ORANGE, width=w + 1)
        d.polygon([(s * .82, s * .06), (s * .96, s * .34), (s * .66, s * .3)], fill=ORANGE)
        _mini(d, s * .5, s * .26, s * .5, BLUE)
    elif name == "help":
        d.ellipse([s * .06, s * .06, s * .94, s * .94], fill=BLUE)
        d.text((s * .36, s * .14), "?", fill="white", font=_font(int(s * .7)))
    elif name == "build":
        d.polygon([(s * .1, s * .9), (s * .5, s * .5), (s * .6, s * .6), (s * .2, s * 1.0)], fill=GREY)
        d.rounded_rectangle([s * .4, s * .08, s * .94, s * .4], radius=s * .05, fill=DARK)
        d.line([s * .62, s * .4, s * .38, s * .66], fill="#986a44", width=w + 2)
    elif name == "start":
        d.ellipse([s * .06, s * .06, s * .94, s * .94], fill=GREEN)
        d.polygon([(s * .38, s * .26), (s * .76, s * .5), (s * .38, s * .74)], fill="white")
    elif name == "preview":
        d.ellipse([s * .04, s * .26, s * .96, s * .74], fill=PURPLE)
        d.ellipse([s * .32, s * .3, s * .68, s * .7], fill="white"); d.ellipse([s * .42, s * .4, s * .58, s * .6], fill=DARK)
    elif name == "folder":
        d.rectangle([s * .06, s * .18, s * .44, s * .34], fill="#c88800")
        d.rectangle([s * .06, s * .28, s * .94, s * .84], fill="#f6d32d")
    elif name == "game":
        d.rounded_rectangle([s * .04, s * .26, s * .96, s * .78], radius=s * .2, fill=DARK)
        d.line([s * .2, s * .52, s * .4, s * .52], fill="white", width=w); d.line([s * .3, s * .42, s * .3, s * .62], fill="white", width=w)
        d.ellipse([s * .62, s * .38, s * .74, s * .5], fill=RED); d.ellipse([s * .74, s * .52, s * .86, s * .64], fill=GREEN)
    elif name == "move":
        _mini(d, s * .5, s * .1, s * .85, ORANGE)
        d.line([s * .1, s * .5, s * .3, s * .5], fill=GREY, width=w); d.line([s * .05, s * .65, s * .25, s * .65], fill=GREY, width=w)
    else:
        d.ellipse([s * .2, s * .2, s * .8, s * .8], fill=GREY)
    return im


def _mini(d, cx, y0, h, col):
    r = h * .14
    d.ellipse([cx - r, y0, cx + r, y0 + 2 * r], fill=col)
    d.rectangle([cx - h * .14, y0 + 2.2 * r, cx + h * .14, y0 + h * .62], fill=col)
    d.line([cx - h * .07, y0 + h * .6, cx - h * .14, y0 + h * .95], fill=col, width=max(1, int(h * .1)))
    d.line([cx + h * .07, y0 + h * .6, cx + h * .14, y0 + h * .95], fill=col, width=max(1, int(h * .1)))


def _font(px):
    from PIL import ImageFont
    for f in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            pass
    return ImageFont.load_default()


NAMES = ["photo", "video", "frames", "mannequin", "library", "spec", "hd", "retro", "3d", "turn", "help", "build", "start",
         "preview", "folder", "game", "move"]


def icon(name, size=20):
    big = _draw(name, size * 4)   # supersample for smooth edges
    return big.resize((size, size), Image.LANCZOS) if name != "retro" else big.resize((size, size), Image.NEAREST)


def tk_icon(name, size=20):
    k = (name, size)
    if k not in _cache:
        from PIL import ImageTk
        _cache[k] = ImageTk.PhotoImage(icon(name, size))
    return _cache[k]


def sheet(path, size=48):
    """All icons in one strip (for the README / tests)."""
    im = Image.new("RGBA", (len(NAMES) * (size + 8), size + 8), (255, 255, 255, 255))
    for i, n in enumerate(NAMES):
        ic = icon(n, size); im.alpha_composite(ic, (i * (size + 8) + 4, 4))
    im.save(path)
    return path
