"""v11.22 sprite drawing for rigs with any number of textures (MakeHuman looks, captures, downloaded or Meshy models).

Before, a rig with more than one texture (skin, hair, kit, eyes...) was drawn one flat colour per triangle, sampled
at the triangle's centre, and lit per triangle: blotchy patches, a faceted, blocky body, the shirt number gone.
Now every pixel is drawn from its own texture:

  * z-buffered, supersampled (to about 640 px tall: 4x for a 160 px cell, 2x for an HD one), every material's texture sampled bilinearly from a pre-shrunk copy
    (so a 2048 px texture on a 100 px sprite does not shimmer);
  * smooth lighting: normals blended across each surface (hard creases above ~50 degrees kept), a key light, a soft
    fill from below and a little rim light - the same light direction as the other renderers;
  * alpha-tested hair, brow and lash cards in a second layer: a card's see-through pixels show what is behind;
  * the kit recolours materials the same way as before (sforge.kits rules via Rig.kit_texture).
Same framing (anchor, ground line, follow_root) and outline as render.render_tris, so frames line up with every
other path.
"""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageFilter

from .rig import HEIGHT
from .mathutil import ry, rx

TEX_MAX = 512           # textures are shrunk to this before sampling (a sprite is ~100-400 px tall)


def ss_for(cell_h):
    """supersampling: to ~640 px tall (4x for a 160 px cell, 2x for an HD 320 px cell) - smooth edges, steady cost"""
    return max(2, min(4, int(round(640.0 / max(1, cell_h)))))


def shrink(img, side=TEX_MAX):
    """PIL image -> float32 RGBA (h, w, 4) 0..1, at most `side` px (box-filtered, which is what a mip level is)"""
    im = img.convert("RGBA")
    if max(im.size) > side:
        k = side / float(max(im.size))
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BOX)
    return np.asarray(im, np.float32) / 255.0


def sample(tex, uv):
    """bilinear sample of (h,w,4) at uv (n,2), v = 0 is the top row (glTF)"""
    th, tw = tex.shape[:2]
    x = np.clip(np.mod(uv[:, 0], 1.0) * tw - 0.5, 0, tw - 1.001)
    y = np.clip(np.mod(uv[:, 1], 1.0) * th - 0.5, 0, th - 1.001)
    x0 = x.astype(int); y0 = y.astype(int); fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    x1 = np.minimum(x0 + 1, tw - 1); y1 = np.minimum(y0 + 1, th - 1)
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy)
            + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)


def smooth_groups(Vbind, decimals=4):
    """vertex -> group of vertices at the same bind position (UV seams split vertices; their normals are shared)"""
    key = np.round(np.asarray(Vbind, float) * 10 ** decimals).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.reshape(-1)


def corner_normals(Vp, F, groups, cos_lim=0.62):
    """(nf,3,3) per-corner normals of the posed mesh: area-weighted, shared across seams, creases kept"""
    P = Vp[F]
    N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    Nf = N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
    S = np.zeros((groups.max() + 1, 3))
    np.add.at(S, np.repeat(groups[F].reshape(-1, 3), 1, axis=0).ravel(), np.repeat(N, 3, axis=0))
    Sn = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-12)
    CN = Sn[groups[F]]                                                     # (nf,3,3)
    ok = (CN * Nf[:, None, :]).sum(-1, keepdims=True) > cos_lim
    return np.where(ok, CN, Nf[:, None, :]), Nf


def _raster(sx, sy, sz, F, W, H):
    from .render_sculpt import rasterise
    if not len(F):
        return np.full((H, W), -1, np.int64), np.zeros((H, W, 3)), np.full((H, W), -1e9)
    tid, bc, z = rasterise(sx, sy, sz, F, W, H, K=6)
    return tid.reshape(H, W), np.asarray(bc).reshape(H, W, 3), np.asarray(z).reshape(H, W)


