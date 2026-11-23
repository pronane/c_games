#!/usr/bin/env python3
"""Frame-level A/B for the visual-ab legs: per-frame stats + original-vs-LOD delta.

Answers the two questions a reviewer would otherwise need a download for:
  1. Are the captured frames real (not black/uniform SwiftShader output)?
  2. How much do the legs actually differ, pixel-wise? (LOD should look *similar*,
     not identical — small delta + fewer triangles is the ideal outcome.)

Usage:  python3 tools/frame_ab.py <original/dir> <lod/dir> > frame-ab.md
Writes frame-ab.json next to the report. Exit 1 if either leg produced dead frames.
Requires numpy + pillow (installed in the CI job for the GLB bake).
"""
from __future__ import annotations
import json
import os
import sys

import numpy as np
from PIL import Image, ImageStat

DEAD_STDDEV = 2.0          # luminance stddev below this => near-uniform frame
CHANGE_THRESHOLD = 10      # per-channel abs delta that counts a pixel as "changed"


def load_small(path: str, box):
    im = Image.open(path).convert("RGB")
    return im.resize(box)


def leg_stats(d: str):
    rows = []
    for f in sorted(os.listdir(d)):
        if not (f.startswith("frame-") and f.endswith(".png")):
            continue
        im = Image.open(os.path.join(d, f)).convert("L").resize((384, 216))
        st = ImageStat.Stat(im)
        rows.append({"frame": f, "mean": round(st.mean[0], 2), "stddev": round(st.stddev[0], 2)})
    return rows


def main() -> int:
    orig_dir, lod_dir = sys.argv[1], sys.argv[2]
    o, l = leg_stats(orig_dir), leg_stats(lod_dir)
    l_by_frame = {r["frame"]: r for r in l}

    dead = [r["frame"] for r in o if r["stddev"] < DEAD_STDDEV] + [
        r["frame"] for r in l if r["stddev"] < DEAD_STDDEV
    ]

    pairs = [r for r in o if r["frame"] in l_by_frame]
    deltas = []
    for r in pairs:
        a = load_small(os.path.join(orig_dir, r["frame"]), (192, 108))
        b = load_small(os.path.join(lod_dir, r["frame"]), (192, 108))
        d = np.abs(np.asarray(a, np.float32) - np.asarray(b, np.float32)).mean(axis=2)
        deltas.append({
            "frame": r["frame"],
            "mean_abs_delta": round(float(d.mean()), 3),
            "changed_pct": round(float((d > CHANGE_THRESHOLD).mean()) * 100, 2),
        })

    mean_delta = round(float(np.mean([d["mean_abs_delta"] for d in deltas])), 3) if deltas else None
    mean_changed = round(float(np.mean([d["changed_pct"] for d in deltas])), 2) if deltas else None

    report = {
        "original": {"frames": len(o), "dead": sum(1 for r in o if r["stddev"] < DEAD_STDDEV),
                      "mean_stddev": round(float(np.mean([r["stddev"] for r in o])), 2) if o else None},
        "lod": {"frames": len(l), "dead": sum(1 for r in l if r["stddev"] < DEAD_STDDEV),
                 "mean_stddev": round(float(np.mean([r["stddev"] for r in l])), 2) if l else None},
        "paired_frames": len(deltas),
        "mean_abs_delta": mean_delta,
        "changed_pct": mean_changed,
        "dead_frames": dead,
    }
    out_json = os.path.join(os.path.dirname(lod_dir.rstrip("/")) or ".", "frame-ab.json")
    with open(out_json, "w") as fh:
        json.dump(report, fh, indent=1)

    print("# Frame A/B — original vs LOD")
    print()
    print("| metric | original | LOD |")
    print("|---|---|---|")
    print("| frames captured | %d | %d |" % (len(o), len(l)))
    print("| mean luminance stddev | %s | %s |" % (report["original"]["mean_stddev"], report["lod"]["mean_stddev"]))
    print("| dead (near-uniform) frames | %d | %d |" % (report["original"]["dead"], report["lod"]["dead"]))
    print()
    print("**Paired comparison over %d aligned frames**" % len(deltas))
    print()
    print("| mean abs channel delta (0-255) | %s |" % mean_delta)
    print("|---|---|")
    print("| pixels changed > %d /255 | %s%% |" % (CHANGE_THRESHOLD, mean_changed))
    print()
    if dead:
        print("⚠️ %d near-uniform frame(s): %s — SwiftShader output may be broken" % (len(dead), ", ".join(dead)))
    else:
        print("✅ no dead frames — captures contain real scene content")
    print()
    print("JSON report → `frame-ab.json`")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
