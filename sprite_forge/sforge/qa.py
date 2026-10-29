"""Sprite Forge Studio v9 - sprite QA checker.

Checks every frame of a build (or any build folder: forge.py qa <folder>):
  clipped     figure touches the cell edge (cut off)              FAIL
  empty       frame has no pixels                                 FAIL
  ground      feet not on ground_y in grounded moves (> tol px)   WARN
  pop         body centre jumps sideways between frames           WARN
  loop_seam   looping move: last->first frame jump much bigger than the move's normal step   WARN
  duplicate   two consecutive identical frames                    INFO
  strays      small detached pixel islands (dirt from cut-outs)   WARN
  fringe      bright / dark halo in the half-transparent edge     WARN
  scale       idle height differs from the build's stand height   WARN
Writes qa_report.txt + qa.json (score 0-100, per move status)."""
from __future__ import annotations
import glob
import json
import os
import re

import numpy as np
from PIL import Image

AIR_RE = re.compile(r"jump|air|fall|flip|knock|ko|dead|death|lie|lying|down|sweep|slide|dive|fly|hit|throw|victory|special", re.I)
SEV = {"FAIL": 3, "WARN": 2, "INFO": 1, "PASS": 0}


def _a(im):
    return np.asarray(im.getchannel("A"))


def check_move(name, frames, ground_y, loop=False, tol=3):
    issues = []
    cents, steps = [], []
    prev = None
    import cv2
    for i, im in enumerate(frames):
        A = _a(im)
        M = A > 40
        if not M.any():
            issues.append(("FAIL", "empty", i, "no pixels")); cents.append(None); prev = None; continue
        H, W = M.shape
        ys, xs = np.nonzero(M)
        if xs.min() == 0 or xs.max() == W - 1 or ys.min() == 0 or (ys.max() == H - 1 and ground_y < H - 1):
            edge = [n for n, c in (("left", xs.min() == 0), ("right", xs.max() == W - 1), ("top", ys.min() == 0),
                                   ("bottom", ys.max() == H - 1)) if c]
            issues.append(("FAIL", "clipped", i, "touches the %s edge" % "/".join(edge)))
        if not AIR_RE.search(name):
            low = int(ys.max())
            if abs(low - ground_y) > tol:
                issues.append(("WARN", "ground", i, "lowest pixel y=%d, ground_y=%d (%+d px)" % (low, ground_y, low - ground_y)))
        cents.append(float(xs.mean()))
        n, lab, st, _ = cv2.connectedComponentsWithStats(M.astype(np.uint8), 8)
        if n > 2:
            areas = st[1:, cv2.CC_STAT_AREA]
            small = [a for a in areas if a < max(12, 0.002 * areas.max())]
            if small:
                issues.append(("WARN", "strays", i, "%d detached speck(s) (%d px)" % (len(small), sum(small))))
        semi = (A > 10) & (A < 200)
        if semi.sum() > 50:
            rgb = np.asarray(im.convert("RGB")).astype(np.float32)
            lum = rgb.mean(-1)
            inner = lum[A >= 250]
            if inner.size:
                e = lum[semi]
                bright = float(((e > min(250, np.percentile(inner, 99) + 25))).mean())
                if bright > 0.25:
                    issues.append(("WARN", "fringe", i, "%.0f%% of the soft edge is a bright halo" % (100 * bright)))
        if prev is not None:
            d = float(np.abs(A.astype(np.int16) - prev.astype(np.int16)).mean())
            steps.append(d)
            if d == 0.0:
                issues.append(("INFO", "duplicate", i, "same as frame %d" % (i - 1)))
        prev = A
    W = frames[0].width if frames else 1
    c = [x for x in cents if x is not None]
    for i in range(1, len(cents)):
        if cents[i] is not None and cents[i - 1] is not None and abs(cents[i] - cents[i - 1]) > 0.12 * W and not AIR_RE.search(name):
            issues.append(("WARN", "pop", i, "body centre jumps %.0f px" % (cents[i] - cents[i - 1])))
    if loop and len(frames) > 2 and steps:
        seam = float(np.abs(_a(frames[0]).astype(np.int16) - _a(frames[-1]).astype(np.int16)).mean())
        med = float(np.median(steps)) or 1e-6
        if seam > 2.5 * med and seam > 1.0:
            issues.append(("WARN", "loop_seam", len(frames) - 1, "last->first change %.1f vs %.1f per step" % (seam, med)))
    status = max([s for s, *_ in issues], key=lambda s: SEV[s], default="PASS")
    if status == "INFO":
        status = "PASS"
    return {"status": status, "issues": [{"level": s, "check": k, "frame": f, "detail": d} for s, k, f, d in issues]}


