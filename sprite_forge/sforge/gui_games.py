"""Sprite Forge Studio - Games tab (v11.19): one page per kind of game you build characters for.

Every game-type pack in game_packs/ (soccer, Gaelic, basketball, tennis, boxing, fighting, wrestling, beat 'em up,
platformer, shooter, kart, top-down RPG - and any JSON you add) gets its own page:

  * what the game needs: camera, frame size, props, notes;
  * its move list, each move with the clip it will play (your own, the starter's, or a stand-in borrowed from another
    move or made procedurally), where that clip came from, its licence, frames and timing, the game events on it
    (ball contact, hit window, footsteps...) and the motion checks;
  * any move plays on the mannequin, side-on or front-on, with its events marked on the timeline;
  * the character: the mannequin (body sliders), a library rig, or your own captured GLB / FBX - and the settings
    this kind of game has: a fighter's or a player's type (timing, stance, reach, weight), a team kit;
  * Build: `forge.py build --game PACK ...` in the background with the log streamed, then the sheet preview and the
    sprite QA (clipping, feet drift, pops, loop seams...) per move;
  * Shot list: what to film to replace the stand-ins with your own moves.
v11.23:
  * the preview can show the built character's own sprites (the mannequin, a rig or your capture) instead of the figure;
  * Build the team / the fighter cast: `forge.py roster` - two sides for team sports, a cast for fighting games - with
    a portrait per player and a select screen;
  * Export project: `forge.py engine` - Godot, Unity, Unreal, raylib, web or pygame, ready to open, for the last
    build or roster.
"""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# which character types and kits make sense for each kind of game
FIGHTER_TYPES = ["balanced", "quick_striker", "heavy_brawler", "small_agile", "big_boss"]
PLAYER_TYPES = ["balanced", "playmaker", "keeper"]
GENERAL_TYPES = ["balanced", "small_agile", "big_boss"]
KITS = ["home", "away", "blue", "red", "black", "gk"]
STYLE = {
    "soccer": ("players", True), "gaelic": ("players", True), "basketball": ("players", True), "tennis": ("players", False),
    "boxing": ("fighters", False), "fighting": ("fighters", False), "wrestling": ("fighters", False),
    "beat_em_up": ("fighters", False),
}
EVENT_LABEL = {"ball_contact": "ball contact", "hit_start": "hit starts", "hit_end": "hit ends", "throw_release": "release",
               "shoot": "shot", "reload": "reload", "footsteps": "footstep"}


def types_for(pack_name):
    kind = STYLE.get(pack_name, ("general", False))[0]
    return {"fighters": FIGHTER_TYPES, "players": PLAYER_TYPES}.get(kind, GENERAL_TYPES)


def has_kits(pack_name):
    return STYLE.get(pack_name, ("", False))[1]


def game_rows(pack, library=None):
    """the move table of a pack -> [dict(move, plays, status, origin, licence, frames, fps, loop, events, category, record)]

    status: "own" - a clip made for this move; "shared" - another move's clip stands in (header plays jump);
    "procedural" - no clip at all, the procedural motion of that name is drawn"""
    from . import gamepack as GP, motionlib as ML
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import check_motion as CM
    p = GP.load(pack)
    clips = {m: (path, rec) for m, path, rec in CM.pack_clips(pack, library)}
    rows = []
    for m in p["moves"]:
        name = m["name"]
        path, rec = clips.get(name, (None, None))
        if path is None:
            plays, status, origin = "-", "missing", ""
        elif str(path).startswith("procedural:"):
            plays, status, origin = path.split(":", 1)[1], "procedural", "procedural"
        else:
            plays = os.path.splitext(os.path.basename(path))[0]
            own = plays == name or plays in (m.get("prefer") or []) or plays.startswith(name + "_") or name in plays
            status = "own" if own else "shared"
            try:
                origin = ML.origin_of(plays, library or None)
            except Exception:                                              # noqa: BLE001
                origin = (rec or {}).get("origin", "")
        lic = (rec or {}).get("licence") or {}
        ev = {k: v for k, v in (m.get("events") or {}).items() if v not in (-1, [], None)}
        rows.append(dict(move=name, plays=plays, status=status, origin=origin,
                         licence=(lic.get("spdx") if isinstance(lic, dict) else str(lic)) or ("CC0-1.0" if origin == "procedural" else ""),
                         frames=int(m.get("frames", 8)), fps=int(m.get("fps", 12)), loop=bool(m.get("loop")), events=ev,
                         category=m.get("category") or "", record=rec, path=path))
    return p, rows


