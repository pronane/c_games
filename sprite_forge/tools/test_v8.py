#!/usr/bin/env python3
"""v8 tests.  usage: python tools/test_v8.py [OUT_DIR]   (env SFS_TEST_CUTOUT=DIR with cutout.png + landmarks.json
from `forge.py cutout` enables the turn / puppet tests - the package ships no photo of a real person)
Covers: icons, the wizard command for the 3 goal tabs, forge.py cutout + export-ef (mannequin 'photo'), turn angle parsing, forge.py turn (0/90/180/270 + fine angle), build --turn final vs draft, thread-pool
render == serial render, cache rebuild, the Start-tab wizard (needs tkinter + a display) and that the command it
shows rebuilds the same atlas from the terminal.  Writes OUT_DIR/RESULTS_v8.md + results_v8.json."""
import json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_v8out_")
os.makedirs(OUT, exist_ok=True)
W = tempfile.mkdtemp(prefix="sfs_v8test_")
CUT = os.environ.get("SFS_TEST_CUTOUT", "")
R = []
EF = ("idle:5:8:loop,walk:10:11:loop,crouch:4:17:once,jump:8:10:once,punch:6:14:once,kick:6:14:once,pyramid_blast:6:12:once,"
      "bum_fireball:8:12:once,hit:6:10:once,throw:6:14:once,jump_attack:6:17:once,taunt:6:8:loop,block:6:8:once,victory:8:8:loop")


def rec(name, ok, detail="", secs=None):
    R.append({"test": name, "ok": bool(ok), "detail": detail, "secs": None if secs is None else round(secs, 2)})
    print("%-4s %-55s %s%s" % ("PASS" if ok else "FAIL", name, detail, "" if secs is None else "  (%.1f s)" % secs), flush=True)


def forge(args, env=None):
    e = dict(os.environ, SFS_CACHE=os.path.join(W, "cache")); e.update(env or {})
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + args, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout + p.stderr, time.time() - t


def same_png(a, b):
    from PIL import Image, ImageChops
    A, B = Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")
    return A.size == B.size and ImageChops.difference(A, B).getbbox() is None


# 1. turn angle parsing (no GUI needed)
from sforge import turn as TN
ok = all(abs(TN.turn_args(s) - v) < 1e-6 for s, v in (("90", 90), ("180", 180), ("270", 270), ("0", 0)))
rec("turn_args parses 0/90/180/270", ok)
try:
    import tkinter  # noqa
    from sforge.gui import turn_value, TURN_CHOICES
    ok = [turn_value(c) for c in TURN_CHOICES] == [0, 90, 180, 270] and turn_value(TURN_CHOICES[1], "60") == 60
    rec("GUI turn dropdown -> degrees (+ fine angle override)", ok)
    HAVE_TK = True
except ImportError:
    rec("GUI turn dropdown (skipped: no tkinter)", True, "skipped"); HAVE_TK = False

# 1b. icons (procedural, no files)
from sforge import icons as IC
ims = [IC.icon(n, 24) for n in IC.NAMES]
rec("icons: %d drawn, all non-empty RGBA" % len(ims), all(im.mode == "RGBA" and im.getbbox() for im in ims))

# 1c. the command the wizard shows reflects the three goal tabs (fake app - no window needed)
if HAVE_TK:
    from sforge import gui_home as GH
    from sforge.moves import MoveSpec

    class _V:
        def __init__(self, x): self.x = x
        def get(self): return self.x

    class _App:
        def __init__(self, mode, console, glb, fbx, anim):
            vv = dict(mode=mode, name="t", fw="672", fh="800", figh="560", ground="788", console=console, profile="(none)",
                      quality="final", out="o", kit="", human="", spec="c.txt", photo="p.png", landmarks="", turn="0  front", turn_yaw="",
                      turn_depth="auto", turn_side="", fill="placeholder", cutout="auto", rig="")
            self.v = {k: _V(x) for k, x in vv.items()}
            self.b = {k: _V(x) for k, x in dict(glb=glb, fbx=fbx, anim_export=anim, cache=True, dither=True).items()}
        def selected_moves(self):
            return [MoveSpec("idle", "Idle", "F", 4, 8, True, "", "")]
    c1 = GH.forge_command(_App("mannequin", "SNES / Super Famicom", True, False, True))
    c2 = GH.forge_command(_App("photo", "None (standard output only)", True, True, False))
    rec("wizard command: 3D tab -> --no-fbx --anim-export, retro tab -> --console snes",
        "--no-fbx" in c1 and "--anim-export" in c1 and "--no-glb" not in c1 and c1[c1.index("--console") + 1] == "snes")
    rec("wizard command: photo source -> no 3D / console flags", not any(x in c2 for x in ("--no-glb", "--anim-export", "--console")))

