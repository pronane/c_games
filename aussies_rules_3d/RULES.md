# The Rules — exact Australian football laws implemented in Aussie Rules 3D

Aussie Rules 3D plays by the **2026 Laws of Australian Football**, including
the major 2026 reforms (no centre bounce, five-player interchange, the
last-disposal out-of-bounds law, the shrug-is-prior-opportunity law, the
5-metre stand rule and the 8-second restart clock).

Every law below is implemented as a pure, unit-tested function in
`src/rules/laws.ts` and wired into live play by `src/rules/engine.ts`.
The test suite (`tests/scoring.spec.ts`, `tests/laws.spec.ts`,
`tests/engine.spec.ts`) proves each one.

## Match structure (Law 1.3)

| Law | Implementation | Test |
|---|---|---|
| 4 quarters | `MatchSettings.quarters = 4` | `engine.spec` |
| 20 minutes playing time per quarter + time on | `quarterSeconds = 1200`, clock runs only while the ball is live, stoppage time is added as "time on" | `engine.spec` |
| 18 players per team on the ground | 18 named players per team + 5 interchange | `engine.spec` |
| 5-player interchange (2026), 75 rotations | `interchange = 5`, `rotationCap = 75` | `engine.spec` |
| Siren ends each quarter; a set shot at the siren is completed | `endQuarter` / `matchEnd` | `engine.spec` |

## Scoring (Law 1.5)

| Law | Points | Implementation |
|---|---|---|
| Kicked through the two tall goal posts, untouched | **6 (goal)** | `scoreLineOutcome` |
| Through the gap between a goal post and a behind post | **1 (behind)** | `scoreLineOutcome` |
| Touched in flight before crossing the goal line | 1 (behind) | `ball.touched` check |
| Carried or handballed over the goal line | 1 (behind) | `lastDisposal !== 'kick'` check |
| Hits a goal post | 1 (behind), play stops | `postHit: 'goalPost'` |
| Hits a behind post on the full | no score, free kick to the opposition beside the post | `behindPostOnFull` |
| Hits a behind post after bouncing | no score, boundary throw-in | `behindPostBounced` |
| Defender deliberately forces the ball over their own goal line | 1 (behind) **and** a free kick to the attackers 15 m out, directly in front | `deliberateRushedBehind` |
| A defender's own kick through the middle | goal to the attackers (a rushed goal still counts) | `scoreLineOutcome` |

## Marks (Law 1.7 / 5.9)

- A clean catch from a kick that travelled **at least 15 metres** untouched in
  the air is a **mark**: a free kick from the spot, and the player may play on.
- A catch from a shorter kick is just possession — play continues.
- A ball that bounced, or was touched in flight, cannot be marked.
- Only a kick can be marked (never a handball).

## Tackling & holding the ball (Law 1.8)

- Tackles must be between the shoulders and the knees.
- **Prior opportunity** (including a **shrug** or fend — 2026 law) + tackled
  without a legal disposal → **holding the ball**, free kick to the tackler.
- No prior opportunity + locked up → **ball-up** at the stoppage.
- No prior opportunity + spills free with a genuine disposal attempt → play on.
- High contact / push in the back by the tackler → free kick to the carrier.
- Throwing the ball or dropping it in the tackle → free kick against.

## Running with the ball (Law 1.7.3)

- A player carrying the ball must **bounce it or touch it to the ground every
  15 metres**. Further without a bounce → free kick (running too far).

## Out of bounds (Law 12, 2026 reforms)

| Situation | Result |
|---|---|
| Kicked out on the full (untouched) | Free kick to the opposition where it crossed |
| **Last disposal** (kick or handball) crosses the boundary untouched **between the 50 m arcs** (2026 "lasso" law) | Free kick to the opposition |
| Smothered, deflected off hands/feet | Boundary throw-in |
| Inside the 50 m arcs, deliberate / insufficient intent | Free kick to the opposition |
| Otherwise (accidental) | Boundary **throw-in** |

## Restarts (Law 1.6)

- **2026: there is no centre bounce.** Quarters and goals restart with a
  **centre ball-up** — the umpire throws the ball up at the centre.
- Around the ground, stoppages are ball-ups or boundary throw-ins.
- **Kick-in after a behind**: from inside the goal square, within **8 seconds**
  (2026 law, aligned with set-kick time), and the ball must be kicked. A
  kick-in that goes out untouched → free kick to the attackers. Taking too
  long or leaving the square early → free kick against.
- **6-6-6 at centre ball-ups**: six players from each team in each 50 m arc
  and six in the middle (2026: **no** requirement for a player in the goal
  square).
- **Ruck rules (2026)**: at centre ball-ups a competing ruck may not cross the
  centre circle line before contesting; play can restart without a nominated
  ruck, and if no rucks contest the ball must hit the ground before play on.

## Free kicks, marks & penalties (Law 1.8.4)

- After a mark or free kick, opponents must **stand the mark**. Any opponent
  within the **5 m protected area must stand** (2026 "stand" rule) and may not
  retreat or interfere.
- Interference (running over the mark, holding the kicker, delaying the return
  of the ball, moving inside 5 m) → **50 metre penalty**: the kick is moved
  50 m toward goal, or to the top of the goal square when already inside 50.
- Set shots inside 50 are taken with an **8-second** clock.

## Free-kick infringements modelled

Holding the ball · running too far · high tackle · push in the back · holding
the man · throwing · trip · kick in danger · charge · out on the full ·
last disposal out of bounds · deliberate out of bounds · deliberate rushed
behind · interference after a mark · protected-area breach · third man up ·
ruck crossing the centre line · kick-in not cleared.

---

**A note on the "last disposal" law.** The 2026 AFL law change package replaced
the old "insufficient intent" judgement between the 50 m arcs with the AFLW /
SANFL-style last-disposal free kick: if a kick or handball takes the ball over
the boundary line untouched between the arcs, the opposition gets the free
kick. Inside the arcs, insufficient intent remains. Aussie Rules 3D
implements exactly that split.

*Sources: 2026 Laws of Australian Football and the AFL's October 2025 law
change announcements (centre bounce removed, substitute removed in favour of a
five-player interchange, last-disposal out of bounds, ruck nomination
restarts, shrug = prior opportunity, 5-metre stand rule, 8-second kick-ins).*
