"""forge.py mocap / forge.py scan command lines."""
import argparse
import json
import os
import sys
import time

MOCAP_HELP = """forge.py mocap  -  your own video of a person (or puppet / mannequin) -> animated mannequin.

  --clip MOVE[:FRAMES]=VIDEO[@START-END]    repeatable (same syntax as forge.py video)
  --model lite|full|heavy    MediaPipe pose model (default full; heavy = slower, a bit steadier)
  --facing auto|side|front|mp   camera view of the person (auto: side-on is detected)
  --loop / --once MOVE       force loop / one-shot for a move (default from the move name)
  --name NAME --out DIR      the build that is made with the captured motions (mannequin mode; add --rig NAME|FILE
                             to drive a library / FBX / GLB rig instead)
  --kit KIT  --yaw 90 ...    everything else goes to forge.py build (e.g. --consoles snes,gba --no-fbx)
Writes out/<name>_mocap/<move>.json (keys), <move>_pose.json (raw landmarks), <move>_check.png.
Needs a Python 3.9-3.12 with mediapipe (see forge.py help mocap); the studio calls it as a helper.
"""

SCAN_HELP = """forge.py scan  -  orbit video -> photogrammetry -> mesh -> console LODs (NOT one-click).

  --video ORBIT.mp4      walk around the object / person (who agreed) 1-2 times, see help scan
  --frames N             frames to extract (default 80, sharpest per time slot)
  --run                  also run COLMAP (needs colmap on PATH; CPU = sparse + our hull/mesh; slow)
  --mask auto|none       cut the object from the background for the mesh step
  --mesh FILE            skip reconstruction: import a finished mesh (obj/ply/glb from Meshroom,
                         RealityScan, Polycam, COLMAP+OpenMVS ...) and make console LODs
  --budgets ps1=800,n64=1200,ps2=6000,hd=30000   triangle budgets (default list per console)
  --name NAME --out DIR
"""


def _strip(argv, flag, nargs=1):
    out, val, i = [], [], 0
    while i < len(argv):
        if argv[i] == flag:
            val.append(argv[i + 1] if nargs else True); i += 1 + nargs
        else:
            out.append(argv[i]); i += 1
    return out, val


def cmd_mocap(argv):
    ap = argparse.ArgumentParser(prog="forge.py mocap", description=MOCAP_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", action="append", required=True)
    ap.add_argument("--model", default="full", choices=["lite", "full", "heavy"])
    ap.add_argument("--facing", default="auto", choices=["auto", "side", "front", "mp"])
    ap.add_argument("--loop", action="append", default=[]); ap.add_argument("--once", action="append", default=[])
    ap.add_argument("--fix-swaps", dest="fix_swaps", action="store_true", help="repair left/right label swaps (off: it hurt on our tests)")
    ap.add_argument("--name", default="mocap_char"); ap.add_argument("--out", default="out")
    ap.add_argument("--consoles", default="")
    ap.add_argument("--no-build", dest="no_build", action="store_true")
    a, rest = ap.parse_known_args(argv)
    from . import mocap as MC
    from .video import parse_clip, LOCO
    from .moves import slug
    from .motions import find_motion
    work = os.path.join(a.out, slug(a.name) + "_mocap"); os.makedirs(work, exist_ok=True)
    files, moves = [], []
    for c in a.clip:
        mv, n, path, start, end, _ = parse_clip(c)
        key = slug(mv)
        lib = find_motion(key)
        loop = (key in a.loop) or (key not in a.once and (bool(lib and lib.loop) or any(k in key for k in LOCO)))
        print("mocap %s -> %s (%s)" % (os.path.basename(path), key, "loop" if loop else "one-shot"))
        pj = os.path.join(work, key + "_pose.json")
        try:
            d = MC.track(path, pj, a.model, start, end)
        except RuntimeError as e:
            print("mocap: %s" % e); return 2
        keys, rep, dbg = MC.analyse(d, key, loop, n or 8, facing=a.facing, swap_fix=a.fix_swaps)
        name = "mocap_" + key
        f = os.path.join(work, key + ".json")
        MC.save_keys(f, name, keys, loop, rep)
        MC.LIB[name] = MC.keys_motion(name, keys, loop)
        rep["check_sheet"] = MC.overlay_sheet(d, dbg, rep, os.path.join(work, key + "_check.png"))
        sel = rep["selection"]
        fps = 12
        if loop and sel.get("period_s"):
            fps = max(4, min(30, int(round((n or 8) / sel["period_s"]))))
        elif sel.get("span_s"):
            fps = max(4, min(30, int(round((n or 8) / max(0.2, sel["span_s"])))))
        print("  fitted %d frames in %.1fs (%.0f frames/s), mean bone direction error %.1f deg, facing %s, %s"
              % (rep["frames"], rep["fit_s"], rep["fit_fps"], rep["mean_bone_err_deg"], rep["facing"],
                 ("loop %.1f frames" % sel["period_frames"]) if loop else ("action frames %d-%d" % tuple(sel["span"]))))
        files.append(f); moves.append("%s=%s:%d:%d:%s" % (key, name, n or 8, fps, "loop" if loop else "once"))
    json.dump({"files": files, "moves": moves}, open(os.path.join(work, "mocap_meta.json"), "w"), indent=1)
    if a.no_build:
        return 0
    import forge
    # --rig LIB_NAME|FILE.fbx|FILE.glb in the rest args: the captured motion is retargeted onto that library rig instead
    base = ["build"] + ([] if ("--rig" in rest or any(r.startswith("--rig=") for r in rest)) else ["--mannequin"]) + \
        ["--moves", ",".join(moves), "--out", a.out]
    for f in files:
        base += ["--mocap", f]
    if "--yaw" not in rest:
        base += ["--yaw", "90"]
    rc = forge.main(base + ["--name", a.name] + rest)
    for c in [x.strip() for x in a.consoles.split(",") if x.strip()]:
        rc = forge.main(base + ["--name", "%s_%s" % (a.name, c), "--console", c, "--no-fbx"] + rest) or rc
    return rc


def main(argv):
    if argv[0] == "mocap":
        return cmd_mocap(argv[1:])
    from . import scan
    return scan.cli(argv[1:], SCAN_HELP)
