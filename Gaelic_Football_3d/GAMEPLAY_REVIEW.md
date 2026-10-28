# Gaelic Football v3.2: gameplay review and gap analysis

This review compares the game against EA FC/FIFA, PES/eFootball, Sensible Soccer/Kick Off, Rocket League, AFL 26 and the PS2 *Gaelic Games: Football* (2005). It is based on the actual code (`src/game.c` engine, `src/main.c` client), as of v3.2.
Sizes: **S** is under half a day, **M** is 1–3 days, **L** is a week or more.

## 1. Why v3.x felt "off" (root causes)

| Symptom | Root cause in code | v3.2 status |
|---|---|---|
| The camera "doesn't zoom like it used to" | v2/v3 `updateCamera` used a fixed height/distance broadcast rig that only followed the ball, so nothing in it widened. The older legacy build had `camera_openness`. v3 added the right-stick orbit/zoom. A resting trigger axis on some pads (EasySMX reports a trigger as a stick axis) pinned that zoom at a single value. | **Fixed:** `framingTarget()` gives an openness from 0 to 1 based on carrier speed, player spread, flight distance and height, and the restart type (kick-outs are widest). It is smoothed with `smoothDamp`. `pad.c` `axisLive` ignores an axis until it has been seen at rest. The right stick recentres after 3 s. |
| Control doesn't go to whoever has the ball after a turnover | The selection moved only when *your* team gained possession or you pressed a key. Against an opposing carrier, nobody was picked, and the engine AI skips the selected player, so he stood still. | **Fixed:** `autoSwitch()` gives you your carrier instantly. When the opposition has the ball, it picks the best goal-side defender. On loose or aerial balls it picks the receiver who will arrive soonest, and on a home pass it picks the intended receiver. It has hysteresis and a cooldown so it doesn't flicker. |
| Passes go "somewhere" | The engine passed along the facing direction to the nearest player in a cone. There was no visual target, and the stick direction was lost when the player turned. | **Fixed:** you get a stick-direction target ring (cyan for a hand pass, orange for a kick). The engine aims `pass_target` with a run-lead, and the kick power is auto-fitted to the distance. |
| Can't pick up or catch reliably | You had to be within 1.6 m (`FOOT_PICKUP_RADIUS`) and press the right button at the right time. A catch needed a manual jump in a 2.1 m window. | **Fixed:** pickup magnetism within 7 m, and an auto-run to the catch point with the catch assist. |
| Movement feels twitchy, like ice | Movement is instant: facing equals the stick, at a constant 7 or 9 m/s. | **Improved:** a client-side curve with acceleration of 3.5/s and a turn rate that falls as speed rises. A plant-and-turn slows you on reversals, and sprint ramps up. |
| You always get caught | `AI_SPEED` is 8.2 m/s against your 7 m/s jog. The CPU tackles once it has been within 2.2 m for 0.3 s and wins about 80% of tackles. | **Not changed** (engine balance). See R1. |

## 2. Benchmarks: what the reference games do

- **EA FC 26 switching.** Its options are Auto Switching (Air Balls & Loose Balls is the default and the competitive meta), Next Player Switching (Classic, Goal Side, or Closest to Ball), Right-Stick Switching, a reaction-time calibration (it switches to the *previously* recommended player), and Player Lock.
  - Our v3.2 auto-switch is close to "Automatic". The 2 s manual hold acts as a light player lock.
- **EA FC passing.** Assisted, Semi and Manual modes for each pass type. "Pass Receiver Lock" is set to Late by default, meaning the target locks at the last moment.
  - Ours locks at the button press (`queue_release` captures it). Late lock would feel better.
