"""Sprite Forge Studio v9 - hitbox / hurtbox / frame-data export for fighting games.

Measured from the finished sprite frames themselves (works for every mode, also photo builds):
  hurtboxes  3 boxes per frame (head / body / legs) = the figure's alpha inside three height bands
  hitboxes   attack moves only: frames where the figure reaches furthest forward (sprites face right) beyond its
             own body are ACTIVE; the hitbox covers the part sticking out past the body (fist / foot / weapon)
  startup / active / recovery = frames before / during / after the active window (+ times from the move fps)
Outputs framedata.json (all boxes, cell pixel coords, origin top-left) + framedata.cfg (one line per box, easy
to parse in C) + framedata_preview.png (boxes drawn on the attack frames).  ESTIMATED from the silhouette -
tune damage / boxes in the json if your game needs exact values."""
from __future__ import annotations
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw

ATTACK_RE = re.compile(r"punch|kick|attack|special|blast|fireball|throw|uppercut|slash|strike|jab|hook|sweep|combo|smash|"
                       r"slam|headbutt|elbow|knee|lariat|swing|stab|shoot|shot|tackle|header|volley|projectile|lunge|bite|claw|cast", re.I)
HEAVY_RE = re.compile(r"kick|special|blast|fireball|uppercut|smash|slam|sweep|jump_?attack", re.I)


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def _alpha(im):
    return np.asarray(im.getchannel("A")) > 60


def hurtboxes(A):
    rows = np.nonzero(A.any(1))[0]
    if not len(rows):
        return []
    top, bot = rows[0], rows[-1]
    h = bot - top + 1
    out = []
    for f0, f1, tag in ((0.0, 0.17, "head"), (0.17, 0.55, "body"), (0.55, 1.0, "legs")):
        y0, y1 = int(top + f0 * h), int(top + f1 * h) + 1
        band = np.zeros_like(A); band[y0:y1] = A[y0:y1]
        # ignore thin extremities (an outstretched arm is a hitbox, not extra hurtbox): columns with few pixels
        cols = band.sum(0)
        keep = cols >= max(2, 0.18 * (y1 - y0))
        band &= keep[None, :]
        b = _bbox(band)
        if b:
            out.append({"part": tag, "box": b})
    return out


def body_right(A):
    """right edge of the torso core (median of the body band's dense columns)"""
    rows = np.nonzero(A.any(1))[0]
    if not len(rows):
        return None
    top, bot = rows[0], rows[-1]; h = bot - top + 1
    y0, y1 = int(top + 0.2 * h), int(top + 0.5 * h)
    band = A[y0:y1]
    cols = band.sum(0)
    dense = np.nonzero(cols >= 0.6 * (y1 - y0))[0]
    return int(dense.max()) if len(dense) else int(np.nonzero(band.any(0))[0].max())


