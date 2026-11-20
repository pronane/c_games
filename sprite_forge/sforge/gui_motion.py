"""Sprite Forge Studio - Motion tab (v11.18).

The shared-skeleton motion library (`forge.py motion`) in the Studio. Every move - the shipped starter set, your
recorded clips, imports from Mixamo / CMU / Quaternius - is listed with where it came from and its licence. Pick one
and it plays on the mannequin, front and side, with a scrubber; the motion checks (tools/check_motion.py: size,
floor, pops, loop, facing...) are shown beside it. Import a BVH / FBX / GLB, record a move from a video, clean a
move (foot plant, weight shift, anticipation, follow-through) or retarget it onto a rig, from the buttons.
"""
from __future__ import annotations
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# bones drawn, child -> parent (the rig's own names); the ball and root are left out
DRAW = [("spine", "hips"), ("chest", "spine"), ("neck", "chest"), ("head", "neck"),
        ("upperarm_L", "chest"), ("forearm_L", "upperarm_L"), ("hand_L", "forearm_L"), ("hand_L_tip", "hand_L"),
        ("upperarm_R", "chest"), ("forearm_R", "upperarm_R"), ("hand_R", "forearm_R"), ("hand_R_tip", "hand_R"),
        ("thigh_L", "hips"), ("shin_L", "thigh_L"), ("foot_L", "shin_L"), ("foot_L_tip", "foot_L"),
        ("thigh_R", "hips"), ("shin_R", "thigh_R"), ("foot_R", "shin_R"), ("foot_R_tip", "foot_R")]
TIPS = {"hand_L": (0, -0.1, 0), "hand_R": (0, -0.1, 0), "foot_L": (0, -0.05, 0.17), "foot_R": (0, -0.05, 0.17)}


def move_rows(library):
    """[(name, category, seconds, loop, origin, licence)] for every move the library can play"""
    from . import motionlib as ML
    lib = ML.open_library(library or None)
    rows = []
    for n in lib.names():
        try:
            rec = lib.load(n)
        except (OSError, ValueError, KeyError):
            continue
        lic = rec.get("licence") or {}
        lic_s = lic.get("spdx") or lic.get("id") or "" if isinstance(lic, dict) else str(lic)
        try:
            org = ML.origin_of(n, library or None)
        except KeyError:
            org = rec.get("origin", "")
        rows.append((n, rec.get("category") or "", float(rec.get("duration") or 1.0), bool(rec.get("loop")), org, lic_s))
    return rows


def pose_points(motion, t):
    """the drawn joints' world positions (metres; +x the figure's left, +y up, +z forward) at time t (0..1)"""
    from . import rig
    pose, mix = motion.sample(t)
    s = rig.evaluate(pose, mix) if mix else rig.evaluate(pose)
    W = s.world
    pts = {}
    for b in {x for pair in DRAW for x in pair}:
        if b in W:
            pts[b] = np.asarray(W[b])[:3, 3]
    for b, off in TIPS.items():                                     # the hand's and foot's far end
        if b in W:
            M = np.asarray(W[b])
            pts[b + "_tip"] = M[:3, :3] @ np.array(off, float) + M[:3, 3]
    return pts


def project(pts, view, size, scale=None, floor=0.0):
    """joint positions -> canvas pixels for a front (camera on +z, looking back) or side (figure facing right) view"""
    w, h = size
    s = scale or (h * 0.82 / 2.0)                                   # 2 m of figure fills most of the height
    out = {}
    for b, p in pts.items():
        x = p[0] if view == "front" else p[2]                      # facing the viewer, the figure's left is on the right
        out[b] = (w * 0.5 + s * x, h * 0.92 - s * (p[1] - floor))
    return out


def qa(rec, name):
    """the motion checks for one move -> [(check, ok, detail)]"""
    sys.path.insert(0, os.path.join(HERE, "tools"))
    try:
        import check_motion as CM
    except ImportError:
        return []
    try:
        return [(c, ok, d) for c, ok, d in CM.check_clip(rec, name)]
    except Exception as e:                                           # noqa: BLE001
        return [("checks", False, "could not run: %s" % e)]


