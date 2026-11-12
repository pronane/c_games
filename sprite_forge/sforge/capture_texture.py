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

def head_sides(col, X, side, face, log=print, ratio=1.25, force=None):
    """-> (colours, info). How cleanly each side of the head (x > 0 / x < 0) joins the face: the colour step
    between face texels and the side texels next to them (within 1.5 cm). The worse side, when worse by `ratio`,
    is replaced by the mirror image of the better one."""
    from scipy.spatial import cKDTree
    from .capture_clean import _lab
    L = _lab(col)
    fi = np.nonzero(face)[0]
    step = {}
    for sgn, nm in ((1, "left"), (-1, "right")):
        si = np.nonzero(side & (np.sign(X[:, 0]) == sgn))[0]
        if len(si) < 100:
            return col, {}
        d, j = cKDTree(X[fi]).query(X[si], k=1)
        near = d < 0.015
        if near.sum() < 30:
            return col, {}
        step[nm] = float(np.median(np.linalg.norm(L[si[near]] - L[fi[j[near]]], axis=1)))
    worse = force or max(step, key=step.get)
    better = "right" if worse == "left" else "left"
    info = dict(step=step)
    if force or step[worse] > ratio * step[better]:
        sb = 1 if better == "left" else -1
        src = np.nonzero(side & (np.sign(X[:, 0]) == sb))[0]
        dst = np.nonzero(side & (np.sign(X[:, 0]) == -sb))[0]
        d, j = cKDTree(X[src]).query(X[dst] * [-1, 1, 1], k=3)
        w = 1.0 / (d + 1e-3)
        col = col.copy()
        col[dst] = (col[src][j] * w[..., None]).sum(1) / w.sum(1)[:, None]
        info["mirrored"] = worse
        log("texture: the head's %s side joined the face badly (colour step %.0f vs %.0f): mirrored from the %s" % (
            worse, step[worse], step[better], better))
    return col, info


def face_balance(col, X, face, log=print, strength=0.5, radius=0.02):
    """the face from one frame keeps that frame's light: one cheek bright, the other dark. The smooth part of the
    left / right lightness difference (each texel against its mirror image, averaged over 2 cm) is taken out half
    each side; eyes, brows and the beard - fine detail - are left as they are"""
    from scipy.spatial import cKDTree
    from .capture_clean import _lab, _rgb
    fi = np.nonzero(face)[0]
    if len(fi) < 500:
        return col, {}
    L = _lab(col[fi])
    tr = cKDTree(X[fi])
    d, j = tr.query(X[fi] * [-1, 1, 1], k=1)
    ok = d < 0.006
    diff = np.where(ok, L[:, 0] - L[j, 0], 0.0)
    # smooth over 2 cm
    nb = tr.query_ball_point(X[fi], r=radius)
    sm = np.array([diff[n].mean() if len(n) else 0.0 for n in nb])
    L2 = L.copy()
    L2[:, 0] = L[:, 0] - strength * sm
    col = col.copy()
    col[fi] = _rgb(L2)
    info = dict(mean_abs_lr_step=float(np.abs(sm).mean()))
    log("texture: face light evened left / right (mean step %.1f L)" % info["mean_abs_lr_step"])
    return col, info


RINGS = os.environ.get("SF_RINGS", "1") != "0"
HEAD_MIN_FACING = float(os.environ.get("SF_HEAD_FACING", "0.4"))


ALIGN = os.environ.get("SF_ALIGN", "1") != "0"
SURE_SD = float(os.environ.get("SF_SURE_SD", "25"))
SHARP_SIGMA = float(os.environ.get("SF_SHARP_SIGMA", "10"))


