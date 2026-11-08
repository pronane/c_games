"""forge.py capture, step 3 - fit the MakeHuman body to a tracked turnaround (v11).

  shape    macro sliders (gender, muscle, weight, proportions) + modifier sliders (capture_body.SLIDERS)
  pose     upper arms / forearms / thighs / shins turned to the directions measured from the video (MediaPipe world
           landmarks expressed in the body's own frame and averaged over the orbit)
  cameras  one perspective camera per frame, solved with PnP from the body's joints to the frame's 2D landmarks
           (focal length from the frame size; refined once over all frames)
  fit      the posed body's silhouette against the person mask in ~24 frames spread round the orbit: mean IoU,
           with MediaPipe's hair label ignored (hair is not body). Powell search over the sliders, cameras re-solved
           for every shape, so the body, its joints and the cameras stay consistent.

Absolute size cannot be seen by one camera: the body is made `height_m` tall (default 1.75, or --height-cm).
Everything here is numpy + OpenCV + SciPy."""
from __future__ import annotations
import json
import math
import os
import numpy as np
from PIL import Image

from . import capture_body as CB
from .capture_track import (L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN, NOSE)

# landmark -> body joint (bone head) used for the cameras
LM_JOINT = {L_SH: "upperarm01.L", R_SH: "upperarm01.R", L_EL: "lowerarm01.L", R_EL: "lowerarm01.R",
            L_WR: "wrist.L", R_WR: "wrist.R", L_HIP: "upperleg01.L", R_HIP: "upperleg01.R",
            L_KN: "lowerleg01.L", R_KN: "lowerleg01.R", L_AN: "foot.L", R_AN: "foot.R"}
SWAP = {L_SH: R_SH, R_SH: L_SH, L_EL: R_EL, R_EL: L_EL, L_WR: R_WR, R_WR: L_WR, L_HIP: R_HIP, R_HIP: L_HIP,
        L_KN: R_KN, R_KN: L_KN, L_AN: R_AN, R_AN: L_AN}
POSE_BONES = {"upperarm01.L": (L_SH, L_EL), "lowerarm01.L": (L_EL, L_WR), "upperarm01.R": (R_SH, R_EL),
              "lowerarm01.R": (R_EL, R_WR), "upperleg01.L": (L_HIP, L_KN), "lowerleg01.L": (L_KN, L_AN),
              "upperleg01.R": (R_HIP, R_KN), "lowerleg01.R": (R_KN, R_AN)}


def load(cap_dir):
    d = json.load(open(os.path.join(cap_dir, "track.json")))
    d["dir"] = cap_dir
    return d


def body_frame(world):
    """rotation from MediaPipe world (x right, y down, z away) to the body frame (x = person's left, y up, z forward)"""
    W = np.asarray(world)
    x = (W[L_HIP] - W[R_HIP]) + 0.6 * (W[L_SH] - W[R_SH])
    up = np.array([0, -1.0, 0])
    x = x - up * np.dot(x, up); x /= np.linalg.norm(x) + 1e-9
    z = np.cross(x, up)                               # forward: facing the camera when x is +image-x
    return np.stack([x, up, z])                       # rows: body axes in world coords


def measure_pose(track, frames):
    """median bone directions (body frame) over the given frames"""
    acc = {b: [] for b in POSE_BONES}
    for r in frames:
        W = np.asarray(r["world"]); B = body_frame(W)
        for b, (i, j) in POSE_BONES.items():
            if min(r["lm"][i][2], r["lm"][j][2]) < 0.5:
                continue
            v = B @ (W[j] - W[i])
            acc[b].append(v / (np.linalg.norm(v) + 1e-9))
    out = {}
    for b, vs in acc.items():
        if len(vs) >= 3:
            m = np.median(np.array(vs), 0)
            if "leg" in b:
                # MediaPipe's depth for knees / ankles is the least reliable value it gives (it leans standing legs
                # back by 15-40 deg); a person standing for a turnaround has vertical legs seen from the side
                m[2] = 0.0
            out[b] = (m / np.linalg.norm(m)).tolist()
    return out


