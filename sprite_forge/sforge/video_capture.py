"""Sprite Forge video capture pipeline.

Record yourself doing moves, feed through pose estimation,
retarget to soccer rig, bake as GLB animation clips.

Pipeline:
1. Video input (phone recording)
2. Pose estimation (MediaPipe or OpenPose)
3. Retarget to 19-bone soccer rig
4. Clean up (smooth, foot sliding fix, root motion)
5. Bake as GLB clip
6. Integrate into soccer_motions.py

Usage:
    python -m sforge.video_capture input.mp4 --clip soccer_stepover --output clips/
"""

import json
import math
from pathlib import Path
from typing import List, Tuple

# Soccer rig bones (19)
SOCCER_BONES = [
    "hips", "spine", "chest", "neck", "head",
    "upper_arm_l", "forearm_l", "hand_l",
    "upper_arm_r", "forearm_r", "hand_r",
    "thigh_l", "shin_l", "foot_l", "toe_l",
    "thigh_r", "shin_r", "foot_r", "toe_r",
]

# MediaPipe pose landmarks (33 points)
MEDIAPIPE_JOINTS = {
    "hips": 23,  # left_hip (use average of 23,24)
    "spine": 11,  # left_shoulder (approx)
    "chest": 12,  # right_shoulder
    "neck": 0,    # nose
    "head": 0,
    "upper_arm_l": 11,
    "forearm_l": 13,
    "hand_l": 15,
    "upper_arm_r": 12,
    "forearm_r": 14,
    "hand_r": 16,
    "thigh_l": 23,
    "shin_l": 25,
    "foot_l": 27,
    "toe_l": 31,
    "thigh_r": 24,
    "shin_r": 26,
    "foot_r": 28,
    "toe_r": 32,
}


def extract_poses(video_path: str) -> List[List[Tuple[float, float, float]]]:
    """Extract 3D poses from video using MediaPipe.

    Returns list of frames, each with 33 joint positions (x, y, z).
    """
    try:
        import mediapipe as mp
    except ImportError:
        raise ImportError("MediaPipe required: pip install mediapipe")

    import cv2
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5)

    cap = cv2.VideoCapture(video_path)
    frames = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)
        if results.pose_landmarks:
            joints = []
            for lm in results.pose_landmarks.landmark:
                joints.append((lm.x, lm.y, lm.z))
            frames.append(joints)

    cap.release()
    pose.close()
    return frames


def retarget_pose(mediapipe_frame: List[Tuple[float, float, float]]) -> dict:
    """Retarget MediaPipe pose to soccer rig bones.

    Returns dict of bone_name -> (x, y, z) position.
    """
    retargeted = {}
    for bone, mp_idx in MEDIAPIPE_JOINTS.items():
        if mp_idx < len(mediapipe_frame):
            retargeted[bone] = mediapipe_frame[mp_idx]
    return retargeted


def smooth_poses(poses: List[dict], window: int = 5) -> List[dict]:
    """Smooth pose sequence with moving average."""
    if len(poses) < window:
        return poses
    smoothed = []
    for i in range(len(poses)):
        start = max(0, i - window // 2)
        end = min(len(poses), i + window // 2 + 1)
        avg = {}
        for bone in poses[i].keys():
            xs = [poses[j][bone][0] for j in range(start, end) if bone in poses[j]]
            ys = [poses[j][bone][1] for j in range(start, end) if bone in poses[j]]
            zs = [poses[j][bone][2] for j in range(start, end) if bone in poses[j]]
            if xs:
                avg[bone] = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
        smoothed.append(avg)
    return smoothed


def extract_root_motion(poses: List[dict]) -> List[Tuple[float, float, float]]:
    """Extract root motion (hips translation) from poses."""
    roots = []
    for pose in poses:
        if "hips" in pose:
            roots.append(pose["hips"])
        else:
            roots.append((0, 0, 0))
    return roots


def detect_foot_contact(poses: List[dict], threshold: float = 0.05) -> List[int]:
    """Detect frames where foot contacts ground (y < threshold)."""
    contacts = []
    for i, pose in enumerate(poses):
        for foot in ["foot_l", "foot_r"]:
            if foot in pose and pose[foot][1] < threshold:
                contacts.append(i)
                break
    return contacts


def bake_clip(
    poses: List[dict],
    clip_name: str,
    fps: int = 30,
) -> dict:
    """Bake poses into animation clip data.

    Returns clip dict with bones, frames, root motion, contacts.
    """
    smoothed = smooth_poses(poses)
    roots = extract_root_motion(smoothed)
    contacts = detect_foot_contact(smoothed)

    clip = {
        "name": clip_name,
        "fps": fps,
        "frames": len(smoothed),
        "bones": SOCCER_BONES,
        "poses": smoothed,
        "root_motion": roots,
        "foot_contacts": contacts,
    }
    return clip


def save_clip(clip: dict, output_dir: str):
    """Save clip as JSON for integration into soccer_motions.py."""
    out = Path(output_dir) / f"{clip['name']}.json"
    out.write_text(json.dumps(clip, indent=2))
    print(f"Saved clip: {out} ({clip['frames']} frames)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sprite Forge video capture")
    parser.add_argument("video", help="Input video file")
    parser.add_argument("--clip", default="soccer_custom", help="Clip name")
    parser.add_argument("--output", default="clips/", help="Output directory")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second")
    args = parser.parse_args()

    print(f"Extracting poses from {args.video}...")
    frames = extract_poses(args.video)
    print(f"Extracted {len(frames)} frames")

    print("Retargeting to soccer rig...")
    poses = [retarget_pose(f) for f in frames]

    print("Baking clip...")
    clip = bake_clip(poses, args.clip, args.fps)

    Path(args.output).mkdir(parents=True, exist_ok=True)
    save_clip(clip, args.output)

    print(f"Done! Clip '{args.clip}' ready for soccer_motions.py integration.")


if __name__ == "__main__":
    main()
