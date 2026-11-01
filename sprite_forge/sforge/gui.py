"""Sprite Forge Studio - visual tool (tkinter + Pillow, no other deps).

Adaptive UI: pick an INPUT MODE and only the fields that mode needs are shown. Every field has a (?) tooltip.
Help tab / Help menu with beginner docs (same text as HELP.md and `forge.py help`), an Example walkthrough,
console target presets (NES ... PS5). The same core as `forge.py build` is used."""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk

from . import __version__, helptext, consoles
from .moves import PRESETS, MoveSpec, preset, slug
from .motions import LIB
from .mesh import KITS
from .build import BuildConfig, build, checker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODES = [("photo", "Photo (own pixels)", "Your photo -> idle with your real pixels; other moves are labelled placeholder transforms."),
         ("frames", "Frames folder", "A folder of frames you made elsewhere: walk/01.png ... or walk_01.png ..."),
         ("movesheets", "Per-move sheets", "One strip image per move (a row of that move's frames)."),
         ("sheet", "Sprite sheet", "One big sheet with every move: one row per move (or one cell per move)."),
         ("spec", "Text spec (fictional)", "A key=value text file describing a made-up character -> 3D mannequin + model.glb/.fbx."),
         ("mannequin", "Gaelic / 3D mannequin", "No input: the default no-likeness mannequin in a team kit (+ 3D models)."),
         ("video", "Video -> sprites", "Your own clips (one per move): frames are cut out, looped / trimmed, slowed down and laid out as sprites."),
         ("mocap", "Video -> mocap (3D)", "Your own clips -> body pose tracking -> the 3D mannequin performs the move (GLB/FBX + sprites). Needs mediapipe (Help > Video to mocap)."),
         ("library", "Library rig (FBX/GLB)", "A rig from your library (Library tab) or any FBX / GLB file: its own mesh, bones and clips are the template; missing moves are retargeted (Help > Library)."),
         ("scan", "Orbit video -> 3D mesh", "A walk-around video of a STILL object -> photogrammetry project / CPU mesh -> console LODs. Guided, not one-click.")]
MODE_LABEL = {k: l for k, l, _ in MODES}
IMPORT = {"photo", "frames", "movesheets", "sheet"}
THREE_D = {"spec", "mannequin", "library"}
MANNEQUIN_3D = {"spec", "mannequin"}
OWN_COLOURS = "(own colours)"
CLI_MODES = {"video", "mocap", "scan"}      # run through forge.py video / mocap / scan in a subprocess
NO_CONSOLE = "None (standard output only)"
NO_PROFILE = "(none)"
# v8 TURN: photo puppet seen from another angle (sforge/turn.py)
TURN_CHOICES = ["0  front (as photographed)", "90  side-on, faces right", "180  back", "270  left side (mirrored to face right)"]


def turn_value(choice, fine=""):
    """'90  side-on...' (+ optional fine angle text) -> degrees"""
    if str(fine).strip():
        return float(fine)
    t = str(choice).strip().split()
    try:
        return float(t[0]) if t else 0.0
    except ValueError:
        from .turn import turn_args
        return turn_args(t[0])


class Tooltip:
    def __init__(self, widget, text):
        self.w, self.text, self.tip, self.job = widget, text, None, None
        widget.bind("<Enter>", lambda e: self._sched()); widget.bind("<Leave>", lambda e: self.hide())
        widget.bind("<Button-1>", lambda e: self.show())

    def _sched(self):
        self.job = self.w.after(350, self.show)

    def show(self):
        if self.tip:
            return
        x, y = self.w.winfo_rootx() + 18, self.w.winfo_rooty() + 18
        self.tip = tk.Toplevel(self.w); self.tip.wm_overrideredirect(True); self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify=tk.LEFT, background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                 wraplength=360, padx=6, pady=4).pack()

    def hide(self):
        if self.job:
            self.w.after_cancel(self.job); self.job = None
        if self.tip:
            self.tip.destroy(); self.tip = None


