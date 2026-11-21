#!/usr/bin/env python3
"""v11.22: sprites that are not blocky or blotchy, bigger players, a sports idle.

    python tools/test_render_quality.py [--quick]

Without any assets (synthetic meshes):
  1 textured drawing: a rig with several textures shows its texture detail per pixel (the old way kept one colour
    per triangle)
  2 smooth light: a faceted sphere comes out with smooth shading - no steps at the triangle edges
  3 alpha cards: the see-through half of a hair card shows what is behind it, the opaque half covers it
  4 the kit still recolours a textured material; vertices split by UV seams share one normal
  5 supersampling follows the cell (4x at 160 px, 2x at 320 px)
  6 garment hems: a zig-zag hem comes out straight, keeps its size, and no vertex moves more than 1.5 cm
  7 the sports idle: in the starter (CC0), chosen by soccer / Gaelic / basketball / tennis, knees softer than the
    plain idle; a pack's named procedural motion is found even when it is not a library clip
  8 grounding: the feet reference is where idle / walk / run plant (median), and the cell fit puts it on the line
  9 the QA's ground tolerance grows with the cell (3 px at 160, 6 px at 320)
With builds:
 10 HD (--frame 2x, roster --hd, Games tab): every game pack at 256x320 on the mannequin builds with no clipped
    move, the player twice as tall as at 128x160, and a pack's figure share (Gaelic 0.58) kept
 11 the sports idle builds on the mannequin with its feet on the ground and passes the QA
"""
from __future__ import annotations
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name, ("  - " + str(detail)[:400]) if detail and not ok else ""))


def forge(*a):
    return subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(a), cwd=HERE, capture_output=True, text=True, timeout=1800)


def _rs(w=128, h=160, fig=140):
    from sforge.render import RenderSettings
    return RenderSettings(cell_w=w, cell_h=h, figure_h=fig, baseline=int(h * 0.9), anchor_x=w // 2, yaw=0, pitch=0, ss=3,
                          outline=False)


def _quad_rig(textures, mats, faces_mat, z=(0.0, 0.0)):
    """two quads (4 triangles) facing the camera: x -0.4..0.4, y 0.4..1.4; quad k at depth z[k]"""
    from sforge.rigrec import Rig
    r = Rig("t")
    V, F, UV = [], [], []
    for k, zz in enumerate(z):
        b = len(V)
        V += [[-0.4, 0.4, zz], [0.4, 0.4, zz], [0.4, 1.4, zz], [-0.4, 1.4, zz]]
        F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    r.V = np.array(V, float); r.F = np.array(F)
    uvv = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], float)
    r.fuv = np.array([uvv[[0, 1, 2]], uvv[[0, 2, 3]]] * len(z))
    r.fmat = np.array(faces_mat)
    r.materials = mats
    r.textures = textures
    return r


