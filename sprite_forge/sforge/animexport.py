"""v7: separate animation files (forge.py anim-export, or forge.py build --anim-export).

  <out>/character_base.glb     mesh + skeleton + skin together (never the mesh alone), no animation
  <out>/anim_<move>.glb        the same armature (same joint order, a skin with the same inverse binds, NO mesh) and
                               ONE animation with full tracks: rotation + translation + scale for every bone
  <out>/*.fbx                  the same files as FBX (built-in writer) when fbx=True
  <out>/manifest.json          bones (order, parents), moves (file, frames, fps, duration, loop), fps, limits checked

Every anim file loads on its own (Blender, Godot, Unity, raylib: LoadModelAnimations("anim_walk.glb")) and its tracks
apply onto character_base.glb because the joint list is identical.

raylib compliance (checked against raylib 5.5 / 6.0 rmodels.c + cgltf):
  * one skin per file (raylib reads skins[0] only)          -> exactly one skin in base and anim files
  * anim files need a skin (LoadModelAnimationsGLTF reads skins[0].joints) -> skin without mesh
  * bones topologically sorted (parent index < child index; otherwise "Skipping bone not topologically sorted")
                                                            -> bones are re-ordered parents-first
  * Mesh.boneIndices are unsigned char                     -> at most 255 bones (refused above)
  * BoneInfo.name is char[32]                               -> names longer than 31 bytes are shortened (unique)
  * at most 4 influences per vertex (JOINTS_0 / WEIGHTS_0)  -> we always write 4
  * linear / step interpolation, sampled by raylib at 60 fps -> LINEAR keys at our 30 fps
  * the boneCount of model and animation must match (IsModelAnimationValid) -> same joint list
  * raylib 6.0 reads the world transform of skin.joints[0]->parent (a NULL parent crashes it)
                                                            -> an identity "Armature" node above the root joint
"""
from __future__ import annotations
import copy
import json
import os
import re

import numpy as np

RAYLIB_MAX_BONES = 255
RAYLIB_NAME_MAX = 31


def topo_sorted(rig):
    """copy of the rig with bones re-ordered parents-first (J indices, binds, clips permuted). -> (rig, changed)"""
    order = rig.order()
    if order == list(range(rig.nb)):
        return rig, False
    r = copy.deepcopy(rig)
    inv = np.empty(rig.nb, int); inv[order] = np.arange(rig.nb)
    r.bones = [rig.bones[i] for i in order]
    r.parent = np.array([inv[rig.parent[i]] if rig.parent[i] >= 0 else -1 for i in order], int)
    r.bind = rig.bind[order]
    if len(r.J):
        r.J = inv[rig.J]
    for k, c in rig.clips.items():
        r.clips[k] = type(c)(c.name, c.R[:, order], c.T[:, order], c.fps, c.loop, c.source)
    if "hips_index" in rig.meta:
        r.meta["hips_index"] = int(inv[rig.meta["hips_index"]])
    r._tri_cache = {}
    return r, True


def raylib_names(rig):
    """shorten bone names to <= 31 bytes (raylib BoneInfo.name[32]), keeping them unique. -> {old: new}"""
    ren, used = {}, set()
    for b in rig.bones:
        n = b
        if len(n.encode("utf-8")) > RAYLIB_NAME_MAX:
            n = n.split(":")[-1].split("|")[-1]
            n = n.encode("utf-8")[:RAYLIB_NAME_MAX].decode("utf-8", "ignore")
        base, k = n, 2
        while n in used:
            suf = "_%d" % k; n = base[:RAYLIB_NAME_MAX - len(suf)] + suf; k += 1
        used.add(n)
        if n != b:
            ren[b] = n
    return ren


def check_limits(rig):
    probs = []
    if rig.nb > RAYLIB_MAX_BONES:
        probs.append("%d bones > %d (raylib stores bone indices as unsigned char)" % (rig.nb, RAYLIB_MAX_BONES))
    if len(rig.W) and (rig.W > 0).sum(axis=1).max() > 4:
        probs.append("more than 4 weights on a vertex")
    return probs


def safe(n):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", n).strip("_") or "move"


