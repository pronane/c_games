#!/usr/bin/env python3
"""
Console Asset Pipeline – Intelligent Sprite / Atlas Generator
=============================================================
Expert-level desktop developer tool that turns a single source image
(+ optional text prompt) into production-ready graphics constrained
to historical console hardware rules.

Supported modes:
  • 2D / Sprite Sheet
  • HD Sprite Sheet Array
  • 2.5D Atlas (multi-angle orthographic)
  • Multi-Angle 3D Workaround Sheet

Output: master .PNG + engine-ready .JSON manifest.

Dependencies (install once):
  pip install Pillow numpy
  (optional) pip install rembg opencv-python-headless   # for better bg removal

Author: Graphics Automation Engineer
"""

from __future__ import annotations

import json
import math
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance, ImageChops
except ImportError:
    print("ERROR: Pillow is required →  pip install Pillow")
    sys.exit(1)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Optional advanced bg removal
try:
    from rembg import remove, new_session
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False

# ---------------------------------------------------------------------------
# Console Hardware Profiles
# ---------------------------------------------------------------------------

@dataclass
class ConsoleProfile:
    name: str
    max_frame_w: int
    max_frame_h: int
    max_colors: int                 # 0 = unlimited / full RGBA
    pixel_art: bool                 # force nearest-neighbour
    dither: bool
    filter_style: str               # "none", "bilinear", "soft", "jagged"
    atlas_angles: int               # 4 or 8 for 2.5D/3D modes
    default_frames_per_action: int
    notes: str = ""

CONSOLE_PROFILES: Dict[str, ConsoleProfile] = {
    "Atari 2600": ConsoleProfile(
        name="Atari 2600",
        max_frame_w=8, max_frame_h=32,
        max_colors=2, pixel_art=True, dither=False,
        filter_style="none", atlas_angles=4,
        default_frames_per_action=2,
        notes="1-bit / binary look, extremely limited canvas"
    ),
    "NES": ConsoleProfile(
        name="NES",
        max_frame_w=16, max_frame_h=16,
        max_colors=4, pixel_art=True, dither=False,
        filter_style="none", atlas_angles=4,
        default_frames_per_action=3,
        notes="8×8 / 16×16 tiles, 4-color palette per sprite"
    ),
    "SNES / Genesis": ConsoleProfile(
        name="SNES / Genesis",
        max_frame_w=64, max_frame_h=64,
        max_colors=16, pixel_art=True, dither=True,
        filter_style="none", atlas_angles=4,
        default_frames_per_action=4,
        notes="Up to 64×64, 16-color indexed + dithering"
    ),
    "PlayStation 1": ConsoleProfile(
        name="PlayStation 1",
        max_frame_w=64, max_frame_h=64,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="jagged", atlas_angles=8,
        default_frames_per_action=4,
        notes="256×256 total atlas typical, unfiltered / affine wobble look"
    ),
    "Nintendo 64": ConsoleProfile(
        name="Nintendo 64",
        max_frame_w=64, max_frame_h=64,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="bilinear", atlas_angles=8,
        default_frames_per_action=4,
        notes="Strict 64×64 texture cache, heavy bilinear filtering"
    ),
    "PlayStation 2 / GameCube": ConsoleProfile(
        name="PlayStation 2 / GameCube",
        max_frame_w=128, max_frame_h=128,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="soft", atlas_angles=8,
        default_frames_per_action=6,
        notes="512×512 textures, clean mid-poly / Phong aesthetic"
    ),
    "PS3 / Xbox 360": ConsoleProfile(
        name="PS3 / Xbox 360",
        max_frame_w=256, max_frame_h=256,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="soft", atlas_angles=8,
        default_frames_per_action=6,
        notes="1024×1024, pre-baked lighting style"
    ),
    "PS4 / Xbox One": ConsoleProfile(
        name="PS4 / Xbox One",
        max_frame_w=512, max_frame_h=512,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="none", atlas_angles=8,
        default_frames_per_action=8,
        notes="2048×2048 PBR-ready surface look"
    ),
    "PlayStation 5": ConsoleProfile(
        name="PlayStation 5",
        max_frame_w=1024, max_frame_h=1024,
        max_colors=0, pixel_art=False, dither=False,
        filter_style="none", atlas_angles=8,
        default_frames_per_action=8,
        notes="4096×4096 cinematic / ray-traced quality target"
    ),
}