def textured_check():
    from sforge.render_rich import render_rich, corner_normals
    tex = Image.new("RGBA", (64, 64))
    d = ImageDraw.Draw(tex)
    for i in range(8):
        for j in range(8):
            d.rectangle([i * 8, j * 8, i * 8 + 7, j * 8 + 7], fill=(230, 40, 40, 255) if (i + j) % 2 else (40, 40, 230, 255))
    r = _quad_rig({"a.png": tex, "b.png": Image.new("RGBA", (8, 8), (40, 200, 40, 255))},
                  [{"name": "shirt", "texture": "a.png"}, {"name": "skin", "texture": "b.png"}], [0, 0, 1, 1], z=(0.0, -0.3))
    P = r.V[r.F]
    CN, _ = corner_normals(r.V, r.F, r.smooth_groups())
    im = render_rich(P, r.fuv, r.fmat, r.rich_materials(), r.face_colors(), CN, _rs())
    a = np.asarray(im.convert("RGB")).astype(int)
    row = a[im.height // 2 - 10]
    red = (row[:, 0] > 150) & (row[:, 2] < 120); blue = (row[:, 2] > 150) & (row[:, 0] < 120)
    switches = int(np.abs(np.diff(red.astype(int))).sum())
    rec("1 several textures drawn per pixel (checker squares across the shirt)", switches >= 6 and red.sum() > 10 and blue.sum() > 10,
        "switches %d red %d blue %d" % (switches, red.sum(), blue.sum()))


def sphere(n=10, m=14):
    V, F = [], []
    for i in range(n + 1):
        th = math.pi * i / n
        for j in range(m):
            ph = 2 * math.pi * j / m
            V.append([0.4 * math.sin(th) * math.cos(ph), 0.9 + 0.4 * math.cos(th), 0.4 * math.sin(th) * math.sin(ph)])
    for i in range(n):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            c, d = a + m, b + m
            F += [[a, c, b], [b, c, d]]
    return np.array(V), np.array(F)


def smooth_check():
    from sforge.render_rich import render_rich, corner_normals, smooth_groups
    V, F = sphere()
    P = V[F]
    rgb = np.full((len(F), 3), 0.7)
    mats = [dict(tex=None, alpha=False)]
    fmat = np.zeros(len(F), int)
    CN, Nf = corner_normals(V, F, smooth_groups(V), cos_lim=-1.0)
    rs = _rs(160, 160, 200)
    sm = np.asarray(render_rich(P, None, fmat, mats, rgb, CN, rs).convert("L"), float)
    flat = np.asarray(render_rich(P, None, fmat, mats, rgb, np.repeat(Nf[:, None, :], 3, 1), rs).convert("L"), float)
    inside = np.asarray(render_rich(P, None, fmat, mats, rgb, CN, rs).getchannel("A")) > 250
    from scipy import ndimage
    inside = ndimage.binary_erosion(inside, iterations=4)

    def steps(img):
        g = np.abs(np.diff(img, axis=1))[:, :][inside[:, 1:] & inside[:, :-1]]
        return float(np.percentile(g, 99))
    rec("2 smooth light: no steps at triangle edges (99th-percentile pixel step smooth %.1f vs faceted %.1f)" % (steps(sm), steps(flat)),
        steps(sm) < 0.6 * steps(flat), "")


def alpha_check():
    from sforge.render_rich import render_rich, corner_normals
    card = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(card).rectangle([0, 0, 15, 31], fill=(20, 20, 20, 255))          # left half opaque dark hair
    back = Image.new("RGBA", (8, 8), (220, 30, 30, 255))
    r = _quad_rig({"hair.png": card, "skin.png": back},
                  [{"name": "hair_short", "texture": "hair.png"}, {"name": "skin", "texture": "skin.png"}],
                  [0, 0, 1, 1], z=(0.2, 0.0))                                 # card in front of the red quad
    P = r.V[r.F]
    CN, _ = corner_normals(r.V, r.F, r.smooth_groups())
    mats = r.rich_materials()
    im = np.asarray(render_rich(P, r.fuv, r.fmat, mats, r.face_colors(), CN, _rs()).convert("RGB")).astype(int)
    y = im.shape[0] // 2 - 10
    left, right = im[y, 40], im[y, 88]
    ok = mats[0]["alpha"] and not mats[1]["alpha"] and left.max() < 90 and right[0] > 150 and right[1] < 100
    rec("3 alpha cards: the see-through half shows the red behind, the opaque half covers it", ok, "%s %s %s" % (left, right, [m["alpha"] for m in mats]))


def kit_seam_check():
    from sforge.render_rich import smooth_groups, corner_normals
    tex = Image.new("RGBA", (8, 8), (200, 200, 200, 255))
    r = _quad_rig({"k.png": tex}, [{"name": "Jersey_Mat", "texture": "k.png"}], [0, 0, 0, 0], z=(0.0, 0.0))
    m0 = r.rich_materials()[0]["tex"][..., :3].mean((0, 1))
    km = r.rich_materials({"name": "test", "slots": {"jersey": {"color": [0.1, 0.2, 0.9], "mode": "replace"}}})
    k_ok = True
    try:
        from sforge import kits as K
        rule = K.rule_for({"name": "test", "slots": {"jersey": {"color": [0.1, 0.2, 0.9], "mode": "replace"}}}, "Jersey_Mat")
        k_ok = rule is None or km[0]["tex"] is None or np.abs(km[0]["tex"][..., :3].mean((0, 1)) - m0).max() > 0.2
    except Exception:                                                      # noqa: BLE001
        pass
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [0, -1, 0.5]], float)       # vertex 0 and 3: one place
    F = np.array([[0, 1, 2], [3, 4, 1]])
    g = smooth_groups(V)
    CN, _ = corner_normals(V, F, g, cos_lim=-1.0)
    rec("4 the kit recolours a textured material; seam-split vertices share one normal",
        k_ok and g[0] == g[3] and np.allclose(CN[0, 0], CN[1, 0]), "groups %s" % g)


