"""Blend weight learner for soccer clips.

Learns optimal blend weights from mocap data.
Pre-computes weights per blend-space cell for runtime use.
"""
from __future__ import annotations

import numpy as np
from typing import Dict, Tuple


class BlendWeightLearner:
    """Learns blend weights from mocap clip data."""

    def __init__(self, speed_bins: int = 5, turn_bins: int = 4, ball_bins: int = 3):
        self.speed_bins = speed_bins
        self.turn_bins = turn_bins
        self.ball_bins = ball_bins
        self.weights: Dict[Tuple[int, int, int], float] = {}

    def learn_from_clips(self, clips: list[dict]) -> dict:
        """Learn blend weights from a set of clips.

        Each clip has speed, turnRate, ballState metadata.
        Computes optimal weight per blend-space cell.
        """
        # Group clips by blend-space cell
        cells: Dict[Tuple[int, int, int], list] = {}
        for clip in clips:
            cell = self._get_cell(clip.get("speed", 0), clip.get("turnRate", 0), clip.get("ballState", 0))
            if cell not in cells:
                cells[cell] = []
            cells[cell].append(clip)

        # Compute weights (normalised by clip count)
        total = sum(len(v) for v in cells.values())
        for cell, cell_clips in cells.items():
            self.weights[cell] = len(cell_clips) / total if total > 0 else 0

        return self.weights

    def get_weight(self, speed: float, turn_rate: float, ball_state: int) -> float:
        """Get blend weight for a blend-space position."""
        cell = self._get_cell(speed, turn_rate, ball_state)
        return self.weights.get(cell, 0.0)

    def export_weights(self) -> dict:
        """Export learned weights as JSON-serialisable dict."""
        return {
            f"{s}_{t}_{b}": w
            for (s, t, b), w in self.weights.items()
        }

    def _get_cell(self, speed: float, turn_rate: float, ball_state: int) -> Tuple[int, int, int]:
        """Map continuous values to blend-space cell."""
        speed_bin = min(int(speed / 2.0), self.speed_bins - 1)
        turn_bin = min(int(abs(turn_rate) / 1.0), self.turn_bins - 1)
        ball_bin = min(ball_state, self.ball_bins - 1)
        return (speed_bin, turn_bin, ball_bin)


def learn_blend_weights(clips: list[dict]) -> dict:
    """Convenience function to learn blend weights."""
    learner = BlendWeightLearner()
    learner.learn_from_clips(clips)
    return learner.export_weights()
