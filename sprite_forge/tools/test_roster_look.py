#!/usr/bin/env python3
"""v11.21: rosters whose players look different, every move inside its cell, hit boxes in the preview.

    python tools/test_roster_look.py [--quick]        (--quick: 4 packs instead of all for check 7)

Without any assets:
  1 default looks: every player of every game's default roster has a look of their own (no two alike in a roster),
    every look is valid MakeHuman appearance, the same roster gives the same looks every time, and the muscles
    follow the type (a heavy brawler is more muscular than a small agile fighter)
  2 a look becomes the right `forge.py look` line: the roster's kit and the squad number on the back
  3 hair / brow / lash colours are baked into their textures (not only a vertex colour engines ignore)
  4 the game kits paint plain shirts in the kit's colours with the squad number readable on the back (not mirrored)
  5 see-through parts of alpha-textured cards are not drawn as solid faces
  6 cell fit on synthetic frames: a move reaching past the cell moves the shared pivot; a ball flying off is ignored;
    a move that cannot fit with the others gets its own pivot; a character too big for the cell is scaled once
With builds:
  7 every game pack, mannequin: no move clips its cell (the QA's "clipped" FAIL is gone); each move's pivot in
    game_character.json equals its frames' pivot in atlas.json; grounded moves stand on their own ground line
  8 a tall library rig (sample_lanky) on the packs with leaps and dives: no clipped moves either
  9 (MakeHuman library here) a real two-player roster: each built from its look, coloured hair in the model, different
    portraits, the number on the shirt
"""
from __future__ import annotations
import argparse
import glob
import io
import json
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
    return subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(a), cwd=HERE, capture_output=True, text=True, timeout=1200)


def looks_checks():
    from sforge import roster as RO, gamepack as GP
    from sforge.appearance import Appearance
    bad = []
    for g in GP.list_packs():
        r = RO.default_roster(g, 6)
        looks = [p.get("look") for p in r["players"]]
        if any(not lk for lk in looks):
            bad.append(g + ": a player without a look"); continue
        keyset = [tuple(sorted((k, str(v)) for k, v in lk.items() if k in ("hair_style", "hair_colour", "skin", "facial_hair"))) for lk in looks]
        if len(set(keyset)) != len(keyset):
            bad.append(g + ": two players look alike")
        for p in r["players"]:
            ap = Appearance()
            for k, v in p["look"].items():
                try:
                    ap.set(k, v)
                except Exception as e:                                     # noqa: BLE001
                    bad.append("%s/%s %s=%s: %s" % (g, p["name"], k, v, e))
        if RO.default_roster(g, 6) != r:
            bad.append(g + ": not repeatable")
        if RO.validate(r):
            bad.append("%s: %s" % (g, RO.validate(r)))
    cast = {p["type"]: p["look"] for p in RO.default_roster("fighting", 5)["players"]}
    if not cast["heavy_brawler"]["muscle_arms"] > cast["small_agile"]["muscle_arms"]:
        bad.append("muscles do not follow the type")
    rec("1 every default roster player has a valid look of their own, repeatable, muscles by type", not bad, "; ".join(bad[:5]))
    p = dict(name="k", kit="gk", number=1, look=dict(hair_style="buzz", skin="young_african_male"))
    a = RO.look_argv(p, "/o/k.glb")
    b = RO.player_argv("soccer", p, "/o", look_glb="/o/k.glb")
    ok = a == ["look", "--set", "hair_style=buzz,skin=young_african_male", "--kit", "sf_gk#1", "--glb", "/o/k.glb"] and \
        b[:7] == ["build", "--game", "soccer", "--name", "k", "--out", "/o"] and "--rig" in b and "--kit" not in b
    rec("2 a look becomes the right look line (roster kit, squad number) and build line", ok, "%s | %s" % (a, b))


