"""Stadium crowd: low-poly spectators a game instances by the thousand and animates in a shader (v11.32).

Fed back from Arena FC, whose crowd was coloured boxes (desktop) or a box with a ball on it (web).  Each
spectator is ~100 triangles - torso, head, hair, two arms, seated legs - in a seated and a standing build,
plus a team flag on a pole and a scarf held between the hands.  Nothing is skinned: the game moves the
parts in its vertex shader from a channel baked into COLOR_0:

    TEXCOORD_1.x  part   0 skin, .25 hair, .5 shirt, .75 trousers, 1 scarf / flag cloth
    TEXCOORD_1.y  arm    0 body .. 1 hand: how far a vertex swings when the arms go up
    COLOR_0       the same four channels as (part, arm, side, height) for viewers that show colours -
                  engines may convert vertex colours to sRGB on import, so a shader reads TEXCOORD_1;
                  side is the sign of x, height is y
    TEXCOORD_0    flag / scarf cloth coordinates (0..1), 0 elsewhere

The shoulder pivot is `SHOULDER` (m above the seat, +-x), so a shader raises an arm by rotating the
vertex about it by (arm weight x excitement).  Seat positions come from `sforge.stadium` (.seats).

    from sforge import crowd as C
    C.export("crowd.glb")          # nodes: seated, standing, flag, scarf
"""
from __future__ import annotations

import math

import numpy as np

SHOULDER = (0.21, 0.80)        # x offset, height above the seat
PART = {"skin": 0.0, "hair": .25, "shirt": .5, "trousers": .75, "cloth": 1.0}


class _M:
    def __init__(self):
        self.V, self.N, self.C, self.UV, self.F = [], [], [], [], []

    def prism(self, p0, p1, r0, r1, seg, part, arm=0.0, side=.5, arm1=None, caps=False):
        """a tapered prism from p0 (radius r0) to p1 (radius r1), capped."""
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        ax = p1 - p0; L = np.linalg.norm(ax); ax = ax / L
        u = np.cross(ax, [0, 0, 1.0] if abs(ax[1]) > .9 else [0, 1.0, 0]); u /= np.linalg.norm(u)
        v = np.cross(ax, u)
        a1 = arm if arm1 is None else arm1
        ring0 = [p0 + (math.cos(2 * math.pi * k / seg) * u + math.sin(2 * math.pi * k / seg) * v) * r0 for k in range(seg)]
        ring1 = [p1 + (math.cos(2 * math.pi * k / seg) * u + math.sin(2 * math.pi * k / seg) * v) * r1 for k in range(seg)]
        o = len(self.V)
        for k in range(seg):
            n = ring0[k] - p0
            n = n / max(np.linalg.norm(n), 1e-9)
            for P, a in ((ring0[k], arm), (ring1[k], a1)):
                self.V.append(P); self.N.append(n); self.C.append((PART[part], a, side, 0)); self.UV.append((0, 0))
        for k in range(seg):
            i0, i1 = o + 2 * k, o + 2 * ((k + 1) % seg)
            self.F += [(i0, i1, i0 + 1), (i1, i1 + 1, i0 + 1)]
        for ring, c, nrm, a in (((ring0, p0, -ax, arm), (ring1, p1, ax, a1)) if caps else ()):
            oc = len(self.V)
            self.V.append(c); self.N.append(nrm); self.C.append((PART[part], a, side, 0)); self.UV.append((0, 0))
            for k in range(seg):
                self.V.append(ring[k]); self.N.append(nrm); self.C.append((PART[part], a, side, 0)); self.UV.append((0, 0))
            for k in range(seg):
                a_, b_ = oc + 1 + k, oc + 1 + (k + 1) % seg
                self.F.append((oc, b_, a_) if nrm is ax else (oc, a_, b_))

    def ball(self, c, r, part, rings=3, seg=6, squash=1.0):
        c = np.asarray(c, float)
        o = len(self.V)
        pts = [(0, 1, 0)]
        for i in range(1, rings):
            th = math.pi * i / rings
            for k in range(seg):
                ph = 2 * math.pi * k / seg
                pts.append((math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)))
        pts.append((0, -1, 0))
        for p in pts:
            p = np.array(p)
            self.V.append(c + p * r * np.array([1, squash, 1])); self.N.append(p); self.C.append((PART[part], 0, .5, 0)); self.UV.append((0, 0))
        top, bot = o, o + len(pts) - 1
        for k in range(seg):
            self.F.append((top, o + 1 + (k + 1) % seg, o + 1 + k))
        for i in range(rings - 2):
            for k in range(seg):
                a = o + 1 + i * seg + k; b = o + 1 + i * seg + (k + 1) % seg
                c_ = a + seg; d = b + seg
                self.F += [(a, b, d), (a, d, c_)]
        base = o + 1 + (rings - 2) * seg
        for k in range(seg):
            self.F.append((bot, base + k, base + (k + 1) % seg))

    def cloth(self, corners, uv, part="cloth", arm=1.0, side=.5):
        o = len(self.V)
        a, b, c, d = (np.asarray(x, float) for x in corners)
        n = np.cross(b - a, d - a); n /= np.linalg.norm(n)
        for P, t in zip((a, b, c, d), uv):
            self.V.append(P); self.N.append(n); self.C.append((PART[part], arm, side, 0)); self.UV.append(t)
        self.F += [(o, o + 1, o + 2), (o, o + 2, o + 3), (o, o + 2, o + 1), (o, o + 3, o + 2)]

    def arrays(self):
        V = np.array(self.V, np.float32)
        C = np.array(self.C, np.float32)
        C[:, 3] = np.clip(V[:, 1] / 1.0, 0, 1)
        return V, np.array(self.N, np.float32), C, np.array(self.UV, np.float32), np.array(self.F, np.uint32)


