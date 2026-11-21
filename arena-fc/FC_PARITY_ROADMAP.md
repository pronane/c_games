# Arena FC — FC 25 parity roadmap (working tracker)

This is the **single working list**. It replaces the order (not the content) of
`GAP_ANALYSIS_AND_ROADMAP.md`, `ROADMAP_GRAPHICS_GAMEPLAY.md` and `GAP_ROADMAP_10_PHASES.md`.
Each item ships as its own PR; tick it here in the same PR.

Order rule: **simulation correctness → ball and player physics → controls → AI shape →
animation/visuals → modes**. Animation work comes after the football is right, because
no animation can make a scramble for a dead ball look like FC 25.

Measured with the headless soak harness (`Tools/soak`, 30 seeded matches per size).
Real-football targets used as gates are in §0.

Legend: ✅ done · 🔧 in progress · ⬜ to do

---

## 0. Football-realism gate (CI)
| Metric (11-a-side, per match) | Before | Target band |
|---|---|---|
| Pass reaches a team-mate | 53% | 75–90% |
| Shots (both teams) | 1.9 | 15–30 |
| Shots on target counted | 0 | 30–45% of shots |
| Throw-ins | 0 | 25–50 |
| Corners | 0 | 6–14 |
| Goal kicks | 0.6 | 10–20 |
| Offsides | 0 | 1–6 |
| Tackles won | ~120 | 25–60 |

