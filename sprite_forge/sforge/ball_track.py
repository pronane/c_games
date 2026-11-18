"""Ball trajectory solver for soccer mocap.

Extracts ball path from video and bakes it into clip metadata.
Colour-based ball detection per frame, exported as keyframes.
"""
from __future__ import annotations

import numpy as np
from typing import Optional

# Ball colour ranges (HSV)
BALL_COLORS = {
    "white": ((0, 0, 170), (180, 30, 255)),
    "yellow": ((20, 100, 100), (35, 255, 255)),
    "orange": ((5, 100, 100), (20, 255, 255)),
    "red": ((0, 100, 100), (10, 255, 255)),
}


class BallTracker:
    """Tracks ball position across video frames."""

    def __init__(self, color: str = "white", min_radius: int = 5):
        self.color = color
        self.min_radius = min_radius
        self.trajectory = []

    def track_frame(self, frame: np.ndarray) -> Optional[tuple]:
        """Detect ball in a single frame.

        Returns (x, y, radius) or None if not found.
        Uses colour thresholding + contour detection.
        """
        # Placeholder: actual implementation uses OpenCV
        # cv2.inRange(frame, lower, upper) + findContours
        return None

    def track_video(self, frames: list[np.ndarray]) -> list[Optional[tuple]]:
        """Track ball across all frames.

        Returns list of (x, y, radius) or None per frame.
        Interpolates missing detections.
        """
        detections = []
        for frame in frames:
            detections.append(self.track_frame(frame))

        # Interpolate missing detections
        last_valid = None
        for i, det in enumerate(detections):
            if det is not None:
                last_valid = det
            elif last_valid is not None:
                # Linear interpolation to next valid
                next_valid = None
                for j in range(i + 1, len(detections)):
                    if detections[j] is not None:
                        next_valid = detections[j]
                        break
                if next_valid is not None:
                    t = (i - (i - 1)) / (j - (i - 1)) if j > i - 1 else 0
                    detections[i] = (
                        last_valid[0] + (next_valid[0] - last_valid[0]) * t,
                        last_valid[1] + (next_valid[1] - last_valid[1]) * t,
                        last_valid[2],
                    )

        self.trajectory = detections
        return detections

    def export_keyframes(self) -> dict:
        """Export ball trajectory as clip keyframes.

        Returns dict with ball_contact frame and trajectory data.
        """
        if not self.trajectory:
            return {"ball_contact": None, "trajectory": []}

        # Find contact frame (ball closest to foot)
        # This is a placeholder — actual implementation uses foot positions
        contact_frame = None
        for i, pos in enumerate(self.trajectory):
            if pos is not None and pos[2] > self.min_radius:
                contact_frame = i
                break

        return {
            "ball_contact": contact_frame,
            "trajectory": [
                {"x": p[0], "y": p[1], "r": p[2]} if p else None
                for p in self.trajectory
            ],
        }


def track_ball(frames: list[np.ndarray], color: str = "white") -> dict:
    """Convenience function to track ball in video frames."""
    tracker = BallTracker(color=color)
    tracker.track_video(frames)
    return tracker.export_keyframes()
