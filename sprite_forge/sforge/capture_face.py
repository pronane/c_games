"""forge.py capture - the face's own shape, from the video (v11.2).

The body fit gets the head's size right, but the face on it is MakeHuman's average face: the nose, eyes and mouth
painted from the best frontal frame then sit where the camera ray happened to hit that average face, and turn wrong
as soon as the head turns (a nose painted on a cheek, eyes too wide apart). Here the face itself is fitted:

  1 detect       MediaPipe Face Landmarker (478 points, Apache-2.0) on every frame that sees the face (yaw within
                 60 deg), on a crop round the head, upscaled - the face is ~70 px in a phone turnaround
  2 head pose    each frame gets the head's own pose from its landmarks (PnP): the body's cameras put the face
                 25-40% of its width off (a small part of a whole-body fit, and the head moves a little)
  3 correspond   the same Face Landmarker run on a render of MakeHuman's average face: each landmark gets the
                 point of MakeHuman's surface under it (so "eye corner" is MakeHuman's eye corner)
  4 fit          MakeHuman's own face modifiers (nose, mouth, eyes, brows, chin, cheeks, forehead, head size and
                 position - FACE_SLIDERS), shared by all frames, by bounded least squares on the landmarks'
                 reprojection through each frame's head pose (alternating with the poses).
                 They are ordinary MakeHuman modifiers: NAME.mhm carries the fitted face into MakeHuman / MPFB.

    fit_face(fitter, frames, log)          -> report dict; fitter.sl updated, fitter.face = head poses etc.
    landmark_error(fitter, frames, corr)   -> mean landmark error (% of the face width) on frames not used
The texture bake projects the head through those poses (capture_texture), so the face is painted where it is.
"""
from __future__ import annotations
import os
import numpy as np
from PIL import Image


# slider -> [(modifier "group/base", negative-side target suffix, positive-side suffix)], value in -1..1
# (MakeHuman modifier "group/base-neg|pos": a negative value applies base-neg, a positive one base-pos)
FACE_SLIDERS = {
    "head_trans_x": [("head/head-trans", "in", "out")],
    "head_trans_y": [("head/head-trans", "down", "up")],
    "head_trans_z": [("head/head-trans", "backward", "forward")],
    "nose_y": [("nose/nose-trans", "down", "up")],
    "nose_z": [("nose/nose-trans", "backward", "forward")],
    "nose_len": [("nose/nose-scale-vert", "decr", "incr")],
    "nose_width": [("nose/nose-scale-horiz", "decr", "incr")],
    "nose_depth": [("nose/nose-scale-depth", "decr", "incr")],
    "nostrils": [("nose/nose-nostrils-width", "decr", "incr")],
    "nose_point": [("nose/nose-point-width", "decr", "incr")],
    "mouth_width": [("mouth/mouth-scale-horiz", "decr", "incr")],
    "mouth_height": [("mouth/mouth-scale-vert", "decr", "incr")],
    "mouth_y": [("mouth/mouth-trans", "down", "up")],
    "mouth_z": [("mouth/mouth-trans", "backward", "forward")],
    "upperlip": [("mouth/mouth-upperlip-height", "decr", "incr")],
    "lowerlip": [("mouth/mouth-lowerlip-height", "decr", "incr")],
    "eyes_apart": [("eyes/l-eye-trans", "in", "out"), ("eyes/r-eye-trans", "in", "out")],
    "eyes_y": [("eyes/l-eye-trans", "down", "up"), ("eyes/r-eye-trans", "down", "up")],
    "eyes_size": [("eyes/l-eye-scale", "decr", "incr"), ("eyes/r-eye-scale", "decr", "incr")],
    "brows_y": [("eyebrows/eyebrows-trans", "down", "up")],
    "brows_z": [("eyebrows/eyebrows-trans", "backward", "forward")],
    "chin_prominent": [("chin/chin-prominent", "decr", "incr")],
    "chin_width": [("chin/chin-width", "decr", "incr")],
    "chin_height": [("chin/chin-height", "decr", "incr")],
    "cheek_bones": [("cheek/l-cheek-bones", "decr", "incr"), ("cheek/r-cheek-bones", "decr", "incr")],
    "cheek_volume": [("cheek/l-cheek-volume", "decr", "incr"), ("cheek/r-cheek-volume", "decr", "incr")],
    "forehead_z": [("forehead/forehead-trans", "backward", "forward")],
    "forehead_h": [("forehead/forehead-scale-vert", "decr", "incr")],
}
HEAD_SLIDERS = ("head_width", "head_height", "head_depth")          # capture_body.SLIDERS, refitted here too
MAX_YAW = 60.0


