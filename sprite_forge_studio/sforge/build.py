"""Build orchestrator shared by the GUI, the CLI (forge.py) and forge.bat.

Output layout (per character):
  out/<name>/character.ini     name, frame_w, frame_h, ground_y, pivot_x, scale, facing, mode ...
  out/<name>/atlas.png         (+ atlas_1.png ... only if one page is not enough)
  out/<name>/atlas.json        engine-neutral (TexturePacker-style hash + animations)
  out/<name>/sprites.cfg       SpriteForge v1 text format (spriteforge/include/spriteforge.h)
  out/<name>/moves/<move>_<NN>.png
  out/<name>/preview.png       labelled contact sheet of every move
  out/<name>/model.glb / model.fbx   (SPEC / mannequin mode only; FBX = built-in writer, Blender optional)
  out/<name>/build_report.txt  what was imported / rendered / filled
"""
from __future__ import annotations
import configparser
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from . import __version__
from .moves import MoveSpec, preset, slug, motion_for
from .spec import CharacterSpec, load_spec
from . import imaging

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class BuildConfig:
    name: str = "character"
    mode: str = "spec"                 # spec | photo | frames | sheet | library   ("mannequin" == spec with defaults)
    moves: List[MoveSpec] = field(default_factory=lambda: preset("gaelic36"))
    spec_path: str = ""
    spec: Optional[CharacterSpec] = None
    kit: str = ""                      # overrides spec kit if set
    photo: str = ""                    # PHOTO: front photo
    back: str = ""                     # PHOTO: optional back photo -> idle_back
    videos: Dict[str, str] = field(default_factory=dict)   # move -> video file (ffmpeg) or frames folder
    frames_dir: str = ""               # FRAMES: folder with <move>/ subfolders or <move>_<N>.png files
    sheet: str = ""                    # SHEET: sprite sheet image
    sheet_layout: str = "rows"         # rows = one row per move ; cells = one cell (1 frame) per move
    grid_rows: int = 0
    grid_cols: int = 0
    cutout: str = "auto"               # auto | alpha | rembg | threshold | none
    flip: bool = False                 # mirror imported images (make them face right)
    height_cm: float = 0.0             # PHOTO/FRAMES: real height -> relative scale (0 = standard)
    fill: str = "placeholder"          # missing moves: placeholder | static | mannequin | skip
    anchor: str = "auto"               # auto | feet | strip
    frame_w: int = 256
    frame_h: int = 256
    figure_h: int = 0                  # px height of a 180 cm standing figure (0 = 62% of frame_h)
    ground_y: int = 0                  # 0 = 94% of frame_h
    pivot_x: int = 0                   # 0 = frame_w / 2
    yaw: float = 65.0                  # mannequin camera: 90 = pure side profile, 0 = front
    outline: bool = True
    max_atlas: int = 8192
    out_root: str = "out"
    glb: bool = True
    fbx: bool = True
    blender: str = ""                  # path to blender(.exe); auto-detected if empty
    strips: bool = False               # also write strips/<move>.png
    gifs: bool = False                 # also write previews/<move>.gif
    extra_back_view: bool = True
    legacy_photo: bool = False         # True = old Studio-only photo path (no SpriteForge core)
    prop: str = "auto"                 # auto | kart | none  (kart prop for the kart-racer moves)
    kits: List[str] = field(default_factory=list)   # extra model_<kit>.glb/.fbx team variants
    mocap_files: List[str] = field(default_factory=list)   # mocap/<move>.json from `forge.py mocap` -> motions mocap_<move>
    move_sheets: Dict[str, str] = field(default_factory=dict)   # MOVESHEETS: move -> strip image (one row of frames)
    console: str = ""                  # console target preset key (sforge/consoles.py) -> out/<name>/console/
    dither: Optional[bool] = None      # console quantize dithering (None = preset default)
    # MULTI-VIEW (sforge/views.py)
    view_sources: Dict[str, str] = field(default_factory=dict)   # view -> image / frames folder / video
    view_list: List[str] = field(default_factory=list)           # views to output (filled if no source)
    billboard8: bool = False           # output all 8 directions (missing ones mirrored / interpolated + flagged)
    view_cut: float = 0.0              # keep the top fraction of each view's figure (0.55 = bust, for karts); 0 = full
    view_figure_h: int = 0             # px figure height in view cells (0 = figure_h)
    view_moves: List[str] = field(default_factory=list)          # moves animated per view (empty = all)
    view_frames: int = 6               # frames taken from a per-view video / folder
    view_frame_pngs: bool = True       # write views/<view>/<move>_NN.png too
    # OUTPUT PROFILE (sforge/profiles.py, profiles/*.json)
    profile: Optional[dict] = None
    profile_vars: Dict[str, str] = field(default_factory=dict)  # --set key=value (template variables)
    display_name: str = ""             # the name as typed (folder name is a slug of it)
    # LIBRARY mode (v6, sforge/librarybuild.py): a rig from the user library (FBX / GLB imported) as the template
    rig: str = ""                      # library asset name (forge.py library list) or an .fbx / .glb path
    library_dir: str = ""              # "" = <studio>/library or $SFS_LIBRARY
    clip_map: Dict[str, dict] = field(default_factory=dict)   # move -> {"clip": "LIB:CLIP", "speed", "loop", "trim": [a, b]}
    root_motion: str = "keep"          # 3D takes: keep | inplace | root   (sprites are always drawn in place)
    # v7 (sforge/matslots.py): engine material slots Skin_Mat / Jersey_Mat / Shorts_Mat / Socks_Mat (+ Trim/Hair/Shoes)
    material_split: str = "auto"       # auto = split a single-material / unnamed mesh by bone regions + heights | off = rename only
    material_slots: str = "full"       # full (4 core + Trim/Hair/Shoes) | core4 (exactly the 4 core slots) | keep (leave materials as imported)
    # v7 (sforge/human.py): MakeHuman mode - "gender=1,age=25,muscle=0.6,weight=0.5,height=0.5,proportions=0.5,skeleton=game_engine"
    human: str = ""
    # v7 (sforge/equip.py): outfits skinned to the same skeleton + props on sockets (hand_r hand_l head back hip foot)
    outfits: List[str] = field(default_factory=list)   # library outfits/<name>; "name:hide=torso+arms" overrides the hide mask
    props: List[str] = field(default_factory=list)     # "name[@socket][:ox,oy,oz[:rx,ry,rz[:scale]]]"
    slot_colors: str = ""              # "Jersey=#c8102e,Armour_Mat=#777777" - recolour material slots
    anim_export: bool = False          # v7: also write anim/character_base.glb + anim/anim_<move>.glb (+ .fbx) + anim/manifest.json

    def resolved(self):
        if not self.figure_h:
            kart = _prop(self) == "kart" and self.mode in ("spec", "mannequin")
            self.figure_h = int(self.frame_h * (0.50 if kart else 0.62))
        if not self.ground_y:
            self.ground_y = int(round(self.frame_h * 0.94))
        if not self.pivot_x:
            self.pivot_x = self.frame_w // 2
        if not self.display_name:
            self.display_name = self.name
        self.name = slug(self.name) or "character"
        return self


class Report:
    def __init__(self, log):
        self.log = log; self.rows = []; self.warn = []

    def move(self, name, source, n, note=""):
        self.rows.append((name, source, n, note))
        self.log("  %-24s %-12s %2d frames %s" % (name, source, n, note))

    def warning(self, msg):
        self.warn.append(msg); self.log("  ! " + msg)

    def note(self, msg):
        self.log("  " + msg)


