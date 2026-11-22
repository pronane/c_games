"""v11.22 3D joint tracks -> the shared skeleton.

Body-pose datasets (SkillCorner open body pose, OpenPose BODY_25 exports, multi-camera
markerless systems) give named 3D joint positions per frame rather than a rig.  This fits
them onto the shared skeleton with the same per-frame IK as `forge.py mocap`
(sforge/mocap.py: bone directions -> joint angles), so a clip from a dataset lands in the
motion library exactly like a recorded or imported one.

    keys, rep = fit_tracks(frames, fps=25, joint_names=SKILLCORNER, up="z")

`frames` is a list of {joint name: (x, y, z)} (missing joints allowed; missing frames
None).  Positions are metres; `up` names the vertical axis of the source.  The clip is
turned so the player faces forward at `face_frame` (default: the middle), like the
importer's canonical cut, and the root stays in place (the game supplies root motion).

Limits: single-person tracks only; no finger, twist or face channels; ankles come from
the heel -> toe line; precision is the source's (broadcast pose: 7-15 cm per joint).
"""
from __future__ import annotations

import math

import numpy as np

from . import mocap as MC

# Source joint name -> MediaPipe landmark slot the IK fit reads.
SKILLCORNER = {
    "nose": [0, 9, 10], "lEye": [1, 2, 3], "rEye": [4, 5, 6], "lEar": [7], "rEar": [8],
    "lShoulder": [11], "rShoulder": [12], "lElbow": [13], "rElbow": [14],
    "lWrist": [15], "rWrist": [16], "lPinky": [17], "rPinky": [18], "lThumb": [19, 21], "rThumb": [20, 22],
    "lHip": [23], "rHip": [24], "lKnee": [25], "rKnee": [26], "lAnkle": [27], "rAnkle": [28],
    "lHeel": [29], "rHeel": [30], "lBigToe": [31], "rBigToe": [32],
}
# OpenPose BODY_25 uses the same names in a different spelling.
BODY25 = {
    "Nose": [0, 9, 10], "LEye": [1, 2, 3], "REye": [4, 5, 6], "LEar": [7], "REar": [8],
    "LShoulder": [11], "RShoulder": [12], "LElbow": [13], "RElbow": [14], "LWrist": [15], "RWrist": [16],
    "LHip": [23], "RHip": [24], "LKnee": [25], "RKnee": [26], "LAnkle": [27], "RAnkle": [28],
    "LHeel": [29], "RHeel": [30], "LBigToe": [31], "RBigToe": [32],
}
REQUIRED = (11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)
FALLBACK = {0: 7, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 9: 0, 10: 0, 17: 15, 19: 15, 21: 15, 18: 16, 20: 16, 22: 16,
            29: 27, 31: 27, 30: 28, 32: 28}


def to_rig_axes(p, up="z"):
    """source metres -> rig axes (Y up, right-handed)."""
    x, y, z = p
    if up == "z":
        return (x, z, -y)
    if up == "y":
        return (x, y, z)
    raise ValueError("up must be 'y' or 'z'")


def landmarks(frames, joint_names=SKILLCORNER, up="z"):
    """(N, 33, 3) landmark array in rig axes, NaN where a joint is missing."""
    N = len(frames)
    P = np.full((N, 33, 3), np.nan)
    for i, fr in enumerate(frames):
        if not fr:
            continue
        for nm, xyz in fr.items():
            slots = joint_names.get(nm)
            if slots is None or xyz is None:
                continue
            v = to_rig_axes(xyz, up)
            for s in slots:
                P[i, s] = v
    # slots the source doesn't have borrow the nearest joint it does (eyes -> nose,
    # finger tips -> wrist, heel / toe -> ankle) so every column is defined
    for slot, src in FALLBACK.items():
        miss = np.isnan(P[:, slot, 0])
        P[miss, slot] = P[miss, src]
    for i in range(N):            # a frame missing a limb joint is no use to the fit
        if np.isnan(P[i, list(REQUIRED), 0]).any():
            P[i] = np.nan
    return P


