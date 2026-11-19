#!/usr/bin/env python3
"""Portable checks for the Sprite Forge realistic soccer player (no Godot/.NET needed).

  python3 Tools/test_soccer_forge.py

Covers: the soccer motion library (needs sprite_forge on PYTHONPATH), the
generated GLB (MakeHuman 52-joint skeleton, 71 clips, three identities
v0/v2/v6 on one skin, baked skin/eye/hair atlases and flat per-club kit
slots), the browser rig JSON (ProceduralRig3D schema + variant_sets), the
manifest (action aliases, loop flags) and the C#/GDScript wiring.  Sections
that need numpy/sforge SKIP cleanly when they are unavailable; the file
checks always run.
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

# MakeHuman 52-joint order, parents first (skins[0].joints of the template).
MH_JOINTS = ["pelvis", "spine_01", "thigh_l", "thigh_r", "spine_02", "calf_l", "calf_r", "spine_03",
             "foot_l", "foot_r", "clavicle_l", "clavicle_r", "neck_01", "ball_l", "ball_r",
             "upperarm_l", "upperarm_r", "head", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r",
             "index_01_l", "middle_01_l", "pinky_01_l", "ring_01_l", "thumb_01_l",
             "index_01_r", "middle_01_r", "pinky_01_r", "ring_01_r", "thumb_01_r",
             "index_02_l", "middle_02_l", "pinky_02_l", "ring_02_l", "thumb_02_l",
             "index_02_r", "middle_02_r", "pinky_02_r", "ring_02_r", "thumb_02_r",
             "index_03_l", "middle_03_l", "pinky_03_l", "ring_03_l", "thumb_03_l",
             "index_03_r", "middle_03_r", "pinky_03_r", "ring_03_r", "thumb_03_r"]


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
        check("71 soccer clips", len(SM.ALL_CLIPS) == 71, str(len(SM.ALL_CLIPS)))
        check("82 action aliases", len(SM.ACTION_ALIASES) == 82, str(len(SM.ACTION_ALIASES)))
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
        check("GLB skeleton is the 52 MakeHuman joints (parents first)", joints == MH_JOINTS, str(joints))
        anims = [a["name"] for a in j.get("animations", [])]
        check("GLB carries 71 soccer clips", len(anims) == 71, str(len(anims)))
        check("every clip animates every joint (+pelvis translation)",
              all(len(a["channels"]) == 53 for a in j["animations"]),
              str(sorted(set(len(a["channels"]) for a in j["animations"]))))
        mesh_nodes = [n for n in j["nodes"] if "mesh" in n]
        prefixes = sorted({n["name"].split("_", 1)[0] for n in mesh_nodes})
        check("GLB carries the three identities (v0/v2/v6)", prefixes == ["v0", "v2", "v6"], str(prefixes))
        for v in ("v0", "v2", "v6"):
            have = {n["name"][len(v) + 1:] for n in mesh_nodes if n["name"].startswith(v + "_")}
            check("%s has body, kit and face parts" % v,
                  {"body", "jersey", "shorts", "socks", "boots", "eyes"} <= have, str(sorted(have)))
        mat_names = [m.get("name") for m in j.get("materials", [])]
        check("GLB has the flat kit slots + natural atlases",
              {"jersey", "shorts", "socks", "boots", "skin_v0", "skin_v2", "skin_v6"} <= set(mat_names),
              str(mat_names))
        shell_prefixes = ("hair_", "eyelashes_", "eyebrows_", "beard_", "facial_")
        check("hair/lash/brow shells keep alpha MASK + doubleSided",
              all(m.get("alphaMode") == "MASK" and m.get("doubleSided")
                  for m in j["materials"] if m.get("name", "").startswith(shell_prefixes)),
              str([m.get("name") for m in j["materials"]
                   if m.get("name", "").startswith(shell_prefixes) and m.get("alphaMode") != "MASK"]))
        prims = [j["meshes"][n["mesh"]]["primitives"][0] for n in mesh_nodes]
        prim = prims[0]
        pos_accs = [j["accessors"][p["attributes"]["POSITION"]] for p in prims]
        gmin = [min(a["min"][k] for a in pos_accs) for k in range(3)]
        gmax = [max(a["max"][k] for a in pos_accs) for k in range(3)]
        check("mesh stands on the ground (min y ~ 0)", abs(gmin[1]) < 0.01, str(gmin))
        check("mesh height ~1.77 m", 1.6 < gmax[1] < 1.95, str(gmax))
        # Regression: fmat was once fed per-vertex layers, truncating the GLB
        # to a half-body mesh with scrambled materials.  Guard the full body,
        # the tri budget, and regional kit layers.
        check("GLB mesh is full-body (x spans both sides)",
              gmin[0] < -0.2 and gmax[0] > 0.2, "%s..%s" % (gmin[0], gmax[0]))
        glb_tris = sum(j["accessors"][p["indices"]]["count"] for p in prims) // 3
        check("GLB carries the full realistic tri budget (~108k)", 100000 <= glb_tris <= 115000, str(glb_tris))
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
        check("rig JSON has the ProceduralRig3D schema",
              all(k in d for k in ("bones", "pos", "nrm", "uv", "bi", "w", "mats", "idx")))
        check("rig JSON skeleton is the 52 MakeHuman joints",
              [b["n"] for b in d["bones"]] == MH_JOINTS)
        check("rig JSON parents come first",
              all(int(b["p"]) < i for i, b in enumerate(d["bones"])))
        verts = len(d["pos"]) // 3
        check("rig JSON vertex counts agree",
              len(d["nrm"]) == verts * 3 and len(d["uv"]) == verts * 2
              and len(d["bi"]) == verts * 4 and len(d["w"]) == verts * 4)
        check("rig JSON bone indices in range", max(d["bi"]) < len(d["bones"]) and min(d["bi"]) >= 0)
        ws = [sum(d["w"][i * 4:(i + 1) * 4]) for i in range(min(verts, 200))]
        check("rig JSON weights sum to 1", all(abs(s - 1) < 1e-3 for s in ws))
        check("rig JSON material slots are Arena slots + eyes",
              set(d["mats"]) <= {0, 1, 2, 3, 6, 8, 9}, str(d["mats"]))
        tris = sum(len(t) for t in d["idx"]) // 3
        check("rig JSON base identity tri budget (~36k)", 30000 <= tris <= 45000, str(tris))
        # The realistic rig ships two further identities that share the skeleton.
        check("rig JSON carries the v2/v6 variant sets",
              set(d.get("variant_sets", {})) == {"v2", "v6"}, str(sorted(d.get("variant_sets", {}))))
        for v, vs in d.get("variant_sets", {}).items():
            vtris = sum(len(t) for t in vs["idx"]) // 3
            check("%s variant set is self-consistent" % v,
                  len(vs["pos"]) == len(vs["nrm"]) == (len(vs["uv"]) * 3 // 2)
                  and max(vs["bi"]) < 52 and min(vs["bi"]) >= 0 and 30000 <= vtris <= 45000,
                  "tris=%d bi_max=%d" % (vtris, max(vs["bi"])))
        # Baked clips: the Web template has no glTF module, so the browser
        # plays these keyframes instead of the GLB.
        check("rig JSON bakes the clip keyframes", "clips" in d)
        if "clips" in d:
            clips = d["clips"]
            check("baked clips cover the manifest", set(clips) == set(man["clips"]) if "man" in dir() else len(clips) == 71)
            loco = ("soccer_idle", "soccer_walk", "soccer_jog", "soccer_run",
                    "soccer_sprint", "soccer_dribble", "soccer_run_ball")
            check("baked locomotion clips loop",
                  all(clips[c]["loop"] for c in loco if c in clips))
            check("baked one-shots do not loop",
                  not clips["soccer_kick_place"]["loop"] and not clips["soccer_celebrate"]["loop"])
            check("baked clip quaternions are normalized",
                  all(abs(sum(x * x for x in clips["soccer_run"]["bones"]["pelvis"]["r"][:4]) - 1) < 0.01
                      for _ in [0]))
            check("baked clips carry fps/frames",
                  clips["soccer_run"]["fps"] == 30.0 and clips["soccer_run"]["frames"] == 31)
            check("baked clips carry pelvis translation",
                  "t" in clips["soccer_run"]["bones"]["pelvis"])
            # Phase 0.1: every baked clip carries its event frames.
            check("baked clips carry event frames",
                  all("events" in c and "ball_contact_frac" in c["events"] for c in clips.values()))
            check("ball clips carry a contact frame",
                  all(clips[c]["events"]["ball_contact"] >= 0 for c in
                      ("soccer_short_pass", "soccer_shoot", "soccer_volley",
                       "soccer_header", "soccer_chest_control", "soccer_trap")))
            check("locomotion clips carry footsteps",
                  all(clips[c]["events"]["footsteps"] for c in
                      ("soccer_walk", "soccer_run", "soccer_sprint")))

    section("Manifest")
    man_path = os.path.join(ROOT, "Data", "soccer_player_manifest.json")
    check("manifest exists", os.path.isfile(man_path))
    if os.path.isfile(man_path):
        man = json.load(open(man_path))
        check("manifest lists 71 clips", len(man["clips"]) == 71)
        check("manifest aliases cover match actions",
              all(a in man["action_aliases"] for a in
                  ("idle", "run", "kick", "tackle", "slide", "dive", "catch", "foul", "celebrate")))
        man_mats = set(man.get("materials", []))
        check("manifest materials cover the GLB material order",
              {"jersey", "shorts", "socks", "boots", "skin_v0", "skin_v2", "skin_v6"} <= man_mats,
              str(sorted(man_mats)))
        check("manifest declares the realistic look + identities",
              man.get("look") == "realistic" and man.get("variants") == ["v0", "v2", "v6"]
              and man.get("skeleton") == "makehuman-52",
              str((man.get("look"), man.get("variants"), man.get("skeleton"))))
        check("manifest ships 52 MakeHuman bones", man.get("bones") == MH_JOINTS)
        check("manifest clips carry event frames",
              all("events" in c and "ball_contact_frac" in c["events"] for c in man["clips"]))
        check("manifest aliases include Phase 0 actions",
              all(a in man["action_aliases"] for a in
                  ("volley", "header", "chest_control", "trap", "parry", "cut")))

    section("Runtime wiring (static checks)")
    soccer_cs = open(os.path.join(ROOT, "Scripts", "Godot", "SoccerClipRig.cs")).read()
    factory = open(os.path.join(ROOT, "Scripts", "Godot", "RigFactory.cs")).read()
    world = open(os.path.join(ROOT, "Scripts", "Godot", "World3D.cs")).read()
    boot = open(os.path.join(ROOT, "Web", "BrowserBoot.gd")).read()
    match_cs = open(os.path.join(ROOT, "Scripts", "Core", "Match.cs")).read()
    check("C# rig drives the GLB animation player",
          "AnimationPlayer" in soccer_cs and "GltfDocument" in soccer_cs)
    check("C# loader plays clips from PlayerState",
          "SelectClip" in soccer_cs)
    # FIFA-style locomotion: cadence matched to ground speed per clip
    # (foot speed ~= ground speed), blend-space clip selection, phase sync,
    # foot-planting IK, look-at/reach and archetype biases (Phase 1).
    check("locomotion cadence matches ground speed",
          "NaturalRate" in soccer_cs and "speed / (nat" in soccer_cs)
    check("blend-space clip selection", "SelectClip" in soccer_cs and "SelectDirectionalClip" in soccer_cs)
    check("phase sync on clip switch", "_phase" in soccer_cs and "startPhase" in soccer_cs)
    check("foot-planting IK", "SolveTwoBone" in soccer_cs and "ShortestArc" in soccer_cs)
    check("look-at and reach", "UpdateLookAt" in soccer_cs and "UpdateReach" in soccer_cs)
    check("archetype biases", "SetArchetype" in soccer_cs and "Archetype.Explosive" in soccer_cs)
    check("body lean/roll from acceleration", "UpdateLean" in soccer_cs)
    check("RigFactory attaches the soccer player", "AttachSoccer" in factory)
    check("RigAnimator routes to clips", "rig.Soccer.Update" in world)
    check("browser loads the sculpted rig", "soccer_rig.json" in boot)
    # Browser clip playback mirrors the desktop cadence matching.
    check("browser plays baked clips", "animate_clip" in boot and "clips_data" in boot)
    check("browser cadence matches ground speed",
          "CLIP_NATURAL" in boot and "speed / nat" in boot)
    check("browser locomotion bands have hysteresis",
          "clip_select_locomotion" in boot)
    check("browser falls back to procedural gait", "animate_rig(r" in boot)
    # Phase 0: event-synced ball release/capture, first-touch selection,
    # speed-scaled dribble lead, turn-rate clip selection and keeper parry.
    check("C# syncs ball release to the contact frame",
          "FirePending" in match_cs and "ActionContactAt" in match_cs)
    check("C# selects first-touch by ball height/speed",
          '"chest_control"' in match_cs and '"trap"' in match_cs and '"header"' in match_cs)
    check("C# scales dribble lead by speed",
          "Lerp(0.15f, 0.60f" in match_cs)
    check("C# parries hot shots",
          '"parry"' in match_cs and "spd > 18f" in match_cs)
    check("desktop selects turns by turn rate",
          '"soccer_turn"' in soccer_cs and "turnRate" in soccer_cs)
    check("desktop directional clips", '"soccer_strafe_l"' in soccer_cs and '"soccer_backpedal"' in soccer_cs)
    check("browser syncs ball release to the contact frame",
          "fire_pending" in boot and "pending" in boot)
    check("browser selects first-touch by ball height/speed",
          '"chest_control"' in boot and '"trap"' in boot and '"header"' in boot)
    check("browser scales dribble lead by speed",
          "lerpf(0.15, 0.60" in boot)
    check("browser parries hot shots",
          '"parry"' in boot and "spd > 18.0" in boot)
    check("browser selects turns by turn rate",
          '"soccer_turn"' in boot and "turn_rate" in boot)
    # Phase 1: blend space, directional clips, archetypes, foot IK, look/reach.
    check("browser blend-space directional clips",
          '"soccer_strafe_l"' in boot and '"soccer_backpedal"' in boot and '"soccer_jockey"' in boot)
    check("browser archetype biases", "ARCHETYPE_BIAS" in boot and "archetype" in boot)
    check("browser foot-planting IK", "apply_foot_ik" in boot and "solve_two_bone" in boot)
    check("browser look-at and reach", "apply_look_reach" in boot)
    # Phase 2: gameplay depth — first touch, dribble, passing, shooting,
    # defending, keeper AI, off-ball AI, set pieces, presets.
    check("C# first-touch quality", "FirstTouchQuality" in match_cs and "pressure" in match_cs)
    check("C# dribble momentum/burst", "DribbleMomentum" in match_cs and "DribbleBurstCd" in match_cs)
    check("C# pass types", "PassType" in match_cs and "Driven" in match_cs and "Threaded" in match_cs)
    check("C# shot types", "ShotType" in match_cs and "Placement" in match_cs and "Volley" in match_cs)
    check("C# jockey/contain", "JockeyState" in match_cs and "jockey" in match_cs.lower())
    check("C# keeper angle-cutting", "angle" in match_cs.lower() and "rush" in match_cs.lower())
    check("C# off-ball runs", "RunType" in match_cs and "overlap" in match_cs.lower())
    check("C# set-piece routines", "isCorner" in match_cs and "isThrowIn" in match_cs)
    check("C# match presets", "MatchPreset" in match_cs and "Authentic" in match_cs)
    check("browser first-touch quality", "first_touch" in boot and "quality" in boot)
    check("browser pass types", '"threaded"' in boot and '"lofted"' in boot and '"chip"' in boot)
    check("browser shot types", '"placement"' in boot and '"volley"' in boot and '"power"' in boot)
    check("browser jockey", '"jockey"' in boot)
    check("browser keeper punch", '"punch"' in boot)
    # Phase 3: presentation and platform.
    check("C# quality presets", "QualityPreset" in match_cs and "DetectQuality" in open(os.path.join(ROOT, "Scripts", "Godot", "World3D.cs")).read())
    check("C# replay recorder", "ReplayRecorder" in open(os.path.join(ROOT, "Scripts", "Core", "ReplayRecorder.cs")).read())
    check("C# game modes", "GameMode" in open(os.path.join(ROOT, "Scripts", "Godot", "GameApp.cs")).read())
    check("C# match analysis", "MatchAnalysis" in open(os.path.join(ROOT, "Scripts", "Core", "MatchAnalysis.cs")).read())
    check("pitch shader has wear/wet", "wear_amount" in open(os.path.join(ROOT, "Shaders", "pitch.gdshader")).read())
    check("ball shader has spin blur", "spin_blur" in open(os.path.join(ROOT, "Shaders", "ball.gdshader")).read())
    check("net shader has ripple", "ripple" in open(os.path.join(ROOT, "Shaders", "net.gdshader")).read())
    check("audio has crowd ambience", "ambience" in open(os.path.join(ROOT, "Scripts", "Core", "Audio", "ProceduralAudio.gd")).read())
    # Phase 3.9: ML blend weights.
    check("C# blend learner", "BlendLearner" in open(os.path.join(ROOT, "Scripts", "Core", "BlendLearner.cs")).read())
    check("builder exists", os.path.isfile(os.path.join(ROOT, "Tools", "build_soccer_player.py")))
    check("realistic builder exists",
          os.path.isfile(os.path.join(ROOT, "Tools", "build_soccer_realistic.py")))

    print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
