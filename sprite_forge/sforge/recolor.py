"""Sprite Forge Studio v9 - colour / texture swapping of skin, hair and clothing.

recolour spec (BuildConfig.recolor / forge.py --recolor / Studio "Colours" tab):
    "team_red"                         a named one-click set (built in, or library/recolor_sets/<name>.json)
    "top=#c01010,bottom=white"         per-region colours  (regions: skin hair top trim bottom socks shoes accessory)
    "team_blue;hair=black"             a set + overrides
overlay spec (BuildConfig.overlay):
    "hoops:#ffffff"  "stripes:gold"  "sash:#111"  "chest_band:red"  "halves:navy"  "check:white"  "dots:#fff"  "camo:#334422"
    "texture:my_cloth.png[:0.8]"      a user texture tiled over the top (shading kept)
regions (BuildConfig.regions):  a painted map PNG (same size as the photo) using the REGION_COLOURS legend - overrides
    the automatic segmentation (the build writes regions.png you can edit and feed back).

Mannequin builds: colours go straight into the 3D spec (exact).  Photo builds: the photo's own pixels are re-tinted
in LAB space inside ESTIMATED region masks (pose landmarks + a skin colour model + colour clusters); shading and
texture detail are kept, nothing new is painted except an optional overlay pattern."""
from __future__ import annotations
import glob
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw

REGIONS = ["skin", "hair", "top", "trim", "bottom", "socks", "shoes", "accessory"]
REGION_COLOURS = {"skin": (255, 205, 160), "hair": (110, 60, 20), "top": (230, 30, 30), "trim": (255, 140, 0),
                  "bottom": (30, 60, 230), "socks": (240, 240, 40), "shoes": (0, 200, 200), "accessory": (210, 0, 210)}
PATTERNS = ["hoops", "stripes", "sash", "chest_band", "halves", "check", "dots", "camo"]

SETS = {
    "team_red":    {"label": "Team Red", "top": "#c4161c", "trim": "#ffffff", "bottom": "#ffffff", "socks": "#c4161c"},
    "team_blue":   {"label": "Team Blue", "top": "#1c3fb0", "trim": "#ffffff", "bottom": "#0d1a4a", "socks": "#1c3fb0"},
    "team_green":  {"label": "Team Green", "top": "#0b7a3b", "trim": "#ffffff", "bottom": "#ffffff", "socks": "#0b7a3b"},
    "team_yellow": {"label": "Team Yellow", "top": "#f2c512", "trim": "#111111", "bottom": "#111111", "socks": "#f2c512"},
    "team_black":  {"label": "Team Black", "top": "#151518", "trim": "#d4af37", "bottom": "#151518", "socks": "#151518"},
    "team_white":  {"label": "Team White", "top": "#f2f2f2", "trim": "#1c1c1c", "bottom": "#1c1c1c", "socks": "#f2f2f2"},
    "kerry":       {"label": "Kerry (green & gold)", "top": "#0b6b34", "trim": "#f2c512", "bottom": "#ffffff", "socks": "#0b6b34",
                    "pattern": "chest_band", "pattern_colour": "#f2c512"},
    "dublin":      {"label": "Dublin (sky & navy)", "top": "#6cace4", "trim": "#0b1f4b", "bottom": "#0b1f4b", "socks": "#0b1f4b"},
    "mayo":        {"label": "Mayo (green & red)", "top": "#0b6b34", "trim": "#c4161c", "bottom": "#ffffff", "socks": "#0b6b34",
                    "pattern": "chest_band", "pattern_colour": "#c4161c"},
    "cork":        {"label": "Cork (red & white)", "top": "#c4161c", "trim": "#ffffff", "bottom": "#ffffff", "socks": "#c4161c"},
    "galway":      {"label": "Galway (maroon & white)", "top": "#7a1530", "trim": "#ffffff", "bottom": "#ffffff", "socks": "#7a1530"},
    "hoops_green": {"label": "Green & white hoops", "top": "#0b7a3b", "bottom": "#ffffff", "socks": "#ffffff",
                    "pattern": "hoops", "pattern_colour": "#ffffff"},
    "egypt_gold":  {"label": "Egyptian gold & lapis", "top": "#d4a017", "trim": "#1f3c88", "bottom": "#1f3c88", "socks": "#d4a017",
                    "accessory": "#d4a017"},
    "desert":      {"label": "Desert", "top": "#c8a165", "trim": "#5b3a1e", "bottom": "#7b5a36", "socks": "#c8a165", "shoes": "#4a3020"},
    "ninja":       {"label": "Ninja", "top": "#141418", "trim": "#8b0000", "bottom": "#141418", "socks": "#141418", "shoes": "#141418"},
    "villain":     {"label": "Villain (purple & black)", "top": "#4b136e", "trim": "#111111", "bottom": "#111111", "socks": "#4b136e",
                    "hair": "#111111"},
    "ghost":       {"label": "Ghost (pale)", "top": "#d8dde6", "trim": "#9aa4b5", "bottom": "#b8c0cc", "socks": "#d8dde6",
                    "hair": "#e8e8e8"},
    "fire":        {"label": "Fire", "top": "#e2401c", "trim": "#ffc21a", "bottom": "#2a0e08", "socks": "#e2401c", "hair": "#ff7a1a"},
    "ice":         {"label": "Ice", "top": "#8fd3ff", "trim": "#ffffff", "bottom": "#2b5d8a", "socks": "#8fd3ff", "hair": "#e8f6ff"},
    "p2_alt":      {"label": "Player 2 alt (hue shift)", "shift": 150},
}
HELP_KEYS = "regions: " + " ".join(REGIONS) + "; also pattern=<%s>, pattern_colour=, shift=<hue degrees>" % "|".join(PATTERNS)


