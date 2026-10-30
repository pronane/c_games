"""Offline person cut-out for ordinary phone photos (Pillow + numpy + scipy only).

GrabCut-style:
  1. a trimap from a hint: a box around the person (outside = background), optional
     foreground / background points, or a hand-made mask (white = person, black = background,
     grey = let the tool decide);
  2. colour + position Gaussian-mixture models for person and background, re-fitted 6 times;
  3. an edge-aware smoothness term (contrast-weighted neighbours, mean-field), so the cut
     follows real edges instead of colour noise;
  4. the person blob(s) touching the hint are kept, small holes filled;
  5. at full resolution the edge is refined with a colour guided filter (soft, hair-aware
     alpha) and edge pixels are de-contaminated (the photo background is un-mixed from them),
     so there is no halo of the old background around the cut-out.
No network, no neural model, no generative model: the output pixels are the photo's own pixels.
"""
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi

WORK = 560          # working resolution for the segmentation (longest side)


def load_photo(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


# ------------------------------------------------------------------ Gaussian mixtures ----
class GMM:
    def __init__(self, k):
        self.k = k

    def fit(self, X, rng, iters=10):
        n, d = X.shape
        k = min(self.k, max(1, n // 20))
        # k-means++ init
        c = [X[rng.integers(n)]]
        for _ in range(1, k):
            d2 = np.min(((X[:, None, :] - np.array(c)[None]) ** 2).sum(-1), 1)
            p = d2 / max(d2.sum(), 1e-12)
            c.append(X[rng.choice(n, p=p)])
        c = np.array(c)
        for _ in range(6):
            lab = np.argmin(((X[:, None, :] - c[None]) ** 2).sum(-1), 1)
            for j in range(k):
                if (lab == j).any():
                    c[j] = X[lab == j].mean(0)
        self.mu = c
        self.w = np.array([(lab == j).mean() + 1e-3 for j in range(k)])
        self.cov = np.array([np.cov(X[lab == j].T) if (lab == j).sum() > d + 1 else np.eye(d) * 0.01 for j in range(k)])
        self.cov += np.eye(d)[None] * 1e-4
        for _ in range(iters):                       # a few EM steps
            r = self._resp(X)
            nk = r.sum(0) + 1e-9
            self.w = nk / nk.sum()
            self.mu = (r.T @ X) / nk[:, None]
            for j in range(k):
                dx = X - self.mu[j]
                self.cov[j] = (r[:, j, None] * dx).T @ dx / nk[j] + np.eye(d) * 1e-4
        return self

    def _logp_each(self, X):
        out = []
        for j in range(len(self.w)):
            ci = np.linalg.inv(self.cov[j])
            _, ld = np.linalg.slogdet(self.cov[j])
            dx = X - self.mu[j]
            m = np.einsum("ni,ij,nj->n", dx, ci, dx)
            out.append(np.log(self.w[j]) - 0.5 * (m + ld))
        return np.stack(out, 1)

    def _resp(self, X):
        L = self._logp_each(X)
        L -= L.max(1, keepdims=True)
        r = np.exp(L)
        return r / r.sum(1, keepdims=True)

    def logp(self, X):
        L = self._logp_each(X)
        m = L.max(1)
        return m + np.log(np.exp(L - m[:, None]).sum(1))


def _features(rgb, pos_w):
    h, w, _ = rgb.shape
    yy, xx = np.mgrid[0:h, 0:w]
    s = max(h, w)
    f = np.concatenate([rgb, (xx / s * pos_w)[..., None], (yy / s * pos_w)[..., None]], -1)
    return f.reshape(-1, 5)


def _pairwise(rgb):
    """contrast-sensitive neighbour weights (right, down) like GrabCut"""
    dr = ((rgb[:, 1:] - rgb[:, :-1]) ** 2).sum(-1)
    dd = ((rgb[1:] - rgb[:-1]) ** 2).sum(-1)
    beta = 1.0 / (2 * max(np.concatenate([dr.ravel(), dd.ravel()]).mean(), 1e-6))
    return np.exp(-beta * dr), np.exp(-beta * dd)


def _meanfield(D, wr, wd, hard_fg, hard_bg, gamma=3.0, iters=18):
    q = 1 / (1 + np.exp(-np.clip(D, -30, 30)))
    for _ in range(iters):
        s = 2 * q - 1
        msg = np.zeros_like(D)
        msg[:, :-1] += wr * s[:, 1:]
        msg[:, 1:] += wr * s[:, :-1]
        msg[:-1] += wd * s[1:]
        msg[1:] += wd * s[:-1]
        q = 1 / (1 + np.exp(-np.clip(D + gamma * msg, -30, 30)))
        q[hard_fg] = 1
        q[hard_bg] = 0
    return q


def _disk_mask(shape, pts, r):
    m = np.zeros(shape, bool)
    yy, xx = np.ogrid[0:shape[0], 0:shape[1]]
    for (x, y) in pts:
        m |= (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    return m


def _wand(rgb, pts, r, tol):
    """magic wand: each hint point marks a disk plus the connected patch of similar colour"""
    h, w, _ = rgb.shape
    out = _disk_mask((h, w), pts, r)
    lim = int(0.18 * max(h, w))
    for (x, y) in pts:
        xi, yi = int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))
        y0, y1, x0, x1 = max(0, yi - lim), min(h, yi + lim), max(0, xi - lim), min(w, xi + lim)
        patch = rgb[y0:y1, x0:x1]
        ref = rgb[max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2].reshape(-1, 3).mean(0)
        sim = np.sqrt(((patch - ref) ** 2).sum(-1)) < tol * 1.7
        L, _ = ndi.label(sim)
        lv = L[yi - y0, xi - x0]
        if lv:
            out[y0:y1, x0:x1] |= L == lv
    return out


def find_face(rgb):
    """rough face finder for photos without hints (rgb 0..1, working resolution):
    the largest skin-coloured blob in the upper 65% of the picture, preferring the
    horizontal middle.  Returns (x0, y0, x1, y1) in working pixels or None."""
    h, w, _ = rgb.shape
    v = rgb * 255
    y = 0.299 * v[..., 0] + 0.587 * v[..., 1] + 0.114 * v[..., 2]
    cr = (v[..., 0] - y) * 0.713 + 128
    cb = (v[..., 2] - y) * 0.564 + 128
    sk = (cr > 136) & (cr < 175) & (cb > 85) & (cb < 128) & (y > 70) & (y < 245)
    sk[int(0.65 * h):] = False
    sk = ndi.binary_opening(sk, iterations=2)
    sk = ndi.binary_closing(sk, iterations=3)
    L, n = ndi.label(sk)
    best, bs = None, 0
    for i, sl in enumerate(ndi.find_objects(L)):
        if sl is None:
            continue
        blob = L[sl] == i + 1
        area = blob.sum()
        bh, bw = blob.shape
        if area < 0.004 * h * w or bh < 0.6 * bw or bh > 2.6 * bw or area < 0.4 * bh * bw:
            continue                      # faces are roughly oval and fairly solid
        cx = (sl[1].start + sl[1].stop) / 2
        score = area * (1.2 - abs(cx / w - 0.5))
        if score > bs:
            best, bs = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop), score
    return best


def segment(img, box=None, fg_pts=(), bg_pts=(), mask=None, pos_w=0.0, seed=1, log=print,
            fg_boxes=(), bg_boxes=()):
    """returns a soft person-probability map (working resolution) and the scale used"""
    W0, H0 = img.size
    sc = WORK / max(W0, H0)
    w, h = max(8, int(W0 * sc)), max(8, int(H0 * sc))
    rgb = np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.float64) / 255.0
    rgb_s = ndi.gaussian_filter(rgb, (0.7, 0.7, 0))
    hard_fg = np.zeros((h, w), bool)
    hard_bg = np.zeros((h, w), bool)
    if mask is not None:
        m = np.asarray(mask.convert("L").resize((w, h), Image.NEAREST))
        hard_fg |= m > 200
        hard_bg |= m < 55
        if box is None:
            ys, xs = np.nonzero(m >= 55)
            box = (xs.min() / sc, ys.min() / sc, (xs.max() + 1) / sc, (ys.max() + 1) / sc)
    auto_face = None
    if not fg_pts and mask is None:
        auto_face = find_face(rgb)
        if auto_face is not None and box is not None:     # ignore a 'face' outside the user's box
            fx0, fy0, fx1, fy1 = auto_face
            cxf, cyf = (fx0 + fx1) / 2 / sc, (fy0 + fy1) / 2 / sc
            if not (box[0] < cxf < box[2] and box[1] < cyf < box[3]):
                auto_face = None
        if auto_face is not None:
            fx0, fy0, fx1, fy1 = auto_face
            fw, fh = fx1 - fx0, fy1 - fy0
            cx = (fx0 + fx1) / 2
            if box is None:
                box = (max(0, cx - 2.4 * fw) / sc, max(0, fy0 - 0.75 * fh) / sc, min(w, cx + 2.4 * fw) / sc, H0)
            ix, iy = 0.22 * fw, 0.18 * fh
            fg_boxes = list(fg_boxes) + [((fx0 + ix) / sc, (fy0 + iy) / sc, (fx1 - ix) / sc, (fy1 - iy) / sc),
                                         ((cx - 0.45 * fw) / sc, (fy1 + 0.35 * fh) / sc, (cx + 0.45 * fw) / sc, min(h, fy1 + 1.6 * fh) / sc),
                                         ((cx - 0.25 * fw) / sc, max(0, fy0 - 0.12 * fh) / sc, (cx + 0.25 * fw) / sc, (fy0 + 0.2 * fh) / sc)]
            log("  cut-out: found a face at %d,%d-%d,%d; person box %d,%d-%d,%d" % (
                fx0 / sc, fy0 / sc, fx1 / sc, fy1 / sc, *box))
    if box is None:     # no hint: assume a person roughly in the middle of the picture
        box = (W0 * 0.10, H0 * 0.03, W0 * 0.90, H0 * 1.0)
        log("  cut-out: no --box given and no face found, assuming the person is in the middle 80% of the photo")
    bx0, by0, bx1, by1 = [int(round(v * sc)) for v in box]
    bx0, by0 = max(0, bx0), max(0, by0)
    bx1, by1 = min(w, bx1), min(h, by1)
    outside = np.ones((h, w), bool)
    outside[by0:by1, bx0:bx1] = False
    hard_bg |= outside & ~hard_fg
    r = max(3, int(0.012 * max(w, h)))
    if fg_pts:
        hard_fg |= _wand(rgb_s, [(x * sc, y * sc) for x, y in fg_pts], r, 0.05)
    if bg_pts:
        hard_bg |= _wand(rgb_s, [(x * sc, y * sc) for x, y in bg_pts], r, 0.075) & ~hard_fg
    for bb, tgt in ((fg_boxes, hard_fg), (bg_boxes, hard_bg)):
        for (x0, y0, x1, y1) in bb:          # "this rectangle is definitely person / background"
            tgt[max(0, int(y0 * sc)):int(y1 * sc) + 1, max(0, int(x0 * sc)):int(x1 * sc) + 1] = True
    hard_bg &= ~hard_fg
    # initial guess: inside the box = person, with a soft centre-weighted prior
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cw = (bx0 + bx1) / 2, max(1, (bx1 - bx0) / 2)
    prior = -1.2 * ((xx - cx) / cw) ** 2 + 0.6           # people are usually centred in their box
    prior[outside] = -8
    lab = ~hard_bg
    # soft background seeds so the first colour model has something to learn from even
    # when the box is the whole photo: the photo's border strips, and (with a face) the
    # top corners beside the head
    seed_bg = np.zeros((h, w), bool)
    e = max(2, int(0.035 * min(w, h)))
    seed_bg[:e] = True; seed_bg[:int(0.75 * h), :e] = True; seed_bg[:int(0.75 * h), -e:] = True
    if auto_face is not None:
        fx0, fy0, fx1, fy1 = auto_face
        fw = fx1 - fx0
        cxf = (fx0 + fx1) / 2
        side = (yy < fy1) & (np.abs(xx - cxf) > 1.25 * fw)
        top = yy < fy0 - 0.45 * (fy1 - fy0)
        seed_bg |= side | top
    lab &= ~(seed_bg & ~hard_fg)
    X = _features(rgb_s, pos_w)
    wr, wd = _pairwise(rgb_s)
    rng = np.random.default_rng(seed)
    q = lab.astype(float)
    for it in range(6):
        fgi = np.flatnonzero(lab.ravel())
        bgi = np.flatnonzero(~lab.ravel())
        if len(fgi) < 50 or len(bgi) < 50:
            break
        fg = GMM(6).fit(X[rng.choice(fgi, min(len(fgi), 12000), replace=False)], rng)
        bg = GMM(10).fit(X[rng.choice(bgi, min(len(bgi), 16000), replace=False)], rng)
        D = (fg.logp(X) - bg.logp(X)).reshape(h, w)
        D = np.clip(D, -12, 12) + prior * (0.5 if it == 0 else 0.25)
        q = _meanfield(D, wr, wd, hard_fg, hard_bg)
        lab = q > 0.5
        lab = _keep_person(lab, hard_fg, (bx0, by0, bx1, by1))
    q = np.where(lab, np.maximum(q, 0.62), np.minimum(q, 0.38))
    return q, sc


