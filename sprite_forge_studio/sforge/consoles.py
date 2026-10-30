"""Console target presets + the console/ export (retro tile banks, CLUT texture pages, low-poly models).

IMPORTANT: hardware numbers are typical/practical values for a single character, not hard specs for every
game. Values marked APPROX in `approx` are rules of thumb (budgets differ per engine, scene and mode).
The out/<name>/ layout is never changed; everything here goes to out/<name>/console/.
"""
from __future__ import annotations
import json
import math
import os
import numpy as np
from PIL import Image, ImageDraw

# ------------------------------------------------------------------ master palettes / colour spaces
_NES_HEX = (
    "7C7C7C 0000FC 0000BC 4428BC 940084 A80020 A81000 881400 503000 007800 006800 005800 004058 000000 000000 000000 "
    "BCBCBC 0078F8 0058F8 6844FC D800CC E40058 F83800 E45C10 AC7C00 00B800 00A800 00A844 008888 000000 000000 000000 "
    "F8F8F8 3CBCFC 6888FC 9878F8 F878F8 F85898 F87858 FCA044 F8B800 B8F818 58D854 58F898 00E8D8 787878 000000 000000 "
    "FCFCFC A4E4FC B8B8F8 D8B8F8 F8B8F8 F8A4C0 F0D0B0 FCE0A8 F8D878 D8F878 B8F8B8 B8F8D8 00FCFC F8D8F8 000000 000000").split()
# usable NES colour indices (skip duplicate blacks $xD-$xF except $0F, and $0D "blacker than black")
NES_USABLE = [i for i in range(64) if (i & 15) < 13 or i in (0x0F, 0x2D, 0x3D)]
NES_RGB = {i: tuple(int(_NES_HEX[i][k:k + 2], 16) for k in (0, 2, 4)) for i in range(64)}
GB_SHADES = [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)]   # DMG green, 0 = lightest


def _a2600_palette():
    """APPROX NTSC TIA palette: 16 hues x 8 luminances (computed, not measured)."""
    out = {}
    for hue in range(16):
        for lum in range(8):
            y = 0.06 + lum / 7.0 * 0.88
            if hue == 0:
                r = g = b = y
            else:
                ang = (hue - 1) / 15.0 * 2 * math.pi * 0.97 + 2.7
                i, q = 0.18 * math.cos(ang), 0.18 * math.sin(ang)
                r, g, b = y + 0.956 * i + 0.621 * q, y - 0.272 * i - 0.647 * q, y - 1.106 * i + 1.703 * q
            out[(hue << 4) | (lum << 1)] = tuple(int(max(0, min(1, c)) * 255) for c in (r, g, b))
    return out


A2600_RGB = _a2600_palette()


def _levels(bits):
    n = (1 << bits) - 1
    return [int(round(v * 255 / n)) for v in range(n + 1)]


def snap_colour(rgb, space):
    """-> (display rgb, native value) for one colour in a console colour space."""
    r, g, b = [int(x) for x in rgb[:3]]
    if space in ("bgr555", "rgb555"):
        q = [int(round(c * 31 / 255)) for c in (r, g, b)]
        disp = tuple((c << 3) | (c >> 2) for c in q)
        nat = q[0] | (q[1] << 5) | (q[2] << 10) if space == "bgr555" else (q[2] | (q[1] << 5) | (q[0] << 10))
        return disp, nat
    if space == "sms":   # 00BBGGRR
        q = [int(round(c * 3 / 255)) for c in (r, g, b)]
        return tuple(c * 85 for c in q), q[0] | (q[1] << 2) | (q[2] << 4)
    if space == "gen":   # 0000 BBB0 GGG0 RRR0 (APPROX linear levels; real VDP output is non-linear)
        q = [int(round(c * 7 / 255)) for c in (r, g, b)]
        return tuple(int(round(c * 255 / 7)) for c in q), (q[0] << 1) | (q[1] << 5) | (q[2] << 9)
    if space == "rgba4444":
        q = [int(round(c * 15 / 255)) for c in (r, g, b)]
        return tuple(c * 17 for c in q), (q[0] << 8) | (q[1] << 4) | q[2] | 0xF000
    if space in ("nes", "gb", "a2600"):
        table = ({i: NES_RGB[i] for i in NES_USABLE} if space == "nes" else
                 {i: c for i, c in enumerate(GB_SHADES)} if space == "gb" else A2600_RGB)
        best = min(table, key=lambda k: _dist((r, g, b), table[k]))
        return table[best], best
    return (r, g, b), (r << 16) | (g << 8) | b   # rgb888


def _dist(a, b):  # perceptual-ish weighted RGB distance
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return 2 * dr * dr + 4 * dg * dg + 3 * db * db


# ------------------------------------------------------------------ presets
def P(key, label, **k):
    d = dict(key=key, label=label, tiles=False, tex=False, frame_max=(512, 512), tile=(8, 8), colours=0, palettes=1,
             space="rgb888", fmt=None, bank_tiles=0, line_sprites=0, line_px=0, pow2=False, align=1, max_tex=8192,
             tris=None, model_tex=0, dither=True, approx="", notes="")
    d.update(k); return d