def cam_landmarks(r, lo=0.5, need=7):
    """landmarks used for a camera: the visible ones; from behind MediaPipe reports low visibility for everything,
    so the `need` most visible are used whatever their score"""
    idx = [i for i in LM_JOINT if r["lm"][i][2] > lo]
    if len(idx) < need:
        idx = sorted(LM_JOINT, key=lambda i: -r["lm"][i][2])[:need + 1]
    return idx


def pick_frames(track, n=24, tpose=False):
    def usable(r):
        """head to hips inside the frame (legs may be cut off: the silhouette is compared inside the frame only),
        and for standing frames the arms down (not on the way to / from the T-pose)"""
        w, h = r["size"]
        L = r["lm"]
        if not all(2 < L[i][0] < w - 2 and 2 < L[i][1] < h - 2 for i in (NOSE, L_HIP, R_HIP)):
            return False
        if not tpose:
            torso = abs((L[L_HIP][1] + L[R_HIP][1]) / 2 - (L[L_SH][1] + L[R_SH][1]) / 2) + 1e-6
            sh_y = (L[L_SH][1] + L[R_SH][1]) / 2
            if min(L[L_WR][1], L[R_WR][1]) < sh_y + 0.6 * torso:
                return False
        return True
    ok = [r for r in track["frames"] if r.get("ok") and bool(r.get("tpose")) == tpose and r["vis"] > 0.6 and usable(r)]
    if not ok:
        return []
    bins = {}
    for r in ok:
        b = int(((r["yaw"] + 180) % 360) // (360.0 / n))
        if b not in bins or r["vis"] > bins[b]["vis"]:
            bins[b] = r
    return [bins[k] for k in sorted(bins)]


class Cameras:
    """perspective camera per frame: K (focal f, centre), rvec, tvec (OpenCV: x right, y down, z forward)"""

    def __init__(self, focal_k=0.8):
        self.focal_k = focal_k
        self.cam = {}
        self.par = {}

    def K(self, size):
        w, h = size
        f = self.focal_k * max(w, h)
        return np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]])

    @staticmethod
    def rot(yaw, pitch, roll):
        """model -> camera rotation: yaw about the body's vertical, then camera pitch (looking down +) and roll"""
        y, p, q = math.radians(yaw), math.radians(pitch), math.radians(roll)
        Ry = np.array([[math.cos(y), 0.0, -math.sin(y)], [0.0, -1.0, 0.0], [-math.sin(y), 0.0, -math.cos(y)]])
        Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
        Rz = np.array([[math.cos(q), -math.sin(q), 0], [math.sin(q), math.cos(q), 0], [0, 0, 1]])
        return Rz @ Rx @ Ry

    def solve(self, r, joints3d, bm, yaw_tol=20.0):
        """camera = (yaw, pitch, roll, t): the yaw stays near the orbit's measured yaw (side views are where a free PnP
        swaps left and right), robust least squares on the visible joints"""
        import cv2
        from scipy.optimize import least_squares
        idx = cam_landmarks(r)
        if len(idx) < 6:
            return False
        X0 = np.array([joints3d[bm.bi[LM_JOINT[i]]] for i in idx], np.float64)
        Xs = np.array([joints3d[bm.bi[LM_JOINT[SWAP[i]]]] for i in idx], np.float64)
        x = np.array([r["lm"][i][:2] for i in idx], np.float64)
        K = self.K(r["size"])
        y0 = float(r["yaw"])
        prev0 = self.par.get(r["i"])
        best = None
        # seen from behind or the side MediaPipe sometimes labels the person's left as right: try both readings
        for X in ((X0, Xs) if abs(((y0 + 180) % 360) - 180) > 60 else (X0,)):
            sol = self._solve1(X, x, K, y0, prev0, yaw_tol)
            if best is None or sol.cost < best.cost:
                best = sol
        p = best.x
        if p[5] <= 0.3:
            return False
        R = self.rot(*p[:3])
        rv, _ = cv2.Rodrigues(R)
        self.par[r["i"]] = p
        self.cam[r["i"]] = (rv.reshape(3), p[3:6].copy())
        return True

    def _solve1(self, X, x, K, y0, prev, yaw_tol):
        from scipy.optimize import least_squares
        if prev is None:
            h_px = np.ptp(x[:, 1]) + 1e-6
            h_m = np.ptp(X[:, 1]) + 1e-6
            dist = K[0, 0] * h_m / h_px
            c = x.mean(0); cm = X.mean(0)
            prev = np.array([y0, 5.0, 0.0, (c[0] - K[0, 2]) * dist / K[0, 0], (c[1] - K[1, 2]) * dist / K[1, 1] + cm[1], dist])

        def res(p):
            R = self.rot(*p[:3]); Pc = X @ R.T + p[3:6]
            uv = Pc[:, :2] / np.maximum(Pc[:, 2:3], 1e-3) * K[0, 0] + K[:2, 2]
            sc = np.ptp(x[:, 1]) / 100.0                     # residuals in "percent of body height"
            return np.r_[((uv - x) / sc).ravel(), (p[0] - y0) / yaw_tol * 3, p[1] / 15.0, p[2] / 8.0]
        return least_squares(res, prev, loss="soft_l1", f_scale=2.0, max_nfev=60)

    def project(self, r, P):
        import cv2
        rv, tv = self.cam[r["i"]]
        uv, _ = cv2.projectPoints(np.asarray(P, np.float64), rv, tv, self.K(r["size"]), None)
        return uv.reshape(-1, 2)

    def reproj_error(self, r, joints3d, bm):
        if r["i"] not in self.cam:
            return float("nan")
        idx = cam_landmarks(r)
        X = np.array([joints3d[bm.bi[LM_JOINT[i]]] for i in idx])
        x = np.array([r["lm"][i][:2] for i in idx])
        return float(np.mean(np.linalg.norm(self.project(r, X) - x, axis=1)))


