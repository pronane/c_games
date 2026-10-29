"""Software renderer (numpy + Pillow only, no GPU / Blender needed).

Flat-shaded low-poly look, painter's algorithm with back-face culling,
supersampled for anti-aliasing, optional dark outline.  Every frame is drawn
into a fixed cell with the feet on the same baseline and the root on the same
anchor column, so all moves share one scale and pivot."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .rig import JOINT_NAMES, rest_world, HEIGHT
from .mathutil import ry, rx, mat4
from .mesh import MATS

_BIND_INV = None


def bind_inverse():
    global _BIND_INV
    if _BIND_INV is None:
        J = rest_world()
        _BIND_INV = np.stack([np.linalg.inv(mat4(None, J[n])) for n in JOINT_NAMES])
    return _BIND_INV


def skin_matrices(state):
    W = []
    for n in JOINT_NAMES:
        if n == "ball":
            if state.ball_pos is None:
                W.append(np.zeros((4, 4)))
            else:
                W.append(mat4(None, state.ball_pos))
        else:
            W.append(state.world[n])
    return np.einsum("nij,njk->nik", np.stack(W), bind_inverse())


def pose_triangles(T, B, state):
    S = skin_matrices(state)
    M = S[B]                                            # (n,4,4)
    V = np.concatenate([T, np.ones(T.shape[:2] + (1,))], axis=2)  # (n,3,4)
    out = np.einsum("nij,nkj->nki", M, V)[..., :3]
    keep = np.abs(M).sum(axis=(1, 2)) > 0             # hidden ball
    return out, keep


class RenderSettings:
    def __init__(self, cell_w=256, cell_h=256, figure_h=190, baseline=None, anchor_x=None,
                 yaw=65.0, pitch=6.0, ss=3, outline=True, outline_rgb=(22, 24, 28), light=(-0.45, 0.75, 0.55),
                 ambient=0.42, follow_root=False):
        self.cell_w, self.cell_h, self.figure_h = cell_w, cell_h, figure_h
        self.baseline = baseline if baseline is not None else int(cell_h * 0.93)
        self.anchor_x = anchor_x if anchor_x is not None else cell_w // 2
        self.yaw, self.pitch, self.ss, self.outline = yaw, pitch, ss, outline
        self.outline_rgb, self.light, self.ambient = outline_rgb, np.array(light) / np.linalg.norm(light), ambient
        self.follow_root = follow_root


def render_tris(P, mats, colors, rs: RenderSettings, root_xz=(0, 0), wire=False, rgb=None, two_sided=False):
    """P: posed triangles (n,3,3) in world metres.  rgb: optional per-triangle colours (n,3) 0-1 (library rigs);
    two_sided: draw back faces too (imported meshes often have mixed winding)."""
    view = rx(rs.pitch) @ ry(rs.yaw)
    Q = P.copy()
    if rs.follow_root:
        Q[..., 0] -= root_xz[0]; Q[..., 2] -= root_xz[1]
    Q = Q @ view.T
    scale = rs.figure_h / HEIGHT * rs.ss
    W, H = rs.cell_w * rs.ss, rs.cell_h * rs.ss
    sx = rs.anchor_x * rs.ss + Q[..., 0] * scale
    sy = rs.baseline * rs.ss - Q[..., 1] * scale
    e1 = Q[:, 1] - Q[:, 0]; e2 = Q[:, 2] - Q[:, 0]
    N = np.cross(e1, e2); ln = np.linalg.norm(N, axis=1) + 1e-12; N = N / ln[:, None]
    front = N[:, 2] > 0 if not (wire or two_sided) else np.ones(len(N), bool)
    if two_sided:
        N = N * np.where(N[:, 2:3] < 0, -1.0, 1.0)
    depth = Q[..., 2].mean(axis=1)
    order = np.argsort(depth)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    ndl = np.clip(N @ rs.light, 0, 1)
    rim = np.clip(1 - N[:, 2], 0, 1) ** 3 * 0.15
    # v8: colours and screen points computed for all triangles at once (numpy), then one PIL call per triangle
    order = order[front[order]]
    pts_all = np.stack([sx[order], sy[order]], axis=-1).tolist()          # (n,3,2) python floats
    if wire:
        for pts in pts_all:
            pts = [tuple(p) for p in pts]
            dr.line(pts + [pts[0]], fill=(200, 205, 215, 255), width=max(1, rs.ss // 2))
    else:
        if rgb is not None:
            base = np.asarray(rgb, dtype=float)[order]
        else:
            lut = {}
            base = np.array([lut.setdefault(m, colors[MATS[m]]) for m in np.asarray(mats)[order].tolist()], dtype=float).reshape(-1, 3)
        shade = rs.ambient + (1 - rs.ambient) * ndl[order]
        c = np.clip(base * shade[:, None] + rim[order][:, None], 0, 1)
        cols = (c * 255).astype(np.int64).tolist()
        poly = dr.polygon
        for pts, cc in zip(pts_all, cols):
            col = (cc[0], cc[1], cc[2], 255)
            poly([tuple(p) for p in pts], fill=col, outline=col)
    if rs.ss == 1:
        pass
    else:
        img = img.resize((rs.cell_w, rs.cell_h), Image.LANCZOS)
    if rs.outline and not wire:
        a = img.getchannel("A")
        grow = a.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
        under = Image.new("RGBA", img.size, rs.outline_rgb + (0,))
        under.putalpha(grow)
        img = Image.alpha_composite(under, img)
    return img


def render_state(T, B, Mt, colors, state, rs, wire=False):
    P, keep = pose_triangles(T, B, state)
    return render_tris(P[keep], Mt[keep], colors, rs, (state.root_t[0], state.root_t[2]), wire=wire)