PRESETS = {p["key"]: p for p in [
    P("atari2600", "Atari 2600", tiles=True, frame_max=(8, 32), tile=(8, 1), colours=1, space="a2600", fmt="a2600",
      dither=False, aspect=4.0, approx="frame height (kernel dependent), NTSC palette RGB values",
      notes="1 player sprite = 8 px wide, 1 colour per scanline (colour table per row). Rows are stretched up to 4x vertically (one row = several scanlines, typical of 2600 kernels). Double width via NUSIZ is not used."),
    P("nes", "NES / Famicom", tiles=True, frame_max=(32, 32), tile=(8, 8), colours=3, palettes=1, space="nes", fmt="nes2",
      bank_tiles=256, line_sprites=8, approx="32x32 character size (typical, metasprite of 8x8 sprites); 64 sprites total",
      notes="2bpp CHR tiles, 3 colours + transparent per sprite palette (4 sprite palettes exist; one is used here), 8 sprites per scanline."),
    P("sms", "Sega Master System", tiles=True, frame_max=(32, 32), tile=(8, 8), colours=15, space="sms", fmt="sms4",
      bank_tiles=256, line_sprites=8, approx="32x32 character size", notes="4bpp planar tiles, 15 colours + transparent from 64 (RGB222), 8 sprites per line."),
    P("gb", "Game Boy (DMG)", tiles=True, frame_max=(32, 32), tile=(8, 8), colours=3, space="gb", fmt="gb2",
      bank_tiles=256, line_sprites=10, approx="32x32 character size; colours shown with DMG green tint",
      notes="2bpp tiles, 3 shades + transparent (OBP0), 10 sprites per line, 40 total."),
    P("snes", "SNES / Super Famicom", tiles=True, frame_max=(64, 64), tile=(8, 8), colours=15, space="bgr555", fmt="snes4",
      bank_tiles=512, line_px=256, approx="64x64 character size; 512 sprite tiles in VRAM at once (16 KB name tables)",
      notes="4bpp planar (SNES format) tiles, 15 colours + transparent per palette (8 OBJ palettes), BGR555. 32 sprites / 34 tiles per line."),
    P("genesis", "Sega Genesis / Mega Drive", tiles=True, frame_max=(64, 64), tile=(8, 8), colours=15, space="gen", fmt="gen4",
      bank_tiles=512, line_px=320, approx="64x64 character, 512 tiles reserved for sprites (VRAM is 64 KB shared), linear RGB333 levels",
      notes="4bpp packed tiles (left pixel = high nibble), 15 colours + transparent per line (4 palettes), 9-bit colour, 20 sprites / 320 px per line."),
    P("gba", "Game Boy Advance", tiles=True, frame_max=(64, 64), tile=(8, 8), colours=15, space="bgr555", fmt="gba4",
      bank_tiles=1024, line_px=0, approx="64x64 character (largest OBJ size); 1024 4bpp tiles in OBJ VRAM (32 KB, tile modes 0-2)",
      notes="4bpp linear tiles (left pixel = low nibble), 15 colours + transparent per palette (16 OBJ palettes), BGR555."),
    P("ds", "Nintendo DS", tiles=True, frame_max=(64, 64), tile=(8, 8), colours=15, space="bgr555", fmt="gba4",
      bank_tiles=1024, tris=600, model_tex=128, approx="OBJ VRAM depends on bank setup (1024 tiles assumed); 3D budget ~600 tris per character (2048 per frame total)",
      notes="Same 4bpp OBJ format as GBA; also a low-poly 3D model for the 3D engine."),
    P("ps1", "PlayStation 1", tex=True, frame_max=(128, 128), colours=255, space="rgb555", max_tex=256, pow2=False, align=4,
      tris=600, model_tex=128, approx="128 px sprite frames, ~600 tris / 128x128 texture per character (game dependent)",
      notes="8bpp CLUT texture pages (256x256), 15-bit colour, 255 colours + transparent (colour 0 = transparent)."),
    P("n64", "Nintendo 64", tex=True, frame_max=(64, 64), colours=15, space="rgb555", max_tex=1024, pow2=True,
      tris=900, model_tex=64, approx="TMEM is 4 KB: CI4 64x64 per load; ~900 tris per character",
      notes="Each frame is a power-of-two CI4 (16-colour) texture that fits TMEM; frames are stored on pow2 sheet pages."),
    P("saturn", "Sega Saturn", tex=True, frame_max=(128, 128), colours=255, space="rgb555", max_tex=512, align=8,
      tris=1000, model_tex=64, approx="VDP1 sprite width must be a multiple of 8; ~500 quads (1000 tris) per character",
      notes="8bpp palette sprites (VDP1), 15-bit colour."),
    P("dreamcast", "Sega Dreamcast", tex=True, frame_max=(256, 256), colours=0, space="rgba4444", max_tex=1024, pow2=True,
      tris=3000, model_tex=256, approx="~3000 tris, 256x256 textures per character",
      notes="Power-of-two ARGB4444 textures (16-bit), up to 1024x1024."),
    P("ps2gc", "PS2 / GameCube / Xbox", tex=True, frame_max=(256, 256), colours=255, space="rgb888", max_tex=1024, pow2=True,
      tris=5000, model_tex=512, approx="~5000 tris, 512x512 texture per character",
      notes="8bpp CLUT pow2 textures (PS2 style); GC/Xbox can also use the RGBA pages from out/<name>/."),
    P("psp", "PSP", tex=True, frame_max=(128, 128), colours=255, space="rgb888", max_tex=512, pow2=True,
      tris=3000, model_tex=256, approx="~3000 tris, 256x256 texture", notes="8bpp CLUT pow2 textures, max 512x512."),
    P("wii360ps3", "Wii / Xbox 360 / PS3", tex=True, frame_max=(512, 512), colours=0, space="rgb888", max_tex=2048, pow2=True,
      tris=15000, model_tex=1024, approx="~15k tris, 1024 textures (Wii far lower: ~5k / 512)", notes="RGBA8 pow2 pages up to 2048."),
    P("switch_ps4", "Switch / PS4 / Xbox One", tex=True, frame_max=(512, 512), colours=0, space="rgb888", max_tex=4096,
      tris=40000, model_tex=2048, approx="~40k tris, 2048 textures (hero characters often more)", notes="RGBA8 pages up to 4096."),
    P("ps5", "PS5 / Xbox Series", tex=True, frame_max=(1024, 1024), colours=0, space="rgb888", max_tex=8192,
      tris=100000, model_tex=4096, approx="~100k tris, 4096 textures (no hard limit)", notes="RGBA8 pages up to 8192."),
    P("pc_hd", "PC HD", tex=True, frame_max=(1024, 1024), colours=0, space="rgb888", max_tex=8192, tris=None, model_tex=2048,
      approx="no hard limits", notes="Full-colour RGBA pages; model at standard detail."),
]}
ORDER = list(PRESETS)
LABELS = {k: v["label"] for k, v in PRESETS.items()}


