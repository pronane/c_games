#!/usr/bin/env bash
# Headless tests for the GDScript half of Arena FC: audio, replay, set-piece aim, rig builder,
# the browser edition's game loop and USB/EasySMX pad support. No display, no .NET needed.
# Usage:
#   GODOT=/path/to/godot Tools/run-gd-tests.sh
#
# Each SceneTree test must call quit(); a script error before that would otherwise leave Godot
# running forever (and hang CI).  A per-test timeout plus annotations makes that a fast, visible
# failure instead.  Override the limit with ARENA_FC_TEST_TIMEOUT (seconds).
set -u
GODOT="${GODOT:-godot}"
LIMIT="${ARENA_FC_TEST_TIMEOUT:-180}"
cd "$(dirname "$0")/.."
status=0
TIMEOUT=()
if command -v timeout >/dev/null 2>&1; then TIMEOUT=(timeout "$LIMIT"); fi
for t in Tests/gd/test_modules.gd Tests/gd/test_game.gd Tests/gd/test_rules.gd Tests/gd/test_pads.gd; do
  echo "=== $t"
  out=$("${TIMEOUT[@]}" "$GODOT" --headless --path . --script "res://$t" 2>&1); code=$?
  echo "$out" | grep -E "^(PASS|FAIL|RESULT)|SCRIPT ERROR|Parse Error" || true
  if [ $code -ne 0 ] || echo "$out" | grep -qE "^FAIL|SCRIPT ERROR|Parse Error"; then
    status=1
    echo "--- $t FAILED (exit $code, limit ${LIMIT}s with ${#TIMEOUT[@]} timeout args) ---"
    echo "$out" | head -40
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
      echo "::error file=$t::$t failed (exit $code)"
      # Surface the useful lines as check-run annotations: logs live on a host some
      # sandboxes cannot reach, annotations are available through the API.
      echo "$out" | grep -E "SCRIPT ERROR|Parse Error|^FAIL|^ERROR|at:" | head -20 |
        while IFS= read -r line; do printf '::error file=%s::%s\n' "$t" "${line//%/%%}"; done
    fi
  fi
done
exit $status
