"""forge.py capture, step 5 - the captured person as a game character (v11).

GLB  skinned mesh (MakeHuman topology, UVs, the baked photo texture), 26-bone skeleton with the common game names
     (pelvis, spine_01.., thigh_l, calf_l, upperarm_l ...), MakeHuman's own skin weights, and Sprite Forge's built-in
     clips (idle, walk, run, jump, kick, punch, celebrate) retargeted onto it - the same skeleton as `forge.py look`.
FBX  the same character, written from the GLB by Sprite Forge's own FBX writer (texture embedded).
OBJ  the static mesh in the captured stance (+ .mtl + texture), for tools that only want geometry.
rig  a Sprite Forge library rig (rig.json + rig.npz) so every existing sprite / console / game exporter can use it.
"""
from __future__ import annotations
import io
import json
import os
import numpy as np
from PIL import Image


def make_rig(shape, name="captured"):
    """capture_body.Shape (rest A-pose) -> rigrec.Rig with skeleton, weights, UVs"""
    from .rigrec import Rig, m4
    from .human import _orient
    m = shape.m
    r = Rig(name)
    r.bones = list(m.order)
    r.parent = np.array(m.parent, int)
    r.bind = np.array([m4(_orient(shape.head[i], shape.tail[i]), shape.head[i]) for i in range(len(m.order))], float)
    r.V = shape.V.copy(); r.F = m.F.copy(); r.J = m.J.copy(); r.W = m.W.copy()
    r.fmat = np.zeros(len(r.F), int)
    r.materials = [dict(name="Skin_Mat", color=[1, 1, 1], texture="textures/%s.png" % name)]
    r.fuv = m.fuv.copy()
    r.meta = dict(source="Sprite Forge capture: MakeHuman CC0 body fitted to a turnaround video", hips_index=m.bi["root"],
                  convention="makehuman")
    r._tri_cache = {}
    return r


LAYER_NAMES = ["Body", "Clothes", "Skirt", "Hair"]