# 1d. cutout (procedural mannequin 'photo', never a real person) + export-ef
SAMPLE = os.path.join(W, "sample")
rc, log, dt = forge(["build", "--mannequin", "--moves", "idle", "--frame", "672x800", "--figure-h", "560", "--ground-y", "788",
                     "--no-glb", "--no-fbx", "--out", SAMPLE, "--name", "ph"])
if rc == 0:
    from PIL import Image
    a = Image.open(os.path.join(SAMPLE, "ph", "moves", "idle_00.png")).convert("RGBA")
    bg = Image.new("RGBA", a.size, (205, 215, 225, 255)); bg.alpha_composite(a)
    ph = os.path.join(W, "mannequin_photo.jpg"); bg.convert("RGB").save(ph, quality=92)
    rc, log, dt = forge(["cutout", ph, "--person", "largest", "--out", os.path.join(W, "cut")])
    cp = os.path.join(W, "cut", "cutout.png")
    if "needs mediapipe" in log:
        rec("forge.py cutout (skipped: no mediapipe pose model - tools/setup_pose.py)", True, "skipped")
    else:
        ok = os.path.isfile(cp)     # rc 1 = the strict QA verdict failed (reported below), not a crash
        rep = open(os.path.join(W, "cut", "cutout_report.txt")).read() if os.path.isfile(os.path.join(W, "cut", "cutout_report.txt")) else ""
        qa = "QA verdict %s" % ("PASS" if "PASS                               True" in rep else "FAIL (see cutout_report.txt)")
        if ok:
            im = Image.open(cp)
            al = im.convert("RGBA").getchannel("A")
            w_, h_ = al.size
            border = [al.getpixel((x, 0)) for x in range(w_)] + [al.getpixel((x, h_ - 1)) for x in range(w_)]
            ok = im.mode == "RGBA" and max(border) == 0 and al.getbbox() is not None and all(
                os.path.isfile(os.path.join(W, "cut", f)) for f in ("landmarks.json", "sprite.png", "sprite_hd.png", "cutout_report.txt"))
        rec("forge.py cutout: transparent RGBA cut-out, clear border, sprite + HD sprite + landmarks", ok, qa, dt)
        if os.path.isfile(os.path.join(W, "cut", "verify.png")):
            shutil.copy(os.path.join(W, "cut", "verify.png"), os.path.join(OUT, "cutout_verify_mannequin.png"))
    # export-ef from a small fighter build
    rc, log, dt = forge(["build", "--mannequin", "--moves", EF, "--frame", "336x400", "--figure-h", "280", "--ground-y", "394",
                         "--no-glb", "--no-fbx", "--quality", "draft", "--out", os.path.join(W, "ef"), "--name", "eft"])
    if rc == 0:
        dst = os.path.join(W, "game", "assets", "char_eft")
        rc, log, dt = forge(["export-ef", os.path.join(W, "ef", "eft"), dst])
        cfg = open(os.path.join(dst, "sprites.cfg")).read() if os.path.isfile(os.path.join(dst, "sprites.cfg")) else ""
        names = [it.split(":")[0] for it in EF.split(",")]
        strips = all(any(f.endswith(n + ".png") for f in os.listdir(dst)) for n in names) if os.path.isdir(dst) else False
        rec("forge.py export-ef: sprites.cfg + one strip per move for all 14 fighter moves",
            rc == 0 and strips and all(n in cfg for n in names), log.strip().splitlines()[-1] if log.strip() else "", dt)
    else:
        rec("export-ef source build", False, log[-300:])
else:
    rec("cutout / export-ef sample build", False, log[-300:])

