# HD Fighter 2 — online multiplayer

Two browsers share a room on the Node server in `multiplayer/`. The server relays inputs and keeps the room; each browser runs the fight.

## Play

1. One player chooses **Create Private Room** or **Quick Play**. A private room gets a 5-character code such as `K7Q2M` (not a counter like `R0001`).
2. The other player joins with that code or the invite link (`#` plus the code).
3. Both pick a fighter and press **Ready**. Ready is a set value: pressing it again does not cancel it.
4. When both have picked and both are ready, the server sends a countdown with one seed and one start time. Each browser loads and replies. The fight starts only after both replies, at that start time.
5. On a cold host (Render’s free tier sleeps), the page says **Waking the server...** and keeps trying for about 90 seconds. A wrong or expired code still fails as soon as the server answers.

If you leave and reopen the same tab, the game reclaims your slot. The previous socket is closed. A late disconnect from that old socket does not remove you from the room. The player id is stored in `sessionStorage`, so a second tab is a different player and joins as the other slot instead of taking the first tab's place.

## Simulation

The fight steps at a fixed 1/60 s. Each input is numbered with the sim frame it belongs to and is applied 3 frames later, so both screens use the same input on the same frame. A screen waits when the other player's input for that frame has not arrived. The seed in the start message drives the only random number generator. Every 30 frames the clients exchange a state hash and show a warning if the fights diverge. Lobby messages and inputs have separate rate limits: extra inputs are dropped, and the socket is closed only for a flood.

The player id lives in `sessionStorage` for this tab. A second tab is a different player and does not take the first tab's slot. Reloading the same tab keeps the id.

## Run locally

```bash
cd HD_Fighter/multiplayer
npm install
npm start
```

Open `http://localhost:3000` in two browsers.

## Test

```bash
cd HD_Fighter/multiplayer
npm test
```

`test_handshake.js` starts the server and checks:

- two clients join, ready, load, and both receive `go` with the same seed and start time
- a client rejoins mid-way, the old socket closes, and the new socket still gets the start
- creating again while you are alone stores the socket, so the next player is the other slot
- 100 pairs in a row each reach `go` with distinct codes
- 60 input messages per second for 60 seconds are all delivered, and the sockets stay open

`SOAK_SECONDS=2 npm test` shortens the input check.

## Deploy

Render: root directory `HD_Fighter/multiplayer`, build `npm install`, start `node server.js`, health check `/api/health`.

The free instance sleeps when idle. The client waits and retries while it wakes. Room codes are kept in memory, so a restart drops existing rooms. New codes are random, so a restart does not hand `R0001` to the next pair.
