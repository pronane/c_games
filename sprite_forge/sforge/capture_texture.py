"""forge.py capture, step 4 - paint the fitted body from the video frames (v11).

Every texel of MakeHuman's UV layout is a point on the fitted, posed body. For each frame with a camera that point is
projected into the image; it takes the frame's colour when it is the nearest surface there (z-buffer), inside the
person mask, and facing the camera. Frames are blended per texel with weight (facing)^4 x mask x sharpness, which
in practice means "the best one or two views", so the result stays sharp. Exposure differences between frames
(phones re-expose as they walk round) are removed with one RGB gain per frame, solved on the texels frames share.
Texels no frame saw (under the arms, the soles, the top of the head) are filled from their neighbours in UV space.
"""
from __future__ import annotations
import os
import numpy as np
from PIL import Image

from .render_sculpt import rasterise


def texel_map(F, fuv, res):
    nf = len(F)
    sx = fuv[:, :, 0].reshape(-1) * res
    sy = (1.0 - fuv[:, :, 1].reshape(-1)) * res                      # image rows go down, OBJ v goes up
    Fc = np.arange(nf * 3).reshape(nf, 3)
    tid, bc, _ = rasterise(sx, sy, np.zeros(nf * 3), Fc, res, res, K=8)
    return tid.reshape(res, res), bc.reshape(res, res, 3)


def vertex_normals(V, F):
    N = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def _sharpness(img):
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def bake(fitter, frames=None, res=1024, power=4.0, min_facing=0.15, log=print):
    """-> (texture RGB uint8 (res,res,3), coverage (res,res) float, stats)"""
    import cv2
    from scipy import ndimage as ndi
    bm = fitter.bm
    sh, P, Pg = fitter.posed()
    F = bm.F
    tid, bc = texel_map(F, bm.fuv, res)
    inside = tid >= 0
    ti = tid[inside]; b = bc[inside]
    X = (b[:, :, None] * P[F[ti]]).sum(1)                                  # texel points (posed body)
    Nv = vertex_normals(P, F)
    Nt = (b[:, :, None] * Nv[F[ti]]).sum(1); Nt /= np.linalg.norm(Nt, axis=1, keepdims=True) + 1e-12
    frames = frames or [t.r for t in fitter.targets]
    # rest-pose texel positions / normals (the face is where the rest head faces +Z)
    Vr = sh.V
    Xr = (b[:, :, None] * Vr[F[ti]]).sum(1)
    Nvr = vertex_normals(Vr, F)
    Nr = (b[:, :, None] * Nvr[F[ti]]).sum(1); Nr /= np.linalg.norm(Nr, axis=1, keepdims=True) + 1e-12
    hi = [bm.bi[b] for b in ("head", "neck01") if b in bm.bi]
    head_v = np.isin(bm.J[:, 0], hi) & (bm.W[:, 0] > 0.5)
    head_t = head_v[F[ti]].any(1)
    cols, ws, used = [], [], []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        m = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % r["i"]))).astype(np.float32) / 255.0
        m = ndi.minimum_filter(m, size=5)                                   # stay clear of the background edge
        pp = os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])
        if os.path.isfile(pp):                                              # the multiclass labels must agree: a
            lab = np.asarray(Image.open(pp))                                # floor the same colour as skin is not
            person = (lab >= 1) & (lab <= 4)                                # hair, skin, face, clothes - not
            m = m * ndi.minimum_filter(person.astype(np.float32), size=3)  # "other" (a TV, a chair) or background
        H, W = img.shape[:2]
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv)
        K = fitter.cams.K(r["size"])
        Pc = P @ R.T + tv
        sx = Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]; sy = Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]
        _, _, zbuf = rasterise(sx, sy, -Pc[:, 2], F, W, H, K=6)
        zbuf = zbuf.reshape(H, W)
        Xc = X @ R.T + tv
        u = Xc[:, 0] / Xc[:, 2] * K[0, 0] + K[0, 2]; v = Xc[:, 1] / Xc[:, 2] * K[1, 1] + K[1, 2]
        ui = np.clip(np.round(u - 0.5).astype(int), 0, W - 1); vi = np.clip(np.round(v - 0.5).astype(int), 0, H - 1)
        inb = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        vis = inb & (np.abs(-Xc[:, 2] - zbuf[vi, ui]) < 0.025)
        view = -(Xc / np.linalg.norm(Xc, axis=1, keepdims=True))              # towards the camera
        Ncam = Nt @ R.T
        facing = np.clip((Ncam * view).sum(1), 0, 1)
        # detail: pixels per metre at the texel (closer frames see more), and the frame's sharpness
        ppm = K[0, 0] / np.maximum(Xc[:, 2], 0.3)
        ok = vis & (facing > min_facing) & (m[vi, ui] > 0.6)        # grazing views stretch; mask edge = background
        pw = np.where(head_t, power * 2.0, power)                         # a face blurs when views are mixed
        w = np.where(ok, facing ** pw * m[vi, ui] * (ppm / 400.0) ** 2, 0.0) * (_sharpness(img) ** 0.5)
        c = _bilinear(img, u - 0.5, v - 0.5)
        cols.append(c.astype(np.float32)); ws.append(w.astype(np.float32)); used.append(r["i"])
    C = np.stack(cols); Wt = np.stack(ws)                                  # (frames, texels, 3), (frames, texels)
    # the face comes from as few frames as possible: per frame a head score (how much of the head it sees, how
    # squarely and how close); head texels are weighted by (score / best)^10, so one good frontal frame paints the
    # face instead of a patchwork of slightly misaligned ones (double eyes)
    face_t = head_t & (Nr[:, 2] > 0.35) & (Xr[:, 1] < Xr[head_t, 1].max() - 0.05)   # front of the head, not the crown
    if face_t.any():
        hs = (Wt[:, face_t]).sum(1)
        hs = hs / (hs.max() + 1e-9)
        Wt[:, face_t] *= (hs[:, None] ** 10)
    # exposure: one RGB gain per frame against the blended result, two rounds
    gains = np.ones((len(C), 3), np.float32)
    for _ in range(2):
        mix = (Wt[..., None] * C * gains[:, None, :]).sum(0) / (Wt.sum(0)[:, None] + 1e-9)
        for k in range(len(C)):
            sel = (Wt[k] > 0.05 * Wt[k].max()) & (Wt.sum(0) > Wt[k] * 1.5)
            if sel.sum() > 500:
                gains[k] = np.clip(np.median(mix[sel], 0) / (np.median(C[k][sel], 0) + 1e-3), 0.7, 1.4)
    Cg = C * gains[:, None, :]
    mean = (Wt[..., None] * Cg).sum(0) / (Wt.sum(0)[:, None] + 1e-9)
    # robust: the weighted median (by luminance) of the views, blended with the weighted mean where the views agree.
    # One misaligned view (a leg drawn over the floor, a shadow) then cannot paint a texel
    lum = Cg @ np.array([0.299, 0.587, 0.114], np.float32)
    order = np.argsort(lum, axis=0)
    ws = np.take_along_axis(Wt, order, 0); cs = np.cumsum(ws, 0)
    half = 0.5 * cs[-1]
    k = np.argmax(cs >= half[None, :], axis=0)
    pick = np.take_along_axis(order, k[None, :], 0)[0]
    med = Cg[pick, np.arange(Cg.shape[1])]
    spread = np.linalg.norm(mean - med, axis=1)
    a = np.clip((spread - 8.0) / 20.0, 0, 1)[:, None]                  # disagreement -> trust the median
    mix = mean * (1 - a) + med * a
    cover = Wt.sum(0)
    tex = np.zeros((res, res, 3), np.float32); cov = np.zeros((res, res), np.float32)
    tex[inside] = mix; cov[inside] = cover
    seen = cov > 1e-6 * (cover.max() + 1e-9)
    # fill the unseen parts of the islands, then bleed into the gutters (mip / filtering safety)
    hole = (inside & ~seen).astype(np.uint8)
    t8 = np.clip(tex, 0, 255).astype(np.uint8)
    if hole.any():
        t8 = cv2.inpaint(t8, hole, 6, cv2.INPAINT_TELEA)
    gut = (~inside).astype(np.uint8)
    t8 = cv2.inpaint(t8, gut, 3, cv2.INPAINT_TELEA) if gut.any() else t8
    stats = dict(frames=len(used), seen=float(seen.sum() / max(1, inside.sum())), gains=gains.tolist())
    log("texture: %d frames, %.0f%% of the body seen, %dx%d" % (len(used), 100 * stats["seen"], res, res))
    return t8, cov, stats


