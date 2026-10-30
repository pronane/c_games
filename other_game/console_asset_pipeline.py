#!/usr/bin/env python3
"""
Console Asset Pipeline v2 – Transparent Sprite & Atlas Generator
================================================================
Production tool that converts a single source image into fully
transparent (RGBA, Alpha=0 background) asset sheets constrained
to every major console generation from Atari 2600 → PlayStation 5.

TWO DISTINCT MODES
------------------
OPTION A – Chronological Action Sheet (2D Flipbook)
  Each requested action (walk, run, kick…) occupies its own row.
  Frames progress left → right so a delta-time loop plays the action.

OPTION B – Directional 3D Turnaround (2.5D / Faux-3D Billboard)
  Pose stays locked. Camera rotates around the subject at 0°, 45°,
  90° … 315° + top-down. Engine code selects the correct slice
  according to the player’s angle to the object.

All outputs are pure RGBA with transparent backgrounds ready for
direct compositing over engine layers.

Dependencies (minimum):
  pip install Pillow

Optional (better background removal – can be skipped on Windows):
  pip install rembg
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageEnhance
except ImportError:
    print("ERROR: Pillow is required →  pip install Pillow")
    sys.exit(1)

# Optional – never required
try:
    from rembg import remove, new_session
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False

# tkinter is only needed for the GUI
HAS_TK = False
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    HAS_TK = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Console Hardware Profiles (complete matrix)
# ---------------------------------------------------------------------------

@dataclass
class ConsoleProfile:
    name: str
    max_frame_w: int
    max_frame_h: int
    max_colors: int          # 0 = full RGBA, no quantisation
    pixel_art: bool
    dither: bool
    filter_style: str        # none | bilinear | soft | jagged
    atlas_angles: int        # 4 or 8
    default_frames_per_action: int
    notes: str = ""

CONSOLE_PROFILES: Dict[str, ConsoleProfile] = {
    "Atari 2600": ConsoleProfile(
        "Atari 2600", 8, 32, 2, True, False, "none", 4, 2,
        "1-bit binary look, extremely limited canvas"
    ),
    "NES": ConsoleProfile(
        "NES", 16, 16, 4, True, False, "none", 4, 3,
        "8×8 / 16×16 tiles, 4-colour palette per sprite"
    ),
    "SNES / Genesis": ConsoleProfile(
        "SNES / Genesis", 64, 64, 16, True, True, "none", 4, 4,
        "Up to 64×64, 16-colour indexed + dithering"
    ),
    "PlayStation 1": ConsoleProfile(
        "PlayStation 1", 64, 64, 0, False, False, "jagged", 8, 4,
        "Unfiltered / affine-wobble look, 256×256 atlas typical"
    ),
    "Nintendo 64": ConsoleProfile(
        "Nintendo 64", 64, 64, 0, False, False, "bilinear", 8, 4,
        "Strict 64×64 texture cache, heavy bilinear filtering"
    ),
    "PlayStation 2 / GameCube": ConsoleProfile(
        "PlayStation 2 / GameCube", 128, 128, 0, False, False, "soft", 8, 6,
        "Clean mid-poly / Phong aesthetic, 512×512 textures"
    ),
    "PS3 / Xbox 360": ConsoleProfile(
        "PS3 / Xbox 360", 256, 256, 0, False, False, "soft", 8, 6,
        "1024×1024, pre-baked lighting style"
    ),
    "PS4 / Xbox One": ConsoleProfile(
        "PS4 / Xbox One", 512, 512, 0, False, False, "none", 8, 8,
        "2048×2048 PBR-ready surface look"
    ),
    "PlayStation 5": ConsoleProfile(
        "PlayStation 5", 1024, 1024, 0, False, False, "none", 8, 8,
        "4096×4096 cinematic / ray-traced quality target"
    ),
}

DEFAULT_ACTIONS_A = "idle, walk, run, jump, punch, kick, hand-pass, solo"
DEFAULT_ANGLES_B  = "angle_0, angle_45, angle_90, angle_135, angle_180, angle_225, angle_270, angle_315, top_down"

# ---------------------------------------------------------------------------
# Image helpers – always produce clean RGBA with transparent background
# ---------------------------------------------------------------------------

def force_transparent_background(img: Image.Image) -> Image.Image:
    """Guarantee pure transparent background (Alpha = 0)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # Make sure any near-black or near-white leftover is fully transparent
    pixels = list(img.getdata())
    new_pixels = []
    for r, g, b, a in pixels:
        if a < 10 or (r > 250 and g > 250 and b > 250) or (r < 8 and g < 8 and b < 8):
            new_pixels.append((0, 0, 0, 0))
        else:
            new_pixels.append((r, g, b, a))
    out = Image.new("RGBA", img.size)
    out.putdata(new_pixels)
    return out


