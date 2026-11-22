#!/usr/bin/env python3
"""SoccerTrack v2 -> Sprite Forge moves (v11.29), using the dataset's own labels.

SoccerTrack v2 (Scott et al., CC BY 4.0, huggingface.co/datasets/atomscott/soccertrack-v2)
has 10 full university matches as 4K panoramas at 25 fps, with every ball event labelled
(pass, high pass, cross, shot, free kick, header, tackle, block, throw-in, drive) - when, by
which team and player - and every player's box in every frame (GSR).  So each event is cut
at its own moment on its own player: no detector, no tracker, no kick guessing.

    python tools/soccertrack_capture.py ROOT OUT [--matches 117092 ...] [--models DIR]
           [--min-height 60] [--workers 4]

ROOT is the downloaded dataset (videos/, bas/, gsr/).  Each match writes OUT/<match>/ and
the batch merges them into OUT/moves (prefix "st").  Only joint angles are written.

Data quirks handled (see the dataset's src/data_utils/soccertrack_v2.py):
  * BAS events live under "actions" (docs say "annotations"); labels may be UPPER CASE
  * BAS (v1.3 files) carries each event's `frame` in its half's video; use it directly
  * GSR files are ~2.7 GB per half: streamed with ijson, keeping only the boxes needed
  * GSR image_id is offset (e.g. 3903000001 for frame 0): frame = image_id - first image_id
  * GSR bbox_image is a fixed-size box around a projected pitch position, not the body: it is
    used as a hint and the player found with the detector (matchcapture.refine_box); the
    MOT files have real boxes but only for each match's first 4 minutes
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_SF = os.path.dirname(HERE)
sys.path.insert(0, ROOT_SF)

HALF_MS = 45 * 60 * 1000
FPS = 25.0
LICENCE = dict(spdx="CC-BY-4.0", author="Atom Scott, Ikuma Uchida, Kento Kuroda, Yufi Kim, Keisuke Fujii (SoccerTrack v2)",
               url="https://huggingface.co/datasets/atomscott/soccertrack-v2", redistribution="yes",
               attribution="Motion derived from SoccerTrack v2 (Scott et al., CC BY 4.0); changed: 3D pose estimated "
                           "and fitted to a game skeleton.",
               text="")


def parse_bas(path):
    """-> [dict(half, frame, label, team, player)] for visible events of halves 1-2.

    The released files (v1.3) give each event's `frame` in its half's video, and `position` in ms
    from that video's first frame (the file's "clock" says so) - not from the start of the match
    as the dataset paper and older loader assume.  Older files without `frame`: position / 40."""
    d = json.load(open(path))
    rows = next((d[k] for k in ("actions", "annotations") if k in d), [])
    fps = float(d.get("fps", FPS))
    out = []
    for a in rows:
        if str(a.get("visibility", "visible")).lower().startswith("not"):
            continue
        gt = str(a.get("gameTime", ""))
        if " - " not in gt:
            continue                                   # a third period with no half prefix
        half = int(gt.split(" - ", 1)[0])
        if half not in (1, 2):
            continue
        frame = int(a["frame"]) if a.get("frame") is not None else int(round(int(a["position"]) * fps / 1000.0))
        out.append(dict(half=half, frame=frame, label=str(a["label"]).casefold(), team=a.get("team"), player=a.get("player_id")))
    return out


def player_key(player, team):
    """BAS player ids come as GSR's numeric player_id or as '<match>_<L|R>_<jersey>'."""
    if player is None:
        return None
    if isinstance(player, int) or str(player).isdigit():
        return ("pid", int(player))
    parts = str(player).split("_")
    if len(parts) >= 3 and parts[-2] in ("L", "R"):
        return ("jersey", "left" if parts[-2] == "L" else "right", str(int(parts[-1])) if parts[-1].isdigit() else parts[-1])
    return ("pid", str(player))


def gsr_keys(rec):
    at = rec.get("attributes") or {}
    keys = []
    if at.get("player_id") is not None:
        keys.append(("pid", int(at["player_id"]) if str(at["player_id"]).isdigit() else str(at["player_id"])))
    jersey = at.get("jersey", rec.get("jersey_number"))
    team = at.get("team", rec.get("team_side"))
    if jersey not in (None, "", "null") and team:
        keys.append(("jersey", team, str(int(jersey)) if str(jersey).isdigit() else str(jersey)))
    return keys


