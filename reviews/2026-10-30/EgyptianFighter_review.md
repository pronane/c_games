# Egyptian Fighter — code review

**Scope:** C99 + raylib 2D fighter, ~2.8k lines in `src/` (`game.c` 1227, `player.c` 615, `pad.c` 331, `gfx.c`, `demo.c`, `main.c`), 7 characters, Python sprite tools.
**Method:** static read of `game.c`, `player.c`, `common.h`, `player.h`; compile check with `-Wall -Wextra -Wshadow` against raylib 5.5 headers.
**Not done:** I could not build or run the game, so everything below comes from reading the code. I did not test controllers or the sprite tools.

## Summary
A fun, complete prototype with solid controller support and graceful handling of missing art. The combat rules have one real exploit (blocking) and the physics is tied to frame rate. Characters currently differ only in art, because every move uses the same timings and damage.

## Findings

| # | Severity | Area | Finding | Suggestion |
|---|---|---|---|---|
| 1 | High | Blocking (`CheckHits`) | Melee is cancelled whenever `inputBlock` is held (`!p2->inputBlock`); it does not check the player is in `STATE_BLOCK`, grounded, or facing the attacker. A player can hold block while walking, jumping or mid-attack and take no melee damage. Throws are also blocked, and block has no meter, pushback or stun. Projectiles do require `onGround`; melee does not. | Test `state == STATE_BLOCK && onGround && facing`; let throws bypass block; add block-stun/chip damage. |
| 2 | High | Frame rate (`player.c`) | Movement, gravity (`GRAVITY 0.55`), jump force and projectile speed are applied per frame, while animation and the round timer use `dt`, and invincibility uses `GetFrameTime()`. `UpdatePhysics` takes `dt` but ignores it (the one compiler warning). At anything other than 60 FPS the game runs faster or slower relative to animation and timers. | Fixed-step simulation at 60 Hz, or scale by `dt`. |
| 3 | Medium | Keyboard 2P (`ReadInputP1`/`P2`) | P1 reads WASD **and** the arrow keys; P2 reads the arrow keys. In 1P vs 2P on one keyboard the arrows move both fighters. | Remove arrows from P1 when P2 is human. |
| 4 | Medium | Double KO (`CheckHits`) | P1's health is checked first, so if both reach 0 on the same frame P2 wins. (A timeout draw *is* handled: `winner = 0`.) | Detect double KO and declare a draw. |
| 5 | Medium | Combat depth | `HitPlayer` gives 0.6 s invincibility and 0.6 s hit-stun, so combos are impossible by design; all fighters share the same move times and damage (`MELEE_DAMAGE 8`, `PROJ_DAMAGE 10`). | Per-character data table (damage, startup, recovery). |
| 6 | Medium | CPU (`SimpleCPU`) | Reads the human's attack state perfectly and blocks 35% of the time (a comment says 45%); no difficulty setting; frame-counter cooldowns (so tied to finding 2). | Reaction delay, difficulty levels. |
| 7 | Low | Docs | README describes `char1`/`char2` with 14 sheets, but the repo has `char_daragh`, `char_dec`, `char_dragon`, `char_egypt`, `char_flame`, `char_mike`; `char1` contains only a README. The README keyboard table lists "WASD / Arrows" for P1 and "Arrow keys" for P2 (see #3). | Update README. |
| 8 | Low | Publication | Characters named "Padel Mike", "Dangerous Dec", "Daragh" and in-jokes ("Bum Fireball") may refer to real people. | Confirm consent/rename before public release. |
| 9 | Info | Testing | No automated tests or CI. Useful dev hooks exist (`EF_FAKEPAD_DIR`, `EF_LOGSTATE`, `EF_TEST_HP2`). | Script a headless run using those hooks. |

## Positives
- Runs even with zero art (coloured placeholders and warnings).
- Gamepad support with SDL controller DB, raw fallback, and a controller test screen.
- Sprite alignment normalised from visible bounds; optional `sprites.cfg` grid mode.
- One consistent rule set (`MOVE_TIME_*`, `ACTIVE_FROM/TO`) makes balance easy to reason about.

## Suggested priorities
1. Fix blocking (#1) and frame-rate dependence (#2).
2. Keyboard split for local 2P (#3), double-KO draw (#4).
3. Per-character move data (#5) to make fighters feel different.