def align_flows(fitter, frames, tex, mesh=None, log=print, max_frac=0.03):
    """v11.9: per frame, where the character really is in the picture, to the pixel.

    The cameras and the body put each texel within a centimetre or two of where the frame shows it - enough for the
    silhouette, not for a 1 cm stripe or a logo: averaged over frames that each miss by a different centimetre,
    thin detail goes grey. Here the first texture is drawn into each frame from its camera and the frame is matched
    to that drawing by optical flow (DIS, on locally normalised grey so exposure does not matter): the flow says how
    far each drawn pixel has to move to land on the real one. It is smoothed, capped at `max_frac` of the frame
    height and kept only where both the drawing and the person are. -> {frame index: (fx, fy) float32 HxW}"""
    import cv2
    from scipy import ndimage as ndi
    sh, P, Pg = fitter.posed()
    Fm, fuvm = fitter.bm.F, fitter.bm.fuv
    if mesh is not None:
        P = mesh[0].pose(mesh[1]); Fm, fuvm = mesh[0].F, mesh[0].fuv
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

    def norm(g, m):
        g = g.astype(np.float32)
        mu = cv2.GaussianBlur(g, (0, 0), 6); sd = np.sqrt(np.maximum(cv2.GaussianBlur(g * g, (0, 0), 6) - mu * mu, 1.0))
        z = np.clip((g - mu) / sd, -3, 3)
        return np.where(m, z * 40 + 128, 128).astype(np.uint8)
    flows = {}; mags = []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        msk = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % r["i"]))) > 127
        H, W = img.shape[:2]
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv)
        ren, m = render(P, Fm, fuvm, tex, size=(W, H), cam=(R, tv, fitter.cams.K(r["size"])))
        both = ndi.binary_dilation(m & msk, iterations=8)
        a = norm(cv2.cvtColor(ren, cv2.COLOR_RGB2GRAY), both)
        b = norm(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), both)
        fl = dis.calc(a, b, None)                                      # ren(x) ~ img(x + fl(x))
        cap = max_frac * H
        for k in range(2):
            f_ = fl[..., k]
            f_ = np.where(m & msk, f_, 0.0)
            # smooth inside the drawing only (normalised convolution), so the zeros outside do not pull it in
            wsm = cv2.GaussianBlur((m & msk).astype(np.float32), (0, 0), 4)
            f_ = cv2.GaussianBlur(f_.astype(np.float32), (0, 0), 4) / np.maximum(wsm, 1e-3)
            # near the outline (feet on the floor, a hand against the trousers) the flow matches the wrong thing:
            # it fades to nothing over the outer 15 px of the person
            fade = np.clip(ndi.distance_transform_edt(m & msk) / 15.0, 0, 1)
            fl[..., k] = np.clip(f_, -cap, cap) * fade
        flows[r["i"]] = (fl[..., 0].astype(np.float32), fl[..., 1].astype(np.float32))
        sel = m & msk
        if sel.any():
            mags.append(float(np.median(np.hypot(fl[..., 0][sel], fl[..., 1][sel]))))
    if mags:
        log("texture: frames aligned to the first texture by optical flow, median shift %.1f px (%.1f-%.1f)" % (
            float(np.median(mags)), min(mags), max(mags)))
    return flows


