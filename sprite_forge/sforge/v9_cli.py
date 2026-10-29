"""Sprite Forge Studio v9 command line: recolor, variants, atlas, batch, qa, framedata, npc, sets, expressions."""
from __future__ import annotations
import argparse
import os
import sys


def _recolor(argv):
    p = argparse.ArgumentParser(prog="forge.py recolor", description="Palette-swap a FINISHED build or game folder into a new folder "
                                "(the original is not touched). Mannequin builds know their colours (character.ini); for a photo / "
                                "game folder say which colours to replace with --from.")
    p.add_argument("folder"); p.add_argument("--set", "--recolor", dest="rec", required=True,
                                             help="set name (forge.py sets) and/or region=colour list, e.g. team_blue;hair=black")
    p.add_argument("--from", dest="src", default="", help="source colours top=#rrggbb,bottom=...,socks=... (photo / game folders)")
    p.add_argument("--out", help="output folder (default <folder>_<set>)")
    a = p.parse_args(argv)
    from . import recolor as RC
    src = {}
    for kv in [x for x in a.src.split(",") if x.strip()]:
        k, _, v = kv.partition("=")
        src[k.strip()] = v.strip()
    try:
        out, n, pairs = RC.recolor_folder(a.folder, a.rec, a.out, src)
    except ValueError as e:
        print(e); return 2
    print("recoloured %d images -> %s" % (n, out)); return 0


def _variants(argv):
    p = argparse.ArgumentParser(prog="forge.py variants", description="N procedural variants of a character (each reproducible "
                                "from its seed) -> variants_sheet.png + variant_<seed>.txt specs. Photo cut-outs: recolour + scale only.")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--spec"); src.add_argument("--npc", help="start from an NPC preset (forge.py npc)")
    src.add_argument("--cutout", help="PHOTO: cutout.png from forge.py cutout (landmarks.json next to it)")
    p.add_argument("-n", "--count", type=int, default=8); p.add_argument("--seed", type=int, default=1)
    p.add_argument("--vary", default="body,outfit,colours,accessories", help="body,outfit,colours,skin,accessories,face or all")
    p.add_argument("--out", default="out/variants")
    a = p.parse_args(argv)
    from . import variants as V
    try:
        V.parse_vary(a.vary)
    except ValueError as e:
        print(e); return 2
    if a.cutout:
        import json
        from PIL import Image
        lm = os.path.join(os.path.dirname(a.cutout), "landmarks.json")
        d = json.load(open(lm))
        lms = d["landmarks"] if isinstance(d, dict) else d      # forge.py cutout writes {"landmarks": [...], ...}
        V.write_photo(a.out, Image.open(a.cutout).convert("RGBA"), lms, a.count, a.seed, a.vary)
        return 0
    if a.npc:
        from . import npcpack
        sp, _ = npcpack.character_spec(a.npc)
    elif a.spec:
        from .spec import load_spec
        sp = load_spec(a.spec)
    else:
        from .spec import CharacterSpec
        sp = CharacterSpec(name="mannequin")
    V.write(a.out, sp, a.count, a.seed, a.vary)
    print("rebuild one: forge.py build %s --variant SEED --vary %s" % ("--npc " + a.npc if a.npc else "--spec " + (a.spec or "<spec>"), a.vary))
    return 0


def _atlas(argv):
    p = argparse.ArgumentParser(prog="forge.py atlas", description="Pack several characters into shared atlas pages (trimmed, "
                                "duplicate frames shared) -> pack_N.png + pack.json (TexturePacker-style; Unity / Godot importers read it)")
    p.add_argument("folders", nargs="+"); p.add_argument("--out", default="out/pack")
    p.add_argument("--max", type=int, default=4096); p.add_argument("--padding", type=int, default=2)
    p.add_argument("--no-trim", action="store_true"); p.add_argument("--pot", action="store_true", help="power-of-two pages")
    p.add_argument("--scale", type=float, default=1.0)
    a = p.parse_args(argv)
    from . import atlaspack
    try:
        atlaspack.pack(a.folders, a.out, a.max, a.padding, not a.no_trim, a.pot, a.scale)
    except ValueError as e:
        print(e); return 2
    return 0


def _qa(argv):
    p = argparse.ArgumentParser(prog="forge.py qa", description="Sprite QA checker on a build folder (atlas.json + moves/) or a "
                                "game folder (sprites.cfg) -> qa_report.txt + qa.json. Exit code 1 when a move FAILs.")
    p.add_argument("folders", nargs="+")
    a = p.parse_args(argv)
    from . import qa
    bad = 0
    for f in a.folders:
        try:
            r = qa.check_folder(f)
        except ValueError as e:
            print(e); return 2
        bad += len(r["fail"])
    return 1 if bad else 0


