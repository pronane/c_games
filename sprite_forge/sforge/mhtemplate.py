"""Built-in CC0 template for realistic characters (v10.3): Sprite Forge's own rigged MakeHuman body + clips.

`forge.py look` needs a rigged MakeHuman-topology GLB (skeleton + clips) to carry looks onto.  This makes one from
nothing but the CC0 MakeHuman assets and Sprite Forge's own code, so the Studio needs no other game or program:
  mesh      the CC0 MakeHuman base body, adult male, athletic (sforge.human macro targets)
  skeleton  26 bones reduced from MakeHuman's CC0 default skeleton (sforge.human 'body'), renamed to the common
            game names (pelvis, spine_01.., thigh_l, calf_l, upperarm_l ...)
  clips     Sprite Forge's built-in procedural motions (idle, walk, run, jump, kick, punch, celebrate) retargeted
            onto it - generated, CC0.
Written once to <studio>/assets/makehuman/template_cc0.glb and reused."""
from __future__ import annotations
import os

NAMES = {"root": "pelvis", "spine05": "spine_01", "spine04": "spine_02", "spine03": "spine_03", "spine02": "spine_04",
         "spine01": "spine_05", "neck01": "neck_01", "head": "head"}
for s, t in (("L", "l"), ("R", "r")):
    NAMES.update({"clavicle.%s" % s: "clavicle_%s" % t, "pelvis.%s" % s: "hip_%s" % t,
                  "upperleg01.%s" % s: "thigh_%s" % t, "lowerleg01.%s" % s: "calf_%s" % t, "foot.%s" % s: "foot_%s" % t,
                  "toe1-1.%s" % s: "ball_%s" % t, "upperarm01.%s" % s: "upperarm_%s" % t,
                  "lowerarm01.%s" % s: "lowerarm_%s" % t, "wrist.%s" % s: "hand_%s" % t})
PARAMS = dict(gender=1.0, age=0.5, muscle=0.62, weight=0.5, height=0.5, proportions=0.6)


def path(root=None):
    from . import human as HU
    return os.path.join(HU.assets_dir(root), "template_cc0.glb")


def make(out=None, log=print, root=None):
    from . import human as HU, bonemap as BM, samplerigs as SR, rigrec as RR
    out = out or path(root)
    r = HU.build(PARAMS, "body", root, "sforge_human", log=lambda *a: None)
    rec = BM.detect(r)
    SR.add_clips(r, rec)
    # the mannequin's neck / head channels tip the MakeHuman head back (different bone rolls): keep them at rest so
    # the head follows the chest and looks forward
    from .rigrec import quat_from_mats, polar
    L0 = r.rest_local()
    for b in ("neck01", "head"):
        if b in r.bones:
            i = r.bones.index(b)
            q = quat_from_mats(polar(L0[i:i + 1, :3, :3]))[0]
            for c in r.clips.values():
                c.R[:, i] = q
    r.bones = [NAMES.get(b, b) for b in r.bones]
    r.meta["hips_index"] = r.bones.index("pelvis")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".skel.glb"
    RR.write_glb(r, tmp, list(r.clips))
    # mesh with per-vertex UVs (MakeHuman seams split), on the skeleton + clips just written
    import io
    import numpy as np
    from PIL import Image
    from . import glbpack, mhchar
    uvq = np.round(r.fuv.reshape(-1, 2) * 1e6).astype(np.int64)
    key = np.c_[r.F.reshape(-1), uvq]
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    vi = uk[:, 0]
    UV = uk[:, 1:] / 1e6
    UV[:, 1] = 1.0 - UV[:, 1]                                             # OBJ (v up) -> glTF (v down)
    F = inv.reshape(-1, 3)
    V = r.V[vi]
    tiny = io.BytesIO(); Image.new("RGB", (1, 1), (200, 160, 140)).save(tiny, "PNG")
    glbpack.pack(tmp, out, V, mhchar.normals(V, F), UV, F, r.J[vi].astype(np.uint16), r.W[vi].astype(np.float32),
                 tiny.getvalue(), name="sforge_human",
                 extras={"source": "Sprite Forge CC0 template: MakeHuman CC0 base body + built-in procedural clips"})
    os.remove(tmp)
    log("CC0 template: %d bones, %d clips (%s), %.2f m -> %s" % (r.nb, len(r.clips), ", ".join(r.clips), r.height(), out))
    return out


def ensure(root=None, log=print):
    p = path(root)
    return p if os.path.isfile(p) else make(p, log, root)
