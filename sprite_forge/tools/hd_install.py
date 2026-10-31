"""Validate HD Fighter sprite strips against meta.json and install them into the game.

    python3 tools/hd_install.py --src "/tmp/forge/{c}/strips/{s}.png"            # check only
    python3 tools/hd_install.py --src "/tmp/forge/{c}/strips/{s}.png" --install  # + copy into both sprite dirs

Checks per sheet: width = frames x 192 (frame count from meta.json), height 256, transparent background, nothing
touching the cell edges (clipped), and standing states with their lowest solid pixel on the 244 baseline."""
from __future__ import annotations
import argparse, json, os, shutil, sys
import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "HD_Fighter"))
DIRS = [os.path.join(ROOT, "assets_hd", "sprites"), os.path.join(ROOT, "multiplayer", "public", "assets_hd", "sprites")]
GROUNDED = ("idle", "walk", "crouch", "lp", "hp", "lk", "block", "throw", "special1", "hit", "win", "lose")


def check(path, n, state, fw=192, fh=256, base=244):
    errs = []
    im = Image.open(path)
    if im.mode != "RGBA":
        errs.append("mode %s" % im.mode)
        im = im.convert("RGBA")
    if im.size != (fw * n, fh):
        errs.append("size %s, want %dx%d" % (im.size, fw * n, fh))
        return errs
    a = np.asarray(im)[..., 3]
    for i in range(n):
        c = a[:, i * fw:(i + 1) * fw]
        if c.max() == 0:
            errs.append("frame %d empty" % i); continue
        if c[0].max() > 40 or c[-1].max() > 40 or c[:, 0].max() > 40 or c[:, -1].max() > 40:
            errs.append("frame %d touches the cell edge (clipped)" % i)
        rows = np.nonzero(c.max(1) > 40)[0]
        low = rows.max()
        if low > base:
            errs.append("frame %d below the baseline (%d > %d)" % (i, low, base))
        if state in GROUNDED and i == 0 and abs(low - base) > 3:
            errs.append("frame 0 feet at %d, want %d" % (low, base))
    if (a[0] > 0).any() and (a[:, 0] > 0).all():
        errs.append("background not transparent")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="pattern with {c} and {s}")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, "assets_hd", "meta.json")))
    bad = 0
    for c, states in meta["characters"].items():
        for s, (rel, n, fps) in states.items():
            src = a.src.format(c=c, s=s)
            if not os.path.exists(src):
                print("MISSING", src); bad += 1; continue
            e = check(src, n, s)
            if e:
                bad += 1
                print("%-7s %-9s %s" % (c, s, "; ".join(e)))
    print("%s: %d sheet(s) with problems" % ("FAIL" if bad else "OK", bad))
    if a.install and not bad:
        for c, states in meta["characters"].items():
            for s, (rel, n, fps) in states.items():
                for d in DIRS:
                    shutil.copyfile(a.src.format(c=c, s=s), os.path.join(d, os.path.basename(rel)))
        print("installed %d sheets into %s" % (sum(len(v) for v in meta["characters"].values()), ", ".join(DIRS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
