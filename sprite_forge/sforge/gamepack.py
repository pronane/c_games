"""v11.5 game-type packs — what a genre needs, as data.

A pack is one JSON file. It does not replace profiles (fighter14, gaelic36, ... still
build exactly as before). A pack says:

  moves     the names the game uses, each mapped to a generic motion-library clip
            (punch, kick, walk, ...). Frame count, fps and loop are per move.
  camera    side | three_quarter | topdown8
  props     things the GAME draws (a ball, a kart). Sprite Forge does not draw them.
  events    gameplay frames: hit_start / hit_end, ball_contact, footsteps, throw_release,
            shoot, reload. -1 or [] means "this move has none". Extra numeric keys are
            kept for a pack you write yourself; the small loaders read the known ones.

Drop a file in game_packs/ or pass a path. No code change.

Character types (v11.4) apply on top: the pack chooses the moves, the type chooses
how the same skeleton clip is performed.
"""
from __future__ import annotations
import json
import os

from .moves import MoveSpec, slug

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_DIR = os.path.join(HERE, "game_packs")
CAMERAS = {"side", "three_quarter", "topdown8"}
EVENT_KEYS = ("hit_start", "hit_end", "ball_contact", "throw_release", "shoot", "reload")


def list_packs():
    if not os.path.isdir(PACK_DIR):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(PACK_DIR) if f.endswith(".json") and not f.startswith("_"))


def path_of(name_or_path):
    if not name_or_path:
        raise ValueError("game pack name is empty")
    if os.path.isfile(name_or_path):
        return name_or_path
    p = name_or_path if str(name_or_path).endswith(".json") else str(name_or_path) + ".json"
    if os.path.isfile(p):
        return p
    cand = os.path.join(PACK_DIR, os.path.basename(p))
    if os.path.isfile(cand):
        return cand
    raise FileNotFoundError("game pack '%s' not found (have: %s)" % (name_or_path, ", ".join(list_packs()) or "none"))


def _events(raw):
    src = raw or {}
    if not isinstance(src, dict):
        raise ValueError("events must be an object")
    out = {}
    for k in EVENT_KEYS:
        v = src.get(k, -1)
        if v is None or v == "":
            v = -1
        out[k] = int(v)
    steps = src.get("footsteps", [])
    if steps is None:
        steps = []
    if isinstance(steps, int):
        steps = [steps]
    out["footsteps"] = [int(x) for x in steps]
    for k, v in src.items():
        if k in out or k == "footsteps":
            continue
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out[k] = int(v)
        elif isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
            out[k] = [int(x) for x in v]
    return out


def load(name_or_path):
    p = path_of(name_or_path)
    with open(p, encoding="utf-8") as f:
        try:
            d = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("%s is not valid JSON: %s" % (p, e))
    if not isinstance(d, dict):
        raise ValueError("%s must be a JSON object" % p)
    name = str(d.get("name") or os.path.splitext(os.path.basename(p))[0])
    cam = str(d.get("camera") or "side")
    if cam not in CAMERAS:
        raise ValueError("%s: camera must be one of %s" % (p, ", ".join(sorted(CAMERAS))))
    moves = d.get("moves")
    if not isinstance(moves, list) or not moves:
        raise ValueError("%s: 'moves' must be a non-empty list" % p)
    norm = []
    seen = set()
    for i, m in enumerate(moves):
        if not isinstance(m, dict) or not m.get("name"):
            raise ValueError("%s: moves[%d] needs a name" % (p, i))
        nm = slug(m["name"])
        if nm in seen:
            raise ValueError("%s: move '%s' is listed twice" % (p, nm))
        seen.add(nm)
        lib = slug(m.get("library") or nm)
        try:
            frames = int(m.get("frames", 6))
            fps = int(m.get("fps", 12))
        except (TypeError, ValueError):
            raise ValueError("%s: move '%s' frames and fps must be numbers" % (p, nm))
        if frames < 1 or frames > 64 or fps < 1 or fps > 60:
            raise ValueError("%s: move '%s' frames 1..64 and fps 1..60" % (p, nm))
        norm.append({
            "name": nm,
            "label": str(m.get("label") or nm.replace("_", " ").title()),
            "library": lib,
            "frames": frames,
            "fps": fps,
            "loop": bool(m.get("loop", False)),
            "category": str(m.get("category") or "Game"),
            "events": _events(m.get("events")),
            "desc": str(m.get("desc") or ""),
        })
    yaw = d.get("yaw")
    if yaw is None:
        yaw = {"side": 90, "three_quarter": 65, "topdown8": 90}[cam]
    frame = d.get("frame") or [128, 160]
    if not (isinstance(frame, (list, tuple)) and len(frame) == 2):
        raise ValueError("%s: frame must be [width, height]" % p)
    return {
        "name": name,
        "label": str(d.get("label") or name.replace("_", " ").title()),
        "description": str(d.get("description") or ""),
        "camera": cam,
        "yaw": float(yaw),
        "props": [str(x) for x in (d.get("props") or [])],
        "prop": str(d.get("prop") or "none"),
        "frame": [int(frame[0]), int(frame[1])],
        "view_moves": [slug(x) for x in (d.get("view_moves") or [])],
        "notes": str(d.get("notes") or ""),
        "moves": norm,
        "path": p,
    }


