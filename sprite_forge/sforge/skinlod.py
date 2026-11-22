"""Level-of-detail meshes for skinned game characters (v11.37, fed back from Arena FC).

A football match draws 22 players, 3 officials and the benches; at broadcast distance a 45k-triangle player
is mostly wasted.  `simplify` takes a skinned part (tailor.Part) down to a share of its triangles by
quadric-error *half-edge* collapses: every surviving vertex is an original vertex, so its UVs, skin
weights, normals and flutter weights (UV2) stay exact - no attribute re-projection, no seam smearing.
Openings and UV seams are locked (a hem or a texture seam never moves), and a collapse that would flip or
sliver a triangle is refused.

    from sforge import skinlod as SL
    lods = SL.lod_parts(parts)                 # {"body": [lod1, lod2], "jersey": [...], ...}
    SL.simplify(part, .5)                      # one part to half its triangles

`LOD_PLAN` says which parts drop out at which level (eyelashes and brows vanish long before the body
does) and the screen distances a game can switch at.
"""
from __future__ import annotations

import heapq

import numpy as np

from .tailor import Part

# ratio of triangles kept per level, and parts dropped from that level on (too small to see); `under`:
# which parts lie under which (their hidden faces are cut before simplifying, so a coarse level never pokes
# through: the shins inside the socks, the shirt tail inside the shorts)
LOD_PLAN = {
    "ratios": (0.45, 0.22),
    # (optional layers - a keeper's base layer and gloves - never hide the skin: outfield players show it)
    "under": {"body": ("jersey", "shorts", "socks", "boots"), "jersey": ("shorts",),
              "socks": ("boots",), "sleeves": ("gloves",)},
    "drop": {2: ("lashes", "brows", "hairinner", "beardshell1")},
    "keep_full": ("eyes",),
    # the shirt is what the camera sees most: it keeps more of its shape than the ratio says
    "min_ratio": {"jersey": (0.5, 0.35), "shorts": (0.5, 0.35)},
    # a coarse garment's flat faces cut chords inside its curved original: stand it off a little (m)
    "inflate": {"jersey": (.0012, .0028), "shorts": (.0012, .0028), "socks": (.001, .0025),
                "sleeves": (.001, .0025), "gloves": (.001, .002), "boots": (.0008, .0015)},                       # few triangles, and the silhouette of an eye matters
    "distances_m": {"ultra": (22.0, 48.0), "high": (16.0, 36.0), "performance": (11.0, 26.0)},
}


def _locked(V, F):
    """Vertices that may not move: on an opening (boundary edge) or on a UV seam (another vertex index
    sits at the same position)."""
    n = len(V)
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    e, cnt = np.unique(E, axis=0, return_counts=True)
    lock = np.zeros(n, bool)
    lock[e[cnt == 1].ravel()] = True
    q = np.round(V / 1e-6).astype(np.int64)
    _, inv, c = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    lock |= c[inv.ravel()] > 1
    used = np.zeros(n, bool)
    used[F.ravel()] = True
    return lock | ~used


def _boundary(V, F):
    """Vertices on an opening (a boundary edge after welding coincident vertices: seams do not count)."""
    q = np.round(V / 1e-6).astype(np.int64)
    _, canon = np.unique(q, axis=0, return_inverse=True)
    canon = canon.ravel()
    G = canon[F]
    E = np.sort(np.concatenate([G[:, [0, 1]], G[:, [1, 2]], G[:, [2, 0]]]), axis=1)
    e, cnt = np.unique(E, axis=0, return_counts=True)
    onb = np.zeros(canon.max() + 1, bool)
    onb[e[cnt == 1].ravel()] = True
    return onb[canon]


def _quadrics(V, F):
    Q = np.zeros((len(V), 4, 4))
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    area = np.linalg.norm(n, axis=1)
    n = n / np.maximum(area, 1e-12)[:, None]
    p = np.concatenate([n, -(n * a).sum(1, keepdims=True)], 1)
    K = p[:, :, None] * p[:, None, :] * area[:, None, None]
    for k in range(3):
        np.add.at(Q, F[:, k], K)
    return Q