def _slots(cfg):
    """mannequin GLB material naming: full / core4 slot names, or the old part names for 'keep'"""
    return {"core4": "core4", "keep": "parts"}.get(getattr(cfg, "material_slots", "full"), "full")


# ------------------------------------------------------------------ sources
def _prop(cfg):
    if cfg.prop != "auto":
        return None if cfg.prop in ("", "none") else cfg.prop
    return "kart" if any((motion_for(m) and motion_for(m).category == "Kart") for m in cfg.moves) else None


def _mannequin_frames(cfg, sp, report, only=None):
    from . import mesh, render, anim
    T, B, M = mesh.build_mannequin(sp, prop=_prop(cfg))
    cols = sp.colours()
    rs = render.RenderSettings(cfg.frame_w, cfg.frame_h, cfg.figure_h * sp.scale, cfg.ground_y, cfg.pivot_x,
                               yaw=cfg.yaw, outline=cfg.outline)
    out = {}
    for m in cfg.moves:
        if only is not None and m.name not in only:
            continue
        mo = motion_for(m)
        if mo is None:
            report.warning("no procedural motion for '%s' - set its 'motion' to an existing one" % m.name)
            continue
        frames, clip = [], False
        for st in anim.states_for(mo, m.frames, m.loop):
            im = render.render_state(T, B, M, cols, st, rs)
            a = im.getchannel("A")
            bb = a.getbbox()
            if bb and (bb[0] <= 0 or bb[1] <= 0 or bb[2] >= im.width or bb[3] >= im.height):
                clip = True
            frames.append(im)
        out[m.name] = (frames, "mannequin" if mo.name == m.name else "mannequin:" + mo.name, "clipped at cell edge" if clip else "")
    return out


def _cut(path, cfg, report):
    im = imaging.load_rgba(path)
    im = imaging.cutout(im, cfg.cutout, report.log)
    if cfg.flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im


def _target_h(cfg):
    s = (cfg.height_cm / 180.0) if cfg.height_cm else 1.0
    return cfg.figure_h * s, s


def _import_sequence(paths, cfg, report, scale=None, mode="strip"):
    figs = [_cut(p, cfg, report) for p in paths]
    th, _ = _target_h(cfg)
    if scale is None:
        hs = sorted(imaging.trim(f)[0].height for f in figs)
        scale = th / max(1, hs[len(hs) // 2])
    if mode == "feet":
        res = [imaging.place(imaging.trim(f)[0], cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, scale) for f in figs]
        return [r[0] for r in res], any(r[1] for r in res), scale
    cells, clip = imaging.place_strip(figs, cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, scale)
    return cells, clip, scale


def _source_list(src, n, report):
    """video file -> n frames via ffmpeg ; folder -> its images (n evenly spaced if more)."""
    if os.path.isdir(src):
        fs = imaging.list_images(src)
        return imaging.pick_even(fs, n) if n and len(fs) > n else fs
    return imaging.video_frames(src, n, report.log)


def _find_move_frames(folder, moves):
    """FRAMES mode: <folder>/<move>/*.png  or  <folder>/<move>_<N>.png"""
    found = {}
    by_slug = {m.name.replace("_", ""): m.name for m in moves}
    for d in sorted(os.listdir(folder)):
        p = os.path.join(folder, d)
        if os.path.isdir(p):
            k = slug(d).replace("_", "")
            if k in by_slug and imaging.list_images(p):
                found[by_slug[k]] = imaging.list_images(p)
    for f in imaging.list_images(folder):
        base = os.path.splitext(os.path.basename(f))[0]
        if "_" not in base and "-" not in base:
            continue
        mv = slug(base.rsplit("_", 1)[0] if "_" in base else base.rsplit("-", 1)[0]).replace("_", "")
        if mv in by_slug:
            found.setdefault(by_slug[mv], []).append(f)
    for k in found:
        found[k] = imaging.list_images(os.path.dirname(found[k][0])) if os.path.isdir(os.path.join(folder, k)) and False else found[k]
    return found


def _fill_missing(cfg, frames, report, sp):
    need = [m for m in cfg.moves if m.name not in frames]
    if not need:
        return
    if cfg.fill == "skip":
        for m in need:
            report.warning("skipped '%s' (no source frames)" % m.name)
        return
    if cfg.fill == "mannequin":
        got = _mannequin_frames(cfg, sp or CharacterSpec(), report, only={m.name for m in need})
        for k, (fr, src, note) in got.items():
            frames[k] = (fr, "filled:" + src, "different style - procedural mannequin")
        return
    base = None
    for key in ("idle", "fight_idle", "hold"):
        if key in frames:
            base = frames[key][0][0]; break
    if base is None and frames:
        base = next(iter(frames.values()))[0][0]
    if base is None:
        report.warning("nothing to fill from"); return
    for m in need:
        if cfg.fill == "static":
            frames[m.name] = ([base.copy() for _ in range(m.frames)], "filled:static", "copy of idle still")
        else:
            mo = motion_for(m)
            frames[m.name] = (imaging.placeholder_frames(base, m.frames, (mo.name if mo else m.name), cfg.pivot_x, cfg.ground_y),
                              "filled:placeholder", "idle pixels moved/rotated - NOT a real pose")


# ------------------------------------------------------------------ SpriteForge core bridge
SF_DIR = os.path.join(HERE, "spriteforge")


def _sf_core():
    sys.path.insert(0, os.path.join(SF_DIR, "tools"))
    import spriteforge as sfc          # spriteforge/tools/spriteforge.py (the 2D core)
    return sfc


def _sf_name(sfc, move):
    for std, al in sfc.ALIASES.items():
        if move == std or move in al:
            return std
    return None


def _spriteforge_photo(cfg, report):
    """PHOTO mode through the SpriteForge core (tools/spriteforge.py): its cut-out,
    common height, ground line and procedural fallback table (bob, legswing, legkick,
    squash, stretch, lunge, glow, hitflash ...).  Only the person's own pixels are used.
    Its 14 standard moves are re-placed 1:1 into the Studio cell; moves outside the
    standard 14 (kart / Gaelic extras) are filled from its idle by _fill_missing."""
    import tempfile, io, contextlib
    sfc = _sf_core()
    th, _ = _target_h(cfg)
    stand = max(16, int(round(th)))
    src = cfg.photo
    tmp = tempfile.mkdtemp(prefix="sfs_core_")
    if cfg.cutout in ("auto", "rembg") and not has_alpha_file(src):
        # optional AI segmentation (background removal only); SpriteForge then trims/places it
        im = imaging.load_rgba(src)
        r = imaging._rembg(im) if cfg.cutout in ("auto", "rembg") else None
        if r is not None:
            src = os.path.join(tmp, "idle.png"); r.save(src)
            report.note("cut-out: rembg (%s) -> SpriteForge core" % os.environ.get("SFS_REMBG_MODEL", "u2net"))
        else:
            report.note("cut-out: SpriteForge border-colour model (rembg not installed)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = sfc.build(cfg.name, src, os.path.join(tmp, "out"), height=stand, preview=False)
    for ln in buf.getvalue().splitlines():
        if ln.strip():
            report.note("  core: " + ln.strip())
    cw, ch, ground, origin = r["cell_w"], r["cell_h"], r["ground"], r["origin"]
    if cfg.flip:
        pass
    frames = {}
    fdir = os.path.join(tmp, "out", "frames")
    for m in cfg.moves:
        std = _sf_name(sfc, m.name)
        if std is None:
            continue
        paths = sorted(glob.glob(os.path.join(fdir, std + "_[0-9][0-9].png")))
        cells, clip = [], False
        for pth in paths:
            im = Image.open(pth).convert("RGBA")
            if cfg.flip:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            cell = Image.new("RGBA", (cfg.frame_w, cfg.frame_h), (0, 0, 0, 0))
            ox, oy = cfg.pivot_x - cw // 2, cfg.ground_y - ground
            cell.paste(im, (ox, oy))          # no mask: keep the core's alpha exactly
            if ox < 0 or oy < 0 or ox + cw > cfg.frame_w or oy + ch > cfg.frame_h:
                bb = im.getchannel("A").getbbox()
                if bb and (bb[0] + ox < 0 or bb[1] + oy < 0 or bb[2] + ox > cfg.frame_w or bb[3] + oy > cfg.frame_h):
                    clip = True
            cells.append(cell)
        if not cells:
            continue
        m.frames = len(cells)
        o = origin.get(std, "real")
        tag = "photo" if o.startswith("real") else "filled:spriteforge:" + o
        frames[m.name] = (cells, tag, ("clipped " if clip else "") + ("own pixels" if o == "real" else
                          "own pixels, SpriteForge %s" % o + ("" if o.startswith("real") else " - NOT a real pose")))
    shutil.rmtree(tmp, ignore_errors=True)
    return frames


def _lowest_solid(im, thr=40):
    import numpy as np
    a = np.asarray(im.getchannel("A"))
    rows = np.nonzero((a > thr).any(1))[0]
    return int(rows.max()) + 1 if len(rows) else None


def _shift(im, dy):
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, dy))
    return out


def _ground_lock(cfg, frames, report):
    """Feet on ONE ground line, exactly as spriteforge.h / verify_cfg.py expect:
    1) one constant shift for the whole set so the reference standing frame (idle 0)
       has its lowest solid pixel (alpha > 40, outline included) on ground_y;
    2) any single frame that still dips below the line is lifted onto it.
    Frames above the line (jumps) stay airborne."""
    ref_mv = "idle" if "idle" in frames else next(iter(frames))
    low = _lowest_solid(frames[ref_mv][0][0])
    dy = (cfg.ground_y - low) if low else 0
    lifted = 0
    for mv, (fr, src, note) in frames.items():
        new = []
        for im in fr:
            if dy:
                im = _shift(im, dy)
            lo = _lowest_solid(im)
            if lo and lo > cfg.ground_y:
                im = _shift(im, cfg.ground_y - lo); lifted += 1
            new.append(im)
        fr[:] = new
    if dy or lifted:
        report.note("ground lock: set shifted %+d px, %d frame(s) lifted onto ground_y=%d" % (dy, lifted, cfg.ground_y))


def has_alpha_file(p):
    try:
        return imaging.has_alpha(Image.open(p))
    except Exception:
        return False


VIDEO_EXT = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".gif")


