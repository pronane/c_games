"""v9 Studio: the 'Style' step (Faces / Colours / Variants), the 'Extras' goal tab and the Tools menu
(Batch queue, Atlas pack, QA check, Recolour a finished build, NPC presets).

Everything maps 1:1 onto forge.py flags (style_argv) and BuildConfig fields (apply_to_config), so the Studio and the
command line stay the same build.  Previews run a tiny 1-move build through the SAME core (forge.py build)."""
from __future__ import annotations
import os
import shutil
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from . import expressions as X
from . import recolor as RC
from . import variants as VA

V9_VARS = dict(expressions="auto", expr_map="", talk="", recolor_set="", overlay_kind="", overlay_colour="#ffffff",
               overlay_tex="", regions="", variant="", vary=VA.DEFAULT_VARY, variants="0", variant_seed="1",
               fx="", maps="", blend="", lods="0", npc="", **{"rc_" + r: "" for r in RC.REGIONS})
V9_BOOLS = dict(blink=True, faces_sheet=True, physics=True, footlock=False, framedata=False, qa=True)
FACE_MODES = [("auto", "Automatic per move (punch = angry, hit = hurt, taunt = taunt ...)"),
              ("off", "Off (neutral face everywhere)"), ("map", "My own per-move choices (below)")]
FX_PRESETS = ["", "outline=2", "outline=2,cel=3", "cel=4,light=-1:-1:1,rim=0.4", "pixel=4,colors=32,outline=1", "outline=3,outline_colour=#101018,cel=3"]


def install_vars(app):
    for k, val in V9_VARS.items():
        app.v.setdefault(k, tk.StringVar(value=val))
    for k, val in V9_BOOLS.items():
        app.b.setdefault(k, tk.BooleanVar(value=val))


# ------------------------------------------------------------------ settings -> recolour / overlay strings
def recolor_string(app):
    v = _views(app)[0]
    parts = [v["recolor_set"].get().strip()] if v["recolor_set"].get().strip() else []
    regs = ",".join("%s=%s" % (r, v["rc_" + r].get().strip()) for r in RC.REGIONS if v["rc_" + r].get().strip())
    if regs:
        parts.append(regs)
    return ";".join(parts)


def overlay_string(app):
    v = _views(app)[0]; k = v["overlay_kind"].get().strip()
    if not k:
        return ""
    if k == "texture":
        return "top:texture:%s" % v["overlay_tex"].get().strip() if v["overlay_tex"].get().strip() else ""
    return "top:%s:%s" % (k, v["overlay_colour"].get().strip() or "#ffffff")


def expr_values(app):
    """(expressions, expr_map) as forge.py takes them"""
    v = _views(app)[0]
    m = v["expressions"].get()
    if m == "map":
        return "auto", v["expr_map"].get().strip()
    if m in ("auto", "off"):
        return m, (v["expr_map"].get().strip() if m == "auto" else "")
    return m, ""


def apply_to_config(app, c):
    v, b = app.v, app.b
    c.expressions, c.expr_map = expr_values(app)
    c.blink = b["blink"].get(); c.faces_sheet = b["faces_sheet"].get(); c.talk = v["talk"].get().strip()
    c.recolor = recolor_string(app); c.overlay = overlay_string(app); c.regions = v["regions"].get().strip()
    c.physics = b["physics"].get()
    c.variant = int(v["variant"].get()) if v["variant"].get().strip().lstrip("-").isdigit() else -1
    c.vary = v["vary"].get().strip() or VA.DEFAULT_VARY
    c.variants = int(v["variants"].get() or 0) if v["variants"].get().strip().isdigit() else 0
    c.variant_seed = int(v["variant_seed"].get() or 1) if v["variant_seed"].get().strip().isdigit() else 1
    c.fx = v["fx"].get().strip(); c.maps = v["maps"].get().strip(); c.blend = v["blend"].get().strip()
    c.footlock = b["footlock"].get(); c.framedata = b["framedata"].get(); c.qa = b["qa"].get()
    c.lods = int(v["lods"].get() or 0) if v["lods"].get().strip().isdigit() else 0
    if v["npc"].get().strip() and c.mode in ("mannequin", "spec"):
        from . import npcpack
        c.spec, _ = npcpack.character_spec(v["npc"].get().strip())
        c.mode = "mannequin"; c.kit = ""; c.spec_path = ""
    return c


class _Const:
    def __init__(self, x): self.x = x
    def get(self): return self.x


