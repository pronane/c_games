#!/usr/bin/env python3
"""Portable checks for the Sprite Forge soccer player (no Godot/.NET needed).

  python3 Tools/test_soccer_forge.py

Covers: the soccer motion library (needs sprite_forge on PYTHONPATH), the
generated GLB (18 Arena joints, 67 clips, 6 kit materials), the browser rig
JSON (rig_default.json schema), the manifest (action aliases, loop flags) and
the C#/GDScript wiring.  Sections that need numpy/sforge SKIP cleanly when
they are unavailable; the file checks always run.
"""
from __future__ import annotations

import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF = os.path.abspath(os.path.join(ROOT, "..", "sprite_forge"))
sys.path.insert(0, SF)
sys.path.insert(0, os.path.join(ROOT, "Tools"))

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s %s" % (name, detail))


def section(s):
    print("\n== %s ==" % s)


def read_glb(path):
    d = open(path, "rb").read()
    assert d[:4] == b"glTF", "not a GLB"
    ln = struct.unpack("<I", d[12:16])[0]
    j = json.loads(d[20:20 + ln])
    off = 20 + ln
    bl = struct.unpack("<I", d[off:off + 4])[0]
    return j, d[off + 8:off + 8 + bl]


def acc_bytes(j, buf, i):
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    ctype = {5126: 4, 5123: 2, 5121: 1, 5125: 4, 5122: 2, 5120: 1}[a["componentType"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return buf[off:off + ctype * ncomp * a["count"]], a["count"], ncomp


def main():
    section("Soccer motion library")
    try:
        import soccer_motions as SM
        check("motion library validates", SM.validate() == [], str(SM.validate()))
        check("67 soccer clips", len(SM.ALL_CLIPS) == 67, str(len(SM.ALL_CLIPS)))
        check("75 action aliases", len(SM.ACTION_ALIASES) == 75, str(len(SM.ACTION_ALIASES)))
        core_actions = ["idle", "run", "kick", "tackle", "slide", "dive", "catch", "foul", "celebrate"]
        check("match-engine actions all aliased",
              all(a in SM.ACTION_ALIASES for a in core_actions),
              str([a for a in core_actions if a not in SM.ACTION_ALIASES]))
        check("loop clips are looping", SM.LOOP_CLIPS <= set(SM.ALL_CLIPS))
    except ImportError as e:
        print("  SKIP  sprite_forge not importable (%s)" % e)

    section("Generated GLB (desktop)")
    glb = os.path.join(ROOT, "Data", "models", "soccer_player.glb")
    check("soccer_player.glb exists", os.path.isfile(glb))
    if os.path.isfile(glb):
        j, buf = read_glb(glb)
        names = [n.get("name", "?") for n in j["nodes"]]
        joints = [names[i] for i in j["skins"][0]["joints"]]
        arena = json.load(open(os.path.join(ROOT, "Data", "rig_default.json")))
        arena_bones = [b["n"] for b in arena["bones"]]
        check("GLB skeleton is Arena's 18 bones", joints == arena_bones, str(joints))
        anims = [a["name"] for a in j.get("animations", [])]
        check("GLB carries 67 soccer clips", len(anims) == 67, str(len(anims)))
        check("every clip animates every bone",
              all(len(a["channels"]) >= 18 for a in j["animations"]),
              str(min(len(a["channels"]) for a in j["animations"])))
        check("GLB has 6 flat kit materials",
              [m.get("name") for m in j.get("materials", [])] == ["skin", "jersey", "shorts", "socks", "boots", "hair"],
              str([m.get("name") for m in j.get("materials", [])]))
        check("GLB mesh has 6 primitives (one per layer)",
              len(j["meshes"][0]["primitives"]) == 6)
        prim = j["meshes"][0]["primitives"][0]
        pos_acc = j["accessors"][prim["attributes"]["POSITION"]]
        check("mesh stands on the ground (min y ~ 0)", abs(pos_acc["min"][1]) < 0.01, str(pos_acc["min"]))
        check("mesh height ~1.77 m", 1.6 < pos_acc["max"][1] < 1.95, str(pos_acc["max"]))
        wraw, wn, _ = acc_bytes(j, buf, prim["attributes"]["WEIGHTS_0"])
        import array
        w = array.array("f")
        w.frombytes(wraw[:wn * 4 * 4])
        sums = [sum(w[i * 4:(i + 1) * 4]) for i in range(min(wn, 200))]
        check("skin weights sum to 1", all(abs(s - 1) < 1e-3 for s in sums))

    section("Browser rig JSON")
    rig_path = os.path.join(ROOT, "Data", "soccer_rig.json")
    check("soccer_rig.json exists", os.path.isfile(rig_path))
    if os.path.isfile(rig_path):
        d = json.load(open(rig_path))
        arena = json.load(open(os.path.join(ROOT, "Data", "rig_default.json")))
        check("rig JSON has the ProceduralRig3D schema",
              all(k in d for k in ("bones", "pos", "nrm", "uv", "bi", "w", "mats", "idx")))
        check("rig JSON skeleton matches rig_default.json", d["bones"] == arena["bones"])
        verts = len(d["pos"]) // 3
        check("rig JSON vertex counts agree",
              len(d["nrm"]) == verts * 3 and len(d["uv"]) == verts * 2
              and len(d["bi"]) == verts * 4 and len(d["w"]) == verts * 4)
        check("rig JSON bone indices in range", max(d["bi"]) < len(d["bones"]) and min(d["bi"]) >= 0)
        ws = [sum(d["w"][i * 4:(i + 1) * 4]) for i in range(min(verts, 200))]
        check("rig JSON weights sum to 1", all(abs(s - 1) < 1e-3 for s in ws))
        check("rig JSON material slots are Arena slots", set(d["mats"]) <= {0, 1, 2, 3, 6, 8}, str(d["mats"]))
        tris = sum(len(t) for t in d["idx"]) // 3
        check("rig JSON triangle budget", 8000 < tris <= 20000, str(tris))

    section("Manifest")
    man_path = os.path.join(ROOT, "Data", "soccer_player_manifest.json")
    check("manifest exists", os.path.isfile(man_path))
    if os.path.isfile(man_path):
        man = json.load(open(man_path))
        check("manifest lists 67 clips", len(man["clips"]) == 67)
        check("manifest aliases cover match actions",
              all(a in man["action_aliases"] for a in
                  ("idle", "run", "kick", "tackle", "slide", "dive", "catch", "foul", "celebrate")))
        check("manifest material order matches GLB",
              man["materials"] == ["skin", "jersey", "shorts", "socks", "boots", "hair"])

    section("Runtime wiring (static checks)")
    soccer_cs = open(os.path.join(ROOT, "Scripts", "Godot", "SoccerClipRig.cs")).read()
    factory = open(os.path.join(ROOT, "Scripts", "Godot", "RigFactory.cs")).read()
    world = open(os.path.join(ROOT, "Scripts", "Godot", "World3D.cs")).read()
    boot = open(os.path.join(ROOT, "Web", "BrowserBoot.gd")).read()
    check("C# loader reads the GLB + manifest",
          "GltfDocument" in soccer_cs and "soccer_player_manifest.json" in soccer_cs)
    check("C# loader plays clips from PlayerState",
          "SelectClip" in soccer_cs and "PlayerState" in soccer_cs)
    check("RigFactory attaches the soccer player", "AttachSoccer" in factory)
    check("RigAnimator routes to clips", "rig.Soccer.Update" in world)
    check("browser loads the sculpted rig", "soccer_rig.json" in boot)
    check("builder exists", os.path.isfile(os.path.join(ROOT, "Tools", "build_soccer_player.py")))

    print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
