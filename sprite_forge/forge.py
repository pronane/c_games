#!/usr/bin/env python3
"""Sprite Forge Studio - command line + GUI launcher.

  python forge.py                      -> opens the visual studio (tkinter)
  python forge.py gui
  python forge.py build --spec char.txt
  python forge.py build --photo front.png --back back.png --name qanna
  python forge.py build --photo front.png --video walk=walk.mp4 --video run=run_frames/ --name qanna
  python forge.py build --frames my_frames/ --name hero          (<move>/ folders or <move>_<N>.png)
  python forge.py build --sheet sheet.png --sheet-layout rows --name hero
  python forge.py build --preset gaelic36 --kit away --name away_player      (default mannequin)
  python forge.py build --photo front.jpg --side side.jpg --back back.jpg --profile kart_racer --name zed
  python forge.py build --spec char.txt --billboard8 --profile topdown8dir
  python forge.py profile list | show NAME | validate FILE | new NAME [--from BASE]
  python forge.py video --clip walk=walk.mp4 --clip "jump:12=jump.mp4#plate_start=0.5" --name hero --consoles snes,gba
  python forge.py mocap --clip run=my_run.mp4 --name hero        (pose tracking -> mannequin animation, see help mocap)
  python forge.py scan --video orbit.mp4 --name statue            (orbit video -> COLMAP project / mesh, see help scan)
  python forge.py doctor               -> what is installed / what each missing piece disables
  python forge.py list                 -> presets, moves, motions, kits
  python forge.py example-spec > char.txt
Run `python forge.py build -h` for every option.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sforge import __version__  # noqa: E402
from sforge.moves import MoveSpec, preset, PRESETS, PRESET_KEYS, slug  # noqa: E402
from sforge.motions import LIB, find_motion  # noqa: E402


def parse_moves(base, spec):
    """--moves 'idle,walk,dash=sprint:8:14:loop'  (name[=motion][:frames[:fps[:loop]]])"""
    if not spec:
        return base
    by = {m.name: m for m in base}
    out = []
    for item in [x.strip() for x in spec.split(",") if x.strip()]:
        parts = item.split(":")
        nm, _, mot = parts[0].partition("=")
        key = slug(nm)
        m = by.get(key)
        if m is None:
            mo = find_motion(mot or nm)
            m = MoveSpec(key, nm, mo.category if mo else "Custom", 8, 12, bool(mo and mo.loop), mot or "", "custom move")
        if mot:
            m.motion = mot
        if len(parts) > 1 and parts[1]:
            m.frames = int(parts[1])
        if len(parts) > 2 and parts[2]:
            m.fps = int(parts[2])
        if len(parts) > 3:
            m.loop = parts[3].lower() in ("1", "loop", "true", "yes")
        out.append(m)
    return out


def cmd_build(a):
    from sforge.build import BuildConfig, build
    cfg = BuildConfig()
    if getattr(a, "fbx_writer", None):
        os.environ["SFS_FBX_WRITER"] = a.fbx_writer
    if a.config:
        with open(a.config) as f:
            d = json.load(f)
        for k, v in d.items():
            if k == "moves":
                cfg.moves = [MoveSpec.from_dict(x) for x in v]
            elif k == "profile_name" and v:
                from sforge import profiles
                profiles.apply(cfg, profiles.load(v))
            elif hasattr(cfg, k) and k != "profile":
                setattr(cfg, k, v)
    if a.profile:
        from sforge import profiles
        try:
            prof = profiles.load(a.profile)
        except (FileNotFoundError, ValueError) as e:
            print(e); return 2
        errs, warns = profiles.validate(prof)
        if errs:
            print("profile %s has errors:\n  " % prof["_path"] + "\n  ".join(errs)); return 2
        profiles.apply(cfg, prof)
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        cfg.profile_vars[k.strip()] = v.strip()
    if a.mocap:
        from sforge import mocap as _mc
        for f in a.mocap:
            if f not in cfg.mocap_files:
                cfg.mocap_files.append(f)
            _mc.register(f)      # so --moves can resolve mocap_<move> below
    if a.preset:
        cfg.moves = preset(a.preset)
    cfg.moves = parse_moves(cfg.moves, a.moves)
    if getattr(a, "landmarks", None):
        cfg.landmarks = a.landmarks
    if a.photo:
        cfg.mode = "photo"; cfg.photo = a.photo
    elif a.spec:
        cfg.mode = "spec"; cfg.spec_path = a.spec
    elif a.frames:
        cfg.mode = "frames"; cfg.frames_dir = a.frames
    elif a.sheet:
        cfg.mode = "sheet"; cfg.sheet = a.sheet
    elif a.move_sheet:
        cfg.mode = "movesheets"
        for v in a.move_sheet:
            mv, _, path = v.partition("=")
            if not path:
                print("--move-sheet needs MOVE=path.png"); return 2
            cfg.move_sheets[mv.strip()] = path.strip()
        if a.frames_across:
            cfg.grid_cols = a.frames_across
    elif a.rig:
        cfg.mode = "library"; cfg.rig = a.rig
    elif a.mannequin:
        cfg.mode = "mannequin"
    if a.back:
        cfg.back = a.back
    if getattr(a, "turn", None) is not None or getattr(a, "turn_yaw", None) is not None:
        from sforge.turn import turn_args
        base = turn_args(a.turn) if a.turn is not None else 0.0
        cfg.turn = float(a.turn_yaw) if a.turn_yaw is not None else base
        if cfg.turn and cfg.fill != "puppet" and cfg.mode == "photo":
            cfg.fill = "puppet"
    for k in ("turn_depth", "side_photo", "side_faces", "side_frame", "turn_template"):
        if getattr(a, k, None) is not None:
            setattr(cfg, k, getattr(a, k))
    from sforge import views as V
    try:
        if a.side:
            img = a.side
            if a.side_faces_left:
                cfg.view_sources["left"] = img
            else:
                cfg.view_sources["right"] = img
        cfg.view_sources.update(V.parse_views(a.view or []))
        if a.views:
            if a.views.strip().lower() in ("billboard8", "8dir", "8"):
                cfg.billboard8 = True
            else:
                cfg.view_list = V.parse_view_list(a.views)
    except ValueError as e:
        print(e); return 2
    if a.billboard8:
        cfg.billboard8 = True
    if a.view_cut is not None:
        cfg.view_cut = a.view_cut
    if a.view_frames:
        cfg.view_frames = a.view_frames
    if a.view_moves:
        cfg.view_moves = [x.strip() for x in a.view_moves.split(",") if x.strip()]
    for v in a.video or []:
        mv, _, path = v.partition("=")
        cfg.videos[mv] = path
    if a.name:
        cfg.name = a.name
        cfg.display_name = a.display_name or a.name
    elif cfg.mode == "spec" and cfg.spec_path:
        from sforge.spec import load_spec
        cfg.name = load_spec(cfg.spec_path).name
    elif cfg.mode == "photo":
        cfg.name = os.path.splitext(os.path.basename(cfg.photo))[0]
    if a.frame:
        w, _, h = a.frame.lower().partition("x"); cfg.frame_w, cfg.frame_h = int(w), int(h or w)
    for k in ("prop", "figure_h", "ground_y", "pivot_x", "yaw", "kit", "cutout", "fill", "anchor", "height_cm", "blender",
              "sheet_layout", "max_atlas"):
        v = getattr(a, k)
        if v not in (None, ""):
            setattr(cfg, k, v)
    if a.grid:
        r, _, c = a.grid.lower().partition("x"); cfg.grid_rows, cfg.grid_cols = int(r), int(c)
    if a.display_name:
        cfg.display_name = a.display_name
    cfg.flip = a.flip or cfg.flip
    cfg.strips = a.strips or cfg.strips; cfg.gifs = a.gifs or cfg.gifs
    if a.no_outline:
        cfg.outline = False
    if a.no_glb:
        cfg.glb = cfg.fbx = False
    if a.no_fbx:
        cfg.fbx = False
    if a.library:
        cfg.library_dir = a.library
    if cfg.mode == "library" and not a.name and cfg.name == "character":
        cfg.name = os.path.splitext(os.path.basename(cfg.rig))[0]
    if a.clip_map:
        from sforge.librarybuild import load_clip_map
        cfg.clip_map.update(load_clip_map(a.clip_map))
    try:
        from sforge.librarybuild import parse_clip_arg
        for c in a.clip or []:
            mv_, e_ = parse_clip_arg(c); cfg.clip_map[mv_] = e_
    except ValueError as e:
        print(e); return 2
    if a.root_motion:
        cfg.root_motion = a.root_motion
    for k_ in ("material_split", "material_slots"):
        if getattr(a, k_, None):
            setattr(cfg, k_, getattr(a, k_))
    if getattr(a, "anim_export", False):
        cfg.anim_export = True
    if getattr(a, "quality", None):
        cfg.quality = a.quality
    if getattr(a, "no_cache", False):
        cfg.cache = False
    for sm in getattr(a, "set_move", None) or []:          # v8: --set-move punch:frames=8,fps=14,loop=1
        mv_, _, kvs = sm.partition(":")
        hit_ = [m for m in cfg.moves if m.name == mv_.strip()]
        if not hit_:
            print("--set-move: no move '%s' in this build" % mv_); return 2
        for kv in kvs.split(","):
            k_, _, v_ = kv.partition("=")
            k_ = k_.strip()
            if k_ in ("frames", "fps"):
                setattr(hit_[0], k_, int(v_))
            elif k_ == "loop":
                hit_[0].loop = v_.strip().lower() in ("1", "true", "yes", "loop")
            elif k_ == "motion":
                hit_[0].motion = v_.strip()
            else:
                print("--set-move: unknown key '%s' (frames, fps, loop, motion)" % k_); return 2
    if getattr(a, "human", None):
        cfg.human = a.human
    if getattr(a, "outfit", None):
        cfg.outfits = list(a.outfit)
    if getattr(a, "attach", None):
        cfg.props = list(a.attach)
    if getattr(a, "slot_color", None):
        cfg.slot_colors = ",".join(a.slot_color)
    # ---- v9
    if getattr(a, "npc", None):
        from sforge import npcpack
        try:
            sp_, mp_ = npcpack.character_spec(a.npc)
        except ValueError as e:
            print(e); return 2
        cfg.mode = "mannequin"; cfg.spec = sp_
        if not a.preset and not a.moves:
            cfg.moves = preset(mp_)
        if not a.name:
            cfg.name = cfg.display_name = a.npc
    for k_ in ("expressions", "expr_map", "talk", "recolor", "overlay", "regions", "vary", "fx", "maps", "blend"):
        if getattr(a, k_, None) not in (None, ""):
            setattr(cfg, k_, getattr(a, k_))
    for k_ in ("variant", "variants", "variant_seed", "lods"):
        if getattr(a, k_, None) is not None:
            setattr(cfg, k_, int(getattr(a, k_)))
    if a.no_blink:
        cfg.blink = False
    if a.no_faces_sheet:
        cfg.faces_sheet = False
    if a.no_physics:
        cfg.physics = False
    if a.no_qa:
        cfg.qa = False
    if getattr(a, "puppet_engine", None):
        cfg.puppet_engine = a.puppet_engine
    if getattr(a, "motion_style", None):
        cfg.motion_style = a.motion_style
    if a.footlock:
        cfg.footlock = True
    if a.framedata:
        cfg.framedata = True
    if cfg.vary:
        from sforge import variants as _V
        try:
            _V.parse_vary(cfg.vary)
        except ValueError as e:
            print(e); return 2
    if a.kits:
        from sforge.mesh import KITS
        if cfg.mode == "library" and a.kits == "all":
            from sforge import library as _L
            cfg.kits = _L.Library(cfg.library_dir or None).names("kits")
        else:
            cfg.kits = list(KITS) if a.kits == "all" else [k.strip() for k in a.kits.split(",")]
    cfg.out_root = a.out
    if a.console:
        from sforge import consoles
        if not consoles.by_label(a.console):
            print("unknown console '%s'. Choose one of: %s" % (a.console, ", ".join(consoles.ORDER))); return 2
        cfg.console = consoles.by_label(a.console)
    if a.dither is not None:
        cfg.dither = a.dither
    if a.save_config:
        d = {k: v for k, v in cfg.__dict__.items() if k not in ("spec", "profile") and not k.startswith("_")}
        if cfg.profile:
            d["profile_name"] = cfg.profile.get("name")
        d["moves"] = [m.to_dict() for m in cfg.moves]
        with open(a.save_config, "w") as f:
            json.dump(d, f, indent=1)
        print("saved", a.save_config)
    r = build(cfg)
    return 0 if r else 1


def cmd_list(a):
    print("Presets:")
    for k, v in PRESET_KEYS.items():
        print("  %-14s %s" % (k, v))
        print("      " + ", ".join(m.name for m in PRESETS[v]))
    print("\nProcedural motions (usable for custom moves: --moves mymove=<motion>):")
    cats = {}
    for m in LIB.values():
        cats.setdefault(m.category, []).append(m.name)
    for c, ns in cats.items():
        print("  %-14s %s" % (c, ", ".join(ns)))
    from sforge.mesh import KITS
    print("\nKits: " + ", ".join("%s (%s)" % (k, v["label"]) for k, v in KITS.items()))
    from sforge import consoles
    print("\nConsole targets (--console KEY):")
    for k in consoles.ORDER:
        print("  %-11s %-26s %s" % (k, consoles.LABELS[k], consoles.describe(k)))


def cmd_profile(a):
    from sforge import profiles
    if a.action in ("list", None):
        for n in profiles.list_profiles():
            d = profiles.load(n)
            print("  %-13s %s" % (n, d.get("description", "")))
        print("\n(profiles live in %s; forge.py profile show NAME prints one)" % profiles.PROFILE_DIR); return 0
    if a.action == "show":
        d = profiles.load(a.target); d.pop("_path", None)
        print(json.dumps(d, indent=2)); return 0
    if a.action == "validate":
        targets = [a.target] if a.target else profiles.list_profiles()
        bad = 0
        for t in targets:
            try:
                d = profiles.load(t)
            except (FileNotFoundError, ValueError) as e:
                print("FAIL %s: %s" % (t, e)); bad += 1; continue
            errs, warns = profiles.validate(d)
            print("%s %s" % ("FAIL" if errs else "OK  ", d["_path"]))
            for e in errs:
                print("   error:   " + e)
            for w in warns:
                print("   warning: " + w)
            bad += bool(errs)
        return 1 if bad else 0
    if a.action == "new":
        if not a.target:
            print("profile new NAME [--from BASE] [--moves ...] [--views ...] [--frame WxH] [--manifest godot_spriteframes,tiled_tsx,unity_json]"); return 2
        frame = None
        if a.frame:
            w, _, h = a.frame.lower().partition("x"); frame = (int(w), int(h or w))
        moves = None
        if a.moves:
            moves = a.moves if a.moves in PRESET_KEYS else [x.strip() for x in a.moves.split(",") if x.strip()]
        views = None
        if a.views:
            views = a.views if a.views.lower() == "billboard8" else [x.strip() for x in a.views.split(",") if x.strip()]
        mans = [x.strip() for x in a.manifest.split(",")] if a.manifest else None
        d = profiles.new_profile(a.target, a.base, moves, views, frame, mans, a.description or "")
        errs, warns = profiles.validate(d)
        if errs:
            print("not saved:\n  " + "\n  ".join(errs)); return 1
        p = profiles.save(d, a.out)
        print("saved", p); [print("  warning:", w) for w in warns]
        return 0
    print("unknown action"); return 2


VIDEO_HELP = """forge.py video  -  turn your own video clips into sprite moves, then build.

  --clip MOVE[:FRAMES]=VIDEO[@START-END][#opt=val,...]   repeatable, one clip per move
        walk=walk.mp4                 loop move: the stride is found automatically
        run:8=run.mp4@2.0-5.5         only use seconds 2.0 .. 5.5
        jump:12=jump.mp4#plate_start=0.5    the first 0.5 s show the empty scene (clean plate)
        punch:16=punch.mp4#bg=chroma        per-clip options: camera bg plate plate_start thr
                                            slowmo interp period flip shadows key spacing
  --camera auto|static|handheld|tracking    (default auto = measured)
  --bg auto|median|chroma|plate|rembg       (default auto: chroma if a green/blue screen, else median)
  --plate FILE        clean-plate image or video of the empty scene (all clips)
  --slowmo X          ffmpeg motion-interpolated slow motion before analysis (2 = half speed)
  --interp auto|on|off   optical-flow in-betweens when the clip has too few frames for --frames
  --work DIR          where the per-move frames go (default out/<name>_video)
  --consoles a,b      also build <name>_<console> for each console (snes,gba,ps1,...)
  --no-build          only extract the frames (+ debug sheets)
  everything else is passed to `forge.py build` (e.g. --frame 128x128 --profile fighter14 --no-fbx)
"""


def cmd_video(argv):
    ap = argparse.ArgumentParser(prog="forge.py video", description=VIDEO_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", action="append", required=True)
    ap.add_argument("--camera", default="auto", choices=["auto", "static", "handheld", "tracking"])
    ap.add_argument("--bg", default="auto", choices=["auto", "median", "chroma", "plate", "rembg"])
    ap.add_argument("--plate"); ap.add_argument("--plate-start", dest="plate_start", type=float)
    ap.add_argument("--slowmo", type=float, default=1.0)
    ap.add_argument("--interp", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--max-h", dest="max_h", type=int, default=720)
    ap.add_argument("--no-shadows", dest="shadows", action="store_false", help="keep cast shadows in the matte")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--work"); ap.add_argument("--name", default="video_char")
    ap.add_argument("--out", default="out")
    ap.add_argument("--consoles", default="")
    ap.add_argument("--no-build", dest="no_build", action="store_true")
    a, rest = ap.parse_known_args(argv)
    from sforge import video as V
    try:
        clips = [V.parse_clip(c) for c in a.clip]
    except ValueError as e:
        print(e); return 2
    opts = V.ClipOptions(camera=a.camera, bg=a.bg, plate=a.plate, plate_start=a.plate_start or 0, slowmo=a.slowmo,
                         interp=a.interp, max_h=a.max_h, shadows=a.shadows, flip=a.flip)
    work = a.work or os.path.join(a.out, slug(a.name) + "_video")
    moves = []
    try:
        meta = V.run_clips(clips, moves, work, opts)
    except (ValueError, RuntimeError) as e:
        print("video: %s" % e); return 2
    print("frames: %s   debug sheets: %s" % (work, os.path.join(work, "_debug")))
    if a.no_build:
        return 0
    mv = ",".join("%s:%d:%d:%s" % (m.name, m.frames, m.fps, "loop" if m.loop else "once") for m in moves)
    base = ["build", "--frames", work, "--moves", mv, "--fill", "skip", "--out", a.out] + rest
    rc = main(base + ["--name", a.name])
    return run_consoles(base, a.name, [x.strip() for x in a.consoles.split(",") if x.strip()]) or rc


def _console_job(argv):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = main(argv)
        except SystemExit as e:
            rc = e.code
        except Exception as e:
            print("error: %s" % e); rc = 1
    return rc, buf.getvalue()


def run_consoles(base, name, cons):
    """v8: one build per console (<name>_<console>), quantised in parallel worker processes."""
    if not cons:
        return 0
    from sforge import cache as C
    jobs = [base + ["--name", "%s_%s" % (name, c), "--console", c, "--no-glb", "--no-fbx"] for c in cons]
    if len(jobs) > 1:
        print("building %d console versions on %d worker processes ..." % (len(jobs), C.workers(len(jobs))))
    res = C.pmap(_console_job, jobs)
    rc = 0
    for c, (r, text) in zip(cons, res):
        print("---- %s ----" % c); print(text.rstrip()); rc = rc or (r or 0)
    return rc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "video":
        return cmd_video(argv[1:])
    if argv and argv[0] in ("mocap", "scan"):
        from sforge import mocap_cli
        return mocap_cli.main(argv)
    if argv and argv[0] == "library":
        from sforge import library_cli
        return library_cli.main(argv[1:])
    if argv and argv[0] == "build" and "--consoles" in argv:     # v8: build several console versions at once
        i = argv.index("--consoles"); cons = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
        rest = argv[:i] + argv[i + 2:]
        name = rest[rest.index("--name") + 1] if "--name" in rest else "character"
        if "--name" in rest:
            j = rest.index("--name"); rest = rest[:j] + rest[j + 2:]
        rc = main(rest + ["--name", name])
        return run_consoles(rest, name, cons) or rc
    if argv and argv[0] == "cache":          # v8: forge.py cache [stats|clear|prune]
        from sforge import cache as C
        sub_ = argv[1] if len(argv) > 1 else "stats"
        if sub_ == "clear":
            C.clear(); print("cache cleared: %s" % C.cache_root())
        elif sub_ == "prune":
            print("removed %d cached moves" % C.prune())
        else:
            print(json.dumps(C.stats(), indent=1))
        return 0
    if argv and argv[0] == "human":         # v7: MakeHuman mode (CC0 assets, own code) -> library rig
        from sforge import human
        return human.main(argv[1:])
    if argv and argv[0] == "autoskin":      # v7 experimental: bind a static mesh to a skeleton by bone distance
        from sforge import autoskin
        return autoskin.main(argv[1:])
    if argv and argv[0] == "retarget":
        from sforge import library_cli
        return library_cli.retarget_main(argv[1:])
    if argv and argv[0] == "anim-export":     # v7: character_base.glb + anim_<move>.glb (+ .fbx) + manifest.json
        from sforge import animexport
        return animexport.main(argv[1:])
    if argv and argv[0] == "cutout":        # v7.1: one chosen person -> transparent cut-out + sprite + HD sprite + checks
        from sforge import cutout_cli
        return cutout_cli.main(argv[1:])
    if argv and argv[0] in ("package", "summary"):     # v7.1: drop-in zip / pipeline summary image
        from sforge import package_cli
        return package_cli.main(argv)
    if argv and argv[0] == "turn":          # v8: the cut-out person seen side-on / from behind (estimated depth)
        from sforge import turn_cli
        return turn_cli.main(argv[1:])
    if argv and argv[0] in ("fighter", "export-ef"):   # v7.1: photo puppet fighter moves / game export
        from sforge import fighter_cli
        return fighter_cli.main(argv)
    from sforge import v9_cli
    if argv and argv[0] in v9_cli.COMMANDS:     # v9: recolor variants atlas batch qa framedata npc sets expressions
        return v9_cli.main(argv)
    if argv and argv[0] == "doctor":
        from sforge import doctor
        return doctor.run(argv[1:])
    if argv and argv[0] == "fbx":       # forge.py fbx model.glb [model.fbx]   (built-in writer, no Blender)
        from sforge import fbx as F
        if len(argv) < 2:
            print("usage: forge.py fbx MODEL.glb [OUT.fbx]"); return 2
        dst = argv[2] if len(argv) > 2 else os.path.splitext(argv[1])[0] + ".fbx"
        st = F.write_fbx_from_glb(argv[1], dst)
        print("wrote %s: %d bones, %d clusters, %d takes" % (dst, st["bones"], st["clusters"], len(st["takes"]))); return 0
    p = argparse.ArgumentParser(prog="forge.py", description="Sprite Forge Studio %s" % __version__,
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog="""more commands (each has -h):
  cutout      photo -> one person cut out (transparent) + sprite + HD sprite + pose points
  turn        cut-out person seen side-on / from behind (--yaw 0|90|180|270 or any angle; estimated depth)
  export-ef   built character -> Egyptian Fighter / Padel Wars char_<name>/ folder (sprites.cfg, HD + low-res)
  package     drop-in zip for a game's assets/ folder (<= 25 MB check)
  summary     one-page pipeline summary image
  cache       build cache: cache stats | clear | prune
v9:
""" + "\n".join("  %-11s %s" % kv for kv in v9_cli.HELP.items()))
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="build a character")
    src = b.add_argument_group("source (pick one; default = mannequin)")
    src.add_argument("--spec", help="SPEC mode: key=value text file describing a fictional character")
    src.add_argument("--photo", help="PHOTO mode: front photo of the person (own pixels only)")
    src.add_argument("--back", help="PHOTO mode: optional back photo -> idle_back")
    src.add_argument("--video", action="append", metavar="MOVE=PATH", help="PHOTO mode: frames for a move from a video (decoded by imageio-ffmpeg / OpenCV) or a folder of frames; repeatable")
    src.add_argument("--frames", help="FRAMES mode: folder of per-move frames")
    src.add_argument("--sheet", help="SHEET mode: sprite sheet image")
    src.add_argument("--move-sheet", dest="move_sheet", action="append", metavar="MOVE=STRIP.png", help="PER-MOVE SHEETS mode: one strip image (a row of frames) per move; repeatable")
    src.add_argument("--frames-across", dest="frames_across", type=int, help="PER-MOVE SHEETS: frames per strip (default: auto-detect by transparent gaps)")
    src.add_argument("--rig", help="LIBRARY mode: a rig from the user library (forge.py library list) or an .fbx / .glb path, rendered with the same pipeline")
    src.add_argument("--mannequin", action="store_true", help="MANNEQUIN mode (default when no source given): no-likeness 3D figure")
    src.add_argument("--sheet-layout", dest="sheet_layout", choices=["rows", "cells"], help="rows: one row per move; cells: one cell per move")
    src.add_argument("--grid", help="sheet grid ROWSxCOLS (default auto-detect by transparent gaps)")
    b.add_argument("--name"); b.add_argument("--preset", choices=list(PRESET_KEYS) + list(PRESETS))
    b.add_argument("--moves", help="subset / custom: 'idle,walk,dash=sprint:8:14:loop'")
    b.add_argument("--frame", help="frame size WxH (default 256x256)")
    b.add_argument("--figure-h", dest="figure_h", type=int, help="px height of a 180 cm figure (default 62%% of frame height)")
    b.add_argument("--ground-y", dest="ground_y", type=int, help="ground line / pivot y in the frame (default 94%%)")
    b.add_argument("--pivot-x", dest="pivot_x", type=int)
    b.add_argument("--yaw", type=float, help="mannequin camera angle: 90 = side profile, 65 = 3/4 (default)")
    b.add_argument("--kit", help="home away blue red black gk")
    b.add_argument("--kits", help="extra 3D team variants: 'all' or 'home,away,gk'")
    b.add_argument("--cutout", choices=["auto", "alpha", "rembg", "threshold", "none"])
    b.add_argument("--flip", action="store_true", help="mirror imported images so the character faces right")
    b.add_argument("--height-cm", dest="height_cm", type=float, help="PHOTO/FRAMES: person height for relative scale")
    b.add_argument("--fill", choices=["placeholder", "static", "mannequin", "skip", "puppet"], help="what to do with moves that have no source frames (puppet = v7.1 cut-out photo puppet: needs the landmarks.json from `forge.py cutout`)")
    b.add_argument("--turn", metavar="0|90|180|270|side|back", help="v8 PHOTO + puppet: show the person turned (90 = side-on facing right, 180 = back, 270 = left side, mirrored to face right). The unseen sides are ESTIMATED from the one photo + a depth model; implies --fill puppet")
    b.add_argument("--turn-yaw", type=float, metavar="DEG", help="fine turn angle in degrees (overrides --turn), e.g. 75")
    b.add_argument("--turn-depth", choices=["auto", "template", "relief", "side"], help="depth for --turn: template = MakeHuman CC0 body (forge.py human --setup), relief = procedural, auto = template if installed")
    b.add_argument("--side-photo", metavar="IMG|VIDEO", help="optional real side-on photo / video of the same person: fits the turned silhouette and side colours")
    b.add_argument("--side-faces", choices=["left", "right"], help="which way the person faces in --side-photo (default right)")
    b.add_argument("--side-frame", type=float, metavar="SEC", help="--side-photo is a video: take the frame at SEC (default the middle)")
    b.add_argument("--turn-template", metavar="k=v,..", help="MakeHuman body for --turn-depth template, e.g. 'gender=1,age=0.55,muscle=0.5,weight=0.55'")
    b.add_argument("--landmarks", help="PHOTO + --fill puppet: landmarks.json written by `forge.py cutout` (default: next to the photo)")
    b.add_argument("--anchor", choices=["auto", "feet", "strip"])
    b.add_argument("--max-atlas", dest="max_atlas", type=int)
    b.add_argument("--out", default="out")
    b.add_argument("--no-glb", action="store_true"); b.add_argument("--no-fbx", action="store_true")
    b.add_argument("--quality", choices=["final", "draft"], help="v8: draft = Quick preview (half-size frames, <= 4 frames a move, sprites only)")
    b.add_argument("--no-cache", dest="no_cache", action="store_true", help="v8: re-render everything (ignore the build / frame cache)")
    b.add_argument("--set-move", dest="set_move", action="append", metavar="MOVE:frames=8,fps=12,loop=1",
                   help="v8: change one move of the preset (repeatable)")
    b.add_argument("--blender", help="optional path to blender(.exe) (only for --fbx-writer blender)")
    b.add_argument("--fbx-writer", dest="fbx_writer", choices=["builtin", "blender"], help="FBX exporter (default builtin = pure Python, no Blender)")
    b.add_argument("--strips", action="store_true"); b.add_argument("--gifs", action="store_true")
    b.add_argument("--no-outline", action="store_true")
    b.add_argument("--prop", choices=["auto", "kart", "none"], help="mannequin prop: auto = kart for Kart moves (default), none = driver only (for games that draw their own kart)")
    b.add_argument("--console", help="console target preset (forge.py consoles): nes snes gba ps1 n64 ps5 pc_hd ... -> out/<name>/console/")
    b.add_argument("--dither", dest="dither", action="store_true", default=None, help="console export: Floyd-Steinberg dithering when reducing colours")
    b.add_argument("--no-dither", dest="dither", action="store_false")
    mv = b.add_argument_group("multi-view (front / side / back / 3-4 views -> views/, turnaround.png, billboard8.png)")
    mv.add_argument("--side", help="side photo / frames folder / video (character faces image-RIGHT; see --side-faces-left)")
    mv.add_argument("--side-faces-left", dest="side_faces_left", action="store_true", help="the --side image faces image-left")
    mv.add_argument("--view", action="append", metavar="VIEW=SRC", help="any view: front, front_right (3/4), right, back_right, back, back_left, left, front_left or an angle (45=...); SRC = image, frames folder or video; repeatable")
    mv.add_argument("--views", help="views to output, e.g. 'front,right,back,left' or 'billboard8'; missing ones are mirrored / interpolated and flagged")
    mv.add_argument("--billboard8", action="store_true", help="output all 8 directions (= --views billboard8)")
    mv.add_argument("--view-cut", dest="view_cut", type=float, help="keep the top fraction of each view (0.55 = head-to-lap bust for kart drivers; 0 = whole figure)")
    mv.add_argument("--view-frames", dest="view_frames", type=int, help="frames to take from a per-view video / folder (default 6)")
    mv.add_argument("--view-moves", dest="view_moves", help="moves animated per view (others = still copies), e.g. 'idle,walk'")
    b.add_argument("--profile", help="output profile: forge.py profile list (kart_racer, fighter14, topdown8dir, generic_2d, ...) or a .json path")
    b.add_argument("--set", action="append", metavar="KEY=VALUE", help="profile template variable, e.g. --set tagline=\"Fast!\" --set speed=4; repeatable")
    b.add_argument("--display-name", dest="display_name", help="name shown in manifests (folder name = slug of --name)")
    b.add_argument("--mocap", action="append", metavar="FILE.json", help="motion-capture clip from `forge.py mocap` (adds motion mocap_<move>; use it with --moves run=mocap_run); repeatable")
    lb = b.add_argument_group("library rig (v6: --rig NAME)")
    lb.add_argument("--library", help="library folder (default <studio>/library or $SFS_LIBRARY)")
    lb.add_argument("--clip", action="append", metavar="MOVE=[LIB:]CLIP[@speed=1,trim=a-b,loop|once]",
                    help="play this clip for a move, e.g. --clip wave=sample_moves:wave --clip kick=kick@trim=0.1-0.7; repeatable")
    lb.add_argument("--clip-map", dest="clip_map", help="JSON file {move: {clip, speed, loop, trim}}")
    lb.add_argument("--root-motion", dest="root_motion", choices=["keep", "inplace", "root"], help="3D takes: keep (default) | inplace | root")
    v7 = b.add_argument_group("v7: material slots, separate animation files")
    v7.add_argument("--material-split", dest="material_split", choices=["auto", "off"],
                    help="auto (default): a single-material / unnamed mesh is split into Skin_Mat/Jersey_Mat/Shorts_Mat/Socks_Mat(/Shoes_Mat) by bone regions + heights; off: only rename recognisable material names")
    v7.add_argument("--material-slots", dest="material_slots", choices=["full", "core4", "keep"],
                    help="full (default): Skin/Jersey/Shorts/Socks + Trim/Hair/Shoes slots | core4: exactly the 4 core slots | keep: materials as imported (pre-v7)")
    v7.add_argument("--anim-export", dest="anim_export", action="store_true",
                    help="also write anim/character_base.glb + anim/anim_<move>.glb (+ .fbx) + anim/manifest.json (separate animation files, raylib-compatible)")
    b.add_argument("--human", metavar="gender=1,age=25,muscle=0.5,weight=0.5,height=0.5,proportions=0.5,skeleton=game_engine",
                   help="v7 MakeHuman mode: a parametric human from the CC0 MakeHuman assets (forge.py human --setup); skeleton default|default_no_toes|game_engine|body; without the assets: fallback to the mannequin")
    eq = b.add_argument_group("v7: equip - outfits skinned to the same skeleton, props on sockets (library outfits/ props/)")
    eq.add_argument("--outfit", action="append", metavar="NAME[:hide=torso+arms][:slot=Jersey]",
                    help="wear library outfit NAME (repeatable); hide= overrides the body regions it hides (%s)" % "torso hips neck head shoulders upperarms forearms hands thighs shins feet arms legs body")
    eq.add_argument("--attach", "--equip-prop", dest="attach", action="append", metavar="NAME[@SOCKET][:ox,oy,oz[:rx,ry,rz[:scale]]]",
                    help="attach library prop NAME to a socket: hand_r hand_l head back hip foot (default: the prop's own socket); repeatable")
    eq.add_argument("--slot-color", dest="slot_color", action="append", metavar="SLOT=#RRGGBB",
                    help="recolour a material slot, e.g. --slot-color Jersey=#c8102e --slot-color Armour=#777777")
    v9 = b.add_argument_group("v9 STYLE: faces / colours / variants")
    v9.add_argument("--expressions", help="auto (per move: hit=hurt, punch=angry, taunt=taunt ...) | off | one expression for all moves (forge.py expressions)")
    v9.add_argument("--expr-map", dest="expr_map", help="per-move expressions, e.g. 'punch=shout,victory=happy,idle=neutral'")
    v9.add_argument("--no-blink", dest="no_blink", action="store_true", help="no blink in looping neutral moves")
    v9.add_argument("--talk", help="a line of dialogue -> talk/ strip with mouth shapes + talk.json timing ('sheet' = every mouth shape)")
    v9.add_argument("--no-faces-sheet", dest="no_faces_sheet", action="store_true", help="skip faces.png (HUD portraits of every expression)")
    v9.add_argument("--recolor", help="colour set and/or regions: team_red | kerry | 'team_blue;hair=black' | 'top=#c8102e,skin=..' (forge.py sets)")
    v9.add_argument("--overlay", help="texture overlay on the top: 'top:hoops:#ffffff' | 'top:stripes:gold' | 'top:texture:cloth.png'")
    v9.add_argument("--regions", help="PHOTO: your painted region map PNG (colours as in regions_preview.png) instead of the automatic one")
    v9.add_argument("--no-physics", dest="no_physics", action="store_true", help="no hair / cape / scarf swing")
    v9.add_argument("--variant", type=int, help="build procedural variant SEED of this character")
    v9.add_argument("--vary", help="what a variant changes: body,outfit,colours,skin,accessories,face | all")
    v9.add_argument("--variants", type=int, help="also write variants/ (sheet + spec files of N variants)")
    v9.add_argument("--variant-seed", dest="variant_seed", type=int, help="first seed for --variants (default 1)")
    v9.add_argument("--npc", help="build an enemy / NPC preset character (forge.py npc): goblin, guard, wizard, boss_king ...")
    v9x = b.add_argument_group("v9 EXTRAS")
    v9x.add_argument("--fx", help="post passes: 'outline=2,cel=3,pixel=4,colors=32,light=-1:-1:1,rim=0.4,outline_colour=#101018'")
    v9x.add_argument("--maps", help="'normal,emissive' (emissive=#59f2ff to pick the glow colour) -> maps/")
    v9x.add_argument("--puppet-engine", choices=["classic", "skin"], help="v9.1 photo puppet renderer: skin = smooth bending elbows / knees (default classic)")
    v9x.add_argument("--motion-style", choices=["classic", "polish"], help="v9.1 photo puppet in-betweens: polish = smooth curves + limb lag when a move has more frames than key poses (default classic)")
    v9x.add_argument("--footlock", action="store_true", help="pin planted feet with 2-bone IK (no foot sliding) - mannequin / library moves")
    v9x.add_argument("--framedata", action="store_true", help="hit / hurt boxes + startup / active / recovery -> framedata.json + framedata.cfg")
    v9x.add_argument("--blend", help="transition moves 'idle>walk:3,punch>idle:3' -> blend_<a>_<b>")
    v9x.add_argument("--no-qa", dest="no_qa", action="store_true", help="skip the sprite QA checker")
    v9x.add_argument("--lods", type=int, help="3D: model_baked.glb (1 texture, 1 material) + N lower-detail model_lodN.glb")
    b.add_argument("--config", help="load a project .json (saved from the GUI)")
    b.add_argument("--save-config", dest="save_config")
    sub.add_parser("video", help="video clips -> sprite moves -> build   (forge.py video -h)")
    sub.add_parser("mocap", help="video -> pose tracks -> animated mannequin GLB/FBX + sprites (forge.py mocap -h)")
    sub.add_parser("scan", help="orbit video -> photogrammetry project / mesh -> console LODs (forge.py scan -h)")
    sub.add_parser("gui", help="open the visual studio")
    sub.add_parser("library", help="user library of FBX/GLB rigs, animations, kits + .sfpack packs (forge.py library -h)")
    sub.add_parser("retarget", help="apply clips from one library rig / FBX / GLB to another (forge.py retarget -h)")
    sub.add_parser("human", help="v7: MakeHuman mode - parametric human (gender/age/muscle/weight/height/proportions) from the CC0 MakeHuman assets -> library rig (forge.py human -h)")
    sub.add_parser("autoskin", help="v7 EXPERIMENTAL: skin your own static mesh (OBJ/GLB/FBX) to a library skeleton by bone distance (forge.py autoskin -h)")
    sub.add_parser("anim-export", help="v7: separate animation files - character_base.glb + anim_<move>.glb (+ .fbx) + manifest.json (forge.py anim-export -h)")
    sub.add_parser("doctor", help="check installed pieces and what each missing one disables (forge.py doctor [--json])")
    sub.add_parser("fbx", help="convert a Sprite Forge GLB to FBX with the built-in writer: forge.py fbx model.glb [out.fbx]")
    sub.add_parser("list", help="list presets, motions and kits")
    sub.add_parser("example-spec", help="print an example character spec")
    h = sub.add_parser("help", help="beginner help: forge.py help [topic]   (topics: forge.py help)")
    h.add_argument("topic", nargs="?", default="")
    sub.add_parser("consoles", help="list console target presets and their limits")
    pr = sub.add_parser("profile", help="output profiles: profile list | show NAME | validate [NAME|FILE] | new NAME")
    pr.add_argument("action", nargs="?", choices=["list", "show", "validate", "new"])
    pr.add_argument("target", nargs="?")
    pr.add_argument("--from", dest="base", help="new: start from this profile")
    pr.add_argument("--moves"); pr.add_argument("--views"); pr.add_argument("--frame")
    pr.add_argument("--manifest", help="new: extra manifests: godot_spriteframes,tiled_tsx,unity_json")
    pr.add_argument("--description"); pr.add_argument("--out", help="new: save path (default profiles/NAME.json)")
    a = p.parse_args(argv)
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "help":
        from sforge import helptext
        sys.stdout.write(helptext.render(a.topic) + "\n"); return 0
    if a.cmd == "consoles":
        from sforge import consoles
        for k in consoles.ORDER:
            print("  %-11s %-26s %s" % (k, consoles.LABELS[k], consoles.describe(k)))
        return 0
    if a.cmd == "list":
        return cmd_list(a)
    if a.cmd == "profile":
        return cmd_profile(a)
    if a.cmd == "example-spec":
        from sforge.spec import EXAMPLE_SPEC
        sys.stdout.write(EXAMPLE_SPEC); return 0
    from sforge.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main() or 0)
