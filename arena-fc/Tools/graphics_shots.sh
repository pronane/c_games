#!/usr/bin/env bash
# Render the graphics-benchmark shots: Tools/graphics_shots.sh OUT_DIR [renderer]
# Each shot is a screenshot plus a --graphics-report JSON (Scripts/Godot/GraphicsReport.cs).
# renderer: opengl3 (default: the web/mobile renderer, and what a GPU-less CI runner can draw)
#           or vulkan (Forward+, the desktop look; needs a GPU to finish in reasonable time).
set -euo pipefail
out="${1:?output dir}"; drv="${2:-opengl3}"
mkdir -p "$out"
failed=0
: "${GODOT:?set GODOT to the Godot binary}"
shot() {
  local name="$1"; shift
  echo "== $name"
  timeout 1200 xvfb-run -a -s "-screen 0 1920x1080x24" "$GODOT" --path . --rendering-driver "$drv" \
    --audio-driver Dummy --resolution 1920x1080 -- "$@" --screenshot \
    --shot-out "$out/$name.png" --graphics-report "$out/$name.json" > "$out/$name.log" 2>&1 || true
  test -s "$out/$name.png" && test -s "$out/$name.json" || { echo "::error::shot $name failed"; tail -20 "$out/$name.log"; failed=1; }
}
shot broadcast --match --size 11 --seed 2026 --ai-vs-ai --camera 0 --shot-frame 240
shot close     --match --size 11 --seed 2026 --ai-vs-ai --camera 2 --shot-frame 90   # closer view costs more per frame on software GL
shot player    --rigshot
shot face      --rigshot --rigshot-face
exit "$failed"
