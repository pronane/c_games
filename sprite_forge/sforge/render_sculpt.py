"""Renderer for sculpted characters (v10, numpy only).

Vectorised rasteriser for dense meshes (every small triangle is tested against the pixels of its bounding box in one
array pass; the few large triangles, e.g. a sword blade, fall back to a loop), then deferred shading per pixel:
  * paints evaluated per pixel at the interpolated bind-pose position (texture-sharp faces, prints and logos)
  * soft key light with a painterly terminator, cool fill, warm sub-surface tint on skin
  * coloured rim lights on both silhouette edges, Blinn specular per material, hair sheen
  * screen-space ambient occlusion from the depth buffer (muscle and fold definition)
  * emissive paints + bloom, energy glow emitters (fx)
  * ink: outer silhouette line plus inner lines from depth, crease and layer (garment / skin) edges
Supersampled, then downscaled with premultiplied alpha."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageFilter
from .rig import HEIGHT
from .mathutil import ry, rx
from . import sculpt as SC


class SculptSettings:
    def __init__(self, cell_w=192, cell_h=256, figure_h=158.0, baseline=244, anchor_x=92, yaw=90.0, pitch=4.0, ss=3,
                 light=(-0.30, 0.62, 0.72), outline=(18, 14, 20), ink=1.0, ao=0.55, rim=1.0, shadows=True, cavity=0.35):
        self.cell_w, self.cell_h, self.figure_h = cell_w, cell_h, figure_h
        self.baseline, self.anchor_x, self.yaw, self.pitch, self.ss = baseline, anchor_x, yaw, pitch, ss
        L = np.array(light, float); self.light = L / np.linalg.norm(L)
        self.outline, self.ink, self.ao, self.rim, self.shadows, self.cavity = outline, ink, ao, rim, shadows, cavity


def view_matrix(rs):
    return rx(rs.pitch) @ ry(rs.yaw)


def project(P, rs, scale_mul=1.0):
    view = view_matrix(rs)
    Q = P @ view.T
    ss = rs.ss
    scale = rs.figure_h * scale_mul / HEIGHT * ss
    sx = rs.anchor_x * ss + Q[:, 0] * scale
    sy = rs.baseline * ss - Q[:, 1] * scale
    return sx, sy, Q[:, 2], view


def rasterise(sx, sy, sz, F, W, H, K=5):
    """-> tri id per pixel (-1 empty), barycentrics (H,W,3), depth (H,W)"""
    tx = sx[F]; ty = sy[F]; tz = sz[F]
    x0 = np.floor(tx.min(1)).astype(np.int64); y0 = np.floor(ty.min(1)).astype(np.int64)
    x1 = np.ceil(tx.max(1)).astype(np.int64); y1 = np.ceil(ty.max(1)).astype(np.int64)
    d = (ty[:, 1] - ty[:, 2]) * (tx[:, 0] - tx[:, 2]) + (tx[:, 2] - tx[:, 1]) * (ty[:, 0] - ty[:, 2])
    ok = np.abs(d) > 1e-12
    small = ok & ((x1 - x0) <= K) & ((y1 - y0) <= K)
    big = np.nonzero(ok & ~small)[0]
    best_z = np.full(H * W, -1e9); best_t = np.full(H * W, -1, np.int64)
    best_b = np.zeros((H * W, 3))

    def consider(t, px, py):
        # t, px, py: flat candidate arrays
        inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        t, px, py = t[inb], px[inb], py[inb]
        gx, gy = px + 0.5, py + 0.5
        X, Y, dd = tx[t], ty[t], d[t]
        a = ((Y[:, 1] - Y[:, 2]) * (gx - X[:, 2]) + (X[:, 2] - X[:, 1]) * (gy - Y[:, 2])) / dd
        b = ((Y[:, 2] - Y[:, 0]) * (gx - X[:, 2]) + (X[:, 0] - X[:, 2]) * (gy - Y[:, 2])) / dd
        c = 1 - a - b
        m = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        if not m.any():
            return
        t, px, py, a, b, c = t[m], px[m], py[m], a[m], b[m], c[m]
        z = a * tz[t, 0] + b * tz[t, 1] + c * tz[t, 2]
        pix = py * W + px
        order = np.lexsort((-z, pix))
        pix, z, t, a, b, c = pix[order], z[order], t[order], a[order], b[order], c[order]
        first = np.ones(len(pix), bool); first[1:] = pix[1:] != pix[:-1]
        pix, z, t, a, b, c = pix[first], z[first], t[first], a[first], b[first], c[first]
        win = z > best_z[pix]
        pix, z, t = pix[win], z[win], t[win]
        best_z[pix] = z; best_t[pix] = t
        best_b[pix] = np.stack([a[win], b[win], c[win]], 1)

    st = np.nonzero(small)[0]
    for dy in range(K + 1):
        for dx in range(K + 1):
            px = x0[st] + dx; py = y0[st] + dy
            keep = (px <= x1[st]) & (py <= y1[st])
            consider(st[keep], px[keep], py[keep])
    for t in big:
        xs = np.arange(max(x0[t], 0), min(x1[t] + 1, W)); ys = np.arange(max(y0[t], 0), min(y1[t] + 1, H))
        if len(xs) == 0 or len(ys) == 0:
            continue
        gx, gy = np.meshgrid(xs, ys)
        consider(np.full(gx.size, t), gx.ravel(), gy.ravel())
    return best_t.reshape(H, W), best_b.reshape(H, W, 3), best_z.reshape(H, W)


def shadow_term(Pp, F, P_pix, L_world, res=0.004, bias=0.012, soft=1.5):
    """key-light shadow map: orthographic depth along L from the posed mesh, PCF-filtered lookup for P_pix"""
    L = L_world / np.linalg.norm(L_world)
    up = np.array([0, 1.0, 0]) if abs(L[1]) < 0.95 else np.array([1.0, 0, 0])
    u = np.cross(up, L); u /= np.linalg.norm(u); v = np.cross(L, u)
    B = np.stack([u, v, L])                      # rows: light-space axes (z = towards the light)
    Q = Pp @ B.T
    lo = Q[:, :2].min(0) - 0.05
    sx = (Q[:, 0] - lo[0]) / res; sy = (Q[:, 1] - lo[1]) / res
    Wd = int(sx.max()) + 4; Hd = int(sy.max()) + 4
    tid, _, zmap = rasterise(sx, sy, Q[:, 2], F, Wd, Hd, K=4)
    zmap = np.where(tid >= 0, zmap, -1e9)
    q = P_pix @ B.T
    px = (q[:, 0] - lo[0]) / res; py = (q[:, 1] - lo[1]) / res
    lit = np.zeros(len(q))
    taps = [(dx, dy) for dx in (-soft, 0, soft) for dy in (-soft, 0, soft)]
    for dx, dy in taps:
        ix = np.clip((px + dx).astype(int), 0, Wd - 1); iy = np.clip((py + dy).astype(int), 0, Hd - 1)
        lit += (q[:, 2] + bias >= zmap[iy, ix])
    return lit / len(taps)


def _blur(a, r):
    if r <= 0:
        return a
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(a.astype(np.float32), r / 2.0)


def render_frame(ch, sm, state, rs: SculptSettings, cols=None):
    """posed SculptMesh -> RGBA cell image"""
    ss = rs.ss
    W, H = rs.cell_w * ss, rs.cell_h * ss
    Pp, Np = SC.skin_points(sm, state)
    sx, sy, sz, view = project(Pp, rs, ch.scale)
    Nv = Np @ view.T
    tid, bary, zb = rasterise(sx, sy, sz, sm.F, W, H)
    alpha = tid >= 0
    out = np.zeros((H, W, 4), np.float32)
    if not alpha.any():
        return Image.fromarray(out.astype(np.uint8), "RGBA").resize((rs.cell_w, rs.cell_h))
    idx = np.nonzero(alpha)
    t = tid[idx]; bc = bary[idx]
    vi = sm.F[t]                                   # (n,3)
    n = (Nv[vi] * bc[..., None]).sum(1)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    pb = (sm.V[vi] * bc[..., None]).sum(1)          # bind position for paint
    pw = (Pp[vi] * bc[..., None]).sum(1)            # posed world position (shadows)
    pick = vi[np.arange(len(vi)), np.argmax(bc, 1)]
    paint = sm.paint[pick]; mat = sm.mat[pick]; layer = sm.layer[pick]
    if cols is None:
        rgb, em = SC.vertex_colours(ch, sm, pb, paint)
    else:
        rgb, em = cols
    # ---------------- lighting (view space: x right, y up, z towards the camera)
    L = rs.light
    L2 = np.array([0.75, 0.10, 0.45]); L2 /= np.linalg.norm(L2)
    ndl = n @ L
    if rs.shadows:
        Lw = view.T @ L                                  # key light direction in world space
        sh = shadow_term(Pp, sm.F, pw, Lw)
        ndl = np.minimum(ndl, -0.25 + 1.25 * sh * np.maximum(ndl, 0) + (1 - sh) * 0.0) if False else ndl
        terminator_sh = sh
    else:
        terminator_sh = np.ones(len(n))
    terminator = np.clip((ndl + 0.18) / 0.55, 0, 1); terminator = terminator * terminator * (3 - 2 * terminator)
    terminator = terminator * (0.25 + 0.75 * terminator_sh)
    diff = 0.72 * terminator + 0.28 * np.clip(ndl * 0.5 + 0.5, 0, 1)
    bounce = np.clip(-n[:, 1], 0, 1) * 0.10                              # warm floor bounce
    fill = np.clip(n @ L2, 0, 1) * 0.22
    sky = (n[:, 1] * 0.5 + 0.5) * 0.12
    spec_s = np.array([SC.SHADING[m][0] for m in SC.MATS])[mat]
    shin = np.array([SC.SHADING[m][1] for m in SC.MATS])[mat]
    rimw = np.array([SC.SHADING[m][2] for m in SC.MATS])[mat]
    sss = np.array([SC.SHADING[m][3] for m in SC.MATS])[mat]
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    spec = np.clip(n @ Hh, 0, 1) ** shin * spec_s * (0.15 + 0.85 * terminator)
    # rims: back-left warm/char colour, back-right cool
    edge = np.clip(1 - np.abs(n[:, 2]), 0, 1) ** 2.4
    rim1 = edge * np.clip(-n[:, 0] * 0.8 + n[:, 1] * 0.4, 0, 1) * 0.85
    rim2 = edge * np.clip(n[:, 0] * 0.8 + n[:, 1] * 0.25, 0, 1) * 0.55
    rimc = np.array(ch.rim)
    # ambient occlusion from the depth buffer
    zfill = np.where(alpha, zb, np.nan)
    zz = np.where(alpha, zb, zb[alpha].min() - 0.3)
    occ = np.zeros_like(zz)
    for r, wgt in ((3 * ss, 0.5), (8 * ss, 0.5)):
        bl = _blur(zz, r)
        occ += wgt * np.clip((bl - zz) / (0.02 + 0.01 * r / ss), 0, 1)
    ao = 1 - rs.ao * np.clip(occ[idx], 0, 1)
    if sm.curv is not None:                          # cavity: creases darker, ridges catch light
        cv = (sm.curv[vi] * bc).sum(1)
        ao = ao * (1 + rs.cavity * np.clip(cv, -1, 1) * np.where(cv < 0, 1.0, 0.5))
    warm = np.array([1.0, 0.62, 0.48])
    shade = (0.20 + diff * 0.80 + fill + sky + bounce)
    col = rgb * shade[:, None] * ao[:, None]
    col += (sss * (1 - terminator) * terminator * 2.0)[:, None] * rgb * warm * 0.35
    col += (spec * ao)[:, None] * np.array([1.0, 0.97, 0.92])
    col += (rim1 * rimw * rs.rim)[:, None] * rimc * 0.95
    col += (rim2 * rimw * rs.rim)[:, None] * np.array([0.65, 0.75, 1.0]) * 0.6
    # hair: anisotropic band
    hair = mat == SC.MI["hair"]
    if hair.any():
        band = np.exp(-((n[hair, 1] - 0.55) / 0.18) ** 2) * 0.22
        col[hair] += band[:, None] * np.array([1.0, 0.98, 0.95])
    glow = mat == SC.MI["glow"]
    col = col * (1 - em[:, None]) + rgb * em[:, None] * 1.25
    img = np.zeros((H, W, 3), np.float32)
    img[idx] = np.clip(col, 0, 1.4)
    # bloom from emissive
    emi = np.zeros((H, W), np.float32); emi[idx] = em
    emc = np.zeros((H, W, 3), np.float32); emc[idx] = rgb * em[:, None]
    # ---------------- ink
    lay = np.full((H, W), -1, np.int32); lay[idx] = layer
    nn = np.zeros((H, W, 3), np.float32); nn[idx] = n
    dz_x = np.abs(np.diff(zz, axis=1, prepend=zz[:, :1])); dz_y = np.abs(np.diff(zz, axis=0, prepend=zz[:1]))
    thr = 0.045
    e_depth = (dz_x > thr) | (dz_y > thr)
    dn = 1 - (nn * np.roll(nn, 1, 1)).sum(-1); dn2 = 1 - (nn * np.roll(nn, 1, 0)).sum(-1)
    e_crease = (dn > 0.55) | (dn2 > 0.55)
    e_layer = (lay != np.roll(lay, 1, 1)) | (lay != np.roll(lay, 1, 0))
    ink = (e_depth | e_crease) & alpha
    soft = e_layer & alpha & ~ink
    ink_m = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
    soft_m = np.asarray(Image.fromarray((soft * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
    oc = np.array(rs.outline, np.float32) / 255.0
    img[soft_m & alpha] = img[soft_m & alpha] * 0.55 + oc * 0.45 * rs.ink
    img[ink_m & alpha] = img[ink_m & alpha] * 0.22 + oc * 0.78 * rs.ink
    # outer outline: grow the silhouette
    a8 = (alpha * 255).astype(np.uint8)
    grow = np.asarray(Image.fromarray(a8).filter(ImageFilter.MaxFilter(2 * ss + 1))) > 0
    ring = grow & ~alpha
    out[..., :3] = img
    out[..., 3] = alpha.astype(np.float32)
    out[ring, :3] = oc; out[ring, 3] = 1.0
    # glow: bloom of emissive + fx emitters (additive, also outside the body with alpha)
    glow_rgb = np.zeros((H, W, 3), np.float32)
    if emi.any():
        for r, k in ((2 * ss, 0.9), (6 * ss, 0.6)):
            glow_rgb += np.stack([_blur(emc[..., c], r) for c in range(3)], -1) * k
    if ch.fx:
        yy, xx = np.mgrid[0:H, 0:W]
        for bone, off, c, rad in ch.fx:
            Wm = state.world[bone]
            p = Wm[:3, :3] @ np.array(off) + Wm[:3, 3]
            px, py, pz, _ = project(p[None], rs, ch.scale)
            rpx = rad * rs.figure_h * ch.scale / HEIGHT * ss
            d2 = ((xx - px[0]) ** 2 + (yy - py[0]) ** 2) / (rpx * rpx)
            core = np.exp(-d2 * 6.0); halo = np.exp(-d2 * 1.6) * 0.55
            # wisps
            ang = np.arctan2(yy - py[0], xx - px[0])
            wisp = np.exp(-d2 * 1.2) * (0.5 + 0.5 * np.sin(ang * 5 + d2 * 9)) ** 6 * 0.6
            g = (core + halo + wisp)[..., None] * np.array(c, np.float32)
            g += core[..., None] * 0.5
            glow_rgb += g
    if glow_rgb.any():
        ga = np.clip(glow_rgb.max(-1), 0, 1)
        out[..., :3] = out[..., :3] * out[..., 3:4] + glow_rgb
        out[..., 3] = np.clip(out[..., 3] + ga * (1 - out[..., 3]), 0, 1)
        out[..., :3] = np.where(out[..., 3:4] > 1e-4, out[..., :3] / np.maximum(out[..., 3:4], 1e-4), 0)
    out[..., :3] = np.clip(out[..., :3], 0, 1)
    # premultiplied downscale
    pm = out.copy(); pm[..., :3] *= pm[..., 3:4]
    small = pm.reshape(rs.cell_h, ss, rs.cell_w, ss, 4).mean((1, 3))
    a = small[..., 3:4]
    rgbs = np.where(a > 1e-4, small[..., :3] / np.maximum(a, 1e-4), 0)
    res = np.concatenate([np.clip(rgbs, 0, 1), np.clip(a, 0, 1)], -1)
    im = Image.fromarray((res * 255 + 0.5).astype(np.uint8), "RGBA")
    return im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
