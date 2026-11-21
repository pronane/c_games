#!/usr/bin/env python3
"""Rosters, portraits and the one-click engine projects (v11.20).

    python tools/test_engines.py [--godot BIN] [--raylib RAYLIB_SRC] [--keep DIR]

Checks every game pack's default roster and every engine, not one sample:
  1 every game gets a sensible default roster: two sides with a keeper in the keeper's kit for team sports, a cast of
    different fighter types for fighting games; each one validates; bad rosters are refused with a reason
  2 a roster player becomes the right build line (mannequin body, rig or capture, kit, type)
  3 a real roster builds (two fighters): each player's sprites, model, QA and a portrait from the 3D model; the
    roster.json, select screen and team sheet; the portrait falls back to the sprites when there is no model
  4 `forge.py engine all` makes all six projects from the roster and from a single build; every character's manifest
    and strips are in each; a folder with neither a build nor a roster is refused
  5 raylib's copy of each model has 8-bit joint indices and still reads back with the same skin
  6 Godot: the project files are well formed (and, with a Godot 4 binary, both demos run headless and load every
    character and every animation)
  7 Unity: package manifest, assembly references and scripts are consistent with the bundled importer
  8 Unreal: the import script runs against a recording stand-in of UE5's Python API - a texture, a sprite per frame
    and a flipbook per move at its fps for every character, the FBX imported as a skeletal mesh with its animations,
    every move event a sync marker inside its take, and a demo level with each character
  9 raylib: with raylib 5.5 built (--raylib), both demos compile and run and draw every character
 10 web: in a browser (Playwright), the sprite page loads every character and move
 11 pygame: with pygame installed, the player runs headless and draws every character
Unity and Unreal themselves do not run here; their projects are checked as above, not opened.
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name, ("  - " + str(detail)[:400]) if detail and not ok else ""))


def skip(name, why):
    print("skip %s  - %s" % (name, why))


def forge(*argv, cwd=HERE, timeout=900):
    return subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(argv), cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


def roster_checks():
    from sforge import roster as RO, gamepack as GP
    bad = []
    for g in GP.list_packs():
        r = RO.default_roster(g)
        v = RO.validate(r)
        if v:
            bad.append("%s: %s" % (g, v))
        ps = r["players"]
        if g in RO.TEAM_GAMES:
            sides = sorted({p["side"] for p in ps})
            keepers = [p for p in ps if p["type"] == "keeper"]
            if sides != ["Away", "Home"] or len(keepers) != 2 or any(p["kit"] != "gk" for p in keepers):
                bad.append("%s: sides %s, keepers %s" % (g, sides, [(p["name"], p["kit"]) for p in keepers]))
            if any(p["kit"] == "gk" for p in ps if p["type"] != "keeper"):
                bad.append(g + ": an outfield player in the keeper's kit")
        if g in RO.FIGHT_GAMES and len({p["type"] for p in ps}) < len(ps):
            bad.append(g + ": fighters share a type")
    big = RO.default_roster("soccer", 7)
    if len(big["players"]) != 14:
        bad.append("size 7 gave %d players" % len(big["players"]))
    refused = [RO.validate(x) for x in (dict(game="nope", players=[dict(name="a")]), dict(game="soccer", players=[]),
                                         dict(game="soccer", players=[dict(name="a"), dict(name="a")]),
                                         dict(game="boxing", players=[dict(name="x y")]),
                                         dict(game="boxing", players=[dict(name="x", type="wizard")]),
                                         dict(game="boxing", players=[dict(name="x", body=dict(muscle=3))]))]
    if not all(refused):
        bad.append("not refused: %s" % refused)
    rec("1 every game's default roster fits it and validates; bad rosters are refused", not bad, "; ".join(bad))
    a = RO.player_argv("soccer", dict(name="k", kit="gk", type="keeper", body=dict(gender=1, muscle=0.6)), "/o", glb=False, library="/l")
    b = RO.player_argv("boxing", dict(name="mike", rig="/c/mike.glb"), "/o")
    ok = (a == ["build", "--game", "soccer", "--name", "k", "--out", "/o", "--mannequin", "--human", "gender=1.00,muscle=0.60",
                "--kit", "gk", "--character-type", "keeper", "--motion-library", "/l", "--no-glb"]
          and b == ["build", "--game", "boxing", "--name", "mike", "--out", "/o", "--rig", "/c/mike.glb"])
    rec("2 a roster player becomes the right build line", ok, "%s | %s" % (a, b))


def build_roster(tmp):
    r = forge("roster", "--game", "fighting", "--size", "2", "--out", tmp)
    d = os.path.join(tmp, "fighting")
    from PIL import Image
    bad = []
    if r.returncode != 0:
        rec("3 a real roster builds with portraits, select screen and team sheet", False, (r.stdout + r.stderr)[-400:])
        return None
    doc = json.load(open(os.path.join(d, "roster.json")))
    for p in doc["players"]:
        f = os.path.join(d, p["folder"])
        for need in ("game_character.json", "model.glb", "qa.json", "portrait.png"):
            if not os.path.isfile(os.path.join(f, need)):
                bad.append("%s: no %s" % (p["name"], need))
        if p.get("portrait_from") != "3d":
            bad.append("%s portrait from %s" % (p["name"], p.get("portrait_from")))
        else:
            im = Image.open(os.path.join(f, "portrait.png")).convert("RGB")
            import numpy as np
            a = np.asarray(im).astype(int)
            fg = (np.abs(a - np.array([28, 32, 40])).sum(2) > 30).mean()
            if not 0.15 < fg < 0.9:
                bad.append("%s portrait is %.0f%% figure" % (p["name"], fg * 100))
    for need in ("select_screen.png", "team_sheet.png"):
        if not os.path.isfile(os.path.join(d, need)):
            bad.append("no " + need)
    from sforge import portrait as PT
    one = os.path.join(d, doc["players"][0]["folder"])
    t = os.path.join(tmp, "nomodel")
    shutil.copytree(one, t, ignore=shutil.ignore_patterns("model.*", "portrait.png"))
    p, how = PT.portrait(t)
    if how != "sprite" or not p:
        bad.append("fallback portrait: %s %s" % (p, how))
    rec("3 a real roster builds with portraits (from the model), select screen and team sheet", not bad, "; ".join(bad))
    return d


def export_checks(tmp, rost):
    from sforge import engines as E
    bad = []
    single = os.path.join(rost, json.load(open(os.path.join(rost, "roster.json")))["players"][0]["folder"])
    projects = {}
    for label, src in (("roster", rost), ("single", single)):
        out = os.path.join(tmp, "eng_" + label)
        r = forge("engine", "all", src, "--out", out)
        if r.returncode:
            bad.append("%s: %s" % (label, (r.stdout + r.stderr)[-300:])); continue
        _, chars = E.characters(src)
        roots = dict(godot="characters", unity="Assets/Characters", unreal="SpriteForge/characters", raylib="characters",
                     web="characters", pygame="characters")
        for e in E.ENGINES:
            for c in chars:
                cdir = os.path.join(out, e, roots[e], c["name"])
                m = os.path.join(cdir, "game_character.json")
                if not os.path.isfile(m):
                    bad.append("%s/%s: no manifest" % (label, e)); continue
                for a in json.load(open(m))["animations"]:
                    if not os.path.isfile(os.path.join(cdir, a["strip"])):
                        bad.append("%s/%s/%s: strip %s missing" % (label, e, c["name"], a["strip"]))
            if not os.path.isfile(os.path.join(out, e, "README.md")):
                bad.append("%s/%s: no README" % (label, e))
        projects[label] = out
    r = forge("engine", "godot", tmp, "--out", os.path.join(tmp, "x"))
    if r.returncode == 0:
        bad.append("a folder with no build was accepted")
    rec("4 `engine all` makes all six projects from a roster and from one build, every character complete", not bad, "; ".join(bad[:6]))
    return projects.get("roster")


def joints_check(proj):
    from sforge.importers import load_file
    import numpy as np
    bad = []
    for glb in glob.glob(os.path.join(proj, "raylib", "characters", "*", "model.glb")):
        raw = open(glb, "rb").read()
        n = int.from_bytes(raw[12:16], "little")
        gl = json.loads(raw[20:20 + n])
        for m in gl["meshes"]:
            for p in m["primitives"]:
                for k, v in p["attributes"].items():
                    if k.startswith("JOINTS_") and gl["accessors"][v]["componentType"] != 5121:
                        bad.append(glb + " joints not 8-bit")
        name = os.path.basename(os.path.dirname(glb))
        orig = os.path.join(proj, "godot", "characters", name, "model.glb")
        a, b = load_file(orig)[0], load_file(glb)[0]
        if a.V.shape != b.V.shape or not np.allclose(a.skin(a.bind), b.skin(b.bind), atol=1e-5) or set(a.clips) != set(b.clips):
            bad.append(name + ": the converted model reads back differently")
    rec("5 raylib's models have 8-bit joints and read back with the same skin and clips", not bad and glob.glob(
        os.path.join(proj, "raylib", "characters", "*", "model.glb")), "; ".join(bad))


def godot_checks(proj, godot):
    g = os.path.join(proj, "godot")
    bad = []
    pg = open(os.path.join(g, "project.godot")).read()
    for need in ('run/main_scene="res://main.tscn"', "config_version=5", "res://addons/sprite_forge/plugin.cfg"):
        if need not in pg:
            bad.append("project.godot lacks " + need)
    for f in ("main.tscn", "demo3d.tscn", "demo.gd", "demo3d.gd", "sprite_forge/game_character.gd", "addons/sprite_forge/plugin.cfg"):
        if not os.path.isfile(os.path.join(g, f)):
            bad.append("missing " + f)
    for scn in ("main.tscn", "demo3d.tscn"):
        for res in re.findall(r'path="res://([^"]+)"', open(os.path.join(g, scn)).read()):
            if not os.path.isfile(os.path.join(g, res)):
                bad.append("%s points at missing %s" % (scn, res))
    n = len(json.load(open(os.path.join(g, "characters", "index.json"))))
    if godot and os.path.isfile(godot):
        subprocess.run([godot, "--headless", "--path", g, "--import"], capture_output=True, timeout=300)
        r1 = subprocess.run([godot, "--headless", "--path", g, "--quit-after", "30"], capture_output=True, text=True, timeout=300)
        r2 = subprocess.run([godot, "--headless", "--path", g, "res://demo3d.tscn", "--quit-after", "30"], capture_output=True, text=True, timeout=300)
        d2 = [ln for ln in r1.stdout.splitlines() if ln.startswith("SF_DEMO ")]
        d3 = [ln for ln in r2.stdout.splitlines() if ln.startswith("SF_DEMO3D ")]
        errs = [ln for ln in (r1.stdout + r1.stderr + r2.stdout + r2.stderr).splitlines() if "ERROR" in ln or "SCRIPT ERROR" in ln]
        if len(d2) != n or any(int(x.split()[-1]) < 5 for x in d2):
            bad.append("2D demo: %s" % d2)
        if len(d3) != n or any(int(x.split()[-1]) < 5 for x in d3):
            bad.append("3D demo: %s" % d3)
        if errs:
            bad.append("errors: %s" % errs[:3])
        rec("6 Godot project runs headless: %d characters in 2D and 3D, every animation" % n, not bad, "; ".join(bad))
    else:
        rec("6 Godot project files are well formed (no Godot binary: not run)", not bad, "; ".join(bad))


def unity_checks(proj):
    u = os.path.join(proj, "unity")
    bad = []
    man = json.load(open(os.path.join(u, "Packages", "manifest.json")))["dependencies"]
    for need in ("com.unity.2d.sprite", "com.unity.modules.physics2d", "com.unity.modules.animation", "com.unity.modules.jsonserialize"):
        if need not in man:
            bad.append("manifest lacks " + need)
    asm = {json.load(open(p))["name"] for p in glob.glob(os.path.join(u, "**", "*.asmdef"), recursive=True)}
    for p in glob.glob(os.path.join(u, "Assets", "**", "*.asmdef"), recursive=True):
        for ref in json.load(open(p)).get("references", []):
            if ref not in asm:
                bad.append("%s references missing %s" % (os.path.basename(p), ref))
    imp = open(os.path.join(u, "Packages", "com.spriteforge.importer", "Editor", "SpriteForgeImporter.cs")).read()
    rt = "".join(open(p).read() for p in glob.glob(os.path.join(u, "Packages", "com.spriteforge.importer", "Runtime", "*.cs")))
    setup = open(os.path.join(u, "Assets", "SpriteForge", "Editor", "SpriteForgeProjectSetup.cs")).read()
    demo = open(os.path.join(u, "Assets", "SpriteForge", "SpriteForgeDemo.cs")).read()
    if not re.search(r"public static \S*List<string> ImportFolder\(string", imp) and "public static List<string> ImportFolder" not in imp:
        bad.append("the importer has no public static ImportFolder(string) returning paths")
    for need in ("public void Play(string", "public SpriteForgeCharacterData data", "class SpriteForgeCharacter"):
        if need not in rt:
            bad.append("runtime lacks " + need)
    if "moves" not in open(glob.glob(os.path.join(u, "Packages", "com.spriteforge.importer", "Runtime", "SpriteForgeCharacterData.cs"))[0]).read():
        bad.append("character data has no moves list")
    for name, src in (("setup", setup), ("demo", demo)):
        if src.count("{") != src.count("}") or src.count("(") != src.count(")"):
            bad.append(name + " has unbalanced brackets")
    for c in os.listdir(os.path.join(u, "Assets", "Characters")):
        if not os.path.isfile(os.path.join(u, "Assets", "Characters", c, "atlas.json")):
            bad.append(c + ": no atlas.json for the importer")
    rec("7 Unity project: manifest, assemblies and scripts agree with the bundled importer (not opened in Unity)", not bad, "; ".join(bad))


def unreal_checks(proj):
    import importlib
    import unreal_stub as U
    ue = os.path.join(proj, "unreal")
    bad = []
    up = json.load(open(os.path.join(ue, "SpriteForgeDemo.uproject")))
    if {p["Name"] for p in up["Plugins"] if p["Enabled"]} < {"Paper2D", "PythonScriptPlugin", "EditorScriptingUtilities"}:
        bad.append("uproject plugins %s" % up["Plugins"])
    if not os.path.isfile(os.path.join(ue, "Content", "Python", "init_unreal.py")):
        bad.append("no init_unreal.py")
    U.install(ue)
    sys.path.insert(0, os.path.join(ue, "SpriteForge"))
    try:
        S = importlib.import_module("sprite_forge_import")
        importlib.reload(S)
        made = S.run()
    except Exception as e:                                                 # noqa: BLE001
        rec("8 Unreal import script against the UE5 stand-in", False, "%s: %s" % (type(e).__name__, e)); return
    finally:
        sys.path.remove(os.path.join(ue, "SpriteForge"))
    L = U.LOG
    idx = json.load(open(os.path.join(ue, "SpriteForge", "characters", "index.json")))
    for c in idx:
        m = json.load(open(os.path.join(ue, "SpriteForge", "characters", c["dir"], "game_character.json")))
        fbs, mesh, anims = made.get(c["name"], ({}, None, {}))
        for a in m["animations"]:
            fb = fbs.get(a["name"])
            if fb is None:
                bad.append("%s/%s: no flipbook" % (c["name"], a["name"])); continue
            kf = fb._p.get("key_frames") or []
            if len(kf) != a["frames"] or abs(fb._p.get("frames_per_second", 0) - a["fps"]) > 1e-6:
                bad.append("%s/%s: %d frames @ %s" % (c["name"], a["name"], len(kf), fb._p.get("frames_per_second")))
            for i, k in enumerate(kf):
                uv, dim = k.sprite._p["source_uv"], k.sprite._p["source_dimension"]
                if (uv.x, uv.y, dim.x, dim.y) != (i * a["w"], 0, a["w"], a["h"]):
                    bad.append("%s/%s frame %d rect" % (c["name"], a["name"], i)); break
        if c["fbx"]:
            if mesh is None or len(anims) != len(m["animations"]):
                bad.append("%s: mesh %s, %d of %d animations" % (c["name"], mesh, len(anims), len(m["animations"])))
            want = sum(1 for a in m["animations"] for k, v in (a.get("events") or {}).items()
                       for f in (v if isinstance(v, list) else [v]) if isinstance(f, (int, float)) and f >= 0)
            got = sum(1 for s, _, _ in L["markers"] if any(s == x._path for x in anims.values()))
            if got != want:
                bad.append("%s: %d event markers, want %d" % (c["name"], got, want))
    if not L["levels"] or len(L["actors"]) != len(idx) + sum(1 for c in idx if c["fbx"]):
        bad.append("level %s, %d actors" % (L["levels"], len(L["actors"])))
    if [x for x in L["logs"] if x.startswith("WARNING")]:
        bad.append("warnings: %s" % [x for x in L["logs"] if x.startswith("WARNING")][:3])
    rec("8 Unreal import script (UE5 stand-in): flipbooks at their fps, sprites, skeletal mesh + animations, events, level",
        not bad, "; ".join(bad[:6]))


def raylib_checks(proj, rl):
    if not rl or not os.path.isfile(os.path.join(rl, "libraylib.a")):
        skip("9 raylib", "no raylib 5.5 build given (--raylib PATH_TO_raylib/src)"); return
    d = os.path.join(proj, "raylib")
    gl = tempfile.mkdtemp()
    for cand in ("/usr/lib/x86_64-linux-gnu/libGL.so.1", "/usr/lib/libGL.so.1"):
        if os.path.isfile(cand):
            os.symlink(cand, os.path.join(gl, "libGL.so"))
            break
    r = subprocess.run(["make", "-s", "RAYLIB_PATH=" + rl, "LDFLAGS=-L%s -L%s" % (rl, gl)], cwd=d, capture_output=True, text=True)
    if r.returncode:
        rec("9 raylib demos compile and run", False, r.stderr[-400:]); return
    n = len(open(os.path.join(d, "characters", "index.txt")).read().split())
    outs = []
    for exe in ("demo", "demo3d"):
        shot = os.path.join(gl, exe + ".png")
        r = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x720x24", "./" + exe, "--shot", shot], cwd=d,
                           capture_output=True, text=True, timeout=120)
        sf = [ln for ln in r.stdout.splitlines() if ln.startswith("SF_")]
        outs.append((sf[-1] if sf else r.stdout[-200:]) + (" (shot)" if os.path.isfile(shot) else " (no shot)"))
    ok = outs[0].startswith("SF_DEMO %d characters" % n) and outs[1].startswith("SF_DEMO3D %d models" % n) and all("(shot)" in o for o in outs)
    rec("9 raylib demos compile and run: %d characters, sprites and models" % n, ok, outs)


def web_check(proj):
    node = shutil.which("node")
    if not node:
        skip("10 web", "no node"); return
    d = os.path.join(proj, "web")
    js = os.path.join(tempfile.mkdtemp(), "w.js")
    port = 8790
    open(js, "w").write('''
const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage(); const errs = [];
 p.on('pageerror', e => errs.push(String(e)));
 await p.goto('http://localhost:%d/index.html');
 await p.waitForFunction(() => window.sfReady, null, {timeout: 30000});
 console.log(JSON.stringify({r: await p.evaluate(() => window.sfReady), errs})); await b.close(); })().catch(e => { console.log(JSON.stringify({err: String(e)})); process.exit(0); });
''' % port)
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        time.sleep(0.8)
        r = subprocess.run([node, js], capture_output=True, text=True, timeout=120)
    finally:
        srv.terminate()
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        skip("10 web", "playwright not available (%s)" % r.stderr[-120:]); return
    if "err" in out and "Cannot find module" in out["err"]:
        skip("10 web", "playwright not installed"); return
    n = len(json.load(open(os.path.join(d, "characters", "index.json"))))
    ok = out.get("r", {}).get("characters") == n and out.get("r", {}).get("moves", 0) >= 5 and not out.get("errs")
    rec("10 web page loads every character and move in a browser", ok, out)


def pygame_check(proj):
    try:
        import pygame  # noqa: F401
    except ImportError:
        skip("11 pygame", "pygame not installed"); return
    d = os.path.join(proj, "pygame")
    shot = os.path.join(tempfile.mkdtemp(), "p.png")
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    r = subprocess.run([sys.executable, "play.py", "--shot", shot], cwd=d, capture_output=True, text=True, timeout=120, env=env)
    n = len(json.load(open(os.path.join(d, "characters", "index.json"))))
    ok = r.returncode == 0 and ("SF_DEMO %d characters" % n) in r.stdout and os.path.isfile(shot)
    rec("11 pygame player runs and draws every character", ok, (r.stdout + r.stderr)[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", default=os.environ.get("SFS_GODOT", ""))
    ap.add_argument("--raylib", default=os.environ.get("SFS_RAYLIB", ""))
    ap.add_argument("--keep", default="")
    a = ap.parse_args()
    roster_checks()
    tmp = a.keep or tempfile.mkdtemp(prefix="sf_eng_")
    os.makedirs(tmp, exist_ok=True)
    try:
        rost = build_roster(tmp)
        if rost:
            proj = export_checks(tmp, rost)
            if proj:
                joints_check(proj)
                godot_checks(proj, a.godot)
                unity_checks(proj)
                unreal_checks(proj)
                raylib_checks(proj, a.raylib)
                web_check(proj)
                pygame_check(proj)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
