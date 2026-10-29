# Sprite Forge Studio v9 - results

Built and tested on 29 Oct 2026 (Europe/London, UTC+0) on the Linux build box (8 cores, no GPU). The scripts are
pip-only and the same on Windows (`build_release.bat`) and Linux (`build_release.sh`). Everything runs through
`forge.py` and the Studio UI.

## Tests
| suite | result | notes |
|---|---|---|
| `tools/test_v9.py` | **46/46 PASS** (27 s) | full table: `previews_v9/tests/RESULTS_v9_tests.md` |
| - Godot plugin | PASS | Godot 4.3 headless: import build -> SpriteFrames (all moves) + scene |
| - Unity package | PASS | compiles against **stub** UnityEngine / UnityEditor APIs (0 warnings, 0 errors), not run in Unity |
| `tools/test_v8.py` | **20/20 PASS** (137 s) | the 12 photo tests need `SFS_TEST_CUTOUT`; without it, 8 tests run |
| `tools/test_v7.py` | **50/50 PASS** (13 s) | |

The v9 tests cover:
* expressions and the per-move map, talk mouth shapes, and photo expressions (warps of a **drawn** test face only);
* recolour sets / regions / overlays / palette swap, and photo-region regressions on a drawn doll;
* seeded variants and photo variants keeping the hair;
* foot-lock IK (walk slide 7.26 -> 0.28 cm in the unit test, 14.0 -> 0.0 cm in a build);
* the fx / maps / blend passes and the physics chains;
* the NPC pack (17 characters), frame data, LODs (6236 -> 3124 -> 1837 triangles, baked model has 1 material) and QA;
* a full mannequin build with every v9 option, the atlas packer, the batch queue, the CLI commands, and the Godot
  and Unity checks.

## Feature checklist
| feature | where | status |
|---|---|---|
| Facial expressions + mouth shapes per move (7 faces, 8 mouths, blink, talk strip) | Style > Faces, `--expressions/--expr-map/--talk` | done; 3D exact, photo **estimated** |
| Colour / texture swaps (20 sets, 8 regions, 8 overlays + own texture, folder palette swap) | Style > Colours, `--recolor/--overlay/--regions`, `forge.py recolor` | done; photo regions **estimated** |
| Procedural seeded variants (sheet + specs, `--vary`) | Style > Variants, `--variants/--variant`, `forge.py variants` | done |
| Foot locking / 2-bone IK | Extras, `--footlock` | done (sprites) |
| Hit / hurt box frame data | Extras, `--framedata`, `forge.py framedata` | done (**estimated**) |
| Outline / cel / pixel / lighting passes | Extras, `--fx` | done |
| Normal + emissive maps | Extras, `--maps` | done (**estimated** normals) |
| Animation blending | Extras, `--blend` | done |
| Multi-character atlas | Tools, `forge.py atlas` | done (MaxRects, ~83% fill) |
| Batch queue | Tools, `forge.py batch` | done |
| Sprite QA | default on, `forge.py qa` | done |
| Unity + Godot plugins | `plugins/` | Godot tested on 4.3; Unity stub compile only |
| Baking + LODs | `--lods N` | done |
| Cloth / hair physics | default on for 3D characters, `--no-physics` | done |
| NPC preset pack (17 characters, 7 move presets) | `forge.py npc`, `--npc` | done |

## Evidence (all mannequin / fictional NPCs; no real-person images)
* Studio screenshots (Xvfb): `gui_v9_1_style_faces.png`, `gui_v9_2_style_colours.png`, `gui_v9_3_style_variants.png`,
  `gui_v9_4_extras.png`, `gui_v9_5_build_npc.png`.
* Outputs: `out_v9_faces_sheet.png`, `out_v9_colour_sets.png`, `out_v9_variants_sheet.png`, `out_v9_fx_passes.png`,
  `out_v9_maps2.png`, `out_v9_framedata_preview.png`, `out_v9_atlas_pack.png`, `out_v9_npc_pack.png`,
  `out_v9_godot_plugin.png`.
* Video: `videos/06_v9_faces_colours_variants.mp4` (61 s Xvfb screen recording of the Studio).
* Timings: `TIMINGS_v9.md`, `bench_v9.json` and `bench_v8_scenarios_on_v9.json`.

## Real-photo test (Mike / Egyptian Fighter), kept OUT of the release
Everything is in `/workspace/mike/v3/` and was made only with forge.py from the user's own photo. No new images
of the person were generated.
* There were two builds. The **gold** build used the egypt_gold set, per-move expressions and a talk line, turned
  side-on (`--turn 90`). The **variant 8** build is a seeded clothes-colour variant. Each took about 38 s, and both
  scored **QA 100/100**.
* In-game test: Egyptian Fighter `--demo 7` under Xvfb played all 14 moves, giving 388 frames for each build with
  0 load failures.
* Outputs: the captioned video `mike_v3_faces_colours_variant_ingame.mp4` (84.7 s) and the drop-in
  `mike_the_postman_timon_v3_dropin.zip` (19.5 MB).
* The Mike test found and fixed four bugs, each now covered by a regression test that uses a drawn doll:
  * Photo regions were wrong: shading was taken as trim, pocket hands as accessory, jeans as socks and the collar as
    hair.
  * Photo variants re-tinted a bald scalp as hair.
  * `forge.py variants --cutout` crashed on a dict `landmarks.json`.
  * After a light-blue recolour, the rig dropped a forearm.

## Honest limits
* **Photo expressions are estimated** procedural warps and overlays of the photo's own face. They are subtle on a
  ~40 px in-game face, very subtle on side-on (turned) views, where the profile is itself estimated, and absent on
  back views.
* **Photo regions are estimated**, and small patches such as a backpack strap can be missed. Use `regions.png` +
  `--regions` to fix them.
* **Photo variants** change only the clothes colours and the build scale. The face, skin and hair are kept.
* Every move on a photo character is a procedural puppet pose.
* Foot locking applies to the sprites only; the GLB clips are not re-solved. On photo builds, blending is a crossfade.
* Normals are estimated from 2D. Emissive maps only pick up the glow colours set in the spec.
* Frame data is estimated, and the Egyptian Fighter game ignores it. The game does not use the talk strip either.
* Talk mouth shapes come from letters, not audio.
* LODs use lower segment counts, not real decimation. The baked texture is a flat palette.
* The Unity package has only been compiled against stubs and never run in Unity. Godot was tested on 4.3 only.
* The NPC `sit` motion sits on an invisible stool.
* QA flags real clipping. For example, the sample `rua_keeper` special1 frame 4 touches the top of the cell.
* v9 turns on faces, faces.png and QA by default. That makes the UI quick preview 1.5 s instead of v8's 0.3 s, and
  `--no-faces-sheet` brings it back to 0.3 s.
* `previews_v2`-`previews_v4` are left out of the v9 zip to stay under 25 MB. They are in the v8 zip.
