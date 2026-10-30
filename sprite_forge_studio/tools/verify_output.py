#!/usr/bin/env python3
"""Check a Sprite Forge output folder: frames per move must agree between
sprites.cfg (SpriteForge v1 'move' lines), atlas.json, character.ini and moves/<move>_<NN>.png, and every atlas
cell must be inside its page.  usage: python tools/verify_output.py out/<name> [...]"""
import configparser, glob, json, os, re, sys
from PIL import Image


def verify(folder):
    errs, rows = [], []
    cfg = {"anims": {}}
    for ln in open(os.path.join(folder, "sprites.cfg")):
        p = ln.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "move":      # SpriteForge v1: move <name> <file> <frames> <w> <h> <fps> <loop> <row>
            p = ln.split("#", 1)[0].split()
            cfg["anims"][p[1]] = dict(file=p[2], count=int(p[3]), w=int(p[4]), h=int(p[5]), fps=float(p[6]),
                                      loop=p[7] == "1", row=int(p[8]))
        elif p[0] == "frame":
            cfg["fw"], cfg["fh"] = int(p[1]), int(p[2])
        elif p[0] == "columns":
            cfg["cols"] = int(p[1])
    js = json.load(open(os.path.join(folder, "atlas.json")))
    ini = configparser.ConfigParser(strict=False, interpolation=None)
    txt = open(os.path.join(folder, "character.ini"), errors="ignore").read()
    # a profile may write a game's own character.ini (keys before any [section], e.g. TurboTumble64)
    ini.read_string(txt if txt.lstrip(" \t\r\n;#").startswith("[") or "\n[character]" in txt else "[character]\n" + txt)
    game_ini = not ini.has_section("moves")
    for k in ("name", "frame_w", "frame_h", "ground_y", "scale"):
        if ini.has_section("character") and k not in ini["character"]:
            errs.append("character.ini missing " + k)
    pages = [Image.open(os.path.join(folder, f)).size for f in js["meta"]["images"]]
    for name, a in cfg["anims"].items():
        ja = js["animations"].get(name)
        files = sorted(glob.glob(os.path.join(folder, "moves", name + "_[0-9][0-9]*.png")))
        files = [f for f in files if re.fullmatch(re.escape(name) + r"_\d+\.png", os.path.basename(f))]
        jcount = len(ja["frames"]) if ja else -1
        im_ = "" if game_ini else ini["moves"].get(name, "")
        icount = a["count"] if game_ini else (int(im_.split(",")[0]) if im_ else -1)
        ok = a["count"] == jcount == len(files) == icount
        if ja and (ja["fps"] != a["fps"] or bool(ja["loop"]) != a["loop"]):
            ok = False; errs.append("%s fps/loop differ" % name)
        for i, fn in enumerate((ja or {}).get("frames", [])):
            r = js["frames"][fn]["frame"]; pg = js["frames"][fn].get("page", 0); pw, ph = pages[pg]
            if js["meta"]["images"][pg] != a["file"] or (r["x"], r["y"]) != (i * a["w"], a["row"] * a["h"]):
                ok = False; errs.append(fn + " rect differs between atlas.json and sprites.cfg")
            if r["x"] + r["w"] > pw or r["y"] + r["h"] > ph:
                ok = False; errs.append(fn + " outside page")
        rows.append((name, a["count"], jcount, icount, len(files), "OK" if ok else "MISMATCH"))
        if not ok:
            errs.append("%s: cfg %d json %d ini %d files %d" % (name, a["count"], jcount, icount, len(files)))
    extra = set(js["animations"]) - set(cfg["anims"])
    if extra:
        errs.append("in atlas.json but not sprites.cfg: %s" % sorted(extra))
    return rows, errs


def main(argv):
    bad = 0
    for f in argv:
        rows, errs = verify(f)
        print("== %s" % f)
        print("  %-14s %5s %5s %5s %5s" % ("move", "cfg", "json", "ini", "files"))
        for r in rows:
            print("  %-14s %5d %5d %5d %5d  %s" % r)
        print("  RESULT: %s" % ("PASS" if not errs else "FAIL: " + "; ".join(errs)))
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
