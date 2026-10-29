#!/usr/bin/env python3
"""Timing benchmark (same inputs, same machine).  usage: python tools/bench_v8.py [STUDIO_DIR] [OUT.json] [--quick-only]
Runs each scenario twice: 'first' (fresh output + empty cache) and 'rebuild' (same command again, nothing changed),
plus 'one move changed' where it applies.  STUDIO_DIR lets the same script time an older version (v7) for comparison."""
import json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIO = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else HERE
OUTJ = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
W = tempfile.mkdtemp(prefix="sfs_bench_")
PHOTO = os.path.join(W, "photo_mannequin.png")


def run(args, env=None):
    e = dict(os.environ, SFS_CACHE=os.path.join(W, "cache"), SFS_LIBRARY=os.path.join(STUDIO, "library"))
    e.update(env or {})
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(STUDIO, "forge.py")] + args, capture_output=True, text=True, cwd=W, env=e)
    dt = time.time() - t
    if p.returncode:
        print(p.stdout[-800:], p.stderr[-1500:])
        raise SystemExit("FAILED: %s" % " ".join(args))
    return dt


# a procedural 'photo' (a mannequin render - never a real person)
run(["build", "--mannequin", "--moves", "idle", "--frame", "512x512", "--no-glb", "--no-fbx", "--out", W, "--name", "ph"])
shutil.copy(os.path.join(W, "ph", "moves", "idle_00.png"), PHOTO)
V = os.path.join(STUDIO, "examples_video")
SC = [
    ("spec fighter14 + SNES console", ["build", "--mannequin", "--preset", "fighter14", "--console", "snes", "--no-fbx"], ["--set-move", "punch:frames=8"]),
    ("photo fighter14", ["build", "--photo", PHOTO, "--preset", "fighter14", "--no-glb", "--no-fbx"], None),
    ("library rig fighter14 (3D render)", ["build", "--rig", "sample_stocky", "--preset", "fighter14", "--no-fbx"], None),
    ("mannequin gaelic36 + GLB + FBX", ["build", "--mannequin", "--preset", "gaelic36"], ["--set-move", "tackle:frames=10"]),
    ("video -> sprites (2 clips)", ["video", "--clip", "walk=" + os.path.join(V, "walk_static.mp4"), "--clip", "punch=" + os.path.join(V, "punch_green.mp4"), "--no-fbx"], None),
]
quick = ("UI quick preview (fighter14 draft)", ["build", "--mannequin", "--preset", "fighter14", "--no-fbx", "--no-glb"], ["--quality", "draft"])
v8 = os.path.exists(os.path.join(STUDIO, "sforge", "cache.py"))
res = []
for name, args, changed in SC + [quick]:
    o = os.path.join(W, "o_" + str(len(res)))
    base = args + ["--out", o, "--name", "c%d" % len(res)]
    row = {"scenario": name}
    if changed == ["--quality", "draft"]:
        row["first"] = run(base + (changed if v8 else []))
        res.append(row); print(row); continue
    row["first"] = run(base)
    row["rebuild"] = run(base)
    if changed and v8:
        row["one_move_changed"] = run(base + changed)
    res.append(row); print(row); sys.stdout.flush()
if OUTJ:
    json.dump({"studio": STUDIO, "cpus": os.cpu_count(), "results": res}, open(OUTJ, "w"), indent=1)
shutil.rmtree(W, ignore_errors=True)
