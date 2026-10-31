#!/usr/bin/env python3
"""Procedural hurling assets: a rigged hurler + hurley (glb), a sliotar (glb), and hurling motions.

    python3 gen_hurling_assets.py OUTDIR            # writes hurler_home.glb, hurler_away.glb, sliotar.glb, clips.json
    python3 gen_hurling_assets.py OUTDIR --sheet    # also writes contact sheets (clip_*.png) for eyeballing

Y up, metres, character faces +Z, "L" is the +X side. 18-joint skeleton, bind pose = A-pose with every
local rotation identity, so an animation key is simply a delta rotation. The hurley is skinned to its own
joint (child of the right hand). In two-handed clips the left hand is solved onto the handle with 2-bone IK
at bake time, so the grip stays on the stick through a swing. Output is plain glTF 2.0: vertex colours
(no textures), JOINTS_0 as ubyte, 30 fps LINEAR rotation channels (+ hips translation).
"""
import json, math, struct, sys, os
import numpy as np

FPS = 30

# ---------------------------------------------------------------- skeleton
# name, parent, bind world position
BONES = [
    ("hips", None, (0, 0.95, 0)),
    ("spine", "hips", (0, 1.08, 0)),
    ("chest", "spine", (0, 1.25, 0)),
    ("neck", "chest", (0, 1.48, 0)),
    ("head", "neck", (0, 1.55, 0)),
]
ARM_DIR = {"L": np.array([math.sin(math.radians(18)), -math.cos(math.radians(18)), 0.0]),
           "R": np.array([-math.sin(math.radians(18)), -math.cos(math.radians(18)), 0.0])}
for s, sx in (("L", 1.0), ("R", -1.0)):
    sh = np.array([0.21 * sx, 1.40, 0.0]); d = ARM_DIR[s]
    el = sh + d * 0.29; wr = el + d * 0.26
    BONES += [(s + "_arm", "chest", tuple(sh)), (s + "_fore", s + "_arm", tuple(el)), (s + "_hand", s + "_fore", tuple(wr))]
    BONES += [(s + "_thigh", "hips", (0.09 * sx, 0.92, 0.0)), (s + "_shin", s + "_thigh", (0.09 * sx, 0.50, 0.0)),
              (s + "_foot", s + "_shin", (0.09 * sx, 0.08, 0.0))]
IDX_R_HAND = [b[0] for b in BONES].index("R_hand")
BONES += [("hurley", "R_hand", tuple(np.array(BONES[IDX_R_HAND][2])))]
NAMES = [b[0] for b in BONES]
IDX = {n: i for i, n in enumerate(NAMES)}
PAR = [IDX[b[1]] if b[1] else -1 for b in BONES]
BIND = np.array([b[2] for b in BONES], dtype=float)
OFF = np.array([BIND[i] - (BIND[PAR[i]] if PAR[i] >= 0 else 0) for i in range(len(BONES))])
HURLEY_D = ARM_DIR["R"]          # handle direction in bind (towards the bas)
HURLEY_TOP, HURLEY_BAS = -0.22, 0.74   # along HURLEY_D from the hand joint (hand is at ~0.55 below... see build)
GRIP_L = 0.30                    # left hand sits this far below the right on the handle

# ---------------------------------------------------------------- math
def rx(a): c, s = math.cos(a), math.sin(a); return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
def ry(a): c, s = math.cos(a), math.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
def rz(a): c, s = math.cos(a), math.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
def euler(e):  # degrees (x, y, z) -> matrix
    return rz(math.radians(e[2])) @ ry(math.radians(e[1])) @ rx(math.radians(e[0]))
def mat2quat(m):
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1) * 2; q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2; q = [s / 4, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2; q = [(m[0, 1] + m[1, 0]) / s, s / 4, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2; q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, s / 4, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q); return q / np.linalg.norm(q)
def unit(v): n = np.linalg.norm(v); return v / n if n > 1e-9 else v
def arc(a, b):  # shortest-arc rotation matrix taking unit a to unit b
    a, b = unit(a), unit(b); v = np.cross(a, b); c = float(np.dot(a, b))
    if c < -0.9999:
        ax = unit(np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0]))
        return 2 * np.outer(ax, ax) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)

def fk(local_rot, hips_pos):
    n = len(NAMES); R = [None] * n; P = np.zeros((n, 3))
    for i in range(n):
        if PAR[i] < 0: R[i] = local_rot[i]; P[i] = hips_pos
        else: R[i] = R[PAR[i]] @ local_rot[i]; P[i] = P[PAR[i]] + R[PAR[i]] @ OFF[i]
    return R, P

