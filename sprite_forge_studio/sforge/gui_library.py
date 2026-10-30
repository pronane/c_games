"""Library tab of the Studio: your FBX / GLB rigs, animations and kits as templates; .sfpack export / install with licences."""
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext

from PIL import Image, ImageTk

from . import library as L

REDIST_CHOICES = ["yes", "no", "unknown"]


class LibraryTab:
    def __init__(self, studio, tab):
        self.s = studio; self.root = studio.root; self.tab = tab
        self.lib = L.Library()
        self.thumbs = {}; self.big = None; self.cur = None; self.cur_rig = None
        self.play_job = None; self.t = tk.DoubleVar(value=0.0); self.clip = tk.StringVar()
        self.dlg = None                       # last dialog (autotest / screenshots)
        self._ui()
        self.refresh()

    # ------------------------------------------------------------ layout
    def _ui(self):
        top = ttk.Frame(self.tab); top.pack(fill=tk.X, padx=6, pady=(6, 2))
        ttk.Label(top, text="Library", style="H.TLabel").pack(side=tk.LEFT)
        self.dir_lbl = ttk.Label(top, text="", foreground="#555"); self.dir_lbl.pack(side=tk.LEFT, padx=8)
        for txt, cmd in (("Add FBX / GLB...", self.add_file), ("Remove", self.remove), ("Rescan (import inbox/)", self.rescan),
                         ("Install pack...", self.install_pack), ("Export pack...", self.export_pack)):
            ttk.Button(top, text=txt, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Help", command=lambda: self.s.show_help("library")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Licensing", command=lambda: self.s.show_help("licensing")).pack(side=tk.LEFT, padx=2)
        main = ttk.Frame(self.tab); main.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        lf = ttk.Frame(main); lf.pack(side=tk.LEFT, fill=tk.Y)
        st = ttk.Style(); st.configure("Lib.Treeview", rowheight=52)
        cols = ("kind", "bones", "clips", "licence", "redist")
        self.tree = ttk.Treeview(lf, columns=cols, show="tree headings", height=13, style="Lib.Treeview", selectmode="extended")
        self.tree.heading("#0", text="asset"); self.tree.column("#0", width=230)
        for c, w in zip(cols, (80, 55, 50, 110, 80)):
            self.tree.heading(c, text={"redist": "redistribute"}.get(c, c)); self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.Y); sb.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        ttk.Separator(main, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        rf = ttk.Frame(main); rf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        a = ttk.Frame(rf); a.pack(fill=tk.X)
        self.img = ttk.Label(a); self.img.pack(side=tk.LEFT, anchor="n")
        info = ttk.Frame(a); info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        self.info = scrolledtext.ScrolledText(info, height=17, width=62, font="TkFixedFont", wrap=tk.WORD); self.info.pack(fill=tk.BOTH, expand=True)
        cp = ttk.Frame(rf); cp.pack(fill=tk.X, pady=4)
        ttk.Label(cp, text="Clip").pack(side=tk.LEFT)
        self.clip_cb = ttk.Combobox(cp, textvariable=self.clip, width=22, state="readonly"); self.clip_cb.pack(side=tk.LEFT, padx=3)
        self.clip_cb.bind("<<ComboboxSelected>>", lambda e: (self.t.set(0.0), self.draw()))
        self.play_btn = ttk.Button(cp, text="Play", width=6, command=self.toggle_play); self.play_btn.pack(side=tk.LEFT)
        self.scrub = ttk.Scale(cp, from_=0.0, to=1.0, variable=self.t, orient=tk.HORIZONTAL, length=260, command=lambda e: self.draw())
        self.scrub.pack(side=tk.LEFT, padx=6)
        self.t_lbl = ttk.Label(cp, text="", width=16); self.t_lbl.pack(side=tk.LEFT)
        bp = ttk.Frame(rf); bp.pack(fill=tk.X, pady=2)
        ttk.Button(bp, text="Use as template (Build tab)", command=self.use_template).pack(side=tk.LEFT)
        ttk.Button(bp, text="Use this clip for a move...", command=self.use_clip).pack(side=tk.LEFT, padx=3)
        ttk.Button(bp, text="Bone map...", command=self.bonemap_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(bp, text="Licence...", command=self.licence_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(bp, text="Export GLB / FBX...", command=self.export_model).pack(side=tk.LEFT, padx=3)
        self.msg = ttk.Label(rf, text="", foreground="#26a269", wraplength=760, justify=tk.LEFT); self.msg.pack(anchor="w", pady=4)

    def say(self, s, err=False):
        self.msg.configure(text=s, foreground="#c01c28" if err else "#26a269"); self.s._log(s)

    # ------------------------------------------------------------ list
    def refresh(self, select=None):
        self.lib = L.Library()
        self.dir_lbl.configure(text=self.lib.dir)
        self.tree.delete(*self.tree.get_children()); self.thumbs = {}
        try:
            man = self.lib.scan(import_inbox=False, log=lambda s: None)[0]
        except Exception as e:
            self.say("library scan failed: %s" % e, True); return
        for e in man.get("assets", []):
            iid = "%s/%s" % (e["kind"], e["name"])
            img = ""
            tp = os.path.join(self.lib.dir, e.get("thumb", "")) if e.get("thumb") else ""
            try:
                if tp and os.path.exists(tp):
                    im = Image.open(tp).convert("RGBA"); im.thumbnail((48, 48))
                elif e["kind"] == "kits":
                    im = self._kit_swatch(e["name"], 48)
                else:
                    im = None
                if im is not None:
                    self.thumbs[iid] = ImageTk.PhotoImage(im); img = self.thumbs[iid]
            except Exception:
                pass
            lic = e.get("licence", {})
            self.tree.insert("", tk.END, iid=iid, text=" " + e["name"], image=img,
                             values=(e["kind"][:-1], e.get("bones", "-"), len(e.get("clips", [])) if e["kind"] != "kits" else "-",
                                     (lic.get("spdx") or "?") + ("" if e.get("licence_ok") else " (incomplete)"),
                                     ("owner-confirmed" if lic.get("owner_confirmed") and lic.get("redistributable") else
                                      "no (includes)" if lic.get("redistribution") == "yes" and lic.get("redistributable") is False else
                                      lic.get("redistribution") or "unknown")))
        kids = self.tree.get_children()
        if select and select in kids:
            self.tree.selection_set(select); self.tree.see(select)
        elif kids and not self.tree.selection():
            self.tree.selection_set(kids[0])
        self.s.refresh_library_choices()

    def _kit_swatch(self, name, n):
        from . import kits as K
        kit = K.load(name, self.lib.dir) or {}
        cols = [K.parse_color(v.get("color") if isinstance(v, dict) else v) for v in kit.get("materials", {}).values()][:4] or [(128, 128, 128)]
        im = Image.new("RGBA", (n, n), (236, 239, 244, 255))
        w = n // len(cols)
        for i, c in enumerate(cols):
            c = [x * 255 for x in c[:3]] if max(c[:3]) <= 1.0 else c[:3]
            im.paste(tuple(int(x) for x in c) + (255,), (i * w, 4, (i + 1) * w, n - 4))
        return im

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def select(self):
        iid = self.selected()
        if not iid:
            return
        self.stop()
        self.cur = iid; k, n = iid.split("/", 1)
        self.info.delete("1.0", tk.END)
        if k == "kits":
            import json
            kit = json.load(open(self.lib.path(k, n), encoding="utf-8"))
            self.cur_rig = None; self.clip_cb["values"] = []; self.clip.set("")
            txt = ["kit %s  -  %s" % (n, kit.get("description", "")), "", "materials:"]
            for m, r in kit.get("materials", {}).items():
                txt.append("  %-14s %s" % (m, r))
            txt += ["", L.licence_text(self.lib.licence(iid), iid)]
            self.info.insert(tk.END, "\n".join(txt))
            self._show(self._kit_swatch(n, 220)); return
        try:
            self.cur_rig = self.lib.load_rig(iid); rec = self.lib.bonemap(iid, self.cur_rig)
        except Exception as e:
            self.say("cannot load %s: %s" % (iid, e), True); return
        r = self.cur_rig; e = self.lib.entry(k, n)
        txt = ["%s %s  -  %s" % (k[:-1], n, e.get("description") or ""),
               "bones %d, triangles %s, height %.2f m, bone names: %s" % (r.nb, len(r.F) if r.has_mesh() else 0, r.height(), rec.get("convention")),
               "unmapped bones: %s" % (", ".join(rec.get("unmapped", [])) or "none"),
               "missing canonical bones: %s" % (", ".join(rec.get("missing", [])) or "none"),
               "clips (%d): %s" % (len(r.clips), ", ".join("%s %.2fs" % (c, r.clips[c].duration) for c in r.clips) or "none"),
               "materials: %s" % (", ".join(m.get("name", "?") if isinstance(m, dict) else str(m) for m in r.materials) or "-"), "",
               L.licence_text(self.lib.licence(iid), iid)]
        self.info.insert(tk.END, "\n".join(txt))
        cl = list(r.clips)
        self.clip_cb["values"] = ["(rest pose)"] + cl
        self.clip.set(cl[0] if cl else "(rest pose)"); self.t.set(0.0)
        self.draw()

    def _show(self, im):
        self.big = ImageTk.PhotoImage(im); self.img.configure(image=self.big)

    def draw(self):
        r = self.cur_rig
        if r is None:
            return
        from . import rigrec as RR
        c = self.clip.get()
        if c in r.clips:
            d = r.clips[c].duration; t = float(self.t.get()) * d
            im = RR.thumbnail(r, size=260, clip=c, t=t)
            self.t_lbl.configure(text="%.2f / %.2f s" % (t, d))
        else:
            im = RR.thumbnail(r, size=260); self.t_lbl.configure(text="rest pose")
        if not r.has_mesh():
            from .render import RenderSettings
            W = r.worlds(r.clips[c], t) if c in r.clips else r.bind
            rs = RenderSettings(cell_w=520, cell_h=520, figure_h=int(520 * 0.86 * 1.8 / max(0.3, r.height(W))), baseline=490, anchor_x=260, yaw=35, ss=1)
            sk = RR.render_skeleton(r, W, rs, root_xz=tuple(W[0, [0, 2], 3]))
            bg = Image.new("RGBA", sk.size, (236, 239, 244, 255)); im = Image.alpha_composite(bg, sk).resize((260, 260))
        self._show(im)

    def toggle_play(self):
        if self.play_job:
            self.stop(); return
        self.play_btn.configure(text="Pause"); self._tick()

    def _tick(self):
        r = self.cur_rig; c = self.clip.get()
        if r is None or c not in r.clips:
            self.stop(); return
        d = max(0.1, r.clips[c].duration)
        self.t.set((float(self.t.get()) + (1 / 12.0) / d) % 1.0); self.draw()
        self.play_job = self.root.after(83, self._tick)

    def stop(self):
        if self.play_job:
            self.root.after_cancel(self.play_job); self.play_job = None
        self.play_btn.configure(text="Play")

    # ------------------------------------------------------------ actions
    def use_template(self):
        iid = self.selected()
        if not iid or iid.startswith("kits/"):
            if iid:
                self.s.v["kit"].set(iid.split("/", 1)[1]); self.say("kit %s set on the Build tab" % iid)
            return
        if self.cur_rig is not None and not self.cur_rig.has_mesh():
            self.say("%s has no mesh (animations only): use 'Use this clip for a move...' to drive a rig with it." % iid, True); return
        self.s.v["mode"].set("library"); self.s.v["rig"].set(iid.split("/", 1)[1])
        self.s.nb.select(0); self.s.apply_mode()
        self.say("Build tab: mode 'Library rig', rig = %s. Pick moves / kit / profile / console and press BUILD." % iid)

    def use_clip(self, move=None):
        iid = self.selected(); c = self.clip.get()
        if not iid or self.cur_rig is None or c not in self.cur_rig.clips:
            self.say("select a rig or animation and one of its clips first", True); return
        mv = move or simpledialog.askstring("Use clip", "Which move (row in '3. Moves') should play %s:%s?" % (iid.split('/', 1)[1], c), parent=self.root)
        if not mv:
            return
        ok = self.s.set_move_clip(mv.strip(), "%s:%s" % (iid.split("/", 1)[1], c))
        self.say(("move %s now uses clip %s:%s (Build tab, column 'library clip')" % (mv, iid.split('/', 1)[1], c)) if ok else
                 "no move row named %s on the Build tab - add it there first" % mv, not ok)

    def add_file(self, path=None, name=None, licence=None):
        p = path or filedialog.askopenfilename(title="Rig or animation (your own, or one whose licence you know)",
                                               filetypes=[("3D", "*.fbx *.glb *.gltf"), ("All", "*.*")])
        if not p:
            return
        nm = name or simpledialog.askstring("Name", "Library name for this asset:", initialvalue=L.slug(os.path.splitext(os.path.basename(p))[0]), parent=self.root)
        if not nm:
            return
        try:
            k, n, _rec, rep = self.lib.add_file(p, nm, licence=licence, log=self.s._log)
        except Exception as e:
            self.say("could not import %s: %s" % (p, e), True); return
        self.refresh("%s/%s" % (k, n))
        self.say("added %s/%s (%s). Now fill in its licence (Licence...) - packs refuse assets without one." % (k, n, ", ".join(rep.get("clips", [])) or "no clips"))
        if licence is None and not self.s.autotest:
            self.licence_dialog()

    def remove(self):
        iid = self.selected()
        if not iid:
            return
        if not self.s.autotest and not messagebox.askyesno("Remove", "Remove %s from the library?\n(the original file you imported is not touched)" % iid):
            return
        self.lib.remove(iid); self.refresh(); self.say("removed " + iid)

    def rescan(self):
        try:
            man, _imp = self.lib.scan(import_inbox=True, log=self.s._log)
        except Exception as e:
            self.say("scan: %s" % e, True); return
        self.refresh(); self.say("library.json rebuilt: %d assets (files dropped in %s were imported)" % (len(man["assets"]), os.path.join(self.lib.dir, "inbox")))

    def export_model(self):
        iid = self.selected()
        if not iid or self.cur_rig is None:
            return
        p = filedialog.asksaveasfilename(defaultextension=".glb", filetypes=[("glTF binary", "*.glb"), ("FBX", "*.fbx")])
        if not p:
            return
        from . import rigrec as RR
        import tempfile
        glb = p if p.lower().endswith(".glb") else os.path.join(tempfile.mkdtemp(), "m.glb")
        RR.write_glb(self.cur_rig, glb, list(self.cur_rig.clips), self.s.lib_kit())
        if p.lower().endswith(".fbx"):
            from . import fbx
            fbx.write_fbx_from_glb(glb, p)
        self.say("wrote %s (%d takes)" % (p, len(self.cur_rig.clips)))

    # ------------------------------------------------------------ licence editor
    def licence_dialog(self, auto=None):
        iid = self.selected()
        if not iid:
            return
        lic = dict(L.blank_licence(), **self.lib.licence(iid))
        w = tk.Toplevel(self.root); w.title("Licence of %s" % iid); self.dlg = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 300, self.root.winfo_rooty() + 90))
        f = ttk.Frame(w, padding=10); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Every asset needs a licence record before it can go into a pack.\nYou only know the licence of files you made "
                          "or whose terms you have read (Help > Licensing).", foreground="#555", justify=tk.LEFT).grid(row=0, column=0, columnspan=2, sticky="w")
        fv = {k: tk.StringVar(value=str(lic.get(k) or "")) for k in ("spdx", "author", "source_url", "redistribution", "attribution", "notes")}
        rows = [("SPDX id", ttk.Combobox(f, textvariable=fv["spdx"], values=[""] + list(L.SPDX_COMMON), width=34)),
                ("Author", ttk.Entry(f, textvariable=fv["author"], width=44)),
                ("Source URL", ttk.Entry(f, textvariable=fv["source_url"], width=44)),
                ("Redistribution", ttk.Combobox(f, textvariable=fv["redistribution"], values=REDIST_CHOICES, state="readonly", width=10)),
                ("Attribution", ttk.Entry(f, textvariable=fv["attribution"], width=44)),
                ("Notes", ttk.Entry(f, textvariable=fv["notes"], width=44))]
        for i, (lab, wd) in enumerate(rows, 1):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=2); wd.grid(row=i, column=1, sticky="w", pady=2)
        r = len(rows) + 1
        ttk.Label(f, text="Custom licence text (if no SPDX id)").grid(row=r, column=0, columnspan=2, sticky="w")
        ct = tk.Text(f, height=4, width=60); ct.grid(row=r + 1, column=0, columnspan=2, sticky="we"); ct.insert("1.0", lic.get("custom_text") or "")
        if lic.get("rights_override"):
            ro = lic["rights_override"]
            ttk.Label(f, text="Recorded: '%s' - %s, %s" % (ro.get("statement"), ro.get("by"), ro.get("date")), foreground="#a05a00",
                      wraplength=520).grid(row=r + 2, column=0, columnspan=2, sticky="w")
        m = ttk.Label(f, text="", wraplength=520, justify=tk.LEFT); m.grid(row=r + 4, column=0, columnspan=2, sticky="w")

        def save():
            new = dict(lic); new.update({k: x.get().strip() for k, x in fv.items()}); new["custom_text"] = ct.get("1.0", tk.END).strip()
            probs = L.validate_licence(new)
            self.lib.set_licence(iid, new); self.refresh(iid)
            ok, why = L.redistributable(new)
            m.configure(text=("saved. " + ("can go into a pack" if ok and not probs else "stays local: " + "; ".join(probs or [why]))),
                        foreground="#26a269" if ok and not probs else "#a05a00")
            self.say("licence of %s saved (%s)" % (iid, "redistributable" if ok and not probs else "local only"))
        bf = ttk.Frame(f); bf.grid(row=r + 3, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(bf, text="Save licence", command=save).pack(side=tk.LEFT)
        ttk.Button(bf, text="Close", command=w.destroy).pack(side=tk.LEFT, padx=4)
        if auto:
            for k, v in auto.items():
                if k == "custom_text":
                    ct.delete("1.0", tk.END); ct.insert("1.0", v)
                elif k in fv:
                    fv[k].set(v)
            w.after(300, save)
        return w

    # ------------------------------------------------------------ bone map
    def bonemap_dialog(self, auto=None):
        iid = self.selected()
        if not iid or self.cur_rig is None:
            return
        from . import bonemap as BM, rigrec as RR
        from .render import RenderSettings
        r = self.cur_rig; rec = self.lib.bonemap(iid, r); mp = dict(rec["map"])
        w = tk.Toplevel(self.root); w.title("Bone map of %s (%s names)" % (iid, rec.get("convention"))); self.dlg = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 220, self.root.winfo_rooty() + 60))
        f = ttk.Frame(w, padding=8); f.pack(fill=tk.BOTH, expand=True)
        tv = ttk.Treeview(f, columns=("bone",), show="tree headings", height=24)
        tv.heading("#0", text="canonical"); tv.column("#0", width=130); tv.heading("bone", text="rig bone"); tv.column("bone", width=230)
        tv.grid(row=0, column=0, rowspan=6, sticky="ns")
        pic = ttk.Label(f); pic.grid(row=0, column=1, columnspan=3, sticky="n", padx=6)
        bone = tk.StringVar()
        ttk.Label(f, text="rig bone").grid(row=1, column=1, sticky="w", padx=6)
        cb = ttk.Combobox(f, textvariable=bone, values=["(none)"] + list(r.bones), width=30, state="readonly"); cb.grid(row=1, column=2, sticky="w")
        info = ttk.Label(f, text="", foreground="#555", wraplength=330, justify=tk.LEFT); info.grid(row=3, column=1, columnspan=3, sticky="w", padx=6)
        state = {"img": None}

        def fill():
            tv.delete(*tv.get_children())
            for c in BM.CANON:
                tv.insert("", tk.END, iid=c, text=c + (" *" if c in BM.REQUIRED else ""), values=(mp.get(c, "-"),))
            un = [b for b in r.bones if b not in mp.values()]
            info.configure(text="* = required.  Unmapped bones (%d, follow their parents): %s" % (len(un), ", ".join(un[:30]) + (" ..." if len(un) > 30 else "")))

        def pic_update(c=None):
            hl = {r.index(mp[c])} if c and c in mp and r.index(mp[c]) >= 0 else set()
            cols = {r.index(b): (40, 170, 90, 255) for b in mp.values() if r.index(b) >= 0}
            for i in hl:
                cols[i] = (230, 60, 60, 255)
            rs = RenderSettings(cell_w=640, cell_h=680, figure_h=int(680 * 0.86 * 1.8 / max(0.3, r.height())), baseline=650, anchor_x=320, yaw=20, ss=1)
            im = RR.render_skeleton(r, r.bind, rs, colors=cols)
            bg = Image.new("RGBA", im.size, (236, 239, 244, 255)); im = Image.alpha_composite(bg, im).resize((320, 340))
            state["img"] = ImageTk.PhotoImage(im); pic.configure(image=state["img"])

        def on_sel(e=None):
            s = tv.selection()
            if s:
                bone.set(mp.get(s[0], "(none)")); pic_update(s[0])

        def set_bone(e=None):
            s = tv.selection()
            if not s:
                return
            if bone.get() == "(none)":
                mp.pop(s[0], None)
            else:
                mp[s[0]] = bone.get()
            fill(); tv.selection_set(s[0]); pic_update(s[0])
        tv.bind("<<TreeviewSelect>>", on_sel); cb.bind("<<ComboboxSelected>>", set_bone)
        msg = ttk.Label(f, text="", foreground="#26a269", wraplength=330); msg.grid(row=5, column=1, columnspan=3, sticky="w", padx=6)

        def save():
            k, n = self.lib.find(iid)
            new = BM.make_record(r, rec.get("convention", "custom"), mp, edited=True)
            BM.save(new, os.path.join(self.lib.path(k, n), "bonemap.json")); self.refresh(iid)
            msg.configure(text="saved bonemap.json (missing required: %s)" % (", ".join(new.get("missing", [])) or "none"))

        def auto_detect():
            mp.clear(); mp.update(BM.detect(r)["map"]); fill(); pic_update()
        bf = ttk.Frame(f); bf.grid(row=4, column=1, columnspan=3, sticky="w", padx=6, pady=6)
        ttk.Button(bf, text="Save", command=save).pack(side=tk.LEFT)
        ttk.Button(bf, text="Auto-detect again", command=auto_detect).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Close", command=w.destroy).pack(side=tk.LEFT)
        fill(); pic_update()
        if auto:
            tv.selection_set(auto); tv.see(auto)
        return w

    # ------------------------------------------------------------ packs
    def install_pack(self, path=None, auto_accept=None):
        p = path or filedialog.askopenfilename(title="Install a Sprite Forge pack", filetypes=[("Sprite Forge pack", "*.sfpack"), ("All", "*.*")])
        if not p:
            return
        rep = L.verify(p)
        if not rep["ok"]:
            self.say("pack refused - verification failed:\n  " + "\n  ".join(rep["problems"]), True); return
        man = rep["manifest"]
        w = tk.Toplevel(self.root); w.title("Install pack: licences"); self.dlg = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 260, self.root.winfo_rooty() + 70))
        f = ttk.Frame(w, padding=10); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Pack '%s' - %d assets. Read the licence of each asset before you install:" % (man.get("name"), len(man["assets"])),
                  style="H.TLabel").pack(anchor="w")
        if man.get("description"):
            ttk.Label(f, text=man["description"], foreground="#555", wraplength=640).pack(anchor="w")
        t = scrolledtext.ScrolledText(f, width=90, height=22, font="TkFixedFont", wrap=tk.WORD); t.pack(fill=tk.BOTH, expand=True, pady=4)
        for a in man["assets"]:
            t.insert(tk.END, L.licence_text(a["licence"], "%s/%s" % (a["kind"], a["name"])) + "\n\n")
        for wmsg in rep.get("warnings", []):
            t.insert(tk.END, "warning: %s\n" % wmsg)
        t.configure(state=tk.DISABLED)
        ack = tk.BooleanVar(value=False); ow = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="I have read these licences and will follow them (attribution, redistribution terms)", variable=ack).pack(anchor="w")
        ttk.Checkbutton(f, text="Overwrite assets with the same name (otherwise identical ones are skipped, different ones renamed _2)", variable=ow).pack(anchor="w")
        m = ttk.Label(f, text="", foreground="#c01c28", wraplength=640); m.pack(anchor="w")
        bf = ttk.Frame(f); bf.pack(anchor="w", pady=6)

        def go():
            if not ack.get():
                m.configure(text="Tick the acknowledgement first - nothing is installed without it."); return
            try:
                res = self.lib.install(p, accept=True, overwrite=ow.get(), log=self.s._log)
            except Exception as e:
                m.configure(text=str(e)); return
            w.destroy(); self.refresh()
            self.say("installed pack %s: %s" % (os.path.basename(p), ", ".join("%s/%s (%s)" % x for x in res)))
        inst = ttk.Button(bf, text="Install", command=go, state=tk.DISABLED); inst.pack(side=tk.LEFT)
        ack.trace_add("write", lambda *a: inst.configure(state=tk.NORMAL if ack.get() else tk.DISABLED))
        ttk.Button(bf, text="Cancel", command=w.destroy).pack(side=tk.LEFT, padx=4)
        if auto_accept is not None:
            ack.set(bool(auto_accept)); w.after(700, go)
        return w

    def export_pack(self, out=None, auto=None):
        sel = [i for i in self.tree.selection()] or list(self.tree.get_children())
        w = tk.Toplevel(self.root); w.title("Export pack"); self.dlg = w
        w.geometry("+%d+%d" % (self.root.winfo_rootx() + 240, self.root.winfo_rooty() + 60))
        f = ttk.Frame(w, padding=10); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Export a .sfpack (zip + pack.json + licences) to share", style="H.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text="Only assets whose licence allows redistribution can go in. For your own work you can confirm you own the rights; "
                          "that statement, your name and the date are written into the pack.", foreground="#555", wraplength=640,
                  justify=tk.LEFT).grid(row=1, column=0, columnspan=4, sticky="w")
        inc, own = {}, {}
        for i, iid in enumerate(sel, 2):
            lic = self.lib.licence(iid); ok, why = L.redistributable(lic); probs = L.validate_licence(lic)
            good = ok and not probs
            inc[iid] = tk.BooleanVar(value=good); own[iid] = tk.BooleanVar(value=False)
            ttk.Checkbutton(f, text=iid, variable=inc[iid]).grid(row=i, column=0, sticky="w")
            ttk.Label(f, text=("%s, redistribution %s" % (lic.get("spdx") or "custom/none", lic.get("redistribution") or "unknown")),
                      foreground="#26a269" if good else "#a05a00").grid(row=i, column=1, sticky="w", padx=6)
            if not (lic.get("redistribution") == "yes"):
                ttk.Checkbutton(f, text="I own the rights", variable=own[iid]).grid(row=i, column=2, sticky="w")
        r = len(sel) + 2
        fv = {k: tk.StringVar(value=v) for k, v in dict(name="my_pack", description="", by="",
                                                        out=out or os.path.join(os.getcwd(), "my_pack.sfpack")).items()}
        for j, (lab, k, wd) in enumerate((("Pack name", "name", 24), ("Description", "description", 50), ("Your name (for 'I own the rights')", "by", 24),
                                           ("Save as", "out", 50))):
            ttk.Label(f, text=lab).grid(row=r + j, column=0, sticky="w"); ttk.Entry(f, textvariable=fv[k], width=wd).grid(row=r + j, column=1, columnspan=2, sticky="w")
        ttk.Button(f, text="...", width=3, command=lambda: fv["out"].set(filedialog.asksaveasfilename(defaultextension=".sfpack",
                   filetypes=[("Sprite Forge pack", "*.sfpack")]) or fv["out"].get())).grid(row=r + 3, column=3)
        m = ttk.Label(f, text="", foreground="#c01c28", wraplength=640, justify=tk.LEFT); m.grid(row=r + 5, column=0, columnspan=4, sticky="w")

        def go():
            names = [i for i, v in inc.items() if v.get()]
            ov = [i for i in names if own[i].get()]
            if not names:
                m.configure(text="nothing selected"); return
            if ov and not fv["by"].get().strip():
                m.configure(text="'I own the rights' needs your name - it is recorded in the pack."); return
            try:
                p = fv["out"].get()
                self.lib.pack(p, names, fv["name"].get().strip() or None, fv["description"].get(), override=ov,
                                  by=fv["by"].get().strip(), log=self.s._log)
            except Exception as e:
                m.configure(text=str(e)); return
            rep = L.verify(p)
            w.destroy(); self.refresh()
            self.say("pack written: %s (%d assets, verify %s)" % (p, len(rep["manifest"]["assets"]) if rep.get("manifest") else 0, "OK" if rep["ok"] else "FAILED"))
        bf = ttk.Frame(f); bf.grid(row=r + 4, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Button(bf, text="Export pack", command=go).pack(side=tk.LEFT)
        ttk.Button(bf, text="Cancel", command=w.destroy).pack(side=tk.LEFT, padx=4)
        if auto:
            for k, v in auto.get("vars", {}).items():
                fv[k].set(v)
            for k in auto.get("own", []):
                if k in own:
                    own[k].set(True); inc[k].set(True)
            if auto.get("go"):
                w.after(700, go)
        return w
