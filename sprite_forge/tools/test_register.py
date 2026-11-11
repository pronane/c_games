#!/usr/bin/env python3
"""Camera registration to the picture (v11.10): does it fix any video's cameras, and never break a good one?

    python tools/test_register.py

Synthetic and exact: a MakeHuman body with a textured surface is filmed by 8 known cameras round it. The cameras
handed to the registration are the true ones knocked off by 0.5-2 degrees and 0.5-2 cm - what the landmark fit
leaves on a real video. The texture it draws with is the true one blurred (a first bake is soft). Checks, each one
a property any new video relies on:
  1 knocked-off cameras come back: the vertices' reprojection error against the truth falls by at least half
    (median over frames) and no frame gets worse
  2 a camera that is already right stays right (moves under 0.3 px, or is left alone)
  3 a frame that is not the person (noise where the picture should be) keeps its camera
  4 a frame with half the person hidden (someone walks in front) never ends up worse than it started
  5 a camera far off (15 degrees: a tracking failure, not a misfit) is not "corrected" - it is left alone
  6 a frame where the person is tiny is left alone
  7 kinds of video the five samples do not have - a close-up with the legs cut off, a dim noisy room, motion blur,
    heavy JPEG, a ragged segmentation mask, plain one-colour clothes: never worse, and better wherever the
    picture has detail to align to (at least 30% of the way back)
Skips (exit 0) without the MakeHuman assets."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    from sforge import human as HU
    if not HU.have_assets():
        print("SKIP: MakeHuman assets missing"); return 0
    import cv2
    from sforge import capture_body as CB, capture_fit as CF, capture_register as CR, capture_texture as CT
    bm = CB.BodyModel()
    sh = bm.shape(dict(gender=1.0, weight=0.6), {}, 1.78)
    dirs = {"upperarm01.L": [0.25, -0.97, 0.0], "upperarm01.R": [-0.25, -0.97, 0.0]}
    P, _, _ = sh.pose(dirs)
    F, fuv = bm.F, bm.fuv
    # a surface with things to see: bands, a checker, stripes, a "logo"
    N = 1024
    yy, xx = np.mgrid[0:N, 0:N] / N
    tex = np.stack([110 + 90 * np.sin(9 * xx), 100 + 80 * np.cos(7 * yy), 130 + 70 * np.sin(5 * (xx + yy))], -1)
    tex[((np.floor(xx * 48) + np.floor(yy * 48)) % 2) == 0] *= 0.75
    tex[(np.floor(xx * 160) % 9) == 0] = 235
    tex = np.clip(tex, 0, 255).astype(np.uint8)
    soft = cv2.GaussianBlur(tex, (0, 0), 2.0)
    W, H = 600, 800
    cams = CF.Cameras(0.8)
    K = cams.K((W, H))
    rng = np.random.default_rng(7)
    truth = []
    for k in range(8):
        yaw = k * 45.0
        par = np.array([yaw, 6.0, 0.0, 0.0, 0.0, 3.0])
        # put the body's middle in the middle of the frame
        Rm = cams.rot(*par[:3]); c = P.mean(0) @ Rm.T
        par[3:5] = -c[:2]
        truth.append(par)

    def film(par):
        img, m = CT.render(P, F, fuv, tex, size=(W, H), cam=(cams.rot(*par[:3]), par[3:6], K), bg=(90, 95, 100))
        return img, m

    def reproj(par, ref):
        idx, _ = CR._visible(P, F, ref, K, W, H)
        a, _ = CR._project(par, P[idx], K); b, _ = CR._project(ref, P[idx], K)
        return float(np.median(np.linalg.norm(a - b, axis=1)))

    def knock(par, deg, cm):
        p = par.copy()
        p[:3] += rng.uniform(-1, 1, 3) * deg
        p[3:6] += rng.uniform(-1, 1, 3) * cm / 100.0
        return p
    # 1 knocked-off cameras come back
    errs0, errs1 = [], []
    for k, tp in enumerate(truth):
        img, m = film(tp)
        bad = knock(tp, rng.uniform(0.5, 2.0), rng.uniform(0.5, 2.0))
        cur = bad
        for _ in range(2):
            cur, info = CR.register_frame(P, F, fuv, soft, img, m, cur, K, rng=np.random.default_rng(k))
        errs0.append(reproj(bad, tp)); errs1.append(reproj(cur, tp))
    e0, e1 = np.median(errs0), np.median(errs1)
    worse = sum(b > a + 0.3 for a, b in zip(errs0, errs1))
    rec("knocked-off cameras come back (median error halved)", e1 < 0.5 * e0, "%.2f -> %.2f px" % (e0, e1))
    rec("no frame ends up worse", worse == 0, "per frame %s -> %s" % (np.round(errs0, 1).tolist(), np.round(errs1, 1).tolist()))
    # 2 a right camera stays right
    img, m = film(truth[1])
    new, info = CR.register_frame(P, F, fuv, soft, img, m, truth[1], K)
    rec("a right camera stays right", reproj(new, truth[1]) < 0.3, "moved %.2f px (%s)" % (reproj(new, truth[1]), "kept" if info["kept"] else info.get("why")))
    # 3 not the person
    noise = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    bad = knock(truth[2], 1.0, 1.0)
    new, info = CR.register_frame(P, F, fuv, soft, noise, film(truth[2])[1], bad, K)
    rec("a frame that is not the person keeps its camera", np.allclose(new, bad), info.get("why", "moved!"))
    # 4 half the person hidden
    img, m = film(truth[3])
    img = img.copy(); img[:, : W // 2] = (40, 40, 40)
    m2 = m.copy(); m2[:, : W // 2] = False
    bad = knock(truth[3], 1.2, 1.2)
    new, info = CR.register_frame(P, F, fuv, soft, img, m2, bad, K)
    rec("half the person hidden: never worse", reproj(new, truth[3]) <= reproj(bad, truth[3]) + 0.3,
        "%.2f -> %.2f px (%s)" % (reproj(bad, truth[3]), reproj(new, truth[3]), "kept" if info["kept"] else info.get("why")))
    # 5 far off: a tracking failure is not a misfit
    img, m = film(truth[4])
    far = truth[4].copy(); far[0] += 15.0
    new, info = CR.register_frame(P, F, fuv, soft, img, m, far, K)
    rec("a camera 15 degrees off is left alone", np.allclose(new, far), info.get("why", "moved!"))
    # 6 tiny person
    tiny = truth[5].copy(); tiny[5] = 40.0
    img, m = film(tiny)
    new, info = CR.register_frame(P, F, fuv, soft, img, m, knock(tiny, 1.0, 1.0), K)
    rec("a tiny person in the frame is left alone", not info["kept"], info.get("why", "moved!"))
    # 7 kinds of video the five samples do not cover: each frame starts knocked off; the registration must never
    # leave a frame worse, and must help where the picture has something to align to
    def scenario(name, frame_fn, texture=tex, expect_help=True):
        e0s, e1s = [], []
        for k in (0, 2, 5, 6):
            tp = truth[k]
            img, m, tp = frame_fn(tp, texture)                  # tp: the camera that really filmed it
            bad = knock(tp, 1.5, 1.5)
            cur = bad
            for _ in range(2):
                cur, _ = CR.register_frame(P, F, fuv, cv2.GaussianBlur(texture, (0, 0), 2.0), img, m, cur, K,
                                           rng=np.random.default_rng(k))
            e0s.append(reproj(bad, tp)); e1s.append(reproj(cur, tp))
        never_worse = all(b <= a + 0.3 for a, b in zip(e0s, e1s))
        helped = np.median(e1s) < 0.7 * np.median(e0s)          # at least 30% of the way back
        rec("video: %s - never worse%s" % (name, ", and helps" if expect_help else ""),
            never_worse and (helped or not expect_help), "%.2f -> %.2f px" % (np.median(e0s), np.median(e1s)))

    def plain(tp, texture):
        img, m = CT.render(P, F, fuv, texture, size=(W, H), cam=(cams.rot(*tp[:3]), tp[3:6], K), bg=(90, 95, 100))
        return img, m, tp

    def closeup(tp, texture):                              # a close-up: legs out of the frame (like most phone videos)
        p = tp.copy(); p[5] = 1.6; p[4] -= 0.25
        return plain(p, texture)

    def dark(tp, texture):                                 # a dim room: low contrast, noisy
        img, m, tp = plain(tp, texture)
        img = np.clip(img.astype(np.float32) * 0.35 + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)
        return img, m, tp

    def blurred(tp, texture):                              # motion blur from a hand-held walk round
        img, m, tp = plain(tp, texture)
        k_ = np.zeros((9, 9), np.float32); k_[4, :] = 1 / 9.0
        return cv2.filter2D(img, -1, k_), m, tp

    def jpeg(tp, texture):                                 # heavy compression (messaging apps)
        img, m, tp = plain(tp, texture)
        ok, buf = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 25])
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)[..., ::-1].copy(), m, tp

    def ragged_mask(tp, texture):                          # a segmentation mask that bleeds and bites
        img, m, tp = plain(tp, texture)
        from scipy import ndimage as ndi
        m2 = ndi.binary_dilation(m, iterations=6) if rng.random() < 0.5 else ndi.binary_erosion(m, iterations=6)
        return img, m2, tp
    plain_tex = np.full_like(tex, 0); plain_tex[:] = (60, 70, 140)       # one plain colour: nothing to align to
    plain_tex = (plain_tex.astype(np.float32) * (0.9 + 0.1 * np.sin(20 * yy))[..., None]).astype(np.uint8)
    scenario("full body, textured clothes", plain)
    scenario("close-up, legs out of frame", closeup)
    scenario("dim room, noisy", dark)
    scenario("motion blur", blurred)
    scenario("heavy JPEG", jpeg)
    scenario("ragged segmentation mask", ragged_mask)
    scenario("plain one-colour clothes", plain, texture=plain_tex, expect_help=False)
    bad_ = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad_), len(R)))
    return 1 if bad_ else 0


if __name__ == "__main__":
    sys.exit(main())
