"""v9.1 SKIN PUPPET: bendy limbs for the photo puppet (opt-in: --puppet-engine skin).

The classic puppet (puppet.Rig) cuts the person into rigid pieces and rotates each piece about its joint.  When a
joint bends, the two rigid pieces open a wedge-shaped gap or overlap that has to be hidden by "cap" discs, so a
kicking knee or a punching elbow looks like two tubes, not one limb.

SkinRig keeps the classic rig's segmentation, joints, torso gap-fill and layer order (so faces, colour regions, QA
and exporters keep working) and replaces only the rendering:

  * each limb is ONE layer (upper + lower piece + caps merged); every pixel gets smooth skinning weights:
      - elbow / knee weight: smoothstep of the distance past the joint along the limb (0 = upper, 1 = lower)
      - shoulder / hip weight: smoothstep of the distance from the joint (0 = body, 1 = limb)
    A pixel moves by the weighted blend of the transforms (linear blend skinning, like a 3D rig), so a bent elbow
    is a smooth bend.
  * pixels are forward-mapped ("splatted") in PREMULTIPLIED alpha, so edges keep their own colour, and pin-holes
    are closed from the neighbourhood.  Optional supersampling (ss=2) anti-aliases further but is ~4x slower.
  * the figure is grounded before it is drawn, so each frame is resampled once.

Every output pixel is a pixel of the person's own photo, moved.  Nothing is generated.
If a hidden hand was faked (rig.fist) the classic renderer is used for that build.

Measured (mannequin test, 8 moves): the classic puppet has 4-5 separate pixel islands in kick / punch / jump
frames (detached forearms and shins); this renderer has 3 (body + two hands/feet clusters) in every frame.
"""
from __future__ import annotations
import math
import numpy as np
from scipy import ndimage as ndi
from PIL import Image

from . import puppet as PP

ARM_R, LEG_R = "arm", "leg"


