#!/usr/bin/env python3
"""Tag motion-library moves and file catch-alls into real categories (v11.40).

    python3 tools/retag_motions.py motion_library                 # report only
    python3 tools/retag_motions.py motion_library --write         # re-file catch-alls + add tags in place
    python3 tools/retag_motions.py ../arena-fc/Data/mocap/* --keep-category --write \
        --ml-training cmu=yes                                     # a game's moves: tags + ml_training only

--keep-category leaves each record's category alone (a game's own clip vocabulary, e.g. Arena FC's
"Kick" / "FirstTouch") and only adds `tags` and, where the licence record lacks it, `ml_training`
(read from the licence by sforge.motiontags.training_allowed, or set per folder with --ml-training).
The report lists moves per category and source and how many may be used to train models.
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sforge import motiontags as MT  # noqa: E402


def records(paths):
    for d in paths:
        files = sorted(glob.glob(os.path.join(d, "*.json"))) if os.path.isdir(d) else [d]
        for f in files:
            if os.path.basename(f).startswith("_"):
                continue
            try:
                r = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(r, dict) and "keys" in r and "name" in r:
                yield f, r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="motion folders or move .json files")
    ap.add_argument("--write", action="store_true", help="write the changes back (default: report only)")
    ap.add_argument("--keep-category", action="store_true", help="only add tags / ml_training; never re-file")
    ap.add_argument("--ml-training", action="append", default=[], metavar="FOLDER=yes|no|unknown",
                    help="set licence.ml_training for every move in a folder (by folder name)")
    ap.add_argument("--json", help="write the report as JSON here")
    a = ap.parse_args(argv)
    forced = {}
    for s in a.ml_training:
        k, _, v = s.partition("=")
        if v not in MT.TRAINING:
            ap.error("--ml-training %s: value must be yes / no / unknown" % s)
        forced[k] = v
    cats, train, refiled, untold, changed = collections.Counter(), collections.Counter(), [], [], 0
    for f, r in records(a.paths):
        before = json.dumps(r, sort_keys=True)
        cat0 = r.get("category")
        MT.retag(r, refile=False if a.keep_category else True)
        lic = r.setdefault("licence", {})
        folder = os.path.basename(os.path.dirname(os.path.abspath(f)))
        if folder in forced:
            lic["ml_training"] = forced[folder]
        elif "ml_training" not in lic:
            lic["ml_training"] = MT.training_allowed(lic)
        if r.get("category") != cat0:
            refiled.append((r["name"], cat0, r["category"]))
        if r["tags"].get("needs_category"):
            untold.append((r["name"], cat0))
        src = r["tags"].get("source", folder)
        cats[(r.get("category"), src)] += 1
        train[(src, lic["ml_training"])] += 1
        if json.dumps(r, sort_keys=True) != before:
            changed += 1
            if a.write:
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(r, fh, indent=1, ensure_ascii=False)
                    fh.write("\n")
    print("%d moves %s%s" % (sum(cats.values()), "updated" if a.write else "would change", ": %d" % changed))
    for (c, s), n in sorted(cats.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print("  %-14s %-12s %4d" % (c, s, n))
    print("training rights (source, ml_training):")
    for (s, v), n in sorted(train.items()):
        print("  %-12s %-8s %4d" % (s, v, n))
    for n, c0, c1 in refiled:
        print("  re-filed %-28s %s -> %s" % (n, c0, c1))
    for n, c0 in untold:
        print("  NEEDS A CATEGORY %-20s (still %s)" % (n, c0))
    if a.json:
        json.dump(dict(categories=[[c, s, n] for (c, s), n in cats.items()],
                       training=[[s, v, n] for (s, v), n in train.items()],
                       refiled=refiled, needs_category=untold), open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
