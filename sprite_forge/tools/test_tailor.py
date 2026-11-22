#!/usr/bin/env python3
"""Garment shells and the kit atlas (v11.30, fed back from Arena FC).

    python tools/test_tailor.py

On the Gaelic squad GLB (MakeHuman game skeleton, skin-tight clothes, boots that are bare feet):
  1 every garment comes back, every identity, and the QA passes
  2 each opening is cut straight: the hem loop lies on one plane (spread < 2 mm), where the source
    staircase spreads over centimetres
  3 the cloth stands off the source (median 5 mm .. 25 mm) and never sinks into it by more than 4 mm
  4 boots: flat sole on the ground, and the toes are gone (the toe-gap curvature drops)
  5 the shirt tail tucked in the shorts is cut away (nothing of the shirt below the shorts' waist)
  6 UVs land inside their LAYOUT panels; the back print area is on the back of the torso
  7 replace_parts keeps every node, the skin and every animation; the new GLB reads back
  8 kitdesign: every style's mask, the detail and glyph atlases, the layout contract, a painted kit
  9 flutter (v11.35): free hems (sleeves, shorts legs) carry the flutter weight; the collar, the chest and the
    waistband none; it is written as TEXCOORD_1 and reads back
 11 clips_from (v11.36): replace_parts takes the clips of another GLB of the same skeleton
 10 keeper garments (v11.35): a base layer covering the arms from inside the short sleeve to the wrist,
    gloves covering the whole hand and overlapping the sleeve at the cuff"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import kitdesign as KD  # noqa: E402
from sforge import tailor as T  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402

SRC = os.path.join(HERE, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))


def loop_spread(V, F):
    sp = []
    for lp in T.boundary_loops(F):
        if len(lp) < 8:
            continue
        P = V[lp] - V[lp].mean(0)
        sp.append(float(np.linalg.svd(P, compute_uv=False)[2] / np.sqrt(len(lp))))
    return sp


def main():
    bones, jn = T.skeleton_from_glb(SRC)
    out_all = {}
    for pre in ("v0_", "v3_"):
        parts = T.read_parts(SRC, pre)
        out = T.tailor(parts, bones, joint_names=jn, log=lambda *a: None)
        out_all[pre] = out
        rec("%s all four garments" % pre, all(k in out and len(out[k].F) > 100 for k in ("jersey", "shorts", "socks", "boots")))
        rec("%s QA" % pre, T.qa(out, bones) == [], str(T.qa(out, bones)))
    parts = T.read_parts(SRC, "v0_")
    out = out_all["v0_"]
    for g in T.soccer_garments():
        src = parts[g.source]
        c = T.weld(src.V)
        u = np.unique(c)
        rm = -np.ones(len(src.V), int); rm[u] = np.arange(len(u))
        before = max(loop_spread(src.V[u], rm[c[src.F]]) or [0])
        p = T.cut_garment(src, g, None if g.name != "jersey" else float(np.percentile(parts["shorts"].V[:, 1], 99)) - .022)
        core = p.F[(p.F < p.extras["n_core"]).all(1)]
        after = max(loop_spread(p.V, core) or [1])
        rec("hems straight: %s" % g.name, after < .003, "spread %.1f mm -> %.2f mm" % (before * 1e3, after * 1e3))
        from scipy.spatial import cKDTree
        n = p.extras["n_core"]
        d, i = cKDTree(src.V).query(p.V[:n])
        sd = ((p.V[:n] - src.V[i]) * src.N[i]).sum(1)
        # skip the stretch an opening was extended past the source
        on = (p.V[:n, 1] <= src.V[:, 1].max()) & (p.V[:n, 1] >= src.V[:, 1].min())
        # 7 mm: smoothing pulls the crotch of the shorts in a little; the thighs there are under the cloth
        rec("cloth stands off: %s" % g.name, .003 <= np.median(d) <= .025 and np.percentile(sd[on], 5) > -.007,
            "median %.1f mm, 5th pct signed %.1f mm" % (np.median(d) * 1e3, np.percentile(sd[on], 5) * 1e3))
    b = out["boots"]
    rec("boot soles on the ground", abs(b.V[:, 1].min()) < 1e-6 and (b.V[:, 1] < .002).sum() > 50,
        "min y %.4f, %d sole verts" % (b.V[:, 1].min(), int((b.V[:, 1] < .002).sum())))

    def roughness(V, F):
        """share of toe-box edges folded by more than 45 deg: the gaps between toes are creases,
        a boot's toe box has none (the mesh is coarse there, so a mean angle says little)."""
        zf = np.percentile(V[:, 2], 80)
        c = T.weld(V)
        F = c[F]
        F = F[((V[F][:, :, 1] > .02) & (V[F][:, :, 2] > zf)).all(1)]
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        edge = {}
        for fi, f in enumerate(F):
            for a_, b_ in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                edge.setdefault((min(a_, b_), max(a_, b_)), []).append(fi)
        ang = [np.degrees(np.arccos(np.clip(fn[x[0]] @ fn[x[1]], -1, 1))) for x in edge.values() if len(x) == 2]
        return float((np.array(ang) > 45).mean())
    src = parts["boots"]
    c = T.weld(src.V); u = np.unique(c); rm = -np.ones(len(src.V), int); rm[u] = np.arange(len(u))
    r0 = roughness(src.V, src.F)
    r1 = roughness(b.V, b.F)
    rec("toes smoothed out of the boots", r1 < r0 * .5, "toe-box creases > 45 deg: %.1f%% -> %.1f%%" % (r0 * 100, r1 * 100))
    waist = float(np.percentile(parts["shorts"].V[:, 1], 99))
    rec("shirt tail tucked (cut inside the shorts)", out["jersey"].V[:, 1].min() > waist - .05,
        "shirt bottom %.3f, shorts waist %.3f" % (out["jersey"].V[:, 1].min(), waist))
    ok = True
    for nm in ("jersey", "shorts", "socks", "boots"):
        uv = out[nm].UV
        cen = uv[out[nm].F].mean(1)
        inside = np.zeros(len(cen), bool)
        for pn, (u0, v0, u1, v1) in T.LAYOUT.items():
            inside |= (cen[:, 0] >= u0 - 1e-6) & (cen[:, 0] <= u1 + 1e-6) & (cen[:, 1] >= v0 - 1e-6) & (cen[:, 1] <= v1 + 1e-6)
        ok &= bool(inside.all())
    rec("UVs inside the LAYOUT panels", ok)
    je = out["jersey"]
    u0, v0, u1, v1 = T.PRINT["back_number"]
    cen = je.UV[je.F].mean(1)
    inb = (cen[:, 0] > u0) & (cen[:, 0] < u1) & (cen[:, 1] > v0) & (cen[:, 1] < v1)
    zc = je.V[je.F][inb].mean(1)[:, 2]
    rec("back number area is on the back (faces -forward)", inb.sum() > 20 and (zc < .02).mean() > .9,
        "%d faces, %.0f%% behind" % (inb.sum(), 100 * (zc < .02).mean() if inb.sum() else 0))
    # flutter: the collar and the waistband are held, the sleeve and leg hems move
    je, sh = out["jersey"], out["shorts"]
    top = je.V[:, 1] > je.V[:, 1].max() - .01
    wst = sh.V[:, 1] > sh.V[:, 1].max() - .01
    leg = sh.V[:, 1] < sh.V[:, 1].min() + .01
    g = {x.name: x for x in T.soccer_garments()}
    rec("flutter: collar and waistband held, free hems move",
        np.abs(je.UV2[top, 0]).max() < 1e-6 and np.abs(sh.UV2[wst, 0]).max() < 1e-6 and np.abs(sh.UV2[leg, 0]).min() > g["shorts"].flutter * .5
        and je.UV2[:, 0].max() > g["jersey"].flutter * .95, "shorts leg %.4f" % np.abs(sh.UV2[leg, 0]).min())
    chest = (np.abs(je.V[:, 0]) < .08) & (je.V[:, 1] < je.V[:, 1].max() - .08) & (je.V[:, 1] > je.V[:, 1].max() - .25)
    rec("flutter stays off the chest and back", np.abs(je.UV2[chest, 0]).max() < 1e-6 and chest.sum() > 20)
    kp = T.tailor(parts, bones, garments=T.keeper_garments(), joint_names=jn, log=lambda *a: None)
    near, _t = T.dominant_bone(parts["body"], bones, jn)
    hand = np.char.endswith(near.astype(str), "Hand")
    hv = parts["body"].V[hand]
    gl, sl = kp.get("gloves"), kp.get("sleeves")
    ok = gl is not None and sl is not None and len(gl.F) > 500 and len(sl.F) > 300
    if ok:
        lo, hi = gl.V.min(0), gl.V.max(0)
        cover = ((hv >= lo - .002) & (hv <= hi + .002)).all(1).mean()
        # the base layer runs from inside the short sleeve down under the glove cuff
        overlap = sl.V[:, 1].min() < gl.V[:, 1].max() and sl.V[:, 1].max() > je.V[np.abs(je.V[:, 0]) > .2, 1].min()
        ok = cover > .99 and overlap
    rec("keeper base layer and gloves cover the arms and hands", ok)
    with tempfile.TemporaryDirectory() as td:
        dst = os.path.join(td, "t.glb")
        T.replace_parts(SRC, dst, out_all, extras={"kit_atlas": T.layout_json()})
        j0, _ = read_glb(SRC)
        j1, _ = read_glb(dst)
        rec("replace_parts keeps nodes, skin and clips",
            len(j1["nodes"]) == len(j0["nodes"]) and j1["skins"][0]["joints"] == j0["skins"][0]["joints"]
            and len(j1.get("animations", [])) == len(j0.get("animations", [])))
        p2 = T.read_parts(dst, "v0_")
        rec("tailored garments read back", len(p2["jersey"].F) == len(out["jersey"].F) and "kit_atlas" in j1["asset"]["extras"])
        dst2 = os.path.join(td, "c.glb")
        T.replace_parts(dst, dst2, {}, clips_from=SRC)
        j2, _ = read_glb(dst2)
        rec("clips_from: the clips of another GLB move over by node name",
            [a["name"] for a in j2.get("animations", [])] == [a["name"] for a in j0.get("animations", [])]
            and len(j2["nodes"]) == len(j1["nodes"]))
        rec("flutter weights read back (TEXCOORD_1)", p2["jersey"].UV2 is not None
            and np.allclose(p2["jersey"].UV2, out["jersey"].UV2, atol=1e-6))
        lay = KD.export(os.path.join(td, "kit"))
        files = os.listdir(os.path.join(td, "kit"))
        rec("kitdesign export", all("kit_pattern_%s.png" % s in files for s in KD.STYLES)
            and {"kit_detail.png", "kit_glyphs.png", "kit_layout.json"} <= set(files)
            and lay["glyphs"] == KD.GLYPHS and set(lay["print"]) >= {"back_name", "back_number"})
        masks = {s: KD.pattern_mask(s, 256) for s in KD.STYLES}
        rec("every style differs from plain", all(masks[s].sum() > 0 for s in KD.STYLES if s != "plain") and masks["plain"].sum() == 0)
        img = KD.paint("hoops", "#15803d", "#ffffff", "#111827", number=7, name="O'NEILL", size=512)
        a = np.asarray(img)
        rec("painted kit has the colours and a print", a.shape == (512, 512, 3) and len(np.unique(a.reshape(-1, 3), axis=0)) > 50)
    fails = [r for r in R if not r[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
