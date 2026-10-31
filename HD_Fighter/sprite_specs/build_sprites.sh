#!/usr/bin/env bash
# Rebuild the HD Fighter in-game sprite sheets with Sprite Forge (v10 sculpt renderer).
#   HD_Fighter/sprite_specs/build_sprites.sh [out_dir] [--install]
# Each <char>.txt spec has `sculpt = <char>`, which selects the sculpted costume preset in sprite_forge/sforge/sculpt.py;
# poses are the hand-posed HD Fighter frames in sforge/hdfighter.py (attack peaks on frames 1-2, frame counts = meta.json).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FORGE="$HERE/../../sprite_forge"
OUT="${1:-/tmp/hd_fighter_sprites}"
cd "$FORGE"
M="$(python3 -c 'import sys; sys.path.insert(0, "."); from sforge import hdfighter as H; print(H.MOVES)')"
pids=()
for c in kairo lyra naomi brutus void zap; do
  python3 forge.py build --spec "$HERE/$c.txt" --moves "$M" --yaw 90 --frame 192x256 --figure-h 158 --ground-y 244 \
    --pivot-x 92 --quality final --expressions off --strips --no-glb --no-fbx --no-cache --out "$OUT/$c" > "$OUT.$c.log" 2>&1 &
  pids+=($!)
  if (( ${#pids[@]} >= ${JOBS:-2} )); then wait "${pids[0]}"; pids=("${pids[@]:1}"); fi
done
wait
python3 tools/hd_install.py --src "$OUT/{c}/{c}/strips/{s}.png" ${2:-}
