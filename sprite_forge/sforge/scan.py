"""forge.py scan  -  orbit video -> photogrammetry project -> (CPU) mesh -> console LODs.

Honest scope: this is a GUIDED pipeline, not one-click.
  1. extract   sharpest frame per time slot from an orbit video -> <work>/images  (+ COLMAP/Meshroom scripts)
  2. --run     COLMAP sparse SfM on CPU: pycolmap pip wheel (default) or the colmap CLI on PATH
  3. dense     our CPU dense step: SGBM stereo on neighbouring rectified views -> depth maps, cross-checked
               between two neighbours -> TSDF fusion -> marching cubes -> floor cut -> largest piece.
               (COLMAP's own dense patch-match needs CUDA; OpenMVS / Meshroom do better if installed.)
  4. LODs      decimate to console triangle budgets (open3d / Blender / numpy vertex clustering) -> GLB+OBJ.
  --mesh FILE  skip 1-3: import a mesh made elsewhere (Meshroom, RealityScan, Polycam, OpenMVS...) and do 4.
Pure numpy/OpenCV/scikit-image; COLMAP does the SfM, OpenCV the stereo.
"""
import os, sys, json, math, time, shutil, struct, subprocess
import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def log(*a):
    print("scan:", *a); sys.stdout.flush()


# ----------------------------------------------------------------------------- 1. frames
def extract_frames(video, out_dir, n=80, start=None, end=None, max_w=1280):
    """Decode with ffmpeg, keep the sharpest frame (variance of Laplacian) in each of n equal time slots."""
    frames, fps = _decode(video, max_w, start, end)
    N = len(frames)
    if N == 0:
        raise SystemExit("scan: no frames decoded from %s" % video)
    n = min(n, N)
    sharp = np.array([cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), cv2.CV_32F).var() for f in frames])
    edges = np.linspace(0, N, n + 1).astype(int)
    picks = [int(a + np.argmax(sharp[a:b])) for a, b in zip(edges[:-1], edges[1:]) if b > a]
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for k, i in enumerate(picks):
        nm = "frame_%04d.png" % k
        cv2.imwrite(os.path.join(out_dir, nm), cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR))
        names.append(nm)
    blurry = int((sharp[picks] < 0.35 * np.median(sharp)).sum())
    return {"decoded": N, "fps": fps, "picked": picks, "size": [frames[0].shape[1], frames[0].shape[0]],
            "blurry_picks": blurry, "sharpness_median": float(np.median(sharp))}


def _decode(path, max_w, start, end):
    from . import media
    st = media.probe(path)
    w, h, fps = st["w"], st["h"], st["fps"]
    if w > max_w:
        h = int(round(h * max_w / w / 2) * 2); w = max_w
    w -= w % 2; h -= h % 2
    fr = media.read_frames(path, w, h, start, end)
    return [f for f in fr], fps


def write_project_scripts(work):
    sh = """#!/bin/sh
# COLMAP sparse reconstruction on CPU (run from this folder). Dense: needs CUDA (patch_match_stereo) or use OpenMVS.
colmap feature_extractor --database_path db.db --image_path images --ImageReader.single_camera 1 --ImageReader.camera_model SIMPLE_RADIAL --SiftExtraction.use_gpu 0
colmap sequential_matcher --database_path db.db --SiftMatching.use_gpu 0 --SequentialMatching.overlap 10
mkdir -p sparse && colmap mapper --database_path db.db --image_path images --output_path sparse
# with a CUDA GPU you can continue with COLMAP's own dense MVS:
# colmap image_undistorter --image_path images --input_path sparse/0 --output_path dense
# colmap patch_match_stereo --workspace_path dense && colmap stereo_fusion --workspace_path dense --output_path dense/fused.ply
# colmap poisson_mesher --input_path dense/fused.ply --output_path dense/meshed.ply
"""
    open(os.path.join(work, "run_colmap.sh"), "w").write(sh)
    open(os.path.join(work, "run_colmap.bat"), "w").write(sh.replace("#!/bin/sh\n", "@echo off\n").replace("# ", "REM ")
                                                          .replace("mkdir -p sparse &&", "mkdir sparse 2>nul &"))
    open(os.path.join(work, "MESHROOM_AND_OTHERS.txt"), "w").write(
        "Other tools that take the images/ folder directly (better dense quality than our CPU step):\n"
        "  Meshroom (AliceVision, free, NVIDIA GPU for depth maps): drag images/ in, press Start, export Texturing/texturedMesh.obj\n"
        "  RealityScan / RealityCapture, Polycam, Kiri Engine (phone apps / cloud), COLMAP + OpenMVS (CPU, slow)\n"
        "  Gaussian splatting (Postshot, nerfstudio) gives great looking captures but NOT a game mesh without extra work.\n"
        "Then:  python forge.py scan --mesh texturedMesh.obj --name myobject   -> console LODs\n")


# ----------------------------------------------------------------------------- 2. COLMAP
def sfm_backend():
    """'pycolmap' (pip wheel, CPU) > 'colmap' binary on PATH / $SFS_COLMAP > None."""
    try:
        import pycolmap  # noqa: F401
        return "pycolmap"
    except Exception:
        pass
    if shutil.which(os.environ.get("SFS_COLMAP", "colmap")):
        return "colmap"
    return None


