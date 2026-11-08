"""forge.py capture - the fitted body as MakeHuman files, to keep editing it in MakeHuman / MPFB (v11.1).

  NAME.mhm         MakeHuman 1.x model file: the macros (gender, age, muscle, weight, height, proportions) and every
                   fitted modifier (torso-scale-depth-decr|incr, measure-bust-circ-decr|incr, ...) - open it in
                   MakeHuman (File > Load) or in Blender with MPFB2 (Import > MakeHuman model .mhm)
  NAME.mpfb.json   the same body as an MPFB2 human preset (Blender: MPFB > Presets > load human)
The texture is in NAME_texture.png (MakeHuman UV layout, top-left quarter of the atlas = the body; NAME_skin.png is
that quarter alone, ready to use as a MakeHuman / MPFB skin image).

MakeHuman sets size with its height macro, Sprite Forge scales the body to the given height: the height macro
written here is the one that gives that stature (found by bisection on MakeHuman's own targets), so the model
loads at the right size."""
from __future__ import annotations
import json
import os
import numpy as np

from . import human as HU, capture_body as CB

MACRO_LINES = [("macrodetails/Gender", "gender"), ("macrodetails/Age", "age"),
               ("macrodetails-universal/Muscle", "muscle"), ("macrodetails-universal/Weight", "weight"),
               ("macrodetails-height/Height", "height"), ("macrodetails-proportions/BodyProportions", "proportions"),
               ("macrodetails/African", "african"), ("macrodetails/Asian", "asian"), ("macrodetails/Caucasian", "caucasian"),
               ("breast/BreastSize", "cupsize"), ("breast/BreastFirmness", "firmness")]


# MPFB2's macro interpolation (data/targets/macrodetails/macro.json): MakeHuman 1.x's curves with small dead zones
# (height has none between 0.49 and 0.51) and a 0.01 cutoff on combined weights. Used to pick the height macro so the
# .mhm / .mpfb.json load at the captured stature in MPFB.
MPFB_PARTS = {
    "gender": [(-0.01, 1.01, "female", "male")],
    "age": [(-0.01, 0.1874998, "baby", "child"), (0.1874999, 0.49998, "child", "young"), (0.49999, 1.01, "young", "old")],
    "muscle": [(-0.01, 0.49998, "minmuscle", "averagemuscle"), (0.49999, 1.01, "averagemuscle", "maxmuscle")],
    "weight": [(-0.01, 0.49998, "minweight", "averageweight"), (0.49999, 1.01, "averageweight", "maxweight")],
    "proportions": [(-0.01, 0.4999, "uncommonproportions", ""), (0.5, 1.01, "", "idealproportions")],
    "height": [(-0.01, 0.49, "minheight", ""), (0.51, 1.01, "", "maxheight")],
}


def _mpfb_components(name, v):
    out = []
    for lo, hi, low, high in MPFB_PARTS[name]:
        if lo < v < hi:
            pct = (v - lo) / (hi - lo)
            if low:
                out.append((low, round(1 - pct, 4)))
            if high:
                out.append((high, round(pct, 4)))
    return out


def mpfb_macro_weights(p, cutoff=0.01):
    c = {k: _mpfb_components(k, float(p.get(k, 0.5))) for k in MPFB_PARTS}
    races = {r: float(p.get(r, 1 / 3.0)) for r in ("african", "asian", "caucasian")}
    out = {}
    for r, rv in races.items():
        for a, av in c["age"]:
            for g, gv in c["gender"]:
                w = rv * gv * av
                if w > cutoff:
                    out["targets/macrodetails/%s-%s-%s" % (r, g, a)] = w
    for g, gv in c["gender"]:
        for a, av in c["age"]:
            for m, mv in c["muscle"]:
                for wn, wv in c["weight"]:
                    base = gv * av * mv * wv
                    if base > cutoff:
                        out["targets/macrodetails/universal-%s-%s-%s-%s" % (g, a, m, wn)] = base
                    for h, hv in c["height"]:
                        if base * hv > cutoff:
                            out["targets/macrodetails/height/%s-%s-%s-%s-%s" % (g, a, m, wn, h)] = base * hv
                    for pr, pv in c["proportions"]:
                        if base * pv > cutoff and a != "baby":
                            out["targets/macrodetails/proportions/%s-%s-%s-%s-%s" % (g, a, m, wn, pr)] = base * pv
    return out