- ✅ 0.3 (PR #7) `--ai-vs-ai`, `--size N`, `--seed N` for autoplay: full 11-a-side computer-vs-computer matches in the real app.
- ✅ 0.2 `--autoplay` QA flag (PR #3): plays a whole match / shootout / training session unattended in the real Godot app (headless, `--fixed-fps 60`), logs every 5 game-minutes and a full-time summary, then quits. A 90-minute match takes ~25 s. Verified: full match, shootout (decided early, 5 v 4 kicks), Training, Practice Arena — no script errors.
- ✅ 0.1 (PR #16) Add the soak harness to `Tests/` and fail CI when a metric leaves its band (bands widen until the AI items below land). MatchCoreTests now runs a realism gate: 4 full AI matches; shots 4–35, goals 0.5–6, passes 80–700, tackles 20–130, fouls 1–30, cards ≤ 8 per match.

## 1. Simulation correctness (PR #1)
- ✅ 1.1 Ground-ball friction ~5× too high (full-power pass rolled 12 m). Now: 15 m/s rolls ~30 m.
- ✅ 1.2 Pass weight computed from distance (ground passes arrive at the receiver with pace; lofted/chipped carry ~80% in the air).
- ✅ 1.3 Pass/shot wind-up could be tackled ~1 in 4 times before the ball left the foot.
- ✅ 1.4 Shots on target never counted (keeper saves derived from it were wrong).
- ✅ 1.5 xG formula clamped almost every shot to 0.01 → logistic model on distance + visible goal angle.
- ✅ 1.6 AI substitution replaced a player with himself; now uses the real bench, never on a human side.
- ✅ 1.7 Defensive header clearance aimed at the defender's own goal.
- ✅ 1.8 Skill-move cooldown never counted down (one skill per player per match).
- ✅ 1.9 Stale motion-database test fixture crashed `MatchCoreTests`.

## 2. Modes (PR #1)
- ✅ 2.1 Penalty shootout restarted into open play after kick 1 → proper shootout (only taker + keeper move, no clock, best-of-5 + sudden death, early finish, kick tally on screen).
- ✅ 2.2 Training was a normal match with fouls off → Training ground with drills (Attack / Defend) and a coach that teaches every move with pad + keyboard prompts and auto-detects completion.
- ✅ 2.3 Starting Training / Practice Arena switched fouls + offside off for every later match.
- 🔧 2.4 Practice Arena now opens the training ground on free practice (PR #3). Skill Games is still a plain match.
- ✅ 2.5 (PR #12) You control your keeper (dive left/right/stay) on the computer's penalties. The computer now takes a ~1.5 s run-up; the stick held at the strike picks the dive (centre = stay big). Also fixed: the keeper was walked round the 10-yard circle (off-centre) and rushed the penalty taker; and in a shootout the human taker could walk off the spot, which gave a free kick and turned the shootout into open play.

## 3. Ball physics & goal detection
- ✅ 3.1 Running the ball into the net while dribbling is not a goal (goal check only runs on a free ball).
- 🔧 3.2 (PR #6: landing-point prediction; AI crosses from wide) Lofted ground passes / clearances / crosses: real arcs, bounce and roll on landing; chips over the keeper.
- ✅ 3.3 (PR #15, #17) Curl: spin from the shot/pass type and stick, visible Magnus curve (finesse = inside foot curl, outside-foot trivela). Finesse starts outside the post and bends in; trivela (finesse + sprint) starts inside and swerves out; through balls and long passes with a defender in the lane are bent round him (pass spin used to be a random sign). Pass completion unchanged (67%).
- ✅ 3.4 (PR #18) Shot power: hold-to-charge bar + timed-finish second press; height from power and body shape; low driven vs dipping vs chipped finishes. Shots are now struck at a height at the goal line (by shot type), and the things that go wrong lift or scatter them: over-hitting (charge >.85, worse from range), bad timing, sprinting through it, weak foot. A perfectly timed shot from 16 m used to clear the bar every time; now 0/20. Full power from 24 m still goes over about half the time. Shots on target in AI matches went up to a realistic 35–45%.
- 🔧 3.5 (PR #7: pass error now grows with pressure, distance and pass type, with over/under-hit weight — it was a flat ~4° from skill alone; throw-ins 1.1 → 1.8/match. PR #3: wide players use the touchline, pokes/clearances/parries go out — throw-ins 0 → ~2, corners 0 → 0.1/match; still well under real rates) Ball out of play really happens (throw-ins, corners, goal kicks at real rates) — follows from 1.1 + 6.x.

## 4. First touch, aerial control and heading
- ✅ 4.1 (PR #6: foot <0.45 m, thigh/knee <0.95 m, chest <1.55 m, head above; quality from skill + pressure) Controlling a high ball: chest, thigh/knee, instep cushion — chosen by ball height and speed; quality from skill + pressure; heavy touches pop the ball away.
- ✅ 4.2 (PR #6: stick at reception knocks it that way, sprint knocks it further) Player-directed first touch: stick direction at the moment of the touch takes the ball that way; LT = soft touch-and-stop, RT = knock-on.
- 🔧 4.3 (PR #6: jumping headers up to height+0.55 m, aerial duels on height/strength/skill, X = header at goal / A = header pass, AI attacks crosses; players run to the landing point) Headers: attacking (aim with stick, `X` = header on goal, `A` = header pass), defensive clearances, jump timing, aerial duels decided by heading + jumping + strength.
- 🔧 4.4 (PR #6: first-time volleys at goal / volley passes; bicycle kicks to do) Volleys / half-volleys and bicycle kicks from high balls in the box.

## 5. Controls — every move clear and reachable
Current scheme (Xbox / EasySMX labels): `LS` move · `RT/RB` sprint · `LT/L3` close control/shield · `A` pass · `Y` through · `X` shoot (hold) · `VIEW` long ball · `B` tackle · `RT+B` slide · `LB` switch (with ball: call a run) · `RS` flick skills (LT+RS advanced) · `X`→`A` fake shot.
- ✅ 5.1 Skill moves wired to input (were unreachable): RS flicks + keys 1–7.
- ✅ 5.2 Call a team-mate's run (LB / Tab with the ball).
- ✅ 5.3 (PR #8: B = poke tackle (foot in, no slide), RT+B = slide, hold LT = jockey, hold A = contain (auto goal-side), sprint alongside + B = shoulder charge — jockey/contain were AI-only) Defending set: `B` stand tackle / poke (foot in, no slide) · `RT+B` slide · `LT` jockey (contain, face-up, stay goal-side) · `A` (held) contain by team-mate · `B` (held) push/pull · shoulder charge = move into carrier while jockeying.
- ✅ 5.4 (PR #8: LT+X finesse/curl, LB+X chip, double-tap X low driven — finesse was a hidden 50–65% power window; **the stick now aims shots**, the post was random) Attacking extras: `RB` knock-on (speed burst touch) · `LB`+`Y` lofted through · `RB+X` finesse/curl shot · `LB+X` chip shot · `LT+X` low driven shot · `RB` (with pass) driven pass.
- ✅ 5.5 (PR #8) Switch play: `RS` flick off the ball = switch to the player in that direction (right-stick switching).
- ✅ 5.6 (PR #8: pause menu → "Controls – every move", generated from the coach's lessons; coach now 27 lessons) In-game control cards: pause-menu page with the full layout, plus first-time contextual prompts (“Press B to tackle”) in matches.
- ⬜ 5.7 Remap screen covers every action, not just six.

## 6. Team shape & AI
- ✅ 6.1 (PR #3) Formation discipline — the block now steps up in possession and drops compact out of it (final-third entries 4 → 14/match): units hold lines (4-4-2 back four and midfield four), shift across with the ball, step up together; compactness between lines.
- ✅ 6.2 (PR #3) Marking — goal-side, away from the ball; chasers handle the ball: goal-side positioning, zonal by default, track runners, only the nearest one/two press; no crowding round the ball.
- 🔧 6.3 (xG-based shooting PR #2: 1.4 → 4.8; shot bar lowered to real-football levels PR #7: → 8.4 shots, 1.7 goals/match) AI attacking decisions: shoot when in range and on angle (target ~6–15 shots per side), cross from wide, through balls into runs, keep possession under pressure.
- 🔧 6.4 (one-challenger tackling done, PR #2: tackles 91 → 33/match) Carrier who can't be dispossessed (kept the ball ~80 s under repeated tackles) — check tackle odds vs shielding/close-control stacking.
- 🔧 6.5 (1v1 off-the-line + smother done, PR #2) Goalkeeper: comes off the line to narrow the angle and smother 1v1s, claims crosses, sweeper behaviour on through balls; distribution.
- ✅ 6.6 (PR #14) Defensive player-switch stability (ring hops between team-mates). While you steer, auto-switch needs a team-mate clearly closer (≥4 m or 40%): 18 → 9 switches a minute while defending, hops within 1 s 19% → 8%.
- 🔧 6.7 (PR #3: attackers hold the onside line) Offside line held by the back four; offsides at realistic rates.

## 7. Set pieces
- ✅ 7.1 (PR #3) Free kicks: taker must play the ball (pass/shoot/cross) — no picking it up and dribbling; wall at 9.15 m (10 yards) for direct kicks near goal; every opponent at least 9.15 m away.
- 🔧 7.2 (PR #3: throw-ins from the touchline, taker behind the line, 2 m rule, keeper tips for corners) Corners and throw-ins: aimable delivery, near/far post runs, short options; throw-in is a throw (hands), not a pass.
- ✅ 7.3 (PR #13) Penalty kicks in matches use the shootout aiming model. Yours: control jumps to the taker, you aim and strike (auto-taken after 8 s); it used to be struck for you instantly. Theirs: a run-up and your dive decides it; a committed dive the right way reaches full stretch. Also: an AI throw-in taker with nobody within 25 m (5-a-side) stood there forever; now plays it to the nearest team-mate after 3 s.
- ✅ 7.5 (PR #5) **Rules are enforced, not physically prevented** (FIFA/PES behaviour): a human may encroach — caution and sent back (second = red); a human taker may run off with a set piece — free kick to the opposition (foul throw → throw-in to them); a double touch — indirect free kick. AI players keep the distance by choice.
- ✅ 7.6 (PR #5) **Violent conduct**: punch (hold LB+RB, then B / key G) and headbutt (LB+RB, then Y / key T), human-only. Seen by the referee (likelier near the ball) → straight red + direct free kick / penalty; unseen → **VAR** review at the next stoppage or within 6 s → red, and a goal the offending side scored in the meantime is disallowed.
- ✅ 7.7 (PR #5) Skill moves and call-for-ball now work online (they were never sent over the wire).
- ✅ 7.4 Goal kicks: short or long choice (A short / VIEW long for you; the AI mixes them, measured 14 short and 6 long over six matches).
- ✅ 7.4a (PR #10) Law 16 / 13: opponents outside the penalty area at a goal kick (and a defending free kick in its own area) until the ball is played. Found in a 720p playtest: two attackers stood in the box. Referee waves them out; inside 10 yards is still a caution.

## 7b. Rules audit (PR #3)
- ✅ Full-match restart audit in `Tests/MatchCoreTests` (opponents 9.15 m / 2 m, taker can't carry the ball, throw-ins on the line, penalty area clear, parry direction). Found and fixed: opponents only 4 m back; ~10% double touches; throw-ins 1 m inside the pitch; a throw-in taker loop; **keeper parries aimed at his own net**; tackles/fouls animations carrying through stoppages; an idle human could stall a set piece forever (now auto-taken after 8 s).

## 8. Animation & body mechanics (after 3–7)
- ✅ **Fixed in PR #4** (`conform_to_bind` in `Tools/build_soccer_player.py`: upper arms 35°, forearms 46°, neck 18°, legs 6°). **Root cause (PR #3, `Tools/clip_sheet.gd` contact sheets):** every one of the 71 Sprite Forge clips has the arms ~45–60° too far out/up. Side-on, idle/run look like "boxer" arms at chest height; front-on, idle stands with arms out in an A/T shape, and pass/shoot throw both arms above the head. The clips themselves are authored correctly in `Tools/soccer_motions.py` (Sprite Forge's arm (0,0,0) = hanging down); the bias comes from `Tools/build_soccer_player.py` skinning the sculpted mesh to Arena's 18-bone skeleton bound in a different arm pose. Fix = rebuild the GLB through Sprite Forge with matching rest poses (next PR), then re-shoot the sheets.
- ✅ (PR #4: foul → `soccer_trip`) `soccer_foul` is a both-arms-up surrender pose for the whole clip and is what the fouled player plays at every free kick → use `soccer_trip`/`soccer_stumble` instead.
- ✅ (PR #4) `soccer_slide_tackle` is a crouch with one leg out, not a feet-first slide along the ground → re-author in `soccer_motions.py` (hips down to the turf, lead leg extended, travel along the ground).
- ✅ 8.1 (PR #4) Arms: no raised/T-pose arms off the ball; arms only go up for celebrations, appeals, headers and keeper actions.
- ✅ 8.2 (PR #4: the motion engine's Locomotion category held block/appeal/victory/keeper clips at speed 0, so standing players picked arms-up poses; reclassified + idle when stationary) No “jump with arms up” at the wrong time (trigger only from real events).
- ✅ 8.3 (PR #4) Slide tackles go feet first along the ground in the direction of travel.
- ⬜ 8.4 Skill-move, chest/knee control, header and keeper clips via Sprite Forge (capture → solve → clean → export → feedback).
- ⬜ 8.5 Motion engine (already in `Scripts/Core/Animation/`): extend the clip database; foot planting; ball-contact sync for every new action.

## 9. Presentation & UI
- ✅ 9.1 (PR #9) Main menu panel overlaps the subtitle (subtitle no longer wraps; menu anchored below it and stretched to the bottom).
- ✅ 9.2 (PR #9) Match preview off-centre on a blank grey screen; shows “Arena Stadium” instead of the home ground (now centred on a pitch-green backdrop, home club's ground).
- ✅ 9.3 (PR #9) Weather: “Rain” shown but not rendered. Three bugs: the preview weather never reached the match; the HUD looked for the stadium at the wrong node path (so rain *and* goal crowd celebrations never fired); the particles had no mesh. Weather is now a MatchOptions field (resets per match, affects ball drag/wind) and `--weather rain|windy|snow|fog` for QA.
- ✅ 9.4 (PR #9) HUD footprint at 720p: legend cut to two real lines and auto-hidden after 20 s of play (H brings it back), commentary fades after ~8 s idle, minimap ~25% smaller.
- ✅ 9.5 (PR #8: Input.Reset cleared the held state, so the Esc that opened pause read as a new press next frame and closed it) Esc / Menu pause screen and clock (verify on real hardware).
- ✅ 9.6 (PR #9) Training/shootout scoreboard shows a match clock (now “TRAINING GROUND” / “PENALTY SHOOTOUT”).

## 10. Later (modes & platform) — unchanged from the existing docs
Career skeleton, ranked online, replay editor, browser-edition parity (the GDScript web build has its own ball physics and needs 1.1/1.2 ported).

## Engineering housekeeping
- ✅ H.1 (PR #11) Build outputs (`obj/`, `bin/`, `.godot/`) are committed; add to `.gitignore` and remove from the index.
