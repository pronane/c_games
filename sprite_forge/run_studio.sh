#!/bin/sh
# Opens the visual Sprite Forge Studio (Tkinter).  Linux needs python3-tk (forge.sh doctor tells you the command).
D="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$D/.venv/bin/python" ]; then PY="$D/.venv/bin/python"
elif [ -x "$D/.venv/Scripts/python.exe" ]; then PY="$D/.venv/Scripts/python.exe"
else PY=$(command -v python3 || command -v python); fi
if ! "$PY" -c 'import tkinter' 2>/dev/null; then
  echo "tkinter missing:"; "$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); from sforge.doctor import tk_install_hint; print("  " + tk_install_hint())' "$D"; exit 1
fi
exec "$PY" "$D/sprite_forge_studio.py" "$@"