class _Defaults(dict):
    """app.v / app.b view that falls back to the v9 defaults (older callers / fake apps without the v9 vars)"""
    def __init__(self, real, defaults):
        super().__init__(); self.real, self.defaults = real, defaults
    def __getitem__(self, k):
        return self.real[k] if k in self.real else _Const(self.defaults.get(k, ""))
    def __contains__(self, k):
        return k in self.real or k in self.defaults


def _views(app):
    return _Defaults(app.v, V9_VARS), _Defaults(app.b, V9_BOOLS)


def style_argv(app):
    """the v9 forge.py build flags for the current Studio settings"""
    v, b = _views(app)
    a = []
    e, em = expr_values(app)
    if e != "auto":
        a += ["--expressions", e]
    if em:
        a += ["--expr-map", em]
    if not b["blink"].get():
        a += ["--no-blink"]
    if v["talk"].get().strip():
        a += ["--talk", v["talk"].get().strip()]
    if not b["faces_sheet"].get():
        a += ["--no-faces-sheet"]
    if recolor_string(app):
        a += ["--recolor", recolor_string(app)]
    if overlay_string(app):
        a += ["--overlay", overlay_string(app)]
    if v["regions"].get().strip():
        a += ["--regions", v["regions"].get().strip()]
    if not b["physics"].get():
        a += ["--no-physics"]
    if v["variant"].get().strip().lstrip("-").isdigit() and int(v["variant"].get()) >= 0:
        a += ["--variant", v["variant"].get().strip()]
    if (v["vary"].get().strip() or VA.DEFAULT_VARY) != VA.DEFAULT_VARY:
        a += ["--vary", v["vary"].get().strip()]
    if v["variants"].get().strip().isdigit() and int(v["variants"].get()) > 0:
        a += ["--variants", v["variants"].get().strip()]
        if (v["variant_seed"].get().strip() or "1") != "1":
            a += ["--variant-seed", v["variant_seed"].get().strip()]
    for k, flag in (("fx", "--fx"), ("maps", "--maps"), ("blend", "--blend")):
        if v[k].get().strip():
            a += [flag, v[k].get().strip()]
    if b["footlock"].get():
        a += ["--footlock"]
    if b["framedata"].get():
        a += ["--framedata"]
    if not b["qa"].get():
        a += ["--no-qa"]
    if v["lods"].get().strip().isdigit() and int(v["lods"].get()) > 0:
        a += ["--lods", v["lods"].get().strip()]
    return a


def _swatch(parent, colour, size=16):
    c = tk.Canvas(parent, width=size, height=size, highlightthickness=1, highlightbackground="#888")
    try:
        c.configure(background=RC.hexc(RC.to_rgb(colour)) if colour else "#f0f0f0")
    except Exception:
        pass
    return c


