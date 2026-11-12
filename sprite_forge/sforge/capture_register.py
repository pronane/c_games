"""forge.py capture - register every frame's camera to the picture itself (v11.10).

The cameras come from 33 body landmarks and the silhouette: right for the outline, but each frame still sits a
centimetre or two off what the picture shows (5-10 px at 1080p), different in every frame. That is what blurs a
texture averaged over frames, and what makes a held-out frame disagree with the render.

Here a frame's camera is moved to where the picture says it is:
  1 the character (a first, plain texture) is drawn from the frame's camera
  2 DIS optical flow from the drawing to the frame says, for every drawn pixel, where it really is; it is kept
    where it is trustworthy: inside the person (not the outline), and where the flow back agrees with the flow
    there (forward / backward check)
  3 the visible vertices under those pixels are 3D points with known 2D targets: the camera (yaw, pitch, roll,
    position) is re-solved to them (robust least squares, kept near where it was)
  4 the new camera is KEPT only if it really is better and still sane - the safeguards that make this safe for any
    video, not just the ones it was tuned on:
       - the median flow left after the move is at least 10% smaller
       - the silhouette agrees at least as well (IoU drop under 0.005)
       - the move is a correction, not a jump: under 8 degrees and 12% of the camera's distance per round
       - enough points: at least 150 trusted vertices spread over at least 25% of the person's height
    otherwise the frame keeps its old camera and the report says why.
Three rounds by default; each starts from the last one's result. On real footage the person also moves a little
between frames (arms, sway), which no camera can absorb: what is left after this is handled per texel by the
texture's own flow alignment (capture_texture.align_flows).

    register(fitter, frames, tex, mesh=None, log) -> report {frame: {...}}, summary
"""
from __future__ import annotations
import os

import numpy as np

MAX_ROT_DEG = 8.0
MAX_T_FRAC = 0.12
MIN_POINTS = 150
MIN_SPAN = 0.25
MIN_GAIN = 0.10
MAX_IOU_DROP = 0.005
ROT_PRIOR = float(os.environ.get("SF_REG_ROT", "1.0"))          # degrees: how far the angles may drift cheaply


def _norm(g, m):
    import cv2
    g = g.astype(np.float32)
    mu = cv2.GaussianBlur(g, (0, 0), 6)
    sd = np.sqrt(np.maximum(cv2.GaussianBlur(g * g, (0, 0), 6) - mu * mu, 1.0))
    z = np.clip((g - mu) / sd, -3, 3)
    return np.where(m, z * 40 + 128, 128).astype(np.uint8)


def flow_pair(ren, rmask, img, pmask):
    """DIS flow from the drawing to the frame on locally normalised grey (exposure does not matter), plus a
    trust mask: inside both masks, away from the outline, forward / backward consistent. -> (flow HxWx2, trust)"""
    import cv2
    from scipy import ndimage as ndi
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    both = rmask & pmask
    reach = ndi.binary_dilation(both, iterations=8)
    a = _norm(cv2.cvtColor(ren, cv2.COLOR_RGB2GRAY), reach)
    b = _norm(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), reach)
    fw = dis.calc(a, b, None)
    bw = dis.calc(b, a, None)
    H, W = a.shape
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    bx = cv2.remap(bw[..., 0], gx + fw[..., 0], gy + fw[..., 1], cv2.INTER_LINEAR)
    by = cv2.remap(bw[..., 1], gx + fw[..., 0], gy + fw[..., 1], cv2.INTER_LINEAR)
    fb = np.hypot(fw[..., 0] + bx, fw[..., 1] + by)
    inner = ndi.distance_transform_edt(both) > 12
    # flat areas carry no information: some texture under the pixel
    gm = cv2.GaussianBlur(np.abs(cv2.Laplacian(a.astype(np.float32), cv2.CV_32F)), (0, 0), 2)
    trust = inner & (fb < 1.5) & (gm > 4.0)
    return fw, trust


def _project(par, X, K):
    from .capture_fit import Cameras
    R = Cameras.rot(*par[:3])
    Pc = X @ R.T + par[3:6]
    return Pc[:, :2] / np.maximum(Pc[:, 2:3], 1e-3) * K[0, 0] + K[:2, 2], Pc[:, 2]


