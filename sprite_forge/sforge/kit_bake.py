"""Kit texture baking for soccer player.

Bakes kit colours into a texture atlas for efficient rendering.
Keeps flat-colour materials for per-club tinting while providing
an optional baked texture variant for higher visual fidelity.

Usage:
    from sforge.kit_bake import bake_kit_texture, KIT_PALETTES
    texture = bake_kit_texture("home", size=512)
"""
from __future__ import annotations

import numpy as np

# Kit palettes: (jersey, trim, shorts, socks, skin, hair, boots)
KIT_PALETTES = {
    "home": {
        "jersey": (0.16, 0.27, 0.78),   # blue
        "trim": (0.98, 0.84, 0.12),     # gold
        "shorts": (0.96, 0.96, 0.96),   # white
        "socks": (0.16, 0.27, 0.78),    # blue
        "skin": (0.89, 0.70, 0.56),
        "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "away": {
        "jersey": (0.78, 0.08, 0.16),   # red
        "trim": (0.08, 0.59, 0.16),     # green
        "shorts": (0.12, 0.12, 0.12),   # black
        "socks": (0.78, 0.08, 0.16),    # red
        "skin": (0.89, 0.70, 0.56),
        "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "gk_home": {
        "jersey": (0.08, 0.67, 0.35),   # green
        "trim": (0.04, 0.35, 0.20),     # dark green
        "shorts": (0.08, 0.08, 0.08),   # black
        "socks": (0.08, 0.67, 0.35),    # green
        "skin": (0.89, 0.70, 0.56),
        "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "gk_away": {
        "jersey": (0.98, 0.55, 0.08),   # orange
        "trim": (0.12, 0.12, 0.12),     # black
        "shorts": (0.12, 0.12, 0.12),   # black
        "socks": (0.98, 0.55, 0.08),    # orange
        "skin": (0.89, 0.70, 0.56),
        "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
}

# UV region mapping: (u0, v0, u1, v1) for each body part
UV_REGIONS = {
    "jersey": (0.0, 0.0, 0.5, 0.5),
    "shorts": (0.5, 0.0, 1.0, 0.5),
    "socks": (0.0, 0.5, 0.5, 1.0),
    "skin": (0.5, 0.5, 0.75, 1.0),
    "hair": (0.75, 0.5, 1.0, 1.0),
    "boots": (0.75, 0.75, 1.0, 1.0),
}


def bake_kit_texture(kit_name: str, size: int = 512) -> np.ndarray:
    """Bake a kit texture atlas.

    Returns an (size, size, 3) float32 array with colours in each UV region.
    """
    palette = KIT_PALETTES.get(kit_name, KIT_PALETTES["home"])
    texture = np.zeros((size, size, 3), dtype=np.float32)

    for part, (u0, v0, u1, v1) in UV_REGIONS.items():
        if part in palette:
            color = np.array(palette[part], dtype=np.float32)
            x0, x1 = int(u0 * size), int(u1 * size)
            y0, y1 = int(v0 * size), int(v1 * size)
            texture[y0:y1, x0:x1] = color

    return texture


def get_kit_palette(kit_name: str) -> dict:
    """Get the colour palette for a kit."""
    return KIT_PALETTES.get(kit_name, KIT_PALETTES["home"])


def list_kits() -> list[str]:
    """List available kits."""
    return list(KIT_PALETTES.keys())