def bake(fitter, frames=None, res=1024, power=4.0, min_facing=0.15, log=print, mesh=None, delight=False, clean=True,
         flows=None, align=None):
    """-> (texture RGB uint8 (res,res,3), coverage (res,res) float, stats)
    mesh: optional (rest Mesh, skinning matrices) from capture_layers - body + clothes + skirt + hair in one atlas;
    default the bare body with MakeHuman's UVs.
    align (default on, SF_ALIGN=0 off): v11.9 - a first, plain texture is baked, every frame is matched to it by
    optical flow (align_flows) and the texture is baked again from the corrected positions"""
    if align is None:
        align = ALIGN
    if align and flows is None:
        fr = frames or [t.r for t in fitter.targets]
        t0, _, _ = bake(fitter, frames=fr, res=res, power=power, min_facing=min_facing, log=lambda *a: None,
                        mesh=mesh, delight=False, clean=False, align=False)
        flows = align_flows(fitter, fr, t0, mesh=mesh, log=log)
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
    # v11.9: hands and feet are thin and sit on the person's outline (against the floor, the trousers): optical flow
    # matches the wrong thing there, so they keep the camera's own projection
    ext_b = [bm.bi[b] for b in bm.bi if b.split(".")[0] in ("foot", "toe1-1", "toe2-1", "toe3-1", "toe4-1", "toe5-1",
                                                               "wrist") or b.startswith(("finger", "metacarpal", "toe"))]
    ext_t = np.isin(Jm[F[ti, 0], 0], ext_b)
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
            # v11.7: "other" inside the person's own mask is something worn - socks, shoes, a watch. Before, it was
            # thrown away with the TV and the chair, so white socks were never sampled and the shins came out skin
            person |= (lab == 5) & (m > 0.5)
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
        c0 = getattr(fitter.cams, "cam0", None) or {}
        if r["i"] in c0 and ext_t.any():
            # v11.10: hands and feet are drawn through the landmark fit's camera, not the registered one
            # (capture_register keeps it: it was placed by the ankle, toe and wrist keypoints)
            R0, _ = cv2.Rodrigues(np.asarray(c0[r["i"]][0], float)); t0 = np.asarray(c0[r["i"]][1], float)
            P0 = P @ R0.T + t0
            x0 = P0[:, 0] / P0[:, 2] * K[0, 0] + K[0, 2]; y0 = P0[:, 1] / P0[:, 2] * K[1, 1] + K[1, 2]
            _, _, z0 = rasterise(x0, y0, -P0[:, 2], F, W, H, K=6)
            z0 = z0.reshape(H, W)
            Xe = X[ext_t] @ R0.T + t0
            ue = Xe[:, 0] / Xe[:, 2] * K[0, 0] + K[0, 2]; ve = Xe[:, 1] / Xe[:, 2] * K[1, 1] + K[1, 2]
            uie = np.clip(np.round(ue - 0.5).astype(int), 0, W - 1); vie = np.clip(np.round(ve - 0.5).astype(int), 0, H - 1)
            ine = (ue >= 0) & (ue < W) & (ve >= 0) & (ve < H)
            u[ext_t], v[ext_t], ui[ext_t], vi[ext_t] = ue, ve, uie, vie
            vis[ext_t] = ine & (np.abs(-Xe[:, 2] - z0[vie, uie]) < 0.025)
            ve_ = -(Xe / np.linalg.norm(Xe, axis=1, keepdims=True))
            facing[ext_t] = np.clip(((Nt[ext_t] @ R0.T) * ve_).sum(1), 0, 1)
        # grazing views stretch; mask edge = background. v11.7: the head needs a squarer view - a frontal frame
        # seen at a slant paints its eye onto the side of the head (a ghost eye by the ear)
        ok = vis & (facing > np.where(hd_t, HEAD_MIN_FACING, min_facing)) & (m[vi, ui] > 0.6)
        pw = np.where(head_t, power * 2.0, power)                         # a face blurs when views are mixed
        if flows and r["i"] in flows:
            # v11.9: sample where the frame really shows the texel (the head has its own pose already)
            fx, fy = flows[r["i"]]
            bd = (~hd_t if r["i"] in poses else np.ones(len(u), bool)) & ~ext_t
            du = fx[vi, ui]; dv = fy[vi, ui]
            u = np.where(bd, u + du, u); v = np.where(bd, v + dv, v)
            ui = np.clip(np.round(u - 0.5).astype(int), 0, W - 1); vi = np.clip(np.round(v - 0.5).astype(int), 0, H - 1)
            ok &= (u >= 0) & (u < W) & (v >= 0) & (v < H) & (m[vi, ui] > 0.6)
        c = _bilinear(img, u - 0.5, v - 0.5)
        w = np.where(ok, facing ** pw * m[vi, ui] * (ppm / 400.0) ** 2, 0.0) * (_sharpness(img) ** 0.5)
        cols.append(np.clip(np.round(c), 0, 255).astype(np.uint8)); ws.append(w.astype(np.float32)); used.append(r["i"])
        labs.append(_label_class(lab[vi, ui]) if lab is not None else np.zeros(len(u), np.int8))
    C = np.stack(cols); Wt = np.stack(ws)                                  # (frames, texels, 3), (frames, texels)
    # label vote per texel: hair / skin / clothes. A sample whose label disagrees with the texel's majority is a
    # misplacement (a hand hanging over the jeans, a sleeve over the waist) and is dropped
    Lb = np.stack(labs)
    tally = np.stack([(Wt * (Lb == c)).sum(0) for c in range(5)])
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
    # v11.7: the face is painted mostly from its best frame, but where that frame sees a cheek at a slant other
    # frames fill in - with their own exposure and light, a dark patch with a sharp edge. Each frame gets a face
    # gain matching it to the best frame on the face texels both see
    fgain = np.ones((len(C), 3), np.float32)
    if face_t.any():
        fi_ = np.nonzero(face_t)[0]
        best = int(np.argmax(Wt[:, fi_].sum(1)))
        for k in range(len(C)):
            if k == best:
                continue
            com = fi_[(Wt[best, fi_] > 0) & (Wt[k, fi_] > 0)]
            if len(com) > 200:
                a_ = np.median(C[best][com].astype(np.float32) * gains[best], 0)
                b_ = np.median(C[k][com].astype(np.float32) * gains[k], 0)
                fgain[k] = np.clip(a_ / np.maximum(b_, 1.0), 0.6, 1.6)
        stats_fg = float(np.abs(np.log(fgain)).mean())
    out = []; sd_out = []; ne_out = []
    for c in chunks:
        Cg = C[:, c].astype(np.float32) * gains[:, None, :]; Wc = Wt[:, c]
        fc = face_t[c]
        if fc.any():
            Cg[:, fc] *= fgain[:, None, :]
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
        # v11.9: how well the views agree - their weighted spread round the mean, and how many views really count
        sw = Wc.sum(0)
        var = (Wc[..., None] * (Cg - mean[None]) ** 2).sum(0) / (sw[:, None] + 1e-9)
        neff = sw ** 2 / ((Wc ** 2).sum(0) + 1e-12)
        sd_out.append(np.sqrt(var.mean(1))); ne_out.append(neff)
    mix = np.concatenate(out)
    view_sd = np.concatenate(sd_out); view_n = np.concatenate(ne_out)
    cover = Wt.sum(0)
    seen_t = cover > 1e-6 * (cover.max() + 1e-9)
    light = None
    if delight:
        # v11.2: the room's light divided out (capture_light); the lit texture is kept for the held-out check
        from . import capture_light as CLI
        lay_t = (M.layer[F[ti, 0]] if mesh is not None else np.zeros(len(ti), int))
        groups = lay_t * 5 + np.where(tally[1:].sum(0) > 0, major, 0)
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
        # the neck is skin to clean like any other (only the head itself - the face - is protected)
        prot_c = head_t & (bone_c != bm.bi.get("neck01", -1))
        args = (Xr, lay_c, lab_c, bone_c, prot_c, skin_b, skin_b[:2])
        # v11.7: garment edges on the limbs are rings (capture_rings)
        from . import capture_rings as CR
        limb_c, s_c = CR.limb_coords(sh.head, Xr, bone_c, bm.bi)
        torso_b = [bm.bi[b] for b in ("root", "spine05", "spine04", "spine03", "spine02", "spine01", "clavicle.L",
                                      "clavicle.R") if b in bm.bi]
        kw = dict(limb=limb_c, s=s_c, torso_bones=torso_b) if RINGS else {}
        kw["foot_bones"] = [bm.bi[b] for b in bm.bi if b.startswith(("foot.", "toe"))]
        # the underside of the jaw and the neck are skin or beard: a collar seen past the chin paints them the
        # shirt's colour. Body texels there whose colour is near a garment's and far from the skin are dropped
        neck_b = [bm.bi[b] for b in ("head", "neck01") if b in bm.bi]
        cand = (lay_c == 0) & np.isin(bone_c, neck_b) & ((Nr[:, 1] < -0.2) | (bone_c == bm.bi.get("neck01", -1))) \
            & (lab_c != 1)                                                 # not hair / beard
        if cand.any() and (lay_c == 1).any():
            from .capture_clean import _lab, W_LAB
            L_ = _lab(mix)
            sk = seen_t & (lay_c == 0) & (lab_c == 2) & ~head_t
            g_ = seen_t & (lay_c == 1)
            if sk.sum() > 200 and g_.sum() > 200:
                from .capture_clean import _kmeans
                skm = np.median(L_[sk], 0)
                _, gc = _kmeans(L_[g_] * W_LAB, 3)                 # the garments' colours
                dsk = np.linalg.norm((L_ - skm) * W_LAB, axis=1)
                dg = np.min(np.linalg.norm((L_ * W_LAB)[:, None, :] - gc[None], axis=2), 1)
                kw["drop"] = cand & (dg < dsk) & (dg < 30)
                stats["chin_dropped"] = int(kw["drop"].sum())
        mix_raw = mix.copy(); alb_raw = alb.copy() if (light is not None and light.get("applied")) else None
        mix, _, stats["clean"] = CC.clean(mix, seen_t, *args, log=log, **kw)
        if light is not None and light.get("applied"):
            alb, _, _ = CC.clean(alb, seen_t, *args, log=lambda *a: None, **kw)
        known = inside
        # v11.7: the sides of the head. The face comes from one frontal frame; each side of the head from the
        # frames that see it. When one side's frames had a worse head pose, that side shows the ear and hairline
        # too far forward - a seam and a second profile next to the face. The side that joins the face cleanly is
        # mirrored onto the other
        mix, stats["face_balance"] = face_balance(mix, Xr, face_t & (lay_c == 0), log=log)
        if light is not None and light.get("applied"):
            alb, _ = face_balance(alb, Xr, face_t & (lay_c == 0), log=lambda *a: None)
        side_t = hd_t & (lay_c == 0) & ~face_t
        if os.environ.get("SF_DEBUG_MASKS"):
            dbg = np.zeros((res, res, 3), np.uint8); cc = np.zeros((len(ti), 3), np.uint8)
            cc[face_t] = (255, 0, 0); cc[side_t & (Xr[:, 0] > 0)] = (0, 255, 0); cc[side_t & (Xr[:, 0] < 0)] = (0, 0, 255)
            cc[head_t & ~hd_t] = (255, 255, 0)
            if os.environ.get("SF_DEBUG_MASKS") == "limbs":
                cc[:] = 128
                for lb_, ch_ in ((2, 0), (3, 1), (0, 2), (1, 2)):
                    sel_ = limb_c == lb_
                    cc[sel_] = 0
                    cc[sel_, ch_] = np.clip(60 + 200 * s_c[sel_] / 1.0, 0, 255).astype(np.uint8)
                sel_ = (limb_c >= 0) & (np.abs(s_c - 0.75) < 0.01)
                cc[sel_] = (255, 255, 255)
            dbg[inside] = cc
            stats["debug_masks"] = dbg
        if side_t.sum() > 500 and face_t.sum() > 500:
            mix, hinfo = head_sides(mix, Xr, side_t, face_t, log=log)
            stats["head_sides"] = hinfo
            if light is not None and light.get("applied") and hinfo.get("mirrored"):
                alb, _ = head_sides(alb, Xr, side_t, face_t, log=lambda *a: None, force=hinfo["mirrored"])

    def fill(colours):
        # unseen texels and the gutters are filled together, from known texels only (filling the holes first let
        # the black gutters bleed into them along the island edges)
        tex = np.zeros((res, res, 3), np.float32); tex[inside] = colours
        t8 = np.clip(tex, 0, 255).astype(np.uint8)
        unknown = (~known).astype(np.uint8)
        return cv2.inpaint(t8, unknown, 6, cv2.INPAINT_TELEA) if unknown.any() else t8
    detail = None
    if clean and flows and mesh is not None:
        # v11.9: the clean decides each garment's colours and edges; the fine detail - a print's lettering, a
        # stripe, a seam - is put back on top of it from the aligned bake, but only on the clothes and only where
        # at least two views agree on it (blotches are views that disagree; detail is what every view sees).
        # Detail = the raw texture minus its own blur (SHARP_SIGMA texels), so a colour cast or a big patch is not
        sure_t = seen_t & (view_n >= 1.8) & (view_sd < SURE_SD) & (lay_c >= 1)
        sm = np.zeros((res, res), np.float32); sm[inside] = sure_t
        sm = cv2.GaussianBlur(sm, (0, 0), 1.5)                          # soft edge of the detail mask
        # where the clean may have moved a garment edge: the limbs and the hips (rings, hems); a print on the chest
        # is never an edge the clean moved, however different its raw colours are from the clean's blocks
        moved = np.zeros((res, res), np.float32)
        if "limb" in kw and kw["limb"] is not None:
            moved[inside] = (kw["limb"] >= 0)
        moved = cv2.dilate(moved, np.ones((9, 9), np.uint8))

        def detail_of(raw):
            img_ = fill(raw).astype(np.float32)
            return img_ - cv2.GaussianBlur(img_, (0, 0), SHARP_SIGMA)

        def sharpen(clean_img, raw):
            # where the views agree: the clean texture's own blur (its colours, without the blocks the clean leaves
            # round small features) plus the raw detail; elsewhere the clean texture as it is
            c_ = clean_img.astype(np.float32)
            base = cv2.GaussianBlur(c_, (0, 0), SHARP_SIGMA)
            sh_ = base + detail_of(raw)
            # not where the clean moved a garment edge (a hem snapped to its ring): there the raw detail is the old
            # edge, and adding it back would smear the shirt into the shorts
            far = np.linalg.norm(fill(raw).astype(np.float32) - c_, axis=2)
            # the clean's own garment edges on the limbs (hems): a strong step in the clean texture, widened by the
            # blur's reach. A stripe down a leg is not one - the clean has no stripe - so it gets its detail back
            step = np.linalg.norm(c_ - cv2.GaussianBlur(c_, (0, 0), 3), axis=2) > 20
            hem = cv2.dilate((step & (moved > 0)).astype(np.uint8), np.ones((int(2 * SHARP_SIGMA) | 1,) * 2, np.uint8))
            w_ = sm * (1.0 - hem * (1.0 - np.clip((60.0 - far) / 30.0, 0, 1)))
            w_ = np.minimum(w_, cv2.erode(w_, np.ones((5, 5), np.uint8)) + 0.0)
            w_ = cv2.GaussianBlur(w_, (0, 0), 1.5)
            return np.clip(c_ + w_[..., None] * (sh_ - c_), 0, 255).astype(np.uint8)
        detail = True
        stats["sure"] = float(sure_t.sum() / max(1, (seen_t & (lay_c >= 1)).sum()))
        log("texture: detail put back on %.0f%% of the clothes (views agree within %g)" % (100 * stats["sure"], SURE_SD))
    t8 = fill(mix)
    if detail is not None:
        t8 = sharpen(t8, mix_raw)
    if light is not None and light.get("applied"):
        stats["light"] = light
        stats["lit_texture"] = t8                                       # as filmed (the room's light in it)
        t8 = fill(alb)
        if detail is not None:
            t8 = sharpen(t8, alb_raw)
    log("texture: %d frames, %.0f%% of the body seen, %dx%d" % (len(used), 100 * stats["seen"], res, res))
    return t8, cov, stats


def _label_class(l):
    """MediaPipe multiclass -> 1 hair, 2 skin (body or face), 3 clothes, 4 worn (socks, shoes, accessories), 0 none"""
    out = np.zeros(l.shape, np.int8)
    out[l == 1] = 1; out[(l == 2) | (l == 3)] = 2; out[l == 4] = 3; out[l == 5] = 4
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