# ---------------------------------------------------------------- mesh
class Mesh:
    def __init__(self): self.v = []; self.n = []; self.c = []; self.j = []; self.w = []; self.i = []
    def add_tube(self, p0, p1, prof, color_fn, weight_fn, segs=10, up=None):
        """Elliptical tube p0->p1. prof = [(t, ru, rv)]; u axis is 'up' (default world X), v the other."""
        p0, p1 = np.array(p0, float), np.array(p1, float); ax = p1 - p0; L = np.linalg.norm(ax); a = ax / L
        u = unit(np.cross(a, [0, 0, 1])) if up is None and abs(a[2]) < 0.9 else unit(np.cross(a, up if up is not None else [1, 0, 0]))
        if up is not None: u = unit(np.array(up) - a * np.dot(up, a))
        v = np.cross(a, u); base = len(self.v)
        for t, ru, rv in prof:
            for k in range(segs):
                th = 2 * math.pi * k / segs; d = math.cos(th) * u * ru + math.sin(th) * v * rv
                nn = unit(math.cos(th) * u / max(ru, 1e-4) + math.sin(th) * v / max(rv, 1e-4))
                self.v.append(p0 + a * L * t + d); self.n.append(nn); self.c.append(color_fn(t))
                jw = weight_fn(t); jj = [b for b, _ in jw] + [0] * (4 - len(jw)); ww = [x for _, x in jw] + [0.0] * (4 - len(jw))
                self.j.append(jj); self.w.append(ww)
        for r in range(len(prof) - 1):
            for k in range(segs):
                a0 = base + r * segs + k; a1 = base + r * segs + (k + 1) % segs; b0 = a0 + segs; b1 = a1 + segs
                self.i += [a0, b0, a1, a1, b0, b1]
        # caps (fan to centre)
        for ring, flip in ((0, True), (len(prof) - 1, False)):
            t = prof[ring][0]; ci = len(self.v); cen = p0 + a * L * t
            self.v.append(cen); self.n.append(-a if flip else a); self.c.append(color_fn(t))
            jw = weight_fn(t); self.j.append([b for b, _ in jw] + [0] * (4 - len(jw))); self.w.append([x for _, x in jw] + [0.0] * (4 - len(jw)))
            for k in range(segs):
                a0 = base + ring * segs + k; a1 = base + ring * segs + (k + 1) % segs
                self.i += [ci, a1, a0] if flip else [ci, a0, a1]

def lerp(a, b, t): return a + (b - a) * t

def build_mesh(jersey, shorts, socks, trim):
    m = Mesh(); SKIN = (0.86, 0.66, 0.54); BOOT = (0.08, 0.08, 0.09); WOOD = (0.78, 0.62, 0.38); HELM = trim
    col = lambda c, a=1.0: [c[0], c[1], c[2], a]
    def blend(parent, child, e=0.28):
        def f(t):
            r = []
            if t < e and parent is not None: wp = 0.5 * (1 - t / e); r += [(parent, wp)]; wc = 1 - wp
            else: wc = 1.0
            if t > 1 - e and child is not None: ww = 0.5 * (t - (1 - e)) / e; r += [(child, ww)]; wc -= ww
            return [(NAMES.index(x) if isinstance(x, str) else x, w) for x, w in [(own, wc)] + r] if False else r + [(None, wc)]
        return f
    def W(own, parent, child, e=0.28):
        oi, pi, ci = IDX[own], (IDX[parent] if parent else None), (IDX[child] if child else None)
        def f(t):
            out = []; wc = 1.0
            if pi is not None and t < e: wp = 0.5 * (1 - t / e); out.append((pi, wp)); wc -= wp
            if ci is not None and t > 1 - e: wn = 0.5 * (t - (1 - e)) / e; out.append((ci, wn)); wc -= wn
            return [(oi, wc)] + out
        return f
    B = lambda n: BIND[IDX[n]]
    def ell(rs, n=6):  # smooth profile rs=[(t, ru, rv)...] resampled
        return rs
    # torso
    m.add_tube(B("hips") + [0, -0.05, 0], B("spine"), [(0, .16, .105), (.5, .17, .11), (1, .16, .10)], lambda t: col(shorts if t < .6 else jersey), W("hips", None, "spine"), 12, up=[1, 0, 0])
    m.add_tube(B("spine"), B("chest"), [(0, .16, .10), (1, .17, .105)], lambda t: col(jersey), W("spine", "hips", "chest"), 12, up=[1, 0, 0])
    m.add_tube(B("chest"), B("neck"), [(0, .17, .105), (.5, .20, .115), (.9, .20, .105), (1, .07, .06)], lambda t: col(jersey), W("chest", "spine", "neck"), 12, up=[1, 0, 0])
    m.add_tube(B("neck") + [0, -.02, 0], B("head") + [0, .01, 0], [(0, .05, .05), (1, .048, .048)], lambda t: col(SKIN), W("neck", "chest", "head", .4), 8, up=[1, 0, 0])
    # head: ellipsoid + helmet + faceguard bars
    hp = B("head") + [0, 0.02, 0.0]; top = hp + [0, 0.20, 0]
    prof = [(t, 0.095 * math.sqrt(max(0, 1 - (2 * t - 1) ** 2)) + 0.012, 0.11 * math.sqrt(max(0, 1 - (2 * t - 1) ** 2)) + 0.012) for t in np.linspace(0, 1, 9)]
    m.add_tube(hp - [0, 0.0, 0], top, prof, lambda t: col(HELM if t > .55 else SKIN), lambda t: [(IDX["head"], 1.0)], 12, up=[1, 0, 0])
    for yy in (0.08, 0.12, 0.16):  # faceguard horizontal bars (steel)
        m.add_tube(hp + [-0.08, yy - 0.04, 0.095], hp + [0.08, yy - 0.04, 0.095], [(0, .006, .006), (1, .006, .006)], lambda t: col((0.7, 0.7, 0.72)), lambda t: [(IDX["head"], 1.0)], 5)
    for xx in (-0.045, 0.0, 0.045):
        m.add_tube(hp + [xx, 0.05, 0.10], hp + [xx, 0.16, 0.10], [(0, .005, .005), (1, .005, .005)], lambda t: col((0.7, 0.7, 0.72)), lambda t: [(IDX["head"], 1.0)], 5)
    # arms: short sleeves on upper arm
    for s in "LR":
        ar, fo, ha = B(s + "_arm"), B(s + "_fore"), B(s + "_hand")
        m.add_tube(ar - ARM_DIR[s] * 0.03, fo, [(0, .062, .062), (.6, .055, .055), (1, .045, .045)], lambda t: col(jersey if t < .55 else SKIN), W(s + "_arm", "chest", s + "_fore"), 9, up=[0, 0, 1])
        m.add_tube(fo, ha, [(0, .045, .045), (1, .032, .032)], lambda t: col(SKIN), W(s + "_fore", s + "_arm", s + "_hand"), 9, up=[0, 0, 1])
        m.add_tube(ha, ha + ARM_DIR[s] * 0.10, [(0, .032, .03), (.5, .04, .022), (1, .02, .015)], lambda t: col((0.9, 0.85, 0.2) if False else (0.15, 0.15, 0.16)), lambda t: [(IDX[s + "_hand"], 1.0)], 8, up=[0, 0, 1])  # glove
        th, sn, ft = B(s + "_thigh"), B(s + "_shin"), B(s + "_foot")
        m.add_tube(th + [0, .03, 0], sn, [(0, .085, .085), (.5, .075, .075), (1, .055, .055)], lambda t: col(shorts if t < .45 else SKIN), W(s + "_thigh", "hips", s + "_shin"), 9, up=[0, 0, 1])
        m.add_tube(sn, ft + [0, .03, 0], [(0, .055, .055), (.5, .05, .05), (1, .04, .04)], lambda t: col(socks if t > .15 else SKIN), W(s + "_shin", s + "_thigh", s + "_foot"), 9, up=[0, 0, 1])
        m.add_tube(ft + [0, 0.02, -0.06], ft + [0, 0.0, 0.2], [(0, .042, .05), (.6, .045, .04), (1, .035, .02)], lambda t: col(BOOT), lambda t: [(IDX[s + "_foot"], 1.0)], 8, up=[1, 0, 0])
    # hurley (handle + bas), bound rigidly to the hurley joint
    h0 = B("hurley"); d = HURLEY_D
    m.add_tube(h0 + d * HURLEY_TOP, h0 + d * 0.58, [(0, .018, .018), (1, .016, .016)], lambda t: col(WOOD), lambda t: [(IDX["hurley"], 1.0)], 7, up=[0, 0, 1])
    m.add_tube(h0 + d * 0.56, h0 + d * HURLEY_BAS, [(0, .017, .015), (.4, .05, .011), (1, .062, .011)], lambda t: col(WOOD), lambda t: [(IDX["hurley"], 1.0)], 8, up=[0, 0, 1])
    m.add_tube(h0 + d * (HURLEY_TOP + .08), h0 + d * (HURLEY_TOP + .24), [(0, .021, .021), (1, .021, .021)], lambda t: col((0.1, 0.1, 0.1)), lambda t: [(IDX["hurley"], 1.0)], 7, up=[0, 0, 1])  # grip tape
    return m

