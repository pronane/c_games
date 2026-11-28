"""The "environments" library kind: a ground to play in, as one reusable recipe (v11.41).

The stadium, crowd, pitch-side boards, turf, goals and touchline (v11.32, v11.33, v11.39) were separate
modules with no library kind, so every game wired them up again.  An environment asset is a small recipe
that names a preset for each part; `build` turns it into the files a game loads:

    library/environments/<name>/environment.json   the recipe (below)
    library/environments/<name>/licence.json       CC0 for the built-in presets (all procedural)

recipe:
    sport      soccer / gaelic / hurling / rugby / aussie_rules (stadium.PITCH)
    stadium    {preset: bowl / classic / ground, ...StadiumSpec overrides}   or null
    pitch      {mow: stripes / checker / diagonal / rings / wide_stripes}    or null (turf texture)
    crowd      {fill: 0..1, home: "#hex", away: "#hex"}                      or null
    adboards   {rows: [[text, bg, fg, mark], ...]} (default sponsors)         or null
    goals      {sport: soccer / futsal / gaelic / hockey / handball}          or null
    touchline  {subs, ball_kids, photographers}                              or null

    from sforge import environments as E
    E.build(E.PRESETS["soccer_bowl"], "out/soccer_bowl")   # -> {"stadium": "...glb", "pitch": "...png", ...}

The same recipe works for every field sport the modules support; parts a sport has no model for (rugby
posts, Aussie rules turf markings) are null and `validate` says so.
"""
from __future__ import annotations

import copy
import json
import os

META = "environment.json"

PRESETS = {
    "soccer_bowl": dict(description="modern two-tier bowl, striped pitch, full house", sport="soccer",
                        stadium=dict(preset="bowl"), pitch=dict(mow="stripes"), crowd=dict(fill=.9, home="#c8102e", away="#1d428a"),
                        adboards={}, goals=dict(sport="soccer"), touchline={}),
    "soccer_classic": dict(description="old-style ground with open corners, checkerboard cut", sport="soccer",
                           stadium=dict(preset="classic"), pitch=dict(mow="checker"), crowd=dict(fill=.75, home="#7f1d1d", away="#f2f2f2"),
                           adboards={}, goals=dict(sport="soccer"), touchline={}),
    "soccer_ground": dict(description="small single-tier club ground, wide stripes, half full", sport="soccer",
                          stadium=dict(preset="ground"), pitch=dict(mow="wide_stripes"), crowd=dict(fill=.5, home="#14532d", away="#f5c400"),
                          adboards={}, goals=dict(sport="soccer"), touchline=dict(photographers=4)),
    "gaelic_ground": dict(description="county ground for Gaelic football", sport="gaelic",
                          stadium=dict(preset="ground", sport="gaelic"), pitch=dict(mow="stripes"),
                          crowd=dict(fill=.7, home="#006a4e", away="#c8102e"), adboards={}, goals=dict(sport="gaelic"), touchline={}),
    "hurling_ground": dict(description="county ground for hurling", sport="hurling",
                           stadium=dict(preset="classic", sport="hurling"), pitch=dict(mow="diagonal"),
                           crowd=dict(fill=.8, home="#7a1f2b", away="#00539f"), adboards={}, goals=dict(sport="gaelic"), touchline={}),
    "rugby_ground": dict(description="rugby ground (no posts model yet)", sport="rugby",
                         stadium=dict(preset="classic", sport="rugby"), pitch=dict(mow="wide_stripes"),
                         crowd=dict(fill=.8, home="#00205b", away="#ffffff"), adboards={}, goals=None, touchline={}),
    "aussie_oval": dict(description="Aussie rules oval (no turf markings or posts model yet)", sport="aussie_rules",
                        stadium=dict(preset="bowl", sport="aussie_rules"), pitch=None,
                        crowd=dict(fill=.85, home="#002b5c", away="#e21937"), adboards={}, goals=None, touchline=None),
}


def licence():
    from .library import blank_licence
    lic = blank_licence(redistribution="yes", ml_training="yes")
    lic.update(spdx="CC0-1.0", author="Sprite Forge Studio",
               notes="Procedural: built by sforge.stadium / pitch / crowd / adboards / goalnet / pitchside. No third-party assets.")
    return lic