def run_pycolmap(work, exhaustive=False):
    import pycolmap
    if not os.environ.get("SFS_VERBOSE"):          # COLMAP logs every image at INFO level; keep errors only
        try:
            pycolmap.logging.minloglevel = 2
        except Exception:
            pass
    db = os.path.join(work, "db.db")
    if os.path.exists(db):
        os.remove(db)
    sp = os.path.join(work, "sparse"); shutil.rmtree(sp, ignore_errors=True); os.makedirs(sp)
    imgs = os.path.join(work, "images")
    t = {}
    cpu = getattr(getattr(pycolmap, "Device", None), "cpu", None)
    t0 = time.time()
    try:                                      # pycolmap >= 3.12 / 4.x API
        ro = pycolmap.ImageReaderOptions(); ro.camera_model = "SIMPLE_RADIAL"
        eo = pycolmap.FeatureExtractionOptions(); eo.use_gpu = False
        pycolmap.extract_features(db, imgs, camera_mode=pycolmap.CameraMode.SINGLE, reader_options=ro, extraction_options=eo,
                                  device=cpu)
    except (AttributeError, TypeError):       # older pycolmap (0.4 - 3.11)
        pycolmap.extract_features(db, imgs, camera_mode=pycolmap.CameraMode.SINGLE, camera_model="SIMPLE_RADIAL")
    t["features"] = round(time.time() - t0, 1); log("pycolmap features: %.1fs" % t["features"])
    t0 = time.time()
    if exhaustive:
        pycolmap.match_exhaustive(db)
    else:
        try:
            po = pycolmap.SequentialPairingOptions(); po.overlap = 10; po.loop_detection = False
            pycolmap.match_sequential(db, pairing_options=po)
        except (AttributeError, TypeError):
            mo = pycolmap.SequentialMatchingOptions(); mo.overlap = 10; mo.loop_detection = False
            pycolmap.match_sequential(db, matching_options=mo)
    t["matching"] = round(time.time() - t0, 1); log("pycolmap matching: %.1fs" % t["matching"])
    t0 = time.time()
    recs = pycolmap.incremental_mapping(db, imgs, sp)
    t["mapper"] = round(time.time() - t0, 1); log("pycolmap mapper: %.1fs" % t["mapper"])
    if not recs:
        raise SystemExit("scan: COLMAP registered no model - orbit too fast / too little texture? see help scan")
    best = max(recs.values(), key=lambda r: r.num_reg_images())
    txt = os.path.join(work, "sparse_txt"); os.makedirs(txt, exist_ok=True)
    best.write_text(txt)
    t["backend"] = "pycolmap %s" % getattr(pycolmap, "__version__", "?")
    return txt, t


def run_colmap(work, exhaustive=False, colmap=None):
    be = os.environ.get("SFS_SFM", "") or sfm_backend()
    if be == "pycolmap":
        return run_pycolmap(work, exhaustive)
    colmap = colmap or os.environ.get("SFS_COLMAP", "colmap")
    if not shutil.which(colmap):
        raise SystemExit("scan: no SfM engine. `pip install pycolmap` (CPU wheel, Windows/Linux/macOS) or install the COLMAP "
                         "binary, or run Meshroom on %s/images and come back with --mesh" % work)
    db = os.path.join(work, "db.db")
    if os.path.exists(db):
        os.remove(db)
    sp = os.path.join(work, "sparse"); shutil.rmtree(sp, ignore_errors=True); os.makedirs(sp)
    t = {}
    steps = [("features", [colmap, "feature_extractor", "--database_path", db, "--image_path", os.path.join(work, "images"),
                           "--ImageReader.single_camera", "1", "--ImageReader.camera_model", "SIMPLE_RADIAL", "--SiftExtraction.use_gpu", "0"]),
             ("matching", [colmap, "exhaustive_matcher", "--database_path", db, "--SiftMatching.use_gpu", "0"] if exhaustive else
                          [colmap, "sequential_matcher", "--database_path", db, "--SiftMatching.use_gpu", "0",
                           "--SequentialMatching.overlap", "10", "--SequentialMatching.loop_detection", "0"]),
             ("mapper", [colmap, "mapper", "--database_path", db, "--image_path", os.path.join(work, "images"), "--output_path", sp])]
    for nm, cmd in steps:
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        open(os.path.join(work, "colmap_%s.log" % nm), "w").write(r.stdout + r.stderr)
        t[nm] = round(time.time() - t0, 1)
        log("colmap %s: %.1fs" % (nm, t[nm]))
        if r.returncode:
            raise SystemExit("scan: colmap %s failed (see colmap_%s.log)" % (nm, nm))
    models = sorted([d for d in os.listdir(sp) if d.isdigit()], key=lambda d: -os.path.getsize(os.path.join(sp, d, "images.bin")))
    if not models:
        raise SystemExit("scan: COLMAP registered no model - orbit too fast / too little texture? see help scan")
    best = os.path.join(sp, models[0]); txt = os.path.join(work, "sparse_txt"); os.makedirs(txt, exist_ok=True)
    subprocess.run([colmap, "model_converter", "--input_path", best, "--output_path", txt, "--output_type", "TXT"], capture_output=True)
    t["backend"] = "colmap CLI"
    return txt, t


def read_colmap_txt(d):
    cams = {}
    for ln in open(os.path.join(d, "cameras.txt")):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split(); cid, model, w, h = int(p[0]), p[1], int(p[2]), int(p[3]); pr = [float(v) for v in p[4:]]
        if model == "SIMPLE_RADIAL":
            K = np.array([[pr[0], 0, pr[1]], [0, pr[0], pr[2]], [0, 0, 1]]); dist = np.array([pr[3], 0, 0, 0])
        elif model == "PINHOLE":
            K = np.array([[pr[0], 0, pr[2]], [0, pr[1], pr[3]], [0, 0, 1]]); dist = np.zeros(4)
        elif model in ("SIMPLE_PINHOLE",):
            K = np.array([[pr[0], 0, pr[1]], [0, pr[0], pr[2]], [0, 0, 1]]); dist = np.zeros(4)
        elif model == "RADIAL":
            K = np.array([[pr[0], 0, pr[1]], [0, pr[0], pr[2]], [0, 0, 1]]); dist = np.array([pr[3], pr[4], 0, 0])
        else:  # OPENCV
            K = np.array([[pr[0], 0, pr[2]], [0, pr[1], pr[3]], [0, 0, 1]]); dist = np.array(pr[4:8])
        cams[cid] = (K, dist, w, h)
    imgs = []
    lines = [l for l in open(os.path.join(d, "images.txt")) if not l.startswith("#")]
    for k in range(0, len(lines) - 1, 2):
        p = lines[k].split()
        if len(p) < 10:
            continue
        q = np.array([float(v) for v in p[1:5]]); t = np.array([float(v) for v in p[5:8]])
        imgs.append({"name": p[9], "R": _qrot(q), "t": t, "cam": int(p[8])})
    imgs.sort(key=lambda r: r["name"])
    pts = []
    for ln in open(os.path.join(d, "points3D.txt")):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split(); pts.append([float(v) for v in p[1:7]] + [float(p[7])])
    return cams, imgs, np.array(pts)