def by_label(s):
    s = (s or "").strip()
    for k, v in PRESETS.items():
        if s in (k, v["label"]):
            return k
    n = s.lower().replace("playstation ", "ps").replace("playstation", "ps").replace(" ", "")
    for k, v in PRESETS.items():
        if n in (k, v["label"].lower().replace(" ", "")) or (n and v["label"].lower().replace(" ", "").startswith(n)):
            return k
    return ""


def describe(key):
    p = PRESETS[key]
    fw, fh = p["frame_max"]
    parts = ["max frame %dx%d" % (fw, fh)]
    if p["tiles"]:
        parts.append("%dx%d tiles" % p["tile"])
    parts.append(("%d colours + transparent" % p["colours"]) if p["colours"] else "full colour")
    if p["bank_tiles"]:
        parts.append("%d tiles/bank" % p["bank_tiles"])
    if p["tex"]:
        parts.append("pages <= %d%s" % (p["max_tex"], " pow2" if p["pow2"] else ""))
    if p["tris"]:
        parts.append("model <= %d tris" % p["tris"])
    return ", ".join(parts) + "  (approx: %s)" % (p["approx"] or "-")


# ------------------------------------------------------------------ helpers
def _pow2(n):
    return 1 << max(0, int(math.ceil(math.log2(max(1, n)))))


def _resize_rgba(im, w, h):
    pm = im.convert("RGBa").resize((w, h), Image.LANCZOS if (w < im.width) else Image.NEAREST)
    return pm.convert("RGBA")


def _union_bbox(frames):
    bb = None
    for fr in frames:
        for im in fr:
            b = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
            if b:
                bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]))
    return bb


