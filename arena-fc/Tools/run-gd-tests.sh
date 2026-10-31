#!/usr/bin/env bash
# Headless tests for the GDScript half of Arena FC: audio, replay, set-piece aim, rig builder and the
# browser edition's game loop. No display, no .NET needed. Usage:
#   GODOT=/path/to/godot Tools/run-gd-tests.sh
set -u
GODOT="${GODOT:-godot}"
cd "$(dirname "$0")/.."
status=0
for t in Tests/gd/test_modules.gd Tests/gd/test_game.gd; do
  echo "=== $t"
  out=$("$GODOT" --headless --path . --script "res://$t" 2>&1); code=$?
  echo "$out" | grep -E "^(PASS|FAIL|RESULT)|SCRIPT ERROR|Parse Error"
  if [ $code -ne 0 ] || echo "$out" | grep -qE "^FAIL|SCRIPT ERROR|Parse Error"; then status=1; fi
done
exit $status
