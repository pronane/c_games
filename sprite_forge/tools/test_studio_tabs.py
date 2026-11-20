#!/usr/bin/env python3
"""The Studio's Capture and Motion tabs (v11.18). No videos needed; the window checks need Tk and a display
(on a server: xvfb-run python tools/test_studio_tabs.py) and are skipped without them.

    python tools/test_studio_tabs.py

Capture tab (sforge/gui_capture.py) - checked without a window:
  1 every option on the form becomes the right `forge.py capture` flag; defaults add none
  2 the progress steps light up from the capture's real log lines, in order (track, fit, texture, export, check)
  3 the inputs are checked before anything runs: no video, a missing file, a bad name, a height in feet or metres
  4 finished captures in an output folder are found; their report reads as plain lines and their files are listed
Motion tab (sforge/gui_motion.py) - checked without a window:
  5 every move of the shipped starter set is listed, with its category, length and licence
  6 every starter move can be drawn: finite joints at the start, middle and end, a figure 0.7-2.3 m across (a crouch
    is small)
  7 the views are the right way round: facing the viewer the figure's left hand is on the right; side-on it faces
    right; the feet are drawn on the floor line
  8 the motion checks run on a move and come back as pass / fail lines
With a window (Tk + a display):
  9 the Studio opens with Capture and Motion tabs
 10 Motion: picking a move fills the details and checks and draws the figure; the search box filters the list
 11 Motion: Import file runs `forge.py motion import` on a BVH, the new move appears in the list and plays
 12 Capture: a capture started from the tab streams its log and reports failure plainly (a missing video)"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-70s %s" % ("PASS" if ok else "FAIL", name, detail))


def _have_tk():
    try:
        import tkinter
        r = tkinter.Tk(); r.destroy()
        return True
    except Exception:                                                  # noqa: BLE001
        return False


def capture_checks(GC):
    a = GC.capture_argv("v.mp4", "mike", "180", "out", body="male", neutral="upper", face_photo="f.jpg", fps="3",
                        texture="2048", layers=False, face=False, delight=False, register=False)
    want = ["capture", "v.mp4", "--name", "mike", "--height-cm", "180", "--out", "out", "--body", "male", "--neutral", "upper",
            "--face-photo", "f.jpg", "--fps", "3", "--texture", "2048", "--no-layers", "--no-face", "--keep-light", "--no-register"]
    d = GC.capture_argv("v.mp4", "mike", "180", "out")
    rb = GC.capture_argv("v.mp4", "mike", "", "out", rebuild=True)
    rec("1 the form's options become the right capture flags; defaults add none",
        a == want and d == ["capture", "v.mp4", "--name", "mike", "--height-cm", "180", "--out", "out"]
        and rb == ["capture", "--name", "mike", "--out", "out", "--rebuild"], " ".join(a))
    log = ["capture: 162 frames at 4.0 fps from mike.mp4", "capture: 160/162 frames tracked, orbit 352 deg",
           "fit: 24 frames round the orbit", "fit: pass 2  IoU after cameras 0.87", "layers: clothes over 6 parts",
           "face: held-out frames, landmark error 2.1 px", "texture: 41 frames", "light: left / right colour difference 3",
           "capture: mike.glb (MakeHuman; 53 bones, 7 clips)", "capture: white balance from the upper garment",
           "check (6 held-out frames): silhouette IoU 0.85", "capture: mike done in 412 s -> captures/mike"]
    got = [GC.step_of(x) for x in log]
    seen = [s for s in got if s]
    order = [k for k, _, _ in GC.STEPS]
    mono = all(order.index(a_) <= order.index(b) for a_, b in zip(seen, seen[1:]))
    rec("2 the progress steps follow the capture's real log lines, in order", set(seen) == set(order) and mono,
        " ".join(s or "-" for s in got))
    import tkinter as _tk                                              # noqa: F401  (vars need no window)
    tmp = tempfile.mkdtemp()
    vid = os.path.join(tmp, "v.mp4"); open(vid, "wb").write(b"\0")
    cases = [(dict(video=""), "Choose the video"), (dict(video=os.path.join(tmp, "nope.mp4")), "not found"),
             (dict(name="mi ke"), "letters"), (dict(height="5.9"), "centimetres"), (dict(height="1.8"), "centimetres"),
             (dict(height=""), "how tall"), (dict(), None)]
    ok3, det = True, []
    for over, want_ in cases:
        fake = _Fake(dict(video=vid, name="mike", height="180", face_photo=""), over)
        err = GC.CaptureTab.check_inputs(fake)
        good = (err is None) if want_ is None else (err is not None and want_ in err)
        ok3 &= good; det.append("%s->%s" % (list(over.items()) or "ok", "ok" if err is None else "error"))
    rec("3 the inputs are checked before anything runs", ok3, "; ".join(det[:3]) + " ...")
    out = os.path.join(tmp, "caps")
    for n, iou in (("anna", 0.88), ("ben", 0.91)):
        o = os.path.join(out, n, "out"); os.makedirs(o)
        rep = dict(name=n, height_m=1.7, fit=dict(iou=iou, iou_start=0.8, frames=20), check=dict(iou=0.85, dE=9.5, ssim=0.66),
                   macros=dict(gender=0.1, muscle=0.4, weight=0.5), files=dict(glb=n + ".glb", fbx=n + ".fbx"),
                   layers=dict(clothes_faces=10, offsets_m={"torso_low": 0.01}, skirt=True, hair_length_m=0.3))
        json.dump(rep, open(os.path.join(o, "report.json"), "w"))
        open(os.path.join(o, n + ".glb"), "wb").write(b"glTF")
    os.makedirs(os.path.join(out, "half_done"))                         # no report: not listed
    found = GC.find_captures(out)
    lines = GC.summary(json.load(open(os.path.join(out, "anna", "out", "report.json"))))
    files = GC.files_of(json.load(open(os.path.join(out, "anna", "out", "report.json"))), os.path.join(out, "anna"))
    rec("4 finished captures are found, their report reads plainly, their files listed",
        [n for n, _ in found] == ["anna", "ben"] and any("Silhouette fit 88%" in x for x in lines)
        and any("female" in x for x in lines) and any("a skirt" in x and "hair 30 cm" in x for x in lines)
        and [os.path.basename(p) for _, p in files] == ["anna.glb"], " | ".join(lines))
    shutil.rmtree(tmp, ignore_errors=True)


class _Fake:
    """just enough of a CaptureTab for check_inputs"""
    class _V:
        def __init__(self, s):
            self.s = s

        def get(self):
            return self.s

    def __init__(self, base, over):
        d = dict(base); d.update(over)
        self.v = {k: self._V(v) for k, v in d.items()}


def motion_checks(GM):
    from sforge import motionlib as ML
    rows = GM.move_rows(ML.builtin_dir())
    starter = ML.open_library(ML.builtin_dir()).names()
    names = [r[0] for r in rows]
    rec("5 every starter move is listed with category, length and licence",
        set(starter) <= set(names) and all(r[2] > 0 and r[5] for r in rows if r[0] in starter),
        "%d moves, e.g. %s" % (len(rows), rows[0] if rows else None))
    bad, tall = [], []
    for n in starter:
        m = ML.as_motion(n, ML.builtin_dir())
        for t in (0.0, 0.5, 1.0):
            pts = GM.pose_points(m, t)
            P = np.array(list(pts.values()))
            if not np.isfinite(P).all() or len(pts) < 20:
                bad.append(n); break
            tall.append(float(np.ptp(P, axis=0).max()))           # lying down counts too
    rec("6 every starter move can be drawn: finite joints, a person-sized figure", not bad and 0.7 < min(tall) and max(tall) < 2.3,
        "heights %.2f-%.2f m%s" % (min(tall), max(tall), (", bad: %s" % bad) if bad else ""))
    idle = ML.as_motion("idle", ML.builtin_dir())
    pts = GM.pose_points(idle, 0.0)
    fr = GM.project(pts, "front", (280, 330)); sd = GM.project(pts, "side", (280, 330))
    floor_y = 330 * 0.92
    feet = min(abs(fr["foot_L_tip"][1] - floor_y), abs(fr["foot_R_tip"][1] - floor_y))
    rec("7 views the right way round: left hand on the viewer's right; faces right side-on; feet on the floor",
        fr["hand_L"][0] > fr["hand_R"][0] and sd["foot_L_tip"][0] > sd["foot_L"][0] and feet < 25,
        "left hand x %.0f vs right %.0f; toe %.0f px from the floor line" % (fr["hand_L"][0], fr["hand_R"][0], feet))
    rec_ = ML.open_library(ML.builtin_dir()).load("kick")
    q = GM.qa(rec_, "kick")
    rec("8 the motion checks run on a move", len(q) >= 4 and all(len(x) == 3 for x in q),
        ", ".join("%s %s" % (c, "ok" if ok else "FAIL") for c, ok, _ in q if ok is not None))


def _bvh(path):
    """a small synthetic BVH with Unity-style names (the same as tools/test_motion_v114.py writes)"""
    joints = [
        ("Hips", None, (0, 0.95, 0), True),
        ("Spine", "Hips", (0, 0.20, 0), False),
        ("Chest", "Spine", (0, 0.20, 0), False),
        ("RightUpperArm", "Chest", (-0.20, 0.15, 0), False),
        ("RightLowerArm", "RightUpperArm", (0, -0.28, 0), False),
        ("LeftUpperArm", "Chest", (0.20, 0.15, 0), False),
        ("LeftLowerArm", "LeftUpperArm", (0, -0.28, 0), False),
        ("RightUpperLeg", "Hips", (-0.10, -0.10, 0), False),
        ("RightLowerLeg", "RightUpperLeg", (0, -0.42, 0), False),
        ("LeftUpperLeg", "Hips", (0.10, -0.10, 0), False),
        ("LeftLowerLeg", "LeftUpperLeg", (0, -0.42, 0), False),
    ]
    lines = ["HIERARCHY"]

    def emit(name, depth):
        j = next(x for x in joints if x[0] == name)
        _, parent, off, root = j
        pad = "  " * depth
        lines.append("%s%s %s" % (pad, "ROOT" if root else "JOINT", name))
        lines.append("%s{" % pad)
        lines.append("%s  OFFSET %.4f %.4f %.4f" % (pad, off[0], off[1], off[2]))
        ch = "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation" if root else "3 Zrotation Xrotation Yrotation"
        lines.append("%s  CHANNELS %s" % (pad, ch))
        kids = [c[0] for c in joints if c[1] == name]
        if not kids:
            lines.append("%s  End Site" % pad)
            lines.append("%s  {" % pad)
            lines.append("%s    OFFSET 0 %.4f 0" % (pad, -0.25))
            lines.append("%s  }" % pad)
        for k in kids:
            emit(k, depth + 1)
        lines.append("%s}" % pad)
    emit("Hips", 0)
    nch = 6 + 3 * (len(joints) - 1)
    lines += ["MOTION", "Frames: 3", "Frame Time: 0.1"]
    # channel order is the joint order above. RightUpperArm is index 3 -> rotation channels start at 6+3+3=12
    for ax in (0.0, -40.0, -80.0):
        row = [0.0] * nch
        row[1] = 0.95
        row[12] = ax          # RightUpperArm Xrotation (Z, X, Y) so index 12 is Z, 13 is X
        row[13] = ax
        lines.append(" ".join("%.4f" % v for v in row))
    open(path, "w").write("\n".join(lines) + "\n")


def window_checks():
    import tkinter as tk
    import time
    from sforge import gui, motionlib as ML
    root = tk.Tk(); root.geometry("1300x820")
    app = gui.Studio(root)
    names = [app.nb.tab(i, "text").strip() for i in range(len(app.nb.tabs()))]
    rec("9 the Studio opens with Capture and Motion tabs", "Capture" in names and "Motion" in names, ", ".join(names))
    lib = tempfile.mkdtemp(prefix="sf_tab_lib_")
    m = app.motionlib
    m.lib.set(lib); m.reload()
    n_all = len(m.tree.get_children())
    m.search.set("kick"); n_kick = len(m.tree.get_children()); m.search.set("")
    m.tree.selection_set("kick"); m.select("kick"); root.update()
    drawn = len(m.canvas.find_all())
    rec("10 picking a move fills details and checks and draws it; search filters",
        "kick" in m.info.cget("text") and len(m.checks.winfo_children()) >= 4 and drawn > 20 and 0 < n_kick < n_all,
        "%d canvas items, %d checks, search kick -> %d of %d" % (drawn, len(m.checks.winfo_children()), n_kick, n_all))
    bvh = os.path.join(lib, "_arm.bvh"); _bvh(bvh)
    m._run(["import", bvh, "--name", "arm_swing", "--spdx", "CC0-1.0"], "importing", then="arm_swing")
    t0 = time.time()
    while m._proc is not None and time.time() - t0 < 120:
        root.update(); time.sleep(0.05)
    root.update()
    ok11 = m.tree.exists("arm_swing") and "arm_swing" in m.info.cget("text")
    rec("11 Import file: the BVH becomes a move in the list and plays", ok11, m.status.get() + " " + m.log.get("1.0", "end")[-160:].strip().replace("\n", " | "))
    c = app.capture
    c.v["out"].set(lib); c.v["name"].set("ghost"); c.v["height"].set("170")
    c._start(["capture", os.path.join(lib, "no_such_video.mp4"), "--name", "ghost", "--height-cm", "170", "--out", lib], "test")
    t0 = time.time()
    while c._proc is not None and time.time() - t0 < 120:
        root.update(); time.sleep(0.05)
    root.update()
    text = c.log.get("1.0", "end")
    rec("12 Capture: a run from the tab streams its log and says plainly when it fails",
        c.status.get().startswith("Failed") and len(text.strip()) > 0 and str(c.go.cget("state")) == "normal",
        c.status.get())
    root.destroy()
    shutil.rmtree(lib, ignore_errors=True)


def main():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("skipped: this Python has no tkinter (the Studio needs it)")
        return 0
    from sforge import gui_capture as GC, gui_motion as GM
    capture_checks(GC)
    motion_checks(GM)
    if _have_tk():
        window_checks()
    else:
        print("window checks skipped: no display (run under xvfb-run)")
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
