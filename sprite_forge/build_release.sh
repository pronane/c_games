#!/bin/sh
# Sprite Forge Studio - build + verify every demo (Linux / macOS / MSYS2).  Run ./setup.sh once first.
#   ./build_release.sh            all steps;   ./build_release.sh --quick   skip scan --run and the C example
cd "$(dirname "$0")" || exit 1
QUICK=0; [ "$1" = "--quick" ] && QUICK=1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
else PY=$(command -v python3 || command -v python); echo "(no .venv - run ./setup.sh; using $PY)"; fi
step() { printf '\n[%s] %s\n' "$1" "$2"; }
fail() { echo "FAILED at step $1 - see messages above"; exit 1; }
step 0 "doctor";                         $PY forge.py doctor || fail 0
step 1 "SPEC demo (fighter14) + GLB + built-in FBX -> out/rua_keeper"
$PY forge.py build --spec examples_char.txt --preset fighter14 --out out || fail 1
$PY tools/verify_output.py out/rua_keeper || fail 1
step 1b "FBX check with independent readers (assimp / FBX2glTF / Blender when available)"
$PY tools/verify_fbx.py out/rua_keeper/model.glb out/rua_keeper/model.fbx --json out/rua_keeper/fbx_check.json > /dev/null \
  && echo "FBX check PASS (out/rua_keeper/fbx_check.json)" || fail 1b
step 2 "SNES console export";            $PY forge.py build --spec examples_char.txt --preset fighter14 --console snes --no-fbx --out out_snes || fail 2
$PY tools/verify_console.py out_snes/rua_keeper || fail 2
step 3 "profiles";                       $PY forge.py profile validate || fail 3
$PY forge.py build --spec examples_char.txt --profile kart_racer --no-fbx --out out_profiles || fail 3
step 4 "VIDEO: bundled clips -> sprites + SNES"
$PY forge.py video --clip walk:8=examples_video/walk_static.mp4 --clip run:8=examples_video/run_tracking.mp4 \
  --clip jump:12=examples_video/jump_handheld.mp4 --clip punch:10=examples_video/punch_green.mp4 \
  --name vidhero --out out_video --consoles snes --no-fbx || fail 4
step 5 "SCAN: orbit clip"
if [ "$QUICK" = 0 ] && $PY -c "import sys; sys.path.insert(0, '.'); from sforge.scan import sfm_backend; sys.exit(0 if sfm_backend() else 1)"; then
  $PY forge.py scan --video examples_video/orbit_mannequin.mp4 --frames 72 --run --height 1.75 --name orbit_demo --out out_scan || fail 5
else
  $PY forge.py scan --video examples_video/orbit_mannequin.mp4 --frames 72 --name orbit_demo --out out_scan || fail 5
  echo "(project only: pip install pycolmap for --run)"
fi
step 6 "MOCAP (needs venv_pose from tools/setup_pose.py)"
if [ -x venv_pose/bin/python ] || [ -x venv_pose/Scripts/python.exe ]; then
  $PY forge.py mocap --clip walk:8=examples_video/walk_static.mp4 --clip jump:12=examples_video/jump_handheld.mp4 --name mocap_demo --out out_mocap || fail 6
else
  echo "(skipped - run: $PY tools/setup_pose.py)"
fi
step 6b "v8: Quick preview (draft) + cached rebuild + Egyptian Fighter export + v8 tests -> out_v8"
$PY forge.py build --spec examples_char.txt --preset fighter14 --quality draft --out out_v8/draft || fail 6b
$PY forge.py build --spec examples_char.txt --preset fighter14 --no-fbx --out out_v8 || fail 6b
$PY forge.py build --spec examples_char.txt --preset fighter14 --no-fbx --out out_v8 || fail 6b
$PY forge.py export-ef out_v8/rua_keeper out_v8/game_assets/char_rua || fail 6b
$PY tools/test_v8.py out_v8/tests || fail 6b
step 7 "raylib C example (optional)"
if [ "$QUICK" = 0 ] && command -v make >/dev/null 2>&1 && command -v cc >/dev/null 2>&1; then
  make -C spriteforge || echo "(C example not built - needs raylib: see spriteforge/README_spriteforge.md or 'make -C spriteforge raylib')"
else
  echo "(skipped)"
fi
printf '\nDone.  ./run_studio.sh  |  ./forge.sh help quickstart  |  outputs in out*/\n'
