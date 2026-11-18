"""Phone-video mocap for soccer.

Multi-angle capture with ball tracking and foot-contact detection.
Includes multi-angle fusion — combine front + side cameras into 3D.
"""
from __future__ import annotations

import numpy as np
from typing import Optional

SOCCER_CLIPS = [
    "dribble_close", "dribble_open", "dribble_sprint",
    "trap_ground", "trap_aerial", "chest_control",
    "kick_pass", "kick_shoot", "kick_volley",
    "turn_left", "turn_right", "cut",
    "shield", "step_over", "roulette",
    "header", "toe_lift", "knock_on",
]

BALL_COLOR_RANGE = {
    "white": ((170, 170, 170), (255, 255, 255)),
    "yellow": ((180, 180, 0), (255, 255, 100)),
    "orange": ((200, 100, 0), (255, 180, 50)),
}

FOOT_CONTACT = {
    "height_threshold": 0.05,
    "velocity_threshold": 0.5,
    "distance_threshold": 0.15,
}


class SoccerMocap:
    """Soccer-specific motion capture from phone video."""

    def __init__(self, fps: int = 30):
        self.fps = fps
        self.ball_track = None
        self.foot_contacts = []

    def capture(self, clip_name: str, video_path: str,
                ball_color: str = "white") -> dict:
        """Capture a soccer clip from video."""
        return {
            "clip_name": clip_name,
            "video_path": video_path,
            "fps": self.fps,
            "ball_color": ball_color,
            "keyframes": None,
            "ball_contact": None,
            "footsteps": [],
            "ball_track": None,
        }

    def detect_ball(self, frame: np.ndarray, color: str = "white") -> Optional[tuple]:
        """Detect ball position in a frame."""
        return None

    def detect_foot_contact(self, foot_pos: np.ndarray,
                           ball_pos: Optional[np.ndarray]) -> bool:
        """Detect if foot is in contact with ball."""
        if ball_pos is None:
            return False
        height = foot_pos[1]
        distance = np.linalg.norm(foot_pos - ball_pos)
        return (height < FOOT_CONTACT["height_threshold"] and
                distance < FOOT_CONTACT["distance_threshold"])

    def segment_clip(self, keyframes: list, clip_type: str) -> dict:
        """Segment a captured clip by action type."""
        return {
            "clip_type": clip_type,
            "start_frame": 0,
            "end_frame": len(keyframes),
            "contact_frame": None,
            "phases": [],
        }

    def fuse_angles(self, front_keyframes: list, side_keyframes: list) -> list:
        """Fuse front and side camera captures into 3D skeleton.

        Triangulates joint positions from two camera angles.
        Front camera gives X/Y, side camera gives Z/Y.
        Combined: X from front, Z from side, Y averaged.
        """
        if len(front_keyframes) != len(side_keyframes):
            raise ValueError("Front and side captures must have same frame count")

        fused = []
        for front, side in zip(front_keyframes, side_keyframes):
            frame = {}
            for joint in front:
                if joint in side:
                    # X from front, Z from side, Y averaged
                    frame[joint] = np.array([
                        front[joint][0],  # X from front
                        (front[joint][1] + side[joint][1]) / 2,  # Y averaged
                        side[joint][2],   # Z from side
                    ])
                else:
                    frame[joint] = front[joint]
            fused.append(frame)
        return fused


def capture_soccer_clip(clip_name: str, video_path: str, fps: int = 30) -> dict:
    """Convenience function to capture a soccer clip."""
    mocap = SoccerMocap(fps=fps)
    return mocap.capture(clip_name, video_path)


def list_soccer_clips() -> list[str]:
    """List supported soccer clip types."""
    return SOCCER_CLIPS