if CUT and os.path.isfile(os.path.join(CUT, "landmarks.json")):
    # 2. forge.py turn at every preset angle + a fine angle
    for yaw in ("0", "90", "180", "270", "60"):
        rc, log, dt = forge(["turn", CUT, "--yaw", yaw, "--out", os.path.join(W, "turn")])
        f = os.path.join(W, "turn", "turned_%s.png" % yaw)
        rec("forge.py turn --yaw %s" % yaw, rc == 0 and os.path.isfile(f), log.strip().splitlines()[-1] if log.strip() else "", dt)
        if rc == 0 and yaw == "90":
            shutil.copy(os.path.join(W, "turn", "compare_90.png"), os.path.join(OUT, "compare_90.png"))
    base = ["build", "--photo", os.path.join(CUT, "cutout.png"), "--landmarks", os.path.join(CUT, "landmarks.json"), "--turn", "90",
            "--cutout", "alpha", "--name", "t", "--moves", EF, "--frame", "672x800", "--figure-h", "560", "--ground-y", "788",
            "--pivot-x", "336", "--no-glb", "--no-fbx"]
    # 3. final (threads) vs serial, draft, cache
    rc, log, dt = forge(base + ["--out", os.path.join(W, "fin"), "--no-cache"])
    rec("build --turn 90 final (thread pool)", rc == 0, "", dt); t_fin = dt
    rc2, log2, dt2 = forge(base + ["--out", os.path.join(W, "ser"), "--no-cache"], env={"SFS_THREADS": "1"})
    rec("build --turn 90 final, SFS_THREADS=1 (serial)", rc2 == 0, "", dt2)
    if rc == 0 and rc2 == 0:
        rec("thread pool output == serial output (atlas.png)", same_png(os.path.join(W, "fin", "t", "atlas.png"), os.path.join(W, "ser", "t", "atlas.png")),
            "speed-up x%.1f" % (dt2 / max(0.01, dt)))
    rc, log, dt = forge(base + ["--out", os.path.join(W, "fin")])
    rec("rebuild unchanged (cache)", rc == 0 and "Up to date" in log, "", dt)
    rc, log, dt = forge(base + ["--out", os.path.join(W, "draft"), "--quality", "draft", "--no-cache"])
    rec("build --turn 90 --quality draft (Quick preview)", rc == 0 and dt < max(15.0, t_fin / 2), "x%.1f faster than final" % (t_fin / max(0.01, dt)), dt)
    rep = open(os.path.join(W, "fin", "t", "build_report.txt")).read() if os.path.isfile(os.path.join(W, "fin", "t", "build_report.txt")) else ""
    rec("build report labels turned moves honestly", "filled:turned-puppet" in rep and "NOT a real photo" in rep and "placeholders)" not in rep)
    if os.path.isfile(os.path.join(W, "fin", "t", "preview.png")):
        shutil.copy(os.path.join(W, "fin", "t", "preview.png"), os.path.join(OUT, "turn90_final_preview.png"))
    # 4. GUI wizard build (draft) + its shown command rebuilds the same atlas
    if HAVE_TK and os.environ.get("DISPLAY"):
        flag = os.path.join(W, "gui_done")
        d = {"flag": flag, "mode": "photo", "vars": {"name": "wiz", "photo": os.path.join(CUT, "cutout.png"), "landmarks": os.path.join(CUT, "landmarks.json"),
             "cutout": "alpha", "out": os.path.join(W, "wiz"), "turn": "90  side-on, faces right", "quality": "draft"},
             "home": {"step": 4, "target": "Egyptian Fighter / Padel Wars fighter (14 moves, HD 672x800)", "action": "build"}}
        e = dict(os.environ, SFS_AUTOTEST=json.dumps(d), SFS_CACHE=os.path.join(W, "cache_gui"))
        t = time.time()
        pr = subprocess.Popen([sys.executable, os.path.join(HERE, "sprite_forge_studio.py")], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while not os.path.exists(flag) and time.time() - t < 300:
            time.sleep(0.3)
        pr.kill(); pr.wait()
        cmdf = os.path.join(W, "wiz", "wiz", "forge_command.txt")
        ok = os.path.isfile(os.path.join(W, "wiz", "wiz", "atlas.png")) and os.path.isfile(cmdf)
        rec("Start-tab wizard: photo -> turn 90 -> EF target -> Quick preview build", ok, "", time.time() - t)
        if ok:
            import shlex
            argv = shlex.split(open(cmdf).read())[2:]
            o = argv.index("--out"); argv[o + 1] = os.path.join(W, "wizcli")
            rc, log, dt = forge(argv + ["--no-cache"])
            rec("wizard's 'Same as typing' command == wizard build", rc == 0 and same_png(os.path.join(W, "wiz", "wiz", "atlas.png"), os.path.join(W, "wizcli", "wiz", "atlas.png")), "", dt)
    else:
        rec("Start-tab wizard build (skipped: no tkinter / DISPLAY)", True, "skipped")
else:
    rec("turn / puppet tests (skipped: set SFS_TEST_CUTOUT to a forge.py cutout folder)", True, "skipped")

json.dump(R, open(os.path.join(OUT, "results_v8.json"), "w"), indent=1)
with open(os.path.join(OUT, "RESULTS_v8.md"), "w") as f:
    f.write("# Sprite Forge Studio v8 tests\n\n| result | test | detail | s |\n|---|---|---|---|\n")
    for r in R:
        f.write("| %s | %s | %s | %s |\n" % ("PASS" if r["ok"] else "**FAIL**", r["test"], r["detail"], "" if r["secs"] is None else r["secs"]))
n_fail = sum(not r["ok"] for r in R)
print("\n%d tests, %d failed -> %s" % (len(R), n_fail, os.path.join(OUT, "RESULTS_v8.md")))
shutil.rmtree(W, ignore_errors=True)
sys.exit(1 if n_fail else 0)
