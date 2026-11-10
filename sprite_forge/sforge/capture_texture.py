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


# head texels are weighted by (frame's head score / best) ** FACE_POWER: high = the face from (nearly) one frame
FACE_POWER = float(os.environ.get("SFS_FACE_POWER", "10"))

def bake(fitter, frames=None, res=1024, power=4.0, min_facing=0.15, log=print, mesh=None, delight=False, clean=True):
    """-> (texture RGB uint8 (res,res,3), coverage (res,res) float, stats)
    mesh: optional (rest Mesh, skinning matrices) from capture_layers - body + clothes + skirt + hair in one atlas;
    default the bare body with MakeHuman's UVs"""
    import cv2
    from scipy import ndimage as ndi
    bm = fitter.bm
    sh, P, Pg = fitter.posed()
    F = bm.F
    fuv = bm.fuv
    Vrest = sh.V
    Jm, Wm = bm.J, bm.W
    body_v = np.ones(len(P), bool)
    if mesh is not None:
        M, S = mesh
        P = M.pose(S); F = M.F; fuv = M.fuv; Vrest = M.V; Jm, Wm = M.J, M.W
        body_v = M.layer == 0
    tid, bc = texel_map(F, fuv, res)
    inside = tid >= 0
    ti = tid[inside]; b = bc[inside]
    X = (b[:, :, None] * P[F[ti]]).sum(1)                                  # texel points (posed body)
    Nv = vertex_normals(P, F)
    Nt = (b[:, :, None] * Nv[F[ti]]).sum(1); Nt /= np.linalg.norm(Nt, axis=1, keepdims=True) + 1e-12
    frames = frames or [t.r for t in fitter.targets]
    # rest-pose texel positions / normals (the face is where the rest head faces +Z)
    Vr = Vrest
    Xr = (b[:, :, None] * Vr[F[ti]]).sum(1)
    Nvr = vertex_normals(Vr, F)
    Nr = (b[:, :, None] * Nvr[F[ti]]).sum(1); Nr /= np.linalg.norm(Nr, axis=1, keepdims=True) + 1e-12
    hi = [bm.bi[b] for b in ("head", "neck01") if b in bm.bi]
    head_v = np.isin(Jm[:, 0], hi) & (Wm[:, 0] > 0.5) & body_v
    head_t = head_v[F[ti]].any(1)
    # v11.2: frames that see the face carry the head's own pose (capture_face): the head's texels (face, scalp, hair
    # shell) are projected through it - the body camera puts the face 10-50 px off in a phone turnaround
    face = getattr(fitter, "face", None) or {}
    poses = face.get("poses", {})
    hv = (Jm[:, 0] == bm.bi["head"]) & (Wm[:, 0] > 0.5)
    hd_t = hv[F[ti]].all(1)
    hd_F = F[hv[F].all(1)]
    cols, ws, used, labs = [], [], [], []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        m = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % r["i"]))).astype(np.float32) / 255.0
        m = ndi.minimum_filter(m, size=5)                                   # stay clear of the background edge
        pp = os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])
        lab = None
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
        if r["i"] in poses and hd_t.any():
            Rh, _ = cv2.Rodrigues(np.asarray(poses[r["i"]][0], float)); th = np.asarray(poses[r["i"]][1], float)
            Ph = P @ Rh.T + th
            hx = Ph[:, 0] / Ph[:, 2] * K[0, 0] + K[0, 2]; hy = Ph[:, 1] / Ph[:, 2] * K[1, 1] + K[1, 2]
            _, _, zh = rasterise(hx, hy, -Ph[:, 2], hd_F, W, H, K=6)
            zh = zh.reshape(H, W)
            Xh = X[hd_t] @ Rh.T + th
            uh = Xh[:, 0] / Xh[:, 2] * K[0, 0] + K[0, 2]; vh = Xh[:, 1] / Xh[:, 2] * K[1, 1] + K[1, 2]
            uih = np.clip(np.round(uh - 0.5).astype(int), 0, W - 1); vih = np.clip(np.round(vh - 0.5).astype(int), 0, H - 1)
            inh = (uh >= 0) & (uh < W) & (vh >= 0) & (vh < H)
            u[hd_t], v[hd_t], ui[hd_t], vi[hd_t] = uh, vh, uih, vih
            vis[hd_t] = inh & (np.abs(-Xh[:, 2] - zh[vih, uih]) < 0.025)
            vh_ = -(Xh / np.linalg.norm(Xh, axis=1, keepdims=True))
            facing[hd_t] = np.clip(((Nt[hd_t] @ Rh.T) * vh_).sum(1), 0, 1)
        ok = vis & (facing > min_facing) & (m[vi, ui] > 0.6)        # grazing views stretch; mask edge = background
        pw = np.where(head_t, power * 2.0, power)                         # a face blurs when views are mixed
        w = np.where(ok, facing ** pw * m[vi, ui] * (ppm / 400.0) ** 2, 0.0) * (_sharpness(img) ** 0.5)
        c = _bilinear(img, u - 0.5, v - 0.5)
        cols.append(np.clip(np.round(c), 0, 255).astype(np.uint8)); ws.append(w.astype(np.float32)); used.append(r["i"])
        labs.append(_label_class(lab[vi, ui]) if lab is not None else np.zeros(len(u), np.int8))
    C = np.stack(cols); Wt = np.stack(ws)                                  # (frames, texels, 3), (frames, texels)
    # label vote per texel: hair / skin / clothes. A sample whose label disagrees with the texel's majority is a
    # misplacement (a hand hanging over the jeans, a sleeve over the waist) and is dropped
    Lb = np.stack(labs)
    tally = np.stack([(Wt * (Lb == c)).sum(0) for c in range(4)])
    major = np.argmax(tally[1:], 0) + 1
    strong = tally[1:].max(0) > 0.6 * (tally[1:].sum(0) + 1e-9)
    disagree = (Lb != major[None, :]) & (Lb > 0) & strong[None, :]
    Wt = np.where(disagree, 0.0, Wt)
    if mesh is not None:
        # a layer takes only its own kind of pixel: clothes / skirt only clothes-labelled samples, hair only hair (a
        # hem that ends a little higher in the video must not paint the legs onto the skirt)
        lay = M.layer[F[ti, 0]]
        want = np.select([lay == 1, lay == 2, lay == 3], [3, 3, 1], 0).astype(np.int8)
        # a texel with no sample of its own kind (a hem hanging lower than the real one) stays unseen and is
        # filled from the garment around it
        Wt = np.where((want[None, :] > 0) & (Lb != want[None, :]), 0.0, Wt)
        # a skirt is one garment: leggings / tights under it are labelled clothes too, so samples far from the
        # skirt's own median colour are dropped
        sk = np.nonzero(lay == 2)[0]
        if len(sk):
            sub = sk[::max(1, len(sk) // 20000)]                          # the reference from a subsample
            Ws = Wt[:, sub]
            ref = np.median(C[:, sub][Ws > 0].astype(np.float32), 0) if (Ws > 0).any() else None
            if ref is not None:
                for i in range(0, len(sk), 100000):                       # chunks: frames x texels floats are big
                    c = sk[i:i + 100000]
                    far = np.linalg.norm(C[:, c].astype(np.float32) - ref, axis=2) > 70.0
                    Wt[:, c] = np.where(far, 0.0, Wt[:, c])
                # and the legs under it are not the dress: below the crotch, body / clothes texels drop dress-coloured
                # samples (where the real hem sits lower than the leg texel thought)
                crotch = 0.5 * (sh.joint("upperleg01.L")[1] + sh.joint("upperleg01.R")[1]) - 0.06
                lg = np.nonzero((lay <= 1) & (Xr[:, 1] < crotch - 0.03))[0]
                for i in range(0, len(lg), 100000):
                    c = lg[i:i + 100000]
                    near = np.linalg.norm(C[:, c].astype(np.float32) - ref, axis=2) < 40.0
                    Wt[:, c] = np.where(near, 0.0, Wt[:, c])
    # hands are skin unless the video never shows them as skin (gloves): a hand hanging by the thigh must not take the
    # trousers' colour
    hand_v = np.isin(Jm[:, 0], [bm.bi[b] for b in ("wrist.L", "wrist.R") if b in bm.bi]) & body_v
    hand_t = np.nonzero(hand_v[F[ti]].all(1))[0]
    if len(hand_t):
        Lh = Lb[:, hand_t]; Wh = Wt[:, hand_t]
        has_skin = (Wh * (Lh == 2)).sum(0) > 0
        Wt[:, hand_t] = np.where(has_skin[None, :] & (Lh != 2), 0.0, Wh)
    # the face comes from as few frames as possible: per frame a head score (how much of the head it sees, how
    # squarely and how close); head texels are weighted by (score / best)^10, so one good frontal frame paints the
    # face instead of a patchwork of slightly misaligned ones (double eyes)
    face_t = head_t & (Nr[:, 2] > 0.35) & (Xr[:, 1] < Xr[head_t, 1].max() - 0.05)   # front of the head, not the crown
    if face_t.any():
        hs = (Wt[:, face_t]).sum(1)
        hs = hs / (hs.max() + 1e-9)
        Wt[:, face_t] *= (hs[:, None] ** FACE_POWER)
    # exposure: one RGB gain per frame against the blended result, two rounds. Samples stay uint8 and the blend runs
    # in texel chunks: (frames x texels) float copies of a 2048^2 atlas would need several GB
    n = C.shape[1]; CH = 150000
    chunks = [slice(i, min(n, i + CH)) for i in range(0, n, CH)]
    Wsum = Wt.sum(0)
    gains = np.ones((len(C), 3), np.float32)
    for _ in range(2):
        mix = np.concatenate([(Wt[:, c, None] * (C[:, c].astype(np.float32) * gains[:, None, :])).sum(0)
                              / (Wsum[c, None] + 1e-9) for c in chunks])
        for k in range(len(C)):
            sel = (Wt[k] > 0.05 * Wt[k].max()) & (Wsum > Wt[k] * 1.5)
            if sel.sum() > 500:
                gains[k] = np.clip(np.median(mix[sel], 0) / (np.median(C[k][sel].astype(np.float32), 0) + 1e-3), 0.7, 1.4)
    # robust: the weighted median (by luminance) of the views, blended with the weighted mean where the views agree.
    # One misaligned view (a leg drawn over the floor, a shadow) then cannot paint a texel
    out = []
    for c in chunks:
        Cg = C[:, c].astype(np.float32) * gains[:, None, :]; Wc = Wt[:, c]
        mean = (Wc[..., None] * Cg).sum(0) / (Wc.sum(0)[:, None] + 1e-9)
        lum = Cg @ np.array([0.299, 0.587, 0.114], np.float32)
        order = np.argsort(lum, axis=0)
        wsrt = np.take_along_axis(Wc, order, 0); cs = np.cumsum(wsrt, 0)
        kk = np.argmax(cs >= 0.5 * cs[-1][None, :], axis=0)
        pick = np.take_along_axis(order, kk[None, :], 0)[0]
        med = Cg[pick, np.arange(Cg.shape[1])]
        spread = np.linalg.norm(mean - med, axis=1)
        al = np.clip((spread - 8.0) / 20.0, 0, 1)[:, None]               # disagreement -> trust the median
        out.append(mean * (1 - al) + med * al)
    mix = np.concatenate(out)
    cover = Wt.sum(0)
    seen_t = cover > 1e-6 * (cover.max() + 1e-9)
    light = None
    if delight:
        # v11.2: the room's light divided out (capture_light); the lit texture is kept for the held-out check
        from . import capture_light as CLI
        lay_t = (M.layer[F[ti, 0]] if mesh is not None else np.zeros(len(ti), int))
        groups = lay_t * 4 + np.where(tally[1:].sum(0) > 0, major, 0)
        alb, light = CLI.fit_light(mix, Nt, groups, weights=seen_t.astype(float), log=log)
    seen = np.zeros((res, res), bool); seen[inside] = seen_t
    cov = np.zeros((res, res), np.float32); cov[inside] = cover

    stats = dict(frames=len(used), seen=float(seen.sum() / max(1, inside.sum())), gains=gains.tolist())
    known = seen
    if clean:
        # v11.3: off-colour skin and garment speckles dropped, every unseen texel filled on the body in 3D
        # (capture_clean) - only the gutters between UV islands are left to 2D inpainting
        from . import capture_clean as CC
        lay_c = (M.layer[F[ti, 0]] if mesh is not None else np.zeros(len(ti), int))
        lab_c = np.where(tally[1:].sum(0) > 0, major, 0)
        bone_c = Jm[F[ti, 0], 0]
        skin_b = [bm.bi[b] for b in ("wrist.L", "wrist.R", "neck01") if b in bm.bi]
        args = (Xr, lay_c, lab_c, bone_c, head_t, skin_b, skin_b[:2])
        mix, _, stats["clean"] = CC.clean(mix, seen_t, *args, log=log)
        if light is not None and light.get("applied"):
            alb, _, _ = CC.clean(alb, seen_t, *args, log=lambda *a: None)
        known = inside

    def fill(colours):
        # unseen texels and the gutters are filled together, from known texels only (filling the holes first let
        # the black gutters bleed into them along the island edges)
        tex = np.zeros((res, res, 3), np.float32); tex[inside] = colours
        t8 = np.clip(tex, 0, 255).astype(np.uint8)
        unknown = (~known).astype(np.uint8)
        return cv2.inpaint(t8, unknown, 6, cv2.INPAINT_TELEA) if unknown.any() else t8
    t8 = fill(mix)
    if light is not None and light.get("applied"):
        stats["light"] = light
        stats["lit_texture"] = t8                                       # as filmed (the room's light in it)
        t8 = fill(alb)
    log("texture: %d frames, %.0f%% of the body seen, %dx%d" % (len(used), 100 * stats["seen"], res, res))
    return t8, cov, stats


def _label_class(l):
    """MediaPipe multiclass -> 1 hair, 2 skin (body or face), 3 clothes, 0 other"""
    out = np.zeros(l.shape, np.int8)
    out[l == 1] = 1; out[(l == 2) | (l == 3)] = 2; out[l == 4] = 3
    return out


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
