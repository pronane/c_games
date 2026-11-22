#!/usr/bin/env python3
"""Bake the AFL motion-matching assets from the shipped GAA squad GLB.

Writes TWO files into public/assets/:

  afl_motion.json          — runtime clip manifest (durations measured from the
                             GLB, categories/ball states/contact fractions from
                             afl_clip_meta.py)
  afl_motion_features.json — the 24-dim, z-scored pose-level feature table the
                             motion engine searches (schema v2, same contract as
                             the Arena FC bake: facing_root_xz space, zscore,
                             trajectory horizons 0.2/0.4/0.6, time_to_contact)

Deterministic: same GLB + same metadata -> identical bytes. Run after any change
to the squad GLB or afl_clip_meta.py.

    ../sfvenv/bin/python tools/build_afl_motion_features.py
"""
from __future__ import annotations
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(REPO, "sprite_forge"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sforge import gltfread  # noqa: E402
import afl_clip_meta  # noqa: E402

GLB = os.path.join(ROOT, "public", "assets", "gaelic_player.glb")
OUT_MANIFEST = os.path.join(ROOT, "public", "assets", "afl_motion.json")
OUT_FEATURES = os.path.join(ROOT, "public", "assets", "afl_motion_features.json")

LAYOUT = [
    "foot_l_pos_x", "foot_l_pos_z", "foot_r_pos_x", "foot_r_pos_z",
    "foot_l_vel_x", "foot_l_vel_z", "foot_r_vel_x", "foot_r_vel_z",
    "root_vel_x", "root_vel_z", "yaw_rate",
    "traj_pos_0_x", "traj_pos_0_z", "traj_pos_1_x", "traj_pos_1_z",
    "traj_pos_2_x", "traj_pos_2_z",
    "traj_dir_0_x", "traj_dir_0_z", "traj_dir_1_x", "traj_dir_1_z",
    "traj_dir_2_x", "traj_dir_2_z",
    "time_to_contact",
]
WEIGHTS = [1.0] * len(LAYOUT)
for i in range(4, 8): WEIGHTS[i] = 1.3
WEIGHTS[8:10] = [0.8, 0.8]
WEIGHTS[10] = 0.7
WEIGHTS[11:17] = [1.5] * 6
WEIGHTS[17:23] = [1.2] * 6
WEIGHTS[23] = 12.0
TIMES = (0.2, 0.4, 0.6)
NO_CONTACT = 1.5
ENTRY_WINDOW = 0.35
FPS = 30.0

JOINT_FOOT_L = "ball_l"   # MakeHuman ball-of-foot (toe) — the gait end, like Arena's LFoot+toe offset
JOINT_FOOT_R = "ball_r"
JOINT_ROOT = "pelvis"


def yaw_of_matrix(m: np.ndarray) -> float:
    # y-axis yaw of a rotation matrix: atan2-style on the projected forward (+Z) axis.
    return math.atan2(m[0, 2], m[2, 2])


def angle_diff(a: float, b: float) -> float:
    d = math.fmod(a - b, 2 * math.pi)
    if d > math.pi: d -= 2 * math.pi
    if d < -math.pi: d += 2 * math.pi
    return d


def local_xz(delta: np.ndarray, yaw: float) -> tuple[float, float]:
    x, _, z = float(delta[0]), float(delta[1]), float(delta[2])
    c, s = math.cos(yaw), math.sin(yaw)
    return (x * c - z * s, x * s + z * c)


def main() -> int:
    rig = gltfread.load(GLB)
    names = list(rig.bones)
    idx = {n: i for i, n in enumerate(names)}
    for j in (JOINT_ROOT, JOINT_FOOT_L, JOINT_FOOT_R):
        if j not in idx:
            print(f"FATAL: squad GLB is missing joint '{j}' (has {names[:8]}...)")
            return 1
    root_i, fl_i, fr_i = idx[JOINT_ROOT], idx[JOINT_FOOT_L], idx[JOINT_FOOT_R]

    # ---- manifest, durations measured from the GLB
    clips = []
    for clip_id, (category, ball, contact, pref_speed, pref_turn, loop) in afl_clip_meta.CLIP_META.items():
        if clip_id not in rig.clips:
            print(f"FATAL: manifest lists '{clip_id}' but the GLB has no such clip")
            return 1
        clip = rig.clips[clip_id]
        duration = max(0.0, (clip.frames - 1) / FPS)
        clips.append({
            "id": clip_id,
            "category": category,
            "ballState": ball,
            "contactFraction": contact,
            "footPlantFrames": [],
            "footPlantSides": [],
            "rootVelocityX": 0.0,
            "rootVelocityZ": round(float(pref_speed), 3),
            "preferredSpeed": pref_speed,
            "preferredTurnRate": pref_turn,
            "tags": [],
            "boneCount": len(names),
            "loop": bool(loop),
            "duration": round(duration, 6),
        })
    clips.sort(key=lambda c: c["id"])
    manifest = {"version": 1, "clips": clips}

    # ---- features, from skinned world transforms (exact, not kinematic re-solve)
    def frame_pose(worlds: np.ndarray, f: int):
        f = f % worlds.shape[0]
        W = worlds[f]
        root = W[root_i, :3, 3].copy()
        yaw = yaw_of_matrix(W[root_i, :3, :3])
        feet = []
        for fi in (fl_i, fr_i):
            feet.append(local_xz(W[fi, :3, 3] - root, yaw))
        return root, yaw, feet

    rows = []
    for clip_id, (category, ball, contact, pref_speed, pref_turn, loop) in sorted(afl_clip_meta.CLIP_META.items()):
        clip = rig.clips[clip_id]
        worlds = rig.clip_worlds(clip_id)
        count = worlds.shape[0]
        duration = max(0.0, (count - 1) / FPS)
        poses = [frame_pose(worlds, i) for i in range(count)]
        for f in range(count):
            phase = f / count
            if not loop and phase > (contact if contact >= 0 else ENTRY_WINDOW) + 1e-6:
                continue                      # one-shots: entry frames only
            if category == "Locomotion" and not loop:
                continue                      # non-loop gaits are not part of the gait search
            prev_p, next_p = poses[(f - 1) % count], poses[(f + 1) % count]
            cur = poses[f]
            dt = 1.0 / FPS
            feat = [cur[2][0][0], cur[2][0][1], cur[2][1][0], cur[2][1][1]]
            for foot in range(2):
                feat.extend((next_p[2][foot][a] - prev_p[2][foot][a]) / (2 * dt) for a in range(2))
            # The shipped clips are in-place (pelvis travel < 0.3 m over a whole
            # cycle), so per-frame central differences are noise, not motion. Use
            # the authored locomotion profile for every row: deterministic, and it
            # matches the preferredSpeed semantics the runtime maps speeds onto.
            root_vel = (0.0, float(pref_speed))
            turn_rate = float(pref_turn)
            feat.extend(root_vel)
            feat.append(turn_rate)
            for horizon in TIMES:
                if abs(turn_rate) < 1e-5:
                    dx, dz = root_vel[0] * horizon, root_vel[1] * horizon
                else:
                    angle = turn_rate * horizon
                    dx = (root_vel[0] * math.sin(angle) + root_vel[1] * (1 - math.cos(angle))) / turn_rate
                    dz = (root_vel[1] * math.sin(angle) - root_vel[0] * (1 - math.cos(angle))) / turn_rate
                feat.extend((dx, dz))
            for horizon in TIMES:
                relative = turn_rate * horizon
                feat.extend((math.sin(relative), math.cos(relative)))
            ttc = (contact - phase) * duration if 0.0 <= phase <= contact else NO_CONTACT
            feat.append(min(max(ttc, 0.0), NO_CONTACT))
            assert len(feat) == len(LAYOUT)
            rows.append({
                "clipId": clip_id,
                "frameIndex": f,
                "phase": round(phase, 6),
                "category": category,
                "ballState": ball,
                "styleTag": "",
                "features": [round(float(x), 6) for x in feat],
            })

    matrix = [[row["features"][d] for row in rows] for d in range(len(LAYOUT))]
    mean, std_dev = [], []
    for values in matrix:
        mu = sum(values) / len(values)
        var = sum((x - mu) ** 2 for x in values) / len(values)
        mean.append(round(mu, 8))
        std_dev.append(round(max(math.sqrt(var), 1e-3), 8))
    features = {
        "version": 2,
        "featureSchemaVersion": 2,
        "dimensions": len(LAYOUT),
        "layout": LAYOUT,
        "trajectoryTimes": list(TIMES),
        "space": "facing_root_xz",
        "normalization": {"method": "zscore", "mean": mean, "stdDev": std_dev},
        "weights": WEIGHTS,
        "rows": rows,
    }

    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    with open(OUT_FEATURES, "w", encoding="utf-8") as fh:
        json.dump(features, fh, separators=(",", ":"))
    print(f"afl_motion.json          : {len(clips)} clips, {os.path.getsize(OUT_MANIFEST)/1024:.1f} KiB")
    print(f"afl_motion_features.json : {len(rows)} rows x {len(LAYOUT)} dims, "
          f"{os.path.getsize(OUT_FEATURES)/1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