def _apply_move_videos(cfg, frames, report):
    """PHOTO mode: real frames for some moves from a clip (decoded via sforge.media) or a frames folder."""
    for mv, src in cfg.videos.items():
        m = next((x for x in cfg.moves if x.name == slug(mv)), None)
        if m is None:
            m = MoveSpec(slug(mv), mv, "Imported", 8, 12, False); cfg.moves.append(m)
        how = os.path.basename(src)
        if os.path.isfile(src) and src.lower().endswith(VIDEO_EXT):
            # a real clip: same background removal as VIDEO mode (camera model, median / chroma / plate matte)
            from . import video as _v
            import tempfile
            out, rep, _dbg = _v.process_clip(src, m.name, m.frames, m.loop, _v.ClipOptions(bg="auto"), log=lambda *a: None)
            td = tempfile.mkdtemp(prefix="sfs_mv_")
            paths = []
            for k, im in enumerate(out):
                paths.append(os.path.join(td, "%s_%02d.png" % (m.name, k))); im.save(paths[-1])
            how += " (video matte: %s camera, %s background)" % (rep.get("camera", "?"), rep.get("background", "?"))
        else:
            paths = _source_list(src, m.frames, report)
        cells, clip, _ = _import_sequence(paths, cfg, report, None, "strip" if cfg.anchor in ("auto", "strip") else "feet")
        m.frames = len(cells)
        frames[m.name] = (cells, "photo-video", ("clipped " if clip else "") + how)


