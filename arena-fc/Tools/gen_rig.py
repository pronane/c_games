#!/usr/bin/env python3
"""Generates Data/rig_default.json: the skinned 18-bone footballer used by the browser edition.

v2 replaces the original blocky limbs and ball-shaped head with tapered, soft-skinned limbs, a shaped torso
(shoulders, waist, hips), a head with jaw, nose, ears, eyes and hair, shorts, socks and boots. Same bones,
same material slots, so every existing consumer (BrowserBoot, ProceduralRig3D, Sprite Forge overrides) works.

  python3 Tools/gen_rig.py            # rewrites Data/rig_default.json
Material slots: 0 skin, 1 shirt, 2 shorts, 3 socks, 4 trim (shorts colour), 5 badge, 6 hair, 7 eyes, 8 boots.
"""
import json, math, os, sys

OLD = os.path.join(os.path.dirname(__file__), "..", "Data", "rig_default.json")
OUT = OLD
bones = json.load(open(OLD))["bones"]          # keep the existing skeleton exactly
BI = {b["n"]: i for i, b in enumerate(bones)}
HEAD_H = {b["n"]: b["h"] for b in bones}

pos, nrm, uv, bi, wt = [], [], [], [], []
tris = {}                                       # material -> list of vertex indices

def smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)

def add_vertex(p, uvc, weights):
    w = sorted(weights, key=lambda x: -x[1])[:4]
    s = sum(x[1] for x in w) or 1.0
    w = [(b, v / s) for b, v in w] + [(0, 0.0)] * (4 - len(w))
    pos.extend(p); nrm.extend([0.0, 1.0, 0.0]); uv.extend(uvc)
    bi.extend(b for b, _ in w); wt.extend(round(v, 4) for _, v in w)
    return len(pos) // 3 - 1

def ring_pts(y, cx, cz, rx, rz, n, power=2.0):
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        out.append((cx + rx * math.copysign(abs(c) ** (2 / power), c), y, cz + rz * math.copysign(abs(s) ** (2 / power), s)))
    return out

def lathe(rings, mat, weight_fn, n, close_top=True, close_bottom=True, v_scale=1.8):
    """rings: list of (y, cx, cz, rx, rz[, power]). weight_fn(point) -> [(bone, weight)]."""
    idx = []
    for r in rings:
        pts = ring_pts(r[0], r[1], r[2], r[3], r[4], n, r[5] if len(r) > 5 else 2.0)
        row = []
        for k, p in enumerate(pts):
            row.append(add_vertex(p, (k / n, p[1] / v_scale), weight_fn(p)))
        idx.append(row)
    t = tris.setdefault(mat, [])
    for i in range(len(idx) - 1):
        for k in range(n):
            a, b = idx[i][k], idx[i][(k + 1) % n]
            c, d = idx[i + 1][k], idx[i + 1][(k + 1) % n]
            t += [a, c, b, b, c, d]
    def cap(row, ycap, top):
        cx = sum(pos[v * 3] for v in row) / n; cz = sum(pos[v * 3 + 2] for v in row) / n
        c = add_vertex((cx, ycap, cz), (0.5, ycap / v_scale), weight_fn((cx, ycap, cz)))
        for k in range(n):
            a, b = row[k], row[(k + 1) % n]
            t.extend([a, c, b] if top else [a, b, c])
    if close_top:
        r = rings[-1]; cap(idx[-1], r[0] + (r[0] - rings[-2][0]) * 0.0, True)
    if close_bottom:
        r = rings[0]; cap(idx[0], r[0], False)

def ellipsoid(c, r, mat, weight_fn, n=12, rows=8):
    rings = []
    for j in range(1, rows):
        a = math.pi * j / rows
        s = math.sin(a)
        rings.append((c[1] + r[1] * math.cos(a), c[0], c[2], max(r[0] * s, 1e-4), max(r[2] * s, 1e-4)))
    rings.reverse()
    lathe(rings, mat, weight_fn, n, True, True)

def W1(name):
    return lambda p: [(BI[name], 1.0)]