def _here():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def all_sets():
    d = dict(SETS)
    for f in sorted(glob.glob(os.path.join(_here(), "library", "recolor_sets", "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                js = json.load(fh)
            d[os.path.splitext(os.path.basename(f))[0]] = js
        except Exception:
            pass
    return d


def save_set(name, mapping):
    """save a user set (Studio 'Save set') -> library/recolor_sets/<name>.json"""
    name = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "my_set"
    p = os.path.join(_here(), "library", "recolor_sets", name + ".json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=1)
    return p


def to_rgb(c):
    """'#rrggbb' | '#rgb' | colour name | (r,g,b) 0-1 or 0-255 -> (r,g,b) 0-255 ints"""
    if isinstance(c, (tuple, list)):
        v = [float(x) for x in c[:3]]
        return tuple(int(round(x * 255 if max(v) <= 1.0 else x)) for x in v)
    s = str(c).strip().lower()
    if s.startswith("#") or re.fullmatch(r"[0-9a-f]{6}", s):
        s = s.lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    from .spec import COLOURS, HAIR_COLOURS, SKIN_TONES
    for t in (COLOURS, HAIR_COLOURS, SKIN_TONES):
        if s in t:
            return tuple(int(round(x * 255)) for x in t[s][:3])
    raise ValueError("unknown colour '%s' (use #rrggbb or a name like red, navy, gold)" % c)


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb[:3])


def parse(spec):
    """recolour spec -> dict(region -> rgb, pattern?, pattern_colour?, shift?, label)"""
    if not spec:
        return {}
    if isinstance(spec, dict):
        parts, base = [], dict(spec)
    else:
        spec = str(spec).strip()
        if spec.endswith(".json") and os.path.isfile(spec):
            with open(spec, encoding="utf-8") as f:
                base, parts = json.load(f), []
        else:
            base, parts = {}, [p.strip() for p in re.split(r"[;,]", spec) if p.strip()]
    sets = all_sets()
    out = {}
    for k, v in base.items():
        out[k] = v
    for p in parts:
        if "=" not in p:
            key = p.lower()
            if key not in sets:
                raise ValueError("unknown colour set '%s' (sets: %s)" % (p, ", ".join(sorted(sets))))
            out.update(sets[key]); out.setdefault("label", key)
            continue
        k, v = [x.strip() for x in p.split("=", 1)]
        k = k.lower().replace("color", "colour")
        k = {"shirt": "top", "jersey": "top", "shorts": "bottom", "pants": "bottom", "trousers": "bottom",
             "boots": "shoes", "skin_tone": "skin"}.get(k, k)
        out[k] = v
    res = {}
    for k, v in out.items():
        if k in REGIONS:
            res[k] = to_rgb(v)
        elif k == "pattern_colour":
            res[k] = to_rgb(v)
        elif k == "pattern":
            if v not in PATTERNS:
                raise ValueError("unknown pattern '%s' (%s)" % (v, ", ".join(PATTERNS)))
            res[k] = v
        elif k == "shift":
            res[k] = float(v)
        elif k == "label":
            res[k] = str(v)
        else:
            raise ValueError("unknown recolour key '%s' (%s)" % (k, HELP_KEYS))
    return res


def parse_overlay(spec):
    """'hoops:#fff' | 'texture:file.png:0.8' | 'file.png' -> dict(kind, colour|path, opacity)"""
    if not spec:
        return None
    s = str(spec).strip()
    if s.lower().startswith("top:"):
        s = s[4:]
    if s.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.isfile(s):
        return {"kind": "texture", "path": s, "opacity": 1.0}
    k, _, rest = s.partition(":")
    k = k.lower()
    if k == "texture":
        m = re.match(r"(.*?)(?::([0-9.]+))?$", rest)
        path, op = m.group(1), float(m.group(2) or 1.0)
        if not os.path.isfile(path):
            raise ValueError("overlay texture not found: %s" % path)
        return {"kind": "texture", "path": path, "opacity": op}
    if k not in PATTERNS:
        raise ValueError("unknown overlay '%s' (patterns: %s, or texture:<file.png>)" % (k, ", ".join(PATTERNS)))
    col, _, op = rest.partition(":")
    return {"kind": k, "colour": to_rgb(col or "white"), "opacity": float(op or 1.0)}


# ---------------------------------------------------------------- mannequin (exact: colours go into the 3D spec)
_SPEC_FIELD = {"top": "top_colour", "trim": "trim_colour", "bottom": "bottom_colour", "socks": "socks_colour",
               "shoes": "shoes_colour", "hair": "hair_colour", "skin": "skin_tone", "accessory": "accessory_colour"}


def apply_to_spec(sp, rec, overlay=None):
    rec = parse(rec) if not isinstance(rec, dict) else rec
    if rec.get("shift"):
        cols = sp.colours()
        for reg, slot in (("top", "shirt"), ("trim", "trim"), ("bottom", "shorts"), ("socks", "socks")):
            if reg not in rec:
                rec[reg] = hue_shift(tuple(int(c * 255) for c in cols[slot]), rec["shift"])
    for reg, field in _SPEC_FIELD.items():
        if reg in rec:
            setattr(sp, field, hexc(rec[reg]))
    if rec.get("pattern"):
        sp.pattern = rec["pattern"]
        sp.pattern_colour = hexc(rec.get("pattern_colour", rec.get("trim", (255, 255, 255))))
    ov = parse_overlay(overlay) if isinstance(overlay, str) else overlay
    if ov and ov["kind"] in PATTERNS:
        sp.pattern, sp.pattern_colour = ov["kind"], hexc(ov["colour"])
    elif ov and ov["kind"] == "texture":
        sp.extra["top_texture"] = ov["path"]
    return sp


def hue_shift(rgb, deg):
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*[c / 255.0 for c in rgb])
    r, g, b = colorsys.hls_to_rgb((h + deg / 360.0) % 1.0, l, s)
    return (int(r * 255), int(g * 255), int(b * 255))


# ---------------------------------------------------------------- LAB helpers
def _lab(rgb_u8):
    """sRGB 0-255 -> CIE LAB (L 0-100) float32 (OpenCV; same scale as skimage)"""
    import cv2
    a = np.ascontiguousarray(np.asarray(rgb_u8, np.float32)[..., :3] / 255.0)
    sh = a.shape
    a2 = a.reshape(-1, 1, 3) if a.ndim != 3 else a
    return cv2.cvtColor(a2, cv2.COLOR_RGB2Lab).reshape(sh)


def _rgb(lab):
    import cv2
    lab = np.ascontiguousarray(np.asarray(lab, np.float32))
    sh = lab.shape
    l2 = lab.reshape(-1, 1, 3) if lab.ndim != 3 else lab
    return np.clip(cv2.cvtColor(l2, cv2.COLOR_Lab2RGB) * 255.0 + 0.5, 0, 255).astype(np.uint8).reshape(sh)


def recolour_pixels(lab, mask_w, target_rgb, stats=None):
    """re-tint LAB pixels towards target keeping shading; mask_w 0-1 soft weights. returns new LAB"""
    t = _lab(np.array([[target_rgb]], np.uint8))[0, 0]
    sel = mask_w > 0.5
    if stats is None:
        if not sel.any():
            return lab
        L = lab[..., 0][sel]
        Lm = float(np.median(L)); am = float(np.median(lab[..., 1][sel])); bm = float(np.median(lab[..., 2][sel]))
    else:
        Lm, am, bm = stats
    room_t = min(t[0], 100 - t[0]) + 8
    room_s = min(Lm, 100 - Lm) + 8
    g = float(np.clip(room_t / room_s, 0.35, 1.3))
    out = lab.copy()
    out[..., 0] = np.clip(t[0] + (lab[..., 0] - Lm) * g, 0, 100)
    out[..., 1] = t[1] + (lab[..., 1] - am) * 0.25
    out[..., 2] = t[2] + (lab[..., 2] - bm) * 0.25
    w = mask_w[..., None]
    return lab * (1 - w) + out * w


# ---------------------------------------------------------------- photo segmentation (ESTIMATED)
def _capsule(draw, a, b, r, val):
    draw.line([tuple(a), tuple(b)], fill=val, width=max(1, int(2 * r)))
    for p in (a, b):
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=val)


def _zone(size, fn):
    im = Image.new("L", size, 0)
    fn(ImageDraw.Draw(im))
    return np.asarray(im) > 0


def _cdist(lab, ref):
    """colour distance that mostly ignores lightness (shading / folds / denim fade keep their region)"""
    d = lab - ref
    return np.sqrt((d[..., 0] * 0.35) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)


def segment(cut, lms):
    """region label map (H,W) int8: -1 = none, else index into REGIONS; from the 33 pose landmarks (pixel coords
    of the cutout) + a skin colour model sampled on the face + colour clusters.  ESTIMATED."""
    from scipy import ndimage as ndi
    a = np.asarray(cut)
    A = a[..., 3] > 40
    H, W = A.shape
    lab = _lab(a[..., :3])
    P = lambda i: np.array(lms[i][:2], float)
    sh_l, sh_r, hp_l, hp_r = P(11), P(12), P(23), P(24)
    sw = max(8.0, float(np.linalg.norm(sh_l - sh_r)))
    eyes = (P(2) + P(5)) / 2
    mouth = (P(9) + P(10)) / 2
    s = max(4.0, float(np.linalg.norm(mouth - eyes)))
    # skin model from the cheeks / nose (a,b chroma + loose L)
    yy, xx = np.mgrid[0:H, 0:W]
    fc = (eyes + mouth) / 2
    disc = ((xx - fc[0]) ** 2 + (yy - fc[1]) ** 2 < (0.8 * s) ** 2) & A
    if disc.sum() < 20:
        disc = ((xx - fc[0]) ** 2 + (yy - fc[1]) ** 2 < (1.4 * s) ** 2) & A
    sk = lab[disc]
    mu = np.median(sk, 0)
    sd = np.maximum(np.percentile(np.abs(sk - mu), 75, axis=0) * 1.6, [9.0, 4.0, 4.0])
    d = np.sqrt(((lab[..., 1] - mu[1]) / sd[1]) ** 2 + ((lab[..., 2] - mu[2]) / sd[2]) ** 2 + ((lab[..., 0] - mu[0]) / max(11.0, 1.1 * sd[0])) ** 2)
    skin = (d < 2.4) & A
    lab_ = np.full((H, W), -1, np.int8)
    R = REGIONS.index
    # zones
    head_c = (eyes * 0.6 + mouth * 0.4) - np.array([0, 0.4 * s])
    head = ((xx - head_c[0]) ** 2 / (2.3 * s) ** 2 + (yy - head_c[1]) ** 2 / (2.9 * s) ** 2 < 1) & (yy < (sh_l[1] + sh_r[1]) / 2 - 0.2 * s)
    size = (W, H)
    torso = _zone(size, lambda dr: dr.polygon([tuple(sh_l + (sh_l - sh_r) * 0.18 - [0, 0.12 * sw]),
                                                 tuple(sh_r + (sh_r - sh_l) * 0.18 - [0, 0.12 * sw]),
                                                 tuple(hp_r + (hp_r - hp_l) * 0.35), tuple(hp_l + (hp_l - hp_r) * 0.35)], fill=1))
    arms = _zone(size, lambda dr: [_capsule(dr, P(i), P(j), 0.16 * sw, 1) for i, j in ((11, 13), (12, 14), (13, 15), (14, 16))])
    hand = _zone(size, lambda dr: [_capsule(dr, P(i), P(j), 0.11 * sw, 1) for i, j in ((15, 19), (16, 20), (15, 17), (16, 18))])
    hipw = max(8.0, float(np.linalg.norm(hp_l - hp_r)))
    legs_up = _zone(size, lambda dr: [_capsule(dr, P(i), P(j), 0.42 * hipw, 1) for i, j in ((23, 25), (24, 26))] +
                    [dr.polygon([tuple(hp_l + (hp_l - hp_r) * 0.3), tuple(hp_r + (hp_r - hp_l) * 0.3), tuple(P(26)), tuple(P(25))], fill=1)])
    legs_lo = _zone(size, lambda dr: [_capsule(dr, P(i), P(j), 0.30 * hipw, 1) for i, j in ((25, 27), (26, 28))])
    feet = _zone(size, lambda dr: [_capsule(dr, P(i), P(j), 0.28 * hipw, 1) for i, j in ((27, 31), (28, 32), (29, 31), (30, 32))])
    nonskin = A & ~skin
    # hair: non-skin inside the head zone above the mouth; dark-ish beard below the mouth too
    eye_y = eyes[1]
    hairish = nonskin & head & ((yy < eye_y + 0.2 * s) | (lab[..., 0] < 45))
    lab_[A & head & skin] = R("skin")
    lab_[hairish] = R("hair")
    lab_[nonskin & head & (lab_ < 0)] = R("accessory")
    body = A & ~head
    lab_[body & skin & (torso | arms | hand | legs_up | legs_lo | feet)] = R("skin")
    lab_[body & nonskin & (torso | arms)] = R("top")
    lab_[body & nonskin & legs_up & ~hand & (lab_ < 0)] = R("bottom")
    hsel = body & nonskin & hand & (lab_ < 0)     # hands in pockets / on the hips: cloth colour wins over accessory
    if hsel.any():
        idx = np.nonzero(hsel)
        best = np.full(len(idx[0]), 1e9); lbl = np.full(len(idx[0]), R("accessory"))
        for k in ("top", "bottom"):
            ksel = lab_ == R(k)
            if ksel.sum() > 30:
                dk = _cdist(lab[hsel], np.median(lab[ksel], 0))
                take = (dk < 16) & (dk < best)
                best[take] = dk[take]; lbl[take] = R(k)
        lab_[idx] = lbl
    lo = body & nonskin & legs_lo & (lab_ < 0) & ~feet
    if lo.any():                                   # shorts/trousers continuing below the knee vs socks: compare to bottom colour
        bsel = lab_ == R("bottom")
        if bsel.any():
            bm = np.median(lab[bsel], 0)
            dd = _cdist(lab[lo], bm)
            idx = np.nonzero(lo)
            near = dd < 18
            lab_[idx[0][near], idx[1][near]] = R("bottom")
            lab_[idx[0][~near], idx[1][~near]] = R("socks")
        else:
            lab_[lo] = R("socks")
    fsel = body & nonskin & feet & (lab_ < 0)
    ssel = lab_ == R("socks")
    if fsel.any() and ssel.sum() > 30:          # sock colour continuing into the foot zone stays sock
        sm = np.median(lab[ssel], 0)
        idx = np.nonzero(fsel)
        near = _cdist(lab[fsel], sm) < 14
        lab_[idx[0][near], idx[1][near]] = R("socks")
        fsel = fsel & (lab_ < 0)
    lab_[fsel] = R("shoes")
    # collar / neckline inside the head zone below the mouth that matches the top's colour -> top (not beard)
    tsel0 = lab_ == R("top")
    nk = head & (lab_ == R("hair")) & (yy > mouth[1])
    if nk.any() and tsel0.sum() > 200:
        idx = np.nonzero(nk)
        near = _cdist(lab[nk], np.median(lab[tsel0], 0)) < 14
        lab_[idx[0][near], idx[1][near]] = R("top")
    # trim: within the top, a small minority colour cluster far from the top's main colour
    tsel = lab_ == R("top")
    if tsel.sum() > 200:
        tm = np.median(lab[tsel], 0)
        dd = _cdist(lab, tm)
        cand = tsel & (dd > 22)
        cand = ndi.binary_opening(cand, iterations=1) & tsel
        if 0.02 < cand.sum() / tsel.sum() < 0.35:
            lab_[cand] = R("trim")
    # leftovers -> nearest labelled region (within the figure)
    rest = A & (lab_ < 0)
    if rest.any() and (lab_ >= 0).any():
        _, (iy, ix) = ndi.distance_transform_edt(lab_ < 0, return_indices=True)
        lab_[rest] = lab_[iy[rest], ix[rest]]
    # tidy: majority filter removes speckle
    out = lab_.copy()
    for k in range(len(REGIONS)):
        m = lab_ == k
        if m.any():
            m2 = ndi.binary_opening(m, iterations=1)
            out[m & ~m2] = -2
    hole = out == -2
    if hole.any():
        _, (iy, ix) = ndi.distance_transform_edt(hole, return_indices=True)
        out[hole] = out[iy[hole], ix[hole]]
    out[~A] = -1
    return out


def load_region_map(path, size):
    im = Image.open(path).convert("RGBA").resize(size, Image.NEAREST)
    a = np.asarray(im).astype(int)
    keys = list(REGION_COLOURS)
    pal = np.array([REGION_COLOURS[k] for k in keys])
    d = ((a[..., None, :3] - pal[None, None]) ** 2).sum(-1)
    lab_ = np.array([REGIONS.index(k) for k in keys], np.int8)[d.argmin(-1)]
    lab_[(a[..., 3] < 128) | (d.min(-1) > 3 * 60 ** 2)] = -1
    return lab_


def region_map_image(labels):
    H, W = labels.shape
    out = np.zeros((H, W, 4), np.uint8)
    for i, k in enumerate(REGIONS):
        m = labels == i
        out[m, :3] = REGION_COLOURS[k]; out[m, 3] = 255
    return Image.fromarray(out, "RGBA")


def _torso_uv(lms, H, W):
    P = lambda i: np.array(lms[i][:2], float)
    sl, sr, hl, hr = P(11), P(12), P(23), P(24)
    top = (sl + sr) / 2; bot = (hl + hr) / 2
    ax = bot - top; Lt = max(1.0, float(np.linalg.norm(ax))); ax /= Lt
    side = np.array([-ax[1], ax[0]])
    sw = max(1.0, float(np.linalg.norm(sl - sr)))
    yy, xx = np.mgrid[0:H, 0:W]
    rel = np.stack([xx - top[0], yy - top[1]], -1).astype(np.float32)
    v = (rel @ ax) / Lt
    u = (rel @ side) / sw + 0.5
    return u, v, sw / Lt


def pattern_mask(kind, u, v, aspect=1.0, seed=7):
    if kind == "hoops":
        return ((v * 4.0) % 1.0) < 0.5
    if kind == "stripes":
        return ((u * 6.0) % 1.0) < 0.5
    if kind == "sash":
        return np.abs((u - 0.5) * aspect * 1.6 + (v - 0.5)) < 0.12
    if kind == "chest_band":
        return (v > 0.18) & (v < 0.36)
    if kind == "halves":
        return u < 0.5
    if kind == "check":
        return (((v * 4.0) % 1.0) < 0.5) ^ (((u * 4.0) % 1.0) < 0.5)
    if kind == "dots":
        fu, fv = (u * 6.0) % 1.0 - 0.5, (v * 6.0 / max(0.3, aspect)) % 1.0 - 0.5
        return fu * fu + fv * fv < 0.08
    if kind == "camo":
        from scipy import ndimage as ndi
        rng = np.random.default_rng(seed)
        g = ndi.zoom(rng.random((12, 12)), (u.shape[0] / 12.0, u.shape[1] / 12.0), order=3)[:u.shape[0], :u.shape[1]]
        return g > 0.55
    return np.zeros_like(u, bool)


def recolor_cutout(cut, lms, recolor="", overlay="", regions="", log=print):
    """photo path: -> (new cutout, info{summary, preview, labels})"""
    from scipy import ndimage as ndi
    rec = parse(recolor) if recolor else {}
    ov = parse_overlay(overlay) if overlay else None
    if rec.get("pattern") and not ov:
        ov = {"kind": rec["pattern"], "colour": rec.get("pattern_colour", rec.get("trim", (255, 255, 255))), "opacity": 1.0}
    a = np.asarray(cut.convert("RGBA")).copy()
    H, W = a.shape[:2]
    labels = load_region_map(regions, (W, H)) if regions else segment(cut, lms)
    lab = _lab(a[..., :3])
    new = lab.copy()
    done = []
    shift = rec.get("shift")
    for i, k in enumerate(REGIONS):
        m = labels == i
        if not m.any():
            continue
        tgt = rec.get(k)
        if tgt is None and shift and k in ("top", "trim", "bottom", "socks"):
            med = _rgb(np.median(lab[m], 0)[None, None])[0, 0]
            tgt = hue_shift(tuple(int(x) for x in med), shift)
        if tgt is None:
            continue
        w = ndi.gaussian_filter(m.astype(np.float32), 0.8) * (a[..., 3] > 0)
        w = np.where(m, np.maximum(w, 0.85), w * 0.6)
        if float(np.median(lab[m][:, 0])) > 30:      # keep drawn outlines / deep shadow lines dark
            w = w * np.clip((lab[..., 0] - 8.0) / 14.0, 0, 1)
        new = recolour_pixels(new, w, tgt)
        done.append("%s->%s" % (k, hexc(tgt)))
    if ov:
        top = labels == REGIONS.index("top")
        if top.any():
            u, v, asp = _torso_uv(lms, H, W)
            w = top.astype(np.float32)
            if ov["kind"] == "texture":
                tex = Image.open(ov["path"]).convert("RGB")
                tw, th = tex.size
                sw = max(8, int(np.linalg.norm(np.subtract(lms[11][:2], lms[12][:2]))))
                k_ = sw / float(tw) * 1.0
                tex = np.asarray(tex.resize((max(1, int(tw * k_)), max(1, int(th * k_))), Image.LANCZOS)).astype(np.float32)
                ty, tx = tex.shape[:2]
                uu = ((u * sw).astype(int) % tx); vv = ((v * sw / max(asp, 0.2)).astype(int) % ty)
                tcol = _lab(tex[vv, uu].astype(np.uint8))
                Lm = float(np.median(lab[top][:, 0]))
                tl = tcol.copy(); tl[..., 0] = np.clip(tcol[..., 0] + (lab[..., 0] - Lm) * 0.8, 0, 100)
                ww = (w * ov["opacity"])[..., None]
                new = new * (1 - ww) + tl * ww
                done.append("texture %s" % os.path.basename(ov["path"]))
            else:
                pm = pattern_mask(ov["kind"], u, v, asp) & top
                if pm.any():
                    Lm = float(np.median(lab[top][:, 0]))
                    st = (Lm, float(np.median(lab[top][:, 1])), float(np.median(lab[top][:, 2])))
                    ww = ndi.gaussian_filter(pm.astype(np.float32), 0.7) * top * ov["opacity"]
                    new = recolour_pixels(new, ww, ov["colour"], stats=st)
                    done.append("%s %s" % (ov["kind"], hexc(ov["colour"])))
    rgb = _rgb(new)
    out = a.copy()
    sel = a[..., 3] > 0
    out[sel, :3] = rgb[sel]
    res = Image.fromarray(out, "RGBA")
    prev = preview(cut, labels, res)
    info = {"summary": ", ".join(done) or "regions only", "preview": prev, "labels": labels,
            "regions_png": region_map_image(labels)}
    if log:
        log("  recolour: %s" % info["summary"])
    return res, info


def preview(before, labels, after, h=420):
    """before | region map (ESTIMATED) | after, with a legend"""
    from .build import checker, _font
    ims = [before.convert("RGBA"), Image.alpha_composite(before.convert("RGBA").copy(), _tint(region_map_image(labels), 150)),
           after.convert("RGBA")]
    k = h / float(before.height)
    tw = max(150, int(before.width * k))
    sheet = Image.new("RGB", (tw * 3 + 40 + 150, h + 40), (30, 34, 42))
    d = ImageDraw.Draw(sheet)
    for i, (im, t) in enumerate(zip(ims, ("photo", "regions (ESTIMATED)", "recoloured"))):
        x = 10 + i * (tw + 10)
        bg = checker(tw, h, 10)
        sm = im.resize((tw, h), Image.LANCZOS)
        bg.paste(sm, (0, 0), sm)
        sheet.paste(bg, (x, 28))
        d.text((x, 6), t, fill=(230, 230, 230), font=_font(13))
    lx = 30 + 3 * (tw + 10) - 10
    for j, k_ in enumerate(REGIONS):
        y = 32 + j * 20
        d.rectangle([lx, y, lx + 14, y + 14], fill=REGION_COLOURS[k_])
        d.text((lx + 20, y), k_, fill=(230, 230, 230), font=_font(12))
    return sheet


def _tint(im, alpha):
    a = np.asarray(im).copy()
    a[..., 3] = (a[..., 3].astype(int) * alpha // 255).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def write_preview(cfg, out, ctx, report):
    p = getattr(cfg, "_regions_preview", None)
    if p is None:
        return None
    p.save(os.path.join(out, "regions_preview.png"))
    rp = getattr(cfg, "_regions_png", None)
    if rp is not None:
        rp.save(os.path.join(out, "regions.png"))
    return "regions_preview.png + regions.png (paint over it and pass --regions to override)"


# ---------------------------------------------------------------- palette swap on finished sprites (any build / game folder)
def swap_image(im, pairs, tol=26.0):
    """pairs: [(src_rgb, dst_rgb)] - pixels whose chroma/lightness is near a source colour are re-tinted to the
    destination with their shading kept (classic palette swap, but works on anti-aliased / shaded pixels)."""
    a = np.asarray(im.convert("RGBA")).copy()
    sel = a[..., 3] > 0
    if not sel.any() or not pairs:
        return im
    px = a[sel][:, :3]
    lab = _lab(px[None])[0]
    out = lab.copy()
    best = np.full(len(px), 1e9); who = np.full(len(px), -1)
    srcs = [_lab(np.array([[s]], np.uint8))[0, 0] for s, _ in pairs]
    for j, s in enumerate(srcs):
        dch = np.sqrt((lab[:, 1] - s[1]) ** 2 + (lab[:, 2] - s[2]) ** 2)
        dl = np.abs(lab[:, 0] - s[0])
        d = dch + 0.35 * np.maximum(0, dl - 12)
        better = d < best
        best[better] = d[better]; who[better] = j
    for j, (s, (_, dst)) in enumerate(zip(srcs, pairs)):
        m = (who == j) & (best < tol)
        if not m.any():
            continue
        w = np.clip(1.4 - best[m] / tol, 0, 1)
        t = _lab(np.array([[dst]], np.uint8))[0, 0]
        room_t = min(t[0], 100 - t[0]) + 8; room_s = min(s[0], 100 - s[0]) + 8
        g = float(np.clip(room_t / room_s, 0.35, 1.3))
        nl = np.stack([np.clip(t[0] + (lab[m, 0] - s[0]) * g, 0, 100), t[1] + (lab[m, 1] - s[1]) * 0.3,
                       t[2] + (lab[m, 2] - s[2]) * 0.3], 1)
        out[m] = lab[m] * (1 - w[:, None]) + nl * w[:, None]
    a2 = a.copy()
    a2[sel, :3] = _rgb(out[None])[0]
    return Image.fromarray(a2, "RGBA")


def build_source_colours(folder):
    """slot colours of a finished build (character.ini [spec]) -> {region: rgb}; {} for photo builds"""
    import configparser
    ini = configparser.ConfigParser(interpolation=None); ini.optionxform = str
    p = os.path.join(folder, "character.ini")
    if not os.path.isfile(p):
        return {}
    ini.read(p)
    if "spec" not in ini:
        return {}
    from .spec import CharacterSpec
    sp = CharacterSpec()
    for k, v in ini["spec"].items():
        if k in sp.__dataclass_fields__ and k != "extra":
            cur = getattr(sp, k)
            try:
                setattr(sp, k, type(cur)(v) if not isinstance(cur, (list, dict, bool)) else
                        (v.lower() in ("1", "true", "yes") if isinstance(cur, bool) else cur))
            except Exception:
                pass
    c = sp.colours()
    m = {"top": c["shirt"], "trim": c["trim"], "bottom": c["shorts"], "socks": c["socks"], "shoes": c["boots"],
         "hair": c["hair"], "skin": c["skin"], "accessory": c["accessory"]}
    return {k: tuple(int(round(x * 255)) for x in v) for k, v in m.items()}


def recolor_folder(folder, recolor, out=None, src_colours=None, log=print):
    """palette-swap every PNG of a finished build or game drop-in folder -> a new folder (the original is not touched)"""
    import shutil
    rec = parse(recolor)
    src = dict(build_source_colours(folder))
    for k, v in (src_colours or {}).items():
        src[k] = to_rgb(v)
    if not src:
        raise ValueError("no source colours: a photo build needs --from top=#rrggbb,... (the colours to replace)")
    pairs = []
    for k, dst in rec.items():
        if k in REGIONS and k in src and k != "skin":
            pairs.append((src[k], dst))
    if rec.get("shift"):
        for k in ("top", "trim", "bottom", "socks"):
            if k in src and k not in rec:
                pairs.append((src[k], hue_shift(src[k], rec["shift"])))
    if "skin" in rec and "skin" in src:
        pairs.append((src["skin"], rec["skin"]))
    if not pairs:
        raise ValueError("nothing to swap (set regions %s; the build's colours: %s)" % (", ".join(rec), ", ".join(src)))
    out = out or folder.rstrip("/\\") + "_" + re.sub(r"[^a-z0-9_]+", "_", (rec.get("label") or "recolour").lower())
    if os.path.abspath(out) == os.path.abspath(folder):
        raise ValueError("output folder must differ from the input")
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(folder, out)
    n = 0
    for root, _, files in os.walk(out):
        for f in files:
            if f.lower().endswith(".png") and not f.startswith(("regions", "preview_", "faces")):
                p = os.path.join(root, f)
                im = Image.open(p)
                if im.mode not in ("RGBA", "RGB", "P", "LA"):
                    continue
                swap_image(im.convert("RGBA"), pairs).save(p, compress_level=6)
                n += 1
    with open(os.path.join(out, "palette_swap.json"), "w") as f:
        json.dump({"source": folder, "pairs": [{"from": hexc(s), "to": hexc(d)} for s, d in pairs],
                   "set": rec.get("label", ""), "images": n}, f, indent=1)
    log("  recolour: %d images, %d colour pairs -> %s" % (n, len(pairs), out))
    return out, n, pairs
