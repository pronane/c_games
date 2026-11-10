"""forge.py motion — list / record / import / retarget / clean, and character types.

The library is the shared skeleton (semantic pose keys). Record goes through
sforge/mocap.py. Import goes through the FBX/GLB readers or the BVH reader, then
the existing retargeter onto the mannequin. Retarget goes back out through the
same retargeter. Clean-up writes foot planting, weight shift, anticipation and
follow-through into the stored clip.
"""
from __future__ import annotations
import argparse
import json
import os

from . import motionlib as ML
from .library import validate_licence


def _lic_args(p):
    g = p.add_argument_group("licence (stored on the move; required before you pack it)")
    g.add_argument("--spdx", help="SPDX id, e.g. CC0-1.0. Do not import a clip whose licence is not free for this project.")
    g.add_argument("--author")
    g.add_argument("--source-url", dest="source_url")
    g.add_argument("--redistribution", choices=["yes", "no", "unknown"])
    g.add_argument("--attribution")
    g.add_argument("--notes")


def _lic_from(a):
    lic = ML._licence()
    for k in ("spdx", "author", "source_url", "redistribution", "attribution", "notes"):
        v = getattr(a, k, None)
        if v is not None:
            lic[k] = v
    return lic


def _print_move(rec, path):
    lic = rec.get("licence") or {}
    keys = rec.get("keys") or []
    print("  %-16s %-10s %3d keys  %-5s  %-22s  %s" % (
        rec.get("name"), rec.get("category") or "-", len(keys),
        "loop" if rec.get("loop") else "once",
        (rec.get("source") or "-")[:22],
        lic.get("spdx") or "no spdx"))
    if path:
        print("    %s" % path)