def spectator(seated=True):
    m = _M()
    hip = .0 if seated else .48
    sx, sy = SHOULDER
    sy = sy + hip
    # legs
    if seated:
        for x in (-.09, .09):
            m.prism((x, .02, 0), (x, .02, .40), .07, .065, 3, "trousers")       # thigh forward
            m.prism((x, .02, .40), (x, -.40, .44), .06, .05, 3, "trousers")     # shin down
    else:
        for x in (-.09, .09):
            m.prism((x, hip, 0), (x, -.02, .02), .075, .055, 3, "trousers")
    m.prism((0, hip, 0), (0, sy + .02, 0), .17, .2, 6, "shirt", caps=True)      # torso
    m.ball((0, sy + .2, .01), .105, "skin", rings=3, seg=5, squash=1.15)       # head
    m.ball((0, sy + .25, -.012), .108, "hair", rings=2, seg=5, squash=.75)     # hair cap
    for side, x in ((0.0, -sx), (1.0, sx)):
        m.prism((x, sy, 0), (x * 1.08, sy - .30, .03), .055, .045, 3, "shirt", arm=.15, arm1=.55, side=side)
        m.prism((x * 1.08, sy - .30, .03), (x * 1.0, sy - .55, .14), .045, .04, 3, "skin", arm=.55, arm1=1.0, side=side, caps=True)
    return m


def flag():
    """a 1.2 m pole with a 0.9 x 0.6 m cloth, held in the right hand (grip at the origin)."""
    m = _M()
    m.prism((0, -.1, 0), (0, 1.2, 0), .012, .012, 3, "hair", arm=1.0, side=1.0)
    m.cloth([(0, .6, 0), (.9, .6, 0), (.9, 1.2, 0), (0, 1.2, 0)], [(0, 1), (1, 1), (1, 0), (0, 0)], side=1.0)
    return m


def scarf():
    """a scarf held up between the hands (1.3 m x 0.18 m), in the hands' frame (y up, centred)."""
    m = _M()
    m.cloth([(-.65, -.09, 0), (.65, -.09, 0), (.65, .09, 0), (-.65, .09, 0)], [(0, 1), (1, 1), (1, 0), (0, 0)])
    return m


def export(path):
    from .glbpack import _Out
    from .officials import _write
    out = _Out()
    nodes, meshes = [], []
    mat = {"name": "crowd", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1},
           "doubleSided": False}
    stats = {}
    for name, m in (("seated", spectator(True)), ("standing", spectator(False)), ("flag", flag()), ("scarf", scarf())):
        V, N, C, UV, F = m.arrays()
        attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True), "NORMAL": out.add(N, 5126, "VEC3", 34962),
                 "COLOR_0": out.add(C, 5126, "VEC4", 34962), "TEXCOORD_0": out.add(UV, 5126, "VEC2", 34962),
                 "TEXCOORD_1": out.add(np.ascontiguousarray(C[:, :2]), 5126, "VEC2", 34962)}
        ind = out.add(F.reshape(-1).astype(np.uint16), 5123, "SCALAR", 34963)
        meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind, "material": 0, "mode": 4}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
        stats[name] = int(len(F))
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge crowd (v11.32)", "extras": {"crowd": {
              "tris": stats, "shoulder": list(SHOULDER), "channels": "TEXCOORD_1 x part, y arm weight (COLOR_0 mirrors them plus side, height)"}}},
          "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": [mat],
          "accessors": out.acc, "bufferViews": out.views, "buffers": [{"byteLength": 0}]}
    _write(gl, out.b, path)
    return stats
