"""Turf for field sports: line markings, mowing patterns and wear as masks (v11.33, fed back from Arena FC).

Arena FC drew one stripe pattern with soccer lines hard-coded in its shader.  A broadcast pitch is cut in a
pattern the groundsman chose (stripes, checkerboard, diagonals, rings round the centre spot), worn where play
concentrates (goalmouths, the centre circle, the assistants' channels down the touchlines), and marked for the
sport being played.  This writes those as one RGB texture a turf shader reads:

    R  line markings (1 = paint)            for SPORTS: soccer, gaelic / hurling, rugby
    G  mowing direction mask (0 / 1 bands, a game shades the two directions lighter / darker)
    B  wear (0 lush .. 1 bare)

    from sforge import pitch as P
    P.export("pitch_soccer_stripes.png", sport="soccer", mow="stripes")
    P.MOW                                   # stripes, checker, diagonal, rings, wide_stripes

The texture covers the playing area plus a run-off margin (`MARGIN` m); `layout(sport)` gives the world
extent so a shader maps world x / z to UV.  Units are metres; the long axis is x.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

from .stadium import PITCH

MARGIN = 4.0
PX_PER_M = 24.0
MOW = ("stripes", "checker", "diagonal", "rings", "wide_stripes")
SPORTS = ("soccer", "gaelic", "hurling", "rugby")


def layout(sport):
    hl, hw = PITCH[sport]
    W = int(round((2 * (hl + MARGIN)) * PX_PER_M))
    H = int(round((2 * (hw + MARGIN)) * PX_PER_M))
    return {"half": [hl, hw], "margin": MARGIN, "size_px": [W, H], "extent": [hl + MARGIN, hw + MARGIN]}


class _Painter:
    def __init__(self, sport, line_w=.12):
        self.L = layout(sport)
        self.W, self.H = self.L["size_px"]
        self.ex, self.ez = self.L["extent"]
        self.img = Image.new("L", (self.W, self.H), 0)
        self.d = ImageDraw.Draw(self.img)
        self.lw = max(2, int(round(line_w * PX_PER_M)))

    def px(self, x, z):
        return ((x + self.ex) * PX_PER_M, (z + self.ez) * PX_PER_M)

    def line(self, x0, z0, x1, z1, dash=None):
        if dash:
            L = math.hypot(x1 - x0, z1 - z0)
            n = int(L / (2 * dash))
            for k in range(n + 1):
                a, b = 2 * k * dash / L, min(1, (2 * k + 1) * dash / L)
                self.d.line([self.px(x0 + (x1 - x0) * a, z0 + (z1 - z0) * a), self.px(x0 + (x1 - x0) * b, z0 + (z1 - z0) * b)],
                            fill=255, width=self.lw)
            return
        self.d.line([self.px(x0, z0), self.px(x1, z1)], fill=255, width=self.lw)

    def rect(self, x0, z0, x1, z1):
        for a, b in (((x0, z0), (x1, z0)), ((x1, z0), (x1, z1)), ((x1, z1), (x0, z1)), ((x0, z1), (x0, z0))):
            self.line(*a, *b)

    def arc(self, cx, cz, r, a0=0, a1=360):
        # Pillow paints an arc's width inwards from its box: grow the box by half a line so the paint is
        # centred on the true radius (the centre circle is 9.15 m to the middle of the line)
        h = self.lw / 2 / PX_PER_M
        x0, z0 = self.px(cx - r - h, cz - r - h)
        x1, z1 = self.px(cx + r + h, cz + r + h)
        self.d.arc([x0, z0, x1, z1], a0, a1, fill=255, width=self.lw)

    def spot(self, x, z, r=.11):
        x0, z0 = self.px(x - r, z - r)
        x1, z1 = self.px(x + r, z + r)
        self.d.ellipse([x0, z0, x1, z1], fill=255)


def markings(sport="soccer"):
    """float mask of the painted lines for the sport."""
    p = _Painter(sport)
    hl, hw = PITCH[sport]
    p.rect(-hl, -hw, hl, hw)
    if sport == "soccer":
        p.line(0, -hw, 0, hw)
        p.arc(0, 0, 9.15)
        p.spot(0, 0, .15)
        for s in (-1, 1):
            gx = s * hl
            p.rect(min(gx, gx - s * 16.5), -20.16, max(gx, gx - s * 16.5), 20.16)
            p.rect(min(gx, gx - s * 5.5), -9.16, max(gx, gx - s * 5.5), 9.16)
            px = gx - s * 11
            p.spot(px, 0, .15)
            # the D: the arc of radius 9.15 round the spot, outside the box
            ang = math.degrees(math.acos(5.5 / 9.15))
            if s > 0:
                p.arc(px, 0, 9.15, 180 - ang, 180 + ang)
            else:
                p.arc(px, 0, 9.15, -ang, ang)
            for cz in (-1, 1):
                a0 = {(1, 1): 180, (1, -1): 90, (-1, 1): 270, (-1, -1): 0}[(s, cz)]
                p.arc(gx, cz * hw, 1.0, a0, a0 + 90)
    elif sport in ("gaelic", "hurling"):
        # 13 m, 20 m, 45 m (hurling 65 m) lines from each end, the halfway line, the small and large rectangles,
        # the arc of radius 13 m beyond the 20 m line
        p.line(0, -hw, 0, hw)
        for s in (-1, 1):
            gx = s * hl
            for dist in ((13, 20, 45) if sport == "gaelic" else (13, 20, 65)):
                p.line(gx - s * dist, -hw, gx - s * dist, hw)
            p.rect(min(gx, gx - s * 4.5), -3.25 - 3, max(gx, gx - s * 4.5), 3.25 + 3)
            p.rect(min(gx, gx - s * 13), -9.5, max(gx, gx - s * 13), 9.5)
            cx = gx - s * 20
            p.arc(cx, 0, 13, 90 if s > 0 else -90, 270 if s > 0 else 90)
            p.spot(gx - s * 11, 0, .15)
        p.line(-.5, 0, .5, 0)
    elif sport == "rugby":
        p.line(0, -hw, 0, hw)
        for s in (-1, 1):
            gx = s * hl
            p.line(gx - s * 22, -hw, gx - s * 22, hw)
            p.line(s * 10, -hw, s * 10, hw, dash=1.0)
            p.line(gx - s * 5, -hw, gx - s * 5, hw, dash=1.0)
            p.line(gx + s * 10, -hw, gx + s * 10, hw)       # dead-ball line inside the margin's reach
        for z in (-hw + 5, -hw + 15, hw - 15, hw - 5):
            p.line(-hl, z, hl, z, dash=1.0)
    return np.asarray(p.img, np.float32) / 255


def mowing(sport="soccer", style="stripes"):
    """0 / 1 bands of the two mowing directions."""
    L = layout(sport)
    W, H = L["size_px"]
    ex, ez = L["extent"]
    hl, hw = L["half"]
    z, x = np.mgrid[0:H, 0:W].astype(np.float32)
    x = x / PX_PER_M - ex
    z = z / PX_PER_M - ez
    band = (2 * hl) / 16.0                    # 16 stripes goal line to goal line (FIFA-style 5-6 m)
    if style == "stripes":
        m = np.floor((x + hl) / band) % 2
    elif style == "wide_stripes":
        m = np.floor((x + hl) / (band * 2)) % 2
    elif style == "checker":
        m = (np.floor((x + hl) / band) + np.floor((z + hw) / band)) % 2
    elif style == "diagonal":
        m = np.floor((x + z) / (band * .9)) % 2
    elif style == "rings":
        r = np.hypot(x, z)
        m = np.where(r < 9.15 * 2.2, np.floor(r / (band * .6)) % 2, np.floor((x + hl) / band) % 2)
    else:
        m = np.zeros_like(x)
    return m.astype(np.float32)


def wear(sport="soccer", seed=3):
    """0..1 wear: goalmouths, the centre spot, the penalty spots, the assistants' channels down the touchlines,
    soft noise so it never looks stencilled."""
    L = layout(sport)
    W, H = L["size_px"]
    ex, ez = L["extent"]
    hl, hw = L["half"]
    z, x = np.mgrid[0:H, 0:W].astype(np.float32)
    x = x / PX_PER_M - ex
    z = z / PX_PER_M - ez
    w = np.zeros_like(x)
    for s in (-1, 1):
        gx = s * hl
        w = np.maximum(w, np.exp(-(((x - gx + s * 3.5) / 4.2) ** 2 + (z / 4.8) ** 2)))           # goalmouth
        w = np.maximum(w, .55 * np.exp(-(((x - gx + s * 11) / 1.4) ** 2 + (z / 1.4) ** 2)))     # penalty spot
        w = np.maximum(w, .35 * np.exp(-(((x - gx + s * 16) / 9) ** 2 + (z / 10) ** 2)))        # edge of the box
        # assistant's channel: just outside the touchline, the half he runs
        w = np.maximum(w, .6 * np.exp(-((z - s * (hw + 1.2)) / .7) ** 2) * (x * s > 0))
    w = np.maximum(w, .45 * np.exp(-((x / 3.0) ** 2 + (z / 3.0) ** 2)))                         # centre spot
    rng = np.random.default_rng(seed)
    n = rng.random((H // 32 + 2, W // 32 + 2)).astype(np.float32)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
    w = np.clip(w * (.65 + .7 * n), 0, 1)
    return w


def texture(sport="soccer", mow="stripes"):
    m = markings(sport)
    g = mowing(sport, mow)
    b = wear(sport)
    return Image.fromarray((np.stack([m, g, b], -1) * 255).astype(np.uint8), "RGB")


def export(path, sport="soccer", mow="stripes"):
    img = texture(sport, mow)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, optimize=True)
    meta = dict(layout(sport), sport=sport, mow=mow, channels="R markings, G mowing band, B wear", version="11.33")
    with open(os.path.splitext(path)[0] + ".json", "w") as f:
        json.dump(meta, f, indent=1)
    return meta