def premultiply(rgba_u8):
    a = rgba_u8.astype(np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a


def unpremultiply(p):
    a = np.clip(p[..., 3:4], 0.0, 1.0)
    rgb = np.where(a > 1e-4, p[..., :3] / np.maximum(a, 1e-4), 0.0)
    return (np.concatenate([np.clip(rgb, 0, 1), a], axis=-1) * 255.0 + 0.5).astype(np.uint8)


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _apply(M, P):
    return P @ M[:2, :2].T + M[:2, 2]


def _splat(xy, prem, shape):
    """bilinear forward splat of premultiplied colours; density-normalised, pin-holes closed"""
    H, W = shape
    x, y = xy[:, 0], xy[:, 1]
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
    acc = np.zeros((5, H * W), np.float64)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        if not ok.any():
            continue
        idx = yi[ok] * W + xi[ok]
        ww = w[ok]
        for c in range(4):
            acc[c] += np.bincount(idx, weights=prem[ok, c] * ww, minlength=H * W)
        acc[4] += np.bincount(idx, weights=ww, minlength=H * W)
    wsum = acc[4].reshape(H, W)
    col = acc[:4].reshape(4, H, W)
    good = wsum > 0.30
    out = np.zeros((H, W, 4), np.float32)
    out[good] = (col[:, good] / wsum[good]).T
    sil = ndi.binary_closing(good, structure=np.ones((3, 3), bool), iterations=1)
    hole = sil & ~good
    if hole.any():
        ys, xs = np.nonzero(hole)
        y0_, y1_ = max(0, ys.min() - 5), min(H, ys.max() + 6)
        x0_, x1_ = max(0, xs.min() - 5), min(W, xs.max() + 6)
        g, o, hh = good[y0_:y1_, x0_:x1_], out[y0_:y1_, x0_:x1_], hole[y0_:y1_, x0_:x1_]
        num = np.stack([ndi.gaussian_filter(np.where(g, o[..., c], 0.0), 1.3) for c in range(4)], -1)
        den = ndi.gaussian_filter(g.astype(np.float32), 1.3)
        fill = num / np.maximum(den[..., None], 1e-4)
        o[hh] = fill[hh]
    return out


def _over(dst, src):
    dst *= (1.0 - src[..., 3:4])
    dst += src


class _Layer:
    __slots__ = ("P", "C", "ws", "wj", "kind", "side")


class SkinRig(PP.Rig):
    SS = 1

    def __init__(self, cut, landmarks, pad_frac=0.75, colour_ref=None, ss=None):
        super().__init__(cut, landmarks, pad_frac=pad_frac, colour_ref=colour_ref)
        self.ss = int(ss or self.SS)
        self._skin_ok = not self.fist
        self._limbs = {}
        self._body_src = None
        if self._skin_ok:
            self._build_limbs()

    def _build_limbs(self):
        J, A = self.J, self.A
        sw = math.hypot(self.L[11][0] - self.L[12][0], self.L[11][1] - self.L[12][1])
        ru = 0.165 * sw
        for k in ("n", "f"):
            for kind, (a, b, c), R, names in (
                    (ARM_R, ("S", "E", "T"), ru, ("u" + k, "u" + k + "_cap", "f" + k + "_cap", "f" + k)),
                    (LEG_R, ("P", "K", "A"), self.r_leg, ("s" + k, "s" + k + "_cap", "t" + k + "_cap", "t" + k))):
                m = np.zeros(self.shape, bool)
                for nm in names:
                    m |= self.pieces[nm]
                m &= A[..., 3] > 0
                if not m.any():
                    continue
                ys, xs = np.nonzero(m)
                P = np.stack([xs, ys], 1).astype(np.float32)
                root, mid = np.asarray(J[k][a], np.float32), np.asarray(J[k][b], np.float32)
                u = mid - root
                u /= max(1e-6, float(np.hypot(*u)))
                s_mid = ((P - mid) @ u) / (1.3 * R)
                d_root = np.hypot(P[:, 0] - root[0], P[:, 1] - root[1])
                L = _Layer()
                L.P, L.C = P, premultiply(A[ys, xs])
                L.wj = _smooth((s_mid + 1.0) * 0.5).astype(np.float32)
                L.ws = _smooth((d_root - 0.35 * R) / (1.9 * R)).astype(np.float32)
                L.kind, L.side = kind, k
                self._limbs[(kind, k)] = L

    def _body_layer(self):
        im = self.layer("torso")
        if self._body_src is None or self._body_src[0] != id(im):
            a = np.asarray(im)
            ys, xs = np.nonzero(a[..., 3] > 0)
            self._body_src = (id(im), np.stack([xs, ys], 1).astype(np.float32), premultiply(a[ys, xs]))
        return self._body_src[1], self._body_src[2]

    def render(self, pose):
        if not self._skin_ok:
            return super().render(pose)
        J, rest, ss = self.J, self.rest, self.ss
        pelvis = ((J["n"]["P"][0] + J["f"]["P"][0]) / 2, (J["n"]["P"][1] + J["f"]["P"][1]) / 2)
        M0 = PP._rot(-pose.get("lean", 0.0), pelvis) @ PP._scale(pose.get("sx", 1.0), pose.get("sy", 1.0), pelvis)

        def chain(k, a, b, ja, jb, jc):
            d1 = pose.get(a, rest[a]) - rest[a]
            d2 = (pose[b] - rest[b]) if b in pose else d1
            R1 = PP._rot(d1, J[k][ja])
            j2 = PP._ap(R1, J[k][jb])
            M1 = M0 @ R1
            M2 = M0 @ PP._tr(j2[0] - J[k][jb][0], j2[1] - J[k][jb][1]) @ PP._rot(d2, J[k][jb])
            return M1, M2, PP._ap(M2, J[k][jc])

        def skin(L, Mb, M1, M2):
            P = L.P
            wj, ws = L.wj[:, None], L.ws[:, None]
            limb = _apply(M1, P) * (1.0 - wj) + _apply(M2, P) * wj
            return _apply(Mb, P) * (1.0 - ws) + limb * ws

        draws, hands = [], {}
        for k in ("f", "n"):
            Mt, Ms, _ = chain(k, "t" + k, "s" + k, "P", "K", "A")
            L = self._limbs.get((LEG_R, k))
            if L is not None:
                draws.append((skin(L, M0, Mt, Ms), L.C))
        Pb, Cb = self._body_layer()
        draws.append((_apply(M0, Pb), Cb))
        for k in pose.get("arm_order", ("f", "n")):
            Mu, Mf, tip = chain(k, "u" + k, "f" + k, "S", "E", "T")
            L = self._limbs.get((ARM_R, k))
            if L is not None:
                draws.append((skin(L, M0, Mu, Mf), L.C))
            hands[k] = (PP._ap(Mf, J[k]["W"]), tip)

        low = max(float(p[c[:, 3] > 0.16, 1].max()) for p, c in draws if (c[:, 3] > 0.16).any())
        dy = self.ground - low - pose.get("lift", 0.0) * self.stand_h
        dx = pose.get("dx", 0.0) * self.stand_h
        allp = np.concatenate([p for p, _ in draws])
        ox, oy = int(math.floor(allp[:, 0].min() + dx)) - 3, int(math.floor(allp[:, 1].min() + dy)) - 3
        ex, ey = int(math.ceil(allp[:, 0].max() + dx)) + 4, int(math.ceil(allp[:, 1].max() + dy)) + 4
        Wc, Hc = ex - ox, ey - oy
        shape = (Hc * ss, Wc * ss)
        acc = np.zeros(shape + (4,), np.float32)
        for p, c in draws:
            q = (p + np.array([dx - ox, dy - oy], np.float32)) * ss + (ss - 1) * 0.5
            if ss > 1:
                offs = np.arange(ss, dtype=np.float32) - (ss - 1) / 2.0
                qq = np.concatenate([q + np.array([a_, b_], np.float32) for a_ in offs for b_ in offs])
                cc = np.concatenate([c] * (ss * ss))
            else:
                qq, cc = q, c
            _over(acc, _splat(qq, cc, shape))
        if ss > 1:
            acc = acc.reshape(Hc, ss, Wc, ss, 4).mean(axis=(1, 3))
        out = Image.new("RGBA", self.layer("torso").size, (0, 0, 0, 0))
        out.paste(Image.fromarray(unpremultiply(acc), "RGBA"), (ox, oy))
        if pose.get("tint"):
            r, g, b, kk = pose["tint"]
            arr = np.asarray(out).astype(np.float32)
            m = arr[..., 3] > 0
            arr[m, :3] = arr[m, :3] * (1 - kk) + np.array([r, g, b]) * kk
            out = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        fx = []
        for k in pose.get("glow_hands", ""):
            w_, t_ = hands[k]
            fx.append(("glow", ((w_[0] + t_[0]) / 2 + dx, (w_[1] + t_[1]) / 2 + dy), pose.get("glow", (120, 200, 255)), 0.07 * self.stand_h))
        if pose.get("orb"):
            pts = [hands[k][1] for k in pose.get("orb_hand", "n")]
            c = (sum(p[0] for p in pts) / len(pts) + dx + pose.get("orb_ahead", 0.03) * self.stand_h,
                 sum(p[1] for p in pts) / len(pts) + dy)
            fx.append(("orb", c, pose["orb"], pose.get("orb_r", 0.05) * self.stand_h))
        for kind, c, col, r in fx:
            out = PP._effect(out, kind, c, col, r)
        return out
