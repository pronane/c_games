"""Sprite Forge Studio - Capture tab (v11.18).

`forge.py capture` in the Studio: a turnaround video (or one photo) of a person -> a rigged, textured 3D character.
Pick the video, say how tall the person is, press Capture. The log streams as it runs, the five steps light up as
they finish, and the turntable, the fit scores and the files appear on the right. Earlier captures in the output
folder are listed so their results can be opened again, or their texture rebuilt with --rebuild.
"""
from __future__ import annotations
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

STEPS = [("track", "Track", "pose, person mask and hair / skin / clothes labels in every frame"),
         ("fit", "Fit", "body shape, pose and one camera per frame, to the silhouettes"),
         ("texture", "Texture", "the photo texture, baked from the best views"),
         ("export", "Export", "GLB / FBX with skeleton and clips, OBJ, library rig"),
         ("check", "Check", "held-out frames re-rendered and compared with the real ones")]

# a log line -> the step it shows has started (the capture prints these prefixes as it goes)
STEP_OF = [(re.compile(r"^capture: \d+ frames at |^capture: \d+/\d+ frames tracked"), "track"),
           (re.compile(r"^(fit\b|layers:|face:|head:)"), "fit"),
           (re.compile(r"^(texture:|light:)"), "texture"),
           (re.compile(r"^capture: \S+\.(glb|fbx|obj)\b|^capture: FBX|^capture: white balance|^capture: --neutral"), "export"),
           (re.compile(r"^check\b"), "check")]

NEUTRAL = ["(none)", "upper", "lower", "shoes"]
NEUTRAL_LABEL = {"(none)": "Keep the colour as filmed", "upper": "Top (shirt, jumper, hoodie)",
                 "lower": "Trousers, shorts or skirt", "shoes": "Shoes"}


def step_of(line):
    """the capture step a log line belongs to, or None"""
    s = line.strip()
    for rx, step in STEP_OF:
        if rx.search(s):
            return step
    return None


def capture_argv(video, name, height_cm, out, body="auto", neutral="(none)", face_photo="", fps="", texture="",
                 layers=True, face=True, delight=True, register=True, rebuild=False):
    """the forge.py command line the tab runs (kept separate so it can be checked without a window)"""
    a = ["capture"]
    if video and not rebuild:
        a.append(video)
    if name:
        a += ["--name", name]
    if height_cm:
        a += ["--height-cm", str(height_cm)]
    if out:
        a += ["--out", out]
    if body and body != "auto":
        a += ["--body", body]
    if neutral and neutral != "(none)":
        a += ["--neutral", neutral]
    if face_photo:
        a += ["--face-photo", face_photo]
    if fps:
        a += ["--fps", str(fps)]
    if texture:
        a += ["--texture", str(texture)]
    if not layers:
        a.append("--no-layers")
    if not face:
        a.append("--no-face")
    if not delight:
        a.append("--keep-light")
    if not register:
        a.append("--no-register")
    if rebuild:
        a.append("--rebuild")
    return a


def find_captures(out):
    """[(name, folder)] of finished captures under an output folder (each has NAME/out/report.json)"""
    found = []
    if not out or not os.path.isdir(out):
        return found
    for n in sorted(os.listdir(out)):
        d = os.path.join(out, n)
        if os.path.isfile(os.path.join(d, "out", "report.json")):
            found.append((n, d))
    return found


def summary(report):
    """report.json -> short lines for the results panel"""
    lines = []
    h = report.get("height_m")
    if h:
        lines.append("Height %.2f m" % h)
    fit = report.get("fit") or {}
    if "iou" in fit:
        lines.append("Silhouette fit %.0f%% (from %.0f%%) over %d frames" % (100 * fit["iou"], 100 * fit.get("iou_start", fit["iou"]),
                                                                          fit.get("frames", 0)))
    c = report.get("check") or {}
    if "iou" in c:
        lines.append("Held-out frames: outline %.0f%%, colour difference %.1f, structure %.2f" % (
            100 * c["iou"], c.get("dE", float("nan")), c.get("ssim", float("nan"))))
    mac = report.get("macros") or {}
    if mac:
        lines.append("Body: %s, muscle %.0f%%, weight %.0f%%" % ("male" if mac.get("gender", 0.5) >= 0.5 else "female",
                                                                100 * mac.get("muscle", 0.5), 100 * mac.get("weight", 0.5)))
    lay = report.get("layers")
    if isinstance(lay, dict) and lay.get("clothes_faces"):
        parts = ["clothes over %s" % ", ".join(p.replace("_", " ") for p in (lay.get("offsets_m") or {}))] if lay.get("offsets_m") else ["clothes"]
        if lay.get("skirt"):
            parts.append("a skirt")
        hl = lay.get("hair_length_m") or 0.0
        if hl > 0.02:
            parts.append("hair %.0f cm long" % (100 * hl))
        elif (lay.get("hair_thickness_m") or 0) > 0:
            parts.append("short hair")
        lines.append("Layers: %s" % "; ".join(parts))
    wb = report.get("white_balance")
    if isinstance(wb, dict) and wb.get("applied"):
        lines.append("White balance from the %s garment" % wb.get("part"))
    return lines


