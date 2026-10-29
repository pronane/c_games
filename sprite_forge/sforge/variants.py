"""Sprite Forge Studio v9 - procedural character variants (crowds, NPC teams, alt costumes).

variants(base_spec, count, seed, vary) -> list of (seed, CharacterSpec, summary)
Every variant is reproducible from its seed: --variant SEED on any build re-creates exactly that one.
vary: comma list of  body (height / weight / build / head / hands)  outfit (top / bottom / shoes / pattern / hair style)
      colours (kit colours, hair colour)  skin (skin tone)  accessories (0-2 from mesh.ACCESSORIES)  face (facial hair)
PHOTO builds: a variant is a recolour of the photo's own clothing / hair (estimated regions) + a body scale
(height / width) - never a new image of the person."""
from __future__ import annotations
import copy
import json
import os
import random

from PIL import Image, ImageDraw

DEFAULT_VARY = "body,outfit,colours,accessories"
VARY_KEYS = ["body", "outfit", "colours", "skin", "accessories", "face"]

_PALETTES = [  # (top, trim, bottom, socks, shoes) - readable team-ish combinations
    ("#c4161c", "#ffffff", "#ffffff", "#c4161c", "#111111"), ("#1c3fb0", "#ffffff", "#0d1a4a", "#1c3fb0", "#111111"),
    ("#0b7a3b", "#ffffff", "#ffffff", "#0b7a3b", "#111111"), ("#f2c512", "#111111", "#111111", "#f2c512", "#111111"),
    ("#151518", "#d4af37", "#151518", "#151518", "#d4af37"), ("#6cace4", "#0b1f4b", "#0b1f4b", "#0b1f4b", "#ffffff"),
    ("#7a1530", "#ffffff", "#ffffff", "#7a1530", "#111111"), ("#e2401c", "#ffc21a", "#2a0e08", "#e2401c", "#2a0e08"),
    ("#4b136e", "#111111", "#111111", "#4b136e", "#111111"), ("#d4a017", "#1f3c88", "#1f3c88", "#d4a017", "#4a3020"),
    ("#c8a165", "#5b3a1e", "#7b5a36", "#c8a165", "#4a3020"), ("#2e8b57", "#f5deb3", "#3b2f2f", "#2e8b57", "#3b2f2f"),
    ("#ff6f91", "#ffffff", "#2d2d2d", "#ff6f91", "#ffffff"), ("#00a6a6", "#f2f2f2", "#1b2a41", "#00a6a6", "#f2f2f2"),
    ("#8d99ae", "#2b2d42", "#2b2d42", "#8d99ae", "#2b2d42"), ("#f2f2f2", "#c4161c", "#c4161c", "#f2f2f2", "#111111"),
]
_HAIR = ["black", "dark_brown", "brown", "light_brown", "auburn", "ginger", "blonde", "platinum", "grey"]
_SKIN = ["fair", "light", "light_medium", "medium", "olive", "tan", "brown", "dark_brown", "dark", "deep"]
_HAIR_STYLE = ["bald", "buzz", "short", "long", "ponytail", "curly", "afro", "bun"]
_TOPS = ["jersey", "tshirt", "longsleeve", "tank", "hoodie"]
_BUILDS = ["slim", "lean", "average", "athletic", "stocky", "heavy"]
_PATTERNS = ["", "", "", "hoops", "stripes", "sash", "chest_band", "halves", "check"]
_ACC_GROUPS = {"head": ["cap", "beanie", "headband", "helmet", "crown", "horns"], "eyes": ["glasses", "sunglasses", "visor"],
               "face": ["mask"], "back": ["backpack", "cape", "satchel"], "neck": ["scarf"],
               "body": ["belt", "armor", "shoulder_pads"], "limbs": ["wristbands", "gloves", "kneepads"]}


def parse_vary(v):
    ks = [x.strip().lower() for x in (v or DEFAULT_VARY).replace("+", ",").split(",") if x.strip()]
    if "all" in ks:
        return set(VARY_KEYS)
    bad = [k for k in ks if k not in VARY_KEYS]
    if bad:
        raise ValueError("unknown vary key(s) %s (use %s or all)" % (", ".join(bad), ", ".join(VARY_KEYS)))
    return set(ks)


