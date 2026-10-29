"""poses.py - build fighting moves from a character's existing photo frames.

No new pictures are generated: a base frame is cut into parts (far leg, near leg, body,
arms, racket) and the parts are rotated / shifted / squashed and composited again, the
same way the walk cycle is rebuilt.  Used by build_sprites.py for moves that have no real
source frames (see SPEC entries with  proc=...).
"""
import math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

PAD_X, PAD_T, PAD_B = 320, 360, 40


def _diffuse_fill(rgb, known, todo, iters=60):
    """fill pixels in `todo` with the average of known neighbours (simple inpainting)"""
    rgb = rgb.astype(float).copy()
    known = known.copy()
    k = np.ones((3, 3))
    for _ in range(iters):
        if not (todo & ~known).any():
            break
        w = ndi.convolve(known.astype(float), k, mode='constant')
        acc = np.stack([ndi.convolve(rgb[..., c] * known, k, mode='constant') for c in range(3)], -1)
        new = todo & ~known & (w > 0)
        rgb[new] = acc[new] / w[new][:, None]
        known |= new
    return rgb.clip(0, 255).astype(np.uint8)


class Rig:
    def __init__(self, sub, cfg, leg_rig):
        self.cfg = cfg
        r = leg_rig(sub, crotch_frac=cfg.get('crotch'), prop_overlay=cfg.get('prop', False))
        if r is None:
            raise RuntimeError('leg rig failed')
        P = ((PAD_T, PAD_B), (PAD_X, PAD_X))
        pad = lambda x: None if x is None else np.pad(x, P + ((0, 0),) * (x.ndim - 2))
        a = pad(r['a'])
        back, front, body, overlay = pad(r['back']), pad(r['front']), pad(r['base']), pad(r['overlay'])
        self.h, self.w = a.shape[:2]
        self.hip = (r['cx'] + PAD_X, r['pivot'] + PAD_T)
        self.layers = {}
        bsrc = a
        if cfg.get('clone_leg'):
            bsrc = a.copy(); bsrc[..., :3] = (bsrc[..., :3] * 0.82).astype(np.uint8)
            back = front
        self.layers['leg_b'] = self._layer(bsrc, back)
        self.layers['leg_f'] = self._layer(a, front)
        self.pivots = {}
        self.fore, self.elbows, self.joint = {}, {}, {}
        YY, XX = np.mgrid[0:self.h, 0:self.w]
        removed = np.zeros((self.h, self.w), bool)
        cloth_jobs = []
        full_overlay = overlay
        for name, arm in cfg.get('arms', {}).items():
            x0, y0, x1, y1 = arm['box']
            m = (XX >= x0 + PAD_X) & (XX < x1 + PAD_X) & (YY >= y0 + PAD_T) & (YY < y1 + PAD_T)
            for ex in arm.get('ellipses', []):
                cx_, cy_, rx, ry = ex
                m |= ((XX - cx_ - PAD_X) / rx) ** 2 + ((YY - cy_ - PAD_T) / ry) ** 2 <= 1
            src = body.copy()
            if arm.get('cut_legs'):
                # the hand-held prop also hangs over the leg layers (below the hip pivot): take
                # it out of the legs too (dark / neon pixels; bare skin stays with the leg)
                rgb_ = a[..., :3].astype(int)
                sk_ = (rgb_[..., 0] - rgb_[..., 2] > 22) & (rgb_[..., 1] > 70) & (rgb_[..., 0] - rgb_[..., 1] > 14)
                ell = np.zeros((self.h, self.w), bool)
                for ex_ in arm.get('ellipses', []):
                    cx_, cy_, rx, ry = ex_
                    ell |= ((XX - cx_ - PAD_X) / rx) ** 2 + ((YY - cy_ - PAD_T) / ry) ** 2 <= 1
                leg_px = np.zeros((self.h, self.w), bool)
                for ln in ('leg_b', 'leg_f'):
                    Lg = self.layers[ln]
                    px_ = ell & (Lg[..., 3] > 0) & ~(sk_ & (rgb_[..., 2] > 60))
                    # the racket's neon rim / white print just outside the ellipse
                    ring = ndi.binary_dilation(ell, iterations=20) & ~ell & (Lg[..., 3] > 0) & (YY < ell.nonzero()[0].max() + 22)
                    neon = (rgb_[..., 1] > 60) & (rgb_[..., 1] - rgb_[..., 2] > 30) & (np.abs(rgb_[..., 0] - rgb_[..., 1]) < 30)
                    whitish = (rgb_.min(-1) > 120) & (rgb_.max(-1) - rgb_.min(-1) < 40)
                    rim = ring & (neon | whitish)
                    rim = ndi.binary_dilation(rim, iterations=1) & ring & ~(sk_ & (rgb_[..., 2] > 60) & ~neon)
                    px_ |= rim
                    self._rim = getattr(self, '_rim', np.zeros_like(rim)) | (ndi.binary_dilation(ell, iterations=20) & ~ell & (YY < ell.nonzero()[0].max() + 22) & (neon | whitish))
                    self._ell = ell
                    src[px_] = Lg[px_]
                    leg_px |= px_
                    Lg[px_] = 0
                    self._leg_cut = getattr(self, '_leg_cut', {})
                    self._leg_cut[ln] = self._leg_cut.get(ln, np.zeros_like(px_)) | px_
            if arm.get('with_prop') and full_overlay is not None:
                po = full_overlay[..., 3] > 0
                src[po] = full_overlay[po]
                m = (m & (body[..., 3] > 0)) | po
                overlay = None
            else:
                m &= body[..., 3] > 0
            if arm.get('cut_legs'):
                m |= leg_px
            lab, n = ndi.label(m)
            if n > 1:
                sz = ndi.sum(m, lab, range(1, n + 1))
                m = np.isin(lab, 1 + np.nonzero(sz >= 0.08 * sz.max())[0])
            self.layers[name] = self._layer(src, m)
            self.pivots[name] = (arm['pivot'][0] + PAD_X, arm['pivot'][1] + PAD_T)
            if 'elbow' in arm:
                # split off the forearm (everything past a line through the elbow that is
                # perpendicular to shoulder->elbow) so it can bend on its own
                ex, ey = arm['elbow'][0] + PAD_X, arm['elbow'][1] + PAD_T
                px, py = self.pivots[name]
                d = np.array([ex - px, ey - py], float); d /= np.linalg.norm(d)
                fore = m & (((XX - ex) * d[0] + (YY - ey) * d[1]) > 0)
                L = self.layers[name]
                self.fore[name] = self._layer(L, fore)
                L[fore] = 0
                self.elbows[name] = (ex, ey)
                # joint patch: a disc of the arm's own colour hides the seam when it bends
                ring = m & (np.abs((XX - ex) * d[0] + (YY - ey) * d[1]) < 6)
                if ring.any():
                    xs = XX[ring]
                    r = max(4.0, (xs.max() - xs.min()) / 2.0 - 1)
                    col = np.median(src[ring][:, :3], 0).astype(np.uint8)
                    self.joint[name] = (r, tuple(int(c) for c in col))
            body[m & (body[..., 3] > 0)] = 0
            removed |= m
            if 'cloth_poly' in arm:
                cloth_jobs.append(arm)
        # torso pixels that were hidden behind an arm (cfg 'fill' boxes): inpaint them
        fill = np.zeros((self.h, self.w), bool)
        for arm in cfg.get('arms', {}).values():
            for (x0, y0, x1, y1) in arm.get('fill', []):
                box = np.zeros_like(fill)
                box[y0 + PAD_T:y1 + PAD_T, x0 + PAD_X:x1 + PAD_X] = True
                if 'fill_rgb' in arm:      # flat cloth colour + a little shading noise
                    mm = box & removed
                    rng = np.random.default_rng(1)
                    body[mm, :3] = np.clip(np.array(arm['fill_rgb']) + rng.normal(0, 2, (mm.sum(), 1)), 0, 255)
                    body[mm, 3] = 255
                else:
                    fill |= box
        fill &= removed
        if fill.any():
            al = body[..., 3] > 0
            body[..., :3] = _diffuse_fill(body[..., :3], al, fill, iters=80)
            body[fill, 3] = 255
        self.layers['body'] = body
        # cloth hidden behind a prop (cfg arm 'cloth_poly' = outline of the garment in base
        # coordinates): repainted in the garment's own colour with a soft fold texture,
        # only inside the garment's outline, on the body (above the hip pivot) or the near leg
        for arm in cloth_jobs:
            from PIL import ImageDraw as _D
            pm = Image.new('L', (self.w, self.h), 0)
            _D.Draw(pm).polygon([(x + PAD_X, y + PAD_T) for x, y in arm['cloth_poly']], fill=255)
            poly = np.asarray(pm) > 0
            have = np.zeros_like(poly)
            for nm_, L_ in self.layers.items():
                if not nm_.startswith('arm'):
                    have |= L_[..., 3] > 200
            if getattr(self, '_rim', None) is not None:
                rb = ndi.binary_dilation(self._rim, iterations=1) & (body[..., 3] > 0)
                body[rb] = 0
                have &= ~rb
            todo = poly & ~have
            # real cloth pixels near the hole (body + near leg), used as texture
            comp = body.copy()
            lf = self.layers['leg_f']
            use = lf[..., 3] > 200
            comp[use] = lf[use]
            rgbv = comp[..., :3].astype(int)
            near = ndi.binary_dilation(poly, iterations=30)
            known = near & have & (comp[..., 3] > 200) & (rgbv.max(-1) - rgbv.min(-1) < 22) & (rgbv.mean(-1) < 95)
            known &= ~ndi.binary_dilation(~(comp[..., 3] > 200), iterations=3)    # not the outline
            if getattr(self, '_ell', None) is not None:
                known &= ~ndi.binary_dilation(self._ell, iterations=18)
            base_col = np.median(comp[known][:, :3], 0) if known.any() else np.array(arm.get('fill_rgb', (30, 30, 33)))
            col = np.zeros((self.h, self.w, 3), np.uint8)
            col[:] = base_col.astype(np.uint8)
            done_ = np.zeros_like(todo)
            ty, tx = np.nonzero(todo)
            for r_ in (24, 36, 50, 66, 84, 104):
                for ddx, ddy in ((-r_, 0), (0, -r_), (r_, 0), (-r_, -r_), (r_, -r_), (0, r_), (-r_, r_), (r_, r_)):
                    sy_, sx_ = ty + ddy, tx + ddx
                    ok_ = (sy_ >= 0) & (sy_ < self.h) & (sx_ >= 0) & (sx_ < self.w)
                    ok_[ok_] &= known[sy_[ok_], sx_[ok_]]
                    ok_ &= ~done_[ty, tx]
                    col[ty[ok_], tx[ok_]] = comp[sy_[ok_], sx_[ok_], :3]
                    done_[ty[ok_], tx[ok_]] = True
            # blur the copied texture a little so patch edges don't show
            for c_ in range(3):
                ch = col[..., c_].astype(float)
                col[..., c_] = np.where(todo, ndi.gaussian_filter(ch, 1.2), ch).astype(np.uint8)
            pivot_y = self.hip[1]
            for tgt, rows in ((body, YY < pivot_y + 1000), ):
                mm = todo & rows
                tgt[mm, :3] = col[mm]
                tgt[mm, 3] = 255
            # soften the seam between the repaint and the real cloth
            for tgt in (body, self.layers['leg_f']):
                seam = ndi.binary_dilation(todo, iterations=2) & ~todo & (tgt[..., 3] > 0) & poly
                if seam.any():
                    tgt[seam, :3] = ((tgt[seam, :3].astype(int) + col[seam]) // 2).astype(np.uint8)
        # holes the prop left in the legs (below the shorts' hem): inpaint each leg from its
        # own nearest pixels, limited to the leg's horizontal span on that row
        for ln, cut in getattr(self, '_leg_cut', {}).items():
            Lg = self.layers[ln]
            hole = cut & (Lg[..., 3] == 0)
            for other in self.layers.values():
                if other is not Lg and other is not body and other is not self.layers.get('leg_b' if ln == 'leg_f' else 'leg_f'):
                    continue
            if ln == 'leg_b':
                hole &= self.layers['leg_f'][..., 3] < 200
            hole &= body[..., 3] < 200
            have_ = Lg[..., 3] > 200
            span = np.zeros_like(hole)
            for yy in np.nonzero(hole.any(1))[0]:
                xs_ = np.nonzero(have_[yy])[0]
                if len(xs_) > 3:
                    span[yy, xs_.min():xs_.max() + 1] = True
            hole &= span
            if not hole.any():
                continue
            idx = ndi.distance_transform_edt(~have_, return_distances=False, return_indices=True)
            Lg[hole] = Lg[idx[0][hole], idx[1][hole]]
            Lg[hole, 3] = 255
            for c_ in range(3):
                ch = ndi.gaussian_filter(Lg[..., c_].astype(float), 1.5)
                Lg[hole, c_] = ch[hole].astype(np.uint8)
        self.overlay = overlay
        # bending: everything above the waist line folds forward about the back of the waist
        # (cfg 'waist' = y of the belt line; default a little above the crotch)
        self.waist = int(cfg['waist'] + PAD_T) if 'waist' in cfg else int(self.hip[1]) - 12
        row = np.nonzero(body[self.waist, :, 3] > 0)[0]
        self.bend_pivot = (float(row.min() + 8) if len(row) else self.hip[0], float(self.waist + 4))
        ys = np.nonzero((a[..., 3] > 0).any(1))[0]
        self.feet_y = int(ys.max())
        col = (body[..., 3] > 0).sum(0).astype(float)
        c = np.cumsum(col)
        self.anchor = float(np.searchsorted(c, c[-1] / 2))

    def _layer(self, src, m):
        L = np.zeros_like(src)
        L[m] = src[m]
        return L

    # ------------------------------------------------------------------ posing --
    def pose(self, legs=(0, 0), arms=None, lean=0.0, squash=(1.0, 1.0), leg_sy=1.0,
             tint=None, glow=None, dx=0, fore=None, bend=0.0, bulge=1.0, flip=False):
        """legs: (far, near) leg rotation in degrees (+ = foot forward/up)
           arms: {name: degrees} (+ = hand forward/up for a figure facing right)
           fore: {name: degrees} extra elbow bend of the forearm (arms with an 'elbow')
           bend: upper body (torso, head, arms) rotation about the back of the hips
                 (+ = bend forward; legs stay put)
           bulge: >1 widens the upper arm a little (flexed biceps)
           flip: mirror the finished frame (figure turns its back; see extract_proc)
           lean: whole-figure rotation about the feet (+ = lean forward)
           squash: (sx, sy) about the feet;  leg_sy < 1 shortens the legs (crouch) and
           lowers the upper body by the same amount"""
        arms = arms or {}
        hx, hy = self.hip
        fyl = self.feet_y
        drop = (fyl - hy) * (1 - leg_sy)
        img = Image.new('RGBA', (self.w, self.h))
        names = list(self.layers)
        arm_names = [n for n in names if n.startswith('arm')]
        order = ['leg_b'] + [n for n in arm_names if self.cfg['arms'][n].get('behind')] + ['body', 'leg_f', '#ov']
        order += [n for n in arm_names if not self.cfg['arms'][n].get('behind')]
        for name in order:
            if name == '#ov':
                if self.overlay is None:
                    continue
                L = Image.fromarray(self.overlay)
            else:
                L = Image.fromarray(self.layers[name])
            if name in ('leg_b', 'leg_f'):
                if leg_sy != 1.0:   # scale legs about the floor line
                    L = L.transform(L.size, Image.AFFINE, (1, 0, 0, 0, 1 / leg_sy, fyl - fyl / leg_sy),
                                    resample=Image.BICUBIC)
                ang = legs[0] if name == 'leg_b' else legs[1]
                if ang:
                    L = L.rotate(ang, resample=Image.BICUBIC, center=(hx, hy + drop))
            else:
                if drop:
                    L = L.transform(L.size, Image.AFFINE, (1, 0, 0, 0, 1, -drop), resample=Image.BICUBIC)
                if name in self.fore:
                    L = self._arm_with_forearm(name, L, (fore or {}).get(name, 0.0), drop, bulge)
                if name in arms and arms[name]:
                    px, py = self.pivots[name]
                    L = L.rotate(arms[name], resample=Image.BICUBIC, center=(px, py + drop))
                if bend:
                    bx, by = self.bend_pivot
                    if name == 'body':      # hips / shorts stay with the legs
                        wy = int(round(self.waist + drop))
                        a_ = np.asarray(L)
                        low = a_.copy(); low[:wy] = 0
                        up = a_.copy(); up[wy:] = 0
                        L = Image.fromarray(up).rotate(-bend, resample=Image.BICUBIC, center=(bx, by + drop))
                        L.alpha_composite(Image.fromarray(low))     # shorts drawn over the shirt tail
                    else:
                        L = L.rotate(-bend, resample=Image.BICUBIC, center=(bx, by + drop))
            img.alpha_composite(L)
        out = img
        fx, fy = self.anchor, float(fyl)
        if squash != (1.0, 1.0):
            sx, sy = squash
            out = out.transform(out.size, Image.AFFINE, (1 / sx, 0, fx - fx / sx, 0, 1 / sy, fy - fy / sy),
                                resample=Image.BICUBIC)
        if lean:
            out = out.rotate(-lean, resample=Image.BICUBIC, center=(fx, fy))
        arr = np.asarray(out).copy()
        if flip:
            arr = arr[:, ::-1].copy()
        if tint is not None:
            r, g, b, k = tint
            m = arr[..., 3] > 0
            arr[m, :3] = (arr[m, :3] * (1 - k) + np.array([r, g, b]) * k).astype(np.uint8)
        if glow is not None:
            arr = add_glow(arr, glow)
        if dx:
            arr = np.roll(arr, int(dx), axis=1)
        return arr, self.anchor + dx

    def _arm_with_forearm(self, name, upper, fdeg, drop, bulge):
        """upper arm layer (already dropped) + elbow joint disc + forearm rotated at the elbow"""
        ex, ey = self.elbows[name]
        ey += drop
        out = upper
        if bulge != 1.0:     # flex: widen the upper arm about its own centre line
            px, py = self.pivots[name]
            cx = (px + ex) / 2.0
            out = out.transform(out.size, Image.AFFINE, (1 / bulge, 0, cx - cx / bulge, 0, 1, 0),
                                resample=Image.BICUBIC)
        F = Image.fromarray(self.fore[name])
        if drop:
            F = F.transform(F.size, Image.AFFINE, (1, 0, 0, 0, 1, -drop), resample=Image.BICUBIC)
        if fdeg:
            F = F.rotate(fdeg, resample=Image.BICUBIC, center=(ex, ey))
        out = out.copy()
        if name in self.joint and fdeg:
            from PIL import ImageDraw
            r, col = self.joint[name]
            j = Image.new('RGBA', out.size)
            ImageDraw.Draw(j).ellipse((ex - r, ey - r, ex + r, ey + r), fill=col + (255,))
            out.alpha_composite(j)
        out.alpha_composite(F)
        return out

    def debug(self):
        """colour-coded part map"""
        cols = {'leg_b': (255, 0, 0), 'leg_f': (0, 0, 255), 'body': (128, 128, 128),
                'arm_f': (0, 200, 0), 'arm_r': (255, 200, 0), 'fore': (0, 220, 220)}
        out = np.zeros((self.h, self.w, 3), np.uint8) + 60
        for n, L in list(self.layers.items()) + [('fore', f) for f in self.fore.values()]:
            m = L[..., 3] > 0
            out[m] = (L[m, :3] * 0.4 + np.array(cols.get(n, (255, 0, 255))) * 0.6).astype(np.uint8)
        if self.overlay is not None:
            m = self.overlay[..., 3] > 0
            out[m] = (255, 0, 255)
        for n, (px, py) in list(self.pivots.items()) + list(self.elbows.items()) + [('hip', self.hip), ('bend', self.bend_pivot)]:
            out[int(py) - 3:int(py) + 4, int(px) - 3:int(px) + 4] = (255, 255, 255)
        return out


def add_glow(arr, color, radius=9, strength=0.75):
    al = arr[..., 3].astype(float) / 255
    g = ndi.gaussian_filter(ndi.grey_dilation(al, size=(radius, radius)), radius / 2)
    g = (g * strength).clip(0, 1)
    out = np.zeros_like(arr)
    out[..., :3] = color
    out[..., 3] = (g * 255).astype(np.uint8)
    o = Image.fromarray(out)
    o.alpha_composite(Image.fromarray(arr))
    return np.asarray(o).copy()


def trim_with_anchor(arr, anchor):
    m = arr[..., 3] > 8
    ys, xs = np.nonzero(m)
    return arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1], anchor - xs.min()


