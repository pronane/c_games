"""Sprite Forge Studio - Appearance tab (v10.2): sliders for a realistic MakeHuman character with a live preview.

Body (arm / shoulder / chest / back / thigh / calf muscle, shoulder width), face (nose, lips, mouth, cheekbones,
cheeks, jaw, chin, eye size, ears, brow height), hair (style, colour, balding hairline, moustache / goatee / beard,
eyebrow shape, thickness and colour) and skin & eyes.  Every control is one Appearance key (sforge/appearance.py),
so a look saves as plain `key = value` lines that forge.py look / tools/gaelic_squad.py read too."""
from __future__ import annotations
import os, random, threading
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox

from .appearance import Appearance, SLIDERS, GROUPS, INFO

PREVIEW_H = 460


class AppearanceTab:
    def __init__(self, app, frame):
        self.app, self.root, self.frame = app, app.root, frame
        self.ap = Appearance()
        self.vars = {}
        self.view = tk.StringVar(value="face + body")
        self.kit = tk.StringVar(value="home")
        self.status = tk.StringVar(value="")
        self.builder = None
        self._job = None; self._busy = False; self._again = False
        self._photo = None
        self.last_image = None
        self._ui()

    # ------------------------------------------------------------------ UI
    def _ui(self):
        top = ttk.Frame(self.frame); top.pack(fill=tk.X, padx=6, pady=(6, 2))
        for txt, cmd in (("Load look...", self.load), ("Save look...", self.save), ("Randomise", self.randomise),
                         ("Reset", self.reset), ("Export GLB...", self.export_glb), ("Export sprites...", self.export_sprites)):
            ttk.Button(top, text=txt, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Label(top, text="  Kit").pack(side=tk.LEFT)
        from . import footballer as FB
        cb = ttk.Combobox(top, textvariable=self.kit, values=list(FB.KITS), width=9, state="readonly"); cb.pack(side=tk.LEFT, padx=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self.changed())
        body = ttk.Frame(self.frame); body.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        # left: scrolling controls
        wrap = ttk.Frame(body, width=470); wrap.pack(side=tk.LEFT, fill=tk.Y); wrap.pack_propagate(False)
        cv = tk.Canvas(wrap, highlightthickness=0, width=450)
        sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=cv.yview)
        inner = ttk.Frame(cv)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=inner, anchor="nw", width=448)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        cv.bind("<Button-4>", lambda e: cv.yview_scroll(-3, "units")); cv.bind("<Button-5>", lambda e: cv.yview_scroll(3, "units"))
        self.canvas_controls = cv
        for g in GROUPS:
            lf = ttk.LabelFrame(inner, text=g); lf.pack(fill=tk.X, pady=3)
            lf.columnconfigure(1, weight=1)
            r = 0
            for key, kind, d, rng, label, group, _ in SLIDERS:
                if group != g:
                    continue
                ttk.Label(lf, text=label, width=24).grid(row=r, column=0, sticky="w", padx=3)
                if kind == "slider":
                    v = tk.DoubleVar(value=d)
                    s = ttk.Scale(lf, from_=rng[0], to=rng[1], variable=v, orient=tk.HORIZONTAL,
                                  command=lambda _v, k=key: self._slid(k))
                    s.grid(row=r, column=1, sticky="ew", padx=3)
                    lab = ttk.Label(lf, text="%.2f" % d, width=5); lab.grid(row=r, column=2)
                    s.bind("<ButtonRelease-1>", lambda e: self.changed())
                    self.vars[key] = (v, lab)
                elif kind == "choice":
                    v = tk.StringVar(value=d)
                    c = ttk.Combobox(lf, textvariable=v, values=list(rng), state="readonly", width=24)
                    c.grid(row=r, column=1, columnspan=2, sticky="ew", padx=3)
                    c.bind("<<ComboboxSelected>>", lambda e, k=key: self._set(k))
                    self.vars[key] = (v, None)
                else:
                    v = tk.StringVar(value=d)
                    f = ttk.Frame(lf); f.grid(row=r, column=1, columnspan=2, sticky="ew", padx=3)
                    e = ttk.Entry(f, textvariable=v, width=9); e.pack(side=tk.LEFT)
                    e.bind("<Return>", lambda ev, k=key: self._set(k)); e.bind("<FocusOut>", lambda ev, k=key: self._set(k))
                    sw = tk.Label(f, width=3, relief=tk.SUNKEN); sw.pack(side=tk.LEFT, padx=3)
                    ttk.Button(f, text="Pick...", command=lambda k=key: self._pick(k)).pack(side=tk.LEFT)
                    self.vars[key] = (v, sw)
                r += 1
        # right: preview
        right = ttk.Frame(body); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        vf = ttk.Frame(right); vf.pack(fill=tk.X)
        for t in ("face + body", "front", "side", "back", "sprites: run", "sprites: kick"):
            ttk.Radiobutton(vf, text=t, value=t, variable=self.view, command=self.changed).pack(side=tk.LEFT, padx=2)
        self.preview = tk.Label(right, bg="#5c8550", width=720, height=PREVIEW_H); self.preview.pack(fill=tk.BOTH, expand=True, pady=4)
        ttk.Label(right, textvariable=self.status, foreground="#444", wraplength=700, justify=tk.LEFT).pack(anchor="w")
        self.keys_text = tk.Text(right, height=6, width=60, font=("Courier", 9)); self.keys_text.pack(fill=tk.X, pady=(4, 0))
        self._sync_swatches()
        self.status.set("Move a slider or pick a style: the preview rebuilds (about 3-5 s).  Needs the MakeHuman library "
                        "(forge.py human --setup --full).")

    # ------------------------------------------------------------------ values
    def _slid(self, k):
        v, lab = self.vars[k]
        lab.config(text="%.2f" % v.get())

    def _set(self, k):
        v, _ = self.vars[k]
        try:
            self.ap.set(k, v.get())
        except (ValueError, KeyError) as e:
            self.status.set(str(e)); return
        self._sync_swatches(); self.changed(read=False)

    def _pick(self, k):
        cur = self.ap.rgb(k)
        init = "#%02x%02x%02x" % tuple(int(c * 255) for c in cur) if cur else None
        res = colorchooser.askcolor(color=init, title=INFO[k][4])
        if res and res[1]:
            self.vars[k][0].set(res[1]); self._set(k)

    def _sync_swatches(self):
        for k, (v, w) in self.vars.items():
            if INFO[k][1] == "colour" and w is not None:
                c = self.ap.rgb(k)
                w.config(bg="#%02x%02x%02x" % tuple(int(x * 255) for x in c) if c else "#d9d9d9")

    def read_controls(self):
        for k, (v, _) in self.vars.items():
            try:
                self.ap.set(k, v.get())
            except (ValueError, KeyError, tk.TclError):
                pass

    def write_controls(self):
        for k, (v, lab) in self.vars.items():
            val = self.ap.values[k]
            v.set(val)
            if lab is not None and INFO[k][1] == "slider":
                lab.config(text="%.2f" % float(val))
        self._sync_swatches()

    def set_values(self, d):
        for k, val in d.items():
            self.ap.set(k, val)
        self.write_controls(); self.changed(read=False)

    # ------------------------------------------------------------------ actions
    def reset(self):
        self.ap = Appearance(); self.write_controls(); self.changed(read=False)

    def randomise(self, seed=None):
        rnd = random.Random(seed)
        ap = Appearance()
        for key, kind, d, rng, *_ in SLIDERS:
            if kind == "slider":
                ap.set(key, round(rnd.uniform(*rng) * (0.6 if rng[0] < 0 else 0.5), 2) if rnd.random() < 0.55 else d)
            elif kind == "choice":
                ap.set(key, rnd.choice(rng))
        ap.set("hair_colour", rnd.choice(["#1c140e", "#3b2614", "#5b3a1e", "#9a4a1c", "#c9a35e", "#6b6b6b"]))
        if ap.skin.endswith("female"):
            ap.set("facial_hair", "none")
        self.ap = ap; self.write_controls(); self.changed(read=False)

    def load(self, path=None):
        path = path or filedialog.askopenfilename(title="Load look", filetypes=[("Look / squad", "*.txt"), ("All", "*.*")])
        if not path:
            return
        from .look import read_looks
        looks = read_looks(open(path, encoding="utf-8").read())
        if not looks:
            messagebox.showerror("Load look", "no appearance keys in " + path); return
        self.ap = looks[0][1]; self.write_controls(); self.changed(read=False)
        self.status.set("loaded %s%s" % (os.path.basename(path), " (first of %d looks)" % len(looks) if len(looks) > 1 else ""))

    def save(self, path=None):
        self.read_controls()
        path = path or filedialog.asksaveasfilename(title="Save look", defaultextension=".txt", filetypes=[("Look", "*.txt")])
        if not path:
            return
        from .look import look_text
        open(path, "w").write("# Sprite Forge look (forge.py look --look %s)\n" % os.path.basename(path) + look_text(self.ap))
        self.status.set("saved " + path)

    def _need_builder(self):
        if self.builder is None:
            from .look import Builder
            self.builder = Builder()
        return self.builder

    def export_glb(self, path=None):
        path = path or filedialog.asksaveasfilename(title="Export GLB", defaultextension=".glb", filetypes=[("glTF binary", "*.glb")])
        if not path:
            return
        self.read_controls(); ap = self._copy()
        self._bg(lambda b: (b.glb(b.character(ap, self.kit.get()), path), "GLB -> " + path)[1])

    def export_sprites(self, folder=None, clips=None, frames=8):
        folder = folder or filedialog.askdirectory(title="Sprites folder")
        if not folder:
            return
        self.read_controls(); ap = self._copy()

        def work(b):
            from .look import pick_clips
            cl = clips.split(",") if clips else pick_clips(b.poser.clips)
            ch = b.character(ap, self.kit.get())
            b.sprites(ch, cl, frames, folder, log=lambda *a: None)
            return "sprites (%s, %d frames, 192x256, facing right) -> %s" % (", ".join(cl), frames, folder)
        self._bg(work)

    def _copy(self):
        a = Appearance(); a.values = dict(self.ap.values); return a

    def _bg(self, fn):
        self.status.set("working...")

        def run():
            try:
                msg = fn(self._need_builder())
            except Exception as e:                                   # noqa: BLE001 - shown to the user
                msg = "failed: %s" % e
            self.root.after(0, lambda: self.status.set(msg))
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------ live preview
    def changed(self, read=True):
        if read:
            self.read_controls()
        self.keys_text.delete("1.0", tk.END)
        self.keys_text.insert("1.0", "\n".join(self.ap.spec_lines()) or "(template look: every slider at 0)")
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(350, self._rebuild)

    def _rebuild(self, done=None):
        self._job = None
        if self._busy:
            self._again = True; return
        self._busy = True
        ap, view, kit = self._copy(), self.view.get(), self.kit.get()
        self.status.set("building preview...")

        def run():
            import time
            t0 = time.time()
            try:
                b = self._need_builder()
                ch = b.character(ap, kit, skin_res=512)
                img = self.render_view(b, ch, view)
                msg = "%s - %d meshes, %d triangles, %.1f s" % (view, len(ch.parts), sum(len(p.F) for p in ch.parts), time.time() - t0)
            except Exception as e:                                   # noqa: BLE001
                img, msg = None, "preview failed: %s" % e
            self.root.after(0, lambda: self._show(img, msg, done))
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def render_view(b, ch, view):
        from . import mhrender as MR
        from PIL import Image
        if view == "face + body":
            return b.preview(ch, PREVIEW_H)
        if view in ("front", "side", "back"):
            yaw = {"front": 0.0, "side": 90.0, "back": 180.0}[view]
            im = MR.render(ch, MR.rest(ch), MR.View.full(yaw), (int(PREVIEW_H * 0.62), PREVIEW_H), bg=(0.36, 0.52, 0.30))
            face = MR.render(ch, MR.rest(ch), MR.View.face(yaw), (PREVIEW_H, PREVIEW_H), bg=(0.36, 0.52, 0.30))
            out = Image.new("RGBA", (face.width + im.width, PREVIEW_H)); out.paste(face, (0, 0)); out.paste(im, (face.width, 0))
            return out
        clip = "run" if view.endswith("run") else ("kick_run" if "kick_run" in b.poser.clips else "kick")
        cells = b.sprites(ch, [clip], 6, None)[clip]
        sheet = MR.contact_sheet(cells, 3)
        return sheet.resize((int(sheet.width * 0.9), int(sheet.height * 0.9)), Image.LANCZOS)

    def _show(self, img, msg, done=None):
        self._busy = False
        self.status.set(msg)
        if img is not None:
            from PIL import ImageTk
            self.last_image = img
            self._photo = ImageTk.PhotoImage(img)
            self.preview.config(image=self._photo, width=img.width, height=img.height)
        if self._again:
            self._again = False; self._rebuild(done); return
        if done:
            done()
