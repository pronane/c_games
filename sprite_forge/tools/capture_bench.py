#!/usr/bin/env python3
"""What the turnaround videos teach the one-photo engine - priors + a measured benchmark (v11).

    python tools/capture_bench.py CAPTURES_DIR [--people mike,anna,...] [--write-priors] [--out bench/]

For every person with a finished video capture (CAPTURES_DIR/<name>/fit.pkl from `forge.py capture VIDEO`):
  1 priors      the depth sliders a front photo cannot see (torso / hip depth, belly, buttocks, bust, head depth),
                fitted on real people from all round: their mean, and a linear fit on weight when it explains them.
                --write-priors stores them in sforge/data/capture_priors.json (numbers only, no images).
  2 photo test  the most frontal frame of the video is used as if it were the only photo (leave-one-out: that
                person's own video is NOT in the priors used for them). Its body is then judged against every
                other frame of the video - views the photo never saw:
                    silhouette IoU at front / three-quarter / side / back
                for: the average MakeHuman body, the photo fit without priors, the photo fit with priors, and the
                video fit (the upper bound). Each gets its own best cameras (same solver for all, fair).
  3 texture     the back of the photo model rendered from the real back frames' cameras, colour dE vs the frame.
Writes OUT/BENCH.md + bench.json."""
from __future__ import annotations
import argparse
import json
import os
import pickle
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import capture_fit as CF, capture_photo as CP, capture_body as CB, capture_texture as CT, capture as CAP  # noqa: E402


def load_fit(d):
    return pickle.load(open(os.path.join(d, "fit.pkl"), "rb"))


def make_priors(fits):
    out = dict(mean={}, linear={}, n=len(fits))
    for k in CP.DEPTH:
        v = np.array([f["sl"].get(k, 0.0) for f in fits], float)
        out["mean"][k] = float(v.mean())
        out.setdefault("range", {})[k] = [float(v.min()), float(v.max())]   # never extrapolate past what was seen
        w = np.array([f["mac"]["weight"] for f in fits], float)
        if len(fits) >= 4 and np.std(w) > 0.05:
            A = np.c_[np.ones(len(w)), w]
            coef, res, *_ = np.linalg.lstsq(A, v, rcond=None)
            pred = A @ coef
            r2 = 1 - np.sum((v - pred) ** 2) / max(1e-9, np.sum((v - v.mean()) ** 2))
            if r2 > 0.5:
                out["linear"][k] = dict(a=float(coef[0]), b_weight=float(coef[1]), r2=float(r2))
    return out


def photo_dir_from_video(cap, work):
    """the most frontal usable frame of a video capture, as a one-photo capture"""
    tr = CF.load(cap)
    cands = CF.pick_frames(tr, 72)
    r = min(cands, key=lambda r: abs(((r["yaw"] + 180) % 360) - 180))
    os.makedirs(work, exist_ok=True)
    for sub in ("frames", "masks", "parts"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)
        ext = ".jpg" if sub == "frames" else ".png"
        shutil.copy(os.path.join(cap, sub, "%04d%s" % (r["i"], ext)), os.path.join(work, sub, "%04d%s" % (r["i"], ext)))
    t = dict(tr); t["frames"] = [r]
    json.dump(t, open(os.path.join(work, "track.json"), "w"))
    return work, r


def judge(cap, mac, sl, height, frames, log=print):
    """silhouette IoU of a body (mac, sl) over the video's frames, each with its own best camera"""
    f = CF.Fitter(cap, height_m=height, n_frames=24, log=lambda *a: None)
    f.mac, f.sl = dict(mac), dict(sl)
    f.frames = frames
    f.targets = [CF.Target(cap, r, f.scale) for r in frames]
    sh, P, Pg = f.posed()
    f.solve_cameras(Pg); f.refine_cameras(P, Pg)
    per = f.score(P, Pg, cams=False, detail=True)
    ids = [t.r for t in f.targets if t.r["i"] in f.cams.cam]
    return per, ids, f


