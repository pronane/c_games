"""v8 Start tab: a 5-step guided wizard over the same Studio settings (and the same build core as forge.py build).

1 Start from  ->  2 Your source  ->  3 Look & view (turn)  ->  4 Game target  ->  5 Build.
Every choice just fills in the Build tab (which stays as the 'advanced' view), and step 5 shows the exact
forge.py command that does the same thing, so nothing here is hidden magic."""
from __future__ import annotations
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from .moves import MoveSpec, PRESETS
from . import consoles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = ["1  Start from", "2  Your source", "3  Look & view", "4  What to make", "5  Build"]
SOURCES = [  # mode, title, one-line description
    ("photo", "A photo of a person", "Your own photo. The person is cut out (your real pixels) and posed per move; can be turned side-on."),
    ("video", "Video clips of each move", "One clip per move (e.g. walk.mp4, punch.mp4); frames are cut out and laid out as sprites."),
    ("frames", "Frames / sprite sheets", "A folder of frames, one strip per move, or one big sheet you already made."),
    ("mannequin", "Make a character (no photo)", "The built-in 3D mannequin or a MakeHuman CC0 body in team colours (+ GLB / FBX models)."),
    ("library", "A rig from my library", "An FBX / GLB from the Library tab; its own mesh and clips, missing moves retargeted."),
    ("spec", "A text description", "A key=value text file describing a made-up character (Help > Spec file)."),
]
# Egyptian Fighter / Padel Wars move list (same names, frames and fps as the bundled fighters)
EF14 = "idle:5:8:loop,walk:10:11:loop,crouch:4:17:once,jump:8:10:once,punch:6:14:once,kick:6:14:once," \
       "pyramid_blast:6:12:once,bum_fireball:8:12:once,hit:6:10:once,throw:6:14:once,jump_attack:6:17:once," \
       "taunt:6:8:loop,block:6:8:once,victory:8:8:loop"
TARGETS = [  # label, preset or moves, frame WxH, figure px, ground y, profile
    ("Egyptian Fighter / Padel Wars fighter (14 moves, HD 672x800)", EF14, "672x800", "560", "788", None),
    ("Fighter, generic (14 moves, 256x256)", "Fighter (14 moves)", "256x256", "", "", None),
    ("Platformer (10 moves, 128x128)", "Platformer basics (10 moves)", "128x128", "", "", None),
    ("Kart racer - TurboTumble64 (12 moves)", "Kart racer - TurboTumble64 (12 moves)", "256x256", "", "", None),
    ("Gaelic football (36 moves)", "Gaelic football (36 moves)", "256x256", "", "", None),
    ("Retro NES (64x64, 4 colours a sprite)", "Platformer basics (10 moves)", "64x64", "", "", "retro_nes"),
]


def _ic(name, size=20):
    from . import icons
    return icons.tk_icon(name, size)


def ef_moves():
    out = []
    for it in EF14.split(","):
        n, fr, fps, lp = it.split(":")
        out.append(MoveSpec(n, n.replace("_", " ").title(), "Fighter", int(fr), int(fps), lp == "loop", "", "Egyptian Fighter move"))
    return out


def _q(path):
    return '"%s"' % path if (" " in path or "'" in path) else path


def forge_command(app):
    """The forge.py command line equivalent to the current Studio settings (shown in step 5 and saved with the build)."""
    v, b = app.v, app.b
    mode = v["mode"].get()
    if mode in ("video", "mocap", "scan"):
        return ["python", "forge.py"] + app.cli_argv()
    a = ["python", "forge.py", "build"]
    if mode == "photo":
        a += ["--photo", v["photo"].get().strip()]
        if v["landmarks"].get().strip():
            a += ["--landmarks", v["landmarks"].get().strip()]
        from .gui import turn_value
        try:
            t = turn_value(v["turn"].get(), v["turn_yaw"].get())
        except ValueError:
            t = 0
        if t % 360:
            a += ["--turn", ("%g" % t)]
            if v["turn_depth"].get() not in ("", "auto"):
                a += ["--turn-depth", v["turn_depth"].get()]
            if v["turn_side"].get().strip():
                a += ["--side-photo", v["turn_side"].get().strip()]
        elif v["fill"].get() not in ("", "placeholder"):
            a += ["--fill", v["fill"].get()]
        if v["cutout"].get() not in ("", "auto"):
            a += ["--cutout", v["cutout"].get()]
    elif mode == "frames":
        a += ["--frames", v["frames"].get().strip()]
    elif mode == "sheet":
        a += ["--sheet", v["sheet"].get().strip()]
    elif mode == "movesheets":
        for it in [x for x in v["movesheets"].get().split(";") if "=" in x]:
            a += ["--move-sheet", it.strip()]
    elif mode == "spec":
        a += ["--spec", v["spec"].get().strip()]
    elif mode == "mannequin":
        a += ["--mannequin"]
        if v["human"].get().strip():
            a += ["--human", v["human"].get().strip()]
    elif mode == "library":
        a += ["--rig", v["rig"].get().strip()]
    if mode != "spec" or v["name"].get() not in ("", "hero"):
        a += ["--name", v["name"].get().strip() or "hero"]
    if v["kit"].get() and mode in ("spec", "mannequin", "library") and not v["kit"].get().startswith("("):
        a += ["--kit", v["kit"].get()]
    mv = app.selected_moves()
    a += ["--moves", ",".join("%s:%d:%d:%s" % (m.name, m.frames, m.fps, "loop" if m.loop else "once") for m in mv)]
    a += ["--frame", "%sx%s" % (v["fw"].get().strip() or "256", v["fh"].get().strip() or "256")]
    if v["figh"].get().strip():
        a += ["--figure-h", v["figh"].get().strip()]
    if v["ground"].get().strip():
        a += ["--ground-y", v["ground"].get().strip()]
    ck = consoles.by_label(v["console"].get())
    if ck:
        a += ["--console", ck]
        if b["dither"].get() != consoles.PRESETS[ck]["dither"]:
            a += ["--dither"] if b["dither"].get() else ["--no-dither"]
    if mode in ("spec", "mannequin", "library"):
        a += [] if b["glb"].get() else ["--no-glb"]
        a += [] if b["fbx"].get() else ["--no-fbx"]
        a += ["--anim-export"] if b["anim_export"].get() else []
    if v["profile"].get() not in ("", "(none)"):
        a += ["--profile", v["profile"].get()]
    if v["quality"].get() == "draft":
        a += ["--quality", "draft"]
    if not b["cache"].get():
        a += ["--no-cache"]
    a += ["--out", v["out"].get().strip() or "out"]
    return a


