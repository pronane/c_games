"""LIBRARY mode (v6): render sprites / views / console art / 3D from a rig in the user library.

Same cut-out / anchor pipeline as the mannequin: every frame is drawn with render.RenderSettings
(feet on ground_y, body centre on pivot_x, 180 cm = figure_h px), so a 1.1 m chibi rig is drawn smaller
than a 2.0 m rig unless --height-cm is given.

Which clip plays for each move (first match wins):
  1. the explicit clip map (--clip MOVE=LIB:CLIP[@speed=1.2,trim=0.1-0.8,loop|once], --clip-map file.json,
     profile "clip_map" / a profile move {"name": ..., "clip": ...}, or the GUI per-move table)
  2. a mocap motion for that move (--mocap mocap/<move>.json), retargeted to the rig
  3. a clip with the move's name (or its motion's name) inside the rig itself
  4. a clip with that name in any other library rig / animation file, retargeted
  5. the built-in procedural motion for the move, retargeted from the mannequin
  6. the rig's rest pose (static) - reported as FILLED
Clip-map JSON: {"kick": {"clip": "sample_moves:hop", "speed": 1.0, "loop": false, "trim": [0.0, 0.6]},
               "idle": "breathing"}            (a bare string = a clip of the rig itself, or LIB:CLIP)
"""
from __future__ import annotations
import json
import os
import re

import numpy as np

from .moves import motion_for

_CACHE = {}


def parse_clip_arg(s):
    """'MOVE=LIB:CLIP@speed=1.2,trim=0.1-0.8,loop' -> (move, entry)"""
    mv, _, rhs = s.partition("=")
    if not rhs:
        raise ValueError("--clip needs MOVE=CLIP or MOVE=LIB:CLIP (got %r)" % s)
    clip, _, opts = rhs.partition("@")
    e = {"clip": clip.strip()}
    for o in filter(None, (x.strip() for x in opts.split(","))):
        k, _, v = o.partition("=")
        k = k.lower()
        if k in ("loop", "once"):
            e["loop"] = (k == "loop")
        elif k == "speed":
            e["speed"] = float(v)
        elif k == "trim":
            a, _, b = v.partition("-")
            e["trim"] = [float(a), float(b)]
        else:
            raise ValueError("--clip option '%s' unknown (speed=, trim=a-b, loop, once)" % o)
    return mv.strip(), e


def norm_entry(e):
    """a clip-map value: "asset:clip@speed=..,trim=a-b,loop" or {"clip":..., "speed":..., "trim":[a,b], "loop":bool}"""
    if isinstance(e, str):
        return parse_clip_arg("m=" + e)[1]
    if not isinstance(e, dict) or not e.get("clip"):
        raise ValueError("needs a 'clip' (asset:clip)")
    e = dict(e)
    if "speed" in e and not (0.05 <= float(e["speed"]) <= 20):
        raise ValueError("speed 0.05..20")
    if "trim" in e:
        a, b = [float(x) for x in e["trim"]]
        if not (0 <= a < b):
            raise ValueError("trim [a, b] in seconds with 0 <= a < b")
        e["trim"] = [a, b]
    return e


def entry_str(e):
    """inverse of parse_clip_arg (for the UI's clip column)"""
    e = norm_entry(e); o = []
    if e.get("speed", 1.0) != 1.0:
        o.append("speed=%g" % e["speed"])
    if e.get("trim"):
        o.append("trim=%g-%g" % tuple(e["trim"]))
    if "loop" in e:
        o.append("loop" if e["loop"] else "once")
    return e["clip"] + ("@" + ",".join(o) if o else "")


def load_clip_map(path):
    d = json.load(open(path, encoding="utf-8"))
    return {k: norm_entry(v) for k, v in d.get("clip_map", d).items()}