class MotionTab:
    def __init__(self, app, frame):
        self.app, self.root, self.frame = app, app.root, frame
        from . import motionlib as ML
        self.ML = ML
        self.lib = tk.StringVar(value=os.environ.get("SFS_MOTIONS") or ML.user_dir())
        self.search = tk.StringVar()
        self.cat = tk.StringVar(value="(all)")
        self.speed = tk.DoubleVar(value=1.0)
        self.t = tk.DoubleVar(value=0.0)
        self.playing = True
        self.status = tk.StringVar(value="")
        self.motion = None
        self.rec = None
        self._proc = None
        self._q = queue.Queue()          # the worker thread's lines and exit code, read on Tk's own thread
        self._then = None
        self._ui()
        self.reload()
        self.root.after(40, self._tick)

    # ------------------------------------------------------------ layout
    def _ui(self):
        H = ("Segoe UI", 11, "bold")
        outer = ttk.Frame(self.frame); outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        left = ttk.Frame(outer, width=520); left.pack(side=tk.LEFT, fill=tk.BOTH)
        right = ttk.Frame(outer); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        top = ttk.Frame(left); top.pack(fill=tk.X)
        ttk.Label(top, text="Library", font=H).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.lib, width=40).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(top, text="...", width=3, command=self._browse_lib).pack(side=tk.LEFT)
        flt = ttk.Frame(left); flt.pack(fill=tk.X, pady=4)
        ttk.Label(flt, text="Find").pack(side=tk.LEFT)
        e = ttk.Entry(flt, textvariable=self.search, width=22); e.pack(side=tk.LEFT, padx=4)
        self.search.trace_add("write", lambda *a: self.fill())
        ttk.Label(flt, text="Category").pack(side=tk.LEFT, padx=(8, 0))
        self.cat_box = ttk.Combobox(flt, textvariable=self.cat, state="readonly", width=16)
        self.cat_box.pack(side=tk.LEFT, padx=4)
        self.cat_box.bind("<<ComboboxSelected>>", lambda e: self.fill())
        self.count = ttk.Label(flt, text=""); self.count.pack(side=tk.LEFT, padx=6)

        cols = ("category", "secs", "loop", "origin", "licence")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings", height=22, selectmode="browse")
        self.tree.heading("#0", text="Move"); self.tree.column("#0", width=170)
        for c, lab, w in (("category", "Category", 100), ("secs", "Secs", 44), ("loop", "Loop", 40),
                          ("origin", "From", 70), ("licence", "Licence", 92)):
            self.tree.heading(c, text=lab); self.tree.column(c, width=w, anchor="w" if c in ("category", "origin", "licence") else "e")
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())

        ttk.Label(right, text="Preview", font=H).pack(anchor="w")
        self.canvas = tk.Canvas(right, width=560, height=330, bg="#f6f7f9", highlightthickness=1, highlightbackground="#ccd")
        self.canvas.pack(anchor="w", pady=4)
        ctl = ttk.Frame(right); ctl.pack(fill=tk.X)
        self.play_b = ttk.Button(ctl, text="Pause", width=7, command=self.toggle); self.play_b.pack(side=tk.LEFT)
        self.scrub = ttk.Scale(ctl, from_=0.0, to=1.0, variable=self.t, command=lambda v: self._scrubbed(), length=300)
        self.scrub.pack(side=tk.LEFT, padx=6)
        ttk.Label(ctl, text="Speed").pack(side=tk.LEFT)
        ttk.Combobox(ctl, values=["0.25", "0.5", "1.0", "2.0"], width=5, state="readonly",
                     textvariable=self.speed).pack(side=tk.LEFT, padx=4)
        self.info = ttk.Label(right, text="", justify=tk.LEFT, wraplength=560); self.info.pack(anchor="w", pady=(6, 2))
        ttk.Label(right, text="Checks", font=H).pack(anchor="w", pady=(6, 0))
        self.checks = ttk.Frame(right); self.checks.pack(anchor="w")

        acts = ttk.Frame(right); acts.pack(anchor="w", pady=(10, 2))
        ttk.Button(acts, text="Import file...", command=self.import_file).pack(side=tk.LEFT)
        ttk.Button(acts, text="Record from video...", command=self.record).pack(side=tk.LEFT, padx=4)
        self.clean_b = ttk.Button(acts, text="Clean move", command=self.clean, state=tk.DISABLED); self.clean_b.pack(side=tk.LEFT)
        self.ret_b = ttk.Button(acts, text="Retarget onto...", command=self.retarget, state=tk.DISABLED); self.ret_b.pack(side=tk.LEFT, padx=4)
        ttk.Label(right, textvariable=self.status, wraplength=560, foreground="#333").pack(anchor="w")
        self.log = tk.Text(right, width=78, height=6, wrap="word", font=("Consolas", 9)); self.log.pack(anchor="w", pady=4)

    def _browse_lib(self):
        p = filedialog.askdirectory()
        if p:
            self.lib.set(p); self.reload()

    # ------------------------------------------------------------ list
    def reload(self):
        try:
            self.rows = move_rows(self.lib.get().strip())
        except Exception as e:                                       # noqa: BLE001
            self.rows = []
            self.status.set("Could not read the library: %s" % e)
        cats = sorted({r[1] for r in self.rows if r[1]})
        self.cat_box.configure(values=["(all)"] + cats)
        if self.cat.get() not in ["(all)"] + cats:
            self.cat.set("(all)")
        self.fill()

    def fill(self):
        q = self.search.get().strip().lower(); c = self.cat.get()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for n, cat, secs, loop, org, lic in self.rows:
            if q and q not in n.lower() and q not in cat.lower():
                continue
            if c != "(all)" and cat != c:
                continue
            self.tree.insert("", tk.END, iid=n, text=n, values=(cat, "%.1f" % secs, "yes" if loop else "", org, lic))
            shown += 1
        self.count.configure(text="%d of %d moves" % (shown, len(self.rows)))

    def select(self, name=None):
        name = name or (self.tree.selection() or [None])[0]
        if not name:
            return
        try:
            self.rec = self.ML.open_library(self.lib.get().strip() or None).load(name)
            self.motion = self.ML.as_motion(name, self.lib.get().strip() or None)
        except Exception as e:                                       # noqa: BLE001
            self.status.set("Could not load %s: %s" % (name, e)); return
        self.t.set(0.0)
        r = self.rec; lic = r.get("licence") or {}
        lines = ["%s  -  %s%s" % (name, r.get("category") or "", ", loops" if r.get("loop") else ""),
                 r.get("desc") or "", "Source: %s" % (r.get("source") or "-")]
        if isinstance(lic, dict) and lic:
            lines.append("Licence: %s%s%s" % (lic.get("spdx") or "?", ("  by " + lic["author"]) if lic.get("author") else "",
                                              "  (may not be redistributed)" if lic.get("redistribution") == "no" else ""))
        self.info.configure(text="\n".join(x for x in lines if x))
        for w in self.checks.winfo_children():
            w.destroy()
        for c, ok, d in qa(r, name):
            if ok is None:
                continue
            row = ttk.Frame(self.checks); row.pack(anchor="w")
            tk.Label(row, text=" pass " if ok else " fail ", bg="#c8ecc9" if ok else "#f6c9c9",
                     fg="#1d5e20" if ok else "#8a1c1c", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
            ttk.Label(row, text="  %-8s %s" % (c, d), wraplength=500).pack(side=tk.LEFT)
        origin = self.ML.origin_of(name, self.lib.get().strip() or None) if self.ML.has_move(name, self.lib.get().strip() or None) else ""
        self.clean_b.configure(state=tk.NORMAL if origin != "starter" else tk.DISABLED)
        self.ret_b.configure(state=tk.NORMAL)
        self.draw()

    # ------------------------------------------------------------ preview
    def toggle(self):
        self.playing = not self.playing
        self.play_b.configure(text="Pause" if self.playing else "Play")

    def _scrubbed(self):
        self.draw()

    def _tick(self):
        self._drain()
        if self.playing and self.motion is not None:
            dur = max(0.2, float((self.rec or {}).get("duration") or 1.0))
            t = self.t.get() + 0.04 * float(self.speed.get() or 1.0) / dur
            if t > 1.0:
                t = t - 1.0                                          # loops wrap; one-shot moves start again
            self.t.set(t)
            self.draw()
        try:
            self.root.after(40, self._tick)
        except tk.TclError:
            pass

    def draw(self):
        cv = self.canvas
        cv.delete("all")
        if self.motion is None:
            cv.create_text(280, 165, text="Pick a move to play it on the mannequin", fill="#778")
            return
        try:
            pts = pose_points(self.motion, float(self.t.get()))
        except Exception as e:                                       # noqa: BLE001
            cv.create_text(280, 165, text="Cannot draw this move: %s" % e, fill="#a33"); return
        W, Hh = 560, 330
        cv.create_line(0, Hh * 0.92, W, Hh * 0.92, fill="#bbc")
        for k, (view, x0) in enumerate((("front", 0), ("side", W // 2))):
            p2 = project(pts, view, (W // 2, Hh))
            cv.create_text(x0 + 10, 12, text=view, anchor="w", fill="#889")
            for b, par in DRAW:
                if b in p2 and par in p2:
                    col = "#c0392b" if "_L" in b else ("#2463b3" if "_R" in b else "#333")
                    (x1, y1), (x2, y2) = p2[par], p2[b]
                    cv.create_line(x0 + x1, y1, x0 + x2, y2, fill=col, width=4, capstyle=tk.ROUND)
            if "head" in p2:
                x, y = p2["head"]
                cv.create_oval(x0 + x - 9, y - 18, x0 + x + 9, y, outline="#333", width=2)
        cv.create_text(W - 8, Hh - 8, anchor="se", fill="#889", text="red = the figure's left, blue = its right   t %.2f" % self.t.get())

    # ------------------------------------------------------------ actions
    def _forge(self):
        return os.path.join(HERE, "forge.py")

    def _run(self, argv, msg, then=None):
        if self._proc is not None:
            self.status.set("Busy - wait for the last action to finish."); return
        self.status.set(msg); self.log.delete("1.0", tk.END)
        lib = self.lib.get().strip()
        full = [sys.executable, "-u", self._forge(), "motion"] + (["--library", lib] if lib else []) + argv
        try:
            self._proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=HERE)
        except OSError as e:
            self.status.set(str(e)); return

        self._then = then
        proc = self._proc

        def pump():
            for line in proc.stdout:
                self._q.put(("line", line))
            self._q.put(("done", proc.wait()))
        threading.Thread(target=pump, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, val = self._q.get_nowait()
                if kind == "line":
                    self.log.insert(tk.END, val); self.log.see(tk.END)
                else:
                    self._done(val, self._then)
        except queue.Empty:
            pass

    def _done(self, code, then):
        self._proc = None
        self.status.set("Done." if code == 0 else "Failed (exit %d) - the log says why." % code)
        if code == 0:
            sel = then or (self.tree.selection() or [None])[0]
            self.reload()
            if sel and self.tree.exists(sel):
                self.tree.selection_set(sel); self.tree.see(sel); self.select(sel)

    def _ask(self, title, prompt, initial=""):
        """a small in-window prompt -> the text, or None"""
        win = tk.Toplevel(self.root); win.title(title); win.transient(self.root)
        ttk.Label(win, text=prompt, wraplength=360).pack(padx=12, pady=(12, 4), anchor="w")
        v = tk.StringVar(value=initial)
        e = ttk.Entry(win, textvariable=v, width=40); e.pack(padx=12, fill=tk.X); e.focus_set()
        out = {}
        bf = ttk.Frame(win); bf.pack(pady=10)
        ttk.Button(bf, text="OK", command=lambda: (out.setdefault("v", v.get()), win.destroy())).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side=tk.LEFT)
        win.bind("<Return>", lambda ev: (out.setdefault("v", v.get()), win.destroy()))
        win.grab_set(); self.root.wait_window(win)
        return out.get("v")

    def import_file(self):
        p = filedialog.askopenfilename(filetypes=[("Motion", "*.bvh *.fbx *.glb *.gltf *.json"), ("All", "*.*")])
        if not p:
            return
        base = os.path.splitext(os.path.basename(p))[0].lower().replace(" ", "_")
        name = self._ask("Import a move", "Name for the move in your library (what game packs ask for, e.g. 'jab', 'kick_pass'):", base)
        if not name:
            return
        lic = self._ask("Licence", "Its licence as an SPDX id (CC0-1.0, CC-BY-4.0...), or leave blank if you are unsure:", "")
        argv = ["import", p, "--name", name] + (["--spdx", lic] if lic else [])
        self._run(argv, "Importing %s as %s..." % (os.path.basename(p), name), then=name)

    def record(self):
        p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm"), ("All", "*.*")])
        if not p:
            return
        base = os.path.splitext(os.path.basename(p))[0].lower().replace(" ", "_")
        name = self._ask("Record a move", "Name for the move (e.g. 'header', 'hand_pass'):", base)
        if not name:
            return
        self._run(["record", "--clip", "%s=%s" % (name, p), "--name", name], "Recording %s from the video..." % name, then=name)

    def clean(self):
        sel = (self.tree.selection() or [None])[0]
        if sel:
            self._run(["clean", sel], "Cleaning %s (foot plant, weight shift, anticipation, follow-through)..." % sel, then=sel)

    def retarget(self):
        sel = (self.tree.selection() or [None])[0]
        if not sel:
            return
        p = filedialog.askopenfilename(filetypes=[("Rig", "*.glb *.fbx"), ("All", "*.*")])
        if not p:
            return
        out = os.path.splitext(p)[0] + "_" + sel + os.path.splitext(p)[1]
        self._run(["retarget", sel, "--to", p, "--out", out], "Retargeting %s onto %s -> %s" % (sel, os.path.basename(p), os.path.basename(out)))