# Default animation states the user can edit
DEFAULT_ACTIONS = "idle, walk, run, jump, punch, kick, hand-pass, solo"

# ---------------------------------------------------------------------------
# Image Processing Helpers
# ---------------------------------------------------------------------------

def quantize_palette(img: Image.Image, max_colors: int, dither: bool = True) -> Image.Image:
    """Force indexed palette while preserving alpha if present."""
    if max_colors <= 0:
        return img
    has_alpha = img.mode == "RGBA"
    if has_alpha:
        alpha = img.split()[-1]
        rgb = img.convert("RGB")
    else:
        alpha = None
        rgb = img.convert("RGB")

    method = Image.FASTOCTREE
    quantized = rgb.quantize(colors=max_colors, method=method, dither=Image.FLOYDSTEINBERG if dither else Image.NONE)
    out = quantized.convert("RGBA" if has_alpha else "RGB")
    if has_alpha and alpha is not None:
        out.putalpha(alpha)
    return out


def apply_console_look(img: Image.Image, profile: ConsoleProfile) -> Image.Image:
    """Resize + filter + palette according to the chosen console profile."""
    target_w = min(img.width, profile.max_frame_w)
    target_h = min(img.height, profile.max_frame_h)

    # Keep aspect ratio, fit inside the max frame
    img.thumbnail((target_w, target_h), Image.NEAREST if profile.pixel_art else Image.LANCZOS)

    # Create a transparent canvas of exact frame size and centre the asset
    canvas = Image.new("RGBA", (profile.max_frame_w, profile.max_frame_h), (0, 0, 0, 0))
    offset = ((profile.max_frame_w - img.width) // 2, (profile.max_frame_h - img.height) // 2)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    canvas.paste(img, offset, img)

    # Style filters
    if profile.filter_style == "bilinear":
        # Simulate N64 heavy bilinear by slight blur then nearest
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.6))
    elif profile.filter_style == "soft":
        canvas = canvas.filter(ImageFilter.SMOOTH_MORE)
    elif profile.filter_style == "jagged":
        # PS1-style: nearest + slight contrast
        enhancer = ImageEnhance.Contrast(canvas)
        canvas = enhancer.enhance(1.25)

    # Palette reduction
    if profile.max_colors > 0:
        canvas = quantize_palette(canvas, profile.max_colors, dither=profile.dither)

    return canvas


