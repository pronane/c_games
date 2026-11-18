"""Body variants for soccer player archetypes.

Generates distinct body proportions for Explosive / Lengthy / Controlled
archetypes by parameterising the footballer builder with height, bulk,
and leg-length scaling. Each variant produces a distinct silhouette
without changing the skeleton topology.

Usage:
    from sforge.body_variants import ARCHETYPE_BODIES, build_variant
    mesh = build_variant("explosive", skeleton, design)
"""
from __future__ import annotations

import numpy as np

# Archetype body parameters: (height_scale, bulk_scale, leg_scale, shoulder_scale)
ARCHETYPE_BODIES = {
    "explosive": {
        "height": 0.97,   # slightly shorter
        "bulk": 0.92,     # leaner
        "legs": 0.95,     # shorter legs (quick cadence)
        "shoulders": 0.94,
        "description": "Short stride, high cadence, forward lean",
    },
    "lengthy": {
        "height": 1.05,   # taller
        "bulk": 1.08,     # broader
        "legs": 1.08,     # longer legs (long stride)
        "shoulders": 1.06,
        "description": "Long stride, low cadence, upright",
    },
    "controlled": {
        "height": 1.00,   # average
        "bulk": 1.00,     # balanced
        "legs": 1.00,     # standard
        "shoulders": 1.00,
        "description": "Compact, balanced, upright",
    },
}


def scale_skeleton(skeleton, archetype: str):
    """Scale skeleton joint positions for an archetype.

    Returns a new skeleton with scaled bind pose.
    """
    params = ARCHETYPE_BODIES[archetype]
    new_world = {}
    for name, matrix in skeleton.W.items():
        m = matrix.copy()
        pos = m[:3, 3]
        # Scale Y (height) from hips
        if "Hips" in name or "Spine" in name or "Chest" in name or "Neck" in name or "Head" in name:
            pos[1] *= params["height"]
        # Scale legs
        if any(x in name for x in ["Thigh", "Shin", "Foot", "Knee", "Ankle"]):
            pos[1] *= params["legs"]
            pos[0] *= params["bulk"]  # width
        # Scale arms/shoulders
        if any(x in name for x in ["Arm", "Forearm", "Hand", "Shoulder", "Clavicle"]):
            pos[0] *= params["shoulders"]
            pos[1] *= params["height"]
        m[:3, 3] = pos
        new_world[name] = m
    return skeleton.__class__(skeleton.names, [new_world[n] for n in skeleton.names], skeleton.parent)


def build_variant(archetype: str, skeleton, design):
    """Build a footballer mesh with archetype-specific proportions.

    Returns (vertices, faces, paints) for the variant.
    """
    scaled_skeleton = scale_skeleton(skeleton, archetype)
    # Delegate to the footballer builder with scaled skeleton
    from .footballer import build
    return build(scaled_skeleton, design)


def get_variant_params(archetype: str) -> dict:
    """Get body parameters for an archetype."""
    return ARCHETYPE_BODIES.get(archetype, ARCHETYPE_BODIES["controlled"])


def list_archetypes() -> list[str]:
    """List available archetypes."""
    return list(ARCHETYPE_BODIES.keys())