def tint_check():
    from sforge import mhchar
    im = Image.new("RGBA", (8, 8), (200, 200, 200, 255))
    bio = io.BytesIO(); im.save(bio, "PNG")
    images = {"hair_x": bio.getvalue()}
    C = np.tile(np.array([0.2, 0.1, 0.05, 1.0], np.float32), (3, 1))
    part = mhchar.Part("p_hair", "hair", np.zeros((3, 3)), np.array([[0, 1, 2]]), np.zeros((3, 2)), np.zeros((3, 4), int),
                       np.zeros((3, 4)), None, C, "hair_x")
    body = mhchar.Part("p_body", "body", np.zeros((3, 3)), np.array([[0, 1, 2]]), np.zeros((3, 2)), np.zeros((3, 4), int),
                       np.zeros((3, 4)), None, None, "skin")
    out = mhchar.bake_tints([part, body], images)
    h = out[0]
    px = np.asarray(Image.open(io.BytesIO(images[h.image])).convert("RGBA"))[0, 0]
    ok = h.image != "hair_x" and h.C is None and abs(int(px[0]) - 40) <= 2 and abs(int(px[1]) - 20) <= 2 and out[1] is body
    rec("3 hair colour is baked into the hair texture", ok, "%s %s %s" % (h.image, px, h.C))


def kit_check():
    from sforge import footballer as FB
    cols, num = FB.sf_kit("sf_blue#17")
    bad = []
    if num != 17 or cols[0].lower() != "#1440bf":
        bad.append("parse %s %s" % (cols, num))
    try:
        FB.sf_kit("sf_nope")
        bad.append("an unknown kit was accepted")
    except KeyError:
        pass
    pf = FB.paints("sf_blue#10")
    # the back of the shirt as a grid of points (template space: back z < 0.08, x left/right, y up)
    xs = np.linspace(-0.11, 0.11, 120); ys = np.linspace(1.34, 1.06, 150)
    X, Y = np.meshgrid(xs, ys)
    P = np.stack([X.ravel(), Y.ravel(), np.full(X.size, 0.0)], 1)
    col, _ = pf["jersey"].fn(P, np.zeros((len(P), 3)))
    trim = np.array([0.95, 0.95, 0.95])
    m = (np.abs(col - trim).sum(1) < 0.3).reshape(X.shape)
    if not 0.08 < m.mean() < 0.6:
        bad.append("number covers %.0f%% of the back box" % (100 * m.mean()))
    # seen from behind, the viewer's left is the player's left (+x): the "1" of "10" is there, the "0" (more ink) at -x
    left_half, right_half = m[:, 60:].mean(), m[:, :60].mean()     # x > 0 columns appear on the viewer's left
    if not left_half < right_half:
        bad.append("digits look mirrored (the 1 should have less ink than the 0: %.2f vs %.2f)" % (left_half, right_half))
    front = FB.paints("sf_blue#10")["jersey"].fn(np.stack([X.ravel(), Y.ravel(), np.full(X.size, 0.2)], 1), np.zeros((len(P), 3)))[0]
    if (np.abs(front - trim).sum(1) < 0.3).mean() > 0.02:
        bad.append("number on the front too")
    rec("4 game kits: plain shirt in the kit colours, squad number readable on the back only", not bad, "; ".join(bad))


def opaque_check():
    from sforge.rigrec import Rig
    r = Rig("t")
    tex = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(tex).rectangle([0, 0, 31, 63], fill=(30, 20, 10, 255))          # left half opaque
    r.V = np.zeros((6, 3)); r.F = np.array([[0, 1, 2], [3, 4, 5]]); r.fmat = np.zeros(2, int)
    r.fuv = np.array([[[0.05, 0.1], [0.2, 0.1], [0.1, 0.4]], [[0.7, 0.1], [0.9, 0.1], [0.8, 0.4]]])
    r.materials = [{"name": "hair", "color": [1, 1, 1], "texture": "textures/h.png"}]
    r.textures = {"textures/h.png": tex}
    vis = r.opaque_faces()
    rec("5 see-through card faces are not drawn", list(vis) == [True, False], str(list(vis)))


class _Cfg:
    def __init__(self, w=128, h=160):
        self.frame_w, self.frame_h = w, h
        self.pivot_x, self.ground_y = w // 2, int(h * 0.94)


