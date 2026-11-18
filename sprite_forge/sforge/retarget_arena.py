"""Retarget generic mocap to Arena FC's 18-bone skeleton.

Maps external mocap (Mixamo, etc.) to Arena FC bone names.
Opens up external mocap libraries without manual retargeting.
"""
from __future__ import annotations

import numpy as np

# Arena FC 18-bone skeleton
ARENA_BONES = [
    "Hips", "Spine", "Chest", "Neck", "Head", "Face",
    "LUpperArm", "LForearm", "LHand",
    "RUpperArm", "RForearm", "RHand",
    "LThigh", "LShin", "LFoot",
    "RThigh", "RShin", "RFoot",
]

# Generic skeleton mappings (Mixamo, BVH, etc.)
GENERIC_MAPPINGS = {
    "mixamo": {
        "Hips": "Hips",
        "Spine": "Spine",
        "Chest": "Chest",
        "Neck": "Neck",
        "Head": "Head",
        "LUpperArm": "LeftArm",
        "LForearm": "LeftForeArm",
        "LHand": "LeftHand",
        "RUpperArm": "RightArm",
        "RForearm": "RightForeArm",
        "RHand": "RightHand",
        "LThigh": "LeftUpLeg",
        "LShin": "LeftLeg",
        "LFoot": "LeftFoot",
        "RThigh": "RightUpLeg",
        "RShin": "RightLeg",
        "RFoot": "RightFoot",
    },
    "bvh": {
        "Hips": "Hips",
        "Spine": "Spine",
        "Chest": "Chest",
        "Neck": "Neck",
        "Head": "Head",
        "LUpperArm": "LeftArm",
        "LForearm": "LeftForeArm",
        "LHand": "LeftHand",
        "RUpperArm": "RightArm",
        "RForearm": "RightForeArm",
        "RHand": "RightHand",
        "LThigh": "LeftThigh",
        "LShin": "LeftShin",
        "LFoot": "LeftFoot",
        "RThigh": "RightThigh",
        "RShin": "RightShin",
        "RFoot": "RightFoot",
    },
}


class ArenaRetargeter:
    """Retargets generic mocap to Arena FC 18-bone skeleton."""

    def __init__(self, source: str = "mixamo"):
        self.source = source
        self.mapping = GENERIC_MAPPINGS.get(source, {})

    def retarget_clip(self, source_clip: dict) -> dict:
        """Retarget a clip from generic skeleton to Arena FC skeleton.

        Returns clip with Arena FC bone names.
        """
        retargeted = {
            "fps": source_clip["fps"],
            "frames": source_clip["frames"],
            "loop": source_clip.get("loop", True),
            "bones": {},
        }

        source_bones = source_clip.get("bones", {})
        for arena_bone, generic_bone in self.mapping.items():
            if generic_bone in source_bones:
                retargeted["bones"][arena_bone] = source_bones[generic_bone]

        # Face bone has no generic equivalent — use Head data
        if "Face" not in retargeted["bones"] and "Head" in retargeted["bones"]:
            retargeted["bones"]["Face"] = retargeted["bones"]["Head"]

        return retargeted

    def retarget_library(self, source_clips: dict) -> dict:
        """Retarget a library of clips."""
        return {
            name: self.retarget_clip(clip)
            for name, clip in source_clips.items()
        }


def retarget_to_arena(source_clip: dict, source: str = "mixamo") -> dict:
    """Convenience function to retarget a clip."""
    retargeter = ArenaRetargeter(source)
    return retargeter.retarget_clip(source_clip)