# ------------------------------------------------------------------ 1 detect
def _landmarker():
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    from .capture_track import model
    o = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model("face_landmarker.task")),
                                     running_mode=vision.RunningMode.IMAGE, num_faces=1,
                                     min_face_detection_confidence=0.4, min_face_presence_confidence=0.4)
    return vision.FaceLandmarker.create_from_options(o)


def detect(cap_dir, frames, cache=True):
    """{frame i: (478, 2) landmark pixels} for the frames that see the face; cached in CAP/face_landmarks.npz"""
    import mediapipe as mp
    cp = os.path.join(cap_dir, "face_landmarks.npz")
    old = dict(np.load(cp)) if (cache and os.path.isfile(cp)) else {}
    out = {}
    det = None
    for r in frames:
        if abs(((r["yaw"] + 180) % 360) - 180) > MAX_YAW:
            continue
        k = "%04d" % r["i"]
        if k in old:
            if old[k].size:
                out[r["i"]] = old[k]
            continue
        L = r["lm"]
        pts = np.array([L[i][:2] for i in (0, 2, 5, 7, 8, 9, 10)], float)        # nose, eyes, ears, mouth
        c = pts.mean(0)
        half = max(1.6 * np.ptp(pts[:, 0]), 1.4 * np.ptp(pts[:, 1]), 24.0)
        img = np.asarray(Image.open(os.path.join(cap_dir, "frames", k + ".jpg")).convert("RGB"))
        x0, y0 = int(c[0] - half), int(c[1] - half * 1.1)
        size = int(2 * half)
        crop = np.zeros((size, size, 3), np.uint8)
        sx0, sy0 = max(0, x0), max(0, y0); sx1, sy1 = min(img.shape[1], x0 + size), min(img.shape[0], y0 + size)
        if sx1 <= sx0 or sy1 <= sy0:
            old[k] = np.zeros((0, 2)); continue
        crop[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
        up = np.ascontiguousarray(np.asarray(Image.fromarray(crop).resize((512, 512), Image.LANCZOS)))
        if det is None:
            det = _landmarker()
        res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=up))
        if not res.face_landmarks:
            old[k] = np.zeros((0, 2)); continue
        p = np.array([[q.x, q.y] for q in res.face_landmarks[0]]) * size + [x0, y0]
        out[r["i"]] = old[k] = p
    if cache:
        np.savez_compressed(cp, **old)
    return out


