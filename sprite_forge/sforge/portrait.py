"""v11.23 portraits: a head-and-shoulders picture of a built character, for a fighter select screen, a team sheet or
a HUD - and the select screen / team sheet themselves.

The portrait is rendered from the character's own 3D model (model.glb - the mannequin, a library rig or a capture),
three-quarter view, from the top of the head to mid-chest. A build without a model falls back to a crop of its idle
sprite, scaled up (soft, and said so in the result).
"""
from __future__ import annotations
import json
import os

import numpy as np
from PIL import Image, ImageDraw

BG = (28, 32, 40, 255)


def _bust_box(rig, W):
    """(top_y, bottom_y, centre_x, centre_z) in metres for the head-and-shoulders crop of pose W"""
    P = rig.skin(W)
    top = float(P[:, 1].max())
    h = max(0.3, top - float(P[:, 1].min()))
    names = [b.lower() for b in rig.bones]

    def bone(*keys):
        for k in keys:
            for i, n in enumerate(names):
                if n == k or n.endswith(k):
                    return W[i, :3, 3]
        return None
    head = bone("head")
    if head is None:
        near = P[P[:, 1] > top - 0.15 * h]
        head = near.mean(0)
    span = 0.36 * h                                     # top of the head to mid-chest is ~36% of standing height
    return top + 0.04 * h, top - span, float(head[0]), float(head[2]), h


