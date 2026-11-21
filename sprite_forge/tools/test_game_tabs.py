#!/usr/bin/env python3
"""The Studio's Games tab (v11.19): a page per kind of game. Every pack in game_packs/ is checked - including any
pack added later - not only the shipped ones. The window checks need Tk and a display (on a server:
xvfb-run python tools/test_game_tabs.py) and are skipped without them.

    python tools/test_game_tabs.py [--motion-library DIR]     (DIR: also check every game against your own moves)

Without a window:
  1 every game pack loads and gets a page: one row per move, each move's clip found (own / borrowed / procedural)
  2 every move of every game can be played: finite joints at the start, middle and end
  3 every move's events land on its timeline (0..1), in the order of their frames
  4 the character settings fit the game: fighter types for fighting games, player types and kits for team sports,
    and every type offered is one `forge.py build --character-type` accepts
  5 the build command line from the page's settings is right for a mannequin and for a library rig
  6 that command line really builds: a mannequin soccer player in a kit, a library-rig boxer as a heavy brawler -
    and the page reads back the build's QA per move and the clip each move was drawn from
  7 (with --motion-library) every game's moves resolve against your own library too
With a window:
  8 the Studio opens with a Games tab listing every game
  9 each game's page fills: header, moves table, the right character settings; every move plays in the preview
 10 Build from the tab streams the log, then shows the sheet preview and colours the moves by their QA
 11 Shot list from the tab prints what to film for that game
 12 (v11.20) the preview plays the built character's own sprites, frame by frame
 13 (v11.20) Build the team / cast from the tab: a roster with a select screen; Export project makes the engine project"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
R = []
CTYPES = {"balanced", "big_boss", "heavy_brawler", "keeper", "playmaker", "quick_striker", "small_agile"}


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name, ("  - " + detail) if detail and not ok else ""))


def _have_tk():
    try:
        import tkinter as tk
        r = tk.Tk(); r.destroy()
        return True
    except Exception:                                                      # noqa: BLE001
        return False


def _motion_of(GG, row, library=None):
    from sforge import motionlib as ML
    from sforge.motions import find_motion
    return find_motion(row["plays"]) if row["status"] == "procedural" else ML.as_motion(row["plays"], library)


def page_checks(GG, library=None, tag=""):
    from sforge import gamepack as GP
    from sforge.gui_motion import pose_points
    packs = GP.list_packs()
    bad1, bad2, bad3 = [], [], []
    for name in packs:
        try:
            p, rows = GG.game_rows(name, library)
        except Exception as e:                                             # noqa: BLE001
            bad1.append("%s: %s" % (name, e)); continue
        if len(rows) != len(p["moves"]) or not rows:
            bad1.append("%s: %d rows for %d moves" % (name, len(rows), len(p["moves"])))
        for r in rows:
            if r["status"] not in ("own", "shared", "procedural"):
                bad1.append("%s/%s: %s" % (name, r["move"], r["status"])); continue
            try:
                m = _motion_of(GG, r, library)
                for t in (0.0, 0.5, 1.0):
                    pts = pose_points(m, t)
                    if not pts or not all(np.all(np.isfinite(np.asarray(v, float))) for v in pts.values()):
                        raise ValueError("non-finite joints at t=%.1f" % t)
            except Exception as e:                                         # noqa: BLE001
                bad2.append("%s/%s (%s): %s" % (name, r["move"], r["plays"], e))
            marks = GG.event_marks(r)
            ts = [t for t, _ in marks]
            if any(not 0.0 <= t <= 1.0 for t in ts) or ts != sorted(ts):
                bad3.append("%s/%s: %s" % (name, r["move"], marks))
            if r["events"] and not marks:
                bad3.append("%s/%s: events %s not on the timeline" % (name, r["move"], r["events"]))
    n = sum(len(GP.load(x)["moves"]) for x in packs)
    rec("1%s all %d games get a page, every move's clip found" % (tag, len(packs)), not bad1 and len(packs) >= 12, "; ".join(bad1[:5]))
    rec("2%s all %d moves of every game play" % (tag, n), not bad2, "; ".join(bad2[:5]))
    rec("3%s every move's events land on its timeline in frame order" % tag, not bad3, "; ".join(bad3[:5]))
    return packs


def settings_checks(GG, packs):
    bad = []
    for name in packs:
        ts = GG.types_for(name)
        if "balanced" not in ts or not set(ts) <= CTYPES:
            bad.append("%s: %s" % (name, ts))
    for f in ("boxing", "fighting", "wrestling", "beat_em_up"):
        if "heavy_brawler" not in GG.types_for(f):
            bad.append(f + " lacks fighter types")
    for s in ("soccer", "gaelic", "basketball"):
        if not GG.has_kits(s) or "keeper" not in GG.types_for(s):
            bad.append(s + " lacks kits / player types")
    if GG.has_kits("platformer") or GG.has_kits("boxing"):
        bad.append("kits offered where there are no teams")
    rec("4 each game offers the character settings that fit it", not bad, "; ".join(bad))
    a = GG.build_argv("soccer", "/o", human="gender=1.00,muscle=0.50,weight=0.50", kit="home", glb=False)
    b = GG.build_argv("boxing", "/o", source="rig", rig="sample_stocky", ctype="heavy_brawler", library="/lib")
    c = GG.build_argv("platformer", "/o", source="rig", rig="", human="gender=0.00,muscle=0.50,weight=0.50")
    ok = (a == ["build", "--game", "soccer", "--out", "/o", "--mannequin", "--human", "gender=1.00,muscle=0.50,weight=0.50", "--kit", "home", "--no-glb"]
          and b == ["build", "--game", "boxing", "--out", "/o", "--rig", "sample_stocky", "--character-type", "heavy_brawler", "--motion-library", "/lib"]
          and "--mannequin" in c and "--rig" not in c and "--kit" not in c and "--character-type" not in c)
    rec("5 the page's settings become the right build command line", ok, "%s | %s | %s" % (a, b, c))


def build_checks(GG, packs):
    import subprocess
    out = tempfile.mkdtemp(prefix="sf_games_")
    try:
        runs = [("soccer", GG.build_argv("soccer", os.path.join(out, "soccer"), human="gender=1.00,muscle=0.50,weight=0.50", kit="home", glb=False)),
                ("boxing", GG.build_argv("boxing", os.path.join(out, "boxing"), source="rig", rig="sample_stocky", ctype="heavy_brawler", glb=False))]
        bad = []
        for name, argv in runs:
            r = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + argv, cwd=HERE, capture_output=True, text=True, timeout=600)
            folder = GG.build_folder(os.path.join(out, name))
            if r.returncode != 0:
                bad.append("%s exit %d: %s" % (name, r.returncode, (r.stdout + r.stderr)[-300:])); continue
            from sforge import gamepack as GP
            moves = [m["name"] for m in GP.load(name)["moves"]]
            score, qa = GG.read_qa(folder)
            src = GG.read_sources(folder)
            if score is None or set(qa) != set(moves):
                bad.append("%s: QA moves %s vs %s" % (name, sorted(qa), moves))
            if set(src) != set(moves) or any(n < 1 for _, n, _ in src.values()):
                bad.append("%s: sources %s" % (name, src))
            if not os.path.isfile(os.path.join(folder, "preview.png")):
                bad.append(name + ": no preview.png")
        rec("6 the build line really builds (mannequin soccer in a kit, rig boxer), QA and sources read back", not bad, "; ".join(bad))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def window_checks(GG, packs):
    import tkinter as tk
    from sforge import gui
    root = tk.Tk(); root.geometry("1400x860")
    app = gui.Studio(root)
    names = [app.nb.tab(i, "text").strip() for i in range(len(app.nb.tabs()))]
    g = app.games
    rec("8 the Studio has a Games tab listing every game", "Games" in names and g.games.size() == len(packs) and g.packs == packs,
        "%s, %d listed" % (names, g.games.size()))
    app.nb.select(names.index("Games"))
    bad = []
    for i, name in enumerate(packs):
        g.games.selection_clear(0, tk.END); g.games.selection_set(i); g.choose(); root.update()
        rows = g.tree.get_children()
        if len(rows) != len(g.rows) or not g.title.cget("text") or "Camera:" not in g.about.cget("text"):
            bad.append(name + ": page not filled")
        if tuple(g.type_box.cget("values")) != tuple(GG.types_for(name)):
            bad.append(name + ": types %s" % (g.type_box.cget("values"),))
        if (str(g.kit_box.cget("state")) != "disabled") != GG.has_kits(name):
            bad.append(name + ": kit picker state %s" % g.kit_box.cget("state"))
        for mv in rows:
            g.tree.selection_set(mv); g.pick()
            g.t.set(0.5); g.draw()
            if g.motion is None or len(g.canvas.find_all()) < 8:
                bad.append("%s/%s: not drawn (%s)" % (name, mv, g.detail.cget("text")[:80]))
    rec("9 every game's page fills and every move plays in the preview", not bad, "; ".join(bad[:6]))

    out = tempfile.mkdtemp(prefix="sf_gtab_")
    try:
        g.out.set(out); g.glb.set(False)
        g.games.selection_clear(0, tk.END); g.games.selection_set(packs.index("soccer")); g.choose()
        g.source.set("mannequin"); g.kit.set("away")
        g.build()
        t0 = time.time()
        while g._proc is not None and time.time() - t0 < 300:
            root.update(); time.sleep(0.05)
        root.update()
        log = g.log.get("1.0", "end")
        coloured = any(set(g.tree.item(m, "tags")) & {"qa_fail", "qa_warn"} for m in g.tree.get_children()) or \
            all(g.tree.set(m, "check") == "pass" for m in g.tree.get_children())
        ok = (g.status.get().startswith("Last build: QA score") and "Done in" in log and g._img is not None
              and all(g.tree.set(m, "check") in ("pass", "warn", "fail") for m in g.tree.get_children()) and coloured)
        rec("10 Build from the tab streams its log, shows the sheet and the QA per move", ok, g.status.get() + " | " + log[-200:].replace("\n", " | "))
        g.shotlist()
        t0 = time.time()
        while g._proc is not None and time.time() - t0 < 120:
            root.update(); time.sleep(0.05)
        root.update()
        text = g.log.get("1.0", "end")
        rec("11 Shot list from the tab prints what to film", "kick" in text and len(text.splitlines()) > 5, text[:200].replace("\n", " | "))

        # 12: the built character's own sprites in the preview
        g.tree.selection_set("kick"); g.pick(); g.mode.set("character")
        seen = set()
        for t in (0.05, 0.35, 0.65, 0.95):
            g.t.set(t); g.draw(); root.update()
            if getattr(g, "_spr", None) is not None:
                seen.add(int(t * g._strip("kick")[3]))
        st = g._strip("kick")
        rec("12 the preview plays the built character's own sprites", st is not None and len(seen) >= 3, "strip %s, frames %s" % (st and st[1:], seen))
        g.mode.set("figure")

        # 13: a roster from the tab, then an engine project from it
        g.games.selection_clear(0, tk.END); g.games.selection_set(packs.index("boxing")); g.choose()
        g.size.set(2)
        g.roster()
        t0 = time.time()
        while g._proc is not None and time.time() - t0 < 600:
            root.update(); time.sleep(0.05)
        root.update()
        rj = os.path.join(out, "rosters", "boxing", "roster.json")
        ok_r = os.path.isfile(rj) and len(json.load(open(rj))["players"]) == 2 and g.status.get().startswith("2 players")
        g.engine.set("godot")
        g.export()
        t0 = time.time()
        while g._proc is not None and time.time() - t0 < 300:
            root.update(); time.sleep(0.05)
        root.update()
        proj = os.path.join(out, "engines", "boxing", "godot")
        ok_e = os.path.isfile(os.path.join(proj, "project.godot")) and \
            len(json.load(open(os.path.join(proj, "characters", "index.json")))) == 2
        rec("13 Build the cast and Export project from the tab", ok_r and ok_e, "%s | %s" % (g.status.get(), g.log.get("1.0", "end")[-300:]))
    finally:
        root.destroy()
        shutil.rmtree(out, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motion-library", default=os.environ.get("SFS_MOTIONS") or "")
    ap.add_argument("--no-build", action="store_true", help="skip the real builds (6, 10)")
    a = ap.parse_args()
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("skipped: this Python has no tkinter (the Studio needs it)")
        return 0
    os.environ.pop("SFS_MOTIONS", None)
    from sforge import gui_games as GG
    packs = page_checks(GG)
    settings_checks(GG, packs)
    if not a.no_build:
        build_checks(GG, packs)
    if a.motion_library and os.path.isdir(a.motion_library):
        page_checks(GG, a.motion_library, tag="L")
    if _have_tk():
        window_checks(GG, packs)
    else:
        print("window checks skipped: no display (run under xvfb-run)")
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