def _qrot(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


# ----------------------------------------------------------------------------- 3. dense (CPU)
def scene_frame(imgs, pts):
    """Up axis, orbit centre, floor plane and the object's box, from cameras + sparse points (arbitrary SfM scale)."""
    C = np.array([-im["R"].T @ im["t"] for im in imgs])
    up = -np.mean([im["R"][1] for im in imgs], axis=0); up /= np.linalg.norm(up)     # camera -Y = world up (handheld orbit)
    # orbit centre: point closest to all optical axes
    A = np.zeros((3, 3)); b = np.zeros(3)
    for im, c in zip(imgs, C):
        d = im["R"][2]; P = np.eye(3) - np.outer(d, d); A += P; b += P @ c
    ctr = np.linalg.lstsq(A, b, rcond=None)[0]
    X = pts[:, :3]
    # floor: RANSAC plane with normal near up
    rng = np.random.default_rng(0); best = (0, None)
    hz = X @ up
    Rorb = float(np.median(np.linalg.norm((C - ctr) - np.outer((C - ctr) @ up, up), axis=1)))
    tol = 0.006 * Rorb
    for _ in range(400):
        s = X[rng.choice(len(X), 3, replace=False)]
        n = np.cross(s[1] - s[0], s[2] - s[0]); nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn
        if abs(n @ up) < 0.9:
            continue
        inl = np.abs((X - s[0]) @ n) < tol
        if inl.sum() > best[0]:
            best = (inl.sum(), (n if n @ up > 0 else -n, s[0]))
    if best[1] is None:
        fn, fp = up, X[np.argmin(hz)]
    else:
        fn, fp = best[1]
        inl = np.abs((X - fp) @ fn) < tol
        # refine by least squares on inliers
        Q = X[inl]; m = Q.mean(0); _, _, vt = np.linalg.svd(Q - m); fn2 = vt[2] * np.sign(vt[2] @ fn); fn, fp = fn2, m
    up = fn
    h = (X - fp) @ up
    rad = X - ctr; rad = rad - np.outer(rad @ up, up); rd = np.linalg.norm(rad, axis=1)
    obj = (h > 0.01 * Rorb) & (rd < 0.45 * Rorb)
    if obj.sum() < 30:
        raise SystemExit("scan: could not find the object in the sparse cloud (%d points near the centre)" % obj.sum())
    # local frame: Y up, origin on the floor under the object
    ex = np.cross(up, [1, 0, 0]) if abs(up[0]) < 0.9 else np.cross(up, [0, 0, 1]); ex /= np.linalg.norm(ex)
    ez = np.cross(ex, up)
    Rw = np.stack([ex, up, ez])                                  # rows: local axes
    base = ctr - ((ctr - fp) @ up) * up
    L = (X[obj] - base) @ Rw.T
    lo = np.percentile(L, 1, axis=0); hi = np.percentile(L, 99, axis=0)
    pad = 0.12 * (hi - lo).max()
    lo -= pad; hi += pad; lo[1] = -0.02 * Rorb; hi[1] = max(hi[1], np.percentile(L[:, 1], 99.5) + pad)
    return {"Rw": Rw, "origin": base, "lo": lo, "hi": hi, "orbit_r": Rorb, "cams": C, "n_obj_pts": int(obj.sum()),
            "floor_inliers": int(best[0])}


def _pair_depth(img_i, img_j, K, dist, Ri, ti, Rj, tj, zrange):
    """SGBM between two views -> depth map in view i (undistorted pinhole K), NaN where unknown."""
    h, w = img_i.shape[:2]
    R = Rj @ Ri.T; T = tj - R @ ti                                  # x_j = R x_i + T
    R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(K.astype(np.float64), dist.reshape(1, -1).astype(np.float64), K.astype(np.float64), dist.reshape(1, -1).astype(np.float64), (w, h), R.astype(np.float64), T.reshape(3, 1).astype(np.float64), flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    m1 = cv2.initUndistortRectifyMap(K, dist, R1, P1, (w, h), cv2.CV_32FC1)
    m2 = cv2.initUndistortRectifyMap(K, dist, R2, P2, (w, h), cv2.CV_32FC1)
    a = cv2.remap(img_i, *m1, cv2.INTER_LINEAR); b = cv2.remap(img_j, *m2, cv2.INTER_LINEAR)
    vertical = abs(P2[1, 3]) > abs(P2[0, 3])
    if vertical:
        a, b = cv2.rotate(a, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(b, cv2.ROTATE_90_CLOCKWISE)
    f = P1[0, 0]; B = abs((P2[1, 3] if vertical else P2[0, 3]) / P2[0, 0])
    dmin = f * B / zrange[1]; dmax = f * B / zrange[0]
    sign = 1
    if (P2[1, 3] if vertical else P2[0, 3]) > 0:                    # second camera is on the left: mirror both views
        a, b = cv2.flip(a, 1), cv2.flip(b, 1); sign = -1
    mind = int(max(0, math.floor(dmin * 0.8))); nd = int(math.ceil((dmax * 1.2 - mind) / 16.0)) * 16
    nd = int(np.clip(nd, 16, 256))
    sg = cv2.StereoSGBM_create(minDisparity=mind, numDisparities=nd, blockSize=5, P1=8 * 3 * 25, P2=32 * 3 * 25,
                               uniquenessRatio=10, speckleWindowSize=100, speckleRange=2, disp12MaxDiff=1,
                               mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)
    ga, gb = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
    disp = sg.compute(ga, gb).astype(np.float32) / 16.0
    if sign < 0:
        disp = cv2.flip(disp, 1)
    if vertical:
        disp = cv2.rotate(disp, cv2.ROTATE_90_COUNTERCLOCKWISE)
    valid = disp > max(mind, 0.5)
    z = np.where(valid, f * B / np.maximum(disp, 1e-3), np.nan)
    # rectified pixel -> ray in rectified cam -> view i camera coordinates
    hh, ww = z.shape
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    cx, cy = P1[0, 2], P1[1, 2]
    Xr = np.stack([(xx - cx) / f * z, (yy - cy) / f * z, z], -1).reshape(-1, 3)
    ok = np.isfinite(Xr[:, 2])
    Xc = Xr[ok] @ R1                                                # R1^T applied to row vectors
    # project into the undistorted view i with K -> depth map
    u = (K[0, 0] * Xc[:, 0] / Xc[:, 2] + K[0, 2]).round().astype(int); v = (K[1, 1] * Xc[:, 1] / Xc[:, 2] + K[1, 2]).round().astype(int)
    inb = (u >= 0) & (u < w) & (v >= 0) & (v < h) & (Xc[:, 2] > 0)
    D = np.full(h * w, np.inf, np.float32)
    np.minimum.at(D, v[inb] * w + u[inb], Xc[inb, 2].astype(np.float32))
    D[~np.isfinite(D)] = np.nan
    return D.reshape(h, w)


TEX_MIN = 3.0


def dense_mesh(work, txt, res=144, step=None, every=1, log_every=10):
    cams, imgs, pts = read_colmap_txt(txt)
    K, dist, w, h = cams[imgs[0]["cam"]]
    S = scene_frame(imgs, pts)
    n = len(imgs)
    C = S["cams"]
    # neighbour offset giving ~8 degrees baseline around the orbit centre
    ang = []
    ctr = S["origin"]
    for k in range(1, 6):
        a = []
        for i in range(n - k):
            u1, u2 = C[i] - ctr, C[i + k] - ctr
            a.append(math.degrees(math.acos(np.clip(u1 @ u2 / np.linalg.norm(u1) / np.linalg.norm(u2), -1, 1))))
        ang.append(np.median(a))
    k = int(np.argmin([abs(a - 8.0) for a in ang])) + 1 if step is None else step
    log("dense: %d views, neighbour step %d (~%.1f deg), object box %s (orbit radius %.2f SfM units)"
        % (n, k, ang[k - 1], np.round(S["hi"] - S["lo"], 2).tolist(), S["orbit_r"]))
    loaded = [cv2.cvtColor(cv2.imread(os.path.join(work, "images", im["name"])), cv2.COLOR_BGR2RGB) for im in imgs]
    # undistorted colour images for texturing the vertices
    newK = K.copy()
    und = [cv2.undistort(im, K, dist, None, newK) for im in loaded]
    # TSDF grid in local frame
    lo, hi = S["lo"], S["hi"]
    vs = float((hi - lo).max() / res)
    dims = np.ceil((hi - lo) / vs).astype(int) + 1
    g = np.stack(np.meshgrid(*[lo[a] + vs * np.arange(dims[a]) for a in range(3)], indexing="ij"), -1).reshape(-1, 3)
    Gw = g @ S["Rw"] + S["origin"]                                   # voxel centres in SfM world
    tsdf = np.ones(len(g), np.float32); wsum = np.zeros(len(g), np.float32); col = np.zeros((len(g), 3), np.float32)
    trunc = 3.0 * vs
    # depth range of the box from the cameras
    t0 = time.time(); used = 0; cover = []
    for i in range(0, n, every):
        j1, j2 = i + k, i - k
        nb = [j for j in (j1, j2) if 0 <= j < n] or [(i + k) % n]
        Ri, ti = imgs[i]["R"], imgs[i]["t"]
        Xc = Gw @ Ri.T + ti
        zr = (max(1e-3, np.percentile(Xc[:, 2], 0.5) * 0.9), np.percentile(Xc[:, 2], 99.5) * 1.1)
        Ds = [_pair_depth(loaded[i], loaded[j], K, dist, Ri, ti, imgs[j]["R"], imgs[j]["t"], zr) for j in nb]
        if len(Ds) == 2:
            a, b = Ds
            agree = np.abs(a - b) < 0.01 * np.nanmedian(a) + 1e-9
            D = np.where(agree, 0.5 * (a + b), np.nan)
        else:
            D = Ds[0]
        gi = cv2.cvtColor(und[i], cv2.COLOR_RGB2GRAY).astype(np.float32)
        sd = np.sqrt(np.maximum(cv2.blur(gi * gi, (7, 7)) - cv2.blur(gi, (7, 7)) ** 2, 0))
        D = np.where(sd > TEX_MIN, D, np.nan)                     # no depth on flat sky / walls (stereo guesses there)
        cover.append(float(np.isfinite(D).mean()))
        z = Xc[:, 2]
        u = (K[0, 0] * Xc[:, 0] / z + K[0, 2]).round().astype(int); v = (K[1, 1] * Xc[:, 1] / z + K[1, 2]).round().astype(int)
        inb = (z > 0) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        idx = np.nonzero(inb)[0]
        d = D[v[idx], u[idx]]
        ok = np.isfinite(d)
        idx, d = idx[ok], d[ok]
        sdf = d - z[idx]
        keep = sdf > -trunc
        idx, sdf = idx[keep], np.minimum(1.0, sdf[keep] / trunc)
        wn = wsum[idx] + 1
        tsdf[idx] = (tsdf[idx] * wsum[idx] + sdf) / wn
        c = und[i][v[idx], u[idx]].astype(np.float32)
        col[idx] = (col[idx] * wsum[idx, None] + c) / wn[:, None]
        wsum[idx] = wn; used += 1
        if used % log_every == 0:
            log("dense: fused %d/%d views (%.1fs)" % (used, (n + every - 1) // every, time.time() - t0))
    t_fuse = time.time() - t0
    T = tsdf.reshape(dims); Wt = wsum.reshape(dims)
    T[Wt < 2] = 1.0
    # floor cut: everything within ~1.5 voxels of the floor plane is 'outside'
    fl = int(math.ceil((0.0 - lo[1]) / vs + 1.5))
    T[:, :max(0, fl), :] = 1.0
    from skimage import measure
    if T.min() >= 0:
        raise SystemExit("scan: dense fusion found no surface (too few consistent depths)")
    verts, faces, _, _ = measure.marching_cubes(T, 0.0, spacing=(vs, vs, vs))
    verts += lo
    vi = np.clip(np.round((verts - lo) / vs).astype(int), 0, dims - 1)
    vcol = col.reshape(tuple(dims) + (3,))[vi[:, 0], vi[:, 1], vi[:, 2]]
    verts, faces, vcol = largest_component(verts, faces, vcol)
    # scale: SfM units are arbitrary -> report height in SfM units; callers can rescale with --height
    info = {"views": n, "neighbour_step": k, "voxel": vs, "grid": dims.tolist(), "fuse_s": round(t_fuse, 1),
            "depth_coverage_mean": round(float(np.mean(cover)), 3), "tris_raw": int(len(faces)),
            "height_sfm_units": float(verts[:, 1].max() - verts[:, 1].min()), "orbit_radius_sfm": S["orbit_r"],
            "floor_inliers": S["floor_inliers"], "object_sparse_points": S["n_obj_pts"]}
    return verts, faces, vcol, info, S


def largest_component(V, F, Cc=None):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(V)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    nc, lab = connected_components(g, directed=False)
    if nc <= 1:
        return V, F, Cc
    fl = lab[F[:, 0]]; big = np.bincount(fl).argmax()
    F = F[fl == big]
    used = np.unique(F); remap = -np.ones(n, int); remap[used] = np.arange(len(used))
    return V[used], remap[F], (Cc[used] if Cc is not None else None)


# ----------------------------------------------------------------------------- 4. LODs + IO
def decimate(V, F, C, target, prefer="auto"):
    """Quadric decimation: fast-simplification (pip wheel), else open3d, else Blender (SFS_BPY_PYTHON / blender),
    else our numpy vertex clustering."""
    if len(F) <= target:
        return V, F, C, "none"
    if prefer in ("auto", "fast"):
        try:
            import fast_simplification as fs
            V2, F2 = fs.simplify(np.ascontiguousarray(V, np.float32), np.ascontiguousarray(F, np.int32),
                                 target_reduction=float(1.0 - target / float(len(F))))
            V2 = np.asarray(V2, float); F2 = np.asarray(F2, np.int64)
            C2 = None
            if C is not None:
                try:
                    from scipy.spatial import cKDTree
                    C2 = np.asarray(C, float)[cKDTree(V).query(V2)[1]]
                except ImportError:
                    C2 = None
            if len(F2):
                return V2, F2, C2, "fast-simplification-quadric"
        except ImportError:
            pass
    if prefer in ("auto", "open3d"):
        try:
            import open3d as o3d
            m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(V), o3d.utility.Vector3iVector(F))
            if C is not None:
                m.vertex_colors = o3d.utility.Vector3dVector(np.clip(C / 255.0, 0, 1))
            m = m.simplify_quadric_decimation(int(target))
            return np.asarray(m.vertices), np.asarray(m.triangles), (np.asarray(m.vertex_colors) * 255 if C is not None else None), "open3d-quadric"
        except ImportError:
            pass
    bl_exe = os.environ.get("SFS_BLENDER") or shutil.which("blender")
    bpy_py = os.environ.get("SFS_BPY_PYTHON") or (bl_exe and "blender")
    if prefer in ("auto", "blender") and bpy_py:
        import tempfile
        td = tempfile.mkdtemp(prefix="sfs_dec_")
        a, b = os.path.join(td, "in.ply"), os.path.join(td, "out.ply")
        write_ply(a, V, F, C)
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "blender_decimate.py")
        cmd = ([bpy_py, script, a, b, str(int(target))] if bpy_py != "blender" else [bl_exe, "-b", "-P", script, "--", a, b, str(int(target))])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(b):
            V2, F2, C2 = read_mesh(b)
            shutil.rmtree(td, ignore_errors=True)
            return V2, F2, (C2 if C2 is not None else None), "blender-collapse"
    return cluster_decimate(V, F, C, target) + ("vertex-clustering",)


def cluster_decimate(V, F, C, target):
    lo, hi = V.min(0), V.max(0); ext = (hi - lo).max()
    cell = ext / 8.0
    for _ in range(40):
        q = np.floor((V - lo) / cell).astype(np.int64)
        key = q[:, 0] * 1000003 + q[:, 1] * 1009 + q[:, 2]
        uk, inv = np.unique(key, return_inverse=True)
        F2 = inv[F]
        good = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
        if good.sum() > target:
            cell *= 1.12
            continue
        if good.sum() < 0.6 * target and cell > ext / 400:
            cell /= 1.06
            continue
        break
    cnt = np.bincount(inv).astype(float)
    V2 = np.stack([np.bincount(inv, V[:, a]) / cnt for a in range(3)], 1)
    C2 = np.stack([np.bincount(inv, C[:, a]) / cnt for a in range(3)], 1) if C is not None else None
    F2 = np.unique(np.sort(F2[good], 1), axis=0, return_index=True)[1]
    F2 = inv[F][good][np.sort(F2)]
    return V2, F2, C2


def read_mesh(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        V, F, C = [], [], []
        for ln in open(path, errors="ignore"):
            if ln.startswith("v "):
                p = ln.split(); V.append([float(x) for x in p[1:4]])
                if len(p) >= 7:
                    C.append([float(x) for x in p[4:7]])
            elif ln.startswith("f "):
                ids = [int(t.split("/")[0]) for t in ln.split()[1:]]
                ids = [i - 1 if i > 0 else len(V) + i for i in ids]
                for a in range(1, len(ids) - 1):
                    F.append([ids[0], ids[a], ids[a + 1]])
        Cn = np.array(C) if len(C) == len(V) and C else None
        if Cn is not None and Cn.max() <= 1.0:
            Cn = Cn * 255
        return np.array(V, float), np.array(F, int), Cn
    if ext == ".ply":
        return _read_ply(path)
    if ext in (".glb", ".gltf", ".fbx", ".stl", ".dae"):
        try:
            import trimesh
            m = trimesh.load(path, force="mesh")
            Cc = None
            try:
                Cc = np.asarray(m.visual.to_color().vertex_colors)[:, :3].astype(float)
            except Exception:
                pass
            return np.asarray(m.vertices, float), np.asarray(m.faces, int), Cc
        except ImportError:
            raise SystemExit("scan: reading %s needs 'pip install trimesh' (or convert to OBJ/PLY in Blender)" % ext)
    raise SystemExit("scan: unsupported mesh format %s (use obj/ply/glb)" % ext)


def _read_ply(path):
    with open(path, "rb") as f:
        hdr = []
        while True:
            ln = f.readline().decode("ascii", "ignore").strip(); hdr.append(ln)
            if ln == "end_header":
                break
        fmt = [l for l in hdr if l.startswith("format")][0].split()[1]
        elems, cur = [], None
        for l in hdr:
            p = l.split()
            if p and p[0] == "element":
                cur = [p[1], int(p[2]), []]; elems.append(cur)
            elif p and p[0] == "property":
                cur[2].append(p[1:])
        T = {"float": "f4", "float32": "f4", "double": "f8", "float64": "f8", "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
             "ushort": "u2", "uint16": "u2", "short": "i2", "int16": "i2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4"}
        V = F = Cc = None
        if fmt == "ascii":
            rest = f.read().decode().split("\n"); pos = 0
        for name, cnt, props in elems:
            if name == "vertex":
                names = [p[-1] for p in props]
                if fmt == "ascii":
                    arr = np.array([[float(x) for x in rest[pos + i].split()] for i in range(cnt)]); pos += cnt
                    col = {nm: arr[:, a] for a, nm in enumerate(names)}
                else:
                    dt = np.dtype([(p[-1], ("<" if "little" in fmt else ">") + T[p[0]]) for p in props])
                    arr = np.frombuffer(f.read(dt.itemsize * cnt), dt); col = {nm: arr[nm].astype(float) for nm in names}
                V = np.stack([col["x"], col["y"], col["z"]], 1)
                if "red" in col:
                    Cc = np.stack([col["red"], col["green"], col["blue"]], 1)
            elif name == "face":
                p = props[0]
                if fmt == "ascii":
                    rows = [[int(x) for x in rest[pos + i].split()] for i in range(cnt)]; pos += cnt
                else:
                    e = "<" if "little" in fmt else ">"
                    ct, it = np.dtype(e + T[p[1]]), np.dtype(e + T[p[2]])
                    data = f.read()
                    rows, off = [], 0
                    first = np.frombuffer(data, ct, 1, 0)[0]
                    if all(len(pp) == 4 for pp in props) and len(props) == 1:
                        stride = ct.itemsize + it.itemsize * int(first)
                        a = np.frombuffer(data[: stride * cnt], np.dtype([("n", ct), ("i", it, (int(first),))]))
                        if (a["n"] == first).all():
                            rows = a["i"].tolist()
                        else:
                            rows = None
                    if not rows:
                        rows, off = [], 0
                        for _ in range(cnt):
                            k = int(np.frombuffer(data, ct, 1, off)[0]); off += ct.itemsize
                            rows.append(np.frombuffer(data, it, k, off).tolist()); off += it.itemsize * k
                tris = []
                for r in rows:
                    ids = r[1:] if fmt == "ascii" else r
                    for a in range(1, len(ids) - 1):
                        tris.append([ids[0], ids[a], ids[a + 1]])
                F = np.array(tris, int)
            else:
                if fmt != "ascii":
                    break
        return V, F, Cc


def write_ply(path, V, F, C=None):
    with open(path, "wb") as f:
        hdr = "ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\n" % len(V)
        if C is not None:
            hdr += "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        hdr += "element face %d\nproperty uchar vertex_indices\nproperty int vertex_index\nend_header\n" % len(F)
        hdr = hdr.replace("property uchar vertex_indices\nproperty int vertex_index", "property list uchar int vertex_indices")
        f.write(hdr.encode())
        if C is not None:
            dt = np.dtype([("p", "<f4", 3), ("c", "u1", 3)]); a = np.zeros(len(V), dt); a["p"] = V; a["c"] = np.clip(C, 0, 255)
        else:
            a = V.astype("<f4")
        f.write(a.tobytes())
        fa = np.zeros(len(F), np.dtype([("n", "u1"), ("i", "<i4", 3)])); fa["n"] = 3; fa["i"] = F
        f.write(fa.tobytes())


def write_obj(path, V, F, C=None):
    with open(path, "w") as f:
        f.write("# Sprite Forge Studio scan mesh\n")
        for i, v in enumerate(V):
            if C is not None:
                c = np.clip(C[i] / 255.0, 0, 1); f.write("v %.5f %.5f %.5f %.4f %.4f %.4f\n" % (v[0], v[1], v[2], c[0], c[1], c[2]))
            else:
                f.write("v %.5f %.5f %.5f\n" % tuple(v))
        for t in F:
            f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))


def write_glb_mesh(path, V, F, C=None, name="Scan"):
    """Minimal static glTF 2.0 binary: one indexed mesh, POSITION/NORMAL(/COLOR_0)."""
    V = V.astype(np.float32); F = F.astype(np.uint32)
    N = np.zeros_like(V); fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for a in range(3):
        np.add.at(N, F[:, a], fn)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    chunks, views, accs = [], [], []

    def add(arr, target, comp, typ, mm=False):
        off = sum(len(c) for c in chunks); b = arr.tobytes(); b += b"\0" * ((4 - len(b) % 4) % 4); chunks.append(b)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes, "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if mm:
            acc["min"] = arr.min(0).tolist(); acc["max"] = arr.max(0).tolist()
        accs.append(acc); return len(accs) - 1
    attrs = {"POSITION": add(V, 34962, 5126, "VEC3", True), "NORMAL": add(N.astype(np.float32), 34962, 5126, "VEC3")}
    if C is not None:
        c = (np.clip(C, 0, 255) / 255.0).astype(np.float32) ** 2.2          # sRGB -> linear vertex colour
        attrs["COLOR_0"] = add(c, 34962, 5126, "VEC3")
    ind = add(F.reshape(-1), 34963, 5125, "SCALAR")
    js = {"asset": {"version": "2.0", "generator": "Sprite Forge Studio scan"}, "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0, "name": name}],
          "materials": [{"name": "scan", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.9}}],
          "meshes": [{"name": name, "primitives": [{"attributes": attrs, "indices": ind, "material": 0}]}],
          "buffers": [{"byteLength": sum(len(c) for c in chunks)}], "bufferViews": views, "accessors": accs}
    jb = json.dumps(js).encode(); jb += b" " * ((4 - len(jb) % 4) % 4); bb = b"".join(chunks)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(jb) + 8 + len(bb)))
        f.write(struct.pack("<II", len(jb), 0x4E4F534A)); f.write(jb)
        f.write(struct.pack("<II", len(bb), 0x004E4942)); f.write(bb)