class Studio:
    def __init__(self, root):
        self.root = root
        root.title("Sprite Forge Studio %s" % __version__)
        root.geometry("1400x880")
        self.q = queue.Queue()
        self.rows = []
        self.result = None
        self.autotest = False
        self.anim_frames = []; self.anim_i = 0; self.anim_job = None
        self.v = {k: tk.StringVar(value=val) for k, val in dict(
            mode="spec", name="hero", spec="", photo="", back="", videos="", frames="", sheet="", layout="rows", grid="",
            movesheets="", across="", kit="home", kits="", out="out", fw="256", fh="256", figh="", ground="", yaw="65",
            cutout="auto", fill="placeholder", blender="", preset=list(PRESETS)[0], cname="", cmotion="idle", height="",
            prop="auto", console=NO_CONSOLE, side="", view34="", views="", view_cut="", profile=NO_PROFILE,
            pvars="", clips="", vcamera="auto", vbg="auto", slowmo="1", pmodel="full", orbit="", sframes="80",
            smesh="", sheight="", budgets="", rig="", root_motion="keep",
            msplit="auto", mslots="full", human="", outfits="", eprops="", slot_colors="",
            turn=TURN_CHOICES[0], turn_yaw="", turn_depth="auto", turn_side="", landmarks="", quality="final").items()}
        self.b = {k: tk.BooleanVar(value=val) for k, val in dict(flip=False, outline=True, glb=True, fbx=True, strips=False,
                                                                gifs=True, dither=True, side_left=False, srun=True,
                                                                anim_export=False, cache=True).items()}
        from .gui_style import install_vars
        install_vars(self)        # v9 style / extras settings
        self.field_rows = []      # (widgets, modes)
        self._build_ui()
        from .gui_library import LibraryTab
        self.libtab = LibraryTab(self, self.libtab_frame)
        self.load_preset()
        from .gui_home import HomeTab
        self.home = HomeTab(self, self.hometab)
        self.v["mode"].trace_add("write", lambda *a: self.apply_mode())
        self.v["console"].trace_add("write", lambda *a: self._console_info())
        self.b["fbx"].trace_add("write", lambda *a: self.apply_mode())
        self.apply_mode(); self._console_info()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------ layout
    def _q(self, parent, key):
        lab = tk.Label(parent, text="(?)", fg="#1a5fb4", cursor="question_arrow")
        Tooltip(lab, helptext.FIELD_HELP.get(key, key))
        return lab

    def _build_ui(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("H.TLabel", font=("Segoe UI", 11, "bold"))
        st.configure("Err.TLabel", foreground="#c01c28")
        # menu
        mb = tk.Menu(self.root)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="Save project...", command=self.save_project)
        fm.add_command(label="Load project...", command=self.load_project)
        fm.add_command(label="Open output folder", command=self.open_out)
        fm.add_separator(); fm.add_command(label="Quit", command=self.root.destroy)
        mb.add_cascade(label="File", menu=fm)
        hm = tk.Menu(mb, tearoff=0)
        for k, (title, _) in helptext.TOPICS.items():
            hm.add_command(label=title, command=lambda k=k: self.show_help(k))
        hm.add_separator(); hm.add_command(label="Example walkthrough (build the sample)", command=self.walkthrough)
        hm.add_command(label="Check setup (forge.py doctor)", command=self.show_doctor)
        hm.add_command(label="About", command=lambda: messagebox.showinfo("About", "Sprite Forge Studio %s" % __version__))
        from .gui_style import install_menu
        install_menu(self, mb)
        mb.add_cascade(label="Help", menu=hm)
        self.root.config(menu=mb)
        self.nb = ttk.Notebook(self.root); self.nb.pack(fill=tk.BOTH, expand=True)
        self.buildtab = buildtab = ttk.Frame(self.nb); self.helptab = helptab = ttk.Frame(self.nb); self.libtab_frame = ttk.Frame(self.nb)
        from .icons import tk_icon
        self.hometab = hometab = ttk.Frame(self.nb); self.nb.add(hometab, text=" Start  ", image=tk_icon("start"), compound=tk.LEFT)
        self.looktab = ttk.Frame(self.nb); self.nb.add(self.looktab, text=" Appearance  ", image=tk_icon("start"), compound=tk.LEFT)
        from .gui_appearance import AppearanceTab
        self.look = AppearanceTab(self, self.looktab)
        self.nb.add(buildtab, text=" Build (advanced)  ", image=tk_icon("build"), compound=tk.LEFT)
        self.nb.add(self.libtab_frame, text=" Library  ", image=tk_icon("library"), compound=tk.LEFT)
        self.nb.add(helptab, text=" Help  ", image=tk_icon("help"), compound=tk.LEFT)
        self._build_help(helptab)
        main = ttk.Frame(buildtab); main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        # left column scrolls (photo mode + multi-view + profile is taller than small screens)
        lwrap = ttk.Frame(main, width=490); lwrap.pack_propagate(False)
        self.left_canvas = lc = tk.Canvas(lwrap, highlightthickness=0, width=470)
        lsb = ttk.Scrollbar(lwrap, orient=tk.VERTICAL, command=lc.yview)
        left = ttk.Frame(lc)
        left.bind("<Configure>", lambda e: lc.configure(scrollregion=lc.bbox("all")))
        lc.create_window((0, 0), window=left, anchor="nw", width=468)
        lc.configure(yscrollcommand=lsb.set)
        lc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); lsb.pack(side=tk.RIGHT, fill=tk.Y)
        lc.bind("<Enter>", lambda e: lc.bind_all("<MouseWheel>", lambda ev: lc.yview_scroll(int(-ev.delta / 120), "units")))
        lc.bind("<Button-4>", lambda e: lc.yview_scroll(-3, "units")); lc.bind("<Button-5>", lambda e: lc.yview_scroll(3, "units"))
        mid = ttk.Frame(main, width=600); right = ttk.Frame(main, width=290)
        mid.pack_propagate(False)
        lwrap.pack(side=tk.LEFT, fill=tk.Y); ttk.Separator(main, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        mid.pack(side=tk.LEFT, fill=tk.Y); ttk.Separator(main, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- left: mode + fields
        ttk.Label(left, text="1. Input mode", style="H.TLabel").pack(anchor="w")
        mf = ttk.Frame(left); mf.pack(fill=tk.X)
        for i, (val, lab, _) in enumerate(MODES):
            ttk.Radiobutton(mf, text=lab, value=val, variable=self.v["mode"]).grid(row=i // 2, column=i % 2, sticky="w", padx=2)
        self.mode_desc = ttk.Label(left, text="", foreground="#444", wraplength=450, justify=tk.LEFT); self.mode_desc.pack(anchor="w", pady=(2, 4))
        g = ttk.Frame(left); g.pack(fill=tk.X); g.columnconfigure(1, weight=1)
        self._r = 0
        A = set(k for k, _, _ in MODES)

        def row(label, key, modes, kind="entry", values=None, help_key=None, browse=None, width=None):
            ws = [ttk.Label(g, text=label)]
            if kind == "combo":
                w = ttk.Combobox(g, textvariable=self.v[key], values=values, state="readonly", width=width or 22)
            elif kind == "check":
                w = ttk.Checkbutton(g, variable=self.b[key])
            else:
                w = ttk.Entry(g, textvariable=self.v[key], width=width or 26)
            ws.append(w)
            if browse:
                ws.append(ttk.Button(g, text="...", width=3, command=lambda: self._browse(key, browse)))
            else:
                ws.append(ttk.Frame(g))
            ws.append(self._q(g, help_key or label))
            for c, wd in enumerate(ws):
                wd.grid(row=self._r, column=c, sticky="we" if c == 1 and kind != "check" else "w", pady=1)
            self.field_rows.append((ws, set(modes)))
            self._r += 1

        row("Name", "name", A - {"spec"})
        row("Front photo *", "photo", {"photo"}, browse="image", help_key="Front photo")
        row("Side photo", "side", {"photo"}, browse="image", help_key="Side photo")
        row("Side faces left", "side_left", {"photo"}, "check", help_key="Side faces left")
        row("3/4 photo", "view34", {"photo"}, browse="image", help_key="3/4 photo")
        row("Back photo", "back", {"photo"}, browse="image", help_key="Back photo")
        row("Video/frames per move", "videos", {"photo"}, help_key="Video / frames per move")
        row("Frames folder *", "frames", {"frames"}, browse="dir", help_key="Frames folder")
        row("Per-move sheets *", "movesheets", {"movesheets"}, help_key="Per-move sheets")
        ws = [ttk.Frame(g), ttk.Button(g, text="Add strip... (pick a file, name its move)", command=self.add_strip), ttk.Frame(g), ttk.Frame(g)]
        for c, wd in enumerate(ws):
            wd.grid(row=self._r, column=c, sticky="w")
        self.field_rows.append((ws, {"movesheets"})); self._r += 1
        row("Frames across", "across", {"movesheets"}, width=6)
        row("Sprite sheet *", "sheet", {"sheet"}, browse="image", help_key="Sprite sheet")
        row("Sheet layout", "layout", {"sheet"}, "combo", ["rows", "cells"], width=8)
        row("Grid (RxC)", "grid", {"sheet"}, width=8, help_key="Grid")
        row("Spec file *", "spec", {"spec"}, browse="spec", help_key="Spec file")
        sb = ttk.Frame(g)
        ttk.Button(sb, text="New spec from template...", command=self.new_spec).pack(side=tk.LEFT)
        ttk.Button(sb, text="Edit spec...", command=lambda: self.spec_editor(self.v["spec"].get())).pack(side=tk.LEFT, padx=4)
        ws = [ttk.Frame(g), sb, ttk.Frame(g), ttk.Frame(g)]
        for c, wd in enumerate(ws):
            wd.grid(row=self._r, column=c, sticky="w")
        self.field_rows.append((ws, {"spec"})); self._r += 1
        row("Clips (move:frames=file) *", "clips", {"video", "mocap"}, help_key="Clips")
        ws = [ttk.Frame(g), ttk.Button(g, text="Add clip... (pick a video, name its move)", command=self.add_clip), ttk.Frame(g), ttk.Frame(g)]
        for c, wd in enumerate(ws):
            wd.grid(row=self._r, column=c, sticky="w")
        self.field_rows.append((ws, {"video", "mocap"})); self._r += 1
        row("Camera", "vcamera", {"video"}, "combo", ["auto", "static", "handheld", "tracking"], width=10, help_key="Video camera")
        row("Background", "vbg", {"video"}, "combo", ["auto", "median", "plate", "chroma", "rembg"], width=10, help_key="Video background")
        row("Slow motion x", "slowmo", {"video"}, width=6, help_key="Slow motion")
        row("Pose model", "pmodel", {"mocap"}, "combo", ["lite", "full", "heavy"], width=8, help_key="Pose model")
        row("Orbit video", "orbit", {"scan"}, browse="video", help_key="Orbit video")
        row("Frames to extract", "sframes", {"scan"}, width=6, help_key="Scan frames")
        row("Run COLMAP + mesh", "srun", {"scan"}, "check", help_key="Run COLMAP")
        row("...or finished mesh", "smesh", {"scan"}, browse="mesh", help_key="Scan mesh")
        row("Real height (m)", "sheight", {"scan"}, width=6, help_key="Scan height")
        row("Triangle budgets", "budgets", {"scan"}, width=26, help_key="Scan budgets")
        row("Library rig *", "rig", {"library"}, "combo", [], width=24, help_key="Library rig", browse="rigfile")
        self.rig_cb = self.field_rows[-1][0][1]; self.rig_cb.configure(state="normal")
        row("Kit", "kit", THREE_D, "combo", list(KITS), width=16)
        self.kit_cb = self.field_rows[-1][0][1]
        row("Extra kits (3D)", "kits", {"mannequin", "library"}, width=18, help_key="Extra kits")
        row("MakeHuman body", "human", {"mannequin"}, "combo", ["", "gender=1,age=25,muscle=0.5,weight=0.5,height=0.5,skeleton=game_engine",
            "gender=0,age=25,muscle=0.5,weight=0.5,height=0.5,skeleton=game_engine", "gender=1,age=30,muscle=0.8,weight=0.4,height=0.6,skeleton=body",
            "gender=0.5,age=10,skeleton=body"], width=26, help_key="MakeHuman body")
        self.human_cb = self.field_rows[-1][0][1]; self.human_cb.configure(state="normal")
        row("Root motion (3D)", "root_motion", {"library"}, "combo", ["keep", "inplace", "root"], width=8, help_key="Root motion")
        # v7: material slots, separate animation files, equipment
        row("Material split", "msplit", THREE_D, "combo", ["auto", "off"], width=8, help_key="Material split")
        row("Material slots", "mslots", THREE_D, "combo", ["full", "core4", "keep"], width=8, help_key="Material slots")
        row("Separate anim files", "anim_export", THREE_D, "check", help_key="Separate anim files")
        row("Outfits (equip)", "outfits", THREE_D, width=26, help_key="Outfits")
        row("Props (equip)", "eprops", THREE_D, width=26, help_key="Props")
        row("Slot colours", "slot_colors", THREE_D, width=26, help_key="Slot colours")
        ws = [ttk.Frame(g), ttk.Button(g, text="Equip... (outfits + props)", command=self.equip_dialog), ttk.Frame(g), ttk.Frame(g)]
        for c, wd in enumerate(ws):
            wd.grid(row=self._r, column=c, sticky="w")
        self.field_rows.append((ws, THREE_D)); self._r += 1
        row("Camera yaw", "yaw", THREE_D, width=6)
        row("Kart prop", "prop", MANNEQUIN_3D, "combo", ["auto", "kart", "none"], width=8)
        row("Cutout", "cutout", IMPORT, "combo", ["auto", "alpha", "rembg", "threshold", "none"], width=10)
        row("Flip to face right", "flip", IMPORT | {"video"}, "check", help_key="Flip")
        row("Height cm", "height", {"photo", "frames"}, width=6)
        row("Missing moves", "fill", IMPORT, "combo", ["placeholder", "static", "mannequin", "skip", "puppet"], width=12)
        row("Pose landmarks", "landmarks", {"photo"}, browse="json", help_key="Pose landmarks")
        row("Turn (view)", "turn", {"photo"}, "combo", TURN_CHOICES, width=30, help_key="Turn")
        row("Turn angle (fine)", "turn_yaw", {"photo"}, width=6, help_key="Turn angle")
        row("Turn depth", "turn_depth", {"photo"}, "combo", ["auto", "template", "relief", "side"], width=10, help_key="Turn depth")
        row("Turn side reference", "turn_side", {"photo"}, browse="image", help_key="Turn side reference")
        g.columnconfigure(1, weight=1)
        vw = [ttk.Label(g, text="Output views"), ttk.Combobox(g, textvariable=self.v["views"], width=24,
              values=["", "front,back", "front,right,back", "front,right,back,left", "billboard8"]), ttk.Frame(g), self._q(g, "Output views")]
        for c, wd in enumerate(vw):
            wd.grid(row=self._r, column=c, sticky="we" if c == 1 else "w", pady=1)
        self.field_rows.append((vw, A - CLI_MODES)); self._r += 1
        row("View cut (0-1)", "view_cut", A - CLI_MODES, width=6, help_key="View cut")

        ttk.Label(left, text="2. Output", style="H.TLabel").pack(anchor="w", pady=(6, 0))
        pf0 = ttk.Frame(left); pf0.pack(fill=tk.X)
        ttk.Label(pf0, text="Profile").pack(side=tk.LEFT)
        self.profile_cb = ttk.Combobox(pf0, textvariable=self.v["profile"], values=self._profile_names(), state="readonly", width=20)
        self.profile_cb.pack(side=tk.LEFT, padx=3)
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_profile())
        self._q(pf0, "Profile").pack(side=tk.LEFT)
        ttk.Button(pf0, text="Create profile...", command=self.create_profile_dialog).pack(side=tk.LEFT, padx=4)
        pf1 = ttk.Frame(left); pf1.pack(fill=tk.X)
        ttk.Label(pf1, text="Profile vars").pack(side=tk.LEFT)
        ttk.Entry(pf1, textvariable=self.v["pvars"], width=44).pack(side=tk.LEFT, padx=3, fill=tk.X, expand=True)
        self._q(pf1, "Profile vars").pack(side=tk.LEFT)
        self.profile_info = ttk.Label(left, text="", foreground="#555", wraplength=455, justify=tk.LEFT); self.profile_info.pack(anchor="w")
        o = ttk.Frame(left); o.pack(fill=tk.X)
        def sp(r, c, label, key, help_key=None):
            ttk.Label(o, text=label).grid(row=r, column=c * 3, sticky="w")
            ttk.Entry(o, textvariable=self.v[key], width=7).grid(row=r, column=c * 3 + 1, sticky="w")
            self._q(o, help_key or label).grid(row=r, column=c * 3 + 2, sticky="w", padx=(0, 10))
        sp(0, 0, "Frame W", "fw"); sp(0, 1, "Frame H", "fh")
        sp(1, 0, "Figure px", "figh"); sp(1, 1, "Ground line y", "ground")
        cb = ttk.Frame(left); cb.pack(fill=tk.X, pady=2)
        self.cb_3d = []
        for k, lab, hk, only3d in (("outline", "Outline", "Outline", True), ("glb", "GLB model", "GLB model", True),
                                   ("fbx", "FBX", "FBX", True), ("strips", "Strips", "Strips", False), ("gifs", "GIFs", "GIF previews", False)):
            f = ttk.Frame(cb); f.pack(side=tk.LEFT)
            ttk.Checkbutton(f, text=lab, variable=self.b[k]).pack(side=tk.LEFT); self._q(f, hk).pack(side=tk.LEFT, padx=(0, 4))
            if only3d:
                self.cb_3d.append(f)
        self.cb_frame = cb
        qf = ttk.Frame(left); qf.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(qf, text="Quality").pack(side=tk.LEFT)
        ttk.Combobox(qf, textvariable=self.v["quality"], values=["final", "draft"], state="readonly", width=7).pack(side=tk.LEFT, padx=3)
        self._q(qf, "Quality").pack(side=tk.LEFT)
        ttk.Checkbutton(qf, text="Re-use unchanged moves (cache)", variable=self.b["cache"]).pack(side=tk.LEFT, padx=(10, 0))
        self._q(qf, "Cache").pack(side=tk.LEFT)
        cf = ttk.Frame(left); cf.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(cf, text="Console target").pack(side=tk.LEFT)
        self.console_cb = ttk.Combobox(cf, textvariable=self.v["console"], values=[NO_CONSOLE] + [consoles.LABELS[k] for k in consoles.ORDER],
                                       state="readonly", width=28)
        self.console_cb.pack(side=tk.LEFT, padx=3)
        self._q(cf, "Console target").pack(side=tk.LEFT)
        ttk.Checkbutton(cf, text="Dither", variable=self.b["dither"]).pack(side=tk.LEFT, padx=(8, 0)); self._q(cf, "Dither").pack(side=tk.LEFT)
        self.console_info = ttk.Label(left, text="", foreground="#26a269", wraplength=455, justify=tk.LEFT); self.console_info.pack(anchor="w")
        g2 = ttk.Frame(left); g2.pack(fill=tk.X); g2.columnconfigure(1, weight=1)
        ttk.Label(g2, text="Output folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(g2, textvariable=self.v["out"]).grid(row=0, column=1, sticky="we")
        ttk.Button(g2, text="...", width=3, command=lambda: self._browse("out", "dir")).grid(row=0, column=2)
        self._q(g2, "Output folder").grid(row=0, column=3)
        self.blender_w = [ttk.Label(g2, text="Blender exe (optional)"), ttk.Entry(g2, textvariable=self.v["blender"]),
                          ttk.Button(g2, text="...", width=3, command=lambda: self._browse("blender", "file")), self._q(g2, "Blender exe")]
        for c, wd in enumerate(self.blender_w):
            wd.grid(row=1, column=c, sticky="we" if c == 1 else "w")
        bf = ttk.Frame(left); bf.pack(fill=tk.X, pady=5)
        from .icons import tk_icon as _tki
        self.build_btn = ttk.Button(bf, text=" BUILD", image=_tki("build", 22), compound=tk.LEFT, command=self.on_build); self.build_btn.pack(side=tk.LEFT, ipadx=18, ipady=5)
        ttk.Button(bf, text="Example walkthrough", command=self.walkthrough).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Help", command=lambda: self.show_help("quickstart")).pack(side=tk.LEFT)
        self.status = ttk.Label(left, text="", style="Err.TLabel", wraplength=455, justify=tk.LEFT); self.status.pack(anchor="w")
        self.pb = ttk.Progressbar(left, maximum=1.0); self.pb.pack(fill=tk.X)
        self.log = scrolledtext.ScrolledText(left, height=10, width=60, font="TkFixedFont"); self.log.pack(fill=tk.BOTH, expand=True, pady=4)

        # --- middle: moves
        hf = ttk.Frame(mid); hf.pack(fill=tk.X)
        self.moves_hdr = ttk.Label(hf, text="3. Moves / animations", style="H.TLabel"); self.moves_hdr.pack(side=tk.LEFT); self._q(hf, "Moves").pack(side=tk.LEFT)
        pf = ttk.Frame(mid); pf.pack(fill=tk.X)
        ttk.Combobox(pf, textvariable=self.v["preset"], values=list(PRESETS), width=32, state="readonly").pack(side=tk.LEFT)
        ttk.Button(pf, text="Load preset", command=self.load_preset).pack(side=tk.LEFT, padx=3)
        ttk.Button(pf, text="All", width=4, command=lambda: self._all(True)).pack(side=tk.LEFT)
        ttk.Button(pf, text="None", width=5, command=lambda: self._all(False)).pack(side=tk.LEFT)
        hdr = ttk.Frame(mid); hdr.pack(fill=tk.X)
        for t, w in (("use", 4), ("move", 20), ("frames", 7), ("fps", 6), ("loop", 5), ("motion (3D)", 13), ("library clip", 14)):
            ttk.Label(hdr, text=t, width=w).pack(side=tk.LEFT)
        wrap = ttk.Frame(mid); wrap.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", lambda ev: self.canvas.yview_scroll(int(-ev.delta / 120), "units")))
        cf2 = ttk.Frame(mid); cf2.pack(fill=tk.X, pady=4)
        ttk.Label(cf2, text="Custom move").pack(side=tk.LEFT)
        ttk.Entry(cf2, textvariable=self.v["cname"], width=16).pack(side=tk.LEFT, padx=2)
        ttk.Label(cf2, text="using").pack(side=tk.LEFT)
        ttk.Combobox(cf2, textvariable=self.v["cmotion"], values=sorted(LIB), width=16, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Button(cf2, text="Add", command=self.add_custom).pack(side=tk.LEFT)

        # --- right: preview
        ttk.Label(right, text="4. Preview", style="H.TLabel").pack(anchor="w")
        self.prev_move = tk.StringVar()
        pr = ttk.Frame(right); pr.pack(fill=tk.X)
        self.prev_cb = ttk.Combobox(pr, textvariable=self.prev_move, width=24, state="readonly")
        self.prev_cb.pack(side=tk.LEFT); self.prev_cb.bind("<<ComboboxSelected>>", lambda e: self.play(self.prev_move.get()))
        self.qp_btn = ttk.Button(pr, text="Quick preview (3D)", command=self.quick_preview); self.qp_btn.pack(side=tk.LEFT, padx=4)
        self.prev_lbl = ttk.Label(right); self.prev_lbl.pack(pady=4)
        self.prev_info = ttk.Label(right, text="Build, then pick a move to play it.", foreground="#555"); self.prev_info.pack()
        self.sheet_lbl = ttk.Label(right); self.sheet_lbl.pack(pady=4, fill=tk.BOTH, expand=True)

    def _build_help(self, tab):
        lf = ttk.Frame(tab); lf.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        ttk.Label(lf, text="Help topics", style="H.TLabel").pack(anchor="w")
        self.help_list = tk.Listbox(lf, width=34, height=14, exportselection=False, font=("Segoe UI", 10))
        self.help_keys = list(helptext.TOPICS)
        for k in self.help_keys:
            self.help_list.insert(tk.END, helptext.TOPICS[k][0])
        self.help_list.pack(anchor="w")
        self.help_list.bind("<<ListboxSelect>>", lambda e: self.show_help(self.help_keys[self.help_list.curselection()[0]], switch=False)
                            if self.help_list.curselection() else None)
        ttk.Button(lf, text="Example walkthrough\n(build the sample character\nand open its preview)", command=self.walkthrough).pack(fill=tk.X, pady=8)
        ttk.Button(lf, text="Open HELP.md", command=lambda: self._open(os.path.join(ROOT, "HELP.md"))).pack(fill=tk.X)
        self.doctor_btn = ttk.Button(lf, text="Check setup (doctor)", command=self.show_doctor); self.doctor_btn.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(lf, text="Tip: hover any (?) next to a field\nfor a one-line explanation.", foreground="#555").pack(anchor="w", pady=8)
        self.help_txt = scrolledtext.ScrolledText(tab, font=("Consolas" if sys.platform == "win32" else "TkFixedFont", 10), wrap=tk.WORD)
        self.help_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.help_txt.tag_configure("h", font=("Segoe UI", 14, "bold"), foreground="#1a5fb4")
        self.show_help("quickstart", switch=False)

    def show_help(self, key, switch=True):
        title, text = helptext.get(key)
        self.help_txt.configure(state=tk.NORMAL); self.help_txt.delete("1.0", tk.END)
        self.help_txt.insert(tk.END, title + "\n\n", "h"); self.help_txt.insert(tk.END, text)
        self.help_txt.configure(state=tk.DISABLED)
        i = self.help_keys.index(key)
        self.help_list.selection_clear(0, tk.END); self.help_list.selection_set(i); self.help_list.see(i)
        if switch:
            self.nb.select(self.helptab)

    def show_doctor(self, done=None):
        """Run the forge.py doctor checks in the background and show them as a table in the Help pane."""
        import threading
        from . import doctor
        T = self.help_txt
        T.configure(state=tk.NORMAL); T.delete("1.0", tk.END)
        T.insert(tk.END, "Check setup (forge.py doctor)\n\n", "h"); T.insert(tk.END, "checking ...")
        T.configure(state=tk.DISABLED); self.nb.select(self.helptab)
        T.tag_configure("tab", tabs=("190p", "260p"))
        T.tag_configure("ok", foreground="#26a269"); T.tag_configure("bad", foreground="#c01c28"); T.tag_configure("opt", foreground="#777")

        def work():
            try:
                rows, err = doctor.checks(), None
            except Exception as e:
                rows, err = [], str(e)
            self.root.after(0, lambda: show(rows, err))

        def show(rows, err):
            T.configure(state=tk.NORMAL); T.delete("1.0", tk.END)
            T.insert(tk.END, "Check setup (forge.py doctor)\n\n", "h")
            for r in rows:
                st, tg = ("OK", "ok") if r["ok"] else (("MISSING", "bad") if r["kind"] in ("required", "core") else ("--", "opt"))
                T.insert(tk.END, r["name"] + "\t", "tab"); T.insert(tk.END, st, ("tab", tg)); T.insert(tk.END, "\t" + r["detail"] + "\n", "tab")
                if not r["ok"] and r["disables"]:
                    T.insert(tk.END, "\t\t-> disables: " + r["disables"] + "\n", ("tab", tg))
            req = [r["name"] for r in rows if not r["ok"] and r["kind"] == "required"]
            T.insert(tk.END, "\n" + (("NOT READY: missing %s - run setup.bat / ./setup.sh" % ", ".join(req)) if req or err else
                                    "READY: sprites, photo/spec builds, consoles, GLB + FBX export.") + (("\n" + err) if err else "") + "\n", "h" if not req else "bad")
            T.insert(tk.END, "\nThe same table: forge.bat doctor / ./forge.sh doctor.  How to install anything missing: Help topic 'Install / setup'.\n")
            T.configure(state=tk.DISABLED)
            if done:
                done(self)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ adaptive fields
    def apply_mode(self):
        mode = self.v["mode"].get()
        for ws, modes in self.field_rows:
            for w in ws:
                (w.grid() if mode in modes else w.grid_remove())
        for f in self.cb_frame.winfo_children():
            f.pack_forget()
        for f in self.cb_frame.winfo_children():
            if mode in THREE_D or f not in self.cb_3d:
                f.pack(side=tk.LEFT)
        show_bl = mode in MANNEQUIN_3D and self.b["fbx"].get()
        for w in self.blender_w:
            (w.grid() if show_bl else w.grid_remove())
        self.qp_btn.configure(state=tk.NORMAL if mode in MANNEQUIN_3D else tk.DISABLED)
        self.refresh_library_choices()
        if mode == "library" and self.v["kit"].get() in ("home", ""):
            self.v["kit"].set(OWN_COLOURS)
        elif mode != "library" and self.v["kit"].get() not in KITS:
            self.v["kit"].set("home")
        self.mode_desc.configure(text=next(d for k, _, d in MODES if k == mode))
        self.moves_hdr.configure(text="3. Moves - NOT USED in this mode (moves = your clips)" if mode in ("video", "mocap") else
                                 "3. Moves - NOT USED in scan mode" if mode == "scan" else "3. Moves / animations",
                                 foreground="#c01c28" if mode in CLI_MODES else "")
        self.status.configure(text="")

    # ------------------------------------------------------------ library helpers
    def _clip_choices(self):
        try:
            from . import library as _L
            return [""] + sorted(_L.Library().clip_index())
        except Exception:
            return [""]

    def refresh_library_choices(self):
        try:
            from . import library as _L
            lib = _L.Library()
            self.rig_cb["values"] = lib.names("rigs") + lib.names("animations")
            lk = lib.names("kits")
        except Exception:
            lk = []
        self.kit_cb["values"] = ([OWN_COLOURS] + lk + list(KITS)) if self.v["mode"].get() == "library" else list(KITS)
        ch = self._clip_choices()
        for row in self.rows:
            row[7]["values"] = ch

    def _apply_clip_map(self, cm):
        from .librarybuild import entry_str
        for mv, e in (cm or {}).items():
            try:
                self.set_move_clip(mv, entry_str(e))
            except Exception:
                pass

    def set_move_clip(self, move, clip):
        for row in self.rows:
            if row[0].name == move or (row[0].label or "").lower() == move.lower():
                row[6].set(clip); row[1].set(True); return True
        return False

    def lib_kit(self):
        from . import kits as K, library as _L
        k = self.v["kit"].get()
        return None if k in (OWN_COLOURS, "") else K.load(k, _L.libdir())

    def _console_info(self):
        key = consoles.by_label(self.v["console"].get())
        if not key:
            self.console_info.configure(text="No console export (standard out/<name>/ files only).")
        else:
            self.console_info.configure(text=consoles.describe(key) + "\n-> out/<name>/console/  (see Help > Console targets)")
            self.b["dither"].set(consoles.PRESETS[key]["dither"])

    def validate(self):
        v = self.v; mode = v["mode"].get(); errs = []
        def need_file(key, what, hint):
            p = v[key].get().strip()
            if not p:
                errs.append("%s is required for %s mode - %s" % (what, MODE_LABEL[mode], hint))
            elif not os.path.exists(p):
                errs.append("%s not found: %s" % (what, p))
        if mode == "photo":
            need_file("photo", "Front photo", "click ... and pick a picture of your character.")
            try:
                tv = turn_value(self.v["turn"].get(), self.v["turn_yaw"].get())
            except ValueError:
                errs.append("Turn angle: type a number of degrees (e.g. 90), or leave it empty."); tv = 0
            lm = self.v["landmarks"].get().strip() or os.path.join(os.path.dirname(os.path.abspath(self.v["photo"].get() or ".")), "landmarks.json")
            if (tv % 360 or self.v["fill"].get() == "puppet") and not os.path.isfile(lm):
                errs.append("Turn / puppet needs pose landmarks: run 'Cut out person' on the Start tab (or forge.py cutout) first - looked for %s" % lm)
            for key, what in (("back", "Back photo"), ("side", "Side photo"), ("view34", "3/4 photo")):
                if v[key].get().strip() and not os.path.exists(v[key].get().strip()):
                    errs.append("%s not found: %s" % (what, v[key].get()))
            for item in v["videos"].get().split(";"):
                if item.strip() and "=" not in item:
                    errs.append("Video/frames per move must look like  walk=walk.mp4; kick=C:/frames/kick  (got '%s')" % item.strip())
        elif mode == "frames":
            need_file("frames", "Frames folder", "pick the folder that contains walk/01.png ... or walk_01.png ...")
        elif mode in ("video", "mocap"):
            items = [x.strip() for x in v["clips"].get().split(";") if x.strip()]
            if not items:
                errs.append("%s needs at least one clip like  walk:8=C:/clips/walk.mp4  - use 'Add clip...'." % MODE_LABEL[mode])
            from .video import parse_clip
            for it in items:
                try:
                    _, _, cp, _, _, _ = parse_clip(it)
                    if not os.path.exists(cp):
                        errs.append("Clip not found: %s" % cp)
                except Exception as e:
                    errs.append("Clip '%s': %s (format move:frames=file.mp4@start-end)" % (it, e))
            try:
                assert float(v["slowmo"].get() or 1) >= 1
            except (ValueError, AssertionError):
                errs.append("Slow motion must be a number >= 1 (2 = twice as many in-between frames).")
        elif mode == "scan":
            o, m = v["orbit"].get().strip(), v["smesh"].get().strip()
            if not o and not m:
                errs.append("Scan mode needs an Orbit video (walk around a still object) or a finished mesh (obj/ply/glb).")
            for pth, what in ((o, "Orbit video"), (m, "Mesh")):
                if pth and not os.path.exists(pth):
                    errs.append("%s not found: %s" % (what, pth))
            if v["sheight"].get().strip():
                try:
                    float(v["sheight"].get())
                except ValueError:
                    errs.append("Real height is in metres, e.g. 1.75")
            if not v["sframes"].get().strip().isdigit():
                errs.append("Frames to extract must be a whole number (60-120 is typical).")
        elif mode == "movesheets":
            items = [x.strip() for x in v["movesheets"].get().split(";") if x.strip()]
            if not items:
                errs.append("Per-move sheets mode needs at least one  move=strip.png  - use 'Add strip...'.")
            for it in items:
                mv, _, p = it.partition("=")
                if not p:
                    errs.append("'%s' should be  move=path/to/strip.png" % it)
                elif not os.path.exists(p.strip()):
                    errs.append("strip for '%s' not found: %s" % (mv.strip(), p.strip()))
            if v["across"].get().strip() and not v["across"].get().strip().isdigit():
                errs.append("Frames across must be a whole number (or blank for auto).")
        elif mode == "sheet":
            need_file("sheet", "Sprite sheet", "pick the sheet image (one row per move).")
            gr = v["grid"].get().strip().lower()
            if gr and not (len(gr.split("x")) == 2 and all(x.isdigit() for x in gr.split("x"))):
                errs.append("Grid must look like 4x8 (rows x columns), or be blank for auto-detect.")
        elif mode == "spec":
            need_file("spec", "Spec file", "pick a .txt spec or press 'New spec from template...'.")
        elif mode == "library":
            rg = v["rig"].get().strip()
            from . import library as _L
            if not rg:
                errs.append("Library rig: pick one (Library tab > Use as template) or browse to an .fbx / .glb file.")
            elif not os.path.isfile(rg):
                try:
                    k, _n = _L.Library().find(rg)
                    if k == "kits":
                        errs.append("Library rig: '%s' is a kit - choose a rig, and put the kit in 'Kit'." % rg)
                except KeyError:
                    errs.append("Library rig: '%s' is not in the library (%s) and is not a file." % (rg, _L.libdir()))
            from .librarybuild import norm_entry
            for m, on, fr, fps, lp, mo, cl, cc in self.rows:
                if on.get() and cl.get().strip():
                    try:
                        norm_entry(cl.get().strip())
                    except Exception as e:
                        errs.append("Library clip of %s: %s (asset:clip@speed=1.2,trim=0-0.5,loop)" % (m.name, e))
        for key, what, lo, hi in (("fw", "Frame W", 8, 4096), ("fh", "Frame H", 8, 4096)):
            s = v[key].get().strip()
            if not s.isdigit() or not lo <= int(s) <= hi:
                errs.append("%s must be a whole number between %d and %d." % (what, lo, hi))
        for key, what in (("figh", "Figure px"), ("ground", "Ground line y"), ("height", "Height cm")):
            s = v[key].get().strip()
            if s and not s.replace(".", "", 1).isdigit():
                errs.append("%s must be a number (or blank for the default)." % what)
        if v["ground"].get().strip().isdigit() and v["fh"].get().strip().isdigit() and int(v["ground"].get()) >= int(v["fh"].get()):
            errs.append("Ground line y must be inside the frame (smaller than Frame H).")
        if mode in THREE_D:
            try:
                float(v["yaw"].get() or 65)
            except ValueError:
                errs.append("Camera yaw must be a number of degrees (65 = 3/4 view).")
        if mode not in ("spec",) and not v["name"].get().strip():
            errs.append("Give the character a Name (it becomes the output folder).")
        if mode not in CLI_MODES and not any(r[1].get() for r in self.rows):
            errs.append("Tick at least one move in '3. Moves'.")
        if v["views"].get().strip():
            from . import views as V
            try:
                V.parse_view_list(v["views"].get())
            except ValueError as e:
                errs.append("Output views: %s" % e)
        vc = v["view_cut"].get().strip()
        if vc:
            try:
                assert 0 <= float(vc) <= 1
            except (ValueError, AssertionError):
                errs.append("View cut must be between 0 and 1 (0.55 = head-to-lap bust, blank/0 = whole figure).")
        for item in [x for x in v["pvars"].get().split(";") if x.strip()]:
            if "=" not in item:
                errs.append("Profile vars must look like  tagline=Fast!; speed=4  (got '%s')" % item.strip())
        if v["profile"].get() not in ("", NO_PROFILE):
            from . import profiles
            try:
                pe, _ = profiles.validate(profiles.load(v["profile"].get()))
                errs += ["Profile %s: %s" % (v["profile"].get(), e) for e in pe]
            except Exception as e:
                errs.append("Profile: %s" % e)
        ct = v["console"].get().strip()
        if ct and ct != NO_CONSOLE and not consoles.by_label(ct):
            errs.append("Unknown console target '%s' - pick one from the Console target list (Help > Console targets)." % ct)
        return errs

    # ------------------------------------------------------------ helpers for modes
    def add_strip(self):
        p = filedialog.askopenfilename(title="Strip image (a row of frames)", filetypes=[("Images", "*.png *.webp *.gif *.jpg"), ("All", "*.*")])
        if not p:
            return
        from tkinter import simpledialog
        guess = slug(os.path.splitext(os.path.basename(p))[0])
        mv = simpledialog.askstring("Move name", "Which move is this strip? (e.g. walk, punch)", initialvalue=guess, parent=self.root)
        if mv:
            cur = [x for x in self.v["movesheets"].get().split(";") if x.strip()]
            cur.append("%s=%s" % (slug(mv), p)); self.v["movesheets"].set("; ".join(cur))

    def new_spec(self):
        from .spec import EXAMPLE_SPEC
        p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="my_character.txt", filetypes=[("Spec", "*.txt")])
        if not p:
            return
        with open(p, "w") as f:
            f.write(EXAMPLE_SPEC)
        self.v["spec"].set(p); self.spec_editor(p)

    def spec_editor(self, path=None):
        """Built-in plain-text editor for a character spec (key = value lines)."""
        from .spec import EXAMPLE_SPEC
        w = tk.Toplevel(self.root); w.title("Character spec - " + (path or "new")); self.spec_win = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 300, self.root.winfo_rooty() + 60))
        t = tk.Text(w, width=96, height=34, font="TkFixedFont", undo=True); t.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.spec_text = t
        try:
            t.insert("1.0", open(path).read() if path and os.path.exists(path) else EXAMPLE_SPEC)
        except OSError:
            t.insert("1.0", EXAMPLE_SPEC)
        st = ttk.Label(w, text="One 'key = value' per line. Fictional characters only (no real people).", foreground="#444")
        st.pack(anchor="w", padx=6)
        def save(use=True):
            p = path or filedialog.asksaveasfilename(defaultextension=".txt", initialfile="my_character.txt", filetypes=[("Spec", "*.txt")])
            if not p:
                return
            with open(p, "w") as f:
                f.write(t.get("1.0", "end-1c"))
            st.configure(text="Saved " + p, foreground="#26a269")
            if use:
                self.v["mode"].set("spec"); self.v["spec"].set(p)
        self.spec_save = save
        bf = ttk.Frame(w); bf.pack(pady=4)
        ttk.Button(bf, text="Save & use", command=save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Close", command=w.destroy).pack(side=tk.LEFT, padx=4)
        return w

    # ------------------------------------------------------------ moves list
    def _clear_rows(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.rows = []

    def _add_row(self, m: MoveSpec):
        r = ttk.Frame(self.inner); r.pack(fill=tk.X)
        on = tk.BooleanVar(value=m.enabled); fr = tk.StringVar(value=str(m.frames)); fps = tk.StringVar(value=str(m.fps))
        lp = tk.BooleanVar(value=m.loop); mo = tk.StringVar(value=m.motion or m.name)
        ttk.Checkbutton(r, variable=on, width=2).pack(side=tk.LEFT)
        ttk.Label(r, text="%s  [%s]" % (m.label or m.name, m.category), width=20).pack(side=tk.LEFT)
        ttk.Spinbox(r, from_=1, to=64, textvariable=fr, width=4).pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(r, from_=1, to=60, textvariable=fps, width=4).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(r, variable=lp).pack(side=tk.LEFT, padx=6)
        ttk.Combobox(r, textvariable=mo, values=sorted(LIB), width=12).pack(side=tk.LEFT)
        cl = tk.StringVar(value=getattr(m, "_clip", ""))
        cc = ttk.Combobox(r, textvariable=cl, values=self._clip_choices(), width=18); cc.pack(side=tk.LEFT, padx=2)
        Tooltip(cc, helptext.FIELD_HELP.get("Library clip", "library clip"))
        self.rows.append((m, on, fr, fps, lp, mo, cl, cc))

    def load_preset(self):
        self._clear_rows()
        for m in preset(self.v["preset"].get()):
            self._add_row(m)

    def _all(self, state):
        for row in self.rows:
            row[1].set(state)

    def add_custom(self):
        nm = self.v["cname"].get().strip()
        if not nm:
            return
        mot = LIB[self.v["cmotion"].get()]
        self._add_row(MoveSpec(slug(nm), nm, "Custom", 8, 12, mot.loop, mot.name, "custom move using " + mot.name))
        self.canvas.yview_moveto(1.0)

    def selected_moves(self):
        out = []
        for m, on, fr, fps, lp, mo, _cl, _cc in self.rows:
            if not on.get():
                continue
            mm = MoveSpec.from_dict(m.to_dict())
            mm.frames = max(1, int(fr.get() or 1)); mm.fps = max(1, int(fps.get() or 1)); mm.loop = lp.get()
            mm.motion = "" if mo.get() == m.name else mo.get()
            out.append(mm)
        return out

    # ------------------------------------------------------------ config
    def config(self):
        v = self.v; c = BuildConfig(); mode = v["mode"].get()
        if v["profile"].get() not in ("", NO_PROFILE):
            from . import profiles
            profiles.apply(c, profiles.load(v["profile"].get()))
        c.display_name = v["name"].get()
        c.mode = mode; c.name = v["name"].get() or "hero"
        if mode == "spec":
            c.spec_path = v["spec"].get()
            try:
                from .spec import load_spec
                c.name = v["name"].get() if v["name"].get() not in ("", "hero") else load_spec(c.spec_path).name
            except Exception:
                pass
        if mode == "photo":
            c.photo = v["photo"].get(); c.back = v["back"].get()
            if v["side"].get().strip():
                c.view_sources["left" if self.b["side_left"].get() else "right"] = v["side"].get().strip()
            if v["view34"].get().strip():
                c.view_sources["front_right"] = v["view34"].get().strip()
            for item in v["videos"].get().split(";"):
                if "=" in item:
                    k, _, p = item.partition("="); c.videos[k.strip()] = p.strip()
        if mode == "frames":
            c.frames_dir = v["frames"].get()
        if mode == "movesheets":
            for item in v["movesheets"].get().split(";"):
                if "=" in item:
                    k, _, p = item.partition("="); c.move_sheets[k.strip()] = p.strip()
            if v["across"].get().strip().isdigit():
                c.grid_cols = int(v["across"].get())
        if mode == "sheet":
            c.sheet = v["sheet"].get(); c.sheet_layout = v["layout"].get()
            if "x" in v["grid"].get().lower():
                r, _, cc = v["grid"].get().lower().partition("x"); c.grid_rows, c.grid_cols = int(r), int(cc)
        if mode == "library":
            c.rig = v["rig"].get().strip(); c.root_motion = v["root_motion"].get() or "keep"
            from .librarybuild import norm_entry
            cm = dict(c.clip_map or {})
            for m, on, fr, fps, lp, mo, cl, cc in self.rows:
                if on.get() and cl.get().strip():
                    cm[m.name] = norm_entry(cl.get().strip())
            c.clip_map = cm
        if mode in THREE_D:
            c.material_split = v["msplit"].get() or "auto"; c.material_slots = v["mslots"].get() or "full"
            c.anim_export = bool(self.b["anim_export"].get())
            c.outfits = [x.strip() for x in v["outfits"].get().split(";") if x.strip()]
            c.props = [x.strip() for x in v["eprops"].get().split(";") if x.strip()]
            c.slot_colors = v["slot_colors"].get().strip()
            c.human = v["human"].get().strip() if mode == "mannequin" else ""
            c.kit = "" if v["kit"].get() in (OWN_COLOURS, "") else v["kit"].get()
            c.yaw = float(v["yaw"].get() or 65); c.prop = v["prop"].get() if mode != "library" else "none"
            c.outline = self.b["outline"].get(); c.glb = self.b["glb"].get(); c.fbx = self.b["fbx"].get()
            if mode == "library" and v["kits"].get().strip() == "all":
                from . import library as _L
                c.kits = _L.Library().names("kits")
            elif mode in ("mannequin", "library") and v["kits"].get().strip():
                c.kits = list(KITS) if v["kits"].get().strip() == "all" else [k.strip() for k in v["kits"].get().split(",") if k.strip()]
        else:
            c.cutout = v["cutout"].get(); c.fill = v["fill"].get(); c.flip = self.b["flip"].get()
            if mode == "photo":
                c.landmarks = v["landmarks"].get().strip()
                c.turn = turn_value(v["turn"].get(), v["turn_yaw"].get())
                c.turn_depth = v["turn_depth"].get() or "auto"
                c.side_photo = v["turn_side"].get().strip()
                if c.turn % 360:
                    c.fill = "puppet"
            c.height_cm = float(v["height"].get() or 0) if mode in ("photo", "frames") else 0.0
            c.glb = c.fbx = False
        c.out_root = v["out"].get() or "out"
        c.frame_w = int(v["fw"].get() or 256); c.frame_h = int(v["fh"].get() or 256)
        c.figure_h = int(float(v["figh"].get() or 0)); c.ground_y = int(float(v["ground"].get() or 0))
        c.blender = v["blender"].get()
        c.strips = self.b["strips"].get(); c.gifs = self.b["gifs"].get()
        c.console = consoles.by_label(v["console"].get()); c.dither = self.b["dither"].get() if c.console else None
        c.moves = self.selected_moves()
        c.quality = v["quality"].get() or "final"; c.cache = bool(self.b["cache"].get())
        from . import views as V
        vs = v["views"].get().strip()
        c.billboard8 = vs.lower() in ("billboard8", "8dir", "8")
        c.view_list = [] if c.billboard8 or not vs else V.parse_view_list(vs)
        c.view_cut = float(v["view_cut"].get() or 0)
        for item in v["pvars"].get().split(";"):
            if "=" in item:
                k, _, val = item.partition("="); c.profile_vars[k.strip()] = val.strip()
        from .gui_style import apply_to_config
        return apply_to_config(self, c)

    # ------------------------------------------------------------ profiles
    def _profile_names(self):
        from . import profiles
        return [NO_PROFILE] + profiles.list_profiles()

    def apply_profile(self):
        """Fill the UI from the chosen profile (you can still change any field afterwards)."""
        from . import profiles
        name = self.v["profile"].get()
        if name in ("", NO_PROFILE):
            self.profile_info.configure(text="No profile: standard outputs (atlas.png/json, sprites.cfg, character.ini).")
            return
        try:
            d = profiles.load(name)
        except Exception as e:
            self.profile_info.configure(text=str(e)); return
        c = profiles.apply(BuildConfig(), d)
        self.v["fw"].set(str(c.frame_w)); self.v["fh"].set(str(c.frame_h))
        self.v["figh"].set(str(c.figure_h) if c.figure_h else ""); self.v["ground"].set(str(c.ground_y) if c.ground_y else "")
        self.v["views"].set("billboard8" if c.billboard8 else ",".join(c.view_list))
        self.v["view_cut"].set(str(c.view_cut) if c.view_cut else "")
        if "prop" in d:
            self.v["prop"].set(c.prop)
        if "yaw" in d:
            self.v["yaw"].set(str(c.yaw))
        self.v["console"].set(consoles.LABELS[c.console] if c.console else NO_CONSOLE)
        for k in ("gifs", "strips", "outline", "glb", "fbx"):
            if k in d:
                self.b[k].set(bool(d[k]))
        if isinstance(d.get("moves"), str):
            from .moves import PRESET_KEYS
            self.v["preset"].set(PRESET_KEYS.get(d["moves"], d["moves"]))
        if "moves" in d:
            self._clear_rows()
            for m in c.moves:
                self._add_row(m)
        if d.get("rig"):
            self.v["mode"].set("library"); self.v["rig"].set(str(d["rig"]))
        if d.get("root_motion"):
            self.v["root_motion"].set(d["root_motion"])
        if d.get("material_split"):
            self.v["msplit"].set(d["material_split"])
        if d.get("material_slots"):
            self.v["mslots"].set(d["material_slots"])
        if "anim_export" in d:
            self.b["anim_export"].set(bool(d["anim_export"]))
        for k_, vk in (("outfits", "outfits"), ("props", "eprops")):
            if k_ in d:
                val = d[k_]
                self.v[vk].set("; ".join(val) if isinstance(val, (list, tuple)) else str(val or ""))
        if d.get("human"):
            h = d["human"]; self.v["mode"].set("mannequin")
            self.v["human"].set(h if isinstance(h, str) else ",".join("%s=%s" % kv for kv in h.items()))
        if "slot_colors" in d:
            sc = d["slot_colors"]
            self.v["slot_colors"].set(sc if isinstance(sc, str) else ",".join("%s=%s" % kv for kv in sc.items()))
        self._apply_clip_map(c.clip_map)
        self.v["pvars"].set("; ".join("%s=%s" % kv for kv in d.get("vars", {}).items()))
        outs = [im.get("file", im.get("dir", "")) for im in d.get("images", [])] + \
               [m.get("file") or {"godot_spriteframes": "<name>.tres", "tiled_tsx": "<name>.tsx", "unity_json": "<name>.unity.json"}.get(m["type"], m["type"]) for m in d.get("manifests", [])]
        desc = d.get("description", "")
        desc = desc.split(": ")[0] if len(desc) > 90 else desc
        self.profile_info.configure(text="%s\nWrites: standard files%s" % (desc, (" + " + ", ".join(outs)) if outs else ""))

    def create_profile_dialog(self, auto=None):
        """Small form -> profiles/<name>.json (a starting point; edit the JSON for templates)."""
        from . import profiles
        w = tk.Toplevel(self.root); w.title("Create output profile"); self.profile_win = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 380, self.root.winfo_rooty() + 120))
        fv = {k: tk.StringVar(value=val) for k, val in dict(
            name="my_game", base=(self.v["profile"].get() if self.v["profile"].get() != NO_PROFILE else "generic_2d"),
            description="My game's sprite format", views=self.v["views"].get(), frame="%sx%s" % (self.v["fw"].get(), self.v["fh"].get()),
            view_cut=self.v["view_cut"].get(), console=self.v["console"].get()).items()}
        fb = {k: tk.BooleanVar(value=val) for k, val in dict(moves=True, godot=False, tiled=False, unity=False).items()}
        f = ttk.Frame(w, padding=10); f.pack(fill=tk.BOTH, expand=True); f.columnconfigure(1, weight=1)
        rows = [("Profile name", ttk.Entry(f, textvariable=fv["name"], width=30)),
                ("Start from", ttk.Combobox(f, textvariable=fv["base"], values=profiles.list_profiles(), state="readonly", width=28)),
                ("Description", ttk.Entry(f, textvariable=fv["description"], width=40)),
                ("Frame WxH", ttk.Entry(f, textvariable=fv["frame"], width=12)),
                ("Views", ttk.Combobox(f, textvariable=fv["views"], values=["", "front,back", "front,right,back,left", "billboard8"], width=28)),
                ("View cut (0-1)", ttk.Entry(f, textvariable=fv["view_cut"], width=8)),
                ("Console", ttk.Combobox(f, textvariable=fv["console"], values=[NO_CONSOLE] + [consoles.LABELS[k] for k in consoles.ORDER], state="readonly", width=28))]
        for i, (lab, wd) in enumerate(rows):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=2); wd.grid(row=i, column=1, sticky="w", pady=2)
        r = len(rows)
        ttk.Checkbutton(f, text="Use the moves ticked in '3. Moves' (%d)" % sum(1 for x in self.rows if x[1].get()), variable=fb["moves"]).grid(row=r, column=0, columnspan=2, sticky="w")
        mf = ttk.Frame(f); mf.grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(mf, text="Also write:").pack(side=tk.LEFT)
        for k, lab in (("godot", "Godot SpriteFrames"), ("tiled", "Tiled tileset"), ("unity", "Unity JSON")):
            ttk.Checkbutton(mf, text=lab, variable=fb[k]).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="Saved to profiles/<name>.json. Open it in a text editor to add your own\ncharacter.ini keys or templates (Help > Output profiles).",
                  foreground="#555", justify=tk.LEFT).grid(row=r + 2, column=0, columnspan=2, sticky="w")
        msg = ttk.Label(f, text="", foreground="#26a269", wraplength=420, justify=tk.LEFT); msg.grid(row=r + 4, column=0, columnspan=2, sticky="w")
        def save():
            try:
                fr = fv["frame"].get().lower().partition("x")
                frame = (int(fr[0]), int(fr[2] or fr[0])) if fr[0].strip() else None
                moves = None
                if fb["moves"].get():
                    moves = [("%s=%s" % (m.name, m.motion) if m.motion else m.name) + ":%d:%d:%s" % (m.frames, m.fps, "loop" if m.loop else "once")
                             for m in self.selected_moves()]
                mans = [t for k, t in (("godot", "godot_spriteframes"), ("tiled", "tiled_tsx"), ("unity", "unity_json")) if fb[k].get()]
                vs = fv["views"].get().strip()
                d = profiles.new_profile(fv["name"].get(), fv["base"].get() or None, moves, vs or None, frame, mans, fv["description"].get())
                if fv["view_cut"].get().strip():
                    d["view_cut"] = float(fv["view_cut"].get())
                ck = consoles.by_label(fv["console"].get())
                if ck:
                    d["console"] = ck
                else:
                    d.pop("console", None)
                errs, warns = profiles.validate(d)
                if errs:
                    msg.configure(text="Not saved:\n- " + "\n- ".join(errs), foreground="#c01c28"); return None
                p = profiles.save(d)
                self.profile_cb["values"] = self._profile_names(); self.v["profile"].set(d["name"]); self.apply_profile()
                msg.configure(text="Saved %s\n%s" % (p, "\n".join("warning: " + x for x in warns)), foreground="#26a269")
                self._log("profile saved: " + p)
                return p
            except Exception as e:
                msg.configure(text="Not saved: %s" % e, foreground="#c01c28"); return None
        bf = ttk.Frame(f); bf.grid(row=r + 3, column=0, columnspan=2, pady=6, sticky="w")
        ttk.Button(bf, text="Save profile", command=save).pack(side=tk.LEFT)
        ttk.Button(bf, text="Close", command=w.destroy).pack(side=tk.LEFT, padx=4)
        if auto:
            for k, val in auto.get("vars", {}).items():
                fv[k].set(val)
            for k, val in auto.get("bools", {}).items():
                fb[k].set(val)
            if auto.get("save"):
                w.after(400, save)
        return w

    def save_project(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Project", "*.json")])
        if not p:
            return
        d = {"gui_vars": {k: x.get() for k, x in self.v.items()}, "gui_bools": {k: x.get() for k, x in self.b.items()}}
        c = self.config(); d.update({k: val for k, val in c.__dict__.items() if k != "spec"})
        d["moves"] = [m.to_dict() for m in c.moves]
        with open(p, "w") as f:
            json.dump(d, f, indent=1)
        self._log("saved project " + p)

    def load_project(self):
        p = filedialog.askopenfilename(filetypes=[("Project", "*.json")])
        if not p:
            return
        d = json.load(open(p))
        for k, val in d.get("gui_vars", {}).items():
            if k in self.v:
                self.v[k].set(val)
        for k, val in d.get("gui_bools", {}).items():
            if k in self.b:
                self.b[k].set(val)
        if "gui_vars" not in d:   # v1 project
            m = {"mode": "mode", "name": "name", "spec_path": "spec", "photo": "photo", "back": "back", "frames_dir": "frames",
                 "sheet": "sheet", "kit": "kit", "out_root": "out", "frame_w": "fw", "frame_h": "fh", "figure_h": "figh",
                 "ground_y": "ground", "yaw": "yaw", "cutout": "cutout", "fill": "fill", "blender": "blender", "prop": "prop"}
            for k, vk in m.items():
                if k in d:
                    self.v[vk].set(str(d[k]))
        self._clear_rows()
        for x in d.get("moves", []):
            self._add_row(MoveSpec.from_dict(x))
        self._apply_clip_map(d.get("clip_map"))
        self.apply_mode()

    def _browse(self, key, kind):
        if kind == "dir":
            p = filedialog.askdirectory()
        elif kind == "image":
            p = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All", "*.*")])
        elif kind == "spec":
            p = filedialog.askopenfilename(filetypes=[("Spec", "*.txt"), ("All", "*.*")])
        elif kind == "video":
            p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All", "*.*")])
        elif kind == "rigfile":
            p = filedialog.askopenfilename(filetypes=[("Rig", "*.fbx *.glb *.gltf"), ("All", "*.*")])
        elif kind == "json":
            p = filedialog.askopenfilename(filetypes=[("Landmarks", "*.json"), ("All", "*.*")])
        elif kind == "mesh":
            p = filedialog.askopenfilename(filetypes=[("Mesh", "*.obj *.ply *.glb *.gltf"), ("All", "*.*")])
        else:
            p = filedialog.askopenfilename()
        if p:
            self.v[key].set(p)

    def _open(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self._log("could not open %s (%s)" % (path, e))

    def open_out(self):
        p = self.result["out"] if self.result else (self.v["out"].get() or "out")
        os.makedirs(p, exist_ok=True); self._open(os.path.abspath(p))

    # ------------------------------------------------------------ build
    def _log(self, s):
        self.log.insert(tk.END, s + "\n"); self.log.see(tk.END)

    def cli_argv(self):
        """forge.py command line for the Video / Mocap / Scan modes (same as typing it in a terminal)."""
        v = self.v; mode = v["mode"].get(); name = v["name"].get().strip() or "hero"; out = v["out"].get() or "out"
        ck = consoles.by_label(v["console"].get())
        if mode == "scan":
            a = ["scan", "--name", name, "--out", out]
            if v["smesh"].get().strip():
                a += ["--mesh", v["smesh"].get().strip()]
            else:
                a += ["--video", v["orbit"].get().strip(), "--frames", v["sframes"].get().strip() or "80"]
                if self.b["srun"].get():
                    a += ["--run"]
            if v["sheight"].get().strip():
                a += ["--height", v["sheight"].get().strip()]
            if v["budgets"].get().strip():
                a += ["--budgets", v["budgets"].get().strip()]
            return a
        a = [mode]
        for it in [x.strip() for x in v["clips"].get().split(";") if x.strip()]:
            a += ["--clip", it]
        a += ["--name", name, "--out", out]
        if ck:
            a += ["--consoles", ck]
        if mode == "video":
            a += ["--camera", v["vcamera"].get(), "--bg", v["vbg"].get()]
            if (v["slowmo"].get().strip() or "1") != "1":
                a += ["--slowmo", v["slowmo"].get().strip()]
            if self.b["flip"].get():
                a += ["--flip"]
        else:
            a += ["--model", v["pmodel"].get()]
            if not self.b["fbx"].get():
                a += ["--no-fbx"]
        if v["blender"].get().strip():
            a += ["--blender", v["blender"].get().strip()]
        if v["fw"].get().strip() and v["fh"].get().strip():
            a += ["--frame", "%sx%s" % (v["fw"].get().strip(), v["fh"].get().strip())]
        return a

    def equip_dialog(self):
        """v7 Equip panel: tick library outfits / props, choose each prop's socket, set slot colours."""
        from . import library as L
        try:
            lib = L.Library(None)
            outs, props = lib.names("outfits"), lib.names("props")
        except Exception as e:
            messagebox.showerror("Equip", "library: %s" % e); return
        top = tk.Toplevel(self.root); top.title("Equip - outfits + props"); top.transient(self.root)
        f = ttk.Frame(top, padding=10); f.pack(fill=tk.BOTH, expand=True)
        cur_o = {x.split(":")[0] for x in self.v["outfits"].get().split(";") if x.strip()}
        cur_p = {}
        for x in self.v["eprops"].get().split(";"):
            if x.strip():
                n, _, s = x.strip().split(":")[0].partition("@"); cur_p[n] = s
        ttk.Label(f, text="Outfits (skinned to the same skeleton; hide the body under them)", style="H.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ov, r = {}, 1
        for n in outs:
            meta = lib.load_rig("outfits/" + n).meta.get("outfit", {})
            ov[n] = tk.BooleanVar(value=n in cur_o)
            ttk.Checkbutton(f, text=n, variable=ov[n]).grid(row=r, column=0, sticky="w")
            ttk.Label(f, text="hides: %s   slot: %s" % ("+".join(meta.get("hide", [])) or "-", meta.get("slot") or "own")).grid(row=r, column=1, columnspan=2, sticky="w")
            r += 1
        if not outs:
            ttk.Label(f, text="(none - forge.py library add FILE --kind outfit, or python tools/make_equip_samples.py)").grid(row=r, column=0, columnspan=3, sticky="w"); r += 1
        ttk.Label(f, text="Props (rigid, attached to a socket)", style="H.TLabel").grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0)); r += 1
        pv, ps = {}, {}
        for n in props:
            meta = lib.load_rig("props/" + n).meta.get("prop", {})
            pv[n] = tk.BooleanVar(value=n in cur_p)
            ps[n] = tk.StringVar(value=cur_p.get(n) or meta.get("socket", "hand_r"))
            ttk.Checkbutton(f, text=n, variable=pv[n]).grid(row=r, column=0, sticky="w")
            ttk.Combobox(f, textvariable=ps[n], values=list(L.SOCKETS), state="readonly", width=8).grid(row=r, column=1, sticky="w")
            r += 1
        if not props:
            ttk.Label(f, text="(none - forge.py library add FILE --kind prop --socket hand_r)").grid(row=r, column=0, columnspan=3, sticky="w"); r += 1
        ttk.Label(f, text="Slot colours (e.g. Jersey=#c8102e,Armour=#777777)").grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0)); r += 1
        ttk.Entry(f, textvariable=self.v["slot_colors"], width=40).grid(row=r, column=0, columnspan=3, sticky="we"); r += 1

        def ok():
            keep_o = {x.split(":")[0]: x for x in self.v["outfits"].get().split(";") if x.strip()}
            self.v["outfits"].set("; ".join(keep_o.get(n, n) for n in outs if ov[n].get()))
            self.v["eprops"].set("; ".join("%s@%s" % (n, ps[n].get()) for n in props if pv[n].get()))
            top.destroy()
        bb = ttk.Frame(f); bb.grid(row=r, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(bb, text="OK", command=ok).pack(side=tk.RIGHT)
        ttk.Button(bb, text="Cancel", command=top.destroy).pack(side=tk.RIGHT, padx=4)
        self._equip_top = top
        return top

    def add_clip(self):
        p = filedialog.askopenfilename(title="Your video clip for one move", filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("All", "*.*")])
        if not p:
            return
        from tkinter import simpledialog
        mv = simpledialog.askstring("Move name", "Which move is this clip? (walk, run, jump, punch ...)", parent=self.root) or ""
        n = simpledialog.askstring("Frames", "How many sprite frames for %s?" % mv, initialvalue="8", parent=self.root) or "8"
        if mv.strip():
            cur = [x for x in self.v["clips"].get().split(";") if x.strip()]
            self.v["clips"].set("; ".join(cur + ["%s:%s=%s" % (mv.strip(), n.strip(), p)]))

    def run_cli(self, done_cb=None):
        argv = self.cli_argv(); mode = self.v["mode"].get()
        name = self.v["name"].get().strip() or "hero"; out = self.v["out"].get() or "out"
        from .moves import slug
        self._log("> python forge.py " + " ".join('"%s"' % x if " " in x else x for x in argv))
        self.build_btn.state(["disabled"]); self.pb["value"] = 0.05
        env = dict(os.environ); env["PYTHONUNBUFFERED"] = "1"
        if self.v["blender"].get().strip():
            env["SFS_BLENDER"] = self.v["blender"].get().strip()
        def work():
            res = None
            try:
                pr = subprocess.Popen([sys.executable, os.path.join(ROOT, "forge.py")] + argv, cwd=os.getcwd(), env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                n = 0
                for ln in pr.stdout:
                    self.q.put(("log", ln.rstrip())); n += 1
                    self.q.put(("pb", min(0.95, 0.05 + n / 120.0)))
                rc = pr.wait()
                if rc:
                    self.q.put(("err", "forge.py %s exited with code %d (see log)" % (mode, rc)))
                else:
                    d = os.path.join(out, slug(name) + "_scan") if mode == "scan" else os.path.join(out, slug(name))
                    sheet = os.path.join(d, "scan_preview.png" if mode == "scan" else "preview.png")
                    res = {"out": d, "ordered": [], "sheet": sheet if os.path.exists(sheet) else None, "cli": True}
            except Exception as e:
                self.q.put(("err", str(e)))
            self.q.put(("done", res))
            if done_cb:
                self.q.put(("cb", done_cb))
        threading.Thread(target=work, daemon=True).start()
        return True

    def on_build(self, done_cb=None):
        errs = self.validate()
        if errs:
            msg = "Please fix:\n- " + "\n- ".join(errs)
            self.status.configure(text=msg, foreground="#c01c28")
            if not self.autotest:
                messagebox.showwarning("Check your settings", msg)
            return False
        self.status.configure(text="")
        if self.v["mode"].get() in CLI_MODES:
            return self.run_cli(done_cb)
        try:
            cfg = self.config()
        except Exception as e:
            self.status.configure(text=str(e))
            if not self.autotest:
                messagebox.showerror("Settings", str(e))
            return False
        self.build_btn.state(["disabled"]); self.pb["value"] = 0.05
        def work():
            try:
                r = build(cfg, log=lambda s: self.q.put(("log", s)), progress=lambda f: self.q.put(("pb", f)))
                self.q.put(("done", r))
            except Exception as e:
                import traceback
                self.q.put(("log", traceback.format_exc())); self.q.put(("err", str(e))); self.q.put(("done", None))
            if done_cb:
                self.q.put(("cb", done_cb))
        threading.Thread(target=work, daemon=True).start()
        return True

    def walkthrough(self, done_cb=None):
        self.nb.select(self.buildtab)
        self.v["mode"].set("spec")
        self.v["spec"].set(os.path.join(ROOT, "examples_char.txt"))
        self.v["name"].set("hero")
        self.v["preset"].set(next(k for k in PRESETS if k.startswith("Fighter"))); self.load_preset()
        self.v["fw"].set("256"); self.v["fh"].set("256")
        self._log("Example walkthrough: building the sample character (examples_char.txt, Fighter 14 moves)...")
        def fin(app):
            if app.result:
                app.preview_window(app.result["out"])
            if done_cb:
                done_cb(app)
        self.on_build(fin)

    def preview_window(self, out):
        w = tk.Toplevel(self.root); w.title("Example result - " + out)
        im = Image.open(os.path.join(out, "preview.png")); im.thumbnail((900, 520))
        self._pw = ImageTk.PhotoImage(im)
        ttk.Label(w, image=self._pw).pack(padx=6, pady=6)
        files = sorted(f for f in os.listdir(out) if not f.startswith("."))
        expl = {"atlas.png": "the sprite sheet (one row per move)", "atlas.json": "frame rectangles + fps/loop for engines",
                "sprites.cfg": "same info as text, for spriteforge.h (C/raylib)", "character.ini": "size, ground line, pivot, moves",
                "moves": "every frame as its own PNG", "preview.png": "this contact sheet", "model.glb": "rigged 3D model (glTF)",
                "model.fbx": "rigged 3D model (FBX)", "build_report.txt": "what was made / filled", "console": "console export",
                "previews": "GIF per move"}
        txt = "\n".join("  %-18s %s" % (f, expl.get(f, "")) for f in files)
        ttk.Label(w, text="Your files are in %s:\n%s\n\nNext: Help > 'How to use a sprite sheet' shows how to put atlas.png in a game." % (
            os.path.abspath(out), txt), font="TkFixedFont", justify=tk.LEFT).pack(anchor="w", padx=8)
        bf = ttk.Frame(w); bf.pack(pady=6)
        ttk.Button(bf, text="Open folder", command=lambda: self._open(os.path.abspath(out))).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="How to use a sprite sheet", command=lambda: (w.destroy(), self.show_help("sprite-sheet"))).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Close", command=w.destroy).pack(side=tk.LEFT, padx=4)
        self.preview_win = w

    def _poll(self):
        try:
            while True:
                k, val = self.q.get_nowait()
                if k == "log":
                    self._log(val)
                elif k == "pb":
                    self.pb["value"] = val
                elif k == "err":
                    self.status.configure(text="Build failed: " + val)
                elif k == "done":
                    self.build_btn.state(["!disabled"]); self.result = val; self.pb["value"] = 1.0
                    if val and val.get("cli"):
                        if val.get("sheet"):
                            self.show_sheet(val["sheet"])
                        self.status.configure(text="Done: " + os.path.abspath(val["out"]), foreground="#26a269")
                    elif val:
                        names = [mv for mv, _ in val["ordered"]]
                        self.prev_cb["values"] = names
                        if names:
                            self.prev_move.set(names[0]); self.play(names[0])
                        self.show_sheet(os.path.join(val["out"], "turnaround_preview.png" if val.get("views") else "preview.png"))
                elif k == "cb":
                    val(self)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    # ------------------------------------------------------------ preview
    def show_sheet(self, path):
        if not os.path.isfile(path):
            return
        im = Image.open(path); im.thumbnail((max(300, self.sheet_lbl.winfo_width() or 380), 360))
        self._sheet = ImageTk.PhotoImage(im); self.sheet_lbl.configure(image=self._sheet)

    def play(self, mv, frames=None, fps=None):
        if frames is None:
            if not self.result:
                return
            fr = dict(self.result["ordered"]).get(mv)
            if not fr:
                return
            fps = next((m.fps for m in self.selected_moves() if m.name == mv), 12)
        else:
            fr = frames
        size = 270
        bg = checker(size, size, 10)
        self.anim_frames = []
        for im in fr:
            t = im.copy(); t.thumbnail((size, size), Image.NEAREST if im.width <= 128 else Image.LANCZOS)
            if t.width < size // 2:
                f = max(1, (size // 2) // t.width); t = t.resize((t.width * f, t.height * f), Image.NEAREST)
            b = bg.copy(); b.paste(t, ((size - t.width) // 2, (size - t.height) // 2), t)
            self.anim_frames.append(ImageTk.PhotoImage(b))
        self.anim_i = 0; self.anim_ms = int(1000 / max(1, fps or 12))
        self.prev_info.configure(text="%s - %d frames @ %s fps" % (mv, len(fr), fps))
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
        self._tick()

    def _tick(self):
        if not self.anim_frames:
            return
        self.prev_lbl.configure(image=self.anim_frames[self.anim_i % len(self.anim_frames)])
        self.anim_i += 1
        self.anim_job = self.root.after(self.anim_ms, self._tick)

    def quick_preview(self):
        from .build import _mannequin_frames, Report
        cfg = self.config(); cfg.resolved()
        mv = self.prev_move.get() or (cfg.moves[0].name if cfg.moves else "idle")
        sel = [m for m in cfg.moves if m.name == mv] or cfg.moves[:1]
        if not sel:
            return
        from .spec import load_spec, CharacterSpec
        sp = load_spec(cfg.spec_path) if cfg.spec_path else CharacterSpec(kit=cfg.kit)
        if cfg.kit:
            sp.kit = cfg.kit
        cfg.moves = sel
        fr = _mannequin_frames(cfg, sp, Report(lambda s: None))
        if fr:
            self.play(sel[0].name, fr[sel[0].name][0], sel[0].fps)


def run_script(app, steps, caplog=None, flag="/tmp/sfs_gui_done"):
    """Tutorial / demo driver: runs steps one after another on the real UI (used to record the help videos).
    step keys: wait (s, before), cap (caption, logged with a timestamp to caplog), mode, set {var: val},
    type [var, text] (typed letter by letter), bools, preset, profile, help, tab, scroll, point (widget attr),
    build (waits for the build), play, create_profile, spec_editor (path), spec_type (text appended),
    spec_save, close (closes pop-up windows), preview_window, quit."""
    import time as _t
    cap = open(caplog, "a") if caplog else None
    root = app.root
    def log_cap(text):
        if cap:
            cap.write(json.dumps({"t": _t.time(), "cap": text}) + "\n"); cap.flush()
    def point(name):
        wd = getattr(app, name, None)
        if wd is None:
            return
        root.update_idletasks()
        x = wd.winfo_rootx() + wd.winfo_width() // 2; y = wd.winfo_rooty() + wd.winfo_height() // 2
        root.event_generate("<Motion>", warp=True, x=x - root.winfo_rootx(), y=y - root.winfo_rooty())
    def typer(setter, text, then, i=0):
        if i > len(text):
            return then()
        setter(text[:i]); root.after(35 if len(text) < 80 else 8, lambda: typer(setter, text, then, i + 1))
    def step(i):
        if i >= len(steps):
            log_cap("")
            open(flag, "w").write("done")
            return
        st = steps[i]
        nxt = lambda *a: root.after(int(1000 * steps[i + 1].get("wait", 0.8)) if i + 1 < len(steps) else 300, lambda: step(i + 1))
        if "cap" in st:
            log_cap(st["cap"])
        if "tab" in st:
            t = st["tab"]   # v8: ints keep the pre-v8 order (0 Build, 1 Library, 2 Help); "start" = the Start tab
            app.nb.select({"start": app.hometab, "appearance": app.looktab, "build": app.buildtab, "library": app.libtab_frame, "help": app.helptab}.get(t) if isinstance(t, str)
                          else [app.buildtab, app.libtab_frame, app.helptab][int(t)])
        if "mode" in st:
            app.v["mode"].set(st["mode"])
        for k, val in st.get("set", {}).items():
            app.v[k].set(val)
        for k, val in st.get("bools", {}).items():
            app.b[k].set(val)
        if "preset" in st:
            app.v["preset"].set(st["preset"]); app.load_preset()
        if "profile" in st:
            app.v["profile"].set(st["profile"]); app.apply_profile()
        if "untick" in st:
            for row in app.rows:
                if row[0].name in st["untick"]:
                    row[1].set(False)
        if "help" in st:
            app.show_help(st["help"])
        if "doctor" in st:
            app.show_doctor()
        if "scroll" in st:
            root.update_idletasks(); app.left_canvas.yview_moveto(float(st["scroll"]))
        if "help_scroll" in st and True:
            app.help_txt.yview_moveto(float(st["help_scroll"]))
        if "point" in st:
            point(st["point"])
        if "close" in st:
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
        if "spec_editor" in st:
            app.spec_editor(st["spec_editor"])
        if "create_profile" in st:
            app.create_profile_dialog(st["create_profile"])
        if "preview_window" in st and app.result:
            app.preview_window(app.result["out"])
        if "play" in st:
            app.prev_move.set(st["play"]); app.play(st["play"])
        if "lib" in st:              # Library tab actions (v6)
            L_ = app.libtab; d_ = st["lib"]
            if "select" in d_:
                L_.tree.selection_set(d_["select"]); L_.tree.see(d_["select"]); root.update(); L_.select()
            if "clip" in d_:
                L_.clip.set(d_["clip"]); L_.t.set(float(d_.get("t", 0.0))); L_.draw()
            if d_.get("play"):
                L_.toggle_play()
            if d_.get("stop"):
                L_.stop()
            if d_.get("use_template"):
                L_.use_template()
            if d_.get("use_clip"):
                L_.use_clip(d_["use_clip"])
            if "licence" in d_:
                L_.licence_dialog(d_["licence"] or None)
            if "bonemap" in d_:
                L_.bonemap_dialog(d_["bonemap"] or None)
            if "install" in d_:
                L_.install_pack(d_["install"], d_.get("accept"))
            if "export" in d_:
                L_.export_pack(d_["export"].get("vars", {}).get("out"), d_["export"])
            if "add" in d_:
                L_.add_file(d_["add"], d_.get("name"), d_.get("licence_rec"))
            if "remove" in d_:
                L_.tree.selection_set(d_["remove"]); L_.remove()
        if "home" in st:             # v9: Start-tab wizard {"step": n, "style_tab": k, "goal": g, "target": label, "style_preview": true}
            h = st["home"]; app.nb.select(app.hometab)
            if h.get("target"):
                app.home.target.set(h["target"]); app.home.apply_target()
            if h.get("goal"):
                app.home.goal = h["goal"]
            if h.get("style_tab"):
                app.home.style_tab = h["style_tab"]
                if getattr(app.home, "style", None) is not None and app.home.step == h.get("step", app.home.step):
                    try:
                        app.home.style.nb.select(app.home.style.tabs[h["style_tab"]])
                    except Exception:
                        pass
            if "step" in h and h["step"] != app.home.step:
                app.home.go(int(h["step"]))
            if h.get("style_preview"):
                k = app.home.style_tab
                app.home.style.preview(k)
                btn = getattr(app.home.style, "pv_" + k)[0]
                log_cap("@fast")
                def wait_sp(n=0):
                    if "disabled" in btn.state() and n < 900:
                        return root.after(200, lambda: wait_sp(n + 1))
                    log_cap("@normal"); nxt()
                return root.after(400, wait_sp)
            if h.get("face_row"):        # {"punch": "shout"} - change a per-move expression in the Faces grid
                for mv, e in h["face_row"].items():
                    app.v["expr_map"].set(",".join(x for x in app.v["expr_map"].get().split(",") if x and not x.startswith(mv + "=")) + ",%s=%s" % (mv, e))
                try:
                    app.home.style._face_rows()
                except Exception:
                    pass
        if "move_clip" in st:
            app.set_move_clip(*st["move_clip"])
        if "shot" in st:             # screenshot of the whole virtual screen (Xvfb + imagemagick)
            root.update(); root.update_idletasks()
            import shutil as _sh
            imp = _sh.which("import") or "/usr/bin/import"
            subprocess.run([imp, "-window", "root", st["shot"]], env=dict(os.environ))
        if "quit" in st:
            log_cap(""); open(flag, "w").write("done"); return
        if "type" in st:
            k, text = st["type"]
            return typer(app.v[k].set, text, nxt)
        if "spec_type" in st:
            t = app.spec_text
            def put(txt):
                t.delete("spec_typed.first", "end-1c") if t.tag_ranges("spec_typed") else None
                t.insert("end-1c", txt, "spec_typed"); t.see("end")
            t.tag_configure("spec_typed", background="#fff3b0")
            return typer(put, st["spec_type"], nxt)
        if "spec_replace" in st:      # [key, value]: rewrite one 'key = value' line, highlighted
            k, val = st["spec_replace"]; t = app.spec_text
            idx = t.search(r"^%s\s*=" % k, "1.0", regexp=True)
            if idx:
                line = int(idx.split(".")[0])
                t.delete("%d.0" % line, "%d.end" % line)
                t.insert("%d.0" % line, "%-13s = %s" % (k, val), "spec_typed"); t.see("%d.0" % line)
                t.tag_configure("spec_typed", background="#fff3b0")
        if "spec_save" in st:
            app.spec_save()
        if st.get("build"):
            log_cap("@fast")
            def built(a):
                log_cap("@normal"); nxt()
            if not app.on_build(built):
                built(app)
            return
        nxt()
    step(0)


def main():
    root = tk.Tk()
    app = Studio(root)
    auto = os.environ.get("SFS_AUTOTEST")   # test harness: json with settings to apply, then build / validate / show help
    if auto:
        app.autotest = True
        d = json.loads(auto)
        flag = d.get("flag", "/tmp/sfs_gui_done")
        if "mode" in d:
            app.v["mode"].set(d["mode"])
        for k, val in d.get("vars", {}).items():
            app.v[k].set(val)
        for k, val in d.get("bools", {}).items():
            app.b[k].set(val)
        if "preset" in d:
            app.v["preset"].set(d["preset"]); app.load_preset()
        if d.get("profile"):
            app.v["profile"].set(d["profile"]); app.apply_profile()
            for k, val in d.get("vars_after_profile", {}).items():
                app.v[k].set(val)
        if "untick" in d:
            for row in app.rows:
                if row[0].name in d["untick"]:
                    row[1].set(False)
        def finished(a):
            if d.get("play"):
                a.prev_move.set(d["play"]); a.play(d["play"])
            a.root.after(600, lambda: open(flag, "w").write("done"))
        def start():
            act = d.get("action", "build")
            if d.get("help"):
                app.show_help(d["help"])
            if d.get("doctor"):
                app.show_doctor(finished); return
            if d.get("tooltip"):
                for ws, modes in app.field_rows:
                    if isinstance(ws[0], ttk.Label) and ws[0].cget("text").startswith(d["tooltip"]):
                        ws[3].event_generate("<Button-1>")
                        break
            if d.get("scroll"):
                app.root.update_idletasks(); app.left_canvas.yview_moveto(float(d["scroll"]))
            if d.get("equip_dialog"):
                app.equip_dialog()
            if d.get("create_profile") is not None:
                app.create_profile_dialog(d["create_profile"])
            if d.get("open_profile"):
                app.profile_cb.event_generate("<Button-1>")
                app.root.after(300, lambda: app.profile_cb.event_generate("<Down>"))
            if d.get("open_console"):
                app.console_cb.event_generate("<Button-1>")
                app.root.after(300, lambda: app.console_cb.event_generate("<Down>"))
            if d.get("appearance") is not None:  # v10.2 Appearance tab: {"values": {...}, "view": ..., "save": png}
                a_ = d["appearance"]; app.nb.select(app.looktab)
                if a_.get("view"):
                    app.look.view.set(a_["view"])
                if a_.get("randomise") is not None:
                    app.look.randomise(a_["randomise"])
                app.look.set_values(a_.get("values", {}))
                def shot():
                    if a_.get("save") and app.look.last_image is not None:
                        app.look.last_image.save(a_["save"])
                    finished(app)
                app.root.after(0, lambda: app.look._rebuild(shot)); return
            if d.get("home") is not None:      # v8 Start-tab wizard: {"target": label, "step": n, "action": "preview_turn"|"build"}
                h = d["home"]; app.nb.select(app.hometab)
                if h.get("target"):
                    app.home.target.set(h["target"]); app.home.apply_target()
                if h.get("goal"):
                    app.home.goal = h["goal"]
                app.home.step = 0
                ha = h.get("action")
                from .gui_home import BUILD_STEP
                if h.get("style_tab"):
                    app.home.style_tab = h["style_tab"]
                for i in range(BUILD_STEP if ha == "build" else int(h.get("step", 0))):
                    app.home.go(i + 1)
                if ha == "style_preview":        # v9: Style step preview (faces / colours / variants)
                    k = h.get("style_tab", "faces")
                    app.home.style.preview(k)
                    btn = getattr(app.home.style, "pv_" + k)[0]
                    def wait_s(n=0):
                        if "disabled" in btn.state() and n < 900:
                            return app.root.after(200, lambda: wait_s(n + 1))
                        finished(app)
                    app.root.after(500, wait_s); return
                if h.get("raw") and hasattr(app.home, "raw"):
                    app.home.raw.set(h["raw"])
                if ha == "cutout":
                    app.home.cutout()
                    def wait_cut(n=0):
                        if "disabled" in app.home.cut_btn.state() and n < 900:
                            return app.root.after(200, lambda: wait_cut(n + 1))
                        finished(app)
                    app.root.after(500, wait_cut); return
                if ha == "preview_turn":
                    app.home.preview_turn()
                    def wait_turn(n=0):
                        if "disabled" in app.home.turn_btn.state() and n < 600:
                            return app.root.after(200, lambda: wait_turn(n + 1))
                        finished(app)
                    app.root.after(500, wait_turn); return
                if ha == "build":
                    app.home.build()
                    def wait_b(n=0):
                        if "disabled" in app.home.go_btn.state() and n < 3000:
                            return app.root.after(200, lambda: wait_b(n + 1))
                        finished(app)
                    app.root.after(500, wait_b); return
                finished(app); return
            if act == "build":
                if not app.on_build(finished):
                    finished(app)
            elif act == "validate":
                errs = app.validate()
                app.status.configure(text=("Please fix:\n- " + "\n- ".join(errs)) if errs else "All required fields OK - ready to BUILD.",
                                     foreground="#c01c28" if errs else "#26a269")
                finished(app)
            elif act == "walkthrough":
                app.walkthrough(finished)
            else:
                finished(app)
        if d.get("script"):
            root.after(800, lambda: run_script(app, d["script"], d.get("caplog"), flag))
        else:
            root.after(800, start)
    root.mainloop()
    return 0
