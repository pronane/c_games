# Sprite Forge Studio v5 - test evidence

## Test setup
* **Linux:** a fresh unzip of `sprite_forge_studio_v5.zip`, run with `env -i HOME=<empty dir> PATH=<coreutils + sh + python3 only>`.
  ffmpeg, ffprobe, COLMAP, Blender, assimp, gcc, make, curl, wget, git and uv were not visible.
* **Windows:** wine 10.0 (reports Windows 10.0.19043) with the official Windows CPython 3.12.7 (nuget build, no tkinter).
  **This is not a real Windows 10 PC.**

## Results
| What | Linux (clean) | Windows via wine |
|---|---|---|
| setup (`setup.sh` / `setup.bat`) | exit 0, 27 s, nothing cached (`linux_setup_sh.log`) | ran to the end (`wine_setup_bat.log`) |
| doctor | READY (`linux_doctor.txt`, `ui_doctor.png`) | READY (`wine_doctor.txt`): tkinter missing in the nuget Python, mediapipe crashes in wine |
| build_release | exit 0, 122 s (`linux_build_release_sh.log`) | exit 0, 166 s (`wine_build_release_bat.log`) |
| spec build + built-in FBX | PASS | PASS |
| SNES export | PASS | PASS |
| video, 4 clips (imageio-ffmpeg) | OK, decode 690-1100 frames/s | OK |
| scan via pycolmap | 72/72 cameras, 0.45 px | 72/72 cameras, 0.45 px |
| mocap (venv_pose, private Python 3.12) | walk 108/110 frames, 2.4 deg bone error | not possible: wine cannot run MediaPipe |
| consoles nes, gb, genesis, ps1, n64, saturn, ps2gc | PASS (`console_builds_verify.txt`) | - |
| photo + `--video walk=` + GBA | PASS (`photo_build_with_video_walk.png`) | - |
| GUI: spec build with FBX, Blender not installed | OK (`ui_spec_build_fbx_clean.png`) | - (no tkinter) |
| C/raylib example | `make raylib && make` OK with gcc present; skipped when gcc is hidden | skipped (no gcc) |

## Scan accuracy: pycolmap vs v4 COLMAP CLI (`scan_eval_pycolmap.json`)
* Mean surface error: raw mesh 1.31 cm (v4: 1.33); ps2gc LOD 1.28 cm; ps1 LOD (600 tris, fast-simplification) 1.30 cm (v4: 1.40).
* Camera position error: 5.5 mm mean / 10.0 mm max (v4: 4.5 / 8.1).

## Built-in FBX writer
* Speed: 0.29 s for the 14-move character, 0.06 s for the mocap file.
* `rua_keeper` (`fbx_check_rua_keeper.json`, `fbx_builtin_in_blender.png`):
  * Blender 4.2 import: 19 bones, 14 actions, 1010 weighted verts. Joints match the GLB to 0.1 mm at keys
    and 2.97 mm between keys.
  * FBX2glTF (Autodesk FBX SDK): worst joint error 2.75 mm.
  * assimp: 14 animations, 1790 faces.
* `mocap_demo` (`fbx_check_mocap_demo.json`): FBX2glTF 0.009 mm, Blender 0.01 mm.
* Not tested: Unity, Unreal, Maya.

## Bugs found by these tests (fixed)
* setup.bat: an `echo (...)` inside an `if (...)` block broke cmd parsing. Wine found it.
* build_release.bat returned exit 1 when the optional C step was skipped.
* The .bat files had LF line endings. They are CRLF now, and `tools/make_release_zip.py` enforces it.
* Photo mode ignored `--video MOVE=clip.mp4`. This was a pre-existing bug.
* The mocap Python went into the user's home directory (uv's default). It is now in the project's `python312/`.