def remove_background_safe(img: Image.Image) -> Image.Image:
    """Best-effort background removal. Falls back gracefully."""
    if HAS_REMBG:
        try:
            session = new_session("u2netp")
            return remove(img.convert("RGB"), session=session)
        except Exception:
            pass
    # Simple near-white / near-black fallback
    img = img.convert("RGBA")
    datas = list(img.getdata())
    new_data = []
    for r, g, b, a in datas:
        if (r > 245 and g > 245 and b > 245) or (r < 12 and g < 12 and b < 12):
            new_data.append((0, 0, 0, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return img


def make_variant(base: Image.Image, index: int, total: int, mode: str = "subtle") -> Image.Image:
    """
    Create a slight variation of the base frame so that animation sheets
    are not completely static.  This is a practical local approximation;
    real pose variation requires an external generative backend.
    """
    img = base.copy()
    if mode == "subtle":
        # Tiny scale / brightness pulse
        factor = 1.0 + 0.03 * math.sin(index / max(total - 1, 1) * math.pi)
        w, h = img.size
        new_w, new_h = max(1, int(w * factor)), max(1, int(h * factor))
        img = img.resize((new_w, new_h), Image.NEAREST if w < 128 else Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(img, ((w - new_w) // 2, (h - new_h) // 2), img)
        return canvas
    return img


def generate_angle_view(base: Image.Image, angle_deg: int, size: Tuple[int, int]) -> Image.Image:
    """
    Practical multi-angle workaround:
    - 0° / 180° : original / horizontal flip
    - 90° / 270°: rotate + optional shear for pseudo-perspective
    - 45° etc.  : rotate + slight perspective transform
    """
    img = base.convert("RGBA")
    w, h = size

    if angle_deg == 0:
        out = img
    elif angle_deg == 180:
        out = ImageOps.mirror(img)
    elif angle_deg in (90, 270):
        out = img.rotate(-angle_deg, expand=True, resample=Image.BICUBIC)
    else:
        # Diagonal angles – rotate then mild affine shear
        out = img.rotate(-angle_deg, expand=True, resample=Image.BICUBIC)
        # Simple shear approximation
        shear = 0.15 * math.sin(math.radians(angle_deg))
        out = out.transform(
            out.size, Image.AFFINE,
            (1, shear, 0, 0, 1, 0),
            resample=Image.BICUBIC
        )

    # Fit into target size
    out.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    ox = (size[0] - out.width) // 2
    oy = (size[1] - out.height) // 2
    canvas.paste(out, (ox, oy), out)
    return canvas


# ---------------------------------------------------------------------------
# Core Generation Engines
# ---------------------------------------------------------------------------

def create_sprite_sheet(
    source: Image.Image,
    asset_name: str,
    console: str,
    actions: List[str],
    frames_per_action: int,
    mode: str = "2D / Sprite Sheet",
    out_dir: str = "output",
) -> Tuple[str, str]:
    """
    Pipeline 1 – Animation Sprite Sheet Generator.
    Returns (png_path, json_path).
    """
    profile = CONSOLE_PROFILES[console]
    frame_w, frame_h = profile.max_frame_w, profile.max_frame_h

    # Prepare base frame under console constraints
    base = apply_console_look(source, profile)

    num_actions = len(actions)
    canvas_w = frame_w * frames_per_action
    canvas_h = frame_h * num_actions

    master = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    manifest: Dict[str, Any] = {
        "meta": {
            "asset_name": asset_name,
            "target_console": console,
            "mode": mode,
            "frame_width": frame_w,
            "frame_height": frame_h,
            "frames_per_action": frames_per_action,
            "total_width": canvas_w,
            "total_height": canvas_h,
            "notes": profile.notes,
        },
        "frames": {},
    }

    for y_idx, action in enumerate(actions):
        manifest["frames"][action] = []
        for x_idx in range(frames_per_action):
            pos_x = x_idx * frame_w
            pos_y = y_idx * frame_h

            frame = make_variant(base, x_idx, frames_per_action)
            # Optional: draw a tiny label for debugging (comment out for clean production)
            # draw = ImageDraw.Draw(frame)
            # draw.text((2, 2), f"{action[:3]}{x_idx}", fill=(255, 255, 255, 180))

            master.paste(frame, (pos_x, pos_y), frame)

            manifest["frames"][action].append({
                "frame_index": x_idx,
                "x": pos_x,
                "y": pos_y,
                "w": frame_w,
                "h": frame_h,
            })

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_console = console.replace(" ", "_").replace("/", "_").lower()
    png_name = f"{asset_name}_{safe_console}_sheet.png"
    json_name = f"{asset_name}_{safe_console}_meta.json"
    png_path = out_path / png_name
    json_path = out_path / json_name

    master.save(png_path, "PNG")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(png_path), str(json_path)


def create_multi_angle_atlas(
    source: Image.Image,
    asset_name: str,
    console: str,
    mode: str = "2.5D Atlas",
    out_dir: str = "output",
) -> Tuple[str, str]:
    """
    Pipeline 2 – Orthographic multi-angle texture atlas.
    Generates Front, Front-Right … Front-Left + Top-Down.
    """
    profile = CONSOLE_PROFILES[console]
    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    if profile.atlas_angles == 4:
        angles = [0, 90, 180, 270]

    # Also add a top-down view
    labels = [f"angle_{a}" for a in angles] + ["top_down"]

    frame_w = profile.max_frame_w
    frame_h = profile.max_frame_h
    cols = 4
    rows = (len(labels) + cols - 1) // cols

    canvas_w = frame_w * cols
    canvas_h = frame_h * rows
    master = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    base = apply_console_look(source, profile)

    manifest: Dict[str, Any] = {
        "meta": {
            "asset_name": asset_name,
            "target_console": console,
            "mode": mode,
            "frame_width": frame_w,
            "frame_height": frame_h,
            "total_width": canvas_w,
            "total_height": canvas_h,
            "angles": labels,
            "notes": profile.notes,
        },
        "frames": {},
    }

    for idx, label in enumerate(labels):
        r, c = divmod(idx, cols)
        pos_x = c * frame_w
        pos_y = r * frame_h

        if label == "top_down":
            # Simple top-down approximation: heavy downscale + slight blur
            view = base.copy()
            view = view.resize((frame_w // 2, frame_h // 2), Image.LANCZOS)
            view = view.resize((frame_w, frame_h), Image.NEAREST if profile.pixel_art else Image.LANCZOS)
            view = view.filter(ImageFilter.GaussianBlur(radius=1.0))
        else:
            angle = int(label.split("_")[1])
            view = generate_angle_view(base, angle, (frame_w, frame_h))

        master.paste(view, (pos_x, pos_y), view)
        manifest["frames"][label] = [{
            "frame_index": 0,
            "x": pos_x,
            "y": pos_y,
            "w": frame_w,
            "h": frame_h,
            "angle_deg": angle if label != "top_down" else -1,
        }]

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_console = console.replace(" ", "_").replace("/", "_").lower()
    png_name = f"{asset_name}_{safe_console}_atlas.png"
    json_name = f"{asset_name}_{safe_console}_atlas_meta.json"
    png_path = out_path / png_name
    json_path = out_path / json_name

    master.save(png_path, "PNG")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(png_path), str(json_path)


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------

class ConsoleAssetPipelineApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Console Asset Pipeline – Sprite / Atlas Generator")
        self.root.geometry("920x720")
        self.root.minsize(800, 600)

        self.source_image: Optional[Image.Image] = None
        self.source_path: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        # ---- Header ----
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Console Asset Pipeline", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="  Production-ready sprites & multi-angle atlases", font=("Segoe UI", 10)).pack(side=tk.LEFT)

        # ---- Main content ----
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Left column – inputs
        left = ttk.LabelFrame(main, text="Inputs", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Prompt
        ttk.Label(left, text="Core Asset Prompt (metadata):").pack(anchor=tk.W)
        self.prompt_var = tk.StringVar(value="sci-fi soldier")
        ttk.Entry(left, textvariable=self.prompt_var, width=36).pack(fill=tk.X, pady=(0, 8))

        # Source image
        ttk.Label(left, text="Source Image (required for quality):").pack(anchor=tk.W)
        img_row = ttk.Frame(left)
        img_row.pack(fill=tk.X, pady=(0, 8))
        self.img_label = ttk.Label(img_row, text="No image loaded", foreground="gray")
        self.img_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(img_row, text="Browse…", command=self._load_image).pack(side=tk.RIGHT)

        # Console
        ttk.Label(left, text="Target Console:").pack(anchor=tk.W)
        self.console_var = tk.StringVar(value="SNES / Genesis")
        console_cb = ttk.Combobox(left, textvariable=self.console_var,
                                  values=list(CONSOLE_PROFILES.keys()), state="readonly", width=34)
        console_cb.pack(fill=tk.X, pady=(0, 8))
        console_cb.bind("<<ComboboxSelected>>", self._on_console_change)

        # Mode
        ttk.Label(left, text="Animation / Rendering Mode:").pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value="2D / Sprite Sheet")
        mode_cb = ttk.Combobox(left, textvariable=self.mode_var, state="readonly", width=34,
                               values=[
                                   "2D / Sprite Sheet",
                                   "HD Sprite Sheet Array",
                                   "2.5D Atlas",
                                   "Multi-Angle 3D Workaround Sheet",
                               ])
        mode_cb.pack(fill=tk.X, pady=(0, 8))

        # Actions list
        ttk.Label(left, text="Animation states (comma-separated):").pack(anchor=tk.W)
        self.actions_text = scrolledtext.ScrolledText(left, height=4, width=36, wrap=tk.WORD)
        self.actions_text.pack(fill=tk.X, pady=(0, 8))
        self.actions_text.insert(tk.END, DEFAULT_ACTIONS)

        # Frames per action
        fr_row = ttk.Frame(left)
        fr_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(fr_row, text="Frames per action:").pack(side=tk.LEFT)
        self.frames_var = tk.IntVar(value=4)
        ttk.Spinbox(fr_row, from_=1, to=16, textvariable=self.frames_var, width=5).pack(side=tk.RIGHT)

        # Options
        self.remove_bg_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Remove background (if possible)", variable=self.remove_bg_var).pack(anchor=tk.W)

        # Generate button
        ttk.Button(left, text="▶  Generate Assets", command=self._generate).pack(fill=tk.X, pady=12)

        # Right column – log + preview info
        right = ttk.LabelFrame(main, text="Output Log & Console Rules", padding=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log = scrolledtext.ScrolledText(right, height=28, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        self._log("Ready. Load a source image (the static character) then press Generate.\n")
        self._on_console_change()

    def _log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def _on_console_change(self, event=None):
        name = self.console_var.get()
        p = CONSOLE_PROFILES[name]
        self.frames_var.set(p.default_frames_per_action)
        self._log(f"Console selected → {name}")
        self._log(f"  Max frame size : {p.max_frame_w}×{p.max_frame_h}")
        self._log(f"  Palette limit  : {'unlimited' if p.max_colors == 0 else p.max_colors}")
        self._log(f"  Filter style   : {p.filter_style}  |  Pixel-art: {p.pixel_art}")
        self._log(f"  Notes          : {p.notes}\n")

    def _load_image(self):
        path = filedialog.askopenfilename(
            title="Select source character image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            img = Image.open(path)
            self.source_image = img
            self.source_path = path
            self.img_label.configure(text=Path(path).name, foreground="black")
            self._log(f"Loaded source: {path}  ({img.size[0]}×{img.size[1]}, {img.mode})")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _generate(self):
        if self.source_image is None:
            messagebox.showwarning("Missing image", "Please load a source character image first.")
            return

        prompt = self.prompt_var.get().strip() or "asset"
        # Sanitise asset name
        asset_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt)[:40]
        console = self.console_var.get()
        mode = self.mode_var.get()
        actions_raw = self.actions_text.get("1.0", tk.END).strip()
        actions = [a.strip() for a in actions_raw.split(",") if a.strip()]
        if not actions:
            actions = ["idle"]
        frames = max(1, self.frames_var.get())

        self._log("=" * 50)
        self._log(f"Generating: {asset_name}  |  {console}  |  {mode}")
        self._log(f"Actions   : {actions}")
        self._log(f"Frames/act: {frames}")

        # Prepare source
        src = self.source_image.copy()
        if self.remove_bg_var.get():
            self._log("Removing background…")
            src = remove_background_safe(src)

        out_dir = str(Path.cwd() / "pipeline_output")
        try:
            if mode in ("2D / Sprite Sheet", "HD Sprite Sheet Array"):
                # HD mode simply uses the same pipeline; higher-end consoles already have larger frames
                png, js = create_sprite_sheet(
                    source=src,
                    asset_name=asset_name,
                    console=console,
                    actions=actions,
                    frames_per_action=frames,
                    mode=mode,
                    out_dir=out_dir,
                )
            else:
                # 2.5D / Multi-Angle
                png, js = create_multi_angle_atlas(
                    source=src,
                    asset_name=asset_name,
                    console=console,
                    mode=mode,
                    out_dir=out_dir,
                )

            self._log(f"✔ PNG  → {png}")
            self._log(f"✔ JSON → {js}")
            self._log("Done. Drop the PNG + JSON into your engine (Raylib, Godot, Unity, etc.).\n")
            messagebox.showinfo("Success", f"Assets written to:\n{png}\n{js}")
        except Exception as e:
            self._log(f"ERROR: {e}")
            messagebox.showerror("Generation failed", str(e))


# ---------------------------------------------------------------------------
# CLI entry point (also usable without GUI)
# ---------------------------------------------------------------------------

def run_cli_example():
    """Quick non-GUI test that mirrors the sample the user provided."""
    # Create a simple placeholder source if none exists
    src = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(src)
    draw.ellipse([20, 10, 108, 100], fill=(80, 140, 220, 255))
    draw.rectangle([50, 90, 78, 120], fill=(60, 100, 180, 255))

    actions = ["idle", "walk", "run", "punch", "kick"]
    png, js = create_sprite_sheet(
        source=src,
        asset_name="hero_character",
        console="SNES / Genesis",
        actions=actions,
        frames_per_action=4,
        out_dir="pipeline_output",
    )
    print(f"CLI test → {png}\n          {js}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli-test":
        run_cli_example()
    else:
        root = tk.Tk()
        # Use a reasonably modern theme if available
        try:
            style = ttk.Style()
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass
        app = ConsoleAssetPipelineApp(root)
        root.mainloop()