def validate(name_or_path):
    """-> (errors, warnings). A warning if a library name is not in the starter — the procedural motion fills it."""
    from .motionlib import has_move
    errs, warns = [], []
    try:
        pack = load(name_or_path)
    except (ValueError, FileNotFoundError, OSError) as e:
        return [str(e)], []
    for m in pack["moves"]:
        if not has_move(m["library"]):
            warns.append("%s: library '%s' is not in the starter — the build uses the procedural motion of that name if there is one" % (m["name"], m["library"]))
        ev = m["events"]
        if ev["hit_start"] >= 0 and ev["hit_end"] >= 0 and ev["hit_end"] < ev["hit_start"]:
            errs.append("%s: hit_end is before hit_start" % m["name"])
        for k in ("hit_start", "hit_end", "ball_contact", "throw_release", "shoot", "reload"):
            if ev[k] >= m["frames"]:
                warns.append("%s: %s frame %d is past the last frame (%d) — it will be scaled if the build uses fewer frames" % (m["name"], k, ev[k], m["frames"]))
    return errs, warns


def moves_of(pack):
    """MoveSpecs pointing at the shared library. `want_library` tells the set resolver to fall back to the starter."""
    pack = pack if isinstance(pack, dict) and "moves" in pack else load(pack)
    out = []
    for m in pack["moves"]:
        spec = MoveSpec(m["name"], m["label"], m["category"], m["frames"], m["fps"], m["loop"],
                        "lib:" + m["library"], m["desc"] or pack["name"])
        spec.want_library = True
        spec.pack_frames = m["frames"]
        spec.library_name = m["library"]
        out.append(spec)
    return out


def events_of(pack):
    pack = pack if isinstance(pack, dict) and "moves" in pack else load(pack)
    return {m["name"]: dict(m["events"]) for m in pack["moves"]}


def apply(cfg, name_or_path):
    """Fill a BuildConfig from a pack. Explicit --frame / --yaw afterwards still win (forge.py applies those later)."""
    pack = load(name_or_path)
    cfg.game_pack = pack["name"]
    cfg.game_pack_path = pack["path"]
    cfg.game_camera = pack["camera"]
    cfg.game_props = list(pack["props"])
    cfg.game_events = events_of(pack)
    cfg.moves = moves_of(pack)
    cfg.yaw = pack["yaw"]
    cfg.frame_w, cfg.frame_h = pack["frame"]
    if pack["prop"] in ("none", "kart", "auto"):
        cfg.prop = pack["prop"]
    if pack["camera"] == "topdown8":
        cfg.billboard8 = True
        cfg.view_moves = pack["view_moves"] or [m["name"] for m in pack["moves"][:3]]
    return pack


def scale_events(events, src_n, dst_n):
    """Map frame indices from the pack's frame count onto the frames that were actually built."""
    if not events:
        return {}
    src_n = max(1, int(src_n or 1))
    dst_n = max(1, int(dst_n or 1))

    def sc(i):
        i = int(i)
        if i < 0 or src_n == dst_n:
            return i
        if src_n <= 1:
            return 0
        return max(0, min(dst_n - 1, int(round(i * (dst_n - 1) / float(src_n - 1)))))

    out = {}
    for k, v in events.items():
        if isinstance(v, list):
            out[k] = [sc(x) for x in v]
        elif isinstance(v, int):
            out[k] = sc(v)
        else:
            out[k] = v
    return out