def simplify(part: Part, ratio: float, max_angle: float = 22.0, keep=None) -> Part:
    """-> a Part with about `ratio` of the triangles; vertices are a subset of the original's.
    `keep`: a mask of vertices that must stay where they are (e.g. skin just inside a sock's top)."""
    V = np.asarray(part.V, float)
    F = np.asarray(part.F, np.int64).copy()
    target = max(4, int(len(F) * ratio))
    lock = _locked(V, F)
    if keep is not None:
        lock |= keep
    Q = _quadrics(V, F)
    alive_f = np.ones(len(F), bool)
    vf = [set() for _ in range(len(V))]
    for fi, f in enumerate(F):
        for v in f:
            vf[v].add(fi)
    cos_max = np.cos(np.radians(max_angle))

    def fnormal(f):
        n = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
        ln = np.linalg.norm(n)
        return n / ln if ln > 1e-14 else None

    def cost(u, v):
        p = np.append(V[v], 1.0)
        return float(p @ (Q[u] + Q[v]) @ p)

    ver = np.zeros(len(V), np.int64)
    heap = []

    def push(u):
        if lock[u]:
            return
        nbrs = set()
        for fi in vf[u]:
            nbrs.update(int(x) for x in F[fi])
        nbrs.discard(u)
        best = None
        for v in nbrs:
            c = cost(u, v)
            if best is None or c < best[0]:
                best = (c, v)
        if best is not None:
            heapq.heappush(heap, (best[0], int(ver[u]), u, best[1]))

    for u in range(len(V)):
        if vf[u]:
            push(u)
    nf = int(alive_f.sum())
    while nf > target and heap:
        c, vv, u, v = heapq.heappop(heap)
        if vv != ver[u] or lock[u] or not vf[u] or not vf[v]:
            continue
        shared = [fi for fi in vf[u] if v in F[fi]]
        if not shared:
            ver[u] += 1
            push(u)
            continue
        # every face of u that survives gets v in u's place: refuse flips and slivers
        ok = True
        for fi in vf[u]:
            if fi in shared:
                continue
            f0 = F[fi]
            n0 = fnormal(f0)
            f1 = np.where(f0 == u, v, f0)
            n1 = fnormal(f1)
            if n0 is None or n1 is None or n0 @ n1 < cos_max:
                ok = False
                break
            e = V[f1[[1, 2, 0]]] - V[f1]
            la = np.linalg.norm(e, axis=1)
            area2 = np.linalg.norm(np.cross(e[0], -e[2]))
            if area2 < 1e-3 * la.max() ** 2:          # a sliver (very thin triangle)
                ok = False
                break
        # the link condition: u and v may share only the vertices of their shared faces (keeps a manifold)
        if ok:
            nu = set()
            for fi in vf[u]:
                nu.update(int(x) for x in F[fi])
            nv = set()
            for fi in vf[v]:
                nv.update(int(x) for x in F[fi])
            common = (nu & nv) - {u, v}
            opp = set()
            for fi in shared:
                opp.update(int(x) for x in F[fi])
            if common - opp:
                ok = False
        if not ok:
            ver[u] += 1
            # try again later with a worse cost so a blocked vertex does not spin
            heapq.heappush(heap, (c * 4 + 1e-9, int(ver[u]), u, v)) if c < 1e3 else None
            continue
        for fi in shared:
            alive_f[fi] = False
            for x in F[fi]:
                vf[x].discard(fi)
            nf -= 1
        for fi in list(vf[u]):
            F[fi] = np.where(F[fi] == u, v, F[fi])
            vf[v].add(fi)
        vf[u] = set()
        Q[v] = Q[v] + Q[u]
        ver[u] += 1
        touched = set()
        for fi in vf[v]:
            touched.update(int(x) for x in F[fi])
        for x in touched:
            ver[x] += 1
            push(x)
    F = F[alive_f]
    used = np.unique(F)
    remap = -np.ones(len(V), np.int64)
    remap[used] = np.arange(len(used))
    pick = lambda A: None if A is None else np.asarray(A)[used]  # noqa: E731
    return Part(part.name, V[used], pick(part.N), pick(part.UV), pick(part.J), pick(part.W), remap[F],
                material=part.material, UV2=pick(getattr(part, "UV2", None)))


