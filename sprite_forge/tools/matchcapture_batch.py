#!/usr/bin/env python3
"""Run sforge.matchcapture over many clips in parallel, then merge the moves.

    python tools/matchcapture_batch.py FOOTAGE_DIR OUT_DIR [--workers 6] [--models DIR]

FOOTAGE_DIR: *.zip (Veo highlight downloads) and/or *.mp4.  Zips are unpacked to a
scratch folder; each clip is deleted once processed (--purge).  OUT_DIR/moves is the
merged library folder, OUT_DIR/moves.tgz the same packed, OUT_DIR/log.txt the log.
"""
import argparse, glob, os, subprocess, sys, tarfile, time, zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("footage"); ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--models", default=None)
    ap.add_argument("--scratch", default="/tmp/mc_scratch")
    ap.add_argument("--extra", default="", help="extra matchcapture arguments")
    a = ap.parse_args()
    models = a.models or os.path.join(a.out, "models")
    os.makedirs(os.path.join(a.out, "clips"), exist_ok=True); os.makedirs(a.scratch, exist_ok=True)
    clips = []
    for z in sorted(glob.glob(os.path.join(a.footage, "*.zip"))):
        d = os.path.join(a.scratch, os.path.splitext(os.path.basename(z))[0])
        zipfile.ZipFile(z).extractall(d)
        clips += sorted(glob.glob(os.path.join(d, "**", "*.mp4"), recursive=True))
    clips += sorted(glob.glob(os.path.join(a.footage, "*.mp4")))
    log = open(os.path.join(a.out, "log.txt"), "a")
    print("clips: %d" % len(clips), flush=True)
    t0 = time.time(); done = [0]

    def run(item):
        i, v = item
        m = os.path.basename(os.path.dirname(v))
        cmd = [sys.executable, "-m", "sforge.matchcapture", v, "--out", os.path.join(a.out, "clips", "%s-%03d" % (m, i)),
               "--models", models, "--prefix", "c%03d" % i, "--purge"] + a.extra.split()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        log.write(r.stdout + r.stderr[-2000:] + "\n"); log.flush()
        done[0] += 1
        print("%d/%d %s %s (%.0fs)" % (done[0], len(clips), "ok" if r.returncode == 0 else "FAILED", os.path.basename(v), time.time() - t0), flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, enumerate(clips, 1)))
    sys.path.insert(0, ROOT)
    from sforge import matchcapture as M
    cd = os.path.join(a.out, "clips")
    idx = M.merge([os.path.join(cd, d) for d in os.listdir(cd)], os.path.join(a.out, "moves"))
    with tarfile.open(os.path.join(a.out, "moves.tgz"), "w:gz") as t:
        t.add(os.path.join(a.out, "moves"), arcname="moves")
    kinds = {}
    for t in idx["takes"]: kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    print("done: %d moves %s in %.0fs -> %s" % (len(idx["takes"]), kinds, time.time() - t0, os.path.join(a.out, "moves.tgz")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
