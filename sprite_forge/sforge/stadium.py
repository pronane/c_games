"""Stadiums for field sports: the bowl, roof, floodlights, dugouts, tunnel, screens and seat map (v11.32).

Fed back from Arena FC.  Its desktop ground was stacked boxes with a flat roof ring (the browser edition had
a better curved bowl, built at run time in GDScript and nowhere else).  This builds a whole ground from a
`StadiumSpec` and writes it as a GLB a game loads, plus the seat map its crowd is instanced from:

    from sforge import stadium as S
    spec = S.PRESETS["bowl"]                         # or S.StadiumSpec(...) / S.preset("ground", sport="gaelic")
    info = S.export(spec, "out/stadium_bowl.glb")    # GLB + out/stadium_bowl.seats (float32 x6) + .json

Layout (metres, pitch centred on the origin, goals / ends on +-X):
    pitch + run-off -> advertising ring -> front wall -> tiers (rows, aisle between tiers) -> back wall -> roof
The stand ring is a rounded rectangle (`corner_radius`), or four separate stands with open corners
(`open_corners`, the classic British ground).  The pitch size comes from the sport (`PITCH`), so the same
code builds a Gaelic / hurling ground (145 x 90), an Aussie rules oval-ish ground or a rugby ground.

Every mesh node has a stable name and material a game can override:
    stand_seats (vertex colours: sections, row bands, aisles; alpha .25 = home end, .5 = away end, 1 = side -
                 the ends are a grey level a game multiplies by the clubs' colours)   stand_concrete
    roof  roof_fascia (emissive)  roof_columns  floodlight_masts  floodlight_lamps (emissive)
    ad_ring (UV u runs round the ground, v up - for an LED-board shader)  screens (UV 0..1 per screen)
    dugouts  dugout_glass (transparent)  tunnel  concourse
The .json carries the lights (mast / roof-edge lamp positions and aim), the screens, dugouts, tunnel and
seat counts; the .seats file one row per seat: x, y, z, yaw, tier, end (-1 home end, +1 away end, 0 side).
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import asdict, dataclass, field

import numpy as np

# half length, half width of the playing area per sport (m)
PITCH = {"soccer": (52.5, 34.0), "gaelic": (72.5, 45.0), "hurling": (72.5, 45.0), "rugby": (50.0, 35.0),
         "aussie_rules": (80.0, 65.0)}


@dataclass
class Tier:
    rows: int
    rise: float        # m per row
    depth: float = .85  # m per row


@dataclass
class StadiumSpec:
    name: str = "bowl"
    sport: str = "soccer"
    runoff_x: float = 9.0
    runoff_z: float = 7.5
    corner_radius: float = 15.0
    open_corners: bool = False
    tiers: list = field(default_factory=lambda: [Tier(16, .42), Tier(14, .55)])
    aisle: float = 2.6
    roof: bool = True
    roof_cover: float = 1.0       # 0..1 of the top tier the roof overhangs
    floodlights: str = "masts"    # masts | roof | none
    seat_pitch: float = .55       # m between seats along a row
    seat_colour: str = "#26407f"
    seat_alt: str = "#2f4d98"
    concrete: str = "#8c929c"
    roof_colour: str = "#3a404c"
    dugouts: bool = True
    screens: int = 2

    @property
    def half(self):
        return PITCH.get(self.sport, PITCH["soccer"])


PRESETS = {
    "bowl": StadiumSpec(name="bowl"),
    "classic": StadiumSpec(name="classic", open_corners=True, corner_radius=4.0, tiers=[Tier(18, .45), Tier(10, .6)],
                           floodlights="roof", seat_colour="#7f1d1d", seat_alt="#8f2525", runoff_x=8.0, runoff_z=6.0),
    "ground": StadiumSpec(name="ground", open_corners=True, corner_radius=3.0, tiers=[Tier(14, .40)], roof_cover=.6,
                          floodlights="masts", seat_colour="#14532d", seat_alt="#166534", runoff_x=7.0, runoff_z=5.5,
                          screens=1),
}


def preset(name, **over):
    d = asdict(PRESETS[name])
    d["tiers"] = [Tier(**t) for t in d["tiers"]]
    d.update(over)
    return StadiumSpec(**d)


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255


# ------------------------------------------------------------------ ring
class Ring:
    """A rounded rectangle around the pitch: point(i, d) = base[i] + dir[i] * (r + d).  With open corners
    the corner samples are flagged so stands stop short of them."""

    def __init__(self, spec: StadiumSpec, step=1.6, arc=10):
        hl, hw = spec.half
        a0, b0 = hl + spec.runoff_x, hw + spec.runoff_z
        r = spec.corner_radius
        ca, cb = a0 - r, b0 - r
        base, dirs, corner, side = [], [], [], []

        def edge(p0, p1, d, s):
            n = max(1, int(math.ceil(np.linalg.norm(np.subtract(p1, p0)) / step)))
            for k in range(n):
                base.append(np.add(p0, np.subtract(p1, p0) * k / n)); dirs.append(d); corner.append(False); side.append(s)

        def arc_(c, th0):
            for j in range(arc):
                th = th0 + .5 * math.pi * j / arc
                base.append(np.array(c, float)); dirs.append((math.cos(th), math.sin(th))); corner.append(True); side.append(-1)
        edge((ca, -cb), (ca, cb), (1, 0), 0)          # +X end
        arc_((ca, cb), 0)
        edge((ca, cb), (-ca, cb), (0, 1), 1)          # +Z side
        arc_((-ca, cb), .5 * math.pi)
        edge((-ca, cb), (-ca, -cb), (-1, 0), 2)       # -X end
        arc_((-ca, -cb), math.pi)
        edge((-ca, -cb), (ca, -cb), (0, -1), 3)       # -Z side
        arc_((ca, -cb), 1.5 * math.pi)
        self.base, self.dir = np.array(base, float), np.array(dirs, float)
        self.corner, self.side = np.array(corner), np.array(side)
        self.r, self.n = r, len(base)
        self.open = spec.open_corners

    def pt(self, i, d):
        k = i % self.n
        return self.base[k] + self.dir[k] * (self.r + d)

    def active(self, i):
        """segment i -> i+1 carries a stand"""
        if not self.open:
            return True
        return not (self.corner[i % self.n] or self.corner[(i + 1) % self.n])


# ------------------------------------------------------------------ mesh builder
class Mesh:
    def __init__(self, name, material, color=None, emissive=0.0, alpha=1.0):
        self.name, self.material, self.emissive, self.alpha = name, material, emissive, alpha
        self.color = color
        self.V, self.N, self.C, self.UV, self.F = [], [], [], [], []

    def quad(self, a, b, c, d, col=(1, 1, 1), uv=None, n=None):
        if len(col) == 3:
            col = (col[0], col[1], col[2], 1.0)
        a, b, c, d = (np.asarray(x, float) for x in (a, b, c, d))
        if n is None:
            n = np.cross(b - a, d - a)
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-9 else np.array([0, 1.0, 0])
        o = len(self.V)
        self.V += [a, b, c, d]; self.N += [n] * 4; self.C += [col] * 4
        self.UV += list(uv) if uv is not None else [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.F += [(o, o + 1, o + 2), (o, o + 2, o + 3)]

    def box(self, c, s, col=(1, 1, 1), yaw=0.0):
        c = np.asarray(c, float); hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
        cy, sy = math.cos(yaw), math.sin(yaw)
        R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        P = [c + R @ np.array(p) for p in [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
                                            (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]]
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)):
            self.quad(*(P[k] for k in q), col=col)

    def cyl(self, p0, p1, r, col=(1, 1, 1), seg=8):
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        ax = p1 - p0; L = np.linalg.norm(ax); ax /= L
        u = np.cross(ax, [0, 0, 1.0] if abs(ax[1]) > .9 else [0, 1.0, 0]); u /= np.linalg.norm(u)
        v = np.cross(ax, u)
        for k in range(seg):
            a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
            o0 = (math.cos(a0) * u + math.sin(a0) * v) * r; o1 = (math.cos(a1) * u + math.sin(a1) * v) * r
            self.quad(p0 + o0, p0 + o1, p1 + o1, p1 + o0, col=col)

    def arrays(self):
        if not self.V:
            return None
        return (np.array(self.V, np.float32), np.array(self.N, np.float32), np.array(self.C, np.float32),
                np.array(self.UV, np.float32), np.array(self.F, np.uint32))


def _strip(m, ring, da, ha, db, hb, col_fn=None, normal=None, only=None):
    for i in range(ring.n):
        if not ring.active(i) or (only is not None and not only(i)):
            continue
        j = i + 1
        a0, a1 = ring.pt(i, da), ring.pt(j, da)
        b0, b1 = ring.pt(i, db), ring.pt(j, db)
        col = col_fn(i) if col_fn else (1, 1, 1)
        m.quad((a0[0], ha, a0[1]), (b0[0], hb, b0[1]), (b1[0], hb, b1[1]), (a1[0], ha, a1[1]), col=col, n=normal)


# ------------------------------------------------------------------ build
def build(spec: StadiumSpec):
    """-> (meshes {name: Mesh}, info dict, seats ndarray (n,6))"""
    hl, hw = spec.half
    ring = Ring(spec)
    M = {k: Mesh(k, k) for k in ("stand_seats", "stand_concrete", "roof", "roof_fascia", "roof_columns",
                                  "floodlight_masts", "floodlight_lamps", "ad_ring", "screens", "dugouts",
                                  "dugout_glass", "tunnel", "concourse")}
    M["roof_fascia"].emissive = 1.2
    M["floodlight_lamps"].emissive = 6.0
    M["dugout_glass"].alpha = .35
    seatA, seatB = _rgb(spec.seat_colour), _rgb(spec.seat_alt)
    concrete = _rgb(spec.concrete)

    def end_of(i, d=4.0):
        p = ring.pt(i, d)
        if abs(p[0]) > hl + spec.runoff_x - 1 and abs(p[1]) < hw - 2:
            return -1 if p[0] < 0 else 1
        return 0

    def seat_col(i, row, tier):
        sector = i // 7
        c = seatA if sector % 2 == 0 else seatB
        if tier > 0:
            c = c * .85
        e = end_of(i)
        a = 1.0
        if e:
            # the ends wear the clubs' colours: baked here as a grey level the game tints, alpha .25 home / .5 away
            c = np.full(3, .78 if (sector + row) % 3 else .92)
            a = .25 if e < 0 else .5
        if row % 5 == 0:
            c = np.minimum(c * 1.18 + .02, 1)
        if i % 24 in (0, 1):            # aisle stairs: a lighter concrete stripe every ~38 m
            c, a = concrete * .95, 1.0
        return (float(c[0]), float(c[1]), float(c[2]), a)

    # front wall
    _strip(M["stand_concrete"], ring, 0, 0, 0, 1.1, lambda i: tuple(concrete * .7))
    d, h = 0.0, 1.1
    seats, tier_d0 = [], []
    for ti, t in enumerate(spec.tiers):
        if ti > 0:
            _strip(M["stand_concrete"], ring, d, h, d + spec.aisle, h, lambda i: tuple(concrete))
            d += spec.aisle
            _strip(M["stand_concrete"], ring, d, h, d, h + 1.0, lambda i: tuple(concrete * .85))
            h += .6
        tier_d0.append(d)
        for r in range(t.rows):
            _strip(M["stand_concrete"], ring, d, h, d, h + t.rise, lambda i: tuple(concrete * .8))
            h += t.rise
            _strip(M["stand_seats"], ring, d, h, d + t.depth, h, lambda i, r=r, ti=ti: seat_col(i, r, ti), normal=(0, 1, 0))
            dm = d + t.depth * .55
            for i in range(ring.n):
                if not ring.active(i) or i % 24 in (0, 1):
                    continue
                a, b = ring.pt(i, dm), ring.pt(i + 1, dm)
                L = float(np.linalg.norm(b - a))
                cnt = int(L / spec.seat_pitch)
                inward = -ring.dir[i % ring.n]
                yaw = math.atan2(inward[0], inward[1])
                for s in range(cnt):
                    p = a + (b - a) * (s + .5) / max(cnt, 1)
                    seats.append((p[0], h, p[1], yaw, ti, end_of(i)))
            d += t.depth
    d_top, h_top = d, h
    _strip(M["stand_concrete"], ring, d_top, h_top, d_top, h_top + 7.0, lambda i: tuple(concrete * .75))
    # vomitories: dark portals in the aisle riser between tiers
    if len(spec.tiers) > 1:
        dv = tier_d0[1] - 0.01
        hv = 1.1 + spec.tiers[0].rows * spec.tiers[0].rise
        for i in range(0, ring.n, 24):
            if not ring.active(i) or not ring.active(i + 1):
                continue
            a, b = ring.pt(i + 12, dv), ring.pt(i + 13, dv)
            M["tunnel"].quad((a[0], hv + .05, a[1]), (a[0], hv + .95, a[1]), (b[0], hv + .95, b[1]), (b[0], hv + .05, b[1]),
                             col=(.05, .05, .06))
    # roof
    lights, roof_lip = [], None
    if spec.roof:
        last = spec.tiers[-1]
        roof_d0 = d_top - last.rows * last.depth * spec.roof_cover
        roof_h0 = h_top + 3.0
        _strip(M["roof"], ring, roof_d0, roof_h0, d_top + 3.0, h_top + 8.0, lambda i: tuple(_rgb(spec.roof_colour)))
        _strip(M["roof_fascia"], ring, roof_d0, roof_h0 - .9, roof_d0, roof_h0 + .35, lambda i: (.88, .9, .96))
        roof_lip = (roof_d0, roof_h0)
        for i in range(0, ring.n, 12):
            if not ring.active(i):
                continue
            p = ring.pt(i, d_top + 1.5)
            M["roof_columns"].cyl((p[0], 0, p[1]), (p[0], h_top + 8.0, p[1]), .35, col=(.55, .57, .62))
        if spec.floodlights == "roof":
            for i in range(0, ring.n, 4):
                if not ring.active(i):
                    continue
                p = ring.pt(i, roof_d0 + .2)
                c = (p[0], roof_h0 - 1.1, p[1])
                M["floodlight_lamps"].box(c, (1.0, .5, 1.0), col=(1, .97, .86))
                if i % 16 == 0:
                    lights.append({"pos": list(map(float, c)), "aim": [0.0, 0.0, 0.0], "kind": "roof"})
    if spec.floodlights == "masts":
        corner_d = (roof_lip[0] if roof_lip else d_top) + 10.0
        base_h = h_top + 5.0
        for sx in (-1, 1):
            for sz in (-1, 1):
                dirn = np.array([sx, sz], float) / math.sqrt(2)
                c = np.array([(hl + spec.runoff_x - spec.corner_radius) * sx, (hw + spec.runoff_z - spec.corner_radius) * sz]) \
                    + dirn * (spec.corner_radius + corner_d)
                top = base_h + 24.0
                M["floodlight_masts"].cyl((c[0], 0, c[1]), (c[0], top, c[1]), .5, col=(.42, .45, .5))
                yaw = math.atan2(-c[0], -c[1])
                M["floodlight_masts"].box((c[0], top + 2.2, c[1]), (7.6, 4.6, .4), col=(.16, .18, .22), yaw=yaw)
                fwd = np.array([math.sin(yaw), 0, math.cos(yaw)])
                right = np.array([math.cos(yaw), 0, -math.sin(yaw)])
                for gx in range(6):
                    for gy in range(4):
                        p = np.array([c[0], top + 2.2, c[1]]) + right * (-3.0 + gx * 1.2) + np.array([0, -1.65 + gy * 1.1, 0]) + fwd * .25
                        M["floodlight_lamps"].box(p, (.7, .55, .12), col=(1, .97, .86), yaw=yaw)
                lights.append({"pos": [float(c[0]), float(top + 2.2), float(c[1])], "aim": [0.0, 0.0, 0.0], "kind": "mast"})
    # advertising ring: a continuous LED band just outside the touchlines / goal lines
    off_x, off_z = hl + min(5.2, spec.runoff_x - 1.5), hw + min(4.2, spec.runoff_z - 1.5)
    per = 4 * (off_x + off_z)
    u = 0.0
    for (p0, p1) in [((-off_x, -off_z), (off_x, -off_z)), ((off_x, -off_z), (off_x, off_z)),
                     ((off_x, off_z), (-off_x, off_z)), ((-off_x, off_z), (-off_x, -off_z))]:
        L = math.dist(p0, p1)
        n = int(L / 6)
        for k in range(n):
            a = np.add(p0, np.subtract(p1, p0) * k / n); b = np.add(p0, np.subtract(p1, p0) * (k + 1) / n)
            u0, u1 = u / per, (u + L / n) / per
            if spec.dugouts and p0[1] < 0 and p1[1] < 0 and (min(abs(a[0]), abs(b[0])) < 14 or a[0] * b[0] < 0):
                u += L / n          # the technical area: no boards in front of the dugouts
                continue
            M["ad_ring"].quad((a[0], .05, a[1]), (b[0], .05, b[1]), (b[0], 1.0, b[1]), (a[0], 1.0, a[1]),
                              uv=[(u0, 1), (u1, 1), (u1, 0), (u0, 0)])
            u += L / n
    # screens: under the roof at the ends
    scr = []
    for k in range(spec.screens):
        sx = -1 if k == 0 else 1
        x = sx * (hl + spec.runoff_x + (d_top * .55 if spec.roof else d_top + 2))
        y = (roof_lip[1] - 3.5) if roof_lip else h_top + 6
        z = hw * .45 * (1 if k == 0 else -1)
        w, hgt = 14.0, 6.0
        M["concourse"].box((x + sx * .4, y, z), (.6, hgt + .8, w + .8), col=(.06, .06, .07))
        xs = x - sx * .02
        M["screens"].quad((xs, y - hgt / 2, z - sx * w / 2), (xs, y - hgt / 2, z + sx * w / 2), (xs, y + hgt / 2, z + sx * w / 2),
                          (xs, y + hgt / 2, z - sx * w / 2), uv=[(0, 1), (1, 1), (1, 0), (0, 0)])
        scr.append({"centre": [float(x), float(y), float(z)], "size": [w, hgt], "faces": [-sx, 0, 0]})
    # dugouts + tunnel on the -Z side
    dug = []
    if spec.dugouts:
        zb = -(hw + min(3.2, spec.runoff_z - 1.6))
        for k, xc in enumerate((-9.0, 9.0)):
            M["dugouts"].box((xc, .02, zb - .4), (7.5, .04, 2.0), col=(.18, .19, .2))           # floor
            M["dugouts"].box((xc, .55, zb - 1.15), (7.5, .9, .5), col=(.12, .13, .15))           # seat block
            for s in range(10):
                M["dugouts"].box((xc - 3.2 + s * .71, .62, zb - .95), (.55, .1, .45), col=tuple(_rgb(spec.seat_colour)))
            M["dugouts"].box((xc, 2.25, zb - .6), (7.7, .08, 2.2), col=(.75, .77, .8))           # roof
            M["dugouts"].box((xc - 3.85, 1.12, zb - .6), (.06, 2.25, 2.2), col=(.75, .77, .8))
            M["dugouts"].box((xc + 3.85, 1.12, zb - .6), (.06, 2.25, 2.2), col=(.75, .77, .8))
            M["dugout_glass"].quad((xc - 3.85, .4, zb + .48), (xc + 3.85, .4, zb + .48), (xc + 3.85, 2.2, zb + .48),
                                   (xc - 3.85, 2.2, zb + .48), col=(.8, .9, 1.0))
            dug.append({"centre": [xc, 0.0, zb - .6], "seats": 10, "team": k, "front_z": float(zb + .48)})
        zt = -(hw + spec.runoff_z)
        M["tunnel"].box((0, 1.4, zt - .3), (4.5, 2.8, .6), col=(.03, .03, .04))
        M["tunnel"].box((0, 2.9, zt + .8), (5.2, .15, 3.0), col=(.7, .72, .76))
        tunnel = {"mouth": [0.0, 0.0, float(zt + .6)]}
    else:
        tunnel = None
    # concourse ground out to the back of the stand
    R = max(hl, hw) + spec.runoff_x + d_top + 30
    M["concourse"].quad((-R, -.06, -R), (-R, -.06, R), (R, -.06, R), (R, -.06, -R), col=(.08, .09, .11), n=(0, 1, 0))
    seats = np.array(seats, np.float32)
    info = {"version": "11.32", "spec": _spec_dict(spec), "pitch_half": [hl, hw], "lights": lights, "screens": scr,
            "dugouts": dug, "tunnel": tunnel, "seats": int(len(seats)),
            "seats_by_end": {k: int((seats[:, 5] == v).sum()) for k, v in (("home", -1), ("away", 1), ("side", 0))},
            "stand_top": [float(d_top), float(h_top)], "roof_lip": list(roof_lip) if roof_lip else None}
    return M, info, seats


def _spec_dict(spec):
    d = asdict(spec)
    return d


# ------------------------------------------------------------------ GLB
def write_glb(meshes, path, extras=None):
    from .glbpack import _Out
    out = _Out()
    nodes, gmeshes, mats = [], [], []
    for name, m in meshes.items():
        arr = m.arrays()
        if arr is None:
            continue
        V, N, C, UV, F = arr
        mat = {"name": m.material, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, m.alpha], "metallicFactor": 0.0,
                                                             "roughnessFactor": .85}, "doubleSided": True}
        if m.emissive > 0:
            mat["emissiveFactor"] = [1.0, 1.0, 1.0]
            mat["extensions"] = {"KHR_materials_emissive_strength": {"emissiveStrength": m.emissive}}
        if m.alpha < 1:
            mat["alphaMode"] = "BLEND"
        mats.append(mat)
        Ca = C
        attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True), "NORMAL": out.add(N, 5126, "VEC3", 34962),
                 "COLOR_0": out.add(np.round(np.clip(Ca, 0, 1) * 255).astype(np.uint8), 5121, "VEC4", 34962),
                 "TEXCOORD_0": out.add(UV, 5126, "VEC2", 34962)}
        out.acc[attrs["COLOR_0"]]["normalized"] = True
        ind = out.add(F.reshape(-1).astype(np.uint16), 5123, "SCALAR", 34963) if len(V) < 65535 else \
            out.add(F.reshape(-1), 5125, "SCALAR", 34963)

        gmeshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind, "material": len(mats) - 1, "mode": 4}]})
        nodes.append({"name": name, "mesh": len(gmeshes) - 1})
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge stadium (v11.32)"}, "scene": 0,
          "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gmeshes, "materials": mats,
          "accessors": out.acc, "bufferViews": out.views, "buffers": [{"byteLength": 0}],
          "extensionsUsed": ["KHR_materials_emissive_strength"]}
    if extras:
        gl["asset"]["extras"] = extras
    from .officials import _write
    return _write(gl, out.b, path)


def export(spec, glb_path):
    """GLB + <stem>.seats (float32 x, y, z, yaw, tier, end) + <stem>.json.  -> info."""
    meshes, info, seats = build(spec)
    tris = sum(len(m.F) for m in meshes.values())
    info["tris"] = int(tris)
    write_glb(meshes, glb_path, extras={"stadium": {k: v for k, v in info.items() if k != "spec"}})
    stem = glb_path[:-4] if glb_path.endswith(".glb") else glb_path
    with open(stem + ".seats", "wb") as f:
        f.write(struct.pack("<I", len(seats)))
        f.write(seats.astype("<f4").tobytes())
    with open(stem + ".json", "w") as f:
        json.dump(info, f, indent=1)
    return info


def read_seats(path):
    with open(path, "rb") as f:
        n = struct.unpack("<I", f.read(4))[0]
        return np.frombuffer(f.read(n * 24), "<f4").reshape(n, 6)
