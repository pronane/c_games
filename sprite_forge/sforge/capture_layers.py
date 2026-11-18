"""forge.py capture - clothes and hair layers over the fitted body (v11.1).

The body is fitted tight (capture_fit: loose clothes may stand off it). What the person wears and their hair are
then separate layers, so a long jumper or a hoodie no longer makes the body fat, and long hair hangs behind the
head instead of being painted on the skull:

  clothes   the body's faces that the video shows as clothes (MediaPipe's label, voted over every frame that sees
            the vertex), copied and pushed out along the normal by a per-bone offset (torso low / high, upper arm,
            forearm, thigh, shin) fitted to the silhouettes. Skinned with the body's own weights - it moves with it.
  skirt     when clothes fill the gap between the legs (a dress, a long jumper, a coat), a tube from the hips to a
            fitted hem height, its section the outline of the legs at each height plus a fitted flare. Skinned to the
            pelvis at the top, to each thigh by side lower down.
  hair      the scalp (head vertices the video labels hair) as a shell of fitted thickness, plus, when the hair
            reaches below the chin, a curtain behind the head and shoulders to the fitted length. Skinned to the head,
            then the neck and upper spine lower down.

All layers share ONE texture atlas (2x the body's texture size): body in the top-left quarter (its
own MakeHuman UVs), clothes top-right (same UVs), skirt bottom-left and hair bottom-right (cylindrical UVs). One
texture is what every engine, Blender and the OBJ format take without fuss. In the GLB / FBX each layer is its own
named mesh (Body / Clothes / Skirt / Hair) on the one skeleton, sharing the atlas material - hide the clothes in
Blender and the fitted body is underneath; in the OBJ each layer is an `o` / `g` group."""
from __future__ import annotations
import os
import numpy as np
from PIL import Image

from .capture_texture import vertex_normals
from .render_sculpt import rasterise

# atlas quarters (u0, v0) in OBJ convention (v up): body top-left, clothes top-right, skirt bottom-left, hair bottom-right
QUARTER = {"body": (0.0, 0.5), "clothes": (0.5, 0.5), "skirt": (0.0, 0.0), "hair": (0.5, 0.0)}
LAYER_ID = {"body": 0, "clothes": 1, "skirt": 2, "hair": 3}
SKIRT_BONES = ("root", "spine05", "pelvis.L", "pelvis.R", "upperleg01.L", "upperleg01.R", "lowerleg01.L", "lowerleg01.R")
GARMENT_GROUPS = {
    "torso_low": ("root", "spine05", "spine04", "pelvis.L", "pelvis.R"),
    "torso_high": ("spine03", "spine02", "spine01", "clavicle.L", "clavicle.R", "neck01"),
    "upperarm": ("upperarm01.L", "upperarm01.R"),
    "forearm": ("lowerarm01.L", "lowerarm01.R", "wrist.L", "wrist.R"),
    "thigh": ("upperleg01.L", "upperleg01.R"),
    "shin": ("lowerleg01.L", "lowerleg01.R", "foot.L", "foot.R"),
}


# how far a garment may stand off the body (m): a jumper or a coat round the torso, sleeves and trouser legs less
# (an arm hanging against dark trousers can be voted "clothes" - a big sleeve offset then grows spikes)
OFFSET_MAX = {"torso_low": 0.12, "torso_high": 0.10, "upperarm": 0.03, "forearm": 0.03, "thigh": 0.06, "shin": 0.05}


class Mesh:
    """a skinned, UV-mapped triangle mesh in rest pose (metres, Y up) + per-vertex layer id"""

    def __init__(self, V, F, fuv, J, W, layer):
        self.V, self.F, self.fuv, self.J, self.W, self.layer = V, F, fuv, J, W, layer

    def pose(self, S):
        """S: (bones, 3, 4) skinning matrices from Shape.pose"""
        Vh = np.c_[self.V, np.ones(len(self.V))]
        P = np.zeros_like(self.V)
        for k in range(self.J.shape[1]):
            P += self.W[:, k:k + 1] * np.einsum("nij,nj->ni", S[self.J[:, k]], Vh)
        return P


def merge(parts):
    V, F, fuv, J, W, L = [], [], [], [], [], []
    off = 0
    for m in parts:
        V.append(m.V); F.append(m.F + off); fuv.append(m.fuv); J.append(m.J); W.append(m.W); L.append(m.layer)
        off += len(m.V)
    return Mesh(np.concatenate(V), np.concatenate(F), np.concatenate(fuv), np.concatenate(J), np.concatenate(W),
                np.concatenate(L))


def to_quarter(fuv, name):
    u0, v0 = QUARTER[name]
    out = fuv * 0.5
    out[..., 0] += u0; out[..., 1] += v0
    return out


