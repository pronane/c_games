"""Goals with real nets, and corner flags, for field sports (v11.38, fed back from Arena FC).

Arena FC's nets were four flat quads: no depth to the roof, no sag, nothing for the ball to bulge.  This
builds the goal a broadcast shows: posts and crossbar, a net that runs back flat from the bar and then
slopes to the ground, side nets, stanchions and ground bars - as meshes a game can deform:

    net     one mesh (roof + back sheet, two side panels), dense enough to bulge.  TEXCOORD_0 is the
            position on the net in metres / `cell` (a shader draws the mesh with fract()); TEXCOORD_1.x is
            how free the net is to move (0 on the frame and the pegged ground line, 1 mid-panel),
            TEXCOORD_1.y the panel (0 roof/back, .5 left side, 1 right side).  It hangs with a little sag
            already in the geometry.
    frame   posts and crossbar (white), stanchions and ground bars (dark)
    flag    a corner flag: the pole (`flag_pole`) and the cloth (`flag_cloth`, TEXCOORD_1.x = distance from
            the pole 0..1, the part that flaps) - the pole's foot at the origin

Coordinates: the goal line is the plane x = 0, the net runs back along +x, the posts at z = +-width/2,
y up; a game mirrors it for the other end.  `GOALS` has soccer, futsal, hurling / Gaelic (soccer-height
goal under the posts), hockey and handball sizes.

    from sforge import goalnet as G
    G.export("goal_soccer.glb", "soccer")      # nodes: frame, net, flag_pole, flag_cloth
"""
from __future__ import annotations

import json
import math
import struct

import numpy as np

# width x height between the posts (inner), net depth at the top and at the ground, post radius (m)
GOALS = {
    "soccer": dict(width=7.32, height=2.44, depth_top=1.0, depth_ground=2.0, post=.06),
    "futsal": dict(width=3.0, height=2.0, depth_top=.8, depth_ground=1.0, post=.04),
    "gaelic": dict(width=6.5, height=2.5, depth_top=1.0, depth_ground=2.0, post=.06),
    "hockey": dict(width=3.66, height=2.14, depth_top=1.0, depth_ground=1.2, post=.05),
    "handball": dict(width=3.0, height=2.0, depth_top=.8, depth_ground=1.0, post=.04),
}


class _Mesh:
    def __init__(self):
        self.V, self.N, self.UV, self.UV2, self.F, self.C = [], [], [], [], [], []

    def add(self, V, F, UV=None, UV2=None, col=(1, 1, 1)):
        base = len(self.V)
        V = np.asarray(V, float)
        self.V += list(V)
        self.UV += list(UV) if UV is not None else [(0.0, 0.0)] * len(V)
        self.UV2 += list(UV2) if UV2 is not None else [(0.0, 0.0)] * len(V)
        self.C += [col] * len(V)
        self.F += [tuple(int(i) + base for i in f) for f in F]

    def arrays(self):
        V = np.array(self.V, np.float32)
        F = np.array(self.F, np.int64)
        N = np.zeros_like(V)
        tri = V[F]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return dict(V=V, N=N.astype(np.float32), UV=np.array(self.UV, np.float32), UV2=np.array(self.UV2, np.float32),
                    C=np.array(self.C, np.float32), F=F)


def _tube(m, pts, r, col, n=12):
    """a tube along a polyline (closed ends not needed: posts meet the ground and the bar)."""
    pts = np.asarray(pts, float)
    rings = []
    for i, p in enumerate(pts):
        t = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        t /= max(np.linalg.norm(t), 1e-9)
        a = np.cross(t, [0, 1, 0]) if abs(t[1]) < .9 else np.cross(t, [1, 0, 0])
        a /= np.linalg.norm(a)
        b = np.cross(t, a)
        rings.append([p + r * (math.cos(2 * math.pi * k / n) * a + math.sin(2 * math.pi * k / n) * b) for k in range(n)])
    V = [v for ring in rings for v in ring]
    F = []
    for i in range(len(pts) - 1):
        for k in range(n):
            a0, a1 = i * n + k, i * n + (k + 1) % n
            b0, b1 = a0 + n, a1 + n
            F += [(a0, b0, b1), (a0, b1, a1)]
    m.add(V, F, col=col)