def _bilinear(img, x, y):
    H, W = img.shape[:2]
    x = np.clip(x, 0, W - 1.001); y = np.clip(y, 0, H - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    a = img[y0, x0].astype(np.float32); b = img[y0, x0 + 1].astype(np.float32)
    c = img[y0 + 1, x0].astype(np.float32); d = img[y0 + 1, x0 + 1].astype(np.float32)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def render(P, F, fuv, tex, yaw=0.0, size=(360, 480), pitch=0.0, bg=(205, 210, 216), cam=None):
    """unlit textured render (the texture already holds the photo's light). yaw 0 = facing the viewer.
    cam: optional (R, t, K) perspective camera instead of the orthographic turntable view"""
    W, H = size
    if cam is None:
        y = np.radians(yaw); p = np.radians(pitch)
        R = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
        Q = P @ R.T
        h = Q[:, 1].max() - Q[:, 1].min()
        k = 0.9 * H / h
        sx = W / 2 + (Q[:, 0] - 0.5 * (Q[:, 0].min() + Q[:, 0].max())) * k
        sy = H * 0.95 - (Q[:, 1] - Q[:, 1].min()) * k
        sz = Q[:, 2]
    else:
        R, t, K = cam
        Pc = P @ R.T + t
        sx = Pc[:, 0] / Pc[:, 2] * K[0, 0] + K[0, 2]; sy = Pc[:, 1] / Pc[:, 2] * K[1, 1] + K[1, 2]; sz = -Pc[:, 2]
    tid, bc, _ = rasterise(sx, sy, sz, F, W, H, K=6)
    tid = tid.reshape(H, W); bc = bc.reshape(H, W, 3)
    out = np.empty((H, W, 3), np.uint8); out[:] = bg
    m = tid >= 0
    uv = (bc[m][:, :, None] * fuv[tid[m]]).sum(1)
    T = tex.shape[0]
    out[m] = _bilinear(tex, uv[:, 0] * T - 0.5, (1 - uv[:, 1]) * T - 0.5).astype(np.uint8)
    return out, m