# ------------------------------------------------------------------ labels per vertex
def vertex_labels(fitter, P, F, frames, log=print):
    """per vertex: votes for hair / skin / face / clothes from every frame that sees it (z-buffer)"""
    import cv2
    votes = np.zeros((len(P), 6), np.float32)
    Nv = vertex_normals(P, F)
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        lab = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
        H, W = lab.shape
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv)
        K = fitter.cams.K(r["size"])
        Pc = P @ R.T + tv
        sx = Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]; sy = Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]
        _, _, zb = rasterise(sx, sy, -Pc[:, 2], F, W, H, K=6)
        zb = zb.reshape(H, W)
        xi = np.clip(np.round(sx - 0.5).astype(int), 0, W - 1); yi = np.clip(np.round(sy - 0.5).astype(int), 0, H - 1)
        inb = (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
        vis = inb & (np.abs(-Pc[:, 2] - zb[yi, xi]) < 0.02)
        facing = np.clip(-((Nv @ R.T) * (Pc / np.linalg.norm(Pc, axis=1, keepdims=True))).sum(1), 0, 1)
        w = np.where(vis, facing, 0.0)
        np.add.at(votes, (np.arange(len(P)), lab[yi, xi].astype(int).clip(0, 5)), w)
    return votes


# ------------------------------------------------------------------ clothes
def garment_offsets(bm, J, W, off):
    """per-vertex outward offset (m) from the per-group offsets"""
    per_bone = np.zeros(len(bm.order))
    for g, bones in GARMENT_GROUPS.items():
        for b in bones:
            if b in bm.bi:
                per_bone[bm.bi[b]] = off.get(g, 0.0)
    return (W * per_bone[J]).sum(1)


HEMS = {}


def clothes_faces(bm, votes, min_share=0.5, shape=None, log=print):
    """body faces worn by clothes: their vertices are voted clothes, grown by one ring to close small gaps; hands,
    feet and the head never (a sleeve stops at the wrist, a collar at the neck).
    v11.7 (shape given): on the arms and legs the garment is a tube from the shoulder / hip down to one clean hem,
    the same height left and right (capture_rings); lower bands (socks) stay paint on the body."""
    tot = votes[:, 1:5].sum(1) + 1e-6
    cl = votes[:, 4] / tot > min_share
    HEMS.clear()
    if shape is not None:
        from . import capture_rings as CR
        limb, sc = CR.limb_coords(shape.head, shape.V, bm.J[:, 0], bm.bi)
        has = votes[:, 1:5].sum(1) > 1e-3
        mat = np.where(has, cl.astype(int), -1)
        ring, _, _ = CR.segment(limb, sc, mat, 2, which=(0, 1, 2, 3),
                                weight=np.minimum(tot, np.percentile(tot[has], 90)) if has.any() else None)
        hems = []
        for pair in (CR.ARMS, CR.LEGS):
            on = np.isin(limb, pair)
            if not on.any():
                continue
            # the tube runs from s = 0 to the first change from clothes to bare
            order = np.argsort(sc[on]); ss = sc[on][order]; rr = ring[on][order]
            if rr[0] != 1:
                hem = 0.0
            else:
                off = np.nonzero(rr != 1)[0]
                hem = float(ss[off[0]]) if len(off) else float(ss[-1]) + 1.0
            cl[on] = sc[on] < hem
            hems.append(hem)
            HEMS[pair] = hem
        if hems:
            log("layers: sleeves end %.0f cm down the arm, trouser legs %.0f cm down the leg (both sides)" % (
                100 * min(hems[0], 9.99), 100 * min(hems[-1], 9.99)))
    never = [bm.bi[b] for b in ("head", "neck01", "wrist.L", "wrist.R", "foot.L", "foot.R", "toe1-1.L", "toe1-1.R")
             if b in bm.bi]
    hard = np.isin(bm.J[:, 0], never) & (bm.W[:, 0] > 0.5)
    if shape is not None and "neck01" in bm.bi:
        # v11.7: a collar. The base of the neck may be worn, as one ring from the bottom of the neck up to the
        # height most of the views agree on (at most 6 cm): a shirt or jumper collar, a hood's rim
        from . import capture_rings as CR
        nk = (bm.J[:, 0] == bm.bi["neck01"]) & (bm.W[:, 0] > 0.5)
        has = votes[:, 1:5].sum(1) > 1e-3
        if (nk & has).sum() > 20:
            y = shape.V[:, 1] - shape.V[nk, 1].min()
            bins = np.clip((y / 0.005).astype(int), 0, 400)
            nb = int(bins[nk].max()) + 1
            H = np.zeros((nb, 2))
            ev = nk & has
            np.add.at(H, (bins[ev], cl[ev].astype(int)), 1.0)
            tot_b = H.sum(1, keepdims=True)
            lab = CR.viterbi(tot_b - H, 0.6 * float(np.median(tot_b[tot_b > 0])))
            h = 0.0
            if lab[0] == 1:
                off = np.nonzero(lab != 1)[0]
                h = min(0.06, (off[0] if len(off) else nb) * 0.005)
            collar = nk & (y < h)
            hard &= ~collar
            cl[collar] = True
            if h > 0:
                log("layers: a collar %.1f cm up the neck" % (100 * h))
    cl &= ~hard
    F = bm.F
    fsel = cl[F].sum(1) >= 2
    grow = np.zeros(len(cl), bool); grow[F[fsel].ravel()] = True
    fsel = (grow[F].sum(1) >= 2) & ~hard[F].any(1)
    return fsel


def build_clothes(shape, fsel, off, lift=0.004):
    bm = shape.m
    F = bm.F[fsel]
    used = np.unique(F)
    remap = -np.ones(len(shape.V), int); remap[used] = np.arange(len(used))
    N = vertex_normals(shape.V, bm.F)
    d = garment_offsets(bm, bm.J, bm.W, off)[used] + lift
    V = shape.V[used] + N[used] * d[:, None]
    if HEMS:
        # v11.7: the hem is one ring - vertices of the tube's last row past it are slid back along the limb to it,
        # so the edge is straight, not the saw-tooth of whole triangles
        from . import capture_rings as CR
        limb, sc = CR.limb_coords(shape.head, shape.V[used], bm.J[used, 0], bm.bi)
        for pair, hem in HEMS.items():
            if hem <= 0 or hem > 5:
                continue
            for k in pair:
                sel = (limb == k) & (sc > hem)
                if not sel.any():
                    continue
                Q = CR._polyline(shape.head, bm.bi, CR.CHAINS[k])
                # direction of the limb at the hem
                seg = np.cumsum(np.r_[0, np.linalg.norm(np.diff(Q, axis=0), axis=1)])
                i = int(np.clip(np.searchsorted(seg, hem) - 1, 0, len(Q) - 2))
                ax = (Q[i + 1] - Q[i]) / (np.linalg.norm(Q[i + 1] - Q[i]) + 1e-9)
                V[sel] -= (sc[sel] - hem)[:, None] * ax[None, :]
    return Mesh(V, remap[F], to_quarter(bm.fuv[fsel], "clothes"), bm.J[used], bm.W[used], np.full(len(used), 1))


# ------------------------------------------------------------------ skirt
def _hull_radii(dx, dz, ang):
    """radius of the convex hull of points (dx, dz) round the origin, along each angle (atan2(x, z))"""
    import cv2
    pts = np.c_[dx, dz].astype(np.float32)
    if len(pts) < 3:
        return np.full(len(ang), 0.05)
    h = cv2.convexHull(pts)[:, 0].astype(float)
    t = np.linspace(0, 1, 24, endpoint=False)
    dense = np.concatenate([h[i] + (h[(i + 1) % len(h)] - h[i]) * t[:, None] for i in range(len(h))])
    a = np.arctan2(dense[:, 0], dense[:, 1]); r = np.hypot(dense[:, 0], dense[:, 1])
    o = np.argsort(a)
    return np.interp(np.arctan2(np.sin(ang), np.cos(ang)), a[o], r[o], period=2 * np.pi)


def _lbs_matrices(J, W, S):
    """per-vertex blended skinning matrix (n, 3, 4)"""
    A = np.zeros((len(J), 3, 4))
    for k in range(J.shape[1]):
        A += W[:, k, None, None] * S[J[:, k]]
    return A


def build_skirt(shape, hem_drop, flare, top_y=None, n_ang=40, n_rows=12, extra=None, S=None):
    """a tube round both legs from just below the crotch down `hem_drop` metres; section at each height = the legs'
    (and their clothes') outline in that slab, convex, plus `flare` x depth-down (m).
    S: the skinning matrices of the pose the person stands in - the rings are then built round the POSED legs and
    un-skinned back to the rest pose, so no leg pokes through the skirt in that pose"""
    bm = shape.m
    # only the hips and legs set the section (the hands hang at hip height in the rest pose)
    legs = np.array([bm.bi[b] for b in SKIRT_BONES if b in bm.bi])
    sel = np.isin(bm.J[:, 0], legs)
    V = shape.V[sel]
    if S is not None:
        A = _lbs_matrices(bm.J[sel], bm.W[sel], S)
        V = np.einsum("nij,nj->ni", A, np.c_[V, np.ones(len(V))])
    if extra is not None:
        ex = np.isin(extra.J[:, 0], legs)
        V = np.vstack([V, (extra.pose(S) if S is not None else extra.V)[ex]])
    def joint_y(b):
        j = np.r_[shape.joint(b), 1.0]
        return float((S[bm.bi[b]] @ j)[1]) if S is not None else float(j[1])
    crotch = 0.5 * (joint_y("upperleg01.L") + joint_y("upperleg01.R")) - 0.06
    y0 = crotch + 0.10 if top_y is None else top_y
    y1 = crotch - hem_drop
    rows, ring_r = [], []
    cx = float(np.median(V[:, 0])); cz = float(np.median(V[np.abs(V[:, 1] - crotch) < 0.1, 2]))
    ang = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    for k in range(n_rows):
        y = y0 + (y1 - y0) * k / (n_rows - 1)
        sl = V[np.abs(V[:, 1] - y) < 0.025]
        if len(sl) < 8:
            sl = V[np.abs(V[:, 1] - y) < 0.06]
        r_ring = _hull_radii(sl[:, 0] - cx, sl[:, 2] - cz, ang)      # convex: a skirt bridges the legs
        drop = max(0.0, crotch + 0.02 - y)
        rows.append(y); ring_r.append(r_ring + 0.010 + flare * drop)
    P = []
    for y, rr in zip(rows, ring_r):
        for t, r_ in zip(ang, rr):
            P.append([cx + r_ * np.sin(t), y, cz + r_ * np.cos(t)])
    P = np.array(P)
    F = []
    for k in range(n_rows - 1):
        for i in range(n_ang):
            a = k * n_ang + i; b = k * n_ang + (i + 1) % n_ang
            c = (k + 1) * n_ang + i; d = (k + 1) * n_ang + (i + 1) % n_ang
            F += [[a, c, b], [b, c, d]]
    F = np.array(F)
    # outward-facing (every renderer culls back faces)
    nrm = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    rad = P[F].mean(1) - [cx, 0, cz]; rad[:, 1] = 0
    if float((nrm * rad).sum(1).mean()) < 0:
        F = F[:, [0, 2, 1]]
    # UVs: angle across, height down (wrap seam duplicated by face-corner UVs)
    uvv = np.c_[np.tile(np.arange(n_ang) / n_ang, n_rows), 1 - np.repeat(np.arange(n_rows) / (n_rows - 1), n_ang)]
    fuv = uvv[F].copy()
    wrap = (fuv[:, :, 0].max(1) - fuv[:, :, 0].min(1)) > 0.5
    fuv[wrap] = np.where(fuv[wrap][..., :1] < 0.5, fuv[wrap] + [1.0, 0], fuv[wrap])
    fuv[..., 0] *= n_ang / (n_ang + 1.0)
    # skin: pelvis at the waist, thighs by side lower down
    root = bm.bi["root"]; tl = bm.bi["upperleg01.L"]; tr = bm.bi["upperleg01.R"]
    J = np.zeros((len(P), 4), int); W = np.zeros((len(P), 4))
    side = np.clip((P[:, 0] - cx) / 0.08, -1, 1) * 0.5 + 0.5           # 1 = person's left (+X)
    down = np.clip((y0 - P[:, 1]) / max(1e-3, y0 - y1), 0, 1)
    J[:, 0], J[:, 1], J[:, 2] = root, tl, tr
    W[:, 0] = 1 - 0.75 * down; W[:, 1] = 0.75 * down * side; W[:, 2] = 0.75 * down * (1 - side)
    if S is not None:                                                # posed rings -> rest pose (inverse skinning)
        A = _lbs_matrices(J, W, S)
        P = np.einsum("nij,nj->ni", np.linalg.inv(A[:, :, :3]), P - A[:, :, 3])
    return Mesh(P, F, to_quarter(fuv, "skirt"), J, W, np.full(len(P), 2))


# ------------------------------------------------------------------ hair
def _pieces(F):
    """piece id per face, faces joined only through shared edges (two caps touching at one vertex are two
    pieces); ids by size, 0 the largest"""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    nf = len(F)
    if nf < 2:
        return np.zeros(nf, int)
    e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    fid = np.tile(np.arange(nf), 3)
    key = e[:, 0].astype(np.int64) * (int(F.max()) + 1) + e[:, 1]
    o = np.argsort(key, kind="stable"); key, fid = key[o], fid[o]
    same = np.nonzero(key[1:] == key[:-1])[0]
    G = sp.coo_matrix((np.ones(len(same)), (fid[same], fid[same + 1])), (nf, nf))
    _, comp = connected_components(G, directed=False)
    order = np.argsort(-np.bincount(comp), kind="stable")
    rank = np.empty_like(order); rank[order] = np.arange(len(order))
    return rank[comp]


def _main_piece(F):
    """mask of the faces in the largest edge-joined piece"""
    return _pieces(F) == 0


def _clean_piece(F, keep):
    """keep (a mask of F) less the triangles at any vertex where the rim touches itself (two rims through one
    point cannot both be laid round one circle), and less anything that cuts off"""
    from collections import Counter
    keep = keep.copy()
    for _ in range(6):
        idx = np.nonzero(keep)[0]
        if len(idx) < 2:
            break
        cnt = Counter(tuple(sorted(e)) for f in F[idx] for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])))
        deg = Counter(v for e, c in cnt.items() if c == 1 for v in e)
        pinch = [v for v, k in deg.items() if k > 2]
        if not pinch:
            break
        keep[idx[np.isin(F[idx], pinch).any(1)]] = False
        sub = np.nonzero(keep)[0]
        if len(sub) < 2:
            break
        keep[:] = False; keep[sub[_main_piece(F[sub])]] = True
    return keep


