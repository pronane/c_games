#!/usr/bin/env python3
"""Check motion clips - any clip, not only the ones it was tuned on - against what a usable game move must satisfy.

    python tools/check_motion.py LIBRARY_DIR                 (every clip in a motion library folder)
    python tools/check_motion.py LIBRARY_DIR/jab.json ...    (some clips)
    python tools/check_motion.py --pack gaelic --library DIR (the clips a game pack would use from that library, and
                                                            the procedural motions it falls back to)

Run it after `forge.py motion import`, `motion record` or `tools/import_cmu.py` (v11.11). Every clip is evaluated on
the shared skeleton, frame by frame, and checked, with the reason when one fails:

  size        a person: feet to head 1.2 - 2.1 m (a unit mix-up gives a doll or a giant); 0.7 m up for a seated or crouched move
  floor       the feet reach the floor (lowest ankle 0 - 15 cm up) and nothing sinks through it
  pops        no joint jumps between frames (hips over 10 m/s, hands and feet over 30 m/s: a glitch, not a move)
  length      0.25 - 15 s and at least 2 keys (hand-keyed clips are interpolated)
  loop        a looping clip ends where it starts (joints within 10 cm of the first pose, from the hips)
  facing      the hips face forward (+z) on average, within 90 degrees - strikes go at the opponent (a spin is allowed)
  turning     a looping clip (walk, run) goes straight: its hips turn at most 45 degrees over the loop
  move        what the move is, read from its name (or its library entry): a block brings the hands up in front,
              a hit knocks the chest back, a fall or KO ends on the ground, a duck or dodge drops the head, a
              celebration lifts a hand over the head, a stop slows the hips, a sidestep moves sideways, a catch
              (or a keeper's save) takes the hands up, in front or overhead, a dive gets low and travels, a swing
              whips a hand through an arc, a get-up ends standing
Planted feet that slide are a warning, not a failure (mocap clean-up: `forge.py motion clean`).
Exit 1 when anything fails."""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

FPS = 30.0
JOINTS = ("hips", "chest", "head", "hand_L", "hand_R", "foot_L", "foot_R")

# what a move must do, keyed by words in its name: the first pattern that matches applies
MOVES = [
    (r"block|guard|parry", "block"),
    (r"get_?up|stand_?up|rise", "get_up"),          # before "fall": a get-up ends standing
    (r"\bko\b|^ko|knock_?out|fall(?!en)|die|death|collapse", "fall"),
    (r"hit|stagger|stumble|react|hurt_react", "hit"),
    (r"duck|dodge|evade", "duck"),
    (r"celebrat|cheer|victory|happy|(^|_)win(_|$)", "celebrate"),   # a taunt can be anything (arms folded)
    (r"^stop|sudden_stop|_stop$", "stop"),
    (r"side_?step|shuffle|strafe", "sidestep"),
    (r"catch|save", "catch"),                      # a keeper's save is a catch in front; a dive is named so
    (r"dive", "dive"),
    (r"swing|forehand|backhand", "swing"),
]


def kind_of(name):
    n = name.lower()
    for pat, k in MOVES:
        if re.search(pat, n):
            return k
    return None


def track(rec, fps=FPS):
    """joint world positions (frames, joints, 3) of a clip record, resampled at fps"""
    from sforge import rig
    keys = rec["keys"]
    if not keys:
        return np.zeros((0, len(JOINTS), 3)), np.zeros(0)
    # key times run 0..1 over the clip; its length in seconds is `duration` (older records: the last key's time)
    scale = float(rec.get("duration") or keys[-1][0] or 1.0) / float(keys[-1][0] or 1.0)
    t_end = float(keys[-1][0]) * scale
    ts = np.arange(0.0, t_end + 1e-6, 1.0 / fps) if t_end > 0 else np.array([0.0])
    # evaluate at the keys, then interpolate positions in time (enough for these checks)
    kt = np.array([float(k[0]) for k in keys]) * scale
    kp = np.array([[rig.evaluate(k[1]).world[j][:3, 3] for j in JOINTS] for k in keys])
    if len(kt) == 1:
        return np.repeat(kp, len(ts), 0), ts
    out = np.empty((len(ts), len(JOINTS), 3))
    for j in range(len(JOINTS)):
        for c in range(3):
            out[:, j, c] = np.interp(ts, kt, kp[:, j, c])
    return out, ts


def heading(rec):
    """the hips' facing about +y at each key, degrees (0 = +z)"""
    from sforge import rig
    z = np.array([rig.evaluate(k[1]).world["hips"][:3, 2] for k in rec["keys"]])
    return np.degrees(np.arctan2(z[:, 0], z[:, 2]))


def J(name):
    return JOINTS.index(name)


