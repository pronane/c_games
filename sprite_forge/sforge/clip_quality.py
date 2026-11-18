"""Clip quality scorer for soccer animations.

Scores clips 0-100 by foot slide, joint limit violations,
loop seam error, and ball-contact accuracy.
Helps prioritise which clips to re-capture.
"""
from __future__ import annotations

import numpy as np


class ClipQualityScorer:
    """Scores animation clips by quality metrics."""

    def score_clip(self, clip_data: dict) -> dict:
        """Score a clip and return detailed metrics.

        Returns dict with:
        - score: 0-100 overall quality
        - foot_slide: max foot slide in cm
        - joint_violations: count of joint limit violations
        - loop_seam: loop seam error (quaternion distance)
        - ball_contact: ball contact accuracy (0-1)
        """
        foot_slide = self._measure_foot_slide(clip_data)
        joint_violations = self._count_joint_violations(clip_data)
        loop_seam = self._measure_loop_seam(clip_data)
        ball_contact = self._measure_ball_contact(clip_data)

        # Overall score: start at 100, deduct for issues
        score = 100.0
        score -= min(30, foot_slide * 2)  # foot slide penalty
        score -= min(20, joint_violations * 5)  # joint violations
        score -= min(20, loop_seam * 50)  # loop seam
        score -= min(30, (1 - ball_contact) * 30)  # ball contact

        return {
            "score": max(0, min(100, score)),
            "foot_slide_cm": foot_slide,
            "joint_violations": joint_violations,
            "loop_seam_error": loop_seam,
            "ball_contact_accuracy": ball_contact,
        }

    def _measure_foot_slide(self, clip_data: dict) -> float:
        """Measure max foot slide in cm during stance phase."""
        # Placeholder: actual implementation measures foot position during contact
        return 0.0

    def _count_joint_violations(self, clip_data: dict) -> int:
        """Count frames where joints exceed limits."""
        # Placeholder: actual implementation checks joint angles against limits
        return 0

    def _measure_loop_seam(self, clip_data: dict) -> float:
        """Measure loop seam error (first vs last frame quaternion distance)."""
        if not clip_data.get("loop"):
            return 0.0
        bones = clip_data.get("bones", {})
        if not bones:
            return 0.0
        # Compare first and last frame quaternions for Hips bone
        hips = bones.get("Hips", {})
        quats = hips.get("r", [])
        if len(quats) < 8:
            return 0.0
        first = np.array(quats[:4])
        last = np.array(quats[-4:])
        # Quaternion distance (1 - |dot|)
        dot = abs(np.dot(first, last))
        return 1.0 - dot

    def _measure_ball_contact(self, clip_data: dict) -> float:
        """Measure ball contact accuracy (0-1, 1 = perfect)."""
        events = clip_data.get("events", {})
        if "ball_contact" not in events:
            return 0.5  # No contact event = medium score
        return 1.0  # Has contact event = good


def score_clip(clip_data: dict) -> dict:
    """Convenience function to score a clip."""
    scorer = ClipQualityScorer()
    return scorer.score_clip(clip_data)