def files_of(report, folder):
    """[(label, path)] of the exported files that exist"""
    out = []
    names = report.get("files") or {}
    for k, label in (("glb", "GLB (game engines, Blender)"), ("fbx", "FBX (Unity, Unreal, Maya)"), ("obj", "OBJ (static mesh)"),
                     ("mhm", "MakeHuman model"), ("mpfb", "MPFB (Blender MakeHuman)")):
        f = names.get(k)
        if f and os.path.isfile(os.path.join(folder, "out", f)):
            out.append((label, os.path.join(folder, "out", f)))
    return out


class CaptureTab:
    def __init__(self, app, frame):
        self.app, self.root, self.frame = app, app.root, frame
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.v = {k: tk.StringVar(value=val) for k, val in dict(
            video="", name="", height="", out=os.path.join(here, "captures"), body="auto", neutral="(none)",
            face_photo="", fps="", texture="1024").items()}
        self.b = {k: tk.BooleanVar(value=True) for k in ("layers", "face", "delight", "register")}
        self.status = tk.StringVar(value="Pick a turnaround video, say how tall the person is, then press Capture.")
        self._proc = None
        self._photo = None
        self._q = queue.Queue()          # lines and the exit code from the worker thread, read on Tk's own thread
        self._ui()
        self.refresh()
        self.root.after(60, self._poll)

    # ------------------------------------------------------------ layout
    def _ui(self):
        outer = ttk.Frame(self.frame)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        left = ttk.Frame(outer); left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(outer); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        H = ("Segoe UI", 11, "bold")
        ttk.Label(left, text="1. The person", font=H).grid(row=0, column=0, columnspan=3, sticky="w")
        r = 1
        r = self._row(left, r, "Video or photo *", "video", self._browse_video)
        r = self._row(left, r, "Name", "name", None)
        r = self._row(left, r, "Height (cm)", "height", None, width=8)
        ttk.Label(left, text="Body").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(left, textvariable=self.v["body"], values=["auto", "male", "female"], state="readonly",
                     width=10).grid(row=r, column=1, sticky="w"); r += 1
        r = self._row(left, r, "Face close-up (optional)", "face_photo", self._browse_face)

        ttk.Label(left, text="2. Colour", font=H).grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0)); r += 1
        ttk.Label(left, text="Neutral garment").grid(row=r, column=0, sticky="w", pady=2)
        self.neutral_box = ttk.Combobox(left, values=[NEUTRAL_LABEL[k] for k in NEUTRAL], state="readonly", width=30)
        self.neutral_box.current(0)
        self.neutral_box.bind("<<ComboboxSelected>>", lambda e: self.v["neutral"].set(NEUTRAL[self.neutral_box.current()]))
        self.neutral_box.grid(row=r, column=1, columnspan=2, sticky="w"); r += 1
        ttk.Label(left, text="Name one thing they wear that is white, grey or black, and the whole capture is\n"
                             "colour-corrected so it comes out neutral (lamps and windows tint everything).",
                  foreground="#555").grid(row=r, column=0, columnspan=3, sticky="w"); r += 1

        ttk.Label(left, text="3. Options", font=H).grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0)); r += 1
        opts = ttk.Frame(left); opts.grid(row=r, column=0, columnspan=3, sticky="w"); r += 1
        for i, (k, lab) in enumerate((("layers", "Separate clothes and hair meshes"), ("face", "Fit the face shape"),
                                      ("delight", "Take out the room's light"), ("register", "Line up every frame's camera"))):
            ttk.Checkbutton(opts, text=lab, variable=self.b[k]).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 10))
        more = ttk.Frame(left); more.grid(row=r, column=0, columnspan=3, sticky="w", pady=2); r += 1
        ttk.Label(more, text="Texture").pack(side=tk.LEFT)
        ttk.Combobox(more, textvariable=self.v["texture"], values=["512", "1024", "2048"], state="readonly", width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(more, text="Frames per second").pack(side=tk.LEFT)
        ttk.Entry(more, textvariable=self.v["fps"], width=5).pack(side=tk.LEFT, padx=4)
        r = self._row(left, r, "Output folder", "out", lambda: self._browse_dir("out"))

        bf = ttk.Frame(left); bf.grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 2)); r += 1
        self.go = ttk.Button(bf, text="Capture", command=self.capture); self.go.pack(side=tk.LEFT)
        self.stop_b = ttk.Button(bf, text="Stop", command=self.stop, state=tk.DISABLED); self.stop_b.pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Download models", command=self.setup).pack(side=tk.LEFT, padx=4)

        steps = ttk.Frame(left); steps.grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 0)); r += 1
        self.step_lab = {}
        for k, lab, tip in STEPS:
            w = tk.Label(steps, text=" %s " % lab, relief=tk.GROOVE, bg="#eeeeee", fg="#666", padx=6, pady=2)
            w.pack(side=tk.LEFT, padx=2)
            self.step_lab[k] = w
        ttk.Label(left, textvariable=self.status, wraplength=470, foreground="#333").grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 0)); r += 1
        self.log = tk.Text(left, width=66, height=14, wrap="word", font=("Consolas", 9))
        self.log.grid(row=r, column=0, columnspan=3, sticky="we", pady=4); r += 1

        top = ttk.Frame(right); top.pack(fill=tk.X)
        ttk.Label(top, text="Captures", font=H).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=6)
        self.rebuild_b = ttk.Button(top, text="Rebuild texture", command=self.rebuild, state=tk.DISABLED)
        self.rebuild_b.pack(side=tk.LEFT)
        self.open_b = ttk.Button(top, text="Open folder", command=self.open_folder, state=tk.DISABLED)
        self.open_b.pack(side=tk.LEFT, padx=4)
        self.list = tk.Listbox(right, height=5, exportselection=False)
        self.list.pack(fill=tk.X, pady=4)
        self.list.bind("<<ListboxSelect>>", lambda e: self.show_selected())
        self.view = ttk.Label(right); self.view.pack(anchor="nw", pady=4)
        self.result = ttk.Label(right, text="", justify=tk.LEFT, wraplength=620); self.result.pack(anchor="w")
        self.files = ttk.Frame(right); self.files.pack(anchor="w", pady=4)

    def _row(self, parent, r, label, key, browse, width=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
        ttk.Entry(parent, textvariable=self.v[key], width=width or 38).grid(row=r, column=1, sticky="w" if width else "we", pady=2)
        if browse:
            ttk.Button(parent, text="...", width=3, command=browse).grid(row=r, column=2, padx=2)
        return r + 1

    def _browse_video(self):
        p = filedialog.askopenfilename(filetypes=[("Video or photo", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.jpg *.jpeg *.png"), ("All", "*.*")])
        if p:
            self.v["video"].set(p)
            if not self.v["name"].get():
                self.v["name"].set(re.sub(r"[^a-z0-9_]+", "_", os.path.splitext(os.path.basename(p))[0].lower()).strip("_"))

    def _browse_face(self):
        p = filedialog.askopenfilename(filetypes=[("Photo", "*.jpg *.jpeg *.png"), ("All", "*.*")])
        if p:
            self.v["face_photo"].set(p)

    def _browse_dir(self, key):
        p = filedialog.askdirectory()
        if p:
            self.v[key].set(p); self.refresh()

    # ------------------------------------------------------------ running
    def _forge(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "forge.py")

    def argv(self, rebuild=False):
        v = self.v
        return capture_argv(v["video"].get().strip(), v["name"].get().strip(), v["height"].get().strip(), v["out"].get().strip(),
                            body=v["body"].get(), neutral=v["neutral"].get(), face_photo=v["face_photo"].get().strip(),
                            fps=v["fps"].get().strip(), texture=v["texture"].get(), layers=self.b["layers"].get(),
                            face=self.b["face"].get(), delight=self.b["delight"].get(), register=self.b["register"].get(),
                            rebuild=rebuild)

    def check_inputs(self, rebuild=False):
        """-> an error message, or None"""
        v = self.v
        if not rebuild:
            p = v["video"].get().strip()
            if not p:
                return "Choose the video (or one photo) of the person."
            if not os.path.isfile(p):
                return "The video was not found: %s" % p
        if not v["name"].get().strip():
            return "Give the capture a name (letters, digits and _)."
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", v["name"].get().strip()):
            return "Use only letters, digits, - and _ in the name."
        h = v["height"].get().strip()
        if h:
            try:
                hv = float(h)
            except ValueError:
                return "Height is in centimetres, e.g. 178."
            if not 50 <= hv <= 250:
                return "Height is in centimetres, e.g. 178 (between 50 and 250)."
        elif not rebuild:
            return "Say how tall the person is in cm: one camera cannot measure size."
        fp = v["face_photo"].get().strip()
        if fp and not os.path.isfile(fp):
            return "The face photo was not found: %s" % fp
        return None

    def capture(self):
        err = self.check_inputs()
        if err:
            messagebox.showerror("Capture", err); return
        self._start(self.argv(), "Capturing %s - this takes a few minutes on the CPU." % self.v["name"].get())

    def rebuild(self):
        sel = self._selected()
        if not sel:
            return
        self.v["name"].set(sel[0])
        err = self.check_inputs(rebuild=True)
        if err:
            messagebox.showerror("Rebuild", err); return
        self._start(self.argv(rebuild=True), "Rebuilding the texture and exports of %s from its fit." % sel[0])

    def setup(self):
        self._start(["capture", "--setup"], "Downloading the pose and segmentation models (once).")

    def _start(self, argv, msg):
        if self._proc is not None:
            self.status.set("A capture is already running."); return
        self.log.delete("1.0", tk.END)
        for w in self.step_lab.values():
            w.configure(bg="#eeeeee", fg="#666")
        self.status.set(msg)
        self.go.configure(state=tk.DISABLED); self.stop_b.configure(state=tk.NORMAL)
        try:
            self._proc = subprocess.Popen([sys.executable, "-u", self._forge(), *argv], stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True, bufsize=1,
                                          cwd=os.path.dirname(self._forge()))
        except OSError as e:
            self._finish(1, str(e)); return
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        p = self._proc
        for line in p.stdout:
            self._q.put(("line", line))
        self._q.put(("done", p.wait()))

    def _poll(self):
        """Tk is not thread-safe: the worker only queues, and this drains the queue on Tk's thread"""
        try:
            while True:
                kind, val = self._q.get_nowait()
                if kind == "line":
                    self._line(val)
                else:
                    self._finish(val, None)
        except queue.Empty:
            pass
        try:
            self.root.after(60, self._poll)
        except tk.TclError:
            pass

    def _line(self, line):
        self.log.insert(tk.END, line); self.log.see(tk.END)
        st = step_of(line)
        if st:
            self.mark(st)

    def mark(self, step, done=False):
        """light the step (amber while it runs, green once a later one starts or the capture ends)"""
        keys = [k for k, _, _ in STEPS]
        i = keys.index(step)
        for j, k in enumerate(keys):
            if j < i or (done and j == i):
                self.step_lab[k].configure(bg="#c8ecc9", fg="#1d5e20")
            elif j == i:
                self.step_lab[k].configure(bg="#ffe8a8", fg="#6b4e00")

    def stop(self):
        if self._proc is not None:
            self._proc.terminate()
            self.status.set("Stopping...")

    def _finish(self, code, err):
        self._proc = None
        self.go.configure(state=tk.NORMAL); self.stop_b.configure(state=tk.DISABLED)
        if err:
            self.log.insert(tk.END, err)
        if code == 0:
            self.mark("check", done=True)
            self.status.set("Done.")
            self.refresh(select=self.v["name"].get().strip())
        else:
            self.status.set("Stopped." if code < 0 else "Failed (exit %d) - the log above says why." % code)

    # ------------------------------------------------------------ results
    def refresh(self, select=None):
        self.caps = find_captures(self.v["out"].get().strip())
        self.list.delete(0, tk.END)
        for n, d in self.caps:
            self.list.insert(tk.END, n)
        names = [n for n, _ in self.caps]
        if select in names:
            i = names.index(select)
            self.list.selection_clear(0, tk.END); self.list.selection_set(i); self.list.see(i)
            self.show_selected()

    def _selected(self):
        s = self.list.curselection()
        return self.caps[s[0]] if s else None

    def show_selected(self):
        sel = self._selected()
        st = tk.NORMAL if sel else tk.DISABLED
        self.rebuild_b.configure(state=st); self.open_b.configure(state=st)
        for w in self.files.winfo_children():
            w.destroy()
        if not sel:
            return
        name, d = sel
        try:
            rep = json.load(open(os.path.join(d, "out", "report.json")))
        except (OSError, ValueError):
            rep = {}
        self.result.configure(text="\n".join(summary(rep)) or "No report.")
        tt = os.path.join(d, "out", name + "_turntable.jpg")
        if os.path.isfile(tt):
            from PIL import Image, ImageTk
            im = Image.open(tt); im.thumbnail((640, 460))
            self._photo = ImageTk.PhotoImage(im)
            self.view.configure(image=self._photo)
        else:
            self.view.configure(image="")
        for label, path in files_of(rep, d):
            row = ttk.Frame(self.files); row.pack(anchor="w")
            ttk.Label(row, text=label, width=30).pack(side=tk.LEFT)
            ttk.Label(row, text=os.path.basename(path), foreground="#1a5fb4").pack(side=tk.LEFT)

    def open_folder(self):
        sel = self._selected()
        if not sel:
            return
        p = os.path.join(sel[1], "out")
        try:
            if sys.platform.startswith("win"):
                os.startfile(p)                                    # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
        except OSError:
            messagebox.showinfo("Open folder", p)
