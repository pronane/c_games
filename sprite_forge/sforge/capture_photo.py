"""forge.py capture PHOTO - one photo -> a rigged, textured 3D character (v11).

A front photo shows widths and lengths but no depth and no back. What the turnaround videos taught (see
sforge/data/capture_priors.json and tools/capture_bench.py):
  shape    widths, lengths and the macros (gender, muscle, weight, proportions) are fitted to the photo's
           silhouette; the depth sliders (torso / hip depth, belly, buttocks, head depth) are not visible from the
           front, so they come from the priors: their values fitted on real people from all round, as a linear
           function of the visible ones (weight, muscle) where that held up, else their mean
  texture  the front from the photo; the back and sides the photo cannot see are painted from the front's colour at
           the same height and side, low-passed (a shirt's back is the shirt's colour, not its buttons); the back
           of the head takes the hair colour when the photo shows hair, the skin colour when it shows none
"""
from __future__ import annotations
import json
import os
import numpy as np
from PIL import Image

from . import capture_fit as CF, capture_body as CB, capture_texture as CT

HERE = os.path.dirname(os.path.abspath(__file__))
PRIORS = os.path.join(HERE, "data", "capture_priors.json")
DEPTH = ("torso_depth", "hip_depth", "belly", "buttocks", "head_depth", "bust")
FRONT = [k for k in CB.SLIDERS if k not in DEPTH]


def priors():
    if os.path.isfile(PRIORS):
        return json.load(open(PRIORS))
    return dict(mean={k: 0.0 for k in DEPTH}, linear={})


def depth_from_priors(mac, pri=None):
    pri = pri or priors()
    out = {}
    for k in DEPTH:
        v = pri["mean"].get(k, 0.0)
        lin = pri.get("linear", {}).get(k)
        if lin:                                   # v = a + b_weight * weight + b_muscle * muscle
            v = lin["a"] + sum(lin.get("b_" + m, 0.0) * float(mac.get(m, 0.5)) for m in ("weight", "muscle", "gender"))
        lo, hi = pri.get("range", {}).get(k, (-1.0, 1.0))
        out[k] = float(np.clip(v, max(-1.0, lo), min(1.0, hi)))
    return out


class PhotoFitter(CF.Fitter):
    def __init__(self, cap_dir, height_m=1.75, work_px=300, log=print):
        self.dir = cap_dir; self.log = log
        self.track = CF.load(cap_dir)
        self.bm = CB.BodyModel()
        self.height = height_m
        self.frames = [r for r in self.track["frames"] if r.get("ok")][:1]
        if not self.frames:
            raise SystemExit("capture: no person found in the photo")
        self.dirs = CF.measure_pose(self.track, self.frames * 3)
        self.dirs_t = None
        self.cams = CF.Cameras()
        r = self.frames[0]
        ys = [r["lm"][i][1] for i in (0, 27, 28)]
        self.scale = min(1.0, work_px / ((max(ys) - min(ys)) * 1.15))
        self.targets = [CF.Target(cap_dir, r, self.scale)]
        self.mac = dict(gender=0.5, age=0.5, muscle=0.5, weight=0.5, proportions=0.5)
        self.sl = {k: 0.0 for k in CB.SLIDERS}
        self.sl.update(depth_from_priors(self.mac))

    def fit_photo(self, iters=2):
        res = None
        for it in range(iters):
            res = self.fit(iters=1, sliders=FRONT, log_every=False)
            self.sl.update(depth_from_priors(self.mac))           # depth follows the fitted build
        self.log("photo fit: silhouette IoU %.3f (front only; depth from the priors)" % res["iou"])
        return res


