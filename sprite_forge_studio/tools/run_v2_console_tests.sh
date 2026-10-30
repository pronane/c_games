#!/bin/bash
# Sprite Forge Studio v2 - console preset CLI tests + verification.  Output: /workspace/sprite_forge_tests/v2_console/
S=/workspace/sprite_forge_studio; T=/workspace/sprite_forge_tests; O=$T/v2_console
export SFS_BPY_PYTHON=${SFS_BPY_PYTHON:-/workspace/venvs/bpy311/bin/python}
rm -rf $O; mkdir -p $O; cd $S
F="python3 forge.py build"
run() { local tag=$1; shift; echo "=== $tag: $*"; $F "$@" > $O/log_$tag.txt 2>&1 || echo "BUILD FAILED $tag"; tail -1 $O/log_$tag.txt; }
SPEC="--spec $T/inputs/nova_vance.txt"; PHOTO="--photo $T/inputs/test_cartoon_char.jpg --name teal_hero"
# required presets x both test characters (fighter14); HD ones at 512 px frames
for c in nes snes gba ps1 n64; do
  run ${c}_spec   $SPEC  --preset fighter14 --frame 256x256 --console $c --out $O/$c
  run ${c}_photo  $PHOTO --preset fighter14 --frame 256x256 --console $c --out $O/$c
done
for c in pc_hd ps5; do
  run ${c}_spec   $SPEC  --preset fighter14 --frame 512x512 --console $c --out $O/$c
  run ${c}_photo  $PHOTO --preset fighter14 --frame 512x512 --console $c --out $O/$c
done
# kart set on two consoles (spec name differs so use another out root)
run snes_kart_spec $SPEC --preset kart12 --frame 256x256 --console snes --out $O/snes_kart
run ps1_kart_photo $PHOTO --preset kart12 --frame 256x256 --console ps1 --out $O/ps1_kart
# every other preset once (spec, fighter14)
for c in atari2600 sms gb genesis ds saturn dreamcast ps2gc psp wii360ps3 switch_ps4; do
  run ${c}_spec $SPEC --preset fighter14 --frame 256x256 --console $c --no-fbx --out $O/$c
done
# other input modes with a console target
run frames_gba   --frames $T/v2_inputs/frames_folder --name frames_char --moves idle,walk,punch,kick --console gba --out $O/modes
run strips_snes  --move-sheet idle=$T/v2_inputs/strips/idle.png --move-sheet walk=$T/v2_inputs/strips/walk.png --move-sheet punch=$T/v2_inputs/strips/punch.png --move-sheet jump=$T/v2_inputs/strips/jump.png --name strips_char --moves idle,walk,punch,jump --console snes --out $O/modes
run sheet_nes    --sheet $T/v2_inputs/sheet_rows.png --grid 14x10 --name sheet_char --preset fighter14 --console nes --out $O/modes
run gaelic_ps1   --mannequin --preset gaelic36 --name gaelic_ps1 --console ps1 --no-fbx --out $O/modes
echo; echo "=== verify"
python3 tools/verify_console.py $(ls -d $O/*/*/ | sed 's#/$##') > $O/verify_console.txt; tail -1 $O/verify_console.txt
python3 tools/verify_output.py $(ls -d $O/*/*/ | sed 's#/$##') > $O/verify_output.txt; grep -c "RESULT: PASS" $O/verify_output.txt
python3 $T/test_console_headers.py $O > $O/verify_c_headers.txt 2>&1; tail -1 $O/verify_c_headers.txt
echo V2_TESTS_DONE
