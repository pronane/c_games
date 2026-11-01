"""Sculpted characters (v10): smooth, rigged 3D fighters built from signed-distance primitives.

The old mannequin (sforge.mesh) is rigid cylinders and spheres.  A sculpted character is a set of bone-attached SDF
primitives - round cones, ellipsoids, rounded boxes - smooth-unioned per layer (skin, garments, hair, props) and
meshed with marching cubes in a bind pose, so muscles, garments and hair flow into each other like a modelled
character.  Every vertex is skinned to up to four bones (linear blend skinning) from the primitives it came from.
Colour comes from per-region paint functions (faces, fabric patterns, lightning bolts, wraps) evaluated per pixel by
sforge.render_sculpt, or per vertex by the Blender exporter.

The character description is data: build_character(spec) reads the text spec (sforge.spec) - `sculpt = <preset>` picks
a costume preset and every colour / proportion key overrides it - and returns a Character with:
    prims   list of Prim   (bone-local SDF shapes, material, layer, paint tag)
    props   list of Prop   (explicit rigid meshes: katana blade, hairpin)
    paints  tag -> Paint   (bone frame + function(P_local, base_rgb) -> rgb, emissive)
    fx      list of (bone, local point, rgb, radius)   glow emitters (energy in hands)
mesh_character(ch) -> SculptMesh (bind-pose vertices, faces, normals, weights, materials) shared by both renderers.
All of it is procedural geometry of fictional characters."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
from .rig import JOINT_NAMES, evaluate
from .mathutil import euler

BONES = [j for j in JOINT_NAMES if j != "ball"]
BI = {b: i for i, b in enumerate(JOINT_NAMES)}

# arms out, legs slightly apart: no limb touches the body while meshing
BIND_POSE = dict(arm_L=(0, 68, 0), arm_R=(0, 68, 0), leg_L=(0, 7, 0), leg_R=(0, 7, 0), elbow_L=4, elbow_R=4,
                 knee_L=4, knee_R=4, flat=0, ground=False)

# material classes drive shading (roughness, specular, sheen); colours come from paint
MATS = ["skin", "cloth", "silk", "leather", "hair", "metal", "eye", "glow", "rubber"]
MI = {m: i for i, m in enumerate(MATS)}
SHADING = {   # (specular strength, shininess, rim strength, subsurface warmth)
    "skin": (0.30, 22, 1.0, 0.35), "cloth": (0.06, 8, 0.8, 0.0), "silk": (0.22, 30, 1.0, 0.0),
    "leather": (0.25, 26, 0.9, 0.0), "hair": (0.28, 40, 1.0, 0.0), "metal": (0.95, 80, 1.0, 0.0),
    "eye": (0.6, 60, 0.4, 0.0), "glow": (0.0, 1, 0.0, 0.0), "rubber": (0.18, 20, 0.9, 0.0),
}


@dataclass
class Prim:
    bone: str
    kind: str                 # cap | ell | box
    a: tuple = (0, 0, 0)      # cap: start, ell/box: centre
    b: tuple = (0, 0, 0)      # cap: end, ell/box: radii / half extents
    ra: float = 0.05
    rb: float = 0.05          # box: corner rounding
    rot: tuple = (0, 0, 0)    # euler degrees (ell / box)
    mat: str = "skin"
    layer: str = "skin"
    paint: str = "skin"
    grow: float = 0.0
    cuts: tuple = ()          # ((nx,ny,nz), d): keep n.p <= d (bone-local)
    sub: bool = False         # subtractive (carves its layer)
    fine: bool = False        # meshed in the fine (head) pass
    M: tuple = None           # v10.1: 3x3 axes of an ell / box (columns, bone-local); overrides rot

    def axes(self):
        if self.M is not None:
            return np.asarray(self.M, float)
        return euler(*self.rot) if self.rot != (0, 0, 0) else None

    def local_aabb(self):
        if self.kind == "cap":
            a, b = np.array(self.a, float), np.array(self.b, float)
            r = max(self.ra, self.rb) + self.grow
            lo, hi = np.minimum(a, b) - r, np.maximum(a, b) + r
        else:
            c = np.array(self.a, float)
            R = self.axes()
            h = np.array(self.b, float) + self.grow
            ext = h if R is None else np.abs(R) @ h          # exact box extent of the rotated half-extents
            lo, hi = c - ext, c + ext
        return lo, hi


@dataclass
class Prop:
    bone: str
    tris: np.ndarray          # (n,3,3) bone-local
    mat: str
    paint: str


@dataclass
class Paint:
    bone: str
    fn: object                # fn(P_local (N,3), base (N,3)) -> (rgb (N,3), emissive (N,) 0..1)


@dataclass
class Character:
    name: str
    prims: list
    props: list
    paints: dict
    fx: list = field(default_factory=list)
    layer_k: dict = field(default_factory=dict)
    scale: float = 1.0
    rim: tuple = (0.62, 0.74, 1.0)
    outline: tuple = (20, 16, 22)


# ------------------------------------------------------------------ SDF kernels (vectorised, bone-local points)
def sd_cap(p, a, b, r1, r2):
    """round cone (iq)"""
    a = np.asarray(a, float); b = np.asarray(b, float)
    ba = b - a; l2 = float(ba @ ba)
    if l2 < 1e-12:
        return np.linalg.norm(p - a, axis=-1) - max(r1, r2)
    rr = r1 - r2; a2 = l2 - rr * rr; il2 = 1.0 / l2
    pa = p - a; y = pa @ ba; z = y - l2
    x2v = pa * l2 - y[..., None] * ba
    x2 = np.einsum("...i,...i->...", x2v, x2v)
    y2 = y * y * l2; z2 = z * z * l2
    k = math.copysign(1.0, rr) * rr * rr * x2
    d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
    d1 = np.sqrt(x2 + z2) * il2 - r2
    d2 = np.sqrt(x2 + y2) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))


def sd_ell(p, c, r):
    r = np.maximum(np.asarray(r, float), 1e-4)
    q = p - np.asarray(c, float)
    k0 = np.linalg.norm(q / r, axis=-1)
    k1 = np.linalg.norm(q / (r * r), axis=-1)
    return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -np.min(r))


def sd_box(p, c, h, rnd):
    q = np.abs(p - np.asarray(c, float)) - (np.asarray(h, float) - rnd)
    return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(q.max(-1), 0) - rnd


def prim_sdf(pr: Prim, P):
    """P: points already in the prim's bone frame"""
    if pr.kind == "cap":
        d = sd_cap(P, pr.a, pr.b, pr.ra, pr.rb)
    else:
        q = P
        R = pr.axes()
        if R is not None:
            c = np.asarray(pr.a, float)
            q = (P - c) @ R + c          # inverse rotation about the centre
        d = sd_ell(q, pr.a, pr.b) if pr.kind == "ell" else sd_box(q, pr.a, pr.b, pr.rb)
    d = d - pr.grow
    for n, off in pr.cuts:
        n = np.asarray(n, float); n = n / np.linalg.norm(n)
        d = np.maximum(d, P @ n - off)
    return d


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


# ------------------------------------------------------------------ bind pose
_BIND = {}


def bind_world():
    if "W" not in _BIND:
        st = evaluate(dict(BIND_POSE))
        _BIND["W"] = {n: st.world[n].copy() for n in JOINT_NAMES}
    return _BIND["W"]


