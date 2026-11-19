"""Generate kit textures for Sprite Forge soccer player.

Creates PNG textures for jersey (stripes/hoops/sash + number),
shorts, socks, and skin. Textures are baked into the GLB.

Usage:
    from sforge.kit_texture import generate_kit_textures
    textures = generate_kit_textures(home_color=(0.85, 0.15, 0.2), pattern="stripes")
"""
from __future__ import annotations

import io
import struct
import zlib


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Create a PNG chunk with CRC."""
    chunk = chunk_type + data
    crc = zlib.crc32(chunk) & 0xffffffff
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)


def _create_png(width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """Create a PNG from RGB pixel data."""
    # PNG signature
    png = b"\x89PNG\r\n\x1a\n"
    # IHDR chunk
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    png += _png_chunk(b"IHDR", ihdr)
    # IDAT chunk (compressed image data)
    raw = b""
    for row in pixels:
        raw += b"\x00"  # Filter type: None
        for r, g, b in row:
            raw += bytes([r, g, b])
    compressed = zlib.compress(raw, 9)
    png += _png_chunk(b"IDAT", compressed)
    # IEND chunk
    png += _png_chunk(b"IEND", b"")
    return png


def generate_jersey_texture(
    base_color: tuple[float, float, float] = (0.85, 0.15, 0.2),
    pattern: str = "stripes",
    number: int = 10,
    width: int = 512,
    height: int = 512,
) -> bytes:
    """Generate jersey texture with pattern and number.

    Args:
        base_color: RGB tuple (0-1) for jersey base
        pattern: "stripes", "hoops", "sash", "solid"
        number: Jersey number to draw
        width/height: Texture dimensions

    Returns:
        PNG bytes
    """
    # Convert base color to 0-255
    br, bg, bb = int(base_color[0] * 255), int(base_color[1] * 255), int(base_color[2] * 255)
    # Accent color (white for stripes)
    ar, ag, ab = 245, 245, 245

    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            # Base color
            r, g, b = br, bg, bb

            # Apply pattern
            if pattern == "stripes":
                # Vertical stripes (every 64px)
                if (x // 64) % 2 == 1:
                    r, g, b = ar, ag, ab
            elif pattern == "hoops":
                # Horizontal hoops (every 64px)
                if (y // 64) % 2 == 1:
                    r, g, b = ar, ag, ab
            elif pattern == "sash":
                # Diagonal sash
                if abs((x - y) % 256) < 32:
                    r, g, b = ar, ag, ab
            # "solid" = no pattern

            # Add subtle fabric noise
            noise = ((x * 7 + y * 13) % 10) - 5
            r = max(0, min(255, r + noise))
            g = max(0, min(255, g + noise))
            b = max(0, min(255, b + noise))

            row.append((r, g, b))
        pixels.append(row)

    # Draw number in center (simple block digits)
    # Number area: center 128x128
    cx, cy = width // 2, height // 2
    num_str = str(number)
    # Simple 3x5 digit patterns (very basic)
    digits = {
        '0': ["111", "101", "101", "101", "111"],
        '1': ["010", "110", "010", "010", "111"],
        '2': ["111", "001", "111", "100", "111"],
        '3': ["111", "001", "111", "001", "111"],
        '4': ["101", "101", "111", "001", "001"],
        '5': ["111", "100", "111", "001", "111"],
        '6': ["111", "100", "111", "101", "111"],
        '7': ["111", "001", "010", "010", "010"],
        '8': ["111", "101", "111", "101", "111"],
        '9': ["111", "101", "111", "001", "111"],
    }
    digit_w, digit_h = 20, 28
    spacing = 6
    total_w = len(num_str) * digit_w + (len(num_str) - 1) * spacing
    start_x = cx - total_w // 2
    start_y = cy - digit_h // 2

    for i, ch in enumerate(num_str):
        if ch not in digits:
            continue
        pattern_digit = digits[ch]
        dx = start_x + i * (digit_w + spacing)
        for dy in range(digit_h):
            for dx_pixel in range(digit_w):
                # Map pixel to digit grid
                grid_x = dx_pixel * 3 // digit_w
                grid_y = dy * 5 // digit_h
                if pattern_digit[grid_y][grid_x] == '1':
                    px, py = dx + dx_pixel, start_y + dy
                    if 0 <= px < width and 0 <= py < height:
                        # White number with slight shadow
                        pixels[py][px] = (245, 245, 245)

    return _create_png(width, height, pixels)


def generate_skin_texture(
    tone: int = 3,
    width: int = 256,
    height: int = 256,
) -> bytes:
    """Generate skin texture with subtle variation.

    Args:
        tone: Skin tone 1-6 (1=lightest, 6=darkest)
        width/height: Texture dimensions

    Returns:
        PNG bytes
    """
    # Skin tone base colors (approximate)
    tones = {
        1: (0.98, 0.85, 0.72),
        2: (0.92, 0.76, 0.60),
        3: (0.85, 0.65, 0.48),
        4: (0.72, 0.52, 0.38),
        5: (0.55, 0.38, 0.26),
        6: (0.38, 0.26, 0.18),
    }
    base = tones.get(tone, tones[3])
    br, bg, bb = int(base[0] * 255), int(base[1] * 255), int(base[2] * 255)

    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            # Subtle skin variation (pores, freckles)
            noise = ((x * 3 + y * 5) % 8) - 4
            r = max(0, min(255, br + noise))
            g = max(0, min(255, bg + noise))
            b = max(0, min(255, bb + noise))
            row.append((r, g, b))
        pixels.append(row)

    return _create_png(width, height, pixels)


def generate_face_texture(
    skin_tone: int = 3,
    hair_style: str = "short",
    hair_color: tuple[int, int, int] = (31, 41, 55),
) -> bytes:
    """Generate procedural face texture (256x256).

    Features: eyes, nose, mouth, eyebrows, hair.
    """
    import math
    skin_tones = [
        (245, 208, 176), (232, 184, 138), (198, 134, 66),
        (141, 85, 36), (255, 219, 172), (241, 194, 125),
    ]
    skin = skin_tones[skin_tone % len(skin_tones)]
    pixels = [[skin for _ in range(256)] for _ in range(256)]

    # Eyes (white + iris)
    for eye_x in [85, 170]:
        for dy in range(-8, 9):
            for dx in range(-12, 13):
                if dx*dx + dy*dy < 100:
                    pixels[110+dy][eye_x+dx] = (255, 255, 255)
                if dx*dx + dy*dy < 25:
                    pixels[110+dy][eye_x+dx] = (60, 40, 20)  # iris

    # Nose (shadow)
    for dy in range(0, 20):
        for dx in range(-4, 5):
            if abs(dx) < 4 - dy//5:
                pixels[130+dy][128+dx] = tuple(max(0, c-20) for c in skin)

    # Mouth
    for dx in range(-15, 16):
        pixels[165][128+dx] = (120, 60, 60)

    # Hair (top of head)
    if hair_style != "bald":
        hair_height = {"short": 40, "curly": 50, "afro": 60, "long": 80, "mohawk": 30}.get(hair_style, 40)
        for y in range(hair_height):
            for x in range(256):
                if y < hair_height - abs(x-128)//4:
                    pixels[y][x] = hair_color

    return _create_png(256, 256, pixels)


def generate_kit_textures(
    home_color: tuple[float, float, float] = (0.85, 0.15, 0.2),
    pattern: str = "stripes",
    number: int = 10,
    skin_tone: int = 3,
    hair_style: str = "short",
) -> dict[str, bytes]:
    """Generate all kit textures.

    Returns:
        Dict with keys: "jersey", "skin", "shorts", "socks", "face"
    """
    textures = {}
    textures["jersey"] = generate_jersey_texture(home_color, pattern, number)
    textures["skin"] = generate_skin_texture(skin_tone)
    textures["face"] = generate_face_texture(skin_tone, hair_style)

    # Shorts: solid color (darker than jersey)
    shorts_color = tuple(max(0, c * 0.6) for c in home_color)
    sr, sg, sb = int(shorts_color[0] * 255), int(shorts_color[1] * 255), int(shorts_color[2] * 255)
    shorts_pixels = [[(sr, sg, sb) for _ in range(256)] for _ in range(256)]
    textures["shorts"] = _create_png(256, 256, shorts_pixels)

    # Socks: solid with stripe at top
    socks_pixels = []
    for y in range(256):
        row = []
        for x in range(256):
            if y < 32:  # Top stripe (white)
                row.append((245, 245, 245))
            else:
                row.append((sr, sg, sb))
        socks_pixels.append(row)
    textures["socks"] = _create_png(256, 256, socks_pixels)

    return textures
