#!/bin/sh
# Sprite Forge Studio setup - Linux / macOS / MSYS2 shell.  Everything goes into ./.venv (and ./venv_pose for mocap);
# nothing is installed system-wide.  Options:
#   ./setup.sh              core + extras + mocap (mocap may download Python 3.12 via uv, ~30 MB, and the pose model)
#   ./setup.sh --core-only  only requirements-core.txt (no pycolmap / trimesh / mocap)
#   ./setup.sh --no-pose    skip the mocap venv
#   PYTHON=/path/to/python3 ./setup.sh     use that interpreter for .venv
cd "$(dirname "$0")" || exit 1
EXTRAS=1; POSE=1
for a in "$@"; do
  case "$a" in
    --core-only) EXTRAS=0; POSE=0 ;;
    --no-pose) POSE=0 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }

# ---- 1. a Python >= 3.9
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python python3.13 python3.12 python3.11 python3.10; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY=$(command -v "$c"); break
    fi
  done
fi
if [ -z "$PY" ] && command -v uv >/dev/null 2>&1; then
  say "no Python 3.9+ found - fetching Python 3.12 with uv"
  uv python install 3.12 && PY=$(uv python find 3.12)
fi
if [ -z "$PY" ]; then
  echo "Python 3.9+ not found. Install it (Debian/Ubuntu: sudo apt install python3 python3-venv;"
  echo "Fedora: sudo dnf install python3; Arch: sudo pacman -S python; macOS: brew install python;"
  echo "MSYS2: pacman -S mingw-w64-ucrt-x86_64-python) or install uv: https://docs.astral.sh/uv/ and re-run."
  exit 1
fi
say "Python: $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

# ---- 2. .venv
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  say "creating .venv"
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    if command -v uv >/dev/null 2>&1; then
      uv venv --seed --python "$PY" .venv || exit 1
    else
      echo "python -m venv failed. Debian/Ubuntu: sudo apt install python3-venv  (or install uv and re-run)"; exit 1
    fi
  fi
fi
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python.exe; fi

# ---- 3. packages
say "installing core packages (requirements-core.txt)"
"$VPY" -m pip install --disable-pip-version-check --upgrade pip >/dev/null 2>&1
"$VPY" -m pip install --disable-pip-version-check -r requirements-core.txt || { echo "core install failed"; exit 1; }
if [ "$EXTRAS" = 1 ]; then
  say "installing extras (requirements-extras.txt) - optional, failures are not fatal"
  "$VPY" -m pip install --disable-pip-version-check -r requirements-extras.txt || echo "(some extras failed - forge.py doctor shows what that disables)"
fi
if [ "$POSE" = 1 ]; then
  say "mocap: venv_pose with Python 3.12 + mediapipe + pose model (tools/setup_pose.py)"
  "$VPY" tools/setup_pose.py || echo "(mocap setup failed - everything else works; re-run: $VPY tools/setup_pose.py)"
fi

# ---- 4. tkinter (system package on Linux)
if ! "$VPY" -c 'import tkinter' >/dev/null 2>&1; then
  say "tkinter is missing - the visual Studio needs it (the CLI works without it):"
  if command -v apt-get >/dev/null 2>&1; then echo "   sudo apt install python3-tk"
  elif command -v dnf >/dev/null 2>&1; then echo "   sudo dnf install python3-tkinter"
  elif command -v pacman >/dev/null 2>&1; then
    if [ -n "$MSYSTEM" ]; then echo "   pacman -S mingw-w64-ucrt-x86_64-tk"; else echo "   sudo pacman -S tk"; fi
  elif command -v zypper >/dev/null 2>&1; then echo "   sudo zypper install python3-tk"
  elif command -v brew >/dev/null 2>&1; then echo "   brew install python-tk"
  else echo "   install your distro's python3-tk / tkinter package"; fi
fi

# ---- 5. doctor + next steps
say "forge.py doctor"
"$VPY" forge.py doctor
chmod +x forge.sh run_studio.sh build_release.sh 2>/dev/null
cat <<'TXT'

Next steps
  ./run_studio.sh                                   visual Studio (Help tab explains every field)
  ./forge.sh build --spec examples_char.txt --preset fighter14      demo character -> out/rua_keeper (+ model.glb/.fbx)
  ./forge.sh video --clip walk:8=examples_video/walk_static.mp4 --name vid --consoles snes
  ./forge.sh scan --video examples_video/orbit_mannequin.mp4 --frames 72 --run --name orbit
  ./forge.sh help quickstart                        beginner guide;   ./forge.sh doctor   re-check
  ./build_release.sh                                build + verify every demo
TXT
