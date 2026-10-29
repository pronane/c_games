#!/usr/bin/env python3
"""v9 feature cost benchmark (same machine, empty cache each run).  usage: python tools/bench_v9.py [OUT.json]
Times the mannequin fighter14 build alone, then with each v9 option added on its own, then all of them together,
plus an NPC preset and the CLI tools (recolor / variants / atlas / qa / framedata / batch).  Mannequin only."""
import json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTJ = sys.argv[1] if len(sys.argv) > 1 else None
W = tempfile.mkdtemp(prefix="sfs_bench9_")


def run(args, fresh=True):
    shutil.rmtree(os.path.join(W, "cache"), ignore_errors=True)
    if fresh and "--out" in args and args[0] == "build":       # no re-use of an earlier output folder either
        shutil.rmtree(args[args.index("--out") + 1], ignore_errors=True)
    e = dict(os.environ, SFS_CACHE=os.path.join(W, "cache"))
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + args, capture_output=True, text=True, cwd=W, env=e)
    dt = time.time() - t
    if p.returncode and not (args[0] == "qa" and p.returncode == 1):   # qa exits 1 when it finds a FAIL
        print(p.stdout[-800:], p.stderr[-1500:])
        raise SystemExit("FAILED: %s" % " ".join(args))
    return dt


HD = ["--frame", "384x512", "--figure-h", "340", "--ground-y", "492"]      # HD-ish cells so per-frame costs show
BASE = ["build", "--mannequin", "--preset", "fighter14"] + HD + [ "--no-fbx", "--no-glb", "--expressions", "off", "--no-faces-sheet", "--no-qa"]
SC = [
    ("base: mannequin fighter14 (faces off, QA off)", []),
    ("+ expressions per move + faces.png", ["--expressions", "auto"]),
    ("+ faces.png only", ["--expressions", "auto", "--no-faces-sheet"]),
    ("+ talk line (mouth shapes)", ["--talk", "Ready to fight"]),
    ("+ colour set + hoops overlay", ["--recolor", "team_red", "--overlay", "top:hoops:#ffffff"]),
    ("+ variant seed 5 (as the character)", ["--variant", "5"]),
    ("+ 8 variants sheet", ["--variants", "8"]),
    ("+ FX passes (outline, cel, light)", ["--fx", "outline=2,cel=3,light=-1:-1:1"]),
    ("+ FX pixel pass", ["--fx", "pixel=4,colors=32"]),
    ("+ normal + emissive maps", ["--maps", "normal,emissive"]),
    ("+ frame data (hit/hurt boxes)", ["--framedata"]),
    ("+ foot locking (IK)", ["--footlock"]),
    ("+ blend idle>walk:3", ["--blend", "idle>walk:3"]),
    ("+ QA check", ["--qa"] if False else []),
]


def main():
    res = []
    for label, extra in SC:
        args = BASE + extra
        if label == "+ QA check":
            args = [a for a in BASE if a != "--no-qa"]
        dt = min(run(args + ["--out", os.path.join(W, "b")]) for _ in range(2))
        res.append((label, dt)); print("%-46s %6.1f s" % (label, dt), flush=True)
    run(BASE + ["--out", os.path.join(W, "b")])                 # leave a plain build for the tool timings
    base3d = ["build", "--mannequin", "--preset", "fighter14"] + HD + [ "--no-fbx", "--expressions", "off", "--no-faces-sheet", "--no-qa"]
    for label, args in (("3D: + GLB (base for LODs / physics)", base3d), ("3D: + GLB + 2 LODs + baked model", base3d + ["--lods", "2"]),
                        ("3D: + GLB, cloth/hair physics off", base3d + ["--no-physics"])):
        dt = min(run(args + ["--out", os.path.join(W, "b3")]) for _ in range(2))
        res.append((label, dt)); print("%-46s %6.1f s" % (label, dt), flush=True)
    allv9 = ["build", "--mannequin", "--preset", "fighter14"] + HD + [ "--no-fbx", "--expressions", "auto", "--talk", "Ready",
             "--recolor", "team_red", "--overlay", "top:hoops:#ffffff", "--variants", "8", "--fx", "outline=2,cel=3",
             "--maps", "normal,emissive", "--framedata", "--footlock", "--blend", "idle>walk:3", "--lods", "2", "--out", os.path.join(W, "all")]
    dt = run(allv9); res.append(("ALL v9 options together (+ GLB, LODs, QA)", dt)); print("ALL %.1f" % dt, flush=True)
    dt = run(["build", "--npc", "goblin"] + HD + ["--no-fbx", "--no-glb", "--out", os.path.join(W, "npc")])
    res.append(("NPC preset goblin (npc_creature moves)", dt))
    tools = [("forge.py recolor (palette swap of a build)", ["recolor", os.path.join(W, "all", "character"), "--set", "team_blue", "--out", os.path.join(W, "rc")]),
             ("forge.py variants --npc goblin -n 12", ["variants", "--npc", "goblin", "-n", "12", "--out", os.path.join(W, "var")]),
             ("forge.py atlas (3 characters)", ["atlas", os.path.join(W, "all", "character"), os.path.join(W, "npc", "goblin"), os.path.join(W, "b", "character"), "--out", os.path.join(W, "pack")]),
             ("forge.py qa (fighter14 build)", ["qa", os.path.join(W, "b", "character")]),
             ("forge.py framedata (fighter14 build)", ["framedata", os.path.join(W, "b", "character")])]
    for label, args in tools:
        if not os.path.isdir(args[1]) and args[0] in ("recolor", "qa", "framedata"):
            print("skip", label, args[1]); continue
        t = time.time()
        try:
            dt = run(args)
        except SystemExit as e:
            print(e); continue
        res.append((label, dt)); print("%-46s %6.1f s" % (label, dt), flush=True)
    if OUTJ:
        json.dump([{"scenario": a, "secs": round(b, 2)} for a, b in res], open(OUTJ, "w"), indent=1)
    shutil.rmtree(W, ignore_errors=True)


if __name__ == "__main__":
    main()
