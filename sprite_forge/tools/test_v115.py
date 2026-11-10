#!/usr/bin/env python3
"""v11.5 recording sessions, game-type packs, game_character.json. Synthetic only.

  python tools/test_v115.py [OUT_DIR]

No photos, no video of a person, no MediaPipe. Clips are pose-track JSON (the file the
existing mocap tracker writes) plus a couple of solid-colour mp4s for "too dark" and
"too short". The mannequin is the only character that gets built.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
PY = sys.executable
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_v115_")
os.makedirs(OUT, exist_ok=True)
LIB = os.path.join(OUT, "library")
os.makedirs(LIB, exist_ok=True)
R = []


def rec(sec, name, ok, detail=""):
    R.append(dict(section=sec, name=name, ok=bool(ok), detail=str(detail)))
    print("%-5s %-10s %-56s %s" % ("PASS" if ok else "FAIL", sec, name, detail))
    sys.stdout.flush()


def forge(args, env=None):
    e = dict(os.environ)
    e["SFS_LIBRARY"] = LIB
    e.pop("SFS_MOTION_SET", None)
    e.pop("SFS_MOTIONS", None)
    e.update(env or {})
    p = subprocess.run([PY, os.path.join(HERE, "forge.py")] + list(args),
                       capture_output=True, text=True, env=e, cwd=HERE)
    return p.returncode, p.stdout + p.stderr


# ---------------------------------------------------------------- synthetic tracks (pose-track JSON, not a person)
W, H, FPS, N = 320, 240, 10, 33


def _frame(wrist_x, ankle_y, arm_out=True, null=False, nose_y=None):
    if null:
        return None
    img = [[W / 2, H * 0.55, 1.0] for _ in range(N)]
    world = [[0.0, 0.0, 0.0] for _ in range(N)]

    def put(i, x, y):
        img[i] = [float(x), float(y), 1.0]
        world[i] = [(x - W / 2) / W, (y - H / 2) / H, 0.0]

    put(0, W * 0.50, H * 0.16 if nose_y is None else nose_y)
    put(7, W * 0.48, H * 0.18)
    put(8, W * 0.52, H * 0.18)
    put(11, W * 0.42, H * 0.30)
    put(12, W * 0.58, H * 0.30)
    if arm_out:
        put(13, W * 0.30, H * 0.30)
        put(14, W * 0.70, H * 0.30)
        put(15, W * 0.18, H * 0.30)
        put(16, wrist_x, H * 0.30)
    else:
        put(13, W * 0.44, H * 0.45)
        put(14, W * 0.56, H * 0.45)
        put(15, W * 0.44, H * 0.58)
        put(16, W * 0.56, H * 0.58)
    put(23, W * 0.46, H * 0.55)
    put(24, W * 0.54, H * 0.55)
    put(25, W * 0.46, H * 0.72)
    put(26, W * 0.54, H * 0.72)
    put(27, W * 0.46, ankle_y)
    put(28, W * 0.54, ankle_y)
    put(29, W * 0.44, ankle_y + 4)
    put(30, W * 0.56, ankle_y + 4)
    put(31, W * 0.42, min(H - 1, ankle_y + 8))
    put(32, W * 0.60, min(H - 1, ankle_y + 8))
    return {"img": img, "world": world}


def _track(frames, luma=140):
    return {"fps": FPS, "size": [W, H], "frames": frames, "mean_luma": luma}


def _tpose(n, ankle=None):
    ay = H * 0.86 if ankle is None else ankle
    return [_frame(W * 0.78, ay, True) for _ in range(n)]


def _good_punch():
    fr = _tpose(FPS)  # 1 s, arms out
    for r in range(3):
        for i in range(8):
            wx = W * 0.58 + W * 0.22 * math.sin(math.pi * i / 7.0)
            # repeat 0 loses the person, repeat 2 steps out of the bottom of the frame
            null = r == 0 and 3 <= i <= 5
            ay = H * 0.995 if r == 2 else H * 0.86
            fr.append(_frame(wx, ay, True, null=null))
    return _track(fr)


def _good_walk():
    fr = _tpose(FPS)
    for r in range(2):
        for i in range(8):
            wx = W * 0.50 + W * 0.08 * math.sin(2 * math.pi * i / 8.0)
            fr.append(_frame(wx, H * 0.86, True))
    return _track(fr)


def _write(folder, name, track):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(track, f)


CLIPS = os.path.join(OUT, "clips")
os.makedirs(CLIPS, exist_ok=True)
_write(CLIPS, "punch.json", _good_punch())
_write(CLIPS, "walk.json", _good_walk())
# feet out for the whole take (T-pose included, so the only reason left is the feet)
feet = _tpose(FPS, ankle=H * 0.995) + [_frame(W * 0.6, H * 0.995, True) for _ in range(20)]
_write(CLIPS, "bad_feet.json", _track(feet))
# arms hanging, so there is no T-pose
hang = [_frame(W * 0.5, H * 0.86, arm_out=False) for _ in range(24)]
_write(CLIPS, "bad_notpose.json", _track(hang))
# head on the top edge for the whole take
_write(CLIPS, "bad_cutoff.json", _track([_frame(W * 0.7, H * 0.86, True, nose_y=0) for _ in range(24)]))
_write(CLIPS, "bad_short.json", _track(_tpose(4)))
_write(CLIPS, "bad_lost.json", _track([None] * 24))
_write(CLIPS, "bad_dark.json", _track(_tpose(FPS) + [_frame(W * 0.6, H * 0.86, True) for _ in range(16)], luma=8))

# solid-colour videos: no person in them. Too dark / too short are decided before the tracker runs.
from sforge import media
media.encode([__import__("numpy").zeros((64, 64, 3), "uint8")] * 20, os.path.join(CLIPS, "dark.mp4"), fps=10)
bright = __import__("numpy").full((64, 64, 3), 220, "uint8")
media.encode([bright] * 3, os.path.join(CLIPS, "short.mp4"), fps=10)

rc, log = forge(["motion", "record", "--folder", CLIPS, "--set", "owner"])
rec("session", "folder import runs (exit 1 when a clip needs a reshoot)", rc == 1 and "skeleton motion only" in log, "rc %d" % rc)
rec("session", "punch and walk stored", "punch.json" in log and "walk.json" in log and "Stored: punch, walk" in log.replace("\n", " ") or ("punch" in log and "walk" in log and "Stored:" in log), "")
# the Stored line is the reliable one
stored_line = next((ln for ln in log.splitlines() if ln.startswith("Stored:")), "")
rec("session", "named set keeps the good moves", "punch" in stored_line and "walk" in stored_line, stored_line)
reshoot = next((ln for ln in log.splitlines() if ln.startswith("Reshoot:")), "")
for token, why in (("bad_feet.json", "feet out of frame"), ("bad_notpose.json", "no T-pose"),
                   ("bad_cutoff.json", "body cut off"), ("bad_short.json", "too short"),
                   ("bad_lost.json", "tracking lost"), ("bad_dark.json", "too dark"),
                   ("dark.mp4", "too dark"), ("short.mp4", "too short")):
    line = next((ln for ln in log.splitlines() if ln.startswith(token)), "")
    rec("session", "%s flagged: %s" % (token, why), why in line and token in reshoot, line.strip()[:80] or "missing")
rec("session", "best punch repeat is called out", "best repeat 2 of 3" in log, "")

set_dir = os.path.join(LIB, "motion_sets", "owner")
punch = json.load(open(os.path.join(set_dir, "punch.json"), encoding="utf-8"))
blob = json.dumps(punch)
rec("session", "stored file is skeleton keys", "keys" in punch and '"img"' not in blob and '"video"' not in blob and '"world"' not in blob, punch.get("source"))
rec("session", "walk is a loop", json.load(open(os.path.join(set_dir, "walk.json"), encoding="utf-8")).get("loop") is True, "")
media_left = [f for f in os.listdir(set_dir) if os.path.splitext(f)[1].lower() in (".mp4", ".png", ".jpg", ".jpeg", ".webp", ".mov")]
rec("session", "no video or frames left in the set", media_left == [], str(media_left))
meta = json.load(open(os.path.join(set_dir, "_set.json"), encoding="utf-8"))
rec("session", "set says the video was not kept", meta.get("video_kept") is False and meta.get("frames_kept") is False and "not stored" in meta.get("note", ""), "")
rec("session", "rejected moves are not files", not os.path.isfile(os.path.join(set_dir, "bad_feet.json")) and not os.path.isfile(os.path.join(set_dir, "dark.mp4")), "")

rc, shot = forge(["motion", "shotlist", "--game", "soccer"])
rec("session", "shot list names the clips", rc == 0 and "kick.mp4" in shot and "feet out of frame" in shot and "skeleton" in shot.lower(), "")

# ---------------------------------------------------------------- default set changes the build report
BASE = ["build", "--mannequin", "--game", "boxing", "--name", "boxer", "--frame", "96x96",
        "--quality", "draft", "--no-glb", "--no-fbx", "--expressions", "off", "--no-physics", "--no-qa", "--no-cache"]
rc, off = forge(BASE + ["--motion-set", "off", "--out", os.path.join(OUT, "off")])
rc2, on = forge(BASE + ["--motion-set", "owner", "--out", os.path.join(OUT, "on")])
def src_line(text):
    return next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("motion source:")), "")
rec("set", "no set: jab comes from the starter", rc == 0 and "jab=starter" in src_line(off), src_line(off)[:80])
rec("set", "named set: jab comes from the recording", rc2 == 0 and "jab=set:owner" in src_line(on), src_line(on)[:90])
rc, _ = forge(["motion", "use-set", "owner"])
rc3, saved = forge(BASE + ["--out", os.path.join(OUT, "saved")])
rec("set", "saved default is used without a flag", rc == 0 and rc3 == 0 and "jab=set:owner" in src_line(saved), src_line(saved)[:90])

# ---------------------------------------------------------------- packs
from sforge.gamepack import list_packs, validate, load
names = list_packs()
need = ["fighting", "gaelic", "platformer", "topdown_rpg", "kart", "soccer", "basketball",
        "boxing", "wrestling", "tennis", "beat_em_up", "shooter"]
rec("pack", "shipped packs are present", set(need) <= set(names), ", ".join(names))
rc, vlog = forge(["game", "validate"])
rec("pack", "every shipped pack validates", rc == 0 and "ERRORS" not in vlog, "")
# a file the tool did not know about
custom = {
    "name": "custom_wave", "label": "Custom wave", "description": "Added as a file. No code change.",
    "camera": "side", "frame": [96, 96],
    "moves": [{"name": "wave", "library": "wave", "frames": 4, "fps": 8, "loop": False,
               "events": {"flourish": 1}}],
}
custom_path = os.path.join(OUT, "custom_wave.json")
json.dump(custom, open(custom_path, "w"))
errs, warns = validate(custom_path)
rec("pack", "a new JSON pack loads with no code change", not errs and load(custom_path)["moves"][0]["events"].get("flourish") == 1, str(errs))

BUILD = ["--mannequin", "--frame", "96x96", "--quality", "draft", "--no-glb", "--no-fbx",
         "--expressions", "off", "--no-physics", "--no-qa", "--no-cache", "--motion-set", "off",
         "--character-type", "quick_striker"]
built = {}
for n in need + ["custom"]:
    game = custom_path if n == "custom" else n
    dest = os.path.join(OUT, "packs", n)
    rc, blog = forge(["build", "--game", game, "--name", n, "--out", os.path.join(OUT, "packs")] + BUILD)
    man = os.path.join(dest, "game_character.json")
    ok = rc == 0 and os.path.isfile(man)
    built[n] = man if ok else ""
    rec("pack", "build %s" % n, ok, "rc %d" % rc if not ok else src_line(blog)[:60])

from sforge.gamemanifest import validate_file
for n, man in built.items():
    if not man:
        continue
    e, w = validate_file(man)
    rec("manifest", "%s manifest validates" % n, not e, "; ".join(e)[:120])

soc = json.load(open(built["soccer"], encoding="utf-8")) if built.get("soccer") else {}
box = json.load(open(built["boxing"], encoding="utf-8")) if built.get("boxing") else {}
soc_names = [a["name"] for a in soc.get("animations") or []]
box_names = [a["name"] for a in box.get("animations") or []]
rec("pack", "soccer and boxing move lists differ", soc_names != box_names and "kick" in soc_names and "jab" in box_names,
    "%d vs %d" % (len(soc_names), len(box_names)))
rec("pack", "same character type on both", soc.get("character_type") == "quick_striker" and box.get("character_type") == "quick_striker", "")
def ev(doc, move, key):
    for a in doc.get("animations") or []:
        if a["name"] == move:
            return (a.get("events") or {}).get(key, None)
    return None
rec("pack", "soccer kick has a ball contact, boxing jab has a hit",
    isinstance(ev(soc, "kick", "ball_contact"), int) and ev(soc, "kick", "ball_contact") >= 0
    and ev(box, "jab", "hit_start") >= 0 and ev(box, "jab", "ball_contact") == -1, "")
cus = json.load(open(built["custom"], encoding="utf-8")) if built.get("custom") else {}
cus_wave = next((a for a in cus.get("animations") or [] if a["name"] == "wave"), {})
rec("pack", "custom event survives into the manifest", (cus_wave.get("events") or {}).get("flourish") == 1, str(cus_wave.get("events")))

# adapters: drop the index files and rebuild them from the manifest, then the Egyptian Fighter exporter still runs
fight = os.path.join(OUT, "packs", "fighting")
if os.path.isdir(fight):
    os.remove(os.path.join(fight, "atlas.json"))
    os.remove(os.path.join(fight, "sprites.cfg"))
    ef_out = os.path.join(OUT, "ef_out")
    r = subprocess.run([PY, os.path.join(HERE, "tools", "export_ef.py"), fight, ef_out], capture_output=True, text=True)
    rec("adapter", "Egyptian Fighter export reads the manifest", r.returncode == 0 and os.path.isfile(os.path.join(ef_out, "sprites.cfg")),
        (r.stdout + r.stderr)[-200:])
    r2 = subprocess.run([PY, os.path.join(HERE, "tools", "to_egyptian_fighter.py"), fight, os.path.join(OUT, "ef2")],
                        capture_output=True, text=True)
    rec("adapter", "to_egyptian_fighter reads the manifest", r2.returncode == 0 and os.path.isfile(os.path.join(OUT, "ef2", "sprites.cfg")),
        (r2.stdout + r2.stderr)[-160:])
else:
    rec("adapter", "fighting build missing", False, "")

# ---------------------------------------------------------------- raylib loader
preview = os.path.join(OUT, "raylib_preview.png")
ray_ok = False
ray_detail = ""
if built.get("boxing"):
    exe = os.path.join(OUT, "gc_example")
    ray = "/tmp/sfray/raylib/src"
    if not os.path.isfile(os.path.join(ray, "libraylib.a")):
        ray_detail = "raylib not built at " + ray
    else:
        cmd = ["gcc", "-std=c99", "-O2", "-Wall",
               "-I", os.path.join(HERE, "loaders", "raylib"), "-I", ray,
               os.path.join(HERE, "loaders", "raylib", "example.c"),
               "-o", exe, "-L", ray, "-lraylib", "-lGL", "-lm", "-lpthread", "-ldl", "-lrt", "-lX11"]
        c = subprocess.run(cmd, capture_output=True, text=True)
        if c.returncode != 0:
            ray_detail = (c.stderr or c.stdout)[-400:]
        else:
            run = subprocess.run(["xvfb-run", "-a", exe, os.path.join(OUT, "packs", "boxing"), "--shots", preview, "--seconds", "0.2"],
                                 capture_output=True, text=True)
            ray_ok = run.returncode == 0 and os.path.isfile(preview) and os.path.getsize(preview) > 1000
            ray_detail = (run.stdout or run.stderr or "no output")[-200:]
rec("loader", "raylib example compiles and draws the manifest", ray_ok, ray_detail.replace("\n", " ")[:160])
art = "/opt/cursor/artifacts"
if ray_ok and os.path.isdir(art):
    shutil.copy(preview, os.path.join(art, "v115_raylib_preview.png"))

# help text mentions the commands
rc, help_game = forge(["help", "game"])
rec("docs", "forge.py help game has the commands", rc == 0 and "motion record --folder" in help_game and "game_character.json" in help_game
    and "feet out of frame" in help_game, "")

failed = [x for x in R if not x["ok"]]
print("\n%d / %d passed" % (len(R) - len(failed), len(R)))
if failed:
    print("FAILED:")
    for x in failed:
        print("  [%s] %s — %s" % (x["section"], x["name"], x["detail"]))
    sys.exit(1)
print("OUT", OUT)
sys.exit(0)
