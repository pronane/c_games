"""Motion compression for soccer clips.

Compresses clip data via quaternion quantisation and delta encoding.
Reduces JSON size for faster downloads and loading.
"""
from __future__ import annotations

import numpy as np
import struct


class MotionCompressor:
    """Compresses animation clip data."""

    def __init__(self, quat_bits: int = 16, delta_encode: bool = True):
        self.quat_bits = quat_bits
        self.delta_encode = delta_encode

    def compress_clip(self, clip_data: dict) -> dict:
        """Compress a clip's bone data.

        Quantises quaternions and delta-encodes between frames.
        Returns compressed dict with metadata.
        """
        compressed = {
            "fps": clip_data["fps"],
            "frames": clip_data["frames"],
            "loop": clip_data["loop"],
            "bones": {},
            "compression": {
                "quat_bits": self.quat_bits,
                "delta_encode": self.delta_encode,
            },
        }

        for bone_name, bone_data in clip_data["bones"].items():
            quats = np.array(bone_data["r"], dtype=np.float32).reshape(-1, 4)
            if self.delta_encode:
                # Delta encode: store differences from previous frame
                deltas = np.diff(quats, axis=0, prepend=quats[0:1])
                compressed["bones"][bone_name] = {
                    "r": self._quantise(deltas).tolist(),
                    "delta": True,
                }
            else:
                compressed["bones"][bone_name] = {
                    "r": self._quantise(quats).tolist(),
                    "delta": False,
                }

        return compressed

    def decompress_clip(self, compressed: dict) -> dict:
        """Decompress a clip back to original format."""
        clip_data = {
            "fps": compressed["fps"],
            "frames": compressed["frames"],
            "loop": compressed["loop"],
            "bones": {},
        }

        for bone_name, bone_data in compressed["bones"].items():
            quats = np.array(bone_data["r"], dtype=np.float32)
            if bone_data.get("delta"):
                # Cumulative sum to recover original
                quats = np.cumsum(quats, axis=0)
            clip_data["bones"][bone_name] = {"r": quats.flatten().tolist()}

        return clip_data

    def _quantise(self, quats: np.ndarray) -> np.ndarray:
        """Quantise quaternions to fewer bits."""
        # Simple quantisation: scale to [-1, 1] and round
        scale = (2 ** (self.quat_bits - 1)) - 1
        return np.round(np.clip(quats, -1, 1) * scale) / scale


def compress_clip(clip_data: dict) -> dict:
    """Convenience function to compress a clip."""
    comp = MotionCompressor()
    return comp.compress_clip(clip_data)


def estimate_size_reduction(original: dict, compressed: dict) -> float:
    """Estimate size reduction ratio."""
    import json
    orig_size = len(json.dumps(original))
    comp_size = len(json.dumps(compressed))
    return 1.0 - (comp_size / orig_size) if orig_size > 0 else 0.0
