# Arena FC — code review

**Scope:** C# / Godot 4.7 (.NET 9) 3D football game, ~5.6k lines of C# (`Match.cs` 858, `CharacterEditor.cs` 570, `Server/Room.cs` 544, `Server/Program.cs` 527), a GDScript web edition, Python build tools, Dockerfile.
**Method:** static read of the docs, `Server/WebSocketServer.cs`, selected parts of `Server/Program.cs`, `Room.cs` and `Scripts/Core/Match.cs`.
**Not done:** no .NET or Godot in my sandbox, so I did not build, run or test anything. I did not independently verify the author's test claims (66 core tests, 55 in-engine tests, network probes). I did not read the rendering, UI or GDScript code in depth.

## Summary
Good architecture: a Godot-free deterministic core, an authoritative server with resume tokens, and honest documentation of limits. The main risk is the hand-written WebSocket server, which has several robustness and denial-of-service weaknesses that the framework's built-in WebSocket support would avoid.

## Findings

| # | Severity | Area | Finding | Suggestion |
|---|---|---|---|---|
| 1 | High | WebSocket frames | 64-bit payload length is read into a signed `long`; a value with the high bit set becomes negative, passes the `> 4 MiB` check, and `new byte[len]` throws `OverflowException`, which the read loop does not catch (only cancellation/IO/disposed). | Validate `len` as unsigned before allocating; catch generic exceptions. |
| 2 | High | Fragmentation | Each frame is capped at 4 MiB, but continuation frames append to an unbounded `List<byte>`, so one client can exhaust memory. A 4 MiB buffer is also allocated per frame with no per-IP or connection cap. | Cap total message size (e.g. 64 KB); limit connections per IP. |
| 3 | Medium | Handshake timeout | `Stream.ReadTimeout = 5000` does not apply to `ReadAsync`, so a slow client can hold a handshake open. After the handshake the timeout is infinite. | Use a `CancellationTokenSource` with timeout. |
| 4 | Medium | Protocol conformance | Accepts unmasked client frames (RFC 6455 requires masking), does not enforce control-frame limits, RSV bits or UTF-8 validity, and treats binary frames as text. | Prefer ASP.NET Core / `System.Net.WebSockets`. |
| 5 | Medium | Origin | No `Origin` check on upgrade; HTTP responses send `Access-Control-Allow-Origin: *`. | Allow-list origins. |
| 6 | Medium | Determinism | The core uses `MathF` (sin etc.) and float math. Results are not guaranteed bit-identical across OS/CPU architectures, which matters for peer-host simulation handoff and rollback. The README's "honest limits" section acknowledges related limits. | Fixed-point or deterministic math for sim-critical code; cross-platform replay test. |
| 7 | Low | Concurrency | One global `lock(_hub.Gate)` guards all rooms and the game loop; a slow room delays every room. | Per-room locks. |
| 8 | Low | `MatchEngine.Step` | Takes a variable `dt` argument although a fixed `Dt = 1/60` exists. | Remove the parameter or assert it. |
| 9 | Low | Docs | README intro advertises v2 online play, but section 4 says "No ... online multiplayer"; says 47 assertions where `TEST_REPORT.md` says 66; README says .NET 9 while the test report lists 8.0.427 and 9.0.320. | Reconcile. |
| 10 | Low | Maintenance | The web edition is a separate GDScript reimplementation (Godot cannot export C# to web), so the two can drift. | Share data and tests, document the gap. |
| 11 | Info | Repo hygiene | `Tests/obj` is committed; no CI. README calls the test runner "`dotnet test`-style", but it is a console runner. | Add `.gitignore`, CI, xUnit. |

## Positives
- `Scripts/Core` has no Godot references, so it is unit-testable.
- Resume tokens are 256-bit, stored hashed, and compared with a constant-time helper.
- Room limits (`MaxRooms 200`), chat capped at 160 characters, room codes restricted to letters/digits, names HTML-encoded on the status page.
- Unusually candid documentation of what is and is not implemented.

## Suggested priorities
1. Replace or harden the WebSocket server (#1–#5).
2. Decide how much cross-platform determinism you need (#6).
3. Tidy docs and CI (#9, #11).
