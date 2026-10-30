#!/bin/bash
# Builds the C client test, starts the shared hub on a free port, runs it.
set -e
cd "$(dirname "$0")"
gcc -std=c99 -D_DEFAULT_SOURCE -O2 -Wall -Wextra netplay.c netplay_ws.c test_netplay.c -lm -o /tmp/test_netplay
PORT=${PORT:-3917}
(cd ../server && [ -d node_modules ] || npm install --silent --no-audit --no-fund)
PORT=$PORT node ../server/hub.js > /tmp/netplay_hub.log 2>&1 &
HUB=$!
trap 'kill $HUB 2>/dev/null' EXIT
for i in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 0.1; done
/tmp/test_netplay "ws://127.0.0.1:$PORT/egyptian"
/tmp/test_netplay "ws://127.0.0.1:$PORT/turbo"
