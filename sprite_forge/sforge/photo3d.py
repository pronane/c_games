"""PHOTO 3D (v9.3): one front photo -> a skinned 3D point body driven by the skeletal motion library.

    --puppet-engine photo3d        (forge.py build --photo cut/cutout.png --landmarks cut/landmarks.json ...)

Why: the 2D puppets rotate flat sheets of the photo, so a torso can't twist, a shoulder can't roll and a side view
has to be invented separately.  Here the cut-out becomes a 3D body once, and every move and every camera angle is
a render of that body:

  1. parts      the photo puppet's segmentation (sforge.puppet.Rig: head, torso, upper arms, forearms + hands,
                thighs, shins + feet; hidden hands rebuilt; hands hanging on the thigh moved to the arm)
  2. depth      each part is INFLATED from its silhouette (rounded cross-section from the distance transform, per-part
                depth ratio: torso ~0.65 of its width, limbs round, head round + a nose / brow profile from the face
                landmarks).  Arms that overlap the body in the photo sit in front of it.
  3. surface    front = the photo's own pixels; back = the part's edge colours blended across each row (the crown
                colour for the back of the head) - logos, text and the face are never copied to the back
  4. skinning   every point follows two bones of the standard rig (sforge.rig, the same skeleton as the 3D / GLB
                exports) with short blend ramps at shoulders, elbows, wrists, hips, knees, ankles and along the spine
  5. motion     the skeletal motion library (sforge.motions) - the same clips as spec / GLB builds - so a kick is a
                real hip-knee-ankle chain, the torso twists into a punch and the feet stay planted
  6. render     z-buffered point splat at any yaw (0 front, 35 three-quarter fighter, 90 side, 8-way), relit
                relative to the photo's own lighting, 2x supersampled, cracks closed

The heavy maths (skinning, z-buffer) runs through sforge.accel: PyTorch on CUDA / Apple MPS when available,
NumPy otherwise.  Everything not in the photo (back, sides, depth) is ESTIMATED and flagged as such."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import rig as RG
from . import accel
from .mathutil import rx, ry

BONES = ["hips", "spine", "chest", "neck", "head",
         "upperarm_L", "forearm_L", "hand_L", "upperarm_R", "forearm_R", "hand_R",
         "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
BI = {b: i for i, b in enumerate(BONES)}
DEPTH = {"head": 1.0, "torso": 0.62, "u": 0.95, "f": 0.95, "t": 0.92, "s": 0.92, "fist": 0.9}
LIGHT = np.array([-0.35, 0.55, 0.76]); LIGHT = LIGHT / np.linalg.norm(LIGHT)
AMB = 0.62


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _seg_param(xs, ys, p, q):
    """position of pixels along segment p->q (0 at p, 1 at q)"""
    d = np.array(q, float) - np.array(p, float)
    L2 = max(1e-6, float(d @ d))
    return ((xs - p[0]) * d[0] + (ys - p[1]) * d[1]) / L2


class PhotoBody:
    def __init__(self, cut, landmarks, colour_ref=None, detail=820, look=0.8, sharpen=0.0, head_rim=False, log=print):
        from .puppet import Rig
        cut = cut.convert("RGBA")
        bb = cut.getchannel("A").getbbox() or (0, 0, cut.width, cut.height)
        k = min(1.0, detail / float(max(1, bb[3] - bb[1])))
        lms = [list(p) for p in landmarks]
        if k < 0.98:                                   # pose a smaller copy: plenty of points per output pixel
            cut = cut.resize((max(1, int(cut.width * k)), max(1, int(cut.height * k))), Image.LANCZOS)
            lms = [[p[0] * k, p[1] * k] + list(p[2:]) for p in lms]
            if colour_ref is not None:
                colour_ref = colour_ref.convert("RGBA").resize(cut.size, Image.LANCZOS)
        self.log = log
        self.look = look
        self.sharpen, self.head_rim = sharpen, head_rim
        rig = Rig(cut, lms, colour_ref=colour_ref)
        self.rig = rig
        A = rig.A
        H, W = A.shape[:2]
        J, L = rig.J, rig.L
        self.side_L = "n" if J["n"]["S"][0] > J["f"]["S"][0] else "f"        # image right = the person's left
        side = {self.side_L: "L", ("f" if self.side_L == "n" else "n"): "R"}
        self.S = rig.stand_h / RG.HEIGHT                                      # px per metre
        self.x0, self.y0 = float(rig.cx), float(rig.ground)
        yy, xx = np.mgrid[0:H, 0:W]
        # ---- skeleton pivots in photo pixels
        P2 = lambda a: np.array(a[:2], float)
        midS = (P2(J["n"]["S"]) + P2(J["f"]["S"])) / 2
        pelvis = (P2(J["n"]["P"]) + P2(J["f"]["P"])) / 2
        nose = P2(L[0]); eyes = (P2(L[2]) + P2(L[5])) / 2; mouth = (P2(L[9]) + P2(L[10])) / 2
        chin = mouth + 0.85 * (mouth - eyes)
        chin[1] = min(chin[1], midS[1] - 0.04 * rig.stand_h)
        neck = midS + 0.12 * (chin - midS)
        piv = {"hips": pelvis, "spine": pelvis + 0.2 * (neck - pelvis), "chest": pelvis + 0.59 * (neck - pelvis),
               "neck": neck, "head": neck + 0.55 * (chin - neck)}
        for k_, s_ in side.items():
            j = J[k_]
            piv.update({"upperarm_" + s_: P2(j["S"]), "forearm_" + s_: P2(j["E"]), "hand_" + s_: P2(j["W"]),
                        "thigh_" + s_: P2(j["P"]), "shin_" + s_: P2(j["K"]), "foot_" + s_: P2(j["A"])})
        self.fist_shift = {}
        for k_ in rig.fist:                        # hidden hand: the visible forearm stops at the pocket, so the
            s_ = side[k_]                          # wrist (and the rebuilt fist) move to its visible end
            fm = rig.pieces["f" + k_]
            fy, fx = np.nonzero(fm)
            if len(fx) > 20:
                E_, W_ = piv["forearm_" + s_], piv["hand_" + s_]
                sp = _seg_param(fx.astype(float), fy.astype(float), E_, W_)
                smax = float(np.clip(np.percentile(sp, 97), 0.45, 1.0))
                newW = E_ + smax * (W_ - E_)
                d = newW - W_
                if np.hypot(*d) > 2:
                    piv["hand_" + s_] = newW
                    self.fist_shift[k_] = d
                    J[k_] = dict(J[k_]); J[k_]["T"] = (J[k_]["T"][0] + d[0], J[k_]["T"][1] + d[1])
        self.piv2 = piv
        self.chin = chin
        # ---- colour sources with the matte edge replaced by interior colour (a halo would wrap round the sides)
        from .turn import _edge_fixed_rgb
        def fixed(a):
            out = np.array(a, copy=True); out[..., :3] = _edge_fixed_rgb(np.asarray(a), inset=4); return out
        A_f, T_f = fixed(A), fixed(rig.torso_rgba)
        L_f = T_f if rig.leg_src is rig.torso_rgba else (A_f if rig.leg_src is A else fixed(rig.leg_src))
        # ---- parts: (key, mask, rgba source, depth ratio, bone function)
        head_m = rig.torso_mask & (yy <= chin[1])
        torso_m = rig.torso_mask & ~head_m
        parts = [("head", head_m, T_f), ("torso", torso_m, T_f)]
        for k_ in ("n", "f"):
            parts += [("u" + k_, rig.pieces["u" + k_], A_f), ("f" + k_, rig.pieces["f" + k_], A_f),
                      ("t" + k_, rig.pieces["t" + k_], L_f), ("s" + k_, rig.pieces["s" + k_], L_f)]
            if k_ in rig.fist:
                fi = rig.fist[k_]
                if k_ in self.fist_shift:
                    dx_, dy_ = self.fist_shift[k_]
                    fi = fi.transform(fi.size, Image.AFFINE, (1, 0, -dx_, 0, 1, -dy_), resample=Image.BICUBIC)
                fa = np.asarray(fi)
                parts.append(("fist" + k_, fa[..., 3] > 60, fa))
        # ---- depth maps
        zmap = {}
        for key, m, src in parts:
            m = m & (src[..., 3] > 60)
            if m.sum() < 12:
                continue
            e = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
            w = ndi.maximum_filter(e, size=int(2 * e.max()) + 1)
            kd = DEPTH.get(key if key in ("head", "torso") else key[:-1], 0.95)
            z = kd * np.sqrt(np.clip(e * (2 * w - e), 0, None))
            if key == "head":                        # face profile: nose, brow and chin from the landmarks
                hw = float(e.max())
                for c, amp, sig in ((nose, 0.42, 0.13), ((eyes + nose) / 2 - [0, 0.18 * hw], 0.12, 0.30),
                                    (mouth + 0.5 * (chin - mouth), 0.10, 0.25)):
                    d2 = (xx - c[0]) ** 2 + (yy - c[1]) ** 2
                    z = z + amp * hw * np.exp(-d2 / (2 * (sig * hw) ** 2)) * m
            zmap[key] = (m, z)
        # arms / hands that cover the body in the photo sit in front of it
        zbody = np.zeros((H, W)); mbody = np.zeros((H, W), bool)
        for key, (m, z) in zmap.items():
            if key in ("head", "torso") or key[0] in "ts":
                zbody = np.maximum(zbody, np.where(m, z, 0)); mbody |= m
        self.zoff = {}
        for key, (m, z) in zmap.items():
            if key[0] in "uf" and key != "head":
                ov = m & mbody
                off = 0.0
                if ov.sum() > 20:
                    off = max(0.0, float(np.percentile((zbody - z)[ov], 85)) + 0.01 * rig.stand_h)
                self.zoff[key] = off
        # ---- points
        Ps, Cs, Ns, IA, IB, WS, FR, PI = [], [], [], [], [], [], [], []
        self.part_keys = []
        for key, src_ in [(p[0], p[2]) for p in parts]:
            if key not in zmap:
                continue
            m, z = zmap[key]
            ys, xs = np.nonzero(m)
            zf = z[ys, xs] + self.zoff.get(key, 0.0)
            gy, gx = np.gradient(z)
            gx, gy = gx[ys, xs], gy[ys, xs]
            nf = np.stack([-gx, gy, np.ones_like(gx)], 1); nf /= np.linalg.norm(nf, axis=1, keepdims=True)
            nb = nf * np.array([1, 1, -1.0])
            col_f = src_[ys, xs, :3].astype(np.float32)
            if key == "head" and self.head_rim:     # 3D keeps the real ears at the side; the rim fill is optional
                col_f = self._head_rim(m, z, src_, ys, xs, col_f)
            col_b = self._back_colours(key, m, src_, ys, xs)
            # continuity: near the silhouette the back IS the photo's edge colour; the estimated back colour only takes
            # over towards the middle of the back (a hard front / back split showed as a seam on every turned view)
            tb = _smooth(nf[:, 2] * 1.6)[:, None]
            if key[0] in "ufts" and not key.startswith("fist"):
                col_b = col_f * 0.96            # sleeves / trouser legs: same fabric all round - keep its real texture
            else:
                col_b = col_f * (1 - tb) + col_b * tb
            ia, ib, w = self._weights(key, xs.astype(float), ys.astype(float), side)
            X = (xs - self.x0) / self.S; Y = (self.y0 - ys) / self.S
            zb = -z[ys, xs] + self.zoff.get(key, 0.0)
            # steep walls (towards the silhouette the surface drops several px in depth per px across): fill each
            # step with a short column of points, so the surface stays solid when the body turns (no checkerboard
            # of front and back points at glancing angles)
            gm = np.hypot(gx, gy)
            ne = np.clip(np.ceil(gm) - 1, 0, 14).astype(int)
            rep = np.repeat(np.arange(len(xs)), ne)
            jj = np.concatenate([np.arange(1, n + 1) for n in ne]) if ne.sum() else np.zeros(0, int)
            frac_ = jj / (ne[rep] + 1.0) if len(rep) else np.zeros(0)
            def col(v, r=rep):
                return np.concatenate([v, v[r]]) if len(r) else v
            wall_f = col_f
            if key == "head" and len(rep):
                wall_f = self._head_rim(m, z, src_, ys, xs, col_f.copy(), full=True)
            Xf, Yf = col(X), col(Y)
            zf2 = np.concatenate([zf, zf[rep] - gm[rep] * frac_]) if len(rep) else zf
            zb2 = np.concatenate([zb, zb[rep] + gm[rep] * frac_]) if len(rep) else zb
            nn = len(Xf)
            Ps += [np.stack([Xf, Yf, zf2 / self.S], 1), np.stack([Xf, Yf, zb2 / self.S], 1)]
            Cs += [np.concatenate([col_f, wall_f[rep]]) if len(rep) else col_f, col(col_b)]; Ns += [col(nf), col(nb)]
            IA += [col(ia), col(ia)]; IB += [col(ib), col(ib)]; WS += [col(w), col(w)]
            FR += [np.ones(nn, bool), np.zeros(nn, bool)]
            PI += [np.full(2 * nn, len(self.part_keys), np.int16)]; self.part_keys.append(key)
        self.P = np.concatenate(Ps).astype(np.float32); self.C = np.concatenate(Cs).astype(np.float32)
        self.N = np.concatenate(Ns).astype(np.float32)
        self.ia = np.concatenate(IA).astype(np.int64); self.ib = np.concatenate(IB).astype(np.int64)
        self.w = np.concatenate(WS).astype(np.float32); self.front = np.concatenate(FR)
        self.part = np.concatenate(PI)
        lam0 = np.clip(self.N @ LIGHT, 0, 1)
        self.base = np.where(self.front, AMB + (1 - AMB) * lam0, AMB + (1 - AMB) * 0.55).astype(np.float32)
        self.piv3 = {b: np.array([(p[0] - self.x0) / self.S, (self.y0 - p[1]) / self.S, 0.0]) for b, p in piv.items()}
        self.tip3 = {s_: np.array([(J[k_]["T"][0] - self.x0) / self.S, (self.y0 - J[k_]["T"][1]) / self.S, 0.0])
                     for k_, s_ in side.items()}
        # arms drawn in front of the body sit forward in depth: their joints sit there too, or the offset acts as a
        # lever when the arm swings and the sleeve drifts off its bone
        for k_, s_ in side.items():
            dz = max(self.zoff.get("u" + k_, 0.0), self.zoff.get("f" + k_, 0.0)) / self.S
            for b in ("upperarm_", "forearm_", "hand_"):
                self.piv3[b + s_][2] += dz
            self.tip3[s_][2] += dz
        self.lowest = float(self.P[:, 1].min())
        log("photo3d: %d points (%d px front), %d bones, %.0f px/m" % (len(self.P), int(self.front.sum()), len(BONES), self.S))

    # ------------------------------------------------------------------ head rim
    def _head_rim(self, m, z, src, ys, xs, col, full=False):
        """outer band of the face (ear, hair edge, background fringe) -> the row's cheek colour, smoothed vertically;
        the face itself (inner 60%) is untouched"""
        H, W = m.shape
        sk = np.zeros((H, 3), np.float32); ok = np.zeros(H, bool)
        rel = np.zeros(len(xs), np.float32)
        for y in np.unique(ys):
            xr = np.nonzero(m[y])[0]
            if len(xr) < 8:
                continue
            c, hw = (xr.min() + xr.max()) / 2.0, (xr.max() - xr.min() + 1) / 2.0
            u = np.abs((xr - c) / hw)
            cheek = xr[(u >= 0.3) & (u <= 0.6)]
            if len(cheek) >= 2:
                sk[y] = np.median(src[y, cheek, :3].astype(np.float32), 0); ok[y] = True
            sel = ys == y
            rel[sel] = np.abs((xs[sel] - c) / hw)
        if ok.sum() > 3:
            idx = np.nonzero(ok)[0]
            for c in range(3):
                sk[:, c] = np.interp(np.arange(H), idx, ndi.gaussian_filter1d(sk[idx, c], 4))
            top = ys.min(); hh = max(1, ys.max() - top)
            crown = ((ys - top) / hh) < 0.18                 # the very top keeps its own scalp / hair
            wgt = np.clip((rel - 0.62) / 0.25, 0, 1) * np.where(crown, 0.4, 0.9) if not full else \
                np.where(crown, 0.3, 0.85) * np.clip((rel - 0.3) / 0.3, 0, 1)
            col = col * (1 - wgt[:, None]) + sk[ys] * wgt[:, None]
        return col

    # ------------------------------------------------------------------ surface colour of the unseen back
    def _back_colours(self, key, m, src, ys, xs):
        H, W = m.shape
        acc = np.zeros((H, W, 3), np.float32); wt = np.zeros((H, W), np.float32)
        rows = np.nonzero(m.any(1))[0]
        for y in rows:
            xr = np.nonzero(m[y])[0]
            x0, x1 = xr.min(), xr.max(); wdt = x1 - x0 + 1
            band = max(2, int(0.2 * wdt))
            cl = np.median(src[y, x0:x0 + band, :3].reshape(-1, 3), 0)
            cr = np.median(src[y, x1 - band + 1:x1 + 1, :3].reshape(-1, 3), 0)
            t = np.linspace(0, 1, wdt)[:, None]
            acc[y, x0:x1 + 1] = cl * (1 - t) + cr * t; wt[y, x0:x1 + 1] = 1
        if key == "head":                            # back of the head = the crown (hair / scalp)
            top = rows.min(); hh = max(1, rows.max() - top)
            crown = m[top:top + max(3, int(0.22 * hh))]
            cc = src[top:top + crown.shape[0]][crown][:, :3]
            if len(cc):
                cc = np.median(cc, 0)
                kk = np.clip((np.arange(H) - top) / hh - 0.55, 0, 1)[:, None, None] / 0.45
                acc = acc * kk + cc * (1 - kk)
        num = np.stack([ndi.gaussian_filter(acc[..., c] * wt, (10, 2)) for c in range(3)], -1)
        den = ndi.gaussian_filter(wt, (10, 2))[..., None]
        back = np.where(den > 1e-3, num / np.maximum(den, 1e-3), acc)
        return (back[ys, xs] * 0.92).astype(np.float32)

    # ------------------------------------------------------------------ two bones per point
    def _weights(self, key, xs, ys, side):
        n = len(xs)
        B = lambda b: np.full(n, BI[b], np.int64)
        pv = self.piv2
        if key == "head":
            hh = max(1.0, self.chin[1] - ys.min())
            return B("neck"), B("head"), _smooth((self.chin[1] - ys) / (0.12 * hh))
        if key == "torso":
            knots = ["hips", "spine", "chest", "neck"]
            tk = [0.0, 0.2, 0.59, 1.0]
            t = (pv["hips"][1] - ys) / max(1.0, pv["hips"][1] - pv["neck"][1])
            ia = B("hips"); ib = B("hips"); w = np.zeros(n)
            for i in range(3):
                sel = (t >= tk[i]) & (t < tk[i + 1])
                ia[sel] = BI[knots[i]]; ib[sel] = BI[knots[i + 1]]
                w[sel] = _smooth((t[sel] - tk[i]) / (tk[i + 1] - tk[i]))
            top = t >= 1.0
            ia[top] = BI["neck"]; ib[top] = BI["neck"]; w[top] = 1.0
            return ia, ib, w
        s_ = side[key[-1]]
        kind = key[:-1]
        if kind == "u":
            s = _seg_param(xs, ys, pv["upperarm_" + s_], pv["forearm_" + s_])
            return B("chest"), B("upperarm_" + s_), _smooth((s + 0.08) / 0.22)
        if kind in ("f", "fist"):
            s = _seg_param(xs, ys, pv["forearm_" + s_], pv["hand_" + s_])
            ia, ib = B("upperarm_" + s_), B("forearm_" + s_)
            w = _smooth((s + 0.12) / 0.24)
            hand = s > 0.9
            ia[hand] = BI["forearm_" + s_]; ib[hand] = BI["hand_" + s_]; w[hand] = _smooth((s[hand] - 0.9) / 0.25)
            if kind == "fist":
                ia[:] = BI["forearm_" + s_]; ib[:] = BI["hand_" + s_]; w[:] = 0.8
            return ia, ib, w
        if kind == "t":
            s = _seg_param(xs, ys, pv["thigh_" + s_], pv["shin_" + s_])
            return B("hips"), B("thigh_" + s_), _smooth((s + 0.12) / 0.3)
        if kind == "s":
            s = _seg_param(xs, ys, pv["shin_" + s_], pv["foot_" + s_])
            ia, ib = B("thigh_" + s_), B("shin_" + s_)
            w = _smooth((s + 0.1) / 0.2)
            foot = s > 0.92
            ia[foot] = BI["shin_" + s_]; ib[foot] = BI["foot_" + s_]; w[foot] = _smooth((s[foot] - 0.92) / 0.12)
            return ia, ib, w
        return B("chest"), B("chest"), np.zeros(n)

    # ------------------------------------------------------------------ one frame
    def pose_matrices(self, state):
        """bone matrices (B,3,4) mapping rest photo points to the posed body; rest rotations are identity"""
        Rb = {b: np.asarray(state.world[b])[:3, :3] for b in BONES}
        if self.look > 0:          # fighters keep their eyes on the opponent: remove most of the head's yaw
            f = Rb["head"][:, 2]
            yaw_h = math.atan2(f[0], f[2])
            corr = float(np.clip(-yaw_h * self.look, -math.radians(50), math.radians(50)))   # a neck turns ~50 deg
            c, s_ = math.cos(corr), math.sin(corr)
            Ry_ = np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]])
            Rb["head"] = Ry_ @ Rb["head"]
        pp = {}
        for b in BONES:
            par = RG.PARENT[b]
            if par == "root" or par not in pp:
                pp[b] = self.piv3[b].copy()
            else:
                pp[b] = pp[par] + Rb[par] @ (self.piv3[b] - self.piv3[par])
        M = np.zeros((len(BONES), 3, 4))
        for b in BONES:
            M[BI[b], :, :3] = Rb[b]
            M[BI[b], :, 3] = pp[b] - Rb[b] @ self.piv3[b]
        for s_ in ("L", "R"):
            Mh = M[BI["hand_" + s_]]
            pp["tip_" + s_] = Mh[:, :3] @ self.tip3[s_] + Mh[:, 3]
        self._pp = pp
        return M

    def render(self, state, yaw=0.0, cell=(512, 512), baseline=None, fig_px_per_m=None, ss=2, be=None, lift=None, normals=False):
        """normals=True: the same frame as a tangent-space-style normal map (view-space normal -> RGB, flat = 128,128,255)
        for 2D dynamic lighting (Godot CanvasItem normal maps, Unity 2D lights, Laigter-style workflows)"""
        """RGBA frame: feet on `baseline`, body centre on the cell centre, `fig_px_per_m` screen pixels per metre"""
        be = be or accel.backend()
        Wc, Hc = cell
        baseline = baseline if baseline is not None else int(Hc * 0.94)
        scale = (fig_px_per_m or (Hc * 0.62 / RG.HEIGHT)) * ss
        M = self.pose_matrices(state)
        P = be.put(self.P, "P%d" % id(self)); ia = be.put(self.ia, "ia%d" % id(self)); ib = be.put(self.ib, "ib%d" % id(self))
        w = be.put(self.w, "w%d" % id(self)); N = be.put(self.N, "N%d" % id(self))
        Pp = be.skin(P, ia, ib, w, M)
        Mr = M.copy(); Mr[:, :, 3] = 0
        Np = be.skin(N, ia, ib, w, Mr)
        Pn = be.get(Pp); Nn = be.get(Np)
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-6)
        if lift is None:
            lift = rig_lift(state)
        off = np.array([-self.piv3["hips"][0], lift - Pn[:, 1].min(), -self.piv3["hips"][2]])
        Pn += off                     # in place, hips on the pivot (root motion is the game's job), feet on the ground
        view = rx(0.0) @ ry(float(yaw))
        self.last_joints = {}         # QA: every joint projected into the output cell
        for b, p in self._pp.items():
            q = view @ (p + off)
            self.last_joints[b] = (Wc / 2.0 + q[0] * scale / ss, baseline - q[1] * scale / ss)
        Q = Pn @ view.T
        lam = np.clip(Nn @ LIGHT, 0, 1)
        shade = np.clip((AMB + (1 - AMB) * lam) / self.base, 0.55, 1.12)
        rgb = self.C * shade[:, None]
        if normals:
            nv = Nn @ view.T
            rgb = np.stack([(nv[:, 0] * 0.5 + 0.5), (nv[:, 1] * 0.5 + 0.5), np.clip(nv[:, 2], 0, 1) * 0.5 + 0.5], 1) * 255.0
        Ws, Hs = Wc * ss, Hc * ss
        sx = Wc * ss / 2.0 + Q[:, 0] * scale; sy = baseline * ss - Q[:, 1] * scale; sz = Q[:, 2]
        nzv = (Nn @ view.T)[:, 2]
        # soft back-face culling: points facing the camera win depth ties by 4 cm, so a facing-away point only shows
        # where it really is in front (an arm crossing the body) - hard culling opened gaps at the silhouette
        sz = sz + 0.04 * np.clip(nzv * 4.0, -1.0, 1.0)
        img = be.splat(sx, sy, sz, rgb, Ws, Hs)
        img = _close_cracks(img)
        from .puppet import despeckle
        img = np.asarray(despeckle(Image.fromarray(img, "RGBA"), frac=0.01)).copy()   # incl. loose bits (a strap end)
        im = Image.fromarray(img, "RGBA")
        if ss > 1:
            a = img[..., 3:4].astype(np.float32) / 255.0
            pm = np.concatenate([img[..., :3] * a, a * 255.0], -1).reshape(Hc, ss, Wc, ss, 4).mean(axis=(1, 3))
            rgb_ = np.where(pm[..., 3:4] > 0, pm[..., :3] / np.maximum(pm[..., 3:4] / 255.0, 1e-6), 0)
            im = Image.fromarray(np.concatenate([rgb_, pm[..., 3:4]], -1).clip(0, 255).astype(np.uint8), "RGBA")
        if self.sharpen > 0:                       # restore the crispness the box downsample takes off
            from PIL import ImageFilter
            a_ = im.getchannel("A")
            im = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(100 * self.sharpen), threshold=2)).convert("RGBA")
            im.putalpha(a_)
        return im


def _close_cracks(img, it=2):
    """fill transparent pixels surrounded by figure (skinning stretch / grazing-angle gaps)"""
    a = img[..., 3] > 0
    out = img.copy()
    k = np.ones((3, 3)); k[1, 1] = 0
    for _ in range(it):
        cnt = ndi.convolve(a.astype(np.float32), k, mode="constant")
        hole = (~a) & (cnt >= 5)
        if not hole.any():
            break
        for c in range(3):
            s = ndi.convolve(np.where(a, out[..., c], 0).astype(np.float32), k, mode="constant")
            out[..., c][hole] = (s[hole] / cnt[hole]).astype(np.uint8)
        out[..., 3][hole] = 255
        a = out[..., 3] > 0
    return out


_REST_FOOT = None


def rig_lift(state):
    """height of the rig's lowest foot above its standing height (0 when grounded, > 0 in a jump)"""
    global _REST_FOOT
    if _REST_FOOT is None:
        rw = RG.rest_world()
        _REST_FOOT = min(rw["foot_L"][1], rw["foot_R"][1])
    fy = min(np.asarray(state.world["foot_L"])[1, 3], np.asarray(state.world["foot_R"])[1, 3])
    return max(0.0, float(fy - _REST_FOOT) - 0.01)


