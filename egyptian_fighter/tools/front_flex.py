"""front_flex.py - Mike's victory: front-on double-biceps, a turn, the same from behind.

Built only from his real front-facing photo frame (sprite_sources/mike_hyrox/idle.png):
  * both arms (and the racket) are cut off; his free left arm is re-posed with the same
    shoulder / elbow rig as tools/poses.py (upper arm up and out, forearm bent up, fist by
    the head, upper arm widened a little = flexed biceps) and MIRRORED onto the other side,
    so both arms are his own arm
  * the strip of shorts / thigh hidden behind the racket is filled from the mirror image of
    his other side
  * there is NO photo of his back: the back view is his front frame mirrored (as if turned)
    with the chest print painted out in the vest's own black and the face replaced by his
    own hair (rows of the hair band stretched down) - a reconstruction, not a photo
  * the turn is a horizontal squash through side-on
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

# coordinates in the scaled (560 px tall), trimmed front frame
CX = 111.0                       # body centre line (torso / crotch)
SHOULDER = (171.0, 121.0)        # his left shoulder joint (image right)
ELBOW = (191.0, 207.0)
WRIST_Y = 281                    # bottom of his watch strap
# image-right arm = pixels right of this line (y -> x), rows 92..335
ARM_R_EDGE = [(92, 158), (100, 157), (130, 166), (150, 169), (180, 172), (200, 172), (260, 175), (300, 178), (335, 180)]
# image-left arm + racket = pixels left of this line
ARM_L_EDGE = [(92, 70), (100, 70), (130, 67), (150, 61), (180, 53), (200, 54), (240, 51), (270, 47), (300, 42), (312, 40)]
RACKET = [(296, 40), (310, 44), (320, 50), (340, 57), (360, 59), (380, 58), (392, 54), (402, 46)]
PAD = 170                        # canvas padding (raised arms)


def _edge(points, h):
    ys = np.array([p[0] for p in points], float); xs = np.array([p[1] for p in points], float)
    e = np.full(h, np.nan)
    r = np.arange(h)
    ok = (r >= ys[0]) & (r <= ys[-1])
    e[ok] = np.interp(r[ok], ys, xs)
    return e


def fill_print_holes(sub, light=(226, 226, 222)):
    """The source photos had the white print on the black vest keyed out (see-through
    letters / race bib).  Paint enclosed holes that are surrounded by dark cloth back in."""
    a = sub.copy()
    al = a[..., 3]
    m = al > 60
    holes = ndi.binary_fill_holes(m) & ~m
    lab, n = ndi.label(holes)
    lum = a[..., :3].astype(int).mean(-1)
    skin = (a[..., 0].astype(int) - a[..., 2] > 25) & (a[..., 1] > 70)
    for i, sl in enumerate(ndi.find_objects(lab)):
        reg = lab == i + 1
        ring = ndi.binary_dilation(reg, iterations=2) & ~reg & m
        if ring.sum() == 0:
            continue
        if skin[ring].mean() > 0.25:          # a real gap between an arm and the body
            continue
        if reg.sum() > 0.08 * m.sum():
            continue
        tgt = ndi.binary_dilation(reg, iterations=1) & (al < 250)
        k = (al[tgt].astype(float) / 255.0)[:, None]
        a[tgt, :3] = (a[tgt, :3] * k + np.array(light) * (1 - k)).astype(np.uint8)
        a[tgt, 3] = 255
    return a


class FrontRig:
    def __init__(self, base):
        b = np.pad(base, ((PAD, 20), (PAD, PAD), (0, 0)))
        self.h, self.w = b.shape[:2]
        h0 = base.shape[0]
        YY, XX = np.mgrid[0:self.h, 0:self.w]
        fig = b[..., 3] > 0
        er = _edge(ARM_R_EDGE, h0); el = _edge(ARM_L_EDGE, h0); rk = _edge(RACKET, h0)
        ER = np.full(self.h, np.nan); EL = ER.copy(); RK = ER.copy()
        ER[PAD:PAD + h0] = er + PAD; EL[PAD:PAD + h0] = el + PAD; RK[PAD:PAD + h0] = rk + PAD
        arm_r = fig & (XX > np.nan_to_num(ER, nan=1e9)[:, None])
        arm_l = fig & (XX < np.nan_to_num(EL, nan=-1)[:, None])
        racket = fig & (XX < np.nan_to_num(RK, nan=-1)[:, None])
        # keep only the main blob of each arm cut
        self.cx = CX + PAD
        body = b.copy()
        body[arm_r | arm_l | racket] = 0
        # shorts / thigh edge hidden behind the racket: from the mirror image of the other side
        mir = body[:, ::-1]
        shift = int(round(2 * self.cx - (self.w - 1)))
        mir = np.roll(mir, shift, axis=1)
        hole = ndi.binary_dilation(racket | arm_l, iterations=3) & (YY > PAD + 280) & (body[..., 3] < 200) & (mir[..., 3] > 0)
        body[hole] = mir[hole]
        self.body = body
        self.base = b
        # the free arm, split at the elbow
        px, py = SHOULDER[0] + PAD, SHOULDER[1] + PAD
        ex, ey = ELBOW[0] + PAD, ELBOW[1] + PAD
        d = np.array([ex - px, ey - py]); d /= np.linalg.norm(d)
        along = (XX - ex) * d[0] + (YY - ey) * d[1]
        fore = arm_r & (along > -3)
        upper = arm_r & (along < 7)
        arm_px = b.copy()
        # light keying fringe on the arm outline -> drop it
        edge = arm_r & ~ndi.binary_erosion(arm_r)
        lumb = arm_px[..., :3].astype(int).mean(-1)
        arm_px[edge & (lumb > 150), 3] = 0
        self.upper = np.zeros_like(b); self.upper[upper] = arm_px[upper]
        self.fore = np.zeros_like(b); self.fore[fore] = arm_px[fore]
        # fist: the relaxed hand (below the watch strap) is shortened towards the wrist
        wy = WRIST_Y + PAD
        hand = self.fore.copy(); hand[:wy] = 0
        self.fore[wy:] = 0
        H = Image.fromarray(hand).transform(hand.shape[1::-1], Image.AFFINE,
                                            (1 / 1.08, 0, (ex + 4) - (ex + 4) / 1.08, 0, 1 / 0.62, wy - wy / 0.62),
                                            resample=Image.BICUBIC)
        F = Image.fromarray(self.fore); F.alpha_composite(H)
        self.fore = np.asarray(F).copy()
        # shoulder cap (deltoid) stays put under the raised arm so the shoulder line is kept
        cap = arm_r & (YY < py + 6)
        self.cap = np.zeros_like(b); self.cap[cap] = b[cap]
        ring = arm_r & (np.abs((XX - ex) * d[0] + (YY - ey) * d[1]) < 5)
        xs = XX[ring]
        self.joint_r = max(4.0, (xs.max() - xs.min()) / 2.0)
        self.joint_col = tuple(int(c) for c in np.median(b[ring][:, :3], 0))
        self.pivot = (px, py); self.elbow = (ex, ey)
        ys = np.nonzero(fig.any(1))[0]
        self.feet = float(ys.max())

    def arm(self, up, fdeg, bulge=1.0):
        """posed free arm on the canvas: forearm bent fdeg at the elbow, whole arm up `up` deg"""
        px, py = self.pivot; ex, ey = self.elbow
        U = Image.fromarray(self.upper)
        if bulge != 1.0:     # widen the upper arm about its own axis (it hangs ~vertically)
            c = (px + ex) / 2.0
            U = U.transform(U.size, Image.AFFINE, (1 / bulge, 0, c - c / bulge, 0, 1, 0), resample=Image.BICUBIC)
        F = Image.fromarray(self.fore).rotate(fdeg, resample=Image.BICUBIC, center=(ex, ey))
        j = Image.new('RGBA', U.size)
        r = self.joint_r * 0.85 * bulge
        ImageDraw.Draw(j).ellipse((ex - r, ey - r, ex + r, ey + r), fill=self.joint_col + (255,))
        A = Image.new('RGBA', U.size)
        A.alpha_composite(j); A.alpha_composite(F); A.alpha_composite(U)
        return A.rotate(up, resample=Image.BICUBIC, center=(px, py))

    def mirror(self, im):
        a = np.asarray(im)[:, ::-1]
        shift = int(round(2 * self.cx - (self.w - 1)))
        return Image.fromarray(np.roll(a, shift, axis=1).copy())

    def front(self, up=95, fdeg=100, bulge=1.0, sq=(1.0, 1.0)):
        img = Image.new('RGBA', (self.w, self.h))
        R = self.arm(up, fdeg, bulge)
        cap = Image.fromarray(self.cap)
        for layer in (self.mirror(cap), cap):
            img.alpha_composite(layer)
        img.alpha_composite(Image.fromarray(self.body))
        img.alpha_composite(self.mirror(R))
        img.alpha_composite(R)
        return self._squash(np.asarray(img).copy(), sq)

    def _squash(self, a, sq):
        sx, sy = sq
        if (sx, sy) == (1.0, 1.0):
            return a
        fx, fy = self.cx, self.feet
        im = Image.fromarray(a).transform((self.w, self.h), Image.AFFINE,
                                          (1 / sx, 0, fx - fx / sx, 0, 1 / sy, fy - fy / sy), resample=Image.BICUBIC)
        return np.asarray(im).copy()

    def back(self, front_arr, sq=(1.0, 1.0)):
        """his front frame turned round: mirrored, vest / shorts print painted out in the
        cloth's own black, the face replaced by his own hair, a little darker (lit from behind)"""
        a = np.asarray(self.mirror(Image.fromarray(front_arr))).copy()
        rgb = a[..., :3].astype(int); al = a[..., 3]
        YY, XX = np.mgrid[0:self.h, 0:self.w]
        skin = (rgb[..., 0] - rgb[..., 2] > 22) & (rgb[..., 1] > 65) & (rgb[..., 1] > 0.5 * rgb[..., 0])
        body_m = np.asarray(self.mirror(Image.fromarray(self.body)))[..., 3] > 0
        rng = np.random.default_rng(3)
        def paint(m, col, grad=True):
            n = int(m.sum())
            if not n:
                return
            c = np.array(col, float) + rng.normal(0, 2.0, (n, 1))
            if grad:   # darker towards the sides (a rounded back)
                dx = np.abs(XX[m] - self.cx) / 70.0
                c = c * (1.0 - 0.35 * np.clip(dx, 0, 1))[:, None]
            a[m, :3] = np.clip(c, 0, 255).astype(np.uint8)
        vest = body_m & (al > 0) & (YY >= PAD + 96) & (YY < PAD + 292) & (np.abs(XX - self.cx) < 75)
        vest &= ~(skin & (YY < PAD + 112))                       # keep the traps / neck skin
        vest &= ~(skin & (np.abs(XX - self.cx) > 52))            # and the shoulders
        paint(vest, (30, 30, 33))
        a[vest, 3] = 255
        sat = rgb.max(-1) - rgb.min(-1)
        shorts = body_m & (al > 0) & (YY >= PAD + 292) & (YY < PAD + 386) & ~skin & (sat < 28)
        paint(shorts, (24, 24, 27))
        a[shorts & (a[..., 3] > 100), 3] = 255
        # head: everything above the neck replaced by an oval of his own hair
        neck = PAD + 84
        head = (YY < neck) & (al > 0) & (np.abs(XX - self.cx) < 70)
        hy = np.nonzero(head.any(1))[0]
        top = int(hy.min())
        hair_rows = range(top + 2, top + 24)
        hx = np.nonzero(head[top + 16])[0]
        cxh = float(hx.mean()) if len(hx) else self.cx
        rx = max(20.0, (hx.max() - hx.min()) / 2.0 + 3) if len(hx) else 30.0
        cy, ry = top + 40.0, 41.0
        skull = ((XX - cxh) / rx) ** 2 + ((YY - cy) / ry) ** 2 <= 1
        out = a.copy()
        out[head] = 0
        # his own hair (the top of his head in the photo), resized onto the oval
        rows = np.arange(top + 1, top + 30)
        cols = np.nonzero((a[top + 14, :, 3] > 200) & head[top + 14])[0]
        patch = Image.fromarray(a[rows.min():rows.max() + 1, cols.min() + 2:cols.max() - 1])
        y0o, y1o = int(cy - ry), int(cy + ry) + 1
        x0o, x1o = int(cxh - rx), int(cxh + rx) + 1
        patch = np.asarray(patch.resize((x1o - x0o, y1o - y0o), Image.BICUBIC)).copy()
        patch[..., 3] = 255
        sk = skull[y0o:y1o, x0o:x1o]
        reg = out[y0o:y1o, x0o:x1o]
        reg[sk] = patch[sk]
        # nape: hair fades into the neck skin
        nape = skull & (YY > cy + ry * 0.55)
        kk = np.clip((YY[nape] - (cy + ry * 0.55)) / (ry * 0.45), 0, 1)[:, None]
        neckcol = np.median(a[(YY > neck) & (YY < neck + 10) & skin & (np.abs(XX - self.cx) < 25)][:, :3], 0) \
            if (((YY > neck) & (YY < neck + 10) & skin).any()) else np.array([170, 120, 95])
        out[nape, :3] = (out[nape, :3] * (1 - kk * 0.6) + neckcol * kk * 0.6).astype(np.uint8)
        # soft outline for the oval
        al2 = out[..., 3].astype(float)
        ring = skull & ~ndi.binary_erosion(skull)
        al2[ring] *= 0.6
        out[..., 3] = al2.astype(np.uint8)
        # seen from behind he is lit from the back: a touch darker overall
        m = out[..., 3] > 0
        out[m, :3] = (out[m, :3] * 0.82).astype(np.uint8)
        return self._squash(out, sq)


