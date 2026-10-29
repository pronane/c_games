"""OUTPUT PROFILES - a small declarative JSON file that says what to emit for a kind of game,
with NO game-specific code in the tool.  profiles/*.json ship with the studio; make your own with
`forge.py profile new` or the GUI's "Create profile..." dialog, check it with `forge.py profile validate`.

{
  "name": "kart_racer", "description": "...",
  "moves": "kart12" | ["idle", "walk", "dash=sprint:8:14:loop", {"name": "wave", "motion": "kart_taunt", "frames": 6}],
  "frame": [512, 640], "figure_h": 0.97, "ground_y": 639,        (ints = px, floats <= 1 = fraction of frame_h)
  "views": "billboard8" | ["front", "right", "back"],  "view_cut": 0.55, "view_moves": ["idle"],
  "prop": "none", "console": "snes", "dither": true, "fill": "placeholder", "yaw": 65, "gifs": false, ...
  "vars": {"speed": "3.0", ...},                                 (template variables; --set key=value overrides)
  "images":    [ {"type": "grid", "file": "sprite.png", "views": "billboard8", "cols": 4, "move": "idle"},
                 {"type": "frame", "file": "win.png", "view": "front", "move": ["victory", "idle"]},
                 {"type": "portrait", "file": "portrait.png", "view": "front", "size": 256},
                 {"type": "frames", "dir": "anims/{move}", "file": "{i:04d}.png", "view": "front"} ],
  "manifests": [ {"type": "ini", "file": "character.ini", "header": "; ...", "keys": {"name": "{display_name}"},
                  "sections": {"extra": {"k": "v"}}, "per_view_section": "views", "per_view_value": "{angle},{image}"},
                 {"type": "template", "file": "x.txt", "header": "...", "per_move": "...", "per_view": "...", "footer": "..."},
                 {"type": "godot_spriteframes", "file": "{name}.tres", "res_path": "res://characters/{name}/"},
                 {"type": "tiled_tsx", "file": "{name}.tsx"},
                 {"type": "unity_json", "file": "{name}.unity.json"},
                 {"type": "json", "file": "x.json", "data": {...any JSON, strings are templates...}} ]
}
Templates use {placeholders}: see PLACEHOLDERS below (forge.py help profiles lists them).
sprites.cfg, atlas.json and the default character.ini are ALWAYS written; a profile manifest with the
same file name replaces it."""
from __future__ import annotations
import copy
import datetime
import json
import os
import string
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(HERE, "profiles")

PLACEHOLDERS = {
    "name": "folder-safe name (slug)", "display_name": "the name as typed", "version": "studio version",
    "mode": "input mode", "date": "build date", "profile": "profile name",
    "frame_w": "cell width px", "frame_h": "cell height px", "ground_y": "ground line y px",
    "pivot_x": "pivot x px", "pivot_x_norm": "pivot x 0..1", "pivot_y_norm": "ground y 0..1 (from top)",
    "pivot_y_norm_up": "ground y 0..1 from the BOTTOM (Unity)", "scale": "height vs 180 cm reference",
    "px_per_metre": "pixels per metre", "height_px": "standing height px", "atlas": "atlas.png",
    "atlas_w": "atlas width", "atlas_h": "atlas height", "pages": "atlas pages", "columns": "atlas columns",
    "move_count": "number of moves", "moves_csv": "idle,walk,...", "view_count": "number of views",
    "views_csv": "front,right,...", "face_x": "face centre x 0..1 in the front cell", "face_y": "face centre y 0..1",
    "tile_count": "columns x rows of atlas.png",
}
MOVE_KEYS = {"move": "move name", "label": "label", "category": "category", "frames": "frame count", "fps": "fps",
             "loop": "1/0", "loop_word": "loop/once", "loop_bool": "true/false", "row": "atlas row", "page": "atlas page",
             "image": "atlas file", "y": "row y px", "source": "where the frames came from", "duration_ms": "ms per frame",
             "first_tile": "tile id of frame 0 (row*columns)", "index": "0-based move number",
             "repeat": "-1 if it loops, 0 if not (Phaser)", "last_tile": "tile id of the last frame"}
VIEW_KEYS = {"view": "view name", "angle": "camera yaw", "image": "views/atlas_<view>.png", "source": "real / mirrored / filled",
             "filled": "1 if not a real view", "index": "0-based view number", "frame0": "views/<view>/<first move>_00.png"}