def collect_frames(cfg, report):
    """-> dict move -> (list[RGBA cell], source tag, note)"""
    sp = None
    frames = {}
    mode = cfg.mode.lower()
    if cfg.human:
        from . import human as HU
        hp, hsk = HU.parse_params(cfg.human)
        if HU.have_assets():
            cfg._rig_obj = HU.build(hp, hsk or "game_engine", name=cfg.name + "_human", log=report.note)
            cfg.mode = mode = "library"; cfg.rig = cfg.rig or "makehuman:" + (hsk or "game_engine")
            report.note("human: MakeHuman mode (CC0 assets, %s skeleton)" % (hsk or "game_engine"))
        else:
            sp_h = HU.fallback_spec(hp, cfg.name)
            report.warning("human: MakeHuman assets not installed (forge.py human --setup) - FALLBACK to the parametric "
                           "mannequin: height %.0f cm, %s build" % (sp_h.height_cm, sp_h.build))
            if mode not in ("spec", "mannequin"):
                cfg.mode = mode = "mannequin"
            cfg.spec = sp_h
    if mode in ("spec", "mannequin") and (cfg.outfits or cfg.props):
        # equipment needs a skinned mesh: use the mannequin as a library rig (library/rigs/sforge_mannequin)
        report.note("equip: %s mode -> library rig '%s' (outfits / props need a skinned library mesh)" % (mode, cfg.rig or "sforge_mannequin"))
        cfg.mode = mode = "library"; cfg.rig = cfg.rig or "sforge_mannequin"
    if mode in ("spec", "mannequin"):
        sp = load_spec(cfg.spec_path) if cfg.spec_path else (cfg.spec or CharacterSpec(name=cfg.name))
        if cfg.kit:
            sp.kit = cfg.kit
        frames = _mannequin_frames(cfg, sp, report)
        if cfg.extra_back_view and not any(m.name == "idle_back" for m in cfg.moves):
            pass
    elif mode == "library":
        if not cfg.rig:
            raise ValueError("LIBRARY mode needs --rig NAME (forge.py library list) or a .fbx / .glb path")
        from .librarybuild import library_frames
        frames, _ctx = library_frames(cfg, report)
    elif mode == "photo" and not cfg.legacy_photo:
        if not cfg.photo:
            raise ValueError("PHOTO mode needs --photo front.png")
        frames = _spriteforge_photo(cfg, report)
        _apply_move_videos(cfg, frames, report)     # --video MOVE=clip / folder replaces that move's placeholder
    elif mode == "photo":
        if not cfg.photo:
            raise ValueError("PHOTO mode needs --photo front.png")
        th, _ = _target_h(cfg)
        front = _cut(cfg.photo, cfg, report)
        fig, _ = imaging.trim(front)
        scale = th / fig.height
        cell, clip = imaging.place(fig, cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, scale)
        if clip:
            report.warning("front photo figure is clipped by the frame - lower figure_h or raise frame size")
        idle_spec = next((m for m in cfg.moves if m.name in ("idle", "fight_idle")), None)
        n_idle = idle_spec.frames if idle_spec else 1
        idle_frames = imaging.placeholder_frames(cell, n_idle, "idle", cfg.pivot_x, cfg.ground_y) if n_idle > 1 else [cell]
        frames["idle"] = (idle_frames, "photo", "front photo (+ subtle breathing scale)" if n_idle > 1 else "front photo")
        if cfg.back and not multiview_wanted(cfg):
            bk = _cut(cfg.back, cfg, report)
            bfig, _ = imaging.trim(bk)
            bcell, _ = imaging.place(bfig, cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, th / bfig.height)
            frames["idle_back"] = ([bcell], "photo", "back photo")
            if not any(m.name == "idle_back" for m in cfg.moves):
                cfg.moves.insert(1, MoveSpec("idle_back", "Idle (Back)", "Locomotion", 1, 1, True, "idle", "back view still"))
        _apply_move_videos(cfg, frames, report)
    elif mode == "frames":
        found = _find_move_frames(cfg.frames_dir, cfg.moves)
        if not found:
            raise ValueError("no <move>/ folders or <move>_<N>.png files matching the selected moves in " + cfg.frames_dir)
        vmeta = None
        vm_path = os.path.join(cfg.frames_dir, "video_meta.json")
        if os.path.isfile(vm_path):
            try:
                import json as _json
                vmeta = _json.load(open(vm_path))
            except Exception:
                vmeta = None
        if vmeta and vmeta.get("standing_h"):
            # frames from `forge.py video`: already normalised so a standing pose is standing_h px tall,
            # one common scale keeps crouches/jumps at their true relative size
            scale = _target_h(cfg)[0] / float(vmeta["standing_h"])
            for c in vmeta.get("clips", []):
                m = next((x for x in cfg.moves if x.name == c.get("move")), None)
                if m is not None and c.get("sprite_fps"):
                    m.fps = int(c["sprite_fps"])
            report.log("video frames: standing height %.0f px -> scale %.3f" % (vmeta["standing_h"], scale))
        else:
            ref = found.get("idle") or found.get("fight_idle") or next(iter(found.values()))
            rf = imaging.trim(_cut(ref[0], cfg, report))[0]
            scale = _target_h(cfg)[0] / rf.height
        for mv, paths in found.items():
            cells, clip, _ = _import_sequence(paths, cfg, report, scale, "feet" if cfg.anchor == "feet" else "strip")
            frames[mv] = (cells, "imported", "clipped" if clip else "")
    elif mode == "movesheets":
        if not cfg.move_sheets:
            raise ValueError("Per-move sheets mode needs at least one move=strip.png")
        ref_scale = None
        order = sorted(cfg.move_sheets.items(), key=lambda kv: 0 if slug(kv[0]) in ("idle", "fight_idle") else 1)
        for mv, path in order:
            m = next((x for x in cfg.moves if x.name == slug(mv)), None)
            if m is None:
                m = MoveSpec(slug(mv), mv, "Imported", 8, 12, False); cfg.moves.append(m)
            strip = imaging.cutout(imaging.load_rgba(path), cfg.cutout, report.log)
            if cfg.grid_cols > 0:     # explicit frame count across
                cells = imaging.split_sheet(strip, 1, cfg.grid_cols)[0]
            else:
                rows = imaging.split_sheet(strip, 0, 0)
                cells = [c for r in rows for c in r]
            if not cells:
                report.warning("no frames found in %s" % path); continue
            if cfg.flip:
                cells = [c.transpose(Image.FLIP_LEFT_RIGHT) for c in cells]
            if ref_scale is None:
                ref_scale = _target_h(cfg)[0] / max(1, imaging.trim(cells[0])[0].height)
            if cfg.anchor == "feet":
                res = [imaging.place(imaging.trim(c)[0], cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, ref_scale) for c in cells]
                out_c, clip = [r[0] for r in res], any(r[1] for r in res)
            else:
                out_c, clip = imaging.place_strip(cells, cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, ref_scale)
            m.frames = len(out_c)
            frames[m.name] = (out_c, "move-sheet", ("clipped " if clip else "") + os.path.basename(path))
    elif mode == "sheet":
        sheet = imaging.load_rgba(cfg.sheet)
        sheet = imaging.cutout(sheet, cfg.cutout, report.log)
        rows = imaging.split_sheet(sheet, cfg.grid_rows, cfg.grid_cols)
        if cfg.sheet_layout == "cells":
            cells_flat = [c for r in rows for c in r]
            groups = [[c] for c in cells_flat]
        else:
            groups = [r for r in rows if r]
        if cfg.flip:
            groups = [[c.transpose(Image.FLIP_LEFT_RIGHT) for c in g] for g in groups]
        th = _target_h(cfg)[0]
        ref = imaging.trim(groups[0][0])[0] if groups else None
        scale = th / ref.height if ref else 1.0
        uniform = cfg.grid_rows > 0 and cfg.grid_cols > 0
        for m, g in zip(cfg.moves, groups):
            if cfg.anchor == "feet" or (cfg.anchor == "auto" and not uniform):
                res = [imaging.place(imaging.trim(c)[0], cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, scale) for c in g]
                cells, clip = [r[0] for r in res], any(r[1] for r in res)
            else:
                cells, clip = imaging.place_strip(g, cfg.frame_w, cfg.frame_h, cfg.pivot_x, cfg.ground_y, scale)
            frames[m.name] = (cells, "sheet", "clipped" if clip else "")
        if len(groups) < len(cfg.moves):
            report.log("  sheet had %d groups for %d selected moves" % (len(groups), len(cfg.moves)))
    else:
        raise ValueError("unknown mode " + cfg.mode)
    if mode not in ("spec", "mannequin", "library"):
        _fill_missing(cfg, frames, report, sp)
    return frames, sp


# ------------------------------------------------------------------ multi-view
def multiview_wanted(cfg):
    return bool(cfg.view_sources or cfg.view_list or cfg.billboard8)


def _view_sources(cfg):
    srcs = dict(cfg.view_sources)
    if cfg.mode == "photo" and cfg.photo:
        srcs.setdefault("front", cfg.photo)
    if cfg.back:
        srcs.setdefault("back", cfg.back)
    return srcs


