"""Soccer polish presets: clean_keys with soccer joint limits, anticipation
for kicks, follow-through for headers.

Usage:
    from sforge.soccer_polish import soccer_clean_keys
    keys, report = soccer_clean_keys(keys, clip_name="soccer_shoot")
"""
from __future__ import annotations

from .motionlib import clean_keys

# Soccer joint limits (degrees) — prevent hyperextension and impossible poses.
SOCCER_JOINT_LIMITS = {
    "knee_L": (0, 150),
    "knee_R": (0, 150),
    "ankle_L": (-30, 45),
    "ankle_R": (-30, 45),
    "hip_L": (-45, 120),
    "hip_R": (-45, 120),
    "elbow_L": (0, 160),
    "elbow_R": (0, 160),
    "shoulder_L": (-60, 180),
    "shoulder_R": (-60, 180),
}


def soccer_clean_keys(keys, clip_name: str = "", loop: bool = False):
    """Clean keys with soccer-specific settings.

    - Kicks: anticipation (wind-up) + follow-through.
    - Headers: follow-through (neck snap).
    - Locomotion: foot planting + weight shift.
    - All: joint limit clamping.
    """
    # Determine polish settings by clip type.
    is_kick = any(k in clip_name for k in ("kick", "shoot", "pass", "volley"))
    is_header = "header" in clip_name
    is_loco = any(l in clip_name for l in ("walk", "jog", "run", "sprint",
                                           "dribble", "strafe", "turn"))

    cleaned, report = clean_keys(
        keys,
        loop=loop,
        feet=is_loco,
        weight=True,
        anticipation=is_kick,
        follow=is_kick or is_header,
    )

    # Clamp joint angles to soccer limits.
    clamped = 0
    for t, pose in cleaned:
        for joint, (lo, hi) in SOCCER_JOINT_LIMITS.items():
            if joint in pose:
                val = pose[joint]
                if isinstance(val, (int, float)):
                    clamped_val = max(lo, min(hi, val))
                    if clamped_val != val:
                        pose[joint] = clamped_val
                        clamped += 1

    report["soccer_joints_clamped"] = clamped
    report["soccer_clip"] = clip_name
    return cleaned, report