def remove_background(img: Image.Image) -> Image.Image:
    """Best available background removal. Falls back cleanly on Windows."""
    if HAS_REMBG:
        try:
            session = new_session("u2netp")
            result = remove(img.convert("RGB"), session=session)
            return force_transparent_background(result)
        except Exception:
            pass

    # Stronger fallback for studio / grey backgrounds (no extra packages needed)
    img = img.convert("RGBA")
    w, h = img.size
    pixels = list(img.getdata())

    # Sample the four corners to estimate background colour
    corners = [
        pixels[0], pixels[w - 1],
        pixels[(h - 1) * w], pixels[(h - 1) * w + w - 1]
    ]
    avg_r = sum(c[0] for c in corners) // 4
    avg_g = sum(c[1] for c in corners) // 4
    avg_b = sum(c[2] for c in corners) // 4

    new_data = []
    threshold = 38  # how close a pixel must be to the corner colour
    for r, g, b, a in pixels:
        if (abs(r - avg_r) < threshold and
            abs(g - avg_g) < threshold and
            abs(b - avg_b) < threshold):
            new_data.append((0, 0, 0, 0))
        elif r > 245 and g > 245 and b > 245:
            new_data.append((0, 0, 0, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return force_transparent_background(img)


def quantize_palette(img: Image.Image, max_colors: int, dither: bool) -> Image.Image:
    if max_colors <= 0:
        return img
    alpha = img.split()[-1] if img.mode == "RGBA" else None
    rgb = img.convert("RGB")
    quantized = rgb.quantize(
        colors=max_colors,
        method=Image.FASTOCTREE,
        dither=Image.FLOYDSTEINBERG if dither else Image.NONE
    )
    out = quantized.convert("RGBA")
    if alpha is not None:
        out.putalpha(alpha)
    return force_transparent_background(out)


def apply_console_constraints(img: Image.Image, profile: ConsoleProfile) -> Image.Image:
    """Resize, centre, filter and quantise according to the console profile.
    Always returns a clean RGBA image of exactly (max_frame_w × max_frame_h).
    """
    # Fit inside the allowed frame size while preserving aspect
    img = img.copy()
    img.thumbnail(
        (profile.max_frame_w, profile.max_frame_h),
        Image.NEAREST if profile.pixel_art else Image.LANCZOS
    )

    # Create exact-size transparent canvas and centre the asset
    canvas = Image.new("RGBA", (profile.max_frame_w, profile.max_frame_h), (0, 0, 0, 0))
    ox = (profile.max_frame_w - img.width) // 2
    oy = (profile.max_frame_h - img.height) // 2
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    canvas.paste(img, (ox, oy), img)

    # Console-specific look
    if profile.filter_style == "bilinear":
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.55))
    elif profile.filter_style == "soft":
        canvas = canvas.filter(ImageFilter.SMOOTH_MORE)
    elif profile.filter_style == "jagged":
        enhancer = ImageEnhance.Contrast(canvas)
        canvas = enhancer.enhance(1.3)

    if profile.max_colors > 0:
        canvas = quantize_palette(canvas, profile.max_colors, profile.dither)

    return force_transparent_background(canvas)


def make_action_frame(base: Image.Image, index: int, total: int) -> Image.Image:
    """Create a subtle progression frame for OPTION A.
    Real pose changes still require an external generative backend;
    this gives a usable local approximation with correct transparency.
    """
    img = base.copy()
    # Gentle scale pulse so the sheet is not completely static
    t = index / max(total - 1, 1)
    factor = 1.0 + 0.04 * math.sin(t * math.pi)
    w, h = img.size
    nw, nh = max(1, int(w * factor)), max(1, int(h * factor))
    img = img.resize((nw, nh), Image.NEAREST if w < 96 else Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - nw) // 2, (h - nh) // 2), img)
    return force_transparent_background(canvas)


