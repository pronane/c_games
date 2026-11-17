#!/usr/bin/env python3
"""A key pose from a still picture (v11.12): photo / render of a player -> one pose on the shared skeleton.

    python tools/pose_from_image.py IMAGE [IMAGE ...] --out POSES.json [--sheet CHECK.png]

Runs the same MediaPipe pose model and the same solver as `forge.py motion record` (sforge/mocap.py) on each
picture. The bones' directions come from the picture (in-plane exactly, depth from the bone length and the
network's guess), the facing from the toes and nose. A jump is not visible in one still, so each pose comes with
the figure standing; give a lift when you build the move. --sheet draws each picture beside the solved pose (front
and side) so you can see it was read right before using it.

The pose file is {name: {"pose": {...}, "err_deg": median bone error, "facing": side|front|mp}}; tools/
build_gaelic_moves.py turns such key poses into moves."""
from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

LANDMARKS = r'''
import json, sys
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
from PIL import Image
model, out = sys.argv[1], sys.argv[2]
opts = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model),
                                    running_mode=vision.RunningMode.IMAGE, num_poses=1,
                                    min_pose_detection_confidence=0.3)
res = {}
with vision.PoseLandmarker.create_from_options(opts) as det:
    for f in sys.argv[3:]:
        im = np.asarray(Image.open(f).convert("RGB"))
        H, W = im.shape[:2]
        r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(im)))
        if not r.pose_landmarks:
            res[f] = None; continue
        res[f] = {"size": [W, H], "img": [[p.x * W, p.y * H, p.visibility] for p in r.pose_landmarks[0]],
                  "world": [[p.x, p.y, p.z] for p in r.pose_world_landmarks[0]]}
json.dump(res, open(out, "w"))
'''


def landmarks(images, model="heavy"):
    from sforge import mocap as M
    py, mp_ = M.find_pose_python(), M.find_model(model) or M.find_model("full")
    if not py or not mp_:
        raise RuntimeError("mediapipe and the pose model are needed: python tools/setup_pose.py")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        s = os.path.join(d, "lm.py"); o = os.path.join(d, "lm.json")
        open(s, "w").write(LANDMARKS)
        r = subprocess.run([py, s, mp_, o] + list(images), capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-1500:])
        return json.load(open(o))


def solve(lm, facing="auto"):
    """one picture's landmarks -> (pose dict, median bone error in degrees, facing used)"""
    from sforge import mocap as M
    img = np.array(lm["img"], float); P = M._to_rig(np.array(lm["world"], float))
    W = lm["size"][0]
    h = float(M.heading(P[None])[0])
    toe_dx = float(img[[M.TOE_L, M.TOE_R], 0].mean() - img[[M.HEEL_L, M.HEEL_R], 0].mean())
    nose_dx = float(img[M.NOSE, 0] - img[[M.EAR_L, M.EAR_R], 0].mean())
    if abs(toe_dx) > 0.01 * W:
        nose_dx = toe_dx
    mode = facing
    if facing == "auto":
        mode = "side" if (abs(abs(math.degrees(h)) - 90) < 40 or abs(nose_dx) > 0.02 * W) else "mp"
    if mode == "side":
        h = math.radians(90 if nose_dx >= 0 else -90)
    elif mode == "front":
        h = 0.0
    # metres per pixel: in one still the longest limb (relative to the rig) is the one most parallel to the picture
    L = M._rig_lengths(); ratios = []
    for k, (nm, (a, b), _, _) in enumerate(M.SEGS):
        if nm in ("pelvis", "shoulders", "head"):
            continue
        l2 = np.linalg.norm(M._pt_lm(img, b)[:2] - M._pt_lm(img, a)[:2])
        ratios.append(L[k] / max(1.0, l2))
    mpp = float(np.min(ratios))
    T = M.targets(P) if mode == "mp" else M.lifted_targets(img, P, h if mode in ("side", "front") else None, mpp)
    T = T @ M._rotY(-h).T
    x = np.zeros(len(M.PARAMS)); x[[18, 22]] = 10; x[[10, 14]] = 10
    x = M.solve_frame(T, x)
    x = M.solve_frame(T, x)
    pose = M.params_to_pose(x)
    pose = {k: (list(v) if isinstance(v, tuple) else v) for k, v in pose.items()}
    return pose, float(np.median(M.angle_err(T, x))), mode


def sheet(path, items):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    from sforge.rig import evaluate, PARENT
    fig, axs = plt.subplots(len(items), 3, figsize=(7.5, 2.6 * len(items)), squeeze=False)
    for r, (name, f, pose) in enumerate(items):
        axs[r, 0].imshow(Image.open(f).convert("RGB")); axs[r, 0].set_title(name, fontsize=8)
        s = evaluate(dict(pose))
        for v, a in enumerate(axs[r, 1:]):
            for b, par in PARENT.items():
                if par and b in s.world and par in s.world and b != "ball" and par != "root":
                    P, Q = s.world[b][:3, 3], s.world[par][:3, 3]
                    col = "r" if b.endswith("_L") else ("b" if b.endswith("_R") else "k")
                    if v == 0:
                        a.plot([-P[0], -Q[0]], [P[1], Q[1]], col, lw=2)       # front, as seen from the camera
                    else:
                        a.plot([P[2], Q[2]], [P[1], Q[1]], col, lw=2)         # side, facing right
            a.set_xlim(-1.1, 1.1); a.set_ylim(-0.1, 2.2); a.set_aspect("equal")
            a.set_title(("front" if v == 0 else "side (faces right)") + " - red = left", fontsize=7)
        for a in axs[r]:
            a.axis("off")
    plt.tight_layout(); plt.savefig(path, dpi=70)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet")
    ap.add_argument("--facing", default="auto", choices=["auto", "side", "front", "mp"])
    a = ap.parse_args(argv)
    lms = landmarks(a.images)
    out, items = {}, []
    for f in a.images:
        name = os.path.splitext(os.path.basename(f))[0]
        if not lms.get(f):
            print("%-20s no person found" % name); continue
        pose, err, mode = solve(lms[f], a.facing)
        out[name] = dict(pose=pose, err_deg=round(err, 1), facing=mode, image=os.path.basename(f))
        items.append((name, f, pose))
        print("%-20s %s, median bone error %.1f deg" % (name, mode, err))
    json.dump(out, open(a.out, "w"), indent=1)
    if a.sheet and items:
        sheet(a.sheet, items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
