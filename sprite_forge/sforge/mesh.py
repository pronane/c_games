"""Low-poly mannequin mesh built procedurally around the rig (rigid skinning:
each part follows exactly one bone, weight 1.0 - works in every engine).
The figure is a generic sports mannequin, not modelled on any real person."""
from __future__ import annotations
import math
import numpy as np
from .rig import JOINT_NAMES, rest_world, BALL_RADIUS

MATS = ["skin", "shirt", "shorts", "socks", "trim", "boots", "hair", "ball", "ball_seam", "eye", "eye_white", "mouth", "kart", "kart_dark", "kart_trim",
        "accessory", "accessory2", "pattern", "teeth", "emissive", "eyelid", "brow"]   # v9: accessories, top pattern, face, glow
# v9: small face parts are drawn after the head surface they sit on (painter's algorithm depth bias, metres)
DECAL_BIAS = {"eye_white": 0.010, "eye": 0.011, "mouth": 0.010, "teeth": 0.012, "eyelid": 0.014, "brow": 0.012}

KITS = {
    "home":  dict(label="Home (Green)", shirt=(0.04, 0.42, 0.16), shorts=(0.93, 0.93, 0.93), socks=(0.04, 0.42, 0.16), trim=(0.95, 0.95, 0.95)),
    "away":  dict(label="Away (White)", shirt=(0.94, 0.94, 0.94), shorts=(0.94, 0.94, 0.94), socks=(0.94, 0.94, 0.94), trim=(0.04, 0.42, 0.16)),
    "blue":  dict(label="Blue", shirt=(0.08, 0.25, 0.75), shorts=(0.93, 0.93, 0.93), socks=(0.08, 0.25, 0.75), trim=(0.95, 0.95, 0.95)),
    "red":   dict(label="Red", shirt=(0.78, 0.08, 0.08), shorts=(0.93, 0.93, 0.93), socks=(0.78, 0.08, 0.08), trim=(0.95, 0.95, 0.95)),
    "black": dict(label="Black", shirt=(0.08, 0.08, 0.09), shorts=(0.08, 0.08, 0.09), socks=(0.08, 0.08, 0.09), trim=(0.85, 0.68, 0.18)),
    "gk":    dict(label="Goalkeeper (Yellow)", shirt=(0.96, 0.78, 0.08), shorts=(0.08, 0.08, 0.09), socks=(0.96, 0.78, 0.08), trim=(0.1, 0.1, 0.1)),
}


def palette(kit="home", skin="medium", spec=None):
    """Material colours. Uses spec colours if a CharacterSpec is given."""
    from .spec import CharacterSpec
    sp = spec or CharacterSpec(kit=kit, skin_tone=skin)
    return sp.colours()


import os as _os
DETAIL = float(_os.environ.get('SFORGE_DETAIL', '1.0'))   # segment multiplier for cylinders/spheres (console polygon budgets); 1.0 = standard mannequin


def _seg(n, lo=3):
    return max(lo, int(round(n * DETAIL)))


class MeshBuilder:
    def __init__(self):
        self.tris, self.bones, self.mats = [], [], []

    def _add(self, a, b, c, bone, mat):
        self.tris.append((a, b, c)); self.bones.append(JOINT_NAMES.index(bone)); self.mats.append(MATS.index(mat))

    def quad(self, a, b, c, d, bone, mat):
        self._add(a, b, c, bone, mat); self._add(a, c, d, bone, mat)

    def cyl(self, bone, p0, p1, r0, r1, mat, seg=8, cap0=True, cap1=True):
        """Tapered elliptic cylinder from p0 to p1; r = radius or (rx, rz)."""
        seg = _seg(seg)
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        ax = p1 - p0; L = np.linalg.norm(ax); ax = ax / L
        ref = np.array([0, 0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0, 0])
        u = np.cross(ref, ax); u /= np.linalg.norm(u)
        if abs(ax[1]) > 0.9:  # vertical part: keep x/z semantic for elliptic radii
            u = np.array([1.0, 0, 0]); w = np.array([0, 0, 1.0])
        else:
            w = np.cross(ax, u)
        r0 = (r0, r0) if np.isscalar(r0) else r0
        r1 = (r1, r1) if np.isscalar(r1) else r1
        ring0, ring1 = [], []
        for i in range(seg):
            a = 2 * math.pi * (i + 0.5) / seg
            ring0.append(p0 + u * math.cos(a) * r0[0] + w * math.sin(a) * r0[1])
            ring1.append(p1 + u * math.cos(a) * r1[0] + w * math.sin(a) * r1[1])
        for i in range(seg):
            j = (i + 1) % seg
            self.quad(ring0[i], ring0[j], ring1[j], ring1[i], bone, mat)
        if cap0:
            for i in range(seg):
                self._add(p0, ring0[(i + 1) % seg], ring0[i], bone, mat)
        if cap1:
            for i in range(seg):
                self._add(p1, ring1[i], ring1[(i + 1) % seg], bone, mat)

    def sphere(self, bone, c, r, mat, seg=10, rings=7, scale=(1, 1, 1), mat2=None, lat_max=math.pi, lat_min=0.0):
        c = np.asarray(c, float); sx, sy, sz = scale
        seg = _seg(seg, 4); rings = _seg(rings, 2)
        def P(i, k):
            th = lat_min + (min(lat_max, math.pi) - lat_min) * k / rings; ph = 2 * math.pi * i / seg
            return c + np.array([r * sx * math.sin(th) * math.cos(ph), r * sy * math.cos(th), r * sz * math.sin(th) * math.sin(ph)])
        for k in range(rings):
            for i in range(seg):
                m = mat if (mat2 is None or (i + k) % 2 == 0) else mat2
                a, b, cc, d = P(i, k), P(i + 1, k), P(i + 1, k + 1), P(i, k + 1)
                if k == 0 and lat_min == 0:
                    self._add(a, cc, d, bone, m)
                elif k == rings - 1 and lat_max >= math.pi:
                    self._add(a, b, d, bone, m)
                else:
                    self.quad(a, b, cc, d, bone, m)

    def box(self, bone, lo, hi, mat, taper=(1.0, 1.0)):
        x0, y0, z0 = lo; x1, y1, z1 = hi
        cx = (x0 + x1) / 2; tx = taper[0]
        v = [np.array(p, float) for p in [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
                                          (cx + (x0 - cx) * tx, y1, z0), (cx + (x1 - cx) * tx, y1, z0),
                                          (cx + (x1 - cx) * tx, y1, z1 * taper[1] + z0 * (1 - taper[1])),
                                          (cx + (x0 - cx) * tx, y1, z1 * taper[1] + z0 * (1 - taper[1]))]]
        F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        for f in F:
            self.quad(v[f[0]], v[f[1]], v[f[2]], v[f[3]], bone, mat)

    def box8(self, bone, v, mat):
        """box from 8 corners: bottom face 0..3 (lo y), top face 4..7, same order as box()"""
        v = [np.asarray(p, float) for p in v]
        F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        for f in F:
            self.quad(v[f[0]], v[f[1]], v[f[2]], v[f[3]], bone, mat)

    def arrays(self):
        T = np.array(self.tris, dtype=np.float64)          # (M,3,3)
        return T, np.array(self.bones, np.int32), np.array(self.mats, np.int32)