def _framedata(argv):
    p = argparse.ArgumentParser(prog="forge.py framedata", description="Hitboxes / hurtboxes / startup-active-recovery for an "
                                "existing build or game folder -> framedata.json + framedata.cfg + framedata_preview.png (ESTIMATED)")
    p.add_argument("folder"); p.add_argument("--out", help="default: the folder itself")
    a = p.parse_args(argv)
    from . import atlaspack, framedata
    from .moves import MoveSpec
    name, meta, moves = atlaspack.load_character(a.folder)

    class _C:
        pass
    c = _C(); c.name = name; c.frame_w = meta["frame_w"]; c.frame_h = meta["frame_h"]
    c.pivot_x = meta["pivot"]["x"]; c.ground_y = meta["ground_y"]
    ordered = [(mv, [im for _, im in frs]) for mv, fps, loop, frs in moves]
    spec_by = {mv: MoveSpec(name=mv, frames=len(frs), fps=fps, loop=loop) for mv, fps, loop, frs in moves}

    class _R:
        def warning(self, m):
            print("  !", m)
    print(framedata.write_framedata(c, a.out or a.folder, {"ordered": ordered, "spec_by": spec_by}, _R()))
    return 0


def _npc(argv):
    from . import npcpack
    print(npcpack.listing())
    print("\nbuild one:  forge.py build --npc goblin [--preset enemy_grunt] [--variants 6] [--recolor villain]")
    return 0


def _sets(argv):
    from . import recolor as RC
    print("Recolour sets (--recolor NAME, combine: 'team_blue;hair=black'):")
    for k, v in RC.all_sets().items():
        print("  %-12s %-28s %s" % (k, v.get("label", ""), " ".join("%s=%s" % (r, v[r]) for r in RC.REGIONS + ["pattern", "shift"] if r in v)))
    print("\nRegions: %s\nOverlay patterns (--overlay top:NAME:#colour): %s, or top:texture:file.png" % (" ".join(RC.REGIONS), " ".join(RC.PATTERNS)))
    print("Save your own: forge.py sets --save NAME top=#..,bottom=..   (library/recolor_sets/NAME.json)")
    if len(argv) >= 2 and argv[0] == "--save":
        m = RC.parse(",".join(argv[2:]))
        print("saved", RC.save_set(argv[1], {k: RC.hexc(v) if isinstance(v, tuple) else v for k, v in m.items()}))
    return 0


def _expressions(argv):
    from . import expressions as X
    print("Expressions / mouth shapes (--expressions auto|off|NAME, --expr-map move=expr,...):")
    print("  " + ", ".join(X.all_names()))
    print("\nDefault per-move map (auto):")
    for mv in ("idle", "walk", "punch", "kick", "special1", "hit", "ko", "block", "taunt", "victory", "throw", "jump"):
        print("  %-10s -> %s" % (mv, X.expression_for(mv)))
    print("\nTalking: --talk \"Ready to fight!\" -> talk/ strip + talk.json (letter-based mouth shapes, not speech recognition)")
    return 0


COMMANDS = {"recolor": _recolor, "variants": _variants, "atlas": _atlas, "qa": _qa, "framedata": _framedata,
            "npc": _npc, "sets": _sets, "expressions": _expressions,
            "batch": lambda argv: __import__("sforge.batch", fromlist=["x"]).main(argv)}
HELP = {"recolor": "palette-swap a finished build / game folder into a new folder (team colours, alt costumes)",
        "variants": "N procedural variants (body / outfit / colours / accessories, seeded) -> sheet + spec files",
        "atlas": "pack several characters into shared atlas pages + pack.json",
        "batch": "run a queue of forge.py commands (txt or json), in parallel workers, with a report",
        "qa": "sprite QA checker on build / game folders (clipping, empty frames, feet drift, pops, loop seams, specks, halos)",
        "framedata": "hit / hurt boxes + startup / active / recovery for an existing build or game folder",
        "npc": "enemy / NPC preset pack: move presets + fictional character presets",
        "sets": "list recolour sets / save your own",
        "expressions": "list facial expressions, mouth shapes and the per-move map"}


def main(argv):
    return COMMANDS[argv[0]](argv[1:])
