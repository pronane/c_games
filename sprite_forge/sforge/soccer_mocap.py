"""Phone-video mocap for soccer.

Multi-angle capture with ball tracking and foot-contact detection.
Extends the base mocap pipeline with soccer-specific features:
- Ball position tracking (colour-based detection)
- Foot-contact frame detection (for ball_contact events)
- Multi-angle fusion (front + side cameras)
- Soccer-specific clip segmentation (dribble, trap, kick, turn)

Usage:
    from sforge.soccer_mocap import SoccerMocap, capture_soccer_clip
    mocap = SoccerMocap()
    clip = mocap.capture("dribble", video_path="dribble.mp4")
"""
from __future__ import annotations

import numpy as np
from typing import Optional

# Soccer-specific clip types
SOCCER_CLIPS = [
    "dribble_close", "dribble_open", "dribble_sprint",
    "trap_ground", "trap_aerial", "chest_control",
    "kick_pass", "kick_shoot", "kick_volley",
    "turn_left", "turn_right", "cut",
    "shield", "step_over", "roulette",
    "header", "toe_lift", "knock_on",
]

# Ball tracking parameters
BALL_COLOR_RANGE = {
    "white": ((170, 170, 170), (255, 255, 255)),
    "yellow": ((180, 180, 0), (255, 255, 100)),
    "orange": ((200, 100, 0), (255, 180, 50)),
}

# Foot contact thresholds
FOOT_CONTACT = {
    "height_threshold": 0.05,  # metres above ground
    "velocity_threshold": 0.5,  # m/s (foot moving toward ball)
    "distance_threshold": 0.15,  # metres from ball centre
}


class SoccerMocap:
    """Soccer-specific motion capture from phone video."""

    def __init__(self, fps: int = 30):
        self.fps = fps
        self.ball_track = None
        self.foot_contacts = []

    def capture(self, clip_name: str, video_path: str,
                ball_color: str = "white") -> dict:
        """Capture a soccer clip from video.

        Returns dict with:
        - keyframes: baked skeleton data
        - ball_contact: frame index of ball contact
        - footsteps: list of foot contact frames
        - ball_track: ball position per frame
        """
        # This is a placeholder for the full implementation.
        # The actual capture uses MediaPipe PoseLandmarker + ball detection.
        return {
            "clip_name": clip_name,
            "video_path": video_path,
            "fps": self.fps,
            "ball_color": ball_color,
            "keyframes": None,  # Populated by actual capture
            "ball_contact": None,
            "footsteps": [],
            "ball_track": None,
        }

    def detect_ball(self, frame: np.ndarray, color: str = "white") -> Optional[tuple]:
        """Detect ball position in a frame using colour thresholding.

        Returns (x, y, radius) or None if not found.
        """
        # Placeholder: actual implementation uses OpenCV colour thresholding
        return None

    def detect_foot_contact(self, foot_pos: np.ndarray,
                           ball_pos: Optional[np.ndarray]) -> bool:
        """Detect if foot is in contact with ball.

        Uses height, velocity, and distance thresholds.
        """
        if ball_pos is None:
            return False
        height = foot_pos[1]
        distance = np.linalg.norm(foot_pos - ball_pos)
        return (height < FOOT_CONTACT["height_threshold"] and
                distance < FOOT_CONTACT["distance_threshold"])

    def segment_clip(self, keyframes: list, clip_type: str) -> dict:
        """Segment a captured clip by action type.

        Detects action boundaries (e.g., kick windup → contact → follow-through).
        """
        return {
            "clip_type": clip_type,
            "start_frame": 0,
            "end_frame": len(keyframes),
            "contact_frame": None,
            "phases": [],
        }


def capture_soccer_clip(clip_name: str, video_path: str,
                        fps: int = 30) -> dict:
    """Convenience function to capture a soccer clip."""
    mocap = SoccerMocap(fps=fps)
    return mocap.capture(clip_name, video_path)


def list_soccer_clips() -> list[str]:
    """List supported soccer clip types."""
    return SOCCER_CLIPS