def build_mannequin(spec=None, include_ball=True, prop=None, face=None):
    """Build the mannequin. `spec` (CharacterSpec) controls girth, face, hair,
    clothing.  Height is applied as a uniform scale by the caller (spec.scale).
    v9: `face` = expression parameters (sforge.expressions.params_for); the face always has the SAME triangles
    (only moved), so every expression is a morph target of the neutral mesh."""
    from .spec import CharacterSpec
    sp = spec or CharacterSpec()
    g = sp.girth; gx = g ** 0.6          # sideways growth limited (arms stay attached)
    fighter = str(getattr(sp, "style", "") or "").lower() == "fighter"
    gz = g * (1.38 if fighter else 1.0)        # torso depth (front-back) - the mannequin was a plank in side view
    gl = g * (1.22 if fighter else 1.0)        # limb thickness
    J = rest_world()
    b = MeshBuilder()
    hs = sp.size("head")
    fp = dict(face or {})
    top, bottom, shoes = sp.top.lower(), sp.bottom.lower(), sp.shoes.lower()
    # ---- head
    hc = J["head"] + np.array([0, 0.105, 0.0]) * hs
    R = 0.112 * hs
    b.sphere("head", hc, R, "skin", seg=12, rings=8, scale=(0.92, 1.08, 1.0))
    hair = sp.hair_style.lower()
    hc2 = hc + np.array([0, 0.018, -0.012]) * hs
    if hair in ("short", "long", "ponytail", "bun", "curly"):
        b.sphere("head", hc2, R * 1.055, "hair", seg=12, rings=8, scale=(0.95, 1.06, 1.02), lat_max=math.pi * 0.42)
    elif hair == "buzz":
        b.sphere("head", hc2 + [0, -0.004, 0], R * 1.02, "hair", seg=12, rings=8, scale=(0.94, 1.07, 1.01), lat_max=math.pi * 0.38)
    elif hair == "afro":
        b.sphere("head", hc2 + [0, 0.03, -0.01], R * 1.45, "hair", seg=12, rings=8, scale=(1, 0.95, 1), lat_max=math.pi * 0.55)
    if hair == "long":
        b.box("head", hc + np.array([-0.10, -0.20, -0.125]) * hs, hc + np.array([0.10, 0.06, -0.06]) * hs, "hair", taper=(1.0, 1.0))
    if hair == "ponytail":
        b.cyl("head", hc + np.array([0, 0.03, -0.11]) * hs, hc + np.array([0, -0.03, -0.13]) * hs, 0.035, 0.03, "hair", seg=6)   # v9: the tail is a physics chain
    if hair == "bun":
        b.sphere("head", hc + np.array([0, 0.10, -0.09]) * hs, 0.045, "hair", seg=8, rings=5)
    if hair == "curly":
        for i in range(10):
            a = 2 * math.pi * i / 10
            b.sphere("head", hc2 + np.array([math.cos(a) * 0.08, 0.07 + 0.02 * (i % 2), math.sin(a) * 0.08]) * hs, 0.035, "hair", seg=6, rings=4)
    ns = sp.size("nose")
    b.box("head", hc + np.array([-0.016 * ns, -0.03 * ns, 0.09]) * hs, hc + np.array([0.016 * ns, 0.02, 0.09 + 0.045 * ns]) * hs,
          "skin", taper=(0.6, 0.4))
    es = sp.size("ears")
    for sx in (-1, 1):
        b.sphere("head", hc + np.array([sx * 0.105, -0.01, -0.005]) * hs, 0.025 * es * hs, "skin", seg=6, rings=4, scale=(0.6, 1.2, 1))
        # eyes: white + iris (iris coloured by eye_colour)
        ec = hc + np.array([sx * 0.04, 0.012, 0.094]) * hs
        b.sphere("head", ec, 0.017 * hs, "eye_white", seg=6, rings=4, scale=(1.2, 0.8, 0.6))
        b.sphere("head", ec + np.array([0, 0, 0.009]) * hs, 0.0095 * hs, "eye", seg=6, rings=4, scale=(1, 1, 0.6))
        _face_eye(b, ec, sx, hs, fp)
    _face_mouth(b, hc, hs, sp.size("mouth"), fp)
    fh = sp.facial_hair.lower()
    if fh in ("beard", "stubble"):
        grow = 1.03 if fh == "stubble" else 1.09
        b.sphere("head", hc + np.array([0, -0.004, 0.004]) * hs, R * grow, "hair", seg=12, rings=3, scale=(0.92, 1.08, 1.0),
                 lat_min=math.pi * 0.66, lat_max=math.pi * 0.93)
    if fh in ("moustache", "beard"):
        mc = hc + np.array([0, -0.058, 0.093]) * hs          # same mouth centre as _face_mouth
        b.box("head", mc + np.array([-0.03, 0.008, 0.0]) * hs, mc + np.array([0.03, 0.02, 0.018]) * hs, "hair")
    if "freckle" in sp.complexion.lower():
        for sx in (-1, 1):
            for k in range(3):
                b.sphere("head", hc + np.array([sx * (0.035 + 0.012 * k), -0.018 - 0.006 * (k % 2), 0.1]) * hs, 0.0045 * hs,
                         "mouth", seg=4, rings=3)
    # ---- neck + collar
    b.cyl("neck", J["neck"] + [0, -0.06, 0.0], J["head"] + [0, 0.03, 0], 0.052 * g ** 0.5, 0.048 * g ** 0.5, "skin")
    if top in ("jersey", "tshirt", "longsleeve", "hoodie"):
        b.cyl("chest", J["neck"] + [0, -0.05, 0.005], J["neck"] + [0, -0.005, 0.005], (0.075 * gx, 0.07 * g), (0.068 * gx, 0.062 * g), "trim", seg=10)
    # ---- torso
    b.cyl("chest", J["chest"] + [0, -0.07, 0], J["chest"] + [0, 0.19, 0], (0.165 * gx, 0.105 * gz), (0.205 * gx, 0.115 * gz), "shirt", seg=10)
    b.cyl("chest", J["chest"] + [0, 0.19, 0], J["neck"] + [0, -0.01, 0], (0.205 * gx, 0.115 * gz), (0.09 * gx, 0.07 * gz), "shirt", seg=10, cap0=False)
    b.cyl("spine", J["hips"] + [0, 0.0, 0], J["chest"] + [0, -0.03, 0], (0.155 * gx, 0.1 * gz), (0.165 * gx, 0.105 * gz), "shirt", seg=10)
    if top == "hoodie":
        b.sphere("chest", J["neck"] + [0, 0.02, -0.09], 0.09, "shirt", seg=8, rings=5, scale=(1.2, 0.8, 0.8))
    b.cyl("hips", J["hips"] + [0, -0.17, 0], J["hips"] + [0, 0.04, 0], (0.172 * gx, 0.112 * gz), (0.162 * gx, 0.105 * gz), "shorts", seg=10)
    hand_s, foot_s = sp.size("hands"), sp.size("feet")
    for s, sg in (("L", 1), ("R", -1)):
        sh = J["upperarm_" + s]
        sleeve = "skin" if top == "tank" else "shirt"
        b.sphere("upperarm_" + s, sh + [0, -0.01, 0], 0.068 * gl ** 0.8, sleeve, seg=8, rings=5)
        b.cyl("upperarm_" + s, sh + [0, -0.02, 0], sh + [0, -0.15, 0], 0.062 * gl ** 0.8, 0.056 * gl ** 0.8, sleeve)
        long_sl = top in ("longsleeve", "hoodie")
        arm_m = "shirt" if long_sl else "skin"
        b.cyl("upperarm_" + s, sh + [0, -0.15, 0], J["forearm_" + s] + [0, 0.01, 0], 0.046 * gl ** 0.8 * (1.15 if long_sl else 1), 0.042 * gl ** 0.8 * (1.15 if long_sl else 1), arm_m, cap0=False)
        b.cyl("forearm_" + s, J["forearm_" + s] + [0, 0.02, 0], J["hand_" + s] + [0, 0.0, 0], 0.042 * gl ** 0.7 * (1.12 if long_sl else 1), 0.032 * gl ** 0.7 * (1.12 if long_sl else 1), arm_m)
        hd = J["hand_" + s]
        b.cyl("hand_" + s, hd + [0, 0.005, 0], hd + [0, -0.10 * hand_s, 0.0], (0.022 * hand_s, 0.045 * hand_s), (0.018 * hand_s, 0.038 * hand_s), "skin", seg=6)
        b.cyl("hand_" + s, hd + [0, -0.02, 0.035 * hand_s], hd + [sg * 0.01, -0.06 * hand_s, 0.06 * hand_s], 0.013 * hand_s, 0.011 * hand_s, "skin", seg=5)
        th = J["thigh_" + s]
        trousers = bottom in ("trousers", "pants", "jeans")
        b.cyl("thigh_" + s, th + [0, 0.03, 0], th + [0, -0.19, 0], 0.092 * gl, 0.084 * gl, "shorts")
        b.cyl("thigh_" + s, th + [0, -0.19, 0], J["shin_" + s] + [0, 0.0, 0], 0.072 * gl * (1.12 if trousers else 1), 0.056 * gl * (1.15 if trousers else 1), "shorts" if trousers else "skin", cap0=False)
        sn = J["shin_" + s]
        if trousers:
            b.cyl("shin_" + s, sn + [0, 0.02, 0], J["foot_" + s] + [0, 0.02, 0], 0.064 * gl, 0.056 * gl, "shorts")
        else:
            b.cyl("shin_" + s, sn + [0, 0.02, 0], sn + [0, -0.09, 0], 0.056 * gl, 0.058 * gl, "skin")
            if shoes == "barefoot":
                b.cyl("shin_" + s, sn + [0, -0.09, 0], J["foot_" + s] + [0, 0.0, 0], 0.058 * gl, 0.042 * gl, "skin", cap0=False)
            else:
                b.cyl("shin_" + s, sn + [0, -0.09, 0], sn + [0, -0.14, 0], 0.06 * gl, 0.059 * gl, "trim", cap1=False)
                b.cyl("shin_" + s, sn + [0, -0.14, 0], J["foot_" + s] + [0, 0.0, 0], 0.059 * gl, 0.042 * gl, "socks", cap0=False)
        ft = J["foot_" + s]
        fl = 0.19 * foot_s
        b.box("foot_" + s, ft + [-0.048 * foot_s, -0.082, -0.065], ft + [0.048 * foot_s, 0.03 if shoes != "barefoot" else 0.0, fl], "boots", taper=(0.85, 0.55))
    if fighter:
        _fighter_extras(b, J, sp, g, gx, gz, gl, hs, top, bottom, shoes)
    acc = [a.strip().lower() for a in str(getattr(sp, "accessories", "") or "").replace("+", ",").split(",") if a.strip()]
    if acc:
        add_accessories(b, J, sp, acc, hs, g, gx)
    pat = str(getattr(sp, "pattern", "") or "").strip().lower()
    if include_ball:
        bc = J["ball"]
        b.sphere("ball", bc, BALL_RADIUS, "ball", seg=10, rings=6, mat2="ball_seam")
    if prop == "kart":
        add_kart(b, J)
    T, B, M = b.arrays()
    if pat and pat != "none":
        T, B, M = apply_pattern(T, B, M, pat, J)
    return T, B, M