def bucket(yaw):
    a = abs(((yaw + 180) % 360) - 180)
    return "front" if a < 25 else "3/4" if a < 65 else "side" if a < 115 else "back 3/4" if a < 155 else "back"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("captures"); ap.add_argument("--people"); ap.add_argument("--out", default="capture_bench")
    ap.add_argument("--write-priors", action="store_true")
    ap.add_argument("--height", type=float, default=1.75)
    a = ap.parse_args(argv)
    names = a.people.split(",") if a.people else sorted(n for n in os.listdir(a.captures)
                                                        if os.path.isfile(os.path.join(a.captures, n, "fit.pkl")))
    pool = sorted(n for n in os.listdir(a.captures) if os.path.isfile(os.path.join(a.captures, n, "fit.pkl")))
    fits = {n: load_fit(os.path.join(a.captures, n)) for n in pool}           # priors use every video capture
    for n in pool:
        try:
            rep = json.load(open(os.path.join(a.captures, n, "out", "report.json")))
            fits[n]["height"] = rep.get("height_m", a.height)
        except Exception:                                                    # noqa: BLE001
            fits[n]["height"] = a.height
    pri_all = make_priors(list(fits.values()))
    if a.write_priors:
        json.dump(pri_all, open(CP.PRIORS, "w"), indent=1)
        print("priors (%d people) -> %s" % (len(fits), CP.PRIORS))
    os.makedirs(a.out, exist_ok=True)
    results = {}
    for n in names:
        cap = os.path.join(a.captures, n)
        H = fits[n]["height"]
        loo = make_priors([fits[m] for m in pool if m != n]) if len(pool) > 2 else pri_all
        work, r0 = photo_dir_from_video(cap, os.path.join(a.out, "_photo_" + n))
        tr = CF.load(cap)
        frames = [r for r in CF.pick_frames(tr, 72) if r["i"] != r0["i"]]
        variants = {}
        variants["average body"] = (dict(gender=fits[n]["mac"]["gender"], age=0.5, muscle=0.5, weight=0.5, proportions=0.5),
                                    {k: 0.0 for k in CB.SLIDERS})
        # photo fit without priors
        json.dump(dict(mean={k: 0.0 for k in CP.DEPTH}, linear={}), open(os.path.join(a.out, "_zero.json"), "w"))
        old = CP.PRIORS
        CP.PRIORS = os.path.join(a.out, "_zero.json")
        pf = CP.PhotoFitter(work, height_m=H, log=lambda *x: None); pf.fit_photo()
        variants["photo, no priors"] = (pf.mac, pf.sl)
        json.dump(loo, open(os.path.join(a.out, "_loo.json"), "w"))
        CP.PRIORS = os.path.join(a.out, "_loo.json")
        pf2 = CP.PhotoFitter(work, height_m=H, log=lambda *x: None); pf2.fit_photo()
        variants["photo + video priors"] = (pf2.mac, pf2.sl)
        CP.PRIORS = old
        variants["video fit (upper bound)"] = (fits[n]["mac"], fits[n]["sl"])
        res = {}
        for vn, (mac, sl) in variants.items():
            per, ids, fj = judge(cap, mac, sl, H, frames)
            by = {}
            for v, r in zip(per, ids):
                by.setdefault(bucket(r["yaw"]), []).append(v)
            res[vn] = dict(mean=float(np.mean(per)), **{k: float(np.mean(v)) for k, v in by.items()})
            print("%-8s %-24s IoU %.3f  %s" % (n, vn, res[vn]["mean"], "  ".join("%s %.3f" % (k, np.mean(v)) for k, v in sorted(by.items()))))
        # texture of the photo model judged on the real back views
        tex, cov, _ = CT.bake(pf2, frames=pf2.frames, res=1024, power=2.0, min_facing=0.35, log=lambda *x: None)
        tex = CP.fill_unseen(pf2, tex, cov, 1024, log=lambda *x: None)
        per, ids, fj = judge(cap, pf2.mac, pf2.sl, H, frames)
        back = [r for r in ids if bucket(r["yaw"]) in ("back", "back 3/4", "side")]
        chk = CAP.evaluate(fj, back, tex, log=lambda *x: None)
        res["photo texture on unseen views"] = dict(dE=chk["dE"], ssim=chk["ssim"], frames=len(chk["frames"]))
        print("%-8s photo texture on side/back views: dE %.1f, SSIM %.2f (%d frames)" % (n, chk["dE"] or 0, chk["ssim"] or 0, len(chk["frames"])))
        results[n] = res
    json.dump(dict(priors=pri_all, results=results), open(os.path.join(a.out, "bench.json"), "w"), indent=1)
    L = ["# Capture benchmark: how well one photo predicts the views it never saw", "",
         "Silhouette IoU (1 = perfect) against the real video frames, by view.", ""]
    vs = ["average body", "photo, no priors", "photo + video priors", "video fit (upper bound)"]
    cols = ["mean", "front", "3/4", "side", "back 3/4", "back"]
    L += ["| person | body | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for n, res in results.items():
        for v in vs:
            L.append("| %s | %s | %s |" % (n, v, " | ".join("%.3f" % res[v][c] if c in res[v] else "-" for c in cols)))
    L += ["", "Mean over people:", ""]
    for v in vs:
        L.append("- %s: %.3f" % (v, np.mean([results[n][v]["mean"] for n in results])))
    L += ["", "Photo texture judged on side / back frames (colour dE, lower is better; SSIM, higher is better):", ""]
    for n, res in results.items():
        t = res["photo texture on unseen views"]
        L.append("- %s: dE %.1f, SSIM %.2f over %d frames" % (n, t["dE"] or 0, t["ssim"] or 0, t["frames"]))
    open(os.path.join(a.out, "BENCH.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