def collect_views(cfg, report, sp, frames):
    """-> [(view, {move: [cells]}, source)] in angle order, plus {view: {move: tag}}.
    Every view uses the main set's move list and frame counts (same rows as atlas.png)."""
    from . import views as V
    srcs = _view_sources(cfg)
    wanted = list(V.BILLBOARD8) if cfg.billboard8 else list(cfg.view_list)
    for v in srcs:
        if v not in wanted:
            wanted.append(v)
    if not wanted:
        wanted = ["front", "right", "back", "left"]
    wanted = sorted(set(wanted), key=lambda n: V.ANGLE[n])
    th = cfg.view_figure_h or cfg.figure_h
    moves = [m for m in cfg.moves if m.name in frames]
    animate = set(cfg.view_moves) if cfg.view_moves else {m.name for m in moves}
    per_tag = {}
    result = []
    libctx = getattr(cfg, "_libctx", None) if cfg.mode == "library" else None
    if (cfg.mode in ("spec", "mannequin") and sp is not None) or libctx is not None:
        from . import mesh, render, anim
        if libctx is None:
            T, B, M = mesh.build_mannequin(sp, prop=_prop(cfg))
            cols = sp.colours()
        raw_fig = th / (cfg.view_cut if cfg.view_cut else 1.0) * 1.25
        H2 = int(raw_fig * 1.5); W2 = int(max(raw_fig * 1.3, cfg.frame_w * 1.5))
        rs_base = dict(cell_w=W2, cell_h=H2, figure_h=raw_fig * (sp.scale if sp is not None else 1.0), baseline=int(H2 * 0.85), anchor_x=W2 // 2,
                       outline=cfg.outline, ss=1)
        raw = {}
        for v in wanted:
            rs = render.RenderSettings(yaw=float(V.ANGLE[v]), **rs_base)
            raw[v] = {}
            for m in moves:
                mo = motion_for(m)
                n = len(frames[m.name][0])
                if libctx is not None:
                    if m.name in libctx.clips:
                        raw[v][m.name] = libctx.frames_for(m, n, rs, animate=m.name in animate)
                    continue
                if mo is None:
                    continue
                sts = list(anim.states_for(mo, n, m.loop)) if m.name in animate else list(anim.states_for(mo, n, m.loop))[:1]
                raw[v][m.name] = [render.render_state(T, B, M, cols, st, rs) for st in sts]
        ref_v = "front" if "front" in raw else wanted[0]
        ref_m = next((m.name for m in moves if m.name in raw[ref_v]), None)
        mref = V.measure(raw[ref_v][ref_m][0], cfg.view_cut)
        mref["ax"] = W2 / 2
        s = th / mref["h"]; widest = ref_v
        for v in wanted:     # width fit over every view's first frame
            mm = V.measure(raw[v][ref_m][0], cfg.view_cut)
            if mm:
                b = V._bbox(raw[v][ref_m][0].crop((0, mref["top"], W2, mref["line"]))) or (0, 0, 1, 1)
                w = 2 * max(W2 / 2 - b[0], b[2] - W2 / 2)
                if w * s > cfg.frame_w * 0.98:
                    s = cfg.frame_w * 0.98 / w; widest = v
        if s < 0.85 * th / mref["h"]:
            report.note("views: the widest view (%s, pose of '%s') does not fit %dpx wide, so every view is drawn at %d%% of "
                        "the figure height to stay inside the frame and on the same scale (wider frame or a pose with the "
                        "arms in = bigger figure)" % (widest, ref_m, cfg.frame_w, round(100 * s * mref["h"] / th)))
        for v in wanted:
            mv = {}
            for m in moves:
                fr = raw[v].get(m.name)
                n = len(frames[m.name][0])
                if not fr:
                    continue
                cells = [V.apply(im, mref, s, cfg) for im in fr]
                tag = "render" if len(cells) == n else "static"
                if len(cells) < n:
                    cells = [cells[i % len(cells)] for i in range(n)]
                mv[m.name] = cells
                per_tag.setdefault(v, {})[m.name] = tag
            result.append((v, mv, "real (rendered at yaw %d)" % V.ANGLE[v]))
        report.note("views: %d rendered for real (%s)%s" % (len(wanted), ", ".join(wanted), ", bust cut %.2f" % cfg.view_cut if cfg.view_cut else ""))
        return result, per_tag
    # photo / imported views: cut-out, measure, common height, one scale per view
    loaded = {}
    for v, src in srcs.items():
        if os.path.isdir(src) or os.path.splitext(src)[1].lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif"):
            paths = _source_list(src, cfg.view_frames, report)
        else:
            paths = [src]
        if not paths:
            report.warning("view %s: no frames in %s" % (v, src)); continue
        raws = [_cut(pth, cfg, report) for pth in paths]
        m = V.measure(raws[0], cfg.view_cut)
        if not m:
            report.warning("view %s: empty cut-out (%s)" % (v, src)); continue
        loaded[v] = (raws, m, th / m["h"], src)
    if not loaded and not frames:
        raise ValueError("multi-view: no view sources")
    k = 1.0
    for v, (raws, m, sv, src) in loaded.items():
        if m["w"] * sv * k > cfg.frame_w * 0.98:
            k = cfg.frame_w * 0.98 / (m["w"] * sv)
    if k < 1.0:
        report.note("views: all views scaled x%.3f so the widest one fits the %d px frame" % (k, cfg.frame_w))
    have = {}
    for v, (raws, m, sv, src) in loaded.items():
        have[v] = [V.apply(im, m, sv * k, cfg) for im in raws]
        report.note("view %-11s %-4d real: %s%s" % (v, V.ANGLE[v], os.path.basename(src), " (%d frames)" % len(raws) if len(raws) > 1 else ""))
    filled = V.fill_views(have, wanted, cfg.pivot_x)
    for v in wanted:
        if v not in filled:
            continue
        cells, src = filled[v]
        if src != "real":
            report.warning("view %s has no source: %s" % (v, src.replace("filled:", "FILLED ").replace("mirrored:", "MIRRORED from ")))
        still = cells[0]
        mv = {}
        for m in moves:
            n = len(frames[m.name][0])
            mo = motion_for(m)
            if m.name in ("idle", "fight_idle", "kart_idle") and len(cells) > 1:
                mv[m.name] = [cells[int(i * len(cells) / n) % len(cells)] for i in range(n)]
                tag = "video"
            elif m.name in animate and n > 1:
                mv[m.name] = imaging.placeholder_frames(still, n, (mo.name if mo else m.name), cfg.pivot_x, cfg.ground_y)
                tag = "placeholder"
            else:
                mv[m.name] = [still.copy() for _ in range(n)]
                tag = "static"
            per_tag.setdefault(v, {})[m.name] = tag
        result.append((v, mv, src))
    return result, per_tag


def write_views(cfg, out, view_sets, per_tag, ordered, report):
    from . import views as V
    vdir = os.path.join(out, "views")
    if os.path.isdir(vdir):
        shutil.rmtree(vdir)
    os.makedirs(vdir)
    info = {}
    names = [mv for mv, _ in ordered]
    for v, mv, src in view_sets:
        if cfg.view_frame_pngs:
            os.makedirs(os.path.join(vdir, v))
            for m, fr in mv.items():
                for i, im in enumerate(fr):
                    im.save(os.path.join(vdir, v, "%s_%02d.png" % (m, i)))
        vord = [(m, mv[m]) for m in names if m in mv]
        pages, cols, placed = pack_atlas(cfg, vord)
        pn = ["views/atlas_%s.png" % v] + ["views/atlas_%s_%d.png" % (v, i) for i in range(1, len(pages))]
        for im, nm in zip(pages, pn):
            im.save(os.path.join(out, nm), optimize=True)
        info[v] = {"angle": V.ANGLE[v], "source": src, "images": pn, "filled": not src.startswith("real"),
                   "moves": {m: per_tag.get(v, {}).get(m, "") for m in mv},
                   "rows": {m: row for m, page, row, n in placed}, "pages": {m: page for m, page, row, n in placed}}
    labels = {m.name: (m.label or m.name) for m in cfg.moves}
    grid, pv = V.turnaround(view_sets, names, cfg.frame_w, cfg.frame_h, labels)
    grid.save(os.path.join(out, "turnaround.png"), optimize=True)
    pv.save(os.path.join(out, "turnaround_preview.png"), optimize=True)
    files = ["turnaround.png", "turnaround_preview.png"]
    if cfg.billboard8 or len(view_sets) == 8:
        ref = next((m for m in ("idle", "kart_idle", "fight_idle") if m in names), names[0])
        V.billboard_strip(view_sets, cfg.frame_w, cfg.frame_h, ref).save(os.path.join(out, "billboard8.png"), optimize=True)
        files.append("billboard8.png")
    report.note("views: %s -> views/, %s" % (", ".join("%s%s" % (v, "" if not i["filled"] else "*") for v, i in info.items()), ", ".join(files)))
    return info, files


