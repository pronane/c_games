"""HD renderer for the mannequin (numpy only): z-buffered, smooth (angle-limited) vertex normals, soft
key/fill/rim lighting with a little specular, inner ink lines between body parts, supersampled.
Enabled with SFORGE_HD=1 (or RenderSettings.hd = True).  Same camera / anchor maths as render.render_tris."""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageFilter
from .rig import HEIGHT
from .mathutil import ry, rx
from .mesh import MATS, DECAL_BIAS
_BIAS = np.array([DECAL_BIAS.get(m, 0.0) for m in MATS])

_GROUPS = {}


def _groups(P_rest_key, Q):
    """corner -> smooth-group index. Cached per triangle count; groups come from the first posed mesh seen with
    that count (topology is fixed, only positions move) - rounded in the *first* pose, reused after."""
    g = _GROUPS.get(P_rest_key)
    if g is None:
        flat = np.round(Q.reshape(-1, 3) * 2000).astype(np.int64)
        _, inv = np.unique(flat, axis=0, return_inverse=True)
        g = inv.reshape(-1).astype(np.int64)
        _GROUPS[P_rest_key] = g
    return g


def corner_normals(Q, N, area, groups, cos_lim=0.62):
    n = len(Q)
    S = np.zeros((groups.max() + 1, 3))
    W = (N * area[:, None])
    np.add.at(S, groups, np.repeat(W, 3, axis=0))
    Sn = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-12)
    CN = Sn[groups].reshape(n, 3, 3)
    ok = (CN * N[:, None, :]).sum(-1, keepdims=True) > cos_lim
    return np.where(ok, CN, N[:, None, :])


def render_hd(P, mats, colors, rs, root_xz=(0, 0), key=None):
    view = rx(rs.pitch) @ ry(rs.yaw)
    Q = P.copy()
    if rs.follow_root:
        Q[..., 0] -= root_xz[0]; Q[..., 2] -= root_xz[1]
    Q = Q @ view.T
    ss = max(rs.ss, 2)
    scale = rs.figure_h / HEIGHT * ss
    W, H = rs.cell_w * ss, rs.cell_h * ss
    sx = rs.anchor_x * ss + Q[..., 0] * scale
    sy = rs.baseline * ss - Q[..., 1] * scale
    e1 = Q[:, 1] - Q[:, 0]; e2 = Q[:, 2] - Q[:, 0]
    N = np.cross(e1, e2); area = np.linalg.norm(N, axis=1) + 1e-12; N = N / area[:, None]
    groups = _groups(key if key is not None else len(Q), Q)
    CN = corner_normals(Q, N, area, groups)
    mats = np.asarray(mats)
    lut = {}
    base = np.array([lut.setdefault(m, colors[MATS[m]]) for m in mats.tolist()], dtype=float).reshape(-1, 3)
    skin_like = np.array([MATS[m] in ("skin",) for m in mats.tolist()])
    zbuf = np.full((H, W), -1e9)
    col = np.zeros((H, W, 3))
    idb = np.full((H, W), -1, np.int32)
    L = np.array(rs.light, float)
    L2 = np.array([0.55, 0.15, 0.6]); L2 /= np.linalg.norm(L2)         # cool fill from the right/front
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    zb = _BIAS[mats]
    front = N[:, 2] > 0
    for t in np.nonzero(front)[0]:
        xs, ys = sx[t], sy[t]
        x0 = max(int(xs.min()), 0); x1 = min(int(xs.max()) + 1, W - 1)
        y0 = max(int(ys.min()), 0); y1 = min(int(ys.max()) + 1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        b = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        c = 1 - a - b
        m = (a >= -0.02) & (b >= -0.02) & (c >= -0.02)
        if not m.any():
            continue
        z = a * Q[t, 0, 2] + b * Q[t, 1, 2] + c * Q[t, 2, 2] + zb[t]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        m &= z > sub
        if not m.any():
            continue
        n = a[..., None] * CN[t, 0] + b[..., None] * CN[t, 1] + c[..., None] * CN[t, 2]
        n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
        ndl = n @ L
        diff = np.clip(ndl * 0.5 + 0.5, 0, 1) ** 1.35                    # wrapped, soft terminator
        fill = np.clip(n @ L2, 0, 1) * 0.18
        rim = np.clip(1 - n[..., 2], 0, 1) ** 2.6 * 0.38
        spec = np.clip(n @ Hh, 0, 1) ** (18 if skin_like[t] else 34) * (0.20 if skin_like[t] else 0.12)
        shade = rs.ambient * 0.8 + (1 - rs.ambient * 0.8) * diff + fill
        rgb = np.clip(base[t] * shade[..., None] + rim[..., None] * np.array([0.55, 0.65, 0.9]) * 0.6 + spec[..., None], 0, 1)
        sc = col[y0:y1 + 1, x0:x1 + 1]; si = idb[y0:y1 + 1, x0:x1 + 1]
        sc[m] = rgb[m]; sub[m] = z[m]; si[m] = mats[t]
    alpha = (zbuf > -1e8)
    # ink lines: silhouette + depth/material discontinuities inside the figure
    zz = np.where(alpha, zbuf, zbuf[alpha].min() - 1 if alpha.any() else 0)
    gxz = np.abs(np.diff(zz, axis=1, prepend=zz[:, :1])); gyz = np.abs(np.diff(zz, axis=0, prepend=zz[:1]))
    edge_z = (gxz > 0.035) | (gyz > 0.035)
    ids = idb
    edge_id = (np.diff(ids, axis=1, prepend=ids[:, :1]) != 0) | (np.diff(ids, axis=0, prepend=ids[:1]) != 0)
    ink = (edge_z & alpha) | (edge_id & alpha)
    ink_img = Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3 if ss >= 3 else 1)) if ss >= 3 else Image.fromarray((ink * 255).astype(np.uint8))
    inkm = np.asarray(ink_img) > 0
    out = np.zeros((H, W, 4), np.uint8)
    rgb8 = (col * 255).astype(np.uint8)
    inkc = np.array(rs.outline_rgb, np.uint8)
    rgb8[inkm & alpha] = (rgb8[inkm & alpha] * 0.35 + inkc * 0.65).astype(np.uint8)
    out[..., :3] = rgb8
    out[..., 3] = np.where(alpha, 255, 0)
    img = Image.fromarray(out, "RGBA")
    # outer outline
    a = img.getchannel("A")
    grow = a.filter(ImageFilter.MaxFilter(2 * ss // 2 * 2 + 1 if ss > 2 else 3))
    under = Image.new("RGBA", img.size, tuple(rs.outline_rgb) + (0,)); under.putalpha(grow)
    img = Image.alpha_composite(under, img)
    # premultiplied downscale (avoids dark fringes)
    arr = np.asarray(img).astype(np.float32); al = arr[..., 3:4] / 255.0
    pm = Image.fromarray(np.concatenate([arr[..., :3] * al, arr[..., 3:4]], -1).astype(np.uint8), "RGBA") if False else None
    img = img.resize((rs.cell_w, rs.cell_h), Image.LANCZOS)
    return img