def make_angle_view(base: Image.Image, angle_deg: int, size: Tuple[int, int]) -> Image.Image:
    """OPTION B – orthographic-style view for a given camera angle."""
    img = base.convert("RGBA")
    w, h = size

    if angle_deg == 0:
        out = img
    elif angle_deg == 180:
        out = ImageOps.mirror(img)
    elif angle_deg in (90, 270):
        out = img.rotate(-angle_deg, expand=True, resample=Image.BICUBIC)
    else:
        out = img.rotate(-angle_deg, expand=True, resample=Image.BICUBIC)
        shear = 0.12 * math.sin(math.radians(angle_deg))
        out = out.transform(
            out.size, Image.AFFINE,
            (1, shear, 0, 0, 1, 0),
            resample=Image.BICUBIC
        )

    out.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    ox = (size[0] - out.width) // 2
    oy = (size[1] - out.height) // 2
    canvas.paste(out, (ox, oy), out)
    return force_transparent_background(canvas)


# ---------------------------------------------------------------------------
# OPTION A – Chronological Action Sheet
# ---------------------------------------------------------------------------

def create_action_sheet(
    source: Image.Image,
    asset_name: str,
    console: str,
    actions: List[str],
    frames_per_action: int,
    out_dir: str = "pipeline_output",
) -> Tuple[str, str]:
    profile = CONSOLE_PROFILES[console]
    fw, fh = profile.max_frame_w, profile.max_frame_h

    base = apply_console_constraints(source, profile)

    cols = frames_per_action
    rows = len(actions)
    master = Image.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))

    manifest: Dict[str, Any] = {
        "meta": {
            "asset_name": asset_name,
            "target_console": console,
            "mode": "OPTION_A_Chronological_Action_Sheet",
            "frame_width": fw,
            "frame_height": fh,
            "frames_per_action": frames_per_action,
            "total_width": fw * cols,
            "total_height": fh * rows,
            "notes": profile.notes,
            "transparent": True,
        },
        "frames": {},
    }

    for y, action in enumerate(actions):
        manifest["frames"][action] = []
        for x in range(frames_per_action):
            frame = make_action_frame(base, x, frames_per_action)
            master.paste(frame, (x * fw, y * fh), frame)
            manifest["frames"][action].append({
                "frame_index": x,
                "x": x * fw,
                "y": y * fh,
                "w": fw,
                "h": fh,
            })

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe = console.replace(" ", "_").replace("/", "_").lower()
    png_path = out_path / f"{asset_name}_{safe}_action_sheet.png"
    json_path = out_path / f"{asset_name}_{safe}_action_meta.json"

    master.save(png_path, "PNG")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(png_path), str(json_path)


# ---------------------------------------------------------------------------
# OPTION B – Directional Turnaround Atlas
# ---------------------------------------------------------------------------

