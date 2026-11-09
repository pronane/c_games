#!/usr/bin/env bash
# Audio Capture Studio - Linux launcher
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (one time only)..."
    $PY -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

if [ ! -f ".venv/.deps_installed" ]; then
    echo "Installing dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    touch .venv/.deps_installed
fi

exec python audiocapture_app.py "$@"