# ---------------------------------------------------------------- v9 face (fixed topology)
def _rot2(p, c, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    d = np.asarray(p, float) - c
    return c + np.array([d[0] * ca - d[1] * sa, d[0] * sa + d[1] * ca, d[2]])


def _face_eye(b, ec, sx, hs, fp):
    """brow (tilted / raised) + upper eyelid (skin box that slides down over the eye)"""
    up = fp.get("brow_up", 0.0) * 0.010 + (fp.get("brow_one", 0.0) * 0.012 if sx > 0 else 0.0)
    bc = ec + np.array([0, 0.026 + up, 0.004]) * hs
    ang = math.radians(sx * fp.get("brow_in", 0.0) * 22.0)
    hx, hy, hz = 0.02 * hs, 0.004 * hs, 0.008 * hs
    cs = [bc + np.array([dx, dy, dz]) for dy in (-hy, hy) for (dx, dz) in ((-hx, -hz), (hx, -hz), (hx, hz), (-hx, hz))]
    b.box8("head", [_rot2(p, bc, ang) for p in cs], "brow")
    close = min(1.0, fp.get("lid", 0.0) + 0.35 * fp.get("squint", 0.0))
    top = ec[1] + 0.0145 * hs
    h = (0.0004 + 0.029 * close) * hs
    b.box("head", (ec[0] - 0.022 * hs, top - h, ec[2] - 0.002 * hs), (ec[0] + 0.022 * hs, top, ec[2] + 0.0168 * hs), "eyelid")
    sq = 0.35 * fp.get("squint", 0.0)          # lower lid (squint / smile pushes it up)
    bot = ec[1] - 0.0145 * hs
    h2 = (0.0004 + 0.012 * sq) * hs
    b.box("head", (ec[0] - 0.02 * hs, bot, ec[2] - 0.002 * hs), (ec[0] + 0.02 * hs, bot + h2, ec[2] + 0.0165 * hs), "eyelid")


def _face_mouth(b, hc, hs, ms, fp):
    """three-piece mouth (corners bend up / down, centre opens) + teeth; always 4 boxes"""
    mc = hc + np.array([0, -0.058, 0.093]) * hs
    w = 0.028 * ms * fp.get("mouth_w", 1.0)
    hh = 0.0045 * (1.0 - 0.45 * fp.get("press", 0.0))
    op = fp.get("mouth_open", 0.0)
    drop = 0.04 * op
    z0, z1 = -0.004, 0.007
    def P(x, y, z):
        return mc + np.array([x, y, z]) * hs
    b.box8("head", [P(-w / 3, -hh - drop, z0), P(w / 3, -hh - drop, z0), P(w / 3, -hh - drop, z1), P(-w / 3, -hh - drop, z1),
                    P(-w / 3, hh, z0), P(w / 3, hh, z0), P(w / 3, hh, z1), P(-w / 3, hh, z1)], "mouth")
    for sx in (-1, 1):
        lift = 0.016 * fp.get("corner", 0.0) + (0.018 * fp.get("smirk", 0.0) if sx > 0 else 0.0)
        xi, xo = sx * w / 3, sx * w
        lo_i, lo_o = -hh - drop * 0.8, -hh * 0.7 + lift - drop * 0.25
        hi_i, hi_o = hh, hh * 0.7 + lift
        v = [P(xi, lo_i, z0), P(xo, lo_o, z0), P(xo, lo_o, z1), P(xi, lo_i, z1),
             P(xi, hi_i, z0), P(xo, hi_o, z0), P(xo, hi_o, z1), P(xi, hi_i, z1)]
        if sx < 0:
            v = [v[1], v[0], v[3], v[2], v[5], v[4], v[7], v[6]]
        b.box8("head", v, "mouth")
    show = fp.get("teeth", 0.0) * min(1.0, op * 1.6) if op > 0.05 else 0.0
    if show > 0:
        th = 0.0001 + 0.0085 * show
        zt = z1 + 0.0006
        b.box("head", P(-w * 0.55, hh - th - 0.0004, zt - 0.003), P(w * 0.55, hh - 0.0004, zt), "teeth")
    else:                                                    # closed: collapsed inside the head (same topology for morphs)
        e = 1e-5
        b.box("head", P(-e, -e, -0.03), P(e, e, -0.03 + e), "teeth")


def add_kart(b, J):
    """Simple go-kart, built in the *rest* frame so that with SEAT (lift -0.58)
    it sits on the ground.  Follows the hips bone (spins/drifts with the driver)."""
    hy = J["hips"][1]
    o = np.array([0.0, 0.58 * hy / 0.95, 0.0])   # rest-space point that lands on the ground when seated (SEAT lift -0.58)
    def P(x, y, z):
        return o + np.array([x, y, z])
    b.box("hips", P(-0.36, 0.12, -0.55), P(0.36, 0.24, 1.05), "kart", taper=(0.85, 1.0))        # floor pan
    b.box("hips", P(-0.30, 0.24, 0.55), P(0.30, 0.42, 1.10), "kart", taper=(0.6, 0.7))          # nose
    b.box("hips", P(-0.20, 0.24, -0.30), P(0.20, 0.62, -0.12), "kart_dark", taper=(0.9, 1.0))  # seat back
    b.box("hips", P(-0.42, 0.20, -0.70), P(0.42, 0.30, -0.55), "kart_trim")                     # rear bumper
    b.box("hips", P(-0.40, 0.18, 1.05), P(0.40, 0.28, 1.18), "kart_trim")                       # front bumper
    b.cyl("hips", P(0, 0.40, 0.62), P(0, 0.62, 0.42), 0.02, 0.02, "kart_dark", seg=6)           # steering column
    b.cyl("hips", P(0, 0.64, 0.38), P(0, 0.66, 0.43), 0.13, 0.13, "kart_dark", seg=10)          # wheel
    for x, z in ((-0.42, -0.45), (0.42, -0.45), (-0.38, 0.85), (0.38, 0.85)):
        r = 0.17 if z < 0 else 0.14
        b.cyl("hips", P(x - 0.08 * np.sign(x), r, z), P(x + 0.08 * np.sign(x), r, z), r, r, "kart_dark", seg=12)
        b.cyl("hips", P(x + 0.081 * np.sign(x), r, z), P(x + 0.085 * np.sign(x), r, z), r * 0.55, r * 0.55, "kart_trim", seg=8)
    b.box("hips", P(-0.08, 0.42, -0.62), P(0.08, 0.50, -0.40), "kart_trim")                      # engine


def build_ball():
    b = MeshBuilder()
    b.sphere("ball", (0, BALL_RADIUS, 0), BALL_RADIUS, "ball", seg=16, rings=10, mat2="ball_seam")
    return b.arrays()


def build_mannequin_budget(spec=None, prop=None, max_tris=None):
    """Lowest-to-highest detail search: the most detailed mannequin whose triangle count fits max_tris.
    Returns (T, B, M, detail). max_tris=None -> standard detail. Note: higher detail only adds segments
    to the same primitive shapes (smoother), it does not invent new detail."""
    global DETAIL
    if not max_tris:
        DETAIL = 1.0
        T, B, M = build_mannequin(spec, prop=prop)
        return T, B, M, 1.0
    best = None
    try:
        for d in (9.0, 6.0, 4.0, 3.0, 2.0, 1.5, 1.25, 1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.0):
            DETAIL = d
            T, B, M = build_mannequin(spec, prop=prop)
            best = (T, B, M, d)
            if len(T) <= max_tris:
                return best
        return best
    finally:
        DETAIL = 1.0


# ---------------------------------------------------------------- v9 accessories (for variants / NPCs)
ACCESSORIES = {
    "cap": "baseball cap", "beanie": "woolly hat", "headband": "sweat band", "helmet": "round helmet",
    "crown": "crown (gold)", "horns": "two horns", "glasses": "glasses", "sunglasses": "sunglasses", "mask": "face mask",
    "backpack": "backpack", "belt": "belt", "wristbands": "wristbands", "gloves": "gloves", "kneepads": "knee pads",
    "shoulder_pads": "shoulder pads", "armor": "chest plate", "scarf": "scarf (physics tails)",
    "cape": "cape (physics cloth)", "satchel": "shoulder bag (strap + bag)", "visor": "glowing visor (emissive)", "wraps": "hand wraps", "hood": "hood",
}
PHYSICS_ACCESSORIES = ("scarf", "cape")


def add_accessories(b, J, sp, acc, hs, g, gx):
    hc = J["head"] + np.array([0, 0.105, 0.0]) * hs
    R = 0.112 * hs
    for a in acc:
        if a == "cap":
            b.sphere("head", hc + np.array([0, 0.03, -0.005]) * hs, R * 1.09, "accessory", seg=12, rings=6, scale=(0.96, 0.9, 1.04), lat_max=math.pi * 0.42)
            b.box("head", hc + np.array([-0.075, 0.035, 0.07]) * hs, hc + np.array([0.075, 0.047, 0.21]) * hs, "accessory2")
        elif a == "beanie":
            b.sphere("head", hc + np.array([0, 0.035, -0.008]) * hs, R * 1.12, "accessory", seg=12, rings=6, scale=(0.95, 1.12, 1.02), lat_max=math.pi * 0.45)
            b.sphere("head", hc + np.array([0, 0.17, -0.01]) * hs, 0.028 * hs, "accessory2", seg=6, rings=4)
        elif a == "headband":
            b.cyl("head", hc + np.array([0, 0.035, -0.008]) * hs, hc + np.array([0, 0.06, -0.008]) * hs, R * 1.07, R * 1.06, "accessory", seg=12)
        elif a == "helmet":
            b.sphere("head", hc + np.array([0, 0.02, -0.01]) * hs, R * 1.22, "accessory", seg=12, rings=7, scale=(0.98, 1.05, 1.05), lat_max=math.pi * 0.55)
            b.box("head", hc + np.array([-0.12, -0.005, 0.02]) * hs, hc + np.array([0.12, 0.01, 0.13]) * hs, "accessory2")
        elif a == "crown":
            b.cyl("head", hc + np.array([0, 0.08, -0.01]) * hs, hc + np.array([0, 0.125, -0.01]) * hs, R * 0.95, R * 1.0, "accessory2", seg=10, cap0=False, cap1=False)
            for i in range(5):
                an = 2 * math.pi * i / 5
                c = hc + np.array([math.sin(an) * R * 0.97, 0.125, math.cos(an) * R * 0.97 - 0.01]) * hs
                b.cyl("head", c, c + np.array([0, 0.045, 0]) * hs, 0.012 * hs, 0.002 * hs, "accessory2", seg=4)
        elif a == "horns":
            for sx in (-1, 1):
                c = hc + np.array([sx * 0.07, 0.08, 0.0]) * hs
                b.cyl("head", c, c + np.array([sx * 0.06, 0.09, 0.03]) * hs, 0.022 * hs, 0.003 * hs, "accessory", seg=6)
        elif a in ("glasses", "sunglasses", "visor"):
            if a == "visor":
                b.box("head", hc + np.array([-0.085, 0.0, 0.085]) * hs, hc + np.array([0.085, 0.03, 0.113]) * hs, "emissive")
            else:
                mat = "accessory2" if a == "sunglasses" else "eye_white"
                for sx in (-1, 1):
                    ec = hc + np.array([sx * 0.04, 0.012, 0.112]) * hs
                    b.box("head", ec + np.array([-0.023, -0.015, 0]) * hs, ec + np.array([0.023, 0.015, 0.004]) * hs, "accessory")
                    if a == "sunglasses":
                        b.box("head", ec + np.array([-0.019, -0.011, 0.004]) * hs, ec + np.array([0.019, 0.011, 0.006]) * hs, "accessory")
                b.box("head", hc + np.array([-0.02, 0.02, 0.112]) * hs, hc + np.array([0.02, 0.026, 0.117]) * hs, "accessory")
        elif a == "mask":
            b.sphere("head", hc + np.array([0, -0.004, 0.006]) * hs, R * 1.04, "accessory", seg=12, rings=4, scale=(0.94, 1.08, 1.02),
                     lat_min=math.pi * 0.55, lat_max=math.pi * 0.9)
        elif a == "backpack":
            b.box("chest", J["chest"] + np.array([-0.13 * gx, -0.12, -0.13 * g - 0.11]), J["chest"] + np.array([0.13 * gx, 0.2, -0.1 * g]), "accessory", taper=(0.9, 1.0))
        elif a == "satchel":
            b.box("hips", J["hips"] + np.array([0.13 * gx, -0.12, -0.06]), J["hips"] + np.array([0.21 * gx, 0.08, 0.12]), "accessory")
            b.cyl("chest", J["chest"] + np.array([-0.16 * gx, 0.2, 0.0]), J["hips"] + np.array([0.17 * gx, 0.05, 0.03]), 0.012, 0.012, "accessory2", seg=4)
        elif a == "belt":
            b.cyl("hips", J["hips"] + np.array([0, 0.02, 0]), J["hips"] + np.array([0, 0.065, 0]), (0.176 * gx, 0.116 * g), (0.172 * gx, 0.113 * g), "accessory", seg=10)
            b.box("hips", J["hips"] + np.array([-0.025, 0.02, 0.112 * g]), J["hips"] + np.array([0.025, 0.065, 0.125 * g]), "accessory2")
        elif a == "wristbands":
            for s in ("L", "R"):
                b.cyl("forearm_" + s, J["hand_" + s] + [0, 0.06, 0], J["hand_" + s] + [0, 0.0, 0], 0.041 * g ** 0.7, 0.037 * g ** 0.7, "accessory", seg=8)
        elif a == "gloves":
            for s in ("L", "R"):
                hd = J["hand_" + s]
                b.cyl("hand_" + s, hd + [0, 0.01, 0], hd + [0, -0.11, 0.0], (0.03, 0.052), (0.026, 0.046), "accessory", seg=6)
        elif a == "kneepads":
            for s in ("L", "R"):
                b.sphere("shin_" + s, J["shin_" + s] + [0, 0.0, 0.035], 0.055 * g, "accessory", seg=8, rings=5, scale=(1, 1.2, 0.8))
        elif a == "shoulder_pads":
            for s in ("L", "R"):
                b.sphere("upperarm_" + s, J["upperarm_" + s] + [0, 0.01, 0], 0.085 * g ** 0.8, "accessory", seg=8, rings=5, scale=(1.1, 0.7, 1.1), lat_max=math.pi * 0.55)
        elif a == "armor":
            b.cyl("chest", J["chest"] + [0, -0.06, 0], J["chest"] + [0, 0.2, 0], (0.178 * gx, 0.12 * g), (0.215 * gx, 0.128 * g), "accessory", seg=10)
        elif a in ("wraps", "hood"):
            pass     # fighter style adds these in _fighter_extras
        elif a in PHYSICS_ACCESSORIES:
            pass     # physics chains: sforge/physics.py adds them per frame (they swing)
        else:
            raise ValueError("unknown accessory '%s' (use %s)" % (a, ", ".join(ACCESSORIES)))


# ---------------------------------------------------------------- v9 3D texture overlays on the top (follow the body)
PATTERNS = {"hoops": "horizontal hoops", "stripes": "vertical stripes", "sash": "diagonal sash", "chest_band": "one chest band",
            "halves": "left / right halves", "check": "checks", "camo": "camouflage blotches", "dots": "polka dots"}


def _subdiv(T):
    a, b_, c = T[:, 0], T[:, 1], T[:, 2]
    ab, bc, ca = (a + b_) / 2, (b_ + c) / 2, (c + a) / 2
    return np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b_, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])


