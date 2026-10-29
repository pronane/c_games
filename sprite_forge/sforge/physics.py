"""v9 HAIR / CLOTH PHYSICS BONES: ponytail, long-hair strands, scarf tails and a cape as verlet chains.

Every chain hangs from a bone (head / neck / chest), follows it, swings with inertia + gravity, keeps its segment
lengths and is pushed out of the body (sphere colliders on head, chest, hips).  Sprites draw the simulated chain
every frame; the GLB gets the chain as extra joints (hair_*/cape_*/scarf_*) with baked rotation tracks, so the
same swing plays in Godot / Unity / Blender.  Deterministic (no random numbers), loops are simulated twice so the
first and last frame match better.
"""
from __future__ import annotations
import math
import numpy as np
from .rig import rest_world

G = np.array([0.0, -9.81, 0.0])


class Chain:
    def __init__(self, name, bone, root, direction, n, length, radius, mat, kind="tube", width=0.0, stiff=0.0):
        self.name, self.bone, self.n, self.mat, self.kind = name, bone, n, mat, kind
        self.root = np.asarray(root, float)            # rest world position of the hanging point
        d = np.asarray(direction, float); self.dir = d / np.linalg.norm(d)
        self.seg = length / n
        self.radius = np.linspace(radius[0], radius[1], n + 1) if isinstance(radius, (tuple, list)) else np.full(n + 1, radius)
        self.width = width                              # sheet (cape) half width
        self.stiff = stiff                              # 0..1 pull back towards the rest direction

    def rest_points(self):
        return self.root[None] + self.dir[None] * (np.arange(self.n + 1)[:, None] * self.seg)

    def joint_names(self):
        return ["%s_%d" % (self.name, k) for k in range(self.n)]


def chains_for(spec):
    """chains for a CharacterSpec (hair style + accessories)"""
    J = rest_world()
    hs = spec.size("head")
    hc = J["head"] + np.array([0, 0.105, 0.0]) * hs
    acc = [a.strip().lower() for a in str(getattr(spec, "accessories", "") or "").replace("+", ",").split(",") if a.strip()]
    out = []
    hair = spec.hair_style.lower()
    if hair == "ponytail":
        out.append(Chain("hair_tail", "head", hc + np.array([0, -0.03, -0.13]) * hs, (0, -0.8, -0.6), 4, 0.22, (0.03, 0.012), "hair", stiff=0.08))
    if hair == "long":
        for sx in (-1, 1):
            out.append(Chain("hair_%s" % ("L" if sx > 0 else "R"), "head", hc + np.array([sx * 0.07, -0.04, -0.06]) * hs, (0, -1, -0.15), 3, 0.16,
                             (0.03, 0.02), "hair", stiff=0.15))
    if "cape" in acc:
        c = J["chest"] + np.array([0, 0.2, -0.12])
        out.append(Chain("cape", "chest", c, (0, -1, -0.12), 5, 0.95, 0.0, "accessory", kind="sheet", width=0.19, stiff=0.05))
    if "scarf" in acc:
        c = J["neck"] + np.array([0.0, -0.03, -0.07])
        for sx in (-1, 1):
            out.append(Chain("scarf_%s" % ("L" if sx > 0 else "R"), "chest", c + np.array([sx * 0.03, 0, 0]), (sx * 0.15, -1, -0.3), 4, 0.36,
                             (0.022, 0.018), "accessory2", kind="flat", width=0.03, stiff=0.04))
    return out


def _colliders(state):
    W = state.world
    return [(W["head"][:3, 3] + W["head"][:3, :3] @ np.array([0, 0.105, 0]), 0.125),
            (W["chest"][:3, 3] + W["chest"][:3, :3] @ np.array([0, 0.08, -0.0]), 0.17),
            (W["spine"][:3, 3], 0.165), (W["hips"][:3, 3], 0.17)]


def _anchor(chain, state, rest_bone):
    """world position of the chain root + the rest direction rotated by the bone"""
    M = state.world[chain.bone]
    R = M[:3, :3]
    p = M[:3, 3] + R @ (chain.root - rest_bone)
    return p, R @ chain.dir, R


