"""VIDEO -> motion capture for the mannequin rig.

pipeline:  video --(tools/pose_track.py, MediaPipe PoseLandmarker, separate Python)--> 33 landmarks/frame
           -> left/right swap repair, gap fill, Savitzky-Golay smoothing
           -> per-frame IK fit of the rig's semantic channels (hips, chest, neck, arms, elbows, legs, knees)
              by least squares on bone DIRECTIONS (scale-free, so any body size works)
           -> jump height from the feet in the image, loop / action segment detection
           -> baked keyframes (mocap/<move>.json) registered as a library motion "mocap_<move>"
           -> the normal build: sprites (any console), GLB, FBX (built-in writer)

Honest limits (also in help "mocap"):
  * single camera: depth is guessed by the network; side-on clips confuse left/right limbs and arm/leg
    depth (we repair swaps, but cross-body arm motion may come out mirrored).
  * no finger, foot-roll or face capture; wrists/ankles stay neutral (feet auto-flatten on contact).
  * fast motion blur and loose clothing lower the accuracy; the network is trained on real people
    (it worked on the studio's own mannequin renders, see previews_v4/).
"""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np

from . import rig
from .motions import Motion, LIB

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# mediapipe landmark ids
NOSE, EAR_L, EAR_R = 0, 7, 8
SH_L, SH_R, EL_L, EL_R, WR_L, WR_R = 11, 12, 13, 14, 15, 16
HIP_L, HIP_R, KN_L, KN_R, AN_L, AN_R = 23, 24, 25, 26, 27, 28
HEEL_L, HEEL_R, TOE_L, TOE_R = 29, 30, 31, 32
LEFT = [7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31]
RIGHT = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]

PARAMS = [("hips", 0), ("hips", 1), ("hips", 2), ("chest", 0), ("chest", 1), ("chest", 2), ("neck", 0),
          ("arm_L", 0), ("arm_L", 1), ("arm_L", 2), ("elbow_L", None),
          ("arm_R", 0), ("arm_R", 1), ("arm_R", 2), ("elbow_R", None),
          ("leg_L", 0), ("leg_L", 1), ("leg_L", 2), ("knee_L", None),
          ("leg_R", 0), ("leg_R", 1), ("leg_R", 2), ("knee_R", None)]
LO = np.array([-60, -90, -45, -45, -60, -40, -40,  -80, -30, -80, 0,  -80, -30, -80, 0,  -70, -25, -50, 0,  -70, -25, -50, 0], float)
HI = np.array([80, 90, 45, 60, 60, 40, 50,  200, 170, 80, 155,  200, 170, 80, 155,  130, 70, 50, 160,  130, 70, 50, 160], float)
# soft prior (deg) towards 0 for channels a single camera can't see well
PRIOR_W = np.array([0.002, 0.004, 0.004, 0.004, 0.006, 0.004, 0.004,  0.0, 0.0, 0.006, 0.0,  0.0, 0.0, 0.006, 0.0,
                    0.0, 0.002, 0.006, 0.0,  0.0, 0.002, 0.006, 0.0], float)


# ------------------------------------------------------------------ pose tracking (subprocess)
def find_pose_python():
    """A Python that can import mediapipe: $SFS_POSE_PYTHON, the bundled venv, or this one."""
    cands = [os.environ.get("SFS_POSE_PYTHON", ""),
             os.path.join(HERE, "venv_pose", "Scripts", "python.exe"), os.path.join(HERE, "venv_pose", "bin", "python"),
             os.path.join(HERE, ".venv", "Scripts", "python.exe"), os.path.join(HERE, ".venv", "bin", "python"), sys.executable]
    for c in cands:
        if c and os.path.isfile(c):
            r = subprocess.run([c, "-c", "import mediapipe"], capture_output=True)
            if r.returncode == 0:
                return c
    return None


def find_model(name="full"):
    env = os.environ.get("SFS_POSE_MODEL", "")
    if env and os.path.isfile(env) and name in os.path.basename(env):
        return env
    for d in [os.path.join(HERE, "models"), os.environ.get("SFS_MODELS_DIR", "")]:
        p = os.path.join(d, "pose_landmarker_%s.task" % name)
        if os.path.isfile(p):
            return p
    return None


