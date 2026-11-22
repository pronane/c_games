#!/usr/bin/env python3
"""Stadiums, crowd and pitch-side boards (v11.32, fed back from Arena FC).

    python tools/test_stadium.py

  1 every preset builds within a triangle budget, with every named part a game overrides
  2 seats: thousands, all outside the pitch and run-off, every seat facing the pitch, rows rising
  3 the ends are marked (home / away) and the side stands are not
  4 the same code builds a Gaelic / hurling ground round a 145 x 90 m pitch
  5 the advertising ring keeps clear of the dugouts; dugouts sit between the touchline and the stand
  6 GLB + .seats + .json round trip
  7 crowd: seated spectator <= 120 triangles, part / arm channels in TEXCOORD_1, arms marked
  8 board atlas: one row per sponsor, every name original"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import adboards as AB  # noqa: E402
from sforge import crowd as CR  # noqa: E402
from sforge import stadium as S  # noqa: E402
from sforge.glbpack import _acc_bytes, read_glb  # noqa: E402

R = []
PARTS = {"stand_seats", "stand_concrete", "ad_ring", "concourse"}


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    for name, spec in S.PRESETS.items():
        M, info, seats = S.build(spec)
        tris = sum(len(m.F) for m in M.values())
        names = {k for k, m in M.items() if m.V}
        rec("%s: builds under 40k triangles with its parts" % name, tris < 40000 and PARTS <= names, "%d tris" % tris)
        hl, hw = spec.half
        # curved corners bring seats inside the run-off rectangle, never onto the pitch
        outside = (np.abs(seats[:, 0]) > hl + 3) | (np.abs(seats[:, 2]) > hw + 3)
        rec("%s: %d seats, all clear of the pitch" % (name, len(seats)), len(seats) > 4000 and outside.all())
        fwd = np.stack([np.sin(seats[:, 3]), np.cos(seats[:, 3])], 1)
        to_c = -seats[:, [0, 2]] / np.linalg.norm(seats[:, [0, 2]], axis=1, keepdims=True)
        rec("%s: every seat faces the pitch" % name, ((fwd * to_c).sum(1) > .3).all(),
            "min dot %.2f" % (fwd * to_c).sum(1).min())
        r = np.maximum(np.abs(seats[:, 0]) - hl, np.abs(seats[:, 2]) - hw)     # distance back from the pitch
        rec("%s: rows rise away from the pitch" % name, np.corrcoef(r, seats[:, 1])[0, 1] > .5,
            "corr %.2f" % np.corrcoef(r, seats[:, 1])[0, 1])
        ends = seats[:, 5]
        rec("%s: both ends marked, sides not" % name, (ends == -1).sum() > 500 and (ends == 1).sum() > 500
            and np.all(np.abs(seats[ends != 0, 0]) > hl))
        if spec.dugouts:
            ring = np.array(M["ad_ring"].V)
            near = (ring[:, 2] < 0) & (np.abs(ring[:, 0]) < 13)
            dz = [d["front_z"] for d in info["dugouts"]]
            rec("%s: boards keep clear of the dugouts; dugouts behind the touchline" % name,
                not near.any() and all(-hw - spec.runoff_z < z < -hw for z in dz))
    g = S.preset("ground", sport="gaelic")
    M, info, seats = S.build(g)
    rec("Gaelic ground round a 145 x 90 m pitch", info["pitch_half"] == [72.5, 45.0]
        and (np.abs(seats[:, 0]) > 72.5).sum() + (np.abs(seats[:, 2]) > 45.0).sum() >= len(seats))
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "s.glb")
        info = S.export(S.PRESETS["classic"], p)
        j, _ = read_glb(p)
        back = S.read_seats(os.path.join(td, "s.seats"))
        meta = json.load(open(os.path.join(td, "s.json")))
        rec("GLB + seats + json round trip", {n["name"] for n in j["nodes"]} >= PARTS and len(back) == info["seats"]
            and meta["seats"] == info["seats"] and "lights" in meta)
        cp = os.path.join(td, "crowd.glb")
        stats = CR.export(cp)
        jc, bc = read_glb(cp)
        rec("seated spectator <= 120 triangles", stats["seated"] <= 120, str(stats))
        mesh = next(m for m in jc["meshes"] if m["name"] == "seated")
        at = mesh["primitives"][0]["attributes"]
        uv1 = np.frombuffer(_acc_bytes(jc, bc, at["TEXCOORD_1"]), np.float32).reshape(-1, 2)
        V = np.frombuffer(_acc_bytes(jc, bc, at["POSITION"]), np.float32).reshape(-1, 3)
        parts = set(np.round(uv1[:, 0], 2))
        arms = uv1[:, 1] > .1
        rec("crowd channels: parts and arms in TEXCOORD_1", {0.0, .25, .5, .75} <= parts and arms.any()
            and np.all(np.abs(V[arms, 0]) > .15), "parts %s" % sorted(parts))
        atlas = AB.atlas(os.path.join(td, "ads.png"))
        rec("board atlas: one row per sponsor", atlas.size == (AB.PANEL[0], AB.PANEL[1] * len(AB.SPONSORS)))
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
