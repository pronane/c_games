# Laws-of-the-game audit — `src/rules/`

**Date:** 2026-11-06 · **Scope:** `laws.ts` (pure law functions), `field.ts` (geometry),
`engine.ts` (match state machine) vs `types.ts` (`FIELD` constants, 2026 settings).
**Method:** every exported law function classified WIRED / PARTIAL / NOT WIRED,
checked against engine call sites, then covered or gap-noted here with tests.
Automated gates: `tests/laws.spec.ts` (28 tests), `tests/engine.spec.ts` (17 tests).

Two defects were found by the audit and **fixed** (below). Everything else is
classified honestly — including the parts that are explicitly *not* wired.

## Defects found & fixed in this audit

1. **6-6-6 centre placement violated the 6-6-6 law.** `setupSixSixSix()` put a
   middle-third player at `(dir·20, 0)`, which is 49 m from the attacking goal —
   inside that 50 m arc — and `(±24, ±22)` sat only ~50.1 m out, flipping sides
   under the ±1 m jitter. Result: **7–9 players inside the attack arc and 3–5 in
   the middle — an illegal centre ball-up every single time.** Fixed: middle
   slots moved to a corridor ≥ 50 m from *both* goals with > 1.9 m of slack
   (worst case under jitter verified over 5000 synthesised placements). A
   self-check (`checkSixSixSix`) now runs inside `setupSixSixSix()` and
   `console.warn`s on any violation, so this class of bug is caught at runtime.
2. **Goal-line scoring logic duplicated and untested inline.** `onGoalLineCrossed`
   re-implemented what the tested pure `scoreLineOutcome` already encodes.
   Rewired to `scoreLineOutcome` as the single source of truth — the duplicated
   ~70-line inline block (and the dead `scoreAtCrossing` import) is gone.
   Behaviour preserved: post strikes score a behind for the attacking side;
   touched/non-kick dispatches still concede the behind; deliberate rushed
   behinds still yield the 15 m free kick; `engine.spec.ts` "scores & restarts"
   passes unchanged.

## Wiring map (status per law)

