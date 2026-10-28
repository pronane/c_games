#!/bin/sh
# Rebuilds assets/models/gaelic_player.glb + kit textures from the Mixamo/MakeHuman FBX files.
# Needs: FBX2glTF (https://github.com/facebookincubator/FBX2glTF/releases), python3, numpy, pillow.
set -e
cd "$(dirname "$0")/.."
mkdir -p build_gltf
for p in assets/source/player_base.fbx assets/source/anim_*.fbx; do
  f=$(basename "$p" .fbx)
  FBX2glTF -b -i "$p" -o build_gltf/$f
done
python3 tools/build_assets.py . build_gltf