# ---------------------------------------------------------------- glTF writer
class Glb:
    def __init__(self): self.bin = bytearray(); self.bv = []; self.acc = []
    def _pad(self):
        while len(self.bin) % 4: self.bin.append(0)
    def add(self, arr, ctype, typ, target=None, minmax=False):
        self._pad(); off = len(self.bin); b = arr.tobytes(); self.bin += b
        self.bv.append({"buffer": 0, "byteOffset": off, "byteLength": len(b), **({"target": target} if target else {})})
        a = {"bufferView": len(self.bv) - 1, "componentType": ctype, "count": int(arr.shape[0]), "type": typ}
        if minmax: a["min"] = arr.min(axis=0).tolist(); a["max"] = arr.max(axis=0).tolist()
        self.acc.append(a); return len(self.acc) - 1
    def write(self, path, doc):
        self._pad(); doc["buffers"] = [{"byteLength": len(self.bin)}]; doc["bufferViews"] = self.bv; doc["accessors"] = self.acc
        js = json.dumps(doc, separators=(",", ":")).encode()
        while len(js) % 4: js += b" "
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total)); f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
            f.write(struct.pack("<II", len(self.bin), 0x004E4942)); f.write(self.bin)

# ---------------------------------------------------------------- animation
def smooth(t): return t * t * (3 - 2 * t)

class Keys:
    """Key poses: {joint: (x,y,z deg)} plus hips offset 'T' (metres). Interpolated with smoothstep between keys."""
    def __init__(self, keys, loop=False): self.keys = sorted(keys, key=lambda k: k[0]); self.loop = loop
    def at(self, t):
        ks = self.keys
        if t <= ks[0][0]: return ks[0][1]
        if t >= ks[-1][0]: return ks[-1][1]
        for a, b in zip(ks, ks[1:]):
            if a[0] <= t <= b[0]:
                u = smooth((t - a[0]) / max(b[0] - a[0], 1e-6)); out = {}
                for j in set(a[1]) | set(b[1]):
                    va = np.array(a[1].get(j, (0, 0, 0)), float); vb = np.array(b[1].get(j, (0, 0, 0)), float); out[j] = va + (vb - va) * u
                return out

def P(**kw): return {k: v for k, v in kw.items()}

