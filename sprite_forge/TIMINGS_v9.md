# Sprite Forge Studio v9 - timings

Measured on 29 Oct 2026 on the build box: 8 CPU cores, no GPU, Linux, Python 3.12 venv. Every run has an **empty
cache** and a fresh output folder (`tools/bench_v9.py`, raw numbers in `previews_v9/bench_v9.json`; each single
option is the faster of 2 runs). The character is the built-in **mannequin** (no real person), preset `fighter14`
(14 moves, 96 frames), HD-ish cells `--frame 384x512 --figure-h 340`, no FBX.

Base = no faces, no QA, no GLB. Each `+` row adds ONE v9 option to that base. Differences under ~0.3 s are noise.

| scenario | time | cost of the option |
|---|---|---|
| base: mannequin fighter14 (faces off, QA off) | 2.3 s |  |
| + expressions per move + faces.png | 2.3 s | +0.0 s |
| + faces.png only | 2.3 s | +0.0 s |
| + talk line (mouth shapes) | 2.3 s | -0.0 s |
| + colour set + hoops overlay | 2.6 s | +0.3 s |
| + variant seed 5 (as the character) | 2.5 s | +0.2 s |
| + 8 variants sheet | 2.5 s | +0.2 s |
| + FX passes (outline, cel, light) | 3.4 s | +1.1 s |
| + FX pixel pass | 2.2 s | -0.1 s |
| + normal + emissive maps | 7.5 s | +5.2 s |
| + frame data (hit/hurt boxes) | 2.8 s | +0.5 s |
| + foot locking (IK) | 2.5 s | +0.2 s |
| + blend idle>walk:3 | 2.5 s | +0.2 s |
| + QA check | 2.5 s | +0.2 s |
| 3D: + GLB (base for LODs / physics) | 2.4 s |  |
| 3D: + GLB + 2 LODs + baked model | 2.7 s | +0.2 s vs GLB build |
| 3D: + GLB, cloth/hair physics off | 2.4 s | -0.0 s vs GLB build |
| ALL v9 options together (+ GLB, LODs, QA) | 11.6 s |  |
| NPC preset goblin (npc_creature moves) | 2.4 s |  |
| forge.py recolor (palette swap of a build) | 8.3 s |  |
| forge.py variants --npc goblin -n 12 | 0.4 s |  |
| forge.py atlas (3 characters) | 5.3 s |  |
| forge.py qa (fighter14 build) | 0.5 s |  |
| forge.py framedata (fighter14 build) | 0.7 s |  |

## What this means
* Faces, talk, colours, variants, foot locking, blending, frame data and QA each add **0-0.5 s** to a 14-move build.
* **Normal + emissive maps are the most expensive v9 option (about +5 s)**: a normal map is worked out for every frame.
* The FX passes (outline / cel / lighting) add about 1 s.
* LODs + baked model add about 0.2 s to a GLB build. Turning cloth/hair physics off saves almost nothing on this
  character (only the ponytail chain).
* Everything at once (faces, talk, colour set + hoops, 8 variants, FX, maps, frame data, foot lock, blend, GLB, 2 LODs, QA):
  **11.6 s**.
* `forge.py recolor` on a finished build re-tints every PNG in it. On the everything-build (atlas, maps, variants,
  talk strip) that took 8.3 s. On a plain 14-move build (96 frames) it took 3.8 s.

## v9 vs v8 (the same v8 benchmark scenarios, `tools/bench_v8.py`, run on both trees on this box)
Raw numbers: `previews_v8/bench_v8.json` (v8) and `previews_v9/bench_v8_scenarios_on_v9.json` (v9).

| scenario | v8 first | v9 first | v8 rebuild | v9 rebuild |
|---|---|---|---|---|
| spec fighter14 + SNES console | 1.5 s | 2.8 s | 0.2 s | 0.2 s |
| photo fighter14 | 2.0 s | 2.1 s | 0.2 s | 0.2 s |
| library rig fighter14 (3D render) | 1.4 s | 1.4 s | 0.2 s | 0.2 s |
| mannequin gaelic36 + GLB + FBX | 3.5 s | 4.7 s | 0.3 s | 0.3 s |
| video -> sprites (2 clips) | 4.6 s | 4.4 s | 1.0 s | 0.9 s |
| UI quick preview (fighter14 draft) | 0.3 s | 1.5 s | - | - |

Why some first builds are slower: v9 turns on **per-move faces, faces.png and the QA check by default**. On
`spec fighter14 + SNES` they cost about 1.5 s. With `--expressions off --no-faces-sheet --no-qa` the same build took
1.5 s, the same as v8. Cached rebuilds are unchanged (about 0.2-0.3 s). Library-rig, photo and video builds take
about the same time as in v8.

**The UI quick preview (draft) went from 0.3 s to 1.5 s.** Almost all of that is the faces.png HUD sheet, which is
on by default. The same draft build took 0.34 s with `--no-faces-sheet` (or faces.png unticked in Style > Faces) and
0.28 s with faces and QA off as well. Draft builds still make faces.png because the Style > Faces preview shows it.

## Tests (same box)
| suite | result | time |
|---|---|---|
| `tools/test_v9.py` (46 tests incl. Godot 4.3 import + Unity stub compile) | 46/46 | 27 s |
| `tools/test_v8.py` (with `SFS_TEST_CUTOUT` set, so the 12 photo tests run) | 20/20 | 137 s |
| `tools/test_v7.py` | 50/50 | 13 s |

## Photo character (Mike test, kept out of the release; times only)
| step | time |
|---|---|
| v3 gold build (egypt_gold colours + expressions + talk + turn 90, fighter14 HD) | 38.0 s |
| v3 variant 8 build | 38.9 s |
| v2 build of the same character (before v9) | 47.7 s |
| whole v3 command script (2 builds + 2 Egyptian Fighter exports) | 1 min 31 s |
| recolour of the photo pixels (estimated regions) | 0.77 s |
| talk strip on the photo face | ~3.4 s |
