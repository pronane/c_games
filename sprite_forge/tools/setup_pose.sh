#!/bin/sh
# kept for v4 users: the real work is done by tools/setup_pose.py (no curl, fetches Python 3.12 with uv if needed)
cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then exec .venv/bin/python tools/setup_pose.py "$@"; fi
exec python3 tools/setup_pose.py "$@"
