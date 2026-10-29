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

The fight steps at a fixed 1/60 s of wall time. A fast link does not fast-forward the round, and a burst of inputs does not skip ahead. Each input is numbered with the sim frame it belongs to. The server picks one input delay for both players from the ping samples they send when they finish loading. The delay covers the path from one player through the server to the other (each side's one-way time), not just the trip to the server. A quiet link stays near 2–8 frames. A link with about 120 ms on each hop needs roughly 20 frames so the round can stay at 60 Hz. The cap is 36 frames (600 ms). Each packet repeats only a short tail of recent inputs, packed as bit masks. A missing frame is a NACK and is resent immediately. "Connection slow" / "Connection lost" follow silence from the other player, not how far the sim is behind the clock. If a player drops mid-fight the round pauses for 30 seconds so they can rejoin the same frame; after that the remaining player wins and both can rematch. A screen shows "Connection slow" only after it has been waiting, and gives up the round if the wait lasts several seconds. The seed in the start message drives the only random number generator. Every 30 frames the clients exchange a state hash and stop the round if they differ.

The player id lives in `sessionStorage` for this tab. A second tab is a different player and does not take the first tab's slot. Reloading the same tab keeps the id.

At about 120 ms on each hop the input delay is roughly 21–24 frames, so a button press reaches the sim about 365–390 ms later. Both screens stay in sync, and the round still lasts about 99 seconds, but the fight feels sluggish. Lockstep has to wait for the other player's input before that frame can run. A later version can hide that wait with rollback: play the local input immediately, keep the last second of state, and if the remote input disagrees, rewind and simulate forward again. That is not in this version — rewinding the hit checks and the seeded RNG is easy to get wrong, and this change only keeps the delay honest.

Reconnects wait 0.3 s and then back off up to 3 s, and a socket that is still connecting after 4 s is closed so the next try can start. A dropped fight stays on the fight screen for 30 s (`Reconnecting...`) instead of giving up at 9 s. **Connection slow** / **Connection lost** mean game inputs or hashes have stopped, not merely that heartbeats are still arriving. A match that is still running but under about 45 sim frames per second for 2 seconds shows **Poor connection**.

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
