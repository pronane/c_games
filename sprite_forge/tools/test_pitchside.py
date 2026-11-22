#!/usr/bin/env python3
"""Pitch-side people, goals with real nets, corner flags (v11.39, fed back from Arena FC).

    python tools/test_pitchside.py

  1 every pitch-side clip passes its QA (loops close, seated / kneeling / camera / cheer poses hold)
  2 placements round a sforge.stadium ground: subs on the dugout seats at seat height, a manager and an
    assistant per team in front of their dugout, ball kids and photographers outside the pitch and off
    the goal mouth, everyone facing the pitch
  3 the dugout lists its seats (bench positions, seat at chair height)
  4 the camera prop GLB reads back
  5 the goal: posts and bar where the sport's size says, the net behind the line, free mid-panel and
    held on the frame and the ground line, the roof sagging; every sport in GOALS builds
  6 corner flag: pole height, cloth free at the far edge; the export GLB has frame, net, flag_pole, flag_cloth
  7 staff trousers (tailor.staff_garments) cover the legs from the shorts to the shin"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import goalnet as G  # noqa: E402
from sforge import pitchside as PS  # noqa: E402
from sforge import stadium as S  # noqa: E402
from sforge import tailor as T  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402

SRC = os.path.join(HERE, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-64s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    PS.register()
    bad = PS.qa_all()
    rec("pitch-side clips pass QA", not bad, str(bad))
    with tempfile.TemporaryDirectory() as td:
        spec = S.preset("bowl")
        gp = os.path.join(td, "s.glb")
        S.export(spec, gp)
        st = json.load(open(gp[:-4] + ".json"))
    dug = st.get("dugouts", [])
    rec("dugouts list their seats at chair height", dug and all(len(d.get("bench", [])) == d["seats"] and
        abs(d.get("seat_top", 0) - .52) < .01 for d in dug))
    hl, hw = st["pitch_half"]
    sp = PS.placements(st, hl, hw)
    roles = {}
    for s in sp:
        roles.setdefault(s["role"], []).append(s)
    seats = {tuple(np.round(b, 3)) for d in dug for b in d["bench"]}
    subs_ok = all(tuple(np.round(s["pos"], 3)) in seats for s in roles.get("sub", []))
    rec("subs sit on dugout seats", len(roles.get("sub", [])) == 14 and subs_ok)
    mgr = roles.get("manager", [])
    rec("a manager and an assistant per team, in front of the dugout",
        len(mgr) == 2 and len(roles.get("assistant", [])) == 2 and
        all(m["pos"][2] > d["front_z"] for m, d in zip(mgr, dug)))
    out_ok = all(abs(s["pos"][0]) > hl + 1 or abs(s["pos"][2]) > hw + 1 for s in roles["ballkid"] + roles["photographer"])
    mouth = all(abs(s["pos"][2]) > 4.5 for s in roles["photographer"])
    rec("ball kids and photographers outside the pitch, clear of the goal mouth", out_ok and mouth)

    def facing_ok(s):
        fx, fz = math.sin(s["yaw"]), math.cos(s["yaw"])
        return fx * (0 - s["pos"][0]) + fz * (0 - s["pos"][2]) > 0
    rec("everyone faces the pitch", all(facing_ok(s) for s in sp))
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "props.glb")
        PS.props_glb(p)
        j, _ = read_glb(p)
        rec("camera prop GLB", [n["name"] for n in j["nodes"]] == ["camera"])
    g = G.GOALS["soccer"]
    b = G.build("soccer")
    fr, net = b["frame"], b["net"]
    post_z = np.abs(fr["V"][:, 2]).max()
    top = fr["V"][:, 1].max()
    rec("goal frame matches the size", abs(post_z - (g["width"] / 2 + 2 * g["post"])) < .03 and abs(top - (g["height"] + g["post"] * 1.3)) < .05,
        "half width %.2f, top %.2f" % (post_z, top))
    V, U2 = net["V"], net["UV2"]
    rec("net behind the goal line", V[:, 0].min() > -1e-6 and V[:, 0].max() <= g["depth_ground"] + .1)
    bar = (V[:, 0] < 1e-3) & (np.abs(V[:, 1] - g["height"]) < 1e-3)
    ground = V[:, 1] < 1e-3
    rec("net held on the frame and the ground, free mid-panel",
        U2[bar, 0].max() < 1e-6 and U2[ground, 0].max() < 1e-6 and U2[:, 0].max() > .95)
    roof = (U2[:, 1] == 0) & (V[:, 0] > .2) & (V[:, 0] < g["depth_top"] - .1) & (np.abs(V[:, 2]) < .5)
    rec("roof sags", roof.any() and V[roof, 1].min() < g["height"] - .03)
    rec("every sport's goal builds", all(len(G.build(s)["net"]["F"]) > 500 for s in G.GOALS))
    fl = G.corner_flag()
    rec("corner flag: 1.5 m pole, cloth free at the far edge",
        abs(fl["flag_pole"]["V"][:, 1].max() - 1.5) < 1e-6 and fl["flag_cloth"]["UV2"][:, 0].max() == 1.0)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "goal.glb")
        G.export(p)
        j, _ = read_glb(p)
        rec("goal GLB nodes", [n["name"] for n in j["nodes"]] == ["frame", "net", "flag_pole", "flag_cloth"]
            and "TEXCOORD_1" in j["meshes"][1]["primitives"][0]["attributes"])
    bones, jn = T.skeleton_from_glb(SRC)
    parts = T.read_parts(SRC, "v0_")
    tr = T.tailor(parts, bones, garments=T.staff_garments(), joint_names=jn, log=lambda *a: None).get("trousers")
    kit = T.tailor(parts, bones, joint_names=jn, log=lambda *a: None)
    ok = tr is not None and len(tr.F) > 400
    if ok:
        ok = tr.V[:, 1].max() > kit["shorts"].V[:, 1].min() and tr.V[:, 1].min() < kit["socks"].V[:, 1].max()
    rec("staff trousers run from under the shorts down over the socks", ok)
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