def cull_covered(inner: Part, outers, margin=.0015, reach=.04, clear=.03) -> Part:
    """`inner` without the faces wholly inside any of `outers` (every corner behind the outer surface by
    more than `margin`, measured to the nearest outer vertex along its normal) and at least `clear` from
    any opening of them (what is seen through a sleeve or a collar stays)."""
    if not outers:
        return inner
    BV = np.concatenate([o.V[_locked(o.V, o.F) & _boundary(o.V, o.F)] for o in outers])
    OV = np.concatenate([o.V for o in outers])
    ON = np.concatenate([o.N for o in outers])
    ON = ON / np.maximum(np.linalg.norm(ON, axis=1, keepdims=True), 1e-9)
    inside = np.zeros(len(inner.V), bool)
    used = np.unique(inner.F)
    for a in range(0, len(used), 512):
        idx = used[a:a + 512]
        P = inner.V[idx]
        d2 = ((P[:, None] - OV[None]) ** 2).sum(-1)
        k = d2.argmin(1)
        s = ((P - OV[k]) * ON[k]).sum(1)
        far = ((P[:, None] - BV[None]) ** 2).sum(-1).min(1) > clear * clear if len(BV) else True
        inside[idx] = (s < -margin) & (d2[np.arange(len(idx)), k] < reach * reach) & far
    keep = ~inside[inner.F].all(1)
    return Part(inner.name, inner.V, inner.N, inner.UV, inner.J, inner.W, inner.F[keep], material=inner.material,
                UV2=getattr(inner, "UV2", None))


def lod_parts(parts, plan=None, log=lambda *a: None):
    """{name: Part} of one identity -> {name: [lod1, lod2, ...]} (a part dropped from a level has None)."""
    plan = plan or LOD_PLAN
    out = {}
    for name, p in parts.items():
        outers = [parts[o] for o in plan.get("under", {}).get(name, ()) if o in parts]
        keep = None
        if outers:
            n0 = len(p.F)
            p = cull_covered(p, outers)
            log("  lod %-10s hidden faces cut: %d -> %d" % (name, n0, len(p.F)))
            # what sits just inside an opening of the layer above keeps its full detail, or a coarse
            # level pokes out at the sock tops and the waistband
            BV = np.concatenate([o.V[_boundary(o.V, o.F)] for o in outers])
            keep = np.zeros(len(p.V), bool)
            for a in range(0, len(p.V), 1024):
                keep[a:a + 1024] = ((p.V[a:a + 1024, None] - BV[None]) ** 2).sum(-1).min(1) < plan.get("keep_near_opening", .05) ** 2
        levels = []
        for k, r in enumerate(plan["ratios"], start=1):
            dropped = any(name in plan["drop"].get(j, ()) for j in range(1, k + 1))
            if dropped:
                levels.append(None)
            elif name in plan.get("keep_full", ()) or len(p.F) < 200:
                levels.append(p)
            else:
                r = max(r, plan.get("min_ratio", {}).get(name, (0,) * 9)[k - 1])
                q = simplify(p, r, keep=keep)
                off = plan.get("inflate", {}).get(name)
                if off:
                    n = q.N / np.maximum(np.linalg.norm(q.N, axis=1, keepdims=True), 1e-9)
                    q = Part(q.name, q.V + n * off[k - 1], q.N, q.UV, q.J, q.W, q.F, material=q.material, UV2=q.UV2)
                levels.append(q)
        out[name] = levels
        log("  lod %-10s %6d -> %s" % (name, len(p.F), " / ".join("-" if q is None else str(len(q.F)) for q in levels)))
    return out


def deviation(a: Part, b: Part, samples=4000, seed=1):
    """How far the simplified surface `b` strays from `a`: the 95th percentile distance (m) from points
    on `a` to the nearest vertex of `b` (vertex-based, an upper bound on the true distance)."""
    rng = np.random.default_rng(seed)
    F = a.F[rng.integers(0, len(a.F), samples)]
    w = rng.dirichlet((1, 1, 1), samples)
    P = (a.V[F] * w[:, :, None]).sum(1)
    d = np.empty(samples)
    for i in range(0, samples, 512):
        d[i:i + 512] = np.sqrt(((P[i:i + 512, None] - b.V[None]) ** 2).sum(-1).min(1))
    return float(np.percentile(d, 95))
