#!/usr/bin/env python3
"""Import real in-match football motion from SkillCorner's open body-pose data.

SkillCorner Open Data - Body Pose (huggingface.co/datasets/SkillCorner/opendata-bodypose,
MIT licence) gives 29 3D joints per player at 25 fps for two full A-League matches,
estimated from the broadcast video.  The same matches' dynamic events (the opendata repo,
MIT) say when each player shot, passed, received, won the ball or carried it.

This joins the two: for every shot, pass, lofted pass, clearance, first touch, ball win
and carry it cuts the player's joints around the moment, keeps the cleanest takes
(complete, detected, low joint error, varied players), fits each onto the shared
skeleton with Sprite Forge's joint-track fitter (sforge.jointtrack - the mocap IK) and
saves them as Sprite Forge library moves in Data/mocap/skillcorner/ with their licence
record.  Tools/soccer_motions.py bakes them into the player GLB like the CMU takes, and
the clip manifest / motion-matching table pick them up.

    python3 Tools/import_skillcorner_pose.py --pose-dir DIR --events-dir OPENDATA/data/matches
           [--work DIR] [--per-kind shot=10,pass=10,...]

DIR holds <match>.jsonl.zip from the Hugging Face dataset.  Extraction streams each
3.3 GB file once (~45 s) and caches the moments in --work.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import pickle
import re
import sys
import time
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)

OUT = os.path.join(ARENA, "Data", "mocap", "skillcorner")
MANIFEST = os.path.join(ARENA, "Data", "clips", "clip_manifest.json")
MATCHES = ("1925299", "1996435")
FPS_T, FPS_P = 10.0, 25.0

LICENCE = dict(
    spdx="MIT",
    custom_text="",
    author="SkillCorner (with PySport)",
    source_url="https://huggingface.co/datasets/SkillCorner/opendata-bodypose",
    redistribution="yes",
    attribution="Body pose and event data: SkillCorner Open Data (MIT licence).",
    notes=("3D joints estimated from broadcast video (7-15 cm per joint). Events from "
           "github.com/SkillCorner/opendata. Fitted onto the shared skeleton with sforge.jointtrack."),
)

# kind -> (event anchor, seconds before, seconds after, library category, game category, ball state)
KINDS = {
    "shot":      ("end", 1.0, .7, "Kick", "Kick", "Possessed"),
    "pass":      ("end", .9, .6, "Pass", "Pass", "Possessed"),
    "pass_high": ("end", .9, .6, "Pass", "Pass", "Possessed"),
    "clearance": ("end", .9, .6, "Kick", "Kick", "Possessed"),
    "receive":   ("start", .6, .8, "FirstTouch", "FirstTouch", "Approaching"),
    "win_ball":  ("start", .8, .6, "Tackle", "Tackle", "None"),
    "carry":     ("start", 0., 3.5, "Dribble", "Locomotion", "Possessed"),
}
QUOTA = dict(shot=10, pass_=10, pass_high=6, clearance=4, receive=10, win_ball=8, carry=8)
QUOTA = {k.rstrip("_"): v for k, v in QUOTA.items()}
STRIKES = ("shot", "pass", "pass_high", "clearance")


# ------------------------------------------------------------------ moments
def moments_for(ev_csv):
    rows = list(csv.DictReader(open(ev_csv)))
    out = []

    def add(kind, r, tf, extra=None):
        _, before, after, *_ = KINDS[kind]
        if kind == "carry":
            after = min(float(r["duration"] or 0), after)
        pk = int(round(int(tf) * 2.5))
        out.append(dict(kind=kind, pid=int(r["player_id"]), player=r["player_name"], lo=pk - int(before * FPS_P),
                        hi=pk + int(after * FPS_P), key=pk, event=r["event_id"], extra=extra or {}))
    for r in rows:
        if r["event_type"] != "player_possession" or not r["player_id"]:
            continue
        end, dur = r["end_type"], float(r["duration"] or 0)
        if end == "shot":
            add("shot", r, r["frame_end"])
        elif end == "pass":
            add("pass_high" if r["high_pass"] == "True" else "pass", r, r["frame_end"],
                dict(distance=r["pass_distance"], outcome=r["pass_outcome"]))
        elif end == "clearance":
            add("clearance", r, r["frame_end"])
        if r["start_type"] == "pass_reception" and r["one_touch"] != "True" and dur > .6:
            add("receive", r, r["frame_start"])
        if r["start_type"] in ("pass_interception", "recovery"):
            add("win_ball", r, r["frame_start"])
        if r["carry"] == "True" and dur > 1.6:
            add("carry", r, r["frame_start"])
    for i, m in enumerate(out):
        m["id"] = i
    return out


def extract(match, zpath, moments, log=print):
    """stream the pose jsonl once; keep each moment's player frames."""
    need = collections.defaultdict(list)
    for m in moments:
        for f in range(m["lo"], m["hi"] + 1):
            need[f].append(m["id"])
    pat = re.compile(rb'"frame":\s*(\d+)')
    data = {m["id"]: {} for m in moments}
    t0 = time.time()
    with zipfile.ZipFile(zpath) as z:
        name = [i for i in z.namelist() if i.endswith(".jsonl") and not i.startswith("__")][0]
        with z.open(name) as fh:
            for line in fh:
                mm = pat.search(line, 0, 40)
                if not mm or int(mm.group(1)) not in need:
                    continue
                fr = json.loads(line)
                ids = need[int(mm.group(1))]
                want = {moments[i]["pid"] for i in ids}
                ps = {p["player_id"]: p for p in fr["player_data"] if p["player_id"] in want}
                for i in ids:
                    p = ps.get(moments[i]["pid"])
                    if p and p.get("joints"):
                        data[i][int(mm.group(1))] = dict(
                            x=p["x"], y=p["y"], det=bool(p["is_detected"]),
                            j={k: (v["xyz"], v["p90_mae_cm"]) for k, v in p["joints"].items()})
    log("  %s: %d moments extracted in %.0fs" % (match, len(moments), time.time() - t0))
    return data