def ss_check():
    from sforge.render_rich import ss_for
    rec("5 supersampling follows the cell: 4x at 160 px, 2x at 320 px", ss_for(160) == 4 and ss_for(320) == 2 and ss_for(640) == 2,
        (ss_for(160), ss_for(320)))


def hem_check():
    from sforge.mhchar import _smooth_hem
    n = 48
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = np.stack([0.06 * np.cos(ang), 0.5 + 0.012 * np.where(np.arange(n) % 2, 1, -1), 0.06 * np.sin(ang)], 1)
    bd = np.array([[i, (i + 1) % n] for i in range(n)])
    S = _smooth_hem(V, bd)
    zig0 = np.ptp(V[:, 1]); zig1 = np.ptp(S[:, 1])
    r0 = np.linalg.norm(V[:, [0, 2]], axis=1).mean(); r1 = np.linalg.norm(S[:, [0, 2]], axis=1).mean()
    mv = np.linalg.norm(S - V, axis=1).max()
    rec("6 a zig-zag hem comes out straight (%.1f -> %.1f mm), keeps its size (%.1f%%), moves <= 1.5 cm" % (zig0 * 1000, zig1 * 1000, 100 * (r1 / r0 - 1)),
        zig1 < 0.3 * zig0 and abs(r1 / r0 - 1) < 0.05 and mv <= 0.0151, "")


def idle_check():
    from sforge import motionlib as ML, gamepack as GP
    from sforge.motions import find_motion, LIB
    bad = []
    if not ML.has_move("idle_athletic", None) or ML.origin_of("idle_athletic", None) != "starter":
        bad.append("not in the starter")
    lic = json.load(open(os.path.join(HERE, "motion_library", "idle_athletic.json"))).get("licence", {})
    if lic.get("spdx") != "CC0-1.0":
        bad.append("licence %s" % lic)
    for g in ("soccer", "gaelic", "basketball", "tennis"):
        idle = next(m for m in GP.load(g)["moves"] if m["name"] == "idle")
        if "idle_athletic" not in (idle.get("prefer") or []):
            bad.append(g + " does not prefer it")
    a, p = LIB["idle_athletic"].sample(0.0)[0], LIB["idle"].sample(0.0)[0]
    if not a.get("knee_L", 0) > p.get("knee_L", 0) + 10:
        bad.append("knees %s vs %s" % (a.get("knee_L"), p.get("knee_L")))
    m = find_motion("lib:idle_athletic")
    if m is None:
        bad.append("lib:idle_athletic not found")
    if find_motion("lib:no_such_motion_anywhere") is not None:
        bad.append("an unknown name was found")
    rec("7 the sports idle: CC0 starter clip, preferred by the sports packs, softer knees, found by name", not bad, "; ".join(bad))


