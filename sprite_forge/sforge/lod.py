"""Sprite Forge Studio v9 - texture baking + LODs for the 3D mannequin model.

  model_baked.glb      all materials baked into one palette texture -> 1 material / 1 draw call
  model_lod1..N.glb    lower-detail meshes (the same procedural mannequin rebuilt with fewer segments, about
                       half the triangles per level) with the SAME skeleton, clips, morph targets and physics joints,
                       so an engine LOD group can swap them freely.
  lods.json            triangle counts + suggested screen-size thresholds.
Only for spec/mannequin builds (a photo is never turned into 3D)."""
from __future__ import annotations
import json
import os


def _meshes(cfg, sp, detail):
    from . import mesh
    from .build import _prop, glb_v9_extras
    old = mesh.DETAIL
    try:
        mesh.DETAIL = detail
        T, B, M = mesh.build_mannequin(sp, prop=_prop(cfg))
        x = glb_v9_extras(cfg, sp)
    finally:
        mesh.DETAIL = old
    return T, B, M, x


def write_lods(cfg, out, ctx, report):
    sp = ctx.get("sp")
    if sp is None or cfg.mode not in ("spec", "mannequin"):
        return "LODs skipped (only for spec/mannequin builds)"
    from . import gltf
    from .build import _slots
    from .moves import motion_for
    clips = [(m.name, motion_for(m), m.frames, m.fps, m.loop) for m in cfg.moves if motion_for(m) is not None]
    T0, B0, M0, x0 = _meshes(cfg, sp, 1.0)
    base = len(T0)
    info = {"lod0": {"file": "model.glb", "tris": base, "screen": 1.0}}
    p = os.path.join(out, "model_baked.glb")
    gltf.write_glb(p, T0, B0, M0, sp.colours(), clips, scale=sp.scale, name=cfg.name + "_baked", slots=_slots(cfg), bake=True, **x0)
    info["baked"] = {"file": "model_baked.glb", "tris": base, "materials": 1, "kb": round(os.path.getsize(p) / 1024)}
    n = max(1, min(4, int(cfg.lods)))
    details = [0.65, 0.4, 0.3, 0.0]
    screen = [0.5, 0.25, 0.12, 0.06]
    last = base
    for k in range(n):
        T, B, M, x = _meshes(cfg, sp, details[k])
        if len(T) >= last:          # cannot go lower
            break
        last = len(T)
        f = "model_lod%d.glb" % (k + 1)
        gltf.write_glb(os.path.join(out, f), T, B, M, sp.colours(), clips, scale=sp.scale, name="%s_LOD%d" % (cfg.name, k + 1),
                       slots=_slots(cfg), bake=True, **x)
        info["lod%d" % (k + 1)] = {"file": f, "tris": len(T), "ratio": round(len(T) / base, 2), "screen": screen[k], "baked": True}
    with open(os.path.join(out, "lods.json"), "w") as fh:
        json.dump(info, fh, indent=1)
    return "LODs: " + ", ".join("%s %d tris" % (k, v["tris"]) for k, v in info.items())