def _profile(g, steps):
    """the net's profile in the (x, y) plane, from the crossbar back along the roof, then down the back to
    the ground: points and their arc length."""
    h, dt, dg = g["height"], g["depth_top"], g["depth_ground"]
    corner = np.array([dt, h])
    pts = [np.array([0.0, h]) + (corner - [0.0, h]) * s for s in np.linspace(0, 1, steps[0], endpoint=False)]
    pts += [corner + (np.array([dg, 0.0]) - corner) * s for s in np.linspace(0, 1, steps[1])]
    P = np.array(pts)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    return P, arc


def build(sport="soccer", cell=.12, sag=.07, res=.11):
    """-> {"frame": arrays, "net": arrays} for a goal of `GOALS[sport]` (see the module docstring)."""
    g = GOALS[sport]
    w, h, dt, dg, pr = g["width"], g["height"], g["depth_top"], g["depth_ground"], g["post"]
    hw = w / 2 + pr
    frame = _Mesh()
    white, dark = (.96, .97, 1.0), (.18, .19, .21)
    for z in (-hw, hw):
        _tube(frame, [(0, 0, z), (0, h + pr, z)], pr, white)
    _tube(frame, [(0, h + pr * .3, -hw - pr), (0, h + pr * .3, hw + pr)], pr, white)
    # stanchions: from the top of each post, back and round down to the ground behind the side net
    for z in (-hw, hw):
        st = [(0.02, h, z), (dt * .95, h - .05, z), (dt + (dg - dt) * .55 + .15, h * .45, z), (dg + .15, 0.0, z)]
        _tube(frame, np.array(st), .025, dark, n=8)
    _tube(frame, [(dg, .015, -hw), (dg, .015, hw)], .02, dark, n=8)                   # back ground bar
    for z in (-hw, hw):
        _tube(frame, [(0, .015, z), (dg, .015, z)], .02, dark, n=8)                    # side ground bars
    net = _Mesh()
    nz = max(8, int(round(w / res)))
    P, arc = _profile(g, (max(4, int(dt / res)), max(10, int(math.hypot(dg - dt, h) / res))))
    L = arc[-1]
    # roof + back: a sheet over (z, profile)
    V, UV, UV2 = [], [], []
    for j, (p, s) in enumerate(zip(P, arc)):
        for i in range(nz + 1):
            u = i / nz
            z = -hw + 2 * hw * u
            v = s / L
            free = min(1.0, 4 * u * (1 - u)) * min(1.0, 5 * v * (1 - v))
            on_roof = p[1] >= h - 1e-6
            x, y = p[0], p[1]
            if on_roof:
                y -= sag * free                                     # the roof sags between the bar and the back
            else:
                x += sag * .6 * free                                # the back bellies out a little
            V.append((x, y, z)); UV.append((z / cell, s / cell)); UV2.append((free, 0.0))
    F = []
    W = nz + 1
    for j in range(len(P) - 1):
        for i in range(nz):
            a, b, c, d = j * W + i, j * W + i + 1, (j + 1) * W + i + 1, (j + 1) * W + i
            F += [(a, b, c), (a, c, d)]
    net.add(V, F, UV, UV2)
    # side panels: the region between the post (x = 0) and the profile, at z = +-hw
    ny = max(10, int(h / res))
    for side, zs in ((.5, -hw), (1.0, hw)):
        V, UV, UV2 = [], [], []
        nx = max(6, int(dg / res))
        for j in range(ny + 1):
            y = h * j / ny
            # profile x at this height (back slope), roof depth at the top
            xe = dt + (dg - dt) * (1 - y / h) if y < h else dt
            for i in range(nx + 1):
                u = i / nx
                x = xe * u
                v = y / h
                free = min(1.0, 4 * u * (1 - u) * 1.0) * min(1.0, 5 * v * (1 - v) + .0)
                V.append((x, y - sag * .3 * free * (y > h * .7), zs + np.sign(zs) * sag * .5 * free))
                UV.append((x / cell, y / cell)); UV2.append((free, side))
        F = []
        W2 = nx + 1
        for j in range(ny):
            for i in range(nx):
                a, b, c, d = j * W2 + i, j * W2 + i + 1, (j + 1) * W2 + i + 1, (j + 1) * W2 + i
                F += [(a, b, c), (a, c, d)] if zs > 0 else [(a, c, b), (a, d, c)]
        net.add(V, F, UV, UV2)
    return {"frame": frame.arrays(), "net": net.arrays()}


