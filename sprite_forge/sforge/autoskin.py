"""v7 EXPERIMENTAL auto-skin: bind YOUR OWN static humanoid mesh (OBJ / GLB / FBX without a skeleton) to a library
skeleton by bone distance - "bring your own mesh".

Sprite Forge does not generate 3D people from text or photos (no paid / web text-to-3D services are used).  Make or
buy a mesh elsewhere (Blender, MakeHuman, a store with a licence that allows it) and either
  * rig it properly (Blender auto-weights / Mixamo) and `forge.py library add rigged.fbx`  <- best quality, or
  * try this quick experimental binder:  forge.py autoskin my_mesh.obj --skeleton sample_lanky --name my_hero

How it works: the mesh is stood upright (+Y, longest axis), scaled to the skeleton's height and centred; each vertex
gets weights from its distance to every bone SEGMENT (head -> child head), w ~ 1/d^4, only the 4 nearest bones,
left / right limbs only for vertices on their own side of the body, then smoothed over mesh neighbours.  Clips are
copied from the skeleton (same bones).  Limits: the mesh must be a roughly T/A-pose humanoid matching the skeleton's
pose; loose clothing, long hair, tails, props and fingers get poor weights; no heat diffusion / geodesic voxel
binding like Blender or Mixamo.  The result is marked experimental in the library and in the build report.
"""
from __future__ import annotations
import os
import numpy as np


def _segments(rig):
    """-> (A (nb,3) heads, B (nb,3) segment ends) - a bone's end is the mean of its children's heads, or a stub."""
    P = rig.bind[:, :3, 3]
    A = P.copy(); B = P.copy()
    kids = {i: [] for i in range(rig.nb)}
    for i, p in enumerate(rig.parent):
        if p >= 0:
            kids[int(p)].append(i)
    for i in range(rig.nb):
        if kids[i]:
            # spine-like bones: use the child that continues the chain (closest to the bone's own axis), not a limb
            ch = min(kids[i], key=lambda k: abs(P[k, 0] - P[i, 0]))
            B[i] = P[ch]
        else:
            y = rig.bind[i, :3, 1]
            pl = P[i] - P[rig.parent[i]] if rig.parent[i] >= 0 else y * 0.1
            B[i] = P[i] + (pl if np.linalg.norm(pl) > 1e-6 else y * 0.05) * 0.5
    return A, B


def _seg_dist(V, A, B):
    """distance of every vertex to every segment: (n, nb)"""
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    out = np.empty((len(V), len(A)))
    for i in range(len(A)):
        t = np.clip(((V - A[i]) @ AB[i]) / L2[i], 0, 1)
        out[:, i] = np.linalg.norm(V - (A[i] + t[:, None] * AB[i]), axis=1)
    return out


def stand_up(rig, log=print):
    ext = np.ptp(rig.V, axis=0)
    from .rigrec import m4
    if ext[2] > ext[1] * 1.2 and ext[2] >= ext[0]:
        c, s = 0.0, -1.0           # Z-up -> Y-up: rotate -90 deg about X
        R = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)
        rig.apply_global(m4(R, [0, 0, 0])); log("  autoskin: mesh was Z-up -> rotated to Y-up")
    elif ext[0] > ext[1] * 1.2:
        R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], float)
        rig.apply_global(m4(R, [0, 0, 0])); log("  autoskin: mesh was lying along X -> rotated upright")


