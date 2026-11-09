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

if [ "$(cat .venv/.deps_installed 2>/dev/null || true)" != "AudioCapture-2" ]; then
    echo "Installing or updating dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo "AudioCapture-2" > .venv/.deps_installed
fi

exec python audiocapture_app.py "$@"