CFG_KEYS = {"moves", "frame", "figure_h", "ground_y", "pivot_x", "views", "view_cut", "view_moves", "view_figure_h",
            "view_frames", "prop", "console", "dither", "fill", "yaw", "outline", "gifs", "strips", "glb", "fbx",
            "max_atlas", "cutout", "anchor", "kit", "rig", "clip_map", "root_motion",
            "material_split", "material_slots", "anim_export", "human", "outfits", "props", "slot_colors"}
TOP_KEYS = CFG_KEYS | {"name", "description", "vars", "images", "manifests", "notes", "game_hint"}
MANIFEST_TYPES = {"ini", "template", "godot_spriteframes", "tiled_tsx", "unity_json", "json"}
IMAGE_TYPES = {"grid", "frame", "portrait", "frames"}


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def fmt(t, ctx):
    if not isinstance(t, str):
        return t
    try:
        return string.Formatter().vformat(t, (), _Safe(ctx))
    except (ValueError, IndexError, KeyError) as e:
        raise ValueError("bad template %r: %s" % (t, e))


def list_profiles():
    if not os.path.isdir(PROFILE_DIR):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))


def path_of(name_or_path):
    if os.path.isfile(name_or_path):
        return name_or_path
    p = os.path.join(PROFILE_DIR, name_or_path if name_or_path.endswith(".json") else name_or_path + ".json")
    if os.path.isfile(p):
        return p
    raise FileNotFoundError("profile '%s' not found (have: %s)" % (name_or_path, ", ".join(list_profiles())))


def load(name_or_path):
    p = path_of(name_or_path)
    with open(p, encoding="utf-8") as f:
        try:
            d = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("%s is not valid JSON: %s" % (p, e))
    d.setdefault("name", os.path.splitext(os.path.basename(p))[0])
    d["_path"] = p
    return d


# ------------------------------------------------------------------ moves / config
def resolve_moves(spec):
    from .moves import preset, PRESETS, PRESET_KEYS, MoveSpec, slug
    from .motions import find_motion
    if isinstance(spec, str):
        return preset(spec)
    allm = {}
    for k in PRESETS.values():
        for m in k:
            allm.setdefault(m.name, m)
    out = []
    for it in spec:
        if isinstance(it, dict):
            base = allm.get(slug(it.get("name", "")))
            m = copy.deepcopy(base) if base else MoveSpec(slug(it["name"]), it.get("label", it["name"]), it.get("category", "Custom"), 8, 12, False)
            for k in ("label", "category", "frames", "fps", "loop", "motion", "desc"):
                if k in it:
                    setattr(m, k, it[k])
            out.append(m); continue
        parts = str(it).split(":")
        nm, _, mot = parts[0].partition("=")
        key = slug(nm)
        m = copy.deepcopy(allm[key]) if key in allm else None
        if m is None:
            mo = find_motion(mot or nm)
            if mo is None:
                raise ValueError("move '%s': no preset move or procedural motion of that name (use name=motion)" % nm)
            m = MoveSpec(key, nm, mo.category, 8, 12, bool(mo.loop), mot or "", "profile move")
        if mot:
            m.motion = mot
        if len(parts) > 1 and parts[1]:
            m.frames = int(parts[1])
        if len(parts) > 2 and parts[2]:
            m.fps = int(parts[2])
        if len(parts) > 3:
            m.loop = parts[3].lower() in ("1", "loop", "true", "yes")
        out.append(m)
    return out


def _px(v, ref):
    if v is None:
        return 0
    v = float(v)
    return int(round(v * ref)) if 0 < v <= 1.0 else int(v)


