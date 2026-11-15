#!/usr/bin/env python3
"""Each fighter move keeps its own animation.

v11.5 mapped several fighting moves onto one library clip (specials and throw
played punch). This builds the fighter14 set and fails when two moves share a
clip or render the same frames, unless the pack explicitly aliases them.

  python tools/test_fighter_variety.py [OUT_DIR]

The character is the mannequin, plus a drawn paper doll for the photo puppet.
No photo of a real person.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
PY = sys.executable
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_variety_")
os.makedirs(OUT, exist_ok=True)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), str(detail)))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))
    sys.stdout.flush()


def forge(args):
    e = dict(os.environ)
    e.pop("SFS_MOTION_SET", None)
    e.pop("SFS_MOTIONS", None)
    p = subprocess.run([PY, os.path.join(HERE, "forge.py")] + list(args),
                       capture_output=True, text=True, env=e, cwd=HERE)
    return p.returncode, p.stdout + p.stderr


def seq_hash(folder, move):
    paths = sorted(glob.glob(os.path.join(folder, "moves", move + "_*.png")))
    h = hashlib.sha256()
    for p in paths:
        h.update(open(p, "rb").read())
    return h.hexdigest(), len(paths)


def same_frames(folder, moves):
    got = {m: seq_hash(folder, m) for m in moves}
    bad = []
    names = list(got)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if got[a][0] == got[b][0] and got[a][1]:
                bad.append("%s==%s (%d frames)" % (a, b, got[a][1]))
    return bad, got


# ---------------------------------------------------------------- resolver: own clip, then own motion, alias only when asked
from sforge.build import BuildConfig
from sforge.gamepack import moves_of
from sforge.moves import preset
from sforge import motionset as MS

os.environ.pop("SFS_MOTION_SET", None)
os.environ.pop("SFS_MOTIONS", None)


def resolved(moves, **kw):
    cfg = BuildConfig()
    cfg.moves = moves
    cfg.motion_set = kw.get("motion_set", "off")
    if kw.get("library_dir"):
        cfg.library_dir = kw["library_dir"]
    MS.apply_cfg(cfg)
    return cfg


fight = resolved(moves_of("fighting"))
ids = [m.resolved_clip for m in fight.moves]
rec("fighting: 14 moves, 14 clips", len(ids) == len(set(ids)) == 14, " ".join(ids))
by = {m.name: m for m in fight.moves}
rec("special, throw and jump attack are not punch",
    by["special1"].resolved_clip != by["punch"].resolved_clip
    and by["special2"].resolved_clip != by["kick"].resolved_clip
    and by["throw"].resolved_clip != by["punch"].resolved_clip
    and by["jumpattack"].resolved_clip != by["kick"].resolved_clip
    and not by["special1"].motion_alias and not by["throw"].motion_alias,
    "%s %s %s" % (by["special1"].resolved_clip, by["throw"].resolved_clip, by["jumpattack"].resolved_clip))
rec("fighting report has nothing shared", MS.shared_note(fight.moves) == "", MS.shared_note(fight.moves))

box = resolved(moves_of("boxing"))
note = MS.shared_note(box.moves)
rec("boxing jab/cross/hook still share punch, and the report says so",
    "jab" in note and "cross" in note and "hook" in note and "lib:punch" in note and "explicit alias" in note, note)

# a recorded set that only contains punch must not be replayed for the other strikes
lib = os.path.join(OUT, "library")
sdir = os.path.join(lib, "motion_sets", "owner")
os.makedirs(sdir, exist_ok=True)
json.dump({"name": "owner", "video_kept": False}, open(os.path.join(sdir, "_set.json"), "w"))
shutil.copy(os.path.join(HERE, "motion_library", "punch.json"), os.path.join(sdir, "punch.json"))
held = resolved(moves_of("fighting"), motion_set="owner", library_dir=lib)
hb = {m.name: m for m in held.moves}
rec("a punch recording is used for punch only",
    hb["punch"].motion_source.startswith("set:")
    and hb["special1"].resolved_clip != hb["punch"].resolved_clip
    and hb["throw"].resolved_clip != hb["punch"].resolved_clip
    and not hb["special1"].motion_source.startswith("set:"),
    "punch=%s special1=%s (%s) throw=%s (%s)" % (
        hb["punch"].motion_source, hb["special1"].resolved_clip, hb["special1"].motion_source,
        hb["throw"].resolved_clip, hb["throw"].motion_source))

prof = resolved(preset("fighter14"))
pb = {m.name: m.resolved_clip for m in prof.moves}
rec("fighter14 profile stays on its own procedural motions",
    len(set(pb.values())) == len(pb) and pb["special1"] == "motion:special_1" and pb["throw"] == "motion:throw"
    and pb["punch"] == "motion:punch", pb["special1"])

# ---------------------------------------------------------------- mannequin build of the fighting pack
BUILD = ["--frame", "96x128", "--quality", "draft", "--no-glb", "--no-fbx", "--expressions", "off",
         "--no-physics", "--no-qa", "--no-cache", "--motion-set", "off"]
rc, log = forge(["build", "--mannequin", "--game", "fighting", "--name", "fighter", "--out", OUT] + BUILD)
man = os.path.join(OUT, "fighter")
moves = [m.name for m in fight.moves]
bad, hashes = same_frames(man, moves) if rc == 0 else (["build failed"], {})
rec("mannequin fighting build", rc == 0 and not bad and "shared clips:" not in log,
    ("rc %d " % rc) + ("; ".join(bad) or "14 distinct frame sequences"))
src = next((ln.strip() for ln in log.splitlines() if ln.strip().startswith("motion source:")), "")
rec("build report: special1 and throw are not the punch source",
    "special1=starter" in src and "throw=starter" in src and "punch=starter" in src, src[:180])

# ---------------------------------------------------------------- fighter14 profile build
rc2, log2 = forge(["build", "--mannequin", "--preset", "fighter14", "--name", "profile", "--out", OUT] + BUILD)
prof_dir = os.path.join(OUT, "profile")
names14 = [m.name for m in prof.moves]
bad2, _ = same_frames(prof_dir, names14) if rc2 == 0 else (["build failed"], {})
rec("mannequin fighter14 profile build", rc2 == 0 and not bad2, ("rc %d " % rc2) + ("; ".join(bad2) or "distinct"))

# ---------------------------------------------------------------- photo puppet, drawn doll (not a person)
def make_doll(folder):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (180, 360), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    skin, top, jean = (210, 170, 140, 255), (40, 90, 160, 255), (50, 70, 120, 255)
    P = {0: (90, 36), 11: (118, 78), 12: (62, 78), 13: (128, 120), 14: (52, 120),
         15: (132, 158), 16: (48, 158), 23: (108, 168), 24: (72, 168),
         25: (106, 230), 26: (74, 230), 27: (104, 300), 28: (76, 300),
         31: (112, 318), 32: (68, 318)}
    d.ellipse((68, 16, 112, 64), fill=skin)
    d.polygon([P[12], P[11], (114, 180), (66, 180)], fill=top)
    d.line([P[11], P[13], P[15]], fill=top, width=14)
    d.line([P[12], P[14], P[16]], fill=top, width=14)
    d.line([P[23], P[25], P[27]], fill=jean, width=16)
    d.line([P[24], P[26], P[28]], fill=jean, width=16)
    d.ellipse((P[31][0] - 12, 308, P[31][0] + 12, 332), fill=(230, 230, 230, 255))
    d.ellipse((P[32][0] - 12, 308, P[32][0] + 12, 332), fill=(230, 230, 230, 255))
    pts = [[90.0, 36.0, 1.0] for _ in range(33)]
    for i, xy in P.items():
        pts[i] = [float(xy[0]), float(xy[1]), 1.0]
    os.makedirs(folder, exist_ok=True)
    im.save(os.path.join(folder, "cutout.png"))
    json.dump({"photo": "drawn-doll", "landmarks": pts, "landmark_format": "mediapipe33"},
              open(os.path.join(folder, "landmarks.json"), "w"))
    return os.path.join(folder, "cutout.png"), os.path.join(folder, "landmarks.json")


doll, lm = make_doll(os.path.join(OUT, "doll"))
rc3, log3 = forge(["build", "--photo", doll, "--landmarks", lm, "--fill", "puppet", "--preset", "fighter14",
                   "--name", "puppet", "--out", OUT] + BUILD)
pup = os.path.join(OUT, "puppet")
watch = ["punch", "kick", "special1", "special2", "throw", "jumpattack", "taunt", "victory"]
bad3, _ = same_frames(pup, watch) if rc3 == 0 else (["build failed"], {})
rec("photo puppet (drawn doll) keeps distinct poses", rc3 == 0 and not bad3,
    ("rc %d " % rc3) + ("; ".join(bad3) or "special / throw / punch differ") + ((" " + log3[-180:].replace("\n", " ")) if rc3 else ""))


def contact(path, rows):
    """rows: [(label, [png paths])]"""
    from PIL import Image, ImageDraw
    cell_w = cell_h = 96
    label_h = 16
    cols = max(len(r[1]) for r in rows)
    sheet = Image.new("RGBA", (cols * cell_w, len(rows) * (cell_h + label_h)), (20, 22, 28, 255))
    dr = ImageDraw.Draw(sheet)
    for ri, (label, paths) in enumerate(rows):
        y = ri * (cell_h + label_h)
        dr.text((4, y), label, fill=(240, 236, 220, 255))
        for ci, pth in enumerate(paths):
            im = Image.open(pth).convert("RGBA")
            if im.size != (cell_w, cell_h):
                im = im.resize((cell_w, cell_h))
            sheet.alpha_composite(im, (ci * cell_w, y + label_h))
    sheet.save(path)
    return path


def mid(folder, move):
    paths = sorted(glob.glob(os.path.join(folder, "moves", move + "_*.png")))
    if not paths:
        return ""
    return paths[len(paths) // 2]


if rc == 0:
    show = ["punch", "special1", "special2", "throw", "jumpattack"]
    after = [mid(man, n) for n in show]
    before = [mid(man, "punch")] * len(show)
    sheet = contact(os.path.join(OUT, "fighter_contact.png"),
                    [("before: specials and throw were the punch clip", before),
                     ("after: each move has its own clip", after)])
    art = "/opt/cursor/artifacts"
    if os.path.isdir(art):
        shutil.copy(sheet, os.path.join(art, "fighter_special_throw_punch.png"))
    rec("contact sheet written", os.path.isfile(sheet) and os.path.getsize(sheet) > 1000, sheet)

failed = [x for x in R if not x[1]]
print("\n%d / %d passed" % (len(R) - len(failed), len(R)))
if failed:
    for name, _, detail in failed:
        print("  FAIL", name, detail)
    sys.exit(1)
print("OUT", OUT)
sys.exit(0)