def _ankle(P, side):
    """ankle flex (deg, + = toes up) from the shin and the heel -> toe line."""
    kn, an, he, to = (MC.KN_L, MC.AN_L, MC.HEEL_L, MC.TOE_L) if side == "L" else (MC.KN_R, MC.AN_R, MC.HEEL_R, MC.TOE_R)
    shin = MC._unit(P[an] - P[kn]); foot = MC._unit(P[to] - P[he])
    if np.isnan(shin).any() or np.isnan(foot).any():
        return 0.0
    ang = math.degrees(math.acos(float(np.clip(np.dot(shin, foot), -1, 1))))
    return float(np.clip(90.0 - ang, -45.0, 40.0))


def fit_tracks(frames, fps=25.0, joint_names=SKILLCORNER, up="z", face_frame=None, smooth=None):
    """named 3D joint tracks -> (keys, report).  keys are (t in 0..1, pose) like mocap."""
    return fit_landmarks(landmarks(frames, joint_names, up), fps, face_frame, smooth)


def fit_landmarks(P, fps=25.0, face_frame=None, smooth=None):
    """(N, 33, 3) MediaPipe-slot landmarks in rig axes (NaN = missing) -> (keys, report).
    Used directly by video capture (sforge.matchcapture), which already has slots."""
    P = np.array(P, dtype=float)
    for slot, src in FALLBACK.items():
        miss = np.isnan(P[:, slot, 0])
        P[miss, slot] = P[miss, src]
    for i in range(len(P)):
        if np.isnan(P[i, list(REQUIRED), 0]).any():
            P[i] = np.nan
    ok = ~np.isnan(P[:, 0, 0])
    if ok.sum() < max(4, int(.6 * len(P))):
        raise ValueError("too few complete frames (%d of %d)" % (int(ok.sum()), len(P)))
    P, _ = MC.fill_and_smooth(P, win=smooth)
    N = len(P)
    # root in place: pelvis centre at the origin, every frame
    pelvis = .5 * (P[:, MC.HIP_L] + P[:, MC.HIP_R])
    P = P - pelvis[:, None, :]
    hd = MC.heading(P)
    fi = N // 2 if face_frame is None else int(np.clip(face_frame, 0, N - 1))
    h = math.atan2(float(np.mean(np.sin(hd[max(0, fi - 2):fi + 3]))), float(np.mean(np.cos(hd[max(0, fi - 2):fi + 3]))))
    R = MC._rotY(-h)
    xs = np.zeros((N, len(MC.PARAMS))); errs = np.zeros((N, len(MC.SEGS)))
    x = np.zeros(len(MC.PARAMS)); x[[18, 22]] = 10; x[[10, 14]] = 10
    keys = []
    Pr = P @ R.T
    for i in range(N):
        T = MC.targets(Pr[i])
        x = MC.solve_frame(T, x, xs[i - 1] if i else None)
        xs[i] = x; errs[i] = MC.angle_err(T, x)
        pose = MC.params_to_pose(x)
        pose["ankle_L"] = _ankle(Pr[i], "L"); pose["ankle_R"] = _ankle(Pr[i], "R")
        pose["lift"] = 0.0; pose["ground"] = True; pose["pos"] = (0.0, 0.0)
        keys.append((i / max(1, N - 1), pose))
    rep = dict(frames=N, fps=float(fps), duration=round((N - 1) / float(fps), 4), frames_complete=int(ok.sum()),
               heading_deg=round(math.degrees(h), 1), mean_bone_err_deg=round(float(errs.mean()), 2),
               bone_err_deg={s[0]: round(float(errs[:, k].mean()), 1) for k, s in enumerate(MC.SEGS)})
    return keys, rep


def keys_record(name, keys, rep, licence, category="Mocap", loop=False, source="", desc=""):
    """a motion-library record (same schema as motionlib.import_file writes)."""
    return {
        "name": name, "category": category, "desc": desc or "3D joint track fitted onto the shared skeleton",
        "loop": bool(loop), "source": source, "origin": "import", "licence": licence,
        "duration": rep["duration"],
        "keys": [[round(t, 5), {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}] for t, p in keys],
        "import": dict(reader="jointtrack", fps=rep["fps"], frames=rep["frames"],
                       mean_bone_err_deg=rep["mean_bone_err_deg"], heading_deg=rep["heading_deg"],
                       note="Fitted with the mocap IK (bone directions -> joint angles); root in place."),
    }