class LibContext:
    """the rig, its bone map, the library and every resolved clip of one build."""

    def __init__(self, cfg, report):
        from . import library as L, kits as K
        self.lib = L.Library(cfg.library_dir or None)
        name = cfg.rig
        if getattr(cfg, "_rig_obj", None) is not None:      # v7 MakeHuman mode: a rig built in memory
            from . import bonemap as BM
            self.rig = cfg._rig_obj; self.rec = BM.detect(self.rig)
            self.licence = dict(L.LICENCE_PRESETS["makehuman"])
        elif os.path.isfile(name):                         # a raw FBX / GLB path: import on the fly (not added)
            from . import importers
            self.rig, self.rec, rep = importers.load_file(name)
            report.note("rig: imported %s on the fly (%s, %d bones) - `forge.py library add` keeps it" % (name, self.rec["convention"], self.rig.nb))
            self.licence = None
        else:
            self.rig = self.lib.load_rig(name)
            self.rec = self.lib.bonemap(name, self.rig)
            self.licence = self.lib.licence(name)
        self.slot_report = None
        if self.rig.has_mesh() and getattr(cfg, "material_slots", "full") != "keep":
            from . import matslots
            self.rig, self.slot_report = matslots.apply(self.rig, self.rec, getattr(cfg, "material_split", "auto"),
                                                        cfg.material_slots, report.note)
            report.note("material slots: " + ", ".join(self.slot_report["materials"]))
        self.equip_parts = []
        if getattr(cfg, "outfits", None) or getattr(cfg, "props", None) or getattr(cfg, "slot_colors", ""):
            from . import equip as EQ
            outs = [EQ.parse_outfit(o) for o in (cfg.outfits or [])]
            self.rig, self.equip_parts = EQ.equip(self.rig, self.rec, self.lib, outs, list(cfg.props or []),
                                                  cfg.slot_colors or None, report.note)
            for p in self.equip_parts:
                lc = p.get("licence") or {}
                if str(lc.get("redistribution", "unknown")).lower() not in ("yes", "true"):
                    report.warning("equip %s '%s': licence %s, redistribution '%s' - check before sharing this build"
                                   % (p["kind"], p["name"], lc.get("spdx") or "not filled in", lc.get("redistribution", "unknown")))
        if not self.rig.has_mesh():
            report.warning("rig '%s' has no mesh - frames show its skeleton (animation-only file)" % name)
        if self.rec.get("missing"):
            report.warning("rig '%s': canonical bones not mapped: %s (edit bonemap.json or the Library tab)" % (name, ", ".join(self.rec["missing"])))
        self.scale = 1.0
        if cfg.height_cm:
            self.scale = cfg.height_cm / 100.0 / max(1e-6, self.rig.height())
        self.kit = K.load(cfg.kit, self.lib.dir) if cfg.kit else None
        if cfg.kit and self.kit is None:
            report.warning("kit '%s' not found (library/kits/<name>.json, a .json path or a built-in kit)" % cfg.kit)
        self.cfg = cfg; self.report = report
        self.clips = {}            # move -> (Clip, source tag)
        self._mann = None

    # ---------- clip resolution
    def _mannequin(self):
        if self._mann is None:
            from . import rigrec as RR, bonemap as BM
            m = RR.from_mannequin(clips=[])
            self._mann = (m, BM.detect(m))
        return self._mann

    def _from_asset(self, asset, clip, name):
        from . import retarget as RT
        if asset in ("", None, self.cfg.rig):
            if clip not in self.rig.clips:
                raise KeyError("rig '%s' has no clip '%s' (has: %s)" % (self.cfg.rig, clip, ", ".join(self.rig.clips)))
            return self.rig.clips[clip], "rig:%s" % clip
        key = (asset,)
        if key not in _CACHE:
            r = self.lib.load_rig(asset)
            _CACHE[key] = (r, self.lib.bonemap(asset, r))
        src, srec = _CACHE[key]
        if clip not in src.clips:
            raise KeyError("library asset '%s' has no clip '%s' (has: %s)" % (asset, clip, ", ".join(src.clips)))
        cl, rep = RT.retarget(src, srec, clip, self.rig, self.rec, root_motion=self.cfg.root_motion, name=name)
        return cl, "lib:%s:%s" % (asset, clip)

    def _procedural(self, motion_name, m):
        from . import rigrec as RR, retarget as RT
        man, mrec = self._mannequin()
        c = RR.motion_clip(man, motion_name, loop=m.loop)
        if c is None:
            return None
        cl, _ = RT.retarget(man, mrec, c, self.rig, self.rec, root_motion=self.cfg.root_motion, name=m.name)
        return cl

    def resolve(self, m):
        from .retarget import edit_clip
        cfg = self.cfg
        e = cfg.clip_map.get(m.name)
        if e:
            e = norm_entry(e)
            ref = e.get("clip", "")
            asset, _, clip = ref.rpartition(":")
            try:
                cl, tag = self._from_asset(asset, clip, m.name)
                if e.get("trim") or e.get("speed", 1.0) != 1.0 or "loop" in e:
                    cl = edit_clip(cl, e.get("trim"), float(e.get("speed", 1.0)), e.get("loop"), m.name)
                    tag += "*"
                return cl, tag
            except Exception as ex:
                self.report.warning("move %s: clip map entry %r failed (%s) - falling back" % (m.name, ref, ex))
        mo = motion_for(m)
        if mo is not None and mo.name.startswith("mocap_"):
            cl = self._procedural(mo.name, m)
            if cl is not None:
                return cl, "mocap:" + mo.name
        names = [m.name] + ([m.motion] if m.motion else []) + ([mo.name] if mo else [])
        for n in names:
            if n in self.rig.clips:
                return self.rig.clips[n], "rig:%s" % n
        idx = self.lib.clip_index()
        for n in names:
            for key, (asset, clip) in sorted(idx.items()):
                if clip == n and asset != cfg.rig:
                    try:
                        return self._from_asset(asset, clip, m.name)
                    except Exception:
                        pass
        if cfg.fill != "skip" and mo is not None:
            cl = self._procedural(mo.name, m)
            if cl is not None:
                return cl, "procedural:%s" % mo.name
        if cfg.fill == "skip":
            return None, "skip"
        from .rigrec import Clip
        return self.rig.rest_clip(), "filled:rest"

    def resolve_all(self, moves):
        for m in moves:
            if m.name not in self.clips:
                cl, tag = self.resolve(m)
                if cl is not None:
                    self.clips[m.name] = (cl, tag)
        return self.clips

    # ---------- rendering
    def times(self, cl, n, loop):
        from .anim import sample_times
        lp = cl.loop if loop is None else loop
        return [t * cl.duration for t in sample_times(n, lp)], lp

    def frames_for(self, m, n, rs, animate=True):
        cl, tag = self.clips[m.name]
        ts, lp = self.times(cl, n, m.loop)
        if not animate:
            ts = ts[:1]
        return [self.rig.render(self.rig.fk(cl.local_at(t, lp)) if cl.frames > 1 else self.rig.worlds(cl, 0.0), rs, self.kit,
                                scale=self.scale) for t in ts]