def fill_unseen(fitter, tex, cov, res, log=print):
    """paint what the photo cannot see from the photo's colour at the same height / side, low-passed"""
    import cv2
    from scipy import ndimage as ndi
    bm = fitter.bm
    sh, P, Pg = fitter.posed()
    F = bm.F
    tid, bc = CT.texel_map(F, bm.fuv, res)
    inside = tid >= 0
    seen = cov > 1e-6 * (cov.max() + 1e-9)
    r = fitter.frames[0]
    img = np.asarray(Image.open(os.path.join(fitter.dir, "frames", "%04d.jpg" % r["i"])).convert("RGB"))
    parts = np.asarray(Image.open(os.path.join(fitter.dir, "parts", "%04d.png" % r["i"])))
    msk = np.asarray(Image.open(os.path.join(fitter.dir, "masks", "%04d.png" % r["i"]))) > 127
    # the photo low-passed inside the person (a big blur of the person only - background never bleeds in)
    m = ndi.binary_erosion(msk, iterations=3).astype(np.float32)
    k = max(15, int(0.07 * img.shape[0]) | 1)                   # strong: a back keeps colours, never letters
    num = cv2.GaussianBlur(img.astype(np.float32) * m[..., None], (k, k), 0)
    den = cv2.GaussianBlur(m, (k, k), 0)[..., None]
    low = num / np.maximum(den, 1e-3)
    hair = parts == 1
    hair_rgb = np.median(img[hair], 0) if hair.sum() > 200 else None
    skin = (parts == 2) | (parts == 3)
    skin_rgb = np.median(img[skin], 0) if skin.sum() > 200 else np.array([200, 160, 140])
    import cv2 as _c
    rv, tv = fitter.cams.cam[r["i"]]
    R, _ = _c.Rodrigues(rv); K = fitter.cams.K(r["size"])
    sel = inside & ~seen
    ti = tid[sel]; b = bc[sel]
    X = (b[:, :, None] * P[F[ti]]).sum(1)
    Xc = X @ R.T + tv
    u = Xc[:, 0] / Xc[:, 2] * K[0, 0] + K[0, 2]; v = Xc[:, 1] / Xc[:, 2] * K[1, 1] + K[1, 2]
    H, W = img.shape[:2]
    ui = np.clip(np.round(u).astype(int), 0, W - 1); vi = np.clip(np.round(v).astype(int), 0, H - 1)
    col = CT._bilinear(low, u - 0.5, v - 0.5)
    # a back is the garment's own colour: per label (clothes / skin / hair) the median colour of the person's pixels
    # in the same band of rows - a print or logo on the front is a minority of its band and drops out
    band = max(3, int(0.03 * H))
    pl = np.where(msk, parts, 0)
    for labv in (1, 2, 3, 4, 5):
        rows_med = np.full((H, 3), np.nan, np.float32)
        ys_, xs_ = np.nonzero(pl == labv)
        if len(ys_) < 50:
            continue
        for y in range(0, H, 2):
            sel_r = np.abs(ys_ - y) <= band
            if sel_r.sum() >= 12:
                rows_med[y:y + 2] = np.median(img[ys_[sel_r], xs_[sel_r]], 0)
        hit = (lab_all := parts[vi, ui]) == labv
        good = hit & ~np.isnan(rows_med[vi, 0])
        col[good] = rows_med[vi[good]]
    # head: the back of the head is hair where the photo shows hair on the head, else skin
    head_v = np.zeros(len(P), bool)
    hi = bm.bi.get("head")
    if hi is not None:
        head_v = (bm.J[:, 0] == hi) & (bm.W[:, 0] > 0.5)
    on_head = head_v[F[ti]].any(1)
    lab = parts[vi, ui]
    if hair_rgb is not None:
        col[on_head & (lab != 1)] = hair_rgb
    else:
        col[on_head & (lab == 3)] = skin_rgb
    # hands the photo hides (pockets, behind the back) are skin, not the pocket's colour
    hand_b = [bm.bi[b] for b in ("wrist.L", "wrist.R") if b in bm.bi]
    on_hand = np.isin(bm.J[:, 0], hand_b)[F[ti]].any(1)
    col[on_hand] = skin_rgb
    out = tex.astype(np.float32).copy()
    out[sel] = col
    # seen hand texels that are not skin-coloured in the photo (a hand in a pocket shows the pocket) -> skin
    sel_h = inside & seen
    hand_all = np.isin(bm.J[:, 0], hand_b)[F[np.maximum(tid, 0)]].any(-1) & sel_h
    if hand_all.any():
        d = np.linalg.norm(out[hand_all] - skin_rgb, axis=1)
        bad = d > 60
        idx = np.argwhere(hand_all)[bad]
        out[idx[:, 0], idx[:, 1]] = skin_rgb
    # soft seam between the photo's front and the painted back
    blend = ndi.gaussian_filter(seen.astype(np.float32), 4)
    sm = cv2.GaussianBlur(out, (0, 0), 3)
    edge = (blend > 0.05) & (blend < 0.95) & inside
    out[edge] = out[edge] * blend[edge][:, None] + sm[edge] * (1 - blend[edge][:, None])
    t8 = np.clip(out, 0, 255).astype(np.uint8)
    gut = (~inside).astype(np.uint8)
    t8 = cv2.inpaint(t8, gut, 3, cv2.INPAINT_TELEA)
    log("photo texture: %.0f%% of the body seen in the photo, the rest painted from it" % (100 * seen[inside].mean()))
    return t8


def run_photo(photo, name="captured", out_root="captures", height_m=1.75, tex_res=1024, cap_dir=None, gender=None, log=print):
    from . import capture_track as CTR, capture_export as CE, capture as CAP
    d = cap_dir or os.path.join(out_root, name)
    if cap_dir is None:
        CTR.track(photo, d, log=log)
    f = PhotoFitter(d, height_m=height_m, log=log)
    if gender is not None:
        f.set_gender(gender)
    res = f.fit_photo()
    tex, cov, st = CT.bake(f, frames=f.frames, res=tex_res, power=2.0, min_facing=0.35, log=log)
    tex = fill_unseen(f, tex, cov, tex_res, log=log)
    sh = f.bm.shape(f.mac, f.sl, height_m)
    Pst, _, _ = sh.pose(f.dirs)
    outd = os.path.join(d, "out")
    files = CE.export(sh, Pst, tex, outd, name, log=log, extras={"capture": dict(source="photo", macros=f.mac,
                                                                                       sliders=f.sl, height_m=height_m)})
    CAP.turntable(Pst, f.bm.F, f.bm.fuv, tex, os.path.join(outd, name + "_turntable.jpg"))
    rep = dict(name=name, photo=os.path.basename(photo) if photo else None, fit_iou=res["iou"],
               macros={k: float(v) for k, v in f.mac.items()}, sliders={k: float(v) for k, v in f.sl.items()},
               files={k: (os.path.basename(v) if isinstance(v, str) else None) for k, v in files.items() if k != "rig"})
    json.dump(rep, open(os.path.join(outd, "report.json"), "w"), indent=1)
    return f, tex, rep