def check_clip(rec, name=None):
    name = name or rec.get("name", "?")
    res = []
    keys = rec.get("keys") or []
    dur = float(rec.get("duration") or (keys[-1][0] if keys else 0.0))
    res.append(("length", len(keys) >= 2 and 0.25 <= dur <= 15.0, "%.2f s, %d keys" % (dur, len(keys))))
    if len(keys) < 2:
        return res
    X, ts = track(rec)
    feet = X[:, [J("foot_L"), J("foot_R")], 1]
    low = feet.min(1)
    head_up = X[:, J("head"), 1] - low
    h = float(np.median(head_up)) + 0.25                      # head bone to the top of the head
    # size: from the standing frames (a fall lies down)
    stand = float(np.percentile(head_up, 90)) + 0.25
    seated = any(re.search(r"sit|seat|drive|kart|kneel|crawl|crouch", str(x or "").lower())
                 for x in (name, rec.get("name"), rec.get("from_motion"), rec.get("category")))
    res.append(("size", (0.7 if seated else 1.2) <= stand <= 2.1, "feet to head %.2f m%s" % (stand, " (seated)" if seated else "")))
    # floor
    lowest = float(low.min()); sink = float(X[:, :, 1].min())
    res.append(("floor", -0.03 <= lowest <= 0.15 and sink > -0.05,
                "lowest ankle %.2f m, lowest joint %.2f m" % (lowest, sink)))
    # pops
    v = np.linalg.norm(np.diff(X, axis=0), axis=2) * FPS
    vh = float(v[:, J("hips")].max()); ve = float(v[:, [J("hand_L"), J("hand_R"), J("foot_L"), J("foot_R")]].max())
    res.append(("pops", vh <= 10.0 and ve <= 30.0, "fastest hips %.1f m/s, hand/foot %.1f m/s" % (vh, ve)))
    # loop
    rel = X - X[:, J("hips"):J("hips") + 1]
    if rec.get("loop"):
        gap = float(np.linalg.norm(rel[-1] - rel[0], axis=1).mean())
        res.append(("loop", gap <= 0.10, "ends %.2f m from its first pose" % gap))
    # facing: the hips' heading (0 = +z, forward). A clip may turn while it plays (a spin kick); on average the
    # body faces the opponent, within 90 degrees, unless it spins right round
    hd = heading(rec)
    mean_h = float(np.degrees(np.arctan2(np.sin(np.radians(hd)).mean(), np.cos(np.radians(hd)).mean())))
    spin = float(np.ptp(np.degrees(np.unwrap(np.radians(hd)))))
    res.append(("facing", abs(mean_h) <= 90.0 or spin >= 150.0,
                "faces %+.0f degrees on average%s" % (mean_h, " (spins %.0f)" % spin if spin >= 150.0 else "")))
    if rec.get("loop"):
        res.append(("turning", spin <= 45.0, "the loop turns %.0f degrees (a walk or run cycle goes straight)" % spin))
    # planted feet sliding (warning)
    slides = []
    for f in ("foot_L", "foot_R"):
        y = X[:, J(f), 1]; p = (y - lowest) < 0.04
        pl = p[1:] & p[:-1]
        if pl.sum() > 5:
            sp = np.linalg.norm(np.diff(X[:, J(f), :][:, [0, 2]], axis=0), axis=1)[pl] * FPS
            slides.append(float(np.percentile(sp, 90)))
    if slides and max(slides) > 0.6:
        res.append(("feet", "warn", "a planted foot slides at %.1f m/s (forge.py motion clean)" % max(slides)))
    # the move itself
    k = kind_of(name) or kind_of(rec.get("from_motion") or "") or kind_of(rec.get("category") or "")
    if k:
        res.append(("move", *signature(k, X, rel, h)))
    return res