def _cap(F, min_faces=20, min_share=0.05):
    """mask of the shell's faces worth keeping: each edge-joined piece of at least min_faces triangles and
    min_share of the shell, cleaned of rim pinches. A shell can come in two pieces (the crown and the back of the
    head, with a row of skin votes between): both are kept, each laid out on its own"""
    pid = _pieces(F)
    keep = np.zeros(len(F), bool)
    for k in range(int(pid.max()) + 1 if len(pid) else 0):
        m = pid == k
        if m.sum() < max(min_faces, min_share * len(F)):
            break
        keep |= _clean_piece(F, m)
    return keep


def _boundary_loop(F):
    """the longest boundary loop of a triangle mesh (vertex ids in order), or None"""
    from collections import Counter, defaultdict
    cnt = Counter(tuple(sorted(e)) for f in F for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])))
    nxt = defaultdict(list)
    for (i, j), c in cnt.items():
        if c == 1:
            nxt[i].append(j); nxt[j].append(i)
    seen, best = set(), None
    for s0 in list(nxt):
        if s0 in seen:
            continue
        loop, prev, cur = [s0], None, s0
        seen.add(s0)
        while True:
            cand = [v for v in nxt[cur] if v != prev and (v not in seen or (v == s0 and len(loop) > 2))]
            if not cand:
                break
            prev, cur = cur, cand[0]
            if cur == s0:
                break
            loop.append(cur); seen.add(cur)
        if best is None or len(loop) > len(best):
            best = loop
    return best if best is not None and len(best) >= 3 else None