def two_hand_ik(R, Pos, pole_side):
    """Solve L_arm/L_fore so the left hand lands on the handle GRIP_L below the right hand."""
    hi = IDX["hurley"]; target = Pos[IDX["R_hand"]] + R[hi] @ (HURLEY_D * GRIP_L)
    # hand joint sits at the end of the forearm; handle surface is at the hurley axis
    sh = Pos[IDX["L_arm"]]; l1 = np.linalg.norm(OFF[IDX["L_fore"]]); l2 = np.linalg.norm(OFF[IDX["L_hand"]])
    dv = target - sh; d = np.linalg.norm(dv); d = min(max(d, abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3); u = unit(dv)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d); h = math.sqrt(max(l1 * l1 - a * a, 1e-6))
    pole = np.array([0.55 * pole_side, -0.6, -0.5]); pv = unit(pole - u * np.dot(pole, u))
    el = sh + u * a + pv * h; wr = sh + u * d
    d1 = unit(el - sh); d2 = unit(wr - el)
    Ru = arc(ARM_DIR["L"], d1); Rf = arc(ARM_DIR["L"], d2)
    return Ru, Rf

def sample_clip(name, spec, nframes):
    """Return per-frame (local rotations list[matrix], hips position)."""
    frames = []; keys = spec["keys"]; dur = spec["dur"]
    for f in range(nframes):
        t = f / FPS; ph = (t / dur) if spec.get("loop") else min(t / dur, 1.0)
        pose = keys(ph, t) if callable(keys) else keys.at(ph)
        loc = [np.eye(3) for _ in NAMES]
        hp = BIND[0] + np.array(pose.get("T", (0, 0, 0)), float)
        for j, e in pose.items():
            if j == "T": continue
            loc[IDX[j]] = euler(e)
        if spec.get("ik"):
            Rw, Pw = fk(loc, hp)
            Ru, Rf = two_hand_ik(Rw, Pw, 1.0)
            pa = Rw[PAR[IDX["L_arm"]]]
            loc[IDX["L_arm"]] = pa.T @ Ru; loc[IDX["L_fore"]] = Ru.T @ Rf
        frames.append((loc, hp))
    return frames

def limb(pitch, bend=0):  # helper: forward pitch (deg) for a hanging limb -> rotation about X (negated)
    return (-pitch, 0, 0)

def run_cycle(speed, carry):
    """speed 0..1 scales stride; carry=True holds the hurley low in the right hand with a small cradle."""
    def f(ph, t):
        a = ph * 2 * math.pi; amp = 28 + 24 * speed; lean = 6 + 14 * speed; kn = 40 + 55 * speed
        sL, sR = math.sin(a), math.sin(a + math.pi)
        def knee(s, c): return max(0.0, math.cos(c)) * kn + 8
        pose = P(
            T=(0, -0.02 - 0.03 * speed + 0.035 * abs(math.cos(a)) * (0.6 + speed), 0),
            hips=(lean * 0.4, 5 * sL, 0), spine=(lean * 0.4, -8 * sL, 0), chest=(lean * 0.5, -4 * sL, 0), neck=(-lean * .6, 0, 0),
            L_thigh=(-amp * sL, 0, 0), R_thigh=(-amp * sR, 0, 0),
            L_shin=(knee(sL, a + 0.9) if True else 0, 0, 0), R_shin=(knee(sR, a + math.pi + 0.9), 0, 0),
            L_foot=(max(0, -10 * math.cos(a)), 0, 0), R_foot=(max(0, -10 * math.cos(a + math.pi)), 0, 0),
            L_arm=(-(45 + 25 * speed) * sR * 0.9, 0, -6), L_fore=(-(70 + 25 * speed), 0, 0),
            R_arm=(-(8 + 8 * speed) + (-14 * sR if not carry else -4 * sR), 0, 10), R_fore=(-(35 + 15 * speed), 0, 0),
            R_hand=(10, 0, 0))
        return pose
    return f

