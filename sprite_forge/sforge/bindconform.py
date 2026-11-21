"""Conform a sculpted mesh to a game skeleton's bind pose before skinning (v11.21).

Fed back from Arena FC, where it fixed the worst animation bug in the game.  The
footballer mesh is sculpted on the MakeHuman template, whose arms rest in an
A-pose (upper arm ~49 deg below horizontal), but Arena's skeleton is bound
with the arms hanging (~84 deg).  Skinning a mesh to a bind pose it is not in
adds that difference to *every* frame of *every* clip: all 71 clips showed the
arms 45-60 deg too far out and up (boxer arms when running, a T-pose at idle,
both arms overhead when passing).

`conform_to_bind` re-poses the mesh so each limb points the way the target
bind skeleton does.  Rotation only, about the source rig's own joints (FK in
the source proportions), so nothing is stretched; bones already within
`tolerance_deg` are left exactly as they are.  Use it on any mesh that was
built in one rest pose and is skinned to a skeleton in another.

    V2, N2, report = conform_to_bind(V, N, J, W, src_heads, tgt_heads, parents)
"""
from __future__ import annotations

import numpy as np


def minrot(a, b) -> np.ndarray:
    """Smallest rotation matrix taking direction a onto direction b."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-8:
        if c > 0:
            return np.eye(3)
        ax = np.cross(a, [1, 0, 0] if abs(a[0]) < .9 else [0, 1, 0]); ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)       # 180 degrees about any perpendicular axis
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def conform_to_bind(V, N, J, W, src_heads, tgt_heads, parents, names=None, tolerance_deg=3.0):
    """Re-pose a skinned mesh from its source rest pose into the target bind pose.

    V, N        (n,3) vertices / normals in the source rest pose
    J, W        (n,k) bone indices / weights (indices into the bone list below)
    src_heads   (b,3) each bone's head in the source rest pose (where the mesh was built)
    tgt_heads   (b,3) each bone's head in the target skeleton's bind pose
    parents     length-b parent index per bone (-1 for the root); parents before children
    Returns (V2, N2, report) - report lists "bone angle" for every bone that was turned.
    """
    src = np.asarray(src_heads, float); tgt = np.asarray(tgt_heads, float)
    nb = len(parents)
    names = list(names) if names is not None else [str(i) for i in range(nb)]
    children = {i: [j for j in range(nb) if parents[j] == i] for i in range(nb)}
    world = [np.eye(3) for _ in range(nb)]
    new_head = src.copy()
    report = []
    for i in range(nb):                                   # parent-first order
        pi = parents[i]
        Wp = world[pi] if pi >= 0 else np.eye(3)
        if pi >= 0:
            new_head[i] = new_head[pi] + world[pi] @ (src[i] - src[pi])
        C = np.eye(3)
        kids = children[i]
        if len(kids) == 1 and np.linalg.norm(src[kids[0]] - src[i]) > 1e-5:
            d_now = Wp @ (src[kids[0]] - src[i])
            d_tgt = tgt[kids[0]] - tgt[i]
            cosang = np.dot(d_now, d_tgt) / np.linalg.norm(d_now) / np.linalg.norm(d_tgt)
            angle = float(np.degrees(np.arccos(np.clip(cosang, -1, 1))))
            if angle >= tolerance_deg:
                C = minrot(d_now, d_tgt)
                report.append("%s %.0f" % (names[i], angle))
        world[i] = C @ Wp
    Rs = np.stack(world)
    V = np.asarray(V, float); N = np.asarray(N, float)
    V2 = np.zeros_like(V); N2 = np.zeros_like(N)
    for k in range(J.shape[1]):
        w = W[:, k:k + 1].astype(float)
        idx = J[:, k].astype(int)
        R = Rs[idx]
        V2 += w * (np.einsum("nij,nj->ni", R, V - src[idx]) + new_head[idx])
        N2 += w * np.einsum("nij,nj->ni", R, N)
    N2 /= np.maximum(np.linalg.norm(N2, axis=1, keepdims=True), 1e-9)
    return V2, N2, report