# ------------------------------------------------------------------ colour helpers for paints
def hexc(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-12), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def in_poly(x, y, poly):
    """even-odd point in polygon for arrays x,y"""
    inside = np.zeros(x.shape, bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        cond = ((y0 > y) != (y1 > y)) & (x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0)
        inside ^= cond
    return inside


def ellmask(x, y, cx, cy, rx, ry, soft=0.15):
    d = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
    return 1 - smooth(1 - soft, 1 + soft, d)


# ------------------------------------------------------------------ face
def face_paint(skin, eye_rgb, brow_rgb, lips_rgb=None, female=False, glow_eyes=False, scowl=0.5, liner=0.0,
               mask=None, stubble=None, scar=None):
    """paint function in head-local coords (head joint origin, face towards +z)"""
    skin = np.asarray(skin, float); eye_rgb = np.asarray(eye_rgb, float); brow_rgb = np.asarray(brow_rgb, float)
    lips = np.asarray(lips_rgb if lips_rgb is not None else skin * np.array([0.82, 0.55, 0.52]), float)

    def fn(P, base):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        col = np.broadcast_to(skin, base.shape).copy()
        em = np.zeros(len(P))
        front = smooth(0.035, 0.06, z)
        ax = np.abs(x)
        # soft shading cues: cheek blush, eye sockets, under-nose, temples
        sock = ellmask(ax, y, 0.034, 0.110, 0.030, 0.020, 0.5) * front
        col = mix(col, col * 0.78, sock * 0.55)
        if female:
            blush = ellmask(ax, y, 0.050, 0.078, 0.026, 0.016, 0.6) * front
            col = mix(col, col * np.array([1.05, 0.86, 0.86]), blush * 0.5)
        # eyes
        tilt = 0.12 * (ax - 0.034) * (1 if female else -1)
        ey = y - tilt
        eyew = ellmask(ax, ey, 0.034, 0.110, 0.0175, 0.0072 if not female else 0.0085, 0.25) * front
        iris = ellmask(ax, ey, 0.031, 0.110, 0.0072, 0.0072, 0.3) * eyew
        pupil = ellmask(ax, ey, 0.031, 0.110, 0.0034, 0.0034, 0.3) * eyew
        if glow_eyes:
            col = mix(col, np.array([0.05, 0.05, 0.08]), eyew)
            col = mix(col, eye_rgb, iris)
            col = mix(col, np.array([0.9, 1.0, 1.0]), pupil * 0.8)
            em = np.maximum(em, iris * 1.0)
        else:
            col = mix(col, np.array([0.93, 0.91, 0.88]), eyew * 0.95)
            col = mix(col, eye_rgb, iris)
            col = mix(col, np.array([0.03, 0.02, 0.02]), pupil)
            hl = ellmask(ax, ey, 0.028, 0.113, 0.0022, 0.0022, 0.3) * eyew
            col = mix(col, np.array([1, 1, 1]), hl * 0.9)
        # upper lid line (liner) + lashes for female
        lid = np.exp(-((ey - (0.110 + 0.0075 + 0.35 * (ax - 0.034) ** 2 / 0.0175)) / 0.0022) ** 2) * (ax > 0.014) * (ax < 0.054) * front
        col = mix(col, np.array([0.06, 0.04, 0.04]), np.clip(lid * (0.9 + liner), 0, 1))
        # brows (scowl pulls the inner ends down)
        by = 0.128 - scowl * 0.010 * (1 - np.clip((ax - 0.012) / 0.04, 0, 1)) + (0.003 if female else 0.0)
        bw = 0.0035 if female else 0.0058
        brow = np.exp(-((y - by) / bw) ** 2) * (ax > 0.010) * (ax < 0.056) * front
        col = mix(col, brow_rgb, np.clip(brow * 1.15, 0, 1))
        # nose shadow, mouth, lips
        ns = ellmask(ax, y, 0.0, 0.082, 0.016, 0.006, 0.6) * front
        col = mix(col, col * 0.72, ns * 0.6)
        mouth_w = 0.020 if female else 0.023
        mline = np.exp(-((y - 0.060 - 0.10 * scowl * (ax / mouth_w) ** 2 * 0.01) / 0.0018) ** 2) * (ax < mouth_w) * front
        lipm = ellmask(ax, y, 0.0, 0.058, mouth_w * 0.95, 0.0075 if female else 0.005, 0.3) * front
        col = mix(col, lips, lipm * (0.85 if female else 0.45))
        col = mix(col, np.array([0.22, 0.08, 0.07]), mline * 0.85)
        if stubble is not None:
            st = ((y < 0.075) & (z > 0.0)).astype(float) * smooth(0.0, 0.03, z)
            col = mix(col, col * np.asarray(stubble), st * 0.35)
        if scar is not None:
            sx = np.exp(-((x - scar[0] - (y - scar[1]) * 0.35) / 0.0018) ** 2) * (np.abs(y - scar[1]) < 0.022) * front
            col = mix(col, col * 0.6, sx)
        if mask is not None:
            col, em = mask(P, col, em)
        return col, em
    return fn


# ------------------------------------------------------------------ body builder
class B:
    """collects prims"""
    def __init__(self):
        self.prims, self.props, self.paints, self.fx = [], [], {}, []

    def add(self, bone, kind, a, b, ra=0.0, rb=0.0, **kw):
        self.prims.append(Prim(bone, kind, tuple(a), tuple(b), ra, rb, **kw)); return self.prims[-1]

    def cap(self, bone, a, b, ra, rb=None, **kw):
        return self.add(bone, "cap", a, b, ra, ra if rb is None else rb, **kw)

    def ell(self, bone, c, r, **kw):
        return self.add(bone, "ell", c, r, **kw)

    def box(self, bone, c, h, rnd=0.01, **kw):
        return self.add(bone, "box", c, h, 0.0, rnd, **kw)

    def sym(self, fn, bone_base, *args, **kw):
        """call fn for L and R: positions with x mirrored for the right side"""
        out = []
        for side, s in (("L", 1), ("R", -1)):
            def mx(v):
                return (v[0] * s,) + tuple(v[1:]) if isinstance(v, tuple) and len(v) == 3 else v
            a2 = [mx(v) for v in args]
            kw2 = dict(kw)
            if "rot" in kw2:
                r = kw2["rot"]; kw2["rot"] = (r[0], -r[1] if s < 0 else r[1], -r[2] if s < 0 else r[2])
            out.append(fn(bone_base + side, *a2, **kw2))
        return out


def body(b: B, g=1.0, musc=0.6, fem=False, hs=1.0, slim_limbs=1.0, hands="fist", neck=1.0):
    """skin layer: anatomy with muscle masses (all procedural)"""
    gw = g * (0.86 if fem else 1.0); gd = g * (0.95 if fem else 1.0); gl = g * slim_limbs * (0.84 if fem else 1.0)
    K = dict(layer="skin", mat="skin", paint="skin")
    # pelvis + glutes
    b.ell("hips", (0, -0.035, 0), (0.150 * gw * (1.18 if fem else 1.0), 0.115, 0.112 * gd), **K)
    for s in (1, -1):                                                                     # glutes
        b.ell("hips", (0.065 * s * gw, -0.075, -0.055 * gd), (0.075 * g * (1.1 if fem else 1.0), 0.085, 0.065 * gd), **K)
    # abdomen / waist
    b.ell("spine", (0, 0.085, 0.004), (0.128 * gw * (0.88 if fem else 1.0), 0.13, 0.098 * gd), **K)
    # ribcage
    b.ell("chest", (0, 0.080, -0.005), (0.160 * gw * (0.9 if fem else 1.0), 0.150, 0.112 * gd), **K)
    if musc > 0.2 and not fem:
        for s in (1, -1):    # pecs, lats on the chest bone
            b.ell("chest", (0.072 * s * gw, 0.118, 0.072 * gd), (0.082 * g, 0.064 * (0.8 + 0.3 * musc), 0.046 * gd * (0.8 + 0.4 * musc)), rot=(0, 0, -8 * s), **K)
            b.ell("chest", (0.112 * s * gw, 0.040, -0.030), (0.065 * g, 0.125, 0.070 * gd), rot=(0, 0, 14 * s), **K)
        for y in (0.170, 0.115, 0.060):    # abs (6 pack) on the spine
            for s in (1, -1):
                b.ell("spine", (0.029 * s, y, 0.088 * gd), (0.027, 0.024, 0.018 * (0.6 + 0.6 * musc)), **K)
        b.ell("chest", (0, 0.205, -0.035), (0.125 * gw, 0.055 * (0.7 + 0.5 * musc), 0.065), **K)        # traps
    if fem:
        for s in (1, -1):
            b.ell("chest", (0.058 * s, 0.085, 0.082 * gd), (0.056, 0.052, 0.046), **K)
    # neck
    b.cap("neck", (0, -0.05, -0.005), (0, 0.12, 0.012), 0.056 * gw * neck * (0.85 if fem else 1.0), 0.050 * gw * neck * (0.85 if fem else 1.0), **K)
    # arms
    for s, side in ((1, "L"), (-1, "R")):
        ua, fa, hd = "upperarm_" + side, "forearm_" + side, "hand_" + side
        b.ell(ua, (0.004 * s, -0.025, 0.0), (0.070 * gl * (0.85 + 0.3 * musc), 0.085, 0.072 * gl * (0.85 + 0.3 * musc)), **K)   # deltoid
        b.cap(ua, (0, 0.0, 0), (0, -0.27, 0), 0.050 * gl, 0.040 * gl, **K)
        b.ell(ua, (0, -0.135, 0.022), (0.042 * gl * (0.8 + 0.4 * musc), 0.085, 0.044 * gl * (0.8 + 0.4 * musc)), **K)    # biceps
        b.ell(ua, (0, -0.120, -0.026), (0.044 * gl, 0.095, 0.042 * gl * (0.85 + 0.3 * musc)), **K)                         # triceps
        b.cap(fa, (0, 0.01, 0), (0, -0.235, 0), 0.044 * gl, 0.030 * gl, **K)
        b.ell(fa, (0.006 * s, -0.065, 0.008), (0.047 * gl * (0.85 + 0.25 * musc), 0.085, 0.042 * gl), **K)                 # forearm mass
        if hands == "fist":
            b.box(hd, (0, -0.062, 0.006), (0.038 * gl ** 0.5, 0.052, 0.047 * gl ** 0.5), 0.022, **K)
            b.cap(hd, (0.030 * s, -0.025, 0.035), (0.010 * s, -0.070, 0.055), 0.013, 0.011, **K)                           # thumb
        else:   # open claw hand
            b.box(hd, (0, -0.050, 0.0), (0.036, 0.040, 0.016), 0.012, **K)
            for i, fx in enumerate((-0.024, -0.008, 0.008, 0.024)):
                b.cap(hd, (fx, -0.085, 0.0), (fx * 1.1, -0.13, 0.022), 0.0085, 0.007, **K)
            b.cap(hd, (0.03 * s, -0.04, 0.012), (0.05 * s, -0.08, 0.035), 0.01, 0.008, **K)
    # legs
    for s, side in ((1, "L"), (-1, "R")):
        th, sh, ft = "thigh_" + side, "shin_" + side, "foot_" + side
        b.cap(th, (0, 0.02, 0), (0, -0.40, 0), 0.086 * g * (1.06 if fem else 1.0), 0.054 * g, **K)
        b.ell(th, (0.0, -0.17, 0.028), (0.066 * g, 0.150, 0.058 * g * (0.8 + 0.3 * musc)), **K)                             # quads
        b.ell(th, (0.025 * s, -0.25, 0.0), (0.050 * g, 0.12, 0.05 * g), **K)                                                # vastus
        b.cap(sh, (0, 0.0, 0), (0, -0.375, -0.005), 0.052 * g, 0.033 * g, **K)
        b.ell(sh, (0, -0.115, -0.030), (0.050 * g, 0.105, 0.050 * g * (0.85 + 0.3 * musc)), **K)                            # calf
        b.ell(sh, (0, 0.0, 0.026), (0.040 * g, 0.035, 0.028), **K)                                                         # knee
        b.box(ft, (0, -0.052, 0.058), (0.044, 0.030, 0.118), 0.026, **K)
        b.cap(ft, (0, 0.0, 0), (0, -0.05, 0.01), 0.036, 0.04, **K)
    # head (fine pass)
    H = dict(K, fine=True, paint="face")
    b.ell("head", (0, 0.118, -0.012), (0.086 * hs, 0.104 * hs, 0.100 * hs), **H)                 # cranium
    b.ell("head", (0, 0.068, 0.030), (0.066 * hs * (0.94 if fem else 1.0), 0.072 * hs, 0.072 * hs), **H)  # face mass
    if not fem:
        b.box("head", (0, 0.034, 0.040), (0.050 * hs, 0.030, 0.050), 0.026, **H)                 # jaw
    b.ell("head", (0, 0.022, 0.066), (0.026 * hs, 0.022, 0.022), **H)                             # chin
    b.ell("head", (0, 0.128, 0.074), (0.066 * hs, 0.016 if fem else 0.019, 0.026), **H)          # brow ridge
    for s in (1, -1):
        b.ell("head", (0.044 * s, 0.093, 0.062), (0.026, 0.017, 0.026), **H)                     # cheekbones
        b.ell("head", (0.083 * s * hs, 0.100, -0.006), (0.009, 0.022, 0.015), **H)                # ears
    b.cap("head", (0, 0.116, 0.090), (0, 0.083, 0.110), 0.008, 0.013 if not fem else 0.010, **H)  # nose
    b.ell("head", (0, 0.060, 0.086), (0.020, 0.010 if fem else 0.007, 0.012), **H)               # lips


def shell(b: B, src, grow, layer, mat, paint, cuts=(), filt=None, extra_rb=None):
    """garment: copies of body prims grown outward (cloth over muscle)"""
    out = []
    for p in list(src):
        if filt and not filt(p):
            continue
        q = Prim(p.bone, p.kind, p.a, p.b, p.ra, p.rb, p.rot, mat, layer, paint, p.grow + grow, tuple(cuts) + tuple(p.cuts), fine=p.fine)
        b.prims.append(q); out.append(q)
    return out


def bone_prims(b, bones, layer="skin"):
    return [p for p in b.prims if p.bone in bones and p.layer == layer and p.kind != "box" or (p.bone in bones and p.layer == layer and p.kind == "box")]


TORSO = ("hips", "spine", "chest")


# ------------------------------------------------------------------ paints
def plain(bone, rgb):
    rgb = np.asarray(rgb, float)
    return Paint(bone, lambda P, base, c=rgb: (np.broadcast_to(c, base.shape).copy(), np.zeros(len(P))))


def shaded_skin(bone, rgb, abs_lines=0.0, veins=0.0):
    rgb = np.asarray(rgb, float)
    def fn(P, base):
        col = np.broadcast_to(rgb, base.shape).copy()
        return col, np.zeros(len(P))
    return Paint(bone, fn)


def wraps(bone, rgb, axis=1, pitch=0.022, dark=0.78):
    """hand / forearm wraps: diagonal bands of tape"""
    rgb = np.asarray(rgb, float)
    def fn(P, base):
        t = P[:, axis] + 0.45 * P[:, 0] + 0.25 * P[:, 2]
        band = 0.5 + 0.5 * np.cos(2 * math.pi * t / pitch)
        line = np.exp(-((((t / pitch) % 1.0) - 0.5) / 0.08) ** 2)
        col = rgb * (1 - (1 - dark) * (0.3 * band + 0.7 * line))[:, None]
        return col, np.zeros(len(P))
    return Paint(bone, fn)


def ribbing(bone, rgb, pitch=0.02, depth=0.15, axis=1):
    rgb = np.asarray(rgb, float)
    def fn(P, base):
        k = 1 - depth * (0.5 + 0.5 * np.cos(2 * math.pi * P[:, axis] / pitch))
        return rgb * k[:, None], np.zeros(len(P))
    return Paint(bone, fn)


def floral(bone, rgb, petal_rgb, scale=0.065, seed=3):
    """kimono print: scattered five-petal flowers"""
    rgb = np.asarray(rgb, float); petal = np.asarray(petal_rgb, float)
    rng = np.random.default_rng(seed)
    cents = rng.uniform(-0.6, 0.6, (90, 3))
    def fn(P, base):
        col = np.broadcast_to(rgb, base.shape).copy()
        best = np.full(len(P), 9.0); ang = np.zeros(len(P))
        for c in cents:
            d = np.linalg.norm((P - c * np.array([1, 1.4, 1])) / scale, axis=1)
            m = d < best
            best = np.where(m, d, best)
            q = P - c * np.array([1, 1.4, 1])
            ang = np.where(m, np.arctan2(q[:, 1], q[:, 0] + q[:, 2] * 0.5), ang)
        r = 0.32 + 0.12 * np.cos(5 * ang)
        petals = 1 - smooth(r - 0.05, r + 0.05, best)
        centre = 1 - smooth(0.06, 0.1, best)
        col = mix(col, petal, petals * 0.85)
        col = mix(col, petal * 0.6 + np.array([0.3, 0.25, 0.1]), centre)
        # subtle fabric weave + fold darkening
        col = col * (0.96 + 0.04 * np.cos(P[:, 1] * 900))[:, None]
        return col, np.zeros(len(P))
    return Paint(bone, fn)


# ------------------------------------------------------------------ the six HD Fighter costumes
def _skin(b, rgb):
    b.paints["skin"] = shaded_skin("chest", rgb)


def preset_kairo(sp, C):
    b = B(); hs = 1.0
    body(b, g=1.06, musc=0.95, hs=hs)
    skin = C["skin"]
    _skin(b, skin)
    b.paints["face"] = Paint("head", face_paint(skin, C["eye"], C["hair"], scowl=0.9))
    # spiky black hair (fine pass): scalp shell + spikes swept back
    HAIR = dict(layer="hair", mat="hair", paint="hair", fine=True)
    b.ell("head", (0, 0.135, -0.022), (0.094, 0.098, 0.104), cuts=(((0, -0.55, 1), 0.012),), **HAIR)
    rng = np.random.default_rng(7)
    for i in range(26):
        th = rng.uniform(-1.2, 1.2); ph = rng.uniform(0.15, 1.25)
        base = np.array([0.08 * math.sin(th) * math.cos(ph * 0.4), 0.13 + 0.08 * math.sin(ph), -0.02 - 0.08 * math.cos(th) * math.cos(ph * 0.3)])
        d = base - np.array([0, 0.12, 0.02]); d /= np.linalg.norm(d)
        d = d + np.array([0, 0.25, -0.65]); d /= np.linalg.norm(d)
        L = rng.uniform(0.07, 0.14)
        b.cap("head", tuple(base), tuple(base + d * L), 0.024, 0.003, **HAIR)
    for x in (-0.05, -0.022, 0.006, 0.034, 0.058):                      # bangs over the headband
        b.cap("head", (x, 0.185, 0.07), (x * 1.25 + 0.01, 0.128, 0.104), 0.014, 0.002, **HAIR)
    b.paints["hair"] = ribbing("head", C["hair"], pitch=0.012, depth=0.25, axis=0)
    # black headband with a gold emblem, long tails flowing back
    HB = dict(layer="band", mat="cloth", paint="headband", fine=True)
    b.ell("head", (0, 0.135, -0.012), (0.092, 0.11, 0.106), cuts=(((0, 1, 0), 0.178), ((0, -1, 0), -0.150)), grow=0.006, **HB)
    b.ell("head", (0, 0.163, -0.112), (0.022, 0.018, 0.016), **HB)                                 # knot
    for pts in (((0, 0.163, -0.112), (0.025, 0.150, -0.20), (0.045, 0.105, -0.27), (0.055, 0.045, -0.31)),
                ((0, 0.160, -0.112), (-0.02, 0.125, -0.18), (-0.035, 0.065, -0.23), (-0.03, -0.005, -0.25))):
        for p0, p1 in zip(pts, pts[1:]):
            b.cap("head", p0, p1, 0.011, 0.010, **HB)
    gold = C["accessory2"]
    def hb(P, base, gold=gold):
        col = np.broadcast_to(np.array([0.07, 0.065, 0.06]), base.shape).copy()
        em = ellmask(P[:, 0], P[:, 1], 0.0, 0.164, 0.017, 0.011, 0.2) * (P[:, 2] > 0.06)
        ring = em * (1 - ellmask(P[:, 0], P[:, 1], 0.0, 0.164, 0.009, 0.005, 0.2))
        col = mix(col, gold, np.clip(ring + em * 0.35, 0, 1))
        return col, np.zeros(len(P))
    b.paints["headband"] = Paint("head", hb)
    # red Muay Thai shorts: flared legs + gold waistband + side trim
    SH = dict(layer="garment", mat="silk", paint="shorts")
    b.ell("hips", (0, -0.03, 0.0), (0.172, 0.13, 0.13), grow=0.012, cuts=(((0, 1, 0), 0.075),), **SH)
    for side in "LR":
        b.cap("thigh_" + side, (0, 0.02, 0), (0, -0.20, 0.01), 0.104, 0.098, cuts=(((0, -1, 0), 0.215),), **SH)
    red, trim = C["shorts"], C["trim"]
    def shorts(P, base, red=red, trim=trim):
        col = np.broadcast_to(red, base.shape).copy()
        band = smooth(0.030, 0.036, P[:, 1])
        col = mix(col, trim, band)
        logo = (np.abs(P[:, 0]) < 0.045) & (P[:, 1] > 0.038) & (P[:, 1] < 0.066) & (P[:, 2] > 0.08)
        col[logo] = np.array([0.55, 0.06, 0.05])
        side = np.exp(-((np.abs(P[:, 0]) - 0.15) / 0.012) ** 2) * (P[:, 1] < 0.03)
        col = mix(col, trim, np.clip(side, 0, 1))
        return col, np.zeros(len(P))
    b.paints["shorts"] = Paint("hips", shorts)
    # gold sash flaps hanging from the waistband (front, lead side)
    FL = dict(layer="flap", mat="silk", paint="flap")
    b.box("hips", (0.10, -0.075, 0.115), (0.034, 0.085, 0.007), 0.005, rot=(-8, 0, 6), **FL)
    b.box("hips", (0.05, -0.11, 0.125), (0.03, 0.105, 0.007), 0.005, rot=(-10, 0, -4), **FL)
    b.box("hips", (-0.10, -0.06, -0.12), (0.034, 0.08, 0.007), 0.005, rot=(10, 0, -6), **FL)
    b.paints["flap"] = Paint("hips", lambda P, base, g=gold: (mix(np.broadcast_to(g, base.shape), g * 0.7, smooth(-0.13, -0.19, P[:, 1])), np.zeros(len(P))))
    # white hand wraps up the forearm, ankle wraps, yellow armband on the lead biceps
    W = dict(layer="wrap", mat="cloth")
    for side in "LR":
        shell(b, [p for p in b.prims if p.bone == "hand_" + side and p.layer == "skin"], 0.006, "wrap", "cloth", "wrap_h" + side)
        b.cap("forearm_" + side, (0, -0.11, 0), (0, -0.24, 0), 0.044, 0.035, grow=0.0, paint="wrap_f" + side, **W)
        b.cap("shin_" + side, (0, -0.28, -0.004), (0, -0.39, -0.005), 0.042, 0.038, paint="wrap_a" + side, **W)
        b.paints["wrap_h" + side] = wraps("hand_" + side, C["accessory"], pitch=0.02)
        b.paints["wrap_f" + side] = wraps("forearm_" + side, C["accessory"], pitch=0.022)
        b.paints["wrap_a" + side] = wraps("shin_" + side, C["accessory"], pitch=0.02)
    b.cap("upperarm_L", (0, -0.14, 0), (0, -0.175, 0), 0.056, 0.054, layer="band", mat="cloth", paint="armband")
    b.box("upperarm_L", (0.03, -0.20, 0.045), (0.008, 0.05, 0.012), 0.004, rot=(0, 0, 10), layer="band", mat="cloth", paint="armband")
    b.paints["armband"] = ribbing("upperarm_L", gold, pitch=0.008, depth=0.3)
    return b


def preset_lyra(sp, C):
    b = B(); hs = 0.97
    body(b, g=0.93, musc=0.45, fem=True, hs=hs)
    skin = C["skin"]
    _skin(b, skin)
    b.paints["face"] = Paint("head", face_paint(skin, C["eye"], C["hair"] * 0.6, female=True, scowl=0.1, liner=0.4,
                                                lips_rgb=np.array([0.62, 0.32, 0.32])))
    HAIR = dict(layer="hair", mat="hair", paint="hair", fine=True)
    b.ell("head", (0, 0.132, -0.022), (0.092, 0.100, 0.104), cuts=(((0, -0.5, 1), 0.018),), **HAIR)
    for x in (-0.05, -0.02, 0.015, 0.045):                                 # swept fringe
        b.cap("head", (x, 0.205, 0.04), (x * 1.3 + 0.02, 0.150, 0.098), 0.016, 0.004, **HAIR)
    # high ponytail of thick curls flowing back and down
    pts = [(0, 0.215, -0.07), (0, 0.235, -0.13), (0.01, 0.20, -0.19), (0.0, 0.14, -0.215), (-0.01, 0.07, -0.21), (0.0, 0.01, -0.19)]
    rads = [0.035, 0.040, 0.038, 0.034, 0.028, 0.016]
    for i in range(len(pts) - 1):
        b.cap("head", pts[i], pts[i + 1], rads[i], rads[i + 1], **HAIR)
    rng = np.random.default_rng(5)
    for i in range(10):
        t = rng.uniform(0.2, 1.0); k = int(t * (len(pts) - 2))
        c = np.array(pts[k]) + rng.normal(0, 0.012, 3)
        b.ell("head", tuple(c), (0.022, 0.026, 0.022), **HAIR)
    hair = C["hair"]
    b.paints["hair"] = Paint("head", lambda P, base, h=hair: (h * (0.85 + 0.25 * (0.5 + 0.5 * np.sin(P[:, 0] * 260 + P[:, 2] * 140)))[:, None] * np.ones(3), np.zeros(len(P))))
    teal = C["trim"]
    b.ell("head", (0, 0.135, -0.012), (0.092, 0.11, 0.106), cuts=(((0, 1, -0.35), 0.176), ((0, -1, 0.35), -0.150)), grow=0.007,
          layer="band", mat="cloth", paint="hband", fine=True)
    b.paints["hband"] = plain("head", teal * 1.05)
    # white crop top with teal lettering
    top = shell(b, [p for p in b.prims if p.bone == "chest" and p.layer == "skin"], 0.007, "garment", "cloth", "top",
                cuts=(((0, -1, 0), -0.018),))
    def topf(P, base, teal=teal):
        col = np.broadcast_to(np.array([0.93, 0.95, 0.94]), base.shape).copy()
        x, y = P[:, 0], P[:, 1]
        fr = P[:, 2] > 0.05
        # 'VAI' block letters across the chest
        V = in_poly(x, y, [(-0.075, 0.13), (-0.06, 0.13), (-0.046, 0.075), (-0.032, 0.13), (-0.017, 0.13), (-0.04, 0.06), (-0.052, 0.06)])
        A = in_poly(x, y, [(-0.012, 0.06), (0.004, 0.13), (0.018, 0.13), (0.034, 0.06), (0.021, 0.06), (0.011, 0.11), (0.001, 0.06)])
        I = (x > 0.042) & (x < 0.055) & (y > 0.06) & (y < 0.13)
        col[fr & (V | A | I)] = teal
        hem = smooth(0.006, 0.0, P[:, 1] + 0.012)
        col = mix(col, teal, hem)
        return col, np.zeros(len(P))
    b.paints["top"] = Paint("chest", topf)
    # teal capoeira pants (abada): loose legs gathered at the ankle
    PN = dict(layer="garment", mat="cloth", paint="pants")
    b.ell("hips", (0, -0.03, 0.0), (0.175, 0.13, 0.13), grow=0.012, cuts=(((0, 1, 0), 0.07),), **PN)
    for side in "LR":
        b.cap("thigh_" + side, (0, 0.02, 0), (0, -0.40, 0), 0.105, 0.075, **PN)
        b.cap("shin_" + side, (0, 0.02, 0), (0, -0.33, -0.005), 0.072, 0.058, **PN)
        b.cap("shin_" + side, (0, -0.33, -0.005), (0, -0.37, -0.005), 0.05, 0.045, layer="garment", mat="cloth", paint="cuff")
    def pants(P, base, teal=teal):
        col = np.broadcast_to(teal, base.shape).copy()
        fold = 0.95 + 0.05 * np.cos(P[:, 1] * 45 + P[:, 0] * 20)
        return col * fold[:, None], np.zeros(len(P))
    b.paints["pants"] = Paint("hips", pants)
    b.paints["cuff"] = plain("shin_L", teal * 0.85)
    # green cord belt, knotted, tails hanging on the lead hip
    cord = np.array([0.30, 0.62, 0.22])
    b.ell("hips", (0, 0.055, 0.0), (0.172, 0.022, 0.13), grow=0.012, layer="band", mat="cloth", paint="cord")
    b.cap("hips", (0.11, 0.04, 0.10), (0.13, -0.12, 0.13), 0.011, 0.009, layer="band", mat="cloth", paint="cord")
    b.cap("hips", (0.09, 0.04, 0.11), (0.08, -0.16, 0.135), 0.011, 0.009, layer="band", mat="cloth", paint="cord")
    b.paints["cord"] = ribbing("hips", cord, pitch=0.01, depth=0.3, axis=0)
    return b


def katana_tris(L=0.66, w=0.026, t=0.006, curve=0.045):
    """blade + guard + hilt in hand-local coords; the blade leaves the fist forward and up"""
    tris = []
    def quad(a, b_, c, d, out):
        out.append((a, b_, c)); out.append((a, c, d))
    d = np.array([0.0, -0.18, 1.0]); d /= np.linalg.norm(d)
    up = np.array([0.0, 1.0, 0.18]); up /= np.linalg.norm(up)
    side = np.cross(d, up)
    origin = np.array([0.0, -0.06, 0.03])
    blade, guard, hilt = [], [], []
    n = 10
    for i in range(n):
        s0, s1 = i / n, (i + 1) / n
        def P(s, e, h):
            bend = curve * s * s
            return origin + d * (0.04 + L * s) + up * (bend + e * w * (1 - 0.6 * s ** 6)) + side * h * t
        quad(P(s0, 0.5, 0), P(s1, 0.5, 0), P(s1, -0.5, 1), P(s0, -0.5, 1), blade)
        quad(P(s0, -0.5, -1), P(s1, -0.5, -1), P(s1, 0.5, 0), P(s0, 0.5, 0), blade)
        quad(P(s0, -0.5, 1), P(s1, -0.5, 1), P(s1, -0.5, -1), P(s0, -0.5, -1), blade)
    tip = origin + d * (0.04 + L) + up * (curve + 0.6 * w)
    blade.append((origin + d * (0.04 + L) + up * (curve + 0.5 * w * 0.4), tip, origin + d * (0.04 + L) + up * (curve - 0.5 * w * 0.4)))
    # tsuba (guard) and hilt
    for k in range(12):
        a0, a1 = 2 * math.pi * k / 12, 2 * math.pi * (k + 1) / 12
        c0 = origin + d * 0.03
        r = 0.04
        p0 = c0 + (up * math.cos(a0) + side * math.sin(a0)) * r; p1 = c0 + (up * math.cos(a1) + side * math.sin(a1)) * r
        guard.append((c0, p0, p1)); guard.append((c0 + d * 0.008, p1 + d * 0.008, p0 + d * 0.008))
        quad(p0, p1, p1 + d * 0.008, p0 + d * 0.008, guard)
        h0 = origin - d * 0.16; rh = 0.016
        q0 = origin + (up * math.cos(a0) + side * math.sin(a0)) * rh; q1 = origin + (up * math.cos(a1) + side * math.sin(a1)) * rh
        quad(q0 - d * 0.16, q1 - d * 0.16, q1 + d * 0.03, q0 + d * 0.03, hilt)
    return np.array(blade), np.array(guard), np.array(hilt)


def preset_naomi(sp, C):
    b = B(); hs = 0.96
    body(b, g=0.9, musc=0.3, fem=True, hs=hs)
    skin = C["skin"]
    _skin(b, skin)
    b.paints["face"] = Paint("head", face_paint(skin, C["eye"], C["hair"], female=True, scowl=0.35, liner=0.8,
                                                lips_rgb=np.array([0.70, 0.30, 0.34])))
    HAIR = dict(layer="hair", mat="hair", paint="hair", fine=True)
    b.ell("head", (0, 0.130, -0.020), (0.091, 0.101, 0.104), cuts=(((0, -0.5, 1), 0.02),), **HAIR)
    b.ell("head", (0, 0.236, -0.035), (0.050, 0.044, 0.050), **HAIR)                          # bun
    b.ell("head", (0, 0.205, -0.03), (0.042, 0.03, 0.042), **HAIR)
    for s in (1, -1):                                                                           # side locks framing the face
        b.cap("head", (0.074 * s, 0.15, 0.04), (0.070 * s, 0.03, 0.055), 0.014, 0.006, **HAIR)
    for x in (-0.045, -0.015, 0.02, 0.05):                                                     # parted fringe
        b.cap("head", (x * 0.6, 0.212, 0.05), (x * 1.25, 0.150, 0.096), 0.014, 0.004, **HAIR)
    b.paints["hair"] = ribbing("head", C["hair"], pitch=0.01, depth=0.2, axis=0)
    pin = []
    for k in range(8):
        a0, a1 = 2 * math.pi * k / 8, 2 * math.pi * (k + 1) / 8
        p0 = np.array([0.075, 0.245 + 0.004 * math.cos(a0), -0.04 + 0.004 * math.sin(a0)]); p1 = np.array([0.075, 0.245 + 0.004 * math.cos(a1), -0.04 + 0.004 * math.sin(a1)])
        q0 = p0 - np.array([0.15, 0.0, 0.0]); q1 = p1 - np.array([0.15, 0.0, 0.0])
        pin += [(p0, p1, q1), (p0, q1, q0)]
    b.props.append(Prop("head", np.array(pin), "metal", "gold"))
    b.paints["gold"] = plain("head", np.array([0.85, 0.66, 0.22]))
    purple, petal, sash = C["shirt"], C["shirt"] * 1.55 + 0.08, C["trim"]
    # kimono body (closed, overlapping collar), wide sleeves, long split skirt
    KM = dict(layer="garment", mat="silk", paint="kimono")
    shell(b, [p for p in b.prims if p.bone in ("chest", "spine") and p.layer == "skin"], 0.012, "garment", "silk", "kimono")
    b.ell("hips", (0, -0.04, 0.0), (0.18, 0.15, 0.14), grow=0.01, **KM)
    for side in "LR":
        b.ell("upperarm_" + side, (0, -0.03, 0), (0.08, 0.09, 0.08), **KM)
        b.cap("upperarm_" + side, (0, 0.0, 0), (0, -0.27, 0), 0.066, 0.075, **KM)
        b.cap("forearm_" + side, (0, 0.03, 0), (0, -0.20, -0.02), 0.085, 0.112, cuts=(((0, -1, 0), 0.21),), **KM)     # bell sleeve
        b.cap("thigh_" + side, (0, 0.02, 0), (0, -0.42, 0.0), 0.118, 0.112, **KM)
        b.cap("shin_" + side, (0, 0.02, 0), (0, -0.36, 0.0), 0.112, 0.122, cuts=(((0, -1, 0), 0.36),), **KM)
    def kimono(P, base, f=floral("chest", purple, petal)):
        return f.fn(P, base)
    b.paints["kimono"] = Paint("chest", kimono)
    # crossed collar (white under-collar + lavender edge) painted on the chest shell
    def collar(P, base, f=floral("chest", purple, petal)):
        col, em = f.fn(P, base)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        fr = z > 0.04
        e1 = np.abs((y - 0.19) + 1.6 * (x - 0.0) * -1)  # left-over-right V
        v = (np.abs(y - (0.21 - 1.7 * np.abs(x + 0.01))) < 0.016) & fr & (y > 0.02)
        under = (np.abs(y - (0.235 - 1.7 * np.abs(x + 0.01))) < 0.012) & fr & (y > 0.04)
        col[under] = np.array([0.95, 0.93, 0.95])
        col[v] = purple * 0.55
        return col, em
    for p in b.prims:
        if p.paint == "kimono" and p.bone == "chest":
            p.paint = "collar"
    b.paints["collar"] = Paint("chest", collar)
    # obi: wide red sash with a dark cord, bow at the back
    OB = dict(layer="sash", mat="silk", paint="obi")
    b.ell("spine", (0, 0.04, 0.0), (0.142, 0.075, 0.115), grow=0.02, cuts=(((0, 1, 0), 0.105), ((0, -1, 0), 0.03)), **OB)
    b.box("spine", (0, 0.05, -0.155), (0.085, 0.05, 0.03), 0.02, **OB)
    b.box("spine", (0.0, -0.02, -0.16), (0.04, 0.09, 0.012), 0.01, rot=(-10, 0, 0), **OB)
    def obi(P, base, sash=sash):
        col = np.broadcast_to(sash, base.shape).copy()
        cordm = np.exp(-((P[:, 1] - 0.045) / 0.006) ** 2)
        col = mix(col, np.array([0.22, 0.04, 0.06]), cordm * 0.9)
        edge = np.exp(-((P[:, 1] - 0.095) / 0.004) ** 2) + np.exp(-((P[:, 1] + 0.012) / 0.004) ** 2)
        col = mix(col, np.array([0.95, 0.75, 0.3]), np.clip(edge, 0, 1) * 0.8)
        return col, np.zeros(len(P))
    b.paints["obi"] = Paint("spine", obi)
    # white tabi feet
    shell(b, [p for p in b.prims if p.bone.startswith("foot_") and p.layer == "skin"], 0.004, "garment", "cloth", "tabi")
    b.paints["tabi"] = plain("foot_L", np.array([0.92, 0.9, 0.9]))
    # scabbard on the lead hip, katana in the rear hand
    b.cap("hips", (0.16, 0.02, 0.10), (0.20, -0.06, -0.55), 0.020, 0.017, layer="prop", mat="leather", paint="saya")
    b.paints["saya"] = Paint("hips", lambda P, base: (np.where((P[:, 2] < -0.5)[:, None], np.array([0.8, 0.62, 0.2]), np.array([0.06, 0.05, 0.06])), np.zeros(len(P))))
    bl, gu, hi = katana_tris()
    b.props += [Prop("hand_R", bl, "metal", "blade"), Prop("hand_R", gu, "metal", "gold"), Prop("hand_R", hi, "cloth", "hilt")]
    b.paints["blade"] = plain("hand_R", np.array([0.86, 0.88, 0.92]))
    b.paints["hilt"] = plain("hand_R", np.array([0.08, 0.07, 0.09]))
    return b


def preset_brutus(sp, C):
    b = B(); hs = 0.98
    body(b, g=1.36, musc=1.0, hs=hs, neck=1.35)
    skin = C["skin"]
    _skin(b, skin)
    b.paints["face"] = Paint("head", face_paint(skin, C["eye"], np.array([0.25, 0.18, 0.14]), scowl=1.0,
                                                stubble=np.array([0.82, 0.78, 0.78])))
    # brutish skull: heavier brow and jaw
    b.ell("head", (0, 0.132, 0.074), (0.072, 0.024, 0.03), layer="skin", mat="skin", paint="face", fine=True)
    b.box("head", (0, 0.03, 0.035), (0.058, 0.034, 0.056), 0.028, layer="skin", mat="skin", paint="face", fine=True)
    # grey tank top with orange chevron stripes, frayed hem
    grey, orange = C["shirt"], C["trim"]
    shell(b, [p for p in b.prims if p.bone in ("chest", "spine") and p.layer == "skin"], 0.008, "garment", "cloth", "tank")
    b.ell("hips", (0, 0.0, 0.0), (0.21, 0.09, 0.15), grow=0.0, cuts=(((0, -1, 0), 0.04),), layer="garment", mat="cloth", paint="tank_h")
    def tank(P, base, grey=grey, orange=orange):
        col = np.broadcast_to(grey, base.shape).copy()
        x, y = P[:, 0], P[:, 1]
        for k in range(3):
            yy = 0.10 - 0.045 * k
            s1 = np.exp(-((y - yy - 0.35 * (np.abs(x) - 0.12)) / 0.007) ** 2) * (np.abs(x) > 0.08) * (np.abs(x) < 0.17)
            col = mix(col, orange, np.clip(s1, 0, 1))
        col = col * (0.975 + 0.025 * np.cos(P[:, 0] * 260 + P[:, 1] * 40))[:, None]
        return col, np.zeros(len(P))
    b.paints["tank"] = Paint("chest", tank)
    def tank_h(P, base, grey=grey):
        col = np.broadcast_to(grey, base.shape).copy()
        fray = smooth(-0.025, -0.04, P[:, 1] + 0.006 * np.sin(P[:, 0] * 300))
        return mix(col, grey * 0.55, fray), np.zeros(len(P))
    b.paints["tank_h"] = Paint("hips", tank_h)
    # charcoal cargo pants + side pockets, boots
    PN = dict(layer="garment", mat="cloth", paint="pants")
    b.ell("hips", (0, -0.03, 0.0), (0.215, 0.15, 0.16), grow=0.008, cuts=(((0, 1, 0), 0.06),), **PN)
    for s, side in ((1, "L"), (-1, "R")):
        shell(b, [p for p in b.prims if p.bone in ("thigh_" + side, "shin_" + side) and p.layer == "skin"], 0.02, "garment", "cloth", "pants",
              cuts=(((0, -1, 0), 0.36),) if False else ())
        b.cap("thigh_" + side, (0, 0.02, 0), (0, -0.42, 0), 0.13, 0.10, **PN)
        b.cap("shin_" + side, (0, 0.02, 0), (0, -0.30, 0), 0.094, 0.080, **PN)
        b.box("thigh_" + side, (0.10 * s, -0.24, 0.0), (0.03, 0.065, 0.06), 0.012, **PN)                    # cargo pocket
        BT = dict(layer="boot", mat="leather", paint="boot")
        b.cap("shin_" + side, (0, -0.27, -0.005), (0, -0.40, -0.005), 0.07, 0.066, **BT)
        shell(b, [p for p in b.prims if p.bone == "foot_" + side and p.layer == "skin"], 0.014, "boot", "leather", "boot")
    def pants(P, base, c=C["shorts"]):
        return c * (0.96 + 0.04 * np.cos(P[:, 1] * 40 + P[:, 0] * 15))[:, None] * np.ones(3), np.zeros(len(P))
    b.paints["pants"] = Paint("hips", pants)
    b.paints["boot"] = plain("foot_L", C["boots"])
    # orange wraps on the hands and wrists
    for side in "LR":
        shell(b, [p for p in b.prims if p.bone == "hand_" + side and p.layer == "skin"], 0.008, "wrap", "cloth", "wrap_h" + side)
        b.cap("forearm_" + side, (0, -0.17, 0), (0, -0.25, 0), 0.05, 0.046, layer="wrap", mat="cloth", paint="wrap_f" + side)
        b.paints["wrap_h" + side] = wraps("hand_" + side, C["accessory"], pitch=0.022)
        b.paints["wrap_f" + side] = wraps("forearm_" + side, C["accessory"], pitch=0.022)
    return b


def preset_void(sp, C):
    b = B(); hs = 0.98
    body(b, g=0.95, musc=0.25, hs=hs, hands="claw", slim_limbs=0.95)
    skin = C["skin"]; cyan = C["emissive"]
    _skin(b, skin)
    b.paints["face"] = Paint("head", face_paint(skin, cyan, np.array([0.75, 0.75, 0.80]), glow_eyes=True, scowl=0.6,
                                                scar=(0.04, 0.1)))
    # long silver hair falling from under the hood
    HAIR = dict(layer="hair", mat="hair", paint="hair", fine=True)
    b.ell("head", (0, 0.132, -0.02), (0.091, 0.101, 0.104), cuts=(((0, -0.5, 1), 0.025),), **HAIR)
    for s in (1, -1):
        for k, x in enumerate((0.078, 0.088)):
            b.cap("head", (x * s, 0.17, 0.035 - 0.03 * k), (x * s * 1.12, -0.05 - 0.03 * k, 0.03 - 0.03 * k), 0.017, 0.007, **HAIR)
    b.cap("head", (0.02, 0.2, 0.075), (0.045, 0.12, 0.098), 0.013, 0.003, **HAIR)
    b.paints["hair"] = ribbing("head", np.array([0.82, 0.84, 0.88]), pitch=0.008, depth=0.3, axis=0)
    # hood: thick shell with the face opening carved out, peak at the back, cyan trim round the opening
    HD = dict(layer="hood", mat="cloth", paint="hood", fine=True)
    b.ell("head", (0, 0.125, -0.03), (0.138, 0.158, 0.155), **HD)
    b.cap("head", (0, 0.24, -0.08), (0, 0.27, -0.17), 0.05, 0.01, **HD)
    b.ell("head", (0, -0.03, -0.05), (0.15, 0.08, 0.15), **HD)
    b.ell("head", (0, 0.10, 0.12), (0.086, 0.13, 0.12), sub=True, **dict(HD, paint="hood"))
    b.ell("head", (0, 0.13, -0.015), (0.112, 0.130, 0.128), sub=True, **dict(HD, paint="hood"))
    def hood(P, base, cyan=cyan):
        col = np.broadcast_to(np.array([0.06, 0.065, 0.08]), base.shape).copy()
        # rim of the opening: distance to the opening ellipsoid surface
        q = (P - np.array([0, 0.10, 0.12])) / np.array([0.086, 0.13, 0.12])
        r = np.linalg.norm(q, axis=1)
        trim = np.exp(-((r - 1.0) / 0.10) ** 2) * (P[:, 2] > 0.02)
        col = mix(col, cyan, np.clip(trim, 0, 1))
        sigil = np.exp(-((np.abs(P[:, 0])) / 0.004) ** 2) * (P[:, 1] > 0.22) * (P[:, 2] > 0.0)
        col = mix(col, cyan, np.clip(sigil, 0, 1))
        return col, np.clip(trim * 0.8 + sigil, 0, 1)
    b.paints["hood"] = Paint("head", hood)
    # long black coat: open chest with a tattoo, wide sleeves, split skirt to the shin
    CT = dict(layer="garment", mat="cloth", paint="coat")
    shell(b, [p for p in b.prims if p.bone in ("chest", "spine") and p.layer == "skin"], 0.013, "garment", "cloth", "coat_c")
    b.ell("hips", (0, -0.04, 0.0), (0.17, 0.15, 0.135), grow=0.01, **CT)
    b.ell("chest", (0, 0.18, -0.02), (0.20, 0.07, 0.15), **CT)                                          # mantle
    for side in "LR":
        b.cap("upperarm_" + side, (0, 0.0, 0), (0, -0.27, 0), 0.062, 0.062, **CT)
        b.cap("forearm_" + side, (0, 0.02, 0), (0, -0.19, 0), 0.062, 0.078, cuts=(((0, -1, 0), 0.20),), **CT)
        b.cap("thigh_" + side, (0, 0.02, 0), (0, -0.44, 0), 0.105, 0.112, **CT)
        b.cap("shin_" + side, (0, 0.02, 0), (0, -0.16, 0), 0.105, 0.115, cuts=(((0, -1, 0), 0.17),), **CT)
        b.cap("shin_" + side, (0, 0.0, 0), (0, -0.31, 0), 0.06, 0.05, layer="garment", mat="cloth", paint="pants")
        BT = dict(layer="boot", mat="leather", paint="boot")
        b.cap("shin_" + side, (0, -0.26, -0.005), (0, -0.40, -0.005), 0.052, 0.05, **BT)
        shell(b, [p for p in b.prims if p.bone == "foot_" + side and p.layer == "skin"], 0.01, "boot", "leather", "boot")
        shell(b, [p for p in b.prims if p.bone == "hand_" + side and p.layer == "skin"], 0.004, "glove", "leather", "glove" + side)
        b.paints["glove" + side] = Paint("hand_" + side, lambda P, base, c=cyan: (
            mix(np.broadcast_to(np.array([0.05, 0.05, 0.07]), base.shape), c, np.clip(np.exp(-((P[:, 0] - 0.0) / 0.004) ** 2) * (P[:, 1] < -0.03), 0, 1)),
            np.clip(np.exp(-((P[:, 0]) / 0.004) ** 2) * (P[:, 1] < -0.03), 0, 1)))
        b.fx.append(("hand_" + side, (0.0, -0.08, 0.06), tuple(cyan), 0.11))
    dark = np.array([0.055, 0.06, 0.075])
    def coat(P, base, cyan=cyan, dark=dark):
        col = np.broadcast_to(dark, base.shape).copy()
        col = col * (0.9 + 0.12 * np.cos(P[:, 1] * 55 + P[:, 0] * 25))[:, None]
        return col, np.zeros(len(P))
    b.paints["coat"] = Paint("hips", coat)
    def coat_c(P, base, cyan=cyan, dark=dark, skin=skin):
        col, em = coat(P, base)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        fr = z > 0.05
        opening = fr & (np.abs(x) < 0.012 + 0.32 * np.clip(y - 0.0, 0, None)) & (y > 0.02)
        col[opening] = skin * 0.92
        edge = fr & (np.abs(np.abs(x) - (0.012 + 0.32 * np.clip(y, 0, None))) < 0.008) & (y > 0.02)
        col[edge] = cyan
        em = np.where(edge, 0.7, em)
        tat = opening & (np.abs(np.abs(x) - 0.02 - 0.15 * np.abs(y - 0.14)) < 0.004) & (y > 0.08) & (y < 0.2)
        col[tat] = np.array([0.15, 0.15, 0.2])
        return col, em
    b.paints["coat_c"] = Paint("chest", coat_c)
    b.paints["pants"] = plain("shin_L", np.array([0.05, 0.05, 0.065]))
    b.paints["boot"] = plain("foot_L", np.array([0.045, 0.045, 0.055]))
    # hem trim on the coat skirt
    def coat_hem(P, base, cyan=cyan):
        col, em = coat(P, base)
        hem = smooth(-0.135, -0.165, P[:, 1])
        col = mix(col, cyan * 0.9, hem)
        return col, hem * 0.6
    for p in b.prims:
        if p.paint == "coat" and p.bone.startswith("shin_"):
            p.paint = "coat_hem"
    b.paints["coat_hem"] = Paint("shin_L", coat_hem)
    return b


def preset_zap(sp, C):
    b = B(); hs = 1.0
    body(b, g=1.10, musc=0.95, hs=hs)
    skin = C["skin"]; blue = C["accessory"]; yellow = C["trim"]
    _skin(b, skin)
    def mask(P, col, em, blue=blue, yellow=yellow, skin=skin):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        mouth = (y < 0.083) & (z > 0.02) & (ax < 0.06 - 0.25 * (0.083 - y))
        m = ~mouth
        base = np.broadcast_to(blue, col.shape).copy()
        # yellow flame/bolt shapes round the eyes and a centre stripe
        eyeflame = in_poly(ax, y, [(0.012, 0.13), (0.07, 0.145), (0.09, 0.18), (0.06, 0.122), (0.064, 0.10), (0.02, 0.098)]) & (z > 0.02)
        stripe = (ax < 0.010 + 0.02 * np.clip(y - 0.12, 0, None)) & (y > 0.12) & (z > -0.06)
        bolt = in_poly(ax, y, [(0.07, 0.09), (0.09, 0.07), (0.075, 0.06), (0.095, 0.03), (0.065, 0.055), (0.075, 0.07)]) & (z > -0.02)
        base[eyeflame | stripe | bolt] = yellow
        eye_hole = ellmask(ax, y - 0.12 * (ax - 0.034), 0.034, 0.110, 0.022, 0.013, 0.2) > 0.5
        keep = m & ~eye_hole
        col = np.where(keep[:, None], base * (0.92 + 0.08 * np.cos(x * 300))[:, None], col)
        return col, em
    b.paints["face"] = Paint("head", face_paint(skin, C["eye"], np.array([0.1, 0.07, 0.04]), scowl=1.0, mask=mask))
    # mask shell (head enlarged, mouth and chin left open)
    for p in [q for q in b.prims if q.bone == "head" and q.layer == "skin"]:
        p.grow += 0.002
    # wild yellow hair bursting out of the top of the mask
    HAIR = dict(layer="hair", mat="hair", paint="hair", fine=True)
    rng = np.random.default_rng(11)
    for i in range(34):
        th = rng.uniform(-1.6, 1.6); el = rng.uniform(0.0, 1.0)
        base = np.array([0.07 * math.sin(th), 0.165 + 0.05 * el, -0.03 + 0.06 * math.cos(th) * (1 - el)])
        d = np.array([math.sin(th) * 0.75, 0.55 + 0.35 * el, -1.0 + 0.35 * math.cos(th)]); d /= np.linalg.norm(d)
        L = rng.uniform(0.10, 0.19)
        b.cap("head", tuple(base), tuple(base + d * L), 0.03, 0.003, **HAIR)
    b.paints["hair"] = Paint("head", lambda P, base, y=yellow: (mix(np.broadcast_to(y * 1.05, base.shape), np.array([1.0, 0.95, 0.6]), smooth(0.25, 0.33, P[:, 1])), np.zeros(len(P))))
    # blue singlet with yellow lightning across the chest
    SG = dict(layer="garment", mat="rubber")
    shell(b, [p for p in b.prims if p.bone in ("chest", "spine") and p.layer == "skin"], 0.005, "garment", "rubber", "singlet")
    b.ell("hips", (0, -0.035, 0.0), (0.168, 0.124, 0.122), grow=0.008, paint="tights_h", **SG)
    def singlet(P, base, blue=blue, yellow=yellow):
        col = np.broadcast_to(blue, base.shape).copy()
        x, y = P[:, 0], P[:, 1]
        bolt = in_poly(x, y, [(-0.16, 0.24), (-0.06, 0.24), (-0.01, 0.13), (0.06, 0.15), (0.17, -0.02), (0.06, 0.07),
                              (-0.01, 0.04), (-0.04, 0.12), (-0.1, 0.1)])
        fr = P[:, 2] > 0.0
        col[bolt & fr] = yellow
        bolt2 = in_poly(x, y, [(0.06, 0.22), (0.15, 0.2), (0.12, 0.15)]) & fr
        col[bolt2] = yellow
        return col, np.zeros(len(P))
    b.paints["singlet"] = Paint("chest", singlet)
    TT = dict(layer="garment", mat="rubber")
    for s, side in ((1, "L"), (-1, "R")):
        shell(b, [p for p in b.prims if p.bone in ("thigh_" + side, "shin_" + side) and p.layer == "skin"], 0.004, "garment", "rubber", "tights" + side)
        b.paints["tights" + side] = Paint("thigh_" + side, lambda P, base, blue=blue, yellow=yellow, s=s: (
            np.where((in_poly(P[:, 0] * s, P[:, 1], [(0.045, 0.0), (0.075, -0.01), (0.055, -0.19), (0.085, -0.20), (0.04, -0.40), (0.05, -0.23), (0.03, -0.22)]))[:, None], yellow, blue),
            np.zeros(len(P))))
        BT = dict(layer="boot", mat="rubber", paint="boot")
        b.cap("shin_" + side, (0, -0.21, -0.005), (0, -0.40, -0.005), 0.056, 0.05, **BT)
        shell(b, [p for p in b.prims if p.bone == "foot_" + side and p.layer == "skin"], 0.012, "boot", "rubber", "boot")
        b.cap("forearm_" + side, (0, -0.16, 0), (0, -0.235, 0), 0.044, 0.04, layer="wrap", mat="cloth", paint="wristband")
    b.paints["tights_h"] = plain("hips", blue)
    def boot(P, base, blue=blue, yellow=yellow):
        col = np.broadcast_to(blue, base.shape).copy()
        top = P[:, 1] > -0.03
        col[top] = yellow
        return col, np.zeros(len(P))
    b.paints["boot"] = Paint("foot_L", boot)
    b.paints["wristband"] = ribbing("forearm_L", yellow, pitch=0.01, depth=0.2)
    b.fx.append(("hand_L", (0.0, -0.07, 0.04), (0.55, 0.85, 1.0), 0.07))
    return b


PRESETS = {"kairo": preset_kairo, "lyra": preset_lyra, "naomi": preset_naomi, "brutus": preset_brutus,
           "void": preset_void, "zap": preset_zap}
LAYER_K = {"skin": 0.022, "garment": 0.012, "hair": 0.008, "band": 0.004, "wrap": 0.006, "flap": 0.0, "sash": 0.01,
           "hood": 0.012, "boot": 0.01, "glove": 0.004, "prop": 0.0}
RIM = {"void": (0.25, 0.95, 1.0), "zap": (0.55, 0.75, 1.0), "naomi": (1.0, 0.75, 0.85), "lyra": (1.0, 0.85, 0.6),
       "kairo": (1.0, 0.72, 0.45), "brutus": (1.0, 0.6, 0.3)}


def build_character(sp) -> Character:
    """CharacterSpec -> Character.  `sculpt = <preset>` (or the spec name) chooses the costume preset; the spec's
    colours (skin_tone, hair_colour, top/bottom/trim/accessory colours, eye_colour, emissive_colour) recolour it."""
    key = str(sp.extra.get("sculpt", sp.name)).strip().lower()
    if key not in PRESETS:
        raise KeyError("no sculpt preset '%s' (have: %s)" % (key, ", ".join(PRESETS)))
    C = {k: np.asarray(v, float) for k, v in sp.colours().items()}
    b = PRESETS[key](sp, C)
    if "skin" not in b.paints:
        _skin(b, C["skin"])
    rim = sp.extra.get("rim_colour")
    from .spec import parse_colour
    rimc = tuple(parse_colour(rim)) if rim else RIM.get(key, (0.62, 0.74, 1.0))
    return Character(sp.name, b.prims, b.props, b.paints, b.fx, dict(LAYER_K), sp.scale, rimc)


# ------------------------------------------------------------------ meshing
@dataclass
class SculptMesh:
    V: np.ndarray            # (n,3) bind-pose world
    F: np.ndarray            # (m,3) int
    N: np.ndarray            # (n,3) bind normals
    W: np.ndarray            # (n,4) weights
    J: np.ndarray            # (n,4) joint indices (rig JOINT_NAMES)
    mat: np.ndarray          # (n,) material class index (MATS)
    paint: np.ndarray        # (n,) paint index into paint_names
    paint_names: list
    layer: np.ndarray        # (n,) layer index (for ink lines between layers)
    curv: np.ndarray = None  # (n,) signed mean curvature proxy (+ convex, - creases), for cavity shading


def _world_inv():
    Wb = bind_world()
    return {n: np.linalg.inv(Wb[n]) for n in Wb}


def to_local(P, bone, inv=None):
    inv = inv or _world_inv()
    M = inv[bone]
    return P @ M[:3, :3].T + M[:3, 3]


def _prim_world_aabb(pr, Wb):
    lo, hi = pr.local_aabb()
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    M = Wb[pr.bone]
    w = corners @ M[:3, :3].T + M[:3, 3]
    return w.min(0), w.max(0)


def _field(prims, layer_k, origin, shape, h, inv, Wb, margin=0.03):
    """evaluate the layered field on a grid: -> (dist, layer_of_min)"""
    nx, ny, nz = shape
    layers = sorted({p.layer for p in prims})
    big = 1.0
    D = np.full(shape, big, np.float32)
    for li, L in enumerate(layers):
        k = layer_k.get(L, 0.01)
        F = np.full(shape, big, np.float32)
        adds = [p for p in prims if p.layer == L and not p.sub]
        subs = [p for p in prims if p.layer == L and p.sub]
        for p in adds:
            lo, hi = _prim_world_aabb(p, Wb)
            lo = lo - margin - k; hi = hi + margin + k
            i0 = np.clip(np.floor((lo - origin) / h).astype(int), 0, np.array(shape) - 1)
            i1 = np.clip(np.ceil((hi - origin) / h).astype(int) + 1, 0, np.array(shape))
            if np.any(i1 <= i0):
                continue
            xs = origin[0] + h * np.arange(i0[0], i1[0]); ys = origin[1] + h * np.arange(i0[1], i1[1]); zs = origin[2] + h * np.arange(i0[2], i1[2])
            G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
            d = prim_sdf(p, to_local(G, p.bone, inv)).reshape(len(xs), len(ys), len(zs)).astype(np.float32)
            sl = (slice(i0[0], i1[0]), slice(i0[1], i1[1]), slice(i0[2], i1[2]))
            F[sl] = smin(F[sl], d, k)
        for p in subs:
            lo, hi = _prim_world_aabb(p, Wb)
            i0 = np.clip(np.floor((lo - margin - origin) / h).astype(int), 0, np.array(shape) - 1)
            i1 = np.clip(np.ceil((hi + margin - origin) / h).astype(int) + 1, 0, np.array(shape))
            xs = origin[0] + h * np.arange(i0[0], i1[0]); ys = origin[1] + h * np.arange(i0[1], i1[1]); zs = origin[2] + h * np.arange(i0[2], i1[2])
            G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
            d = prim_sdf(p, to_local(G, p.bone, inv)).reshape(len(xs), len(ys), len(zs)).astype(np.float32)
            sl = (slice(i0[0], i1[0]), slice(i0[1], i1[1]), slice(i0[2], i1[2]))
            F[sl] = np.maximum(F[sl], -d)
        D = np.minimum(D, F)
    return D


def _vertex_attrs(V, prims, ch, inv, sigma=0.022):
    """owner prim (for material / paint / layer) + bone weights for vertices"""
    n = len(V)
    D = np.empty((len(prims), n), np.float32)
    for i, p in enumerate(prims):
        D[i] = prim_sdf(p, to_local(V, p.bone, inv))
    for i, p in enumerate(prims):
        if p.sub:
            D[i] = 9.0
    owner = np.argmin(np.abs(D) + np.array([0.0 if not p.sub else 9 for p in prims])[:, None] * 0 + 0.0, axis=0)
    # owner = the outermost (topmost layer) prim the vertex sits on: smallest |d|
    # weights from every prim that the vertex is on or inside
    nb = len(JOINT_NAMES)
    Wb = np.zeros((n, nb), np.float32)
    for i, p in enumerate(prims):
        if p.sub:
            continue
        w = np.exp(-np.maximum(D[i], 0) / sigma) * (1.0 if p.layer in ("skin", "garment", "boot", "wrap", "glove", "hood", "sash") else 0.6)
        Wb[:, BI[p.bone]] += w
    top = np.argsort(-Wb, axis=1)[:, :4]
    tw = np.take_along_axis(Wb, top, 1)
    tw = tw / np.maximum(tw.sum(1, keepdims=True), 1e-9)
    return owner, top.astype(np.int32), tw.astype(np.float32)


def mesh_character(ch: Character, h_body=0.0075, h_fine=0.0032, log=print):
    from skimage.measure import marching_cubes
    Wb = bind_world(); inv = _world_inv()
    out_V, out_F, out_N, owners = [], [], [], []
    body = [p for p in ch.prims if not p.fine]
    fine = [p for p in ch.prims if p.fine]
    vo = 0
    for prims, h in ((body, h_body), (fine, h_fine)):
        if not prims:
            continue
        lo = np.full(3, 9.0); hi = np.full(3, -9.0)
        for p in prims:
            a, c = _prim_world_aabb(p, Wb); lo = np.minimum(lo, a); hi = np.maximum(hi, c)
        lo -= 0.04; hi += 0.04
        shape = tuple(np.ceil((hi - lo) / h).astype(int) + 1)
        D = _field(prims, ch.layer_k, lo, shape, h, inv, Wb)
        v, f, nrm, _ = marching_cubes(D, 0.0, spacing=(h, h, h))
        v = v + lo
        # MC on an ij grid gives outward normals pointing to +field: flip to outward
        out_V.append(v); out_F.append(f[:, ::-1] + vo); out_N.append(-nrm); vo += len(v)
        log("  sculpt %-5s %d^3-ish grid %s -> %d verts" % ("body" if h == h_body else "head", int(np.prod(shape) ** (1 / 3)), shape, len(v)))
    V = np.concatenate(out_V); F = np.concatenate(out_F); N = np.concatenate(out_N)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    allp = ch.prims
    owner, J, W = _vertex_attrs(V, allp, ch, inv)
    names = sorted({p.paint for p in allp} | {pp.paint for pp in ch.props})
    pidx = {nme: i for i, nme in enumerate(names)}
    layers = sorted({p.layer for p in allp} | {"prop"})
    lidx = {l: i for i, l in enumerate(layers)}
    mat = np.array([MI[allp[o].mat] for o in owner], np.int32)
    paint = np.array([pidx[allp[o].paint] for o in owner], np.int32)
    layer = np.array([lidx[allp[o].layer] for o in owner], np.int32)
    # rigid props
    for pr in ch.props:
        T = pr.tris.reshape(-1, 3)
        M = Wb[pr.bone]
        Tw = T @ M[:3, :3].T + M[:3, 3]
        k = len(V)
        nt = len(pr.tris)
        e1 = pr.tris[:, 1] - pr.tris[:, 0]; e2 = pr.tris[:, 2] - pr.tris[:, 0]
        fn = np.cross(e1, e2); fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
        fn = fn @ M[:3, :3].T
        V = np.concatenate([V, Tw]); F = np.concatenate([F, np.arange(k, k + 3 * nt).reshape(-1, 3)])
        N = np.concatenate([N, np.repeat(fn, 3, axis=0)])
        J = np.concatenate([J, np.tile(np.array([BI[pr.bone], 0, 0, 0], np.int32), (3 * nt, 1))])
        W = np.concatenate([W, np.tile(np.array([1, 0, 0, 0], np.float32), (3 * nt, 1))])
        mat = np.concatenate([mat, np.full(3 * nt, MI[pr.mat], np.int32)])
        paint = np.concatenate([paint, np.full(3 * nt, pidx[pr.paint], np.int32)])
        layer = np.concatenate([layer, np.full(3 * nt, lidx["prop"], np.int32)])
    return SculptMesh(V, F.astype(np.int64), N, W, J, mat, paint, names, layer, curvature(V, F, N))


def curvature(V, F, N, iters=2):
    """umbrella-operator curvature: (v - mean(neighbours)) . n / mean edge length, smoothed, roughly -1..1"""
    n = len(V)
    S = np.zeros((n, 3)); cnt = np.zeros(n)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        np.add.at(S, F[:, a], V[F[:, b]]); np.add.at(cnt, F[:, a], 1)
        np.add.at(S, F[:, b], V[F[:, a]]); np.add.at(cnt, F[:, b], 1)
    cnt = np.maximum(cnt, 1)
    el = np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1).mean()
    k = ((V - S / cnt[:, None]) * N).sum(1) / max(el, 1e-6)
    for _ in range(iters):
        T = np.zeros(n)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            np.add.at(T, F[:, a], k[F[:, b]]); np.add.at(T, F[:, b], k[F[:, a]])
        k = 0.5 * k + 0.5 * T / cnt
    return np.clip(k / (np.std(k) * 2.5 + 1e-9), -1, 1).astype(np.float32)