def clips():
    C = {}
    stance = lambda T=(0, -0.03, 0): P(T=T, hips=(4, 0, 0), spine=(8, 0, 0), chest=(6, 0, 0), neck=(-8, 0, 0),
                                       L_thigh=(-10, 0, 3), R_thigh=(-6, 0, -3), L_shin=(18, 0, 0), R_shin=(14, 0, 0),
                                       R_arm=(-10, 0, 10), R_fore=(-35, 0, 0), R_hand=(10, 0, 0))
    C["idle"] = dict(dur=2.4, loop=True, ik=True, keys=Keys([
        (0, {**stance(), }), (0.5, {**stance((0, -0.04, 0)), "chest": (8, 3, 0), "head": (2, -3, 0)}),
        (1, {**stance()})], True))
    C["jog"] = dict(dur=0.86, loop=True, keys=run_cycle(0.35, True))
    C["sprint"] = dict(dur=0.62, loop=True, keys=run_cycle(1.0, True))
    # solo run: hurley held out front with the sliotar balanced on the bas (game attaches the ball to 'hurley')
    def solo(ph, t):
        p = run_cycle(0.55, True)(ph, t); a = ph * 2 * math.pi
        p["R_arm"] = (-62, -8, 6 + 3 * math.sin(a * 2)); p["R_fore"] = (-35, 0, 0); p["R_hand"] = (-18 + 4 * math.sin(a * 2), 0, 0)
        return p
    C["solo_run"] = dict(dur=0.74, loop=True, ik=True, keys=solo)
    # overhead strike (a "pull"): ball released from the left hand/bas, hurley winds back over the shoulder then drives through
    wind = P(T=(0, -0.05, -0.04), hips=(0, -25, 0), spine=(-8, -35, 0), chest=(-6, -30, 0), neck=(-4, 12, 0), head=(0, 18, 0),
             L_thigh=(18, 0, 4), R_thigh=(-34, 0, -3), L_shin=(38, 0, 0), R_shin=(22, 0, 0),
             R_arm=(-170, -20, 38), R_fore=(-95, 0, 0), R_hand=(25, 0, 0))
    hit = P(T=(0, -0.06, 0.12), hips=(8, 32, 0), spine=(14, 48, 0), chest=(10, 36, 0), neck=(-6, -30, 0), head=(0, -34, 0),
            L_thigh=(-38, 0, 3), R_thigh=(10, 0, -3), L_shin=(20, 0, 0), R_shin=(35, 0, 0),
            R_arm=(-85, 38, 4), R_fore=(-10, 0, 0), R_hand=(-35, 0, 0))
    follow = P(T=(0, -0.02, 0.2), hips=(6, 55, 0), spine=(8, 62, 0), chest=(4, 45, 0), neck=(0, -44, 0), head=(0, -45, 0),
               L_thigh=(-18, 0, 3), R_thigh=(26, 0, -3), L_shin=(26, 0, 0), R_shin=(40, 0, 0),
               R_arm=(-15, 82, 12), R_fore=(-42, 0, 0), R_hand=(-20, 0, 0))
    C["strike_overhead"] = dict(dur=1.2, ik=True, contact=0.50, keys=Keys([(0, stance()), (0.22, wind), (0.44, wind), (0.50, hit), (0.7, follow), (1.0, stance())]))
    # ground stroke: low sweep through the ball on the turf
    gw = P(T=(0, -0.20, -0.02), hips=(22, -18, 0), spine=(30, -26, 0), chest=(14, -18, 0), neck=(-24, 8, 0), head=(0, 14, 0),
           L_thigh=(-46, 0, 6), R_thigh=(12, 0, -8), L_shin=(60, 0, 0), R_shin=(40, 0, 0),
           R_arm=(-40, -34, 32), R_fore=(-35, 0, 0), R_hand=(20, 0, 0))
    gh = P(T=(0, -0.22, 0.10), hips=(24, 20, 0), spine=(34, 34, 0), chest=(16, 24, 0), neck=(-26, -22, 0), head=(0, -24, 0),
           L_thigh=(-52, 0, 6), R_thigh=(8, 0, -8), L_shin=(66, 0, 0), R_shin=(48, 0, 0),
           R_arm=(-28, 20, 12), R_fore=(-18, 0, 0), R_hand=(-10, 0, 0))
    gf = P(T=(0, -0.12, 0.16), hips=(14, 48, 0), spine=(20, 56, 0), chest=(8, 40, 0), neck=(-14, -40, 0), head=(0, -40, 0),
           L_thigh=(-28, 0, 4), R_thigh=(22, 0, -6), L_shin=(40, 0, 0), R_shin=(52, 0, 0),
           R_arm=(-60, 62, 10), R_fore=(-30, 0, 0), R_hand=(-30, 0, 0))
    C["strike_ground"] = dict(dur=0.9, ik=True, contact=0.38, keys=Keys([(0, stance()), (0.30, gw), (0.38, gh), (0.58, gf), (1.0, stance())]))
    # puck-out (keeper): ball dropped from the left hand then struck on the half-volley
    pw = P(T=(0, -0.05, -0.06), hips=(0, -20, 0), spine=(-10, -30, 0), chest=(-8, -22, 0), neck=(-4, 8, 0),
           L_thigh=(14, 0, 4), R_thigh=(-26, 0, -3), L_shin=(30, 0, 0), R_shin=(18, 0, 0),
           R_arm=(-150, -16, 30), R_fore=(-80, 0, 0), R_hand=(20, 0, 0))
    ph_ = P(T=(0, -0.06, 0.14), hips=(6, 34, 0), spine=(10, 50, 0), chest=(8, 38, 0), neck=(-6, -32, 0), head=(0, -34, 0),
            L_thigh=(-34, 0, 3), R_thigh=(12, 0, -3), L_shin=(22, 0, 0), R_shin=(34, 0, 0),
            R_arm=(-70, 42, 4), R_fore=(-12, 0, 0), R_hand=(-30, 0, 0))
    C["puckout"] = dict(dur=1.7, ik=True, contact=0.78, keys=Keys([(0, stance()), (0.30, pw), (0.62, pw), (0.78, ph_), (0.92, follow), (1.0, stance())]))
    # ground pickup by "rolling lift": hurley under the ball, flick it into the left hand
    pk0 = P(T=(0, -0.28, 0.04), hips=(30, 10, 0), spine=(36, 16, 0), chest=(18, 10, 0), neck=(-30, -6, 0),
            L_thigh=(-60, 0, 6), R_thigh=(20, 0, -6), L_shin=(78, 0, 0), R_shin=(60, 0, 0),
            R_arm=(-48, 6, 16), R_fore=(-10, 0, 0), R_hand=(-8, 0, 0))
    pk1 = P(T=(0, -0.18, 0.08), hips=(20, 4, 0), spine=(26, 10, 0), chest=(10, 6, 0), neck=(-20, -4, 0),
            L_thigh=(-44, 0, 6), R_thigh=(14, 0, -6), L_shin=(60, 0, 0), R_shin=(48, 0, 0),
            R_arm=(-70, 4, 12), R_fore=(-28, 0, 0), R_hand=(20, 0, 0))
    C["pickup_flick"] = dict(dur=1.0, ik=True, contact=0.40, keys=Keys([(0, stance()), (0.28, pk0), (0.40, pk1), (0.65, stance((0, -0.06, 0))), (1.0, stance())]))
    # hand pass (palm strike of the ball, hurley held in the right hand): left hand strikes the ball
    def handpass(ph, t):
        s = stance(); k = Keys([(0, s), (0.3, P(T=(0, -0.05, 0), hips=(0, -14, 0), spine=(-4, -22, 0), chest=(-4, -14, 0),
                                              L_arm=(-70, -6, -10), L_fore=(-100, 0, 0), L_hand=(0, 0, 0),
                                              R_arm=(-30, 0, 8), R_fore=(-65, 0, 0), L_thigh=(14, 0, 4), R_thigh=(-24, 0, -3), L_shin=(28, 0, 0), R_shin=(20, 0, 0)))
                              , (0.45, P(T=(0, -0.05, 0.1), hips=(4, 20, 0), spine=(8, 30, 0), chest=(6, 20, 0),
                                         L_arm=(-92, 12, -4), L_fore=(-12, 0, 0), L_hand=(-20, 0, 0),
                                         R_arm=(-30, 0, 8), R_fore=(-65, 0, 0), L_thigh=(-30, 0, 4), R_thigh=(8, 0, -3), L_shin=(22, 0, 0), R_shin=(30, 0, 0)))
                              , (1.0, s)])
        return k.at(ph)
    C["handpass"] = dict(dur=0.8, contact=0.45, keys=handpass)
    # high catch: jump, left hand (or both) up for the sliotar, hurley trailing
    c0 = P(T=(0, -0.06, 0), spine=(4, 0, 0), L_thigh=(-10, 0, 3), R_thigh=(-6, 0, -3), L_shin=(22, 0, 0), R_shin=(18, 0, 0), L_arm=(-30, 0, -10), L_fore=(-40, 0, 0),
           R_arm=(-10, 0, 10), R_fore=(-35, 0, 0), R_hand=(10, 0, 0))
    c1 = P(T=(0, 0.34, 0), hips=(-4, 0, 0), spine=(-8, 0, 0), chest=(-6, 0, 0), neck=(10, 0, 0), L_thigh=(-34, 0, 3), R_thigh=(6, 0, -3), L_shin=(60, 0, 0), R_shin=(70, 0, 0),
           L_arm=(-176, 0, -8), L_fore=(-6, 0, 0), L_hand=(-8, 0, 0), R_arm=(-12, 0, 30), R_fore=(-30, 0, 0), R_hand=(10, 0, 0))
    c2 = P(T=(0, 0.1, 0), spine=(4, 0, 0), L_thigh=(-20, 0, 3), R_thigh=(-10, 0, -3), L_shin=(40, 0, 0), R_shin=(30, 0, 0),
           L_arm=(-110, 0, -6), L_fore=(-100, 0, 0), R_arm=(-15, 0, 16), R_fore=(-35, 0, 0))
    C["catch_high"] = dict(dur=1.1, contact=0.42, keys=Keys([(0, c0), (0.2, c0), (0.42, c1), (0.6, c1), (0.85, c2), (1.0, stance())]))
    # block / hook: hurley swept across to intercept (a defensive "hook")
    hk0 = P(T=(0, -0.10, 0), hips=(8, -16, 0), spine=(14, -22, 0), chest=(8, -12, 0), L_thigh=(-34, 0, 6), R_thigh=(8, 0, -6), L_shin=(46, 0, 0), R_shin=(34, 0, 0),
            R_arm=(-24, -10, 30), R_fore=(-30, 0, 0), R_hand=(10, 0, 0))
    hk1 = P(T=(0, -0.12, 0.10), hips=(10, 22, 0), spine=(16, 36, 0), chest=(10, 24, 0), L_thigh=(-42, 0, 6), R_thigh=(10, 0, -6), L_shin=(56, 0, 0), R_shin=(40, 0, 0),
            R_arm=(-75, 55, 4), R_fore=(-12, 0, 0), R_hand=(-30, 0, 0))
    C["block_hook"] = dict(dur=0.8, ik=True, contact=0.4, keys=Keys([(0, stance()), (0.25, hk0), (0.4, hk1), (0.7, hk1), (1.0, stance())]))
    # shoulder charge (legal shoulder-to-shoulder): hurley tucked, driving through
    sc0 = P(T=(0, -0.12, -0.06), hips=(6, 10, 0), spine=(14, 20, 0), chest=(8, 18, 0), L_thigh=(14, 0, 4), R_thigh=(-30, 0, -3), L_shin=(36, 0, 0), R_shin=(20, 0, 0),
            L_arm=(-40, 0, -20), L_fore=(-60, 0, 0), R_arm=(-30, 0, 8), R_fore=(-65, 0, 0))
    sc1 = P(T=(0, -0.10, 0.34), hips=(14, -20, 0), spine=(24, -30, 0), chest=(14, -22, 0), neck=(-14, 20, 0), L_thigh=(-40, 0, 4), R_thigh=(14, 0, -3), L_shin=(30, 0, 0), R_shin=(38, 0, 0),
            L_arm=(-30, 0, -22), L_fore=(-70, 0, 0), R_arm=(-36, 0, 8), R_fore=(-70, 0, 0))
    C["shoulder_charge"] = dict(dur=0.9, ik=True, contact=0.40, keys=Keys([(0, stance()), (0.3, sc0), (0.42, sc1), (0.65, sc1), (1.0, stance())]))
    # hit reaction and knock-down
    hr = P(T=(0, -0.08, -0.14), hips=(-12, 0, 0), spine=(-14, 0, 0), chest=(-10, 0, 0), neck=(14, 0, 0), head=(12, 0, 0), L_arm=(-24, 0, -22), L_fore=(-30, 0, 0),
           R_arm=(-20, 0, 24), R_fore=(-40, 0, 0), L_thigh=(14, 0, 4), R_thigh=(-10, 0, -4), L_shin=(18, 0, 0), R_shin=(16, 0, 0))
    C["hit_react"] = dict(dur=0.7, keys=Keys([(0, stance()), (0.2, hr), (1.0, stance())]))
    fl = P(T=(0, -0.80, 0.0), hips=(-88, 0, 0), spine=(-6, 0, 0), chest=(-4, 0, 0), neck=(6, 0, 0), L_arm=(-30, 0, -50), L_fore=(-20, 0, 0),
           R_arm=(-20, 0, 50), R_fore=(-10, 0, 0), L_thigh=(-6, 0, 6), R_thigh=(-10, 0, -6), L_shin=(30, 0, 0), R_shin=(14, 0, 0))
    C["knocked_down"] = dict(dur=1.6, keys=Keys([(0, stance()), (0.25, hr), (0.6, fl), (1.0, fl)]))
    C["get_up"] = dict(dur=1.4, keys=Keys([(0, fl), (0.5, pk0), (1.0, stance())]))
    cel = P(T=(0, 0.28, 0), spine=(-6, 0, 0), chest=(-8, 0, 0), neck=(12, 0, 0), L_arm=(-170, 0, -20), L_fore=(-10, 0, 0), R_arm=(-175, 0, 24), R_fore=(-6, 0, 0),
            L_thigh=(-22, 0, 6), R_thigh=(-20, 0, -6), L_shin=(46, 0, 0), R_shin=(48, 0, 0))
    C["celebrate"] = dict(dur=1.6, keys=Keys([(0, stance()), (0.22, cel), (0.4, {**cel, "T": (0, -0.04, 0)}), (0.58, cel), (0.76, {**cel, "T": (0, -0.04, 0)}), (1.0, stance())]))
    return C