def _rot_angle(Ra, Rb):
    return math.acos(max(-1.0, min(1.0, (np.trace(Ra.T @ Rb) - 1.0) / 2.0)))


def sample_states(motion, n, loop=None, fine=96, keep_ends=True):
    """n frames of `motion` spaced by POSE CHANGE instead of clock time: a fast strike that the motion covers in a
    few percent of its duration gets in-betweens instead of one 140-degree jump, and holds get fewer frames.
    Change = the largest bone rotation between neighbouring fine samples (all bones of the rig)."""
    from . import anim
    loop = motion.loop if loop is None else loop
    if n <= 2:
        return anim.states_for(motion, n, loop)
    fs = anim.states_for(motion, fine, loop)
    names = [b for b in BONES]
    R = [[np.asarray(st.world[b])[:3, :3] for b in names] for st in fs]
    seq = list(range(len(fs))) + ([0] if loop else [])
    step = [0.0]
    for a_, b_ in zip(seq, seq[1:]):
        d = max(_rot_angle(R[a_][i], R[b_][i]) for i in range(len(names)))
        step.append(d + 0.02)                    # + a little clock time, so long holds still advance
    cum = np.cumsum(step)
    total = cum[-1]
    targets = np.arange(n) * total / n if loop else np.linspace(0, total, n)
    idx = [int(np.clip(np.searchsorted(cum, t), 0, len(fs) - 1)) for t in targets]
    return [fs[i] for i in idx]