def render_rich(P, fuv, fmat, mats, face_rgb, CN, rs, root_xz=(0, 0), ss=None, ambient=0.5):
    """P (nf,3,3) posed triangles; fuv (nf,3,2) or None; fmat (nf,) material per face; mats: list per material of
    dict(tex=(h,w,4) float or None, alpha=bool); face_rgb (nf,3) colour for untextured faces; CN (nf,3,3) corner
    normals in world space. -> RGBA image cell_w x cell_h"""
    ss = int(ss or ss_for(rs.cell_h))
    view = rx(rs.pitch) @ ry(rs.yaw)
    Q = P.copy()
    if rs.follow_root:
        Q[..., 0] -= root_xz[0]; Q[..., 2] -= root_xz[1]
    Q = Q @ view.T
    Nv = CN @ view.T                                                       # normals in view space
    scale = rs.figure_h / HEIGHT * ss
    W, H = rs.cell_w * ss, rs.cell_h * ss
    sx = (rs.anchor_x * ss + Q[..., 0] * scale).reshape(-1)
    sy = (rs.baseline * ss - Q[..., 1] * scale).reshape(-1)
    sz = Q[..., 2].reshape(-1)
    nf = len(P)
    is_card = np.array([bool(mats[m]["alpha"]) if 0 <= m < len(mats) else False for m in fmat], bool) if nf else np.zeros(0, bool)
    out = np.zeros((H, W, 4), np.float32)
    zbuf = np.full((H, W), -1e9)
    L = np.asarray(rs.light, float); L = L / np.linalg.norm(L)
    fill = np.array([0.3, -0.5, 0.8]); fill /= np.linalg.norm(fill)

    def shade_px(t, bc):
        n = (bc[:, :, None] * Nv[t]).sum(1)
        n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
        n = n * np.where(n[:, 2:3] < 0, -1.0, 1.0)                        # two-sided
        key = np.clip(n @ L, 0, 1)
        fl = np.clip(n @ fill, 0, 1)
        rim = np.clip(1 - n[:, 2], 0, 1) ** 3
        s = ambient + (1 - ambient) * key + 0.12 * fl
        s = s / (ambient + (1 - ambient) * 0.8)                            # a surface facing the light keeps its colour
        return s, rim

    def colour_px(t, bc):
        col = np.zeros((len(t), 4), np.float32)
        col[:, 3] = 1.0
        col[:, :3] = face_rgb[t]
        if fuv is not None:
            uv = (bc[:, :, None] * fuv[t]).sum(1)
            mt = fmat[t]
            for mi in np.unique(mt):
                tex = mats[mi]["tex"] if 0 <= mi < len(mats) else None
                if tex is None:
                    continue
                sel = mt == mi
                c = sample(tex, uv[sel])
                col[sel, :3] = c[:, :3] * mats[mi].get("tint", 1.0)
                col[sel, 3] = c[:, 3] if mats[mi]["alpha"] else 1.0
        return col

    for layer in (False, True):                                            # opaque surfaces, then alpha cards
        idx = np.nonzero(is_card == layer)[0]
        if not len(idx):
            continue
        F = (idx[:, None] * 3 + np.arange(3)[None, :])
        tid, bc, z = _raster(sx, sy, sz, F, W, H)
        m = tid >= 0
        if layer:
            m &= z > zbuf
        if not m.any():
            continue
        t = idx[tid[m]]
        b = bc[m]
        col = colour_px(t, b)
        s, rim = shade_px(t, b)
        rgb = np.clip(col[:, :3] * s[:, None] + 0.10 * rim[:, None], 0, 1)
        a = col[:, 3]
        if layer:
            keep = a >= 0.5
            ys, xs = np.nonzero(m)
            ys, xs, rgb = ys[keep], xs[keep], rgb[keep]
            out[ys, xs, :3] = rgb
            out[ys, xs, 3] = 1.0
        else:
            out[m, :3] = rgb
            out[m, 3] = 1.0
            zbuf[m] = z[m]
    img = Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")
    if ss != 1:
        img = img.resize((rs.cell_w, rs.cell_h), Image.LANCZOS)
    if rs.outline:
        a = img.getchannel("A")
        grow = a.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
        under = Image.new("RGBA", img.size, rs.outline_rgb + (0,))
        under.putalpha(grow)
        img = Image.alpha_composite(under, img)
    return img
