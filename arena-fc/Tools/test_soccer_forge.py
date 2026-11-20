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
        check("71 soccer clips", len(SM.ALL_CLIPS) == 71, str(len(SM.ALL_CLIPS)))
        check("82 action aliases", len(SM.ACTION_ALIASES) == 82, str(len(SM.ACTION_ALIASES)))
        core_actions = ["idle", "run", "kick", "tackle", "slide", "dive", "catch", "foul", "celebrate"]
        check("match-engine actions all aliased",
              all(a in SM.ACTION_ALIASES for a in core_actions),
              str([a for a in core_actions if a not in SM.ACTION_ALIASES]))
        check("loop clips are looping", SM.LOOP_CLIPS <= set(SM.ALL_CLIPS))
        # Sample the authored clips, not just their registration: this catches
        # a regression to the generic arms-up run cycle or prone slide pose.
        def sampled(name, count=33):
            motion = SM.LIB[name]
            return [motion.sample(i / (count - 1))[0] for i in range(count)]

        run_poses = [pose for name in ("soccer_jog", "soccer_run", "soccer_sprint")
                     for pose in sampled(name)]
        arm_swing = max(abs(pose.get(side, (0,))[0])
                        for pose in run_poses for side in ("arm_L", "arm_R"))
        elbow_bend = max(abs(pose.get(side, 0))
                         for pose in run_poses for side in ("elbow_L", "elbow_R"))
        arm_out = max(pose.get(side, (0, 0, 0))[1]
                      for pose in run_poses for side in ("arm_L", "arm_R"))
        check("running arms stay compact", arm_swing <= 34, "max swing %.1f deg" % arm_swing)
        check("running arms stay lowered", arm_out <= -50, "max out angle %.1f deg" % arm_out)
        check("running elbows stay relaxed", elbow_bend <= 66, "max bend %.1f deg" % elbow_bend)

        slide = SM.LIB["soccer_slide_tackle"].sample(0.5)[0]
        hips = slide.get("hips", (0, 0, 0))
        neck = slide.get("neck", (0, 0, 0))
        lead = slide.get("leg_L", (0, 0, 0))
        trail = slide.get("leg_R", (0, 0, 0))
        check("slide keeps the head lifted", neck[0] >= 0, "neck pitch %.1f" % neck[0])
        check("slide leads with the extended foot", lead[0] > trail[0]
              and slide.get("knee_L", 0) < slide.get("knee_R", 0),
              "hips=%s lead=%s trail=%s" % (hips, lead, trail))
        check("slide rolls onto the side instead of diving head-first", hips[2] >= 45
              and neck[0] >= 0, "hips=%s neck=%s" % (hips, neck))
        check("slide arms do not reach ahead of the head",
              max(abs(slide.get("arm_L", (0,))[0]), abs(slide.get("arm_R", (0,))[0])) < 60,
              "arms=%s/%s" % (slide.get("arm_L"), slide.get("arm_R")))
        check("slide stays out of a prone face-down pose", slide.get("flat", 1.0) > 0.9)
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
        check("GLB carries 71 soccer clips", len(anims) == 71, str(len(anims)))
        check("every clip animates every bone",
              all(len(a["channels"]) >= 18 for a in j["animations"]),
              str(min(len(a["channels"]) for a in j["animations"])))
        check("GLB has 6 flat kit materials",
              [m.get("name") for m in j.get("materials", [])] == ["skin", "jersey", "shorts", "socks", "boots", "hair"],
              str([m.get("name") for m in j.get("materials", [])]))
        check("GLB mesh has 6 primitives (one per layer)",
              len(j["meshes"][0]["primitives"]) == 6)
        prims = j["meshes"][0]["primitives"]
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
        glb_tris = sum(a["count"] for a in pos_accs) // 3
        check("GLB carries the full tri budget", 14000 <= glb_tris <= 18000, str(glb_tris))
        jersey_acc = pos_accs[1]
        check("jersey layer sits on the torso",
              jersey_acc["min"][1] > 0.5 and jersey_acc["max"][1] < 1.65,
              "%s..%s" % (jersey_acc["min"][1], jersey_acc["max"][1]))
        boots_acc = pos_accs[4]
        check("boots layer sits at the feet", boots_acc["max"][1] < 0.3, str(boots_acc["max"][1]))
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
                  all(abs(sum(x * x for x in clips["soccer_run"]["bones"]["Hips"]["r"][:4]) - 1) < 0.01
                      for _ in [0]))
            check("baked clips carry fps/frames",
                  clips["soccer_run"]["fps"] == 30.0 and clips["soccer_run"]["frames"] == 31)
            check("baked clips carry Hips translation",
                  "t" in clips["soccer_run"]["bones"]["Hips"])
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
        check("manifest material order matches GLB",
              man["materials"] == ["skin", "jersey", "shorts", "socks", "boots", "hair"])
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
    check("one-shots fit the match action window",
          "clipDur / p.ActionDuration" in soccer_cs and "every one-shot" in soccer_cs)
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

    print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
