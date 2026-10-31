"""Pose-seeded GrabCut matte: an offline person cut-out that needs no rembg and no pose network.

Used by `forge.py cutout` when rembg is not installed (instead of the border-colour threshold, which fails on
busy backgrounds) and whenever the caller supplies landmarks (`--landmarks-in`, hand-placed or from another
detector).  The 33 MediaPipe-format landmarks are turned into a body prior:

  * definite foreground  : thin capsules along every bone + the head core + the filled torso quad
  * probable foreground  : the same capsules at body width
  * probable background  : a wider band around them
  * definite background  : everything further out, plus any --exclude X,Y,R discs (another person, a bag ...)

OpenCV GrabCut then decides the band from colour, and a guided filter (opencv-contrib, optional) turns the hard
mask into a soft alpha so hair and sleeve edges don't stair-step.  Radii scale with shoulder width, so the
prior works at any photo size.  Only the person's own pixels are kept; nothing is drawn or generated.
"""
import numpy as np

# (a, b, core radius, body radius) as fractions of shoulder width.  MediaPipe pose indices.
BONES = [
    (11, 13, 0.07, 0.17), (13, 15, 0.06, 0.14), (12, 14, 0.07, 0.17), (14, 16, 0.06, 0.14),
    (15, 19, 0.04, 0.10), (16, 20, 0.04, 0.10), (15, 17, 0.04, 0.10), (16, 18, 0.04, 0.10),
    (23, 25, 0.09, 0.20), (25, 27, 0.07, 0.15), (24, 26, 0.09, 0.20), (26, 28, 0.07, 0.15),
    (27, 31, 0.05, 0.11), (28, 32, 0.05, 0.11), (27, 29, 0.05, 0.11), (28, 30, 0.05, 0.11),
    (29, 31, 0.04, 0.10), (30, 32, 0.04, 0.10),
]


def _capsule_dist(H, W, p0, p1):
    """Distance from every pixel to the segment p0-p1 (float32 HxW)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    p0 = np.asarray(p0, np.float32); p1 = np.asarray(p1, np.float32)
    d = p1 - p0
    L2 = float(d @ d) or 1e-6
    t = np.clip(((xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]) / L2, 0, 1)
    return np.hypot(xx - (p0[0] + t * d[0]), yy - (p0[1] + t * d[1]))


def body_prior(shape, lms, scale=1.0):
    """Return (core, body) boolean masks and the shoulder width used for scaling."""
    import cv2
    H, W = shape
    P = np.asarray([l[:2] for l in lms], np.float32)
    sw = float(np.linalg.norm(P[11] - P[12])) or 0.25 * W
    core = np.zeros((H, W), np.uint8); body = np.zeros((H, W), np.uint8)
    # bones as capsules
    for a, b, rc, rb in BONES:
        dist = _capsule_dist(H, W, P[a], P[b])
        core[dist <= rc * sw * scale] = 1
        body[dist <= rb * sw * scale] = 1
    # torso quad (shoulders + hips), widened for the body mask
    quad = P[[11, 12, 24, 23]]
    c = quad.mean(0)
    cv2.fillPoly(core, [((quad - c) * 0.80 + c).astype(np.int32)], 1)
    cv2.fillPoly(body, [((quad - c) * 1.12 + c).astype(np.int32)], 1)
    # neck + head: ellipse around the face points, sized from the ear span
    face = P[0:11]
    ear = float(np.linalg.norm(P[7] - P[8])) or 0.45 * sw
    hc = face.mean(0) + np.array([0, -0.12 * ear], np.float32)
    cv2.ellipse(core, (int(hc[0]), int(hc[1])), (int(0.40 * ear), int(0.55 * ear)), 0, 0, 360, 1, -1)
    cv2.ellipse(body, (int(hc[0]), int(hc[1])), (int(0.62 * ear), int(0.88 * ear)), 0, 0, 360, 1, -1)
    neck_top = hc + np.array([0, 0.45 * ear], np.float32)
    neck_bot = (P[11] + P[12]) / 2
    dist = _capsule_dist(H, W, neck_top, neck_bot)
    core[dist <= 0.12 * sw] = 1
    body[dist <= 0.22 * sw] = 1
    return core.astype(bool), body.astype(bool), sw


def pose_grabcut(im_rgb, lms, exclude=(), iters=6, log=print):
    """Soft alpha (float32 0..1, HxW) for the person described by `lms` (33 x [x, y, vis] in image pixels).

    exclude: iterable of (x, y, r) discs forced to background (other people, bags, posts)."""
    import cv2
    from scipy import ndimage as ndi
    rgb = np.asarray(im_rgb.convert("RGB"))
    H, W = rgb.shape[:2]
    core, body, sw = body_prior((H, W), lms)
    near = ndi.binary_dilation(body, iterations=max(2, int(0.14 * sw)))
    mask = np.full((H, W), cv2.GC_BGD, np.uint8)
    mask[near] = cv2.GC_PR_BGD
    mask[body] = cv2.GC_PR_FGD
    mask[core] = cv2.GC_FGD
    yy, xx = np.mgrid[0:H, 0:W]
    for (x, y, r) in exclude or ():
        disc = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
        mask[disc & ~body] = cv2.GC_BGD          # outside the body prior: certainly not this person
        mask[disc & body & ~core] = cv2.GC_PR_BGD # inside it: only a hint, so a disc can't bite off a sleeve
    bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    hard = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    # keep the component(s) touching the skeleton core, fill holes
    lab, n = ndi.label(hard)
    if n:
        keep_ids = np.unique(lab[core & hard]); keep_ids = keep_ids[keep_ids > 0]
        hard = np.isin(lab, keep_ids)
    hard = ndi.binary_fill_holes(hard)
    hard = ndi.binary_opening(hard, iterations=1)
    a = hard.astype(np.float32)
    try:
        gf = cv2.ximgproc.guidedFilter(bgr, (a * 255).astype(np.uint8), max(2, int(0.012 * sw)), 60)
        a = gf.astype(np.float32) / 255
    except Exception:
        a = cv2.GaussianBlur(a, (3, 3), 0)
    a = np.clip(a, 0, 1)
    a[~ndi.binary_dilation(hard, iterations=3)] = 0
    log("  matte: pose-seeded GrabCut (offline, %d px fg, shoulder %.0f px)" % (int((a > 0.5).sum()), sw))
    return a


def person_mask_from_alpha(a):
    """Stand-in for the detector's per-person mask when landmarks come from outside."""
    return (a > 0.15).astype(np.float32)
