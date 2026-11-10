"""v11.5 game_character.json — one engine-neutral file for every build.

The manifest describes the character that was just built: name, character type,
game pack, camera, frame size, pivot / ground line, and one record per animation
(sheet or strip, frame count, fps, loop, events, hitboxes / hurtboxes when the
existing frame-data pass can measure them).

Loaders that read it live in loaders/ (raylib C, Godot 4, Unity). A build copies
those text files next to the character. It does not copy a game engine.

Existing Egyptian Fighter / HD Fighter adapters read atlas.json and sprites.cfg.
If those are missing and this manifest is present, ensure_atlas / ensure_sprites_cfg
rebuild the small index they need from the manifest plus moves/*.png. The Gaelic
3D mesh tool and the Arena FC photo tool are not sprite-sheet adapters; they are
unchanged.
"""
from __future__ import annotations
import json
import os
import shutil

from .gamepack import scale_events

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOADERS = os.path.join(HERE, "loaders")
FORMAT = "spriteforge.game_character"
VERSION = 1


def _blank_events():
    return {"hit_start": -1, "hit_end": -1, "ball_contact": -1, "throw_release": -1,
            "shoot": -1, "reload": -1, "footsteps": []}


def _boxes(frames, name, fps):
    """Hit / hurt boxes from the existing framedata pass. Empty lists if it cannot run."""
    hits, hurts = [], []
    note = ""
    try:
        from . import framedata
        info = framedata.analyse_move(frames, name, fps)
    except Exception as e:
        return [], [], "hitboxes not measured (%s)" % e
    for i, fr in enumerate(info.get("frames") or []):
        for h in fr.get("hurt") or []:
            hurts.append({"frame": i, "part": h.get("part") or "body", "box": [int(x) for x in h["box"]]})
        for h in fr.get("hit") or []:
            hits.append({"frame": i, "box": [int(x) for x in h["box"]]})
    if info.get("attack") and not hits:
        note = "no hitbox stood out from the silhouette (framedata estimate)"
    return hits, hurts, note