- **FC defending.** Jockey (slows the player and keeps him square, with Assisted jockey matching the attacker's pace), Contain and Teammate Contain (the AI presses for you), and tackles timed to the attacker's heavy touch.
  - Ours has no jockey and no contain. An idle defender stands still.
- **PES/eFootball vs FIFA movement.** PES has momentum and foot-planting, which feels heavy but physical. FIFA is responsive but can feel like "ice-skating". The usual advice is responsive acceleration with real deceleration and turn penalties, which is what v3.2's curve does.
- **Sensible Soccer/Kick Off.** The ball and the top-down view tell you where the run is before the pass. A "cone around the ball" elects the best support man, and there is aftertouch on kicks.
  - We have no aftertouch or curve.
- **Rocket League camera.** It is defined as focus, rotation around the focus, distance, and FOV, and it blends between states. It pitches only when the ball leaves the frame.
  - Multi-target cameras (the *Push Me Pull You* blog) frame a bounding box of the key actors with a margin, cap the zoom, and average it over recent frames.
  - v3.2 now follows this (focus, openness, smoothDamp).
- **AFL 26.** Pack marking is decided by positioning and timing, not button-mashing, with clear visual cues for the drop zone. Reviewers note that no camera fully suits a huge oval, and that short kicks leave the frame.
  - This is directly relevant to the high catch, the mark and the camera.
- **Gaelic Games: Football (PS2, 2005).** Reviews say it failed on:
  - laggy inputs causing over-carries;
  - "passing rarely works";
  - crude barging tackles where the carrier always offloads;
  - static AI teammates ("your players stand still");
  - a hyperactive camera;
  - weak goalkeepers.
  - These are exactly the traps to avoid. Responsiveness, reliable passing and moving teammates matter more than visuals.
- **Real Gaelic rules (GAA 2020+).**
  - A kick-out mark is a clean catch beyond the 45. The advanced mark is a clean catch inside the 45 from a kick of 20 m or more delivered from outside the 45. The player raises an arm, has 15 s, and opponents retreat 13 m. Playing on gives 4 protected steps or one act.
  - Kick-outs are taken from the 20 m line and must travel 13 m.
  - Ulster GAA data: about 75% of retained kick-outs end in a scoring chance. Teams vary between quick short, press-breaking long, and overload options. Opponents press man-to-man or zonally (3-3-3, 4-4-4).

## 3. Prioritised recommendations (Gaelic-specific)

| # | Item | Size | Why / how (code hook) |
|---|---|---|---|
| R1 | **Defensive balance: CPU tackling** | S | `CPU_TACKLE_COMMIT_TIME` 0.3→0.6 s, and add a tackle success roll based on the angle (from in front or goal-side is more likely to succeed; from behind gives a free, as in Gaelic). Cap `AI_SPEED` chasing a *carrier* at 7.4 so a jinking solo can get away. The constants are in game.c lines 9–16 and the logic at about line 1295. This is the biggest "feels unfair" item. |
| R2 | **Jockey / contain for the selected defender** | S | Hold LT: auto-shadow the nearest attacker at 1.8 m goal-side, at 0.8× speed, facing the ball (reuse `ai_move_to` and the `update_support_and_marking` goal-side point). Tackle then gets a timing bonus if pressed just as the carrier bounces or solos, because the ball is off the hand. |
| R3 | **Solo rhythm assist** | S | Show the 4-step/solo timer as a ring around the carrier's feet that fills up, and auto-solo on the 4th step when B is held, so there are no accidental over-carries (the PS2 game's biggest complaint). The engine already tracks steps and bounces, so this is UI plus one input default. |
| R4 | **The mark: make it a real choice** | M | The engine already emits `GAME_EVENT_ADVANCED_MARK` and `GAME_EVENT_KICKOUT_MARK`, and has `mark_play_on`. Show the "MARK! Y = free, play on = move" prompt, raise the arm, run the 15 s clock, and retreat opponents 13 m. Make the kick assist target forwards *inside* the 45 when the kicker is outside it, so advanced marks happen. |
| R5 | **Kick-out strategy menu** | M | During a kick-out, the d-pad picks Short (corner-back), Long middle (a midfield contest) or Wing (an overload side), and the AI runs to suit. When the CPU takes kick-outs, it picks based on how the user is pressing. Add a user press call ("Press up/zonal/drop", a toggle) that sets the CPU's formation depth. |
| R6 | **High-ball contest** | M | A drop-zone marker at the landing spot (already computed in `landingPoint()`) and a jump-timing grade (early, perfect, late) that decides a clean catch vs a break. 2–3 players contest with a strength/height roll. Breaking ball spills to the side, which creates scrambles (a core Gaelic moment). |
| R7 | **Late pass-receiver lock + cancel** | S | Re-evaluate `pass_target` at the contact frame (`release_ball`) instead of the press, as FC's "Late" does. Add a cancel by tapping LB while charging. |
| R8 | **Stamina** | M | A per-player 0–1 bar, drained by sprinting and recovered by jogging. Low stamina lowers top speed, kick power and catching. Later, add substitutes (the engine has an `off` flag but no bench yet). This gives sprint a cost, so pacing and tempo matter. |
| R9 | **CPU attacking runs** | S | `update_support_and_marking` only helps the home carrier. Mirror it for the CPU team (2 support runners, one hand-pass option and one deep), so the CPU builds attacks rather than solo-carrying into tackles. |
| R10 | **Shot aim cone and curve** | M | Show a translucent cone toward the posts whose width is scaled by power, pressure and angle. Add a curve (hook/screw) via the right stick during the charge, using lateral acceleration in the ball update. This makes points from wide angles a skill. |
| R11 | Throw-in / midfield contest | S | Currently 1v1. Make it 2v2 with a jump-timing contest (reuse R6). |
| R12 | Goalkeeper sweeping and short kick-out reception | M | The keeper comes out for long balls inside 20 m. Defenders show for short kick-outs. |
| R13 | Camera polish | S | The framing box should include the drop-zone marker and the nearest marker. There is an option for "Ball cam / Player cam" (as in Rocket League) and a minimap toggle for long kicks (as in baseball games). |
| R14 | Free-taker aim assist off by default for points beyond 40 m | S | A skill vs accessibility setting (FC-style Assisted/Semi/Manual setting). |

## 4. What v3.2 implemented (from this list and the regressions)

- Dynamic framing camera (all cameras use openness; kick-outs and long kicks widen).
- Auto-switch (carrier, goal-side defender, receiver, the restart taker), L1/Tab walking the nearest four, the switch flash ring, and an off-screen arrow.
- Stick-direction hand-pass and kick-pass assist with rings, lead and auto power (engine: `pass_target`).
- Pickup magnetism, auto-run to catch, and catch assist.
- Movement curve (acceleration, turn rate, plant) and a sprint ramp.
- Home support runs plus goal-side marking by backs (engine: `ai_support`, off by default for the tests).
- Not done: R1–R14 above (R2, R3, R7 and R9 are the next cheapest wins).
