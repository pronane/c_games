"""Sprite Forge Studio v9 - pack several characters into shared texture atlas pages.

forge.py atlas out/hero out/enemy out/npc --out out/pack [--max 4096] [--padding 2] [--no-trim] [--pot] [--scale 0.5]

* reads each build folder (atlas.json + moves/*.png) or a game folder (sprites.cfg strips)
* trims transparent borders, removes exact duplicate frames (shared by every character), MaxRects packing
  (best short side fit) into as few pages as needed (pack_0.png, pack_1.png ...)
* pack.json: TexturePacker-style 'frames' (frame / spriteSourceSize / sourceSize / pivot) keyed
  "<character>/<frame>" + 'animations' keyed "<character>/<move>" + per character meta (ground_y, pivot, fps)
  -> the Unity / Godot importers in plugins/ read it, so do Phaser / Pixi / any TexturePacker-JSON loader."""
from __future__ import annotations
import hashlib
import json
import os

import numpy as np
from PIL import Image


class MaxRects:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.free = [(0, 0, w, h)]

    def insert(self, rw, rh):
        best, bs, bl = None, None, None
        for fx, fy, fw, fh in self.free:
            if rw <= fw and rh <= fh:
                s = min(fw - rw, fh - rh); l = max(fw - rw, fh - rh)
                if best is None or (s, l) < (bs, bl):
                    best, bs, bl = (fx, fy), s, l
        if best is None:
            return None
        x, y = best
        self._split(x, y, rw, rh)
        return x, y

    def _split(self, x, y, w, h):
        nf = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                nf.append((fx, fy, fw, fh)); continue
            if x > fx:
                nf.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                nf.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                nf.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                nf.append((fx, y + h, fw, fy + fh - y - h))
        # prune contained rectangles
        nf = list(set(nf))
        keep = []
        for i, a in enumerate(nf):
            if not any(j != i and a[0] >= b[0] and a[1] >= b[1] and a[0] + a[2] <= b[0] + b[2] and a[1] + a[3] <= b[1] + b[3]
                       and (a != b or j < i) for j, b in enumerate(nf)):
                keep.append(a)
        self.free = keep


