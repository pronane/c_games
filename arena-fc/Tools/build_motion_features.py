#!/usr/bin/env python3
"""Bake deterministic locomotion feature rows from Arena's existing 18-bone rig JSON.

Usage: python3 Tools/build_motion_features.py
The output contains features/payloads only; it does not add or alter pose assets.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RIG_PATH = ROOT / "Data" / "soccer_rig.json"
CLIPS_PATH = ROOT / "Data" / "clips" / "clip_manifest.json"
OUT_PATH = ROOT / "Data" / "clips" / "motion_features.json"
TIMES = (0.2, 0.4, 0.6)
LAYOUT = [
    "foot_l_pos_x", "foot_l_pos_z", "foot_r_pos_x", "foot_r_pos_z",
    "foot_l_vel_x", "foot_l_vel_z", "foot_r_vel_x", "foot_r_vel_z",
    "root_vel_x", "root_vel_z", "yaw_rate",
    "traj_pos_0_x", "traj_pos_0_z", "traj_pos_1_x", "traj_pos_1_z",
    "traj_pos_2_x", "traj_pos_2_z",
    "traj_dir_0_x", "traj_dir_0_z", "traj_dir_1_x", "traj_dir_1_z",
    "traj_dir_2_x", "traj_dir_2_z",
]
WEIGHTS = [1.0] * len(LAYOUT)
for _i in range(4, 8): WEIGHTS[_i] = 1.3
WEIGHTS[8:10] = [0.8, 0.8]
WEIGHTS[10] = 0.7
WEIGHTS[11:17] = [1.5] * 6
WEIGHTS[17:23] = [1.2] * 6


def qmul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw,
            aw*bw - ax*bx - ay*by - az*bz)


def qrotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2*(y*vz - z*vy), 2*(z*vx - x*vz), 2*(x*vy - y*vx)
    return (vx + w*tx + y*tz - z*ty,
            vy + w*ty + z*tx - x*tz,
            vz + w*tz + x*ty - y*tx)


def yaw_of(q):
    x, y, z, w = q
    return math.atan2(2*(w*y + x*z), 1 - 2*(y*y + z*z))


def angle_diff(a, b):
    d = math.fmod(a - b, 2*math.pi)
    if d > math.pi: d -= 2*math.pi
    if d < -math.pi: d += 2*math.pi
    return d


def local_xz(world_delta, yaw):
    x, _, z = world_delta
    c, s = math.cos(yaw), math.sin(yaw)
    return (x*c - z*s, x*s + z*c)


def frame_pose(bones, bone_index, clip, frame):
    count = clip["frames"]
    frame %= count
    local_rot = [(0.0, 0.0, 0.0, 1.0) for _ in bones]
    local_trans = [(0.0, 0.0, 0.0) for _ in bones]
    for name, entry in clip["bones"].items():
        i = bone_index[name]
        r = entry["r"][frame*4:frame*4+4]
        local_rot[i] = tuple(r)
        if "t" in entry:
            t = entry["t"][frame*3:frame*3+3]
            local_trans[i] = tuple(t)
    world_rot = [(0.0, 0.0, 0.0, 1.0) for _ in bones]
    world_pos = [(0.0, 0.0, 0.0) for _ in bones]
    for i, bone in enumerate(bones):
        parent = bone["p"]
        if parent < 0:
            world_rot[i] = local_rot[i]
            world_pos[i] = tuple(bone["h"][axis] + local_trans[i][axis] for axis in range(3))
            continue
        pr = world_rot[parent]
        offset = tuple(bone["h"][axis] - bones[parent]["h"][axis] + local_trans[i][axis]
                       for axis in range(3))
        rotated = qrotate(pr, offset)
        world_pos[i] = tuple(world_pos[parent][axis] + rotated[axis] for axis in range(3))
        world_rot[i] = qmul(pr, local_rot[i])
    hip = bone_index["Hips"]
    root = world_pos[hip]
    yaw = yaw_of(world_rot[hip])
    feet = []
    for name in ("LFoot", "RFoot"):
        i = bone_index[name]
        tail_offset = tuple(bones[i]["t"][axis] - bones[i]["h"][axis] for axis in range(3))
        toe = qrotate(world_rot[i], tail_offset)
        world_toe = tuple(world_pos[i][axis] + toe[axis] for axis in range(3))
        feet.append(local_xz(tuple(world_toe[axis] - root[axis] for axis in range(3)), yaw))
    return root, yaw, feet


def features_for_clip(bones, bone_index, clip, meta):
    count, fps = clip["frames"], float(clip["fps"])
    poses = [frame_pose(bones, bone_index, clip, i) for i in range(count)]
    speed = float(meta.get("preferredSpeed", 0.0))
    clip_id = meta["id"]
    if "backpedal" in clip_id:
        profile_vel = (0.0, -speed)
    elif "strafe_l" in clip_id:
        profile_vel = (-speed, 0.0)
    elif "strafe_r" in clip_id:
        profile_vel = (speed, 0.0)
    else:
        profile_vel = (0.0, speed)
    preferred_turn = float(meta.get("preferredTurnRate", 0.0))
    if "strafe_r" in clip_id:
        preferred_turn = -preferred_turn
    rows = []
    for i, (root, yaw, feet) in enumerate(poses):
        prev_pose, next_pose = poses[(i-1) % count], poses[(i+1) % count]
        dt = 1.0 / fps
        feat = [feet[0][0], feet[0][1], feet[1][0], feet[1][1]]
        for foot_index in range(2):
            feat.extend(((next_pose[2][foot_index][axis] - prev_pose[2][foot_index][axis]) / (2*dt)
                         for axis in range(2)))
        root_delta = tuple((next_pose[0][axis] - prev_pose[0][axis]) / (2*dt) for axis in range(3))
        measured_root_vel = local_xz(root_delta, yaw)
        # The shipped clips are largely in-place; use the authored preferred-speed
        # metadata as a deterministic root-motion proxy when baked translation is absent.
        root_vel = measured_root_vel if math.hypot(*measured_root_vel) > 0.05 else profile_vel
        measured_turn = angle_diff(next_pose[1], prev_pose[1]) / (2*dt)
        turn_rate = measured_turn if abs(measured_turn) > 0.1 else preferred_turn
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
        if len(feat) != len(LAYOUT):
            raise AssertionError(f"{clip['id']}: expected {len(LAYOUT)} features, got {len(feat)}")
        rows.append(feat)
    return rows


def main():
    rig = json.loads(RIG_PATH.read_text())
    manifest = json.loads(CLIPS_PATH.read_text())
    bones = rig["bones"]
    bone_index = {bone["n"]: i for i, bone in enumerate(bones)}
    pose_clips = rig["clips"]
    meta_by_id = {clip["id"]: clip for clip in manifest["clips"]}
    rows = []
    for clip_id in sorted(pose_clips):
        source = pose_clips[clip_id]
        meta = meta_by_id.get(clip_id)
        if not meta or meta["category"] != "Locomotion" or not source["loop"]:
            continue
        for frame, feature in enumerate(features_for_clip(bones, bone_index, source, meta)):
            rows.append({
                "clipId": clip_id,
                "frameIndex": frame,
                "phase": frame / source["frames"],
                "category": "Locomotion",
                "ballState": meta["ballState"],
                "styleTag": "",
                "features": [round(float(x), 6) for x in feature],
            })
    if not rows:
        raise RuntimeError("No looped locomotion clips found in the rig data")
    matrix = [[row["features"][d] for row in rows] for d in range(len(LAYOUT))]
    mean, std_dev = [], []
    for values in matrix:
        mu = sum(values) / len(values)
        variance = sum((x - mu) ** 2 for x in values) / len(values)
        mean.append(round(mu, 8))
        sigma = math.sqrt(variance)
        std_dev.append(round(max(sigma, 1e-3), 8))
    output = {
        "version": 1,
        "featureSchemaVersion": 1,
        "dimensions": len(LAYOUT),
        "layout": LAYOUT,
        "trajectoryTimes": list(TIMES),
        "space": "facing_root_xz",
        "normalization": {"method": "zscore", "mean": mean, "stdDev": std_dev},
        "weights": WEIGHTS,
        "rows": rows,
    }
    OUT_PATH.write_text(json.dumps(output, separators=(",", ":")) + "\n")
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(rows)} rows x {len(LAYOUT)} dims ({OUT_PATH.stat().st_size/1024:.1f} KiB)")


if __name__ == "__main__":
    main()
