#!/usr/bin/env python3
"""Train Sprite Forge's 2D -> 3D pose lifter (sforge/models/lifter_*.onnx).

Public 2D-to-3D lifters are trained on Human3.6M, which is licensed for research
only.  This one learns from real match 3D body pose instead - SkillCorner Open Data
body pose (MIT), the cache arena-fc/Tools/import_skillcorner_pose.py writes - seen
through random cameras: every training sample is a 9-frame window of real 3D joints,
projected orthographically from a random azimuth and a 3-35 degree elevation (a
touchline or Veo-style camera), with 2D noise, missing joints and mirroring.  It
predicts the centre frame's 3D pose (hips-centred, torso-normalised), so it reads
directly into sforge.jointtrack.

    python tools/train_lifter.py --cache DIR [--epochs 12] [--out sforge/models/lifter_v1.onnx]

DIR holds the *.pkl caches (one match is held out for validation).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import pickle
import sys
import time

import numpy as np

# 19 joints shared by RTMPose Halpe-26 (2D) and SkillCorner (3D)
JOINTS = ["nose", "lEar", "rEar", "lShoulder", "rShoulder", "lElbow", "rElbow", "lWrist", "rWrist",
          "lHip", "rHip", "lKnee", "rKnee", "lAnkle", "rAnkle", "lHeel", "rHeel", "lBigToe", "rBigToe"]
HALPE = [0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 24, 25, 20, 21]
MIRROR = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17]
WIN = 9
J = len(JOINTS)


def sequences(pkl):
    """runs of consecutive frames (T, 19, 3), rig axes (Y up), metres."""
    data = pickle.load(open(pkl, "rb"))
    out = []
    for frames in data.values():
        ks = sorted(frames)
        run = []
        for k in ks:
            j = frames[k]["j"]
            if not all(n in j for n in JOINTS):
                run = []; continue
            if run and k != run[-1][0] + 1:
                if len(run) >= WIN * 2: out.append(np.array([r[1] for r in run]))
                run = []
            p = np.array([j[n][0] for n in JOINTS], float)
            run.append((k, np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)))       # (x, y, z up) -> rig
        if len(run) >= WIN * 2:
            out.append(np.array([r[1] for r in run]))
    return out


def normalise3d(P):
    """centre on the hips, scale by the shoulder-to-hip distance (torso)."""
    hip = .5 * (P[..., 9, :] + P[..., 10, :])
    sh = .5 * (P[..., 3, :] + P[..., 4, :])
    s = np.linalg.norm(sh - hip, axis=-1)[..., None, None]
    return (P - hip[..., None, :]) / np.maximum(s, 1e-3)


def normalise2d(X):
    """window (W, J, 2): centre on the centre frame's hips, scale by its torso length in 2D."""
    c = WIN // 2
    hip = .5 * (X[c, 9] + X[c, 10]); sh = .5 * (X[c, 3] + X[c, 4])
    s = max(np.linalg.norm(sh - hip), 1e-3)
    return (X - hip) / s


def project(P, az, el):
    """orthographic camera: image x right, image y down."""
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    x = ca * P[..., 0] - sa * P[..., 2]
    zc = sa * P[..., 0] + ca * P[..., 2]
    y = ce * P[..., 1] - se * zc
    return np.stack([x, -y], -1)