def write(cfg, out, frames, placed, spec_by, view_info, stand_px, page_names):
    """Write game_character.json, per-move strips, and a copy of the loaders. -> relative path."""
    os.makedirs(os.path.join(out, "strips"), exist_ok=True)
    by_place = {mv: (page, row, n) for mv, page, row, n in placed}
    anims = []
    notes = []
    events_all = getattr(cfg, "game_events", None) or {}
    for m in cfg.moves:
        if m.name not in frames or m.name not in by_place:
            continue
        cells, sprite_src, sprite_note = frames[m.name]
        page, row, n = by_place[m.name]
        n = len(cells)
        strip_name = "strips/%s.png" % m.name
        from PIL import Image
        strip = Image.new("RGBA", (cfg.frame_w * n, cfg.frame_h), (0, 0, 0, 0))
        for i, im in enumerate(cells):
            strip.paste(im, (i * cfg.frame_w, 0))
        strip.save(os.path.join(out, strip_name))
        src_n = int(getattr(m, "pack_frames", 0) or n)
        ev = scale_events(events_all.get(m.name) or _blank_events(), src_n, n)
        hits, hurts, box_note = _boxes(cells, m.name, m.fps)
        if box_note:
            notes.append("%s: %s" % (m.name, box_note))
        sheet = page_names[page] if page < len(page_names) else (page_names[0] if page_names else "atlas.png")
        anims.append({
            "name": m.name,
            "label": m.label or m.name,
            "category": m.category,
            "strip": strip_name,
            "sheet": sheet,
            "frames": n,
            "fps": int(m.fps),
            "loop": bool(m.loop),
            "w": int(cfg.frame_w),
            "h": int(cfg.frame_h),
            "row": int(row),
            "col0": 0,
            "pivot": {"x": int(cfg.pivot_x), "y": int(cfg.ground_y)},
            "ground_y": int(cfg.ground_y),
            "source": getattr(m, "motion_source", "") or sprite_src or "procedural",
            "library": getattr(m, "library_name", "") or ((m.motion or "").split(":", 1)[-1] if (m.motion or "").startswith("lib:") else ""),
            "events": ev,
            "hitboxes": hits,
            "hurtboxes": hurts,
        })
    views = []
    for v, inf in (view_info or {}).items():
        views.append({"name": v, "angle": inf.get("angle"), "file": (inf.get("images") or [""])[0],
                      "source": inf.get("source")})
    cam = getattr(cfg, "game_camera", "") or ""
    if not cam:
        if getattr(cfg, "billboard8", False):
            cam = "topdown8"
        elif abs(float(getattr(cfg, "yaw", 65) or 65) - 90) < 5:
            cam = "side"
        else:
            cam = "three_quarter"
    doc = {
        "format": FORMAT,
        "version": VERSION,
        "generator": "Sprite Forge v11.5",
        "name": cfg.name,
        "character_type": getattr(cfg, "character_type", "") or "",
        "game_pack": getattr(cfg, "game_pack", "") or "",
        "camera": cam,
        "props": list(getattr(cfg, "game_props", None) or []),
        "frame": {"w": int(cfg.frame_w), "h": int(cfg.frame_h)},
        "pivot": {"x": int(cfg.pivot_x), "y": int(cfg.ground_y)},
        "ground_y": int(cfg.ground_y),
        "height_px": int(stand_px),
        "facing": "right",
        "coords": "pixels, origin top-left, y down. pivot/ground_y is the foot line inside the cell.",
        "animations": anims,
        "views": views,
        "notes": notes,
        "limits": [
            "Hitboxes and hurtboxes are estimated from the sprite silhouette (the v9 framedata pass), not authored collision.",
            "Events are frame indices into the animation that was built. A Quick preview uses fewer frames, so indices are scaled.",
            "The motion source is set:<name>, library, starter, or procedural.",
            "This file has no photo, no video and no body mesh.",
        ],
    }
    path = os.path.join(out, "game_character.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    copied = copy_loaders(out)
    return "game_character.json", copied


def copy_loaders(out):
    dst = os.path.join(out, "loaders")
    if not os.path.isdir(LOADERS):
        return []
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(LOADERS, dst, ignore=shutil.ignore_patterns("__pycache__", "*.o", "*.exe", "example"))
    return ["loaders/"]


def validate_file(path):
    """-> (errors, warnings) for a game_character.json on disk."""
    errs, warns = [], []
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [str(e)], []
    if d.get("format") != FORMAT:
        errs.append("format is %r, expected %r" % (d.get("format"), FORMAT))
    if int(d.get("version") or 0) != VERSION:
        errs.append("version is %r, expected %d" % (d.get("version"), VERSION))
    if not d.get("name"):
        errs.append("name is missing")
    fr = d.get("frame") or {}
    if not (isinstance(fr, dict) and int(fr.get("w") or 0) > 0 and int(fr.get("h") or 0) > 0):
        errs.append("frame.w / frame.h missing")
    anims = d.get("animations")
    if not isinstance(anims, list) or not anims:
        errs.append("animations is empty")
        return errs, warns
    folder = os.path.dirname(path)
    for a in anims:
        if not a.get("name"):
            errs.append("an animation has no name")
            continue
        for k in ("frames", "fps", "w", "h"):
            if int(a.get(k) or 0) <= 0:
                errs.append("%s: %s must be > 0" % (a["name"], k))
        if "loop" not in a:
            errs.append("%s: loop flag missing" % a["name"])
        gy = (a.get("pivot") or {}).get("y", a.get("ground_y"))
        if gy is None:
            errs.append("%s: no ground line" % a["name"])
        strip = a.get("strip") or ""
        if strip and not os.path.isfile(os.path.join(folder, strip)):
            warns.append("%s: strip %s is not next to the manifest" % (a["name"], strip))
        ev = a.get("events") or {}
        n = int(a.get("frames") or 1)
        for k in ("hit_start", "hit_end", "ball_contact", "throw_release", "shoot", "reload"):
            if k in ev and int(ev[k]) >= n:
                errs.append("%s: event %s=%s is past the last frame" % (a["name"], k, ev[k]))
    return errs, warns


def atlas_from_manifest(folder):
    """Minimal atlas.json so tools/export_ef.py and tools/export_hdf.py can read a manifest-only folder."""
    man_path = os.path.join(folder, "game_character.json")
    with open(man_path, encoding="utf-8") as f:
        man = json.load(f)
    fr = man["frame"]
    anims = {}
    for a in man.get("animations") or []:
        anims[a["name"]] = {
            "label": a.get("label") or a["name"],
            "frames": ["%s_%02d" % (a["name"], i) for i in range(int(a["frames"]))],
            "fps": a["fps"], "loop": bool(a["loop"]), "row": a.get("row", 0),
            "count": int(a["frames"]), "source": a.get("source") or "manifest",
        }
    js = {"meta": {"name": man.get("name") or "character", "frame_w": fr["w"], "frame_h": fr["h"],
                   "ground_y": man.get("ground_y") or (man.get("pivot") or {}).get("y") or fr["h"],
                   "pivot": man.get("pivot") or {"x": fr["w"] // 2, "y": fr["h"]},
                   "from": "game_character.json"},
          "animations": anims}
    with open(os.path.join(folder, "atlas.json"), "w", encoding="utf-8") as f:
        json.dump(js, f, indent=1)
    return js


def sprites_cfg_from_manifest(folder):
    """sprites.cfg (SpriteForge v1) from the manifest, for tools/to_egyptian_fighter.py."""
    man_path = os.path.join(folder, "game_character.json")
    with open(man_path, encoding="utf-8") as f:
        man = json.load(f)
    fr = man["frame"]
    gy = int(man.get("ground_y") or (man.get("pivot") or {}).get("y") or fr["h"])
    px = int((man.get("pivot") or {}).get("x") or fr["w"] // 2)
    L = ["# sprites.cfg written from game_character.json",
         "version 1", "name %s" % (man.get("name") or "character"),
         "frame %d %d" % (fr["w"], fr["h"]),
         "height %d" % int(man.get("height_px") or gy),
         "ground %d" % gy, "anchor_x %d" % px]
    for a in man.get("animations") or []:
        sheet = a.get("sheet") or "atlas.png"
        L.append("move %s %s %d %d %d %g %d %d" % (
            a["name"], sheet, int(a["frames"]), int(a["w"]), int(a["h"]), float(a["fps"]),
            1 if a.get("loop") else 0, int(a.get("row") or 0)))
    with open(os.path.join(folder, "sprites.cfg"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def ensure_atlas(folder):
    if os.path.isfile(os.path.join(folder, "atlas.json")):
        return False
    if not os.path.isfile(os.path.join(folder, "game_character.json")):
        return False
    atlas_from_manifest(folder)
    return True


def ensure_sprites_cfg(folder):
    if os.path.isfile(os.path.join(folder, "sprites.cfg")):
        return False
    if not os.path.isfile(os.path.join(folder, "game_character.json")):
        return False
    sprites_cfg_from_manifest(folder)
    return True