def vary_spec(base, seed, vary=DEFAULT_VARY):
    """one reproducible variant of a CharacterSpec -> (spec, summary list)"""
    from .spec import BUILDS
    r = random.Random(int(seed) * 7919 + 17)
    keys = parse_vary(vary) if isinstance(vary, str) else set(vary)
    sp = copy.deepcopy(base)
    sp.extra = dict(base.extra)
    notes = []
    if "body" in keys:
        sp.height_cm = round(float(base.height_cm) * r.uniform(0.9, 1.08), 1)
        builds = [b for b in _BUILDS if b in BUILDS] or ["average"]
        sp.build = r.choice(builds)
        sp.weight_kg = round(float(base.weight_kg) * (sp.height_cm / float(base.height_cm)) ** 2 * r.uniform(0.85, 1.25), 1)
        sp.head = r.choice(["small", "medium", "medium", "large"])
        sp.hands = r.choice(["small", "medium", "large"])
        notes.append("%.0fcm %s %.0fkg" % (sp.height_cm, sp.build, sp.weight_kg))
    if "outfit" in keys:
        sp.top = r.choice(_TOPS)
        sp.bottom = r.choice(["shorts", "shorts", "trousers"])
        sp.shoes = r.choice(["boots", "trainers", "trainers"])
        sp.hair_style = r.choice(_HAIR_STYLE)
        sp.pattern = r.choice(_PATTERNS)
        notes.append("%s/%s/%s%s, hair %s" % (sp.top, sp.bottom, sp.shoes, (" " + sp.pattern) if sp.pattern else "", sp.hair_style))
    if "colours" in keys:
        top, trim, bottom, socks, shoes = r.choice(_PALETTES)
        sp.top_colour, sp.trim_colour, sp.bottom_colour, sp.socks_colour, sp.shoes_colour = top, trim, bottom, socks, shoes
        sp.pattern_colour = trim
        sp.hair_colour = r.choice(_HAIR)
        sp.accessory_colour = r.choice([top, trim, "#202024", "#e8e8e8"])
        sp.accessory2_colour = r.choice(["#d4af37", trim, "#c0c0c0"])
        notes.append("kit %s/%s/%s, hair %s" % (top, trim, bottom, sp.hair_colour))
    if "skin" in keys:
        sp.skin_tone = r.choice(_SKIN)
        notes.append("skin %s" % sp.skin_tone)
    if "face" in keys:
        sp.facial_hair = r.choice(["none", "none", "stubble", "beard", "moustache"])
        notes.append("face %s" % sp.facial_hair)
    if "accessories" in keys:
        n = r.choice([0, 1, 1, 2, 2, 3])
        groups = r.sample(list(_ACC_GROUPS), k=min(n, len(_ACC_GROUPS)))
        acc = [r.choice(_ACC_GROUPS[g]) for g in groups]
        if sp.hair_style in ("ponytail", "long") and "helmet" in acc:
            acc.remove("helmet")
        sp.accessories = ",".join(acc)
        notes.append("acc " + (sp.accessories or "none"))
    sp.name = "%s_v%d" % (base.name, int(seed))
    return sp, notes


def photo_variant(seed, vary=DEFAULT_VARY):
    """PHOTO variant = recolour spec + body scale; -> (recolor string, (sx, sy), summary)"""
    r = random.Random(int(seed) * 7919 + 17)
    keys = parse_vary(vary) if isinstance(vary, str) else set(vary)
    parts, notes, scale = [], [], (1.0, 1.0)
    if "colours" in keys or "outfit" in keys:
        top, trim, bottom, socks, shoes = r.choice(_PALETTES)
        parts += ["top=" + top, "trim=" + trim, "bottom=" + bottom, "socks=" + socks, "shoes=" + shoes]
        notes.append("kit %s/%s/%s" % (top, trim, bottom))
        if "outfit" in keys:
            pat = r.choice(_PATTERNS)
            if pat:
                parts.append("pattern=" + pat); parts.append("pattern_colour=" + trim)
                notes.append(pat)
    if "colours" in keys and r.random() < 0.5:
        h = r.choice(_HAIR)          # drawn for the seed sequence, but a real person's hair is never recoloured
        notes.append("hair kept (photo)")
    if "body" in keys:
        scale = (round(r.uniform(0.93, 1.08), 3), round(r.uniform(0.92, 1.06), 3))
        notes.append("width x%.2f height x%.2f" % scale)
    if "accessories" in keys or "skin" in keys or "face" in keys:
        notes.append("(photo: accessories / skin / face are not varied - the person's own pixels are kept)")
    return ",".join(parts), scale, notes


def make(base, count=8, seed=1, vary=DEFAULT_VARY):
    return [(seed + i,) + vary_spec(base, seed + i, vary) for i in range(int(count))]