def export(rig, clips, out, fbx=False, kit=None, root_motion="keep", name=None, log=print, raylib=True):
    """write base + one file per clip + manifest.  clips: {move: Clip} on this rig's skeleton."""
    from . import rigrec as RR
    os.makedirs(out, exist_ok=True)
    rig2 = copy.deepcopy(rig); rig2.clips = dict(clips)
    rig2, reordered = topo_sorted(rig2)
    clips = rig2.clips
    probs = check_limits(rig2)
    if probs and raylib:
        raise ValueError("animation export: " + "; ".join(probs))
    ren = raylib_names(rig2) if raylib else {}
    if ren:
        rig2.bones = [ren.get(b, b) for b in rig2.bones]
    name = name or rig.name
    files = {}
    base = os.path.join(out, "character_base.glb")
    RR.write_glb(rig2, base, {}, kit, extras={"sforge": "character_base", "name": name}, root_motion=root_motion,
                 armature_node=True)
    files["base"] = ["character_base.glb"]
    moves = []
    for mv, c in clips.items():
        fn = "anim_%s.glb" % safe(mv)
        p = os.path.join(out, fn)
        RR.write_glb(rig2, p, {mv: c}, None, extras={"sforge": "animation", "move": mv, "base": "character_base.glb"},
                     root_motion=root_motion, with_mesh=False, force_skin=True, full_tracks=True, armature_node=True)
        ent = dict(move=mv, file=fn, frames=int(c.frames), fps=float(c.fps), duration=round(float(c.duration), 4),
                   loop=bool(c.loop), source=c.source)
        if fbx:
            from . import fbx as F
            try:
                F.write_fbx_from_glb(p, p[:-4] + ".fbx"); ent["fbx"] = fn[:-4] + ".fbx"
            except Exception as e:
                ent["fbx_error"] = str(e)
        moves.append(ent)
    if fbx:
        from . import fbx as F
        F.write_fbx_from_glb(base, base[:-4] + ".fbx"); files["base"].append("character_base.fbx")
    man = dict(format="sforge-anim-set", version=1, name=name, fps=30, base="character_base.glb",
               base_fbx="character_base.fbx" if fbx else None,
               bones=[dict(name=b, parent=int(rig2.parent[i])) for i, b in enumerate(rig2.bones)],
               bone_count=rig2.nb, moves=moves, root_motion=root_motion,
               materials=[m.get("name") for m in rig2.materials],
               raylib=dict(checked=bool(raylib), one_skin=True, topologically_sorted=True, reordered=reordered,
                           max_bones=RAYLIB_MAX_BONES, renamed=ren, max_weights=4,
                           usage='Model m = LoadModel("character_base.glb"); int n; ModelAnimation *a = LoadModelAnimations("anim_walk.glb", &n);'),
               notes="each anim_<move> file holds the full armature + skin (no mesh) and one animation; joint order == base")
    json.dump(man, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"), indent=1)
    log("  animation files: character_base.glb + %d anim_<move>.glb%s -> %s%s" % (
        len(moves), " (+ .fbx)" if fbx else "", out, ("; bones re-ordered parents-first" if reordered else "")))
    return man


def verify(out, ref=None, tol=1e-3):
    """load each anim_<move>.glb standalone with our reader, apply its tracks onto character_base.glb and skin the base
    mesh.  With ref (the source rig + clips) the skinned vertices are compared with the source motion frame by frame.
    -> list of dict(move, standalone, same_joints, frames, max_vertex_err_m, ok)"""
    from . import gltfread
    man = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
    base = gltfread.load(os.path.join(out, man["base"]), {})
    res = []
    for m in man["moves"]:
        a = gltfread.load(os.path.join(out, m["file"]), {})
        c = list(a.clips.values())[0] if len(a.clips) == 1 else None
        same = a.bones == base.bones and np.array_equal(a.parent, base.parent)
        ent = dict(move=m["move"], standalone=bool(c is not None and not a.has_mesh()), same_joints=bool(same),
                   frames=int(c.frames) if c else 0, max_vertex_err_m=None)
        if c is not None and same:
            Wb = base.clip_worlds(c)                      # the anim tracks driven on the base's own skeleton
            if ref is not None and m["move"] in ref.clips:
                rc = ref.clips[m["move"]]
                Wr = ref.clip_worlds(rc)
                ren = (man.get("raylib") or {}).get("renamed") or {}
                back = {v: k for k, v in ren.items()}
                idx = [ref.index(back.get(b, b)) for b in base.bones]
                err = 0.0 if min(idx) >= 0 else 9e9
                for f in range(min(len(Wr), len(Wb))):
                    if err > 1e9:
                        break
                    Vb = base.skin(Wb[f])
                    Vr = base.skin(Wr[f][idx])                # the SOURCE motion on the same mesh
                    err = max(err, float(np.abs(Vb - Vr).max()))
                ent["max_vertex_err_m"] = err
        ent["ok"] = bool(ent["standalone"] and ent["same_joints"] and (ent["max_vertex_err_m"] is None or ent["max_vertex_err_m"] < tol))
        res.append(ent)
    return res


def mannequin_rig(cfg, sp):
    """the spec / mannequin character as a Rig with one baked clip per move (same motions as model.glb)."""
    from . import rigrec as RR
    from .moves import motion_for
    from .build import _slots
    r = RR.from_mannequin(cfg.name, getattr(sp, "kit", "home"), clips=[], slots=_slots(cfg), sp=sp)
    clips = {}
    for m in cfg.moves:
        mo = motion_for(m)
        if mo is None:
            continue
        c = RR.motion_clip(r, mo.name, None, m.loop)        # 30 fps, natural duration (sprite frame counts are 2D only)
        if c is not None:
            c.name = m.name; clips[m.name] = c
    sc = float(getattr(sp, "scale", 1.0) or 1.0)
    if abs(sc - 1.0) > 1e-9:
        r.clips = clips; G = np.eye(4); G[:3, :3] *= sc; r.apply_global(G); clips = r.clips
    return r, clips


def from_build(cfg, out, log=print, sp=None, rig_clips=None, libctx=None):
    """forge.py build --anim-export: <out>/anim/ from the same rig + takes as model.glb."""
    if rig_clips is None and libctx is not None:
        from .librarybuild import model_clips
        rig_clips = (libctx.rig, model_clips(libctx, cfg.moves))
    if rig_clips is not None:
        rig, clips = rig_clips
        kit = getattr(libctx, "kit", None)
    else:
        from .spec import CharacterSpec
        rig, clips = mannequin_rig(cfg, sp or CharacterSpec())
        kit = None
    return export(rig, clips, os.path.join(out, "anim"), fbx=bool(cfg.fbx), kit=kit,
                  root_motion=cfg.root_motion, name=cfg.name, log=log)


def main(argv):
    """forge.py anim-export  (--rig NAME | --model FILE | --mannequin) [--moves a,b] [--kit K] [--fbx] --out DIR"""
    import argparse
    p = argparse.ArgumentParser(prog="forge.py anim-export",
                                description="write character_base.glb + anim_<move>.glb (+ .fbx) + manifest.json")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--rig", help="library rig name (moves come from its clips or --moves)")
    g.add_argument("--model", help="any rigged GLB / glTF / FBX / zip with animations (every take -> one anim file)")
    g.add_argument("--mannequin", action="store_true", help="the built-in mannequin (default)")
    p.add_argument("--moves", help="comma list of moves (default: idle,walk,run,jump,attack for rigs / every take of --model)")
    p.add_argument("--kit", help="kit to bake into character_base.glb")
    p.add_argument("--fbx", action="store_true", help="also write .fbx files (built-in writer)")
    p.add_argument("--root-motion", choices=["keep", "inplace"], default="keep")
    p.add_argument("--material-split", choices=["auto", "off"], default="auto")
    p.add_argument("--material-slots", choices=["full", "core4", "keep"], default="full")
    p.add_argument("--no-raylib-check", action="store_true", help="skip the raylib limits (bones <= 255, names <= 31 bytes)")
    p.add_argument("--verify", action="store_true", help="reload every file standalone and compare the motion with the source")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    from . import importers as IM, matslots
    kit = None
    if a.model:
        rep = {}
        rig, rec, rep = IM.load_file(a.model, rep)
        if a.material_slots != "keep":
            matslots.apply(rig, rec, a.material_split, a.material_slots, print)
        clips = dict(rig.clips)
        if a.moves:
            want = [m.strip() for m in a.moves.split(",") if m.strip()]
            clips = {k: v for k, v in clips.items() if k in want}
        name = os.path.splitext(os.path.basename(a.model))[0]
    else:
        from .build import BuildConfig
        from .moves import preset, PRESETS
        import importlib
        parse_moves = importlib.import_module("forge").parse_moves
        cfg = BuildConfig()
        cfg.mode = "library" if a.rig else "mannequin"
        cfg.rig = a.rig or ""
        cfg.name = a.rig or "mannequin"
        cfg.material_split, cfg.material_slots = a.material_split, a.material_slots
        cfg.root_motion = a.root_motion
        mv = a.moves or "idle,walk,run,jump,attack"
        cfg.moves = parse_moves(preset(next(iter(PRESETS))), mv)
        if a.kit:
            cfg.kit = a.kit
        if a.rig:
            from .librarybuild import LibContext, model_clips
            from .build import Report
            ctx = LibContext(cfg, Report(print))
            ctx.resolve_all(cfg.moves)
            rig, clips = ctx.rig, model_clips(ctx, cfg.moves); kit = ctx.kit
        else:
            from .spec import CharacterSpec
            sp = CharacterSpec()
            if a.kit:
                sp.kit = a.kit
            rig, clips = mannequin_rig(cfg, sp)
        name = cfg.name
    if a.kit and kit is None and a.model:
        from . import kits as K
        kit = K.load(a.kit)
    if not clips:
        print("no animations to export"); return 2
    export(rig, clips, a.out, fbx=a.fbx, kit=kit, root_motion=a.root_motion, name=name, raylib=not a.no_raylib_check)
    if a.verify:
        bad = 0
        for e in verify(a.out, ref=_ref(rig, clips)):
            print("  verify %-12s standalone=%s same_joints=%s frames=%d max_err=%s %s" % (
                e["move"], e["standalone"], e["same_joints"], e["frames"],
                "%.2e m" % e["max_vertex_err_m"] if e["max_vertex_err_m"] is not None else "-", "OK" if e["ok"] else "FAIL"))
            bad += not e["ok"]
        return 1 if bad else 0
    return 0


def _ref(rig, clips):
    r = copy.copy(rig); r.clips = dict(clips); return r
