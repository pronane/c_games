"""2D image utilities: cutout, trimming, normalising imported frames onto a
common cell (same scale, feet on one ground line, pivot bottom-centre).

PHOTO mode only ever re-uses the person's own pixels: cut out, scaled,
placed, optionally flipped / moved / rotated for placeholders.  No pixels
are invented or regenerated."""
from __future__ import annotations
import glob
import math
import os
import re
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageChops

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".gif")


def load_rgba(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGBA")


def has_alpha(im, frac=0.03):
    a = np.asarray(im.getchannel("A"))
    return (a < 250).mean() > frac


_RB_SESSION = None


def _rembg(im):
    """Optional AI *segmentation* (background removal only - it never draws pixels).
    Model: env SFS_REMBG_MODEL (default u2net, ~170 MB, downloaded once by rembg)."""
    global _RB_SESSION
    try:
        from rembg import remove, new_session  # optional, heavy
    except Exception:
        return None
    try:
        if _RB_SESSION is None:
            _RB_SESSION = new_session(os.environ.get("SFS_REMBG_MODEL", "u2net"))
        out = remove(im, session=_RB_SESSION)
        return out.convert("RGBA")
    except Exception:
        return None


def threshold_cutout(im, tol=38):
    """Background = colour of the image border (works for plain / studio backdrops)."""
    a = np.asarray(im.convert("RGB")).astype(np.int32)
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    d = np.sqrt(((a - bg) ** 2).sum(axis=2))
    fg = d > tol
    try:
        from scipy import ndimage
        fg = ndimage.binary_opening(fg, iterations=1)
        lab, n = ndimage.label(fg)
        if n > 0:
            sizes = ndimage.sum(fg, lab, range(1, n + 1))
            keep = np.zeros(n + 1, bool)
            big = sizes.max()
            keep[1:] = sizes >= big * 0.08
            fg = keep[lab]
        fg = ndimage.binary_fill_holes(fg)
    except Exception:
        pass
    m = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.copy(); out.putalpha(m)
    return out


def cutout(im, method="auto", log=print):
    """method: auto | alpha | rembg | threshold | none"""
    if method == "none":
        return im
    if method in ("auto", "alpha") and has_alpha(im):
        return im
    if method in ("auto", "rembg"):
        r = _rembg(im)
        if r is not None:
            return r
        if method == "rembg":
            log("  ! rembg not available - falling back to border-colour threshold cutout")
    return threshold_cutout(im)


def trim(im, thr=8):
    a = im.getchannel("A").point(lambda v: 255 if v > thr else 0)
    bb = a.getbbox()
    return (im.crop(bb), bb) if bb else (im, (0, 0, im.width, im.height))


def alpha_centroid_x(im):
    a = np.asarray(im.getchannel("A")).astype(np.float64)
    s = a.sum()
    if s <= 0:
        return im.width / 2
    return float((a.sum(axis=0) * np.arange(im.width)).sum() / s)


def place(fig, cell_w, cell_h, anchor_x, ground_y, scale, offset=(0, 0), log=None):
    """Scale a trimmed figure and paste it so its bottom sits on ground_y and its
    alpha centroid is on anchor_x.  Returns (cell_image, clipped?)."""
    nw, nh = max(1, round(fig.width * scale)), max(1, round(fig.height * scale))
    f = fig.resize((nw, nh), Image.LANCZOS)
    cx = alpha_centroid_x(f)
    x = int(round(anchor_x - cx + offset[0])); y = int(round(ground_y - nh + offset[1]))
    cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
    cell.paste(f, (x, y), f)
    clipped = x < 0 or y < 0 or x + nw > cell_w or y + nh > cell_h
    return cell, clipped


def place_strip(figs, cell_w, cell_h, anchor_x, ground_y, scale):
    """Keep relative motion within a move (video frames): align the union box."""
    boxes = [f.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() or (0, 0, 1, 1) for f in figs]
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    # anchor: centroid of the first frame
    first = figs[0].crop(boxes[0])
    cx = (boxes[0][0] + alpha_centroid_x(first) - x0) * scale
    out, clip = [], False
    for f in figs:
        u = f.crop((x0, y0, x1, y1))
        nw, nh = max(1, round(u.width * scale)), max(1, round(u.height * scale))
        u = u.resize((nw, nh), Image.LANCZOS)
        cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
        x = int(round(anchor_x - cx)); y = int(round(ground_y - nh))
        cell.paste(u, (x, y), u)
        clip = clip or x < 0 or y < 0 or x + nw > cell_w or y + nh > cell_h
        out.append(cell)
    return out, clip


def list_images(folder):
    fs = [f for f in sorted(glob.glob(os.path.join(folder, "*"))) if f.lower().endswith(IMG_EXT)]
    def key(p):
        n = re.findall(r"\d+", os.path.basename(p))
        return (int(n[-1]) if n else 0, p)
    return sorted(fs, key=key)


def video_frames(path, n, log=print):
    """Extract n evenly spaced frames from a video (imageio-ffmpeg / system ffmpeg / OpenCV, see media.py)."""
    from . import media
    from PIL import Image
    info = media.probe(path)
    fr = media.read_frames(path, info["w"], info["h"])
    if not len(fr):
        raise RuntimeError("no frames decoded from " + path)
    tmp = tempfile.mkdtemp(prefix="sfs_vid_")
    for i in sorted(set(round(k * (len(fr) - 1) / max(1, n - 1)) for k in range(n)) if 0 < n < len(fr) else range(len(fr))):
        Image.fromarray(fr[i]).save(os.path.join(tmp, "f_%05d.png" % (i + 1)))
    fs = list_images(tmp)
    if not fs:
        raise RuntimeError("no frames decoded from " + path)
    return pick_even(fs, n)


def pick_even(items, n):
    if n <= 0 or n >= len(items):
        return list(items)
    return [items[round(i * (len(items) - 1) / max(1, n - 1))] for i in range(n)]


def split_sheet(sheet, rows=0, cols=0, thr=8):
    """Split a sprite sheet into a list of rows, each a list of cell images.
    rows/cols > 0: uniform grid.  0: auto-detect by empty (transparent) bands."""
    if rows > 0 and cols > 0:
        cw, ch = sheet.width // cols, sheet.height // rows
        out = []
        for r in range(rows):
            row = []
            for c in range(cols):
                cell = sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
                if cell.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox():
                    row.append(cell)
            out.append(row)
        return out
    a = np.asarray(sheet.getchannel("A")) > thr
    def bands(v):
        res, on, s = [], False, 0
        for i, x in enumerate(v):
            if x and not on:
                on, s = True, i
            elif not x and on:
                on = False; res.append((s, i))
        if on:
            res.append((s, len(v)))
        return res
    out = []
    for y0, y1 in bands(a.any(axis=1)):
        sub = a[y0:y1]
        row = [sheet.crop((x0, y0, x1, y1)) for x0, x1 in bands(sub.any(axis=0)) if x1 - x0 > 2]
        out.append(row)
    return out


# ------------------------------------------------------------ placeholders
def placeholder_frames(cell, n, motion_name, anchor_x, ground_y):
    """Fill a move from ONE still: the same pixels moved / rotated.  Clearly a
    placeholder - it does not invent new body poses."""
    nm = motion_name
    out = []
    for i in range(n):
        t = i / max(1, n - 1) if n > 1 else 0.0
        ph = math.sin(2 * math.pi * i / max(1, n))
        dx = dy = ang = 0.0; sy = 1.0; sx = 1.0; tint = None
        if nm == "steer_left":
            ang = 9 * min(1.0, 2 * t)
        elif nm == "steer_right":
            ang = -9 * min(1.0, 2 * t)
        elif nm == "drift":
            ang = 7; dx = -6 * abs(ph); dy = -2 * abs(ph)
        elif nm == "boost":
            ang = 6; dx = 6 + 3 * ph
        elif nm == "kart_drive":
            dy = -2 * abs(ph)
        elif nm == "spin_out":
            sx = math.cos(2 * math.pi * t)          # fake turn: squash through 0 and mirror
        elif nm == "defeat":
            sy = 1 - 0.05 * t; ang = -5 * t
        elif any(k in nm for k in ("walk", "run", "sprint", "carry", "bounce", "solo")):
            dy = -abs(ph) * (6 if "walk" in nm else 12); ang = 2.5 * ph
        elif any(k in nm for k in ("jump", "leap", "aerial", "block", "celebrate_goal", "special_1")):
            dy = -math.sin(math.pi * t) * cell.height * 0.18
        elif nm in ("hit", "kart_hit"):
            dx = -10 * math.sin(math.pi * t); ang = 6 * math.sin(math.pi * t); tint = (255, 60, 60) if i == 1 else None
        elif any(k in nm for k in ("fall", "ko", "dive")):
            ang = -88 * t if "left" not in nm else 88 * t
        elif nm == "get_up":
            ang = -88 * (1 - t)
        elif any(k in nm for k in ("victory", "celebrate", "taunt")):
            dy = -abs(ph) * 10; sy = 1 + 0.02 * abs(ph)
        elif any(k in nm for k in ("idle", "hold", "injured", "back")):
            sy = 1 + 0.012 * (ph + 1) / 2
        else:  # attacks, passes, kicks: lean in and back
            ang = -7 * math.sin(math.pi * t); dx = 8 * math.sin(math.pi * t)
        im = cell
        if sx != 1.0:
            w2 = max(2, int(round(cell.width * abs(sx))))
            sq = cell.resize((w2, cell.height), Image.BICUBIC)
            if sx < 0:
                sq = sq.transpose(Image.FLIP_LEFT_RIGHT)
            c1 = Image.new("RGBA", cell.size, (0, 0, 0, 0))
            c1.paste(sq, (int(round(anchor_x - anchor_x * abs(sx))), 0), sq); im = c1
        if sy != 1.0:
            h2 = round(cell.height * sy)
            im = im.resize((cell.width, h2), Image.BICUBIC)
            c2 = Image.new("RGBA", cell.size, (0, 0, 0, 0)); c2.paste(im, (0, int(round(ground_y - ground_y * sy))), im)
            im = c2
        if ang:
            im = im.rotate(ang, resample=Image.BICUBIC, center=(anchor_x, ground_y))
        if dx or dy:
            c3 = Image.new("RGBA", im.size, (0, 0, 0, 0)); c3.paste(im, (int(dx), int(dy)), im); im = c3
        if tint:
            r = Image.new("RGBA", im.size, tint + (0,)); r.putalpha(im.getchannel("A").point(lambda v: v * 0.45))
            im = Image.alpha_composite(im, r)
        out.append(im)
    return out