def track(video, out_json, model="full", start=None, end=None, log=print):
    py = find_pose_python()
    if py is None:
        raise RuntimeError("mediapipe is not installed for any Python found (it needs Python 3.9-3.12).\n"
                           "  Run:  python tools/setup_pose.py   (or setup.bat / setup.sh) - it makes venv_pose with Python 3.12,\n"
                           "  fetching that Python with uv if needed, and downloads the pose model.  Or set SFS_POSE_PYTHON.")
    mp = find_model(model)
    if mp is None:
        raise RuntimeError("pose model models/pose_landmarker_%s.task missing - run  python tools/setup_pose.py  or download it from\n"
                           "  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_%s/float16/latest/pose_landmarker_%s.task"
                           % (model, model, model))
    cmd = [py, os.path.join(HERE, "tools", "pose_track.py"), video, out_json, "--model", mp]
    if start is not None:
        cmd += ["--start", str(start)]
    if end is not None:
        cmd += ["--end", str(end)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    line = [x for x in r.stdout.splitlines() if x.startswith("pose:")]
    if r.returncode != 0 or not os.path.isfile(out_json):
        raise RuntimeError("pose tracking failed:\n" + (r.stderr[-1500:] or r.stdout[-1500:]))
    log("  " + (line[-1] if line else "pose tracked") + " (wall %.1fs incl. model load)" % (time.time() - t0))
    return json.load(open(out_json))


# ------------------------------------------------------------------ track clean-up
def _arrays(d):
    fr = d["frames"]; N = len(fr)
    img = np.full((N, 33, 3), np.nan); wld = np.full((N, 33, 3), np.nan)
    for i, o in enumerate(fr):
        if o:
            img[i] = o["img"]; wld[i] = o["world"]
    return img, wld


def repair_swaps(img, wld, ratio=0.5):
    """MediaPipe sometimes swaps the left/right labels on side-on views.  Viterbi over the two
    labellings per frame (legs and arms separately): cost = distance of knees/ankles (elbows/wrists)
    to their constant-velocity prediction, so legs that merely CROSS keep their labels."""
    N = len(img); swaps = 0
    groups = [([KN_L, AN_L, HEEL_L, TOE_L], [KN_R, AN_R, HEEL_R, TOE_R], [HIP_L, KN_L, AN_L, HEEL_L, TOE_L], [HIP_R, KN_R, AN_R, HEEL_R, TOE_R]),
              ([EL_L, WR_L], [EL_R, WR_R], [SH_L, EL_L, WR_L, 17, 19, 21], [SH_R, EL_R, WR_R, 18, 20, 22])]
    idx = [i for i in range(N) if not np.isnan(img[i, 0, 0])]
    if len(idx) < 4:
        return 0
    for gl, gr, swl, swr in groups:
        X = img[idx][:, gl + gr, :2]                 # (n, 2k, 2)
        k = len(gl)
        def lab(i, s):
            return X[i] if s == 0 else np.concatenate([X[i, k:], X[i, :k]])
        n = len(idx)
        # state = labelling of frame i (0 keep, 1 swap); 2nd-order handled by carrying the best previous
        cost = np.zeros((n, 2)); back = np.zeros((n, 2), int)
        cost[0, 1] = 1e-3
        for i in range(1, n):
            for s in (0, 1):
                best = None
                for sp in (0, 1):
                    cur = lab(i, s); prev = lab(i - 1, sp)
                    if i >= 2:
                        pp = lab(i - 2, back[i - 1, sp])
                        pred = prev + (prev - pp) * 0.7
                    else:
                        pred = prev
                    c = cost[i - 1, sp] + float(np.linalg.norm(cur - pred, axis=-1).sum()) + (0 if s == sp else 1e-3)
                    if best is None or c < best[0]:
                        best = (c, sp)
                cost[i, s], back[i, s] = best
        s = int(np.argmin(cost[-1])); path = [s]
        for i in range(n - 1, 0, -1):
            s = back[i, s]; path.append(s)
        path = path[::-1]
        # keep the majority labelling as "the network's" one
        if sum(path) > n / 2:
            path = [1 - p for p in path]
        for i, s in zip(idx, path):
            if s:
                for A in (img, wld):
                    A[i, swl + swr] = A[i, swr + swl]
                swaps += 1
    return swaps


SMOOTH_WIN = 7


def fill_and_smooth(A, win=None):
    win = SMOOTH_WIN if win is None else win
    """linear gap fill + Savitzky-Golay (keeps peaks of fast moves better than a moving average)."""
    from scipy.signal import savgol_filter
    N = len(A); t = np.arange(N); out = A.copy()
    ok = ~np.isnan(A[:, 0, 0])
    if ok.sum() < 2:
        raise RuntimeError("the pose network found a person in fewer than 2 frames")
    for j in range(A.shape[1]):
        for c in range(A.shape[2]):
            out[:, j, c] = np.interp(t, t[ok], A[ok, j, c])
    w = min(win, N - (1 - N % 2))
    if w >= 5:
        out = savgol_filter(out, w if w % 2 else w - 1, 2, axis=0)
    return out, ok


# ------------------------------------------------------------------ IK fit
def _to_rig(w):
    """mediapipe world (x right, y down, z away from camera) -> rig (Y up, right-handed)."""
    return np.stack([w[..., 0], -w[..., 1], -w[..., 2]], axis=-1)


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


def _rotY(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def heading(P):
    """facing angle about Y from the pelvis left vector (rig: X left, Z forward)."""
    L = P[..., HIP_L, :] - P[..., HIP_R, :] + 0.5 * (P[..., SH_L, :] - P[..., SH_R, :])
    F = np.stack([-L[..., 2], np.zeros(L.shape[:-1]), L[..., 0]], axis=-1)   # left x up = forward
    return np.arctan2(F[..., 0], F[..., 2])


SEGS = [  # (name, target from landmark ids, rig from joint names, weight)
    ("pelvis", (HIP_R, HIP_L), ("thigh_R", "thigh_L"), 1.0),
    ("trunk", ((HIP_L, HIP_R), (SH_L, SH_R)), (("thigh_L", "thigh_R"), ("upperarm_L", "upperarm_R")), 1.5),
    ("shoulders", (SH_R, SH_L), ("upperarm_R", "upperarm_L"), 0.8),
    ("head", ((SH_L, SH_R), (EAR_L, EAR_R)), (("upperarm_L", "upperarm_R"), "head"), 0.5),
    ("uarm_L", (SH_L, EL_L), ("upperarm_L", "forearm_L"), 1.0), ("farm_L", (EL_L, WR_L), ("forearm_L", "hand_L"), 0.8),
    ("uarm_R", (SH_R, EL_R), ("upperarm_R", "forearm_R"), 1.0), ("farm_R", (EL_R, WR_R), ("forearm_R", "hand_R"), 0.8),
    ("thigh_L", (HIP_L, KN_L), ("thigh_L", "shin_L"), 1.2), ("shin_L", (KN_L, AN_L), ("shin_L", "foot_L"), 1.2),
    ("thigh_R", (HIP_R, KN_R), ("thigh_R", "shin_R"), 1.2), ("shin_R", (KN_R, AN_R), ("shin_R", "foot_R"), 1.2),
]


def _pt_lm(P, k):
    return P[list(k)].mean(axis=0) if isinstance(k, tuple) else P[k]


def _pt_rig(W, k):
    if isinstance(k, tuple):
        return np.mean([W[x][:3, 3] for x in k], axis=0)
    return W[k][:3, 3]


def targets(P):
    return np.array([_unit(_pt_lm(P, b) - _pt_lm(P, a)) for _, (a, b), _, _ in SEGS])


def params_to_pose(x):
    pose = {"flat": 1.0}
    for (k, c), v in zip(PARAMS, x):
        if c is None:
            pose[k] = float(v)
        else:
            t = list(pose.get(k, (0.0, 0.0, 0.0))); t[c] = float(v); pose[k] = tuple(t)
    sp = pose.get("chest", (0, 0, 0))
    pose["spine"] = tuple(0.4 * v for v in sp); pose["chest"] = tuple(0.6 * v for v in sp)
    pose["neck"] = (pose["neck"][0], 0.0, 0.0)
    return pose


def _fk(pose):
    R = rig.local_rotations(pose)
    return rig._fk(R, np.zeros(3))


def rig_dirs(x):
    W = _fk(params_to_pose(x))
    return np.array([_unit(_pt_rig(W, b) - _pt_rig(W, a)) for _, _, (a, b), _ in SEGS])


SW = np.array([s[3] for s in SEGS])


def solve_frame(T, x0, prev=None, smooth_w=0.004):
    from scipy.optimize import least_squares

    def res(x):
        r = ((rig_dirs(x) - T) * SW[:, None]).ravel()
        reg = PRIOR_W * x
        if prev is not None:
            reg = np.concatenate([reg, smooth_w * (x - prev)])
        return np.concatenate([r, reg])
    sol = least_squares(res, np.clip(x0, LO + 1e-3, HI - 1e-3), bounds=(LO, HI), diff_step=1e-3, max_nfev=200, x_scale=30.0)
    return sol.x


def angle_err(T, x):
    D = rig_dirs(x)
    return np.degrees(np.arccos(np.clip((D * T).sum(axis=1), -1, 1)))


# ------------------------------------------------------------------ whole clip
RIG_LEN = None


def _rig_lengths():
    global RIG_LEN
    if RIG_LEN is None:
        W = _fk(params_to_pose(np.zeros(len(PARAMS))))
        RIG_LEN = np.array([np.linalg.norm(_pt_rig(W, b) - _pt_rig(W, a)) for _, _, (a, b), _ in SEGS])
    return RIG_LEN


DEPTH_GAIN = 0.4


def lifted_targets(img, P, facing, mpp):
    """bone directions in camera space: in-plane part from the IMAGE landmarks (accurate), depth
    magnitude from the rig's bone length (|z| = sqrt(L^2 - proj^2)), depth sign from the network's
    3D guess.  For a known side-on facing the pelvis / shoulder depth sign follows from the facing."""
    L = _rig_lengths()
    out = np.zeros((len(SEGS), 3))
    for k, (nm, (a, b), _, _) in enumerate(SEGS):
        pa, pb = _pt_lm(img, a), _pt_lm(img, b)
        dx, dy = (pb[0] - pa[0]) * mpp, -(pb[1] - pa[1]) * mpp
        proj = math.hypot(dx, dy)
        dz = math.sqrt(max(0.0, L[k] ** 2 - proj ** 2))
        zs = _pt_lm(P, b)[2] - _pt_lm(P, a)[2]
        if facing is not None and nm in ("pelvis", "shoulders"):
            # R -> L vector = person's left = up x forward = (Fz, 0, -Fx), forward = (sin h, 0, cos h)
            zs = -math.sin(facing)
        out[k] = (dx, dy, DEPTH_GAIN * dz * float(np.clip(zs / 0.05, -1.0, 1.0)))
    return _unit(out)


def analyse(d, move, loop, n_frames, facing="auto", log=print, period=None, swap_fix=False):
    """facing: auto (side-on if the network says roughly side-on), side, front, mp (raw network 3D)."""
    from .video import find_period, action_span, dist_matrix
    t0 = time.time()
    img, wld = _arrays(d)
    fps = float(d["fps"]); W, H = d["size"]
    swaps = repair_swaps(img, wld) if swap_fix else 0
    img_s, ok = fill_and_smooth(img); wld_s, _ = fill_and_smooth(wld)
    P = _to_rig(wld_s)                                         # (N,33,3) camera-aligned, Y up
    N = len(P)
    hd = heading(P)
    h = math.atan2(np.median(np.sin(hd)), np.median(np.cos(hd)))
    # which way along the image x does the person face?  nose ahead of the ears
    # toes ahead of the heels (robust, also for faceless figures), nose ahead of the ears as a tie-break
    toe_dx = float(np.median(img_s[:, [TOE_L, TOE_R], 0].mean(axis=1) - img_s[:, [HEEL_L, HEEL_R], 0].mean(axis=1)))
    nose_dx = float(np.median(img_s[:, NOSE, 0] - img_s[:, [EAR_L, EAR_R], 0].mean(axis=1)))
    if abs(toe_dx) > 0.01 * W:
        nose_dx = toe_dx
    mode = facing
    if facing == "auto":
        mode = "side" if (abs(abs(math.degrees(h)) - 90) < 40 or abs(nose_dx) > 0.02 * W) else "mp"
    if mode == "side":
        h = math.radians(90 if nose_dx >= 0 else -90)
    elif mode == "front":
        h = 0.0
    # metres per pixel from the limb lengths (90th percentile of the 2D lengths ~ limbs parallel to the image)
    L = _rig_lengths(); ratios = []
    for k, (nm, (a, b), _, _) in enumerate(SEGS):
        if nm in ("pelvis", "shoulders", "head"):
            continue
        l2 = np.linalg.norm(np.array([_pt_lm(img_s[i], b)[:2] - _pt_lm(img_s[i], a)[:2] for i in range(N)]), axis=1)
        ratios.append(L[k] / max(1.0, np.percentile(l2, 90)))
    mpp = float(np.median(ratios))
    facing_xz = h if mode in ("side", "front") else None
    R = _rotY(-h)
    Tall = []
    for i in range(N):
        if mode == "mp":
            T = targets(P[i])
        else:
            T = lifted_targets(img_s[i], P[i], facing_xz, mpp)
        Tall.append(T @ R.T)
    xs = np.zeros((N, len(PARAMS))); errs = np.zeros((N, len(SEGS)))
    x = np.zeros(len(PARAMS)); x[[18, 22]] = 10; x[[10, 14]] = 10
    for i in range(N):
        T = Tall[i]
        x = solve_frame(T, x, xs[i - 1] if i else None)
        xs[i] = x; errs[i] = angle_err(T, x)
    t_fit = time.time() - t0
    # ---- jump height from the feet in the image (metres via body height in px)
    feet = img_s[:, [AN_L, AN_R, HEEL_L, HEEL_R, TOE_L, TOE_R], 1].max(axis=1)          # lowest foot point (px)
    # trunk (hip -> shoulder) is ~0.47 m on the rig: gives metres per pixel
    m_per_px = mpp
    ground = np.percentile(feet, 90)
    lift = np.clip((ground - feet) * m_per_px, 0, None)
    lift[lift < 0.04] = 0.0
    # ---- segment selection on the joint-angle signal
    F = (xs - xs.mean(axis=0)) / max(1.0, float(xs.std()))
    Dm = dist_matrix(F.reshape(N, -1)) if N <= 600 else None
    sel = {}
    if loop:
        p, pin = find_period(Dm, fps, loco=False, override=period)
        if not p:
            p = float(N - 1); pin = {"note": "no repeat found - using the whole clip"}
        # best start: smallest seam error inside the clip
        pi = int(round(p)); best = (1e9, 0)
        for s in range(0, max(1, N - pi - 1)):
            e = float(np.abs(F[s] - F[min(N - 1, s + pi)]).mean())
            if e < best[0]:
                best = (e, s)
        s0 = best[1]; seg = (s0, s0 + p)
        sel = {"period_frames": float(p), "period_s": float(p / fps), "start": s0, "seam": best[0]}
    else:
        E = np.r_[0, np.abs(np.diff(xs, axis=0)).mean(axis=1)] + 50 * np.r_[0, np.abs(np.diff(lift))]
        a, b, info = action_span(E)
        seg = (a, max(a + 2, b - 1)); sel = {"span": [int(a), int(b)], "span_s": float((b - a) / fps)}
    # ---- bake keys over the segment at the source frame rate
    s0, s1 = seg
    ts = np.arange(int(math.floor(s0)), int(math.ceil(s1)) + 1)
    ts = ts[ts < N]
    keys = []
    for i in ts:
        pose = params_to_pose(xs[i]); pose["lift"] = float(lift[i])
        keys.append(((i - s0) / max(1e-6, s1 - s0), pose))
    rep = {"move": move, "facing": mode, "heading_deg": round(math.degrees(h), 1), "m_per_px": round(mpp, 5), "frames_tracked": int(ok.sum()), "frames": N, "fps": fps, "lr_swaps_fixed": int(swaps),
           "fit_s": round(t_fit, 2), "fit_fps": round(N / max(t_fit, 1e-6), 1),
           "mean_bone_err_deg": round(float(errs.mean()), 1),
           "bone_err_deg": {s[0]: round(float(errs[:, k].mean()), 1) for k, s in enumerate(SEGS)},
           "max_lift_m": round(float(lift.max()), 2), "selection": sel, "loop": bool(loop)}
    return keys, rep, dict(xs=xs, errs=errs, lift=lift, img=img_s)


def keys_motion(name, keys, loop, desc="motion capture"):
    """baked keys -> library Motion (linear in time between source frames; loops wrap)."""
    ts = np.array([k[0] for k in keys]); poses = [k[1] for k in keys]

    def lerp(p0, p1, a):
        out = {}
        for k in set(p0) | set(p1):
            v0, v1 = p0.get(k, 0), p1.get(k, 0)
            if isinstance(v0, (tuple, list)) or isinstance(v1, (tuple, list)):
                v0 = tuple(v0) if isinstance(v0, (tuple, list)) else (v0, 0, 0)
                v1 = tuple(v1) if isinstance(v1, (tuple, list)) else (v1, 0, 0)
                out[k] = tuple(a0 * (1 - a) + a1 * a for a0, a1 in zip(v0, v1))
            else:
                out[k] = float(v0) * (1 - a) + float(v1) * a
        return out

    def f(t):
        if loop:
            t = t % 1.0
        t = min(max(t, ts[0]), ts[-1])
        k = int(np.searchsorted(ts, t, side="right") - 1)
        k = min(max(k, 0), len(ts) - 2)
        a = (t - ts[k]) / max(1e-9, ts[k + 1] - ts[k])
        return lerp(poses[k], poses[k + 1], a)
    return Motion(name, func=f, loop=loop, desc=desc, category="Mocap")


def save_keys(path, name, keys, loop, rep):
    json.dump({"name": name, "loop": loop, "report": rep,
               "keys": [[t, {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}] for t, p in keys]},
              open(path, "w"), indent=0)


def load_keys(path):
    d = json.load(open(path))
    keys = [(t, {k: (tuple(v) if isinstance(v, list) else v) for k, v in p.items()}) for t, p in d["keys"]]
    return d["name"], keys, bool(d.get("loop"))


def register(path):
    """load a mocap/<move>.json and add it to the motion library as its name (e.g. mocap_run)."""
    name, keys, loop = load_keys(path)
    LIB[name] = keys_motion(name, keys, loop)
    return name


def overlay_sheet(d, dbg, rep, path, k=6):
    """source frames with the tracked skeleton (yellow = left, cyan = right) + the fitted rig render."""
    from PIL import Image, ImageDraw
    from . import render, mesh
    from .spec import CharacterSpec
    from .build import _font
    E = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
         (24, 26), (26, 28), (27, 31), (28, 32)]
    from . import media
    W, H = d["size"]
    fr = media.read_frames(d["video"], W, H)
    N = min(len(fr), len(dbg["xs"]))
    sel = rep["selection"]
    if "start" in sel:
        a, b = sel["start"], sel["start"] + sel["period_frames"]
    else:
        a, b = sel["span"]
    idx = np.linspace(a, min(N - 1, b), k).round().astype(int)
    spec = CharacterSpec(); T, B, M = mesh.build_mannequin(spec, False, None)
    cols = spec.colours()
    th = 300
    tiles = []
    for i in idx:
        im = Image.fromarray(fr[i]); dr = ImageDraw.Draw(im)
        p = dbg["img"][i]
        for u, v in E:
            dr.line([tuple(p[u][:2]), tuple(p[v][:2])], fill=(255, 230, 0) if u % 2 else (0, 230, 255), width=3)
        cx = int(np.median(p[:, 0])); cy = int(np.median(p[:, 1]))
        hh = int(1.25 * (p[:, 1].max() - p[:, 1].min())) + 20
        box = (cx - hh // 2, cy - hh // 2, cx + hh // 2, cy + hh // 2)
        crop = im.crop(box).resize((th, th))
        pose = params_to_pose(dbg["xs"][i]); pose["lift"] = float(dbg["lift"][i])
        st = rig.evaluate(pose)
        rs = render.RenderSettings(th, th, int(th * 0.7), int(th * 0.92), th // 2, yaw=90, pitch=0, ss=2, outline=True)
        rr = render.render_state(T, B, M, cols, st, rs)
        tile = Image.new("RGB", (th, 2 * th), (40, 44, 52))
        tile.paste(crop, (0, 0))
        bg = Image.new("RGBA", (th, th), (210, 214, 222, 255)); bg.alpha_composite(rr.convert("RGBA"))
        tile.paste(bg.convert("RGB"), (0, th))
        ImageDraw.Draw(tile).text((4, 4), "#%d  err %.0f deg" % (i, dbg["errs"][i].mean()), fill=(255, 255, 255), font=_font(13))
        tiles.append(tile)
    sheet = Image.new("RGB", (k * th, 2 * th + 26), (24, 26, 32))
    for n, t in enumerate(tiles):
        sheet.paste(t, (n * th, 26))
    ImageDraw.Draw(sheet).text((6, 5), "mocap %s  <- %s   tracked %d/%d   mean bone error %.1f deg   L/R swaps fixed %d   (top: MediaPipe landmarks, bottom: fitted mannequin, side view)"
                               % (rep["move"], os.path.basename(d["video"]), rep["frames_tracked"], rep["frames"],
                                  rep["mean_bone_err_deg"], rep["lr_swaps_fixed"]), fill=(230, 230, 230), font=_font(14))
    sheet.save(path)
    return path