def corner_flag(height=1.5, cloth=(.45, .35), seg=(10, 7)):
    """-> {"flag_pole": arrays, "flag_cloth": arrays}: a thin pole, foot at the origin, and a cloth hung from
    its top along +x (TEXCOORD_0 0..1 over the cloth, TEXCOORD_1.x = distance from the pole 0..1)."""
    pole = _Mesh()
    _tube(pole, [(0, 0, 0), (0, height, 0)], .016, (.95, .95, .92), n=10)
    cl = _Mesh()
    nx, ny = seg
    V, UV, UV2 = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            V.append((.016 + cloth[0] * u, height - cloth[1] * v, 0.0))
            UV.append((u, v)); UV2.append((u, v))
    F = []
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i
            F += [(a, c, b), (a, d, c)]
    cl.add(V, F, UV, UV2)
    return {"flag_pole": pole.arrays(), "flag_cloth": cl.arrays()}


def export(path, sport="soccer", cell=.12):
    """Write frame, net, flag_pole and flag_cloth into one GLB (vertex colours on the frame and pole)."""
    meshes = dict(build(sport, cell=cell))
    meshes.update(corner_flag())
    return _write(path, meshes, extras={"goal": dict(GOALS[sport], sport=sport, cell=cell)})


def _write(path, meshes, extras=None):
    buf = bytearray()
    views, accs, gm, gn = [], [], [], []

    def add(arr, comp, typ, target, minmax=False):
        nonlocal buf
        b = np.ascontiguousarray(arr).tobytes()
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(b), "target": target})
        buf += b
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        accs.append(a)
        return len(accs) - 1
    mats = [{"name": "frame", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": .35}},
            {"name": "net", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": .8}, "doubleSided": True,
             "alphaMode": "BLEND"},
            {"name": "flag", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": .7}, "doubleSided": True}]
    for name, m in meshes.items():
        at = {"POSITION": add(m["V"], 5126, "VEC3", 34962, True), "NORMAL": add(m["N"], 5126, "VEC3", 34962),
              "TEXCOORD_0": add(m["UV"], 5126, "VEC2", 34962), "TEXCOORD_1": add(m["UV2"], 5126, "VEC2", 34962),
              "COLOR_0": add(m["C"], 5126, "VEC3", 34962)}
        ind = add(m["F"].astype(np.uint32).reshape(-1), 5125, "SCALAR", 34963)
        mat = 1 if name == "net" else 2 if name == "flag_cloth" else 0
        gm.append({"name": name, "primitives": [{"attributes": at, "indices": ind, "material": mat}]})
        gn.append({"name": name, "mesh": len(gm) - 1})
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge goalnet v11.38", "extras": extras or {}},
          "scene": 0, "scenes": [{"nodes": list(range(len(gn)))}], "nodes": gn, "meshes": gm, "materials": mats,
          "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": 0}]}
    while len(buf) % 4:
        buf.append(0)
    gl["buffers"][0]["byteLength"] = len(buf)
    js = json.dumps(gl).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(buf), 0x004E4942) + bytes(buf)
    with open(path, "wb") as f:
        f.write(out)
    return len(out)