def load_character(folder):
    """-> (name, meta, [(move, fps, loop, [(frame_name, PIL RGBA)])])"""
    name = os.path.basename(os.path.normpath(folder))
    aj = os.path.join(folder, "atlas.json")
    moves = []
    if os.path.isfile(aj) and os.path.isdir(os.path.join(folder, "moves")):
        js = json.load(open(aj))
        m = js["meta"]
        name = m.get("name", name)
        meta = {"frame_w": m["frame_w"], "frame_h": m["frame_h"], "ground_y": m["ground_y"], "pivot": m["pivot"], "facing": m.get("facing", "right")}
        for mv, a in js["animations"].items():
            moves.append((mv, a.get("fps", 12), a.get("loop", False),
                          [(f, Image.open(os.path.join(folder, "moves", f + ".png")).convert("RGBA")) for f in a["frames"]]))
        return name, meta, moves
    cfgp = os.path.join(folder, "sprites.cfg")
    if not os.path.isfile(cfgp):
        raise ValueError("%s: not a Sprite Forge build (atlas.json + moves/) or a game folder (sprites.cfg)" % folder)
    cw = ch = 0; ground = None
    for line in open(cfgp):
        p = line.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "cell":
            cw, ch = int(p[1]), int(p[2])
        elif p[0] == "baseline":
            ground = int(p[1])
        elif p[0] == "anim" and len(p) >= 4 and cw:
            sh = Image.open(os.path.join(folder, p[2])).convert("RGBA")
            ft = float(p[4]) if len(p) > 4 else 0.08
            moves.append((p[1], round(1 / ft) if ft > 0 else 12, p[1] in ("idle", "walk", "taunt", "victory"),
                          [("%s_%02d" % (p[1], i), sh.crop((i * cw, 0, (i + 1) * cw, ch))) for i in range(sh.width // cw)]))
    gy = ground if ground is not None else ch - 12
    return name, {"frame_w": cw, "frame_h": ch, "ground_y": gy, "pivot": {"x": cw // 2, "y": gy}, "facing": "right"}, moves


def pack(folders, out, max_size=4096, padding=2, trim=True, pot=False, scale=1.0, log=print):
    os.makedirs(out, exist_ok=True)
    chars = [load_character(f) for f in folders]
    names = [c[0] for c in chars]
    for i, n in enumerate(names):                       # unique character keys
        if names.count(n) > 1:
            names[i] = "%s_%d" % (n, i)
    items, uniq = [], {}
    total_frames = 0
    for cname, (_, meta, moves) in zip(names, chars):
        for mv, fps, loop, frs in moves:
            for fn, im in frs:
                total_frames += 1
                if scale != 1.0:
                    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
                bb = im.getchannel("A").getbbox() if trim else (0, 0, im.width, im.height)
                if bb is None:
                    bb = (0, 0, 1, 1)
                crop = im.crop(bb)
                h = hashlib.md5(crop.tobytes() + bytes(str(crop.size), "ascii")).hexdigest()
                if h not in uniq:
                    uniq[h] = crop
                items.append((cname, mv, fn, h, bb, im.size))
    order = sorted(uniq, key=lambda h: (-uniq[h].height, -uniq[h].width))
    for h in order:
        if uniq[h].width + padding > max_size or uniq[h].height + padding > max_size:
            raise ValueError("frame %dx%d bigger than --max %d" % (uniq[h].width, uniq[h].height, max_size))
    need = sum((uniq[h].width + padding) * (uniq[h].height + padding) for h in order)
    pages, place = [], {}
    side = max(64, int(need ** 0.5))                   # smallest square page that holds everything (grow 8% a try)
    while side < max_size:
        pg, pl = MaxRects(side, side), {}
        for h in order:
            p = pg.insert(uniq[h].width + padding, uniq[h].height + padding)
            if p is None:
                break
            pl[h] = (0, p[0], p[1])
        else:
            pages, place = [pg], pl
            break
        side = int(side * 1.08) + 1
    if not pages:                                       # does not fit one max-size page: several pages
        for h in order:
            w, hh = uniq[h].width + padding, uniq[h].height + padding
            for pi, pg in enumerate(pages):
                p = pg.insert(w, hh)
                if p:
                    place[h] = (pi, p[0], p[1]); break
            else:
                pg = MaxRects(max_size, max_size); pages.append(pg)
                p = pg.insert(w, hh); place[h] = (len(pages) - 1, p[0], p[1])
    # shrink each page to its used area
    files, sizes = [], []
    for pi in range(len(pages)):
        used = [(x + uniq[h].width, y + uniq[h].height) for h, (p, x, y) in place.items() if p == pi]
        W = max(u[0] for u in used); H = max(u[1] for u in used)
        if pot:
            W = 1 << (W - 1).bit_length(); H = 1 << (H - 1).bit_length()
        canvas = Image.new("RGBA", (W, H))
        for h, (p, x, y) in place.items():
            if p == pi:
                canvas.paste(uniq[h], (x, y))
        fn = "pack_%d.png" % pi
        canvas.save(os.path.join(out, fn), optimize=True)
        files.append(fn); sizes.append({"w": W, "h": H})
    frames, anims, cmeta = {}, {}, {}
    for cname, (_, meta, moves) in zip(names, chars):
        s = scale
        cmeta[cname] = {"frame_w": round(meta["frame_w"] * s), "frame_h": round(meta["frame_h"] * s),
                        "ground_y": round(meta["ground_y"] * s), "pivot": {"x": round(meta["pivot"]["x"] * s), "y": round(meta["pivot"]["y"] * s)},
                        "facing": meta.get("facing", "right")}
        for mv, fps, loop, frs in moves:
            anims["%s/%s" % (cname, mv)] = {"character": cname, "move": mv, "fps": fps, "loop": bool(loop),
                                            "frames": ["%s/%s" % (cname, fn) for fn, _ in frs]}
    for cname, mv, fn, h, bb, src in items:
        p, x, y = place[h]
        im = uniq[h]
        cm = cmeta[cname]
        frames["%s/%s" % (cname, fn)] = {
            "frame": {"x": x, "y": y, "w": im.width, "h": im.height}, "page": p, "image": files[p], "rotated": False,
            "trimmed": bool(trim), "spriteSourceSize": {"x": bb[0], "y": bb[1], "w": im.width, "h": im.height},
            "sourceSize": {"w": src[0], "h": src[1]},
            "pivot": {"x": round(cm["pivot"]["x"] / max(1, src[0]), 4), "y": round(cm["pivot"]["y"] / max(1, src[1]), 4)}}
    used_px = sum(i.width * i.height for i in uniq.values())
    area = sum(s["w"] * s["h"] for s in sizes)
    js = {"meta": {"app": "Sprite Forge Studio", "version": "9.0.0", "kind": "multi-character pack", "images": files, "size": sizes,
                   "format": "RGBA8888", "padding": padding, "trimmed": trim, "scale": scale, "characters": cmeta,
                   "coords": "pixels, origin top-left, y down", "fill": round(used_px / max(1, area), 3),
                   "frames_total": total_frames, "frames_unique": len(uniq)},
          "frames": frames, "animations": anims}
    with open(os.path.join(out, "pack.json"), "w") as f:
        json.dump(js, f, indent=1)
    raw = sum(c[1]["frame_w"] * c[1]["frame_h"] * sum(len(m[3]) for m in c[2]) for c in chars) * scale * scale
    log("atlas pack: %d characters, %d frames (%d unique) -> %d page(s) %s, fill %.0f%%, %.0f%% of the untrimmed pixels"
        % (len(chars), total_frames, len(uniq), len(files), ", ".join("%dx%d" % (s["w"], s["h"]) for s in sizes),
           100 * js["meta"]["fill"], 100 * area / max(1, raw)))
    return js