def event_marks(row):
    """[(t 0..1, label)] of a move's events, for the preview's timeline"""
    n = max(2, row["frames"])
    out = []
    for k, v in row["events"].items():
        for f in (v if isinstance(v, list) else [v]):
            if isinstance(f, (int, float)) and f >= 0:
                out.append((min(1.0, f / float(n - 1)), EVENT_LABEL.get(k, k)))
    return sorted(out)


def build_argv(pack, out, source="mannequin", rig="", human="", ctype="balanced", kit="", glb=True, library="", hd=False):
    """the `forge.py build` command line for one game's character (hd: sprites at twice the game's frame size)"""
    a = ["build", "--game", pack, "--out", out]
    if hd:
        from .roster import hd_frame
        a += ["--frame", hd_frame(pack)]
    if source == "rig" and rig:
        a += ["--rig", rig]
    else:
        a.append("--mannequin")
        if human:
            a += ["--human", human]
    if ctype and ctype != "balanced":
        a += ["--character-type", ctype]
    if kit:
        a += ["--kit", kit]
    if library:
        a += ["--motion-library", library]
    if not glb:
        a.append("--no-glb")
    return a


def read_qa(folder):
    """a build folder's qa.json -> (score, {move: (status, first issue)})"""
    p = os.path.join(folder, "qa.json")
    if not os.path.isfile(p):
        return None, {}
    q = json.load(open(p))
    per = {}
    for m, v in (q.get("moves") or {}).items():
        iss = [i for i in v.get("issues", []) if i.get("level") in ("FAIL", "WARN")]
        per[m] = (v.get("status", "?"), ("%s, frame %s: %s" % (iss[0]["check"], iss[0].get("frame"), iss[0]["detail"])) if iss else "")
    return q.get("score"), per


def read_sources(folder):
    """a build folder's build_report.txt -> {move: (source, frames, note)}: what the build really drew each move from"""
    p = os.path.join(folder, "build_report.txt")
    out = {}
    if not os.path.isfile(p):
        return out
    on = False
    for line in open(p, encoding="utf-8", errors="replace"):
        if line.startswith("move") and "source" in line:
            on = True; continue
        if on:
            if not line.strip():
                break
            bits = line.split(None, 3)
            if len(bits) >= 3 and bits[2].isdigit():
                out[bits[0]] = (bits[1], int(bits[2]), bits[3].strip() if len(bits) > 3 else "")
    return out


def build_folder(out):
    """the character folder a build wrote under OUT (named after the character: character/, the rig's name...) -
    the newest one with a qa.json, or OUT itself"""
    best, when = None, -1.0
    for d in [out] + ([os.path.join(out, x) for x in os.listdir(out)] if os.path.isdir(out) else []):
        q = os.path.join(d, "qa.json")
        if os.path.isfile(q) and os.path.getmtime(q) > when:
            best, when = d, os.path.getmtime(q)
    return best or out