def _visible(P, F, par, K, W, H):
    """vertices the camera sees (z-buffer test) -> (indices, their pixels)"""
    from .render_sculpt import rasterise
    uv, z = _project(par, P, K)
    _, _, zbuf = rasterise(uv[:, 0], uv[:, 1], -z, F, W, H, K=6)
    zbuf = zbuf.reshape(H, W)
    ui = np.round(uv[:, 0] - 0.5).astype(int); vi = np.round(uv[:, 1] - 0.5).astype(int)
    inb = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H) & (z > 0.1)
    vis = np.zeros(len(P), bool)
    vis[inb] = np.abs(-z[inb] - zbuf[vi[inb], ui[inb]]) < 0.02
    return np.nonzero(vis)[0], uv


def _iou(a, b):
    return float((a & b).sum()) / max(1, (a | b).sum())


def register_frame(P, F, fuv, tex, img, pmask, par, K, rng=None):
    """one frame -> (new camera parameters, info). The camera comes back unchanged when a safeguard fails."""
    from scipy.optimize import least_squares
    from .capture_fit import Cameras
    from .capture_texture import render
    import cv2
    H, W = pmask.shape
    par = np.asarray(par, float)
    rng = rng or np.random.default_rng(0)

    def draw(p):
        R = Cameras.rot(*p[:3])
        return render(P, F, fuv, tex, size=(W, H), cam=(R, p[3:6], K))
    ren, rm = draw(par)
    info = dict(kept=False)
    if rm.sum() < 500 or pmask.sum() < 500:
        info["why"] = "person too small in the frame"
        return par, info
    fw, trust = flow_pair(ren, rm, img, pmask)
    idx, uv = _visible(P, F, par, K, W, H)
    ui = np.clip(np.round(uv[idx, 0] - 0.5).astype(int), 0, W - 1); vi = np.clip(np.round(uv[idx, 1] - 0.5).astype(int), 0, H - 1)
    ok = trust[vi, ui]
    idx, ui, vi = idx[ok], ui[ok], vi[ok]
    info["points"] = int(len(idx))
    span = (uv[idx, 1].max() - uv[idx, 1].min()) / max(1.0, np.ptp(np.nonzero(pmask)[0])) if len(idx) else 0.0
    info["span"] = round(float(span), 3)
    if len(idx) < MIN_POINTS or span < MIN_SPAN:
        info["why"] = "too few trusted points (%d, span %.0f%% of the person)" % (len(idx), 100 * span)
        return par, info
    if len(idx) > 4000:
        pick = rng.choice(len(idx), 4000, replace=False); idx, ui, vi = idx[pick], ui[pick], vi[pick]
    X = P[idx]
    tgt = uv[idx] + fw[vi, ui]
    before = float(np.median(np.hypot(*(fw[vi, ui].T))))
    info["flow_before_px"] = round(before, 2)
    dist = float(par[5])

    # mostly the picture is shifted, not turned: the position is solved first, then all six with the angles held
    # close (ROT_PRIOR degrees) - a small turn and a small shift look alike, and the shift is the likelier one
    def res_t(q):
        p = np.r_[par[:3], q]
        u, _ = _project(p, X, K)
        return np.r_[(u - tgt).ravel(), (q - par[3:6]) / (0.03 * dist)]
    q = least_squares(res_t, par[3:6], loss="soft_l1", f_scale=2.0, max_nfev=60).x

    def res(p):
        u, _ = _project(p, X, K)
        reg = np.r_[(p[:3] - par[:3]) / ROT_PRIOR, (p[3:6] - par[3:6]) / (0.03 * dist)]
        return np.r_[(u - tgt).ravel(), reg * np.sqrt(len(X) / 50.0)]
    sol = least_squares(res, np.r_[par[:3], q], loss="soft_l1", f_scale=2.0, max_nfev=80)
    new = sol.x
    d_rot = float(np.abs(new[:3] - par[:3]).max()); d_t = float(np.linalg.norm(new[3:6] - par[3:6]) / dist)
    info.update(d_rot_deg=round(d_rot, 2), d_t_frac=round(d_t, 4))
    if d_rot > MAX_ROT_DEG or d_t > MAX_T_FRAC:
        info["why"] = "the move is too large to be a correction (%.1f deg, %.1f%% of the distance)" % (d_rot, 100 * d_t)
        return par, info
    # judge the new camera the same way: draw, flow, median of what is left
    ren2, rm2 = draw(new)
    fw2, trust2 = flow_pair(ren2, rm2, img, pmask)
    idx2, uv2 = _visible(P, F, new, K, W, H)
    u2 = np.clip(np.round(uv2[idx2, 0] - 0.5).astype(int), 0, W - 1); v2 = np.clip(np.round(uv2[idx2, 1] - 0.5).astype(int), 0, H - 1)
    t2 = trust2[v2, u2]
    after = float(np.median(np.hypot(*(fw2[v2[t2], u2[t2]].T)))) if t2.sum() > MIN_POINTS // 2 else before
    iou0, iou1 = _iou(rm, pmask), _iou(rm2, pmask)
    info.update(flow_after_px=round(after, 2), iou_before=round(iou0, 4), iou_after=round(iou1, 4))
    if after > (1 - MIN_GAIN) * before:
        info["why"] = "not better: %.1f -> %.1f px" % (before, after)
        return par, info
    if iou1 < iou0 - MAX_IOU_DROP:
        info["why"] = "the outline got worse (IoU %.3f -> %.3f)" % (iou0, iou1)
        return par, info
    info["kept"] = True
    return new, info