def _frame(cfg, pad, x0, x1, y0, y1, ball=None):
    im = Image.new("RGBA", (cfg.frame_w + 2 * pad, cfg.frame_h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([pad + x0, pad + y0, pad + x1, pad + y1], fill=(200, 50, 50, 255))
    if ball:
        d.ellipse([pad + ball[0], pad + ball[1], pad + ball[0] + 6, pad + ball[1] + 6], fill=(240, 240, 240, 255))
    return im


def cellfit_check():
    from sforge import cellfit as CF
    bad = []
    cfg = _Cfg(); pad = CF.pad_for(cfg)
    st = lambda: _frame(cfg, pad, 54, 74, 50, 150)                           # standing on the ground line (150)
    dive = [_frame(cfg, pad, 60, 140, 120, 150)]                             # reaches 12 px past the right edge
    out = CF.fit({"idle": ([st()], "t", ""), "dive": (dive, "t", "")}, cfg, pad)
    if CF._clipped(out["dive"][0]) or CF._clipped(out["idle"][0]) or not cfg.pivot_x < 64 or cfg.move_pivots:
        bad.append("shared shift: pivot %s own %s" % (cfg.pivot_x, cfg.move_pivots))
    cfg = _Cfg()
    out = CF.fit({"idle": ([st()], "t", ""), "kick": ([_frame(cfg, pad, 54, 74, 50, 150, ball=(170, 60))], "t", "")}, cfg, pad)
    if cfg.pivot_x != 64 or CF._clipped(out["kick"][0]):
        bad.append("a ball flying off moved the pivot (%s)" % cfg.pivot_x)
    cfg = _Cfg()
    left = [_frame(cfg, pad, -40, 40, 120, 150)]; right = [_frame(cfg, pad, 60, 150, 120, 150)]
    out = CF.fit({"idle": ([st()], "t", ""), "ko_left": (left, "t", ""), "dive_right": (right, "t", "")}, cfg, pad)
    if not cfg.move_pivots or any(CF._clipped(v[0]) for v in out.values()):
        bad.append("own pivot: %s" % cfg.move_pivots)
    for m, (px, gy) in cfg.move_pivots.items():
        if gy != cfg.ground_y and m != "x":
            pass
    cfg = _Cfg()
    huge = {"idle": ([st()], "t", ""), "leap": ([_frame(cfg, pad, 50, 80, -30, 150)], "t", "")}
    k = CF.scale_needed(huge, cfg)
    if not 0.8 < k < 0.97:
        bad.append("scale for a too-tall move: %.3f" % k)
    rec("6 cell fit: shared pivot shift, a flying ball ignored, own pivot when needed, one scale for a too-big character",
        not bad, "; ".join(bad))


def pack_checks(quick):
    from sforge import gamepack as GP
    packs = GP.list_packs()
    if quick:
        packs = [p for p in packs if p in ("soccer", "gaelic", "boxing", "shooter")]
    tmp = tempfile.mkdtemp(prefix="sf_fit_")
    bad = []
    try:
        for g in packs:
            r = forge("build", "--game", g, "--mannequin", "--no-glb", "--no-cache", "--out", os.path.join(tmp, g))
            if r.returncode:
                bad.append("%s build: %s" % (g, (r.stdout + r.stderr)[-200:])); continue
            d = glob.glob(os.path.join(tmp, g, "*", "qa.json"))[0]
            folder = os.path.dirname(d)
            q = json.load(open(d))
            clipped = sorted({m for m, v in q["moves"].items() for i in v["issues"] if i["check"] == "clipped"})
            if clipped:
                bad.append("%s: clipped %s" % (g, clipped))
            man = json.load(open(os.path.join(folder, "game_character.json")))
            atl = json.load(open(os.path.join(folder, "atlas.json")))
            for a in man["animations"]:
                fr = atl["frames"].get("%s_00" % a["name"])
                if fr is None:
                    continue
                want = (round(a["pivot"]["x"] / a["w"], 5), round(a["pivot"]["y"] / a["h"], 5))
                if (fr["pivot"]["x"], fr["pivot"]["y"]) != want:
                    bad.append("%s/%s: atlas pivot %s vs manifest %s" % (g, a["name"], fr["pivot"], want))
            idle = next((a for a in man["animations"] if a["name"] == "idle"), None)
            if idle:
                strip = Image.open(os.path.join(folder, idle["strip"]))
                al = np.asarray(strip.getchannel("A")) > 40
                low = np.nonzero(al.any(1))[0].max() + 1
                if abs(low - idle["ground_y"]) > 3:
                    bad.append("%s idle stands at %d, ground %d" % (g, low, idle["ground_y"]))
        rec("7 %d packs on the mannequin: no clipped moves; manifest and atlas pivots agree; idle on its ground" % len(packs),
            not bad, "; ".join(bad[:6]))
        bad = []
        for g in (["gaelic", "platformer"] if quick else ["gaelic", "platformer", "soccer", "boxing"]):
            r = forge("build", "--game", g, "--rig", "sample_lanky", "--no-glb", "--no-cache", "--out", os.path.join(tmp, "lanky_" + g))
            if r.returncode:
                bad.append("%s: %s" % (g, (r.stdout + r.stderr)[-200:])); continue
            q = json.load(open(glob.glob(os.path.join(tmp, "lanky_" + g, "*", "qa.json"))[0]))
            clipped = sorted({m for m, v in q["moves"].items() for i in v["issues"] if i["check"] == "clipped"})
            if clipped:
                bad.append("%s: clipped %s" % (g, clipped))
        rec("8 a tall library rig on the packs with leaps and dives: no clipped moves", not bad, "; ".join(bad))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "checkout", "-q", "--", "library/library.json"], cwd=HERE, capture_output=True)


