#!/usr/bin/env bash
# Arena FC - run the 47 core + 39 in-engine tests.
set -e
cd "$(dirname "$0")"
exec python3 Tools/build.py --check
