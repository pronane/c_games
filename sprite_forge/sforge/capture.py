"""forge.py capture - a person filmed walking round (a turnaround video) -> a rigged, textured 3D character (v11).

    forge.py capture --setup                                   # MediaPipe models (once) - MakeHuman: human --setup
    forge.py capture VIDEO --name mike [--height-cm 180] [--out captures/] [--fps 4] [--texture 1024]

How to film: the person stands still, arms a little away from the body, while you walk once round them holding the
phone at chest height, whole body in the frame where you can (feet may be cut off now and then). A T-pose at the end
is used if present. 20-40 s is plenty.

Steps (all on the CPU, no Blender / MakeHuman program needed):
  1 track     capture_track    MediaPipe pose + person mask + hair / skin / clothes labels per frame, body yaw
  2 fit       capture_fit      MakeHuman CC0 body shape + arm / leg pose + one camera per frame, to the silhouettes
  3 texture   capture_texture  photo texture baked into MakeHuman's UV layout from the best views
  4 export    capture_export   GLB / FBX (skeleton, weights, 7 clips) + OBJ + Sprite Forge library rig
  5 check     held-out frames (not used for the texture) are re-rendered from their cameras and compared with the
              real frames: silhouette IoU, colour difference (CIE dE), structural similarity (SSIM) -> report.json
"""
from __future__ import annotations
import json
import os
import pickle
import time
import numpy as np
from PIL import Image

from . import capture_track as CTR, capture_fit as CF, capture_texture as CT, capture_export as CE


