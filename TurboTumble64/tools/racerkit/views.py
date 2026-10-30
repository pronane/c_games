"""racerkit.views - turn person cut-outs into an 8-angle HD driver sprite sheet.

Angles are measured around the driver, 0 = camera in front, 90 = camera at the
driver's RIGHT-hand side (we see the right cheek, nose points image-right),
180 = behind, 270 = left-hand side.  Missing angles are filled by mirroring the
opposite side, and if there is no back photo a back view is *invented* from the
front's own pixels (mirrored silhouette, hair/clothing colours, no new face).
Everything here only crops, scales, mirrors, tints and blurs the person's own
pixels - no generative model is involved.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageEnhance
from scipy import ndimage as ndi

from .cutout import bleed

ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
FW, FH = 512, 640          # sheet cell (4 x 2 cells -> 2048 x 1280)


# ------------------------------------------------------------------ helpers ----
def alpha_np(im):
    return np.asarray(im.getchannel("A"), dtype=np.float64) / 255.0


def tight(im, thr=8):
    bb = im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()
    return im.crop(bb) if bb else im


def drop_specks(im, keep_frac=0.02):
    """remove loose bits that are not attached to the person (bits of furniture, specks)"""
    a = np.asarray(im).copy()
    solid = a[..., 3] > 100
    L, n = ndi.label(solid)
    if n <= 1:
        return im
    sizes = ndi.sum(solid, L, range(1, n + 1))
    keep = np.isin(L, np.flatnonzero(sizes >= keep_frac * sizes.max()) + 1)
    # soft edge pixels belong to whatever solid part is next to them
    near = ndi.binary_dilation(keep, iterations=4)
    a[..., 3] = np.where(near, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def match_colors(im, ref, amount=0.75):
    """make another photo/video frame of the same outfit match the front photo's colour + contrast"""
    A = np.asarray(im, dtype=np.float64)
    R = np.asarray(ref, dtype=np.float64)
    ma, mr = A[..., 3] > 200, R[..., 3] > 200
    if ma.sum() < 100 or mr.sum() < 100:
        return im
    out = A.copy()
    for c in range(3):
        sa, sr = A[..., c][ma], R[..., c][mr]
        mu_a, sd_a = sa.mean(), sa.std() + 1e-3
        mu_r, sd_r = sr.mean(), sr.std() + 1e-3
        m = (A[..., c] - mu_a) * (sd_r / sd_a) + mu_r
        out[..., c] = A[..., c] * (1 - amount) + m * amount
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _bbox(im, thr=8):
    return im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox() or (0, 0, im.width, im.height)


def cut_at(im, frac, with_offset=False):
    """keep the top `frac` of the person (e.g. 0.55 = head to lap for a seated photo)"""
    b1 = _bbox(im)
    im = im.crop(b1)
    ox, oy = b1[0], b1[1]
    if frac < 0.999:
        im = im.crop((0, 0, im.width, max(8, int(im.height * frac))))
        b2 = _bbox(im)
        im = im.crop(b2)
        ox, oy = ox + b2[0], oy + b2[1]
    return (im, (ox, oy)) if with_offset else im