def samples(seqs, n, rng, stride_choices=(1, 2)):
    Xs, Ys = [], []
    lens = np.array([len(s) for s in seqs], float)
    p = lens / lens.sum()
    for _ in range(n):
        s = seqs[rng.choice(len(seqs), p=p)]
        st = int(rng.choice(stride_choices))
        span = (WIN - 1) * st
        if len(s) <= span:
            continue
        i = rng.integers(0, len(s) - span)
        P = s[i:i + span + 1:st]
        if rng.random() < .5:
            P = P[:, MIRROR] * np.array([-1, 1, 1])
        az, el = rng.uniform(0, 2 * math.pi), math.radians(rng.uniform(3, 35))
        X = project(P, az, el)
        X = normalise2d(X)
        X = X + rng.normal(0, .045, X.shape)                     # ~2 cm on a 50 cm torso
        mask = (rng.random((WIN, J)) > .06).astype(float)
        X = X * mask[..., None]
        # target: centre frame in camera space (so the network needn't guess the azimuth)
        c = P[WIN // 2]
        ca, sa = math.cos(az), math.sin(az)
        cam = np.stack([ca * c[:, 0] - sa * c[:, 2], c[:, 1], sa * c[:, 0] + ca * c[:, 2]], 1)
        Y = normalise3d(cam)
        Xs.append(np.concatenate([X, mask[..., None]], -1).reshape(-1))
        Ys.append(Y.reshape(-1))
    return np.array(Xs, np.float32), np.array(Ys, np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--train-samples", type=int, default=300000)
    ap.add_argument("--hidden", type=int, default=768)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "sforge", "models", "lifter_v1.onnx"))
    a = ap.parse_args()
    import torch
    import torch.nn as nn
    torch.manual_seed(0)
    pk = sorted(glob.glob(os.path.join(a.cache, "*.pkl")))
    train_seq = [s for p in pk[:-1] for s in sequences(p)]
    val_seq = sequences(pk[-1])
    print("train runs %d (%d frames), val runs %d (%d frames)" % (
        len(train_seq), sum(map(len, train_seq)), len(val_seq), sum(map(len, val_seq))))
    rng = np.random.default_rng(0)
    Xtr, Ytr = samples(train_seq, a.train_samples, rng)
    Xva, Yva = samples(val_seq, 20000, np.random.default_rng(1))
    D, O = Xtr.shape[1], Ytr.shape[1]

    class Lifter(nn.Module):
        def __init__(self, h):
            super().__init__()
            self.inp = nn.Linear(D, h)
            self.blocks = nn.ModuleList([nn.Sequential(nn.LayerNorm(h), nn.Linear(h, h), nn.GELU(), nn.Dropout(.1), nn.Linear(h, h))
                                         for _ in range(3)])
            self.out = nn.Linear(h, O)

        def forward(self, x):
            z = self.inp(x)
            for b in self.blocks:
                z = z + b(z)
            return self.out(z)

    net = Lifter(a.hidden)
    opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, total_steps=a.epochs * (len(Xtr) // 512 + 1))
    Xt, Yt = torch.from_numpy(Xtr), torch.from_numpy(Ytr)
    Xv, Yv = torch.from_numpy(Xva), torch.from_numpy(Yva)
    torso_cm = 50.0

    def mpjpe(pred, y):
        return float(((pred - y).reshape(len(y), J, 3).norm(dim=-1).mean()) * torso_cm)

    for ep in range(a.epochs):
        net.train(); t0 = time.time()
        perm = torch.randperm(len(Xt))
        for i in range(0, len(Xt), 512):
            idx = perm[i:i + 512]
            loss = (net(Xt[idx]) - Yt[idx]).reshape(len(idx), J, 3).norm(dim=-1).mean()
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        net.eval()
        with torch.no_grad():
            print("epoch %2d  val MPJPE %.1f cm  (%.0fs)" % (ep + 1, mpjpe(net(Xv), Yv), time.time() - t0), flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    torch.onnx.export(net, torch.zeros(1, D), a.out, input_names=["x"], output_names=["y"],
                      dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)
    with torch.no_grad():
        val = mpjpe(net(Xv), Yv)
    meta = dict(joints=JOINTS, halpe_index=HALPE, window=WIN, input="window x joints x (x, y, mask); 2D centred on the centre frame's hips, / its 2D torso length",
                output="centre frame, camera space (x right, y up, z towards camera's right-handed depth), hips-centred, / 3D torso length",
                trained_on=[os.path.basename(p) for p in pk[:-1]], validated_on=os.path.basename(pk[-1]),
                val_mpjpe_cm=round(val, 1), epochs=a.epochs, hidden=a.hidden)
    with open(os.path.splitext(a.out)[0] + ".json", "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote", a.out, "val MPJPE %.1f cm" % val)
    return 0


if __name__ == "__main__":
    sys.exit(main())