def run(ordered, ground_y, loops=None, stand_px=None):
    loops = loops or {}
    res = {"moves": {}}
    for mv, fr in ordered:
        res["moves"][mv] = check_move(mv, fr, ground_y, loops.get(mv, False))
    idle = dict(ordered).get("idle")
    if idle and stand_px:
        ys = np.nonzero((_a(idle[0]) > 40).any(1))[0]
        if len(ys):
            h = int(ys.max() - ys.min() + 1)
            if abs(h - stand_px) > 0.08 * stand_px:
                res["moves"]["idle"]["issues"].append({"level": "WARN", "check": "scale", "frame": 0,
                                                       "detail": "idle height %d px vs stand height %d" % (h, stand_px)})
                if res["moves"]["idle"]["status"] == "PASS":
                    res["moves"]["idle"]["status"] = "WARN"
    pen = sum({"FAIL": 12, "WARN": 3, "PASS": 0}[m["status"]] for m in res["moves"].values())
    nw = sum(1 for m in res["moves"].values() for i in m["issues"] if i["level"] == "WARN")
    res["score"] = max(0, 100 - pen - min(20, nw // 4))
    res["fail"] = [m for m, d in res["moves"].items() if d["status"] == "FAIL"]
    res["warn"] = [m for m, d in res["moves"].items() if d["status"] == "WARN"]
    return res


def report_text(res, name):
    L = ["Sprite QA - %s   score %d/100   %d FAIL, %d WARN, %d PASS" % (
        name, res["score"], len(res["fail"]), len(res["warn"]), len(res["moves"]) - len(res["fail"]) - len(res["warn"]))]
    for mv, d in res["moves"].items():
        L.append("%-22s %s" % (mv, d["status"]))
        by = {}
        for i in d["issues"]:
            by.setdefault((i["level"], i["check"]), []).append(i)
        for (lv, ck), items in sorted(by.items(), key=lambda kv: -SEV[kv[0][0]]):
            fr = ",".join(str(i["frame"]) for i in items[:12]) + ("..." if len(items) > 12 else "")
            L.append("    %-4s %-10s frames %s: %s" % (lv, ck, fr, items[0]["detail"]))
    return "\n".join(L) + "\n"


def write_qa(cfg, out, ctx, report):
    loops = {m: s.loop for m, s in ctx["spec_by"].items()}
    stand = int(round(cfg.figure_h * ctx.get("scale", 1.0)))
    res = run(ctx["ordered"], cfg.ground_y, loops, stand)
    with open(os.path.join(out, "qa.json"), "w") as f:
        json.dump(res, f, indent=1)
    with open(os.path.join(out, "qa_report.txt"), "w") as f:
        f.write(report_text(res, cfg.name))
    if res["fail"]:
        report.warning("QA: FAIL in %s - see qa_report.txt" % ", ".join(res["fail"]))
    return "QA %d/100 (%d fail, %d warn)" % (res["score"], len(res["fail"]), len(res["warn"]))


def check_folder(folder, log=print):
    """forge.py qa <build folder | game folder with sprites.cfg>"""
    ordered, loops, ground, stand = [], {}, None, None
    aj = os.path.join(folder, "atlas.json")
    if os.path.isfile(aj) and os.path.isdir(os.path.join(folder, "moves")):
        js = json.load(open(aj))
        ground = js["meta"]["ground_y"]
        for mv, a in js["animations"].items():
            fr = [Image.open(os.path.join(folder, "moves", f + ".png")).convert("RGBA") for f in a["frames"]]
            ordered.append((mv, fr)); loops[mv] = a.get("loop", False)
    else:
        cfgp = os.path.join(folder, "sprites.cfg")
        if not os.path.isfile(cfgp):
            raise ValueError("%s: no atlas.json+moves/ or sprites.cfg" % folder)
        cw = ch = 0
        for line in open(cfgp):
            p = line.split()
            if not p or p[0].startswith("#"):
                continue
            if p[0] == "cell":
                cw, ch = int(p[1]), int(p[2])
            elif p[0] in ("baseline", "ground"):
                ground = int(p[1])
            elif p[0] == "stand_height":
                stand = int(p[1])
            elif p[0] == "frame" and len(p) >= 3:
                cw, ch = int(p[1]), int(p[2])
            elif p[0] == "anim" and len(p) >= 4 and cw:
                sh = Image.open(os.path.join(folder, p[2])).convert("RGBA")
                fr = [sh.crop((i * cw, 0, (i + 1) * cw, ch)) for i in range(sh.width // cw)]
                ordered.append((p[1], fr)); loops[p[1]] = p[1] in ("idle", "walk", "taunt", "victory", "fight_idle", "run")
            elif p[0] == "move" and len(p) >= 9:
                sh = Image.open(os.path.join(folder, p[2])).convert("RGBA")
                n, fw, fh, row = int(p[3]), int(p[4]), int(p[5]), int(p[8])
                ordered.append((p[1], [sh.crop((i * fw, row * fh, (i + 1) * fw, (row + 1) * fh)) for i in range(n)]))
                loops[p[1]] = p[7] == "1"
        if ground is None:
            ground = ch - 12
    res = run(ordered, ground, loops, stand)
    txt = report_text(res, os.path.basename(folder.rstrip("/\\")))
    with open(os.path.join(folder, "qa_report.txt"), "w") as f:
        f.write(txt)
    with open(os.path.join(folder, "qa.json"), "w") as f:
        json.dump(res, f, indent=1)
    log(txt)
    return res
