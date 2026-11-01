"""Gaelic footballer design (v10.1) fitted to a game skeleton - the shared character description used by both the
Sprite Forge 3D pipeline (sforge.gamemesh) and the Blender reference build (tools/blender_gaelic.py).

Unlike sforge.sculpt's presets (bone-local to Sprite Forge's own rig), every shape here is placed from the skeleton's
JOINT POSITIONS in its bind pose, in world space: limbs run joint to joint, muscles sit at fractions along a segment
with offsets in that segment's own (side, front) frame, hands follow the real finger joints.  So the same design fits
any humanoid skeleton that uses (or is mapped to) these joint names (Unreal / MakeHuman 'game_engine' naming):
pelvis spine_01..03 neck_01 head clavicle_* upperarm_* lowerarm_* hand_* thigh_* calf_* foot_* ball_* + fingers.

Prims are in WORLD bind coordinates (evaluate with an identity bind); `Prim.bone` is the bone that owns the shape
and seeds the skin weights.  Paints are world-space too (bone=None), with kit colours as parameters, so one mesh +
one UV layout carries every kit as a different texture (the game swaps kit_<name>.png at draw time)."""
from __future__ import annotations
import math
import numpy as np
from .sculpt import B, Prim, Paint, face_paint, body as _forge_body, smooth, mix, ellmask, in_poly, hexc

SIDES = (("l", 1.0), ("r", -1.0))

# kit colours (jersey A, hoop / trim B, shorts, socks) - the same six kits the game ships (tools/build_assets.py)
KITS = {
    "home":    ("#2846c8", "#fad71e", "#f5f5f5", "#2846c8"),
    "away":    ("#c81428", "#14962a", "#1e1e1e", "#c81428"),
    "gk_home": ("#14aa5a", "#0a5a32", "#141414", "#14aa5a"),
    "gk_away": ("#fa8c14", "#1e1e1e", "#1e1e1e", "#fa8c14"),
    "referee": ("#191919", "#e6c800", "#191919", "#191919"),
    "umpire":  ("#fafafa", "#fafafa", "#fafafa", "#1e1e1e"),
}
SKIN = "#e3b28f"
HAIR = "#3b2614"
EYE = "#5a3a1e"


