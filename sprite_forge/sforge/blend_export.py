"""Blend-space exporter: exports blend weights + phase-sync points alongside clips.

Generates a JSON file describing the locomotion blend space (speed x turnRate
x ballState -> clip + phase + weight) that the runtime (SoccerClipRig.cs /
BrowserBoot.gd) can use for data-driven blending.

Usage:
    from sforge.blend_export import export_blend_space
    export_blend_space("blend_space.json")
"""
from __future__ import annotations

import json


def default_blend_space() -> dict:
    """Default blend space matching the runtime SoccerClipRig logic."""
    return {
        "version": 1,
        "axes": {
            "speed": {"min": 0.0, "max": 6.0, "bands": [0.35, 1.4, 2.4, 3.8]},
            "turnRate": {"min": -3.0, "max": 3.0, "threshold": 2.2},
            "ballState": {"values": ["none", "has_ball", "dribbling"]},
        },
        "cells": [
            # (speed_max, turn_max, ball_state) -> clip
            {"speed_max": 0.35, "turn_max": 99, "ball": "none", "clip": "soccer_idle"},
            {"speed_max": 0.35, "turn_max": 99, "ball": "has_ball", "clip": "soccer_shield"},
            {"speed_max": 1.4, "turn_max": 99, "ball": "none", "clip": "soccer_walk"},
            {"speed_max": 1.4, "turn_max": 99, "ball": "has_ball", "clip": "soccer_dribble"},
            {"speed_max": 2.4, "turn_max": 99, "ball": "none", "clip": "soccer_jog"},
            {"speed_max": 2.4, "turn_max": 99, "ball": "has_ball", "clip": "soccer_dribble"},
            {"speed_max": 3.8, "turn_max": 99, "ball": "none", "clip": "soccer_run"},
            {"speed_max": 3.8, "turn_max": 99, "ball": "has_ball", "clip": "soccer_run_ball"},
            {"speed_max": 99, "turn_max": 99, "ball": "none", "clip": "soccer_sprint"},
            {"speed_max": 99, "turn_max": 99, "ball": "has_ball", "clip": "soccer_run_ball"},
            # Turn override (any speed > 1.2, turnRate > 2.2).
            {"speed_max": 99, "turn_max": 2.2, "ball": "any", "clip": "soccer_turn", "override": True},
            # Directional (heading offset).
            {"heading": "forward", "clip": "forward_locomotion"},
            {"heading": "left", "clip": "soccer_strafe_l"},
            {"heading": "right", "clip": "soccer_strafe_r"},
            {"heading": "backward", "clip": "soccer_backpedal"},
        ],
        "phase_sync": {
            "enabled": True,
            "crossfade_duration": 0.18,
            "sync_on_switch": True,
        },
        "natural_rates": {
            "soccer_walk": 0.74, "soccer_jog": 1.01, "soccer_run": 1.01,
            "soccer_sprint": 1.22, "soccer_dribble": 0.60,
            "soccer_run_ball": 0.98, "soccer_shield": 0.30,
            "soccer_turn": 0.62, "soccer_strafe_l": 0.55,
            "soccer_strafe_r": 0.55, "soccer_backpedal": 0.58,
            "soccer_jockey": 0.66,
        },
        "max_rates": {
            "soccer_walk": 2.2, "soccer_jog": 2.6, "soccer_run": 2.6,
            "soccer_sprint": 2.8, "soccer_dribble": 1.8,
            "soccer_run_ball": 2.6, "soccer_shield": 1.2,
            "soccer_turn": 1.6, "soccer_strafe_l": 1.6,
            "soccer_strafe_r": 1.6, "soccer_backpedal": 1.6,
            "soccer_jockey": 1.8,
        },
    }


def export_blend_space(path: str, blend_space: dict | None = None) -> None:
    """Export the blend space to a JSON file."""
    data = blend_space or default_blend_space()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