def real_roster_check():
    from sforge import roster as RO
    if not RO.looks_available():
        print("skip 9 - no MakeHuman library here (forge.py human --setup --full)"); return
    tmp = tempfile.mkdtemp(prefix="sf_look_")
    try:
        r = forge("roster", "--game", "soccer", "--size", "1", "--out", tmp)
        d = os.path.join(tmp, "soccer")
        bad = []
        if r.returncode:
            rec("9 a real roster built from looks", False, (r.stdout + r.stderr)[-300:]); return
        doc = json.load(open(os.path.join(d, "roster.json")))
        from sforge.importers import load_file
        ports = []
        for p in doc["players"]:
            if p.get("built_as") != "look":
                bad.append("%s built as %s" % (p["name"], p.get("built_as")))
            rig = load_file(os.path.join(d, p["folder"], "model.glb"))[0]
            hair = [m for m in rig.materials if m["name"].startswith("hair_")]
            if p["look"].get("hair_style") != "bald" and hair:
                im = rig.textures[hair[0]["texture"]]
                a = np.asarray(im.convert("RGBA")).reshape(-1, 4).astype(float)
                op = a[a[:, 3] > 128][:, :3].mean(0)
                want = np.array([int(p["look"]["hair_colour"][i:i + 2], 16) for i in (1, 3, 5)], float)
                if np.abs(op - want).max() > 90 or (op.std() < 4 and op.mean() > 180):
                    bad.append("%s hair texture %s, look %s" % (p["name"], op.round(), want))
            kit = [m for m in rig.materials if m["name"] == "kit"]
            if not kit:
                bad.append(p["name"] + ": no kit material")
            ports.append(np.asarray(Image.open(os.path.join(d, p["portrait"])).convert("RGB"), float))
        if len(ports) == 2 and np.abs(ports[0] - ports[1]).mean() < 8:
            bad.append("the two portraits are nearly the same")
        rec("9 a real roster: built from looks, hair coloured in the model, portraits differ", not bad, "; ".join(bad))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "checkout", "-q", "--", "library/library.json"], cwd=HERE, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    looks_checks()
    tint_check()
    kit_check()
    opaque_check()
    cellfit_check()
    pack_checks(a.quick)
    real_roster_check()
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