def _azimuthal(Vs, c):
    """the head's own angles as a disc: the angle down from the top of the head is the distance from the centre,
    the direction round it the angle round the head (0 = the front, at the top of the map)"""
    d = Vs - c
    ph = np.arctan2(d[:, 0], d[:, 2])
    th = np.arccos(np.clip(d[:, 1] / (np.linalg.norm(d, axis=1) + 1e-12), -1, 1))
    r = th / max(float(th.max()) * 1.02, 1e-6)
    return np.c_[r * np.sin(ph), r * np.cos(ph)]


def _lay_piece(Vs, Fp, c):
    """one piece of the shell (faces Fp, a disc topologically) -> per-vertex positions in the unit disc (NaN
    off the piece), no triangle folded. Starts from the head's own angles, so the texels spread about as they do
    on the head; where that folds (the hollow over an ear, the back of the head below its widest point) the
    vertices round the fold are laid out again with mean-value weights (Floater - all positive), the rest held,
    the patch growing until nothing folds. A piece that still folds has its rim laid on a circle and everything
    inside by the mean-value weights: always one-to-one"""
    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve
    n = len(Vs)
    onv = np.zeros(n, bool); onv[np.unique(Fp)] = True
    xy = np.full((n, 2), np.nan)
    az = _azimuthal(Vs, c)
    loop = _boundary_loop(Fp)
    ii, jj, ww = [], [], []
    for k in range(3):
        i, j, l = Fp[:, k], Fp[:, (k + 1) % 3], Fp[:, (k + 2) % 3]
        e1 = Vs[j] - Vs[i]; e2 = Vs[l] - Vs[i]
        n1 = np.linalg.norm(e1, axis=1) + 1e-12; n2 = np.linalg.norm(e2, axis=1) + 1e-12
        t = np.tan(0.5 * np.arccos(np.clip((e1 * e2).sum(1) / (n1 * n2), -1, 1)))
        ii += [i, i]; jj += [j, l]; ww += [t / n1, t / n2]
    W = sp.coo_matrix((np.concatenate(ww), (np.concatenate(ii), np.concatenate(jj))), (n, n)).tocsr()
    L = (sp.diags(np.asarray(W.sum(1)).ravel()) - W).tocsr()

    def solve(base, free_):
        out = base.copy()
        if len(free_):
            hold = np.nonzero(onv & ~np.isin(np.arange(n), free_))[0]
            rhs = -(L[free_][:, hold] @ out[hold])
            Lff = L[free_][:, free_].tocsc()
            out[free_] = np.c_[spsolve(Lff, rhs[:, 0]), spsolve(Lff, rhs[:, 1])]
        return out

    def folded(p):
        u = p[Fp]
        ar = (u[:, 1, 0] - u[:, 0, 0]) * (u[:, 2, 1] - u[:, 0, 1]) - (u[:, 2, 0] - u[:, 0, 0]) * (u[:, 1, 1] - u[:, 0, 1])
        bad = ~np.isfinite(ar)
        ar = np.nan_to_num(ar)
        return bad | (np.sign(ar) != np.sign(np.median(ar))) | (np.abs(ar) < 1e-14)

    rim = np.zeros(n, bool)
    if loop is not None:
        rim[loop] = True
    base = np.full((n, 2), np.nan)
    base[onv] = az[onv]
    out, bad = base, folded(base)
    region = np.zeros(n, bool)
    for it in range(8):
        if not bad.any():
            break
        region[np.unique(Fp[bad])] = True
        for _ in range(2):
            region[np.unique(Fp[region[Fp].any(1)])] = True
        fr_ = np.nonzero(region & onv & (~rim if it < 4 else True))[0]       # the rim too, if need be
        if len(fr_) >= onv.sum() - 2:
            break
        out = solve(base, fr_); bad = folded(out)
    if bad.any() and loop is not None:
        loop = np.array(loop)
        seg = np.linalg.norm(np.diff(Vs[np.r_[loop, loop[:1]]], axis=0), axis=1)
        ang = np.r_[0.0, np.cumsum(seg)[:-1]] / max(seg.sum(), 1e-12) * 2 * np.pi
        # the rim the same way round as the head's angles, starting nearest the front
        ph = np.arctan2(az[loop, 0], az[loop, 1])
        if np.sum(np.diff(np.unwrap(ph))) < 0:
            ang = -ang
        circ = np.full((n, 2), np.nan); circ[loop] = np.c_[np.sin(ang), np.cos(ang)]
        out = solve(circ, np.nonzero(onv & ~rim)[0])
    xy[onv] = out[onv]
    # the front of the head at the top and the figure's left on the map's right (a turn and a mirror move no
    # triangle over another)
    on = np.nonzero(onv)[0]
    d = Vs[on] - c
    fr = on[d[:, 2] > 0.02]; lf = on[d[:, 0] > 0.02]; rt = on[d[:, 0] < -0.02]
    if len(lf) and len(rt) and xy[lf, 0].mean() < xy[rt, 0].mean():
        xy[on, 0] = -xy[on, 0]
    if len(fr) and np.linalg.norm(xy[fr].mean(0) - xy[on].mean(0)) > 1e-6:
        f_ = xy[fr].mean(0) - xy[on].mean(0)
        rot = np.arctan2(f_[0], f_[1])
        cR, sR = np.cos(rot), np.sin(rot)
        xy[on] = xy[on] @ np.array([[cR, -sR], [sR, cR]]).T
        if len(lf) and len(rt) and xy[lf, 0].mean() < xy[rt, 0].mean():
            xy[on, 0] = -xy[on, 0]
    # into the unit disc
    ctr = 0.5 * (np.nanmax(xy[on], 0) + np.nanmin(xy[on], 0))
    xy[on] = (xy[on] - ctr) / (np.linalg.norm(xy[on] - ctr, axis=1).max() + 1e-12) * 0.98
    return xy


