#!/usr/bin/env python3
"""Video-to-move self-test (v9.4): proves the capture -> retarget -> photo3d chain without a camera or a pose model.

    python tools/test_video_move.py OUT [--motion f3d_kick] [--photo cut/cutout.png --landmarks cut/landmarks.json]

A known motion is turned into exactly what tools/pose_track.py (MediaPipe PoseLandmarker) writes for a filmed clip:
33 image landmarks (px) + 33 world landmarks (metres, hips at the origin) per frame at 30 fps.  That track goes
through the real mocap solver (sforge.mocap.analyse -> keys -> library motion 'mocap_<name>'), and the recovered
motion is compared bone by bone with the original (degrees).  With --photo it is then rendered on the photo3d body,
the same way `forge.py build --mocap OUT/<name>.json --moves idle,<name>=mocap_<name>:8:14` uses a real capture.
Exit 1 when the mean bone error is above 12 degrees."""
from __future__ import annotations
import argparse, json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# MediaPipe Pose 33 -> (rig joint, offset in that joint's frame, metres)
LM = {0: ("head", (0, .10, .10)), 1: ("head", (.02, .13, .09)), 2: ("head", (.035, .13, .09)), 3: ("head", (.05, .13, .08)),
      4: ("head", (-.02, .13, .09)), 5: ("head", (-.035, .13, .09)), 6: ("head", (-.05, .13, .08)),
      7: ("head", (.08, .11, 0)), 8: ("head", (-.08, .11, 0)), 9: ("head", (.025, .06, .09)), 10: ("head", (-.025, .06, .09)),
      11: ("upperarm_L", (0, 0, 0)), 12: ("upperarm_R", (0, 0, 0)), 13: ("forearm_L", (0, 0, 0)), 14: ("forearm_R", (0, 0, 0)),
      15: ("hand_L", (0, 0, 0)), 16: ("hand_R", (0, 0, 0)), 17: ("hand_L", (.02, -.08, 0)), 18: ("hand_R", (-.02, -.08, 0)),
      19: ("hand_L", (0, -.09, .01)), 20: ("hand_R", (0, -.09, .01)), 21: ("hand_L", (-.02, -.05, .02)), 22: ("hand_R", (.02, -.05, .02)),
      23: ("thigh_L", (0, 0, 0)), 24: ("thigh_R", (0, 0, 0)), 25: ("shin_L", (0, 0, 0)), 26: ("shin_R", (0, 0, 0)),
      27: ("foot_L", (0, 0, 0)), 28: ("foot_R", (0, 0, 0)), 29: ("foot_L", (0, -.06, -.05)), 30: ("foot_R", (0, -.06, -.05)),
      31: ("foot_L", (0, -.07, .13)), 32: ("foot_R", (0, -.07, .13))}
BONES = [("upperarm_L", "forearm_L"), ("forearm_L", "hand_L"), ("upperarm_R", "forearm_R"), ("forearm_R", "hand_R"),
         ("thigh_L", "shin_L"), ("shin_L", "foot_L"), ("thigh_R", "shin_R"), ("shin_R", "foot_R")]


def synth_track(states, W=720, H=1280, px_per_m=520.0):
    """MediaPipe-style frames from rig states (front camera, orthographic)"""
    frames = []
    for st in states:
        pts = {}
        for i, (j, off) in LM.items():
            M = np.asarray(st.world[j]); pts[i] = (M @ np.array([*off, 1.0]))[:3]
        hip = (pts[23] + pts[24]) / 2
        world = [[float(p[0] - hip[0]), float(-(p[1] - hip[1])), float(-(p[2] - hip[2]))] for p in (pts[i] for i in range(33))]
        img = [[float(W / 2 + p[0] * px_per_m), float(H - 60 - p[1] * px_per_m), float(-p[2])] for p in (pts[i] for i in range(33))]
        frames.append({"img": img, "world": world})
    return {"fps": 30.0, "size": [W, H], "frames": frames}


def bone_dirs(st):
    out = []
    for a, b in BONES:
        d = np.asarray(st.world[b])[:3, 3] - np.asarray(st.world[a])[:3, 3]
        out.append(d / max(1e-9, np.linalg.norm(d)))
    return np.array(out)


def main(argv=None):
    from sforge import anim, mocap, motions, rig as RG
    try:
        from sforge import fightpack
        fightpack.register()
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--motion", default="f3d_kick"); ap.add_argument("--name", default="synth_kick")
    ap.add_argument("--photo"); ap.add_argument("--landmarks"); ap.add_argument("--yaw", type=float, default=35.0)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    mo = motions.find_motion(a.motion)
    if mo is None:
        raise SystemExit("unknown motion %s" % a.motion)
    N = 36
    src = anim.states_for(mo, N, False)
    track = synth_track(src)
    json.dump(track, open(os.path.join(a.out, a.name + "_pose.json"), "w"))
    keys, rep, dbg = mocap.analyse(track, a.name, False, 8, facing="mp", log=lambda *x: None)
    path = os.path.join(a.out, a.name + ".json")
    mocap.save_keys(path, "mocap_" + a.name, keys, False, rep)
    name = mocap.register(path)
    rec = anim.states_for(motions.LIB[name], N, False)
    # the solver trims the clip to its action span: compare on the same normalised time base
    span = rep["selection"].get("span", [0, N])
    s0, s1 = span[0], max(span[0] + 2, span[1] - 1)
    errs = []
    for i in range(N):
        t = (i - s0) / max(1e-6, s1 - s0)
        if 0 <= t <= 1:
            j = int(round(t * (N - 1)))
            d0, d1 = bone_dirs(src[i]), bone_dirs(rec[j])
            errs.append(np.degrees(np.arccos(np.clip((d0 * d1).sum(1), -1, 1))))
    errs = np.array(errs)
    res = {"motion": a.motion, "solver_mean_bone_err_deg": rep["mean_bone_err_deg"],
           "recovered_vs_original_mean_deg": round(float(errs.mean()), 1),
           "recovered_vs_original_p90_deg": round(float(np.percentile(errs, 90)), 1), "mocap_file": path}
    if a.photo:
        from PIL import Image
        from sforge import photo3d as P3
        from sforge.moves import MoveSpec
        lms = json.load(open(a.landmarks)); lms = lms["landmarks"] if isinstance(lms, dict) else lms
        body = P3.PhotoBody(Image.open(a.photo), lms, log=lambda *x: None)
        sts = P3.sample_states(motions.LIB[name], 8, False)
        ims = [body.render(s, yaw=a.yaw, cell=(420, 520), baseline=500, fig_px_per_m=330 / RG.HEIGHT) for s in sts]
        W = Image.new("RGBA", (420 * len(ims), 520), (205, 210, 216, 255))
        for k, im in enumerate(ims):
            W.alpha_composite(im, (420 * k, 0))
        W.convert("RGB").save(os.path.join(a.out, a.name + "_photo3d.png"))
        res["render"] = os.path.join(a.out, a.name + "_photo3d.png")
    json.dump(res, open(os.path.join(a.out, "video_move_report.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    return 1 if res["recovered_vs_original_mean_deg"] > 12 else 0


if __name__ == "__main__":
    sys.exit(main())