def _keep_person(lab, hard_fg, box):
    L, n = ndi.label(lab)
    if n == 0:
        return lab
    sizes = ndi.sum(lab, L, range(1, n + 1))
    keep = set()
    if hard_fg.any():
        keep |= set(np.unique(L[hard_fg & lab])) - {0}
    big = int(np.argmax(sizes)) + 1
    keep.add(big)
    for i in range(n):                     # other big blobs (an arm cut off by an object)
        if sizes[i] > 0.15 * sizes[big - 1]:
            keep.add(i + 1)
    out = np.isin(L, list(keep))
    # fill small holes only (gaps between arm and body stay open)
    holes = ndi.binary_fill_holes(out) & ~out
    HL, hn = ndi.label(holes)
    if hn:
        hs = ndi.sum(holes, HL, range(1, hn + 1))
        ys = np.nonzero(out.any(1))[0]
        head_y = ys.min() + 0.3 * (ys.max() - ys.min())       # no real gaps inside the head
        cy = np.array([c[0] for c in ndi.center_of_mass(holes, HL, range(1, hn + 1))])
        fill = (hs < 0.015 * out.sum()) | (cy < head_y)
        out |= np.isin(HL, np.flatnonzero(fill) + 1)
    return out


# ------------------------------------------------------------------ full-res refinement ----
def _box(a, r):
    return ndi.uniform_filter(a, size=2 * r + 1, mode="reflect")