def build_palette(images, n, space, alpha_thr=128):
    """Shared palette for all frames: median cut on every opaque pixel, then snapped to the console colour space."""
    px = []
    for im in images:
        a = np.asarray(im)
        m = a[..., 3] >= alpha_thr
        if m.any():
            px.append(a[..., :3][m])
    if not px:
        return [], []
    px = np.concatenate(px)
    if len(px) > 250000:
        px = px[np.random.RandomState(1).choice(len(px), 250000, replace=False)]
    strip = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8), "RGB")
    want = n
    for _ in range(4):
        q = strip.quantize(colors=min(256, want), method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[:3 * min(256, want)]
        used = sorted(set(np.asarray(q).ravel().tolist()))
        cols = [tuple(pal[3 * i:3 * i + 3]) for i in used]
        disp, nat = [], []
        for c in cols:
            d, v = snap_colour(c, space)
            if v not in nat:
                disp.append(d); nat.append(v)
        if len(nat) >= n or want >= 256 or len(cols) < want:
            break
        want = min(256, want + (n - len(nat)))     # snapping merged colours: ask for a few more
    return disp[:n], nat[:n]


def quantize_frame(im, disp, dither, alpha_thr=128):
    """RGBA -> index array (0 = transparent, 1..len(disp) = palette)."""
    a = np.asarray(im)
    mask = a[..., 3] >= alpha_thr
    K = len(disp)
    if K == 0:
        return np.zeros(mask.shape, np.uint8)
    rgb = a[..., :3].copy()
    if mask.any():
        rgb[~mask] = rgb[mask].mean(axis=0).astype(np.uint8)
    if dither:
        pal = list(sum((list(c) for c in disp), []))
        pal += list(disp[0]) * (256 - K)
        pimg = Image.new("P", (1, 1)); pimg.putpalette(pal)
        idx = np.asarray(Image.fromarray(rgb, "RGB").quantize(palette=pimg, dither=Image.Dither.FLOYDSTEINBERG)).astype(np.int32)
        idx[idx >= K] = 0
    else:
        P_ = np.array(disp, np.int32)
        flat = rgb.reshape(-1, 3).astype(np.int32)
        w = np.array([2, 4, 3])
        d = (((flat[:, None, :] - P_[None, :, :]) ** 2) * w).sum(-1)
        idx = d.argmin(1).reshape(mask.shape)
    out = (idx + 1).astype(np.uint8)
    out[~mask] = 0
    return out


def indexed_png(idx, disp, path, transparent=(255, 0, 255)):
    im = Image.fromarray(idx.astype(np.uint8), "P")
    pal = list(transparent) + sum((list(c) for c in disp), [])
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.info["transparency"] = 0
    im.save(path, transparency=0, optimize=False)
    return im


def write_jasc(path, disp, transparent=(255, 0, 255)):
    cols = [transparent] + list(disp)
    with open(path, "w", newline="\r\n") as f:
        f.write("JASC-PAL\n0100\n%d\n" % len(cols))
        for c in cols:
            f.write("%d %d %d\n" % tuple(c))


def encode_tile(t, fmt):
    """t: 2D uint8 tile (8x8) of palette indices -> bytes in the console's native tile format."""
    t = np.asarray(t, np.uint8); out = bytearray()
    def plane(row, b):
        v = 0
        for x in range(8):
            v = (v << 1) | ((int(row[x]) >> b) & 1)
        return v
    if fmt == "nes2":
        out += bytes(plane(t[y], 0) for y in range(8)); out += bytes(plane(t[y], 1) for y in range(8))
    elif fmt == "gb2":
        for y in range(8):
            out += bytes((plane(t[y], 0), plane(t[y], 1)))
    elif fmt == "sms4":
        for y in range(8):
            out += bytes(plane(t[y], b) for b in range(4))
    elif fmt == "snes4":
        for y in range(8):
            out += bytes((plane(t[y], 0), plane(t[y], 1)))
        for y in range(8):
            out += bytes((plane(t[y], 2), plane(t[y], 3)))
    elif fmt == "gen4":
        for y in range(8):
            out += bytes(((int(t[y][x]) & 15) << 4) | (int(t[y][x + 1]) & 15) for x in range(0, 8, 2))
    elif fmt == "gba4":
        for y in range(8):
            out += bytes((int(t[y][x]) & 15) | ((int(t[y][x + 1]) & 15) << 4) for x in range(0, 8, 2))
    else:
        raise ValueError(fmt)
    return bytes(out)


def _carr(name, data, ctype="uint8_t", per=16, fmt="0x%02X"):
    s = ["static const %s %s[%d] = {" % (ctype, name, max(1, len(data)))]
    for i in range(0, len(data), per):
        s.append("    " + ", ".join(fmt % v for v in data[i:i + per]) + ",")
    if not data:
        s.append("    0")
    s.append("};")
    return "\n".join(s)


HDR_TYPES = """#ifndef SFT_TYPES_DEFINED
#define SFT_TYPES_DEFINED
#include <stdint.h>
/* Sprite Forge console export - shared types.
   A frame is a grid of tw x th tiles. maps[map + ty*tw + tx] = tile entry for that cell:
   bits 0-11 = tile index inside the frame's bank, bit 14 = horizontal flip, 0xFFFF = empty (draw nothing).
   pivot_x / ground_y = feet position inside the frame (pixels). rise = how many pixels the character is in the air
   in this frame (jumps): draw it 'rise' pixels higher. Sprites face RIGHT: flip the whole frame
   (mirror tx and toggle bit 14) to face left. */
#define SFT_EMPTY  0xFFFF
#define SFT_HFLIP  0x4000
#define SFT_TILE(e) ((e) & 0x0FFF)
typedef struct { uint8_t bank, tw, th, pad; uint16_t pivot_x, ground_y; uint16_t map; int16_t rise; } SFTFrame;
typedef struct { const char *name; uint16_t first, count; uint8_t fps, loop; } SFTAnim;
typedef struct { const uint8_t *tiles; uint16_t count; } SFTBank;
typedef struct { uint16_t x, y, w, h; uint8_t page; uint8_t pad; int16_t pivot_x, ground_y, rise; } SFTRect;
#endif
"""


# ------------------------------------------------------------------ main export
def export(out_dir, name, ordered, moves, key, ground_y, pivot_x, dither=None, log=print, model=None):
    """ordered: [(move, [RGBA frames])]; moves: {move: MoveSpec}; model: callable(max_tris)->(T,B,M,detail) or None.
    Writes out_dir/console/ and returns the stats dict (also saved as console/console.json)."""
    p = PRESETS[key]
    cdir = os.path.join(out_dir, "console")
    if os.path.isdir(cdir):
        import shutil
        shutil.rmtree(cdir)
    os.makedirs(os.path.join(cdir, "frames"))
    dither = p["dither"] if dither is None else dither
    sym = "".join(c if c.isalnum() else "_" for c in name) + "_" + key
    st = {"console": key, "label": p["label"], "approx": p["approx"], "notes": p["notes"], "limits": {
        "frame_max": p["frame_max"], "tile": p["tile"] if p["tiles"] else None, "colours": p["colours"], "space": p["space"],
        "bank_tiles": p["bank_tiles"], "pow2": p["pow2"], "max_tex": p["max_tex"] if p["tex"] else None,
        "tris": p["tris"], "model_tex": p["model_tex"]}, "dither": bool(dither), "warnings": []}
    W = lambda m: (st["warnings"].append(m), log("  ! console: " + m))
    # --- 0. airborne frames are dropped onto the ground line; the height is kept as 'rise' (move the sprite up by it)
    rises = {}
    grounded = []
    for mv, fr in ordered:
        out_fr = []
        for i, im in enumerate(fr):
            a = np.asarray(im.getchannel("A")) > 40
            ys = np.nonzero(a.any(axis=1))[0]
            d = int(ground_y - 1 - ys[-1]) if len(ys) else 0
            if d > 1:
                sh_ = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh_.paste(im, (0, d)); im = sh_
                rises[(mv, i)] = d
            out_fr.append(im)
        grounded.append((mv, out_fr))
    ordered = grounded
    # --- 1. crop to the union box (keeping ground + pivot), scale to fit the frame limit
    fw0, fh0 = ordered[0][1][0].size
    bb = _union_bbox([fr for _, fr in ordered]) or (0, 0, fw0, fh0)
    x0, y0, x1, y1 = bb
    y1 = max(y1, ground_y + 1)
    half = max(pivot_x - x0, x1 - pivot_x)                 # symmetric around the pivot so flipping is trivial
    x0, x1 = max(0, pivot_x - half), min(fw0, pivot_x + half)
    mw, mh = p["frame_max"]
    cw, ch = x1 - x0, y1 - y0
    s = min(1.0, mw / cw, mh / ch)
    if p["tex"] and not p["tiles"] and s >= 1.0:
        x0, y0, x1, y1, cw, ch = 0, 0, fw0, fh0, fw0, fh0        # HD targets keep the original frame
        s = min(1.0, mw / cw, mh / ch)
    sy = min(1.0, mh / ch, s * p.get("aspect", 1.0))       # 2600: tall, chunky pixels (one sprite row = several scanlines)
    sw, sh = max(1, int(round(cw * s))), max(1, int(round(ch * sy)))
    if p["tiles"]:
        tw, th = p["tile"]
        FW, FH = min(mw, int(math.ceil(sw / tw)) * tw), min(mh, int(math.ceil(sh / th)) * th)
    elif p["pow2"]:
        FW, FH = min(mw, _pow2(sw)), min(mh, _pow2(sh))
    else:
        a = p["align"]
        FW, FH = int(math.ceil(sw / a)) * a, int(math.ceil(sh / a)) * a
    sw, sh = min(sw, FW), min(sh, FH)
    ox, oy = (FW - sw) // 2, FH - sh                       # bottom-aligned: the ground line is kept
    gy = oy + int(round((ground_y - y0) * sy)); gy = min(gy, FH - 1)
    px = ox + int(round((pivot_x - x0) * s))
    if s < 1.0:
        log("  console %s: character scaled x%.3f into %dx%d frames" % (key, s, FW, FH))
    small = []
    for mv, fr in ordered:
        ims = []
        for im in fr:
            c = im.crop((x0, y0, x1, y1))
            c = _resize_rgba(c, sw, sh) if (sw, sh) != c.size else c
            cell = Image.new("RGBA", (FW, FH), (0, 0, 0, 0)); cell.paste(c, (ox, oy), c)
            ims.append(cell)
        small.append((mv, ims))
    allims = [im for _, ims in small for im in ims]
    rise_of = lambda mv, i: int(round(rises.get((mv, i), 0) * sy))
    st["rise"] = {"%s_%02d" % k: rise_of(*k) for k in rises}
    st.update(frame_w=FW, frame_h=FH, ground_y=gy, pivot_x=px, scale=round(s, 4), scale_y=round(sy, 4))
    # --- 2. palette + quantize
    indexed = p["colours"] > 0
    if key == "atari2600":
        return _export_2600(cdir, sym, small, moves, st, gy, px, log)
    if indexed:
        disp, nat = build_palette(allims, p["colours"], p["space"])
        st["palette_display"] = [list(c) for c in disp]; st["palette_native"] = nat
        write_jasc(os.path.join(cdir, "palette.pal"), disp)
        sw_ = Image.new("RGB", (16 * (len(disp) + 1), 16), (255, 0, 255))
        d = ImageDraw.Draw(sw_)
        for i, c in enumerate(disp):
            d.rectangle([16 * (i + 1), 0, 16 * (i + 2) - 1, 15], fill=tuple(c))
        sw_.save(os.path.join(cdir, "palette.png"))
        nb = 1 if p["space"] in ("nes", "gb", "sms") else (3 if p["space"] == "rgb888" else 2)
        with open(os.path.join(cdir, "palette.bin"), "wb") as f:
            f.write(b"".join(int(v).to_bytes(nb, "little") for v in ([0] + nat)))
        qframes = [(mv, [quantize_frame(im, disp, dither) for im in ims]) for mv, ims in small]
    else:
        disp, nat = [], []
        if p["space"] == "rgba4444":
            def to4444(im):
                a = np.asarray(im).astype(np.int32)
                a = ((a * 15 + 127) // 255) * 17
                return Image.fromarray(a.astype(np.uint8), "RGBA")
            small = [(mv, [to4444(im) for im in ims]) for mv, ims in small]
        qframes = None
    # per-frame files + sheet (rows = moves)
    for mi, (mv, ims) in enumerate(small):
        for i, im in enumerate(ims):
            fn = os.path.join(cdir, "frames", "%s_%02d.png" % (mv, i))
            if indexed:
                indexed_png(qframes[mi][1][i], disp, fn)
            else:
                im.save(fn)
    maxn = max(len(ims) for _, ims in small)
    if indexed:
        sheet = np.zeros((FH * len(small), FW * maxn), np.uint8)
        for r, (mv, ids) in enumerate(qframes):
            for i, ix in enumerate(ids):
                sheet[r * FH:(r + 1) * FH, i * FW:(i + 1) * FW] = ix
        indexed_png(sheet, disp, os.path.join(cdir, "sheet.png"))
    else:
        sh_ = Image.new("RGBA", (FW * maxn, FH * len(small)), (0, 0, 0, 0))
        for r, (mv, ims) in enumerate(small):
            for i, im in enumerate(ims):
                sh_.paste(im, (i * FW, r * FH))
        sh_.save(os.path.join(cdir, "sheet.png"))
    anims = []; first = 0
    for mv, ims in small:
        m = moves.get(mv)
        anims.append((mv, first, len(ims), int(m.fps if m else 12), 1 if (m and m.loop) else 0)); first += len(ims)
    st["anims"] = [dict(name=a[0], first=a[1], count=a[2], fps=a[3], loop=a[4]) for a in anims]
    H = ["/* %s - Sprite Forge Studio console export for %s (%s).\n   %s\n   APPROX: %s */" % (
        sym + ".h", p["label"], key, p["notes"], p["approx"] or "-"), HDR_TYPES,
        "#define %s_FRAME_W %d\n#define %s_FRAME_H %d\n#define %s_PIVOT_X %d\n#define %s_GROUND_Y %d" % (sym.upper(), FW, sym.upper(), FH, sym.upper(), px, sym.upper(), gy)]
    if indexed:
        H.append("/* palette: entry 0 = transparent; native %s values */" % p["space"])
        ct = "uint8_t" if nb == 1 else ("uint16_t" if nb == 2 else "uint32_t")
        H.append(_carr(sym + "_palette", [0] + nat, ct, 16, "0x%02X" if nb == 1 else ("0x%04X" if nb == 2 else "0x%06X")))
    # --- 3a. tile consoles: dedupe tiles (+h-flip), banks, tilemaps
    if p["tiles"]:
        tw, th = p["tile"]
        banks = [{}]; bank_tiles = [[]]; maps = []; frames_meta = []; worst_line = 0
        for mv, ids in qframes:
            for fi, ix in enumerate(ids):
                gw, gh = FW // tw, FH // th
                cells = []
                for ty in range(gh):
                    for tx in range(gw):
                        t = ix[ty * th:(ty + 1) * th, tx * tw:(tx + 1) * tw]
                        cells.append(None if not t.any() else t)
                need = []
                for t in cells:
                    if t is None:
                        continue
                    k1, k2 = t.tobytes(), t[:, ::-1].tobytes()
                    if k1 not in banks[-1] and k2 not in banks[-1] and k1 not in need:
                        need.append(k1)
                if len(banks[-1]) + len(need) > p["bank_tiles"]:
                    banks.append({}); bank_tiles.append([])
                bank, btl = banks[-1], bank_tiles[-1]
                base = len(maps)
                for t in cells:
                    if t is None:
                        maps.append(0xFFFF); continue
                    k1, k2 = t.tobytes(), t[:, ::-1].tobytes()
                    if k1 in bank:
                        maps.append(bank[k1])
                    elif k2 in bank:
                        maps.append(bank[k2] | 0x4000)
                    else:
                        bank[k1] = len(btl); btl.append(t); maps.append(bank[k1])
                for ty in range(gh):
                    worst_line = max(worst_line, sum(1 for tx in range(gw) if cells[ty * gw + tx] is not None))
                frames_meta.append((len(banks) - 1, gw, gh, px, gy, base, rise_of(mv, fi)))
        st["banks"] = [len(b) for b in bank_tiles]; st["unique_tiles"] = sum(st["banks"])
        st["max_tiles_per_row"] = worst_line
        if len(bank_tiles) > 1:
            W("%d tiles do not fit one %d-tile bank -> %d banks (swap/stream banks per move: CHR bank switching / VRAM DMA)"
              % (st["unique_tiles"], p["bank_tiles"], len(bank_tiles)))
        if p["line_sprites"] and worst_line > p["line_sprites"]:
            W("a frame row needs %d 8x8 sprites side by side (limit %d per scanline incl. everything else) - expect flicker"
              % (worst_line, p["line_sprites"]))
        # tile sheets (indexed png, 16 tiles wide) + binary
        for bi, btl in enumerate(bank_tiles):
            cols = 16; rows_ = max(1, int(math.ceil(len(btl) / cols)))
            ts = np.zeros((rows_ * th, cols * tw), np.uint8)
            for i, t in enumerate(btl):
                ts[(i // cols) * th:(i // cols + 1) * th, (i % cols) * tw:(i % cols + 1) * tw] = t
            indexed_png(ts, disp, os.path.join(cdir, "tiles_bank%d.png" % bi))
            data = b"".join(encode_tile(t, p["fmt"]) for t in btl)
            with open(os.path.join(cdir, "tiles_bank%d.%s" % (bi, {"nes2": "chr", "gb2": "2bpp"}.get(p["fmt"], "4bpp"))), "wb") as f:
                f.write(data)
            H.append("/* bank %d: %d tiles, %s format */" % (bi, len(btl), p["fmt"]))
            H.append(_carr("%s_bank%d_tiles" % (sym, bi), list(data)))
        H.append("static const SFTBank %s_banks[%d] = { %s };" % (sym, len(bank_tiles), ", ".join(
            "{ %s_bank%d_tiles, %d }" % (sym, i, len(b)) for i, b in enumerate(bank_tiles))))
        H.append(_carr(sym + "_maps", maps, "uint16_t", 16, "0x%04X"))
        H.append("static const SFTFrame %s_frames[%d] = {\n%s\n};" % (sym, len(frames_meta), "\n".join(
            "    { %d, %d, %d, 0, %d, %d, %d, %d }," % f for f in frames_meta)))
        st["tiles"] = {"format": p["fmt"], "tile_w": tw, "tile_h": th, "map_entries": len(maps)}
    # --- 3b. texture consoles: pack frames onto pages
    if p["tex"]:
        T = p["max_tex"]
        per_row = max(1, T // FW); per_col = max(1, T // FH); per_page = per_row * per_col
        flat = [(mv, i, im) for (mv, ims) in small for i, im in enumerate(ims)]
        flat_ix = [ix for (_, ids) in qframes for ix in ids] if indexed else None
        npages = int(math.ceil(len(flat) / per_page))
        rects = []
        for pg in range(npages):
            chunk = flat[pg * per_page:(pg + 1) * per_page]
            n = len(chunk); cols_ = min(per_row, n); rows_ = int(math.ceil(n / cols_))
            PW, PH = cols_ * FW, rows_ * FH
            if p["pow2"]:
                PW, PH = _pow2(PW), _pow2(PH)
            if indexed:
                pg_arr = np.zeros((PH, PW), np.uint8)
            else:
                pg_im = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
            for j, (mv, i, im) in enumerate(chunk):
                x, y = (j % cols_) * FW, (j // cols_) * FH
                if indexed:
                    pg_arr[y:y + FH, x:x + FW] = flat_ix[pg * per_page + j]
                else:
                    pg_im.paste(im, (x, y))
                rects.append((mv, i, x, y, FW, FH, pg))
            fn = os.path.join(cdir, "page%d.png" % pg)
            if indexed:
                indexed_png(pg_arr, disp, fn)
            else:
                pg_im.save(fn)
        st["pages"] = npages; st["page_files"] = ["page%d.png" % i for i in range(npages)]
        st["rects"] = [dict(move=r[0], index=r[1], x=r[2], y=r[3], w=r[4], h=r[5], page=r[6], rise=rise_of(r[0], r[1])) for r in rects]
        H.append("static const SFTRect %s_rects[%d] = {\n%s\n};" % (sym, len(rects), "\n".join(
            "    { %d, %d, %d, %d, %d, 0, %d, %d, %d },  /* %s_%02d */" % (r[2], r[3], r[4], r[5], r[6], px, gy, rise_of(r[0], r[1]), r[0], r[1]) for r in rects)))
    H.append("static const SFTAnim %s_anims[%d] = {\n%s\n};" % (sym, len(anims), "\n".join(
        '    { "%s", %d, %d, %d, %d },' % a for a in anims)))
    H.append("#define %s_ANIM_COUNT %d" % (sym.upper(), len(anims)))
    with open(os.path.join(cdir, sym + ".h"), "w", newline="\n") as f:
        f.write("\n\n".join(H) + "\n")
    st["header"] = sym + ".h"
    # --- 4. low-poly model
    if p["tris"] is not None and model is not None or (key == "pc_hd" and model is not None):
        st["model"] = model(p["tris"], cdir)
        if st["model"] and p["tris"] and st["model"]["tris"] > p["tris"]:
            W("model has %d tris (lowest detail) > budget %d" % (st["model"]["tris"], p["tris"]))
        if st["model"] and p["tris"] and st["model"]["tris"] < 0.5 * p["tris"]:
            st["model"]["note"] = "under budget: the source model has no more real detail to add"
    _write_readme(cdir, sym, p, st)
    with open(os.path.join(cdir, "console.json"), "w") as f:
        json.dump(st, f, indent=1)
    log("  console/ (%s): %dx%d frames, %s%s" % (p["label"], FW, FH,
        ("%d colours" % len(disp)) if indexed else "full colour",
        (", %d tiles in %d bank(s)" % (st["unique_tiles"], len(st["banks"]))) if p["tiles"] else (", %d page(s)" % st.get("pages", 0))))
    return st


def _export_2600(cdir, sym, small, moves, st, gy, px, log):
    """Atari 2600: 8-px wide 1bpp rows + one NTSC colour per row."""
    gfx, cols, meta = [], [], []
    FW, FH = st["frame_w"], st["frame_h"]
    allrgb = []
    for mv, ims in small:
        for i, im in enumerate(ims):
            a = np.asarray(im); m = a[..., 3] >= 128
            rows_b, rows_c = [], []
            prev = 0
            for y in range(FH):
                bits = 0
                for x in range(8):
                    bits = (bits << 1) | (1 if (x < FW and m[y, x]) else 0)
                if m[y].any():
                    c = tuple(int(v) for v in a[y][m[y]][:, :3].mean(0))
                    disp, nat = snap_colour(c, "a2600")
                    prev = nat
                else:
                    nat = prev
                rows_b.append(bits); rows_c.append(nat)
            meta.append((mv, i, len(gfx)))
            gfx += rows_b; cols += rows_c
            # preview frame
            pv = Image.new("RGBA", (8, FH), (0, 0, 0, 0))
            for y in range(FH):
                for x in range(8):
                    if (rows_b[y] >> (7 - x)) & 1:
                        pv.putpixel((x, y), A2600_RGB[rows_c[y]] + (255,))
            pv.save(os.path.join(cdir, "frames", "%s_%02d.png" % (mv, i)))
            allrgb.append(pv)
    maxn = max(len(ims) for _, ims in small)
    sh = Image.new("RGBA", (8 * maxn, FH * len(small)), (0, 0, 0, 0))
    k = 0
    for r, (mv, ims) in enumerate(small):
        for i in range(len(ims)):
            sh.paste(allrgb[k], (i * 8, r * FH)); k += 1
    sh.save(os.path.join(cdir, "sheet.png"))
    anims, first = [], 0
    for mv, ims in small:
        m = moves.get(mv); anims.append((mv, first, len(ims), int(m.fps if m else 12), 1 if (m and m.loop) else 0)); first += len(ims)
    H = ["/* %s.h - Atari 2600 export. Each frame = %d rows (top to bottom) of GRP0 bytes + a COLUP0 colour per row.\n"
         "   Most kernels read rows bottom-up: index with (FRAME_H-1-line). APPROX: NTSC palette RGB in previews. */" % (sym, FH),
         "#include <stdint.h>\n#define %s_FRAME_H %d\n#define %s_GROUND_Y %d" % (sym.upper(), FH, sym.upper(), gy),
         _carr(sym + "_gfx", gfx), _carr(sym + "_colours", cols),
         "static const uint16_t %s_frame_offset[%d] = { %s };" % (sym, len(meta), ", ".join(str(m[2]) for m in meta)),
         "typedef struct { const char *name; uint16_t first, count; uint8_t fps, loop; } SFTAnim2600;",
         "static const SFTAnim2600 %s_anims[%d] = {\n%s\n};" % (sym, len(anims), "\n".join('    { "%s", %d, %d, %d, %d },' % a for a in anims))]
    with open(os.path.join(cdir, sym + ".h"), "w", newline="\n") as f:
        f.write("\n\n".join(H) + "\n")
    st.update(header=sym + ".h", anims=[dict(name=a[0], first=a[1], count=a[2], fps=a[3], loop=a[4]) for a in anims],
              colours_used=len(set(cols)))
    p = PRESETS["atari2600"]
    _write_readme(cdir, sym, p, st)
    with open(os.path.join(cdir, "console.json"), "w") as f:
        json.dump(st, f, indent=1)
    log("  console/ (Atari 2600): 8x%d frames, %d row colours" % (FH, len(set(cols))))
    return st


def _write_readme(cdir, sym, p, st):
    L = ["Sprite Forge Studio - console export: %s" % p["label"], "",
         p["notes"], "APPROXIMATIONS: " + (p["approx"] or "-"), "",
         "frame size : %dx%d px   pivot_x %d   ground_y %d   (sprites face RIGHT; mirror to face left)" % (
             st["frame_w"], st["frame_h"], st["pivot_x"], st["ground_y"]),
         "files      :",
         "  frames/<move>_<NN>.png   every frame at console size%s" % (" (indexed PNG, index 0 = transparent)" if p["colours"] else ""),
         "  sheet.png                all frames, one row per move (like atlas.png)",
         "  %s.h      C arrays: palette, tiles/rects, frames, anims" % sym]
    if p["colours"] and p["key"] != "atari2600":
        L += ["  palette.pal / .png / .bin  JASC palette (Aseprite/GIMP), swatch, native console values (entry 0 = transparent)"]
    if p["tiles"]:
        L += ["  tiles_bankN.png / .chr|.2bpp|.4bpp   unique 8x8 tiles (indexed PNG + raw native tile data)",
              "  banks: %s tiles each (limit %d per bank)" % (st.get("banks"), p["bank_tiles"])]
    if p["tex"]:
        L += ["  pageN.png                texture pages (<= %d px%s)" % (p["max_tex"], ", power of two" if p["pow2"] else "")]
    if st.get("model"):
        m = st["model"]; L += ["  %s  low-poly model: %d tris (budget %s), texture budget %d px (model uses flat material colours: no texture needed)"
                               % (" + ".join(m["files"]), m["tris"], p["tris"], p["model_tex"])]
    for w in st.get("warnings", []):
        L.append("WARNING: " + w)
    with open(os.path.join(cdir, "README.txt"), "w") as f:
        f.write("\n".join(L) + "\n")
