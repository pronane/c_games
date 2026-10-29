# HD Fighter multiplayer — test results

Branch `cursor/hd-fighter-online-handshake-e3e2`. `cd HD_Fighter/multiplayer && npm test` exited 0.

## What changed

- Stall follows silence of **inputs, hashes, or acks**, not heartbeats and not how far the sim is behind the clock. **Connection slow** after 1 s, **Connection lost** after 9 s. A crawling match (under about 45 sim fps for 2 s) shows **Poor connection**. A background tab keeps a worker heartbeat so a throttled `requestAnimationFrame` is not what the stall timer watches.
- The shared input delay is each player's one-way time to the server added together (`rttA/2 + rttB/2`), plus jitter and about one extra frame. The cap is 36 frames (600 ms). A 120 ms hop on both sides is about 240 ms from player to player, so half a ping was too short.
- Steady input packets carry packed bitmasks (the unacked frames, capped at 32), and a gap is a NACK that is resent immediately.
- A lobby reconnect restores the saved pick, so Ready works without picking again.
- A drop during a fight keeps **both** fight screens up for 30 s. The player who is still connected sees `Opponent reconnecting... (30 s)`. The dropped player sees `Reconnecting... (30 s)` and keeps retrying; they are not sent to the lobby at 9 s. After the timeout the remaining player wins and both can rematch.
- Reconnects use exponential backoff with jitter, from about 0.3 s up to 3 s. A socket that is still connecting after 4 s is closed so the next try can start, and only one socket is in flight. After a forfeit, a rejoin lands in the lobby with Ready enabled.
- A refused connection says **Can't reach the server.** An HTTP response, including 503, says **Waking the server...** and the room pill is cleared when the connection is refused.
- Rotate-your-device is only on a small touch portrait. On a 664×390 touch landscape the stage is 372×209 (16:9) and the D-pad does not cover it. A 1280×800 touch landscape leaves about 5 px of side bar.

## npm test

Handshake: join/ready/`go`, rejoin, leave during countdown (`Opponent left`, both ready flags cleared), 100/100 unique rooms, 3600/3600 inputs in 60485 ms.

Lockstep through 15–85 ms jitter: one heavy punch deals 12, 3600 frames, 120/120 hashes, 0 mismatches, HP 52 and 88.

Pace (steady rate after the first inputs arrive). The proxy delays each TCP leg and holds 5% or 1% of chunks an extra 40 ms.

| Profile | Sim fps | Packets/s | Delay | Timer vs wall | Hashes |
|---|---|---|---|---|---|
| No latency, 60 Hz ticker | 60.00 | — | 4 | — | match |
| No latency, 144 Hz ticker | 59.97 | — | 4 | — | — |
| 25 ms/leg + 1% | 59.96 | — | 6 | — | match |
| 120 ms/leg + 5% | 59.94 | — | 22 (cap 36) | — | match |
| 120 ms/leg ±30 + 5% | 60.06 | — | 24 (cap 36) | — | match |

At 59.9 fps a 99 s timer is about 99.2 s of wall time. The delay did not sit on the 36-frame cap.

Stall unit tests: a peer that sends every 200 ms for 30 s stays quiet; a blackholed peer is slow at 1 s and lost at 9 s; 220 heartbeats with no input or hash still count as lost; a ~8 fps step trace shows **Poor connection** and a 60 fps trace does not. Backoff starts at 300 ms, grows, and caps at 3 s. A 503 is **Waking the server...**; a refused connection is **Can't reach the server.**

Reconnect: 300/300 ready-without-re-pick after rejoin. Mid-fight resume replayed to frame 12 with the same hash (`3144470544`). Forfeit awarded the remaining player and Ready worked afterward.

Chromium, headless, through a TCP proxy on port 3210 that was closed so connects were refused (not port 9):

| Outage | Attempts while refused | Longest gap | At ~11 s | After the port returned |
|---|---|---|---|---|
| 15 s | 9 | 3.5 s | Fight still up, `Reconnecting... (20 s)` | Server logged rejoin. Status `Opponent reconnected.` |
| 34 s | 16 | 3.4 s | Fight still up, `Reconnecting... (20 s)` | Lobby, room code kept, Ready enabled. Not `No room`. |

Refusals fail immediately, so this run did not leave a socket in CONNECTING. The 4 s close is there for the case where Chromium does.

Input history on the server is a `Uint16Array` capped at 6400 frames per player and dropped when the match returns to the lobby. Two hundred active fights are about 5 MB of history. The 200-room RSS number was not re-measured here.

## Known limit

At 120 ms per hop the agreed delay is about 21–24 frames, so a press reaches the sim about 365–390 ms later. The round stays in sync and near 60 Hz, and it feels sluggish. Lockstep cannot show a frame until the other player's input for that frame has arrived. A later change can hide that with rollback: apply the local input immediately, keep the last second of state, and if the remote input disagrees, rewind and simulate forward. That rewind has to include hit checks and the seeded RNG, so it is not in this change. See `README_ONLINE.md`.

Packed input packets in the unit test were about 20 KB for 60 packets in the worst unacked window, against the 180–360 KB/s measured on the previous build.

## Not tested

- The independent Playwright suite (Firefox, WebKit, the message-drop proxy). Chromium was used for the refused-port outages above. Pace numbers are this repo's TCP delay proxy.
- A full 99 s round left running on the wall clock. The timer check is a 4 s slice and an 8 s slice.
- A real Render 503. The wording is covered by the unit test of the status choice.
- A physical phone or iPhone Safari. The 664×390 and 1280×800 checks were headless Chrome with touch emulation.
- WebKit playing the demo. Chrome reports `canPlayType` "probably". The video has a poster and a fallback line if the codec is missing.
- Replacing the Brutus, Void, and Zap placeholder silhouettes.
