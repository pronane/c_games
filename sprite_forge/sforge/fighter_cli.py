"""v7.1  forge.py export-ef : Sprite Forge build -> Egyptian Fighter / Padel Wars fighter folder.

  forge.py export-ef out/<name> <game>/assets/char_<x> [--like <game>/assets/char_dragon/sprites.cfg]
                     [--scale 0.5] [--projectile card] [--prefix g_] [--portrait-w 268]

--like REF  copies the reference fighter's move list, frame counts, frame times, file naming (g_<move>.png)
            and its 'projectile' line (unless --projectile is given); a move whose frame count differs is
            resampled (frames repeated / dropped evenly) and reported.
--scale S   resizes every cell (cell, baseline and stand_height scale too) - e.g. 0.5 for a low-res set.
Writes <prefix><move>.png (one uniform horizontal strip per move), sprites.cfg, portrait.png,
contact_sheet.png and export_report.txt (feet-on-baseline + common-height checks)."""
from __future__ import annotations
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

EF_NAMES = {"special1": "pyramid_blast", "special_1": "pyramid_blast", "special2": "bum_fireball",
            "special_2": "bum_fireball", "jumpattack": "jump_attack"}
EF_STATES = ["idle", "walk", "crouch", "jump", "punch", "kick", "pyramid_blast", "bum_fireball",
             "block", "hit", "throw", "jump_attack", "taunt", "victory"]


def read_cfg(path):
    d = {"anims": [], "projectile": None}
    for line in open(path):
        p = line.split("#")[0].split()
        if not p:
            continue
        if p[0] == "cell":
            d["cell"] = (int(p[1]), int(p[2]))
        elif p[0] in ("baseline", "stand_height"):
            d[p[0]] = int(p[1])
        elif p[0] == "anim":
            d["anims"].append((p[1], p[2], int(p[3]), p[4]))
        elif p[0] == "projectile":
            d["projectile"] = p[1]
    return d


def _font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def _resample(frames, n):
    if len(frames) == n:
        return frames
    idx = np.round(np.linspace(0, len(frames) - 1, n)).astype(int)
    return [frames[i] for i in idx]