def normalise(V, F, height=None, up="y"):
    """Put the mesh on the floor (min y = 0), centred in x/z; optional real-world height in metres."""
    if up == "z":
        V = V[:, [0, 2, 1]] * np.array([1, 1, -1])
    lo, hi = V.min(0), V.max(0)
    V = V - np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    if height:
        V = V * (float(height) / max(1e-9, hi[1] - lo[1]))
    return V


def render_views(V, F, C, size=260, yaws=(0, 90, 180, 270), title=""):
    """Tiny software renderer (painter's algorithm, flat Lambert x vertex colour) for preview sheets."""
    from PIL import Image, ImageDraw
    ims = []
    for yaw in yaws:
        a = math.radians(yaw); R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
        P = V @ R.T
        lo, hi = P.min(0), P.max(0); s = 0.86 * size / max(hi[0] - lo[0], hi[1] - lo[1], 1e-9)
        X = (P[:, 0] - (lo[0] + hi[0]) / 2) * s + size / 2; Y = size / 2 - (P[:, 1] - (lo[1] + hi[1]) / 2) * s
        tri = P[F]; n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        L = np.array([0.35, 0.6, 0.72]); L /= np.linalg.norm(L)
        shade = 0.3 + 0.7 * np.abs(n @ L)
        base = C[F].mean(1) if C is not None else np.full((len(F), 3), 190.0)
        rgb = np.clip(base * shade[:, None], 0, 255).astype(int)
        order = np.argsort(tri[:, :, 2].mean(1))                         # far (−z) first
        im = Image.new("RGB", (size, size), (52, 56, 66)); dr = ImageDraw.Draw(im)
        for t in order:
            i0, i1, i2 = F[t]
            dr.polygon([(X[i0], Y[i0]), (X[i1], Y[i1]), (X[i2], Y[i2])], fill=tuple(rgb[t]))
        ims.append(im)
    return ims


