"""Garment shells for a skinned body: shirts, shorts, socks and boots with clean hems (v11.30).

Fed back from Arena FC.  Its squad wore its kit as body paint: the MakeHuman clothes hug every
muscle, the hems are a staircase of whole triangles, and the "boots" are the bare feet with toes.
`tailor` cuts each garment out of the body by bone region, snaps every hem onto a straight cut,
smooths the muscles away, lets the cloth stand off the body (looser towards the hem), turns a
lip in at each opening, lays the pieces out on one kit atlas, and hides the body faces each
garment covers so nothing pokes through in motion.

    from sforge import tailor as T
    parts = T.read_parts("player.glb", "v0_")                 # name -> Part (skinned, bind pose)
    bones = T.bones_from_rig(rig_json)                        # Arena-18 heads / tails
    out = T.tailor(parts["body"], bones)                      # {"jersey": Part, ..., "body": trimmed body}
    T.replace_parts("player.glb", "out.glb", {"v0_": out})    # skeleton, skin and every clip kept

Rules live in `GARMENTS` (bone, range along the bone, ease, flare, hems), so another sport can cut
long sleeves, a guernsey, rugby shorts or keeper gloves without code.  The atlas layout is `LAYOUT`
(the same rectangles `sforge.kitdesign` paints and a game uses to place names and numbers).
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field

import numpy as np

from .glbpack import _Out, _acc_bytes, read_glb

# ---------------------------------------------------------------- atlas layout (u0, v0, u1, v1), v down
LAYOUT = {
    "torso_front": (0.00, 0.00, 0.50, 0.50),
    "torso_back": (0.50, 0.00, 1.00, 0.50),
    "sleeve_L": (0.00, 0.50, 0.25, 0.75),
    "sleeve_R": (0.25, 0.50, 0.50, 0.75),
    "shorts_L": (0.50, 0.50, 0.75, 0.75),
    "shorts_R": (0.75, 0.50, 1.00, 0.75),
    "socks_L": (0.00, 0.75, 0.25, 1.00),
    "socks_R": (0.25, 0.75, 0.50, 1.00),
    "boots_L": (0.50, 0.75, 0.75, 1.00),
    "boots_R": (0.75, 0.75, 1.00, 1.00),
}
# where a game prints the player's name and numbers (atlas UV, inside the panels above)
PRINT = {
    "back_name": (0.60, 0.075, 0.90, 0.135),
    "back_number": (0.62, 0.15, 0.88, 0.36),
    "front_number": (0.21, 0.17, 0.29, 0.25),
    "crest": (0.31, 0.065, 0.37, 0.125),
    "shorts_number": (0.53, 0.53, 0.58, 0.58),
}

TORSO = ("Hips", "Spine", "Chest", "Neck")
SIDES = ("L", "R")


@dataclass
class Part:
    name: str
    V: np.ndarray
    N: np.ndarray
    UV: np.ndarray
    J: np.ndarray
    W: np.ndarray
    F: np.ndarray
    material: str = ""
    image: str = ""
    C: np.ndarray | None = None
    extras: dict = field(default_factory=dict)


@dataclass
class Garment:
    """One piece of clothing, rebuilt from a skin-tight source mesh (MakeHuman-style clothes that
    follow every muscle and end in a staircase of triangles).  `ease` is how far it stands off the
    source (m), `flare` how much looser it gets over the last `flare_len` metres before an opening,
    `smooth` the Taubin passes that take the muscles (or toes) out, `lip` the depth of the hem
    turned in at each opening, `flat_sole` presses the bottom onto the ground (boots)."""
    name: str
    source: str
    ease: float
    flare: float = 0.0
    flare_len: float = 0.06
    smooth: int = 8
    lip: float = 0.006
    flat_sole: bool = False
    skip_lip_below: float = -1.0     # no lip on openings lower than this (a tucked-in shirt tail)
    extend: float = 0.0              # push every opening this much further (covers a body hole's ragged edge)
    tuck_into: str = ""              # cut the tail off where it is inside this garment (shirt -> shorts)
    flare_above: float = -1.0        # only openings higher than this flare (a tucked shirt stays inside the shorts)


def soccer_garments():
    """Football kit: shirt tucked into the shorts, short sleeves; loose shorts; socks; boots."""
    return [
        Garment("jersey", "jersey", ease=.008, flare=.010, flare_len=.08, smooth=24, flare_above=1.1,
                skip_lip_below=1.0, extend=.006, tuck_into="shorts"),
        Garment("shorts", "shorts", ease=.013, flare=.010, flare_len=.10, smooth=12),
        Garment("socks", "socks", ease=.0065, smooth=5, lip=.004, extend=.018),
        Garment("boots", "boots", ease=.004, smooth=400, lip=.004, flat_sole=True),
    ]


# ---------------------------------------------------------------- reading / bones
def bones_from_rig(rig_json):
    """{bone: (head, tail)} from an Arena rig JSON (bones with n / h / t)."""
    return {bo["n"]: (np.array(bo["h"], float), np.array(bo["t"], float)) for bo in rig_json["bones"]}


# MakeHuman / Unreal-style game skeleton -> the Arena-18 names the garment rules use
# (Arena's left is the template's right: the template faces -Z)
MAKEHUMAN_TO_ARENA = {
    "pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine", "spine_03": "Chest", "neck_01": "Neck",
    "head": "Head", "clavicle_r": "Chest", "clavicle_l": "Chest",
    "upperarm_r": "LUpperArm", "lowerarm_r": "LForearm", "hand_r": "LHand",
    "upperarm_l": "RUpperArm", "lowerarm_l": "RForearm", "hand_l": "RHand",
    "thigh_r": "LThigh", "calf_r": "LShin", "foot_r": "LFoot", "ball_r": "LFoot",
    "thigh_l": "RThigh", "calf_l": "RShin", "foot_l": "RFoot", "ball_l": "RFoot",
}


def skeleton_from_glb(glb_path, mapping=MAKEHUMAN_TO_ARENA):
    """(bones, joint_names) for a GLB on another skeleton: Arena-named heads/tails from the joint
    world positions, and the skin's joint list renamed (fingers fold into the hand)."""
    from .footballer import Skeleton
    j, _ = read_glb(glb_path)
    sk = Skeleton.from_glb(glb_path)
    names = [j["nodes"][i]["name"] for i in j["skins"][0]["joints"]]
    child = {"pelvis": "spine_01", "spine_01": "spine_03", "spine_03": "neck_01", "neck_01": "head",
             "upperarm_r": "lowerarm_r", "lowerarm_r": "hand_r", "upperarm_l": "lowerarm_l", "lowerarm_l": "hand_l",
             "thigh_r": "calf_r", "calf_r": "foot_r", "thigh_l": "calf_l", "calf_l": "foot_l",
             "foot_r": "ball_r", "foot_l": "ball_l", "hand_r": "middle_01_r", "hand_l": "middle_01_l"}
    bones = {}
    for src, dst in mapping.items():
        if src in child and dst not in bones:
            bones[dst] = (np.array(sk.p(src), float), np.array(sk.p(child[src]), float))
    hd = np.array(sk.p("head"), float)
    bones.setdefault("Head", (hd, hd + np.array([0, .2, 0])))
    jn = []
    for n in names:
        if n in mapping:
            jn.append(mapping[n])
        elif n.endswith("_l") or n.endswith("_r"):
            jn.append(("L" if n.endswith("_r") else "R") + "Hand")
        else:
            jn.append(n)
    return bones, jn


