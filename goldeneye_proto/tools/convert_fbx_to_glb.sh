#!/usr/bin/env bash
# Facility 64 - convert FBX models to GLB for assets/models/.
#   tools/convert_fbx_to_glb.sh model.fbx [more.fbx ...]
#   tools/convert_fbx_to_glb.sh some_folder/
# Uses Blender (best: keeps every animation take as a named clip) if 'blender' is on PATH
# (or BLENDER=/path/to/blender), otherwise falls back to the Assimp command-line tool
# ('assimp export in.fbx out.glb'; install: apt install assimp-utils / brew install assimp).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BLENDER="${BLENDER:-blender}"
[ $# -eq 0 ] && { sed -n 2,7p "$0"; exit 1; }
files=()
for a in "$@"; do
  if [ -d "$a" ]; then for f in "$a"/*.[fF][bB][xX]; do [ -e "$f" ] && files+=("$f"); done; else files+=("$a"); fi
done
for f in "${files[@]}"; do
  out="${f%.*}.glb"
  if command -v "$BLENDER" >/dev/null 2>&1; then
    "$BLENDER" -b -P "$HERE/blender_fbx_to_glb.py" -- "$f" "$out" | grep -E "wrote|Error" || true
  elif command -v assimp >/dev/null 2>&1; then
    assimp export "$f" "$out" -fglb2 && echo "wrote $out (assimp)"
  else
    echo "Need Blender or assimp on PATH to convert $f"; exit 1
  fi
done
echo "Now copy the .glb files into assets/models/ and point models.cfg at them (F3 reloads in game)."
