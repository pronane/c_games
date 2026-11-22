"""Close-up shading for game characters: skin pores, hair, eyes (v11.34, fed back from Arena FC).

A skin atlas from a 1-2k MakeHuman texture holds colour, not skin: up close it reads as plastic.  Real-time
engines fix that with a tiling *detail* normal map (pores, fine creases) laid over the atlas at a high UV
repeat, subsurface scattering, and a hair / eye response of their own.  This writes the maps and the
material presets a game applies to Sprite Forge characters:

    from sforge import skinshade as SS
    SS.export("out_dir")        # skin_detail_normal.png (tileable), skin_detail_rough.png, materials.json

    SS.PRESETS["skin"]          # roughness, specular, subsurface, detail repeat ...
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

# Engine-neutral material presets (Godot names in brackets).  Values are what reads as skin, hair and eyes
# under daylight and floodlights at broadcast and replay distance.
PRESETS = {
    "skin": {"roughness": .52, "specular": .35, "subsurface": .28, "subsurface_tint": [.95, .55, .45],
             "rim": .18, "rim_tint": .5, "detail_repeat": 38.0, "detail_strength": .55,
             "note": "subsurface needs a deferred / clustered renderer (Godot Forward+); skin_mode on"},
    "hair": {"roughness": .38, "specular": .55, "anisotropy": .6, "alpha_scissor": .45, "alpha_antialias": True,
             "note": "alpha-scissor with alpha-to-coverage; anisotropic highlight along the strands"},
    "eyes": {"roughness": .05, "specular": .8, "clearcoat": 1.0, "clearcoat_roughness": .02,
             "note": "wet cornea highlight - the catch-light that makes a face read alive"},
    "lashes": {"roughness": .6, "alpha_scissor": .4},
    "beard": {"roughness": .55, "alpha_scissor": .35, "anisotropy": .3},
}


def _periodic_noise(n, cutoff, seed):
    """tileable band-limited noise: random phases filtered in frequency space."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    r = np.sqrt(fx ** 2 + fy ** 2)
    spec = (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) * np.exp(-(r / cutoff) ** 2)
    spec[0, 0] = 0
    out = np.real(np.fft.ifft2(spec))
    return (out - out.mean()) / (out.std() + 1e-9)


def detail_height(n=512, seed=11):
    """pores (small sharp pits), fine creases (stretched mid-frequency), and a soft undulation."""
    rng = np.random.default_rng(seed)
    pores = np.zeros((n, n))
    k = int(n * n / 90)                          # one pore per ~90 px² at the detail scale
    ys, xs = rng.integers(0, n, k), rng.integers(0, n, k)
    depth = rng.uniform(.4, 1.0, k)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            w = np.exp(-(dx * dx + dy * dy) / 1.2)
            np.add.at(pores, ((ys + dy) % n, (xs + dx) % n), -depth * w)
    creases = _periodic_noise(n, .06, seed + 1)
    creases = np.abs(creases) * -0.35                       # thin valleys
    soft = _periodic_noise(n, .012, seed + 2) * .5
    h = pores * .9 + creases + soft
    return (h - h.min()) / (h.max() - h.min() + 1e-9)


def height_to_normal(h, strength=2.5):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * .5 * strength
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * .5 * strength
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return nrm


def export(out_dir, n=512):
    os.makedirs(out_dir, exist_ok=True)
    h = detail_height(n)
    nrm = height_to_normal(h, strength=6.0)
    Image.fromarray(((nrm * .5 + .5) * 255).astype(np.uint8), "RGB").save(os.path.join(out_dir, "skin_detail_normal.png"))
    rough = np.clip(.5 + (1 - h) * .35, 0, 1)                # pores a little rougher than the skin between them
    Image.fromarray((rough * 255).astype(np.uint8), "L").save(os.path.join(out_dir, "skin_detail_rough.png"))
    with open(os.path.join(out_dir, "materials.json"), "w") as f:
        json.dump({"version": "11.34", "presets": PRESETS,
                   "maps": {"skin_detail_normal": "tangent-space, tileable, OpenGL (+Y) convention",
                            "skin_detail_rough": "tileable roughness modulation"}}, f, indent=1)
    return PRESETS