def pattern_value(name, P, J):
    """True = pattern colour at rest-pose points P (n,3)"""
    y = P[:, 1] - J["chest"][1]
    x, z = P[:, 0], P[:, 2]
    if name == "hoops":
        return (np.floor(y / 0.07) % 2 == 0)
    if name == "stripes":
        return (np.floor((x + 1.0) / 0.06) % 2 == 0)
    if name == "sash":
        return np.abs((x + y * 0.9)) < 0.05
    if name == "chest_band":
        return np.abs(y - 0.09) < 0.045
    if name == "halves":
        return x > 0
    if name == "check":
        return ((np.floor(y / 0.07) + np.floor((x + 1.0) / 0.07)) % 2 == 0)
    if name == "dots":
        gx_, gy_ = (x + 1.0) / 0.08, y / 0.08
        return ((gx_ - np.round(gx_)) ** 2 + (gy_ - np.round(gy_)) ** 2) < 0.08
    if name == "camo":
        v = np.sin(x * 23 + 1.3) * np.sin(y * 19 + 0.7) + 0.6 * np.sin((x + y) * 37 + z * 11) + 0.4 * np.sin(z * 29 - y * 13)
        return v > 0.35
    raise ValueError("unknown pattern '%s' (use %s)" % (name, ", ".join(PATTERNS)))


