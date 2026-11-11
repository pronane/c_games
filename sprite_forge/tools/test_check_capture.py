#!/usr/bin/env python3
"""Does tools/check_capture.py catch a bad capture? (v11.10, no assets needed)

    python tools/test_check_capture.py

check_capture is the gate a new video's capture goes through. Here it is shown fake captures: one that is fine,
then one broken in each way the gate looks for - a missing export, a GLB with no skeleton, a fit gone wrong
(held-out IoU 0.55), a texture that saw too little, a registration that made the misfit worse, a frame worse after
moving, a move far beyond a correction, a face that got worse. The good one must pass, each broken one must fail
for its own reason (and only that), and a hard but honest video gives a warning, not a failure."""
from __future__ import annotations
import copy
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
import check_capture as CC                                                  # noqa: E402

R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-50s %s" % ("PASS" if ok else "FAIL", name, detail))


def glb(path, joints=26, clips=7):
    j = dict(asset=dict(version="2.0"), skins=[dict(joints=list(range(joints)))] if joints else [],
             animations=[dict(channels=[], samplers=[])] * clips)
    b = json.dumps(j).encode(); b += b" " * (-len(b) % 4)
    with open(path, "wb") as fh:
        fh.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(b)) + struct.pack("<II", len(b), 0x4E4F534A) + b)


GOOD = dict(check=dict(iou=0.84), texture=dict(seen=0.8),
            register=dict(frames=10, moved=6, flow_px_before=6.0, flow_px_after=4.0, refused={},
                          per_frame={str(i): dict(moved=i < 6, start_px=6.0, end_px=4.0 if i < 6 else 3.0,
                                                  d_rot_deg=1.0, d_t_frac=0.01) for i in range(10)}),
            face=dict(heldout_err_pct_before=2.5, heldout_err_pct_after=1.8))


def make(root, name, rep, files=True, glb_kw=None):
    out = os.path.join(root, name, "out"); os.makedirs(out)
    json.dump(rep, open(os.path.join(out, "report.json"), "w"))
    if files:
        for ext in ("fbx", "obj"):
            open(os.path.join(out, "%s.%s" % (name, ext)), "w").write("x")
        for f in ("%s_texture.png", "%s_turntable.jpg"):
            open(os.path.join(out, f % name), "w").write("x")
        glb(os.path.join(out, "%s.glb" % name), **(glb_kw or {}))
    return os.path.join(root, name)


def fails(res):
    return sorted(set(a for a, ok, _ in res if ok is False))


def main():
    root = tempfile.mkdtemp(prefix="sf_check_")
    try:
        r = CC.check(make(root, "good", GOOD))
        rec("a good capture passes", not fails(r), str(fails(r)))
        cases = []

        def bad(name, area, mutate=None, files=True, glb_kw=None):
            rep = copy.deepcopy(GOOD)
            if mutate:
                mutate(rep)
            cases.append((name, area, make(root, name, rep, files=files, glb_kw=glb_kw)))
        bad("noexport", "files", files=False)
        bad("noskel", "files", glb_kw=dict(joints=0))
        bad("badfit", "fit", lambda r: r["check"].update(iou=0.55))
        bad("thintex", "texture", lambda r: r["texture"].update(seen=0.3))
        bad("worsereg", "registration", lambda r: r["register"].update(flow_px_after=7.5))
        bad("frameworse", "registration", lambda r: r["register"]["per_frame"]["0"].update(end_px=9.0))
        bad("bigmove", "registration", lambda r: r["register"]["per_frame"]["1"].update(d_rot_deg=14.0))
        bad("faceworse", "face", lambda r: r["face"].update(heldout_err_pct_after=3.4))
        for name, area, cap in cases:
            f = fails(CC.check(cap))
            rec("caught: %s" % name, f == [area], "failed on %s" % f)
        # a one-photo capture (no held-out frames, no registration) is judged on the photo's own fit
        rec("a one-photo capture is checked on its fit",
            not fails(CC.check(make(root, "photo", dict(photo="me.jpg", fit_iou=0.80)))) and
            fails(CC.check(make(root, "photobad", dict(photo="me.jpg", fit_iou=0.5)))) == ["fit"], "")
        # a hard video: most frames still off, but nothing got worse -> a warning, not a failure
        def hard(r):
            for v in r["register"]["per_frame"].values():
                v["end_px"] = 9.0; v["start_px"] = 9.5
            r["register"].update(flow_px_before=9.5, flow_px_after=9.0)
        rep = copy.deepcopy(GOOD); hard(rep)
        res = CC.check(make(root, "hard", rep))
        rec("a hard video warns, does not fail", not fails(res) and any(ok == "warn" for _, ok, _ in res), "")
        # --all finds every capture in a folder and exits 1 if any fails
        rc = CC.main(["--all", root])
        rec("--all exits 1 when one capture fails", rc == 1, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    bad_ = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad_), len(R)))
    return 1 if bad_ else 0


if __name__ == "__main__":
    sys.exit(main())
