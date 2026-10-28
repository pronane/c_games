#!/usr/bin/env bash
# Arena FC - build every device package. Requires Python 3.9+.
set -e
cd "$(dirname "$0")"
python3 Tools/build.py "$@"