def shell_uv(Vs, head_pts, F=None):
    """hair shell UVs in the hair quarter's left half (v11.14). Before, the shell was projected straight down onto
    (x, z): below the widest part of the head the back and sides fold under the top in that view, so a fifth of the
    shell's texels were claimed by two triangles in different places - each painted the other's colour, the tiled
    head. Now each piece of the shell (usually one cap) is flattened onto a disc with no triangle folded
    (_lay_piece), the biggest piece given most of the half, the others stacked below it. Faces left off (a sliver
    of a few triangles) are folded into a point in the map's corner.
    -> per-face UVs (len(F), 3, 2); per-vertex UVs from the head's angles alone when F is None"""
    c = np.median(head_pts, 0)
    if F is None:
        xy = _azimuthal(Vs, c)
        return np.c_[0.25 + 0.235 * xy[:, 0], 0.5 + 0.47 * xy[:, 1]]
    fuv = np.zeros((len(F), 3, 2)); fuv[:] = [0.25 - 0.24, 0.5 - 0.49]    # the corner
    keep = _cap(F)
    pid = _pieces(F)
    ids = [k for k in np.unique(pid[keep])]
    if not ids:
        return fuv
    A = np.array([0.5 * np.linalg.norm(np.cross(Vs[F[pid == k][:, 1]] - Vs[F[pid == k][:, 0]],
                                                 Vs[F[pid == k][:, 2]] - Vs[F[pid == k][:, 0]]), axis=1).sum()
                  for k in ids])
    # the half (0.48 wide x 0.95 high in the quarter) cut into bands, one per piece, by area
    h = 0.95 * A / A.sum()
    y0 = 0.975
    for k, hk in zip(ids, h):
        m = keep & (pid == k)
        xy = _lay_piece(Vs, F[m], c)
        rx, ry = 0.235, min(0.47, 0.45 * hk)                               # a gap of a tenth between bands
        cy = y0 - 0.5 * hk
        fuv[m] = np.c_[0.25 + rx * xy[:, 0], cy + ry * xy[:, 1]][F[m]]
        y0 -= hk
    return fuv


def uv_overlap(F, fuv, res=1024):
    """the number of atlas texels claimed by two or more triangles (v11.14). Every texel must belong to one place
    on the body, or the bake paints one place's colour on two"""
    tx = fuv[:, :, 0] * res; ty = (1.0 - fuv[:, :, 1]) * res
    x0 = np.floor(tx.min(1)).astype(int); y0 = np.floor(ty.min(1)).astype(int)
    x1 = np.ceil(tx.max(1)).astype(int); y1 = np.ceil(ty.max(1)).astype(int)
    d = (ty[:, 1] - ty[:, 2]) * (tx[:, 0] - tx[:, 2]) + (tx[:, 2] - tx[:, 1]) * (ty[:, 0] - ty[:, 2])
    ok = np.abs(d) > 1e-12
    cov = np.zeros(res * res, np.int32)
    idx = np.nonzero(ok)[0]
    span = int(max(1, (x1 - x0)[idx].max(initial=1), (y1 - y0)[idx].max(initial=1)))
    for dy in range(span + 1):
        for dx in range(span + 1):
            px = x0[idx] + dx; py = y0[idx] + dy
            m = (px <= x1[idx]) & (py <= y1[idx]) & (px >= 0) & (px < res) & (py >= 0) & (py < res)
            t, px, py = idx[m], px[m], py[m]
            gx, gy = px + 0.5, py + 0.5
            X, Y, dd = tx[t], ty[t], d[t]
            a = ((Y[:, 1] - Y[:, 2]) * (gx - X[:, 2]) + (X[:, 2] - X[:, 1]) * (gy - Y[:, 2])) / dd
            b = ((Y[:, 2] - Y[:, 0]) * (gx - X[:, 2]) + (X[:, 0] - X[:, 2]) * (gy - Y[:, 2])) / dd
            inside = (a > 1e-6) & (b > 1e-6) & (1 - a - b > 1e-6)          # strictly inside: shared edges are fine
            np.add.at(cov, py[inside] * res + px[inside], 1)
    return int((cov > 1).sum())