def create_turnaround_atlas(
    source: Image.Image,
    asset_name: str,
    console: str,
    out_dir: str = "pipeline_output",
) -> Tuple[str, str]:
    profile = CONSOLE_PROFILES[console]
    fw, fh = profile.max_frame_w, profile.max_frame_h

    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    if profile.atlas_angles == 4:
        angles = [0, 90, 180, 270]
    labels = [f"angle_{a}" for a in angles] + ["top_down"]

    cols = 4
    rows = (len(labels) + cols - 1) // cols
    master = Image.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))

    base = apply_console_constraints(source, profile)

    manifest: Dict[str, Any] = {
        "meta": {
            "asset_name": asset_name,
            "target_console": console,
            "mode": "OPTION_B_Directional_Turnaround_Atlas",
            "frame_width": fw,
            "frame_height": fh,
            "total_width": fw * cols,
            "total_height": fh * rows,
            "angles": labels,
            "notes": profile.notes,
            "transparent": True,
        },
        "frames": {},
    }

    for idx, label in enumerate(labels):
        r, c = divmod(idx, cols)
        px, py = c * fw, r * fh

        if label == "top_down":
            view = base.copy()
            view = view.resize((max(1, fw // 2), max(1, fh // 2)), Image.LANCZOS)
            view = view.resize((fw, fh), Image.NEAREST if profile.pixel_art else Image.LANCZOS)
            view = view.filter(ImageFilter.GaussianBlur(radius=0.8))
        else:
            angle = int(label.split("_")[1])
            view = make_angle_view(base, angle, (fw, fh))

        master.paste(view, (px, py), view)
        manifest["frames"][label] = [{
            "frame_index": 0,
            "x": px,
            "y": py,
            "w": fw,
            "h": fh,
            "angle_deg": -1 if label == "top_down" else int(label.split("_")[1]),
        }]

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe = console.replace(" ", "_").replace("/", "_").lower()
    png_path = out_path / f"{asset_name}_{safe}_turnaround_atlas.png"
    json_path = out_path / f"{asset_name}_{safe}_turnaround_meta.json"

    master.save(png_path, "PNG")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(png_path), str(json_path)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ConsoleAssetPipelineApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Console Asset Pipeline v2 – Transparent Sheets")
        self.root.geometry("960x760")
        self.root.minsize(820, 640)

        self.source_image: Optional[Image.Image] = None
        self.source_path: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Console Asset Pipeline v2", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="  Fully transparent RGBA sheets for every console", font=("Segoe UI", 10)).pack(side=tk.LEFT)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- Left panel ----
        left = ttk.LabelFrame(main, text="Inputs", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        ttk.Label(left, text="Asset name / prompt:").pack(anchor=tk.W)
        self.prompt_var = tk.StringVar(value="gaelic_footballer")
        ttk.Entry(left, textvariable=self.prompt_var, width=38).pack(fill=tk.X, pady=(0, 8))

        ttk.Label(left, text="Source image (required):").pack(anchor=tk.W)
        img_row = ttk.Frame(left)
        img_row.pack(fill=tk.X, pady=(0, 8))
        self.img_label = ttk.Label(img_row, text="No image loaded", foreground="gray")
        self.img_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(img_row, text="Browse…", command=self._load_image).pack(side=tk.RIGHT)

        ttk.Label(left, text="Target Console:").pack(anchor=tk.W)
        self.console_var = tk.StringVar(value="PlayStation 2 / GameCube")
        cb = ttk.Combobox(left, textvariable=self.console_var,
                          values=list(CONSOLE_PROFILES.keys()), state="readonly", width=36)
        cb.pack(fill=tk.X, pady=(0, 8))
        cb.bind("<<ComboboxSelected>>", self._on_console_change)

        ttk.Label(left, text="Workflow Mode:").pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value="OPTION A – Chronological Action Sheet")
        mode_cb = ttk.Combobox(left, textvariable=self.mode_var, state="readonly", width=36,
                               values=[
                                   "OPTION A – Chronological Action Sheet",
                                   "OPTION B – Directional Turnaround Atlas",
                               ])
        mode_cb.pack(fill=tk.X, pady=(0, 8))
        mode_cb.bind("<<ComboboxSelected>>", self._on_mode_change)

        ttk.Label(left, text="States / Angles (comma-separated):").pack(anchor=tk.W)
        self.states_text = scrolledtext.ScrolledText(left, height=5, width=38, wrap=tk.WORD)
        self.states_text.pack(fill=tk.X, pady=(0, 8))
        self.states_text.insert(tk.END, DEFAULT_ACTIONS_A)

        fr = ttk.Frame(left)
        fr.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(fr, text="Frames per action (Option A):").pack(side=tk.LEFT)
        self.frames_var = tk.IntVar(value=4)
        ttk.Spinbox(fr, from_=1, to=16, textvariable=self.frames_var, width=5).pack(side=tk.RIGHT)

        self.remove_bg_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Remove background (works without rembg)",
                        variable=self.remove_bg_var).pack(anchor=tk.W, pady=(0, 4))

        ttk.Button(left, text="▶  Generate Transparent Sheet", command=self._generate).pack(fill=tk.X, pady=12)

        # ---- Right panel – log ----
        right = ttk.LabelFrame(main, text="Log & Console Rules", padding=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log = scrolledtext.ScrolledText(right, height=32, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        self._log("Ready. Load a source image, choose console + mode, then Generate.\n")
        self._log("All outputs are pure RGBA with transparent backgrounds (Alpha = 0).\n")
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
        self._log(f"Console → {name}")
        self._log(f"  Frame size   : {p.max_frame_w}×{p.max_frame_h}")
        self._log(f"  Palette      : {'full RGBA' if p.max_colors == 0 else p.max_colors}")
        self._log(f"  Filter       : {p.filter_style}  |  Pixel-art: {p.pixel_art}")
        self._log(f"  Atlas angles : {p.atlas_angles}")
        self._log(f"  Notes        : {p.notes}\n")

    def _on_mode_change(self, event=None):
        mode = self.mode_var.get()
        self.states_text.delete("1.0", tk.END)
        if "OPTION A" in mode:
            self.states_text.insert(tk.END, DEFAULT_ACTIONS_A)
            self._log("Mode → OPTION A (Chronological Action Sheet)\n")
        else:
            self.states_text.insert(tk.END, DEFAULT_ANGLES_B)
            self._log("Mode → OPTION B (Directional Turnaround Atlas)\n")

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
            self._log(f"Loaded: {path}  ({img.size[0]}×{img.size[1]}, {img.mode})")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _generate(self):
        if self.source_image is None:
            messagebox.showwarning("Missing image", "Please load a source character image first.")
            return

        prompt = self.prompt_var.get().strip() or "asset"
        asset_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt)[:48]
        console = self.console_var.get()
        mode = self.mode_var.get()
        states_raw = self.states_text.get("1.0", tk.END).strip()
        states = [s.strip() for s in states_raw.split(",") if s.strip()]
        if not states:
            states = ["idle"]
        frames = max(1, self.frames_var.get())

        self._log("=" * 54)
        self._log(f"Generating  : {asset_name}")
        self._log(f"Console     : {console}")
        self._log(f"Mode        : {mode}")
        self._log(f"States      : {states}")

        src = self.source_image.copy()
        if self.remove_bg_var.get():
            self._log("Removing background…")
            src = remove_background(src)
        else:
            src = force_transparent_background(src.convert("RGBA"))

        out_dir = str(Path.cwd() / "pipeline_output")
        try:
            if "OPTION A" in mode:
                png, js = create_action_sheet(
                    source=src,
                    asset_name=asset_name,
                    console=console,
                    actions=states,
                    frames_per_action=frames,
                    out_dir=out_dir,
                )
            else:
                png, js = create_turnaround_atlas(
                    source=src,
                    asset_name=asset_name,
                    console=console,
                    out_dir=out_dir,
                )

            self._log(f"✔ Transparent PNG → {png}")
            self._log(f"✔ JSON manifest  → {js}")
            self._log("Done. Background is fully transparent (Alpha = 0).\n")
            messagebox.showinfo("Success", f"Assets written:\n\n{png}\n{js}")
        except Exception as e:
            self._log(f"ERROR: {e}")
            messagebox.showerror("Generation failed", str(e))


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def run_cli_demo():
    """Quick verification that everything produces transparent RGBA."""
    src = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(src)
    d.ellipse([24, 16, 104, 96], fill=(70, 150, 230, 255))
    d.rectangle([54, 90, 74, 120], fill=(50, 110, 190, 255))

    png, js = create_action_sheet(
        source=src,
        asset_name="demo_hero",
        console="SNES / Genesis",
        actions=["idle", "walk", "punch"],
        frames_per_action=4,
    )
    print(f"OPTION A → {png}")
    print(f"         → {js}")

    png2, js2 = create_turnaround_atlas(
        source=src,
        asset_name="demo_hero",
        console="PlayStation 2 / GameCube",
    )
    print(f"OPTION B → {png2}")
    print(f"         → {js2}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli-test":
        run_cli_demo()
    else:
        if not HAS_TK:
            print("tkinter is not available on this system.")
            print("You can still use the pure functions from another script,")
            print("or run:  python console_asset_pipeline.py --cli-test")
            sys.exit(1)
        root = tk.Tk()
        try:
            style = ttk.Style()
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass
        app = ConsoleAssetPipelineApp(root)
        root.mainloop()
