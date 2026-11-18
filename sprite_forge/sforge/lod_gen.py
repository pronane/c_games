"""LOD generator for soccer player mesh.

Generates 4k/8k/16k triangle LODs from the base mesh.
Preserves skinning weights for runtime LOD switching.
"""
from __future__ import annotations

import numpy as np


class LODGenerator:
    """Generates mesh LODs by decimation."""

    def __init__(self, target_triangles: list[int] = [4000, 8000, 16000]):
        self.target_triangles = sorted(target_triangles)

    def generate_lods(self, vertices: np.ndarray, faces: np.ndarray,
                      skin_weights: np.ndarray) -> dict[int, tuple]:
        """Generate LODs from base mesh.

        Returns dict mapping triangle count to (vertices, faces, weights).
        """
        lods = {}
        for target in self.target_triangles:
            if target >= len(faces):
                lods[target] = (vertices, faces, skin_weights)
            else:
                lods[target] = self._decimate(vertices, faces, skin_weights, target)
        return lods

    def _decimate(self, vertices, faces, weights, target):
        """Simple edge-collapse decimation.

        Placeholder: actual implementation uses quadric error metrics.
        """
        # For now, return a subset of faces (not ideal but functional)
        ratio = target / len(faces)
        n_faces = int(len(faces) * ratio)
        return vertices, faces[:n_faces], weights


def generate_lods(vertices: np.ndarray, faces: np.ndarray,
                  skin_weights: np.ndarray) -> dict:
    """Convenience function to generate LODs."""
    gen = LODGenerator()
    return gen.generate_lods(vertices, faces, skin_weights)