def build_hair(shape, votes, thick, length, min_share=0.35, n_ang=28, n_rows=10):
    """scalp shell (+ a curtain when `length` reaches below the ears)"""
    bm = shape.m
    hi = bm.bi["head"]
    head = (bm.J[:, 0] == hi) & (bm.W[:, 0] > 0.6)
    tot = votes[:, 1:5].sum(1) + 1e-6
    hairy = head & (votes[:, 1] / tot > min_share)
    # v11.14: one-vertex gaps in the votes (a glint, a frame that saw skin through the hair) closed: a head vertex
    # whose neighbours are mostly hair is hair. A hole in the cap would be a second rim the map cannot lay out
    import scipy.sparse as sp
    e_ = np.r_[bm.F[:, [0, 1]], bm.F[:, [1, 2]], bm.F[:, [2, 0]]]
    A_ = sp.coo_matrix((np.ones(len(e_) * 2), (np.r_[e_[:, 0], e_[:, 1]], np.r_[e_[:, 1], e_[:, 0]])),
                       (len(votes), len(votes))).tocsr()
    A_.data[:] = 1.0
    nd = np.asarray(A_.sum(1)).ravel() + 1e-9
    for _ in range(2):
        hairy = hairy | (head & ((A_ @ hairy.astype(float)) / nd > 0.5))
    V0 = shape.V
    if hairy.sum() < 30:
        # no hair seen (short / shaved): a thin cap over the top of the skull keeps the silhouette honest
        top = V0[head, 1].max()
        hairy = head & (V0[:, 1] > top - 0.06)
    N = vertex_normals(V0, bm.F)
    fsel = hairy[bm.F].all(1)
    # v11.14: one cap - stray islands of hair-voted triangles (a few by an ear, or touching the cap at one vertex)
    # are left off the shell
    if fsel.sum() > 3:
        keep = np.zeros(len(bm.F), bool); keep[np.nonzero(fsel)[0][_cap(bm.F[fsel])]] = True
        fsel = keep
    F = bm.F[fsel]
    used = np.unique(F)
    remap = -np.ones(len(V0), int); remap[used] = np.arange(len(used))
    Vs = V0[used] + N[used] * (thick + 0.002)
    # v11.14: the shell flattened onto a disc (shell_uv) - planar from above folded the back under the top
    shell = Mesh(Vs, remap[F], to_quarter(shell_uv(Vs, V0[head], remap[F]), "hair"), bm.J[used], bm.W[used],
                 np.full(len(used), 3))
    parts = [shell]
    ear_y = float(np.median(V0[head, 1])) - 0.02
    if length > 0.06:
        # curtain: back half-ring from ear height down `length`, following the head / neck / back outline
        cx = float(np.median(V0[head, 0])); cz = float(np.median(V0[head, 2]))
        half_w = 0.5 * float(np.ptp(V0[head, 0])) + thick
        ang = np.linspace(np.radians(100), np.radians(260), n_ang)
        P = []
        rows = [ear_y - length * k / (n_rows - 1) for k in range(n_rows)]
        for y in rows:
            sl = V0[np.abs(V0[:, 1] - y) < 0.03]
            dx, dz = sl[:, 0] - cx, sl[:, 2] - cz
            a = np.arctan2(dx, dz); rr = np.hypot(dx, dz)
            for t in ang:
                near = np.abs(((a - t) + np.pi) % (2 * np.pi) - np.pi) < 0.3
                r_ = rr[near].max(initial=0.08) + thick + 0.006
                x = float(np.clip(r_ * np.sin(t), -half_w, half_w))       # hair hangs within the head's width
                P.append([cx + x, y, cz + r_ * np.cos(t)])
        P = np.array(P)
        Fc = []
        for k in range(n_rows - 1):
            for i in range(n_ang - 1):
                a = k * n_ang + i; b = a + 1; c = a + n_ang; d = c + 1
                Fc += [[a, b, c], [b, d, c]]
        Fc = np.array(Fc)
        uvc = np.c_[0.51 + 0.48 * np.tile(np.arange(n_ang) / (n_ang - 1), n_rows),
                    0.975 - 0.95 * np.repeat(np.arange(n_rows) / (n_rows - 1), n_ang)]
        J = np.zeros((len(P), 4), int); W = np.zeros((len(P), 4))
        down = np.clip((ear_y - P[:, 1]) / max(length, 1e-3), 0, 1)
        J[:, 0] = hi; J[:, 1] = bm.bi["neck01"]; J[:, 2] = bm.bi["spine01"]
        W[:, 0] = 1 - down; W[:, 1] = down * 0.5; W[:, 2] = down * 0.5
        parts.append(Mesh(P, Fc, to_quarter(uvc[Fc], "hair"), J, W, np.full(len(P), 3)))
    return merge(parts)


# ------------------------------------------------------------------ fitting the layers
def hair_length_from_frames(fitter, shape, P, frames):
    """how far below ear height the hair reaches: back-ish frames, the lowest hair-labelled pixel on the body's
    centre line, lifted to body height through the camera"""
    import cv2
    bm = shape.m
    head = (bm.J[:, 0] == bm.bi["head"]) & (bm.W[:, 0] > 0.6)
    ear_y = float(np.median(shape.V[head, 1])) - 0.02
    cx = float(np.median(P[head, 0])); cz = float(np.median(P[head, 2])) - 0.05
    ys = np.linspace(ear_y, ear_y - 0.6, 61)
    best = []
    for r in frames:
        if r["i"] not in fitter.cams.cam or abs(abs(r["yaw"]) - 180) > 60:
            continue
        lab = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
        H, W = lab.shape
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv); K = fitter.cams.K(r["size"])
        pts = np.c_[np.full_like(ys, cx), ys, np.full_like(ys, cz)]
        Pc = pts @ R.T + tv
        u = (Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]).astype(int); v = (Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]).astype(int)
        ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        hair = np.zeros(len(ys), bool)
        for k in np.nonzero(ok)[0]:
            win = lab[max(0, v[k] - 2):v[k] + 3, max(0, u[k] - 6):u[k] + 7]
            hair[k] = (win == 1).mean() > 0.4
        if hair[:3].any():
            run = np.argmax(~hair) if (~hair).any() else len(hair)
            best.append(ear_y - ys[max(0, run - 1)])
    return float(np.median(best)) if best else 0.0


def needs_skirt(fitter, shape, P, frames):
    """clothes between the legs below the crotch in front / back views -> a skirt-like garment"""
    import cv2
    crotch = 0.5 * (shape.joint("upperleg01.L")[1] + shape.joint("upperleg01.R")[1]) - 0.06
    cx = float(np.median(P[:, 0])); cz = float(np.median(P[np.abs(P[:, 1] - crotch) < 0.1, 2]))
    fr = []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        a = abs(((r["yaw"] + 180) % 360) - 180)
        if 30 < a < 150:
            continue
        lab = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv); K = fitter.cams.K(r["size"])
        pts = np.array([[cx, crotch - d, cz] for d in (0.05, 0.10, 0.15)])
        Pc = pts @ R.T + tv
        u = (Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]).astype(int); v = (Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]).astype(int)
        H, W = lab.shape
        vals = [lab[v[k], u[k]] for k in range(3) if 0 <= u[k] < W and 0 <= v[k] < H]
        if vals:
            fr.append(np.mean([x == 4 for x in vals]))
    return (float(np.mean(fr)) if fr else 0.0) > 0.5


def hem_from_frames(fitter, shape, P, frames):
    """how far below the crotch the garment reaches: front / back views, the clothes-labelled run going down the
    body's centre line from the crotch (m; 0 when none)"""
    import cv2
    crotch = 0.5 * (shape.joint("upperleg01.L")[1] + shape.joint("upperleg01.R")[1]) - 0.06
    cx = float(np.median(P[:, 0])); cz = float(np.median(P[np.abs(P[:, 1] - crotch) < 0.1, 2]))
    ds = np.linspace(0.0, 0.8, 81)
    out = []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        a = abs(((r["yaw"] + 180) % 360) - 180)
        if 25 < a < 155:
            continue
        lab = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv); K = fitter.cams.K(r["size"])
        Pc = np.c_[np.full_like(ds, cx), crotch - ds, np.full_like(ds, cz)] @ R.T + tv
        u = (Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]).astype(int); v = (Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]).astype(int)
        H, W = lab.shape
        cl = np.zeros(len(ds), bool)
        for k in range(len(ds)):
            if 0 <= u[k] < W and 0 <= v[k] < H:
                win = lab[max(0, v[k] - 1):v[k] + 2, max(0, u[k] - 4):u[k] + 5]
                cl[k] = (win == 4).mean() > 0.5
        if cl[:4].any():
            run = int(np.argmax(~cl)) if (~cl).any() else len(cl)
            out.append(float(ds[max(0, run - 1)]))
    return float(np.median(out)) if out else 0.0