# ------------------------------------------------------------------ selection
def quality(m, fr):
    n = m["hi"] - m["lo"] + 1
    if len(fr) < n or not all(fr[f]["det"] for f in fr):
        return None
    mae = float(np.mean([np.mean([v[1] for v in f["j"].values()]) for f in fr.values()]))
    return mae


def strike(m, fr):
    """contact frame and kicking foot: the ankle whose speed peaks around the event."""
    best = (-1.0, m["key"], "R")
    for f in range(m["key"] - 8, m["key"] + 5):
        if f - 1 not in fr or f not in fr:
            continue
        for side, j in (("L", "lAnkle"), ("R", "rAnkle")):
            a, b = np.array(fr[f - 1]["j"][j][0]), np.array(fr[f]["j"][j][0])
            s = float(np.linalg.norm((b - a)[:2])) * FPS_P
            if s > best[0]:
                best = (s, f, side)
    return best


def root_velocity(m, fr, heading):
    """mean ground velocity over the take in the clip's facing frame (rig X left/right, Z forward)."""
    f0, f1 = m["lo"], m["hi"]
    dx = (fr[f1]["x"] - fr[f0]["x"]) / ((f1 - f0) / FPS_P)
    dy = (fr[f1]["y"] - fr[f0]["y"]) / ((f1 - f0) / FPS_P)
    v = np.array([dx, 0.0, -dy])                          # rig axes (jointtrack.to_rig_axes)
    c, s = math.cos(-heading), math.sin(-heading)
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    w = R @ v
    return float(w[0]), float(w[2])