def export(shape, posed_V, texture, out_dir, name="captured", clips=None, log=print, extras=None, mesh=None,
           posed_mesh=None, makehuman=None):
    """mesh: capture_layers.Mesh (body + clothes + skirt + hair, one atlas) - default the bare body.
    makehuman: dict(macros, sliders) -> also NAME.mhm (MakeHuman 1.x) and NAME.mpfb.json (MPFB2 in Blender)"""
    from . import bonemap as BM, samplerigs as SR, rigrec as RR, glbpack, mhchar, fbx as FBX
    from .mhtemplate import NAMES
    from .rigrec import quat_from_mats, polar
    os.makedirs(out_dir, exist_ok=True)
    r = make_rig(shape, name)
    rec = BM.detect(r)
    SR.add_clips(r, rec, clips or SR.STARTER_CLIPS)
    L0 = r.rest_local()
    for b in ("neck01", "head"):                     # as the CC0 template: head follows the chest, looks forward
        if b in r.bones:
            i = r.bones.index(b)
            q = quat_from_mats(polar(L0[i:i + 1, :3, :3]))[0]
            for c in r.clips.values():
                c.R[:, i] = q
    r.bones = [NAMES.get(b, b) for b in r.bones]
    r.meta["hips_index"] = r.bones.index("pelvis")
    glb = os.path.join(out_dir, name + ".glb")
    tmp = glb + ".skel.glb"
    RR.write_glb(r, tmp, list(r.clips))
    if mesh is None:
        from .capture_layers import Mesh
        mesh = Mesh(shape.V, shape.m.F, shape.m.fuv, shape.m.J, shape.m.W, np.zeros(len(shape.V), int))
    parts = []
    for lid, lname in enumerate(LAYER_NAMES):
        vsel = mesh.layer == lid
        if not vsel.any():
            continue
        fsel = vsel[mesh.F].all(1)
        Fl = mesh.F[fsel]; fuv = mesh.fuv[fsel]
        # one vertex per (position, uv) pair: glTF / FBX want per-vertex UVs
        uvq = np.round(fuv.reshape(-1, 2) * 1e6).astype(np.int64)
        key = np.c_[Fl.reshape(-1), uvq]
        uk, inv = np.unique(key, axis=0, return_inverse=True)
        vi = uk[:, 0]
        UV = uk[:, 1:] / 1e6
        UV[:, 1] = 1.0 - UV[:, 1]
        F = inv.reshape(-1, 3)
        V = mesh.V[vi]
        parts.append(mhchar.Part(name=lname, role=lname.lower(), V=V, F=F, UV=UV, J=mesh.J[vi].astype(np.uint16),
                                 W=mesh.W[vi].astype(np.float32), N=mhchar.normals(V, F), image="atlas"))
    png = io.BytesIO(); Image.fromarray(texture).save(png, "PNG")
    ex = {"source": "Sprite Forge capture (MakeHuman CC0 body + photo texture)",
          "layers": [p.name for p in parts]}
    ex.update(extras or {})
    glbpack.pack_parts(tmp, glb, parts, {"atlas": png.getvalue()}, extras=ex)
    os.remove(tmp)
    fbx = os.path.join(out_dir, name + ".fbx")
    try:
        FBX.write_fbx_from_glb(glb, fbx)
    except Exception as e:                                                  # noqa: BLE001
        log("capture: FBX failed (%s) - GLB and OBJ are fine" % e); fbx = None
    pm = posed_mesh if posed_mesh is not None else posed_V
    obj = write_obj(pm, mesh.F, mesh.fuv, texture, out_dir, name, layer=mesh.layer)
    Image.fromarray(texture).save(os.path.join(out_dir, name + "_texture.png"))
    if (mesh.layer > 0).any():                       # the body quarter alone: a MakeHuman / MPFB skin image
        h = texture.shape[0] // 2
        Image.fromarray(texture[:h, :h]).save(os.path.join(out_dir, name + "_skin.png"))
    out = dict(glb=glb, fbx=fbx, obj=obj, rig=r)
    if makehuman:
        from . import capture_mh
        out.update(capture_mh.write(out_dir, name, makehuman["macros"], makehuman["sliders"], makehuman.get("height_m")))
    log("capture: %s.glb (%s; %d bones, %d clips: %s), %s, %s" % (
        name, " + ".join(p.name for p in parts), len(r.bones), len(r.clips), ", ".join(r.clips),
        os.path.basename(fbx) if fbx else "no FBX", os.path.basename(obj)))
    return out


def write_obj(V, F, fuv, texture, out_dir, name, layer=None):
    """OBJ + MTL in the captured stance; one named object per layer (Body / Clothes / Skirt / Hair) so Blender,
    MakeHuman-style tools and game engines import them as separate, editable meshes"""
    tex = name + "_texture.png"
    with open(os.path.join(out_dir, name + ".mtl"), "w") as f:
        f.write("newmtl atlas\nKd 1 1 1\nKa 0 0 0\nKs 0 0 0\nillum 1\nmap_Kd %s\n" % tex)
    p = os.path.join(out_dir, name + ".obj")
    uv = fuv.reshape(-1, 2)
    lay = np.zeros(len(V), int) if layer is None else layer
    flay = lay[F[:, 0]]
    with open(p, "w") as f:
        f.write("# Sprite Forge capture - MakeHuman CC0 topology (+ clothes / hair layers), metres, Y up\n")
        f.write("mtllib %s.mtl\n" % name)
        f.write("".join("v %.5f %.5f %.5f\n" % tuple(v) for v in V))
        f.write("".join("vt %.6f %.6f\n" % tuple(t) for t in uv))
        for lid, lname in enumerate(LAYER_NAMES):
            ks = np.nonzero(flay == lid)[0]
            if not len(ks):
                continue
            f.write("o %s\ng %s\nusemtl atlas\n" % (lname, lname))
            f.write("".join("f %d/%d %d/%d %d/%d\n" % (F[k, 0] + 1, 3 * k + 1, F[k, 1] + 1, 3 * k + 2, F[k, 2] + 1, 3 * k + 3)
                            for k in ks))
    return p
