#!/usr/bin/env python3
"""Synthetic test of `forge.py capture` (v11) - no people, no MediaPipe: a known body is filmed by a virtual orbit.

  python tools/test_capture.py [--out DIR] [--quick]

1. a MakeHuman body with known, non-average shape sliders, arms down, painted with a known texture
2. rendered from 16 perspective cameras walking round it (plus hand-held wobble): frames, masks, part labels and the
   33 MediaPipe landmarks it would give (joints projected), written as a capture track
3. the fitter starts from the AVERAGE body and recovers the shape; the texture is baked back from the frames
Checks: silhouette IoU after the fit, the body's vertex error against the truth, texture colour error against the
truth texture, and the GLB / FBX / OBJ exports (skeleton, clips). v11.10: the fitted cameras are then knocked off
by 1-2 degrees / 1-2 cm (what a real video's landmark cameras are): the registration must halve the misfit in the
pictures, bring the cameras at least a third of the way back to the truth (the fitted body is not exactly the true
one, so the best camera for it is not exactly the true camera) and make the texture closer to the truth. Skips (exit 0) without the MakeHuman assets."""
from __future__ import annotations
import argparse
import json

import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out"); ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    from sforge import human as HU
    if not HU.have_assets():
        print("SKIP: MakeHuman assets missing (forge.py human --setup --from-git)"); return 0
    from sforge import capture_body as CB, capture_fit as CF, capture_texture as CT, capture_export as CE
    out = a.out or tempfile.mkdtemp(prefix="sfs_capture_test_")
    cap = os.path.join(out, "synthetic")
    for d in ("frames", "masks", "parts"):
        os.makedirs(os.path.join(cap, d), exist_ok=True)
    bm = CB.BodyModel()
    truth_mac = dict(gender=1.0, age=0.5, muscle=0.6, weight=0.7, proportions=0.5)
    truth_sl = dict(CB.SLIDERS and {k: 0.0 for k in CB.SLIDERS})
    truth_sl.update(torso_depth=0.6, belly=0.5, hip_width=0.4, thigh=0.4, shoulders=0.3)
    H_M = 1.80
    sh = bm.shape(truth_mac, truth_sl, H_M)
    dirs = {"upperarm01.L": [0.25, -0.97, 0.0], "upperarm01.R": [-0.25, -0.97, 0.0],
            "lowerarm01.L": [0.12, -0.99, 0.05], "lowerarm01.R": [-0.12, -0.99, 0.05],
            "upperleg01.L": [0.04, -1, 0], "upperleg01.R": [-0.04, -1, 0], "lowerleg01.L": [0.0, -1, 0], "lowerleg01.R": [0.0, -1, 0]}
    P, Pg, _ = sh.pose(dirs)
    # truth texture: smooth colour bands + stripes (something a bake can get wrong)
    R_ = 512
    yy, xx = np.mgrid[0:R_, 0:R_] / R_
    tex = np.stack([120 + 100 * np.sin(6 * xx), 110 + 90 * np.cos(5 * yy), 140 + 80 * np.sin(4 * (xx + yy))], -1)
    tex[(np.floor(yy * 24) % 2) == 0] *= 0.8
    tex = np.clip(tex, 0, 255).astype(np.uint8)
    W, Hh = 480, 640
    frames = []; truth_cams = {}
    n = 10 if a.quick else 16
    rng = np.random.default_rng(3)
    cams = CF.Cameras(0.8)
    for k in range(n):
        yaw = -180 + 360.0 * k / n + rng.normal(0, 3)
        pitch, roll = rng.normal(6, 2), rng.normal(0, 1.5)
        dist = 3.0 + rng.normal(0, 0.2)
        R = CF.Cameras.rot(yaw, pitch, roll)
        t = np.array([rng.normal(0, 0.05), 0.9 + rng.normal(0, 0.05), dist])
        K = cams.K((W, Hh))
        img, m = CT.render(P, bm.F, bm.fuv, tex, size=(W, Hh), cam=(R, t, K), bg=(90, 100, 110))
        truth_cams[k] = (R, t, K)
        Image.fromarray(img).save(os.path.join(cap, "frames", "%04d.jpg" % k), quality=95)
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(cap, "masks", "%04d.png" % k))
        # 2 = body skin: the synthetic person wears nothing. (Labelled clothes, v11.1's fit would - by design - let
        # the body sit inside them and come out ~1 cm small: skin-tight clothes are read as possibly loose)
        Image.fromarray((m * 2).astype(np.uint8)).save(os.path.join(cap, "parts", "%04d.png" % k))
        Pc = Pg @ R.T + t
        uv = Pc[:, :2] / Pc[:, 2:3] * K[0, 0] + K[:2, 2]
        lm = [[W / 2, Hh / 2, 0.0]] * 33
        lm = [list(x) for x in lm]
        for i, b in CF.LM_JOINT.items():
            q = uv[bm.bi[b]]; lm[i] = [float(q[0]), float(q[1]), 1.0]
        head = P[:, 1].argmax()
        q = (P[head] @ R.T + t); q = q[:2] / q[2] * K[0, 0] + K[:2, 2]
        lm[0] = [float(q[0]), float(q[1] + 30), 1.0]
        # world landmarks: joints in a camera-aligned frame (x right, y down, z away), hips at 0
        Wl = [[0.0, 0.0, 0.0]] * 33
        Wl = [list(x) for x in Wl]
        Rw = CF.Cameras.rot(yaw, 0, 0)
        hip = 0.5 * (Pg[bm.bi["upperleg01.L"]] + Pg[bm.bi["upperleg01.R"]])
        for i, b in CF.LM_JOINT.items():
            Wl[i] = (Rw @ (Pg[bm.bi[b]] - hip)).tolist()
        frames.append(dict(i=k, t=k * 0.5, ok=True, lm=lm, world=Wl, yaw=float(((yaw + 180) % 360) - 180), vis=1.0,
                           face=0, tpose=False, size=[W, Hh], orbit=float(yaw)))
    json.dump(dict(video="synthetic", fps=2, frames=frames, orbit_span_deg=360, tpose_frames=[]), open(os.path.join(cap, "track.json"), "w"))
    # ---- fit from the average body
    f = CF.Fitter(cap, height_m=H_M, n_frames=16, log=print)
    res = f.fit(iters=2 if a.quick else 3)
    fit_sh = bm.shape(f.mac, f.sl, H_M)
    err_cm = float(np.mean(np.linalg.norm(fit_sh.V - sh.V, axis=1)) * 100)
    avg = bm.shape(dict(gender=1.0), {}, H_M)
    err0_cm = float(np.mean(np.linalg.norm(avg.V - sh.V, axis=1)) * 100)
    print("shape: mean vertex error %.2f cm (average body: %.2f cm), silhouette IoU %.3f" % (err_cm, err0_cm, res["iou"]))
    t8, cov, st = CT.bake(f, frames=[t.r for t in f.targets], res=R_)
    tid, _ = CT.texel_map(bm.F, bm.fuv, R_)
    seen = (tid >= 0) & (cov > 0)
    tex_err = float(np.mean(np.abs(t8[seen].astype(float) - tex[seen].astype(float))))
    print("texture: mean abs colour error %.1f / 255 on %.0f%% of texels" % (tex_err, 100 * seen.mean()))
    # ---- v11.10 registration: a real video's landmark cameras are 1-2 cm / 1-2 degrees off (the synthetic fit is
    # nearly perfect), so knock them off by that much and let the registration find the pictures again
    import cv2
    from sforge import capture_register as CRG
    _, Pfit, _ = f.posed()

    def cam_err():
        e = []
        for t_ in f.targets:
            i = t_.r["i"]
            if i not in f.cams.par:
                continue
            Rt, tt, Kt = truth_cams[i]
            a_ = P @ Rt.T + tt; a_ = a_[:, :2] / a_[:, 2:3] * Kt[0, 0] + Kt[:2, 2]
            b_, _ = CRG._project(f.cams.par[i], P, Kt)
            e.append(float(np.median(np.linalg.norm(a_ - b_, axis=1))))
        return float(np.median(e))
    e_fit = cam_err()
    rng2 = np.random.default_rng(11)
    for i in list(f.cams.par):
        p_ = np.array(f.cams.par[i], float)
        p_[:3] += rng2.uniform(-1, 1, 3) * rng2.uniform(1.0, 2.0); p_[3:6] += rng2.uniform(-1, 1, 3) * rng2.uniform(0.01, 0.02)
        rv_, _ = cv2.Rodrigues(CF.Cameras.rot(*p_[:3])); f.cams.par[i] = p_; f.cams.cam[i] = (rv_.reshape(3), p_[3:6].copy())
    e_knock = cam_err()
    knocked = {i: (np.array(c[0]), np.array(c[1])) for i, c in f.cams.cam.items()}
    tk, _, _ = CT.bake(f, frames=[t.r for t in f.targets], res=R_, align=False, clean=False, log=lambda *x: None)
    tex_err_k = float(np.mean(np.abs(tk[seen].astype(float) - tex[seen].astype(float))))
    _, rsum = CRG.register(f, [t.r for t in f.targets], tk, log=print)
    e_reg = cam_err()
    c0 = getattr(f.cams, "cam0", {}) or {}
    moved = [i for i in f.cams.cam if not np.allclose(f.cams.cam[i][1], knocked[i][1])]
    hands_feet_ok = bool(moved) and all(i in c0 and np.allclose(c0[i][0], knocked[i][0]) and np.allclose(c0[i][1], knocked[i][1])
                                        for i in moved)
    print("registration kept the camera of: %s" % sorted(set((rsum.get("refused") or {}).values())))
    tr, _, _ = CT.bake(f, frames=[t.r for t in f.targets], res=R_, align=False, clean=False, log=lambda *x: None)
    tex_err_r = float(np.mean(np.abs(tr[seen].astype(float) - tex[seen].astype(float))))
    print("cameras vs truth (median px): fitted %.2f, knocked off %.2f, registered %.2f; texture error %.1f -> %.1f" % (
        e_fit, e_knock, e_reg, tex_err_k, tex_err_r))
    files = CE.export(fit_sh, fit_sh.pose(f.dirs)[0], t8, os.path.join(out, "export"), "synthetic")
    from sforge import fbx as FBX
    fs = FBX.summary(files["fbx"])
    checks = [("silhouette IoU > 0.95", res["iou"] > 0.95),
              ("body vertex error < 1.0 cm", err_cm < 1.0),
              ("texture error < 25", tex_err < 25),
              ("GLB written", os.path.getsize(files["glb"]) > 100000),
              ("FBX: 26 bones, 7 takes", fs["limb_nodes"] == 26 and len(fs["anim_stacks"]) == 7),
              ("OBJ written", os.path.getsize(files["obj"]) > 100000),
              # the fitted body is not exactly the true one, so the camera that fits the pictures best is not exactly
              # the true camera: the pictures' misfit must halve, the camera must come at least a third of the way back
              ("registration: misfit in the pictures halved", rsum["flow_px_after"] < 0.5 * rsum["flow_px_before"]),
              ("registration: cameras a third of the way back", e_reg < 0.67 * e_knock),
              ("registration: texture closer to the truth", tex_err_r < tex_err_k),
              # hands and feet are drawn through the landmark camera (they move on their own)
              ("registration: hands/feet keep the landmark camera", hands_feet_ok)]
    bad = 0
    for name, ok in checks:
        print("%-44s %s" % (name, "PASS" if ok else "FAIL")); bad += not ok
    print("capture test: %d/%d passed -> %s" % (len(checks) - bad, len(checks), out))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
