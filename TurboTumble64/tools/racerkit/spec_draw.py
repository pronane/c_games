"""racerkit.spec_draw - draws a fictional racer from spec parameters (racerkit.spec).

A tiny offline ray-caster: the character is a set of ellipsoids (head, nose, ears,
hair shells, torso, arms, hands...) rendered orthographically from any angle, with
the face (eyes, brows, mouth, freckles, blush) painted onto the head surface so
every angle of the sprite sheet is consistent.  Cel shading + ink outline give a
clean HD cartoon look.  It is a stylised cartoon, not a photo-real person.
"""
import math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

SS = 2   # supersampling


def _rot_axis(a, b):
    """rotation whose local +y axis points from a to b"""
    v = np.array(b, float) - np.array(a, float)
    y = v / (np.linalg.norm(v) + 1e-9)
    t = np.array([0, 0, 1.0]) if abs(y[2]) < 0.9 else np.array([1.0, 0, 0])
    x = np.cross(y, t); x /= np.linalg.norm(x)
    z = np.cross(x, y)
    return np.stack([x, y, z], 1)


def _roty(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rotz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


class Prim:
    def __init__(self, c, r, color, R=None, clip=None, paint=None, mat="cloth", group=None):
        self.c = np.array(c, float)
        self.r = np.array(r, float)
        self.R = np.eye(3) if R is None else np.array(R, float)
        self.color = np.array(color, float)
        self.clip = clip          # f(p_local unit-sphere coords (N,3)) -> bool keep
        self.paint = paint        # f(p_local, base (N,3)) -> colours (N,3)
        self.mat = mat
        self.group = group        # prims of one group don't ink-outline each other


def capsule(a, b, rad, color, mat="cloth", group=None):
    a, b = np.array(a, float), np.array(b, float)
    L = np.linalg.norm(b - a)
    return Prim((a + b) / 2, (rad, L / 2 + rad * 0.85, rad), color, R=_rot_axis(a, b), mat=mat, group=group)


def render(prims, theta, W, H, x0, x1, y0, y1, light=(-0.45, 0.62, 0.64), outline=True):
    """orthographic render, camera at azimuth theta (0 front, 90 = character's right side)"""
    th = math.radians(theta)
    cam = np.array([-math.sin(th), 0.0, math.cos(th)])      # towards the camera
    right = np.array([math.cos(th), 0.0, math.sin(th)])
    up = np.array([0.0, 1.0, 0.0])
    Ws, Hs = W * SS, H * SS
    xs = x0 + (np.arange(Ws) + 0.5) / Ws * (x1 - x0)
    ys = y1 - (np.arange(Hs) + 0.5) / Hs * (y1 - y0)
    depth = np.full((Hs, Ws), -1e9)
    col = np.zeros((Hs, Ws, 3))
    nv = np.zeros((Hs, Ws, 3))
    pid = np.full((Hs, Ws), -1, int)
    gid = np.full((Hs, Ws), -1, int)
    mats = np.zeros((Hs, Ws), int)
    MAT = {"skin": 0, "cloth": 1, "hair": 2, "eye": 3, "shiny": 4}
    px_per = Ws / (x1 - x0)
    for i, p in enumerate(prims):
        cx, cy = p.c @ right, p.c[1]
        rad = p.r.max()
        ix0 = max(0, int((cx - rad - x0) * px_per) - 1); ix1 = min(Ws, int((cx + rad - x0) * px_per) + 2)
        iy0 = max(0, int((y1 - (cy + rad)) * px_per) - 1); iy1 = min(Hs, int((y1 - (cy - rad)) * px_per) + 2)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        X, Y = np.meshgrid(xs[ix0:ix1], ys[iy0:iy1])
        O = X[..., None] * right + Y[..., None] * up + 50.0 * cam - p.c       # (h,w,3)
        Ol = (O @ p.R) / p.r
        Dl = ((-cam) @ p.R) / p.r
        a = Dl @ Dl
        b = 2 * (Ol @ Dl)
        cc = (Ol * Ol).sum(-1) - 1
        disc = b * b - 4 * a * cc
        hit = disc > 0
        if not hit.any():
            continue
        sq = np.sqrt(np.where(hit, disc, 0))
        t1 = (-b - sq) / (2 * a)
        t2 = (-b + sq) / (2 * a)
        P1 = Ol + t1[..., None] * Dl
        P2 = Ol + t2[..., None] * Dl
        k1 = hit.copy()
        k2 = hit.copy()
        if p.clip is not None:
            k1 &= p.clip(P1)
            k2 &= p.clip(P2) & ~k1
        else:
            k2[:] = False
        t = np.where(k1, t1, t2)
        ok = k1 | k2
        dep = 50.0 - t
        sub = depth[iy0:iy1, ix0:ix1]
        win = ok & (dep > sub)
        if not win.any():
            continue
        PL = np.where(k1[..., None], P1, P2)
        nl = PL / p.r
        nw = nl @ p.R.T
        nw /= np.linalg.norm(nw, axis=-1, keepdims=True) + 1e-9
        nw = np.where(k2[..., None], -nw, nw)
        base = np.broadcast_to(p.color, PL.shape).copy()
        if p.paint is not None:
            m = win
            base[m] = p.paint(PL[m], base[m])
        sub[win] = dep[win]
        col[iy0:iy1, ix0:ix1][win] = base[win]
        nview = np.stack([nw @ right, nw[..., 1], nw @ cam], -1)
        nv[iy0:iy1, ix0:ix1][win] = nview[win]
        pid[iy0:iy1, ix0:ix1][win] = i
        gid[iy0:iy1, ix0:ix1][win] = i if p.group is None else 10000 + hash(p.group) % 100000
        mats[iy0:iy1, ix0:ix1][win] = MAT.get(p.mat, 1)
    mask = pid >= 0
    L = np.array(light, float); L /= np.linalg.norm(L)
    lam = np.clip((nv * L).sum(-1), -1, 1)
    # cel shading: two soft bands + a little gradient, rim light, hair/shiny highlight
    band = 1 / (1 + np.exp(-(lam - 0.12) * 18))
    shade = 0.66 + 0.30 * band + 0.10 * np.clip(lam, 0, 1)
    skin = mats == 0
    shade = np.where(skin, 0.74 + 0.22 * band + 0.08 * np.clip(lam, 0, 1), shade)
    rim = np.clip(1 - nv[..., 2], 0, 1) ** 3 * 0.10
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    spec = np.clip((nv * Hh).sum(-1), 0, 1) ** 40
    spec = np.where(mats == 4, (spec > 0.45) * 0.22, np.where(mats == 2, (spec > 0.75) * 0.10, spec * 0.04))
    out = col * shade[..., None] + 255 * (rim + spec)[..., None]
    # ink outline: silhouette + where separate parts overlap with a depth jump
    if outline:
        edge = np.zeros_like(mask)
        def _shift(a, dy, dx, fill):
            o = np.full_like(a, fill)
            hh, ww = a.shape
            o[max(0, dy):hh + min(0, dy), max(0, dx):ww + min(0, dx)] = a[max(0, -dy):hh - max(0, dy), max(0, -dx):ww - max(0, dx)]
            return o
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            g2 = _shift(gid, dy, dx, -1)
            d2 = _shift(depth, dy, dx, -1e9)
            m2 = _shift(mask, dy, dx, False)
            e = (mask != m2) | (mask & m2 & (gid != g2) & (np.abs(depth - d2) > 0.06))
            edge |= e | _shift(e, -dy, -dx, False)
        th_px = max(1, int(round(1.6 * SS * W / 512)))
        edge = ndi.binary_dilation(edge, iterations=th_px)
        # ink is a dark version of the nearest part colour
        idx = ndi.distance_transform_edt(~mask, return_distances=False, return_indices=True)
        near = col[idx[0], idx[1]]
        ink = near * 0.28 + np.array([12, 8, 16]) * 0.72
        out = np.where(edge[..., None], ink, out)
        mask = mask | edge
    rgba = np.dstack([np.clip(out, 0, 255), mask * 255.0])
    im = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    # premultiplied downsample so edges stay clean
    pm = rgba.copy(); pm[..., :3] *= rgba[..., 3:4] / 255
    pmi = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA").resize((W, H), Image.BOX)
    arr = np.asarray(pmi, float)
    a = arr[..., 3:4]
    arr[..., :3] = np.where(a > 0, arr[..., :3] * 255 / np.maximum(a, 1), 0)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ----------------------------------------------------------- character build ----
def _mix(a, b, t):
    return np.array(a, float) * (1 - t) + np.array(b, float) * t


def build(P, pose="drive", expr=None):
    """returns (prims, info) for the parameters P from spec.resolve()"""
    expr = expr or P["expression"]
    age = P["age"]
    skin = np.array(P["skin"], float)
    hairc = np.array(P["hair_color"], float)
    top = np.array(P["top_color"], float)
    W_ = P["width"]
    # proportions (head radius ~1); babies have big heads and short bodies
    hr = {"baby": 1.0, "child": 1.0, "teen": 1.0, "adult": 1.0, "elder": 1.0}[age]
    fs = P["face_shape"]
    hx, hy, hz = {"round": (1.0, 1.0, 1.0), "oval": (0.92, 1.08, 0.98), "long": (0.86, 1.16, 0.96),
                  "square": (1.0, 1.02, 0.98), "heart": (0.95, 1.06, 0.97)}[fs]
    hx *= 1 + 0.12 * (W_ - 1)
    body_k = {"baby": 0.55, "child": 0.75, "teen": 0.95, "adult": 1.0, "elder": 0.98}[age]
    neck_len = {"baby": 0.05, "child": 0.22, "teen": 0.35, "adult": 0.4, "elder": 0.38}[age]
    torso_h = 2.55 * body_k * (P["height_cm"] / {"baby": 80, "child": 125, "teen": 165, "adult": 172, "elder": 168}[age]) ** 0.5
    tw = (0.95 + 0.2 * body_k) * W_ * P["shoulders"]
    td = 0.72 * W_ * (0.9 + 0.1 * body_k)
    head_c = np.array([0.0, 0.0, 0.0])
    neck_top = -hy * 0.82
    sh_y = neck_top - neck_len - 0.25
    torso_c = np.array([0, sh_y - torso_h * 0.42, 0])
    seat_y = torso_c[1] - torso_h * 0.42
    prims = []
    # ---- face painting (head local coords on the unit sphere, +z = face) ----
    eyec = np.array(P["eye_color"], float)
    es = P["eye_size"]
    ex, ey, ew, eh = 0.36, 0.02, 0.15 * es, 0.13 * es * (0.8 if P["eye_shape"] in ("almond", "monolid") else 1.0)
    if age == "baby":
        ey -= 0.06
    lipc = np.array(P["lip_color"], float) if P["lip_color"] is not None else _mix(skin, (190, 70, 80), 0.45)
    browc = np.array(_mix(hairc, (30, 20, 15), 0.35))
    mw = {"small": 0.15, "medium": 0.21, "wide": 0.28, "big": 0.28}[P["mouth"]]
    my = -0.42 if age != "baby" else -0.46
    rng = np.random.default_rng(11)
    freck = rng.uniform(-1, 1, (26, 2)) * np.array([0.22, 0.09]) + np.array([0.0, -0.17])
    freck[:, 0] += np.sign(freck[:, 0]) * 0.28

    def face_paint(p, base):
        az = np.arctan2(p[:, 0], p[:, 2])
        el = np.arcsin(np.clip(p[:, 1], -1, 1))
        out = base.copy()
        front = p[:, 2] > -0.2
        # blush
        if P["blush"] not in ("no", "none"):
            k = 0.32 if P["blush"] in ("yes", "lots") else 0.18
            for sx in (-1, 1):
                d = ((az - sx * 0.45) / 0.17) ** 2 + ((el + 0.24) / 0.10) ** 2
                t = (np.exp(-d * 1.5) * k)[:, None] * front[:, None]
                out = out * (1 - t) + np.array([255, 110, 130]) * t
        if P["freckles"]:
            for fx, fy in freck:
                d = ((az - fx) ** 2 + (el - fy) ** 2) < 0.016 ** 2
                out[d & front] = out[d & front] * 0.78 + np.array([150, 85, 50]) * 0.22
        for sx in (-1, 1):
            cx = sx * ex
            dx, dy = (az - cx) / ew, (el - ey) / eh
            r2 = dx * dx + dy * dy
            if expr in ("happy",):
                # closed happy eyes: ^ arcs
                arc = (np.abs(np.sqrt(dx * dx + (dy + 0.5) ** 2) - 0.75) < 0.16) & (dy > -0.2)
                out[arc & front] = (40, 26, 22)
                continue
            lid = 0.0
            if expr in ("sleepy", "grumpy"):
                lid = 0.25 if expr == "grumpy" else 0.05
            inside = (r2 < 1) & front
            if expr in ("sleepy", "grumpy"):
                inside = (r2 < 1) & front & (dy < (0.05 if expr == "sleepy" else 0.4))
            out[inside] = (250, 250, 252)
            ir = np.sqrt(((az - cx) / (eh * 0.78)) ** 2 + ((el - ey + 0.1 * eh) / (eh * 0.78)) ** 2)
            m = inside & (ir < 1)
            out[m] = eyec * (0.75 + 0.35 * (1 - ir[m]))[:, None]
            out[inside & (ir < 0.45)] = (18, 14, 16)
            hl = np.sqrt(((az - cx + sx * 0.0 + 0.25 * eh) / (eh * 0.22)) ** 2 + ((el - ey - 0.35 * eh) / (eh * 0.22)) ** 2) < 1
            out[inside & hl] = (255, 255, 255)
            # upper lash line / lid
            ring = (r2 > 0.78) & (r2 < 1.25) & (dy > 0.05 if lid == 0 else dy > -0.1) & front
            if expr in ("sleepy",):
                ring = (np.abs(dy - 0.05) < 0.16) & (np.abs(dx) < 1.0) & front
            out[ring] = (36, 24, 24)
            # brows
            bt = {"thin": 0.022, "medium": 0.032, "thick": 0.045, "bushy": 0.055}[P["brows"]]
            tilt = {"grumpy": -0.10 * sx, "sleepy": 0.03 * sx}.get(expr, 0.0)
            by = ey + eh + 0.10 + tilt * (az - cx) / ew * (-1)
            bshape = by + 0.035 * (1 - ((az - cx) / (ew * 1.1)) ** 2)
            brow = (np.abs(el - bshape) < bt) & (np.abs(az - cx) < ew * 1.15) & front
            out[brow] = browc
            if P["glasses"] != "none":
                gw, gh = ew * 1.45, eh * 1.55
                gd = ((az - cx) / gw) ** 2 + ((el - ey) / gh) ** 2 if P["glasses"] == "round" else \
                    np.maximum(np.abs(az - cx) / gw, np.abs(el - ey) / gh) ** 2
                out[(gd > 0.80) & (gd < 1.0) & front] = P["glasses_color"]
        if P["glasses"] != "none":
            bridge = (np.abs(el - ey - 0.02) < 0.02) & (np.abs(az) < ex - ew * 1.4) & front
            out[bridge] = P["glasses_color"]
        # mouth
        u = az / mw
        if expr in ("happy", "cheeky"):
            top_ = my + 0.02
            bot = my - 0.10 * (1 - u * u)
            m = (np.abs(u) < 1) & (el < top_ + 0.01 * u * u) & (el > bot) & front
            out[m] = (120, 30, 40)
            tongue = m & (el < bot + 0.045) & (np.abs(u) < 0.55)
            out[tongue] = (240, 110, 120)
            teeth = m & (el > top_ - 0.025)
            out[teeth] = (252, 252, 250)
        elif expr in ("sleepy", "grumpy", "serious"):
            curve = my - 0.012 + (-0.035 if expr != "serious" else 0) * (1 - u * u) * -1
            th = 0.022 if P["lips"] != "full" else 0.032
            m = (np.abs(u) < 0.85) & (np.abs(el - (my - 0.02 - 0.03 * (u * u))) < th) & front
            out[m] = lipc * 0.8
        else:
            th = {"thin": 0.018, "medium": 0.026, "full": 0.036}[P["lips"]]
            curve = my + 0.05 * (u * u)
            m = (np.abs(u) < 1) & (np.abs(el - curve) < th) & front
            out[m] = lipc * 0.85
            if P["lips"] == "full":
                lip2 = (np.abs(u) < 0.75) & (el < curve - th) & (el > curve - th - 0.04 * (1 - u * u)) & front
                out[lip2] = lipc
        # beard / stubble shading
        if P["beard"] in ("stubble",):
            m = (el < -0.18) & front & ~((np.abs(u) < 1.1) & (np.abs(el - my) < 0.05))
            out[m] = out[m] * 0.82 + hairc * 0.18
        if P["beard"] in ("moustache", "mustache", "goatee", "full"):
            m = (np.abs(az) < mw * 1.1) & (el > my + 0.03) & (el < my + 0.10) & front
            out[m] = hairc
        return out

    prims.append(Prim(head_c, (hx * hr, hy * hr, hz * hr), skin, paint=face_paint, mat="skin", group="head"))
    # nose
    nz = {"button": (0.13, 0.12, 0.12), "small": (0.12, 0.15, 0.14), "snub": (0.14, 0.13, 0.14),
          "medium": (0.15, 0.22, 0.18), "wide": (0.23, 0.17, 0.17), "broad": (0.24, 0.18, 0.17),
          "large": (0.19, 0.27, 0.23), "big": (0.19, 0.27, 0.23), "long": (0.14, 0.30, 0.22),
          "pointy": (0.12, 0.20, 0.30), "hooked": (0.15, 0.28, 0.26), "roman": (0.15, 0.28, 0.25)}[P["nose"]]
    ny_ = -0.16 if age != "baby" else -0.2
    nzpos = hz * math.cos(math.asin(min(0.9, abs(ny_) / hy))) * 0.98

    def nose_paint(p, base):
        out = base.copy()
        nost = (p[:, 1] < -0.55) & (np.abs(np.abs(p[:, 0]) - 0.38) < 0.14) & (p[:, 2] > 0.25)
        out[nost] = base[nost] * 0.72
        return out
    prims.append(Prim((0, ny_, nzpos), nz, _mix(skin, (200, 110, 100), 0.08), paint=nose_paint, mat="skin", group="head"))
    # ears
    ek = {"small": 0.8, "medium": 1.0, "large": 1.25, "big": 1.25, "pointy": 1.0, "sticking out": 1.1, "protruding": 1.1}[P["ears"]]
    for sx in (-1, 1):
        R = _roty(sx * (38 if P["ears"] in ("sticking out", "protruding") else 12))
        rr = (0.10, 0.28 * ek * (1.35 if P["ears"] == "pointy" else 1), 0.19 * ek)
        if P["ears"] == "pointy":
            R = R @ _rotz(-sx * 18)
        ear = Prim((sx * hx * 0.95, -0.06 + (0.08 if P["ears"] == "pointy" else 0), -0.05), rr, skin * 0.97, R=R, mat="skin", group="head")
        ear.paint = (lambda s: (lambda p, b: np.where(((p[:, 0] * s > 0.2) & (np.abs(p[:, 1]) < 0.6))[:, None], b * 0.8, b)))(sx)
        prims.append(ear)
    # neck
    prims.append(Prim((0, neck_top - neck_len / 2 - 0.15, -0.05), (0.42 * (1 + 0.3 * (W_ - 1)), neck_len / 2 + 0.4, 0.40), skin * 0.93, mat="skin", group="body"))
    # ---- hair ----
    HX, HY, HZ = hx * 1.07, hy * 1.07, hz * 1.07
    style, tex = P["hair_style"], P["hair_texture"]

    def hairline(front_y, side_y, back_y):
        def f(p):
            z = p[:, 2] if p.ndim == 2 else p[..., 2]
            y = p[:, 1] if p.ndim == 2 else p[..., 1]
            lim = np.where(z > 0, side_y + (front_y - side_y) * z, side_y + (side_y - back_y) * z)
            return y > lim
        return f

    def strands(p, base):
        az = np.arctan2(p[:, 0], p[:, 2])
        k = 1 + 0.10 * np.sin(az * 28 + p[:, 1] * 3) + 0.05 * np.sin(az * 61)
        if tex in ("curly", "coily"):
            k = 1 + 0.12 * np.sin(az * 40) * np.sin(p[:, 1] * 30)
        return base * k[:, None]
    hc = hairc
    if style == "wisps":
        prims.append(Prim(head_c + (0, 0.02, -0.02), (hx * 1.02, hy * 1.02, hz * 1.02), _mix(hc, skin, 0.35),
                          clip=hairline(0.62, 0.25, -0.35), paint=strands, mat="hair", group="hair"))
        prims.append(Prim((0.15, hy * 1.0, 0.25), (0.08, 0.28, 0.08), hc, R=_rotz(-25), mat="hair", group="hair"))
    elif style in ("bald",):
        pass
    elif style == "buzz":
        prims.append(Prim(head_c, (hx * 1.02, hy * 1.02, hz * 1.02), _mix(hc, skin, 0.25), clip=hairline(0.5, 0.05, -0.5), mat="hair", group="hair"))
    elif style == "afro":
        def afro_clip(p):
            z, y = p[..., 2], p[..., 1]
            return ~((z > 0.0) & ((p[..., 0] / 0.6) ** 2 + ((y + 0.66) / 0.62) ** 2 < 1))
        prims.append(Prim((0, 0.45, -0.35), (hx * 1.42, hy * 1.3, hz * 1.3), hc, clip=afro_clip, paint=strands, mat="hair", group="hair"))
    elif style == "towel":
        prims.append(Prim((0, 0.62, -0.12), (hx * 1.18, hy * 0.95, hz * 1.15), hc, clip=hairline(0.15, -0.2, -0.6), paint=strands, mat="cloth", group="hair"))
        prims.append(Prim((0, 1.45, -0.25), (0.75, 0.55, 0.72), hc, R=_rotz(12), paint=strands, mat="cloth", group="hair"))
    else:
        fy = {"spiky": 0.55, "mohawk": 0.9}.get(style, 0.42)
        prims.append(Prim(head_c, (HX, HY, HZ), hc, clip=hairline(fy, 0.0 if style != "mohawk" else 0.9, -0.55), paint=strands, mat="hair", group="hair"))
        if style in ("long", "bob", "curly"):
            # locks framing the face sides
            for sx in (-1, 1):
                prims.append(Prim((sx * hx * 0.93, -0.35, -0.05), (0.16, 0.85 if style in ("long", "curly") else 0.55, 0.5), hc,
                                  R=_rotz(sx * 6), paint=strands, mat="hair", group="hair"))
        if style == "long":
            prims.append(Prim((0, -1.05, -0.38), (hx * 1.12, 1.7, 0.6), hc, paint=strands, mat="hair", group="hair"))
        if style == "curly":
            prims.append(Prim((0, -0.45, -0.32), (hx * 1.22, 1.15, 0.75), hc, paint=strands, mat="hair", group="hair"))
            for k in range(22):
                a = k / 22 * 2 * math.pi
                prims.append(Prim((math.cos(a) * hx * 1.02, 0.25 + 0.75 * math.sin(a) ** 2, math.sin(a) * hz * 0.9 - 0.15),
                                  (0.32, 0.32, 0.32), hc, paint=strands, mat="hair", group="hair"))
        if style == "bob":
            prims.append(Prim((0, -0.35, -0.3), (hx * 1.14, 0.95, 0.72), hc, paint=strands, mat="hair", group="hair"))
        if style == "bun":
            prims.append(Prim((0, 0.95, -0.55), (0.55, 0.5, 0.55), hc, paint=strands, mat="hair", group="hair"))
        if style == "ponytail":
            prims.append(Prim((0, 0.35, -1.05), (0.28, 0.28, 0.28), hc, mat="hair", group="hair"))
            prims.append(capsule((0, 0.3, -1.15), (0, -1.6, -1.25), 0.32, hc, mat="hair", group="hair"))
        if style == "pigtails":
            for sx in (-1, 1):
                prims.append(capsule((sx * 1.15, 0.2, -0.4), (sx * 1.45, -1.3, -0.4), 0.3, hc, mat="hair", group="hair"))
        if style == "spiky":
            for k in range(9):
                a = -1.1 + k * 0.275
                d = np.array([math.sin(a) * 0.9, math.cos(a), -0.35])
                prims.append(capsule(d * 0.8, d * 1.65, 0.2, hc, mat="hair", group="hair"))
        if style == "mohawk":
            for k in range(5):
                zz = 0.6 - k * 0.38
                prims.append(capsule((0, 0.8, zz), (0, 1.75, zz - 0.15), 0.18, hc, mat="hair", group="hair"))
    # beard volume
    if P["beard"] == "full":
        prims.append(Prim((0, -0.25, 0.05), (hx * 1.03, hy * 0.98, hz * 1.03), hc,
                          clip=lambda p: ((p[..., 1] < -0.36) | ((p[..., 1] < 0.05) & (np.abs(p[..., 0]) > 0.62))) & (p[..., 2] > -0.45)
                          & ~(((p[..., 0] / 0.26) ** 2 + ((p[..., 1] + 0.43) / 0.075) ** 2 < 1) & (p[..., 2] > 0)),
                          paint=strands, mat="hair", group="hair"))
    # hats
    hatc = P["hat_color"]
    if P["hat"] == "cap":
        prims.append(Prim(head_c + (0, 0.05, 0), (HX * 1.03, HY * 1.03, HZ * 1.03), hatc, clip=lambda p: p[..., 1] > 0.35, mat="cloth", group="hat"))
        prims.append(Prim((0, 0.42 * hy, 0.95 * hz), (0.75, 0.05, 0.55), hatc, mat="cloth", group="hat"))
    elif P["hat"] == "beanie":
        prims.append(Prim(head_c + (0, 0.1, -0.02), (HX * 1.05, HY * 1.1, HZ * 1.05), hatc, clip=lambda p: p[..., 1] > 0.28,
                          paint=lambda p, b: b * (1 + 0.08 * np.sign(np.sin(np.arctan2(p[:, 0], p[:, 2]) * 30)))[:, None], mat="cloth", group="hat"))
        prims.append(Prim((0, hy * 1.25, -0.05), (0.3, 0.3, 0.3), hatc, mat="cloth", group="hat"))
    elif P["hat"] == "crown":
        for k in range(5):
            a = -0.9 + k * 0.45
            prims.append(capsule((math.sin(a) * 0.55, hy * 0.95, math.cos(a) * 0.25 - 0.1), (math.sin(a) * 0.6, hy * 1.45, math.cos(a) * 0.25 - 0.1),
                                 0.12, (250, 205, 40), mat="shiny", group="hat"))
        prims.append(Prim((0, hy * 1.0, -0.08), (0.72, 0.16, 0.5), (250, 205, 40), mat="shiny", group="hat"))
    elif P["hat"] == "bow":
        for sx in (-1, 1):
            prims.append(Prim((sx * 0.35, hy * 1.02, 0.15), (0.35, 0.22, 0.12), hatc, R=_rotz(sx * 20), mat="cloth", group="hat"))
        prims.append(Prim((0, hy * 1.02, 0.18), (0.13, 0.13, 0.13), hatc, mat="cloth", group="hat"))
    elif P["hat"] == "headband":
        prims.append(Prim(head_c, (HX * 1.02, HY * 1.02, HZ * 1.02), hatc, clip=lambda p: np.abs(p[..., 1] - 0.55) < 0.1, mat="cloth", group="hat"))
    # ---- body ----
    pat, patc = P["top_pattern"], np.array(P["pattern_color"], float)

    def cloth_paint(p, base):
        out = base.copy()
        if pat == "stripes":
            m = np.sin(p[:, 1] * 14) > 0.3
            out[m] = patc
        elif pat in ("spots", "dots"):
            az = np.arctan2(p[:, 0], p[:, 2])
            m = (np.sin(az * 9) * np.sin(p[:, 1] * 9)) > 0.75
            out[m] = patc
        if P["top"] == "jacket":                            # zip + lapels
            az = np.arctan2(p[:, 0], p[:, 2])
            out[(np.abs(az) < 0.03) & (p[:, 2] > 0)] = (205, 205, 210)
            lap = (np.abs(np.abs(az) - (0.12 + 0.25 * np.clip(p[:, 1], 0, 1))) < 0.03) & (p[:, 1] > -0.1) & (p[:, 2] > 0)
            out[lap] = out[lap] * 0.6
        if P["top"] in ("jumper", "sweater", "hoodie"):   # ribbed knit
            az = np.arctan2(p[:, 0], p[:, 2])
            out = out * (1 + 0.04 * np.sign(np.sin(az * 70)))[:, None]
        return out
    sleeve_skin = P["top"] in ("t-shirt", "tshirt", "vest", "dress")
    prims.append(Prim(torso_c + (0, torso_h * 0.12, 0), (tw * 0.98, torso_h * 0.42, td), top, paint=cloth_paint, mat="cloth", group="body"))
    prims.append(Prim(torso_c + (0, -torso_h * 0.18, 0), (tw * (0.80 + 0.12 * (W_ - 1)), torso_h * 0.40, td * 0.95), top, paint=cloth_paint, mat="cloth", group="body"))
    if P["belly"] > 0.05:
        b = P["belly"]
        prims.append(Prim(torso_c + (0, -torso_h * 0.18, td * 0.25), (tw * 0.9, torso_h * 0.36, td * (0.85 + 0.35 * b)), top, paint=cloth_paint, mat="cloth", group="body"))
    for sx in (-1, 1):
        prims.append(Prim((sx * tw * 0.74, sh_y - 0.22, 0), (0.42 * W_ ** 0.5 * P["shoulders"], 0.36, 0.42), top, paint=cloth_paint, mat="cloth", group="body"))
    # collar
    if P["top"] in ("jumper", "sweater", "t-shirt", "tshirt", "dress", "onesie"):
        prims.append(Prim((0, sh_y + 0.12, 0.02), (0.6 * (1 + 0.3 * (W_ - 1)), 0.16, 0.5), _mix(top, (255, 255, 255), 0.12) if P["top"] != "jumper" else top * 0.92, mat="cloth", group="body"))
    if P["top"] == "hoodie":
        prims.append(Prim((0, sh_y + 0.25, -0.55), (0.95, 0.55, 0.55), top * 0.94, mat="cloth", group="hood"))
        for sx in (-1, 1):
            prims.append(capsule((sx * 0.22, sh_y + 0.05, td * 0.95), (sx * 0.24, sh_y - 0.75, td * 1.0), 0.05, (245, 245, 245), group="body"))
    if P["bib"]:
        prims.append(Prim((0, sh_y - 0.25, td * 0.55), (0.9, 0.75, 0.45), P["bib_color"],
                          clip=lambda p: p[..., 1] < 0.6, mat="cloth", group="bib"))
    # arms + hands
    ar = 0.25 * W_ ** 0.7 * (0.85 if age == "baby" else 1)
    hs = 0.25 * P["hands"] * (0.85 if age == "baby" else 1)
    for sx in (-1, 1):
        S = np.array([sx * tw * 0.82, sh_y - 0.25, 0.0])
        if pose == "drive":
            E = np.array([sx * (tw * 0.95 + 0.1), sh_y - 1.35 * body_k - 0.3, 0.75])
            Hn = np.array([sx * 0.78, sh_y - 1.45 * body_k - 0.25, 1.95])
        elif pose == "cheer":
            E = np.array([sx * (tw + 0.5), sh_y + 0.6, 0.2])
            Hn = np.array([sx * (tw + 0.75), sh_y + 1.9, 0.35])
        elif pose == "fold":
            E = np.array([sx * (tw + 0.15), sh_y - 1.3 * body_k, 0.6])
            Hn = np.array([-sx * 0.55, sh_y - 1.05 * body_k, td + 0.35])
        else:   # stand
            E = np.array([sx * (tw + 0.1), sh_y - 1.4 * body_k, 0.0])
            Hn = np.array([sx * (tw + 0.15), sh_y - 2.7 * body_k, 0.15])
        upper = top
        lower = skin if sleeve_skin else top
        if sleeve_skin:
            mid = S + (E - S) * 0.55
            prims.append(capsule(S, mid, ar * 1.08, top, group="arm%d" % sx))
            prims.append(capsule(mid, E, ar * 0.9, skin, mat="skin", group="arm%d" % sx))
        else:
            prims.append(capsule(S, E, ar, upper, group="arm%d" % sx))
        prims.append(capsule(E, Hn, ar * 0.9, lower, mat="skin" if sleeve_skin else "cloth", group="arm%d" % sx))
        prims.append(Prim(Hn, (hs, hs * 1.1, hs * 1.05), skin, mat="skin", group="hand%d" % sx))
        prims.append(Prim(Hn + np.array([-sx * hs * 0.7, hs * 0.3, hs * 0.3]), (hs * 0.38, hs * 0.55, hs * 0.38), skin,
                          R=_rotz(sx * 40), mat="skin", group="hand%d" % sx))      # thumb
    info = {"crown": hy * 1.1 + (0.9 if style in ("afro", "towel", "bun") else 0.5 if style in ("spiky", "mohawk") else 0.15) +
            (0.45 if P["hat"] in ("crown", "beanie") else 0),
            "seat": seat_y, "torso_c": torso_c, "tw": tw, "td": td, "body_k": body_k, "sh_y": sh_y}
    if pose == "stand":
        hip = torso_c[1] - torso_h * 0.45
        leg = 2.9 * body_k * (P["height_cm"] / 172) ** 0.3
        lr = 0.42 * W_ ** 0.7 * (0.9 if age == "baby" else 1)
        tc = np.array(P["trousers_color"], float)
        for sx in (-1, 1):
            Hp = np.array([sx * tw * 0.42, hip, 0])
            K = np.array([sx * tw * 0.44, hip - leg * 0.5, 0.08])
            A = np.array([sx * tw * 0.45, hip - leg, 0])
            prims.append(capsule(Hp, K, lr, tc, group="leg%d" % sx))
            prims.append(capsule(K, A, lr * 0.88, tc, group="leg%d" % sx))
            f = P["feet"] * (0.8 if age == "baby" else 1)
            prims.append(Prim(A + np.array([0, -0.18, 0.25 * f]), (0.36 * f, 0.24, 0.62 * f), P["shoes_color"], mat="shiny", group="foot%d" % sx))
        info["feet"] = hip - leg - 0.45
    return prims, info


def frame_box(info, W, H, pad=0.03, top_extra=0.0):
    y1 = info["crown"] + 0.15 + top_extra
    y0 = info["seat"]
    h = (y1 - y0) / (1 - pad)
    y1 = y0 + h
    w = h * W / H
    return -w / 2, w / 2, y0, y1


def draw_sheet_cells(P, FW=512, FH=640, angles=(0, 45, 90, 135, 180, 225, 270, 315), log=print):
    prims, info = build(P, "drive")
    x0, x1, y0, y1 = frame_box(info, FW, FH)
    cells = {}
    for a in angles:
        cells[a] = render(prims, a, FW, FH, x0, x1, y0, y1)
    return cells


def draw_win(P, style, FW=512, FH=640):
    pose = "cheer" if style != "sleepy" else "fold"
    expr = "happy" if style != "sleepy" else "sleepy"
    prims, info = build(P, pose, expr)
    x0, x1, y0, y1 = frame_box(info, FW, FH, top_extra=1.4 if pose == "cheer" else 0)
    im = render(prims, 15, FW, FH, x0, x1, y0, y1)
    fy = (y1 - 0.25) / (y1 - y0)
    return im, (0.5, max(0.05, min(0.95, (y1 - 0.4) / (y1 - y0))))


def draw_standing(P, W=420, H=640, angle=20, expr=None):
    prims, info = build(P, "stand", expr)
    y0 = info["feet"] - 0.1
    y1 = info["crown"] + 0.2
    h = y1 - y0
    w = h * W / H
    return render(prims, angle, W, H, -w / 2, w / 2, y0, y1)


def draw_portrait(P, size=256):
    prims, info = build(P, "drive")
    c = 0.1
    r = 2.3 if P["hair_style"] not in ("afro", "towel") else 2.9
    return render(prims, 18, size, size, -r, r, c - r * 0.9, c + r * 1.1)


def size_for(P):
    """in-game card height (world units) for the driver: taller people sit taller"""
    return round(max(0.95, min(1.6, 0.92 + 0.0029 * (P["height_cm"] - 80))), 2)
