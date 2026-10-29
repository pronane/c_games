# HD Fighter multiplayer — test results

Branch `cursor/hd-fighter-online-handshake-e3e2`. `cd HD_Fighter/multiplayer && npm test` exited 0.

## What changed

- Stall follows silence from the other player, not how far the sim is behind the clock. **Connection slow** after 1 s without a packet, **Connection lost** after 9 s. A packet clears it. A background tab keeps time and sends a heartbeat from a worker, so a throttled `requestAnimationFrame` is not treated as a dead peer.
- The shared input delay is each player's one-way time to the server added together (`rttA/2 + rttB/2`), plus jitter and about one extra frame. The cap is 36 frames (600 ms). A 120 ms hop on both sides is about 240 ms from player to player, so half a ping was too short.
- Steady input packets carry packed bitmasks (the unacked frames, capped at 32), and a gap is a NACK that is resent immediately.
- A lobby reconnect restores the saved pick, so Ready works without picking again.
- A drop during a fight pauses both sides with `Opponent reconnecting... (30 s)`. The dropped client can rejoin and replay to the agreed frame. After the timeout the remaining player wins and both return to the lobby with Ready available.
- A refused connection says **Can't reach the server.** An HTTP response, including 503, says **Waking the server...** and the room pill is cleared when the connection is refused.
- Rotate-your-device is only on a small touch portrait. On a 664×390 touch landscape the stage is 372×209 (16:9) and the D-pad does not cover it. A 1280×800 touch landscape leaves about 5 px of side bar.

## npm test

Handshake: join/ready/`go`, rejoin, leave during countdown (`Opponent left`, both ready flags cleared), 100/100 unique rooms, 3600/3600 inputs in 60485 ms.

Lockstep through 15–85 ms jitter: one heavy punch deals 12, 3600 frames, 120/120 hashes, 0 mismatches, HP 52 and 88.

Pace (steady rate after the first inputs arrive). The proxy delays each TCP leg and holds 5% or 1% of chunks an extra 40 ms.

| Profile | Sim fps | Packets/s | Delay | Timer vs wall | Hashes |
|---|---|---|---|---|---|
| No latency, 60 Hz ticker | 60.08 | 59.8 | 4 | 5 s dropped in 4.011 s | match |
| No latency, 144 Hz ticker | 60.17 | 60.2 | 4 | — | — |
| 25 ms/leg + 1% | 60.04 | 59.3 | 6 | — | match |
| 120 ms/leg + 5% | 59.94 | 59.3 | 22 (cap 36) | 8 s in 8.008 s | match |
| 120 ms/leg ±30 + 5% | 59.90 | 59.4 | 24 (cap 36) | 8 s in 8.013 s | match |

At 59.9 fps a 99 s timer is about 99.2 s of wall time. The delay did not sit on the 36-frame cap.

Stall unit tests: a peer that sends every 200 ms for 30 s stays quiet; a blackholed peer is slow at 1 s and lost at 9 s; packets resume clears it; 21 s of frame lag with packets every 30 ms does not trip it. A 503 is **Waking the server...**; a refused connection is **Can't reach the server.**

Reconnect: 300/300 ready-without-re-pick after rejoin. Mid-fight resume replayed to frame 12 with the same hash (`1727900688`). Forfeit awarded the remaining player and Ready worked afterward.

Packed input packets in the unit test were about 20 KB for 60 packets in the worst unacked window, against the 180–360 KB/s measured on the previous build.

## Not tested

- The independent Playwright suite (Chrome, Firefox, WebKit, the message-drop proxy). The numbers above are this repo's node proxy, which delays TCP chunks instead of dropping whole WebSocket messages.
- A full 99 s round left running on the wall clock. The timer check is a 4 s slice and an 8 s slice.
- A real Render 503. The wording is covered by the unit test of the status choice.
- A physical phone or iPhone Safari. The 664×390 and 1280×800 checks were headless Chrome with touch emulation.
- WebKit playing the demo. Chrome reports `canPlayType` "probably". The video has a poster and a fallback line if the codec is missing.
- Replacing the Brutus, Void, and Zap placeholder silhouettes.