def register(fitter, frames, tex, mesh=None, log=print, rounds=3):
    """re-solve every frame's camera to its picture (see the module doc). Changes fitter.cams in place.
    -> (per-frame report, summary dict)"""
    import cv2
    from PIL import Image
    if mesh is not None:
        P = mesh[0].pose(mesh[1]); F, fuv = mesh[0].F, mesh[0].fuv
    else:
        _, P, _ = fitter.posed(); F, fuv = fitter.bm.F, fitter.bm.fuv
    rep = {}
    for rnd in range(rounds):
        for r in frames:
            i = r["i"]
            if i not in fitter.cams.par:
                continue
            img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % i)).convert("RGB"))
            pm = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % i))) > 127
            K = fitter.cams.K(r["size"])
            new, info = register_frame(P, F, fuv, tex, img, pm, fitter.cams.par[i], K)
            if info.get("kept"):
                # the landmark fit's camera is kept for the hands and feet (capture_texture draws them through it): it
                # was placed by the ankle, heel, toe and wrist keypoints, this one lines up the bulk of the body, and
                # hands and feet move on their own. With the registered camera PR's navy socks and Mike's white ones
                # were partly painted from the floor and the skin
                c0 = getattr(fitter.cams, "cam0", None)
                if c0 is None:
                    c0 = fitter.cams.cam0 = {}
                c0.setdefault(i, fitter.cams.cam[i])
                rv, _ = cv2.Rodrigues(fitter.cams.rot(*new[:3]))
                fitter.cams.par[i] = new
                fitter.cams.cam[i] = (rv.reshape(3), new[3:6].copy())
            st = rep.setdefault(i, dict(moved=False, rounds=[]))
            st["rounds"].append(info)
            if "flow_before_px" in info:
                st.setdefault("start_px", info["flow_before_px"])
                st["end_px"] = info["flow_after_px"] if info.get("kept") else info["flow_before_px"]
            if info.get("kept"):
                st["moved"] = True
                st["d_rot_deg"] = round(st.get("d_rot_deg", 0.0) + info["d_rot_deg"], 2)
                st["d_t_frac"] = round(st.get("d_t_frac", 0.0) + info["d_t_frac"], 4)
    starts = [v["start_px"] for v in rep.values() if "start_px" in v]
    ends = [v["end_px"] for v in rep.values() if "end_px" in v]
    summ = dict(frames=len(rep), moved=sum(1 for v in rep.values() if v["moved"]),
                flow_px_before=round(float(np.median(starts)), 2) if starts else None,
                flow_px_after=round(float(np.median(ends)), 2) if ends else None,
                refused={int(k): v["rounds"][-1].get("why", "") for k, v in rep.items() if not v["moved"]})
    log("cameras registered to the pictures: median misfit %s -> %s px; %d of %d frames moved%s" % (
        summ["flow_px_before"], summ["flow_px_after"], summ["moved"], summ["frames"],
        (", %d kept their camera" % len(summ["refused"])) if summ["refused"] else ""))
    return rep, summ