class Skeleton:
    """joint names + bind-pose world matrices (from a GLB skin, or any source)"""
    def __init__(self, names, world, parents=None):
        self.names = list(names); self.W = {n: np.asarray(w, float) for n, w in zip(names, world)}
        self.parent = dict(parents or {})

    def p(self, n):
        return self.W[n][:3, 3].copy()

    @classmethod
    def from_glb(cls, path):
        from .gltfread import read
        import struct, json
        d = open(path, "rb").read()
        L = struct.unpack("<I", d[12:16])[0]; j = json.loads(d[20:20 + L]); o = 20 + L
        bl = struct.unpack("<I", d[o:o + 4])[0]; buf = d[o + 8:o + 8 + bl]
        sk = j["skins"][0]; a = j["accessors"][sk["inverseBindMatrices"]]; bv = j["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        ibm = np.frombuffer(buf[off:off + a["count"] * 64], np.float32).reshape(-1, 4, 4).transpose(0, 2, 1)
        names = [j["nodes"][i]["name"] for i in sk["joints"]]
        par = {}
        for i, nd in enumerate(j["nodes"]):
            for c in nd.get("children", []):
                par[j["nodes"][c]["name"]] = nd["name"]
        return cls(names, np.linalg.inv(ibm.astype(float)), {n: par.get(n) for n in names})


def frame(axis, front_hint=(0, 0, 1.0)):
    """orthonormal (side, axis, front) for a segment direction; front = hint made perpendicular"""
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    f = np.asarray(front_hint, float); f = f - a * (f @ a)
    if np.linalg.norm(f) < 1e-6:
        f = np.array([0, 1.0, 0]) - a * a[1]
    f /= np.linalg.norm(f)
    s = np.cross(a, f)
    return s, a, f


class Design:
    def __init__(self, sk: Skeleton):
        self.sk = sk; self.b = B()

    # ---- placement helpers (world coords)
    def seg_pt(self, j0, j1, t, side=0.0, front=0.0, hint=(0, 0, 1.0), sgn=1.0):
        A, Bp = self.sk.p(j0), self.sk.p(j1)
        s, a, f = frame(Bp - A, hint)
        return A + (Bp - A) * t + s * side * sgn + f * front

    def cap(self, bone, p0, p1, r0, r1=None, **kw):
        return self.b.cap(bone, tuple(np.asarray(p0, float)), tuple(np.asarray(p1, float)), r0, r1, **kw)

    def ell_seg(self, bone, j0, j1, t, radii, side=0.0, front=0.0, hint=(0, 0, 1.0), sgn=1.0, **kw):
        """ellipsoid on a segment: radii = (side, along, front) in the segment frame"""
        A, Bp = self.sk.p(j0), self.sk.p(j1)
        s, a, f = frame(Bp - A, hint)
        if sgn < 0:
            s = -s
        c = A + (Bp - A) * t + s * side + f * front
        M = np.stack([s, a, f], 1)
        return self.b.prims.append(Prim(bone, "ell", tuple(c), tuple(radii), M=tuple(map(tuple, M)), **kw)) or self.b.prims[-1]

    def ell(self, bone, c, r, M=None, **kw):
        self.b.prims.append(Prim(bone, "ell", tuple(c), tuple(r), M=None if M is None else tuple(map(tuple, np.asarray(M))), **kw))
        return self.b.prims[-1]

    def box(self, bone, c, h, rnd, M=None, **kw):
        self.b.prims.append(Prim(bone, "box", tuple(c), tuple(h), 0.0, rnd, M=None if M is None else tuple(map(tuple, np.asarray(M))), **kw))
        return self.b.prims[-1]


def build(sk: Skeleton, musc=0.8):
    """-> (prims, paints(kit) function).  All shapes in world bind space."""
    D = Design(sk); b = D.b
    K = dict(layer="skin", mat="skin", paint="skin")
    P = sk.p
    zc = 0.03                                  # the body's centre line sits a little in front of the spine joints
    # ---------------- torso (measured to the shipped player's proportions, a touch more athletic)
    b.ell("pelvis", (0, 0.905, 0.02), (0.160, 0.115, 0.108), **K)
    for s in (1, -1):
        b.ell("pelvis", (0.066 * s, 0.868, -0.040), (0.070, 0.080, 0.060), **K)                     # glutes
    b.ell("spine_01", (0, 1.045, zc + 0.008), (0.134, 0.125, 0.094), **K)                          # abdomen / waist
    b.ell("spine_03", (0, 1.265, zc), (0.162, 0.165, 0.112), **K)                                  # ribcage
    for s in (1, -1):
        b.ell("spine_03", (0.072 * s, 1.335, 0.095), (0.080, 0.058, 0.044), M=_rz(-8 * s), **K)     # pecs
        b.ell("spine_03", (0.106 * s, 1.262, -0.012), (0.056, 0.11, 0.062), M=_rz(10 * s), **K)     # lats
        for y in (1.175, 1.115, 1.055):                                                            # abs
            b.ell("spine_02" if y > 1.09 else "spine_01", (0.029 * s, y, 0.112), (0.027, 0.024, 0.016 * (0.6 + 0.6 * musc)), **K)
        b.ell("spine_03", (0.13 * s, 1.415, -0.005), (0.075, 0.035, 0.06), **K)                     # shoulder top
    b.ell("spine_03", (0, 1.425, -0.02), (0.115, 0.05, 0.062), **K)                                # traps
    D.cap("neck_01", (0, 1.44, 0.0), (0, 1.585, 0.035), 0.058, 0.052, **K)
    # ---------------- head: Sprite Forge's sculpted head, placed so the eyes match the shipped player's (y 1.635)
    hb = B(); _forge_body(hb, g=1.0, musc=musc, hs=1.0)
    O = np.array([0.0, 1.525, 0.052])
    for p in hb.prims:
        if p.bone != "head":
            continue
        q = Prim("head", p.kind, tuple(np.asarray(p.a) + O) if p.kind != "cap" or True else p.a,
                 tuple(np.asarray(p.b) + O) if p.kind == "cap" else p.b, p.ra, p.rb, p.rot, p.mat, p.layer, "face", p.grow,
                 p.cuts, p.sub, False, None)
        if p.cuts:
            q.cuts = tuple((n, off + float(np.asarray(n) @ O / np.linalg.norm(n))) for n, off in p.cuts)
        if p.kind == "cap" and p.a[2] > 0.08:                     # nose: shorter, finer bridge (a real face, not a fighter)
            q.a = tuple(np.asarray(p.a) * [1, 1, 0.97] + O); q.b = tuple(np.asarray(p.b) * [1, 1.01, 0.93] + O)
            q.ra, q.rb = 0.0075, 0.012
        if p.kind == "box":                                      # jaw: rounder corners, a little narrower
            q.b = (p.b[0] * 0.92, p.b[1], p.b[2] * 0.95); q.rb = 0.032
        b.prims.append(q)
    # ---------------- arms
    for side, s in SIDES:
        ua, la, hd = "upperarm_" + side, "lowerarm_" + side, "hand_" + side
        D.ell_seg(ua, ua, la, 0.06, (0.070, 0.085, 0.072), side=0.012, sgn=s, **K)                 # deltoid
        D.cap(ua, P(ua), P(la), 0.050, 0.040, **K)
        D.ell_seg(ua, ua, la, 0.50, (0.040, 0.085, 0.042 * (0.8 + 0.4 * musc)), front=0.020, **K)   # biceps
        D.ell_seg(ua, ua, la, 0.45, (0.043, 0.095, 0.040), front=-0.024, **K)                       # triceps
        hint = np.cross(P(la) - P(ua), P(hd) - P(la)) * s                                          # elbow hinge
        fh = np.cross(hint, P(hd) - P(la))
        D.cap(la, P(la), P(hd), 0.043, 0.029, **K)
        D.ell_seg(la, la, hd, 0.28, (0.046 * (0.85 + 0.2 * musc), 0.085, 0.040), front=0.004, hint=fh, **K)
        # hand: palm block from the wrist to the knuckles, fingers along their own joints
        m1 = P("middle_01_" + side); i1 = P("index_01_" + side); p1 = P("pinky_01_" + side)
        ax = m1 - P(hd); width = i1 - p1
        f = np.cross(width, ax) * s; f /= np.linalg.norm(f)
        a = ax / np.linalg.norm(ax); w = np.cross(a, f)
        M = np.stack([w, a, f], 1)
        b.prims.append(Prim(hd, "box", tuple(P(hd) + ax * 0.55), (0.038, np.linalg.norm(ax) * 0.62, 0.0155), 0.0, 0.013,
                            M=tuple(map(tuple, M)), **K))
        for fn, r0 in (("index", 0.0095), ("middle", 0.0098), ("ring", 0.0092), ("pinky", 0.0082), ("thumb", 0.0115)):
            pts = [P("%s_0%d_%s" % (fn, k, side)) for k in (1, 2, 3)]
            tip = pts[2] + (pts[2] - pts[1]) * 0.85
            pts.append(tip)
            bones = ["%s_0%d_%s" % (fn, k, side) for k in (1, 2, 3)]
            for k in range(3):
                D.cap(bones[k], pts[k], pts[k + 1], r0 * (1 - 0.08 * k), r0 * (1 - 0.08 * (k + 1)), **K)
    # ---------------- legs
    for side, s in SIDES:
        th, cf, ft, bl = "thigh_" + side, "calf_" + side, "foot_" + side, "ball_" + side
        D.cap(th, P(th) + np.array([0, 0.03, 0]), P(cf), 0.088, 0.056, **K)
        D.ell_seg(th, th, cf, 0.42, (0.064, 0.150, 0.056 * (0.8 + 0.3 * musc)), front=0.026, **K)    # quads
        D.ell_seg(th, th, cf, 0.62, (0.050, 0.12, 0.05), side=0.022, sgn=s, **K)                     # vastus medialis
        D.ell_seg(th, th, cf, 0.40, (0.060, 0.15, 0.05), front=-0.024, **K)                          # hamstrings
        D.cap(cf, P(cf), P(ft), 0.052, 0.033, **K)
        D.ell_seg(cf, cf, ft, 0.30, (0.050, 0.11, 0.050 * (0.85 + 0.3 * musc)), front=-0.030, **K)   # calf
        D.ell_seg(cf, cf, ft, 0.0, (0.042, 0.035, 0.03), front=0.022, **K)                          # knee
        # foot: heel to toes along foot -> ball
        heel = P(ft) + np.array([0, -0.04, -0.045]); toe = P(bl) + (P(bl) - P(ft)) * np.array([0.1, 0, 0.55])
        toe[1] = 0.025
        a = toe - heel; L = np.linalg.norm(a); a /= L
        f = np.array([0, 1.0, 0]) - a * a[1]; f /= np.linalg.norm(f); w = np.cross(a, f)
        M = np.stack([w, f, a], 1)
        b.prims.append(Prim(ft, "box", tuple((heel + toe) / 2 + f * 0.0), (0.046, 0.032, L / 2), 0.0, 0.028,
                            M=tuple(map(tuple, M)), **K))
        D.cap(ft, P(ft), heel + np.array([0, 0.02, 0.02]), 0.040, 0.034, **K)
    # ======================= clothing (one surface with the body: each layer is a union, layers meet with a crease)
    G = dict(layer="jersey", mat="cloth", paint="jersey")
    # the jersey covers every torso muscle (grown copies) and drapes over the dips between them: hull shapes plus a
    # wide blend radius for the jersey layer (gamemesh.LAYER_K) bridge the grooves instead of shrink-wrapping each one
    for p in list(b.prims):
        # only the big front forms (ribcage, pecs, abdomen volume); lats, abs and glutes are covered by the hull
        if p.layer == "skin" and p.bone in ("pelvis", "spine_01", "spine_03") and p.kind != "cap" and p.a[1] > 0.84 \
                and (abs(p.a[0]) < 0.09) and p.a[2] > -0.03 and max(p.b) > 0.05:
            b.prims.append(Prim(p.bone, p.kind, p.a, p.b, p.ra, p.rb, p.rot, "cloth", "jersey", "jersey", p.grow + 0.011,
                                (((0, -1, 0), -0.865),), M=p.M))
    b.ell("pelvis", (0, 0.925, 0.02), (0.172, 0.10, 0.125), cuts=(((0, -1, 0), -0.865),), **G)
    b.ell("spine_01", (0, 1.06, zc + 0.004), (0.152, 0.14, 0.118), **G)
    b.ell("spine_03", (0, 1.27, zc + 0.0), (0.190, 0.178, 0.138), **G)
    b.ell("spine_03", (0, 1.40, -0.006), (0.185, 0.052, 0.088), **G)                                # shoulder yoke
    for side, s in SIDES:                                                                          # short sleeves
        ua, la = "upperarm_" + side, "lowerarm_" + side
        A, Bp = P(ua), P(la); ax = (Bp - A) / np.linalg.norm(Bp - A)
        cut = float(ax @ (A + (Bp - A) * 0.50))
        D.cap(ua, A - ax * 0.02, A + (Bp - A) * 0.55, 0.062, 0.055, cuts=((tuple(ax), cut),), **G)
        D.ell_seg(ua, ua, la, 0.10, (0.068, 0.08, 0.07), side=0.006, sgn=s, cuts=((tuple(ax), cut),), **G)
    b.ell("neck_01", (0, 1.455, 0.012), (0.080, 0.022, 0.074), **G)             # collar band
    S = dict(layer="shorts", mat="cloth", paint="shorts")
    b.ell("pelvis", (0, 0.895, 0.004), (0.176, 0.13, 0.130), cuts=(((0, 1, 0), 0.98),), **S)        # one rounded seat
    for side, s in SIDES:
        th, cf = "thigh_" + side, "calf_" + side
        A, Bp = P(th), P(cf); ax = (Bp - A) / np.linalg.norm(Bp - A)
        hem = A + (Bp - A) * 0.36
        D.cap(th, A + np.array([0.010 * s, 0.03, 0]), hem, 0.098, 0.092, cuts=((tuple(ax), float(ax @ hem)),), **S)
    SO = dict(layer="socks", mat="cloth", paint="socks")
    for side, s in SIDES:
        cf, ft = "calf_" + side, "foot_" + side
        A, Bp = P(cf), P(ft); ax = (Bp - A) / np.linalg.norm(Bp - A)
        top = A + (Bp - A) * 0.16
        D.cap(cf, top, Bp, 0.056, 0.036, cuts=(((-ax[0], -ax[1], -ax[2]), float(-ax @ top)),), **SO)
        D.ell_seg(cf, cf, ft, 0.32, (0.054, 0.10, 0.054), front=-0.028, cuts=(((-ax[0], -ax[1], -ax[2]), float(-ax @ top)),), **SO)
    BT = dict(layer="boots", mat="leather", paint="boots")
    for p in [q for q in b.prims if q.layer == "skin" and q.bone.startswith("foot_")]:
        b.prims.append(Prim(p.bone, p.kind, p.a, p.b, p.ra, p.rb, p.rot, "leather", "boots", "boots", p.grow + 0.010, (), M=p.M))
    for side, s in SIDES:                                                                           # sole
        ft, bl = "foot_" + side, "ball_" + side
        heel = P(ft) + np.array([0, -0.06, -0.05]); toe = P(bl) + np.array([0, 0, 0.075])
        b.box(ft, ((heel[0] + toe[0]) / 2, 0.009, (heel[2] + toe[2]) / 2), (0.050, 0.009, (toe[2] - heel[2]) / 2 + 0.01), 0.008,
              layer="boots", mat="leather", paint="boots")
    HR = dict(layer="hair", mat="hair", paint="hair")
    hl = -0.915 / math.hypot(0.62, 1.0)                     # hairline plane z - 0.62 y <= -0.915 (forehead / temples)
    nape = np.array([0, -1.0, 0.35]) / math.hypot(1.0, 0.35)                 # back / sides: down to the nape, above the ears
    b.ell("head", (0, 1.645, 0.036), (0.092, 0.104, 0.105),
          cuts=(((0, -0.62, 1), hl), (tuple(nape), float(nape @ np.array([0, 1.572, -0.04])))), **HR)
    b.ell("head", (0, 1.712, 0.050), (0.078, 0.036, 0.086), **HR)                                   # volume on top
    return b.prims, paints


def _rz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def paints(kit="home", skin=SKIN, hair=HAIR, eye=EYE):
    """paint functions in world bind coords for one kit"""
    A, Bc, Sh, So = (hexc(c) for c in KITS[kit])
    skin = hexc(skin); hairc = hexc(hair); eyec = hexc(eye)
    face_fn = face_paint(skin, eyec, hairc * 1.25, scowl=0.1, stubble=np.array([0.90, 0.85, 0.83]),
                         lips_rgb=skin * np.array([0.88, 0.66, 0.62]))
    O = np.array([0.0, 1.525, 0.052])
    boot = np.array([0.07, 0.07, 0.08]); boot_trim = np.array([0.92, 0.92, 0.94]); sole = np.array([0.16, 0.16, 0.17])

    def mottle(P):
        n = np.sin(P[:, 0] * 173 + P[:, 1] * 91) * np.sin(P[:, 1] * 157 - P[:, 2] * 211) + 0.5 * np.sin(P[:, 2] * 401 + P[:, 0] * 333)
        return 1.0 + 0.035 * n

    def skin_fn(P, base):
        col = np.broadcast_to(skin, base.shape) * mottle(P)[:, None]
        # knuckle / joint warmth, slightly darker forearm hair tone
        return col, np.zeros(len(P))

    def face(P, base):
        c, e = face_fn(P - O, base)
        return c * mottle(P)[:, None], e

    def jersey_fn(P, base):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        col = np.broadcast_to(A, base.shape).copy()
        ax = np.abs(x)
        col[(y > 1.17) & (y < 1.27) & (ax < 0.30)] = Bc                                    # hoop, chest and back
        col[(ax > 0.215) & (np.abs(_arm_t(P) - 0.50) < 0.035)] = Bc                        # sleeve cuffs
        col[(y > 1.435) & (y < 1.49) & (ax < 0.088) & ((z > 0.0) | (y > 1.45))] = Bc     # collar
        col = mix(col, Bc, ellmask(x, y, 0.085, 1.33, 0.022, 0.026, 0.12) * (z > 0.08))     # crest
        col[(y < 0.885) & (ax < 0.30)] = A * 0.93                                           # hem
        return col, np.zeros(len(P))

    def shorts_fn(P, base):
        y = P[:, 1]
        col = np.broadcast_to(Sh, base.shape).copy()
        col[np.abs(y - 0.735 - 0.08 * np.abs(P[:, 0])) < 0.006] = A                         # piping above the hem
        return col, np.zeros(len(P))

    def socks_fn(P, base):
        y = P[:, 1]
        col = np.broadcast_to(So, base.shape).copy()
        col[((y > 0.41) & (y < 0.425)) | ((y > 0.385) & (y < 0.40))] = Bc                  # two hoops
        col[y > 0.445] = So * 0.85                                                          # turned-down top
        return col, np.zeros(len(P))

    def boots_fn(P, base):
        y, z = P[:, 1], P[:, 2]
        col = np.broadcast_to(boot, base.shape).copy()
        col[(np.abs(y - 0.06 + 0.2 * (z - 0.05)) < 0.006) & (z > -0.02)] = boot_trim       # side stripe
        col[y < 0.018] = sole
        return col, np.zeros(len(P))

    def hair_fn(P, base):
        y = P[:, 1]
        n = np.sin(P[:, 0] * 900 + P[:, 2] * 610) * np.sin(y * 700 + P[:, 0] * 330)
        k = 0.92 + 0.10 * n + 0.08 * np.clip((y - 1.66) / 0.08, 0, 1)
        return hairc * k[:, None], np.zeros(len(P))

    def coat(fn):                       # umpires wear a long white coat over the kit (painted: one mesh for all kits)
        def f(P, base):
            col, em = fn(P, base)
            col[(P[:, 1] > 0.50) & (P[:, 1] < 1.47)] = np.array([0.97, 0.97, 0.96])
            return col, em
        return f

    g = {"jersey": jersey_fn, "shorts": shorts_fn, "socks": socks_fn, "boots": boots_fn}
    if kit == "umpire":
        g = {k: (coat(v) if k in ("jersey", "shorts") else v) for k, v in g.items()}
    out = {"skin": Paint(None, skin_fn), "face": Paint(None, face), "hair": Paint(None, hair_fn)}
    out.update({k: Paint(None, v) for k, v in g.items()})
    return out


_SK = {}


def _arm_t(P):
    """fraction along the nearest upper arm (for sleeve cuffs); uses the skeleton registered by build()"""
    sk = _SK.get("sk")
    if sk is None:
        return np.zeros(len(P))
    out = np.full(len(P), -1.0)
    for side, s in SIDES:
        A, Bp = sk.p("upperarm_" + side), sk.p("lowerarm_" + side)
        ab = Bp - A; t = ((P - A) @ ab) / (ab @ ab)
        m = (P[:, 0] * s > 0)
        out[m] = t[m]
    return out


def design(sk: Skeleton, kit="home"):
    _SK["sk"] = sk
    prims, pf = build(sk)
    return prims, pf(kit)