def library_frames(cfg, report):
    """-> (frames dict like _mannequin_frames, ctx)"""
    from . import render
    ctx = LibContext(cfg, report)
    cfg._libctx = ctx
    ctx.resolve_all(cfg.moves)
    rs = render.RenderSettings(cfg.frame_w, cfg.frame_h, cfg.figure_h, cfg.ground_y, cfg.pivot_x, yaw=cfg.yaw, outline=cfg.outline)
    out = {}
    for m in cfg.moves:
        if m.name not in ctx.clips:
            continue
        fr = ctx.frames_for(m, m.frames, rs)
        clip = False
        for im in fr:
            bb = im.getchannel("A").getbbox()
            if bb and (bb[0] <= 0 or bb[1] <= 0 or bb[2] >= im.width or bb[3] >= im.height):
                clip = True
        tag = ctx.clips[m.name][1]
        if tag.startswith("filled"):
            tag = "filled:rest-pose"
        out[m.name] = (fr, tag, "clipped at cell edge" if clip else "")
    return out, ctx


def model_clips(ctx, moves):
    """clips for the 3D export: one take per move (named like the move), at the move's resolved clip."""
    out = {}
    for m in moves:
        if m.name in ctx.clips:
            cl = ctx.clips[m.name][0]
            c2 = type(cl)(m.name, cl.R, cl.T, cl.fps, cl.loop if m.loop is None else bool(m.loop), cl.source)
            out[m.name] = c2
    return out


def write_models(cfg, ctx, out, log, export_fbx):
    """model.glb (+ model.fbx) of the library rig with every move as an animation take, plus kit variants."""
    from . import rigrec as RR, kits as K
    import copy
    rig = ctx.rig
    if ctx.scale != 1.0:
        rig = copy.deepcopy(rig); G = np.eye(4); G[:3, :3] *= ctx.scale; rig.apply_global(G)
    clips = model_clips(ctx, cfg.moves)
    if ctx.scale != 1.0:
        tmp = copy.deepcopy(ctx.rig); tmp.clips = clips; G = np.eye(4); G[:3, :3] *= ctx.scale; tmp.apply_global(G); clips = tmp.clips
    files = []
    glb = os.path.join(out, "model.glb")
    RR.write_glb(rig, glb, clips, ctx.kit, extras={"rig": cfg.rig, "root_motion": cfg.root_motion,
                                                   "clip_sources": {k: v[1] for k, v in ctx.clips.items()}},
                 root_motion=cfg.root_motion)
    files.append("model.glb")
    log("  model.glb written from library rig '%s' (%d takes, %.0f KB)" % (cfg.rig, len(clips), os.path.getsize(glb) / 1024))
    if cfg.fbx and export_fbx(glb, os.path.join(out, "model.fbx"), cfg.blender, log):
        files.append("model.fbx")
    for kn in cfg.kits:
        kit = K.load(kn, ctx.lib.dir)
        if kit is None:
            log("  ! kit '%s' not found - skipped" % kn); continue
        g = os.path.join(out, "model_%s.glb" % re.sub(r"[^A-Za-z0-9_\-]+", "_", kn))
        RR.write_glb(rig, g, clips, kit, root_motion=cfg.root_motion)
        files.append(os.path.basename(g))
        if cfg.fbx and export_fbx(g, g[:-4] + ".fbx", cfg.blender, log):
            files.append(os.path.basename(g)[:-4] + ".fbx")
    return " + ".join(files), (rig, clips)


def console_model_fn(cfg, ctx, rig_clips, key, log, export_fbx):
    from . import rigrec as RR

    def fn(max_tris, cd):
        rig, clips = rig_clips
        d = RR.decimated(rig, max_tris) if max_tris and len(rig.F) > max_tris else rig
        g = os.path.join(cd, "model_%s.glb" % key)
        RR.write_glb(d, g, clips, ctx.kit, extras={"console": key, "tris": int(len(d.F))}, root_motion=cfg.root_motion)
        files = [os.path.basename(g)]
        if cfg.fbx and export_fbx(g, g[:-4] + ".fbx", cfg.blender, log):
            files.append(os.path.basename(g[:-4] + ".fbx"))
        log("  console model: %d tris (library rig %d, budget %s) -> %s" % (len(d.F), len(rig.F), max_tris, ", ".join(files)))
        return {"tris": int(len(d.F)), "detail": round(len(d.F) / max(1, len(rig.F)), 3), "budget": max_tris, "files": files}
    return fn
