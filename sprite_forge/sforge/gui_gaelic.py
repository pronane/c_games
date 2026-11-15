"""Sprite Forge Studio - Gaelic tab.

The same commands as `forge.py gaelic-fit` and `forge.py gaelic-clip`, with the preview image
beside the form. Nothing here writes the shipped player.
"""
from __future__ import annotations
import os, sys, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class GaelicTab:
    def __init__(self, app, frame):
        self.app, self.root, self.frame = app, app.root, frame
        self.mesh = tk.StringVar()
        self.out = tk.StringVar(value="/tmp/gf_fit")
        self.template = tk.StringVar()
        self.preview = tk.BooleanVar(value=True)
        self.player = tk.StringVar()
        self.clip = tk.StringVar()
        self.source = tk.StringVar()
        self.name = tk.StringVar(value="bounce")
        self.clip_out = tk.StringVar(value="/tmp/gf_clip")
        self.status = tk.StringVar(value="Scratch output only. The shipped player is not modified.")
        self._photo = None
        self._busy = False
        self._ui()

    def _ui(self):
        outer = ttk.Frame(self.frame)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        left = ttk.Frame(outer)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(outer)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        ttk.Label(left, text="Fit a mesh onto the Gaelic skeleton", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._row(left, 1, "Mesh", self.mesh, self._browse_mesh)
        self._row(left, 2, "Output directory", self.out, lambda: self._browse_dir(self.out))
        self._row(left, 3, "Template (optional)", self.template, self._browse_template)
        ttk.Checkbutton(left, text="Write preview sheets", variable=self.preview).grid(row=4, column=1, sticky="w", pady=2)
        ttk.Button(left, text="Fit mesh", command=self.fit).grid(row=5, column=1, sticky="w", pady=4)

        ttk.Separator(left, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=3, sticky="we", pady=8)
        ttk.Label(left, text="Merge one clip into a copy", font=("Segoe UI", 11, "bold")).grid(row=7, column=0, columnspan=3, sticky="w")
        self._row(left, 8, "Player GLB", self.player, self._browse_player)
        self._row(left, 9, "Clip GLB", self.clip, self._browse_clip)
        self._row(left, 10, "Source name", self.source, None)
        self._row(left, 11, "Clip name", self.name, None)
        self._row(left, 12, "Output directory", self.clip_out, lambda: self._browse_dir(self.clip_out))
        bf = ttk.Frame(left)
        bf.grid(row=13, column=1, sticky="w", pady=4)
        ttk.Button(bf, text="Check player", command=self.check).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bf, text="Merge clip", command=self.merge).pack(side=tk.LEFT)

        ttk.Label(left, textvariable=self.status, wraplength=420, foreground="#333").grid(row=14, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.log = tk.Text(left, width=62, height=12, wrap="word")
        self.log.grid(row=15, column=0, columnspan=3, sticky="we", pady=6)

        ttk.Label(right, text="Preview", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.view = ttk.Label(right)
        self.view.pack(anchor="nw", pady=4)
        ttk.Label(right, text="Home and away are the kit shells. The deform sheet is the skinned body.",
                  wraplength=280, foreground="#555").pack(anchor="w")

    def _row(self, parent, r, label, var, browse):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
        ttk.Entry(parent, textvariable=var, width=36).grid(row=r, column=1, sticky="we", pady=2)
        if browse:
            ttk.Button(parent, text="...", width=3, command=browse).grid(row=r, column=2, padx=2)

    def _browse_mesh(self):
        p = filedialog.askopenfilename(filetypes=[("Mesh", "*.glb *.gltf *.obj"), ("All", "*.*")])
        if p:
            self.mesh.set(p)

    def _browse_template(self):
        p = filedialog.askopenfilename(filetypes=[("GLB", "*.glb")])
        if p:
            self.template.set(p)

    def _browse_player(self):
        p = filedialog.askopenfilename(filetypes=[("GLB", "*.glb")])
        if p:
            self.player.set(p)

    def _browse_clip(self):
        p = filedialog.askopenfilename(filetypes=[("GLB", "*.glb")])
        if p:
            self.clip.set(p)

    def _browse_dir(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def _forge(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "forge.py")

    def _run(self, argv, image=None):
        if self._busy:
            self.status.set("Already running.")
            return
        self._busy = True
        self.status.set("Running…")
        self.log.delete("1.0", tk.END)

        def work():
            import subprocess
            try:
                p = subprocess.run([sys.executable, self._forge(), *argv], capture_output=True, text=True)
                text = (p.stdout or "") + (p.stderr or "")
                code = p.returncode
            except Exception as e:
                text, code = str(e), 1
            self.root.after(0, lambda: self._done(text, code, image))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, text, code, image):
        self._busy = False
        self.log.insert(tk.END, text[-4000:])
        self.status.set("Done." if code == 0 else "Failed (exit %d)." % code)
        if code == 0 and image and os.path.isfile(image):
            self._show(image)

    def _show(self, path):
        from PIL import Image, ImageTk
        im = Image.open(path)
        im.thumbnail((360, 640))
        self._photo = ImageTk.PhotoImage(im)
        self.view.configure(image=self._photo)

    def fit(self):
        if not self.mesh.get() or not self.out.get():
            messagebox.showerror("Gaelic fit", "Choose a mesh and an output directory.")
            return
        argv = ["gaelic-fit", self.mesh.get(), "--out", self.out.get()]
        if self.template.get():
            argv.extend(["--template", self.template.get()])
        if self.preview.get():
            argv.append("--preview")
        sheet = os.path.join(self.out.get(), "preview", "deform_sheet.png")
        self._run(argv, sheet if self.preview.get() else None)

    def check(self):
        if not self.player.get():
            messagebox.showerror("Gaelic clip", "Choose the player GLB to check.")
            return
        self._run(["gaelic-clip", "check", self.player.get()])

    def merge(self):
        if not (self.player.get() and self.clip.get() and self.source.get() and self.name.get() and self.clip_out.get()):
            messagebox.showerror("Gaelic clip", "Player, clip, source name, clip name and output directory are required.")
            return
        self._run(["gaelic-clip", "merge", self.player.get(), self.clip.get(),
                   "--source", self.source.get(), "--name", self.name.get(),
                   "--out", self.clip_out.get(), "--provenance", "unspecified"])