def dress_like(fitter, shape, P, Pg, frames, hem):
    """is the clothing below the crotch a dress / long jumper / coat rather than shorts or trousers? Median Lab colours
    in the front / back views:
      top   clothes on the centre line 15 cm above the crotch
      mid   clothes on the centre line half way down to the hem
      below the legs (whatever covers them) 10 cm under the hem, on each leg's axis
    One garment from the torso down (top ~ mid) that then ENDS (below differs: skin, tights, leggings) -> True.
    Shorts under a different top (top != mid) or trousers the colour of the top (mid ~ below) -> False."""
    import cv2
    bm = shape.m
    crotch = 0.5 * (shape.joint("upperleg01.L")[1] + shape.joint("upperleg01.R")[1]) - 0.06
    cx = float(np.median(P[:, 0])); cz = float(np.median(P[np.abs(P[:, 1] - crotch) < 0.1, 2]))
    yb = crotch - hem - 0.10

    def on_leg(s):                                            # the leg's axis (hip -> knee -> ankle) at height yb
        A, B, C = (Pg[bm.bi[b + s]] for b in ("upperleg01.", "lowerleg01.", "foot."))
        for X, Y in ((A, B), (B, C)):
            if Y[1] <= yb <= X[1]:
                return X + (Y - X) * (X[1] - yb) / max(1e-6, X[1] - Y[1])
        return None
    legs = [q for q in (on_leg("L"), on_leg("R")) if q is not None]
    top, mid, below = [], [], []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        a = abs(((r["yaw"] + 180) % 360) - 180)
        if 25 < a < 155:
            continue
        lab = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
        img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        if img.shape[:2] != lab.shape:
            img = np.asarray(Image.fromarray(img).resize((lab.shape[1], lab.shape[0])))
        L = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(float)
        pts = [[cx, crotch + 0.15, cz], [cx, crotch - 0.5 * hem, cz]] + [list(q) for q in legs]
        uv = fitter.cams.project(r, np.array(pts)).astype(int)
        H, W = lab.shape
        for k, (u, v) in enumerate(uv):
            if not (0 <= u < W and 0 <= v < H):
                continue
            win = (slice(max(0, v - 4), v + 5), slice(max(0, u - 4), u + 5))
            sel = (lab[win] == 4) if k < 2 else ((lab[win] >= 2) & (lab[win] <= 4))
            if sel.sum() > 10:
                (top if k == 0 else mid if k == 1 else below).append(np.median(L[win][sel], 0))
    # OpenCV 8-bit Lab; lightness counts half (a garment is shaded darker lower down, its colour stays)
    dist = lambda x, y: float(np.linalg.norm((np.median(x, 0) - np.median(y, 0)) * [0.5, 1.0, 1.0]))
    if len(top) < 2 or len(mid) < 2:
        return True
    if dist(top, mid) >= 25.0:
        return False
    return len(below) < 2 or dist(mid, below) >= 25.0


def shod_feet(bm, sh, votes, log=print):
    """v11.8: feet in socks or shoes have no toes. MakeHuman's foot is bare - five modelled toes, which a white
    sock then shows as five white toes. When the video calls the feet something worn (clothes / "other": socks,
    shoes) more than skin, the front of each foot becomes one rounded toe box of the same size.
    -> body vertices (rest pose)"""
    V = sh.V.copy()
    fb = [bm.bi[b] for b in ("foot.L", "foot.R", "toe1-1.L", "toe1-1.R") if b in bm.bi]
    tb = [bm.bi[b] for b in ("toe1-1.L", "toe1-1.R") if b in bm.bi]
    foot = np.isin(bm.J[:, 0], fb) & (bm.W[:, 0] > 0.3)
    if foot.sum() < 50 or not tb:
        return V
    v = votes[foot]
    worn = float(v[:, 4].sum() + v[:, 5].sum()); skin = float(v[:, 2].sum() + v[:, 3].sum())
    if worn <= skin:
        return V
    # the part that moves: the toes and the front half of the foot (ahead of the ball), both feet
    toe = np.isin(bm.J[:, 0], tb) & (bm.W[:, 0] > 0.2)
    ball = np.array([sh.head[b] for b in tb])
    front = foot & (V[:, 2] > (ball[:, 2].min() - 0.03))
    mov = toe | front
    # a toe box: each 5 mm slice across the front of the foot keeps the envelope of the toes (their width and
    # height) and every vertex in it is put on a rounded-rectangle outline of that envelope, at its own angle - the
    # gaps between the toes close, the foot keeps its size. It blends in over the first 2 cm behind the toes
    for side in (1.0, -1.0):
        m = np.nonzero(mov & (np.sign(sh.V[:, 0]) == side))[0]
        if len(m) < 30:
            continue
        P = V[m]
        z0 = P[:, 2].min()
        k = ((P[:, 2] - z0) / 0.005).astype(int)
        nk = int(k.max()) + 1
        ext = np.full((nk, 4), np.nan)                                    # xmin, xmax, ymin, ymax per slice
        for i in range(nk):
            q = P[k == i]
            if len(q):
                ext[i] = [q[:, 0].min(), q[:, 0].max(), q[:, 1].min(), q[:, 1].max()]
        good = ~np.isnan(ext[:, 0])
        for c in range(4):                                                # gaps between slices: interpolate
            ext[:, c] = np.interp(np.arange(nk), np.nonzero(good)[0], ext[good, c])
        sm = ext.copy()
        for i in range(nk):                                               # smooth along the foot
            sm[i] = ext[max(0, i - 1):i + 2].mean(0)
        cx = 0.5 * (sm[k, 0] + sm[k, 1]); ax = 0.5 * (sm[k, 1] - sm[k, 0]) + 1e-4
        cy = 0.5 * (sm[k, 2] + sm[k, 3]); ay = 0.5 * (sm[k, 3] - sm[k, 2]) + 1e-4
        phi = np.arctan2((P[:, 1] - cy) / ay, (P[:, 0] - cx) / ax)
        pw = 4.0                                                          # rounded rectangle (superellipse)
        r = (np.abs(np.cos(phi)) ** pw + np.abs(np.sin(phi)) ** pw) ** (-1.0 / pw)
        tgt = P.copy()
        tgt[:, 0] = cx + ax * r * np.cos(phi)
        tgt[:, 1] = cy + ay * r * np.sin(phi)
        w = np.clip((P[:, 2] - z0) / 0.02, 0, 1)[:, None]               # blend in behind the toes
        V[m] = P + w * (tgt - P)
    # the vertices that sat between the toes now fold over their neighbours: a few light smoothing passes over the
    # toe box, then back onto its outline
    idx = np.nonzero(mov)[0]
    nb = [[] for _ in range(len(V))]
    for a_, b_, c_ in bm.F:
        nb[a_] += [b_, c_]; nb[b_] += [a_, c_]; nb[c_] += [a_, b_]
    nbs = [np.unique(nb[i]) for i in idx]
    box = V[idx].copy()
    for _ in range(10):
        avg = np.array([V[n].mean(0) if len(n) else V[i] for i, n in zip(idx, nbs)])
        V[idx] = V[idx] + 0.5 * (avg - V[idx])
    # smoothing shrinks: half of each vertex's pull inwards is given back
    V[idx] = V[idx] + 0.3 * (box - V[idx])
    # keep the sole on the floor where it was
    low = sh.V[mov, 1].min()
    V[mov, 1] = np.maximum(V[mov, 1], low)
    log("layers: feet in socks / shoes (worn %.0f%% of their votes): toes smoothed into one shape" % (
        100 * worn / max(1e-9, worn + skin)))
    return V