| Law function | Status | Where / why |
|---|---|---|
| `decideMark` (15 m, untouched, on the full) | **WIRED + TESTED** | `onBallCaught`; mark awarded via `makeFreeKick`. tests: laws.spec "marks", engine possession suite. |
| `decideTackle` (holding the ball / HTB prior opp / shrug) | **WIRED + TESTED** | `onTackle`; `holdingTheBall`/`incorrectDisposal` → free kick, legal tackle → possession swap, no-prior → ball-up. laws.spec "tackling", engine "possession". |
| `decideRunTooFar` (15 m bounce law) | **WIRED + TESTED** | Called during live play; `runningTooFar` free kick. laws.spec "running with the ball". |
| `decideOutOfBounds` (2026: OOF / deliberate / smothered) | **WIRED + TESTED** | `onBoundaryCrossed`; covers kick-ins out untouched too (`lastDisposal`/`outOnTheFull` → free kick to attackers). laws.spec "out of bounds", engine "scores & restarts". |
| `scoreLineOutcome` (goal / behind / post / on-the-full post) | **WIRED + TESTED** (was inline; deduplicated this audit) | `onGoalLineCrossed`. See fix #2. |
| `applyScore` / `margin` / `totalPoints` | **WIRED + TESTED** | All score paths; engine end-of-match winner calc. |
| `makeFreeKick` / `isSetShot` / `applyFiftyMetrePenalty` | **WIRED + TESTED** | `awardFreeKick` (set-shot deadline), `onProtectedAreaBreach` (2026 stand → 50 m). 50 m tests in laws.spec "50 m penalty". |
| `decideKickIn` | **TESTED, NOT WIRED (deliberately)** | laws.spec "kick-in after a behind". The kick-in path is enforced by construction (spot always inside the goal square) + the 8 s set-shot clock (`shotClockExpired` → `kickInNotCleared`) + `decideOutOfBounds` for untouched boundary exits. Routing `decideKickIn` into the boundary handler would *tighten* the law (free kick vs throw-in after a bounced-then-out kick-in) beyond the general boundary rule — a law interpretation, not a wiring fix. See "Needs a rule decision" below. |
| `checkSixSixSix` | **NOW WIRED (self-check), "verify" role** | `setupSixSixSix` warns on illegal placement (fix #1). Full placement enforcement would fight the ±1 m jitter design; the check is the audit tool, not a gate. |
| `mustStand` (5 m protected area) | **TESTED, PARTIAL** | `onProtectedAreaBreach` → 50 m is wired and engine-tested. The *predicate* is only correct for "is subject to the stand rule", **not** "is breaching it" — calling it on presence alone would award 50 m penalties to stationary opponents. Actual movement-based violation detection (closing distance vs the mark) is not implemented. See "Needs a rule decision". |
| `ruckCrossedCentre` (2026: ruck may not advance) | **TESTED, NOT WIRED** | No ruck-crossing detection in the sim; placement respects it but violations during the ball-up are not policed. |
| `advantage` | **NOT IMPLEMENTED** | The laws (2023/2026) allow play-on instead of a free kick when penalising disadvantages play. The engine always stops for every free kick; the "PLAY ON!" HUD string exists (`FREE_KICK_TEXT['advantage']`) and `callPlayOn()` exists, but nothing triggers an advantage assessment. Implementing it changes game flow materially — deferred as a feature, not a wiring fix. |
| `restartForTeam` | **NOT WIRED (trivial)** | One-line convenience wrapper over `makeFreeKick`; unused by the engine. Left in place; safe to delete later. |
| `isGoalSquareRestart`, `goalLineXFor` | **NOT WIRED (trivial)** | Convenience helpers; goal-square logic lives inline at the call sites. |
| `formatClock`, `formatScore` | **WIRED + TESTED** | HUD. |

## Needs a rule/umpire decision before wiring (do not wire blindly)

1. **Advantage rule** — when, and for how long, should play-on be preferred over
   the free kick? Needs a possession/stabilisation heuristic and a delay
   (e.g. "no advantage after 0.35 s of prior opportunity" already exists for
   HTB context — reuse it). Until then every penalty stops play, which is
   conservative and non-controversial.
2. **Stand-rule enforcement (`mustStand`)** — the 2026 rule obliges opponents
   inside 5 m of the mark to *stand* (not advance). Enforcement needs a
   movement test (velocity/speed sign toward the mark), plus a decision on
   timing (immediate 50 m vs. warning on first metre gained) and on whether
   it applies to kick-ins as well as marks/free kicks. The predicate itself
   is tested; the enforcement semantics are not defined anywhere in-repo.
3. **Kick-in exits that bounced** — `decideKickIn` treats *any* untouched
   boundary exit from a kick-in as a free kick to the attackers (even after a
   bounce); the general boundary rule (`decideOutOfBounds`) yields a throw-in
   in that case. Which is correct for kick-ins needs an authoritative reading
   of the 2026 kick-in law before the boundary handler changes.
4. **Ruck crossing the centre circle** — detection is trivial (the ball-up
   phase knows the ruck's contest target) but the *penalty* for it is not
   coded (`ruckCrossedCentre` has no free-kick path); needs the intended
   sanction.

## What the audit did NOT cover

- Umpire AI / broadcast umpiring calls, third-man-up enforcement, holding-the-man.
- Player fatigue/injury and sin-bin interactions with free kicks.
- Any actual law edition beyond what `types.ts` encodes in `FIELD` (goal square
  9 m, 50 m arcs, protected area 5 m, 8 s set shot, 6-6-6 middle-corridor).
- GPU/visual correctness — none of the above claims anything about rendering.

## 2026 broadcast-checklist line items this closes

- "Simulation: rules audit pass — ?" → **done, this document.**
- "advantage flow sane — ?" → **no** — advantage is not implemented (§Needs a
  rule decision, item 1). Honest answer, not a silent gap.
- "50 m / holding-the-ball correct — ?" → **50 m correct via
  `applyFiftyMetrePenalty` + `onProtectedAreaBreach` (engine-tested);
  holding-the-ball correct via `decideTackle` (unit-tested); stand-rule
  *movement* enforcement not wired.**
