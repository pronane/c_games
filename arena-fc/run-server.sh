#!/usr/bin/env bash
# Arena FC - start the Play With Friends server (Linux / macOS).
# Friends then enter ws://YOUR-IP:7777 in the game -> PLAY WITH FRIENDS.
set -e
cd "$(dirname "$0")"
PORT="${1:-7777}"
# Optional: ARENA_FC_PEER_HOST=1 ./run-server.sh   (live simulation handoff on host loss)
EXTRA=()
if [ "${ARENA_FC_PEER_HOST:-0}" = "1" ]; then EXTRA+=("--peer-host"); fi
if command -v dotnet >/dev/null 2>&1; then
  DOTNET=dotnet
elif [ -x "$HOME/.cache/arena-fc/dotnet/dotnet" ]; then
  DOTNET="$HOME/.cache/arena-fc/dotnet/dotnet"
  export DOTNET_ROOT="$HOME/.cache/arena-fc/dotnet"
  export PATH="$DOTNET_ROOT:$PATH"
else
  echo "No .NET 9 SDK found. Install from https://dotnet.microsoft.com/download" >&2
  echo "or run: python3 Tools/build.py --check   (bootstraps a local SDK)" >&2
  exit 1
fi
echo "Arena FC friend server on ws://0.0.0.0:$PORT"
echo "Status page: http://127.0.0.1:$PORT/   Health: http://127.0.0.1:$PORT/health"
exec "$DOTNET" run --project Server/ArenaFC.Server.csproj -c Release -- \
     --port "$PORT" --bind 0.0.0.0 --team-size 5 --seed 2026 --verbose "${EXTRA[@]}"