def build(base):
    """list of (frame, anchor_x) - see sprites.cfg 'loop victory 1'"""
    rig = FrontRig(base)          # (base already has the vest print filled in)
    fr = []
    def add(a):
        m = a[..., 3] > 8
        ys, xs = np.nonzero(m)
        fr.append((a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy(), rig.cx - xs.min()))
    raise_ = rig.front(up=50, fdeg=60)
    f1 = rig.front(up=95, fdeg=100)
    f2 = rig.front(up=98, fdeg=112, bulge=1.13, sq=(1.02, 0.985))
    add(raise_)                                   # 0 arms coming up
    add(f1); add(f2); add(f1); add(f2)            # 1-4 flex pulses, facing the camera
    add(rig.front(up=95, fdeg=100, sq=(0.55, 1.0)))   # 5 turning
    add(rig.front(up=95, fdeg=100, sq=(0.22, 1.0)))   # 6 side-on
    add(rig.back(f1, sq=(0.22, 1.0)))             # 7
    add(rig.back(f1, sq=(0.55, 1.0)))             # 8
    add(rig.back(f1)); add(rig.back(f2)); add(rig.back(f1)); add(rig.back(f2))   # 9-12 from behind
    add(rig.back(f1, sq=(0.55, 1.0)))             # 13 turning back
    add(rig.back(f1, sq=(0.22, 1.0)))             # 14
    add(rig.front(up=95, fdeg=100, sq=(0.22, 1.0)))   # 15
    add(rig.front(up=95, fdeg=100, sq=(0.55, 1.0)))   # 16  -> loops to frame 1
    return fr, rig
