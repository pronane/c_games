"""Low-poly mannequin mesh built procedurally around the rig (rigid skinning:
each part follows exactly one bone, weight 1.0 - works in every engine).
The figure is a generic sports mannequin, not modelled on any real person."""
from __future__ import annotations
import math
import numpy as np
from .rig import JOINT_NAMES, rest_world, BALL_RADIUS

MATS = ["skin", "shirt", "shorts", "socks", "trim", "boots", "hair", "ball", "ball_seam", "eye", "eye_white", "mouth", "kart", "kart_dark", "kart_trim"]

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


DETAIL = 1.0   # segment multiplier for cylinders/spheres (console polygon budgets); 1.0 = standard mannequin


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

    def arrays(self):
        T = np.array(self.tris, dtype=np.float64)          # (M,3,3)
        return T, np.array(self.bones, np.int32), np.array(self.mats, np.int32)


def build_mannequin(spec=None, include_ball=True, prop=None):
    """Build the mannequin. `spec` (CharacterSpec) controls girth, face, hair,
    clothing.  Height is applied as a uniform scale by the caller (spec.scale)."""
    from .spec import CharacterSpec
    sp = spec or CharacterSpec()
    g = sp.girth; gx = g ** 0.6          # sideways growth limited (arms stay attached)
    J = rest_world()
    b = MeshBuilder()
    hs = sp.size("head")
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
        b.cyl("head", hc + np.array([0, 0.03, -0.11]) * hs, hc + np.array([0, -0.18, -0.16]) * hs, 0.035, 0.02, "hair", seg=6)
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
        b.box("head", ec + np.array([-0.02, 0.022, -0.004]) * hs, ec + np.array([0.02, 0.03, 0.012]) * hs, "hair")  # brow
    ms = sp.size("mouth")
    mc = hc + np.array([0, -0.058, 0.093]) * hs
    b.box("head", mc + np.array([-0.025 * ms, -0.006, -0.01]) * hs, mc + np.array([0.025 * ms, 0.006, 0.008]) * hs, "mouth")
    fh = sp.facial_hair.lower()
    if fh in ("beard", "stubble"):
        grow = 1.03 if fh == "stubble" else 1.09
        b.sphere("head", hc + np.array([0, -0.004, 0.004]) * hs, R * grow, "hair", seg=12, rings=3, scale=(0.92, 1.08, 1.0),
                 lat_min=math.pi * 0.66, lat_max=math.pi * 0.93)
    if fh in ("moustache", "beard"):
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
    b.cyl("chest", J["chest"] + [0, -0.07, 0], J["chest"] + [0, 0.19, 0], (0.165 * gx, 0.105 * g), (0.205 * gx, 0.115 * g), "shirt", seg=10)
    b.cyl("chest", J["chest"] + [0, 0.19, 0], J["neck"] + [0, -0.01, 0], (0.205 * gx, 0.115 * g), (0.09 * gx, 0.07 * g), "shirt", seg=10, cap0=False)
    b.cyl("spine", J["hips"] + [0, 0.0, 0], J["chest"] + [0, -0.03, 0], (0.155 * gx, 0.1 * g), (0.165 * gx, 0.105 * g), "shirt", seg=10)
    if top == "hoodie":
        b.sphere("chest", J["neck"] + [0, 0.02, -0.09], 0.09, "shirt", seg=8, rings=5, scale=(1.2, 0.8, 0.8))
    b.cyl("hips", J["hips"] + [0, -0.17, 0], J["hips"] + [0, 0.04, 0], (0.172 * gx, 0.112 * g), (0.162 * gx, 0.105 * g), "shorts", seg=10)
    hand_s, foot_s = sp.size("hands"), sp.size("feet")
    for s, sg in (("L", 1), ("R", -1)):
        sh = J["upperarm_" + s]
        sleeve = "skin" if top == "tank" else "shirt"
        b.sphere("upperarm_" + s, sh + [0, -0.01, 0], 0.068 * g ** 0.8, sleeve, seg=8, rings=5)
        b.cyl("upperarm_" + s, sh + [0, -0.02, 0], sh + [0, -0.15, 0], 0.062 * g ** 0.8, 0.056 * g ** 0.8, sleeve)
        long_sl = top in ("longsleeve", "hoodie")
        arm_m = "shirt" if long_sl else "skin"
        b.cyl("upperarm_" + s, sh + [0, -0.15, 0], J["forearm_" + s] + [0, 0.01, 0], 0.046 * g ** 0.8 * (1.15 if long_sl else 1), 0.042 * g ** 0.8 * (1.15 if long_sl else 1), arm_m, cap0=False)
        b.cyl("forearm_" + s, J["forearm_" + s] + [0, 0.02, 0], J["hand_" + s] + [0, 0.0, 0], 0.042 * g ** 0.7 * (1.12 if long_sl else 1), 0.032 * g ** 0.7 * (1.12 if long_sl else 1), arm_m)
        hd = J["hand_" + s]
        b.cyl("hand_" + s, hd + [0, 0.005, 0], hd + [0, -0.10 * hand_s, 0.0], (0.022 * hand_s, 0.045 * hand_s), (0.018 * hand_s, 0.038 * hand_s), "skin", seg=6)
        b.cyl("hand_" + s, hd + [0, -0.02, 0.035 * hand_s], hd + [sg * 0.01, -0.06 * hand_s, 0.06 * hand_s], 0.013 * hand_s, 0.011 * hand_s, "skin", seg=5)
        th = J["thigh_" + s]
        trousers = bottom in ("trousers", "pants", "jeans")
        b.cyl("thigh_" + s, th + [0, 0.03, 0], th + [0, -0.19, 0], 0.092 * g, 0.084 * g, "shorts")
        b.cyl("thigh_" + s, th + [0, -0.19, 0], J["shin_" + s] + [0, 0.0, 0], 0.072 * g * (1.12 if trousers else 1), 0.056 * g * (1.15 if trousers else 1), "shorts" if trousers else "skin", cap0=False)
        sn = J["shin_" + s]
        if trousers:
            b.cyl("shin_" + s, sn + [0, 0.02, 0], J["foot_" + s] + [0, 0.02, 0], 0.064 * g, 0.056 * g, "shorts")
        else:
            b.cyl("shin_" + s, sn + [0, 0.02, 0], sn + [0, -0.09, 0], 0.056 * g, 0.058 * g, "skin")
            if shoes == "barefoot":
                b.cyl("shin_" + s, sn + [0, -0.09, 0], J["foot_" + s] + [0, 0.0, 0], 0.058 * g, 0.042 * g, "skin", cap0=False)
            else:
                b.cyl("shin_" + s, sn + [0, -0.09, 0], sn + [0, -0.14, 0], 0.06 * g, 0.059 * g, "trim", cap1=False)
                b.cyl("shin_" + s, sn + [0, -0.14, 0], J["foot_" + s] + [0, 0.0, 0], 0.059 * g, 0.042 * g, "socks", cap0=False)
        ft = J["foot_" + s]
        fl = 0.19 * foot_s
        b.box("foot_" + s, ft + [-0.048 * foot_s, -0.082, -0.065], ft + [0.048 * foot_s, 0.03 if shoes != "barefoot" else 0.0, fl], "boots", taper=(0.85, 0.55))
    if include_ball:
        bc = J["ball"]
        b.sphere("ball", bc, BALL_RADIUS, "ball", seg=10, rings=6, mat2="ball_seam")
    if prop == "kart":
        add_kart(b, J)
    return b.arrays()


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
