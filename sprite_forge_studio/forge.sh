#!/bin/sh
# Sprite Forge Studio CLI wrapper (Linux / macOS / MSYS2): uses ./.venv if setup.sh made it.
#   ./forge.sh build --spec examples_char.txt --preset fighter14      ./forge.sh doctor      ./forge.sh help
D="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$D/.venv/bin/python" ]; then PY="$D/.venv/bin/python"
elif [ -x "$D/.venv/Scripts/python.exe" ]; then PY="$D/.venv/Scripts/python.exe"
else PY=$(command -v python3 || command -v python); fi
exec "$PY" "$D/forge.py" "$@"
