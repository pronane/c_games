#!/usr/bin/env python3
"""Import our own match recordings (Veo) as real in-match motion.

Sprite Forge's match capture (sforge.matchcapture, v11.26) turns the team's own Veo
recordings into anonymous library moves: person boxes -> tracks -> 2D pose -> Sprite
Forge's 2D->3D lifter -> the mocap IK.  Only joint angles come out - no video, faces,
names, shirt numbers or per-player tracks.  The batch runs on a GPU pod and hands back
one merged folder (moves.tgz).

This keeps the best of them for the game:

  * every move must pass Sprite Forge's motion checks (tools/check_motion.py: size,
    floor, pops, loop seam, facing, turning) - warnings are allowed, failures are not
  * kicks: a visible strike (foot speed), clean fit, legs visible; at most two per clip
  * the move must be big enough to read: a kick's thigh swings 55+ deg and its knee
    opens 50+; a run loop's thighs both swing 45+ (most far-side "runs" are shuffles)
  * steady: shaky tracking (high joint-angle jitter) is dropped
  * run loops: a clean seam, legs visible; at most one per clip
  * arms low-passed (3 passes), body lightly (1 pass) - far-camera arms are noisy
  * ranked by fit error and leg visibility; quotas --strikes / --runs

and writes them to Data/mocap/veo/ (vo_strike_NN, vo_run_NN) with the footage licence,
plus clip-manifest rows.  Tools/soccer_motions.py bakes them into the player GLB.

    python3 Tools/import_matchcapture.py MERGED_DIR [MERGED_DIR ...] [--strikes 24] [--runs 12]
    python3 Tools/import_matchcapture.py --source soccertrack MOVES_DIR [--quota kick=40,header=10]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)
sys.path.insert(0, os.path.join(SF, "tools"))

OUT = os.path.join(ARENA, "Data", "mocap", "veo")
MANIFEST = os.path.join(ARENA, "Data", "clips", "clip_manifest.json")
PREFIX, TAG = "vo_", "veo"       # set per --source in main()

LICENCE = dict(
    spdx="LicenseRef-owner-footage",
    custom_text="Motion taken from the Arena FC team's own Veo match recordings; the team owns the footage "
                "and allows its use in Arena FC and Sprite Forge.",
    author="Arena FC (own match recordings)",
    source_url="",
    redistribution="yes", ml_training="yes",  # v11.40: our own footage
    attribution="Real match motion from our own recordings.",
    notes="",
)
# Where each source's moves go and how they are named.  Labelled sources (SoccerTrack v2:
# every pass / shot / header / tackle tagged with its player and moment) keep their own kind
# and licence; unlabelled ones (our Veo footage) are classified from the 3D legs.
SOURCES = {
    "veo": dict(dir="veo", prefix="vo_", tag="veo", licence=LICENCE, footage="our own match video",
                source="veo:own-footage", title="Arena FC own match recordings (Veo) via sforge.matchcapture"),
    "soccertrack": dict(dir="soccertrack", prefix="st_", tag="soccertrack", licence=None, footage="SoccerTrack v2 match video",
                        source="soccertrack-v2", title="SoccerTrack v2 (CC BY 4.0) via sforge.matchcapture events"),
}
# labelled kind / sub-kind -> (game category, ball state)
GAME_CATEGORY = {"pass": ("Pass", "Possessed"), "lofted": ("Pass", "Possessed"), "cross": ("Pass", "Possessed"),
                 "shot": ("Kick", "Possessed"), "free_kick": ("Kick", "Possessed"), "header": ("FirstTouch", "Approaching"),
                 "tackle": ("Tackle", "None"), "block": ("Tackle", "None"), "carry": ("Locomotion", "Possessed"),
                 "strike": ("Kick", "Possessed"), "run": ("Locomotion", "None")}
LABELLED_QUOTA = dict(kick=40, header=10, tackle=10, block=6, carry=12)
SUB_QUOTA = {"pass": 45, "lofted": 20, "cross": 10, "free_kick": 10, "shot": 4}
LABELLED_CAP = dict(kick=6, header=2, tackle=2, block=2, carry=2)          # per match half
LEG = 0.9          # hip to ankle on the rig, metres
FLIGHT = 1.25      # running strides are longer than the leg sweep (both feet off the ground)


def stride_speed(keys, dur):
    """ground speed of a run loop from its leg sweep: each step covers about
    leg * (sin(forward swing) + sin(back swing)), two steps per loop."""
    steps = []
    for side in ("L", "R"):
        pitch = [float(k[1]["leg_" + side][0]) for k in keys if isinstance(k[1].get("leg_" + side), (list, tuple))]
        if pitch:
            fwd, back = max(pitch), min(pitch)
            steps.append(LEG * (math.sin(math.radians(max(0.0, fwd))) + math.sin(math.radians(max(0.0, -back)))))
    if not steps or dur <= 0:
        return 0.0
    return round(FLIGHT * sum(steps) / dur, 3)


def _series(keys, k, c=None):
    import numpy as np
    out = []
    for _, p in keys:
        v = p.get(k, 0.0)
        out.append(float(v[c] if c is not None and isinstance(v, (list, tuple)) else v))
    return np.array(out)


def shape(rec):
    """(swing, knee, jitter): the working leg's thigh range and knee range in degrees, and the mean
    frame-to-frame change of speed of the main joint angles (deg/frame^2) - shaky tracking is high."""
    import numpy as np
    K = rec["keys"]
    if rec.get("loop"):
        swing = min(np.ptp(_series(K, "leg_L", 0)), np.ptp(_series(K, "leg_R", 0)))
        knee = min(np.ptp(_series(K, "knee_L")), np.ptp(_series(K, "knee_R")))
    else:
        foot = (rec.get("import") or {}).get("foot") or "R"
        swing, knee = np.ptp(_series(K, "leg_" + foot, 0)), np.ptp(_series(K, "knee_" + foot))
    jit = [np.abs(np.diff(_series(K, k), 2)).mean() for k in ("knee_L", "knee_R", "elbow_L", "elbow_R")]
    jit += [np.abs(np.diff(_series(K, k, 0), 2)).mean() for k in ("leg_L", "leg_R", "hips", "chest")]
    return float(swing), float(knee), float(np.mean(jit))


def classify(rec, fps):
    """what the take really is, from the 3D legs: 'kick' when one thigh makes a single big forward
    swing well past the other's, 'run' when both thighs swing big and alternate (a stride the 2D
    detector called a kick is a run), else None.  Returns (kind, rec) - a run becomes a loop."""
    import numpy as np
    from sforge.matchcapture import best_loop_keys
    K = rec["keys"]
    L, R = _series(K, "leg_L", 0), _series(K, "leg_R", 0)
    foot = (rec.get("import") or {}).get("foot") or ("L" if L.max() > R.max() else "R")
    w, o = (L, R) if foot == "L" else (R, L)
    peaks = [i for i in range(1, len(w) - 1) if w[i] >= w[i - 1] and w[i] > w[i + 1] and w[i] > 35.0]
    if not rec.get("loop") and w.max() >= 55.0 and w.max() - o.max() >= 25.0 and len(peaks) <= 1:
        return "kick", rec
    if min(np.ptp(L), np.ptp(R)) < 30.0:
        return None, rec
    if rec.get("loop"):
        return "run", rec
    lk = best_loop_keys(K, int(.45 * fps), int(1.0 * fps), max_seam=7.0)
    if lk is None:
        return None, rec
    k2, n = lk
    out = dict(rec, keys=k2, loop=True, duration=round(n / fps, 4))
    out["import"] = dict(rec["import"], contact=-1.0, foot="", from_strike=True)
    return "run", out


ARM_CHANNELS = ("arm_L", "arm_R", "elbow_L", "elbow_R")
BODY_CHANNELS = ("hips", "chest", "spine", "neck", "leg_L", "leg_R", "knee_L", "knee_R", "ankle_L", "ankle_R")


def smooth(rec, arm_passes=3, body_passes=1):
    """low-pass the joint angles ([1 2 1]/4 per pass, wrapping round a loop): the arms are the
    noisiest part of far-camera pose, the legs need only a touch."""
    import numpy as np
    K = rec["keys"]
    if len(K) < 4:
        return rec
    loop = bool(rec.get("loop"))
    for chans, passes in ((ARM_CHANNELS, arm_passes), (BODY_CHANNELS, body_passes)):
        for ch in chans:
            if ch not in K[0][1]:
                continue
            A = np.array([np.ravel(k[1][ch]) for k in K], float)
            for _ in range(passes):
                if loop:                                   # the last key repeats the first
                    B = A[:-1]
                    B = (np.roll(B, 1, 0) + 2 * B + np.roll(B, -1, 0)) / 4.0
                    A = np.vstack([B, B[:1]])
                else:
                    A[1:-1] = (A[:-2] + 2 * A[1:-1] + A[2:]) / 4.0
            for k, v in zip(K, A):
                k[1][ch] = [float(x) for x in v] if isinstance(k[1][ch], (list, tuple)) else float(v[0])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("merged", nargs="+", help="folders from sforge.matchcapture --merge (unpacked moves.tgz); "
                    "several passes (e.g. 15 and 25 fps) compete for the same quotas")
    ap.add_argument("--strikes", type=int, default=24)
    ap.add_argument("--runs", type=int, default=12)
    ap.add_argument("--max-err", type=float, default=4.0, help="reject fits above this mean bone error (deg)")
    ap.add_argument("--min-vis", type=float, default=0.55, help="reject takes whose legs were seen less than this")
    ap.add_argument("--kick-swing", type=float, default=55.0, help="kicking thigh must swing at least this (deg)")
    ap.add_argument("--kick-knee", type=float, default=50.0, help="kicking knee must bend and open at least this (deg)")
    ap.add_argument("--run-swing", type=float, default=45.0, help="both thighs of a run loop must swing this (deg)")
    ap.add_argument("--max-jitter", type=float, default=4.5, help="reject shakier tracking (deg/frame^2)")
    ap.add_argument("--stage", default="", help="only copy the takes that pass the checks (raw, with an index) to this "
                    "folder - run on the GPU box to bring back a small folder instead of every take")
    ap.add_argument("--source", default="veo", choices=sorted(SOURCES))
    ap.add_argument("--quota", default="", help="labelled sources: kind=n,... (default %s)" %
                    ",".join("%s=%d" % kv for kv in LABELLED_QUOTA.items()))
    ap.add_argument("--label-kick-swing", type=float, default=40.0,
                    help="a labelled kick's thigh must still swing this much (deg) - else the pose missed it")
    args = ap.parse_args()
    import check_motion as CM
    global OUT, PREFIX, TAG
    src_cfg = SOURCES[args.source]
    OUT = os.path.join(ARENA, "Data", "mocap", src_cfg["dir"])
    PREFIX, TAG = src_cfg["prefix"], src_cfg["tag"]
    lquota = dict(LABELLED_QUOTA)
    for kv in filter(None, args.quota.split(",")):
        k, v = kv.split("="); lquota[k] = int(v)

    all_takes = []
    reasons = collections.Counter()
    raw = 0
    for d in args.merged:
        with open(os.path.join(d, "_import.json")) as f:
            idx = json.load(f)
        all_takes += [dict(t, _dir=d) for t in idx["takes"]]
        reasons.update(idx.get("rejected", {}))        # a staged folder carries the GPU box's rejections
        raw += len(idx["takes"]) + sum(idx.get("rejected", {}).values())
    index = dict(takes=all_takes)
    cands = []
    for t in index["takes"]:
        path = os.path.join(t["_dir"], t["name"] + ".json")
        if not os.path.isfile(path):
            reasons["missing"] += 1; continue
        with open(path) as f:
            rec = json.load(f)
        imp = rec.get("import") or {}
        err, vis = float(imp.get("mean_bone_err_deg", 99)), float(imp.get("leg_visibility", 0))
        if err > args.max_err:
            reasons["fit error"] += 1; continue
        if vis < args.min_vis:
            reasons["legs hidden"] += 1; continue
        labelled = bool(imp.get("sub"))
        if labelled:                                   # the footage says what it is
            if t["kind"] not in lquota:
                reasons["kind not imported: " + t["kind"]] += 1; continue
            swing, knee, jit = shape(rec)
            if jit > args.max_jitter:
                reasons["shaky"] += 1; continue
            if t["kind"] == "kick" and swing < args.label_kick_swing:
                reasons["kick swing not seen"] += 1; continue
            if t["kind"] == "carry" and swing < args.run_swing:
                reasons["not running"] += 1; continue
        else:
            kind, rec = classify(rec, float(imp.get("fps", 15.0)))
            if kind is None:
                reasons["neither kick nor run"] += 1; continue
            t = dict(t, kind="strike" if kind == "kick" else "run")
            swing, knee, jit = shape(rec)
            if jit > args.max_jitter:
                reasons["shaky"] += 1; continue
            if t["kind"] == "strike" and (swing < args.kick_swing or knee < args.kick_knee):
                reasons["small swing"] += 1; continue
            if t["kind"] == "run" and swing < args.run_swing:
                reasons["not running"] += 1; continue
        bad = [c for c, ok, _ in CM.check_clip(rec, t["name"]) if ok is False]
        if bad:
            reasons["checks: " + ",".join(bad)] += 1; continue
        score = err / 4.0 + (1.0 - vis) * 2.0 + jit / 4.0 - min(swing, 100.0) / 100.0
        if t["kind"] in ("strike", "kick"):
            sp = float(imp.get("peak_speed") or 0)
            score -= min(sp, 14.0) / 28.0                 # a harder strike shows the swing better
        cands.append((score, t, rec))
    cands.sort(key=lambda c: c[0])
    if args.stage:
        os.makedirs(args.stage, exist_ok=True)
        keep = []
        for score, t, rec in cands:
            src = os.path.join(t["_dir"], t["name"] + ".json")
            with open(src) as f, open(os.path.join(args.stage, t["name"] + ".json"), "w") as g:
                g.write(f.read())
            keep.append({k: v for k, v in t.items() if k != "_dir"})
        with open(os.path.join(args.stage, "_import.json"), "w") as f:
            json.dump(dict(source="staged by import_matchcapture", rejected=dict(reasons), takes=keep), f, indent=1)
        print("staged %d of %d; rejected: %s" % (len(keep), len(index["takes"]), dict(reasons)))
        return 0

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):                      # replace the moves, keep the README
        if f.endswith(".json"):
            os.remove(os.path.join(OUT, f))
    quota = dict(strike=args.strikes, run=args.runs, **lquota)
    per_clip_cap = dict(strike=2, run=1, **LABELLED_CAP)
    count = collections.Counter(); per_clip = collections.Counter()
    takes = []
    for score, t, rec in cands:
        kind = t["kind"]
        if count[kind] >= quota.get(kind, 0):
            continue
        sub0 = (rec.get("import") or {}).get("sub")
        if sub0 and sub0 in SUB_QUOTA and count["name:" + sub0] >= SUB_QUOTA[sub0]:
            continue                                   # keep the kick mix varied, not all short passes
        clip = str(t.get("clip", "")) + "@" + str(round(float(rec["import"].get("fps", 0))))   # per pass
        if per_clip[(kind, clip)] >= per_clip_cap[kind]:
            continue
        count[kind] += 1; per_clip[(kind, clip)] += 1
        imp = rec["import"]
        sub = imp.get("sub") or kind
        count["name:" + sub] += 1
        name = "%s%s_%02d" % (PREFIX, sub, count["name:" + sub])
        dur = float(rec.get("duration") or 1.0)
        loop = bool(rec.get("loop"))
        vz = stride_speed(rec["keys"], dur) if loop else 0.0
        lic = dict(src_cfg["licence"], notes=(rec.get("licence") or {}).get("notes", "")) if src_cfg["licence"] else rec.get("licence")
        gcat, ball = GAME_CATEGORY.get(sub, GAME_CATEGORY.get(kind, ("Kick", "Possessed")))
        cat = rec.get("category") if labelled else ("Kick" if kind == "strike" else "Locomotion")
        rec = smooth(rec)
        what = {"strike": "kick", "run": "run loop", "carry": "dribble loop"}.get(sub, sub.replace("_", " "))
        out = dict(rec, name=name, category=cat, licence=lic, source=src_cfg["source"],
                   desc="%s from %s (anonymous)" % (what, src_cfg["footage"]))
        out["import"] = dict(imp, root_velocity=[0.0, vz])
        with open(os.path.join(OUT, name + ".json"), "w") as f:
            json.dump(out, f, indent=0)
        takes.append(dict(name=name, take="match video %s" % sub, loop=loop, category=cat,
                          game_category=gcat, ball_state=ball,
                          duration=round(dur, 4), keys=len(rec["keys"]), contact=float(imp.get("contact", -1.0)),
                          foot=imp.get("foot", ""), root_velocity=[0.0, vz], fit_err_deg=float(imp["mean_bone_err_deg"]),
                          leg_visibility=float(imp["leg_visibility"])))
        print("  %-12s %4.2fs  fit %.1f deg  legs %.2f%s" % (name, dur, imp["mean_bone_err_deg"], imp["leg_visibility"],
              ("  foot %s" % imp.get("foot")) if imp.get("foot") else "  %.1f m/s" % vz))
    with open(os.path.join(OUT, "_import.json"), "w") as f:
        json.dump(dict(source=src_cfg["title"], licence=src_cfg["licence"] or (takes and out.get("licence")),
                       candidates=raw, rejected=dict(reasons), takes=takes), f, indent=1)
    update_manifest(takes)
    print("kept %d of %d (%s); rejected: %s" % (len(takes), raw,
          ", ".join("%s %d" % kv for kv in count.items() if not kv[0].startswith("name:")), dict(reasons)))
    return 0


def update_manifest(takes):
    with open(MANIFEST) as f:
        man = json.load(f)
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("soccer_" + PREFIX)]
    for t in takes:
        vx, vz = t["root_velocity"]
        tags = ["mocap", TAG, "real_match"]
        if t["ball_state"] == "Possessed":
            tags.append("ball_possessed")
        if t["contact"] >= 0:
            tags.append("ball_contact")
        man["clips"].append(dict(
            id="soccer_" + t["name"], poseDataKey="soccer_" + t["name"], category=t["game_category"],
            duration=round(t["duration"], 6), contactFraction=t["contact"] if t["contact"] >= 0 else -1.0,
            footPlantFrames=[], rootVelocityX=round(vx, 3), rootVelocityZ=round(vz, 3),
            preferredSpeed=round(math.hypot(vx, vz), 3) if t["loop"] else 0.0, preferredTurnRate=0.0,
            ballState=t["ball_state"], tags=tags, boneCount=18, loop=bool(t["loop"]), footPlantSides=[]))
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