def shotlist(name_or_path):
    """Printable checklist: one line per clip the owner should film for this game type."""
    pack = load(name_or_path)
    cam = {"side": "side-on (camera square to the side, character facing right)",
           "three_quarter": "three-quarter (about 65 degrees, character facing toward image-right)",
           "topdown8": "side-on for the library clip; the game also shows 8 directions from that clip"}[pack["camera"]]
    L = []
    L.append("%s — shot list" % pack["label"])
    L.append(pack["description"])
    L.append("")
    L.append("Film yourself. One clip per move. Name the file after the move (punch.mp4, walk.mp4).")
    L.append("Camera: %s." % cam)
    L.append("Full body in frame, feet on the ground, bright enough to see the limbs.")
    L.append("Start with about 1 second of a T-pose (arms straight out at shoulder height), then do the move about 3 times.")
    L.append("Optional: a front-on clip of idle, walk and run, named idle_front.mp4, walk_front.mp4, run_front.mp4.")
    L.append("Sprite Forge stores the skeleton only. The video, the frames, your face and your body shape are deleted after the fit.")
    L.append("")
    L.append("%-22s %-6s %-16s %s" % ("file", "play", "library clip", "what the game reads"))
    for m in pack["moves"]:
        ev = m["events"]
        bits = []
        if ev["hit_start"] >= 0:
            bits.append("hit frames %d-%d" % (ev["hit_start"], ev["hit_end"] if ev["hit_end"] >= 0 else ev["hit_start"]))
        if ev["ball_contact"] >= 0:
            bits.append("ball contact %d" % ev["ball_contact"])
        if ev["throw_release"] >= 0:
            bits.append("throw release %d" % ev["throw_release"])
        if ev["shoot"] >= 0:
            bits.append("shoot %d" % ev["shoot"])
        if ev["reload"] >= 0:
            bits.append("reload %d" % ev["reload"])
        if ev["footsteps"]:
            bits.append("footsteps %s" % ",".join(str(x) for x in ev["footsteps"]))
        L.append("[ ] %-18s %-6s %-16s %s" % (
            m["name"] + ".mp4", "loop" if m["loop"] else "once", m["library"],
            "; ".join(bits) or m["desc"] or m["category"]))
        if m["name"] in ("idle", "walk", "run"):
            L.append("    optional front clip: %s_front.mp4" % m["name"])
    L.append("")
    L.append("After filming:  forge.py motion record --folder CLIPS --set my_moves")
    L.append("The checker will say, in plain language, which clips to reshoot:")
    L.append("  feet out of frame, body cut off, too dark, no T-pose, too short, tracking lost.")
    if pack["props"]:
        L.append("Props the game draws (not in the video): %s." % ", ".join(pack["props"]))
    if pack["notes"]:
        L.append("")
        L.append(pack["notes"])
    return "\n".join(L) + "\n"


def main(argv):
    import argparse
    p = argparse.ArgumentParser(prog="forge.py game", description="Game-type packs (v11.5). A JSON file per genre. forge.py help game")
    sub = p.add_subparsers(dest="act")
    sub.add_parser("list", help="shipped packs and any JSON you added in game_packs/")
    sh = sub.add_parser("show", help="one pack: moves, camera, events")
    sh.add_argument("name")
    v = sub.add_parser("validate", help="check a pack file (or every shipped pack)")
    v.add_argument("name", nargs="?", help="pack name or a path; omit to check every shipped pack")
    sl = sub.add_parser("shotlist", help="printable checklist of clips to film for a pack")
    sl.add_argument("name")
    sl.add_argument("--out", help="also write the checklist to this text file")
    a = p.parse_args(argv)
    try:
        if a.act in (None, "list"):
            print("game packs (%s):" % PACK_DIR)
            print("  %-16s %-14s %3s  %s" % ("name", "camera", "n", "label"))
            for n in list_packs():
                g = load(n)
                print("  %-16s %-14s %3d  %s" % (g["name"], g["camera"], len(g["moves"]), g["label"]))
            print("Add one by dropping a JSON file in game_packs/ (or pass the path to forge.py build --game).")
            return 0
        if a.act == "show":
            g = load(a.name)
            print("%s — %s" % (g["label"], g["description"]))
            print("  camera %s   yaw %g   props %s" % (g["camera"], g["yaw"], ", ".join(g["props"]) or "none"))
            print("  %s" % g["path"])
            if g["notes"]:
                print("  " + g["notes"])
            print("  %-16s %-12s %5s %4s  %s" % ("move", "library", "frames", "fps", "events"))
            for m in g["moves"]:
                ev = {k: v for k, v in m["events"].items() if v not in (-1, [])}
                print("  %-16s %-12s %5d %4d  %s" % (m["name"], m["library"], m["frames"], m["fps"],
                                                    json.dumps(ev) if ev else ("loop" if m["loop"] else "once")))
            return 0
        if a.act == "validate":
            names = [a.name] if a.name else list_packs()
            rc = 0
            for n in names:
                errs, warns = validate(n)
                print("%s: %s" % (n, "ok" if not errs else "ERRORS"))
                for e in errs:
                    print("  error: " + e)
                    rc = 1
                for w in warns:
                    print("  warning: " + w)
            return rc
        if a.act == "shotlist":
            text = shotlist(a.name)
            print(text, end="")
            if a.out:
                with open(a.out, "w", encoding="utf-8") as f:
                    f.write(text)
                print("wrote %s" % a.out)
            return 0
    except (ValueError, FileNotFoundError, OSError) as e:
        print("error:", e)
        return 2
    p.print_help()
    return 2
