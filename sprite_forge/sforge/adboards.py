"""Pitch-side LED board artwork (v11.32, fed back from Arena FC).

Arena FC's boards read "GODOT 4.7" and "GLB EXPORT" over plain stripes.  This draws a strip of original,
fictional sponsor panels (and a few match messages) for an LED-board shader to scroll and cut between:

    from sforge import adboards as AB
    AB.atlas("ad_boards.png")      # rows of panels, one panel per row, PANEL px each
    AB.SPONSORS                    # the names on it, in row order

All names and marks are invented for Arena FC / Sprite Forge (no real brand); the lettering is Big Shoulders
Bold (SIL OFL 1.1).  Rows: the shader picks a row per board segment and scrolls it horizontally.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from .kitdesign import FONT

PANEL = (1024, 96)
# (text, background, foreground, mark) - mark: a simple original logo shape drawn left of the text
SPONSORS = [
    ("SPRITE FORGE", "#0b1020", "#7dd3fc", "anvil"),
    ("ARENA FC", "#d7263d", "#ffffff", "ball"),
    ("KESTRAVA BANK", "#0f3d2e", "#e8f5e9", "wing"),
    ("VOLTARA ENERGY", "#111827", "#facc15", "bolt"),
    ("AERONOVA AIR", "#1e3a8a", "#ffffff", "wing"),
    ("LUMORA MOBILE", "#6d28d9", "#f5f3ff", "ring"),
    ("QUILLBY BOOKS", "#f8fafc", "#111827", "quill"),
    ("FAIR PLAY  RESPECT", "#16a34a", "#ffffff", "hands"),
]


def _mark(d, kind, x, y, h, col):
    s = h
    if kind == "ball":
        d.ellipse((x, y, x + s, y + s), outline=col, width=max(2, s // 12))
        d.regular_polygon((x + s / 2, y + s / 2, s / 5), 5, fill=col)
    elif kind == "bolt":
        d.polygon([(x + s * .55, y), (x + s * .15, y + s * .58), (x + s * .45, y + s * .58), (x + s * .3, y + s),
                   (x + s * .85, y + s * .38), (x + s * .55, y + s * .38)], fill=col)
    elif kind == "wing":
        for k in range(3):
            d.polygon([(x, y + s * (.3 + k * .2)), (x + s * (1 - k * .18), y + s * (.1 + k * .2)),
                       (x + s * (.9 - k * .18), y + s * (.22 + k * .2))], fill=col)
    elif kind == "ring":
        d.ellipse((x, y, x + s, y + s), outline=col, width=max(3, s // 7))
        d.ellipse((x + s * .38, y + s * .38, x + s * .62, y + s * .62), fill=col)
    elif kind == "anvil":
        d.polygon([(x, y + s * .25), (x + s, y + s * .25), (x + s * .8, y + s * .5), (x + s * .62, y + s * .5),
                   (x + s * .7, y + s * .85), (x + s * .3, y + s * .85), (x + s * .38, y + s * .5), (x + s * .15, y + s * .45)],
                  fill=col)
    elif kind == "quill":
        d.polygon([(x + s * .1, y + s), (x + s * .9, y), (x + s * .55, y + s * .55)], fill=col)
    elif kind == "hands":
        d.ellipse((x, y + s * .2, x + s * .6, y + s * .8), fill=col)
        d.ellipse((x + s * .4, y + s * .2, x + s, y + s * .8), outline=col, width=max(3, s // 8))


def panel(text, bg, fg, mark, size=PANEL):
    W, H = size
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, int(H * .7))
    bb = d.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    mh = int(H * .62)
    total = mh + H * .25 + tw
    x0 = (W - total) / 2
    _mark(d, mark, x0, (H - mh) / 2, mh, fg)
    d.text((x0 + mh + H * .25 - bb[0], (H - th) / 2 - bb[1]), text, font=font, fill=fg)
    return im


def atlas(path=None, rows=None):
    rows = rows or SPONSORS
    W, H = PANEL
    im = Image.new("RGB", (W, H * len(rows)))
    for k, (t, bg, fg, mk) in enumerate(rows):
        im.paste(panel(t, bg, fg, mk), (0, k * H))
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        im.save(path, optimize=True)
    return im