def neck_row(im):
    """row of the neck: the narrowest row just above where the shoulders widen out"""
    a = alpha_np(im) > 0.5
    h = a.shape[0]
    widths = np.array([(np.ptp(np.nonzero(r)[0]) + 1) if r.any() else 0 for r in a], float)
    widths = ndi.uniform_filter1d(widths, max(3, h // 100))
    rows = np.nonzero(widths > 0)[0]
    if len(rows) < 10:
        return int(0.3 * h)
    top = rows[0]
    head_w = widths[top:top + max(3, int(0.16 * h))].max()
    S = None
    for y in range(top + int(0.12 * h), int(0.75 * h)):
        if widths[y] > 1.3 * head_w:
            S = y
            break
    if S is None:
        S = int(0.45 * h)
    lo = top + int(0.5 * (S - top))
    return lo + int(np.argmin(widths[lo:S + 1])) if S > lo else int(0.3 * h)


def skin_mask(im):
    rgb = np.asarray(im.convert("RGB"), dtype=np.float64)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cr = (r - y) * 0.713 + 128
    cb = (b - y) * 0.564 + 128
    return (cr > 136) & (cr < 180) & (cb > 80) & (cb < 128) & (y > 60) & (alpha_np(im) > 0.9)


def face_box(im):
    """(x0, y0, x1, y1) of the face: the biggest skin-coloured blob in the top half"""
    sk = skin_mask(im)
    h = sk.shape[0]
    sk[int(0.6 * h):] = False
    sk = ndi.binary_opening(sk, iterations=2)
    L, n = ndi.label(sk)
    if n == 0:
        return None
    sizes = ndi.sum(sk, L, range(1, n + 1))
    i = int(np.argmax(sizes)) + 1
    if sizes[i - 1] < 0.004 * sk.size:
        return None
    blob = L == i
    ys, xs = np.nonzero(blob)
    y0, y1 = ys.min(), ys.max() + 1
    widths = blob.sum(1).astype(float)
    top_w = widths[y0:y0 + max(2, int(0.5 * (y1 - y0)))].max()
    # a beige/pink top can look like skin: stop where the blob gets much wider than the face
    for y in range(y0 + int(0.45 * (y1 - y0)), y1):
        if widths[y] > 1.35 * top_w:
            y1 = y
            break
    if (y1 - y0) > 1.6 * top_w:
        y1 = int(y0 + 1.35 * top_w)
    xs = np.nonzero(blob[y0:y1].any(0))[0]
    return int(xs.min()), int(y0), int(xs.max()) + 1, int(y1)


def head_box(im, face=None):
    """(x0, y0, x1, y1) of the head: from the top of the person to the chin"""
    a = alpha_np(im) > 0.5
    top = int(np.nonzero(a.any(1))[0][0]) if a.any() else 0
    fb = face or face_box(im)
    if fb is not None:
        fx0, fy0, fx1, fy1 = fb
        pad = 0.12 * (fx1 - fx0)
        return int(fx0 - pad), top, int(fx1 + pad), fy1
    ny = neck_row(im)
    xs = np.nonzero(a[:max(2, ny)].any(0))[0]
    if len(xs) == 0:
        return (0, 0, im.width, ny)
    return (int(xs.min()), top, int(xs.max()) + 1, ny)


def place(im, scale, anchor_x=None, cw=FW, ch=FH, bottom_pad=0):
    """scale the person and drop them in a cw x ch cell, bottom aligned, anchored on the torso"""
    w, h = max(1, int(im.width * scale)), max(1, int(im.height * scale))
    s = im.resize((w, h), Image.LANCZOS)
    if anchor_x is None:
        anchor_x = torso_x(im)
    ax = anchor_x * scale
    cell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    x, y = int(round(cw / 2 - ax)), ch - h - bottom_pad
    tmp = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    tmp.paste(s, (x, y), s)
    # paste() with a mask multiplies alpha twice for soft edges - redo the alpha exactly
    al = Image.new("L", (cw, ch), 0)
    al.paste(s.getchannel("A"), (x, y))
    tmp.putalpha(al)
    return tmp


def torso_x(im):
    """x centre of the lower 45% of the person (the torso / lap): the kart seat anchor"""
    a = alpha_np(im)
    h = a.shape[0]
    low = a[int(0.55 * h):]
    xs = np.arange(a.shape[1])
    tot = low.sum()
    return float((low.sum(0) * xs).sum() / tot) if tot > 0 else a.shape[1] / 2


def fade_bottom(cell, frac=0.06):
    """the driver sits *in* the kart: soften the cut line so it never shows as a hard edge"""
    a = np.asarray(cell, dtype=np.float64).copy()
    al = a[..., 3]
    rows = np.nonzero(al.max(1) > 0)[0]
    if len(rows) == 0:
        return cell
    y1 = rows.max() + 1
    n = max(2, int(frac * (y1 - rows.min())))
    ramp = np.linspace(1, 0.25, n)
    al[y1 - n:y1] *= ramp[:, None]
    a[..., 3] = al
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def mirror(im):
    return ImageOps.mirror(im)


def squash(im, sx, dark=1.0):
    w = max(4, int(im.width * sx))
    out = im.resize((w, im.height), Image.LANCZOS)
    if dark != 1.0:
        rgb = ImageEnhance.Brightness(out.convert("RGB")).enhance(dark)
        rgb.putalpha(out.getchannel("A"))
        out = rgb
    return out


def shade_edges(im, amount=0.22):
    """darken towards the silhouette edge so a flat card reads as a rounded body"""
    a = alpha_np(im)
    d = ndi.distance_transform_edt(a > 0.5)
    d = np.clip(d / max(4.0, 0.12 * im.width), 0, 1)
    k = 1 - amount * (1 - d) ** 2
    rgb = np.asarray(im.convert("RGB"), dtype=np.float64) * k[..., None]
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    out.putalpha(im.getchannel("A"))
    return out


# ------------------------------------------------------------- invented back ----
def median_rgb(im, mask):
    rgb = np.asarray(im.convert("RGB"), dtype=np.float64)
    m = mask & (alpha_np(im) > 0.9)
    if m.sum() < 10:
        return np.array([128.0, 110, 90])
    return np.median(rgb[m], axis=0)


def invent_back(front, hair_rgb=None, collar_rgb=None, seed=3, face=None):
    """a believable back view made only from the front photo's own colours:
    mirrored silhouette, a hair-coloured head (strand texture, lighter at the nape),
    the clothing's median colour with a soft knit texture and folds, and an optional
    collar / bib-tie band at the neck.  No facial features are carried over."""
    f = mirror(front)
    a = alpha_np(f)
    h, w = a.shape
    rgb = np.asarray(f.convert("RGB"), dtype=np.float64)
    if face is not None:
        face = (w - face[2], face[1], w - face[0], face[3])
    hx0, hy0, hx1, chin = head_box(f, face)
    chin = int(min(max(chin, 0.15 * h), 0.7 * h))
    yy, xx = np.mgrid[0:h, 0:w]
    hcx, hcy = (hx0 + hx1) / 2, (hy0 + chin) / 2
    hrx, hry = max(4, (hx1 - hx0) / 2) * 1.04, max(4, (chin - hy0) / 2) * 1.04
    ell = ((xx - hcx) / hrx) ** 2 + ((yy - hcy) / hry) ** 2 < 1
    head = (ell | ((yy < hcy) & (xx > hx0 - 0.03 * w) & (xx < hx1 + 0.03 * w))) & (yy < chin) & (a > 0.02)
    body = ~head & (a > 0.02)
    sk = skin_mask(f)
    top = (yy < hy0 + 0.25 * (chin - hy0)) & (a > 0.5) & ~sk
    hair = np.array(hair_rgb, float) if hair_rgb is not None else median_rgb(f, top if top.sum() > 50 else (yy < hy0 + 0.15 * (chin - hy0)))
    skin = median_rgb(f, sk) if sk.sum() > 50 else hair
    cloth = median_rgb(f, body & (a > 0.9) & (yy > chin + 0.1 * (h - chin)))
    rng = np.random.default_rng(seed)
    knit = ndi.gaussian_filter(rng.normal(0, 1, (h, w)), (1.2, 0.8)) * 9
    lum = rgb.mean(-1)
    folds = ndi.gaussian_filter(lum, max(4, w / 40)) - ndi.gaussian_filter(lum, max(12, w / 10))
    out = np.zeros_like(rgb)
    out[:] = cloth
    out += knit[..., None] + np.clip(folds, -18, 18)[..., None] * 0.3
    # head: hair with long vertical strands, fading to skin at the nape
    strands = ndi.gaussian_filter(rng.normal(0, 1, (h, w)), (max(3, h / 90), 0.9)) * 16
    t = np.clip((yy - (hy0 + 0.55 * (chin - hy0))) / max(1, 0.45 * (chin - hy0)), 0, 1)[..., None]
    hc = (hair[None, None, :] + strands[..., None]) * (1 - 0.6 * t) + skin[None, None, :] * 0.6 * t
    rr = np.clip(((xx - hcx) / hrx) ** 2 + ((yy - hcy) / hry) ** 2, 0, 1.4)
    hc = hc * (1.08 - 0.28 * rr)[..., None]                    # make the head read as round
    out = np.where(head[..., None], hc, out)
    # neck band: collar / bib ties with a little knot
    if collar_rgb is not None:
        cx, half = hcx, 0.42 * (hx1 - hx0)
        band = (yy >= chin - 0.03 * h) & (yy < chin + 0.02 * h) & (np.abs(xx - cx) < half) & (a > 0.3)
        knot = ((xx - cx) / (0.035 * w)) ** 2 + ((yy - chin - 0.02 * h) / (0.025 * h)) ** 2 < 1
        cc = np.array(collar_rgb, float)
        out = np.where((band | (knot & (a > 0.3)))[..., None], cc + knit[..., None] * 0.5, out)
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    img.putalpha(f.getchannel("A"))
    return shade_edges(img, 0.30)


def turn(im, amount, sx=1.0, dark=1.0):
    """fake a small head-and-body turn of a flat photo: squash horizontally and
    compress one side more than the other (amount > 0 turns towards image-right)"""
    w, h = im.width, im.height
    nw = max(4, int(w * sx))
    u = (np.arange(nw) + 0.5) / nw
    g = 1.0 + abs(amount)
    src_u = u ** g if amount > 0 else 1 - (1 - u) ** g
    arr = np.asarray(im, dtype=np.float64)
    xs = np.clip(src_u * w - 0.5, 0, w - 1)
    x0 = np.floor(xs).astype(int); x1 = np.minimum(x0 + 1, w - 1); fx = (xs - x0)[None, :, None]
    out = arr[:, x0] * (1 - fx) + arr[:, x1] * fx
    out[..., :3] *= dark
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


# --------------------------------------------------------------- mood edits ----
def _tint(im, rgb_mul, sat=1.0, bright=1.0):
    base = im.convert("RGB")
    if sat != 1.0:
        base = ImageEnhance.Color(base).enhance(sat)
    if bright != 1.0:
        base = ImageEnhance.Brightness(base).enhance(bright)
    arr = np.asarray(base, dtype=np.float64) * np.array(rgb_mul)[None, None, :]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    out.putalpha(im.getchannel("A"))
    return out


def _rot(x, y, deg, cx, cy):
    """where point (x, y) ends up after PIL's Image.rotate(deg, center=(cx, cy))"""
    t = math.radians(deg)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(t) + dy * math.sin(t), cy - dx * math.sin(t) + dy * math.cos(t)


def win_sprite(front, style, face=None):
    """victory card made from the front cut-out with simple edits only:
    happy  -> warm tint, cheek blush, sparkles, a small upward tilt
    sleepy -> desaturated cool tint, droopy 4 degree tilt, a cross 'anger vein'
    (the game draws the floating Zzz itself).  Returns (image, (faceX, faceY))."""
    hx0, hy0, hx1, ny = head_box(front, face)
    fb = face or face_box(front) or (hx0, hy0 + 0.3 * (ny - hy0), hx1, ny)
    fx, fy = (fb[0] + fb[2]) / 2, fb[1] + 0.74 * (fb[3] - fb[1])     # cheek line
    hw = fb[2] - fb[0]
    fh = fb[3] - fb[1]
    pad = int(0.16 * front.height)
    W, H = front.width + 2 * pad, front.height + pad
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if style == "sleepy":
        im = _tint(front, (0.92, 0.97, 1.08), sat=0.72, bright=0.93)
        canvas.alpha_composite(im, (pad, pad))
        canvas = canvas.rotate(-4, resample=Image.BICUBIC, center=(W / 2, H), expand=False)
        d = ImageDraw.Draw(canvas)
        # anger vein: four little red arcs at the upper side of the forehead
        cx, cy = _rot(pad + fb[2] - 0.22 * hw, pad + fb[1] + 0.14 * fh, -4, W / 2, H)
        r = max(6, int(0.09 * hw))
        lw = max(3, r // 3)
        for ang in (45, 135, 225, 315):
            ox = cx + math.cos(math.radians(ang)) * r * 0.75
            oy = cy - math.sin(math.radians(ang)) * r * 0.75
            d.arc((ox - r * 0.6, oy - r * 0.6, ox + r * 0.6, oy + r * 0.6), ang + 90, ang + 270,
                  fill=(225, 30, 40, 255), width=lw)
    else:
        im = _tint(front, (1.06, 1.0, 0.92), sat=1.18, bright=1.05)
        canvas.alpha_composite(im, (pad, pad))
        # blush: two soft pink ovals on the cheeks, only where the person is
        bl = Image.new("L", (W, H), 0)
        bd = ImageDraw.Draw(bl)
        for sx in (-1, 1):
            cx, cy = pad + fx + sx * 0.29 * hw, pad + fy
            rx, ry = 0.11 * hw, 0.06 * hw
            bd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=110)
        bl = bl.filter(ImageFilter.GaussianBlur(max(2, 0.03 * hw)))
        bl = Image.fromarray((np.asarray(bl, float) * (np.asarray(canvas.getchannel("A"), float) / 255)).astype(np.uint8))
        pink = Image.new("RGBA", (W, H), (255, 90, 120, 255))
        pink.putalpha(bl)
        canvas.alpha_composite(pink)
        canvas = canvas.rotate(3, resample=Image.BICUBIC, center=(W / 2, H), expand=False)
        d = ImageDraw.Draw(canvas)
        rng = np.random.default_rng(7)
        for i in range(7):
            ang = -150 + i * 20 + rng.uniform(-6, 6)
            rr = (0.80 + rng.uniform(0, 0.15)) * max(hw, 0.6 * (ny - hy0))
            sx_, sy_ = _rot(pad + fx + math.cos(math.radians(ang)) * rr,
                            pad + (hy0 + ny) / 2 + math.sin(math.radians(ang)) * rr * 0.9, 3, W / 2, H)
            sy_ = max(sy_, 0.6 * pad)
            s = max(5, int(hw * rng.uniform(0.05, 0.09)))
            pts = [(sx_, sy_ - s), (sx_ + s * 0.28, sy_ - s * 0.28), (sx_ + s, sy_), (sx_ + s * 0.28, sy_ + s * 0.28),
                   (sx_, sy_ + s), (sx_ - s * 0.28, sy_ + s * 0.28), (sx_ - s, sy_), (sx_ - s * 0.28, sy_ - s * 0.28)]
            d.polygon(pts, fill=(255, 226, 90, 255), outline=(255, 255, 255, 255))
    zx, zy = _rot(pad + fx, pad + fb[1] + 0.3 * fh, -4 if style == "sleepy" else 3, W / 2, H)
    face_xy = (zx / W, zy / H)
    return canvas, face_xy


def portrait(front, size=256, face=None):
    hx0, hy0, hx1, ny = head_box(front, face)
    fb = face or face_box(front)
    hw, hh = hx1 - hx0, ny - hy0
    side = int(max(hw, hh) * 1.2)
    cx, cy = (hx0 + hx1) / 2, hy0 + hh * 0.55
    if fb is not None:
        fw_, fh_ = fb[2] - fb[0], fb[3] - fb[1]
        side = int(max(1.6 * fh_, 1.15 * (fb[3] - hy0), 1.5 * fw_))
        cx, cy = (fb[0] + fb[2]) / 2, hy0 + side * 0.47
    box = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
    pad = Image.new("RGBA", (front.width + 2 * side, front.height + 2 * side), (0, 0, 0, 0))
    pad.paste(front, (side, side))
    crop = pad.crop((box[0] + side, box[1] + side, box[2] + side, box[3] + side))
    return crop.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- the sheet ----
def build_views(views, cuts=None, back_mode="invent", hair_rgb=None, collar_rgb=None, log=print, faces=None):
    """views: {angle: RGBA cut-out}; must contain 0.  cuts: {angle: fraction of the
    person's height to keep}.  Returns ({angle: cell}, notes) for all 8 angles."""
    cuts = cuts or {}
    notes = {}
    src = {}
    face0 = None
    for a, im in views.items():
        src[a % 360], off = cut_at(drop_specks(im), cuts.get(a, 1.0), with_offset=True)
        notes[a % 360] = "photo"
        if a % 360 == 0 and faces and faces.get(0):
            x0, y0, x1, y1 = faces[0]
            face0 = (x0 - off[0], y0 - off[1], x1 - off[0], y1 - off[1])
    for a in list(src):
        if a != 0 and 0 in src:
            src[a] = match_colors(src[a], src[0])
    if 0 not in src:
        raise SystemExit("a front view (angle 0) is required")
    # opposite-side mirrors
    for a in ANGLES:
        if a not in src and (360 - a) % 360 in src:
            src[a] = mirror(src[(360 - a) % 360])
            notes[a] = "mirrored %d" % ((360 - a) % 360)
    if 180 not in src:
        src[180] = invent_back(src[0], hair_rgb, collar_rgb, face=face0)
        notes[180] = "INVENTED from the front photo's own colours"
    f, b = src[0], src[180]
    fill = {45: (f, 0.92, 0.35, 0.97), 90: (f, 0.80, 0.75, 0.88), 135: (b, 0.88, 0.35, 0.93)}
    for a, (im, sx, amt, dk) in fill.items():
        if a not in src and (360 - a) not in src:
            src[a] = shade_edges(turn(im, amt, sx, dk), 0.12)
            src[360 - a] = mirror(src[a])
            notes[a] = notes[360 - a] = "approximated (squashed %s view)" % ("front" if im is f else "back")
    # common scale: every view keeps the person's height from head-top to cut line
    target = FH * 0.97
    cells = {}
    for a in ANGLES:
        im = src[a]
        s = min(target / im.height, (FW * 0.99) / im.width)
        cells[a] = fade_bottom(place(im, s))
    return cells, notes, src, face0


def sheet(cells, cols=4):
    rows = (len(ANGLES) + cols - 1) // cols
    out = Image.new("RGBA", (FW * cols, FH * rows), (0, 0, 0, 0))
    for i, a in enumerate(ANGLES):
        out.paste(cells[a], ((i % cols) * FW, (i // cols) * FH))
    return bleed(out), rows


def preview(cells, bg=(70, 78, 96)):
    show = [0, 45, 90, 135, 180]
    W = FW // 2
    out = Image.new("RGBA", (W * len(show), FH // 2), bg + (255,))
    for i, a in enumerate(show):
        c = cells[a].resize((W, FH // 2), Image.LANCZOS)
        out.alpha_composite(c, (i * W, 0))
    return out.convert("RGB")
