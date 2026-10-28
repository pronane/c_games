#!/usr/bin/env bash
# Arena FC - run the game locally (downloads Godot .NET if missing).
set -e
cd "$(dirname "$0")"
exec python3 Tools/build.py --run