def analyse_move(frames, name, fps, idle_ref=None):
    As = [_alpha(f) for f in frames]
    out = {"frames": [], "attack": bool(ATTACK_RE.search(name)) and not name.startswith(("blend_", "crossfade_"))}
    reach = []
    for A in As:
        xs = np.nonzero(A.any(0))[0]
        reach.append(int(xs.max()) if len(xs) else 0)
    for i, A in enumerate(As):
        out["frames"].append({"hurt": hurtboxes(A), "hit": []})
    if out["attack"] and len(frames) >= 2:
        import cv2
        H = frames[0].height
        ref = idle_ref if idle_ref is not None else As[0]
        r = max(2, int(0.03 * H))
        D = cv2.dilate(ref.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
        rx = np.nonzero(ref.any(0))[0]
        cx = int((rx.min() + rx.max()) / 2) if len(rx) else frames[0].width // 2
        ref_right = int(rx.max()) if len(rx) else cx
        ext, parts = [], []
        for A in As:
            P = A & ~D
            P[:, :cx] = False
            n, lab, st, _ = cv2.connectedComponentsWithStats(P.astype(np.uint8), 8)
            if n > 1:
                k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
                if st[k, cv2.CC_STAT_AREA] >= max(6, (0.006 * H) ** 2):
                    x, y, w, h = [int(v) for v in st[k, :4]]
                    parts.append([x, y, w, h]); ext.append(x + w - 1 - ref_right); continue
            parts.append(None); ext.append(0)
        hi = max(ext)
        if hi >= 0.04 * H:
            active = [i for i, e in enumerate(ext) if e >= 0.6 * hi and parts[i] is not None]
            a0, a1 = min(active), max(active)
            active = [i for i in range(a0, a1 + 1) if parts[i] is not None]
            for i in active:
                b = parts[i]
                pad = max(2, int(0.01 * H))
                out["frames"][i]["hit"].append({"box": [b[0] - pad, b[1] - pad, b[2] + 2 * pad, b[3] + 2 * pad],
                                                "reach_px": int(ext[i])})
            n_ = len(frames)
            out.update(startup=a0, active=a1 - a0 + 1, recovery=n_ - 1 - a1,
                       startup_s=round(a0 / max(1, fps), 3), active_s=round((a1 - a0 + 1) / max(1, fps), 3),
                       recovery_s=round((n_ - 1 - a1) / max(1, fps), 3))
    if out["attack"]:
        heavy = bool(HEAVY_RE.search(name))
        out.setdefault("startup", 0); out.setdefault("active", 0); out.setdefault("recovery", len(frames))
        out.update(damage=12 if heavy else 7, hitstun=18 if heavy else 12, blockstun=8 if heavy else 5,
                   type="heavy" if heavy else "light")
    return out


def write_framedata(cfg, out, ctx, report):
    ordered = ctx["ordered"]
    spec_by = ctx["spec_by"]
    js = {"version": 1, "app": "Sprite Forge Studio", "name": cfg.name, "frame_w": cfg.frame_w, "frame_h": cfg.frame_h,
          "anchor_x": cfg.pivot_x, "ground_y": cfg.ground_y, "facing": "right",
          "coords": "pixels in the frame cell, origin top-left, y down; [x, y, w, h]",
          "method": "measured from the sprite silhouettes (ESTIMATED); damage / stun are defaults by move type",
          "moves": {}}
    L = ["# framedata.cfg - Sprite Forge Studio (%s)  boxes are x y w h in the %dx%d cell, sprites face right" % (cfg.name, cfg.frame_w, cfg.frame_h),
         "# move <name> <frames> <fps> <startup> <active> <recovery> <damage> <hitstun> <blockstun>",
         "# hurt <name> <frame> <part> x y w h      hit <name> <frame> x y w h",
         "cell %d %d" % (cfg.frame_w, cfg.frame_h), "anchor %d %d" % (cfg.pivot_x, cfg.ground_y)]
    prev = []
    idle = dict(ordered).get("idle") or dict(ordered).get("fight_idle")
    iref = _alpha(idle[0]) if idle else None
    for mv, fr in ordered:
        fps = spec_by[mv].fps if mv in spec_by else 12
        d = analyse_move(fr, mv, fps, iref)
        js["moves"][mv] = d
        if d["attack"]:
            L.append("move %s %d %g %d %d %d %d %d %d" % (mv, len(fr), fps, d["startup"], d["active"], d["recovery"],
                                                         d["damage"], d["hitstun"], d["blockstun"]))
            if d["active"]:
                prev.append((mv, fr, d))
        else:
            L.append("move %s %d %g 0 0 0 0 0 0" % (mv, len(fr), fps))
        for i, f in enumerate(d["frames"]):
            for h in f["hurt"]:
                L.append("hurt %s %d %s %d %d %d %d" % ((mv, i, h["part"]) + tuple(h["box"])))
            for h in f["hit"]:
                L.append("hit %s %d %d %d %d %d" % ((mv, i) + tuple(h["box"])))
    with open(os.path.join(out, "framedata.json"), "w") as f:
        json.dump(js, f, indent=1)
    with open(os.path.join(out, "framedata.cfg"), "w", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    if prev:
        preview(prev, cfg).save(os.path.join(out, "framedata_preview.png"))
    atk = [m for m, d in js["moves"].items() if d["attack"]]
    no_hit = [m for m in atk if not js["moves"][m]["active"]]
    if no_hit:
        report.warning("framedata: no clear active frames found for %s (no forward reach) - set them in framedata.json" % ", ".join(no_hit))
    return "framedata.json/.cfg (%d attack moves%s)" % (len(atk), ", preview" if prev else "")


def preview(items, cfg, th=180):
    from .build import checker, _font
    rows = []
    for mv, fr, d in items:
        k = th / float(cfg.frame_h)
        tw = int(cfg.frame_w * k)
        row = Image.new("RGB", (len(fr) * (tw + 4) + 130, th + 22), (30, 34, 42))
        dr = ImageDraw.Draw(row)
        dr.text((6, 4), mv, fill=(235, 235, 235), font=_font(13))
        dr.text((6, 22), "S%d A%d R%d" % (d["startup"], d["active"], d["recovery"]), fill=(200, 200, 120), font=_font(12))
        for i, im in enumerate(fr):
            bg = checker(tw, th, 8)
            sm = im.resize((tw, th), Image.LANCZOS)
            bg.paste(sm, (0, 0), sm)
            g = ImageDraw.Draw(bg)
            for h in d["frames"][i]["hurt"]:
                x, y, w, hh = [v * k for v in h["box"]]
                g.rectangle([x, y, x + w, y + hh], outline=(60, 200, 255), width=2)
            for h in d["frames"][i]["hit"]:
                x, y, w, hh = [v * k for v in h["box"]]
                g.rectangle([x, y, x + w, y + hh], outline=(255, 50, 50), width=3)
            row.paste(bg, (126 + i * (tw + 4), 0))
            dr.text((126 + i * (tw + 4) + 3, th + 4), str(i), fill=(220, 220, 220), font=_font(11))
        rows.append(row)
    W = max(r.width for r in rows)
    S = Image.new("RGB", (W, sum(r.height + 4 for r in rows) + 24), (24, 26, 32))
    ImageDraw.Draw(S).text((6, 4), "%s - frame data (blue hurtboxes, red hitboxes; ESTIMATED from the sprites)" % cfg.name,
                           fill=(235, 235, 235), font=_font(13))
    y = 24
    for r in rows:
        S.paste(r, (0, y)); y += r.height + 4
    return S