def guided_filter_color(I, p, r, eps):
    """He et al. colour guided filter: I (h,w,3) guide in 0..1, p (h,w) input"""
    mI = np.stack([_box(I[..., c], r) for c in range(3)], -1)
    mp = _box(p, r)
    cov_Ip = np.stack([_box(I[..., c] * p, r) for c in range(3)], -1) - mI * mp[..., None]
    var = np.empty(I.shape[:2] + (3, 3))
    for i in range(3):
        for j in range(3):
            var[..., i, j] = _box(I[..., i] * I[..., j], r) - mI[..., i] * mI[..., j]
    var += np.eye(3) * eps
    a = np.linalg.solve(var, cov_Ip[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    ma = np.stack([_box(a[..., c], r) for c in range(3)], -1)
    mb = _box(b, r)
    return (ma * I).sum(-1) + mb


def refine(img, q, sc, pad=0.04, log=print):
    """full-resolution RGBA cut-out (cropped to the person + a margin)"""
    W0, H0 = img.size
    hq = Image.fromarray((q * 255).astype(np.uint8)).resize((W0, H0), Image.BILINEAR)
    pm = np.asarray(hq, dtype=np.float64) / 255.0
    ys, xs = np.nonzero(pm > 0.5)
    m = int(pad * max(W0, H0))
    x0, x1 = max(0, xs.min() - m), min(W0, xs.max() + 1 + m)
    y0, y1 = max(0, ys.min() - m), min(H0, ys.max() + 1 + m)
    rgb = np.asarray(img.crop((x0, y0, x1, y1)), dtype=np.float64) / 255.0
    hard = (pm[y0:y1, x0:x1] > 0.5).astype(np.float64)
    r = max(2, int(round(0.0045 * max(W0, H0))))
    a = guided_filter_color(rgb, hard, r, 2e-4)
    # only let the filter act near the boundary; keep solid interior/exterior
    band = ndi.binary_dilation(hard > 0.5, iterations=2 * r) & ~ndi.binary_erosion(hard > 0.5, iterations=2 * r)
    a = np.where(band, a, hard)
    a = np.clip((a - 0.18) / 0.64, 0, 1)            # crisp edge: no washed-out fringe
    a = a * a * (3 - 2 * a)
    a[a < 0.03] = 0
    rgb = decontaminate(rgb, a)
    out = np.dstack([rgb, a])
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA"), (x0, y0)


def decontaminate(rgb, a):
    """remove the photo background mixed into semi-transparent edge pixels (no halo)"""
    solid_bg = a < 0.02
    solid_fg = a > 0.97
    # local background colour: normalised blur of pure-background pixels
    wbg = solid_bg.astype(float)
    s = max(3, int(0.012 * max(a.shape)))
    den = ndi.gaussian_filter(wbg, s) + 1e-6
    B = np.stack([ndi.gaussian_filter(rgb[..., c] * wbg, s) for c in range(3)], -1) / den[..., None]
    am = np.maximum(a, 1e-3)[..., None]
    F = (rgb - (1 - am) * B) / am
    # nearest solid person colour as a fallback for very thin alpha
    if solid_fg.any():
        idx = ndi.distance_transform_edt(~solid_fg, return_distances=False, return_indices=True)
        N = rgb[idx[0], idx[1]]
    else:
        N = rgb
    t = np.clip((a - 0.45) / 0.45, 0, 1)[..., None]          # trust the un-mix only where alpha is high
    F = np.clip(F, 0, 1) * t + N * (1 - t)
    edge = (a > 0) & (a < 0.97)
    out = rgb.copy()
    out[edge] = np.clip(F[edge] * 0.7 + N[edge] * 0.3, 0, 1)
    return out


def bleed(rgba):
    """copy edge colours into the fully transparent area so mipmaps never pull in black"""
    a = np.asarray(rgba)
    al = a[..., 3]
    if (al > 0).all():
        return rgba
    idx = ndi.distance_transform_edt(al == 0, return_distances=False, return_indices=True)
    out = a.copy()
    out[..., :3] = a[idx[0], idx[1], :3]
    out[..., 3] = al
    return Image.fromarray(out, "RGBA")


def cutout(img, box=None, fg_pts=(), bg_pts=(), mask=None, log=print, fg_boxes=(), bg_boxes=()):
    q, sc = segment(img, box, fg_pts, bg_pts, mask, log=log, fg_boxes=fg_boxes, bg_boxes=bg_boxes)
    return refine(img, q, sc, log=log)