def apply_pattern(T, B, M, name, J, levels=2):
    """split the shirt triangles (x4 per level) and paint the pattern on the pieces by their REST position, so
    the pattern moves with the body in every frame and in the GLB"""
    si = MATS.index("shirt")
    sel = M == si
    if not sel.any():
        return T, B, M
    St, Sb = T[sel], B[sel]
    for _ in range(levels):
        St = _subdiv(St)
        Sb = np.tile(Sb, 4)
    on = pattern_value(name, St.mean(1), J)
    Sm = np.where(on, MATS.index("pattern"), si).astype(M.dtype)
    return (np.concatenate([T[~sel], St]), np.concatenate([B[~sel], Sb]), np.concatenate([M[~sel], Sm]))


def _fighter_extras(b, J, sp, g, gx, gz, gl, hs, top, bottom, shoes):
    """Extra volume that makes the mannequin read as a fighter: pecs/abs, deltoids, biceps, calves, fists, brow/jaw,
    robe/hakama, hood, spiky hair, hand wraps.  Driven by spec.top / bottom / hair_style / accessories."""
    hc = J["head"] + np.array([0, 0.105, 0.0]) * hs
    R = 0.112 * hs
    bare = top in ("bare", "none", "shirtless")
    torso_m = "skin" if bare else "shirt"
    ch = J["chest"]
    # chest + abs volume
    for sx in (-1, 1):
        b.sphere("chest", ch + np.array([sx * 0.075 * gx, 0.105, 0.075 * gz]), 0.082 * g, torso_m, seg=10, rings=6, scale=(1.0, 0.82, 0.72))
    for k in range(3):
        for sx in (-1, 1):
            b.sphere("spine", J["hips"] + np.array([sx * 0.04 * gx, 0.075 + 0.06 * k, 0.085 * gz]), 0.036 * g, torso_m, seg=6, rings=4, scale=(1.0, 0.9, 0.55))
    # shoulders / biceps / calves
    for s_ in ("L", "R"):
        sh = J["upperarm_" + s_]
        arm_m = "shirt" if top in ("longsleeve", "hoodie", "robe", "kimono") else "skin"
        b.sphere("upperarm_" + s_, sh + [0, -0.01, 0.0], 0.085 * gl ** 0.8, arm_m, seg=10, rings=7)
        b.sphere("upperarm_" + s_, sh + [0, -0.095, 0.012], 0.058 * gl ** 0.8, arm_m, seg=8, rings=5, scale=(1, 1.4, 1.05))
        b.sphere("forearm_" + s_, J["forearm_" + s_] + [0, -0.07, 0.0], 0.05 * gl ** 0.7, arm_m, seg=8, rings=5, scale=(1, 1.5, 1))
        sn = J["shin_" + s_]
        leg_m = "shorts" if bottom in ("trousers", "pants", "jeans") else "skin"
        if bottom == "shorts":
            b.sphere("thigh_" + s_, J["thigh_" + s_] + [0, -0.215, 0.01], 0.078 * gl, "skin", seg=10, rings=6, scale=(1, 1.5, 1.0))
            b.cyl("thigh_" + s_, J["thigh_" + s_] + [0, 0.045, 0], J["thigh_" + s_] + [0, -0.17, 0], (0.118 * gl, 0.118 * gl), (0.11 * gl, 0.11 * gl), "shorts", seg=10)
        b.sphere("shin_" + s_, sn + [0, -0.11, -0.02], 0.062 * gl, leg_m, seg=8, rings=5, scale=(1, 1.7, 1.0))
        hd = J["hand_" + s_]
        b.sphere("hand_" + s_, hd + [0, -0.045, 0.005], 0.058 * sp.size("hands"), "skin", seg=8, rings=6, scale=(0.9, 1.0, 1.0))
    # head: brow ridge + jaw
    b.box("head", hc + np.array([-0.075, 0.03, 0.075]) * hs, hc + np.array([0.075, 0.048, 0.118]) * hs, "skin", taper=(1.0, 0.9))
    b.box("head", hc + np.array([-0.07, -0.105, 0.0]) * hs, hc + np.array([0.07, -0.045, 0.085]) * hs, "skin", taper=(0.78, 0.9))
    hair = sp.hair_style.lower()
    if hair == "spiky":
        for i in range(11):
            an = math.pi * (i / 10.0) * 1.15 - 0.15
            base = hc + np.array([0.0, 0.07 + 0.02 * math.sin(an * 2), -0.02]) * hs
            tip = base + np.array([0.0, math.sin(an) * 0.13, math.cos(an) * -0.12 + 0.03]) * hs
            b.cyl("head", base + np.array([0, 0.02, 0]) * hs, tip + np.array([0, 0.03, 0.05]) * hs, 0.034 * hs, 0.004 * hs, "hair", seg=5)
        b.sphere("head", hc + np.array([0, 0.02, -0.012]) * hs, R * 1.07, "hair", seg=12, rings=8, scale=(0.96, 1.08, 1.04), lat_max=math.pi * 0.46)
    if hair == "hood" or "hood" in str(getattr(sp, "accessories", "")):
        b.sphere("head", hc + np.array([0, 0.012, -0.03]) * hs, R * 1.32, "shirt", seg=14, rings=9, scale=(1.0, 1.08, 1.1), lat_max=math.pi * 0.78)
        b.sphere("head", hc + np.array([0, -0.005, 0.05]) * hs, R * 0.96, "kart_dark", seg=10, rings=6, scale=(0.95, 1.05, 0.5), lat_max=math.pi * 0.9)
        b.sphere("head", hc + np.array([0, -0.005, 0.09]) * hs, R * 0.9, "skin", seg=10, rings=6, scale=(0.82, 0.95, 0.45), lat_max=math.pi * 0.9)
    # robe / hakama (wide trouser legs + sash + sleeves)
    if top in ("robe", "kimono"):
        for s_ in ("L", "R"):
            b.cyl("thigh_" + s_, J["thigh_" + s_] + [0, 0.05, 0], J["shin_" + s_] + [0, 0.0, 0.0], (0.145 * gl, 0.15 * gl), (0.15 * gl, 0.155 * gl), "shirt", seg=10, cap1=False)
            b.cyl("shin_" + s_, J["shin_" + s_] + [0, 0.0, 0.0], J["foot_" + s_] + [0, 0.02, 0], (0.15 * gl, 0.155 * gl), (0.125 * gl, 0.13 * gl), "shirt", seg=10, cap0=False)
            b.cyl("forearm_" + s_, J["forearm_" + s_] + [0, 0.03, 0], J["hand_" + s_] + [0, 0.05, 0], 0.075 * gl, 0.1 * gl, "shirt", seg=8)
        b.cyl("hips", J["hips"] + [0, 0.01, 0], J["hips"] + [0, 0.1, 0], (0.19 * gx, 0.145 * gz), (0.18 * gx, 0.14 * gz), "trim", seg=12)
        b.cyl("hips", J["hips"] + [0, -0.12, 0], J["hips"] + [0, 0.02, 0], (0.2 * gx, 0.16 * gz), (0.19 * gx, 0.15 * gz), "shirt", seg=12)
    acc = [a.strip().lower() for a in str(getattr(sp, "accessories", "") or "").replace("+", ",").split(",") if a.strip()]
    if "wraps" in acc:
        for s_ in ("L", "R"):
            hd = J["hand_" + s_]
            b.cyl("forearm_" + s_, hd + [0, 0.09, 0], hd + [0, 0.0, 0], 0.046 * gl ** 0.7, 0.04 * gl ** 0.7, "accessory", seg=8)
            b.sphere("hand_" + s_, hd + [0, -0.045, 0.005], 0.062 * sp.size("hands"), "accessory", seg=8, rings=6, scale=(0.9, 1.0, 1.0))