def export(src, dst, like=None, scale=1.0, projectile=None, prefix=None, portrait_w=268, title="", log=print):
    js = json.load(open(os.path.join(src, "atlas.json")))
    meta, an = js["meta"], js["animations"]
    fw, fh, gy = meta["frame_w"], meta["frame_h"], meta["ground_y"]
    ref = read_cfg(like) if like else None
    if prefix is None:
        prefix = "g_" if ref and all(a[1].startswith("g_") for a in ref["anims"]) else ""
    W, H = int(round(fw * scale)), int(round(fh * scale))
    base = int(round(gy * scale))
    os.makedirs(dst, exist_ok=True)

    def load(mv, i):
        im = Image.open(os.path.join(src, "moves", "%s_%02d.png" % (mv, i))).convert("RGBA")
        if scale != 1.0:
            # premultiplied resize so transparent edges keep no dark fringe
            a = np.asarray(im).astype(np.float32); a[..., :3] *= a[..., 3:4] / 255.0
            r = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA").resize((W, H), Image.LANCZOS)
            b = np.asarray(r).astype(np.float32); al = np.maximum(b[..., 3:4], 1e-3)
            b[..., :3] = np.where(b[..., 3:4] > 0, b[..., :3] * 255.0 / al, 0)
            im = Image.fromarray(b.clip(0, 255).astype(np.uint8), "RGBA")
        return im

    src_moves = {EF_NAMES.get(mv, mv): mv for mv in an}
    if ref:
        plan = [(st, ref_file.replace(ref_file[:len(ref_file) - len(st) - 4], prefix) if ref_file.endswith(st + ".png") else prefix + st + ".png",
                 n, ft) for st, ref_file, n, ft in ref["anims"]]
    else:
        plan = [(st, prefix + st + ".png", an[src_moves[st]]["count"], "%.3f" % (1.0 / max(1, an[src_moves[st]]["fps"])))
                if st in src_moves else (st, prefix + st + ".png", 0, "0")
                for st in EF_STATES]
    idle0 = load(src_moves.get("idle", next(iter(an))), 0)
    a0 = np.asarray(idle0.getchannel("A"))
    ys = np.nonzero((a0 > 40).any(1))[0]
    stand_h = int(base - ys.min()) if len(ys) else int(H * 0.7)
    lines = ["# exported by Sprite Forge Studio %s  forge.py export-ef  (%s)" % (__import__("sforge").__version__, meta.get("name", "")),
             "# cells are uniform; every frame's feet are on the baseline; sprites face RIGHT (the game flips)",
             "cell %d %d" % (W, H), "baseline %d" % base, "stand_height %d" % stand_h]
    rep = ["export-ef %s -> %s  scale %.3f  cell %dx%d baseline %d stand_height %d" % (src, dst, scale, W, H, base, stand_h)]
    if ref:
        rep.append("like %s: move list, frame counts and frame times copied" % like)
    sheet_rows, missing = [], []
    for st, fn, n, ft in plan:
        mv = src_moves.get(st)
        if mv is None:
            missing.append(st); rep.append("  MISSING %s (game falls back)" % st); continue
        frames = [load(mv, i) for i in range(an[mv]["count"])]
        if len(frames) != n:
            rep.append("  %s: %d frames resampled to %d (reference count)" % (st, len(frames), n))
            frames = _resample(frames, n)
        strip = Image.new("RGBA", (W * n, H), (0, 0, 0, 0))
        lows, tops, edge = [], [], 0
        for i, im in enumerate(frames):
            strip.paste(im, (i * W, 0))
            al = np.asarray(im.getchannel("A")) > 40
            r_ = np.nonzero(al.any(1))[0]; c_ = np.nonzero(al.any(0))[0]
            if len(r_):
                lows.append(int(r_.max())); tops.append(int(r_.min()))
                if c_.min() == 0 or c_.max() == W - 1 or r_.min() == 0:
                    edge += 1
        strip.save(os.path.join(dst, fn), optimize=True)
        lines.append("anim %s %s %d %s" % (st, fn, n, ft))
        rep.append("  %-14s %-22s %2d frames  %s s  lowest px rows %s  (baseline-1 = %d)%s" % (
            st, fn, n, ft, sorted(set(lows)), base - 1, "  EDGE-TOUCH x%d" % edge if edge else ""))
        sheet_rows.append((st, frames))
    proj = projectile or (ref["projectile"] if ref else None)
    if proj:
        lines.append("projectile " + proj)
    open(os.path.join(dst, "sprites.cfg"), "w").write("\n".join(lines) + "\n")
    # portrait: head and shoulders of idle frame 0
    bb = idle0.getchannel("A").getbbox()
    if bb:
        top = ys.min(); h = int(stand_h * 0.42); w = int(h * 0.82)
        row = a0[min(H - 1, top + int(h * 0.3))] > 40
        xs = np.nonzero(row)[0]; cx = int(xs.mean()) if len(xs) else (bb[0] + bb[2]) // 2
        por = idle0.crop((cx - w // 2, max(0, top - int(h * 0.06)), cx + w // 2, max(0, top - int(h * 0.06)) + h))
        por.resize((portrait_w, int(portrait_w * por.height / por.width)), Image.LANCZOS).save(os.path.join(dst, "portrait.png"))
    # contact sheet: every frame of every move, cell border + baseline drawn
    th = 200; tw = int(th * W / H); lab = 22; cols = max(len(f) for _, f in sheet_rows)
    cs = Image.new("RGB", (110 + cols * (tw + 4), 40 + len(sheet_rows) * (th + lab)), (24, 26, 32))
    d = ImageDraw.Draw(cs); f = _font(14)
    d.text((8, 10), (title or meta.get("name", "")) + "  -  %d moves, cell %dx%d, baseline %d (red), stand_height %d" % (
        len(sheet_rows), W, H, base, stand_h), fill=(255, 255, 255), font=_font(18))
    for r, (st, frames) in enumerate(sheet_rows):
        y = 40 + r * (th + lab)
        d.text((8, y + th // 2), st, fill=(230, 230, 230), font=f)
        for i, im in enumerate(frames):
            x = 110 + i * (tw + 4)
            bg = Image.new("RGBA", im.size, (200, 200, 205, 255)); bg.alpha_composite(im)
            t = bg.convert("RGB").resize((tw, th), Image.LANCZOS)
            cs.paste(t, (x, y))
            by = y + int(base * th / H)
            d.line([(x, by), (x + tw - 1, by)], fill=(230, 30, 30), width=1)
            d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(90, 90, 100))
            d.text((x + 3, y + th + 2), "%d" % i, fill=(180, 180, 180), font=f)
    cs.save(os.path.join(dst, "contact_sheet.png"))
    rep.append("projectile: %s" % (proj or "none"))
    rep.append("missing: %s" % (", ".join(missing) or "none"))
    open(os.path.join(dst, "export_report.txt"), "w").write("\n".join(rep) + "\n")
    for l in rep:
        log(l)
    return missing


def main(argv):
    ap = argparse.ArgumentParser(prog="forge.py export-ef", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd"); ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--like", help="reference fighter sprites.cfg: copy move list / frame counts / frame times / naming")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--projectile", choices=["ball", "book", "card", "bubble", "fire", "fire_blue"])
    ap.add_argument("--prefix", default=None, help="strip file prefix (default: like the reference, else none)")
    ap.add_argument("--portrait-w", dest="portrait_w", type=int, default=268)
    ap.add_argument("--title", default="")
    a = ap.parse_args(argv)
    missing = export(a.src, a.dst, a.like, a.scale, a.projectile, a.prefix, a.portrait_w, a.title)
    return 1 if missing else 0
