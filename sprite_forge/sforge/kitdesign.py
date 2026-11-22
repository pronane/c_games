"""Kit design on the tailor atlas: patterns, trim, boots, fabric and shirt lettering (v11.30).

Fed back from Arena FC.  A game tints kits at run time (any club, any colours, the character
editor), so the design is shipped as masks, not as painted kits:

    kit_pattern_<style>.png   L    where the secondary colour goes on the shirt (stripes, hoops ...)
    kit_detail.png            RGB  R trim (collar, cuffs, hems, shorts side stripe, sock bands),
                                   G boot detail (sole plate, side flash, heel), B fabric (weave,
                                   panel seams, shading) - multiply, 1.0 = flat
    kit_glyphs.png            RG   shirt lettering: R fill, G outline; GLYPHS order, GRID cells
    kit_layout.json           the panel / print rectangles (sforge.tailor.LAYOUT / PRINT), styles,
                              glyph grid - the contract a game shader reads

    from sforge import kitdesign as KD
    KD.export("out_dir")                                      # everything above
    img = KD.paint("stripes", "#d7263d", "#ffffff", "#14213d", number=10, name="NOVAK")  # preview

The lettering font is Big Shoulders Bold (SIL OFL 1.1, sforge/data/fonts).  Designs are original:
no real club's crest, sponsor or template.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .tailor import LAYOUT, PRINT, layout_json

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "data", "fonts", "BigShoulders-Bold.ttf")
STYLES = ("plain", "stripes", "hoops", "sash", "halves", "pinstripes", "chevron", "fade", "quarters", "band")
GLYPHS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.-' "
GRID = (8, 5)              # columns, rows
CELL = (96, 144)           # glyph cell (px)


def _uv(size):
    v, u = np.mgrid[0:size, 0:size].astype(np.float32)
    return (u + .5) / size, (v + .5) / size


def _in(u, v, rect):
    u0, v0, u1, v1 = rect
    return (u >= u0) & (u < u1) & (v >= v0) & (v < v1)


def _local(u, v, rect):
    u0, v0, u1, v1 = rect
    return (u - u0) / (u1 - u0), (v - v0) / (v1 - v0)


def pattern_mask(style, size=1024):
    """float [0..1] mask of the secondary colour on the shirt panels (torso + sleeves)."""
    u, v = _uv(size)
    m = np.zeros((size, size), np.float32)
    for panel in ("torso_front", "torso_back", "sleeve_L", "sleeve_R"):
        r = LAYOUT[panel]
        inside = _in(u, v, r)
        lu, lv = _local(u, v, r)
        torso = panel.startswith("torso")
        if style == "stripes":
            val = (np.floor(lu * (7 if torso else 4)) % 2 == 1)
        elif style == "pinstripes":
            val = (np.abs(((lu * (14 if torso else 8)) % 1) - .5) < .06)
        elif style == "hoops":
            val = (np.floor(lv * (7 if torso else 3)) % 2 == 1)
        elif style == "sash":
            # player's right shoulder to left hip on the front, mirrored so it wraps round the back
            d = (lu - lv * .9) if panel == "torso_front" else (1 - lu - lv * .9)
            val = (np.abs(d - .05) < .13) if torso else np.zeros_like(lu, bool)
        elif style == "halves":
            val = (lu < .5) if panel == "torso_front" else (lu >= .5) if torso else (panel == "sleeve_R")
            val = np.broadcast_to(val, lu.shape)
        elif style == "quarters":
            val = ((lu < .5) ^ (lv > .5)) if torso else np.broadcast_to(panel == "sleeve_L", lu.shape)
        elif style == "chevron":
            val = (np.abs(lv - .28 - np.abs(lu - .5) * .55) < .07) if torso else np.zeros_like(lu, bool)
        elif style == "band":
            val = (np.abs(lv - .38) < .07) if torso else np.zeros_like(lu, bool)
        elif style == "fade":
            # a smooth gradient: a dithered one shimmers (moire) on a moving shirt
            val = np.clip((lv - .35) / .6, 0, 1) ** 1.3 if torso else np.zeros_like(lu)
        else:
            val = np.zeros_like(lu, bool)
        m[inside] = np.asarray(val, np.float32)[inside]
    return m


def detail(size=1024, seed=7):
    """RGB float: R trim, G boot detail, B fabric multiply."""
    u, v = _uv(size)
    trim = np.zeros((size, size), np.float32)
    boot = np.zeros((size, size), np.float32)
    fab = np.ones((size, size), np.float32)
    for panel in ("torso_front", "torso_back"):
        r = LAYOUT[panel]
        lu, lv = _local(u, v, r)
        ins = _in(u, v, r)
        neck = (np.abs(lu - .5) < .17) & (lv < .055)
        if panel == "torso_front":                       # a V of trim at the throat
            neck |= (np.abs(lu - .5) < .09 - lv * .9) & (lv < .09)
        trim[ins & neck] = 1
        # side panels under the arms and a seam down each side
        side = (lu < .05) | (lu > .95)
        trim[ins & side] = .65
        seam = (np.abs(lu - .05) < .004) | (np.abs(lu - .95) < .004)
        fab[ins & seam] *= .82
    for panel in ("sleeve_L", "sleeve_R"):
        r = LAYOUT[panel]
        lu, lv = _local(u, v, r)
        ins = _in(u, v, r)
        trim[ins & (lv > .86)] = 1                        # cuff
        fab[ins & (np.abs(lv - .86) < .006)] *= .8
    for panel in ("shorts_L", "shorts_R"):
        r = LAYOUT[panel]
        lu, lv = _local(u, v, r)
        ins = _in(u, v, r)
        trim[ins & (lv > .93)] = 1                        # hem
        trim[ins & (np.abs(lu - .25) < .025)] = 1         # stripe down the outside of the leg (u=.25 is outward)
        trim[ins & (lv < .05)] = .5                       # waistband
    for panel in ("socks_L", "socks_R"):
        r = LAYOUT[panel]
        lu, lv = _local(u, v, r)
        ins = _in(u, v, r)
        trim[ins & ((lv < .07) | ((lv > .12) & (lv < .17)))] = 1
        fab[ins & (lv < .07)] *= .9                        # ribbed turnover
    for panel in ("boots_L", "boots_R"):
        r = LAYOUT[panel]
        lu, lv = _local(u, v, r)
        ins = _in(u, v, r)
        sole = lv > .82
        flash = (np.abs(lv - .55 + (lu - .5) * .5) < .06) & (lu > .25) & (lu < .8)
        heel = (lu < .18) & (lv > .35)
        boot[ins & sole] = 1.0
        boot[ins & flash] = .66
        boot[ins & heel] = .33
        fab[ins] *= .95 + .05 * np.sin(lu[ins] * 90)      # stitched upper
    # knitted fabric: a fine weave plus soft large-scale variation (reads as cloth at TV distance)
    rng = np.random.default_rng(seed)
    weave = .97 + .03 * np.sign(np.sin(u * size * 1.6) * np.sin(v * size * 1.6))
    noise = rng.random((size // 16, size // 16)).astype(np.float32)
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC), np.float32) / 255
    clothy = np.ones_like(fab)
    for panel in ("torso_front", "torso_back", "sleeve_L", "sleeve_R", "shorts_L", "shorts_R", "socks_L", "socks_R"):
        ins = _in(u, v, LAYOUT[panel])
        clothy[ins] = weave[ins] * (.94 + .06 * noise[ins])
    fab *= clothy
    return np.stack([trim, boot, np.clip(fab, 0, 1)], -1)


def glyph_atlas(font_path=FONT):
    """RG8: R glyph fill, G outline (fill dilated), cells in GLYPHS order on GRID."""
    W, H = GRID[0] * CELL[0], GRID[1] * CELL[1]
    fill = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(fill)
    font = ImageFont.truetype(font_path, int(CELL[1] * .86))
    for i, ch in enumerate(GLYPHS):
        cx, cy = (i % GRID[0]) * CELL[0], (i // GRID[0]) * CELL[1]
        if ch == " ":
            continue
        bb = d.textbbox((0, 0), ch, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx + (CELL[0] - w) / 2 - bb[0], cy + (CELL[1] - h) / 2 - bb[1]), ch, fill=255, font=font)
    outline = fill.filter(ImageFilter.MaxFilter(9))
    return Image.merge("RGB", (fill, outline, Image.new("L", (W, H), 0)))


def glyph_index(text):
    return [GLYPHS.index(c) if c in GLYPHS else GLYPHS.index(" ") for c in text.upper()]


def export(out_dir, size=1024, styles=STYLES):
    os.makedirs(out_dir, exist_ok=True)
    for st in styles:
        Image.fromarray((pattern_mask(st, size) * 255).astype(np.uint8), "L").save(
            os.path.join(out_dir, "kit_pattern_%s.png" % st), optimize=True)
    det = detail(size)
    Image.fromarray((det * 255).astype(np.uint8), "RGB").save(os.path.join(out_dir, "kit_detail.png"), optimize=True)
    glyph_atlas().save(os.path.join(out_dir, "kit_glyphs.png"), optimize=True)
    lay = layout_json()
    lay.update({"styles": list(styles), "glyphs": GLYPHS, "glyph_grid": list(GRID), "glyph_cell": list(CELL),
                "font": "Big Shoulders Bold (SIL OFL 1.1)",
                "channels": {"pattern": "L: secondary colour on shirt panels",
                             "detail": "R trim, G boot detail (1 sole, .66 flash, .33 heel), B fabric multiply",
                             "glyphs": "R fill, G outline"}})
    with open(os.path.join(out_dir, "kit_layout.json"), "w") as f:
        json.dump(lay, f, indent=1)
    return lay


def _hex(c):
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def paint(style, primary, secondary, trim, shorts="#ffffff", socks="#ffffff", boots="#111111",
          boot_detail="#e8e8e8", number=None, name="", size=1024):
    """A painted atlas (PIL RGB) - the same maths a game shader runs, for previews and offline kits."""
    u, v = _uv(size)
    pm = pattern_mask(style, size)[..., None]
    det = detail(size)
    base = np.zeros((size, size, 3), np.float32)
    shirt = _in(u, v, (0, 0, 1, .5)) | _in(u, v, (0, .5, .5, .75))
    col = _hex(primary) * (1 - pm) + _hex(secondary) * pm
    base[shirt] = col[shirt]
    base[_in(u, v, (.5, .5, 1, .75))] = _hex(shorts)
    base[_in(u, v, (0, .75, .5, 1))] = _hex(socks)
    bt = _in(u, v, (.5, .75, 1, 1))
    base[bt] = _hex(boots)
    tr = det[..., 0:1]
    base = base * (1 - tr) + _hex(trim) * tr
    bd = det[..., 1:2] * bt[..., None]
    base = base * (1 - (bd > 0)) + _hex(boot_detail) * (bd > 0)
    base *= det[..., 2:3]
    img = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8), "RGB")
    if number is not None or name:
        g = glyph_atlas()
        def stamp(text, rect, h_frac=1.0):
            idx = glyph_index(text)
            u0, v0, u1, v1 = rect
            pw, ph = (u1 - u0) * size, (v1 - v0) * size
            cw = min(pw / max(len(idx), 1), ph * CELL[0] / CELL[1])
            x = u0 * size + (pw - cw * len(idx)) / 2
            for k in idx:
                cell = g.crop(((k % GRID[0]) * CELL[0], (k // GRID[0]) * CELL[1],
                               (k % GRID[0] + 1) * CELL[0], (k // GRID[0] + 1) * CELL[1]))
                cell = cell.resize((max(1, int(cw)), max(1, int(ph))), Image.BILINEAR)
                fill, out, _ = cell.split()
                img.paste(Image.new("RGB", cell.size, trim), (int(x), int(v0 * size)), out)
                img.paste(Image.new("RGB", cell.size, secondary if style == "plain" else "#ffffff"), (int(x), int(v0 * size)), fill)
                x += cw
        if name:
            stamp(name, PRINT["back_name"])
        if number is not None:
            stamp(str(number), PRINT["back_number"])
            stamp(str(number), PRINT["front_number"])
            stamp(str(number), PRINT["shorts_number"])
    return img
