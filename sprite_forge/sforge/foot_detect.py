"""Foot-contact auto-detector for soccer mocap.

Automatically detects foot-contact frames from mocap data
by analysing foot height and velocity.
"""
from __future__ import annotations

import numpy as np


class FootContactDetector:
    """Detects foot-contact frames from skeleton data."""

    def __init__(self, height_threshold: float = 0.05,
                 velocity_threshold: float = 0.5):
        self.height_threshold = height_threshold
        self.velocity_threshold = velocity_threshold

    def detect_contacts(self, foot_positions: list[np.ndarray],
                        foot_velocities: list[np.ndarray]) -> list[int]:
        """Detect contact frames from foot position/velocity arrays.

        Returns list of frame indices where foot is in contact with ground.
        """
        contacts = []
        for i, (pos, vel) in enumerate(zip(foot_positions, foot_velocities)):
            height = pos[1]
            speed = np.linalg.norm(vel)
            if height < self.height_threshold and speed < self.velocity_threshold:
                contacts.append(i)
        return contacts

    def detect_footsteps(self, left_contacts: list[int],
                         right_contacts: list[int]) -> dict:
        """Combine left/right contacts into footstep events.

        Returns dict with left/right footstep frames.
        """
        return {
            "left_footsteps": left_contacts,
            "right_footsteps": right_contacts,
            "total_steps": len(left_contacts) + len(right_contacts),
        }


def detect_foot_contacts(foot_positions: list[np.ndarray]) -> list[int]:
    """Convenience function to detect foot contacts."""
    detector = FootContactDetector()
    velocities = []
    for i in range(len(foot_positions)):
        if i == 0:
            velocities.append(np.zeros(3))
        else:
            velocities.append(foot_positions[i] - foot_positions[i - 1])
    return detector.detect_contacts(foot_positions, velocities)