def chain(joints, width=0.05):
    """Skin weights along a vertical chain [(bone, y_joint_to_next)], blending over +-width at each joint."""
    def f(p):
        y = p[1]
        w = []
        first = joints[0][0]
        for k, (name, yj) in enumerate(joints):
            if k == 0:
                w.append([name, 1.0 - smooth(yj - width, yj + width, y) if False else 0.0])
        # piecewise: weight of bone k = smooth blends between neighbours
        res = {}
        top = joints[0][0]
        res[top] = 1.0
        for k in range(len(joints) - 1):
            nxt = joints[k + 1][0]
            yj = joints[k][1]
            t = 1.0 - smooth(yj - width, yj + width, y)      # 0 above the joint, 1 below it
            for key in list(res):
                res[key] *= (1.0 - t)
            res[nxt] = res.get(nxt, 0.0) + t * 1.0 if False else t * 1.0
            # keep accumulated weights consistent: previous mass stays with earlier bones
        return [(BI[k], v) for k, v in res.items() if v > 1e-3]
    return f

def chain2(items, width=0.05):
    """items: [(bone, y_boundary_below)] top to bottom; boundary None for the last. Smooth blend at each boundary."""
    def f(p):
        y = p[1]
        w = {}
        remaining = 1.0
        for k, (name, yb) in enumerate(items):
            if yb is None:
                w[name] = w.get(name, 0.0) + remaining
                break
            below = 1.0 - smooth(yb - width, yb + width, y)       # share that has moved on to the next bone
            w[name] = w.get(name, 0.0) + remaining * (1.0 - below)
            remaining *= below
        return [(BI[k], v) for k, v in w.items() if v > 1e-3]
    return f

N = 14
SK = 0; SHIRT = 1; SHORTS = 2; SOCKS = 3; TRIM = 4; BADGE = 5; HAIR = 6; EYE = 7; BOOT = 8

def leg(side):
    s = -1.0 if side == "L" else 1.0
    th, sh, ft = BI[side + "Thigh"], BI[side + "Shin"], BI[side + "Foot"]
    cx = lambda y: s * (0.1112 + (0.1213 - 0.1112) * (0.9909 - y) / (0.9909 - 0.5561 if y > 0.5561 else 1))
    xk = s * 0.1213
    xh = s * 0.1112
    wf = chain2([(side + "Thigh", 0.5561), (side + "Shin", 0.1314), (side + "Foot", None)], 0.045)
    # shorts (thigh top)
    lathe([(0.995, xh, 0.0, 0.105, 0.105), (0.93, xh, 0.0, 0.108, 0.108), (0.84, xh, 0.0, 0.102, 0.104), (0.74, xh, 0.0, 0.098, 0.100)],
          SHORTS, wf, N, False, True)
    lathe([(0.742, xh, 0.0, 0.1, 0.102), (0.72, xh, 0.0, 0.1, 0.102), (0.714, xh, 0.0, 0.092, 0.094)], TRIM, wf, N, False, False)
    # bare thigh to the sock top
    lathe([(0.72, xh, 0.0, 0.088, 0.09), (0.64, s * 0.118, 0.002, 0.078, 0.082), (0.5561, xk, 0.004, 0.066, 0.07), (0.50, xk, 0.004, 0.064, 0.068)],
          SK, wf, N, False, False)
    # sock: knee to ankle with calf bulge
    lathe([(0.52, xk, 0.004, 0.066, 0.07), (0.44, xk, -0.012, 0.064, 0.074), (0.36, xk, -0.012, 0.058, 0.066), (0.24, xk, -0.004, 0.046, 0.05),
           (0.15, xk, 0.0, 0.041, 0.044), (0.115, xk, 0.0, 0.043, 0.046)], SOCKS, wf, N, False, False)
    lathe([(0.545, xk, 0.004, 0.0665, 0.071), (0.52, xk, 0.004, 0.0665, 0.071), (0.51, xk, 0.004, 0.0645, 0.0685)], TRIM, wf, N, False, False)
    # boot: shaped like a shoe (heel, instep, toe box)
    wb = lambda p: [(ft, 1.0)]
    xf = s * 0.1213
    lathe([(0.0, xf, 0.045, 0.03, 0.12, 3.0), (0.012, xf, 0.045, 0.052, 0.135, 3.0), (0.04, xf, 0.045, 0.054, 0.13, 3.0), (0.07, xf, 0.02, 0.05, 0.085, 2.5),
           (0.105, xf, 0.0, 0.046, 0.058, 2.2), (0.135, xf, 0.0, 0.043, 0.05, 2.0)], BOOT, wb, N, True, True)
    # studs
    for dz in (-0.04, 0.12):
        for dx in (-0.025, 0.025):
            ellipsoid((xf + dx, 0.0, 0.045 + dz), (0.009, 0.012, 0.009), BOOT, wb, 6, 4)

