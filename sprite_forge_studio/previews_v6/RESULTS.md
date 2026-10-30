# Sprite Forge Studio v6: library test evidence (Linux, pip-only)

## Automated tests: `tools/test_library_v6.py`
| run | result |
|---|---|
| Dev tree with the Blender oracle (`SFS_BPY_PYTHON` = pip bpy, Blender 4.x) | **38 / 38 passed** (`RESULTS_tests.md`, `test_library_v6_log.txt`) |
| Clean extraction of the release zip. `env -i`, restricted PATH, no scipy/opencv, no Blender | **36 / 36 passed** (oracle skipped). See `clean_extraction_restricted_path_tests.txt` |

The tests cover:

* **Packs:**
  * The starter pack verifies.
  * Install is refused without acknowledgement, then works with it, and records provenance.
  * Re-installing identical content is skipped.
  * A tampered file (sha256 mismatch), a path-traversal entry and a non-redistributable asset are each refused.
  * `pack --all`, then install into a second library, gives byte-identical rigs.
* **Licences:**
  * An imported file with no licence warns, and packing it is refused.
  * The "I own the rights" override requires `--by`, and the override is recorded in pack.json.
  * Clips retargeted from a `redistribution=no` source block packing a CC0 rig until `clips-drop`.
* **Import round trip (our GLB writer, our FBX writer, our readers)** for all 5 sample assets:
  * 18 to 27 bones, with every bone mapped;
  * bind error at most 0.001 mm, clip error at most 0.01 mm, all takes present;
  * conventions detected as sforge, unity, mixamo or rigify;
  * a skeleton-only animation asset also works.
* **Blender oracle:** Blender 4 re-exported chibi, lanky and stocky as FBX (leaf bones, embedded textures). Our
  reader finds every bone, with 0.00 mm clip error, the right naming convention and the texture.
* **Retarget between proportions:** six pairs, with leg ratios from 0.34 to 2.91 (lanky 2.0 m to chibi 1.1 m and
  back, mannequin to stocky, the animation-only asset onto chibi and stocky):
  * hip height relative to leg length stays within 2.3% of the source;
  * ground contact stays within 0.8 mm of the scaled source.
* **Builds from library rigs:**
  * fighter14 on lanky with the gold/black kit: 96 frames, 14 FBX takes;
  * platformer on chibi: 71 frames, 10 takes;
  * GBA console on stocky;
  * PS1 console on lanky: decimated to 596 of the 600-triangle budget, all parts present (`library_assets.png`,
    last column);
  * each build used a library clip with speed, trim or loop options.

## Other checks
* **doctor:** READY, with the library row OK (8 assets) on both the dev tree and the clean extraction.
* **Egyptian Fighter copy under Xvfb** (`egyptian_fighter_copy_library_rig.png`):
  * The library_fighter build (sample_lanky, gold_black kit, victory = sample_moves:spin retargeted) was
    exported with `tools/export_ef.py` into a copy of the game, replacing the char_daragh slot.
  * It was played with the game's fake-pad hooks: select, fight, moves, KO and victory.
  * The original game folder was not touched.
* **Headless GUI** (`ui_*.png`):
  * Library tab with thumbnails, clip scrub and asset info;
  * bone-map editor and licence editor;
  * the Install dialog listing every licence, with the acknowledgement tick box gating Install;
  * an added Blender FBX shown as licence "unknown";
  * Export pack refused until a name is given for "I own the rights", then written and verified;
  * Build tab in library mode with the library-clip column, and a finished build;
  * the Help > Library topic;
  * "Use as template" from a clean extraction.
* **Mocap onto a library rig** (`forge.py mocap clip.mp4 --rig sample_lanky`) was checked by hand on the dev box.
  It is not in the automated test, because it needs the MediaPipe Python from `tools/setup_pose.py`.

## Honest limits
* Retargeting transfers bone directions with rest-pose compensation, leg-length scaling of root motion and a
  feet/toes ground fix:
  * There is no IK, foot locking or hand contact, so feet can slide slightly between very different
    proportions. Foot sliding was not measured.
  * The "direction error 0.00 deg" figure is 0 by construction, not independent evidence. The ground-contact
    figure is enforced by the ground fix. Hip height per leg length is the independent check.
* FBX import reads the first animation layer of each take. Blendshapes, constraints, IK targets and non-skin
  deformers are ignored. Textures that are not embedded must sit next to the file.
* Imports are grounded (lowest point at y=0). The skeleton-only asset moved by 29.6 mm and the mannequin by 2 mm.
* All test assets are our own synthetic files, or Blender re-exports of them. No real Mixamo or Unity Asset Store
  downloads were tested, because we don't redistribute third-party files. Real-world files may need bone-map edits.
* Clip speed changes only the 3D take timing. Sprite frame counts come from the move preset.
* Console decimation without fast-simplification uses skin-aware vertex clustering. At about 300 triangles,
  thin parts can show holes.
* Licence records are self-declared. The Studio enforces them but cannot check them.
* The Egyptian Fighter roster is hard-coded, so the test replaced an existing slot, and the display name stays
  that character's.
* Windows was not re-tested for v6. The new code is pure Python/NumPy/Pillow/Tk, the same stack v5 tested under wine.