def fighter_camera(yaw, pack):
    """fighter pack: the camera is side-on (90) and `yaw` becomes how open the torso is to the camera
    (35 = a 3/4 face -> torso opened 55 deg).  -> (camera yaw, open degrees)"""
    if pack == "fighter3d":
        y = float(yaw or 0.0)
        return 90.0, float(max(0.0, min(90.0, 90.0 - y))) if 0.0 < y < 90.0 else (55.0 if y == 0 else 0.0)
    return float(yaw or 0.0), 0.0


def resolve_motion(m, pack="none", open_deg=55.0):
    from .moves import motion_for
    from .motions import find_motion
    if m.motion and (m.motion.startswith("mocap_") or m.motion.startswith("custom_")):   # video-to-move / pose editor
        from .motions import LIB
        if m.motion in LIB:
            return LIB[m.motion], True
    if pack == "fighter3d":
        from . import fightpack
        mo = fightpack.motion_for_move(m.name, pack, open_deg)
        if mo is not None:
            return mo, True
    mo = motion_for(m)
    return (mo or find_motion("idle")), mo is not None


def _smear(prev, cur, k=0.38):
    """classic fighting-game smear: where a limb was a frame ago (and is not now), a faint copy behind it"""
    a_prev = np.asarray(prev)[..., 3] > 80
    a_cur = np.asarray(cur)[..., 3] > 80
    trail = a_prev & ~ndi.binary_dilation(a_cur, iterations=2)
    trail = ndi.binary_opening(trail, iterations=2)          # thin outlines from a small body shift are not a smear
    lab, n = ndi.label(trail)
    if n:
        sz = ndi.sum(trail, lab, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sz >= 0.012 * max(1, a_cur.sum())   # limb-sized trails only
        trail = keep[lab]
    if trail.sum() < 30:
        return cur
    g = np.zeros_like(np.asarray(prev))
    g[trail] = np.asarray(prev)[trail]
    g[..., :3] = (g[..., :3].astype(np.float32) * 0.85 + 255 * 0.15).astype(np.uint8)
    g[..., 3] = (g[..., 3].astype(np.float32) * k).astype(np.uint8)
    out = Image.fromarray(g, "RGBA")
    out.alpha_composite(cur)
    return out


def render_moves(body, moves, yaw, cell, baseline, fig_px_per_m, log=print, be=None, pack="none", smear=True,
                 smear_deg=38.0, ss=2, normals=None):
    """normals: a dict to fill with {move: [normal-map frames]} (same placement, no smear)"""
    """moves: [MoveSpec] -> {name: [RGBA cells]} using the skeletal motion library (or the fighter pack)"""
    be = be or accel.backend(log=log)
    cam, open_deg = fighter_camera(yaw, pack)
    out, missing = {}, []
    look0 = body.look
    for m in moves:
        mo, ok = resolve_motion(m, pack, open_deg)
        if not ok:
            missing.append(m.name)
        body.look = 0.0 if mo.category == "Fighter3D" else look0      # the pack aims the head itself
        states = sample_states(mo, m.frames, m.loop)
        fr = [body.render(st, yaw=cam, cell=cell, baseline=baseline, fig_px_per_m=fig_px_per_m, be=be, ss=ss) for st in states]
        if normals is not None:
            normals[m.name] = [body.render(st, yaw=cam, cell=cell, baseline=baseline, fig_px_per_m=fig_px_per_m, be=be, ss=ss,
                                           normals=True) for st in states]
        if smear and len(fr) > 2 and not m.loop:
            R = [[np.asarray(st.world[b])[:3, :3] for b in BONES] for st in states]
            sm = list(fr)
            for i in range(1, len(fr)):
                d = max(_rot_angle(R[i - 1][j], R[i][j]) for j in range(len(BONES)))
                if math.degrees(d) > smear_deg:
                    sm[i] = _smear(fr[i - 1], fr[i])
            fr = sm
        out[m.name] = fr
    body.look = look0
    if missing:
        log("photo3d: no skeletal motion for %s - idle used" % ", ".join(missing))
    return out