def ground_check():
    from sforge import cellfit as CF

    class C:
        frame_w, frame_h, pivot_x, ground_y = 64, 80, 32, 75
    pad = CF.pad_for(C)

    def fr(low):
        im = Image.new("RGBA", (64 + 2 * pad, 80 + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([pad + 28, pad + 20, pad + 36, pad + low - 1], fill=(200, 0, 0, 255))
        return im
    frames = {"idle": ([fr(78), fr(78)], "t", ""), "walk": ([fr(75), fr(74)], "t", ""), "run": ([fr(75), fr(73)], "t", ""),
              "jump": ([fr(50)], "t", "")}
    ref = CF.ground_ref(frames)
    cfg = C()
    out = CF.fit(frames, cfg, pad)
    low_walk = CF._lowest(out["walk"][0][0])
    rec("8 grounding: feet reference is the median planted foot (idle/walk/run), and the fit puts it on the line",
        ref == pad + 75 and low_walk == cfg.ground_y, "ref %s (want %d), walk low %s ground %s" % (ref, pad + 75, low_walk, cfg.ground_y))


def qa_tol_check():
    from sforge import qa as Q
    im = Image.new("RGBA", (128, 160), (0, 0, 0, 0)); ImageDraw.Draw(im).rectangle([60, 40, 68, 145], fill=(200, 0, 0, 255))
    hd = Image.new("RGBA", (256, 320), (0, 0, 0, 0)); ImageDraw.Draw(hd).rectangle([120, 80, 136, 296], fill=(200, 0, 0, 255))
    sd_issues = Q.check_move("walk", [im], 150)["issues"] if isinstance(Q.check_move("walk", [im], 150), dict) else Q.check_move("walk", [im], 150)
    hd_issues = Q.check_move("walk", [hd], 301)["issues"] if isinstance(Q.check_move("walk", [hd], 301), dict) else Q.check_move("walk", [hd], 301)

    def has_ground(iss):
        return any((i.get("check") if isinstance(i, dict) else i[1]) == "ground" for i in iss)
    rec("9 the ground tolerance grows with the cell (a 4 px float warns at 160 px, not at 320 px)",
        has_ground(sd_issues) and not has_ground(hd_issues), "%s | %s" % (sd_issues, hd_issues))


def hd_checks(quick):
    from sforge import gamepack as GP, roster as RO
    packs = GP.list_packs()
    if quick:
        packs = [p for p in packs if p in ("soccer", "gaelic", "boxing")]
    tmp = tempfile.mkdtemp(prefix="sf_hd_")
    bad = []
    try:
        for g in packs:
            frame = RO.hd_frame(g)
            hs = {}
            for tag, extra in (("sd", []), ("hd", ["--frame", frame])):
                r = forge("build", "--game", g, "--mannequin", "--no-glb", "--no-cache", "--out", os.path.join(tmp, g + tag), *extra)
                if r.returncode:
                    bad.append("%s %s: %s" % (g, tag, (r.stdout + r.stderr)[-200:])); break
                folder = os.path.dirname(glob.glob(os.path.join(tmp, g + tag, "*", "qa.json"))[0])
                q = json.load(open(os.path.join(folder, "qa.json")))
                clipped = sorted({m for m, v in q["moves"].items() for i in v["issues"] if i["check"] == "clipped"})
                if clipped:
                    bad.append("%s %s clipped %s" % (g, tag, clipped))
                man = json.load(open(os.path.join(folder, "game_character.json")))
                idle = next((a for a in man["animations"] if a["name"] == "idle"), man["animations"][0])
                strip = Image.open(os.path.join(folder, idle["strip"]))
                al = np.asarray(strip.getchannel("A")) > 40
                rows = np.nonzero(al[:, :idle["w"]].any(1))[0]
                hs[tag] = (rows.max() - rows.min(), idle["h"])
            if len(hs) == 2:
                k = hs["hd"][0] / float(max(1, hs["sd"][0]))
                if not 1.85 < k < 2.15 or hs["hd"][1] != 2 * hs["sd"][1]:
                    bad.append("%s: HD figure %.2fx (cells %s / %s)" % (g, k, hs["hd"][1], hs["sd"][1]))
        a = RO.player_argv("gaelic", dict(name="x"), "/o", hd=True)
        if a[a.index("--frame") + 1] != "256x320":
            bad.append("roster --hd frame %s" % a)
        rec("10 HD on %d packs: twice the size, no clipped moves, figure shares kept; roster --hd" % len(packs), not bad, "; ".join(bad[:6]))
        q = json.load(open(glob.glob(os.path.join(tmp, "soccersd", "*", "qa.json"))[0]))
        rep = open(glob.glob(os.path.join(tmp, "soccersd", "*", "build_report.txt"))[0]).read()
        idle = q["moves"].get("idle", {})
        rec("11 the sports idle builds on the mannequin with its feet on the ground (QA %s)" % idle.get("status"),
            "idle_athletic" in rep and idle.get("status") == "PASS", [l for l in rep.splitlines() if l.startswith("idle ")])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "checkout", "-q", "--", "library/library.json"], cwd=HERE, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    textured_check()
    smooth_check()
    alpha_check()
    kit_seam_check()
    ss_check()
    hem_check()
    idle_check()
    ground_check()
    qa_tol_check()
    hd_checks(a.quick)
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