def best_loop(keys, lo=14, hi=30):
    """a two-stride loop inside a carry: the window whose ends match best."""
    from sforge import mocap as MC
    X = np.array([[np.ravel(p.get(k, 0.0)).tolist()[c] if isinstance(p.get(k, 0.0), (list, tuple)) else float(p.get(k, 0.0))
                   for k, c in MC.PARAMS] for _, p in keys])
    best = (1e9, 0, 0)
    for L in range(lo, min(hi, len(X) - 2) + 1):
        for s in range(0, len(X) - L - 1):
            e = float(np.abs(X[s] - X[s + L]).mean() + .5 * np.abs((X[s + 1] - X[s]) - (X[s + L + 1] - X[s + L])).mean())
            if e < best[0]:
                best = (e, s, L)
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pose-dir", required=True)
    ap.add_argument("--events-dir", required=True, help="opendata/data/matches")
    ap.add_argument("--work", default="/tmp/sc_pose")
    ap.add_argument("--max-err", type=float, default=4.0, help="reject fits above this mean bone error (deg)")
    args = ap.parse_args()
    from sforge import jointtrack as JT
    os.makedirs(args.work, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    cands = []
    for match in MATCHES:
        zpath = os.path.join(args.pose_dir, match + ".jsonl.zip")
        if not os.path.isfile(zpath):
            print("  missing %s - skipped" % zpath)
            continue
        cache = os.path.join(args.work, match + ".pkl")
        moments = moments_for(os.path.join(args.events_dir, match, match + "_dynamic_events.csv"))
        if os.path.isfile(cache):
            data = pickle.load(open(cache, "rb"))
        else:
            data = extract(match, zpath, moments)
            pickle.dump(data, open(cache, "wb"))
        for m in moments:
            fr = data.get(m["id"], {})
            q = quality(m, fr)
            if q is not None:
                cands.append((q, match, m, fr))
    # cleanest first, at most two takes per player per kind
    cands.sort(key=lambda c: c[0])
    chosen = collections.defaultdict(list); per_player = collections.Counter()
    takes = []
    for q, match, m, fr in cands:
        kind = m["kind"]
        if len(chosen[kind]) >= QUOTA[kind] or per_player[(kind, m["pid"])] >= 2:
            continue
        frames = [{k: v[0] for k, v in fr[f]["j"].items()} for f in range(m["lo"], m["hi"] + 1)]
        contact, foot = -1.0, ""
        face = m["key"] - m["lo"]
        if kind in STRIKES:
            speed, cf, foot = strike(m, fr)
            if speed < 4.0:                          # no visible strike: tracking lost the leg
                continue
            face = cf - m["lo"]
            contact = (cf - m["lo"]) / max(1, m["hi"] - m["lo"])
        elif kind in ("receive", "win_ball"):
            contact = (m["key"] - m["lo"]) / max(1, m["hi"] - m["lo"])
        try:
            keys, rep = JT.fit_tracks(frames, fps=FPS_P, face_frame=face)
        except ValueError:
            continue
        if rep["mean_bone_err_deg"] > args.max_err:
            continue
        loop = False
        if kind == "carry":
            seam, s, L = best_loop(keys)
            if seam > 6.0:
                continue
            keys = [((i - s) / L, keys[i][1]) for i in range(s, s + L + 1)]
            rep["duration"] = round(L / FPS_P, 4); loop = True
            m = dict(m, lo=m["lo"] + s, hi=m["lo"] + s + L)
        hd = math.radians(rep["heading_deg"])
        vx, vz = root_velocity(m, fr, hd)
        n = len(chosen[kind]) + 1
        name = "sc_%s_%02d" % (kind, n)
        lib_cat = KINDS[kind][3]
        rec = JT.keys_record(name, keys, rep, LICENCE, category=lib_cat, loop=loop,
                             source="skillcorner:%s:event %s" % (match, m["event"]),
                             desc="%s by %s (SkillCorner match %s, real broadcast pose)" % (kind.replace("_", " "), m["player"], match))
        rec["import"]["contact"] = round(contact, 4)
        rec["import"]["foot"] = foot
        rec["import"]["root_velocity"] = [round(vx, 3), round(vz, 3)]
        rec["import"]["joint_p90_mae_cm"] = round(q, 1)
        with open(os.path.join(OUT, name + ".json"), "w") as f:
            json.dump(rec, f, indent=0)
        chosen[kind].append(name); per_player[(kind, m["pid"])] += 1
        takes.append(dict(name=name, take="%s:%s" % (match, m["event"]), loop=loop, category=lib_cat,
                          game_category=KINDS[kind][4], ball_state=KINDS[kind][5], duration=rep["duration"],
                          keys=len(keys), contact=round(contact, 4), foot=foot, root_velocity=[round(vx, 3), round(vz, 3)],
                          fit_err_deg=rep["mean_bone_err_deg"], joint_mae_cm=round(q, 1), player=m["player"]))
        print("  %-16s %-26s %4.2fs  fit %.1f deg  joints %.1f cm  v=(%.1f, %.1f)%s" % (
            name, m["player"][:26], rep["duration"], rep["mean_bone_err_deg"], q, vx, vz, ("  foot " + foot) if foot else ""))
    with open(os.path.join(OUT, "_import.json"), "w") as f:
        json.dump(dict(source="SkillCorner Open Data - Body Pose", licence=LICENCE, takes=takes), f, indent=1)
    update_manifest(takes)
    print("wrote %d moves to %s (%s)" % (len(takes), os.path.relpath(OUT, ARENA),
                                         ", ".join("%s %d" % (k, len(v)) for k, v in chosen.items())))
    return 0


def update_manifest(takes):
    """clip-manifest rows for the takes (the motion-matching table reads these)."""
    with open(MANIFEST) as f:
        man = json.load(f)
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("soccer_sc_")]
    for t in takes:
        vx, vz = t["root_velocity"]
        speed = math.hypot(vx, vz)
        tags = ["mocap", "skillcorner", "real_match"]
        if t["ball_state"] == "Possessed":
            tags.append("ball_possessed")
        if t["contact"] >= 0:
            tags.append("ball_contact")
        man["clips"].append(dict(
            id="soccer_" + t["name"], poseDataKey="soccer_" + t["name"], category=t["game_category"],
            duration=round(t["duration"], 6), contactFraction=t["contact"] if t["contact"] >= 0 else -1.0,
            footPlantFrames=[], rootVelocityX=round(vx, 3), rootVelocityZ=round(vz, 3),
            preferredSpeed=round(speed, 3) if t["loop"] else 0.0, preferredTurnRate=0.0,
            ballState=t["ball_state"], tags=tags, boneCount=18, loop=bool(t["loop"]), footPlantSides=[]))
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