def simulate(chains, states, dt, loop=False, substeps=6, damping=0.94):
    """-> list (per state) of list (per chain) of (n+1,3) world points"""
    if not chains or not states:
        return [[] for _ in states]
    J = rest_world()
    rb = [J[c.bone] for c in chains]
    # start hanging in the rest direction of the first frame
    pts, prev = [], []
    for c, r in zip(chains, rb):
        a, d, _ = _anchor(c, states[0], r)
        P = a[None] + d[None] * (np.arange(c.n + 1)[:, None] * c.seg)
        pts.append(P.copy()); prev.append(P.copy())
    passes = 2 if loop else 1
    out = []
    h = dt / substeps
    for pas in range(passes):
        rec = []
        for fi, st in enumerate(states):
            st0 = states[fi - 1] if fi > 0 else (states[-1] if (loop and pas > 0) else st)
            for ss in range(substeps):
                t = (ss + 1) / substeps
                for ci, (c, r) in enumerate(zip(chains, rb)):
                    a0, d0, _ = _anchor(c, st0, r)
                    a1, d1, R1 = _anchor(c, st, r)
                    a = a0 * (1 - t) + a1 * t
                    d = d0 * (1 - t) + d1 * t; d /= np.linalg.norm(d) + 1e-9
                    P, Q = pts[ci], prev[ci]
                    V = (P - Q) * damping
                    Q[:] = P
                    P[1:] += V[1:] + G * h * h
                    P[0] = a
                    for _ in range(3):
                        for k in range(c.n):           # segment lengths
                            e = P[k + 1] - P[k]; L = np.linalg.norm(e) + 1e-9
                            P[k + 1] = P[k] + e * (c.seg / L)
                        if c.stiff:
                            for k in range(1, c.n + 1):
                                tgt = a + d * c.seg * k
                                P[k] += (tgt - P[k]) * c.stiff
                        for ctr, rad in _colliders(st):   # push out of the body
                            rr = rad + float(c.radius.max()) + (0.02 if c.kind == "sheet" else 0.0)
                            D = P[1:] - ctr; L = np.linalg.norm(D, axis=1)
                            m = L < rr
                            if m.any():
                                P[1:][m] = ctr + D[m] / L[m][:, None] * rr
                        floor = 0.01
                        P[:, 1] = np.maximum(P[:, 1], floor)
            rec.append([p.copy() for p in pts])
        out = rec
    return out


# ------------------------------------------------------------------ geometry
def _frame(d):
    d = d / (np.linalg.norm(d) + 1e-9)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 0, 1.0])
    u = np.cross(d, a); u /= np.linalg.norm(u)
    v = np.cross(d, u)
    return u, v


def chain_tris(chain, P, side_vec=None, seg=6):
    """triangles (n,3,3) for one chain's points P (n+1,3).  tube = round, flat = ribbon, sheet = cape (both faces)"""
    tris = []
    if chain.kind == "tube":
        rings = []
        for k in range(chain.n + 1):
            d = P[min(k + 1, chain.n)] - P[max(k - 1, 0)]
            u, v = _frame(d)
            r = chain.radius[k]
            rings.append([P[k] + r * (math.cos(2 * math.pi * i / seg) * u + math.sin(2 * math.pi * i / seg) * v) for i in range(seg)])
        for k in range(chain.n):
            for i in range(seg):
                a, b = rings[k][i], rings[k][(i + 1) % seg]
                c, e = rings[k + 1][(i + 1) % seg], rings[k + 1][i]
                tris += [(a, e, c), (a, c, b)]
        tip = P[-1]
        for i in range(seg):
            tris.append((rings[-1][i], tip, rings[-1][(i + 1) % seg]))
    else:
        w = chain.width
        sv = np.array([1.0, 0, 0]) if side_vec is None else side_vec
        L = [P[k] - sv * w * (1 + 0.25 * k / chain.n) for k in range(chain.n + 1)]
        R = [P[k] + sv * w * (1 + 0.25 * k / chain.n) for k in range(chain.n + 1)]
        for k in range(chain.n):
            q = (L[k], R[k], R[k + 1], L[k + 1])
            tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3]), (q[0], q[2], q[1]), (q[0], q[3], q[2])]   # both faces
    return np.array(tris, float)


def posed_tris(chains, pts_per_chain, state):
    """all chain triangles of one frame + their material names"""
    T, M = [], []
    for c, P in zip(chains, pts_per_chain):
        sv = state.world[c.bone][:3, :3] @ np.array([1.0, 0, 0]) if c.kind != "tube" else None
        t = chain_tris(c, P, sv)
        T.append(t); M += [c.mat] * len(t)
    if not T:
        return np.zeros((0, 3, 3)), []
    return np.concatenate(T), M


def rest_tris(chains):
    """rest-pose chain triangles + the chain joint index (0..) per triangle, for GLB skinning"""
    T, Bj, M = [], [], []
    j0 = 0
    for c in chains:
        P = c.rest_points()
        t = chain_tris(c, P, np.array([1.0, 0, 0]))
        # which segment each triangle belongs to (closest segment start along the chain)
        cen = t.mean(1)
        s = np.clip(((cen - c.root) @ c.dir) / c.seg, 0, c.n - 1e-6).astype(int)
        T.append(t); Bj.append(j0 + s); M += [c.mat] * len(t)
        j0 += c.n
    if not T:
        return np.zeros((0, 3, 3)), np.zeros(0, int), []
    return np.concatenate(T), np.concatenate(Bj), M


def _shortest_arc(a, b):
    a = a / (np.linalg.norm(a) + 1e-9); b = b / (np.linalg.norm(b) + 1e-9)
    v = np.cross(a, b); c = float(np.dot(a, b))
    if c < -0.9999:
        u, _ = _frame(a)
        return 2 * np.outer(u, u) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def joint_rotations(chains, pts, state):
    """local rotation matrix per chain joint for one frame (parent = bone for joint 0, previous joint after)"""
    out = []
    for c, P in zip(chains, pts):
        parent_R = state.world[c.bone][:3, :3]
        for k in range(c.n):
            Wk = _shortest_arc(c.dir, P[k + 1] - P[k])
            out.append(parent_R.T @ Wk)
            parent_R = Wk
    return out
