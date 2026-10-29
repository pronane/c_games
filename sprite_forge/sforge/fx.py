"""Sprite Forge Studio v9 - 2D post passes on finished frames + normal / emissive map estimation.

--fx "light=-1:-1:1,rim=0.4,cel=4,pixel=3,colors=32,outline=2,outline_colour=#14161c"
  light=x:y:z[:strength]  directional light from a normal map ESTIMATED from the silhouette + shading
  rim=strength            rim light on the silhouette edges (opposite the light)
  cel=N                   cel shading: lightness posterised into N bands, colours kept
  pixel=K                 pixel-art pass: K x K blocks, hard alpha (+ colors=N palette limit)
  outline=N               N-px outline around the figure (outline_colour=)
Passes always run in the order light, rim, cel, pixel, outline."""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

ORDER = ["light", "rim", "cel", "pixel", "outline"]


def parse(spec):
    out = {}
    for part in re.split(r"[,;]\s*", spec or ""):
        if not part.strip():
            continue
        k, _, v = part.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k == "light":
            nums = [float(x) for x in (v or "-1:-1:1").split(":")]
            d = np.array(nums[:3] + [1.0] * (3 - len(nums[:3])), float)
            out["light"] = (d / (np.linalg.norm(d) + 1e-9), nums[3] if len(nums) > 3 else 0.55)
        elif k in ("rim",):
            out[k] = float(v or 0.4)
        elif k in ("cel", "pixel", "outline", "colors", "colours"):
            out["colors" if k == "colours" else k] = int(float(v or {"cel": 3, "pixel": 3, "outline": 1, "colors": 32}[k]))
        elif k in ("outline_colour", "outline_color"):
            from .recolor import to_rgb
            out["outline_colour"] = to_rgb(v)
        else:
            raise ValueError("unknown fx '%s' (light rim cel pixel colors outline outline_colour)" % k)
    return out


def estimate_normals(im, bulge=1.0, detail=0.35):
    """tangent-space normals (H,W,3) float32 in -1..1 from the alpha silhouette (inflated height) + luminance detail.
    ESTIMATED: a flat sprite has no real depth; this is the usual 2D-lighting approximation."""
    import cv2
    a8 = np.asarray(im.convert("RGBA"))
    inside = a8[..., 3] > 127
    d = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5)
    R = max(2.0, float(np.percentile(d[inside], 95)) if inside.any() else 2.0)
    h = np.sqrt(np.minimum(d * (1.0 / R), 1.0)) * np.float32(R * 0.9 * bulge)
    lum = cv2.cvtColor(np.ascontiguousarray(a8[..., :3]), cv2.COLOR_RGB2GRAY).astype(np.float32) * np.float32(1 / 255.0)
    h += cv2.GaussianBlur(lum, (0, 0), 1.0) * np.float32(R * 0.25 * detail)
    h = cv2.GaussianBlur(h, (0, 0), 1.2)
    gx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=1) * np.float32(0.5)
    gy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=1) * np.float32(0.5)
    inv = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    n = np.dstack([-gx * inv, gy * inv, inv])          # +Y up (OpenGL / Godot / Unity convention)
    n[~inside] = (0, 0, 1)
    return n, a8[..., 3].astype(np.float32) / 255.0


def normal_map(im):
    n, A = estimate_normals(im)
    rgb = (n * 127.5 + 128.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, np.asarray(im.getchannel("A"))]), "RGBA")


def _light(im, ldir, strength, rim):
    n, A = estimate_normals(im)
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    nd = np.einsum("hwc,c->hw", n, ldir)
    f = 1.0 + strength * (nd - 0.55)
    if rim:
        rd = np.array([-ldir[0], ldir[1] * 0.3, 0.0]); rd /= np.linalg.norm(rd) + 1e-9
        r = np.clip(np.einsum("hwc,c->hw", n, rd), 0, 1) * (1 - n[..., 2]) ** 1.5 * rim * 255
    else:
        r = 0
    a[..., :3] = np.clip(a[..., :3] * f[..., None] + (r[..., None] if rim else 0), 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def _cel(im, k):
    from .recolor import _lab, _rgb
    a = np.asarray(im.convert("RGBA")).copy()
    sel = a[..., 3] > 0
    if not sel.any():
        return im
    lab = _lab(a[sel][None, :, :3])[0]
    L = lab[:, 0]
    lo, hi = np.percentile(L, 3), np.percentile(L, 97)
    t = np.clip((L - lo) / max(1e-3, hi - lo), 0, 1)
    q = (np.floor(t * k - 1e-6).clip(0, k - 1) + 0.5) / k
    lab[:, 0] = lo + q * (hi - lo)
    a[sel, :3] = _rgb(lab[None])[0]
    return Image.fromarray(a, "RGBA")


def _pixel(im, k, colors=0):
    W, H = im.size
    w2, h2 = max(1, W // k), max(1, H // k)
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    al = a[..., 3:4] / 255.0
    pm = np.dstack([a[..., :3] * al, a[..., 3:]])
    small = np.asarray(Image.fromarray(pm.astype(np.uint8), "RGBA").resize((w2, h2), Image.BOX)).astype(np.float32)
    A = small[..., 3:4] / 255.0
    rgb = np.where(A > 0, small[..., :3] / np.maximum(A, 1e-3), 0)
    out = np.dstack([np.clip(rgb, 0, 255), np.where(A[..., 0] > 0.5, 255, 0)]).astype(np.uint8)
    sm = Image.fromarray(out, "RGBA")
    if colors:
        rgbim = sm.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
        sm = Image.merge("RGBA", rgbim.split() + (sm.getchannel("A"),))
    big = sm.resize((w2 * k, h2 * k), Image.NEAREST)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(big, (0, 0))
    return canvas


def _outline(im, n, col=(20, 22, 28)):
    from scipy import ndimage as ndi
    a = np.asarray(im.convert("RGBA")).copy()
    A = a[..., 3] > 40
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    D = ndi.binary_dilation(A, structure=(xx * xx + yy * yy) <= n * n + 0.5)
    ring = D & ~A
    a[ring, :3] = col; a[ring, 3] = 255
    return Image.fromarray(a, "RGBA")


def apply(im, opts):
    if "light" in opts or "rim" in opts:
        ld, st = opts.get("light", (np.array([-0.5, 0.5, 0.7]) / np.linalg.norm([-0.5, 0.5, 0.7]), 0.0))
        im = _light(im, ld, st, opts.get("rim", 0.0))
    if opts.get("cel"):
        im = _cel(im, opts["cel"])
    if opts.get("pixel"):
        im = _pixel(im, opts["pixel"], opts.get("colors", 0))
    elif opts.get("colors"):
        im = _pixel(im, 1, opts["colors"])
    if opts.get("outline"):
        im = _outline(im, opts["outline"], opts.get("outline_colour", (20, 22, 28)))
    return im


def apply_frames(cfg, frames, report):
    opts = parse(cfg.fx)
    from concurrent.futures import ThreadPoolExecutor
    for mv in list(frames):
        fr, src, note = frames[mv]
        with ThreadPoolExecutor(4) as ex:
            fr2 = list(ex.map(lambda im: apply(im, opts), fr))
        frames[mv] = (fr2, src, (note + "; " if note else "") + "fx: " + cfg.fx)
    report.note("fx: %s (normals for light / rim are ESTIMATED from the 2D silhouette)" % cfg.fx)