# --------------------------------------------------------------- move library ----
# each move: list of pose kwargs.  'R' = racket/prop arm, 'A' = free (punching) arm.
def moves(arm_free='arm_f', arm_racket='arm_r'):
    A, R = arm_free, arm_racket
    def P(**k):
        return k
    return {
        'idle_bob': [P(squash=(1, 1.0)), P(squash=(1.004, 0.993)), P(squash=(1.008, 0.986)), P(squash=(1.004, 0.993))],
        'crouch': [P(legs=(-26, 30), leg_sy=0.88, lean=3), P(legs=(-40, 46), leg_sy=0.8, lean=7),
                   P(legs=(-46, 52), leg_sy=0.76, lean=9), P(legs=(-46, 52), leg_sy=0.76, lean=9)],
        'jump': [P(legs=(-20, 24), leg_sy=0.86, lean=4), P(squash=(0.95, 1.06), arms={A: 30}),
                 P(legs=(-12, 26), leg_sy=0.8, arms={A: 60, R: 35}), P(legs=(-6, 36), leg_sy=0.72, arms={A: 70, R: 45}),
                 P(legs=(-10, 24), leg_sy=0.8, arms={A: 50, R: 30}), P(legs=(-12, 16), leg_sy=0.9, arms={A: 30, R: 15})],
        'punch': [P(arms={A: -15}, lean=-3), P(arms={A: 45}, lean=2), P(arms={A: 80}, lean=6),
                  P(arms={A: 84}, lean=7), P(arms={A: 40}, lean=2)],
        'kick': [P(lean=-3, legs=(0, 20)), P(lean=-8, legs=(0, 50)), P(lean=-14, legs=(-5, 85)),
                 P(lean=-15, legs=(-5, 92)), P(lean=-10, legs=(0, 55)), P(lean=-3, legs=(0, 15))],
        'block': [P(arms={R: 95, A: 70}, lean=-3), P(arms={R: 105, A: 75}, lean=-4), P(arms={R: 100, A: 72}, lean=-4)],
        'hit': [P(lean=-8, dx=-6, tint=(255, 40, 40, 0.45)), P(lean=-15, dx=-14, tint=(255, 40, 40, 0.3)),
                P(lean=-11, dx=-10), P(lean=-5, dx=-4)],
        'throw': [P(lean=4, arms={A: 50, R: 30}), P(lean=12, dx=16, arms={A: 85, R: 70}, legs=(-10, 15)),
                  P(lean=14, dx=22, arms={A: 90, R: 80}, legs=(-12, 18)), P(lean=-6, dx=4, arms={A: 140, R: 120}),
                  P(lean=-10, dx=0, arms={A: 160, R: 150}), P(lean=-2, arms={A: 30})],
        # overhead smash: racket goes up behind the head, then whips down and forward
        'special1': [P(arms={R: 60}, lean=-2), P(arms={R: 150}, lean=-6), P(arms={R: 200}, lean=-8),
                     P(arms={R: 110}, lean=8), P(arms={R: 75}, lean=10), P(arms={R: 60}, lean=4)],
        # low drive: crouched, racket swings from behind to forward at hip height
        'special2': [P(arms={R: -40}, legs=(-12, 14), leg_sy=0.85, lean=4), P(arms={R: -55}, legs=(-14, 16), leg_sy=0.82, lean=6),
                     P(arms={R: 20}, legs=(-14, 16), leg_sy=0.82, lean=8), P(arms={R: 80}, legs=(-14, 16), leg_sy=0.82, lean=10),
                     P(arms={R: 100}, legs=(-12, 14), leg_sy=0.85, lean=8), P(arms={R: 60}, lean=3)],
        'jump_attack': [P(legs=(35, 60), leg_sy=0.75), P(legs=(25, 80), lean=-8), P(legs=(20, 95), lean=-14),
                        P(legs=(20, 95), lean=-14), P(legs=(30, 60), leg_sy=0.8)],
        'taunt': [P(arms={R: 60}), P(arms={R: 140}), P(arms={R: 175}, squash=(1, 1.02)), P(arms={R: 170}, squash=(1.02, 0.97)),
                  P(arms={R: 175}, squash=(1, 1.02)), P(arms={R: 120})],
        'victory': [P(arms={R: 120, A: 60}), P(arms={R: 170, A: 110}, squash=(0.97, 1.04)), P(arms={R: 178, A: 125}, squash=(0.97, 1.04)),
                    P(arms={R: 170, A: 110}, squash=(1.03, 0.96)), P(arms={R: 178, A: 125}, squash=(0.98, 1.03)),
                    P(arms={R: 175, A: 120})],
        # double-biceps flex (needs arms with an 'elbow' in the rig): arms come up, then
        # frames 2..5 loop as a flex pulse (sprites.cfg  'loop victory 2')
        'flex': [P(arms={R: -45, A: 40}, fore={R: -35, A: 35}),
                 P(arms={R: -88, A: 75}, fore={R: -75, A: 75}),
                 P(arms={R: -100, A: 86}, fore={R: -100, A: 100}, squash=(0.99, 1.02)),
                 P(arms={R: -104, A: 90}, fore={R: -116, A: 116}, squash=(1.02, 0.985), bulge=1.12, lean=-2),
                 P(arms={R: -100, A: 86}, fore={R: -100, A: 100}, squash=(0.99, 1.02)),
                 P(arms={R: -104, A: 90}, fore={R: -118, A: 118}, squash=(1.025, 0.98), bulge=1.14, lean=-2)],
        # 'bum bubble' special: turn round (squash = side-on), bend over with the backside to the
        # opponent (flip + bend), the game launches the speech bubble on the middle frame,
        # then straighten up and turn back
        'bum1': [P(arms={R: 15}), P(squash=(0.55, 1.0)), P(flip=True, bend=25, arms={R: 25, A: 25}),
                 P(flip=True, bend=60, lean=-5, arms={R: 62, A: 62}),
                 P(flip=True, bend=82, lean=-8, arms={R: 85, A: 85}, squash=(1.03, 0.98)),
                 P(flip=True, bend=80, lean=-8, arms={R: 82, A: 82}),
                 P(flip=True, bend=30, arms={R: 30, A: 30}), P(squash=(0.55, 1.0))],
        'bum2': [P(arms={R: 15}), P(squash=(0.55, 1.0)), P(flip=True, bend=35, arms={R: 35, A: 35}),
                 P(flip=True, bend=75, lean=-6, arms={R: 78, A: 78}, legs=(-6, 6), leg_sy=0.94),
                 P(flip=True, bend=88, lean=-10, arms={R: 92, A: 92}, legs=(-8, 8), leg_sy=0.9, squash=(1.04, 0.97)),
                 P(flip=True, bend=86, lean=-9, arms={R: 90, A: 90}, legs=(-8, 8), leg_sy=0.92),
                 P(flip=True, bend=35, arms={R: 35, A: 35}), P(squash=(0.55, 1.0))],
    }


def build_move(rig, move, extra=None):
    frames = []
    for k in moves()[move]:
        k = dict(k)
        if extra:
            k.update(extra)
        arr, anc = rig.pose(**k)
        frames.append(trim_with_anchor(arr, anc))
    return frames