def apply(cfg, prof):
    """Set BuildConfig defaults from a profile (call BEFORE applying explicit user options)."""
    from . import views as V
    cfg.profile = prof
    if "moves" in prof:
        cfg.moves = resolve_moves(prof["moves"])
    if "frame" in prof:
        f = prof["frame"]
        cfg.frame_w, cfg.frame_h = (int(f[0]), int(f[1])) if isinstance(f, (list, tuple)) else (int(f), int(f))
    for k in ("figure_h", "ground_y"):
        if k in prof:
            setattr(cfg, k, _px(prof[k], cfg.frame_h))
    if "pivot_x" in prof:
        cfg.pivot_x = _px(prof["pivot_x"], cfg.frame_w)
    if "views" in prof:
        v = prof["views"]
        if isinstance(v, str) and v.lower() in ("billboard8", "8dir", "8"):
            cfg.billboard8 = True
        else:
            cfg.view_list = V.parse_view_list(v)
    for k in ("view_cut", "view_frames", "prop", "fill", "yaw", "outline", "gifs", "strips", "glb", "fbx", "max_atlas",
              "cutout", "anchor", "kit", "dither"):
        if k in prof:
            setattr(cfg, k, prof[k])
    if "view_figure_h" in prof:
        cfg.view_figure_h = _px(prof["view_figure_h"], cfg.frame_h)
    if "view_moves" in prof:
        cfg.view_moves = list(prof["view_moves"])
    if prof.get("console"):
        from . import consoles
        cfg.console = consoles.by_label(prof["console"])
    # v6 library rigs: "rig", "root_motion", "clip_map" {move: clip entry}, or "clip" inside a move entry
    if prof.get("rig"):
        cfg.mode = "library"; cfg.rig = prof["rig"]
    if prof.get("root_motion"):
        cfg.root_motion = prof["root_motion"]
    for k_ in ("material_split", "material_slots"):
        if prof.get(k_):
            setattr(cfg, k_, prof[k_])
    if "anim_export" in prof:
        cfg.anim_export = bool(prof["anim_export"])
    if prof.get("human"):
        h = prof["human"]
        cfg.human = h if isinstance(h, str) else ",".join("%s=%s" % kv for kv in h.items())
    for k_ in ("outfits", "props"):
        if prof.get(k_):
            setattr(cfg, k_, [prof[k_]] if isinstance(prof[k_], str) else list(prof[k_]))
    if prof.get("slot_colors"):
        sc = prof["slot_colors"]
        cfg.slot_colors = sc if isinstance(sc, str) else ",".join("%s=%s" % kv for kv in sc.items())
    from .librarybuild import norm_entry, load_clip_map
    if cfg.clip_map is None:
        cfg.clip_map = {}
    cm = prof.get("clip_map") or {}
    if isinstance(cm, str):
        cm = load_clip_map(cm if os.path.isabs(cm) or os.path.exists(cm) else os.path.join(PROFILE_DIR, cm))
    for k, v in cm.items():
        cfg.clip_map[k] = norm_entry(v)
    if isinstance(prof.get("moves"), list):
        from .moves import slug as _slug
        for it in prof["moves"]:
            if isinstance(it, dict) and it.get("clip"):
                e = norm_entry(it["clip"]) if not isinstance(it["clip"], dict) else dict(it["clip"])
                for k in ("speed", "trim"):
                    if k in it:
                        e[k] = it[k]
                if "clip_loop" in it:
                    e["loop"] = bool(it["clip_loop"])
                cfg.clip_map[_slug(it["name"])] = e
    return cfg


# ------------------------------------------------------------------ validation
def _check_tpl(t, keys, where, errs):
    if not isinstance(t, str):
        return
    try:
        for _, field_name, _, _ in string.Formatter().parse(t):
            if field_name is None:
                continue
            base = field_name.split(".")[0].split("[")[0]
            if base and base not in keys:
                errs.append("%s: unknown placeholder {%s}" % (where, base))
    except ValueError as e:
        errs.append("%s: bad template (%s) - use {{ and }} for literal braces" % (where, e))