def torso():
    wt_ = chain2([("Hips", 1.13), ("Spine", 1.33), ("Chest", None)], 0.06)
    # shirt body: hips -> chest -> shoulders
    rings = [(1.02, 0, 0.0, 0.165, 0.105, 2.6), (1.08, 0, 0.0, 0.158, 0.10, 2.6), (1.16, 0, 0.0, 0.150, 0.098, 2.5),
             (1.26, 0, 0.002, 0.160, 0.103, 2.4), (1.36, 0, 0.006, 0.178, 0.112, 2.3), (1.44, 0, 0.004, 0.192, 0.112, 2.3),
             (1.485, 0, 0.0, 0.180, 0.10, 2.3), (1.52, 0, 0.0, 0.10, 0.075, 2.1)]
    lathe(rings, SHIRT, wt_, 18, True, False)
    # shirt hem / waist band into the shorts
    lathe([(1.03, 0, 0.0, 0.167, 0.107, 2.6), (1.0, 0, 0.0, 0.169, 0.109, 2.6), (0.96, 0, 0.0, 0.168, 0.108, 2.6)], SHORTS, wt_, 18, False, True)
    lathe([(1.046, 0, 0.0, 0.1685, 0.1075, 2.6), (1.033, 0, 0.0, 0.1695, 0.1085, 2.6)], TRIM, wt_, 18, False, False)
    # collar ring
    lathe([(1.5, 0, 0.01, 0.062, 0.058), (1.535, 0, 0.012, 0.058, 0.056), (1.55, 0, 0.012, 0.052, 0.050)], TRIM, W1("Neck"), 14, False, False)
    # badge
    ellipsoid((-0.07, 1.33, 0.113), (0.022, 0.022, 0.006), BADGE, W1("Chest"), 10, 6)
    # neck
    lathe([(1.50, 0, 0.004, 0.052, 0.052), (1.57, 0, 0.012, 0.047, 0.048), (1.64, 0, 0.016, 0.046, 0.048)], SK, chain2([("Chest", 1.52), ("Neck", 1.6), ("Head", None)], 0.03), 12, False, False)

def arm(side):
    s = -1.0 if side == "L" else 1.0
    up, fa, ha = side + "UpperArm", side + "Forearm", side + "Hand"
    sx, sy = s * 0.2022, 1.4863
    ex, ey = s * 0.2326, 1.2133
    wx, wy = s * 0.2528, 0.9707
    def xat(y):
        if y > ey:
            t = (sy - y) / (sy - ey); return sx + (ex - sx) * t
        t = (ey - y) / (ey - wy); return ex + (wx - ex) * t
    wf = chain2([(up, ey), (fa, wy), (ha, None)], 0.035)
    # shoulder cap + sleeve
    lathe([(1.505, sx - s * 0.012, 0.0, 0.03, 0.03), (1.495, sx, 0.0, 0.052, 0.052), (1.485, sx, 0.0, 0.062, 0.06), (1.42, xat(1.42), 0.0, 0.058, 0.056), (1.34, xat(1.34), 0.0, 0.053, 0.052)], SHIRT, wf, 12, False, False)
    lathe([(1.345, xat(1.345), 0.0, 0.0535, 0.0525), (1.33, xat(1.33), 0.0, 0.0535, 0.0525), (1.322, xat(1.322), 0.0, 0.050, 0.05)], TRIM, wf, 12, False, False)
    # bare upper arm, elbow, forearm, wrist
    lathe([(1.325, xat(1.325), 0.0, 0.048, 0.048), (1.213, ex, 0.0, 0.040, 0.042), (1.10, xat(1.10), 0.004, 0.038, 0.040), (0.99, xat(0.99), 0.0, 0.030, 0.030), (0.97, wx, 0.0, 0.028, 0.028)],
          SK, wf, 12, False, False)
    # hand: palm + thumb
    wh = lambda p: [(BI[ha], 1.0)]
    lathe([(0.975, wx, 0.0, 0.03, 0.026), (0.935, wx, 0.003, 0.038, 0.022), (0.895, wx, 0.003, 0.034, 0.02), (0.865, wx, 0.002, 0.022, 0.016)], SK, wh, 10, True, False)
    ellipsoid((wx - s * 0.03, 0.925, 0.012), (0.011, 0.028, 0.012), SK, wh, 6, 5)