def validate(r):
    """-> list of problems (empty = buildable)."""
    from . import stadium as S, pitch as P, goalnet as G
    p = []
    sport = r.get("sport")
    if sport not in S.PITCH:
        p.append("sport must be one of %s" % ", ".join(S.PITCH))
    st = r.get("stadium")
    if st is not None:
        if st.get("preset") not in S.PRESETS:
            p.append("stadium preset must be one of %s" % ", ".join(S.PRESETS))
        if st.get("sport", sport) != sport:
            p.append("stadium sport %s differs from the environment's %s" % (st.get("sport"), sport))
    pt = r.get("pitch")
    if pt is not None:
        if sport not in P.SPORTS:
            p.append("no turf markings for %s (set pitch to null)" % sport)
        if pt.get("mow", "stripes") not in P.MOW:
            p.append("pitch mow must be one of %s" % ", ".join(P.MOW))
    cr = r.get("crowd")
    if cr is not None and not 0 <= float(cr.get("fill", 1)) <= 1:
        p.append("crowd fill must be 0..1")
    g = r.get("goals")
    if g is not None and g.get("sport", sport) not in G.GOALS:
        p.append("goals must be one of %s (or null)" % ", ".join(G.GOALS))
    if r.get("touchline") is not None and st is None:
        p.append("the touchline needs a stadium (placements use its dugouts)")
    return p


def build(r, out):
    """write every part of a recipe into folder `out`.  -> {part: path} plus "environment.json" (the recipe
    with the built files and seat counts, which a game reads first)."""
    from . import stadium as S, pitch as P, crowd as C, adboards as A, goalnet as G, pitchside as PS
    probs = validate(r)
    if probs:
        raise ValueError("environment can't be built: " + "; ".join(probs))
    os.makedirs(out, exist_ok=True)
    sport, files, info = r["sport"], {}, {}
    st_info = None
    if r.get("stadium") is not None:
        over = {k: v for k, v in r["stadium"].items() if k != "preset"}
        over.setdefault("sport", sport)
        spec = S.preset(r["stadium"]["preset"], **over)
        files["stadium"] = os.path.join(out, "stadium.glb")
        st_info = S.export(spec, files["stadium"])
        files["seats"] = os.path.join(out, "stadium.seats")
        info["seats"] = int(st_info["seats"]) if isinstance(st_info.get("seats"), (int, float)) else st_info.get("seats_by_end")
        info["tris_stadium"] = st_info["tris"]
    if r.get("pitch") is not None:
        files["pitch"] = os.path.join(out, "pitch.png")
        info["pitch"] = P.export(files["pitch"], sport=sport, mow=r["pitch"].get("mow", "stripes"))
    if r.get("crowd") is not None:
        files["crowd"] = os.path.join(out, "crowd.glb")
        C.export(files["crowd"])
        info["crowd"] = dict(r["crowd"])
    if r.get("adboards") is not None:
        files["adboards"] = os.path.join(out, "adboards.png")
        rows = r["adboards"].get("rows")
        A.atlas(files["adboards"], [tuple(x) for x in rows] if rows else None)
    if r.get("goals") is not None:
        files["goals"] = os.path.join(out, "goal.glb")
        G.export(files["goals"], r["goals"].get("sport", sport))
    if r.get("touchline") is not None and st_info is not None:
        half = S.PITCH[sport]
        tl = PS.placements(st_info, half[0], half[1], **{k: int(v) for k, v in r["touchline"].items()})
        files["touchline"] = os.path.join(out, "touchline.json")
        json.dump(tl, open(files["touchline"], "w"), indent=1)
        files["touchline_props"] = os.path.join(out, "touchline_props.glb")
        PS.props_glb(files["touchline_props"])
        info["touchline_people"] = len(tl)
    man = dict(copy.deepcopy(r), built={k: os.path.basename(v) for k, v in files.items()}, info=info, version="11.41")
    files["environment.json"] = os.path.join(out, META)
    json.dump(man, open(files["environment.json"], "w"), indent=1, default=str)
    return files


def add_environment(lib, name, recipe, lic=None):
    from .library import slug, now
    lib.ensure()
    name = slug(name)
    d = lib.path("environments", name)
    os.makedirs(d, exist_ok=True)
    rec = dict(copy.deepcopy(recipe), name=name, added=now())
    json.dump(rec, open(os.path.join(d, META), "w", encoding="utf-8"), indent=1)
    json.dump(lic or licence(), open(os.path.join(d, "licence.json"), "w", encoding="utf-8"), indent=1)
    return d, validate(rec)


def seed_presets(lib, overwrite=False):
    """put PRESETS into the library.  -> names added"""
    added = []
    for n, r in PRESETS.items():
        if n in lib.names("environments") and not overwrite:
            continue
        add_environment(lib, n, r)
        added.append(n)
    return added


def load(lib, name):
    return json.load(open(os.path.join(lib.path("environments", name), META), encoding="utf-8"))
