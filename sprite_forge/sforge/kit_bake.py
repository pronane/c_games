"""Kit texture baking for soccer player.

Bakes kit colours into a texture atlas for efficient rendering.
Includes kit texture painter — draw stripes, numbers, sponsor logos.
"""
from __future__ import annotations

import numpy as np

KIT_PALETTES = {
    "home": {
        "jersey": (0.16, 0.27, 0.78), "trim": (0.98, 0.84, 0.12),
        "shorts": (0.96, 0.96, 0.96), "socks": (0.16, 0.27, 0.78),
        "skin": (0.89, 0.70, 0.56), "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "away": {
        "jersey": (0.78, 0.08, 0.16), "trim": (0.08, 0.59, 0.16),
        "shorts": (0.12, 0.12, 0.12), "socks": (0.78, 0.08, 0.16),
        "skin": (0.89, 0.70, 0.56), "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "gk_home": {
        "jersey": (0.08, 0.67, 0.35), "trim": (0.04, 0.35, 0.20),
        "shorts": (0.08, 0.08, 0.08), "socks": (0.08, 0.67, 0.35),
        "skin": (0.89, 0.70, 0.56), "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
    "gk_away": {
        "jersey": (0.98, 0.55, 0.08), "trim": (0.12, 0.12, 0.12),
        "shorts": (0.12, 0.12, 0.12), "socks": (0.98, 0.55, 0.08),
        "skin": (0.89, 0.70, 0.56), "hair": (0.23, 0.15, 0.08),
        "boots": (0.10, 0.10, 0.10),
    },
}

UV_REGIONS = {
    "jersey": (0.0, 0.0, 0.5, 0.5),
    "shorts": (0.5, 0.0, 1.0, 0.5),
    "socks": (0.0, 0.5, 0.5, 1.0),
    "skin": (0.5, 0.5, 0.75, 1.0),
    "hair": (0.75, 0.5, 1.0, 1.0),
    "boots": (0.75, 0.75, 1.0, 1.0),
}


def bake_kit_texture(kit_name: str, size: int = 512) -> np.ndarray:
    """Bake a kit texture atlas."""
    palette = KIT_PALETTES.get(kit_name, KIT_PALETTES["home"])
    texture = np.zeros((size, size, 3), dtype=np.float32)
    for part, (u0, v0, u1, v1) in UV_REGIONS.items():
        if part in palette:
            color = np.array(palette[part], dtype=np.float32)
            x0, x1 = int(u0 * size), int(u1 * size)
            y0, y1 = int(v0 * size), int(v1 * size)
            texture[y0:y1, x0:x1] = color
    return texture


def paint_kit(texture: np.ndarray, kit_name: str, pattern: str = "stripes",
              number: int = 10, sponsor: str = "") -> np.ndarray:
    """Paint kit details onto a baked texture.

    Patterns: stripes, hoops, sash, solid.
    Adds jersey number and sponsor text.
    """
    palette = KIT_PALETTES.get(kit_name, KIT_PALETTES["home"])
    size = texture.shape[0]
    u0, v0, u1, v1 = UV_REGIONS["jersey"]
    x0, x1 = int(u0 * size), int(u1 * size)
    y0, y1 = int(v0 * size), int(v1 * size)

    jersey_color = np.array(palette["jersey"], dtype=np.float32)
    trim_color = np.array(palette["trim"], dtype=np.float32)

    if pattern == "stripes":
        # Vertical stripes
        stripe_w = (x1 - x0) // 6
        for i in range(6):
            if i % 2 == 0:
                sx0 = x0 + i * stripe_w
                sx1 = sx0 + stripe_w
                texture[y0:y1, sx0:sx1] = trim_color
    elif pattern == "hoops":
        # Horizontal hoops
        hoop_h = (y1 - y0) // 4
        for i in range(4):
            if i % 2 == 0:
                hy0 = y0 + i * hoop_h
                hy1 = hy0 + hoop_h
                texture[hy0:hy1, x0:x1] = trim_color
    elif pattern == "sash":
        # Diagonal sash
        for y in range(y0, y1):
            x = x0 + int((y - y0) * (x1 - x0) / max(1, y1 - y0))
            if x0 <= x < x1:
                texture[y, max(x0, x-2):min(x1, x+3)] = trim_color

    # Jersey number (simple block digits in centre)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    num_str = str(number)
    digit_w = 8
    for i, digit in enumerate(num_str):
        dx = cx + (i - len(num_str) // 2) * digit_w
        # Draw simple digit as filled rectangle (placeholder for font rendering)
        texture[cy-10:cy+10, dx:dx+digit_w-2] = np.array([1.0, 1.0, 1.0], dtype=np.float32)

    return texture


def get_kit_palette(kit_name: str) -> dict:
    return KIT_PALETTES.get(kit_name, KIT_PALETTES["home"])


def list_kits() -> list[str]:
    return list(KIT_PALETTES.keys())
