#!/usr/bin/env python3
"""Squad mode (v9.4): a folder of people -> a roster of characters at one consistent scale.

    python tools/squad.py PEOPLE_DIR OUT [--roster roster.csv] [--engine skin|photo3d] [--turn-yaw 35]
                          [--preset fighter14] [--frame 512x512] [--game arena-fc|ef|hdf|tt64 --game-dir DIR] [-- build args]

PEOPLE_DIR holds one entry per person:
  * a folder with cutout.png + landmarks.json (what `forge.py cutout` writes), or
  * a photo (.jpg/.png): `forge.py cutout --person largest` is run first (needs the pose model: tools/setup_pose.py)
roster.csv (optional): name,height_cm,dress_as,number,display - matched to the entry's file / folder name.  Heights
put everybody on ONE scale (a 165 cm player is drawn shorter than a 190 cm one, like the real squad); missing
heights use 178 cm.  Outputs: OUT/<name>/... (a normal build each), OUT/roster.json, OUT/lineup.png (idle frames
side by side at true relative height) and, with --game, the game files for every member (Arena FC CharacterSpec
JSONs + squad file, Egyptian Fighter / HD Fighter / TurboTumble64 folders through the existing adapters)."""
from __future__ import annotations
import argparse, csv, glob, json, os, subprocess, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(HERE, "forge.py")


def people(src):
    out = []
    for p in sorted(os.listdir(src)):
        fp = os.path.join(src, p)
        if os.path.isdir(fp) and os.path.isfile(os.path.join(fp, "cutout.png")) and os.path.isfile(os.path.join(fp, "landmarks.json")):
            out.append((os.path.splitext(p)[0], fp, None))
        elif os.path.splitext(p)[1].lower() in (".jpg", ".jpeg", ".png", ".webp") and os.path.isfile(fp):
            out.append((os.path.splitext(p)[0], None, fp))
    return out


def slug(s):
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_") or "player"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--roster"); ap.add_argument("--engine", default="skin", choices=["skin", "classic", "photo3d"])
    ap.add_argument("--turn-yaw", type=float, default=0.0); ap.add_argument("--preset", default="fighter14")
    ap.add_argument("--frame", default="512x512"); ap.add_argument("--moves")
    ap.add_argument("--game", choices=["arena-fc", "ef", "hdf", "tt64"]); ap.add_argument("--game-dir")
    ap.add_argument("--default-height", type=float, default=178.0)
    a, extra = ap.parse_known_args(argv)
    extra = [x for x in extra if x != "--"]
    os.makedirs(a.out, exist_ok=True)
    roster = {}
    if a.roster:
        for row in csv.DictReader(open(a.roster)):
            roster[slug(row.get("name", ""))] = row
    members = []
    for name, cutdir, photo in people(a.src):
        key = slug(name)
        row = roster.get(key, {})
        if cutdir is None:                                   # a plain photo: cut it out first
            cutdir = os.path.join(a.out, "_cut", key)
            r = subprocess.run([sys.executable, FORGE, "cutout", photo, "--person", "largest", "--out", cutdir],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print("  %-16s SKIPPED - cut-out failed (%s)" % (name, (r.stderr or r.stdout).strip().splitlines()[-1:]))
                continue
        h = float(row.get("height_cm") or a.default_height)
        cmd = [sys.executable, FORGE, "build", "--photo", os.path.join(cutdir, "cutout.png"),
               "--landmarks", os.path.join(cutdir, "landmarks.json"), "--fill", "puppet", "--preset", a.preset,
               "--puppet-engine", a.engine, "--frame", a.frame, "--name", key, "--height-cm", str(h),
               "--out", a.out, "--no-glb", "--no-fbx"]
        if a.engine != "photo3d":
            cmd += ["--motion-style", "polish"]
        if a.turn_yaw:
            cmd += ["--turn-yaw", str(a.turn_yaw)]
        if a.moves:
            cmd += ["--moves", a.moves]
        if row.get("dress_as"):
            cmd += ["--dress-as", row["dress_as"]]
        cmd += extra
        r = subprocess.run(cmd, capture_output=True, text=True)
        ok = r.returncode == 0
        print("  %-16s %s  %.0f cm%s" % (name, "ok " if ok else "FAILED", h, ("  dressed as " + row["dress_as"]) if row.get("dress_as") else ""))
        if not ok:
            print("    " + "\n    ".join((r.stderr or r.stdout).strip().splitlines()[-3:]))
            continue
        members.append(dict(name=key, display=row.get("display") or name, height_cm=h, number=row.get("number"),
                            dress_as=row.get("dress_as") or "", build=os.path.join(a.out, key), cut=cutdir))
    json.dump({"members": members, "engine": a.engine, "turn_yaw": a.turn_yaw, "preset": a.preset, "frame": a.frame},
              open(os.path.join(a.out, "roster.json"), "w"), indent=1)
    # line-up: idle frame 0 of everybody, same cell scale (heights already applied by --height-cm)
    if members:
        ims = [Image.open(os.path.join(m["build"], "moves", "idle_00.png")).convert("RGBA") for m in members]
        cw, ch = ims[0].size
        W = Image.new("RGB", (cw * len(ims), ch + 30), (214, 218, 224)); d = ImageDraw.Draw(W)
        for i, (im, m) in enumerate(zip(ims, members)):
            W.paste(im, (i * cw, 0), im)
            d.text((i * cw + 8, ch + 8), "%s  %.0f cm%s" % (m["display"], m["height_cm"], ("  #" + m["number"]) if m.get("number") else ""), fill=(0, 0, 0))
        d.line([(0, ch - (ch - int(ch * 0.94))), (W.width, ch - (ch - int(ch * 0.94)))], fill=(150, 150, 150))
        W.save(os.path.join(a.out, "lineup.png"))
    # game export
    if a.game and members:
        gd = a.game_dir or os.path.join(a.out, "game_" + a.game)
        os.makedirs(gd, exist_ok=True)
        T = os.path.join(HERE, "tools")
        squad = []
        for i, m in enumerate(members):
            if a.game == "arena-fc":
                dst = os.path.join(gd, "%s_%02d.json" % (m["name"], int(m.get("number") or i + 1)))
                subprocess.run([sys.executable, os.path.join(T, "export_arenafc.py"), os.path.join(m["cut"], "cutout.png"),
                                os.path.join(m["cut"], "landmarks.json"), dst, "--name", m["display"],
                                "--number", str(m.get("number") or i + 1), "--height", "%.2f" % (m["height_cm"] / 100.0)],
                               capture_output=True, text=True)
                squad.append(json.load(open(dst)))
            elif a.game == "ef":
                subprocess.run([sys.executable, os.path.join(T, "export_ef.py"), m["build"], os.path.join(gd, "char_" + m["name"])], capture_output=True)
            elif a.game == "hdf":
                subprocess.run([sys.executable, os.path.join(T, "export_hdf.py"), m["build"], gd, m["name"]], capture_output=True)
            elif a.game == "tt64":
                subprocess.run([sys.executable, os.path.join(T, "export_tt64.py"), m["build"], os.path.join(gd, m["name"]),
                                "--display", m["display"]], capture_output=True)
        if squad:
            json.dump(squad, open(os.path.join(gd, "squad.json"), "w"), indent=2)
        print("game files (%s) -> %s" % (a.game, gd))
    print("squad: %d members -> %s (roster.json, lineup.png)" % (len(members), a.out))
    return 0 if members else 1


if __name__ == "__main__":
    sys.exit(main())
