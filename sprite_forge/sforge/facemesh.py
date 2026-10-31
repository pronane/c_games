"""Face relief from MediaPipe's canonical 3D face model (v9.5).

The photo gives the face only from the front. Until v9.4, photo3d guessed its depth with three soft bumps (nose,
brow, chin). Here MediaPipe's 468-point canonical face (Apache-2.0, sforge/data/mediapipe_face/) is posed onto the
photo's face from five landmarks (both eyes, the nose tip and the mouth corners), with a near-orthographic solvePnP
so that a slightly turned or tilted head is followed. Its depth is then rasterised into a per-pixel map in photo
coordinates. photo3d blends that map into the head's depth: the nose stands out, the eyes sit in their sockets,
the lips and chin have their real profile, and the cheeks turn away towards the ears. A three-quarter or side view
then shows a face rather than a flat mask.

    fit(landmarks, shape)          -> FaceFit or None (landmarks: BlazePose 33, photo pixels)
    relief_into(z_head, head_mask, fit) -> new front depth for the head part
"""
from __future__ import annotations
import os
import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
OBJ = os.path.join(HERE, "data", "mediapipe_face", "canonical_face_model.obj")
# BlazePose index -> canonical mesh vertex (or mean of vertices). BlazePose "left" = the person's left = mesh +x
PAIRS = {0: (1,), 2: (362, 263, 386, 374), 5: (33, 133, 159, 145), 9: (291,), 10: (61,)}
_mesh = None


def mesh():
    """(V (468,3) cm, F (898,3)) or None if the data file is missing"""
    global _mesh
    if _mesh is None:
        if not os.path.isfile(OBJ):
            return None
        V, F = [], []
        for line in open(OBJ):
            if line.startswith("v "):
                V.append([float(t) for t in line.split()[1:4]])
            elif line.startswith("f "):
                F.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
        _mesh = (np.array(V, float), np.array(F, int))
    return _mesh


class FaceFit:
    def __init__(self, uv, zpx, F, angle, err):
        self.uv, self.z, self.F, self.angle, self.err = uv, zpx, F, angle, err


def fit(landmarks, shape, max_angle=40.0, log=None):
    """pose the canonical face onto the photo. Returns None when there is no usable face (missing landmarks, a
    profile photo, a fit that does not land on the landmarks)."""
    m = mesh()
    if m is None:
        return None
    V, F = m
    try:
        import cv2
    except Exception:
        return None
    L = landmarks
    if len(L) < 11 or any((len(L[i]) > 2 and L[i][2] < 0.3) for i in PAIRS):
        return None
    img = np.array([L[i][:2] for i in PAIRS], np.float64)
    obj = np.array([V[list(v)].mean(0) for v in PAIRS.values()], np.float64)
    Xo = lambda P: np.stack([P[:, 0], -P[:, 1], -P[:, 2]], 1)      # mesh (x left, y up, z out) -> camera axes
    eye_d = np.hypot(*(img[1] - img[2]))
    if eye_d < 4:
        return None
    s0 = eye_d / np.hypot(*(obj[1, :2] - obj[2, :2]))            # px per cm
    f = 40.0 * max(shape)                                           # long lens: close to orthographic
    Z0 = f / s0
    K = np.array([[f, 0, shape[1] / 2.0], [0, f, shape[0] / 2.0], [0, 0, 1]], np.float64)
    c = img.mean(0)
    t0 = np.array([(c[0] - K[0, 2]) * Z0 / f, (c[1] - K[1, 2]) * Z0 / f, Z0], np.float64)
    t0 -= np.r_[Xo(obj).mean(0)[:2], 0]
    ok, rv, tv = cv2.solvePnP(Xo(obj), img, K, None, np.zeros(3), t0.copy(), True, cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    R, _ = cv2.Rodrigues(rv)
    ang = float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))
    if ang > max_angle:                    # a wild pose from five noisy points: keep the head frontal, fit 2D only
        R = np.eye(3); tv = t0
        ang = 0.0
    Pc = Xo(V) @ R.T + np.asarray(tv).reshape(3)
    uv = Pc[:, :2] / Pc[:, 2:3] * f + K[:2, 2]
    proj = Xo(obj) @ R.T + np.asarray(tv).reshape(3)
    err = float(np.mean(np.hypot(*(proj[:, :2] / proj[:, 2:3] * f + K[:2, 2] - img).T)) / eye_d)
    if err > 0.35:
        return None
    zpx = -(Pc[:, 2] - Pc[:, 2].mean()) * f / Pc[:, 2].mean()       # towards the viewer, photo pixels
    if log:
        log("photo3d: face relief = MediaPipe canonical face, head turned %.0f deg, landmark fit %.0f%% of eye gap"
            % (ang, 100 * err))
    return FaceFit(uv, zpx, F, ang, err)


def rasterise(ff, shape):
    """front-most depth of the posed face per pixel (nan outside)"""
    H, W = shape
    Z = np.full((H, W), -np.inf)
    uv, z = ff.uv, ff.z
    for a, b, c in ff.F:
        p = uv[[a, b, c]]
        x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        v0, v1 = p[1] - p[0], p[2] - p[0]
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-9:
            continue
        dx, dy = xx - p[0, 0], yy - p[0, 1]
        l1 = (dx * v1[1] - v1[0] * dy) / den
        l2 = (v0[0] * dy - dx * v0[1]) / den
        l0 = 1 - l1 - l2
        ins = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
        if not ins.any():
            continue
        zz = l0 * z[a] + l1 * z[b] + l2 * z[c]
        sub = Z[y0:y1 + 1, x0:x1 + 1]
        np.maximum(sub, np.where(ins, zz, -np.inf), out=sub)
    Z[~np.isfinite(Z)] = np.nan
    return Z


def relief_into(z_head, m, ff, feather=0.14, strength=1.0):
    """blend the posed face's depth into the head's front depth map. The face is placed so that its rim sits on
    the head surface, then faded in over `feather` x face width, so there is no step at the hairline, the jaw or the
    ears. Returns (new z, face mask) - z unchanged where the face does not reach."""
    Zf = rasterise(ff, z_head.shape)
    fm = np.isfinite(Zf) & m
    if fm.sum() < 30:
        return z_head, fm
    xs = np.nonzero(fm.any(0))[0]
    fw = max(4.0, float(xs.max() - xs.min() + 1))
    d = ndi.distance_transform_edt(fm)
    band = fm & (d <= max(2.0, 0.06 * fw))
    off = float(np.median((z_head - Zf)[band])) if band.sum() > 5 else float(np.median((z_head - Zf)[fm]))
    zf = np.where(fm, Zf + off, z_head)
    t = np.clip(d / (feather * fw), 0, 1)
    w = t * t * (3 - 2 * t) * strength
    out = z_head * (1 - w) + zf * w
    return np.where(m, out, z_head), fm