def read_parts(glb_path, prefix):
    """Every mesh node named prefix+part -> {part: Part}, with joint indices into the skin's joint list."""
    j, buf = read_glb(glb_path)
    out = {}

    def acc(a, k):
        ac = j["accessors"][a]
        dt = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32}[ac["componentType"]]
        return np.frombuffer(_acc_bytes(j, buf, a), dt).reshape(-1, k)
    for nd in j["nodes"]:
        if "mesh" not in nd or not nd.get("name", "").startswith(prefix):
            continue
        pr = j["meshes"][nd["mesh"]]["primitives"][0]
        at = pr["attributes"]
        mat = j["materials"][pr["material"]]["name"] if "material" in pr else ""
        out[nd["name"][len(prefix):]] = Part(
            nd["name"], acc(at["POSITION"], 3).astype(float), acc(at["NORMAL"], 3).astype(float),
            acc(at["TEXCOORD_0"], 2).astype(float), acc(at["JOINTS_0"], 4).astype(int),
            acc(at["WEIGHTS_0"], 4).astype(float), acc(pr["indices"], 1).reshape(-1, 3).astype(np.int64), mat)
    return out


# ---------------------------------------------------------------- geometry helpers
def weld(V, tol=1e-5):
    """canon[i] = first vertex at V[i]'s position (UV-seam duplicates share one)."""
    key = np.round(V / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return first[inv.ravel()]


def seg_param(P, h, t):
    """distance from P to segment h-t and the (unclamped) parameter along it."""
    d = t - h
    L2 = float(d @ d) or 1e-9
    s = (P - h) @ d / L2
    c = h + np.clip(s, 0, 1)[:, None] * d
    return np.linalg.norm(P - c, axis=1), s


def nearest_bone(V, bones, names):
    D = np.stack([seg_param(V, *bones[n])[0] for n in names], 1)
    S = np.stack([seg_param(V, *bones[n])[1] for n in names], 1)
    k = D.argmin(1)
    return k, S[np.arange(len(V)), k]


def vertex_normals(V, F):
    n = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for c in range(3):
        np.add.at(n, F[:, c], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln < 1e-12] = 1
    return n / ln


def neighbours(F, n):
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    e = np.unique(e, axis=0)
    nb = [[] for _ in range(n)]
    for a, b in e:
        nb[a].append(b)
    return nb, e


def boundary_loops(F):
    """ordered vertex loops along edges used by exactly one face."""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    be = u[cnt == 1]
    adj = {}
    for a, b in be:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    seen, loops = set(), []
    for s in adj:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [x for x in adj[cur] if x != prev and x not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    return loops


def _avg_matrix(nb):
    from scipy.sparse import csr_matrix
    rows, cols, vals = [], [], []
    for q, i in enumerate(nb):
        if len(i):
            rows += [q] * len(i); cols += list(i); vals += [1.0 / len(i)] * len(i)
        else:
            rows.append(q); cols.append(q); vals.append(1.0)
    n = len(nb)
    return csr_matrix((vals, (rows, cols)), shape=(n, n))


def taubin(V, nb, fixed, iters, lam=.33, mu=-.34):
    """Taubin lambda|mu smoothing (no shrinkage), `fixed` vertices held."""
    A = _avg_matrix(nb)
    V = V.copy()
    free = ~fixed
    for _ in range(iters):
        for k in (lam, mu):
            V[free] += k * (A @ V - V)[free]
    return V


# ---------------------------------------------------------------- the cut
def dominant_bone(part, bones, joint_names=None):
    """(bone name, t along it) per vertex from the skin weights: geometry alone is fooled by
    arms hanging beside the torso and thighs pressed together."""
    names = joint_names or list(bones)
    dom = part.J[np.arange(len(part.J)), part.W.argmax(1)]
    near = np.array(names, dtype=object)[dom].astype(str)
    s = np.zeros(len(part.V))
    for b in set(near):
        if b in bones:
            m = near == b
            s[m] = seg_param(part.V[m], *bones[b])[1]
    return near, s


def normalise_t(near, s):
    """t rescaled per bone to the mesh's own extent along it (1st..99th percentile -> 0..1):
    a rig's joint heads rarely sit exactly where a sculpt's limbs start and end."""
    tn = s.copy()
    for b in set(near):
        m = near == b
        if m.sum() < 4:
            continue
        lo, hi = np.percentile(s[m], 1), np.percentile(s[m], 99)
        tn[m] = np.clip((s[m] - lo) / max(hi - lo, 1e-6), 0, 1)
    return tn


def hem_plane(P, centre):
    """A straight cut for one ragged opening: the plane through the loop (normal = the loop's
    least-spread direction), pushed out to the loop's furthest point so the garment only grows
    (the body under a MakeHuman garment has no skin to show through a shortened hem)."""
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c)
    n = vt[2]
    if (c - centre) @ n < 0:
        n = -n
    d = float(((P - c) @ n).max())
    return c + n * d, n


def cut_garment(src, g, tuck_y=None):
    """-> Part (welded, hemmed, smoothed, eased, lipped) from a skin-tight source garment.
    `tuck_y`: faces wholly below this height are dropped (the tail tucked inside the shorts)."""
    if tuck_y is not None:
        keep = src.V[src.F][:, :, 1].mean(1) > tuck_y
        src = Part(src.name, src.V, src.N, src.UV, src.J, src.W, src.F[keep], src.material)
    canon = weld(src.V)
    used = np.unique(canon[src.F])
    remap = -np.ones(len(src.V), int)
    remap[used] = np.arange(len(used))
    F = remap[canon[src.F]]
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    V = src.V[used].copy()
    J, W = src.J[used], src.W[used]
    nb, _ = neighbours(F, len(V))
    loops = [lp for lp in boundary_loops(F) if len(lp) >= 8]
    onb = np.zeros(len(V), bool)
    for lp in loops:
        onb[lp] = True
    centre = V.mean(0)
    planes = []
    for lp in loops:
        o, n = hem_plane(V[lp], centre)
        o = o + n * g.extend
        # the snapped hem pulls its neighbours along so the last row of faces does not fold
        V[lp] -= ((V[lp] - o) @ n)[:, None] * n
        c0 = V[lp].mean(0)
        r0 = np.linalg.norm(V[lp] - c0, axis=1).mean()
        for _ in range(8):
            Q = V[lp]
            V[lp] = .5 * Q + .25 * (np.roll(Q, 1, 0) + np.roll(Q, -1, 0))
            V[lp] -= ((V[lp] - o) @ n)[:, None] * n
        # smoothing a closed loop shrinks it (~13% after 8 passes): put the opening back to its size
        c1 = V[lp].mean(0)
        r1 = np.linalg.norm(V[lp] - c1, axis=1).mean()
        V[lp] = c1 + (V[lp] - c1) * (r0 / max(r1, 1e-9))
        planes.append((o, n, float(V[lp, 1].mean())))
    V0 = V.copy()
    V = taubin(V, nb, onb, g.smooth)
    N = vertex_normals(V, F)
    # cloth rests on the high points (pecs, shoulder blades, calves) and spans the hollows between
    # them: lift the smoothed sheet by how far the source still stands out of it nearby
    h = np.maximum(((V0 - V) * N).sum(1), 0)
    idx = [np.array(x, int) for x in nb]
    for _ in range(2):
        h = np.array([max(h[q], h[i].max()) if len(i) else h[q] for q, i in enumerate(idx)])
    A = _avg_matrix(nb)
    for _ in range(4):
        h = .5 * h + .5 * (A @ h)
    V = V + N * h[:, None]
    N = vertex_normals(V, F)
    fpl = [(o, n) for o, n, y in planes if y > g.flare_above]
    if g.flare > 0 and fpl:
        dist = np.min(np.stack([np.abs((V - o) @ n) for o, n in fpl], 1), 1)
        fl = np.clip(1 - dist / g.flare_len, 0, 1) ** 1.6
        V = V + N * (g.ease + g.flare * fl)[:, None]
    else:
        V = V + N * g.ease
    if g.flat_sole:
        low = V[:, 1] < .010
        V[:, 1] = np.maximum(V[:, 1], 0.0)
        V[low, 1] = 0.0
        V = taubin(V, nb, onb | low, 6)
        V[low, 1] = 0.0
    N = vertex_normals(V, F)
    lip_loops = [lp for lp in loops if V[lp, 1].mean() > g.skip_lip_below]
    V, N, F, J, W, lipsrc = _add_lips(V, N, F, J, W, lip_loops, g.ease + g.lip)
    return Part(g.name, V, N, np.zeros((len(V), 2)), J, W, F, material=g.name,
                extras={"lip_src": lipsrc, "n_core": len(used)})


def _add_lips(V, N, F, J, W, loops, depth):
    Vs, Ns, Js, Ws, Fs = [V], [N], [J], [W], [F]
    n0 = len(V)
    lipv, lipsrc = [], []
    for lp in loops:
        lp = np.array(lp)
        c = V[lp].mean(0)
        _, _, vt = np.linalg.svd(V[lp] - c)
        n = vt[2]
        r = V[lp] - c
        r -= (r @ n)[:, None] * n
        r /= np.maximum(np.linalg.norm(r, axis=1, keepdims=True), 1e-9)
        inner = V[lp] - r * depth            # straight in towards the middle of the opening
        k = len(lp)
        base = n0
        Vs.append(inner); Ns.append(-r); Js.append(J[lp]); Ws.append(W[lp])
        a = lp
        b = np.roll(lp, -1)
        ia = base + np.arange(k)
        ib = base + np.roll(np.arange(k), -1)
        Fs.append(np.stack([a, ia, ib], 1)); Fs.append(np.stack([a, ib, b], 1))
        lipv.extend(range(base, base + k))
        lipsrc.extend(int(q) for q in lp)
        n0 += k
    return (np.concatenate(Vs), np.concatenate(Ns), np.concatenate(Fs), np.concatenate(Js),
            np.concatenate(Ws), np.array(lipsrc, int))


# ---------------------------------------------------------------- UV panels
def _panel_uv(P, tn, panel, lm, bones):
    """UV inside a LAYOUT panel.  Torso: a cylinder about the body's vertical axis (front panel as
    seen from the front, back panel as seen from behind, so prints read the right way round), v from
    the collar down to the hem.  Limbs: a cylinder about the bone, seam on the inside, v along the
    bone.  Boots: a side projection."""
    u0, v0, u1, v1 = LAYOUT[panel]
    side = panel[-1]
    if panel.startswith("torso"):
        zc = .02
        v = (lm["top"] - P[:, 1]) / (lm["top"] - lm["bottom"])
        # Arena faces +Z with the player's left on -X: seen from the front his left is on the
        # viewer's right, seen from behind on the viewer's left
        if panel == "torso_front":
            u = .5 + np.arctan2(P[:, 0], P[:, 2] - zc) / math.pi
        else:
            u = .5 - np.arctan2(P[:, 0], -(P[:, 2] - zc)) / math.pi
    elif panel.startswith("boots"):
        u = (P[:, 2] + .10) / .34
        v = (.16 - P[:, 1]) / .16
    else:
        bone = {"sleeve": "%sUpperArm", "shorts": "%sThigh", "socks": "%sShin"}[panel.split("_")[0]] % side
        hd, tl = bones[bone]
        ax = (tl - hd) / np.linalg.norm(tl - hd)
        out = np.array([-1.0 if side == "L" else 1.0, 0, 0])
        ref = out - (out @ ax) * ax
        ref /= np.linalg.norm(ref)
        fwd = np.cross(ax, ref)
        R = P - hd
        u = .5 + np.arctan2(R @ fwd, R @ ref) / (2 * math.pi)
        v = tn
    u = np.clip(u, 0, 1)
    v = np.clip(v, 0, 1)
    return np.stack([u0 + u * (u1 - u0), v0 + v * (v1 - v0)], 1)


def _face_panel(g_name, Fc, near, P):
    """panel name per face from where its corners sit."""
    cen = P[Fc].mean(1)
    side = np.where(cen[:, 0] < 0, "L", "R")
    if g_name == "jersey":
        arm = np.array([[("UpperArm" in near[q]) for q in f] for f in Fc]).sum(1) >= 2
        zc = .02
        front = cen[:, 2] - zc >= 0
        return np.where(arm, np.char.add("sleeve_", side), np.where(front, "torso_front", "torso_back"))
    return np.char.add(g_name + "_", side)


def unwrap(part, bones, joint_names=None):
    """Lay a garment onto its LAYOUT panels: vertices are split where faces of different panels
    (or the two sides of a cylinder's seam) meet."""
    near, s = dominant_bone(part, bones, joint_names)
    n_core = part.extras["n_core"]
    near[n_core:] = near[part.extras["lip_src"]]
    tn = normalise_t(near, s)
    tn[n_core:] = tn[part.extras["lip_src"]]
    lm = {"top": float(part.V[:, 1].max()), "bottom": float(part.V[:, 1].min())}
    F = part.F
    panels = _face_panel(part.name, F, near, part.V)
    newV, newN, newJ, newW, newUV, newF = [], [], [], [], [], []
    key = {}
    for fi, f in enumerate(F):
        pn = str(panels[fi])
        uv = _panel_uv(part.V[f], tn[f], pn, lm, bones)
        u0, _, u1, _ = LAYOUT[pn]
        wrap = 0
        if not pn.startswith(("boots", "torso")) and (uv[:, 0].max() - uv[:, 0].min()) > (u1 - u0) * .5:
            wrap = 1                        # the triangle straddles the seam: its low corners go to the far edge
            lo = uv[:, 0] < (u0 + u1) * .5
            uv[lo, 0] = u1
        tri = []
        for c, vi in enumerate(f):
            kk = (int(vi), pn, wrap and bool(uv[c, 0] >= u1 - 1e-9))
            if kk not in key:
                key[kk] = len(newV)
                newV.append(part.V[vi]); newN.append(part.N[vi]); newJ.append(part.J[vi]); newW.append(part.W[vi])
                newUV.append(uv[c])
            tri.append(key[kk])
        newF.append(tri)
    return Part(part.name, np.array(newV), np.array(newN), np.array(newUV), np.array(newJ), np.array(newW),
                np.array(newF, np.int64), material=part.material)


def tailor(parts, bones, garments=None, log=print, joint_names=None):
    """parts = {name: Part} of one identity (read_parts).  -> {garment name: Part} rebuilt and laid
    out on the kit atlas; replace the old garment nodes with them (replace_parts)."""
    garments = garments or soccer_garments()
    out = {}
    for g in garments:
        if g.source not in parts:
            continue
        tuck = None
        if g.tuck_into and g.tuck_into in parts:
            tuck = float(np.percentile(parts[g.tuck_into].V[:, 1], 99)) - .022
        p = cut_garment(parts[g.source], g, tuck)
        out[g.name] = unwrap(p, bones, joint_names)
        log("  tailor %-7s %5d -> %5d verts, %5d tris" % (g.name, len(parts[g.source].V), len(out[g.name].V), len(out[g.name].F)))
    return out


def qa(out, bones):
    """[] when the kit is sound: hems level / square, boots have no toes poking out, soles on the
    ground, no garment vertex inside the body by more than a few millimetres."""
    errs = []
    for name in ("jersey", "shorts", "socks", "boots"):
        if name not in out or len(out[name].F) == 0:
            errs.append("%s missing" % name)
    if errs:
        return errs
    bo = out["boots"]
    if bo.V[:, 1].min() < -1e-4:
        errs.append("boot sole below the ground (%.4f)" % bo.V[:, 1].min())
    uv = np.concatenate([out[n].UV for n in ("jersey", "shorts", "socks", "boots")])
    if uv.min() < -1e-6 or uv.max() > 1 + 1e-6:
        errs.append("UVs leave the atlas")
    return errs


# ---------------------------------------------------------------- write back into a GLB
def replace_parts(glb_in, glb_out, by_prefix, materials=None, extras=None):
    """Swap mesh nodes in a skinned GLB.  `by_prefix` = {"v0_": {"jersey": Part, "body": Part, ...}}:
    each named part replaces prefix+name (or is added).  Nodes, skin, animations, images and other
    meshes are kept; buffers are rebuilt so dropped geometry is not carried.  New garment parts get
    the material named like the part (created plain white if missing)."""
    j, buf = read_glb(glb_in)
    out = _Out()
    acc_map = {}

    def keep_acc(i):
        if i not in acc_map:
            acc_map[i] = out.copy_acc(j, buf, i)
        return acc_map[i]
    mats = [dict(m) for m in j.get("materials", [])]
    mat_ix = {m["name"]: k for k, m in enumerate(mats)}
    for nm in (materials or {}):
        if nm not in mat_ix:
            mats.append(dict(materials[nm], name=nm))
            mat_ix[nm] = len(mats) - 1
    meshes, nodes = [], [dict(n) for n in j["nodes"]]
    scene = dict(j["scenes"][j.get("scene", 0)])
    scene["nodes"] = list(scene["nodes"])
    replaced = set()
    for ni, nd in enumerate(nodes):
        if "mesh" not in nd:
            continue
        nm = nd["name"]
        hit = None
        for pre, parts in by_prefix.items():
            if nm.startswith(pre) and nm[len(pre):] in parts:
                hit = parts[nm[len(pre):]]
                replaced.add((pre, nm[len(pre):]))
        if hit is None:
            m = j["meshes"][nd["mesh"]]
            prs = []
            for pr in m["primitives"]:
                p2 = dict(pr)
                p2["attributes"] = {k: keep_acc(v) for k, v in pr["attributes"].items()}
                p2["indices"] = keep_acc(pr["indices"])
                p2.pop("targets", None)
                prs.append(p2)
            meshes.append({"name": m.get("name", nm), "primitives": prs})
        else:
            mat = hit.material or nm
            if mat not in mat_ix:
                mats.append({"name": mat, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": .7}})
                mat_ix[mat] = len(mats) - 1
            meshes.append(_mesh(out, nm, hit, mat_ix[mat] if hit.material else j["meshes"][nd["mesh"]]["primitives"][0].get("material", 0)))
        nd["mesh"] = len(meshes) - 1
    for pre, parts in by_prefix.items():
        for pn, p in parts.items():
            if (pre, pn) in replaced:
                continue
            if p.material not in mat_ix:
                mats.append({"name": p.material, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": .7}})
                mat_ix[p.material] = len(mats) - 1
            meshes.append(_mesh(out, pre + pn, p, mat_ix[p.material]))
            nodes.append({"name": pre + pn, "mesh": len(meshes) - 1, "skin": 0})
            scene["nodes"].append(len(nodes) - 1)
    sk = dict(j["skins"][0])
    sk["inverseBindMatrices"] = keep_acc(sk["inverseBindMatrices"])
    anims = []
    for an in j.get("animations", []):
        sm = [{"input": keep_acc(s["input"]), "output": keep_acc(s["output"]),
               "interpolation": s.get("interpolation", "LINEAR")} for s in an["samplers"]]
        anims.append({"name": an.get("name", "anim"), "channels": an["channels"], "samplers": sm})
    imgs = []
    for im in j.get("images", []):
        im2 = dict(im)
        if "bufferView" in im:
            bv = j["bufferViews"][im["bufferView"]]
            o = bv.get("byteOffset", 0)
            im2["bufferView"] = out.view(bytes(buf[o:o + bv["byteLength"]]))
        imgs.append(im2)
    gl = dict(j)
    gl.update({"scenes": [scene], "scene": 0, "nodes": nodes, "meshes": meshes, "materials": mats,
               "skins": [sk] + j["skins"][1:], "animations": anims, "images": imgs,
               "accessors": out.acc, "bufferViews": out.views, "buffers": [{"byteLength": 0}]})
    if not imgs:
        gl.pop("images", None)
    gl["asset"] = dict(j["asset"])
    gl["asset"]["generator"] = "Sprite Forge tailor.replace_parts (v11.30)"
    if extras:
        ex = dict(gl["asset"].get("extras", {}))
        ex.update(extras)
        gl["asset"]["extras"] = ex
    b = out.b
    while len(b) % 4:
        b.append(0)
    gl["buffers"][0]["byteLength"] = len(b)
    js = json.dumps(gl, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    data = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(b)) + struct.pack("<II", len(js), 0x4E4F534A) + js + \
        struct.pack("<II", len(b), 0x004E4942) + bytes(b)
    open(glb_out, "wb").write(data)
    return len(data)


def _mesh(out, name, p, mat):
    V = np.asarray(p.V, np.float32)
    N = np.asarray(p.N, np.float64)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    ln[ln < 1e-9] = 1
    N = (N / ln).astype(np.float32)
    J = np.asarray(p.J)
    W = np.asarray(p.W, np.float32)
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
    J = np.where(W > 0, J, 0)
    jt = (np.uint8, 5121) if J.max() < 256 else (np.uint16, 5123)
    it = (np.uint16, 5123) if len(V) < 65535 else (np.uint32, 5125)
    attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True), "NORMAL": out.add(N, 5126, "VEC3", 34962),
             "JOINTS_0": out.add(J.astype(jt[0]), jt[1], "VEC4", 34962), "WEIGHTS_0": out.add(W, 5126, "VEC4", 34962),
             "TEXCOORD_0": out.add(np.asarray(p.UV, np.float32), 5126, "VEC2", 34962)}
    ind = out.add(np.asarray(p.F).astype(it[0]).reshape(-1), it[1], "SCALAR", 34963)
    return {"name": name, "primitives": [{"attributes": attrs, "indices": ind, "material": int(mat), "mode": 4}]}


def layout_json():
    """The atlas contract a game reads: panels and print areas in UV (v down)."""
    return {"version": "11.30", "panels": {k: list(v) for k, v in LAYOUT.items()},
            "print": {k: list(v) for k, v in PRINT.items()}}