def autoskin(mesh, skel, smooth=2, log=print):
    """mesh: Rig with a mesh (weights ignored); skel: library Rig (skeleton + clips). -> new Rig skinned to skel."""
    import copy
    from . import bonemap as BM
    from .rigrec import m4
    m = copy.deepcopy(mesh)
    if m.nb == 0:
        m.bones = ["root"]; m.parent = np.array([-1]); m.bind = np.eye(4)[None]
        m.J = np.zeros((len(m.V), 4), int); m.W = np.tile([1.0, 0, 0, 0], (len(m.V), 1))
    stand_up(m, log)
    # scale + place onto the skeleton (feet on its lowest joint level, centred over its hips in X/Z)
    srec = BM.detect(skel)
    P = skel.bind[:, :3, 3]
    hips = srec["map"].get("hips"); hi = skel.bones.index(hips) if hips in skel.bones else 0
    sk_h = skel.height() if skel.has_mesh() else (P[:, 1].max() - P[:, 1].min()) * 1.08
    me_h = np.ptp(m.V[:, 1])
    k = sk_h / max(1e-9, me_h)
    V = (m.V - [0, m.V[:, 1].min(), 0]) * k
    ylo = skel.V[:, 1].min() if skel.has_mesh() else P[:, 1].min() - 0.03 * sk_h
    V = V + [0, ylo, 0]
    # centre the PELVIS slab (vertices around the hips height, hands hanging there excluded) of the mesh on the same
    # slab of the skeleton's own mesh when it has one (joints sit nearer the back than the body centre), else on the hips
    def pelvis_centre(X):
        sl = np.abs(X[:, 1] - P[hi, 1]) < 0.04 * sk_h
        ref = X[sl] if sl.sum() > 10 else X
        cx = 0.5 * (ref[:, 0].min() + ref[:, 0].max())
        core = ref[np.abs(ref[:, 0] - cx) < 0.09 * sk_h]
        ref = core if len(core) > 10 else ref
        return np.array([0.5 * (ref[:, 0].min() + ref[:, 0].max()), 0.0, 0.5 * (ref[:, 2].min() + ref[:, 2].max())])
    target = pelvis_centre(skel.V) if skel.has_mesh() else np.array([P[hi, 0], 0.0, P[hi, 2]])
    V = V + (target - pelvis_centre(V))
    A, B = _segments(skel)
    D = _seg_dist(V, A, B)
    # side rule: a left limb bone only for vertices on its side (x of the bone relative to the hips centre line)
    side = np.sign(P[:, 0] - P[hi, 0]); side[np.abs(P[:, 0] - P[hi, 0]) < 0.02 * sk_h] = 0
    vs = np.sign(V[:, 0] - P[hi, 0])
    bad = (side[None, :] != 0) & (vs[:, None] != side[None, :]) & (np.abs(V[:, 0] - P[hi, 0])[:, None] > 0.01 * sk_h)
    D = D + bad * 10.0
    # leaf / end bones with no deforming role in typical rigs (e.g. *_end, *Top_End) are ignored
    for i, b in enumerate(skel.bones):
        if b.lower().endswith(("_end", "end", "top_end")) and b not in srec["map"].values():
            D[:, i] += 10.0
    J = np.argsort(D, axis=1)[:, :4]
    d = np.take_along_axis(D, J, axis=1)
    W = 1.0 / np.maximum(d, 0.01 * sk_h) ** 4
    W = W / W.sum(1, keepdims=True)
    # neighbour smoothing of the dense weight field (a few Laplacian steps)
    if smooth and len(m.F):
        dense = np.zeros((len(V), skel.nb)); np.put_along_axis(dense, J, W, axis=1)
        e = np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]])
        e = np.concatenate([e, e[:, ::-1]])
        deg = np.bincount(e[:, 0], minlength=len(V)).astype(float)[:, None]
        for _ in range(int(smooth)):
            acc = np.zeros_like(dense); np.add.at(acc, e[:, 0], dense[e[:, 1]])
            dense = 0.5 * dense + 0.5 * acc / np.maximum(deg, 1)
        J = np.argsort(-dense, axis=1)[:, :4]
        W = np.take_along_axis(dense, J, axis=1); W = W / np.maximum(W.sum(1, keepdims=True), 1e-12)
    out = copy.deepcopy(skel)
    out.V = V; out.F = m.F.copy(); out.J = J.astype(int); out.W = W
    out.fmat = m.fmat.copy() if len(m.fmat) == len(m.F) else np.zeros(len(m.F), int)
    out.materials = copy.deepcopy(m.materials) or [dict(name="Skin_Mat", color=[0.8, 0.7, 0.6])]
    out.fuv = m.fuv; out.fcol = m.fcol; out.textures = dict(m.textures)
    out.meta = dict(skel.meta); out.meta.update(source="autoskin (EXPERIMENTAL bone-distance binding) of %s onto %s" % (
        mesh.meta.get("source_file", mesh.name), skel.name), experimental_autoskin=True, mesh_parts=[dict(name="body", f0=0, f1=len(m.F))])
    out._tri_cache = {}
    log("  autoskin: %d verts, %d faces bound to %d bones (scale x%.3f, %d smoothing steps) - EXPERIMENTAL" % (
        len(V), len(m.F), skel.nb, k, smooth))
    return out


def dominant_agreement(a, b):
    """fraction of vertices whose strongest bone is the same in two rigs with identical vertex order + bones"""
    da = a.J[np.arange(len(a.V)), np.argmax(a.W, 1)]
    db = b.J[np.arange(len(b.V)), np.argmax(b.W, 1)]
    return float(np.mean(np.array(a.bones)[da] == np.array(b.bones)[db]))


def main(argv):
    import argparse
    from . import importers, library as L, bonemap as BM
    ap = argparse.ArgumentParser(prog="forge.py autoskin", description=__doc__.split("\n")[0])
    ap.add_argument("mesh", help="your static mesh: .obj / .glb / .gltf / .fbx (any skin in it is ignored)")
    ap.add_argument("--skeleton", default="sforge_mannequin", help="library rig whose skeleton + clips are used (default sforge_mannequin)")
    ap.add_argument("--name", help="library rig name for the result (default <mesh>_autoskin)")
    ap.add_argument("--library"); ap.add_argument("--smooth", type=int, default=2)
    ap.add_argument("--spdx", default="", help="licence of YOUR mesh (e.g. CC0-1.0); stays 'not filled in' otherwise")
    ap.add_argument("--author", default=""); ap.add_argument("--redistribution", choices=["yes", "no", "unknown"], default="unknown")
    ap.add_argument("--glb", help="also write the result as this GLB")
    a = ap.parse_args(argv)
    lib = L.Library(a.library or None)
    rep = {}
    mesh, _, rep = importers.load_file(a.mesh, rep, orient="off")
    if not mesh.has_mesh():
        print("autoskin: %s has no mesh" % a.mesh); return 2
    skel = lib.load_rig(a.skeleton)
    out = autoskin(mesh, skel, a.smooth)
    name = L.slug(a.name or os.path.splitext(os.path.basename(a.mesh))[0] + "_autoskin")
    out.name = name
    lic = L.blank_licence(); lic.update(spdx=a.spdx, author=a.author, redistribution=a.redistribution,
                                        notes="your mesh, auto-skinned (experimental) onto '%s' (its licence: %s)" % (
                                            a.skeleton, lib.licence(a.skeleton).get("spdx") or "?"))
    d = lib.path("rigs", name)
    if os.path.exists(d):
        import shutil; shutil.rmtree(d)
    lib.save_rig(out, BM.detect(out), "rigs", lic, dict(path=os.path.abspath(a.mesh), report=L._jsonable(rep)))
    lib.scan(import_inbox=False)
    if a.glb:
        from . import rigrec as RR
        RR.write_glb(out, a.glb, list(out.clips) or None)
    print("autoskin -> library rig '%s' (%d clips from %s). EXPERIMENTAL - check the deformation: forge.py build --rig %s --moves idle,walk,run"
          % (name, len(out.clips), a.skeleton, name))
    return 0
