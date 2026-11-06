#!/usr/bin/env sh
#
# Starts Aussie Rules 3D.
#
#   ./start.sh            build once, serve at http://localhost:8080
#   ./start.sh --dev      development server with hot reload
#   ./start.sh --port N   use port N
set -eu
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  if [ -f "$HOME/.aussie-rules-3d/node/bin-path" ]; then
    PATH="$(cat "$HOME/.aussie-rules-3d/node/bin-path"):$PATH"
    export PATH
  else
    printf '\nNode is not installed. Run ./install.sh first.\n\n' >&2
    exit 1
  fi
fi

exec node scripts/start.mjs "$@"
