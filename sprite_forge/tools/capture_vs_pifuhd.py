#!/usr/bin/env python3
"""Sprite Forge's one-photo body vs PIFuHD (Saito et al., CVPR 2020) on the views the photo never saw (v11.1, optional).

    python tools/capture_vs_pifuhd.py CAPTURES_DIR BENCH_DIR PIFU_RECON_DIR [--people a,b] [--out DIR]

PIFuHD is Facebook Research's published single-image clothed-human reconstruction (github.com/facebookresearch/pifuhd,
an implicit-function network, 1.5 GB checkpoint). It is run on the SAME frontal photo `tools/capture_bench.py` gives
Sprite Forge (BENCH_DIR/_photo_NAME), e.g.
    python -m apps.simple_test -i PHOTOS -o OUT -r 256 --use_rect          (in the pifuhd checkout)
and its mesh (OUT/pifuhd_final/recon/result_NAME_256.obj) is then judged exactly like Sprite Forge's photo body:
silhouette IoU against every other frame of the person's turnaround video, by view (front / 3/4 / side / back).

Being generous to PIFuHD: its mesh (no scale, no orientation of its own) is scaled to the person's stature and aligned
to the video-fitted body (yaw, handedness, rigid ICP) - the true body, which the photo-only pipeline never gets. Both meshes then
get the same cameras: the video fit's per-frame cameras, each refined for that mesh on its own silhouette.
Writes OUT/PIFUHD.md + pifuhd.json."""
from __future__ import annotations
import argparse
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from sforge import capture_fit as CF, capture_photo as CP  # noqa: E402
import capture_bench as CBN  # noqa: E402


def load_obj(p):
    V, F = [], []
    for line in open(p):
        if line.startswith("v "):
            V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            F.append([int(x.split("/")[0]) - 1 for x in line.split()[1:4]])
    return np.array(V), np.array(F)


def largest_piece(V, F):
    """PIFuHD leaves floating blobs; its own apps/clean_mesh.py keeps the largest connected component - so do we"""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V), len(V)))
    _, lab = connected_components(g, directed=False)
    keep = lab == np.bincount(lab[F[:, 0]]).argmax()
    Fk = F[keep[F].all(1)]
    used = np.unique(Fk); remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
    return V[used], remap[Fk]


def align(Vp, P, height):
    """PIFuHD mesh -> the body's frame: its own Y is up (PIFuHD writes Y up), scaled to the person's stature, then a
    yaw (and handedness) search + rigid ICP onto the video-fitted body P"""
    from scipy.spatial import cKDTree
    from scipy.spatial.transform import Rotation
    V = Vp - Vp.mean(0)
    V = V * (height / np.ptp(V[:, 1]))
    rng = np.random.default_rng(0)
    A = V[rng.choice(len(V), min(4000, len(V)), replace=False)]
    B = P[rng.choice(len(P), min(4000, len(P)), replace=False)]
    tb = cKDTree(B); c = B.mean(0)
    best = None
    for mirror in (1, -1):
        for yaw in range(0, 360, 10):
            R = Rotation.from_euler("y", yaw, degrees=True).as_matrix()
            X = (A * [mirror, 1, 1]) @ R.T
            X = X - X.mean(0) + c
            d = tb.query(X)[0].mean() + cKDTree(X).query(B)[0].mean()
            if best is None or d < best[0]:
                best = (d, mirror, yaw)
    _, mi, yaw = best
    R = Rotation.from_euler("y", yaw, degrees=True).as_matrix()
    X = (V * [mi, 1, 1]) @ R.T
    X = X - X.mean(0) + c
    for _ in range(30):                                   # rigid ICP (the stature is the person's, fixed)
        S = X[rng.choice(len(X), min(4000, len(X)), replace=False)]
        T = B[tb.query(S)[1]]
        ms, mt = S.mean(0), T.mean(0)
        U, _, Wt = np.linalg.svd((S - ms).T @ (T - mt))
        Rk = (U @ Wt).T
        if np.linalg.det(Rk) < 0:
            Wt[-1] *= -1; Rk = (U @ Wt).T
        X = (X - ms) @ Rk.T + mt
    ch = float(tb.query(X[rng.choice(len(X), 4000, replace=False)])[0].mean())
    return X, dict(yaw=yaw, mirror=mi, chamfer_m=ch)