def validate(prof):
    """-> (errors, warnings)"""
    from . import views as V
    errs, warns = [], []
    for k in prof:
        if k not in TOP_KEYS and not k.startswith("_"):
            warns.append("unknown key '%s' (ignored)" % k)
    if "moves" in prof:
        try:
            ms = resolve_moves(prof["moves"])
            if not ms:
                errs.append("moves: empty")
        except Exception as e:
            errs.append("moves: %s" % e)
    if "frame" in prof:
        f = prof["frame"]
        ok = isinstance(f, int) or (isinstance(f, (list, tuple)) and len(f) == 2 and all(isinstance(x, int) and 8 <= x <= 4096 for x in f))
        if not ok:
            errs.append("frame: must be [width, height] in px (8..4096)")
    if "views" in prof:
        try:
            if not (isinstance(prof["views"], str) and prof["views"].lower() in ("billboard8", "8dir", "8")):
                V.parse_view_list(prof["views"])
        except Exception as e:
            errs.append("views: %s" % e)
    if "view_cut" in prof and not (0 <= float(prof["view_cut"]) <= 1):
        errs.append("view_cut: 0..1 (0 = whole figure, 0.55 = bust)")
    if prof.get("console"):
        from . import consoles
        if not consoles.by_label(prof["console"]):
            errs.append("console: unknown '%s' (forge.py consoles)" % prof["console"])
    if prof.get("material_split") and prof["material_split"] not in ("auto", "off"):
        errs.append("material_split: auto | off")
    if prof.get("material_slots") and prof["material_slots"] not in ("full", "core4", "keep"):
        errs.append("material_slots: full | core4 | keep")
    if prof.get("root_motion") and prof["root_motion"] not in ("keep", "inplace", "root"):
        errs.append("root_motion: keep | inplace | root")
    if prof.get("clip_map") is not None:
        cm = prof["clip_map"]
        if not isinstance(cm, (dict, str)):
            errs.append("clip_map: a {move: \"asset:clip@speed=..,trim=a-b,loop\"} object or a JSON file path")
        elif isinstance(cm, dict):
            from . import librarybuild as LB
            for mv, v in cm.items():
                try:
                    LB.norm_entry(v)
                except Exception as e:
                    errs.append("clip_map.%s: %s" % (mv, e))
    if prof.get("rig"):
        try:
            from . import library as L
            r = str(prof["rig"])
            if not (r.lower().endswith((".fbx", ".glb", ".gltf")) or L.Library().find(r, "rigs") or L.Library().find(r, "animations")):
                warns.append("rig: '%s' is not in the library (forge.py library list) - it must exist when you build" % r)
        except Exception:
            pass
    keys = set(PLACEHOLDERS) | set(prof.get("vars", {}))
    for i, im in enumerate(prof.get("images", [])):
        w = "images[%d]" % i
        if im.get("type") not in IMAGE_TYPES:
            errs.append("%s: type must be one of %s" % (w, ", ".join(sorted(IMAGE_TYPES)))); continue
        if im["type"] != "frames" and not im.get("file"):
            errs.append("%s: needs 'file'" % w)
        if im["type"] == "frames":
            _check_tpl(im.get("dir", ""), keys | set(MOVE_KEYS) | {"i", "view"}, w + ".dir", errs)
            _check_tpl(im.get("file", "{move}_{i:02d}.png"), keys | set(MOVE_KEYS) | {"i", "view"}, w + ".file", errs)
        vv = im.get("views")
        if vv:
            try:
                V.parse_view_list(vv)
            except Exception as e:
                errs.append("%s.views: %s" % (w, e))
        if im.get("view"):
            try:
                V.norm_view(im["view"])
            except Exception as e:
                errs.append("%s.view: %s" % (w, e))
    for i, m in enumerate(prof.get("manifests", [])):
        w = "manifests[%d]" % i
        t = m.get("type")
        if t not in MANIFEST_TYPES:
            errs.append("%s: type must be one of %s" % (w, ", ".join(sorted(MANIFEST_TYPES)))); continue
        if t in ("ini", "template", "json") and not m.get("file"):
            errs.append("%s: needs 'file'" % w)
        _check_tpl(m.get("file", ""), keys, w + ".file", errs)
        if t == "ini":
            for k, v in m.get("keys", {}).items():
                _check_tpl(v, keys, "%s.keys.%s" % (w, k), errs)
            for sn, sec in m.get("sections", {}).items():
                for k, v in sec.items():
                    _check_tpl(v, keys, "%s.sections.%s.%s" % (w, sn, k), errs)
            _check_tpl(m.get("per_view_value", ""), keys | set(VIEW_KEYS), w + ".per_view_value", errs)
            _check_tpl(m.get("per_move_value", ""), keys | set(MOVE_KEYS), w + ".per_move_value", errs)
            _check_tpl(m.get("header", ""), keys, w + ".header", errs)
        if t == "template":
            for part in ("header", "footer"):
                _check_tpl(m.get(part, ""), keys, "%s.%s" % (w, part), errs)
            _check_tpl(m.get("per_move", ""), keys | set(MOVE_KEYS), w + ".per_move", errs)
            _check_tpl(m.get("per_view", ""), keys | set(VIEW_KEYS), w + ".per_view", errs)
            if not any(m.get(p) for p in ("header", "per_move", "per_view", "footer")):
                warns.append("%s: template has no text" % w)
        if t == "json":
            def walk(o, path, ks):
                if isinstance(o, str):
                    _check_tpl(o, ks, path, errs)
                elif isinstance(o, dict):
                    for k, v in o.items():
                        extra = set(MOVE_KEYS) if k == "$per_move" else set(VIEW_KEYS) if k == "$per_view" else set()
                        walk(v, path + "." + k, ks | extra)
                elif isinstance(o, list):
                    for j, v in enumerate(o):
                        walk(v, "%s[%d]" % (path, j), ks)
            walk(m.get("data", {}), w + ".data", keys)
    if not prof.get("manifests") and not prof.get("images"):
        warns.append("no images/manifests: only the standard outputs (sprites.cfg, atlas.json, character.ini) are written")
    return errs, warns


