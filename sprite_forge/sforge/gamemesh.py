"""Game-ready 3D characters from sculpt prims (v10.1): one watertight skinned mesh, a polygon budget, UVs, baked
textures - for engines that load a single skinned GLB (raylib, Godot, Unity, Unreal).

    mesh = gamemesh.surface(prims, h=0.005)            # union of every layer, marching cubes (no hidden skin)
    mesh = gamemesh.decimate(mesh, tris=20000)          # quadric edge collapse (pyfqmr)
    mesh = gamemesh.unwrap(mesh)                        # UV charts + packing (xatlas)
    W, J = gamemesh.weights(mesh, prims, skeleton)      # skin weights over the skeleton's joints
    tex = gamemesh.bake(mesh, prims, paints, field)     # per-texel paint * SDF ambient occlusion

Prims are world-space (identity bind) with Prim.bone naming the skeleton joint that owns them (sforge.footballer).
Everything is numpy + three pip wheels (scikit-image, pyfqmr, xatlas); no compiler, no Blender."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from . import sculpt as SC


@dataclass
class GameMesh:
    V: np.ndarray                # (n,3) bind-pose world
    F: np.ndarray                # (m,3)
    N: np.ndarray = None         # (n,3)
    UV: np.ndarray = None        # (n,2) in [0,1], v down (glTF)


class Field:
    """the union SDF sampled on a grid (for AO and fast lookups)"""
    def __init__(self, D, origin, h):
        self.D, self.o, self.h = D, np.asarray(origin, float), h

    def __call__(self, P):
        g = (P - self.o) / self.h
        i0 = np.clip(np.floor(g).astype(int), 0, np.array(self.D.shape) - 2)
        t = np.clip(g - i0, 0, 1)
        D = self.D
        out = 0.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (t[:, 0] if dx else 1 - t[:, 0]) * (t[:, 1] if dy else 1 - t[:, 1]) * (t[:, 2] if dz else 1 - t[:, 2])
                    out = out + w * D[i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz]
        return out


def _ident(prims):
    I = np.eye(4)
    return {p.bone: I for p in prims}


def surface(prims, h=0.005, layer_k=None, log=print):
    """-> (GameMesh, Field).  All layers are unioned: garments sit on the body as one closed skin."""
    from skimage.measure import marching_cubes
    lk = dict(SC.LAYER_K); lk.update(LAYER_K)
    lk.update(layer_k or {})
    inv = _ident(prims)
    lo = np.full(3, 9.0); hi = np.full(3, -9.0)
    for p in prims:
        a, c = SC._prim_world_aabb(p, inv); lo = np.minimum(lo, a); hi = np.maximum(hi, c)
    lo -= 0.03; hi += 0.03
    shape = tuple(np.ceil((hi - lo) / h).astype(int) + 1)
    D = SC._field(prims, lk, lo, shape, h, inv, inv)
    v, f, n, _ = marching_cubes(D, 0.0, spacing=(h, h, h))
    v = v + lo
    f = orient(v, f.astype(np.int64))
    log("  surface: grid %s, %d verts, %d tris" % (shape, len(v), len(f)))
    return GameMesh(v, f, vertex_normals(v, f)), Field(D, lo, h)


def signed_volume(V, F):
    return float(np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]])).sum() / 6.0)


def orient(V, F):
    """counter-clockwise outward (glTF front faces): flip the winding if the enclosed volume comes out negative"""
    return F[:, ::-1].copy() if signed_volume(V, F) < 0 else F


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def decimate(m: GameMesh, tris=20000, aggressiveness=7):
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(m.V.astype(np.float64), m.F.astype(np.int32))
    s.simplify_mesh(target_count=int(tris), aggressiveness=aggressiveness, preserve_border=True, verbose=False)
    V, F, _ = s.getMesh()
    return GameMesh(np.asarray(V, float), np.asarray(F, np.int64), vertex_normals(np.asarray(V, float), np.asarray(F, np.int64)))


def unwrap(m: GameMesh, resolution=1024, padding=6):
    import xatlas
    atlas = xatlas.Atlas()
    atlas.add_mesh(m.V.astype(np.float32), m.F.astype(np.uint32), m.N.astype(np.float32))
    co = xatlas.ChartOptions(); co.max_iterations = 2
    po = xatlas.PackOptions(); po.resolution = resolution; po.padding = padding; po.bilinear = True; po.bruteForce = False
    atlas.generate(co, po)
    vmap, F, UV = atlas[0]
    return GameMesh(m.V[vmap], F.astype(np.int64), m.N[vmap], UV.astype(np.float64)), vmap


# ------------------------------------------------------------------ skin weights
def _segments(sk):
    """bone -> (start, end) segment used for distance weights"""
    seg = {}
    kids = {}
    for n in sk.names:
        p = sk.parent.get(n)
        if p:
            kids.setdefault(p, []).append(n)
    pref = {"pelvis": "spine_01", "spine_03": "neck_01", "clavicle_l": "upperarm_l", "clavicle_r": "upperarm_r",
            "hand_l": "middle_01_l", "hand_r": "middle_01_r", "foot_l": "ball_l", "foot_r": "ball_r"}
    for n in sk.names:
        A = sk.p(n)
        c = pref.get(n) or (kids.get(n) or [None])[0]
        if c:
            seg[n] = (A, sk.p(c))
        else:
            p = sk.parent.get(n)
            d = A - sk.p(p) if p else np.array([0, 0.1, 0])
            L = {"head": 0.20}.get(n, np.linalg.norm(d) * 0.8)
            d = d / (np.linalg.norm(d) + 1e-9) if n != "head" else np.array([0, 1.0, 0])
            seg[n] = (A, A + d * L)
    return seg, kids


def _seg_dist(P, A, B):
    ab = B - A; t = np.clip(((P - A) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(P - (A + t[:, None] * ab), axis=1), t


LAYER_ORDER = ("skin", "jersey", "shorts", "socks", "boots", "hair")    # later = on top
LAYER_K = {"jersey": 0.045, "shorts": 0.045, "socks": 0.008, "boots": 0.008, "hair": 0.012}


def layer_owners(P, prims, layer_k=None, eps=0.002):
    """which LAYER each surface point belongs to (smooth-unioned per layer exactly like the meshing), then the
    nearest prim inside that layer -> prim index.  The top-most layer within eps of its own surface wins."""
    lk = dict(SC.LAYER_K); lk.update(LAYER_K); lk.update(layer_k or {})
    layers = [l for l in LAYER_ORDER if any(p.layer == l for p in prims)] + \
             sorted({p.layer for p in prims} - set(LAYER_ORDER))
    best_layer = np.full(len(P), -1); best_d = np.full(len(P), 1e9)
    near_prim = np.zeros(len(P), np.int64)
    per_layer_prim = {}
    for li, L in enumerate(layers):
        F = np.full(len(P), 1.0); bestp = np.full(len(P), 1e9); bi = np.zeros(len(P), np.int64)
        for i, p in enumerate(prims):
            if p.layer != L:
                continue
            d = SC.prim_sdf(p, P)
            if p.sub:
                F = np.maximum(F, -d); continue
            F = SC.smin(F, d, lk.get(L, 0.01))
            m = np.abs(d) < bestp
            bestp[m] = np.abs(d)[m]; bi[m] = i
        per_layer_prim[li] = bi
        ad = np.abs(F)
        win = (ad < eps) | (ad < best_d - 1e-9)
        win &= ~((best_d < eps) & (ad >= eps))           # an upper layer must actually be on the surface to win
        best_layer[win] = li; best_d[win] = ad[win]
        near_prim[win] = bi[win]
    return near_prim

def owners(P, prims, eps=0.0025):
    """index of the prim each point lies on: the top-most layer whose surface is within eps wins (clean garment
    edges); otherwise the prim with the smallest |sdf|.  Subtractive prims never own."""
    best = np.full(len(P), 1e9); own = np.zeros(len(P), np.int64)
    top = np.full(len(P), -1); top_own = np.zeros(len(P), np.int64); top_d = np.full(len(P), 1e9)
    rank = {l: i for i, l in enumerate(LAYER_ORDER)}
    for i, p in enumerate(prims):
        if p.sub:
            continue
        d = np.abs(SC.prim_sdf(p, P))
        m = d < best
        best[m] = d[m]; own[m] = i
        r = rank.get(p.layer, 0)
        near = d < eps
        win = near & ((r > top) | ((r == top) & (d < top_d)))
        top[win] = r; top_own[win] = i; top_d[win] = d[win]
    return np.where(top >= 0, top_own, own)


def weights(m: GameMesh, prims, sk, power=5.0, smooth_iters=4, max_inf=4):
    """inverse-distance weights to bone segments over the owner bone, its parent and its children, then smoothed
    over the mesh (so shoulders, hips and knees blend) -> (joints (n,4) int, weights (n,4) float)"""
    seg, kids = _segments(sk)
    idx = {n: i for i, n in enumerate(sk.names)}
    own = layer_owners(m.V, prims, eps=0.004)
    obone = np.array([prims[o].bone for o in own])
    n = len(m.V); nb = len(sk.names)
    Wt = np.zeros((n, nb), np.float32)
    for b in set(obone.tolist()):
        sel = np.nonzero(obone == b)[0]
        cand = {b}
        if sk.parent.get(b):
            cand.add(sk.parent[b])
        cand.update(kids.get(b, []))
        # finger chains and the palm stay inside the hand
        if b.startswith(("spine", "pelvis", "neck")):
            cand.update(x for x in sk.names if x.startswith(("spine", "neck", "pelvis", "clavicle")))
        P = m.V[sel]
        for c in cand:
            if c not in seg:
                continue
            d, _ = _seg_dist(P, *seg[c])
            w = 1.0 / np.maximum(d, 0.004) ** power
            if c != b:
                w *= 0.75
            Wt[sel, idx[c]] += w
    Wt /= Wt.sum(1, keepdims=True) + 1e-12
    # smooth over the mesh, keeping each vertex's candidate set
    mask = Wt > 0
    nbr_sum = np.zeros_like(Wt); cnt = np.zeros(n, np.float32)
    E = np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]])
    for _ in range(smooth_iters):
        nbr_sum[:] = 0; cnt[:] = 0
        np.add.at(nbr_sum, E[:, 0], Wt[E[:, 1]]); np.add.at(nbr_sum, E[:, 1], Wt[E[:, 0]])
        np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1)
        Wn = 0.5 * Wt + 0.5 * nbr_sum / np.maximum(cnt, 1)[:, None]
        Wn = np.where(mask | (Wn > 0.02), Wn, 0)
        Wt = Wn / (Wn.sum(1, keepdims=True) + 1e-12)
    top = np.argsort(-Wt, axis=1)[:, :max_inf]
    tw = np.take_along_axis(Wt, top, 1)
    tw[tw < 0.01] = 0
    tw = tw / np.maximum(tw.sum(1, keepdims=True), 1e-9)
    top = np.where(tw > 0, top, 0)                 # glTF: unused influence slots carry joint 0 (validator-clean)
    return top.astype(np.uint16), tw.astype(np.float32), own


# ------------------------------------------------------------------ texture bake
def raster_uv(m: GameMesh, res):
    """rasterise the UV layout: per texel -> triangle id, barycentrics"""
    from .render_sculpt import rasterise
    sx = m.UV[:, 0] * res; sy = m.UV[:, 1] * res
    tid, bc, _ = rasterise(sx, sy, np.zeros(len(sx)), m.F, res, res, K=10)
    return tid, bc


def sdf_ao(field, P, N, steps=(0.008, 0.018, 0.032, 0.05, 0.075), k=1.1):
    """ambient occlusion from the distance field (Quilez): how much nearer the surface is than expected along n"""
    occ = np.zeros(len(P)); w = 1.0
    for d in steps:
        occ += w * np.clip(d - field(P + N * d), 0, None) / d
        w *= 0.6
    return np.clip(1 - k * occ / 2.0, 0.25, 1.0)


def dilate(img, valid, iters=8):
    """fill every empty texel with the nearest painted one (bilinear + mipmap bleed guard)"""
    from scipy.ndimage import distance_transform_edt
    _, (iy, ix) = distance_transform_edt(~valid, return_indices=True)
    return img[iy, ix]


def _dilate_old(img, valid, iters=8):
    from scipy.ndimage import grey_dilation
    img = img.copy(); v = valid.copy()
    for _ in range(iters):
        if v.all():
            break
        acc = np.zeros_like(img); cnt = np.zeros(v.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sv = np.roll(np.roll(v, dy, 0), dx, 1); si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sv[..., None]; cnt += sv
        new = (~v) & (cnt > 0)
        img[new] = acc[new] / cnt[new][:, None]
        v = v | new
    return img


@dataclass
class BakeData:
    tid: np.ndarray
    P: np.ndarray       # texel bind positions
    N: np.ndarray
    own: np.ndarray     # owner prim per texel
    ao: np.ndarray
    idx: tuple


def bake_prepare(m: GameMesh, prims, field, res=1024, log=print):
    tid, bc = raster_uv(m, res)
    idx = np.nonzero(tid >= 0)
    t = tid[idx]; b = bc[idx]
    vi = m.F[t]
    P = (m.V[vi] * b[..., None]).sum(1)
    N = (m.N[vi] * b[..., None]).sum(1); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    # project texels onto the true (pre-decimation) surface so paints see exact positions
    for _ in range(2):
        d = field(P)
        P = P - N * d[:, None]
    own = layer_owners(P, prims)
    ao = sdf_ao(field, P, N)
    log("  bake: %d texels of %d (%.0f%% of the atlas)" % (len(t), res * res, 100.0 * len(t) / (res * res)))
    return BakeData(tid, P, N, own, ao, idx)


def bake(bd: BakeData, prims, paints, res=1024, ao_strength=0.85):
    names = sorted({p.paint for p in prims})
    rgb = np.zeros((len(bd.P), 3))
    pnt = np.array([prims[o].paint for o in bd.own])
    for nme in names:
        sel = pnt == nme
        if not sel.any():
            continue
        c, _ = paints[nme].fn(bd.P[sel], np.zeros((sel.sum(), 3)))
        rgb[sel] = c
    rgb = rgb * (1 - ao_strength + ao_strength * bd.ao)[:, None]
    img = np.zeros((res, res, 3)); valid = np.zeros((res, res), bool)
    img[bd.idx] = np.clip(rgb, 0, 1); valid[bd.idx] = True
    return dilate(img, valid)