def main(argv):
    argv = list(argv)
    # Accepted before or after the subcommand: forge.py motion record --library DIR
    library = None
    if "--library" in argv:
        i = argv.index("--library")
        if i + 1 >= len(argv):
            print("error: --library needs a folder")
            return 2
        library = argv[i + 1]
        del argv[i:i + 2]
    p = argparse.ArgumentParser(prog="forge.py motion", description=(
        "Shared-skeleton motion library (v11.4). One clip can be recorded, imported, "
        "cleaned, stored, and retargeted onto any mapped character. "
        "Character types (timing / stance / reach / weight) are JSON files, applied at build time with --character-type."))
    p.add_argument("--library", help="folder to write into, searched before the shipped starter (default library/motions or $SFS_MOTIONS)")
    sub = p.add_subparsers(dest="act")
    ls = sub.add_parser("list", help="shipped starter + your clips")
    ls.add_argument("--json", action="store_true")
    sh = sub.add_parser("show", help="one move: source, licence, clean-up, first and last pose")
    sh.add_argument("name")
    rec = sub.add_parser("record", help="video -> mocap -> library, or store an existing mocap keys JSON",
                         epilog="--library DIR may be placed before or after the subcommand.")
    rec.add_argument("--clip", help="MOVE[:FRAMES]=VIDEO  (same as forge.py mocap; needs MediaPipe)")
    rec.add_argument("--keys", help="mocap keys JSON already written by forge.py mocap (no video needed)")
    rec.add_argument("--folder", help="v11.5: a folder of clips (punch.mp4, walk.mp4, or a pose-track .json). One import, one named set.")
    rec.add_argument("--set", dest="set_name", help="name for that set (required with --folder)")
    rec.add_argument("--keep-temp", dest="keep_temp", action="store_true",
                     help="keep the tracker JSON under the set's _temp/ (a pose trace — do not pack it). Default: delete it.")
    rec.add_argument("--strict", action="store_true",
                     help="with --folder: a clip without the opening T-pose is a reshoot (default: a note; the whole take is used)")
    rec.add_argument("--name", help="library name (default: the move name)")
    rec.add_argument("--model", default="full", choices=["lite", "full", "heavy"])
    rec.add_argument("--facing", default="auto", choices=["auto", "side", "front", "mp"])
    rec.add_argument("--loop", action="store_true")
    rec.add_argument("--once", action="store_true")
    _lic_args(rec)
    im = sub.add_parser("import", help="BVH / FBX / GLB / mocap JSON -> one library move on the shared skeleton",
                        epilog="--library DIR may be placed before or after the subcommand.")
    im.add_argument("file")
    im.add_argument("--name")
    im.add_argument("--clip", help="which take inside an FBX / GLB (default: the first)")
    im.add_argument("--loop", action="store_true")
    im.add_argument("--once", action="store_true")
    im.add_argument("--start", type=float, help="seconds into the take where the move starts (mocap takes are long)")
    im.add_argument("--end", type=float, help="seconds into the take where the move ends")
    im.add_argument("--no-cycle", dest="no_cycle", action="store_true",
                    help="a --loop move is cut to its best loop inside start..end unless this is given")
    im.add_argument("--peak", help="cut one strike out of a long take: BONE[:BEFORE:AFTER] e.g. hand_R:0.35:0.35 "
                    "(the frame where that bone is furthest in front of the hips, inside start..end)")
    im.add_argument("--raw", action="store_true", help="v11.4 behaviour: no cut, turn, floor or resample")
    _lic_args(im)
    rt = sub.add_parser("retarget", help="library move -> a library rig or an FBX / GLB file")
    rt.add_argument("name")
    rt.add_argument("--to", required=True, help="library rig name, or a .fbx / .glb path")
    rt.add_argument("--out", help="write the target with the new clip as .glb or .fbx")
    rt.add_argument("--save", action="store_true", help="store the clip on a library rig (not a loose file)")
    rt.add_argument("--root-motion", dest="root_motion", choices=["keep", "inplace", "root"], default="keep")
    rt.add_argument("--character-type", dest="character_type", help="perform the clip in this type (character_types/*.json or a path)")
    rt.add_argument("--no-plant", dest="no_plant", action="store_true", help="do not plant the canonical feet on the target")
    cl = sub.add_parser("clean", help="foot plant, weight shift, anticipation, follow-through — written back into the clip")
    cl.add_argument("name")
    cl.add_argument("--no-feet", dest="no_feet", action="store_true")
    cl.add_argument("--no-weight", dest="no_weight", action="store_true")
    cl.add_argument("--no-anticipation", dest="no_anticipation", action="store_true")
    cl.add_argument("--no-follow", dest="no_follow", action="store_true")
    sub.add_parser("sets", help="v11.5: named motion sets (skeleton only) and which one is the default")
    use = sub.add_parser("use-set", help="v11.5: make a set the default source for builds (or --off)")
    use.add_argument("name", nargs="?", help="set name. Omit with --off to clear.")
    use.add_argument("--off", action="store_true", help="builds do not read a saved default set")
    shot = sub.add_parser("shotlist", help="v11.5: printable checklist of clips to film for a game pack")
    shot.add_argument("--game", required=True, help="pack name or a path (forge.py game list)")
    shot.add_argument("--out", help="also write the checklist to this text file")
    sub.add_parser("types", help="list character types (timing, stance, reach, weight)")
    ts = sub.add_parser("type", help="show one character type")
    ts.add_argument("name")
    a = p.parse_args(argv)
    if library is not None:
        a.library = library
    try:
        return _run(a, p)
    except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:
        print("error:", e.args[0] if e.args else e)
        return 2


def _peak(txt):
    if not txt:
        return None
    t = txt.split(":")
    b = t[0]
    pre = float(t[1]) if len(t) > 1 and t[1] else 0.35
    post = float(t[2]) if len(t) > 2 and t[2] else pre
    return (b, pre, post)