def judge_mesh(f, frames, X, F, evals=60):
    """IoU of a fixed mesh on each frame, camera started from the video fit's and refined for this mesh"""
    import cv2
    from scipy.optimize import minimize
    out = []
    for r in frames:
        if r["i"] not in f.cams.par:
            continue
        t = CF.Target(f.dir, r, f.scale)
        p0 = np.array(f.cams.par[r["i"]], float)

        def score(p):
            rv, _ = cv2.Rodrigues(CF.Cameras.rot(*p[:3]))
            f.cams.cam[r["i"]] = (rv.reshape(3), p[3:6])
            return -CF.iou(CF.raster(f.cams.project(r, X), F, r["size"], f.scale), t)
        res = minimize(score, p0, method="Powell", options=dict(maxfev=evals, xtol=1e-3, ftol=1e-4))
        v = -score(res.x if res.fun <= score(p0) else p0)
        out.append((r, v))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("captures"); ap.add_argument("bench"); ap.add_argument("pifu")
    ap.add_argument("--people"); ap.add_argument("--out", default="capture_pifuhd")
    a = ap.parse_args(argv)
    pool = sorted(n for n in os.listdir(a.captures) if os.path.isfile(os.path.join(a.captures, n, "fit.pkl")))
    names = a.people.split(",") if a.people else [n for n in pool if os.path.isfile(os.path.join(a.pifu, "result_%s_256.obj" % n))]
    fits = {n: CBN.load_fit(os.path.join(a.captures, n)) for n in pool}
    os.makedirs(a.out, exist_ok=True)
    res = {}
    for n in names:
        cap = os.path.join(a.captures, n)
        H = json.load(open(os.path.join(cap, "out", "report.json"))).get("height_m", 1.75)
        work = os.path.join(a.bench, "_photo_" + n)
        r0 = json.load(open(os.path.join(work, "track.json")))["frames"][0]
        frames = [r for r in CF.pick_frames(CF.load(cap), 72) if r["i"] != r0["i"]]
        # Sprite Forge, one photo + priors learnt from the OTHER people's videos (leave-one-out)
        loo = CBN.make_priors([fits[m] for m in pool if m != n])
        tmp = os.path.join(a.out, "_loo.json"); json.dump(loo, open(tmp, "w"))
        old = CP.PRIORS; CP.PRIORS = tmp
        pf = CP.PhotoFitter(work, height_m=H, log=lambda *x: None); pf.fit_photo()
        CP.PRIORS = old
        # cameras: the video fit's
        _, _, fv = CBN.judge(cap, fits[n]["mac"], fits[n]["sl"], H, frames)
        _, Pv, _ = fv.posed()
        sf = fv.bm.shape(pf.mac, pf.sl, H)
        Psf, _, _ = sf.pose(fv.dirs)
        Vp, Fp = largest_piece(*load_obj(os.path.join(a.pifu, "result_%s_256.obj" % n)))
        Xp, al = align(Vp, Pv, H)
        row = {}
        for label, X, F in (("Sprite Forge (1 photo)", Psf, fv.bm.F), ("PIFuHD (1 photo)", Xp, Fp),
                            ("Sprite Forge (video, reference)", Pv, fv.bm.F)):
            per = judge_mesh(fv, frames, X, F)
            by = {}
            for r, v in per:
                by.setdefault(CBN.bucket(r["yaw"]), []).append(v)
            row[label] = dict(mean=float(np.mean([v for _, v in per])), **{k: float(np.mean(v)) for k, v in by.items()})
            print("%-7s %-32s IoU %.3f  %s" % (n, label, row[label]["mean"],
                                                "  ".join("%s %.3f" % (k, np.mean(v)) for k, v in sorted(by.items()))), flush=True)
        row["pifuhd_alignment"] = al
        res[n] = row
    json.dump(res, open(os.path.join(a.out, "pifuhd.json"), "w"), indent=1)
    labels = ["Sprite Forge (1 photo)", "PIFuHD (1 photo)", "Sprite Forge (video, reference)"]
    cols = ["mean", "front", "3/4", "side", "back 3/4", "back"]
    L = ["# One photo -> 3D: Sprite Forge vs PIFuHD", "",
         "Silhouette IoU (1 = perfect) on the frames of each person's turnaround video that the photo never saw.", "",
         "| person | method | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for n, row in res.items():
        for lb in labels:
            L.append("| %s | %s | %s |" % (n, lb, " | ".join("%.3f" % row[lb][c] if c in row[lb] else "-" for c in cols)))
    L += ["", "Mean over people:", ""]
    for lb in labels:
        L.append("- %s: %.3f" % (lb, np.mean([res[n][lb]["mean"] for n in res])))
    open(os.path.join(a.out, "PIFUHD.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