# ------------------------------------------------------------------ writers
def pack_atlas(cfg, ordered):
    """SpriteForge 'combined' layout: ONE ROW PER MOVE (frame i of a move at
    x = i*frame_w, y = row*frame_h), so sprites.cfg 'move' lines can point straight at
    the atlas.  A new page (atlas_1.png ...) starts when a page would exceed max_atlas.
    Returns images, columns (max frames), placed [(move, page, row, count)]."""
    fw, fh = cfg.frame_w, cfg.frame_h
    cols = max(len(f) for _, f in ordered)
    if cols * fw > cfg.max_atlas:
        raise ValueError("a move has %d frames: %d px wide > max_atlas %d - lower frames or frame size" % (cols, cols * fw, cfg.max_atlas))
    max_rows = max(1, cfg.max_atlas // fh)
    pages, placed = [[]], []
    for mv, fr in ordered:
        if len(pages[-1]) >= max_rows:
            pages.append([])
        placed.append((mv, len(pages) - 1, len(pages[-1]), len(fr)))
        pages[-1].append(fr)
    images = []
    for p in pages:
        w = max(len(fr) for fr in p) * fw
        atlas = Image.new("RGBA", (w, len(p) * fh), (0, 0, 0, 0))
        for r, fr in enumerate(p):
            for i, im in enumerate(fr):
                atlas.paste(im, (i * fw, r * fh))
        images.append(atlas)
    return images, cols, placed


def _font(size):
    for f in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass
    return ImageFont.load_default()


def checker(w, h, s=12, c1=(236, 236, 236), c2=(208, 208, 208)):
    im = Image.new("RGB", (w, h), c1); d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range((y // s % 2) * s, w, 2 * s):
            d.rectangle([x, y, x + s - 1, y + s - 1], fill=c2)
    return im


def contact_sheet(ordered, labels, fw, fh, title="", cols=9, thumb=150, pick="key"):
    cols = min(cols, max(1, len(ordered)))
    rows = int(math.ceil(len(ordered) / cols))
    th = int(thumb * fh / fw)
    lab_h = 26; pad = 6; top = 44 if title else 6
    W = cols * (thumb + pad) + pad; H = top + rows * (th + lab_h + pad) + pad
    sheet = Image.new("RGB", (W, H), (24, 30, 38)); d = ImageDraw.Draw(sheet)
    if title:
        d.text((pad + 4, 10), title, fill=(255, 255, 255), font=_font(20))
    f = _font(13)
    for i, (mv, fr) in enumerate(ordered):
        x = pad + (i % cols) * (thumb + pad); y = top + (i // cols) * (th + lab_h + pad)
        bg = checker(thumb, th, 8)
        k = fr[min(len(fr) - 1, len(fr) // 2)] if pick == "key" else fr[0]
        t = k.resize((thumb, th), Image.LANCZOS)
        bg.paste(t, (0, 0), t)
        sheet.paste(bg, (x, y))
        d.rectangle([x, y + th, x + thumb - 1, y + th + lab_h - 2], fill=(245, 245, 245))
        txt = labels.get(mv, mv)
        tw = d.textlength(txt, font=f)
        d.text((x + (thumb - tw) / 2, y + th + 5), txt, fill=(20, 20, 20), font=f)
    return sheet


def find_blender(hint=""):
    cands = [hint, os.environ.get("BLENDER", ""), shutil.which("blender") or "", shutil.which("blender.exe") or ""]
    if os.name == "nt":
        import glob
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            cands += sorted(glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
        cands += sorted(glob.glob(r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"))
    for c in cands:
        if c and os.path.isfile(c):
            return [c, "-b", "-P"]
    try:
        import importlib.util
        if importlib.util.find_spec("bpy") is not None:
            return [sys.executable]
    except Exception:
        pass
    vpy = os.environ.get("SFS_BPY_PYTHON", "")
    if vpy and os.path.isfile(vpy):
        return [vpy]
    return None


def export_fbx(glb, fbx, blender_hint, log):
    """FBX 7.4 binary.  Default: the built-in pure-Python writer (sforge/fbx.py, no Blender).
    SFS_FBX_WRITER=blender (or forge.py build --fbx-writer blender) uses Blender's exporter instead."""
    if os.path.isfile(fbx):
        os.remove(fbx)
    if os.environ.get("SFS_FBX_WRITER", "builtin").lower() != "blender":
        from . import fbx as F
        try:
            st = F.write_fbx_from_glb(glb, fbx)
        except Exception as e:      # never lose the build over the FBX
            log("  FBX FAILED (built-in writer): %s" % e)
            return False
        log("  FBX written by the built-in writer: %d bones, %d skin clusters, %d takes, %.0f KB"
            % (st["bones"], st["clusters"], len(st["takes"]), os.path.getsize(fbx) / 1024))
        return True
    cmd = find_blender(blender_hint)
    if not cmd:
        log("  Blender not found for --fbx-writer blender - using the built-in writer")
        os.environ["SFS_FBX_WRITER"] = "builtin"
        return export_fbx(glb, fbx, blender_hint, log)
    script = os.path.join(HERE, "tools", "blender_glb_to_fbx.py")
    args = cmd + [script] + (["--"] if len(cmd) > 1 else []) + [glb, fbx]
    r = subprocess.run(args, capture_output=True, text=True)
    ok = os.path.isfile(fbx) and "SFS wrote" in (r.stdout or "")
    log("  FBX %s via %s" % ("written" if ok else "FAILED", os.path.basename(cmd[0])))
    if not ok:
        log((r.stdout or "")[-800:] + (r.stderr or "")[-800:])
    return ok


def build(cfg: BuildConfig, log=print, progress=None):
    t0 = time.time()
    cfg.resolved()
    cfg.moves = [m for m in cfg.moves if m.enabled]
    for mf in cfg.mocap_files:
        from . import mocap as _mc
        log("mocap motion '%s' loaded from %s" % (_mc.register(mf), mf))
    report = Report(log)
    out = os.path.join(cfg.out_root, cfg.name)
    os.makedirs(os.path.join(out, "moves"), exist_ok=True)
    for old in os.listdir(os.path.join(out, "moves")):
        if old.endswith(".png"):
            os.remove(os.path.join(out, "moves", old))
    log("Sprite Forge Studio %s - building '%s' (%s mode, %d moves) -> %s" % (__version__, cfg.name, cfg.mode, len(cfg.moves), out))
    frames, sp = collect_frames(cfg, report)
    _ground_lock(cfg, frames, report)
    labels = {m.name: (m.label or m.name) for m in cfg.moves}
    ordered = [(m.name, frames[m.name][0]) for m in cfg.moves if m.name in frames]
    for m in cfg.moves:
        if m.name in frames:
            fr, src, note = frames[m.name]
            report.move(m.name, src, len(fr), note)
    if progress:
        progress(0.6)
    # per-move frames
    for mv, fr in ordered:
        for i, im in enumerate(fr):
            im.save(os.path.join(out, "moves", "%s_%02d.png" % (mv, i)), optimize=True)
    if cfg.strips:
        os.makedirs(os.path.join(out, "strips"), exist_ok=True)
        for mv, fr in ordered:
            s = Image.new("RGBA", (cfg.frame_w * len(fr), cfg.frame_h), (0, 0, 0, 0))
            for i, im in enumerate(fr):
                s.paste(im, (i * cfg.frame_w, 0))
            s.save(os.path.join(out, "strips", mv + ".png"), optimize=True)
    pages, cols, placed = pack_atlas(cfg, ordered)
    page_names = ["atlas.png"] + ["atlas_%d.png" % i for i in range(1, len(pages))]
    for f in os.listdir(out):
        if f.startswith("atlas") and f.endswith(".png"):
            os.remove(os.path.join(out, f))
    for im, nm in zip(pages, page_names):
        im.save(os.path.join(out, nm), optimize=True)
    if len(pages) > 1:
        report.warning("atlas split into %d pages (max %d px) - see 'page' in atlas.json / sprites.cfg" % (len(pages), cfg.max_atlas))
    spec_by = {m.name: m for m in cfg.moves}
    view_info, view_files = {}, []
    if multiview_wanted(cfg):
        vsets, vtags = collect_views(cfg, report, sp, frames)
        view_info, view_files = write_views(cfg, out, vsets, vtags, ordered, report)
    elif os.path.isdir(os.path.join(out, "views")):
        shutil.rmtree(os.path.join(out, "views"))
        for f in ("turnaround.png", "turnaround_preview.png", "billboard8.png"):
            if os.path.isfile(os.path.join(out, f)):
                os.remove(os.path.join(out, f))
    if progress:
        progress(0.7)
    libctx = getattr(cfg, "_libctx", None) if cfg.mode == "library" else None
    if libctx is not None:
        scale = libctx.rig.height() * libctx.scale / 1.80
    else:
        scale = (sp.scale if sp else ((cfg.height_cm / 180.0) if cfg.height_cm else 1.0))
    px_per_m = cfg.figure_h / 1.80
    # atlas.json
    js = {"meta": {"app": "Sprite Forge Studio", "version": __version__, "name": cfg.name, "mode": cfg.mode,
                   "image": page_names[0], "images": page_names,
                   "size": [{"w": p.width, "h": p.height} for p in pages], "format": "RGBA8888",
                   "frame_w": cfg.frame_w, "frame_h": cfg.frame_h, "columns": cols, "layout": "one row per move",
                   "pivot": {"x": cfg.pivot_x, "y": cfg.ground_y}, "pivot_norm": {"x": round(cfg.pivot_x / cfg.frame_w, 5), "y": round(cfg.ground_y / cfg.frame_h, 5)},
                   "ground_y": cfg.ground_y, "facing": "right", "scale": round(scale, 4), "px_per_metre": round(px_per_m * scale, 3),
                   "coords": "pixels, origin top-left, y down"},
          "frames": {}, "animations": {}}
    for mv, page, row, n in placed:
        m = spec_by[mv]
        names = []
        for i in range(n):
            fname = "%s_%02d" % (mv, i)
            names.append(fname)
            js["frames"][fname] = {"frame": {"x": i * cfg.frame_w, "y": row * cfg.frame_h, "w": cfg.frame_w, "h": cfg.frame_h},
                                   "page": page, "rotated": False, "trimmed": False,
                                   "spriteSourceSize": {"x": 0, "y": 0, "w": cfg.frame_w, "h": cfg.frame_h},
                                   "sourceSize": {"w": cfg.frame_w, "h": cfg.frame_h},
                                   "pivot": js["meta"]["pivot_norm"], "duration": int(round(1000 / max(1, m.fps)))}
        js["animations"][mv] = {"label": m.label or mv, "category": m.category, "frames": names, "fps": m.fps, "loop": bool(m.loop),
                                "page": page, "image": page_names[page], "row": row, "count": n, "source": frames[mv][1]}
    if view_info:
        js["meta"]["views"] = list(view_info)
        js["meta"]["view_layout"] = "views/atlas_<view>.png has the same rows/columns as atlas.png; view angle = camera yaw (0 front, 90 = facing image-right, 180 back)"
        js["views"] = view_info
    with open(os.path.join(out, "atlas.json"), "w") as f:
        json.dump(js, f, indent=1)
    # sprites.cfg - SpriteForge v1 format (spriteforge/include/spriteforge.h, tools/verify_cfg.py)
    stand_px = int(round(cfg.figure_h * scale))
    L = ["# sprites.cfg - Sprite Forge Studio %s (SpriteForge v1 format, read by spriteforge.h)" % __version__,
         "# move <name> <file> <frames> <frame_w> <frame_h> <fps> <loop> <row>",
         "#   frame i of a move = rect (i*frame_w, row*frame_h, frame_w, frame_h) in <file>",
         "#   feet of every frame on y = ground; body centre x = anchor_x; sprites face RIGHT",
         "version 1", "name %s" % cfg.name, "frame %d %d" % (cfg.frame_w, cfg.frame_h),
         "height %d" % stand_px, "ground %d" % cfg.ground_y, "anchor_x %d" % cfg.pivot_x]
    for mv, page, row, n in placed:
        L.append("move %s %s %d %d %d %g %d %d   # %s" % (mv, page_names[page], n, cfg.frame_w, cfg.frame_h, spec_by[mv].fps,
                                                       1 if spec_by[mv].loop else 0, row, frames[mv][1]))
    if view_info:
        L.append("# view <name> <angle> <file> <source>   (same move rows as above; real | mirrored:<view> | filled:...)")
        for v, i in view_info.items():
            L.append("view %s %d %s %s" % (v, i["angle"], i["images"][0], i["source"].split(" ")[0]))
    with open(os.path.join(out, "sprites.cfg"), "w", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    # character.ini
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini["character"] = {"name": cfg.name, "frame_w": str(cfg.frame_w), "frame_h": str(cfg.frame_h), "ground_y": str(cfg.ground_y),
                        "pivot_x": str(cfg.pivot_x), "scale": "%.4f" % scale, "px_per_metre": "%.3f" % (px_per_m * scale),
                        "facing": "right", "mode": cfg.mode, "height_px": str(stand_px), "atlas": page_names[0], "pages": str(len(pages)), "columns": str(cols),
                        "moves": ",".join(mv for mv, *_ in placed)}
    ini["moves"] = {mv: "%d,%d,%s,%s" % (n, spec_by[mv].fps, "loop" if spec_by[mv].loop else "once", frames[mv][1]) for mv, _, _, n in placed}
    if sp is not None:
        d = sp.to_dict(); extra = d.pop("extra", {})
        ini["spec"] = {k: str(v) for k, v in d.items()}
        if extra:
            ini["spec_extra"] = {k: str(v) for k, v in extra.items()}
    src = {k: v for k, v in {"photo": cfg.photo, "back": cfg.back, "frames_dir": cfg.frames_dir, "sheet": cfg.sheet,
                             "spec_file": cfg.spec_path, "cutout": cfg.cutout, "fill": cfg.fill, "console": cfg.console,
                             "rig": cfg.rig, "rig_kit": cfg.kit if cfg.mode == "library" else "",
                             "root_motion": cfg.root_motion if cfg.mode == "library" else ""}.items() if v}
    src.update({"sheet_" + k: v for k, v in cfg.move_sheets.items()})
    src.update({"video_" + k: v for k, v in cfg.videos.items()})
    src.update({"view_" + k: v for k, v in cfg.view_sources.items()})
    if view_info:
        ini["character"]["views"] = ",".join(view_info)
        ini["views"] = {v: "%d,%s,%s" % (i["angle"], i["images"][0], i["source"]) for v, i in view_info.items()}
    ini["source"] = src
    with open(os.path.join(out, "character.ini"), "w") as f:
        f.write("; character.ini - Sprite Forge Studio. scale = height relative to the 180 cm reference figure\n")
        ini.write(f, space_around_delimiters=False)
    # preview
    cs = contact_sheet(ordered, labels, cfg.frame_w, cfg.frame_h, title="%s - %d moves (%s mode)" % (cfg.name, len(ordered), cfg.mode))
    cs.save(os.path.join(out, "preview.png"), optimize=True)
    if cfg.gifs:
        os.makedirs(os.path.join(out, "previews"), exist_ok=True)
        for mv, fr in ordered:
            bgc = (48, 58, 70)
            gf = []
            for im in fr:
                b = Image.new("RGB", im.size, bgc); b.paste(im, (0, 0), im); gf.append(b)
            gf[0].save(os.path.join(out, "previews", mv + ".gif"), save_all=True, append_images=gf[1:],
                       duration=int(1000 / max(1, spec_by[mv].fps)), loop=0)
    if progress:
        progress(0.8)
    # 3D
    model_note = ""
    lib_rig_clips = None
    if cfg.mode in ("spec", "mannequin") and (cfg.glb or cfg.fbx):
        from . import mesh, gltf
        T, B, M = mesh.build_mannequin(sp, prop=_prop(cfg))
        clips = []
        for m in cfg.moves:
            mo = motion_for(m)
            if mo is not None:
                clips.append((m.name, mo, m.frames, m.fps, m.loop))
        glb = os.path.join(out, "model.glb")
        gltf.write_glb(glb, T, B, M, sp.colours(), clips, scale=sp.scale, name=cfg.name, slots=_slots(cfg),
                       extras={"spec": {k: str(v) for k, v in sp.to_dict().items()}})
        log("  model.glb written (%d animation clips, %.0f KB)" % (len(clips), os.path.getsize(glb) / 1024))
        model_note = "model.glb"
        if cfg.fbx:
            if export_fbx(glb, os.path.join(out, "model.fbx"), cfg.blender, log):
                model_note += " + model.fbx"
        for kit in cfg.kits:
            import copy
            sk = copy.deepcopy(sp); sk.kit = kit
            sk.top_colour = sk.bottom_colour = sk.socks_colour = sk.trim_colour = ""
            kg = os.path.join(out, "model_%s.glb" % kit)
            gltf.write_glb(kg, T, B, M, sk.colours(), clips, scale=sp.scale, name=cfg.name + "_" + kit, slots=_slots(cfg))
            model_note += " + model_%s.glb" % kit
            if cfg.fbx and export_fbx(kg, kg[:-4] + ".fbx", cfg.blender, log):
                model_note += "/.fbx"
        log("  3D: " + model_note)
    elif libctx is not None and (cfg.glb or cfg.fbx):
        from .librarybuild import write_models
        model_note, lib_rig_clips = write_models(cfg, libctx, out, log, export_fbx)
        log("  3D: " + model_note)
    elif cfg.glb or cfg.fbx:
        log("  3D model: not generated in %s mode (a 3D model is only built from a SPEC; photos are never turned into 3D)" % cfg.mode)
    if cfg.anim_export and (cfg.mode in ("spec", "mannequin") or libctx is not None):
        from . import animexport as AX
        try:
            am = AX.from_build(cfg, out, log, sp=sp if cfg.mode in ("spec", "mannequin") else None,
                               rig_clips=lib_rig_clips if libctx is not None and (cfg.glb or cfg.fbx) else None, libctx=libctx)
            model_note = (model_note + " + " if model_note else "") + "anim/ (%d files)" % (len(am["moves"]) + 1)
        except Exception as e:
            report.warn.append("anim-export: %s" % e); log("  ! anim-export failed: %s" % e)
    # console target
    console_note = ""
    cdir = os.path.join(out, "console")
    if cfg.console:
        from . import consoles
        key = consoles.by_label(cfg.console)
        if not key:
            raise ValueError("unknown console preset '%s' (see: forge.py list)" % cfg.console)
        model_fn = None
        if cfg.mode in ("spec", "mannequin") and (cfg.glb or cfg.fbx) and sp is not None:
            def model_fn(max_tris, cd, _sp=sp):
                from . import mesh, gltf
                T2, B2, M2, det = mesh.build_mannequin_budget(_sp, prop=_prop(cfg), max_tris=max_tris)
                clips2 = [(m.name, motion_for(m), m.frames, m.fps, m.loop) for m in cfg.moves if motion_for(m) is not None]
                g = os.path.join(cd, "model_%s.glb" % key)
                gltf.write_glb(g, T2, B2, M2, _sp.colours(), clips2, scale=_sp.scale, name=cfg.name, slots=_slots(cfg),
                               extras={"console": key, "tris": int(len(T2)), "detail": det})
                files = [os.path.basename(g)]
                if cfg.fbx and export_fbx(g, g[:-4] + ".fbx", cfg.blender, log):
                    files.append(os.path.basename(g[:-4] + ".fbx"))
                log("  console model: %d tris (detail x%.2f, budget %s) -> %s" % (len(T2), det, max_tris, ", ".join(files)))
                return {"tris": int(len(T2)), "detail": det, "budget": max_tris, "files": files}
        if libctx is not None and (cfg.glb or cfg.fbx):
            from .librarybuild import console_model_fn
            model_fn = console_model_fn(cfg, libctx, lib_rig_clips, key, log, export_fbx)
        cst = consoles.export(out, cfg.name, ordered, spec_by, key, cfg.ground_y, cfg.pivot_x, cfg.dither, log, model_fn)
        console_note = "%s -> console/ (%dx%d)" % (key, cst["frame_w"], cst["frame_h"])
        for w in cst.get("warnings", []):
            report.warn.append("console: " + w)
    elif os.path.isdir(cdir) and os.path.isfile(os.path.join(cdir, "console.json")):
        shutil.rmtree(cdir)       # stale export from an earlier build
    # output profile (declarative manifests / images)
    profile_note = ""
    if cfg.profile:
        from . import profiles
        ctx = profiles.context(cfg, out, ordered, placed, page_names, spec_by, frames, view_info, scale, px_per_m, stand_px, cols)
        written = profiles.emit(cfg.profile, ctx, out, log)
        profile_note = "%s -> %s" % (cfg.profile.get("name", "?"), ", ".join(written))
    # report
    with open(os.path.join(out, "build_report.txt"), "w") as f:
        f.write("Sprite Forge Studio %s build report - %s\nmode: %s\n\n" % (__version__, cfg.name, cfg.mode))
        f.write("%-24s %-22s %6s  %s\n" % ("move", "source", "frames", "note"))
        for r in report.rows:
            f.write("%-24s %-22s %6d  %s\n" % r)
        filled = [r[0] for r in report.rows if r[1].startswith("filled")]
        f.write("\nFILLED moves (no source frames were given - placeholders): %s\n" % (", ".join(filled) or "none"))
        for w in report.warn:
            f.write("WARNING: %s\n" % w)
        eparts = getattr(libctx, "equip_parts", None) if libctx is not None else None
        if libctx is not None and getattr(libctx, "licence", None):
            lc = libctx.licence
            f.write("rig licence: %s - %s (redistribution: %s)%s\n" % (cfg.rig, lc.get("spdx") or "not filled in", lc.get("redistribution", "unknown"),
                    ("  attribution: " + lc["attribution"]) if lc.get("attribution") else ""))
        for p in eparts or []:
            lc = p.get("licence") or {}
            f.write("equip %s: %s @%s  slot %s  faces %s  hides %s  licence %s (redistribution: %s)%s\n" % (
                p["kind"], p["name"], p.get("socket", "skinned"), p.get("slot") or "own materials", p.get("faces", "?"),
                "+".join(p.get("hide") or []) or "-", lc.get("spdx") or "not filled in", lc.get("redistribution", "unknown"),
                ("  attribution: " + lc["attribution"]) if lc.get("attribution") else ""))
        f.write("3D: %s\n" % (model_note or "none"))
        f.write("console: %s\n" % (console_note or "none"))
        f.write("views: %s\n" % (", ".join("%s=%s" % (v, i["source"]) for v, i in view_info.items()) or "none"))
        f.write("profile: %s\n" % (profile_note or "none"))
    filled = [r[0] for r in report.rows if r[1].startswith("filled")]
    if filled:
        log("  NOTE: %d moves were FILLED (placeholders, not real poses): %s" % (len(filled), ", ".join(filled)))
    log("Done in %.1fs -> %s" % (time.time() - t0, os.path.abspath(out)))
    if progress:
        progress(1.0)
    return {"out": out, "frames": frames, "ordered": ordered, "report": report, "pages": page_names, "filled": filled,
            "views": view_info, "view_files": view_files}