def boxes_for(gsr_path, wanted):
    """stream one half's GSR; wanted = {player key: set(frames)} -> {player key: {frame: (x0, y0, x1, y1)}}"""
    import ijson
    with open(gsr_path, "rb") as f:
        first = next(ijson.items(f, "images.item"))
    base = int(first["image_id"])
    out = collections.defaultdict(dict)
    with open(gsr_path, "rb") as f:
        for r in ijson.items(f, "annotations.item", use_float=True):
            if r.get("supercategory", "object") != "object" or "bbox_image" not in r:
                continue
            fr = int(r["image_id"]) - base
            for k in gsr_keys(r):
                if k in wanted and fr in wanted[k]:
                    b = r["bbox_image"]
                    out[k][fr] = (float(b["x"]), float(b["y"]), float(b["x"]) + float(b["w"]), float(b["y"]) + float(b["h"]))
    return out


def run_half(args):
    root, match, half, out, models, min_height = args
    from sforge import matchcapture as M
    suffix = "1st" if half == 1 else "2nd"
    video = os.path.join(root, "videos", match, "%s_panorama_%s_half.mp4" % (match, suffix))
    gsr = os.path.join(root, "gsr", match, "%s_%s.json" % (match, suffix))
    if not (os.path.isfile(video) and os.path.isfile(gsr)):
        return match, half, 0, "missing files"
    events = [e for e in parse_bas(os.path.join(root, "bas", match, "%s_12_class_events.json" % match)) if e["half"] == half]
    wanted = collections.defaultdict(set)
    for e in events:
        spec = M.EVENT_KINDS.get(e["label"])
        k = player_key(e["player"], e["team"])
        if spec is None or k is None:
            continue
        e["key"] = k
        lo, hi = e["frame"] - int(round(spec[2] * FPS)), e["frame"] + int(round(spec[3] * FPS))
        wanted[k].update(range(lo, hi + 1))
    t0 = time.time()
    boxes = boxes_for(gsr, wanted)
    evs = [dict(label=e["label"], frame=e["frame"], boxes=boxes.get(e["key"], {})) for e in events if "key" in e]
    # GSR boxes are pitch positions projected into the image (fixed 58 x 43, 25-50 px off the body):
    # use them as hints and find the real player with the detector around each one.
    takes, stats = M.process_events(video, evs, models, fps=FPS, min_height=min_height, hint_boxes=True,
                                    log=lambda s: print("  %s %s:%s" % (match, suffix, s), flush=True))
    lic = M.licence_record(["rtmpose_l_halpe26", "lifter_v1"], LICENCE)
    d = os.path.join(out, "%s_%s" % (match, suffix))
    M.write_takes(d, takes, "%s_%s" % (match, suffix), lic, prefix="st", footage="SoccerTrack v2 match video")
    return match, half, len(takes), "%d events, %d with boxes, %.0fs" % (len(events), stats["cut"], time.time() - t0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root"); ap.add_argument("out")
    ap.add_argument("--matches", nargs="*")
    ap.add_argument("--models", default=os.path.join(ROOT_SF, "sforge", "models"))
    ap.add_argument("--min-height", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    from sforge import matchcapture as M
    matches = a.matches or sorted(os.listdir(os.path.join(a.root, "bas")))
    jobs = [(a.root, m, h, a.out, a.models, a.min_height) for m in matches for h in (1, 2)]
    print("soccertrack: %d halves" % len(jobs), flush=True)
    with ProcessPoolExecutor(a.workers) as ex:
        for m, h, n, msg in ex.map(run_half, jobs):
            print("done %s half %d: %d moves (%s)" % (m, h, n, msg), flush=True)
    dirs = [os.path.join(a.out, d) for d in sorted(os.listdir(a.out)) if os.path.isfile(os.path.join(a.out, d, "_import.json"))]
    idx = M.merge(dirs, os.path.join(a.out, "moves"), prefix="st")
    kinds = collections.Counter(t["kind"] for t in idx["takes"])
    print("merged %d moves %s -> %s" % (len(idx["takes"]), dict(kinds), os.path.join(a.out, "moves")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