def raster(uv, F, size, scale):
    """silhouette at the working scale, pixel centres inside a triangle (the same rule as the masks' resampling;
    cv2.fillPoly is even-odd over overlapping triangles and fills partly-touched edge pixels - both bias a fit)"""
    from .render_sculpt import rasterise
    w, h = int(size[0] * scale), int(size[1] * scale)
    # a closed body's silhouette is the union of the triangles facing the camera: the others need not be drawn
    a = uv[F[:, 1]] - uv[F[:, 0]]; b = uv[F[:, 2]] - uv[F[:, 0]]
    cz = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    Fv = F[cz < 0] if (cz < 0).sum() > (cz > 0).sum() * 0.3 else F
    tid, _, _ = rasterise(uv[:, 0] * scale, uv[:, 1] * scale, np.zeros(len(uv)), Fv, w, h, K=8)
    return (tid.reshape(h, w) >= 0).astype(np.uint8)


class Target:
    """one frame's mask (person) and care-mask (not hair) at the working scale"""

    def __init__(self, cap_dir, r, scale):
        name = "%04d.png" % r["i"]
        m = np.asarray(Image.open(os.path.join(cap_dir, "masks", name))).astype(float) / 255.0
        p = np.asarray(Image.open(os.path.join(cap_dir, "parts", name)))
        w, h = int(r["size"][0] * scale), int(r["size"][1] * scale)
        self.mask = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)) > 127
        lab = lambda c: np.asarray(Image.fromarray((np.isin(p, c) * 255).astype(np.uint8)).resize((w, h), Image.NEAREST)) > 0
        hair = lab([1])
        self.care = ~hair
        self.clothes = lab([4, 5]) & self.mask
        self.r = r
        self.pose = "t" if r.get("tpose") else "s"


CLOTHES_SLACK = 0.3     # a missed clothes pixel costs this much: loose clothes may stand off the body


def iou(render, t, tight=False):
    """silhouette overlap, hair ignored. tight: the BODY under the clothes - its pixels outside the person and the
    person's skin pixels it misses cost fully, clothes pixels it does not reach cost only CLOTHES_SLACK (a jumper
    or a dress hangs away from the body; the clothes layer fills that later)"""
    a = render.astype(bool) & t.care; b = t.mask & t.care
    if not tight:
        u = (a | b).sum()
        return float((a & b).sum()) / u if u else 0.0
    tp = (a & b).sum(); fp = (a & ~b).sum()
    miss = b & ~a
    fn = (miss & ~t.clothes).sum() + CLOTHES_SLACK * (miss & t.clothes).sum()
    d = tp + fp + fn
    return float(tp) / d if d else 0.0