class GamesTab:
    def __init__(self, app, frame):
        self.app, self.root, self.frame = app, app.root, frame
        from . import gamepack as GP, motionlib as ML
        self.GP, self.ML = GP, ML
        self.packs = GP.list_packs()
        self.lib = tk.StringVar(value=os.environ.get("SFS_MOTIONS") or "")
        self.out = tk.StringVar(value=os.path.join(HERE, "games_out"))
        self.source = tk.StringVar(value="mannequin")
        self.rig = tk.StringVar(value="")
        self.gender = tk.DoubleVar(value=1.0)
        self.muscle = tk.DoubleVar(value=0.5)
        self.weight = tk.DoubleVar(value=0.5)
        self.ctype = tk.StringVar(value="balanced")
        self.kit = tk.StringVar(value="home")
        self.glb = tk.BooleanVar(value=True)
        self.hd = tk.BooleanVar(value=False)            # v11.25: sprites at twice the game's frame size
        self.status = tk.StringVar(value="")
        self.t = tk.DoubleVar(value=0.0)
        self.view = tk.StringVar(value="side")
        self.mode = tk.StringVar(value="figure")
        self.boxes = tk.BooleanVar(value=True)          # v11.24: hit / hurt boxes over the built character         # figure: the move on the mannequin; character: the built sprites
        self.size = tk.IntVar(value=0)
        self.engine = tk.StringVar(value="godot")
        self._strips = {}
        self.pack = None
        self.rows = []
        self.motion = None
        self.row = None
        self._q = queue.Queue()
        self._proc = None
        self._img = None
        self._ui()
        if self.packs:
            self.games.selection_set(0)
            self.choose()
        self.root.after(45, self._tick)

    # ------------------------------------------------------------ layout
    def _ui(self):
        H = ("Segoe UI", 12, "bold")
        outer = ttk.Frame(self.frame); outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        side = ttk.Frame(outer); side.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(side, text="Game", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.games = tk.Listbox(side, width=24, height=20, exportselection=False, font=("Segoe UI", 10))
        for n in self.packs:
            try:
                lab = self.GP.load(n).get("label") or n
            except Exception:                                              # noqa: BLE001
                lab = n
            self.games.insert(tk.END, lab)
        self.games.pack(fill=tk.Y, expand=True, pady=4)
        self.games.bind("<<ListboxSelect>>", lambda e: self.choose())

        main = ttk.Frame(outer); main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self.title = ttk.Label(main, text="", font=H); self.title.pack(anchor="w")
        self.about = ttk.Label(main, text="", wraplength=900, justify=tk.LEFT, foreground="#333"); self.about.pack(anchor="w")
        self.counts = ttk.Label(main, text="", foreground="#555"); self.counts.pack(anchor="w", pady=(2, 4))

        mid = ttk.Frame(main); mid.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(mid); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cols = ("plays", "status", "frames", "events", "check")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings", height=14, selectmode="browse")
        self.tree.heading("#0", text="Move"); self.tree.column("#0", width=120)
        for c, lab, w in (("plays", "Plays", 120), ("status", "Clip", 120), ("frames", "Frames", 70),
                          ("events", "Events", 150), ("check", "Checks", 120)):
            self.tree.heading(c, text=lab); self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("own", foreground="#1d5e20")
        self.tree.tag_configure("shared", foreground="#8a5a00")
        self.tree.tag_configure("procedural", foreground="#8a1c1c")
        self.tree.tag_configure("qa_fail", background="#f7dcdc")
        self.tree.tag_configure("qa_warn", background="#fbf1d6")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick())
        self.detail = ttk.Label(left, text="", wraplength=640, justify=tk.LEFT); self.detail.pack(anchor="w", pady=4)

        pv = ttk.Frame(mid); pv.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        self.canvas = tk.Canvas(pv, width=300, height=330, bg="#f6f7f9", highlightthickness=1, highlightbackground="#ccd")
        self.canvas.pack()
        vr = ttk.Frame(pv); vr.pack(fill=tk.X)
        for v in ("side", "front"):
            ttk.Radiobutton(vr, text=v, value=v, variable=self.view, command=self.draw).pack(side=tk.LEFT)
        mr = ttk.Frame(pv); mr.pack(fill=tk.X)
        ttk.Label(mr, text="Show").pack(side=tk.LEFT)
        ttk.Radiobutton(mr, text="figure", value="figure", variable=self.mode, command=self.draw).pack(side=tk.LEFT)
        ttk.Radiobutton(mr, text="built character", value="character", variable=self.mode, command=self.draw).pack(side=tk.LEFT)
        ttk.Checkbutton(mr, text="hit boxes", variable=self.boxes, command=self.draw).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Scale(vr, from_=0.0, to=1.0, variable=self.t, command=lambda v: self.draw(), length=160).pack(side=tk.LEFT, padx=4)

        # character + build
        cb = ttk.LabelFrame(main, text="Character and build"); cb.pack(fill=tk.X, pady=(6, 0))
        r1 = ttk.Frame(cb); r1.pack(fill=tk.X, padx=6, pady=3)
        ttk.Radiobutton(r1, text="Mannequin", value="mannequin", variable=self.source).pack(side=tk.LEFT)
        for lab, var in (("female - male", self.gender), ("muscle", self.muscle), ("weight", self.weight)):
            ttk.Label(r1, text=lab).pack(side=tk.LEFT, padx=(8, 2))
            ttk.Scale(r1, from_=0.0, to=1.0, variable=var, length=80).pack(side=tk.LEFT)
        ttk.Radiobutton(r1, text="Rig or capture", value="rig", variable=self.source).pack(side=tk.LEFT, padx=(16, 2))
        self.rig_box = ttk.Combobox(r1, textvariable=self.rig, width=26, values=self._rigs()); self.rig_box.pack(side=tk.LEFT)
        ttk.Button(r1, text="...", width=3, command=self._browse_rig).pack(side=tk.LEFT, padx=2)
        r2 = ttk.Frame(cb); r2.pack(fill=tk.X, padx=6, pady=3)
        self.type_lab = ttk.Label(r2, text="Type"); self.type_lab.pack(side=tk.LEFT)
        self.type_box = ttk.Combobox(r2, textvariable=self.ctype, width=14, state="readonly"); self.type_box.pack(side=tk.LEFT, padx=4)
        self.kit_lab = ttk.Label(r2, text="Kit"); self.kit_lab.pack(side=tk.LEFT, padx=(10, 0))
        self.kit_box = ttk.Combobox(r2, textvariable=self.kit, values=KITS, width=8, state="readonly"); self.kit_box.pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(r2, text="3D GLB too", variable=self.glb).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(r2, text="HD sprites (2x)", variable=self.hd).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(r2, text="Motions").pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.lib, width=24).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="...", width=3, command=self._browse_lib).pack(side=tk.LEFT)
        ttk.Label(r2, text="Out").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Entry(r2, textvariable=self.out, width=24).pack(side=tk.LEFT, padx=2)
        r3 = ttk.Frame(cb); r3.pack(fill=tk.X, padx=6, pady=3)
        self.build_b = ttk.Button(r3, text="Build this game's character", command=self.build); self.build_b.pack(side=tk.LEFT)
        ttk.Button(r3, text="Shot list", command=self.shotlist).pack(side=tk.LEFT, padx=4)
        ttk.Label(r3, textvariable=self.status, foreground="#333", wraplength=640).pack(side=tk.LEFT, padx=8)
        r4 = ttk.Frame(cb); r4.pack(fill=tk.X, padx=6, pady=3)
        self.size_lab = ttk.Label(r4, text="Team size"); self.size_lab.pack(side=tk.LEFT)
        ttk.Spinbox(r4, from_=0, to=11, textvariable=self.size, width=4).pack(side=tk.LEFT, padx=4)
        self.roster_b = ttk.Button(r4, text="Build the team", command=self.roster); self.roster_b.pack(side=tk.LEFT)
        ttk.Label(r4, text="  Engine").pack(side=tk.LEFT, padx=(16, 2))
        from .engines import ENGINES
        ttk.Combobox(r4, textvariable=self.engine, values=ENGINES + ["all"], width=9, state="readonly").pack(side=tk.LEFT)
        ttk.Button(r4, text="Export project", command=self.export).pack(side=tk.LEFT, padx=4)
        ttk.Button(r4, text="Open folder", command=self.open_folder).pack(side=tk.LEFT, padx=4)

        res = ttk.Frame(main); res.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.sheet = ttk.Label(res); self.sheet.pack(side=tk.LEFT, anchor="n")
        self.log = tk.Text(res, width=60, height=8, wrap="word", font=("Consolas", 9)); self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

    def _rigs(self):
        try:
            from . import library as L
            return L.Library().names("rigs")
        except Exception:                                                  # noqa: BLE001
            return []

    def _browse_rig(self):
        p = filedialog.askopenfilename(filetypes=[("Character", "*.glb *.gltf *.fbx"), ("All", "*.*")])
        if p:
            self.rig.set(p); self.source.set("rig")

    def _browse_lib(self):
        p = filedialog.askdirectory()
        if p:
            self.lib.set(p); self.choose()

    # ------------------------------------------------------------ game page
    def choose(self):
        s = self.games.curselection()
        if not s:
            return
        name = self.packs[s[0]]
        try:
            self.pack, self.rows = game_rows(name, self.lib.get().strip() or None)
        except Exception as e:                                             # noqa: BLE001
            self.status.set("Could not read the %s pack: %s" % (name, e)); return
        p = self.pack
        self.title.configure(text=p.get("label") or name)
        props = ", ".join(p.get("props") or []) or "none"
        self.about.configure(text="%s\nCamera: %s   Frame: %s px   Props the game draws: %s%s" % (
            p.get("description", ""), p.get("camera", ""), "x".join(str(v) for v in p.get("frame") or []), props,
            ("\n" + p["notes"]) if p.get("notes") else ""))
        n = len(self.rows)
        own = sum(r["status"] == "own" for r in self.rows)
        shared = sum(r["status"] == "shared" for r in self.rows)
        proc = sum(r["status"] == "procedural" for r in self.rows)
        self.counts.configure(text="%d moves: %d with their own clip, %d borrowing another move's, %d procedural%s" % (
            n, own, shared, proc, "  -  the Shot list says what to film for the rest" if shared + proc else ""))
        self.type_box.configure(values=types_for(name))
        if self.ctype.get() not in types_for(name):
            self.ctype.set("balanced")
        self.type_lab.configure(text={"fighters": "Fighter type", "players": "Player type"}.get(STYLE.get(name, ("",))[0], "Type"))
        kit = has_kits(name)
        self.kit_box.configure(state="readonly" if kit else tk.DISABLED)
        self.kit_lab.configure(foreground="#000" if kit else "#999")
        self.view.set("front" if p.get("camera") == "topdown8" else "side")
        from .roster import TEAM_GAMES, FIGHT_GAMES
        team = name in TEAM_GAMES
        self.size_lab.configure(text="Players per side" if team else ("Fighters" if name in FIGHT_GAMES else "Characters"))
        self.roster_b.configure(text="Build both teams" if team else ("Build the fighter cast" if name in FIGHT_GAMES else "Build the cast"))
        self._fill()
        self._show_build(name)
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0]); self.pick()

    def _fill(self, qa=None):
        self.tree.delete(*self.tree.get_children())
        lab = {"own": "own clip", "shared": "borrowed", "procedural": "procedural", "missing": "missing"}
        for r in self.rows:
            ev = ", ".join("%s %s" % (EVENT_LABEL.get(k, k), ",".join(map(str, v)) if isinstance(v, list) else v)
                           for k, v in r["events"].items())
            chk = ""
            if qa and r["move"] in qa:
                chk = qa[r["move"]][0].lower()
            tags = (r["status"],) + (("qa_" + chk,) if chk in ("fail", "warn") else ())
            self.tree.insert("", tk.END, iid=r["move"], text=r["move"], tags=tags,
                             values=(r["plays"], lab.get(r["status"], r["status"]),
                                     "%d @ %d fps%s" % (r["frames"], r["fps"], ", loop" if r["loop"] else ""), ev or "-", chk or "-"))

    def pick(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = next(x for x in self.rows if x["move"] == sel[0])
        self.row = r
        try:
            if r["status"] == "procedural":
                from .motions import find_motion
                self.motion = find_motion(r["plays"])
            else:
                self.motion = self.ML.as_motion(r["plays"], self.lib.get().strip() or None)
        except Exception as e:                                             # noqa: BLE001
            self.motion = None
            self.detail.configure(text="Cannot play %s: %s" % (r["plays"], e)); return
        say = {"own": "plays its own clip", "shared": "borrows the %s clip - film or import a %s to replace it" % (r["plays"], r["move"]),
               "procedural": "has no clip: the procedural %s motion is drawn" % r["plays"]}.get(r["status"], "")
        lines = ["%s %s (%s)." % (r["move"], say, r["origin"] or "-")]
        if r["licence"]:
            lines.append("Licence: %s" % r["licence"])
        src = getattr(self, "_src", {})
        if r["move"] in src:
            s, n, note = src[r["move"]]
            lines.append("Last build drew it from %s, %d frames%s" % (s, n, (" - " + note) if note else ""))
        qa = getattr(self, "_qa", {})
        if r["move"] in qa and qa[r["move"]][1]:
            lines.append("Sprite QA: %s - %s" % qa[r["move"]])
        self.detail.configure(text="\n".join(lines))
        self.t.set(0.0)
        self.draw()

    # ------------------------------------------------------------ preview
    def _tick(self):
        self._drain()
        if self.motion is not None and self.row is not None:
            dur = max(0.25, self.row["frames"] / float(max(1, self.row["fps"])))
            t = self.t.get() + 0.045 / dur
            self.t.set(t - 1.0 if t > 1.0 else t)
            self.draw()
        try:
            self.root.after(45, self._tick)
        except tk.TclError:
            pass

    def draw(self):
        from .gui_motion import pose_points, project, DRAW
        cv = self.canvas; cv.delete("all")
        W, Hh = 300, 330
        if self.motion is None:
            cv.create_text(W / 2, Hh / 2, text="Pick a move", fill="#778"); return
        t = float(self.t.get())
        if self.mode.get() == "character":
            if self._draw_sprite(cv, W, Hh, t):
                self._timeline(cv, W, Hh, t)
                return
            cv.create_text(W / 2, 40, text="Build this game's character first -\nthe figure is shown until then", fill="#a33")
        try:
            pts = pose_points(self.motion, t)
        except Exception as e:                                             # noqa: BLE001
            cv.create_text(W / 2, Hh / 2, text=str(e), fill="#a33", width=260); return
        floor = Hh * 0.86
        cv.create_line(0, floor, W, floor, fill="#bbc")
        p2 = project(pts, self.view.get(), (W, Hh * 0.94))
        for b, par in DRAW:
            if b in p2 and par in p2:
                col = "#c0392b" if "_L" in b else ("#2463b3" if "_R" in b else "#333")
                (x1, y1), (x2, y2) = p2[par], p2[b]
                cv.create_line(x1, y1, x2, y2, fill=col, width=4, capstyle=tk.ROUND)
        if "head" in p2:
            x, y = p2["head"]; cv.create_oval(x - 9, y - 18, x + 9, y, outline="#333", width=2)
        self._timeline(cv, W, Hh, t)

    def _strip(self, move):
        """the last build's strip of a move -> (PIL image, frame w, h, frames) or None"""
        s = self.games.curselection()
        if not s:
            return None
        folder = build_folder(self._outdir(self.packs[s[0]]))
        p = os.path.join(folder, "strips", move + ".png")
        if not os.path.isfile(p):
            return None
        key = (p, os.path.getmtime(p))
        if key not in self._strips:
            from PIL import Image
            im = Image.open(p).convert("RGBA")
            n = max(1, self.row["frames"])
            src = read_sources(folder).get(move)
            if src:
                n = src[1]
            self._strips = {key: (im, im.width // n, im.height, n)}
        return self._strips[key]

    def _draw_sprite(self, cv, W, Hh, t):
        st = self._strip(self.row["move"])
        if st is None:
            return False
        from PIL import Image, ImageTk
        im, fw, fh, n = st
        f = min(n - 1, int(t * n)) if not self.row["loop"] else int(t * n) % n
        cell = im.crop((f * fw, 0, (f + 1) * fw, fh))
        k = min((W - 20) / float(fw), (Hh - 40) / float(fh))
        cell = cell.resize((max(1, int(fw * k)), max(1, int(fh * k))), Image.NEAREST)
        bg = Image.new("RGBA", cell.size, (246, 247, 249, 255)); bg.alpha_composite(cell)
        self._spr = ImageTk.PhotoImage(bg)
        cx, cy = W / 2, (Hh - 30) / 2 + 4
        cv.create_image(cx, cy, image=self._spr)
        self._frame_now = f
        if self.boxes.get():
            x0, y0 = cx - cell.size[0] / 2.0, cy - cell.size[1] / 2.0
            self._draw_boxes(cv, self.row["move"], f, x0, y0, cell.size[0] / float(fw))
        return True

    def anim_record(self, move):
        """the last build's game_character.json record of a move (pivot, hitboxes, hurtboxes...) or None"""
        s = self.games.curselection()
        if not s:
            return None
        p = os.path.join(build_folder(self._outdir(self.packs[s[0]])), "game_character.json")
        if not os.path.isfile(p):
            return None
        key = (p, os.path.getmtime(p))
        if getattr(self, "_man_key", None) != key:
            self._man_key, self._man = key, {a["name"]: a for a in json.load(open(p)).get("animations", [])}
        return self._man.get(move)

    def _draw_boxes(self, cv, move, f, x0, y0, k):
        """hurt boxes (blue: head / body / legs), hit boxes (red, the frames a strike can land) and the pivot (feet)"""
        a = self.anim_record(move)
        self._boxes_drawn = (0, 0)
        if a is None:
            return
        hurt = [h for h in a.get("hurtboxes", []) if h.get("frame") == f]
        hit = [h for h in a.get("hitboxes", []) if h.get("frame") == f]
        for h in hurt:
            bx, by, bw, bh = h["box"]
            cv.create_rectangle(x0 + bx * k, y0 + by * k, x0 + (bx + bw) * k, y0 + (by + bh) * k, outline="#2463b3", width=2,
                                tags=("hurtbox",))
        for h in hit:
            bx, by, bw, bh = h["box"]
            cv.create_rectangle(x0 + bx * k, y0 + by * k, x0 + (bx + bw) * k, y0 + (by + bh) * k, outline="#c0392b", width=3,
                                fill="#c0392b", stipple="gray25", tags=("hitbox",))
        pv = a.get("pivot") or {}
        if pv:
            px, py = x0 + pv.get("x", 0) * k, y0 + pv.get("y", 0) * k
            cv.create_line(px - 8, py, px + 8, py, fill="#1d5e20", width=2, tags=("pivot",))
            cv.create_line(px, py - 8, px, py + 2, fill="#1d5e20", width=2, tags=("pivot",))
        if hit:
            cv.create_text(x0 + (a.get("w") or 128) * k - 4, y0 + 22, anchor="ne", text="HIT", fill="#c0392b",
                           font=("Segoe UI", 10, "bold"), tags=("hitlabel",))
        self._boxes_drawn = (len(hurt), len(hit))

    def _timeline(self, cv, W, Hh, t):
        # the timeline, with the move's events
        y0 = Hh - 16
        cv.create_line(10, y0, W - 10, y0, fill="#99a", width=2)
        now = None
        for te, lab in event_marks(self.row):
            x = 10 + te * (W - 20)
            cv.create_line(x, y0 - 6, x, y0 + 6, fill="#d35400", width=2)
            if abs(te - t) < 0.06:
                now = lab
        x = 10 + t * (W - 20)
        cv.create_oval(x - 4, y0 - 4, x + 4, y0 + 4, fill="#333")
        cv.create_text(8, 10, anchor="w", text="%s - %s" % (self.row["move"], self.view.get() if self.mode.get() == "figure" else "built character"), fill="#556")
        if now:
            cv.create_text(W - 8, 10, anchor="e", text=now, fill="#d35400", font=("Segoe UI", 10, "bold"))

    # ------------------------------------------------------------ build
    def _human(self):
        return "gender=%.2f,muscle=%.2f,weight=%.2f" % (self.gender.get(), self.muscle.get(), self.weight.get())

    def _outdir(self, name):
        return os.path.join(self.out.get().strip() or os.path.join(HERE, "games_out"), name)

    def argv(self):
        s = self.games.curselection()
        name = self.packs[s[0]] if s else "soccer"
        return name, build_argv(name, self._outdir(name), source=self.source.get(), rig=self.rig.get().strip(),
                                human=self._human(), ctype=self.ctype.get(),
                                kit=self.kit.get() if has_kits(name) else "", glb=self.glb.get(), library=self.lib.get().strip(),
                                hd=self.hd.get())

    def build(self):
        name, a = self.argv()
        if self.source.get() == "rig" and not self.rig.get().strip():
            self.status.set("Choose a rig from the list or a GLB / FBX file, or pick Mannequin."); return
        self._run(a, "Building the %s character (about 20 s, longer with GLB)..." % name, then=("built", name))

    def _roster_dir(self, name):
        return os.path.join(self.out.get().strip() or os.path.join(HERE, "games_out"), "rosters", name)

    def roster(self):
        name, _ = self.argv()
        a = ["roster", "--game", name, "--out", os.path.dirname(self._roster_dir(name))]
        if self.size.get() > 0:
            a += ["--size", str(int(self.size.get()))]
        if self.lib.get().strip():
            a += ["--motion-library", self.lib.get().strip()]
        if not self.glb.get():
            a.append("--no-glb")
        if self.hd.get():
            a.append("--hd")
        self._run(a, "Building the %s roster - a few seconds per player..." % name, then=("roster", name))

    def export_source(self, name):
        """what Export sends: the roster when it is newer than the single build, else the build"""
        r = os.path.join(self._roster_dir(name), "roster.json")
        b = build_folder(self._outdir(name))
        bj = os.path.join(b, "game_character.json")
        if os.path.isfile(r) and (not os.path.isfile(bj) or os.path.getmtime(r) >= os.path.getmtime(bj)):
            return os.path.dirname(r)
        return b if os.path.isfile(bj) else None

    def export(self):
        name, _ = self.argv()
        src = self.export_source(name)
        if src is None:
            self.status.set("Build the character or the team first, then export it."); return
        dst = os.path.join(self.out.get().strip() or os.path.join(HERE, "games_out"), "engines", name)
        if self.engine.get() != "all":
            dst = os.path.join(dst, self.engine.get())
        self._last_export = dst
        self._run(["engine", self.engine.get(), src, "--out", dst], "Making the %s project from %s..." % (self.engine.get(), src),
                  then=("export", name))

    def open_folder(self):
        name, _ = self.argv()
        d = getattr(self, "_last_export", None) or self.export_source(name) or self._outdir(name)
        if not os.path.isdir(d):
            self.status.set("Nothing built yet for %s." % name); return
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)                                            # noqa: S606
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
        except OSError:
            pass
        self.status.set(d)

    def shotlist(self):
        name, _ = self.argv()
        self._run(["game", "shotlist", name], "The %s shot list:" % name, then=("shot", name))

    def _run(self, argv, msg, then=None):
        if self._proc is not None:
            self.status.set("Busy - wait for the last one to finish."); return
        self.status.set(msg); self.log.delete("1.0", tk.END)
        self.build_b.configure(state=tk.DISABLED)
        self._then = then
        try:
            self._proc = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "forge.py")] + argv, cwd=HERE,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as e:
            self.status.set(str(e)); self._proc = None; self.build_b.configure(state=tk.NORMAL); return
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
                    self._proc = None
                    self.build_b.configure(state=tk.NORMAL)
                    what, name = self._then or ("", "")
                    if val != 0:
                        self.status.set("Failed (exit %d) - the log says why." % val)
                    elif what == "built":
                        self.status.set("Built -> %s" % build_folder(self._outdir(name)))
                        self._show_build(name)
                    elif what == "roster":
                        self._show_roster(name)
                    elif what == "export":
                        self.status.set("Engine project ready -> %s (its README says how to open it)" % self._last_export)
                    else:
                        self.status.set("")
                        self.log.see("1.0")
        except queue.Empty:
            pass

    def _show_roster(self, name):
        d = self._roster_dir(name)
        p = os.path.join(d, "select_screen.png")
        try:
            r = json.load(open(os.path.join(d, "roster.json")))
        except (OSError, ValueError):
            self.status.set("The roster did not finish - the log says why."); return
        fails = [x["name"] for x in r["players"] if x.get("qa_fail")]
        self.status.set("%d players -> %s%s" % (len(r["players"]), d, ("  (sprite QA fails in " + ", ".join(fails) + ")") if fails else ""))
        if os.path.isfile(p):
            from PIL import Image, ImageTk
            im = Image.open(p); im.thumbnail((620, 220))
            self._img = ImageTk.PhotoImage(im)
            self.sheet.configure(image=self._img)

    def _show_build(self, name):
        folder = build_folder(self._outdir(name))
        score, self._qa = read_qa(folder)
        self._src = read_sources(folder)
        if self._qa:
            self._fill(self._qa)
            fails = [m for m, (st, _) in self._qa.items() if st == "FAIL"]
            self.status.set("Last build: QA score %s%s" % (score, (" - fails in " + ", ".join(fails)) if fails else " - all moves pass"))
        prev = os.path.join(folder, "preview.png")
        if os.path.isfile(prev):
            from PIL import Image, ImageTk
            im = Image.open(prev); im.thumbnail((560, 200))
            self._img = ImageTk.PhotoImage(im)
            self.sheet.configure(image=self._img)
        else:
            self.sheet.configure(image="")