def render_portrait(rig, size=(256, 320), yaw=25.0, clip=None, t=0.0, bg=BG):
    """head and shoulders of a Rig (sforge.rigrec) -> RGBA image of `size`"""
    from .render import RenderSettings
    from .rig import HEIGHT
    if clip is None:
        clip = next((c for c in ("idle", "fight_idle", "idle_fighting") if c in rig.clips), None)
    W = rig.worlds(clip, t) if clip else rig.bind
    top, bottom, cx, cz, h = _bust_box(rig, W)
    cw, ch = size
    px_per_m = ch / (top - bottom)
    ss = 2
    rs = RenderSettings(cell_w=cw * ss, cell_h=ch * ss, figure_h=int(px_per_m * HEIGHT * ss),
                        baseline=int((top * px_per_m) * ss), anchor_x=cw * ss // 2, yaw=yaw, pitch=4.0, ss=2)
    rs.follow_root = False
    # centre on the head, not the hips: shift the model so the head is at x=0
    sh = rig.skin(W)[rig.F] - np.array([cx, 0.0, cz])
    tex = rig.single_texture(None)
    from .render import render_textured, render_tris
    if tex is not None:
        im = render_textured(sh, rig.fuv, tex, rs, (0.0, 0.0))
    else:
        vis = rig.opaque_faces() if hasattr(rig, "opaque_faces") else np.ones(len(rig.F), bool)
        im = render_tris(sh[vis], np.zeros(int(vis.sum()), int), None, rs, (0.0, 0.0), rgb=rig.face_colors(None)[vis], two_sided=True)
    im = im.resize((cw, ch), Image.LANCZOS)
    out = Image.new("RGBA", (cw, ch), bg)
    out.alpha_composite(im)
    return out


def from_sprite(folder, size=(256, 320), bg=BG):
    """fallback: the head and shoulders of idle frame 0, scaled up"""
    mv = os.path.join(folder, "moves")
    names = sorted(f for f in os.listdir(mv) if f.endswith(".png")) if os.path.isdir(mv) else []
    pick = next((f for f in names if f.startswith("idle_")), names[0] if names else None)
    if pick is None:
        return None
    im = Image.open(os.path.join(mv, pick)).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    if not bb:
        return None
    hgt = bb[3] - bb[1]
    cx = (bb[0] + bb[2]) // 2
    side = max(8, int(hgt * 0.36))
    box = (cx - int(side * 0.4), bb[1] - int(side * 0.05), cx + int(side * 0.4), bb[1] + side)
    crop = im.crop(box).resize(size, Image.LANCZOS)
    out = Image.new("RGBA", size, bg)
    out.alpha_composite(crop)
    return out


def portrait(folder, out_path=None, size=(256, 320), yaw=25.0):
    """a build folder -> portrait.png (from model.glb when there is one). -> (path, how)"""
    out_path = out_path or os.path.join(folder, "portrait.png")
    glb = os.path.join(folder, "model.glb")
    im, how = None, ""
    if os.path.isfile(glb):
        try:
            from .importers import load_file
            rig = load_file(glb)[0]
            if rig.has_mesh():
                im, how = render_portrait(rig, size, yaw), "3d"
        except Exception as e:                                             # noqa: BLE001
            how = "3d failed (%s); " % e
    if im is None:
        im = from_sprite(folder, size)
        how += "sprite"
    if im is None:
        return None, "no model and no sprites"
    im.save(out_path)
    return out_path, how


def _font(n):
    try:
        from .build import _font as F
        return F(n)
    except Exception:                                                      # noqa: BLE001
        from PIL import ImageFont
        return ImageFont.load_default()


def select_screen(entries, out_path, title="SELECT YOUR FIGHTER", cols=0, thumb=(160, 200), accent=(240, 196, 60)):
    """entries: [(portrait_path, name, subtitle)] -> a select-screen grid PNG"""
    n = len(entries)
    cols = cols or min(n, 6)
    rows = (n + cols - 1) // cols
    pad, head = 14, 54
    cw, ch = thumb[0] + pad, thumb[1] + 46
    W = cols * cw + pad
    H = head + rows * ch + pad
    sheet = Image.new("RGBA", (W, H), (16, 18, 24, 255))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 14), title, fill=accent + (255,), font=_font(24))
    for i, (p, name, sub) in enumerate(entries):
        x, y = pad + (i % cols) * cw, head + (i // cols) * ch
        im = Image.open(p).convert("RGBA").resize(thumb, Image.LANCZOS) if p and os.path.isfile(p) else Image.new("RGBA", thumb, BG)
        sheet.alpha_composite(im, (x, y))
        d.rectangle([x - 2, y - 2, x + thumb[0] + 1, y + thumb[1] + 1], outline=accent + (255,) if i == 0 else (90, 96, 110, 255), width=2)
        d.text((x, y + thumb[1] + 5), name.upper()[:18], fill=(240, 240, 240, 255), font=_font(14))
        if sub:
            d.text((x, y + thumb[1] + 24), sub[:24], fill=(160, 168, 184, 255), font=_font(11))
    sheet.save(out_path)
    return out_path


def team_sheet(sides, out_path, title=""):
    """sides: [(side_label, [(idle_png, name, role)])] -> one row per side of full-body idle sprites"""
    pad, th = 12, 30
    rows = []
    for label, ents in sides:
        ims = []
        for p, name, role in ents:
            im = Image.open(p).convert("RGBA") if p and os.path.isfile(p) else None
            ims.append((im, name, role))
        rows.append((label, ims))
    cell = max((im.size for _, ims in rows for im, _, _ in ims if im is not None), default=(128, 160))
    cw, ch = cell[0] + pad, cell[1] + 40
    ncol = max(len(ims) for _, ims in rows) if rows else 1
    W = pad + ncol * cw
    H = (th if title else 0) + sum(24 + ch for _ in rows) + pad
    sheet = Image.new("RGBA", (W, H), (22, 26, 32, 255))
    d = ImageDraw.Draw(sheet)
    y = pad
    if title:
        d.text((pad, y), title, fill=(240, 240, 240, 255), font=_font(18)); y += th
    for label, ims in rows:
        d.text((pad, y), label, fill=(240, 196, 60, 255), font=_font(15)); y += 24
        for i, (im, name, role) in enumerate(ims):
            x = pad + i * cw
            if im is not None:
                sheet.alpha_composite(im, (x, y))
            d.text((x, y + cell[1] + 2), name[:16], fill=(235, 235, 235, 255), font=_font(12))
            d.text((x, y + cell[1] + 18), role[:18], fill=(150, 158, 170, 255), font=_font(10))
        y += ch
    sheet.save(out_path)
    return out_path