def fit_layers(fitter, frames=None, log=print):
    """-> (merged Mesh in rest pose, info). Clothes offsets (+ skirt) fitted to the full silhouettes with the
    cameras held; hair thickness / length from the hair labels."""
    from scipy.optimize import minimize
    from .capture_fit import raster, iou
    frames = frames or [t.r for t in fitter.targets]
    sh, P, Pg = fitter.posed()
    _, _, S = sh.pose(fitter.dirs)
    votes = vertex_labels(fitter, P, fitter.bm.F, frames)
    bm = fitter.bm
    fsel = clothes_faces(bm, votes, shape=sh, log=log)
    Vb = shod_feet(bm, sh, votes, log=log)
    body = Mesh(Vb, bm.F, to_quarter(bm.fuv, "body"), bm.J, bm.W, np.zeros(len(sh.V), int))
    stand = [t for t in fitter.targets if t.pose == "s" and t.r["i"] in fitter.cams.cam]
    stand = stand[::max(1, len(stand) // 12)]                       # 12 views round the orbit are plenty here
    skirt_on = needs_skirt(fitter, sh, P, frames)
    hair_len = hair_length_from_frames(fitter, sh, P, frames)
    hem0 = max(0.05, hem_from_frames(fitter, sh, P, frames)) if skirt_on else 0.0
    if skirt_on and not dress_like(fitter, sh, P, Pg, frames, hem0):
        skirt_on = False; hem0 = 0.0
        log("layers: shorts / trousers below the crotch (not a dress-like garment): no skirt")
    keys = list(GARMENT_GROUPS) + (["hem", "flare"] if skirt_on else []) + ["hair"]

    def build(x):
        off = {k: float(np.clip(v, 0, OFFSET_MAX[k])) for k, v in zip(GARMENT_GROUPS, x[:len(GARMENT_GROUPS)])}
        parts = [body]
        if fsel.any():
            parts.append(build_clothes(sh, fsel, off))
        i = len(GARMENT_GROUPS)
        if skirt_on:
            parts.append(build_skirt(sh, float(np.clip(x[i], 0.05, 0.7)), float(np.clip(x[i + 1], 0, 0.5)),
                                     extra=parts[1] if len(parts) > 1 else None, S=S))
            i += 2
        parts.append(build_hair(sh, votes, float(np.clip(x[i], 0.0, 0.08)), hair_len))
        return merge(parts), off

    def f(x):
        M, _ = build(x)
        Q = M.pose(S)
        v = []
        for t in stand:
            v.append(iou(raster(fitter.cams.project(t.r, Q), M.F, t.r["size"], fitter.scale), t, tight=False))
        return 1 - float(np.mean(v)) + 0.02 * float(np.sum(np.clip(x[:len(GARMENT_GROUPS)], 0, None)))
    x0 = np.array([0.015] * len(GARMENT_GROUPS) + ([hem0, 0.1] if skirt_on else []) + [0.005])
    bounds = ([(0.0, OFFSET_MAX[k]) for k in GARMENT_GROUPS] + ([(max(0.05, hem0 - 0.06), hem0 + 0.06), (0.0, 0.5)] if skirt_on else [])
              + [(0.0, 0.08)])

    def body_only():
        Q = body.pose(S)
        return float(np.mean([iou(raster(fitter.cams.project(t.r, Q), body.F, t.r["size"], fitter.scale), t, tight=False)
                              for t in stand]))
    before = body_only()
    res = minimize(f, x0, method="Powell", bounds=bounds, options=dict(maxiter=2, xtol=0.003, ftol=1e-4))
    res.x = np.clip(res.x, [b[0] for b in bounds], [b[1] for b in bounds])
    after = 1 - f(res.x) + 0.02 * float(np.sum(res.x[:len(GARMENT_GROUPS)]))
    if hair_len > 0.06:
        # keep the long-hair curtain only if the silhouettes want it
        full = hair_len; hair_len = 0.0
        short = 1 - f(res.x) + 0.02 * float(np.sum(res.x[:len(GARMENT_GROUPS)]))
        if short > after + 0.001:
            after = short
            log("layers: long-hair curtain dropped (silhouettes fit better without it)")
        else:
            hair_len = full
    M, off = build(res.x)
    info = dict(clothes_faces=int(fsel.sum()), offsets_m=off, skirt=skirt_on, hair_length_m=hair_len,
                hair_thickness_m=float(res.x[-1]), iou_body_only=before, iou_with_layers=after)
    if skirt_on:
        info.update(hem_drop_m=float(res.x[len(GARMENT_GROUPS)]), flare=float(res.x[len(GARMENT_GROUPS) + 1]))
    log("layers: clothes over %d faces (offsets %s cm)%s, hair %.1f cm thick%s; silhouette IoU %.3f -> %.3f" % (
        fsel.sum(), ", ".join("%s %.1f" % (k, 100 * v) for k, v in off.items()),
        ", skirt hem %.0f cm below the crotch" % (100 * info["hem_drop_m"]) if skirt_on else "",
        100 * info["hair_thickness_m"], (", long hair %.0f cm" % (100 * hair_len)) if hair_len > 0.06 else "",
        before, after))
    return M, info, S