# ------------------------------------------------------------------ the Style step
class StyleStep:
    TABS = [("faces", "Faces"), ("colours", "Colours"), ("variants", "Variants")]

    def __init__(self, home, body):
        self.home, self.app, self.body = home, home.app, body
        app, v = self.app, self.app.v
        self.photo = v["mode"].get() == "photo"
        home._title("Style: faces, colours, variants",
                    "Give the character a face for every move, its own colours, or a whole crowd of variants. "
                    "'Preview' runs a 1-move build (a few seconds) so you see the real result." +
                    ("  PHOTO: faces and colours are ESTIMATED edits of your photo's own pixels (procedural warps / re-tints) - "
                     "nothing new is generated." if self.photo else ""))
        self.nb = nb = ttk.Notebook(body); nb.pack(fill=tk.BOTH, expand=True)
        self.tabs = {}
        for k, lab in self.TABS:
            f = ttk.Frame(nb, padding=8); nb.add(f, text="   %s   " % lab); self.tabs[k] = f
        self._imgs = {}
        self._faces(self.tabs["faces"]); self._colours(self.tabs["colours"]); self._variants(self.tabs["variants"])
        nb.select(self.tabs[getattr(home, "style_tab", "faces")])
        nb.bind("<<NotebookTabChanged>>", lambda e: setattr(home, "style_tab", [k for k, f in self.tabs.items() if str(f) == nb.select()][0]))

    # ---- shared preview (one tiny draft build, same core as forge.py build)
    def _preview_pane(self, parent, kind):
        r = ttk.Frame(parent); r.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        bar = ttk.Frame(r); bar.pack(anchor="w")
        btn = ttk.Button(bar, text=" Preview", image=self.home_icon("preview"), compound=tk.LEFT, command=lambda: self.preview(kind)); btn.pack(side=tk.LEFT)
        info = ttk.Label(bar, text="", foreground="#555", wraplength=520); info.pack(side=tk.LEFT, padx=8)
        img = ttk.Label(r); img.pack(anchor="nw", pady=6)
        setattr(self, "pv_" + kind, (btn, info, img))
        self._show_last(kind)
        return r

    def home_icon(self, n):
        from .icons import tk_icon
        return tk_icon(n, 20)

    def _pv_dir(self):
        return os.path.join(self.app.v["out"].get() or "out", "_style_preview")

    def _pv_file(self, kind):
        d = os.path.join(self._pv_dir(), self.app.v["name"].get().strip() or "hero")
        if kind == "faces":
            return os.path.join(d, "faces.png")
        if kind == "variants":
            return os.path.join(d, "variants", "variants_sheet.png")
        rp = os.path.join(d, "regions_preview.png")
        if os.path.isfile(rp):
            return rp
        md = os.path.join(d, "moves")
        fr = sorted(f for f in os.listdir(md) if f.endswith(".png")) if os.path.isdir(md) else []
        return os.path.join(md, fr[0]) if fr else os.path.join(d, "preview.png")

    def _show_last(self, kind):
        p = self._pv_file(kind)
        if os.path.isfile(p):
            self._show(p, getattr(self, "pv_" + kind)[2], 780, 470)

    def _show(self, path, lbl, w, h):
        from PIL import Image, ImageTk
        im = Image.open(path).convert("RGBA")
        bb = im.getbbox() if "moves" in path else None
        if bb:                         # one sprite frame: crop to the figure and scale it UP on a checker
            from .build import checker
            im = im.crop((max(0, bb[0] - 12), max(0, bb[1] - 12), min(im.width, bb[2] + 12), min(im.height, bb[3] + 12)))
            k = min(w / im.width, h / im.height, 4.0)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
            bg = checker(im.width, im.height, 12).convert("RGBA"); bg.alpha_composite(im); im = bg
        im = im.convert("RGB"); im.thumbnail((w, h))
        self._imgs[str(lbl)] = ImageTk.PhotoImage(im); lbl.configure(image=self._imgs[str(lbl)])

    def preview(self, kind):
        from .gui_home import forge_command
        try:
            argv = forge_command(self.app)[3:]
        except Exception as e:
            getattr(self, "pv_" + kind)[1].configure(text=str(e), foreground="#c01c28"); return
        mv = self.app.selected_moves()
        idle = next((m for m in mv if m.loop), mv[0] if mv else None)
        i = argv.index("--moves")
        argv[i + 1] = "%s:2:%d:loop" % ((idle.name if idle else "idle"), idle.fps if idle else 8)
        if kind == "variants" and not (self.app.v["variants"].get().strip().isdigit() and int(self.app.v["variants"].get()) > 0):
            argv += ["--variants", "8"]
        drop = {"--out", "--quality", "--profile", "--console"}
        a2, skip = [], False
        for x in argv:
            if skip:
                skip = False; continue
            if x in drop:
                skip = True; continue
            a2.append(x)
        a2 += ["--no-glb", "--no-fbx", "--no-qa", "--out", self._pv_dir()]
        for x in ("--framedata", "--footlock"):
            while x in a2:
                a2.remove(x)
        for f in ("--maps", "--lods", "--fx", "--blend"):
            if f in a2:
                j = a2.index(f); del a2[j:j + 2]
        btn, info, img = getattr(self, "pv_" + kind)
        btn.state(["disabled"]); info.configure(text="Building a 1-move preview...", foreground="#555")
        t0 = time.time()

        def done(rc, lines):
            if not btn.winfo_exists():
                return
            btn.state(["!disabled"])
            p = self._pv_file(kind)
            if rc == 0 and os.path.isfile(p):
                info.configure(text="Preview in %.1f s - %s" % (time.time() - t0, p), foreground="#26a269")
                self._show(p, img, 780, 470)
            else:
                info.configure(text="Preview failed: " + (lines[-1] if lines else "?"), foreground="#c01c28")
        self.home._run(["build"] + a2, done)

    # ---- Faces
    def _faces(self, tab):
        v = self.app.v
        left = ttk.Frame(tab); left.pack(side=tk.LEFT, fill=tk.Y, anchor="n")
        ttk.Label(left, text="Facial expressions", font=(self.home.fam, 11, "bold")).pack(anchor="w")
        if v["expressions"].get() not in ("auto", "off", "map") + tuple(X.EXPRESSIONS):
            v["expressions"].set("auto")
        for val, lab in FACE_MODES:
            ttk.Radiobutton(left, text=lab, value=val, variable=v["expressions"], command=self._face_rows).pack(anchor="w")
        f = ttk.Frame(left); f.pack(anchor="w", pady=2)
        ttk.Radiobutton(f, text="One face for every move:", value="__one", variable=v["expressions"],
                        command=lambda: (v["expressions"].set(self.one.get()), self._face_rows())).pack(side=tk.LEFT)
        self.one = tk.StringVar(value=v["expressions"].get() if v["expressions"].get() in X.EXPRESSIONS else "happy")
        cb = ttk.Combobox(f, textvariable=self.one, values=X.EXPRESSIONS, width=9, state="readonly"); cb.pack(side=tk.LEFT, padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: (v["expressions"].set(self.one.get()), self._face_rows()))
        self.app._q(f, "Expressions").pack(side=tk.LEFT)
        self.map_box = ttk.LabelFrame(left, text=" Per move (Automatic shows its choice; change any) ", padding=6)
        self.map_box.pack(anchor="w", fill=tk.X, pady=6)
        self._face_rows()
        f = ttk.Frame(left); f.pack(anchor="w", pady=2)
        ttk.Checkbutton(f, text="Blink in looping moves", variable=self.app.b["blink"]).pack(side=tk.LEFT)
        ttk.Checkbutton(f, text="faces.png HUD portraits", variable=self.app.b["faces_sheet"]).pack(side=tk.LEFT, padx=10)
        f = ttk.LabelFrame(left, text=" Talking (mouth shapes) ", padding=6); f.pack(anchor="w", fill=tk.X, pady=6)
        r = ttk.Frame(f); r.pack(anchor="w")
        ttk.Label(r, text="Line of dialogue").pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=v["talk"], width=34).pack(side=tk.LEFT, padx=4); self.app._q(r, "Talk").pack(side=tk.LEFT)
        ttk.Label(f, text="-> talk/ strip + talk.json timing. Mouth shapes come from the letters (rest, M/B/P, A/I, E, O, U, F/V, L) - "
                  "not speech recognition. 'sheet' = every mouth shape once.", foreground="#555", wraplength=520, justify=tk.LEFT).pack(anchor="w")
        if self.photo:
            ttk.Label(left, text="Photo: expressions are procedural warps / overlays of your own photo's face (ESTIMATED). "
                      "Subtle on small faces; turned and back views keep the neutral face.", foreground="#b5835a",
                      wraplength=520, justify=tk.LEFT).pack(anchor="w")
        self._preview_pane(tab, "faces")

    def _face_rows(self):
        for w in self.map_box.winfo_children():
            w.destroy()
        v = self.app.v
        mode = v["expressions"].get()
        um = {}
        try:
            um = X.parse_map(v["expr_map"].get())
        except ValueError:
            pass
        mv = self.app.selected_moves()
        self.face_vars = {}
        cols = 3 if len(mv) > 16 else 2; per = max(1, -(-len(mv) // cols))
        for i, m in enumerate(mv):
            r, c = i % per, i // per
            cur = (um.get(m.name) or X.expression_for(m.name)) if mode in ("auto", "map") else ("neutral" if mode == "off" else mode)
            sv = tk.StringVar(value=cur); self.face_vars[m.name] = sv
            ttk.Label(self.map_box, text=m.name[:13], width=13).grid(row=r, column=c * 2, sticky="w", padx=(0 if c == 0 else 14, 0))
            cb = ttk.Combobox(self.map_box, textvariable=sv, values=X.EXPRESSIONS, width=7, state="readonly" if mode in ("auto", "map") else "disabled")
            cb.grid(row=r, column=c * 2 + 1, pady=1)
            cb.bind("<<ComboboxSelected>>", lambda e: self._map_changed())

    def _map_changed(self):
        v = self.app.v
        ch = ["%s=%s" % (k, sv.get()) for k, sv in self.face_vars.items() if sv.get() != X.expression_for(k)]
        v["expr_map"].set(",".join(ch))
        v["expressions"].set("map" if ch else "auto")

    # ---- Colours
    def _colours(self, tab):
        v = self.app.v
        left = ttk.Frame(tab); left.pack(side=tk.LEFT, fill=tk.Y, anchor="n")
        ttk.Label(left, text="One-click colour sets", font=(self.home.fam, 11, "bold")).pack(anchor="w")
        g = ttk.Frame(left); g.pack(anchor="w", pady=4)
        sets = RC.all_sets()
        items = [("", {"label": "(own colours)"})] + list(sets.items())
        for i, (k, s) in enumerate(items):
            f = ttk.Frame(g); f.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 8), pady=1)
            sw = tk.Canvas(f, width=34, height=14, highlightthickness=1, highlightbackground="#888"); sw.pack(side=tk.LEFT)
            cols = [s.get(r) for r in ("top", "trim", "bottom") if s.get(r)]
            for j, c in enumerate(cols or ["#dddddd"]):
                try:
                    sw.create_rectangle(j * 34 // max(1, len(cols)), 0, (j + 1) * 34 // max(1, len(cols)), 15, fill=RC.hexc(RC.to_rgb(c)), width=0)
                except Exception:
                    pass
            ttk.Radiobutton(f, text=(lambda L: L if len(L) <= 22 else L.split(" (")[0][:22])(s.get("label", k)), value=k, variable=v["recolor_set"], command=self._rc_info).pack(side=tk.LEFT)
        ttk.Label(left, text="Per region (overrides the set)", font=(self.home.fam, 10, "bold")).pack(anchor="w", pady=(8, 2))
        rg = ttk.Frame(left); rg.pack(anchor="w")
        self.rc_sw = {}
        for i, r in enumerate(RC.REGIONS):
            f = ttk.Frame(rg); f.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16), pady=1)
            ttk.Label(f, text=r, width=10).pack(side=tk.LEFT)
            sw = _swatch(f, v["rc_" + r].get()); sw.pack(side=tk.LEFT); self.rc_sw[r] = sw
            ttk.Entry(f, textvariable=v["rc_" + r], width=9).pack(side=tk.LEFT, padx=3)
            ttk.Button(f, text="Pick", width=5, command=lambda r=r: self._pick(r)).pack(side=tk.LEFT)
            ttk.Button(f, text="x", width=2, command=lambda r=r: (v["rc_" + r].set(""), self._rc_info())).pack(side=tk.LEFT)
        ov = ttk.LabelFrame(left, text=" Texture overlay on the top ", padding=6); ov.pack(anchor="w", fill=tk.X, pady=6)
        r = ttk.Frame(ov); r.pack(anchor="w")
        ttk.Combobox(r, textvariable=v["overlay_kind"], values=[""] + RC.PATTERNS + ["texture"], width=11, state="readonly").pack(side=tk.LEFT)
        ttk.Label(r, text="colour").pack(side=tk.LEFT, padx=(6, 2))
        ttk.Entry(r, textvariable=v["overlay_colour"], width=9).pack(side=tk.LEFT)
        ttk.Label(r, text="or texture").pack(side=tk.LEFT, padx=(6, 2))
        ttk.Entry(r, textvariable=v["overlay_tex"], width=16).pack(side=tk.LEFT)
        ttk.Button(r, text="...", width=3, command=lambda: self._browse_tex()).pack(side=tk.LEFT, padx=2)
        if self.photo:
            r = ttk.Frame(left); r.pack(anchor="w", fill=tk.X)
            ttk.Label(r, text="Painted region map (optional)").pack(side=tk.LEFT)
            ttk.Entry(r, textvariable=v["regions"], width=24).pack(side=tk.LEFT, padx=3)
            ttk.Button(r, text="...", width=3, command=lambda: self.app._browse("regions", "image")).pack(side=tk.LEFT)
            self.app._q(r, "Regions").pack(side=tk.LEFT)
            ttk.Label(left, text="Photo: skin / hair / clothes regions are ESTIMATED from the pose points + colour; your photo's own "
                      "pixels are re-tinted (shading kept). Each build writes regions.png - paint over it and load it here to fix the masks.",
                      foreground="#b5835a", wraplength=520, justify=tk.LEFT).pack(anchor="w", pady=4)
        r = ttk.Frame(left); r.pack(anchor="w", pady=(6, 0))
        ttk.Button(r, text="Save as my set...", command=self._save_set).pack(side=tk.LEFT)
        ttk.Button(r, text="Recolour a finished build...", command=lambda: tool_recolor(self.app)).pack(side=tk.LEFT, padx=6)
        self.rc_lbl = ttk.Label(left, text="", foreground="#1a5fb4", wraplength=520); self.rc_lbl.pack(anchor="w", pady=4)
        for k in ["recolor_set", "overlay_kind", "overlay_colour", "overlay_tex"] + ["rc_" + r for r in RC.REGIONS]:
            if not getattr(self.app, "_rc_traced_" + k, False):
                v[k].trace_add("write", lambda *a: self._rc_info()); setattr(self.app, "_rc_traced_" + k, True)
        self._rc_info()
        self._preview_pane(tab, "colours")

    def _pick(self, r):
        cur = self.app.v["rc_" + r].get().strip()
        try:
            init = RC.hexc(RC.to_rgb(cur)) if cur else None
        except Exception:
            init = None
        c = colorchooser.askcolor(color=init, title="Colour for %s" % r)
        if c and c[1]:
            self.app.v["rc_" + r].set(c[1])

    def _browse_tex(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All", "*.*")])
        if p:
            self.app.v["overlay_tex"].set(p); self.app.v["overlay_kind"].set("texture")

    def _rc_info(self):
        if not hasattr(self, "rc_lbl") or not self.rc_lbl.winfo_exists():
            return
        for r, sw in self.rc_sw.items():
            try:
                sw.configure(background=RC.hexc(RC.to_rgb(self.app.v["rc_" + r].get())) if self.app.v["rc_" + r].get().strip() else "#f0f0f0")
            except Exception:
                pass
        s, o = recolor_string(self.app), overlay_string(self.app)
        try:
            if s:
                RC.parse(s)
            if o:
                RC.parse_overlay(o)
            self.rc_lbl.configure(text="forge.py: %s%s" % (("--recolor \"%s\"" % s) if s else "(own colours)", ("  --overlay %s" % o) if o else ""),
                                  foreground="#1a5fb4")
        except ValueError as e:
            self.rc_lbl.configure(text=str(e), foreground="#c01c28")

    def _save_set(self):
        from tkinter import simpledialog
        n = simpledialog.askstring("Save colour set", "Name for this set (letters, digits, _):")
        if not n:
            return
        try:
            m = RC.parse(recolor_string(self.app))
            p = RC.save_set(n, {k: (RC.hexc(x) if isinstance(x, tuple) else x) for k, x in m.items()})
            messagebox.showinfo("Saved", "Saved %s - it is in the set list next time." % p)
        except Exception as e:
            messagebox.showerror("Save set", str(e))

    # ---- Variants
    def _variants(self, tab):
        v = self.app.v
        left = ttk.Frame(tab); left.pack(side=tk.LEFT, fill=tk.Y, anchor="n")
        ttk.Label(left, text="Procedural variants", font=(self.home.fam, 11, "bold")).pack(anchor="w")
        ttk.Label(left, text="Make a crowd, a team or alt costumes from this character. Every variant is reproducible from its seed." +
                  ("\nPhoto: variants only re-tint your photo's clothes / hair and change the body scale (ESTIMATED regions)." if self.photo else ""),
                  foreground="#555", wraplength=520, justify=tk.LEFT).pack(anchor="w", pady=(0, 6))
        ttk.Label(left, text="What to vary").pack(anchor="w")
        g = ttk.Frame(left); g.pack(anchor="w")
        cur = set(VA.parse_vary(v["vary"].get() or VA.DEFAULT_VARY))
        self.vary_b = {}
        desc = {"body": "body (height, build, head)", "outfit": "outfit (top, pattern, hair style)", "colours": "kit + hair colours",
                "skin": "skin tone", "accessories": "accessories (0-2)", "face": "facial hair"}
        for i, k in enumerate(VA.VARY_KEYS):
            bv = tk.BooleanVar(value=k in cur); self.vary_b[k] = bv
            ttk.Checkbutton(g, text=desc[k], variable=bv, command=self._vary_changed, state="disabled" if self.photo and k not in ("body", "colours", "outfit") else "!disabled"
                            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 12))
        f = ttk.Frame(left); f.pack(anchor="w", pady=6)
        ttk.Label(f, text="How many").pack(side=tk.LEFT)
        ttk.Spinbox(f, from_=0, to=64, textvariable=v["variants"], width=4).pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="first seed").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Spinbox(f, from_=1, to=99999, textvariable=v["variant_seed"], width=6).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="Shuffle", command=lambda: v["variant_seed"].set(str(int(time.time()) % 9000 + 1))).pack(side=tk.LEFT)
        ttk.Label(left, text="How many > 0: the build also writes variants/ (sheet + a spec file per seed).", foreground="#555").pack(anchor="w")
        f = ttk.LabelFrame(left, text=" Build one variant as THE character ", padding=6); f.pack(anchor="w", fill=tk.X, pady=8)
        r = ttk.Frame(f); r.pack(anchor="w")
        ttk.Label(r, text="Seed").pack(side=tk.LEFT)
        ttk.Entry(r, textvariable=v["variant"], width=7).pack(side=tk.LEFT, padx=4)
        ttk.Button(r, text="Clear", command=lambda: v["variant"].set("")).pack(side=tk.LEFT)
        self.app._q(r, "Variant").pack(side=tk.LEFT, padx=4)
        ttk.Label(f, text="Empty = the character itself. Pick a seed from the preview sheet.", foreground="#555").pack(anchor="w")
        f = ttk.LabelFrame(left, text=" Enemy / NPC presets ", padding=6); f.pack(anchor="w", fill=tk.X)
        from . import npcpack
        r = ttk.Frame(f); r.pack(anchor="w")
        ttk.Label(r, text="Character").pack(side=tk.LEFT)
        ttk.Combobox(r, textvariable=v["npc"], values=[""] + list(npcpack.CHARACTERS), width=14, state="readonly").pack(side=tk.LEFT, padx=4)
        ttk.Button(r, text="Use its move set", command=self._npc_moves).pack(side=tk.LEFT)
        ttk.Label(f, text="Fictional preset bodies (goblin, guard, wizard ...) for mannequin / spec builds; vary them for a crowd.",
                  foreground="#555", wraplength=520).pack(anchor="w")
        self._preview_pane(tab, "variants")

    def _vary_changed(self):
        ks = [k for k, b in self.vary_b.items() if b.get()]
        self.app.v["vary"].set(",".join(ks) or VA.DEFAULT_VARY)

    def _npc_moves(self):
        from . import npcpack
        n = self.app.v["npc"].get().strip()
        if not n:
            return
        _, mp = npcpack.character_spec(n)
        from .moves import preset
        self.app._clear_rows()
        for m in preset(mp):
            self.app._add_row(m)
        if self.app.v["mode"].get() not in ("mannequin", "spec"):
            self.app.v["mode"].set("mannequin")
        if self.app.v["name"].get().strip() in ("", "hero"):
            self.app.v["name"].set(n)
        messagebox.showinfo("NPC preset", "%s: %d moves from the '%s' preset." % (n, len(self.app.rows), mp))


