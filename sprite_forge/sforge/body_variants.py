"""Body variants for soccer player archetypes.

Generates distinct body proportions for Explosive / Lengthy / Controlled
archetypes by parameterising the footballer builder with height, bulk,
and leg-length scaling. Each variant produces a distinct silhouette
without changing the skeleton topology.

Also includes archetype clip batch generator — generates
Explosive/Lengthy/Controlled variants of every locomotion clip.
"""
from __future__ import annotations

import numpy as np

# Archetype body parameters: (height_scale, bulk_scale, leg_scale, shoulder_scale)
ARCHETYPE_BODIES = {
    "explosive": {
        "height": 0.97, "bulk": 0.92, "legs": 0.95, "shoulders": 0.94,
        "stride": 0.85, "cadence": 1.15, "lean": 0.15,
        "description": "Short stride, high cadence, forward lean",
    },
    "lengthy": {
        "height": 1.05, "bulk": 1.08, "legs": 1.08, "shoulders": 1.06,
        "stride": 1.15, "cadence": 0.88, "lean": 0.05,
        "description": "Long stride, low cadence, upright",
    },
    "controlled": {
        "height": 1.00, "bulk": 1.00, "legs": 1.00, "shoulders": 1.00,
        "stride": 1.00, "cadence": 1.00, "lean": 0.08,
        "description": "Compact, balanced, upright",
    },
}


def scale_skeleton(skeleton, archetype: str):
    """Scale skeleton joint positions for an archetype."""
    params = ARCHETYPE_BODIES[archetype]
    new_world = {}
    for name, matrix in skeleton.W.items():
        m = matrix.copy()
        pos = m[:3, 3]
        if "Hips" in name or "Spine" in name or "Chest" in name or "Neck" in name or "Head" in name:
            pos[1] *= params["height"]
        if any(x in name for x in ["Thigh", "Shin", "Foot", "Knee", "Ankle"]):
            pos[1] *= params["legs"]
            pos[0] *= params["bulk"]
        if any(x in name for x in ["Arm", "Forearm", "Hand", "Shoulder", "Clavicle"]):
            pos[0] *= params["shoulders"]
            pos[1] *= params["height"]
        m[:3, 3] = pos
        new_world[name] = m
    return skeleton.__class__(skeleton.names, [new_world[n] for n in skeleton.names], skeleton.parent)


def build_variant(archetype: str, skeleton, design):
    """Build a footballer mesh with archetype-specific proportions."""
    scaled_skeleton = scale_skeleton(skeleton, archetype)
    from .footballer import build
    return build(scaled_skeleton, design)


def get_variant_params(archetype: str) -> dict:
    """Get body parameters for an archetype."""
    return ARCHETYPE_BODIES.get(archetype, ARCHETYPE_BODIES["controlled"])


def list_archetypes() -> list[str]:
    """List available archetypes."""
    return list(ARCHETYPE_BODIES.keys())


def generate_archetype_clips(base_clips: dict) -> dict:
    """Generate archetype variants of locomotion clips.

    For each base locomotion clip, generates Explosive/Lengthy/Controlled
    variants with adjusted stride, cadence, and lean parameters.

    Returns dict mapping (archetype, clip_name) to clip data.
    """
    variants = {}
    for clip_name, clip_data in base_clips.items():
        if not clip_name.startswith("soccer_"):
            continue
        for archetype, params in ARCHETYPE_BODIES.items():
            variant = {
                "fps": clip_data["fps"],
                "frames": clip_data["frames"],
                "loop": clip_data.get("loop", True),
                "bones": {},
                "archetype": archetype,
                "stride_scale": params["stride"],
                "cadence_scale": params["cadence"],
                "lean_offset": params["lean"],
            }
            # Copy bone data (actual stride/cadence adjustment happens at bake time)
            for bone_name, bone_data in clip_data.get("bones", {}).items():
                variant["bones"][bone_name] = {
                    "r": bone_data["r"],
                    "t": bone_data.get("t", []),
                }
            variants[(archetype, clip_name)] = variant
    return variants