def vertex_colours(ch: Character, sm: SculptMesh, P=None, paint=None):
    """evaluate paints at bind points P (default: the vertices) -> rgb (n,3), emissive (n,)"""
    P = sm.V if P is None else P
    paint = sm.paint if paint is None else paint
    inv = _world_inv()
    rgb = np.zeros((len(P), 3)); em = np.zeros(len(P))
    for i, nme in enumerate(sm.paint_names):
        m = paint == i
        if not m.any():
            continue
        pt = ch.paints.get(nme) or ch.paints["skin"]
        loc = to_local(P[m], pt.bone, inv)
        c, e = pt.fn(loc, np.full((m.sum(), 3), 0.5))
        rgb[m] = np.clip(c, 0, 1); em[m] = np.clip(e, 0, 1)
    return rgb, em


def skin_points(sm: SculptMesh, state, P=None, N=None):
    """LBS: bind-pose points -> posed world (and normals)"""
    from .render import bind_inverse
    Wb = bind_world()
    S = np.stack([(state.world[n] if n != "ball" else np.eye(4)) @ np.linalg.inv(Wb[n]) for n in JOINT_NAMES])
    P = sm.V if P is None else P
    N = sm.N if N is None else N
    M = np.einsum("nk,nkij->nij", sm.W, S[sm.J])
    Pp = np.einsum("nij,nj->ni", M[:, :3, :3], P) + M[:, :3, 3]
    Np = np.einsum("nij,nj->ni", M[:, :3, :3], N)
    Np /= np.linalg.norm(Np, axis=1, keepdims=True) + 1e-12
    return Pp, Np
