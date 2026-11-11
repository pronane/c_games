#!/usr/bin/env python3
"""Check any capture - not only the five it was tuned on - against what every good capture must satisfy.

    python tools/check_capture.py CAPTURE_DIR [CAPTURE_DIR ...]      (CAPTURE_DIR = captures/NAME)
    python tools/check_capture.py --all captures/                     (every capture in the folder)

Run it after `forge.py capture` on a new video. It reads CAPTURE_DIR/out/report.json and the exported files and
checks, with the reason when one fails:

  files        GLB, FBX, OBJ, the texture and the turntable exist; the GLB is valid glTF 2.0 with a skin, a
               26-bone skeleton and its animation clips
  fit          the held-out frames' silhouette IoU is at least 0.70 (a fit that has not gone wrong); for a one-photo
               capture, the photo's own fit IoU
  texture      the texture saw at least 50% of the body
  registration (v11.10) the cameras' median misfit did not grow; no frame that moved got worse; every move is
               a correction (at most 8 degrees and 12% of the distance per round); and a warning, not a
               failure, when more than half of the frames are still over 6 px off (a hard video: little texture,
               the person moving)
  face         the held-out landmark error did not grow by more than 0.2% of the face width
Exit 1 when anything fails."""
from __future__ import annotations
import argparse
import json
import os
import struct
import sys


def _glb(path):
    with open(path, "rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] != b"glTF":
            return None, "not a GLB"
        ver = struct.unpack("<I", head[4:8])[0]
        n, kind = struct.unpack("<II", fh.read(8))
        if kind != 0x4E4F534A:
            return None, "first chunk is not JSON"
        return dict(version=ver, gltf=json.loads(fh.read(n))), ""


def check(cap):
    out = os.path.join(cap, "out")
    name = os.path.basename(os.path.normpath(cap))
    res = []                                       # (area, ok or "warn", text)
    rp = os.path.join(out, "report.json")
    if not os.path.isfile(rp):
        return [("files", False, "no out/report.json - the capture did not finish")]
    rep = json.load(open(rp))
    # files
    need = ["%s.glb" % name, "%s.fbx" % name, "%s.obj" % name, "%s_texture.png" % name, "%s_turntable.jpg" % name]
    miss = [f for f in need if not os.path.isfile(os.path.join(out, f))]
    res.append(("files", not miss, "missing %s" % ", ".join(miss) if miss else "%d files" % len(need)))
    gp = os.path.join(out, "%s.glb" % name)
    if os.path.isfile(gp):
        g, why = _glb(gp)
        if g is None:
            res.append(("files", False, "GLB: %s" % why))
        else:
            j = g["gltf"]
            skins = j.get("skins") or []
            joints = len(skins[0]["joints"]) if skins else 0
            anims = len(j.get("animations") or [])
            ok = g["version"] == 2 and joints >= 26 and anims >= 1
            res.append(("files", ok, "GLB v%d, %d joints, %d clips" % (g["version"], joints, anims)))
    # fit
    c = rep.get("check") or {}
    iou = c.get("iou")
    if iou is None and rep.get("photo"):
        # a one-photo capture has no held-out frames: the photo's own fit is the check
        iou = rep.get("fit_iou")
        res.append(("fit", iou is not None and iou >= 0.70, "one photo, fit IoU %s" % (round(iou, 3) if iou is not None else None)))
    else:
        res.append(("fit", iou is not None and iou >= 0.70, "held-out IoU %s" % (round(iou, 3) if iou is not None else None)))
    # texture
    st = rep.get("texture") or {}
    cov = st.get("seen")
    if cov is not None:
        res.append(("texture", cov >= 0.5, "%.0f%% of the body seen" % (100 * cov)))
    # registration
    rg = rep.get("register")
    if rg:
        b, a = rg.get("flow_px_before"), rg.get("flow_px_after")
        res.append(("registration", b is None or a is None or a <= b + 1e-6, "median misfit %s -> %s px" % (b, a)))
        pf = rg.get("per_frame") or {}
        worse = [k for k, v in pf.items() if v.get("moved") and v.get("start_px") is not None and v.get("end_px") is not None
                 and v["end_px"] > v["start_px"] + 1e-6]
        res.append(("registration", not worse, "frames worse after moving: %s" % (worse or "none")))
        big = [k for k, v in pf.items() if v.get("d_rot_deg", 0) > 8.0 or v.get("d_t_frac", 0) > 0.12]
        res.append(("registration", not big, "moves beyond a correction: %s" % (big or "none")))
        n = rg.get("frames") or 0; moved = rg.get("moved") or 0
        # frames that needed help and did not get it: still more than 6 px off after registration
        stuck = [k for k, v in pf.items() if (v.get("end_px") or 0) > 6.0]
        if n and len(stuck) > 0.5 * n:
            res.append(("registration", "warn", "%d of %d frames are still over 6 px off - a hard video (little "
                        "texture, the person moving)? reasons: %s" % (len(stuck), n,
                        sorted(set((rg.get("refused") or {}).values()))[:3])))
        else:
            res.append(("registration", True, "%d of %d frames moved; %d still over 6 px off" % (moved, n, len(stuck))))
    # face
    fc = rep.get("face") or {}
    e0, e1 = fc.get("heldout_err_pct_before"), fc.get("heldout_err_pct_after")
    if e0 is not None and e1 is not None:
        res.append(("face", e1 <= e0 + 0.2, "held-out landmark error %.1f%% -> %.1f%%" % (e0, e1)))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--all", help="check every capture under this folder")
    a = ap.parse_args(argv)
    caps = list(a.caps)
    if a.all:
        caps += [os.path.join(a.all, d) for d in sorted(os.listdir(a.all))
                 if os.path.isfile(os.path.join(a.all, d, "out", "report.json"))]
    if not caps:
        print("nothing to check"); return 0
    bad = 0
    for cap in caps:
        res = check(cap)
        fails = [r for r in res if r[1] is False]
        bad += bool(fails)
        print("%s: %s" % (os.path.basename(os.path.normpath(cap)), "FAIL" if fails else "ok"))
        for area, ok, text in res:
            print("   %-5s %-13s %s" % ({True: "ok", False: "FAIL", "warn": "warn"}[ok], area, text))
    print("\n%d of %d captures pass" % (len(caps) - bad, len(caps)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