def signature(k, X, rel, h):
    hip_y = X[:, J("hips"), 1] - X[:, [J("foot_L"), J("foot_R")], 1].min(1).min()
    chest = rel[:, J("chest")]
    hands = rel[:, [J("hand_L"), J("hand_R")]]
    head = rel[:, J("head")]
    if k == "block":
        # a hand comes up to the chest or higher, in front of the body
        up = (hands[:, :, 1] > chest[:, None, 1] - 0.05) & (hands[:, :, 2] > chest[:, None, 2] + 0.05)
        n = int(up.any(1).sum())
        return bool(n >= 3), "block: hands up in front for %d frames" % n
    if k == "hit":
        # the chest is knocked back (from the hips, or the whole body moves back)
        back = (chest[0, 2] - chest[:, 2]).max()
        moved = (X[0, J("hips"), 2] - X[:, J("hips"), 2]).max()
        tilt = np.abs(chest[:, 0] - chest[0, 0]).max()
        ok = back > 0.05 or moved > 0.10 or tilt > 0.08
        return bool(ok), "hit: chest back %.2f m, hips back %.2f m, sway %.2f m" % (back, moved, tilt)
    if k == "get_up":
        # starts low, ends standing with the head above the hips
        n8 = max(1, len(hip_y) // 8)
        start, end = float(hip_y[:n8].mean()), float(hip_y[-n8:].mean())
        head_up = bool((X[-n8:, J("head"), 1] > X[-n8:, J("hips"), 1] + 0.3).all())
        return bool(end > start + 0.25 and end > 0.7 and head_up), \
            "get up: hips %.2f -> %.2f m, head above the hips at the end: %s" % (start, end, head_up)
    if k == "fall":
        end = float(hip_y[-max(1, len(hip_y) // 8):].mean()); top = float(np.percentile(hip_y, 90))
        return bool(end < 0.5 * top), "fall: hips end at %.2f m (standing %.2f m)" % (end, top)
    if k == "duck":
        hy = X[:, J("head"), 1]
        drop = float(hy[0] - hy.min())
        return bool(drop > 0.15), "duck: head drops %.2f m" % drop
    if k == "celebrate":
        over = float((X[:, [J("hand_L"), J("hand_R")], 1] - X[:, J("head"), 1][:, None]).max())
        return bool(over > 0.0), "celebrate: a hand %.2f m over the head" % over
    if k == "stop":
        sp = np.linalg.norm(np.diff(X[:, J("hips"), :][:, [0, 2]], axis=0), axis=1) * FPS
        n = max(1, len(sp) // 5)
        a, b = float(sp[:n].mean()), float(sp[-n:].mean())
        return bool(a > 0.8 and b < 0.4 * a), "stop: hips %.1f -> %.1f m/s" % (a, b)
    if k == "sidestep":
        span = float(np.ptp(X[:, J("hips"), 0]))
        return bool(span > 0.3), "sidestep: hips move %.2f m sideways" % span
    if k == "catch":
        # in front of the chest, or overhead (a high catch takes the ball above the head)
        up = (hands[:, :, 1] > chest[:, None, 1] - 0.1) & ((hands[:, :, 2] > 0.2) | (hands[:, :, 1] > chest[:, None, 1] + 0.45))
        n = int(up.all(1).sum())
        return bool(n >= 2), "catch: both hands up, in front or overhead, for %d frames" % n
    if k == "dive":
        low = float(hip_y.min()); top = float(np.percentile(hip_y, 90))
        trav = float(np.linalg.norm(np.ptp(X[:, J("hips"), :][:, [0, 2]], axis=0)))
        return bool(low < 0.6 * top and trav > 0.5), "dive: hips down to %.2f m (from %.2f), travel %.2f m" % (low, top, trav)
    if k == "swing":
        best = 0.0
        for hj in (J("hand_L"), J("hand_R")):
            p = rel[:, hj]
            w = int(0.6 * FPS)
            for i in range(0, max(1, len(p) - w)):
                seg = p[i:i + w + 1]
                best = max(best, float(np.linalg.norm(np.diff(seg, axis=0), axis=1).sum()))
        return bool(best > 1.0), "swing: a hand travels %.2f m in 0.6 s" % best
    return True, k


def load_lib(path):
    if os.path.isdir(path):
        fs = sorted(f for f in glob.glob(os.path.join(path, "*.json")) if not os.path.basename(f).startswith(("_", "index", "licence")))
    else:
        fs = [path]
    out = []
    for f in fs:
        try:
            r = json.load(open(f))
        except Exception as e:                                   # noqa: BLE001
            out.append((f, None, str(e))); continue
        if isinstance(r, dict) and "keys" in r:
            out.append((f, r, ""))
    return out


def pack_clips(pack, library):
    """(move, clip path or "procedural:<motion>", record) for each move of a game pack: the clip the build would pick
    (its prefer list, then its library name, from your library, then the starter), or the procedural motion the
    build falls back to when there is no clip"""
    from sforge import gamepack as GP, motionlib as ML
    from sforge.motions import find_motion
    lib = ML.MotionLibrary(library) if library else ML.MotionLibrary()
    out = []
    for m in GP.load(pack)["moves"]:
        for n in list(m["prefer"]) + [m["library"]]:
            if lib.has(n):
                p = lib.path_of(n)
                out.append((m["name"], p, json.load(open(p))))
                break
        else:
            src = find_motion(m["name"])
            if src is not None:
                keys = [(float(t), dict(q)) for t, q in src.keys] if src.keys else \
                    [(i / 8.0, dict(src.sample(i / 8.0)[0])) for i in range(9)]
                out.append((m["name"], "procedural:" + src.name,
                            dict(name=m["name"], keys=keys, loop=bool(src.loop), duration=1.0 if src.loop else 0.8)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--pack", help="check the clips this game pack would use")
    ap.add_argument("--library", help="with --pack: your motion library folder")
    a = ap.parse_args(argv)
    items = []
    for p in a.paths:
        items += [(os.path.splitext(os.path.basename(f))[0], f, r, e) for f, r, e in load_lib(p)]
    if a.pack:
        for mv, f, r in pack_clips(a.pack, a.library):
            items.append((mv, f, r, ""))
    if not items:
        print("nothing to check"); return 0
    bad = 0
    for name, f, r, err in items:
        res = [("file", False, err)] if r is None else check_clip(r, name)
        fails = [x for x in res if x[1] is False]
        bad += bool(fails)
        src = " (procedural)" if str(f).startswith("procedural:") else ""
        print("%-22s %s%s" % (name, "FAIL" if fails else "ok", src))
        for area, ok, text in res:
            if ok is not True:
                print("   %-5s %-7s %s" % ({False: "FAIL", "warn": "warn"}[ok], area, text))
    print("\n%d of %d clips pass" % (len(items) - bad, len(items)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