# ------------------------------------------------------------------ 3 correspond
def correspondence(shape, log=None):
    """landmark (468) -> a point on MakeHuman's face: the same Face Landmarker run on a front render of this
    (average) MakeHuman head, each landmark read back off the surface under it. -> (vertex ids (468,3), barycentric
    weights (468,3)); use pts(P, corr). (Aligning MediaPipe's canonical face by surface ICP slid it down a centimetre
    - "eyes" on the cheeks - so the features are matched by the detector itself.)"""
    import mediapipe as mp
    from .render_sculpt import rasterise
    from .capture_texture import vertex_normals
    bm = shape.m
    V, F = shape.V, bm.F
    head = (bm.J[:, 0] == bm.bi["head"]) & (bm.W[:, 0] > 0.5)
    c = V[head].mean(0); R = 0.15; W = 768
    s = W / (2 * R)
    x = (V[:, 0] - c[0]) * s + W / 2; y = (c[1] + 0.02 - V[:, 1]) * s + W / 2
    tid, bc, _ = rasterise(x, y, V[:, 2], F, W, W, K=6)
    tid = tid.reshape(W, W); bc = np.asarray(bc).reshape(W, W, 3)
    N = vertex_normals(V, F)
    l = np.array([0.25, 0.35, 0.9]); l /= np.linalg.norm(l)
    img = np.full((W, W, 3), 30, np.uint8)
    ok = tid >= 0
    shade = np.clip(N[F[tid[ok]]].mean(1) @ l, 0, 1)
    img[ok] = (np.array([224, 180, 150]) * (0.35 + 0.65 * shade[:, None])).astype(np.uint8)
    res = _landmarker().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)))
    if not res.face_landmarks:
        return None
    p = np.array([[q.x, q.y] for q in res.face_landmarks[0]])[:468] * W
    ids = np.zeros((468, 3), int); wts = np.zeros((468, 3))
    for j, (u, v) in enumerate(p):
        ui, vi = int(np.clip(u, 0, W - 1)), int(np.clip(v, 0, W - 1))
        if tid[vi, ui] < 0:                                        # off the mesh (rare): nearest covered pixel
            ys, xs = np.nonzero(ok)
            k = np.argmin((xs - ui) ** 2 + (ys - vi) ** 2); vi, ui = ys[k], xs[k]
        ids[j] = F[tid[vi, ui]]; wts[j] = bc[vi, ui]
    if log:
        log("face: landmarks placed on MakeHuman's own face (the same detector on a render of it)")
    return ids, wts


def pts(P, corr):
    ids, w = corr
    return (P[ids] * w[..., None]).sum(1)


# ------------------------------------------------------------------ 4 fit
def _all_sliders():
    from .capture_body import SLIDERS
    return list(HEAD_SLIDERS) + list(FACE_SLIDERS), SLIDERS


