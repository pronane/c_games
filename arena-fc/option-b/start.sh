#!/bin/bash
# One container, two processes:
#   * the .NET authoritative game server on 127.0.0.1:7777 (internal only)
#   * the shared Node hub (shared/netplay/server) on $PORT: serves the web build at /arena/ and
#     proxies wss://host/arena/ws to the .NET server. It also serves HD Fighter, Egyptian Fighter
#     and TurboTumble64 on their own paths, from the same port.
# If either process stops the container exits, so the platform restarts it instead of looking
# healthy while the game server is dead.
PEER=""; [ "$ARENA_FC_PEER_HOST" = "1" ] && PEER="--peer-host"
dotnet /app/server/ArenaFC.Server.dll --port 7777 --bind 127.0.0.1 --verbose $PEER &
DOTNET_PID=$!
ARENA_BACKEND=ws://127.0.0.1:7777 node /app/shared/netplay/server/hub.js &
NODE_PID=$!
wait -n
kill "$DOTNET_PID" "$NODE_PID" 2>/dev/null
exit 1