def _run(a, p):
    if a.act in (None, "list"):
        lib = ML.open_library(a.library)
        rows = []
        for n in lib.names():
            rec = lib.load(n)
            rows.append(rec)
        if getattr(a, "json", False):
            print(json.dumps([{k: rec.get(k) for k in ("name", "category", "loop", "source", "origin", "licence")} for rec in rows], indent=1))
            return 0
        print("motion library: %s" % " + ".join(lib.dirs))
        print("  %-16s %-10s %s  %-5s  %-22s  %s" % ("name", "category", "keys", " ", "source", "licence"))
        for rec in rows:
            _print_move(rec, rec.get("_path"))
        if not rows:
            print("  (empty) — the starter is motion_library/ next to forge.py")
        print("character types: " + ", ".join(__import__("sforge.chartypes", fromlist=["list_types"]).list_types()))
        return 0
    if a.act == "show":
        rec = ML.load_move(a.name, a.library)
        print("%s  [%s]  %s  %d keys  %.2fs" % (rec["name"], rec.get("category"), "loop" if rec.get("loop") else "once",
                                                len(rec["keys"]), float(rec.get("duration") or 0)))
        print("  source: %s" % rec.get("source"))
        print("  %s" % (rec.get("desc") or ""))
        lic = rec.get("licence") or {}
        print("  licence: %s  author: %s  redistribute: %s" % (lic.get("spdx") or "?", lic.get("author") or "?", lic.get("redistribution")))
        probs = validate_licence(lic)
        if probs:
            print("  licence incomplete: " + "; ".join(probs))
        if rec.get("import"):
            print("  import: %s" % json.dumps(rec["import"]))
        if rec.get("cleanup"):
            print("  cleanup: %s" % json.dumps(rec["cleanup"]))
        t0, p0 = rec["keys"][0]
        t1, p1 = rec["keys"][-1]
        print("  t=%.2f  %s" % (t0, _brief(p0)))
        print("  t=%.2f  %s" % (t1, _brief(p1)))
        return 0
    if a.act == "record":
        lic = _lic_from(a)
        loop = True if a.loop else (False if a.once else None)
        if getattr(a, "folder", None):
            if not a.set_name:
                print("record --folder needs --set NAME  (the clips become that motion set)")
                return 2
            from . import session
            rep = session.import_folder(a.folder, a.set_name, library=a.library, keep_temp=a.keep_temp, licence=lic,
                                        strict=getattr(a, "strict", False))
            print(rep["text"], end="")
            print("Video, frames, face and body shape were not stored.")
            return 1 if rep["rejected"] else 0
        if a.keys:
            rec, out, probs = ML.record_keys(a.keys, name=a.name, path=a.library, loop=loop, licence=lic)
        elif a.clip:
            rec, out, probs = ML.record_video(a.clip, path=a.library, model=a.model, facing=a.facing,
                                             licence=lic, name=a.name, loop=loop)
        else:
            print("record needs --clip MOVE=VIDEO or --keys keys.json")
            return 2
        print("recorded %s -> %s  (%d keys)" % (rec["name"], out, len(rec["keys"])))
        _warn_lic(probs)
        return 0
    if a.act == "import":
        lic = _lic_from(a)
        loop = True if a.loop else (False if a.once else None)
        rec, out, probs = ML.import_file(a.file, name=a.name, clip=a.clip, library=a.library, licence=lic, loop=loop,
                                         start=a.start, end=a.end, cycle=False if a.no_cycle else None, raw=a.raw,
                                         peak=_peak(a.peak))
        info = rec.get("import") or {}
        print("imported %s -> %s  (%d keys, %.2fs, pose error mean %.3f m)" % (
            rec["name"], out, len(rec["keys"]), float(rec.get("duration") or 0), info.get("projection_mean_m") or 0))
        if info.get("canonical"):
            c = info["canonical"]
            print("  cut %.2f-%.2fs%s, turned %+.0f deg to face forward, %g fps" % (
                c["cut_s"][0], c["cut_s"][1], (", loop %.2f-%.2fs" % tuple(c["cycle_s"])) if c.get("cycle_s") else "",
                c["turned_deg"], c["fps"]))
        if info.get("note"):
            print("  " + info["note"])
        _warn_lic(probs)
        return 0
    if a.act == "retarget":
        tgt, cl, rep = ML.retarget_motion(a.name, a.to, path=a.library, character_type=a.character_type,
                                          root_motion=a.root_motion, plant=not a.no_plant)
        print("  %s -> %s   %d frames  leg ratio %.3f  bone-direction error mean %s / max %s deg  (%s common bones)" % (
            a.name, cl.name, cl.frames, rep.get("leg_ratio") or 0, rep.get("mean_dir_err_deg"), rep.get("max_dir_err_deg"),
            rep.get("common_bones")))
        plant = rep.get("plant") or {}
        if plant.get("applied"):
            print("  foot plant on canonical legs: slide %.2f cm -> %.2f cm. %s" % (
                plant.get("before_cm") or 0, plant.get("after_cm") or 0, plant.get("note") or ""))
        elif plant.get("reason"):
            print("  foot plant skipped: %s" % plant["reason"])
        if a.out:
            from . import rigrec as RR
            glb = a.out if a.out.lower().endswith(".glb") else os.path.splitext(a.out)[0] + ".tmp.glb"
            RR.write_glb(tgt, glb, [cl.name], root_motion=a.root_motion)
            if a.out.lower().endswith(".fbx"):
                from . import fbx as F
                F.write_fbx_from_glb(glb, a.out)
                os.remove(glb)
            print("wrote", a.out)
        if a.save:
            if os.path.isfile(a.to):
                print("--save needs a library rig name (forge.py library add the file first)")
                return 2
            from . import library as L
            lib = L.Library()
            k, n = lib.find(a.to)
            tgt.save(lib.path(k, n))
            lib.scan(import_inbox=False)
            print("saved clip %s on %s/%s" % (cl.name, k, n))
        return 0
    if a.act == "clean":
        rec, report, out = ML.clean_move(a.name, a.library, feet=not a.no_feet, weight=not a.no_weight,
                                         anticipation=not a.no_anticipation, follow=not a.no_follow)
        print("cleaned %s -> %s" % (rec["name"], out))
        foot = report.get("foot") or {}
        if foot:
            print("  feet: slide %.2f cm -> %.2f cm  (%d leg-frames refit)" % (
                foot.get("before_cm") or 0, foot.get("after_cm") or 0, foot.get("fitted_legs") or 0))
        if "anticipation_deg" in report:
            print("  anticipation pull: %.1f deg" % report["anticipation_deg"])
        if "followthrough_deg" in report:
            print("  follow-through: %.1f deg" % report["followthrough_deg"])
        if "weight_shift_m" in report:
            print("  weight shift: %.3f m" % report["weight_shift_m"])
        print("  " + report.get("note", ""))
        return 0
    if a.act == "sets":
        from . import motionset as MS
        print("motion sets: %s" % MS.sets_root(None))
        names = MS.list_sets(None)
        default = MS.saved_default(None)
        if not names:
            print("  (none yet)  forge.py motion record --folder CLIPS --set my_moves")
        for n in names:
            mark = "  default" if n == default else ""
            print("  %-20s%s" % (n, mark))
        if default and default not in names:
            print("  saved default '%s' is missing — forge.py motion use-set --off" % default)
        elif not default:
            print("no default set (builds use the starter / procedural motions unless you pass --motion-set)")
        return 0
    if a.act == "use-set":
        from . import motionset as MS
        try:
            label = MS.set_default("" if a.off else (a.name or ""), None)
        except FileNotFoundError as e:
            print("error:", e)
            return 2
        if not label:
            print("default motion set cleared")
        else:
            print("default motion set: %s" % label)
            print("Builds read that set first. Missing moves come from the starter, then the procedural motion.")
            print("The set is skeleton JSON only. forge.py build --motion-set off ignores it for one build.")
        return 0
    if a.act == "shotlist":
        from . import gamepack
        try:
            text = gamepack.shotlist(a.game)
        except (ValueError, FileNotFoundError, OSError) as e:
            print("error:", e)
            return 2
        print(text, end="")
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote", a.out)
        return 0
    if a.act == "types":
        from . import chartypes as CT
        print("%-16s %7s %7s %7s %7s  %s" % ("type", "timing", "stance", "reach", "weight", "label"))
        for t in CT.all_types():
            print("%-16s %7.2f %7.2f %7.2f %7.2f  %s" % (t["name"], t["timing"], t["stance"], t["reach"], t["weight"], t["label"]))
        print("Add one by dropping a JSON file in character_types/ (timing, stance, reach, weight).")
        return 0
    if a.act == "type":
        from . import chartypes as CT
        t = CT.load(a.name)
        print("%s — %s" % (t["name"], t["label"]))
        print("  timing %.2f   stance %.2f   reach %.2f   weight %.2f" % (t["timing"], t["stance"], t["reach"], t["weight"]))
        if t["games"]:
            print("  games: " + ", ".join(t["games"]))
        if t["notes"]:
            print("  " + t["notes"])
        print("  " + t["path"])
        return 0
    p.print_help()
    return 2


def _brief(pose):
    bits = []
    for k in ("arm_R", "leg_R", "knee_R", "hips"):
        if k in pose:
            v = pose[k]
            if isinstance(v, (tuple, list)):
                bits.append("%s=%s" % (k, ",".join("%.0f" % float(x) for x in list(v)[:3])))
            else:
                bits.append("%s=%.0f" % (k, float(v)))
    return "  ".join(bits)


def _warn_lic(probs):
    if probs:
        print("  licence incomplete (" + "; ".join(probs) + ") — fine for a local test, not for a pack. Set --spdx and --author.")
    else:
        print("  licence record complete")