def render_thumbs(specs, cfg_like=None, h=220, move="fight_idle"):
    """idle frame of each variant spec (mannequin renderer) -> list of RGBA images"""
    from . import build as B, moves as MV, render as RD
    rs = RD.RenderSettings(int(h * 0.75), h, int(h * 0.78), h - 6, int(h * 0.375), yaw=35.0, pitch=6, ss=2, outline=True)
    m = MV.MoveSpec(name=move, frames=1, loop=True, motion=move if __import__("sforge.motions", fromlist=["x"]).find_motion(move) else "idle")
    out = []
    for sp in specs:
        rs.figure_h = int(h * 0.78 * sp.scale)
        out.append(B._render_mannequin_move((sp, "", rs, m, ["neutral"], True))[0])
    return out


def sheet(images, labels, title="", cols=8):
    from .build import checker, _font
    n = len(images)
    cols = min(cols, n) or 1
    rows = (n + cols - 1) // cols
    tw = max(im.width for im in images); th = max(im.height for im in images)
    oy = 26 if title else 6
    S = Image.new("RGB", (cols * (tw + 8) + 8, oy + rows * (th + 30) + 4), (30, 34, 42))
    d = ImageDraw.Draw(S)
    if title:
        d.text((8, 6), title, fill=(232, 232, 232), font=_font(13))
    for i, (im, lb) in enumerate(zip(images, labels)):
        x, y = 8 + (i % cols) * (tw + 8), oy + (i // cols) * (th + 30)
        bg = checker(tw, th, 10)
        bg.paste(im, ((tw - im.width) // 2, th - im.height), im)
        S.paste(bg, (x, y))
        d.text((x + 3, y + th + 6), lb, fill=(235, 235, 235), font=_font(12))
    return S


def write(out_dir, base, count=8, seed=1, vary=DEFAULT_VARY, log=print, h=220):
    """variants_sheet.png + variants.json + variant_<seed>.txt spec files (mannequin / spec)"""
    from .spec import save_spec
    os.makedirs(out_dir, exist_ok=True)
    vs = make(base, count, seed, vary)
    ims = render_thumbs([sp for _, sp, _ in vs], h=h)
    sh = sheet(ims, ["seed %d" % s for s, _, _ in vs], "%s - %d procedural variants (vary: %s)" % (base.name, len(vs), vary),
               cols=4 if len(vs) <= 8 else 8)
    sh.save(os.path.join(out_dir, "variants_sheet.png"))
    js = []
    for (s, sp, notes), im in zip(vs, ims):
        fn = "variant_%d.txt" % s
        save_spec(sp, os.path.join(out_dir, fn))
        js.append({"seed": s, "name": sp.name, "spec": fn, "summary": "; ".join(notes)})
    with open(os.path.join(out_dir, "variants.json"), "w") as f:
        json.dump({"base": base.name, "vary": vary, "seed": seed, "count": len(vs), "variants": js,
                   "rebuild": "forge.py build --spec <base> --variant SEED --vary '%s'" % vary}, f, indent=1)
    log("  variants: %d -> %s" % (len(vs), os.path.join(out_dir, "variants_sheet.png")))
    return vs, sh


def write_photo(out_dir, cut, lms, count=8, seed=1, vary=DEFAULT_VARY, log=print, h=300):
    """PHOTO: recoloured + rescaled copies of the user's own cutout (ESTIMATED regions) -> variants_sheet.png"""
    from . import recolor as RC
    os.makedirs(out_dir, exist_ok=True)
    ims, labels, js = [], [], []
    for i in range(int(count)):
        s = seed + i
        rec, (sx, sy), notes = photo_variant(s, vary)
        im = cut
        if rec:
            im, _ = RC.recolor_cutout(cut, lms, rec, log=None)
        k = h / float(cut.height)
        im = im.resize((max(1, int(cut.width * k * sx)), max(1, int(cut.height * k * sy))), Image.LANCZOS)
        ims.append(im); labels.append("seed %d" % s)
        js.append({"seed": s, "recolor": rec, "scale": [sx, sy], "summary": "; ".join(notes)})
    sh = sheet(ims, labels, "%d photo variants (recolour of the photo's own pixels, ESTIMATED regions)" % len(ims),
               cols=4 if len(ims) <= 8 else 8)
    sh.save(os.path.join(out_dir, "variants_sheet.png"))
    with open(os.path.join(out_dir, "variants.json"), "w") as f:
        json.dump({"mode": "photo", "vary": vary, "seed": seed, "variants": js,
                   "rebuild": "forge.py build --photo <cutout> --variant SEED"}, f, indent=1)
    log("  photo variants: %d -> %s" % (len(ims), os.path.join(out_dir, "variants_sheet.png")))
    return js, sh