# ------------------------------------------------------------------ step 5 'Extras' goal tab
def goal_extras(home, tab):
    app = home.app; v, b = app.v, app.b
    ttk.Label(tab, text="Extras (all optional)", font=(home.fam, 11, "bold")).pack(anchor="w")
    g = ttk.Frame(tab); g.pack(anchor="w", pady=4)
    rows = [("framedata", "Hit / hurt boxes + frame data (framedata.json + .cfg, ESTIMATED from the silhouettes)", "Frame data"),
            ("footlock", "Foot locking (2-bone IK pins planted feet - no sliding; 3D characters)", "Foot lock"),
            ("qa", "Sprite QA check (qa_report.txt: clipping, empty frames, drift, pops, loop seams)", "QA"),
            ("physics", "Hair / cape / scarf physics (3D characters)", "Physics")]
    for i, (k, t, hk) in enumerate(rows):
        f = ttk.Frame(g); f.grid(row=i, column=0, sticky="w")
        ttk.Checkbutton(f, text=t, variable=b[k]).pack(side=tk.LEFT); app._q(f, hk).pack(side=tk.LEFT)
    g2 = ttk.Frame(tab); g2.pack(anchor="w", pady=6)
    ents = [("Look passes (fx)", "fx", FX_PRESETS, "FX"), ("Normal / emissive maps", "maps", ["", "normal", "normal,emissive", "emissive=#59f2ff"], "Maps"),
            ("Blend transitions", "blend", ["", "idle>walk:3", "idle>walk:3,walk>idle:3", "idle>walk:3,punch>idle:3"], "Blend"),
            ("3D LODs + baked model", "lods", ["0", "1", "2", "3"], "LODs")]
    for i, (lab, k, vals, hk) in enumerate(ents):
        ttk.Label(g2, text=lab, width=24).grid(row=i, column=0, sticky="w")
        ttk.Combobox(g2, textvariable=v[k], values=vals, width=40).grid(row=i, column=1, sticky="w", pady=1)
        app._q(g2, hk).grid(row=i, column=2, padx=4)
    ttk.Label(tab, text="Several characters into one atlas, a queue of builds, QA on any folder: the Tools menu "
              "(or forge.py atlas / batch / qa). Unity + Godot importers: plugins/ (see Help > Game engines).",
              foreground="#555", wraplength=1000, justify=tk.LEFT).pack(anchor="w", pady=(8, 0))