class Fitter:
    def __init__(self, cap_dir, height_m=1.75, n_frames=24, work_px=220, tight=True, use_tpose=True, log=print):
        self.dir = cap_dir; self.log = log
        self.track = load(cap_dir)
        self.bm = CB.BodyModel()
        self.height = height_m
        self.frames = pick_frames(self.track, n_frames)
        stand = pick_frames(self.track, 72)
        self.dirs = measure_pose(self.track, stand)
        tp = [r for r in self.track["frames"] if r.get("ok") and r.get("tpose")]
        self.dirs_t = measure_pose(self.track, tp) if len(tp) >= 3 else None
        if self.dirs_t and use_tpose:
            # the T-pose frames: arms out, so arm length and shoulder width show directly (by the sides they hide
            # against the torso) - up to 6 of them join the fit with the body posed in the measured T-pose
            self.frames += pick_frames(self.track, 6, tpose=True)
        self.tight = tight
        self.cams = Cameras()
        # working scale: the person ~work_px tall
        hs = []
        for r in self.frames:
            ys = [r["lm"][i][1] for i in (NOSE, L_AN, R_AN)]
            hs.append(max(ys) - min(ys))
        self.scale = min(1.0, work_px / (np.median(hs) * 1.15)) if hs else 0.5
        self.targets = [Target(cap_dir, r, self.scale) for r in self.frames]
        self.mac = dict(gender=0.5, age=0.5, muscle=0.5, weight=0.5, proportions=0.5)
        self.sl = {k: 0.0 for k in CB.SLIDERS}
        log("fit: %d frames round the orbit (%d T-pose), posed bones %s, working scale %.2f, %s" % (
            len(self.frames), sum(1 for r in self.frames if r.get("tpose")), ",".join(sorted(self.dirs)), self.scale,
            "body under the clothes" if tight else "dressed silhouette"))

    def posed(self, mac=None, sl=None, dirs=None):
        sh = self.bm.shape(mac or self.mac, sl or self.sl, self.height)
        P, Pg, S = sh.pose(dirs if dirs is not None else self.dirs)
        self._last_shape = sh
        return sh, P, Pg

    def _tposed(self):
        """the same body in the T-pose measured from the clip's T-pose frames (None without them)"""
        if not self.dirs_t or not any(t.pose == "t" for t in self.targets):
            return None, None
        P, Pg, _ = self._last_shape.pose(self.dirs_t)
        return P, Pg

    def solve_cameras(self, Pg, Pgt=None):
        bad = 0
        for r in self.frames:
            J = Pgt if (r.get("tpose") and Pgt is not None) else Pg
            if not self.cams.solve(r, J, self.bm):
                bad += 1
        return bad

    def score(self, P, Pg, cams=True, detail=False, tight=None):
        tight = getattr(self, "tight", False) if tight is None else tight
        Pt, Pgt = self._tposed()
        if cams:
            self.solve_cameras(Pg, Pgt)
        out = []
        for t in self.targets:
            if t.r["i"] not in self.cams.cam:
                continue
            Q = Pt if (t.pose == "t" and Pt is not None) else P
            uv = self.cams.project(t.r, Q)
            out.append(iou(raster(uv, self.bm.F, t.r["size"], self.scale), t, tight))
        return out if detail else float(np.mean(out)) if out else 0.0

    def refine_focal(self):
        """the phone's focal length is unknown: pick the one with the smallest landmark reprojection error"""
        sh, P, Pg = self.posed()
        best = None
        for k in (0.6, 0.7, 0.8, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.4):
            self.cams = Cameras(k)
            self.solve_cameras(Pg)
            e = np.nanmean([self.cams.reproj_error(r, Pg, self.bm) for r in self.frames if r["i"] in self.cams.cam])
            if best is None or e < best[0]:
                best = (e, k)
        self.cams = Cameras(best[1]); self.solve_cameras(Pg)
        self.log("fit: focal %.2f x frame size (joint reprojection %.1f px)" % (best[1], best[0]))
        return best

    def refine_cameras(self, P, Pg, evals=90, layers=None):
        """each camera nudged (yaw, pitch, roll, position) so the body's silhouette matches the frame's mask, with
        the joint landmarks as a soft anchor - joint positions of a template body and MediaPipe's landmarks differ
        by a few cm, the silhouette does not"""
        import cv2
        from scipy.optimize import minimize
        P0, Pg0 = P, Pg
        Pt, Pgt = self._tposed()
        Fm = self.bm.F if layers is None else layers[1]
        for t in self.targets:
            r = t.r
            if r["i"] not in self.cams.par:
                continue
            if t.pose == "t" and Pt is not None and layers is None:
                P, Pg = Pt, Pgt
            else:
                P, Pg = (P0, Pg0) if layers is None else (layers[0], Pg0)
            tight = getattr(self, "tight", False) and layers is None
            p0 = self.cams.par[r["i"]].copy()
            K = self.cams.K(r["size"])
            idx = cam_landmarks(r)
            X = np.array([Pg[self.bm.bi[LM_JOINT[i]]] for i in idx]); x = np.array([r["lm"][i][:2] for i in idx])
            hp = np.ptp(x[:, 1]) + 1e-6
            step = np.array([4.0, 3.0, 2.0, 0.03, 0.03, 0.08])

            def proj(p, Q):
                R = Cameras.rot(*p[:3]); Pc = Q @ R.T + p[3:6]
                return Pc[:, :2] / np.maximum(Pc[:, 2:3], 1e-3) * K[0, 0] + K[:2, 2]

            def f(z):
                p = p0 + z * step
                sil = iou(raster(proj(p, P), Fm, r["size"], self.scale), t, tight)
                lmk = float(np.mean(np.minimum(np.linalg.norm(proj(p, X) - x, axis=1) / hp, 0.15)))
                return (1 - sil) + 0.5 * lmk + 0.002 * float(np.sum(z * z))
            res = minimize(f, np.zeros(6), method="Powell", options=dict(maxfev=evals, xtol=0.05, ftol=1e-4))
            p = p0 + res.x * step
            if p[5] > 0.3:
                rv, _ = cv2.Rodrigues(Cameras.rot(*p[:3]))
                self.cams.par[r["i"]] = p
                self.cams.cam[r["i"]] = (rv.reshape(3), p[3:6].copy())

    def set_gender(self, g):
        """the body's sex is a choice the silhouette of clothed people cannot make reliably (a long jumper reads as
        either): fix it when known - 0 female, 1 male"""
        self.mac["gender"] = float(g); self.gender_fixed = True

    def coarse_start(self):
        """Powell from the average body stays near it: gender in particular sits in a valley (a man fitted from 0.5
        ended at 0.4). A coarse grid over gender x weight x muscle first, cameras re-solved for each, picks the
        starting body."""
        base = dict(self.mac)
        sh, P, Pg = self.posed(base, self.sl)
        self.solve_cameras(Pg)
        best = (self.score(P, Pg), base)                     # the starting body competes too
        for g in ((self.mac["gender"],) if getattr(self, "gender_fixed", False) else (0.0, 0.5, 1.0)):
            for w in (0.35, 0.6, 0.85):
                for mu in (0.3, 0.6):
                    mac = dict(base, gender=g, weight=w, muscle=mu)
                    sh, P, Pg = self.posed(mac, self.sl)
                    self.solve_cameras(Pg)                    # each body gets its own cameras (fair comparison)
                    v = self.score(P, Pg)
                    if best is None or v > best[0]:
                        best = (v, mac)
        self.mac = best[1]
        sh, P, Pg = self.posed(); self.solve_cameras(Pg)
        self.log("fit: coarse start gender %.1f weight %.2f muscle %.1f (IoU %.3f)" % (
            self.mac["gender"], self.mac["weight"], self.mac["muscle"], best[0]))

    def fit(self, iters=3, sliders=None, macros=("gender", "muscle", "weight", "proportions"), log_every=True):
        """alternate: cameras from the joints (PnP) and silhouettes, then the shape with the cameras held"""
        from scipy.optimize import minimize
        keys_m = list(macros)
        keys_s = list(sliders or CB.SLIDERS)
        lo = np.array([0.0] * len(keys_m) + [-1.0] * len(keys_s)); hi = np.array([1.0] * len(keys_m) + [1.0] * len(keys_s))
        n = [0]

        def unpack(x):
            x = np.clip(x, lo, hi)
            mac = dict(self.mac); mac.update(dict(zip(keys_m, x[:len(keys_m)])))
            sl = dict(self.sl); sl.update(dict(zip(keys_s, x[len(keys_m):])))
            return mac, sl

        def f(x):
            mac, sl = unpack(x)
            sh, P, Pg = self.posed(mac, sl)
            v = 1.0 - self.score(P, Pg, cams=False)
            # weak prior: stay near the average body unless the silhouettes say otherwise
            v += 0.003 * float(np.sum(x[len(keys_m):] ** 2)) + 0.003 * float(np.sum((x[:len(keys_m)] - 0.5) ** 2))
            n[0] += 1
            return v
        sh, P, Pg = self.posed()
        start = self.score(P, Pg)
        if getattr(self, "gender_fixed", False):
            keys_m = [k for k in keys_m if k != "gender"]
            lo = np.array([0.0] * len(keys_m) + [-1.0] * len(keys_s)); hi = np.array([1.0] * len(keys_m) + [1.0] * len(keys_s))
        self.coarse_start()
        for it in range(iters):
            sh, P, Pg = self.posed()
            if it:
                self.solve_cameras(Pg)
            self.refine_cameras(P, Pg)
            cam_iou = self.score(P, Pg, cams=False)
            x0 = np.array([self.mac[k] for k in keys_m] + [self.sl[k] for k in keys_s])
            res = minimize(f, x0, method="Powell", bounds=list(zip(lo, hi)),
                           options=dict(maxiter=1, xtol=0.02, ftol=1e-4))
            self.mac, self.sl = unpack(res.x)
            if log_every:
                self.log("fit: pass %d  IoU after cameras %.3f, after shape %.3f  (%d shape evaluations)" % (
                    it + 1, cam_iou, self.score(*self.posed()[1:], cams=False), n[0]))
        sh, P, Pg = self.posed()
        self.refine_cameras(P, Pg)
        per = self.score(P, Pg, cams=False, detail=True)
        return dict(iou_start=start, iou=float(np.mean(per)), iou_frames=per, evals=n[0], macros=self.mac, sliders=self.sl)

    def overlay(self, path, k=8):
        sh, P, Pg = self.posed()
        tiles = []
        for t in [t for t in self.targets if t.r["i"] in self.cams.cam][::max(1, len(self.targets) // k)][:k]:
            im = Image.open(os.path.join(self.dir, "frames", "%04d.jpg" % t.r["i"])).convert("RGB")
            w, h = im.size
            uv = self.cams.project(t.r, P)
            R = raster(uv, self.bm.F, (w, h), 1.0).astype(bool)
            a = np.asarray(im).astype(float)
            M = np.asarray(Image.open(os.path.join(self.dir, "masks", "%04d.png" % t.r["i"]))) > 127
            edge_r = R ^ _erode(R); edge_m = M ^ _erode(M)
            a[R] = a[R] * 0.6 + np.array([255, 120, 0]) * 0.4
            a[edge_m] = [0, 255, 255]; a[edge_r] = [255, 0, 0]
            tile = Image.fromarray(a.astype(np.uint8)); tile.thumbnail((240, 320)); tiles.append(tile)
        W = Image.new("RGB", (240 * len(tiles), 320), (0, 0, 0))
        for i, tl in enumerate(tiles):
            W.paste(tl, (i * 240, 0))
        W.save(path)
        return path


def _erode(m, n=2):
    from scipy import ndimage as ndi
    return ndi.binary_erosion(m, iterations=n)