# ---------------------------------------------------------------- output
def write_hurler(path, colors, clip_data):
    mesh = build_mesh(*colors); g = Glb()
    pos = np.array(mesh.v, np.float32); nor = np.array(mesh.n, np.float32); col = np.array(mesh.c, np.float32)
    jn = np.array(mesh.j, np.uint8); wt = np.array(mesh.w, np.float32)
    wt = wt / wt.sum(axis=1, keepdims=True); idx = np.array(mesh.i, np.uint16 if len(mesh.v) < 65535 else np.uint32)
    a_pos = g.add(pos, 5126, "VEC3", 34962, True); a_nor = g.add(nor, 5126, "VEC3", 34962); a_col = g.add(col, 5126, "VEC4", 34962)
    a_j = g.add(jn, 5121, "VEC4", 34962); a_w = g.add(wt, 5126, "VEC4", 34962)
    a_idx = g.add(idx.reshape(-1, 1), 5123 if idx.dtype == np.uint16 else 5125, "SCALAR", 34963)
    g.acc[a_idx]["count"] = int(idx.size)
    ibm = np.zeros((len(NAMES), 4, 4), np.float32)
    for i in range(len(NAMES)): ibm[i] = np.eye(4); ibm[i][:3, 3] = -BIND[i]
    ibm = ibm.transpose(0, 2, 1).reshape(len(NAMES), 16)  # column-major
    a_ibm = g.add(ibm, 5126, "MAT4")
    nodes = []
    for i, n in enumerate(NAMES):
        nd = {"name": n, "translation": OFF[i].tolist()}
        ch = [k for k in range(len(NAMES)) if PAR[k] == i]
        if ch: nd["children"] = ch
        nodes.append(nd)
    nodes.append({"name": "Hurler", "mesh": 0, "skin": 0})
    nodes.append({"name": "Armature", "children": [0, len(NAMES)]})
    anims = []
    for cname, spec in clip_data.items():
        frames = spec["frames"]; nf = len(frames); times = (np.arange(nf) / FPS).astype(np.float32)
        a_t = g.add(times.reshape(-1, 1), 5126, "SCALAR", None, True)
        g.acc[a_t]["min"] = [float(times[0])]; g.acc[a_t]["max"] = [float(times[-1])]
        samplers = []; channels = []
        for ji, jn_ in enumerate(NAMES):
            q = np.array([mat2quat(fr[0][ji]) for fr in frames], np.float32)
            for k in range(1, nf):  # keep quaternion hemisphere continuous
                if np.dot(q[k], q[k - 1]) < 0: q[k] = -q[k]
            if np.abs(q - np.array([0, 0, 0, 1], np.float32)).max() < 1e-5 and ji != 0: continue
            samplers.append({"input": a_t, "output": g.add(q, 5126, "VEC4"), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": ji, "path": "rotation"}})
        tr = np.array([fr[1] - BIND[0] + OFF[0] for fr in frames], np.float32)
        samplers.append({"input": a_t, "output": g.add(tr, 5126, "VEC3"), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": 0, "path": "translation"}})
        anims.append({"name": cname, "samplers": samplers, "channels": channels})
    doc = {"asset": {"version": "2.0", "generator": "gen_hurling_assets.py"},
           "scene": 0, "scenes": [{"nodes": [len(NAMES) + 1]}], "nodes": nodes,
           "materials": [{"name": "kit", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.85}}],
           "meshes": [{"name": "Hurler", "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nor, "COLOR_0": a_col, "JOINTS_0": a_j, "WEIGHTS_0": a_w}, "indices": a_idx, "material": 0}]}],
           "skins": [{"name": "HurlerSkin", "joints": list(range(len(NAMES))), "inverseBindMatrices": a_ibm, "skeleton": 0}],
           "animations": anims}
    g.write(path, doc); return len(mesh.v), len(mesh.i) // 3

def write_sliotar(path):
    g = Glb(); r = 0.0365; V = []; N = []; C = []; I = []; rings, segs = 12, 18
    for i in range(rings + 1):
        ph = math.pi * i / rings
        for k in range(segs):
            th = 2 * math.pi * k / segs; n = (math.sin(ph) * math.cos(th), math.cos(ph), math.sin(ph) * math.sin(th))
            V.append([n[0] * r, n[1] * r, n[2] * r]); N.append(n)
            seam = abs(n[1]) < 0.09
            C.append([0.93, 0.92, 0.86, 1] if not seam else [0.35, 0.22, 0.12, 1])
    for i in range(rings):
        for k in range(segs):
            a = i * segs + k; b = i * segs + (k + 1) % segs; c = a + segs; d = b + segs; I += [a, c, b, b, c, d]
    pos = np.array(V, np.float32); a_p = g.add(pos, 5126, "VEC3", 34962, True); a_n = g.add(np.array(N, np.float32), 5126, "VEC3", 34962)
    a_c = g.add(np.array(C, np.float32), 5126, "VEC4", 34962); ix = np.array(I, np.uint16); a_i = g.add(ix.reshape(-1, 1), 5123, "SCALAR", 34963); g.acc[a_i]["count"] = int(ix.size)
    doc = {"asset": {"version": "2.0", "generator": "gen_hurling_assets.py"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "Sliotar", "mesh": 0}],
           "materials": [{"name": "leather", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.6}}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": a_p, "NORMAL": a_n, "COLOR_0": a_c}, "indices": a_i, "material": 0}]}]}
    g.write(path, doc)

def render_sheet(path, clip_name, frames, colors, picks, view="side"):
    from PIL import Image, ImageDraw
    mesh = build_mesh(*colors); V = np.array(mesh.v); J = np.array(mesh.j); Wt = np.array(mesh.w); Fc = np.array(mesh.i).reshape(-1, 3); Cc = np.array(mesh.c)
    cell = 260; img = Image.new("RGB", (cell * len(picks), cell), (150, 185, 220)); dr = ImageDraw.Draw(img)
    for pi, fi in enumerate(picks):
        loc, hp = frames[min(fi, len(frames) - 1)]; R, Pw = fk(loc, hp); out = np.zeros_like(V)
        for k in range(4):
            for b in set(J[:, k].tolist()):
                msk = (J[:, k] == b) & (Wt[:, k] > 0)
                out[msk] += Wt[msk, k, None] * ((R[b] @ (V[msk] - BIND[b]).T).T + Pw[b])
        # side view (z across, y up), light from front-left
        sx = out[:, 2] if view == "side" else out[:, 0]; sy = out[:, 1]; dep = out[:, 0] if view == "side" else -out[:, 2]
        S = cell * 0.46; ox = pi * cell + cell / 2; oy = cell * 0.9
        pts = np.stack([ox + sx * S * (1 if view == "side" else -1), oy - sy * S], 1)
        tri = Fc; zc = dep[tri].mean(1); order = np.argsort(zc)
        for t in order:
            a, b, c = out[tri[t, 0]], out[tri[t, 1]], out[tri[t, 2]]; nrm = unit(np.cross(b - a, c - a)); sh = 0.55 + 0.45 * abs(np.dot(nrm, unit(np.array([0.3, 0.6, 0.7]))))
            cl = Cc[tri[t, 0]][:3] * sh; dr.polygon([tuple(pts[x]) for x in tri[t]], fill=tuple(int(255 * min(1, v)) for v in cl))
        dr.text((pi * cell + 6, 4), f"{clip_name} f{fi}", fill=(0, 0, 0))
    img.save(path)

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); sheet = "--sheet" in sys.argv
    C = clips(); data = {}
    for n, spec in C.items():
        nf = max(2, int(round(spec["dur"] * FPS)) + (0 if spec.get("loop") else 1))
        spec["frames"] = sample_clip(n, spec, nf); data[n] = spec
    home = ((0.10, 0.28, 0.62), (0.96, 0.96, 0.98), (0.10, 0.28, 0.62), (0.96, 0.82, 0.15))
    away = ((0.78, 0.10, 0.12), (0.98, 0.98, 0.98), (0.78, 0.10, 0.12), (0.12, 0.12, 0.14))
    nv, nt = write_hurler(os.path.join(out, "hurler_home.glb"), home, data); write_hurler(os.path.join(out, "hurler_away.glb"), away, data)
    write_sliotar(os.path.join(out, "sliotar.glb"))
    meta = {"fps": FPS, "joints": NAMES, "hurley_joint": "hurley", "grip_offset_m": GRIP_L,
            "clips": {n: {"seconds": s["dur"], "frames": len(s["frames"]), "loop": bool(s.get("loop")), "contact_seconds": (s["contact"] * s["dur"] if "contact" in s else None)} for n, s in data.items()},
            "verts": nv, "tris": nt}
    json.dump(meta, open(os.path.join(out, "clips.json"), "w"), indent=1)
    if sheet:
        for n, s in data.items():
            nf = len(s["frames"]); picks = sorted(set(int(round(x * (nf - 1))) for x in np.linspace(0, 1, 6)))
            render_sheet(os.path.join(out, f"clip_{n}.png"), n, s["frames"], home, picks)
    print(f"{nv} verts, {nt} tris, {len(data)} clips -> {out}")

if __name__ == "__main__":
    main()
