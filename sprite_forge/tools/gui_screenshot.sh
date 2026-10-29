#!/bin/sh
# usage: tools/gui_screenshot.sh OUT.png '<SFS_AUTOTEST json>'   (Linux, needs Xvfb + imagemagick 'import')
#   SFS_PY=python (default .venv/bin/python or python3)   SFS_DISPLAY=:77 (default)   SFS_APP_PATH=...  run the Studio itself with this PATH (e.g. to hide system ffmpeg)
OUT=$1; JSON=$2; D=${SFS_DISPLAY:-:77}
cd "$(dirname "$0")/.." || exit 1
case "$OUT" in /*) ;; *) OUT="$OLDPWD/$OUT" ;; esac
if [ -n "$SFS_PY" ]; then PY=$SFS_PY; elif [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
Xvfb $D -screen 0 1400x900x24 >/dev/null 2>&1 & XP=$!
sleep 1; rm -f /tmp/sfs_gui_done
DISPLAY=$D PATH="${SFS_APP_PATH:-$PATH}" SFS_AUTOTEST="$JSON" $PY sprite_forge_studio.py > /tmp/sfs_gui.log 2>&1 & GP=$!
for i in $(seq 1 240); do [ -f /tmp/sfs_gui_done ] && break; sleep 1; done
sleep 1; if command -v import >/dev/null; then DISPLAY=$D import -window root "$OUT"; else $PY -c "import sys; from PIL import ImageGrab; ImageGrab.grab(xdisplay=sys.argv[1]).save(sys.argv[2])" "$D" "$OUT"; fi; kill $GP $XP 2>/dev/null; wait $XP 2>/dev/null; echo "shot -> $OUT"