def height_macro(macros, sliders, height_m, bm=None, mpfb=True):
    """MakeHuman height macro (0..1) that makes this body `height_m` tall (MPFB2's interpolation by default)"""
    bm = bm or CB.BodyModel()
    D = np.zeros_like(bm.Vall)
    for k, s in (sliders or {}).items():
        if k in bm.slider_d and s:
            d = bm.slider_d[k][1 if s > 0 else 0]
            if d is not None:
                D += abs(float(s)) * d

    def stature(h):
        p = dict(HU.DEFAULTS); p.update({k: float(v) for k, v in macros.items() if k in HU.DEFAULTS}); p["height"] = h
        V, _ = HU.morph(bm.Vall, bm.T, mpfb_macro_weights(p) if mpfb else HU.macro_weights(p))
        V = (V + D)[bm.used_v]
        return float(V[:, 1].max() - V[:, 1].min()) * 0.1            # dm -> m
    lo, hi = 0.0, 1.0
    if not (stature(lo) <= height_m <= stature(hi)):
        return 0.0 if height_m < stature(lo) else 1.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if stature(mid) < height_m:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def modifier_lines(sliders):
    out = []
    for k, s in sorted((sliders or {}).items()):
        if k not in CB.SLIDERS or abs(float(s)) < 1e-4:
            continue
        dn, up = CB.SLIDERS[k]                                   # "torso/torso-scale-depth-decr", "...-incr"
        base = dn[:-len("-decr")]
        out.append(("%s-decr|incr" % base, float(s)))
    return out


def write(out_dir, name, macros, sliders, height_m=None):
    ph = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "height": 0.5, "proportions": 0.5,
          "african": 1 / 3.0, "asian": 1 / 3.0, "caucasian": 1 / 3.0, "cupsize": 0.5, "firmness": 0.5}
    ph.update({k: float(v) for k, v in macros.items() if k in ph})
    if height_m:
        ph["height"] = height_macro(macros, sliders, height_m)
    mods = modifier_lines(sliders)
    L = ["# Written by Sprite Forge capture (MakeHuman CC0 body fitted to a video / photo)", "version v1.2.0",
         "name %s" % name, "camera 0.0 0.0 0.0 0.0 0.0 1.0"]
    L += ["modifier %s %.6f" % (m, ph[k]) for m, k in MACRO_LINES]
    L += ["modifier %s %.6f" % (m, v) for m, v in mods]
    L += ["eyes HighPolyEyes 2c12f43b-1303-432c-b7ce-d78346baf2e6", "clothesHideFaces True",
          "skinMaterial skins/default.mhmat", "skeleton default.mhskel", "subdivide False"]
    mhm = os.path.join(out_dir, name + ".mhm")
    open(mhm, "w").write("\n".join(L) + "\n")
    targets = []
    for m, v in mods:
        base = m.split("/", 1)[1].replace("-decr|incr", "")
        targets.append({"target": base + ("-incr" if v > 0 else "-decr"), "value": abs(v)})
    js = {"phenotype": {"gender": ph["gender"], "age": ph["age"], "muscle": ph["muscle"], "weight": ph["weight"],
                        "height": ph["height"], "proportions": ph["proportions"], "cupsize": ph["cupsize"],
                        "firmness": ph["firmness"],
                        "race": {"african": ph["african"], "asian": ph["asian"], "caucasian": ph["caucasian"]}},
          "targets": targets, "rig": "default", "eyes": "", "eyebrows": "", "eyelashes": "", "hair": "", "proxy": "",
          "tongue": "", "teeth": "", "clothes": [], "skin_mhmat": "", "skin_material_type": "NONE",
          "name": name, "source": "Sprite Forge capture"}
    mp = os.path.join(out_dir, name + ".mpfb.json")
    json.dump(js, open(mp, "w"), indent=1)
    return dict(mhm=mhm, mpfb=mp)