# ------------------------------------------------------------------ Tools menu
def install_menu(app, menubar):
    tm = tk.Menu(menubar, tearoff=0)
    tm.add_command(label="Batch queue... (run a list of builds)", command=lambda: tool_batch(app))
    tm.add_command(label="Atlas pack... (several characters, one atlas)", command=lambda: tool_atlas(app))
    tm.add_command(label="QA check a folder...", command=lambda: tool_qa(app))
    tm.add_command(label="Frame data for a folder...", command=lambda: tool_framedata(app))
    tm.add_command(label="Recolour a finished build...", command=lambda: tool_recolor(app))
    tm.add_separator()
    tm.add_command(label="Enemy / NPC presets", command=lambda: _show_text(app, "NPC presets", __import__("sforge.npcpack", fromlist=["x"]).listing()))
    tm.add_command(label="Game engine plugins folder", command=lambda: app._open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")))
    menubar.add_cascade(label="Tools", menu=tm)


def _show_text(app, title, text):
    w = tk.Toplevel(app.root); w.title(title); w.geometry("900x520")
    t = tk.Text(w, font="TkFixedFont", wrap=tk.NONE); t.pack(fill=tk.BOTH, expand=True); t.insert("1.0", text); t.configure(state=tk.DISABLED)
    return w


def _run_tool(app, argv, title, after=None):
    """forge.py ARGV in a thread, log into a small window"""
    import subprocess, sys, threading
    w = _show_text(app, title, "> python forge.py %s\n" % " ".join(argv))
    t = w.winfo_children()[0]

    def put(s):
        if t.winfo_exists():
            t.configure(state=tk.NORMAL); t.insert(tk.END, s + "\n"); t.see(tk.END); t.configure(state=tk.DISABLED)

    def work():
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ); env["PYTHONUNBUFFERED"] = "1"
        p = subprocess.Popen([sys.executable, os.path.join(root, "forge.py")] + argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        for ln in p.stdout:
            app.q.put(("cb", lambda a, ln=ln: put(ln.rstrip())))
        rc = p.wait()
        app.q.put(("cb", lambda a: (put("[exit %d]" % rc), after and after(rc))))
    threading.Thread(target=work, daemon=True).start()
    return w


def tool_batch(app):
    q = filedialog.askopenfilename(title="Batch queue (.txt: one forge.py command per line, or .json)", filetypes=[("Queue", "*.txt *.json"), ("All", "*.*")])
    if q:
        _run_tool(app, ["batch", q, "--workers", "2"], "Batch queue")


def tool_atlas(app):
    dirs = []
    while True:
        d = filedialog.askdirectory(title="Character build folder %d (Cancel when done)" % (len(dirs) + 1))
        if not d:
            break
        dirs.append(d)
    if len(dirs) < 1:
        return
    out = filedialog.askdirectory(title="Where to write the packed atlas") or os.path.join(app.v["out"].get() or "out", "pack")
    _run_tool(app, ["atlas"] + dirs + ["--out", out], "Atlas pack", lambda rc: rc == 0 and app._open(out))


def tool_qa(app):
    d = filedialog.askdirectory(title="Build folder (atlas.json) or game folder (sprites.cfg)")
    if d:
        _run_tool(app, ["qa", d], "Sprite QA")


def tool_framedata(app):
    d = filedialog.askdirectory(title="Build folder (atlas.json) or game folder (sprites.cfg)")
    if d:
        _run_tool(app, ["framedata", d], "Frame data")


def tool_recolor(app):
    d = filedialog.askdirectory(title="Finished build or game folder to recolour (a copy is made)")
    if not d:
        return
    from tkinter import simpledialog
    rec = recolor_string(app) or simpledialog.askstring("Recolour", "Set name and/or region colours (e.g. team_blue or top=#c01010):")
    if not rec:
        return
    argv = ["recolor", d, "--set", rec]
    if not os.path.isfile(os.path.join(d, "character.ini")):
        src = simpledialog.askstring("Recolour", "This folder has no character.ini (photo / game folder). Colours to replace, e.g.\n"
                                     "top=#2a5bd7,bottom=#202020,socks=#2a5bd7")
        if not src:
            return
        argv += ["--from", src]
    _run_tool(app, argv, "Recolour")