def sheet(rows, out, title):
    """rows: [(label, [PIL images])]"""
    from PIL import Image, ImageDraw
    cw = max(im.width for _, r in rows for im in r); ch = max(im.height for _, r in rows for im in r)
    ncol = max(len(r) for _, r in rows)
    W = 10 + ncol * (cw + 6); H = 34 + len(rows) * (ch + 22)
    S = Image.new("RGB", (W, H), (22, 24, 30)); d = ImageDraw.Draw(S)
    d.text((10, 8), title, fill=(235, 235, 235))
    y = 34
    for lab, r in rows:
        d.text((10, y), lab, fill=(150, 220, 160)); y += 16
        for c, im in enumerate(r):
            S.paste(im, (10 + c * (cw + 6), y))
        y += ch + 6
    S.save(out)


def console_budgets(spec=""):
    from .consoles import PRESETS
    b = {}
    for k, p in PRESETS.items():
        if p.get("tris"):
            b[k] = int(p["tris"])
    b["pc_hd"] = 100000
    if spec:
        b = {}
        for part in spec.split(","):
            k, v = part.split("="); b[k.strip()] = int(v)
    return b


def make_lods(V, F, C, budgets, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    rep = {}
    for key, tris in sorted(budgets.items(), key=lambda kv: -kv[1]):
        t0 = time.time()
        V2, F2, C2, how = decimate(V, F, C, tris)
        base = os.path.join(outdir, "%s_%s" % (name, key))
        write_glb_mesh(base + ".glb", V2, F2, C2, name=name); write_obj(base + ".obj", V2, F2, C2)
        rep[key] = {"budget": tris, "tris": int(len(F2)), "verts": int(len(V2)), "method": how, "s": round(time.time() - t0, 2),
                    "files": [os.path.basename(base) + ".glb", os.path.basename(base) + ".obj"]}
        log("LOD %-10s %6d tris (budget %d, %s)" % (key, len(F2), tris, how))
    return rep


# ----------------------------------------------------------------------------- CLI
def cli(argv, help_text=""):
    import argparse
    ap = argparse.ArgumentParser(prog="forge.py scan", description=help_text, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video"); ap.add_argument("--images", help="folder of photos instead of a video")
    ap.add_argument("--frames", type=int, default=80); ap.add_argument("--start", type=float); ap.add_argument("--end", type=float)
    ap.add_argument("--run", action="store_true"); ap.add_argument("--exhaustive", action="store_true")
    ap.add_argument("--sfm", choices=["pycolmap", "colmap"], help="SfM engine (default: pycolmap if installed, else colmap CLI)")
    ap.add_argument("--no-dense", dest="no_dense", action="store_true")
    ap.add_argument("--res", type=int, default=144, help="TSDF voxels along the longest side (default 144)")
    ap.add_argument("--mesh"); ap.add_argument("--up", default="y", choices=["y", "z"])
    ap.add_argument("--height", type=float, help="real height in metres (SfM scale is arbitrary)")
    ap.add_argument("--budgets", default=""); ap.add_argument("--name", default="scan"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    from .moves import slug
    name = slug(a.name); work = os.path.join(a.out, name + "_scan"); os.makedirs(work, exist_ok=True)
    rep = {"name": name, "tool": "forge.py scan", "not_one_click": True}
    T0 = time.time()
    if a.mesh:
        V, F, C = read_mesh(a.mesh)
        V = normalise(V, F, a.height, a.up)
        rep["source"] = {"mesh": os.path.abspath(a.mesh), "tris": int(len(F)), "verts": int(len(V))}
    else:
        if not (a.video or a.images):
            ap.error("give --video ORBIT.mp4, --images DIR or --mesh FILE")
        img_dir = os.path.join(work, "images")
        if a.video:
            shutil.rmtree(img_dir, ignore_errors=True)
            t0 = time.time(); ex = extract_frames(a.video, img_dir, a.frames, a.start, a.end); ex["s"] = round(time.time() - t0, 1)
            rep["extract"] = ex
            log("extract: %d frames decoded, %d picked (%d blurry) in %.1fs -> %s" % (ex["decoded"], len(ex["picked"]), ex["blurry_picks"], ex["s"], img_dir))
        else:
            shutil.rmtree(img_dir, ignore_errors=True); shutil.copytree(a.images, img_dir)
        write_project_scripts(work)
        if not a.run:
            log("project ready: %s  (run_colmap.sh/.bat, or drag images/ into Meshroom; then forge.py scan --mesh RESULT)" % work)
            json.dump(rep, open(os.path.join(work, "scan_report.json"), "w"), indent=1)
            return 0
        if a.sfm:
            os.environ["SFS_SFM"] = a.sfm
        txt, tcol = run_colmap(work, a.exhaustive)
        cams, imgs, pts = read_colmap_txt(txt)
        rep["colmap"] = {"s": tcol, "registered": len(imgs), "images": len(os.listdir(img_dir)), "points": int(len(pts)),
                         "mean_reproj_px": float(np.mean(pts[:, 6])) if len(pts) else None}
        log("colmap: %d/%d images registered, %d points, reprojection %.2f px"
            % (len(imgs), rep["colmap"]["images"], len(pts), rep["colmap"]["mean_reproj_px"] or -1))
        if a.no_dense:
            json.dump(rep, open(os.path.join(work, "scan_report.json"), "w"), indent=1)
            return 0
        t0 = time.time()
        V, F, C, info, S = dense_mesh(work, txt, res=a.res)
        info["s"] = round(time.time() - t0, 1); rep["dense"] = info
        log("dense: %d tris raw in %.1fs (depth coverage %.0f%%)" % (info["tris_raw"], info["s"], 100 * info["depth_coverage_mean"]))
        V = normalise(V, F, a.height)
        write_ply(os.path.join(work, name + "_raw.ply"), V, F, C)
    budgets = console_budgets(a.budgets)
    rep["lods"] = make_lods(V, F, C, budgets, os.path.join(work, "lods"), name)
    rows = [("source / raw  (%d tris)" % len(F), render_views(V, F, C))]
    for key in [k for k in ("pc_hd", "ps2gc", "ps1") if k in rep["lods"]] or list(rep["lods"])[:3]:
        V2, F2, C2 = read_mesh(os.path.join(work, "lods", "%s_%s.obj" % (name, key)))
        rows.append(("%s LOD: %d tris (budget %d)" % (key, len(F2), budgets[key]), render_views(V2, F2, C2)))
    sheet(rows, os.path.join(work, "scan_preview.png"), "forge.py scan: %s  (front / side / back / side)" % name)
    rep["total_s"] = round(time.time() - T0, 1)
    json.dump(rep, open(os.path.join(work, "scan_report.json"), "w"), indent=1, default=float)
    log("done in %.1fs -> %s (scan_preview.png, lods/, scan_report.json)" % (rep["total_s"], work))
    return 0