def _pnp(X, x, K, cam=None, guess=None):
    """head pose (rvec, tvec): model -> camera, from 3D face points X seen at pixels x (iterative PnP from the
    previous pose or the body camera). Its depth is loose - a 60 px face cannot tell distance from size - but its
    projection is what painting needs, and that matches the landmarks to a few px"""
    import cv2
    X = np.ascontiguousarray(X, np.float64); x = np.ascontiguousarray(x, np.float64)
    g = guess if guess is not None else cam
    rv = np.array(g[0], np.float64).reshape(3, 1); tv = np.array(g[1], np.float64).reshape(3, 1)
    ok, rv, tv = cv2.solvePnP(X, x, K, None, rv, tv, useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
    return rv.ravel().copy(), tv.ravel().copy()


def _project(X, rv, tv, K):
    import cv2
    uv, _ = cv2.projectPoints(np.ascontiguousarray(X, np.float64), np.asarray(rv, np.float64), np.asarray(tv, np.float64), K, None)
    return uv.reshape(-1, 2)


def head_poses(fitter, frames, dets, Xh, guess=None):
    """each frame's own head pose (model -> camera) from its face landmarks: the body's cameras put the face 10-50 px
    off (camera error on a small part, and the head moves a little while the camera walks round)"""
    byi = {r["i"]: r for r in frames}
    out = {}
    for i, x in dets.items():
        if i not in byi or i not in fitter.cams.cam:
            continue
        K = fitter.cams.K(byi[i]["size"])
        out[i] = _pnp(Xh, x[:468], K, fitter.cams.cam[i], guess.get(i) if guess else None)
    return out


def fit_face(fitter, frames, log=print, lam=0.0001):
    """the face sliders, shared by all frames, each frame with its own head pose; updates fitter.sl and stores the
    head poses in fitter.face (the texture bake projects the head through them). -> report dict (or None)"""
    from scipy.optimize import lsq_linear
    dets = detect(fitter.dir, frames)
    if len(dets) < 2:
        log("face: the face is seen in %d frames - kept MakeHuman's average face" % len(dets))
        return None
    byi = {r["i"]: r for r in frames}
    bm = fitter.bm
    keys, _ = _all_sliders()
    sl = dict(fitter.sl)
    for k in keys:
        sl.setdefault(k, 0.0)
    corr = correspondence(bm.shape(fitter.mac, {k: v for k, v in sl.items() if k not in keys}, fitter.height), log)

    def head_pts(s):
        sh = bm.shape(fitter.mac, s, fitter.height)
        P, _, _ = sh.pose(fitter.dirs)                                    # the head is not posed: P == rest there
        return pts(P, corr)

    def residuals(Xh, poses):
        out = []
        for i, (rv, tv) in poses.items():
            K = fitter.cams.K(byi[i]["size"]); x = dets[i][:468]
            out.append(np.linalg.norm(_project(Xh, rv, tv, K) - x, axis=1) / (np.ptp(x[:, 0]) + 1e-6))
        return out
    Xh = head_pts(sl)
    poses = head_poses(fitter, frames, dets, Xh)
    before = float(np.mean([np.median(e) for e in residuals(Xh, poses)]) * 100)
    cam_err = []
    for i in poses:
        K = fitter.cams.K(byi[i]["size"]); rv, tv = fitter.cams.cam[i]; x = dets[i][:468]
        cam_err.append(np.median(np.linalg.norm(_project(Xh, rv, tv, K) - x, axis=1)) / np.ptp(x[:, 0]) * 100)
    for it in range(3):
        Xh = head_pts(sl)
        D = []
        for k in keys:
            s2 = dict(sl); st = 0.25 if sl[k] < 0.75 else -0.25; s2[k] = sl[k] + st
            D.append((head_pts(s2) - Xh) / st)
        rows, rhs, wts = [], [], []
        for i, (rv, tv) in poses.items():
            K = fitter.cams.K(byi[i]["size"]); x = dets[i][:468]
            fw = np.ptp(x[:, 0]) + 1e-6
            u0 = _project(Xh, rv, tv, K)
            e = np.linalg.norm(u0 - x, axis=1)
            w = 1.0 / np.maximum(1.0, e / (2.5 * np.median(e) + 1e-6))     # robust: hair over the brow, a beard
            Jk = [((_project(Xh + 1e-3 * Dk, rv, tv, K) - u0) / 1e-3) for Dk in D]
            rows.append(np.stack([j.ravel() for j in Jk], 1) / fw * np.repeat(w, 2)[:, None])
            rhs.append((x - u0).ravel() / fw * np.repeat(w, 2))
        A = np.vstack(rows); b = np.concatenate(rhs)
        x0 = np.array([sl[k] for k in keys])
        n = len(b) / 2.0
        A = np.vstack([A, np.sqrt(lam * n) * np.eye(len(keys))]); b = np.r_[b, -np.sqrt(lam * n) * x0]
        sol = lsq_linear(A, b, bounds=(-1 - x0, 1 - x0))
        for k, dx in zip(keys, sol.x):
            sl[k] = float(np.clip(sl[k] + dx, -1, 1))
        Xh = head_pts(sl)
        poses = head_poses(fitter, frames, dets, Xh, guess=poses)
    after = float(np.mean([np.median(e) for e in residuals(Xh, poses)]) * 100)
    fitter.sl = sl
    # where the head really is, in the body's frame: each frame's head pose seen through its body camera, the median
    import cv2
    # (sideways / up-down only, at the body camera's distance: the image says where, not how far)
    offs = []
    c0 = Xh.mean(0)
    for i, (rv, tv) in poses.items():
        K = fitter.cams.K(byi[i]["size"])
        Rc, _ = cv2.Rodrigues(np.asarray(fitter.cams.cam[i][0], float)); tc = np.asarray(fitter.cams.cam[i][1], float)
        zc = (Rc @ c0 + tc)[2]
        d_px = _project(c0[None], rv, tv, K)[0] - _project(c0[None], *fitter.cams.cam[i], K)[0]
        offs.append(Rc.T @ np.array([d_px[0] * zc / K[0, 0], d_px[1] * zc / K[1, 1], 0.0]))
    off = np.median(np.array(offs), 0)
    fitter.face = dict(corr=corr, poses=poses, dets=dets, offset=off, frames=sorted(poses))
    big = sorted(((abs(sl[k]), k) for k in FACE_SLIDERS if abs(sl[k]) > 0.15), reverse=True)[:6]
    log("face: %d frames; landmark error %.1f%% -> %.1f%% of the face width (%s); the body cameras put the face "
        "%.0f%% off, the head's own pose per frame fixes that" % (
            len(poses), before, after, ", ".join("%s %+.2f" % (k, sl[k]) for _, k in big) or "close to average",
            float(np.mean(cam_err))))
    return dict(frames=len(poses), err_pct_before=before, err_pct_after=after, body_camera_err_pct=float(np.mean(cam_err)),
                head_offset_cm=(100 * off).round(1).tolist(), sliders={k: sl[k] for k in keys})


def landmark_error(fitter, frames, corr):
    """held-out frames: each gets its own head pose from its landmarks (the shape is not refitted), then the median
    landmark error in % of the face width - how well the face SHAPE predicts frames it never saw"""
    dets = detect(fitter.dir, frames)
    byi = {r["i"]: r for r in frames}
    sh = fitter.bm.shape(fitter.mac, fitter.sl, fitter.height)
    P, _, _ = sh.pose(fitter.dirs)
    Xh = pts(P, corr)
    out = []
    for i, x in dets.items():
        if i not in byi or i not in fitter.cams.cam:
            continue
        K = fitter.cams.K(byi[i]["size"])
        rv, tv = _pnp(Xh, x[:468], K, fitter.cams.cam[i])
        out.append(np.median(np.linalg.norm(_project(Xh, rv, tv, K) - x[:468], axis=1)) / np.ptp(x[:468, 0]) * 100)
    return (float(np.mean(out)), len(out)) if out else (None, 0)


# ------------------------------------------------------------------ 5 a close-up photo of the face (optional)
def paint_photo(fitter, tex, mesh, photo, log=print, focal_k=1.2):
    """paint a close-up photo of the face (phone, front-on, even light) onto the face of the texture `tex`
    (the atlas from capture_texture.bake, mesh = (Mesh, skinning) or None for the bare body). The photo's head pose
    comes from its landmarks against the fitted face; its colours are matched to the video's texture where they
    overlap; it is feathered in by how squarely each texel faces the photo. -> (new texture, info) or (tex, None)"""
    import cv2
    import mediapipe as mp
    from .capture_texture import texel_map, vertex_normals, _bilinear
    from .render_sculpt import rasterise
    img = np.asarray(Image.open(photo).convert("RGB"))
    # detect on a downscaled copy when huge (the detector works at 256 px internally anyway)
    sc = min(1.0, 1600.0 / max(img.shape[:2]))
    small = np.ascontiguousarray(np.asarray(Image.fromarray(img).resize((int(img.shape[1] * sc), int(img.shape[0] * sc)))))
    res = _landmarker().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=small))
    if not res.face_landmarks:
        log("face photo: no face found in %s - not used" % os.path.basename(photo))
        return tex, None
    H, W = img.shape[:2]
    x = np.array([[q.x * W, q.y * H] for q in res.face_landmarks[0]])[:468]
    corr = fitter.face["corr"]
    bm = fitter.bm
    if mesh is not None:
        M, S = mesh
        P = M.pose(S); F = M.F; fuv = M.fuv; Jm, Wm = M.J, M.W
    else:
        sh, P, _ = fitter.posed(); F = bm.F; fuv = bm.fuv; Jm, Wm = bm.J, bm.W
    shb, Pb, _ = fitter.posed()
    Xh = pts(Pb, corr)
    f = focal_k * max(W, H)
    K = np.array([[f, 0, W / 2.0], [0, f, H / 2.0], [0, 0, 1.0]])
    rv, tv = cv2.solvePnP(Xh, x, K, None, flags=cv2.SOLVEPNP_EPNP)[1:]
    ok, rv, tv = cv2.solvePnP(Xh, x, K, None, rv, tv, useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
    err = np.median(np.linalg.norm(_project(Xh, rv.ravel(), tv.ravel(), K) - x, axis=1)) / np.ptp(x[:, 0]) * 100
    if err > 6.0:
        log("face photo: the face does not match the capture (landmark error %.0f%% of the face) - not used" % err)
        return tex, None
    R, _ = cv2.Rodrigues(rv); t = tv.ravel()
    hv = (Jm[:, 0] == bm.bi["head"]) & (Wm[:, 0] > 0.5)
    if mesh is not None:
        hv &= (M.layer == 0)                                            # the skin of the face, not the hair shell
    hF = F[hv[F].all(1)]
    res_ = tex.shape[0]
    tid, bc = texel_map(F, fuv, res_)
    inside = tid >= 0
    ti = tid[inside]; b = bc[inside]
    face_t = hv[F[ti]].all(1)
    X = (b[face_t][:, :, None] * P[F[ti[face_t]]]).sum(1)
    Nv = vertex_normals(P, F)
    Nt = (b[face_t][:, :, None] * Nv[F[ti[face_t]]]).sum(1); Nt /= np.linalg.norm(Nt, axis=1, keepdims=True) + 1e-12
    Pc = P @ R.T + t
    sx = Pc[:, 0] / Pc[:, 2] * f + W / 2.0; sy = Pc[:, 1] / Pc[:, 2] * f + H / 2.0
    _, _, zb = rasterise(sx, sy, -Pc[:, 2], hF, W, H, K=6)
    zb = zb.reshape(H, W)
    Xc = X @ R.T + t
    u = Xc[:, 0] / Xc[:, 2] * f + W / 2.0; v = Xc[:, 1] / Xc[:, 2] * f + H / 2.0
    ui = np.clip(u.astype(int), 0, W - 1); vi = np.clip(v.astype(int), 0, H - 1)
    vis = (u >= 0) & (u < W) & (v >= 0) & (v < H) & (np.abs(-Xc[:, 2] - zb[vi, ui]) < 0.02)
    view = -(Xc / np.linalg.norm(Xc, axis=1, keepdims=True))
    facing = np.clip(((Nt @ R.T) * view).sum(1), 0, 1)
    # only inside the face the detector found (its landmarks' hull, shrunk a little), feathered towards the edge
    hull = cv2.convexHull(x.astype(np.float32))
    inface = np.array([cv2.pointPolygonTest(hull, (float(a), float(c)), True) for a, c in zip(u, v)])
    edge = np.clip(inface / (0.08 * np.ptp(x[:, 0])), 0, 1)
    w = np.where(vis, np.clip((facing - 0.35) / 0.4, 0, 1) * edge, 0.0)
    if (w > 0.5).sum() < 200:
        log("face photo: too little of the face visible - not used")
        return tex, None
    col = _bilinear(img, u - 0.5, v - 0.5)
    rows, cols = np.nonzero(inside)
    rr, cc = rows[face_t], cols[face_t]
    old = tex[rr, cc].astype(float)
    sel = w > 0.5
    gain = np.clip(np.median(old[sel] + 1, 0) / (np.median(col[sel] + 1, 0)), 0.6, 1.6)   # the video's colour
    new = np.clip(col * gain, 0, 255)
    out = tex.copy()
    out[rr, cc] = np.clip(old * (1 - w[:, None]) + new * w[:, None], 0, 255).astype(np.uint8)
    px = np.ptp(x[:, 0])
    log("face photo: %s, face %d px wide (the video's best: ~%d px), landmark error %.1f%%, %d face texels painted" % (
        os.path.basename(photo), px, max((np.ptp(d[:468, 0]) for d in fitter.face["dets"].values()), default=0), err,
        int(sel.sum())))
    return out, dict(photo=os.path.basename(photo), face_px=float(px), landmark_err_pct=float(err), texels=int(sel.sum()),
                     gain=gain.round(3).tolist())