def head():
    wh = W1("Head")
    cy, hy = 1.7175, 0.118
    def hr(y):
        u = (y - cy) / hy
        base = math.sqrt(max(0.0, 1 - u * u))
        jaw = 0.82 + 0.18 * smooth(-0.9, 0.35, u)
        return base, jaw
    rings = []
    for k in range(0, 13):
        y = 1.598 + (1.838 - 1.598) * k / 12
        base, jaw = hr(y)
        rx, rz = 0.092 * base * jaw, 0.104 * base * (0.86 + 0.14 * jaw)
        rings.append((y, 0.0, 0.012 - 0.004 * (1 - jaw), max(rx, 0.008), max(rz, 0.008)))
    lathe(rings, SK, wh, 18, True, True)
    # hair: upper cap, longer at the back
    hair = []
    for k in range(9, 13):
        y = 1.598 + (1.838 - 1.598) * k / 12
        base, jaw = hr(y)
        hair.append((y + 0.003, 0.0, 0.006, max(0.0975 * base * jaw, 0.01), max(0.1095 * base * (0.86 + 0.14 * jaw), 0.01)))
    lathe(hair, HAIR, wh, 18, True, False)
    ellipsoid((0.0, 1.745, -0.062), (0.092, 0.07, 0.062), HAIR, wh, 12, 6)       # back of the head
    # nose, ears, eyes, brows
    ellipsoid((0.0, 1.708, 0.116), (0.015, 0.024, 0.02), SK, wh, 8, 6)
    for sx in (-1, 1):
        ellipsoid((sx * 0.094, 1.71, 0.0), (0.011, 0.03, 0.02), SK, wh, 8, 6)
        ellipsoid((sx * 0.036, 1.738, 0.106), (0.0105, 0.0105, 0.008), EYE, wh, 8, 6)
        ellipsoid((sx * 0.037, 1.76, 0.107), (0.02, 0.005, 0.006), HAIR, wh, 8, 4)

for sd in ("L", "R"):
    leg(sd); arm(sd)
torso(); head()

# smooth normals from face normals (accumulated); vertices are not shared across parts so seams stay crisp
acc = [[0.0, 0.0, 0.0] for _ in range(len(pos) // 3)]
def P(i): return pos[i * 3:i * 3 + 3]
def sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
for m, t in tris.items():
    for k in range(0, len(t), 3):
        a, b, c = t[k:k + 3]
        n = cross(sub(P(b), P(a)), sub(P(c), P(a)))
        for v in (a, b, c):
            for j in range(3): acc[v][j] += n[j]
# Godot front faces are clockwise, so the accumulated normal currently points inward for outward-facing quads:
# decide the sign with a probe (torso front vertex should have +z normal)
probe = min(range(len(acc)), key=lambda i: -pos[i * 3 + 2] if 1.2 < pos[i * 3 + 1] < 1.3 and abs(pos[i * 3]) < 0.02 else 9)
flip = 1.0 if acc[probe][2] > 0 else -1.0
if flip < 0:
    for m in tris:
        t = tris[m]
        for k in range(0, len(t), 3):
            t[k + 1], t[k + 2] = t[k + 2], t[k + 1]
    acc = [[-x for x in a] for a in acc]
# after (possibly) re-winding, outward normals = accumulated normals of the original winding
for i, a in enumerate(acc):
    l = math.sqrt(sum(x * x for x in a)) or 1.0
    nrm[i * 3:i * 3 + 3] = [round(x / l, 4) for x in a]
# the cross-product normal above points outward when front faces are CCW; Godot wants CW, so reverse the
# winding once more so rendering is correct, keeping the (outward) normals computed above
for m in tris:
    t = tris[m]
    for k in range(0, len(t), 3):
        t[k + 1], t[k + 2] = t[k + 2], t[k + 1]

mats = sorted(tris.keys())
idx = [tris.get(m, []) if m in tris else [] for m in range(9)]
data = {"generator": "ArenaFC rig v2 (Tools/gen_rig.py)", "bones": bones,
        "pos": [round(x, 5) for x in pos], "nrm": nrm, "uv": [round(x, 4) for x in uv], "bi": bi, "w": wt,
        "idx": idx, "mats": mats, "height": 1.8483}
json.dump(data, open(OUT, "w"), separators=(",", ":"))
print("verts", len(pos) // 3, "tris", sum(len(t) for t in tris.values()) // 3, "mats", mats)
