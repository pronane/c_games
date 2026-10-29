"""Sprite Forge Studio v9 - normal + emissive maps for 2D lighting (maps/ next to the atlas, same layout).

--maps normal,emissive[=#59f2ff|#ff3020]
  normal    tangent-space normal atlas, +Y up (Godot / Unity 2D lights) - ESTIMATED from silhouette + shading
  emissive  glow atlas: pixels close to the emissive colours (mannequin: the spec's emissive / visor colour)
            on black; everything else black"""
from __future__ import annotations
import json
import os

import numpy as np
from PIL import Image

from . import fx


def parse(spec):
    out = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.lower()
        if k not in ("normal", "emissive"):
            raise ValueError("unknown map '%s' (normal, emissive)" % k)
        out[k] = v
    return out


def emissive_map(im, colours, tol=34.0):
    from .recolor import _lab
    a = np.asarray(im.convert("RGBA"))
    out = np.zeros_like(a)
    out[..., 3] = a[..., 3]
    sel = a[..., 3] > 0
    if not sel.any() or not colours:
        return Image.fromarray(out, "RGBA"), 0
    lab = _lab(a[sel][None, :, :3])[0]
    w = np.zeros(len(lab))
    for c in colours:
        t = _lab(np.array([[c]], np.uint8))[0, 0]
        d = np.linalg.norm(lab - t, axis=1)
        w = np.maximum(w, np.clip(1.5 - d / tol, 0, 1))
    px = a[sel][:, :3].astype(np.float32) * w[:, None]
    o = out[sel]; o[:, :3] = px.astype(np.uint8); out[sel] = o
    return Image.fromarray(out, "RGBA"), int((w > 0.5).sum())


def write_maps(cfg, out, ctx, report):
    from .recolor import to_rgb
    want = parse(cfg.maps)
    md = os.path.join(out, "maps")
    os.makedirs(md, exist_ok=True)
    pages, names = ctx["pages"], ctx["page_names"]
    info = {"layout": "same frames / rows as %s" % names[0], "normal_convention": "tangent space, +X right, +Y up (OpenGL)",
            "estimated": True, "files": {}}
    if "normal" in want:
        for p, n in zip(pages, names):
            fn = n.replace(".png", "_normal.png")
            fx.normal_map(p).save(os.path.join(md, fn), compress_level=6)
            info["files"].setdefault("normal", []).append(fn)
    if "emissive" in want:
        cols = [to_rgb(c) for c in want["emissive"].split("|") if c] if want["emissive"] else []
        sp = ctx.get("sp")
        if not cols and sp is not None:
            cols = [tuple(int(x * 255) for x in sp.colours()["emissive"])]
        lit = 0
        for p, n in zip(pages, names):
            fn = n.replace(".png", "_emissive.png")
            em, k = emissive_map(p, cols)
            lit += k
            em.save(os.path.join(md, fn), compress_level=6)
            info["files"].setdefault("emissive", []).append(fn)
        info["emissive_colours"] = ["#%02x%02x%02x" % c for c in cols]
        info["emissive_pixels"] = lit
        if not lit:
            report.warning("maps: emissive map is empty (no pixels near %s)" % (", ".join(info["emissive_colours"]) or "any colour - pass emissive=#rrggbb"))
    with open(os.path.join(md, "maps.json"), "w") as f:
        json.dump(info, f, indent=1)
    return "maps/ (%s)" % ", ".join(sorted(info["files"]))