class HomeTab:
    def __init__(self, app, frame):
        self.app, self.f = app, frame
        self.step = 0
        self.src = tk.StringVar(value="photo")
        self.person = tk.StringVar(value="largest")
        self.target = tk.StringVar(value=TARGETS[0][0])
        self.goal = "hd"
        self.t0 = 0.0
        self._imgs = {}
        import tkinter.font as tkfont
        fam = tkfont.nametofont("TkDefaultFont").actual()["family"]   # Segoe UI on Windows, DejaVu Sans etc. elsewhere
        self.fam = fam
        st = ttk.Style()
        st.configure("Step.TLabel", font=(fam, 10), foreground="#777", padding=(10, 4))
        st.configure("StepOn.TLabel", font=(fam, 10, "bold"), foreground="#ffffff", background="#1a5fb4", padding=(10, 4))
        st.configure("Big.TLabel", font=(fam, 15, "bold"))
        st.configure("Tile.TRadiobutton", font=(fam, 11, "bold"), padding=6)
        st.configure("Go.TButton", font=(fam, 12, "bold"), padding=(18, 8))
        top = ttk.Frame(frame); top.pack(fill=tk.X, padx=10, pady=(10, 4))
        self.step_lbls = []
        for i, s in enumerate(STEPS):
            lab = ttk.Label(top, text=" " + s, image=_ic(["start", "photo", "turn", "hd", "build"][i], 18), compound=tk.LEFT,
                            style="Step.TLabel", cursor="hand2"); lab.pack(side=tk.LEFT, padx=2)
            lab.bind("<Button-1>", lambda e, i=i: self.go(i)); self.step_lbls.append(lab)
        ttk.Label(top, text="   Advanced: every setting is on the Build tab.", foreground="#555").pack(side=tk.LEFT, padx=10)
        ttk.Separator(frame).pack(fill=tk.X, padx=10)
        self.body = ttk.Frame(frame); self.body.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        nav = ttk.Frame(frame); nav.pack(fill=tk.X, padx=16, pady=8)
        self.back_btn = ttk.Button(nav, text="< Back", command=lambda: self.go(self.step - 1)); self.back_btn.pack(side=tk.LEFT)
        self.next_btn = ttk.Button(nav, text="Next >", command=lambda: self.go(self.step + 1)); self.next_btn.pack(side=tk.RIGHT)
        self.msg = ttk.Label(nav, text="", foreground="#c01c28"); self.msg.pack(side=tk.LEFT, padx=12)
        self.go(0)

    # ------------------------------------------------------------ navigation
    def go(self, i):
        i = max(0, min(len(STEPS) - 1, i))
        if i > self.step:
            err = self.check(self.step)
            if err:
                self.msg.configure(text=err); return
        self.msg.configure(text="")
        self.step = i
        for k, lab in enumerate(self.step_lbls):
            lab.configure(style="StepOn.TLabel" if k == i else "Step.TLabel")
        for w in self.body.winfo_children():
            w.destroy()
        [self.s_start, self.s_source, self.s_look, self.s_target, self.s_build][i]()
        self.back_btn.state(["disabled"] if i == 0 else ["!disabled"])
        self.next_btn.state(["disabled"] if i == len(STEPS) - 1 else ["!disabled"])

    def check(self, i):
        v = self.app.v; m = v["mode"].get()
        if i == 1:
            need = {"photo": "photo", "frames": "frames", "sheet": "sheet", "spec": "spec", "library": "rig"}.get(m)
            if m == "frames" and not v["frames"].get().strip() and v["sheet"].get().strip():
                v["mode"].set("sheet"); return ""
            if need and not v[need].get().strip():
                return "Pick your %s first (the ... button)." % {"rig": "library rig"}.get(need, need)
            if need and need != "rig" and not os.path.exists(v[need].get().strip()):
                return "Can't find %s" % v[need].get().strip()
            if m in ("video", "mocap") and not v["clips"].get().strip():
                return "Add at least one clip (Add clip...)."
        return ""

    def _title(self, t, sub=""):
        ttk.Label(self.body, text=t, style="Big.TLabel").pack(anchor="w")
        if sub:
            ttk.Label(self.body, text=sub, foreground="#444", wraplength=1200, justify=tk.LEFT).pack(anchor="w", pady=(2, 10))

    def _file_row(self, parent, label, key, kind, help_key=None):
        r = ttk.Frame(parent); r.pack(fill=tk.X, pady=3)
        ttk.Label(r, text=label, width=24).pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=self.app.v[key], width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(r, text="...", width=3, command=lambda: self.app._browse(key, kind)).pack(side=tk.LEFT, padx=3)
        self.app._q(r, help_key or label).pack(side=tk.LEFT)
        return r

    # ------------------------------------------------------------ steps
    def s_start(self):
        self._title("What are you starting from?", "Pick one. You can change any detail later on the Build tab.")
        g = ttk.Frame(self.body); g.pack(fill=tk.X)
        cur = self.app.v["mode"].get()
        self.src.set("frames" if cur in ("sheet", "movesheets") else ("video" if cur == "mocap" else cur))
        for i, (mode, title, desc) in enumerate(SOURCES):
            c = ttk.Frame(g, relief=tk.RIDGE, borderwidth=2, padding=10)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6); g.columnconfigure(i % 3, weight=1)
            hr = ttk.Frame(c); hr.pack(anchor="w")
            ttk.Radiobutton(hr, text=title, value=mode, variable=self.src, style="Tile.TRadiobutton",
                            command=lambda m=mode: self.app.v["mode"].set(m)).pack(side=tk.LEFT)
            ttk.Label(hr, image=_ic(mode, 28)).pack(side=tk.LEFT, padx=6)
            ttk.Label(c, text=desc, wraplength=360, foreground="#444", justify=tk.LEFT).pack(anchor="w", padx=(26, 0))
        nf = ttk.Frame(self.body); nf.pack(fill=tk.X, pady=14)
        ttk.Label(nf, text="Character name", width=24).pack(side=tk.LEFT)
        ttk.Entry(nf, textvariable=self.app.v["name"], width=40).pack(side=tk.LEFT)
        ttk.Label(self.body, text="Already know Sprite Forge? Skip straight to the Build tab, or Help > Example walkthrough for a 1-click sample.",
                  foreground="#555").pack(anchor="w", pady=(10, 0))

    def s_source(self):
        m = self.app.v["mode"].get(); v = self.app.v
        if m == "photo":
            self._title("Your photo", "Pick the photo, choose which person (if there are several), then 'Cut out person'. "
                        "That writes a clean transparent cut-out plus 33 pose points (landmarks.json) that the posed "
                        "moves and the Turn option need. Only your photo's own pixels are used.")
            self.raw = tk.StringVar(value=v["photo"].get())
            r = ttk.Frame(self.body); r.pack(fill=tk.X, pady=3)
            ttk.Label(r, text="Photo", width=24).pack(side=tk.LEFT)
            ttk.Entry(r, textvariable=self.raw, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(r, text="...", width=3, command=self._pick_raw).pack(side=tk.LEFT, padx=3)
            r2 = ttk.Frame(self.body); r2.pack(fill=tk.X, pady=3)
            ttk.Label(r2, text="Which person", width=24).pack(side=tk.LEFT)
            ttk.Combobox(r2, textvariable=self.person, values=["largest", "left", "right", "tallest", "center", "0", "1", "2"],
                         width=10, state="readonly").pack(side=tk.LEFT)
            self.cut_btn = ttk.Button(r2, text=" Cut out person", image=_ic("photo"), compound=tk.LEFT, command=self.cutout); self.cut_btn.pack(side=tk.LEFT, padx=8)
            ttk.Label(r2, text="(needs rembg + mediapipe - Help > Check setup; photos that already have a transparent background can skip this)",
                      foreground="#555").pack(side=tk.LEFT)
            self.cut_info = ttk.Label(self.body, text="", foreground="#26a269", wraplength=1200, justify=tk.LEFT)
            self.cut_info.pack(anchor="w", pady=4)
            self.thumb = ttk.Label(self.body); self.thumb.pack(anchor="w")
            self._show(v["photo"].get(), self.thumb, 360)
            if v["landmarks"].get():
                self.cut_info.configure(text="Using cut-out %s with pose points %s" % (v["photo"].get(), v["landmarks"].get()))
        elif m in ("video", "mocap"):
            self._title("Your clips", "One clip per move. 'Add clip...' asks for the file and which move it is. "
                        "Tick 3D below to get a tracked mannequin (GLB/FBX) instead of cut-out sprites.")
            r = ttk.Frame(self.body); r.pack(fill=tk.X)
            ttk.Entry(r, textvariable=v["clips"], width=110).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(r, text="Add clip...", command=self.app.add_clip).pack(side=tk.LEFT, padx=4)
            ttk.Radiobutton(self.body, text="Sprites cut from the video (your pixels)", value="video", variable=v["mode"]).pack(anchor="w", pady=(8, 0))
            ttk.Radiobutton(self.body, text="Body tracking -> 3D mannequin performs the move (needs mediapipe)", value="mocap", variable=v["mode"]).pack(anchor="w")
        elif m in ("frames", "sheet", "movesheets"):
            self._title("Your frames", "Either a folder (walk/01.png ... or walk_01.png ...) or one sheet with one row per move.")
            self._file_row(self.body, "Frames folder", "frames", "dir", "Frames folder")
            ttk.Label(self.body, text="... or ...").pack(anchor="w", padx=180)
            self._file_row(self.body, "One sprite sheet", "sheet", "image", "Sprite sheet")
            ttk.Label(self.body, text="One strip per move? Use 'Per-move sheets' on the Build tab.", foreground="#555").pack(anchor="w", pady=6)
        elif m == "mannequin":
            self._title("Make a character", "No photo needed. Leave the body empty for the default mannequin, or pick a MakeHuman (CC0) body.")
            r = ttk.Frame(self.body); r.pack(fill=tk.X, pady=3)
            ttk.Label(r, text="MakeHuman body", width=24).pack(side=tk.LEFT)
            ttk.Combobox(r, textvariable=v["human"], width=70, values=self.app.human_cb.cget("values")).pack(side=tk.LEFT)
            r = ttk.Frame(self.body); r.pack(fill=tk.X, pady=3)
            ttk.Label(r, text="Kit (team colours)", width=24).pack(side=tk.LEFT)
            ttk.Combobox(r, textvariable=v["kit"], width=24, values=self.app.kit_cb.cget("values"), state="readonly").pack(side=tk.LEFT)
        elif m == "library":
            self._title("Library rig", "Pick a rig you added on the Library tab, or browse to any FBX / GLB.")
            r = ttk.Frame(self.body); r.pack(fill=tk.X, pady=3)
            ttk.Label(r, text="Rig", width=24).pack(side=tk.LEFT)
            ttk.Combobox(r, textvariable=v["rig"], width=50, values=self.app.rig_cb.cget("values")).pack(side=tk.LEFT)
            ttk.Button(r, text="...", width=3, command=lambda: self.app._browse("rig", "rigfile")).pack(side=tk.LEFT, padx=3)
        else:
            self._title("Text description", "A key=value file. 'New spec from template' on the Build tab writes one to edit.")
            self._file_row(self.body, "Spec file", "spec", "spec", "Spec file")

    def s_look(self):
        m = self.app.v["mode"].get(); v = self.app.v
        self._title("Look & view", "How the character faces in the game.")
        if m != "photo":
            ttk.Label(self.body, text="Turning is for photo characters. 3D characters (mannequin / library / spec) use 'Camera yaw' on "
                      "the Build tab (any angle, real 3D); video sprites keep the angle they were filmed at ('Flip' mirrors them).",
                      wraplength=1100, justify=tk.LEFT).pack(anchor="w")
            r = ttk.Frame(self.body); r.pack(anchor="w", pady=8)
            ttk.Label(r, text="Camera yaw (3D)", width=24).pack(side=tk.LEFT)
            ttk.Entry(r, textvariable=v["yaw"], width=8).pack(side=tk.LEFT)
            ttk.Checkbutton(self.body, text="Flip to face right (imported / video sprites)", variable=self.app.b["flip"]).pack(anchor="w")
            return
        from .gui import TURN_CHOICES
        row = ttk.Frame(self.body); row.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(row); left.pack(side=tk.LEFT, fill=tk.Y, anchor="n")
        ttk.Label(left, text="Facing", font=(self.fam, 11, "bold")).pack(anchor="w")
        for c in TURN_CHOICES:
            ttk.Radiobutton(left, text=c.replace("  ", "  -  ", 1), value=c, variable=v["turn"],
                            command=lambda: v["turn_yaw"].set("")).pack(anchor="w", pady=1)
        f = ttk.Frame(left); f.pack(anchor="w", pady=(8, 2))
        ttk.Label(f, text="Fine angle (optional)").pack(side=tk.LEFT)
        ttk.Spinbox(f, from_=0, to=359, increment=15, textvariable=v["turn_yaw"], width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="degrees").pack(side=tk.LEFT); self.app._q(f, "Turn angle").pack(side=tk.LEFT)
        f = ttk.Frame(left); f.pack(anchor="w", pady=2)
        ttk.Label(f, text="Body depth from").pack(side=tk.LEFT)
        ttk.Combobox(f, textvariable=v["turn_depth"], values=["auto", "template", "relief", "side"], width=9, state="readonly").pack(side=tk.LEFT, padx=4)
        self.app._q(f, "Turn depth").pack(side=tk.LEFT)
        f = ttk.Frame(left); f.pack(anchor="w", fill=tk.X, pady=2)
        ttk.Label(f, text="Side reference (optional)").pack(side=tk.LEFT)
        ttk.Entry(f, textvariable=v["turn_side"], width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="...", width=3, command=lambda: self.app._browse("turn_side", "image")).pack(side=tk.LEFT)
        self.app._q(f, "Turn side reference").pack(side=tk.LEFT)
        ttk.Label(left, text="Honest note: from ONE front photo the side view is estimated (depth from the MakeHuman CC0 body "
                  "or your side reference; colours from the front, the back from edge colours). It looks right in motion; "
                  "the face profile and hidden side are guesses.", wraplength=520, foreground="#555", justify=tk.LEFT).pack(anchor="w", pady=8)
        self.turn_btn = ttk.Button(left, text=" Preview this view", image=_ic("turn"), compound=tk.LEFT, command=self.preview_turn); self.turn_btn.pack(anchor="w")
        self.turn_info = ttk.Label(left, text="", foreground="#26a269", wraplength=520); self.turn_info.pack(anchor="w", pady=4)
        self.turn_img = ttk.Label(row); self.turn_img.pack(side=tk.LEFT, padx=20, anchor="n")

    # ---- step 4: three goal tabs (HD sprite sheet / retro console sprites / 3D files) + move picker
    GOALS = [("hd", "HD sprite sheet"), ("retro", "Retro console sprites"), ("3d", "3D files")]

    def s_target(self):
        from . import icons
        v = self.app.v
        self._title("What to make", "Three goals, one tab each. They add up: one build can make the HD sheet, a console version "
                    "and 3D files together. Everything here is also on the Build tab.")
        self.goal_nb = nb = ttk.Notebook(self.body); nb.pack(fill=tk.BOTH, expand=True)
        self.goal_tabs = {}
        for key, label in self.GOALS:
            fr = ttk.Frame(nb, padding=10)
            nb.add(fr, text="  %s  " % label, image=icons.tk_icon(key, 22), compound=tk.LEFT)
            self.goal_tabs[key] = fr
        self._goal_hd(self.goal_tabs["hd"]); self._goal_retro(self.goal_tabs["retro"]); self._goal_3d(self.goal_tabs["3d"])
        nb.select(self.goal_tabs.get(self.goal, self.goal_tabs["hd"]))
        nb.bind("<<NotebookTabChanged>>", lambda e: setattr(self, "goal", [k for k, f in self.goal_tabs.items() if str(f) == nb.select()][0]))
        f = ttk.Frame(self.body); f.pack(anchor="w", pady=(8, 2), fill=tk.X)
        ttk.Label(f, text="Output folder", width=16).pack(side=tk.LEFT)
        ttk.Entry(f, textvariable=v["out"], width=50).pack(side=tk.LEFT)
        ttk.Button(f, text="...", width=3, command=lambda: self.app._browse("out", "dir")).pack(side=tk.LEFT, padx=3)
        self.tinfo = ttk.Label(self.body, text="", foreground="#1a5fb4", font=(self.fam, 10, "bold")); self.tinfo.pack(anchor="w", pady=4)
        self._tinfo()

    def _goal_hd(self, tab):
        left = ttk.Frame(tab); left.pack(side=tk.LEFT, fill=tk.Y, anchor="n")
        ttk.Label(left, text="Game / move set", font=(self.fam, 11, "bold")).pack(anchor="w")
        for t in TARGETS:
            ttk.Radiobutton(left, text=t[0], value=t[0], variable=self.target, command=self.apply_target).pack(anchor="w", pady=1)
        self.apply_target(refresh=False)
        ttk.Label(left, text="Sets the move list, frame size, figure height and ground line\n(fine-tune them on the Build tab).",
                  foreground="#555", justify=tk.LEFT).pack(anchor="w", pady=(8, 0))
        ttk.Separator(tab, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        self.pick = ttk.Frame(tab); self.pick.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, anchor="n")
        self._picker()

    def _picker(self):
        """Move picker: tick the moves to make, change frames / fps, add any move from the other presets."""
        from . import icons
        from .moves import preset as _preset
        for w in self.pick.winfo_children():
            w.destroy()
        hdr = ttk.Frame(self.pick); hdr.pack(fill=tk.X)
        ttk.Label(hdr, text=" Moves", image=icons.tk_icon("move", 20), compound=tk.LEFT, font=(self.fam, 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(hdr, text="All", width=5, command=lambda: (self.app._all(True), self._tinfo())).pack(side=tk.LEFT, padx=(12, 2))
        ttk.Button(hdr, text="None", width=5, command=lambda: (self.app._all(False), self._tinfo())).pack(side=tk.LEFT, padx=2)
        self.app._q(hdr, "Move picker").pack(side=tk.LEFT, padx=4)
        g = ttk.Frame(self.pick); g.pack(fill=tk.X, pady=6)
        cols = 3
        for c in range(cols):
            ttk.Label(g, text="move", foreground="#777").grid(row=0, column=c * 4, sticky="w", padx=(10 if c else 0, 0))
            ttk.Label(g, text="frames", foreground="#777").grid(row=0, column=c * 4 + 1)
            ttk.Label(g, text="fps", foreground="#777").grid(row=0, column=c * 4 + 2)
        rows = self.app.rows
        per = max(1, -(-len(rows) // cols))
        for i, (m, on, fr, fps, lp, *_rest) in enumerate(rows):
            r, c = 1 + i % per, i // per
            ttk.Checkbutton(g, text=m.name, variable=on, command=self._tinfo, width=15).grid(row=r, column=c * 4, sticky="w", padx=(10 if c else 0, 0))
            ttk.Spinbox(g, from_=1, to=64, textvariable=fr, width=3).grid(row=r, column=c * 4 + 1, padx=2)
            ttk.Spinbox(g, from_=1, to=60, textvariable=fps, width=3).grid(row=r, column=c * 4 + 2, padx=2)
        have = {row[0].name for row in rows}
        extra = {}
        for pn in PRESETS:
            for mm in _preset(pn):
                if mm.name not in have and mm.name not in extra:
                    extra[mm.name] = mm
        self._extra = extra
        af = ttk.Frame(self.pick); af.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(af, text="Add a move").pack(side=tk.LEFT)
        self.add_var = tk.StringVar()
        ttk.Combobox(af, textvariable=self.add_var, values=sorted(extra), width=22, state="readonly").pack(side=tk.LEFT, padx=4)
        ttk.Button(af, text="Add", command=self._add_move).pack(side=tk.LEFT)
        self.req_lbl = ttk.Label(self.pick, text="", foreground="#c01c28", wraplength=640, justify=tk.LEFT); self.req_lbl.pack(anchor="w", pady=4)

    def _add_move(self):
        mm = self._extra.get(self.add_var.get())
        if mm:
            self.app._add_row(mm); self._picker(); self._tinfo()

    def _goal_retro(self, tab):
        from . import icons
        v = self.app.v
        from .gui import NO_CONSOLE
        ttk.Label(tab, text="Also make a console version (optional)", font=(self.fam, 11, "bold")).pack(anchor="w")
        ttk.Label(tab, text="Same moves, re-drawn to the console's real limits (size, colours, palettes, tile format) in "
                  "out/<name>/console/. 'None' = HD only.", foreground="#555").pack(anchor="w", pady=(0, 6))
        g = ttk.Frame(tab); g.pack(anchor="w")
        opts = [(None, NO_CONSOLE)] + [(k, consoles.LABELS[k]) for k in consoles.ORDER]
        per = -(-len(opts) // 3)
        for i, (k, lab) in enumerate(opts):
            ttk.Radiobutton(g, text=lab, value=lab, variable=v["console"], command=self._retro_info).grid(
                row=i % per, column=i // per, sticky="w", padx=(0, 24), pady=1)
        f = ttk.Frame(tab); f.pack(anchor="w", pady=(8, 2))
        ttk.Checkbutton(f, text="Dither (smoother shading with few colours)", variable=self.app.b["dither"]).pack(side=tk.LEFT)
        self.app._q(f, "Dither").pack(side=tk.LEFT)
        self.retro_lbl = ttk.Label(tab, text="", foreground="#444", wraplength=1100, justify=tk.LEFT); self.retro_lbl.pack(anchor="w", pady=6)
        self._retro_info(set_dither=False)

    def _retro_info(self, set_dither=True):
        k = consoles.by_label(self.app.v["console"].get())
        if k and set_dither:
            self.app.b["dither"].set(consoles.PRESETS[k]["dither"])
        txt = "%s: %s" % (consoles.LABELS[k], consoles.describe(k)) if k else "HD only - no console version."
        if hasattr(self, "retro_lbl"):
            self.retro_lbl.configure(text=txt)
        self._tinfo()

    def _goal_3d(self, tab):
        from .gui import MANNEQUIN_3D
        mode = self.app.v["mode"].get()
        can = mode in MANNEQUIN_3D or mode == "library"
        ttk.Label(tab, text="3D model files", font=(self.fam, 11, "bold")).pack(anchor="w")
        if not can:
            ttk.Label(tab, text="Your source is a %s, so this build makes sprites only. 3D files need a 3D character: "
                      "'Make a character', 'A rig from my library' or 'A text description' in step 1. "
                      "(The side-on turn uses a 3D estimate internally, but it is not a game-ready model.)" % mode,
                      foreground="#c01c28", wraplength=1000, justify=tk.LEFT).pack(anchor="w", pady=6)
        st = [] if can else ["disabled"]
        for key, text, hk in (("glb", "GLB (glTF binary) - rigged mesh + animations: Godot, three.js, raylib, Blender", "GLB"),
                              ("fbx", "FBX - rigged mesh + animations: Unity, Unreal, Blender", "FBX"),
                              ("anim_export", "Separate animation files per move (raylib 5.5 / 6 friendly)", "Animation export")):
            f = ttk.Frame(tab); f.pack(anchor="w", pady=2)
            cb = ttk.Checkbutton(f, text=text, variable=self.app.b[key], command=self._tinfo); cb.pack(side=tk.LEFT); cb.state(st)
            self.app._q(f, hk).pack(side=tk.LEFT)
        ttk.Label(tab, text="3D files are written by Final builds only (Quick preview skips them to stay fast).",
                  foreground="#555").pack(anchor="w", pady=(8, 0))

    def wants_3d(self):
        from .gui import MANNEQUIN_3D
        m = self.app.v["mode"].get()
        return m in MANNEQUIN_3D or m == "library"

    def _tinfo(self):
        if not hasattr(self, "tinfo") or not self.tinfo.winfo_exists():
            return
        mv = self.app.selected_moves(); v, b = self.app.v, self.app.b
        parts = ["HD sheet: %d moves, frame %sx%s" % (len(mv), v["fw"].get(), v["fh"].get())]
        k = consoles.by_label(v["console"].get())
        if k:
            parts.append("+ %s version" % consoles.LABELS[k])
        if self.wants_3d():
            fs = [n for n, kk in (("GLB", "glb"), ("FBX", "fbx"), ("anim files", "anim_export")) if b[kk].get()]
            if fs:
                parts.append("+ 3D: " + ", ".join(fs))
        self.tinfo.configure(text="Will make:  " + "   ".join(parts))
        t = next((x for x in TARGETS if x[0] == self.target.get()), None)
        if hasattr(self, "req_lbl") and self.req_lbl.winfo_exists():
            miss = []
            if t and t[1] == EF14:
                names = {m.name for m in mv}
                miss = [it.split(":")[0] for it in EF14.split(",") if it.split(":")[0] not in names]
            self.req_lbl.configure(text=("The game needs every fighter move - missing: %s" % ", ".join(miss)) if miss else "")

    def apply_target(self, refresh=True):
        t = next(x for x in TARGETS if x[0] == self.target.get())
        app = self.app
        if t[5]:
            app.v["profile"].set(t[5]); app.apply_profile()
        elif app.v["profile"].get() not in ("", "(none)"):
            app.v["profile"].set("(none)"); app.apply_profile()
        if t[1] in PRESETS:
            app.v["preset"].set(t[1]); app.load_preset()
        else:
            app._clear_rows()
            for m in ef_moves():
                app._add_row(m)
        w, h = t[2].split("x"); app.v["fw"].set(w); app.v["fh"].set(h)
        app.v["figh"].set(t[3]); app.v["ground"].set(t[4])
        if refresh and hasattr(self, "pick") and self.pick.winfo_exists():
            self._picker()
        self._tinfo()

    def s_build(self):
        v = self.app.v
        self._title("Build", "Quick preview first (seconds), then Final when you like it.")
        f = ttk.Frame(self.body); f.pack(anchor="w")
        for val, lab in (("draft", "Quick preview (half size, 4 frames a move, no 3D/console files)"), ("final", "Final (full size, every frame, all files)")):
            ttk.Radiobutton(f, text=lab, value=val, variable=v["quality"]).pack(anchor="w")
        ttk.Checkbutton(f, text="Re-use unchanged moves from the last build (faster)", variable=self.app.b["cache"]).pack(anchor="w", pady=(4, 0))
        ttk.Label(self.body, text="Same as typing:", foreground="#555").pack(anchor="w", pady=(10, 0))
        self.cmd = tk.Text(self.body, height=4, width=150, font="TkFixedFont", wrap=tk.WORD, background="#f4f4f4")
        self.cmd.pack(anchor="w", fill=tk.X)
        self._cmd()
        v["quality"].trace_add("write", lambda *a: self._cmd() if self.step == 4 else None)
        bf = ttk.Frame(self.body); bf.pack(anchor="w", pady=8)
        self.go_btn = ttk.Button(bf, text=" BUILD", image=_ic("build", 24), compound=tk.LEFT, style="Go.TButton", command=self.build); self.go_btn.pack(side=tk.LEFT)
        self.open_btn = ttk.Button(bf, text=" Open output folder", image=_ic("folder"), compound=tk.LEFT, command=self.app.open_out); self.open_btn.pack(side=tk.LEFT, padx=6)
        self.ef_btn = ttk.Button(bf, text=" Export to a game folder...", image=_ic("game"), compound=tk.LEFT, command=self.export_game); self.ef_btn.pack(side=tk.LEFT)
        self.bpb = ttk.Progressbar(self.body, maximum=1.0, length=600); self.bpb.pack(anchor="w")
        self.bstat = ttk.Label(self.body, text="", foreground="#26a269", wraplength=1200, justify=tk.LEFT); self.bstat.pack(anchor="w", pady=4)
        self.bimg = ttk.Label(self.body); self.bimg.pack(anchor="w")
        self._tick_pb()

    def _cmd(self):
        try:
            s = " ".join(_q(x) for x in forge_command(self.app))
        except Exception as e:
            s = "(%s)" % e
        self.cmd.configure(state=tk.NORMAL); self.cmd.delete("1.0", tk.END); self.cmd.insert("1.0", s); self.cmd.configure(state=tk.DISABLED)

    # ------------------------------------------------------------ actions
    def _show(self, path, lbl, size):
        if not path or not os.path.isfile(path):
            return
        im = Image.open(path).convert("RGBA"); im.thumbnail((size * 2, size))
        from .build import checker
        bg = checker(im.width, im.height, 10).convert("RGBA"); bg.alpha_composite(im)
        self._imgs[str(lbl)] = ImageTk.PhotoImage(bg); lbl.configure(image=self._imgs[str(lbl)])

    def _pick_raw(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")])
        if p:
            self.raw.set(p); self.app.v["photo"].set(p); self.app.v["landmarks"].set(""); self._show(p, self.thumb, 360)

    def _run(self, argv, done):
        """forge.py ARGV in a thread; done(rc, log_lines) on the Tk thread."""
        def work():
            env = dict(os.environ); env["PYTHONUNBUFFERED"] = "1"
            try:
                pr = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py")] + argv, capture_output=True, text=True, env=env)
                rc, out = pr.returncode, (pr.stdout + pr.stderr).splitlines()
            except Exception as e:
                rc, out = 1, [str(e)]
            for ln in out:
                self.app.q.put(("log", ln))
            self.app.q.put(("cb", lambda a: done(rc, out)))
        self.app._log("> python forge.py " + " ".join(_q(x) for x in argv))
        threading.Thread(target=work, daemon=True).start()

    def cutout(self):
        src = self.raw.get().strip()
        if not os.path.isfile(src):
            self.cut_info.configure(text="Pick a photo first.", foreground="#c01c28"); return
        out = os.path.join(self.app.v["out"].get() or "out", (self.app.v["name"].get().strip() or "hero") + "_cutout")
        self.cut_btn.state(["disabled"]); self.cut_info.configure(text="Cutting out (about 10-30 s the first time)...", foreground="#555")
        def done(rc, lines):
            self.cut_btn.state(["!disabled"])
            cp, lm = os.path.join(out, "cutout.png"), os.path.join(out, "landmarks.json")
            if os.path.isfile(cp) and (rc == 0 or any("cutout FAIL" in l or "cutout WARN" in l for l in lines)):
                self.app.v["photo"].set(os.path.abspath(cp)); self.app.v["cutout"].set("alpha")
                if os.path.isfile(lm):
                    self.app.v["landmarks"].set(os.path.abspath(lm)); self.app.v["fill"].set("puppet")
                qa = "" if rc == 0 else "  - quality check flagged the edges: see verify.png + cutout_report.txt"
                self.cut_info.configure(text="Cut-out ready: %s%s%s" % (cp, "  (+ pose points)" if os.path.isfile(lm) else "  (no pose points - mediapipe missing?)", qa),
                                        foreground="#26a269" if rc == 0 else "#b5835a")
                self._show(cp, self.thumb, 360)
            else:
                self.cut_info.configure(text="Cut-out failed (see the Build tab log): " + (lines[-1] if lines else "?"), foreground="#c01c28")
        self._run(["cutout", src, "--person", self.person.get(), "--out", out], done)

    def preview_turn(self):
        from .gui import turn_value
        v = self.app.v
        lm = v["landmarks"].get().strip()
        if not lm or not os.path.isfile(lm):
            self.turn_info.configure(text="Needs the cut-out + pose points from step 2 ('Cut out person').", foreground="#c01c28"); return
        try:
            t = turn_value(v["turn"].get(), v["turn_yaw"].get())
        except ValueError:
            self.turn_info.configure(text="Fine angle must be a number.", foreground="#c01c28"); return
        out = os.path.join(v["out"].get() or "out", (v["name"].get().strip() or "hero") + "_turn")
        argv = ["turn", v["photo"].get().strip() or os.path.dirname(lm), "--landmarks", lm, "--yaw", "%g" % t, "--depth", v["turn_depth"].get() or "auto", "--out", out]
        if v["turn_side"].get().strip():
            argv += ["--side-photo", v["turn_side"].get().strip()]
        self.turn_btn.state(["disabled"]); self.turn_info.configure(text="Working out the %g degree view..." % t, foreground="#555")
        t0 = time.time()
        def done(rc, lines):
            self.turn_btn.state(["!disabled"])
            cands = sorted((os.path.join(out, f) for f in os.listdir(out) if f.startswith("compare_")), key=os.path.getmtime) if os.path.isdir(out) else []
            if rc == 0 and cands:
                self._show(cands[-1], self.turn_img, 520)
                self.turn_info.configure(text="Done in %.1f s: %s" % (time.time() - t0, cands[-1]), foreground="#26a269")
            else:
                self.turn_info.configure(text="Turn failed: " + (lines[-1] if lines else "?"), foreground="#c01c28")
        self._run(argv, done)

    def build(self):
        self.t0 = time.time(); self.bstat.configure(text="Building...", foreground="#555"); self.bimg.configure(image="")
        self.go_btn.state(["disabled"])
        def fin(app):
            self.go_btn.state(["!disabled"]); self.bpb["value"] = 1.0
            r = app.result
            if r:
                sheet = os.path.join(r["out"], "preview.png")
                self.bstat.configure(text="Done in %.1f s  ->  %s" % (time.time() - self.t0, os.path.abspath(r["out"])), foreground="#26a269")
                self._show(sheet, self.bimg, 300)
                try:
                    with open(os.path.join(r["out"], "forge_command.txt"), "w") as fh:
                        fh.write(" ".join(_q(x) for x in forge_command(app)) + "\n")
                except OSError:
                    pass
            else:
                self.bstat.configure(text=app.status.cget("text") or "Build failed (see the Build tab log).", foreground="#c01c28")
        if not self.app.on_build(fin):
            self.go_btn.state(["!disabled"])
            self.bstat.configure(text=self.app.status.cget("text"), foreground="#c01c28")

    def _tick_pb(self):
        if self.step == 4 and self.bpb.winfo_exists():
            if "disabled" in self.go_btn.state():
                self.bpb["value"] = self.app.pb["value"]
            if self.t0 and "disabled" in self.go_btn.state():
                self.bstat.configure(text="Building... %.0f s" % (time.time() - self.t0))
            self.f.after(200, self._tick_pb)

    def export_game(self):
        r = self.app.result
        if not r:
            messagebox.showinfo("Export", "Build first."); return
        dst = filedialog.askdirectory(title="Game assets folder to create, e.g. <game>/assets/char_hero")
        if not dst:
            return
        like = filedialog.askopenfilename(title="Optional: an existing fighter's sprites.cfg to copy frame counts from (Cancel = none)",
                                          filetypes=[("sprites.cfg", "*.cfg"), ("All", "*.*")])
        argv = ["export-ef", r["out"], dst] + (["--like", like] if like else [])
        self.bstat.configure(text="Exporting to %s ..." % dst, foreground="#555")
        self._run(argv, lambda rc, lines: self.bstat.configure(
            text=("Exported to %s (see export_report.txt)" % dst) if rc == 0 else "Export failed: " + (lines[-1] if lines else "?"),
            foreground="#26a269" if rc == 0 else "#c01c28"))