def evaluate(fitter, frames, tex, log=print, mesh=None, keep_renders=None):
    """re-render held-out frames from their cameras and compare with the real frames (inside the person mask).
    mesh: (rest Mesh, skin matrices) of the layered character; keep_renders: dict filled with frame -> render"""
    import cv2
    sh, P, Pg = fitter.posed()
    Fm, fuvm = fitter.bm.F, fitter.bm.fuv
    if mesh is not None:
        P = mesh[0].pose(mesh[1]); Fm, fuvm = mesh[0].F, mesh[0].fuv
    rows = []
    for r in frames:
        if r["i"] not in fitter.cams.cam:
            continue
        img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        msk = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % r["i"]))) > 127
        H, W = img.shape[:2]
        rv, tv = fitter.cams.cam[r["i"]]
        R, _ = cv2.Rodrigues(rv)
        ren, m = CT.render(P, Fm, fuvm, tex, size=(W, H), cam=(R, tv, fitter.cams.K(r["size"])))
        if keep_renders is not None:
            keep_renders[r["i"]] = (ren, m)
        inter = m & msk; union = m | msk
        iou = inter.sum() / max(1, union.sum())
        lab_a = cv2.cvtColor(ren, cv2.COLOR_RGB2LAB).astype(float); lab_b = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(float)
        de = float(np.median(np.linalg.norm((lab_a - lab_b)[inter] * [100 / 255.0, 1, 1], axis=1))) if inter.any() else None
        ys, xs = np.nonzero(inter)
        ssim = None
        if len(ys) > 400:
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            ga = cv2.cvtColor(ren[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(float)
            gb = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(float)
            ssim = _ssim(ga, gb, inter[y0:y1, x0:x1])
        rows.append(dict(frame=r["i"], yaw=round(r["yaw"]), iou=float(iou), dE=de, ssim=ssim))
    def mean(k):
        v = [x[k] for x in rows if x[k] is not None]
        return float(np.mean(v)) if v else None
    out = dict(frames=rows, iou=mean("iou"), dE=mean("dE"), ssim=mean("ssim"))
    log("check (%d held-out frames): silhouette IoU %.3f, colour dE %.1f, SSIM %.2f" % (
        len(rows), out["iou"] or 0, out["dE"] or 0, out["ssim"] or 0))
    return out


def _ssim(a, b, m):
    import cv2
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a = cv2.GaussianBlur(a, (7, 7), 1.5); mu_b = cv2.GaussianBlur(b, (7, 7), 1.5)
    va = cv2.GaussianBlur(a * a, (7, 7), 1.5) - mu_a ** 2; vb = cv2.GaussianBlur(b * b, (7, 7), 1.5) - mu_b ** 2
    cov = cv2.GaussianBlur(a * b, (7, 7), 1.5) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + C1) * (2 * cov + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(s[m].mean())


def turntable(P, F, fuv, tex, path, yaws=(0, 45, 90, 135, 180, 225, 270, 315), size=(300, 420)):
    ims = [Image.fromarray(CT.render(P, F, fuv, tex, y, size=size)[0]) for y in yaws]
    W = Image.new("RGB", (size[0] * len(ims), size[1]))
    for i, im in enumerate(ims):
        W.paste(im, (i * size[0], 0))
    W.save(path)
    return path


def run(video=None, name="captured", out_root="captures", height_m=1.75, fps=4.0, tex_res=1024, track_dir=None,
        fit_iters=3, gender=None, log=print, layers=True, face=True, delight=True, face_photo=None):
    t0 = time.time()
    d = os.path.join(out_root, name)
    os.makedirs(d, exist_ok=True)
    if track_dir is None:
        if not os.path.isfile(os.path.join(d, "track.json")):
            CTR.track(video, d, fps, log)
    else:
        d = track_dir
    f = CF.Fitter(d, height_m=height_m, n_frames=24, log=log)
    if gender is not None:
        f.set_gender(gender)
    res = f.fit(iters=fit_iters)
    res.pop("iou_frames_detail", None)
    log("fit: mean silhouette IoU %.3f (start %.3f)" % (res["iou"], res["iou_start"]))
    pickle.dump(dict(mac=f.mac, sl=f.sl, par=f.cams.par, focal=f.cams.focal_k, dirs=f.dirs, height_m=height_m,
                     fit=dict(iou=res["iou"], iou_start=res["iou_start"], frames=len(res["iou_frames"]))),
                open(os.path.join(d, "fit.pkl"), "wb"))
    rep = finish(d, name, height_m, tex_res, log=log, fitter=f, layers=layers, face=face, delight=delight,
                 face_photo=face_photo)
    rep["video"] = os.path.basename(video) if video else None
    rep["seconds"] = round(time.time() - t0)
    json.dump(rep, open(os.path.join(d, "out", "report.json"), "w"), indent=1)
    log("capture: %s done in %d s -> %s" % (name, rep["seconds"], os.path.join(d, "out")))
    return rep


def _save_pairs(f, frames, renders, out_dir):
    """real frame | render from the same camera, for the held-out frames (what external metrics compare)"""
    os.makedirs(out_dir, exist_ok=True)
    for r in frames:
        if r["i"] not in renders:
            continue
        img = np.asarray(Image.open(os.path.join(f.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
        msk = np.asarray(Image.open(os.path.join(f.dir, "masks", "%04d.png" % r["i"]))) > 127
        ren, m = renders[r["i"]]
        Image.fromarray(img).save(os.path.join(out_dir, "%04d_real.jpg" % r["i"]), quality=95)
        Image.fromarray(ren).save(os.path.join(out_dir, "%04d_render.jpg" % r["i"]), quality=95)
        Image.fromarray((msk * 255).astype(np.uint8)).save(os.path.join(out_dir, "%04d_mask.png" % r["i"]))
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(out_dir, "%04d_rmask.png" % r["i"]))


def finish(d, name, height_m=None, tex_res=1024, log=print, fitter=None, layers=True, out_name="out", face=True,
           delight=True, face_photo=None):
    """cameras for every usable frame, texture (checked on held-out frames), exports. Re-runnable from fit.pkl
    (`forge.py capture --rebuild NAME`) when the texture or export code improves - no refit needed."""
    import cv2
    fp = pickle.load(open(os.path.join(d, "fit.pkl"), "rb"))
    height_m = height_m or fp.get("height_m", 1.75)
    f = fitter or CF.Fitter(d, height_m=height_m, n_frames=24, log=lambda *a: None)
    f.mac, f.sl = dict(fp["mac"]), dict(fp["sl"])
    if fp.get("dirs"):
        f.dirs = fp["dirs"]
    allf = CF.pick_frames(f.track, 72)
    f.targets = [CF.Target(d, r, f.scale) for r in allf]
    f.frames = allf
    sh, P, Pg = f.posed()
    if True:                                    # cameras are cheap next to the fit: always re-solve
        f.solve_cameras(Pg); f.refine_cameras(P, Pg)
        fp["par"] = dict(f.cams.par); fp["all_cams"] = True
        pickle.dump(fp, open(os.path.join(d, "fit.pkl"), "wb"))
    else:
        for i, p in fp["par"].items():
            rv, _ = cv2.Rodrigues(CF.Cameras.rot(*p[:3])); f.cams.par[i] = p; f.cams.cam[i] = (rv.reshape(3), p[3:6])
    # every 4th usable frame is held out of the texture (and of the face fit) and used to check it
    held = allf[2::4]
    train = [r for r in allf if r not in held]
    # the face's own shape and each frame's head pose (v11.2)
    finfo = None
    if face:
        from . import capture_face as CFA
        sl0 = dict(f.sl)
        finfo = CFA.fit_face(f, train, log=log)
        if finfo:
            corr = f.face["corr"]
            sl1 = dict(f.sl); f.sl = sl0
            e0 = CFA.landmark_error(f, held, corr)
            f.sl = sl1
            e1 = CFA.landmark_error(f, held, corr)
            finfo.update(heldout_err_pct_before=e0[0], heldout_err_pct_after=e1[0], heldout_frames=e1[1])
            if e1[0] is not None:
                log("face: held-out frames, landmark error %.1f%% -> %.1f%% of the face width (%d frames)" % (e0[0], e1[0], e1[1]))
            # head poses for every frame that sees the face (the held-out ones are only used for the final texture)
            sh_, P_, _ = f.posed()
            dets = CFA.detect(f.dir, allf)
            f.face["poses"] = CFA.head_poses(f, allf, dets, CFA.pts(P_, corr), guess=f.face["poses"])
    # clothes / skirt / hair layers over the tight body (v11.1); --no-layers keeps the bare body
    mesh = None; linfo = None
    if layers:
        from . import capture_layers as CL
        M, linfo, S = CL.fit_layers(f, log=log)
        mesh = (M, S)
        res_ = tex_res * 2                                         # the atlas: four quarters of tex_res
    else:
        res_ = tex_res
    tex, cov, st = CT.bake(f, frames=train, res=res_, log=lambda *a: None, mesh=mesh, delight=delight)
    renders = {}
    # the held-out frames are real footage, with the room's light in them: they are compared with the texture as
    # filmed (the light put back), the exported texture is the light-free one
    ctex = st.get("lit_texture", tex)
    use_photo = face_photo and getattr(f, "face", None)
    if use_photo:
        from . import capture_face as CFA
        ctex, _ = CFA.paint_photo(f, ctex, mesh, face_photo, log=lambda *a: None)
    check = evaluate(f, held, ctex, log=log, mesh=mesh, keep_renders=renders)
    _save_pairs(f, held, renders, os.path.join(d, out_name, "heldout"))
    tex, cov, st = CT.bake(f, frames=allf, res=res_, log=log, mesh=mesh, delight=delight)    # final: every frame
    lit = st.pop("lit_texture", None)
    if use_photo:
        tex, st["face_photo"] = CFA.paint_photo(f, tex, mesh, face_photo, log=log)
        if lit is not None:
            lit, _ = CFA.paint_photo(f, lit, mesh, face_photo, log=lambda *a: None)
    outd = os.path.join(d, out_name)
    os.makedirs(outd, exist_ok=True)
    sh = f.bm.shape(f.mac, f.sl, height_m)
    Pst, _, Sst = sh.pose(f.dirs)
    Pm = mesh[0].pose(mesh[1]) if mesh is not None else None
    if lit is not None:
        # light taken out? bodies and most clothes are left / right symmetric, a lamp on one side is not. If the
        # light-free texture is LESS symmetric, the light found was really the clothes (dark, striped): keep the
        # texture as filmed
        from . import capture_light as CLI
        Vq, Fq, uvq, lay = (Pm, mesh[0].F, mesh[0].fuv, mesh[0].layer) if mesh is not None else (Pst, f.bm.F, f.bm.fuv, None)
        sym = {}
        for nm_, lid in (("body", 0), ("clothes", 1)):
            m_ = (lay == lid) if lay is not None else None
            if m_ is not None and not m_.any():
                continue
            a_ = CLI.symmetry_de(Vq, Fq, uvq, lit, m_)[0]; b_ = CLI.symmetry_de(Vq, Fq, uvq, tex, m_)[0]
            sym[nm_] = dict(as_filmed=round(a_, 2), light_removed=round(b_, 2))
        keep = np.mean([v["light_removed"] for v in sym.values()]) <= np.mean([v["as_filmed"] for v in sym.values()])
        st["light"].update(left_right_dE=sym, kept_removed=bool(keep))
        log("light: left / right colour difference %s - %s" % (", ".join(
            "%s dE %.1f -> %.1f" % (k, v["as_filmed"], v["light_removed"]) for k, v in sym.items()),
            "light removed" if keep else "not better: the texture is kept as filmed"))
        if keep:
            Image.fromarray(lit).save(os.path.join(outd, name + "_texture_as_filmed.png"))
            json.dump(dict(model="real spherical harmonics, order 2, per RGB channel, in log space: "
                                 "as_filmed = (albedo + 4) * exp(sum_k sh[c][k] * Y_k(normal)) - 4; normal in the "
                                 "character's frame (x = its left, y up, z front); constant terms are in the albedo",
                           sh=st["light"]["sh"], spread=st["light"]["spread"], tint=st["light"]["tint"]),
                      open(os.path.join(outd, name + "_lighting.json"), "w"), indent=1)
        else:
            tex = lit
            for fn in (name + "_texture_as_filmed.png", name + "_lighting.json"):
                if os.path.isfile(os.path.join(outd, fn)):
                    os.remove(os.path.join(outd, fn))
    mh = dict(macros=f.mac, sliders=f.sl, height_m=height_m)
    if mesh is not None:
        files = CE.export(sh, Pst, tex, outd, name, log=log, mesh=mesh[0], posed_mesh=Pm, makehuman=mh,
                          extras={"capture": dict(macros=f.mac, sliders=f.sl, height_m=height_m, layers=linfo)})
        turntable(Pm, mesh[0].F, mesh[0].fuv, tex, os.path.join(outd, name + "_turntable.jpg"))
    else:
        files = CE.export(sh, Pst, tex, outd, name, log=log, makehuman=mh,
                          extras={"capture": dict(macros=f.mac, sliders=f.sl, height_m=height_m)})
        turntable(Pst, f.bm.F, f.bm.fuv, tex, os.path.join(outd, name + "_turntable.jpg"))
    f.overlay(os.path.join(outd, name + "_fit_overlay.jpg"))
    rep = dict(name=name, height_m=height_m, fit=fp.get("fit"),
               macros={k: float(v) for k, v in f.mac.items()}, sliders={k: float(v) for k, v in f.sl.items()},
               pose={k: v for k, v in f.dirs.items()}, texture=st, check=check, layers=linfo, face=finfo,
               files={k: (os.path.basename(v) if isinstance(v, str) else None) for k, v in files.items() if k != "rig"})
    json.dump(rep, open(os.path.join(outd, "report.json"), "w"), indent=1)
    return rep


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="forge.py capture", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--setup", action="store_true", help="download the MediaPipe models into models/")
    ap.add_argument("--name", default="captured")
    ap.add_argument("--height-cm", type=float, default=175.0, help="the person's height (one camera cannot measure size)")
    ap.add_argument("--out", default="captures")
    ap.add_argument("--fps", type=float, default=4.0, help="frames sampled per second of video")
    ap.add_argument("--texture", type=int, default=1024)
    ap.add_argument("--body", choices=["auto", "male", "female"], default="auto",
                    help="the body's sex; auto fits it (clothes can fool it: a long jumper reads as either)")
    ap.add_argument("--no-layers", action="store_true",
                    help="bare body only: no separate clothes / skirt / hair meshes (v11 behaviour)")
    ap.add_argument("--face-photo", help="a close-up photo of the face (front-on, even light): painted onto the face")
    ap.add_argument("--no-face", action="store_true", help="keep MakeHuman's average face (no face-shape fit)")
    ap.add_argument("--keep-light", action="store_true",
                    help="leave the room's light in the texture (default: divided out; see NAME_lighting.json)")
    ap.add_argument("--rebuild", action="store_true", help="redo texture + exports of an existing capture (OUT/NAME) from its fit")
    a = ap.parse_args(argv)
    if a.rebuild:
        finish(os.path.join(a.out, a.name), a.name, a.height_cm / 100.0 if a.height_cm != 175.0 else None, a.texture,
               layers=not a.no_layers, face=not a.no_face, delight=not a.keep_light, face_photo=a.face_photo)
        return 0
    if a.setup:
        CTR.setup(); return 0
    if not a.video:
        ap.error("give a VIDEO (or --setup)")
    g = {"auto": None, "male": 1.0, "female": 0.0}[a.body]
    if os.path.splitext(a.video)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
        from . import capture_photo as CPH                  # one photo: depth from the priors, back painted
        CPH.run_photo(a.video, a.name, a.out, a.height_cm / 100.0, a.texture, gender=g)
        return 0
    run(a.video, a.name, a.out, a.height_cm / 100.0, a.fps, a.texture, gender=g, layers=not a.no_layers,
        face=not a.no_face, delight=not a.keep_light, face_photo=a.face_photo)
    return 0