# ------------------------------------------------------------------ context
def _front_still(out, view_info, first_move):
    for v in ("front", "front_right", "front_left"):
        if v in view_info:
            p = os.path.join(out, "views", v, "%s_00.png" % first_move)
            if os.path.isfile(p):
                return Image.open(p).convert("RGBA"), v
    p = os.path.join(out, "moves", "%s_00.png" % first_move)
    return (Image.open(p).convert("RGBA"), "main") if os.path.isfile(p) else (None, "")


def head_box(im, cut, ground_y):
    """Rough head box from the silhouette: top of the figure, ~13% of the full body height."""
    import numpy as np
    a = np.asarray(im.getchannel("A")) > 40
    rows = np.nonzero(a.any(1))[0]
    if not len(rows):
        return None
    top = int(rows.min()); bot = min(int(rows.max()), ground_y)
    full = (bot - top) / (cut if cut and cut < 0.999 else 1.0)
    hh = max(8, int(full * 0.13))
    band = a[top:top + hh]
    xs = np.nonzero(band.any(0))[0]
    cx = float((band.sum(0) * np.arange(a.shape[1])).sum() / max(1, band.sum())) if len(xs) else im.width / 2
    return cx, top, hh


def context(cfg, out, ordered, placed, page_names, spec_by, frames, view_info, scale, px_per_m, stand_px, cols):
    from . import __version__
    prof = cfg.profile or {}
    aw, ah = Image.open(os.path.join(out, page_names[0])).size
    moves = []
    for i, (mv, page, row, n) in enumerate(placed):
        m = spec_by[mv]
        moves.append(dict(move=mv, label=m.label or mv, category=m.category, frames=n, fps=m.fps, loop=1 if m.loop else 0,
                          loop_word="loop" if m.loop else "once", loop_bool="true" if m.loop else "false", row=row, page=page,
                          image=page_names[page], y=row * cfg.frame_h, source=frames[mv][1],
                          duration_ms=int(round(1000 / max(1, m.fps))), first_tile=row * cols, index=i,
                          repeat=-1 if m.loop else 0, last_tile=row * cols + n - 1))
    first = moves[0]["move"] if moves else "idle"
    vlist = []
    for i, (v, inf) in enumerate(view_info.items()):
        vlist.append(dict(view=v, angle=inf["angle"], image=inf["images"][0], source=inf["source"],
                          filled=1 if inf["filled"] else 0, index=i, frame0="views/%s/%s_00.png" % (v, first)))
    ctx = dict(name=cfg.name, display_name=cfg.display_name or cfg.name, version=__version__, mode=cfg.mode,
               date=datetime.date.today().isoformat(), profile=prof.get("name", ""),
               frame_w=cfg.frame_w, frame_h=cfg.frame_h, ground_y=cfg.ground_y, pivot_x=cfg.pivot_x,
               pivot_x_norm=round(cfg.pivot_x / cfg.frame_w, 5), pivot_y_norm=round(cfg.ground_y / cfg.frame_h, 5),
               pivot_y_norm_up=round(1 - cfg.ground_y / cfg.frame_h, 5), scale="%.4f" % scale,
               px_per_metre="%.3f" % (px_per_m * scale), height_px=stand_px, atlas=page_names[0], atlas_w=aw, atlas_h=ah,
               pages=len(page_names), columns=cols, move_count=len(moves), moves_csv=",".join(m["move"] for m in moves),
               view_count=len(vlist), views_csv=",".join(v["view"] for v in vlist), tile_count=cols * (ah // cfg.frame_h),
               face_x="0.500", face_y="0.300")
    still, _ = _front_still(out, view_info, first)
    if still is not None:
        hb = head_box(still, cfg.view_cut if view_info else 0, cfg.ground_y)
        if hb:
            cx, top, hh = hb
            ctx["face_x"] = "%.3f" % (cx / cfg.frame_w); ctx["face_y"] = "%.3f" % ((top + hh * 0.55) / cfg.frame_h)
    vars_ = {k: str(v) for k, v in prof.get("vars", {}).items()}
    vars_.update({k: str(v) for k, v in (cfg.profile_vars or {}).items()})
    for k, v in vars_.items():
        ctx[k] = fmt(v, ctx) if "{" in v else v
    ctx["_moves"], ctx["_views"], ctx["_cfg"] = moves, vlist, cfg
    ctx["_out"] = out
    return ctx


# ------------------------------------------------------------------ images
def _pick(out, view, moves, frame, ctx):
    names = [moves] if isinstance(moves, str) else list(moves or [])
    have = [m["move"] for m in ctx["_moves"]]
    names = [m for m in names if m in have] + have[:1]
    mv = names[0]
    n = next(m["frames"] for m in ctx["_moves"] if m["move"] == mv)
    i = n // 2 if frame == "key" else min(int(frame or 0), n - 1)
    if view:
        p = os.path.join(out, "views", view, "%s_%02d.png" % (mv, i))
        if os.path.isfile(p):
            return Image.open(p).convert("RGBA"), "%s/%s" % (view, mv)
    return Image.open(os.path.join(out, "moves", "%s_%02d.png" % (mv, i))).convert("RGBA"), "main/%s" % mv


def emit_images(prof, ctx, out, log):
    from . import views as V
    cfg = ctx["_cfg"]; written = []
    for im in prof.get("images", []):
        t = im["type"]
        if t == "grid":
            vs = V.parse_view_list(im.get("views", "billboard8"))
            cols = int(im.get("cols", len(vs)))
            rows = (len(vs) + cols - 1) // cols
            g = Image.new("RGBA", (cols * cfg.frame_w, rows * cfg.frame_h), (0, 0, 0, 0))
            src = []
            for i, v in enumerate(vs):
                c, s = _pick(out, v, im.get("move", "idle"), im.get("frame", 0), ctx)
                if not s.startswith(v):
                    log("  ! profile grid %s: view '%s' not built - used %s" % (im["file"], v, s))
                g.paste(c, ((i % cols) * cfg.frame_w, (i // cols) * cfg.frame_h)); src.append(s)
        elif t == "frame":
            g, s = _pick(out, V.norm_view(im["view"]) if im.get("view") else None, im.get("move", "idle"), im.get("frame", "key"), ctx)
        elif t == "portrait":
            c, s = _pick(out, V.norm_view(im.get("view", "front")), im.get("move", "idle"), im.get("frame", 0), ctx)
            hb = head_box(c, cfg.view_cut if ctx["_views"] else 0, cfg.ground_y)
            size = int(im.get("size", 256))
            if hb:
                cx, top, hh = hb
                side = hh * float(im.get("zoom", 1.9)); cy = top + hh * 0.6
                box = tuple(int(round(x)) for x in (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2))
                g = c.crop(box).resize((size, size), Image.LANCZOS)
            else:
                g = c.resize((size, size), Image.LANCZOS)
        elif t == "frames":
            view = V.norm_view(im["view"]) if im.get("view") else None
            n = 0
            for m in ctx["_moves"]:
                d = dict(ctx, **m, view=view or "main")
                for i in range(m["frames"]):
                    src = os.path.join(out, "views", view, "%s_%02d.png" % (m["move"], i)) if view else os.path.join(out, "moves", "%s_%02d.png" % (m["move"], i))
                    if not os.path.isfile(src):
                        continue
                    dst = os.path.join(out, fmt(im.get("dir", "frames/{move}"), d), fmt(im.get("file", "{move}_{i:02d}.png"), dict(d, i=i)))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    Image.open(src).save(dst); n += 1
            written.append("%s (%d frames)" % (fmt(im.get("dir", "frames/{move}"), dict(ctx, move="*", view=view or "main")), n))
            continue
        fn = fmt(im["file"], ctx)
        os.makedirs(os.path.dirname(os.path.join(out, fn)) or out, exist_ok=True)
        g.save(os.path.join(out, fn), compress_level=__import__("sforge.build", fromlist=["PNG_LEVEL"]).PNG_LEVEL()); written.append(fn)
    return written


# ------------------------------------------------------------------ manifests
def _ini(m, ctx):
    L = []
    if m.get("header"):
        L += [fmt(x, ctx) for x in m["header"].split("\n")]
    for k, v in m.get("keys", {}).items():
        L.append("%s = %s" % (k, fmt(str(v), ctx)))
    for sn, sec in m.get("sections", {}).items():
        L += ["", "[%s]" % fmt(sn, ctx)] + ["%s = %s" % (k, fmt(str(v), ctx)) for k, v in sec.items()]
    if m.get("per_move_section"):
        L += ["", "[%s]" % m["per_move_section"]]
        L += ["%s = %s" % (mv["move"], fmt(m.get("per_move_value", "{frames},{fps},{loop_word}"), dict(ctx, **mv))) for mv in ctx["_moves"]]
    if m.get("per_view_section") and ctx["_views"]:
        L += ["", "[%s]" % m["per_view_section"]]
        L += ["%s = %s" % (v["view"], fmt(m.get("per_view_value", "{angle},{image},{source}"), dict(ctx, **v))) for v in ctx["_views"]]
    return "\n".join(L) + "\n"


def _template(m, ctx):
    s = fmt(m.get("header", ""), ctx)
    for mv in ctx["_moves"]:
        s += fmt(m.get("per_move", ""), dict(ctx, **mv))
    for v in ctx["_views"]:
        s += fmt(m.get("per_view", ""), dict(ctx, **v))
    return s + fmt(m.get("footer", ""), ctx)


def _jsonfill(o, ctx):
    if isinstance(o, str):
        r = fmt(o, ctx)
        if o.startswith("{") and o.endswith("}") and o.count("{") == 1:
            try:
                return json.loads(r)
            except Exception:
                return r
        return r
    if isinstance(o, dict):
        if "$per_move" in o:
            return [_jsonfill(o["$per_move"], dict(ctx, **mv)) for mv in ctx["_moves"]]
        if "$per_view" in o:
            return [_jsonfill(o["$per_view"], dict(ctx, **v)) for v in ctx["_views"]]
        return {fmt(k, ctx): _jsonfill(v, ctx) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonfill(x, ctx) for x in o]
    return o


def _godot(m, ctx):
    """Godot 4 SpriteFrames (.tres): one AtlasTexture per frame, one animation per move (+ per view)."""
    res = fmt(m.get("res_path", "res://{name}/"), ctx)
    fw, fh = ctx["frame_w"], ctx["frame_h"]
    images = sorted({mv["image"] for mv in ctx["_moves"]})
    sets = [("", ctx["_moves"], {i: im for i, im in enumerate(images)})]
    ext = list(images)
    if m.get("include_views", True):
        for v in ctx["_views"]:
            ext.append(v["image"])
    ext_id = {p: i + 1 for i, p in enumerate(ext)}
    subs, anims, sid = [], [], 0
    groups = [("", None)] + ([(v["view"], v) for v in ctx["_views"]] if m.get("include_views", True) else [])
    for vname, v in groups:
        for mv in ctx["_moves"]:
            img = mv["image"] if v is None else v["image"]
            row = mv["row"] if v is None else ctx["_out_rows"].get(vname, {}).get(mv["move"], mv["row"])
            frames = []
            for i in range(mv["frames"]):
                sid += 1
                subs.append('[sub_resource type="AtlasTexture" id="AtlasTexture_%d"]\natlas = ExtResource("%d")\nregion = Rect2(%d, %d, %d, %d)\n'
                            % (sid, ext_id[img], i * fw, row * fh, fw, fh))
                frames.append('{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_%d")\n}' % sid)
            nm = mv["move"] if v is None else "%s_%s" % (mv["move"], vname)
            anims.append('{\n"frames": [%s],\n"loop": %s,\n"name": &"%s",\n"speed": %.1f\n}' % (", ".join(frames), mv["loop_bool"], nm, mv["fps"]))
    head = '[gd_resource type="SpriteFrames" load_steps=%d format=3]\n\n' % (len(ext) + sid + 1)
    head += "".join('[ext_resource type="Texture2D" path="%s%s" id="%d"]\n' % (res, p, i) for p, i in ext_id.items()) + "\n"
    return head + "\n".join(subs) + "\n[resource]\nanimations = [%s]\n" % ", ".join(anims)


def _tiled(m, ctx):
    """Tiled tileset (.tsx) over atlas.png: tile id = row*columns + col; one animated tile per move."""
    import xml.sax.saxutils as X
    fw, fh, cols = ctx["frame_w"], ctx["frame_h"], ctx["columns"]
    count = ctx["tile_count"]
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<tileset version="1.10" tiledversion="1.10.2" name="%s" tilewidth="%d" tileheight="%d" tilecount="%d" columns="%d">'
         % (X.escape(ctx["name"]), fw, fh, count, cols),
         ' <tileoffset x="%d" y="%d"/>' % (-ctx["pivot_x"] + fw // 2, ctx["frame_h"] - ctx["ground_y"]),
         ' <image source="%s" width="%d" height="%d"/>' % (ctx["atlas"], ctx["atlas_w"], ctx["atlas_h"])]
    for mv in ctx["_moves"]:
        if mv["page"] != 0:
            continue
        t0 = mv["row"] * cols
        L.append(' <tile id="%d" class="%s">' % (t0, X.escape(mv["move"])))
        L.append('  <properties><property name="move" value="%s"/><property name="loop" type="bool" value="%s"/><property name="fps" type="float" value="%s"/></properties>'
                 % (X.escape(mv["move"]), mv["loop_bool"], mv["fps"]))
        L.append('  <animation>' + "".join('<frame tileid="%d" duration="%d"/>' % (t0 + i, mv["duration_ms"]) for i in range(mv["frames"])) + '</animation>')
        L.append(' </tile>')
    L.append('</tileset>')
    return "\n".join(L) + "\n"


def _unity(m, ctx):
    """Unity-style sprite import JSON: rects in Unity pixel space (origin BOTTOM-left), normalized pivots,
    clips with frame rate - feed it to a small AssetPostprocessor / Sprite Editor script."""
    fw, fh = ctx["frame_w"], ctx["frame_h"]
    sprites, clips = [], []
    def add(img, ah, mv, row, prefix):
        names = []
        for i in range(mv["frames"]):
            n = "%s%s_%02d" % (prefix, mv["move"], i)
            sprites.append({"name": n, "texture": img, "rect": {"x": i * fw, "y": ah - (row + 1) * fh, "width": fw, "height": fh},
                            "pivot": {"x": ctx["pivot_x_norm"], "y": ctx["pivot_y_norm_up"]}, "alignment": 9})
            names.append(n)
        clips.append({"name": prefix + mv["move"], "frameRate": mv["fps"], "loop": bool(mv["loop"]), "sprites": names})
    for mv in ctx["_moves"]:
        add(mv["image"], ctx["atlas_h"], mv, mv["row"], "")
    if m.get("include_views", True):
        for v in ctx["_views"]:
            ah = Image.open(os.path.join(ctx["_out"], v["image"])).size[1]
            for mv in ctx["_moves"]:
                add(v["image"], ah, mv, ctx["_out_rows"].get(v["view"], {}).get(mv["move"], mv["row"]), v["view"] + "/")
    return json.dumps({"generator": "Sprite Forge Studio %s" % ctx["version"], "name": ctx["name"],
                       "pixelsPerUnit": float(ctx["px_per_metre"]), "filterMode": m.get("filter", "Bilinear"),
                       "spriteMode": "Multiple", "sprites": sprites, "clips": clips,
                       "views": [{"name": v["view"], "angle": v["angle"], "texture": v["image"], "source": v["source"]} for v in ctx["_views"]]},
                      indent=1)


def emit(prof, ctx, out, log=print):
    cfg = ctx["_cfg"]
    ctx["_out_rows"] = {}
    try:
        aj = json.load(open(os.path.join(out, "atlas.json")))
        ctx["_out_rows"] = {v: i.get("rows", {}) for v, i in aj.get("views", {}).items()}
    except Exception:
        pass
    written = emit_images(prof, ctx, out, log)
    for m in prof.get("manifests", []):
        t = m["type"]
        default = {"godot_spriteframes": "{name}.tres", "tiled_tsx": "{name}.tsx", "unity_json": "{name}.unity.json"}.get(t, "")
        fn = fmt(m.get("file", default), ctx)
        body = {"ini": _ini, "template": _template, "godot_spriteframes": _godot, "tiled_tsx": _tiled, "unity_json": _unity,
                "json": lambda mm, c: json.dumps(_jsonfill(mm.get("data", {}), c), indent=1) + "\n"}[t](m, ctx)
        p = os.path.join(out, fn)
        os.makedirs(os.path.dirname(p) or out, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline=m.get("newline", "\n")) as f:
            f.write(body)
        written.append(fn)
    log("  profile '%s': %s" % (prof.get("name", "?"), ", ".join(written) or "(standard outputs only)"))
    return written


# ------------------------------------------------------------------ new profile
def new_profile(name, base=None, moves=None, views=None, frame=None, manifests=None, description=""):
    from .moves import slug
    d = copy.deepcopy(load(base)) if base else {}
    d.pop("_path", None)
    d["name"] = slug(name)
    d["description"] = description or d.get("description", "My profile")
    if moves:
        d["moves"] = moves if isinstance(moves, (list, str)) else list(moves)
    d.setdefault("moves", "fighter14")
    if views:
        if isinstance(views, str) and views.strip().lower() not in ("billboard8", "8dir", "8"):
            views = [x.strip() for x in views.replace(";", ",").split(",") if x.strip()]
        d["views"] = views
    if frame:
        d["frame"] = list(frame)
    if manifests is not None:
        mans = [x for x in d.get("manifests", []) if x["type"] not in ("godot_spriteframes", "tiled_tsx", "unity_json")]
        for t in manifests:
            if t in ("godot_spriteframes", "tiled_tsx", "unity_json") and not any(x["type"] == t for x in mans):
                mans.append({"type": t})
        d["manifests"] = mans
    return d


def save(d, path=None):
    path = path or os.path.join(PROFILE_DIR, d["name"] + ".json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in d.items() if not k.startswith("_")}, f, indent=2)
    return path
