"""Pitch, timing, and presentation constants for PEIL 26.

Geometry follows the GAA Official Guide: length 130–145 m, width 80–90 m,
goal 6.5 m wide, crossbar 2.5 m, small rectangle 14 × 4.5 m, large rectangle
19 × 13 m, penalty mark 11 m, lines at 13, 20 and 45 m, and the 40 m arc
adopted with the 2025/26 football rule enhancements.
"""

from __future__ import annotations

VERSION = "1.0.0"

# Championship-size field. Croke Park is about 144.5 × 88; this is the
# legal maximum, which reads well as a modern inter-county venue.
PITCH_L = 145.0
PITCH_W = 90.0
HALF = PITCH_L * 0.5
CENTER_Z = PITCH_W * 0.5

GOAL_HALF_W = 3.25  # posts are 6.5 m apart
CROSSBAR = 2.5
POST_H = 8.0
SMALL_DEPTH = 4.5
SMALL_HALF_W = 7.0  # 14 m rectangle, 3.75 m outside each post
LARGE_DEPTH = 13.0
LARGE_HALF_W = 9.5  # 19 m rectangle, 6.25 m outside each post
PENALTY_DIST = 11.0
ARC_R = 40.0
RETREAT = 13.0
SOLO_GO_R = 4.0
STEP_M = 0.78  # one playing step, used to count the four-step rule

GRAVITY = 9.8
BALL_R = 0.11

# Senior inter-county halves are 35 minutes. Extra time is 10 a side.
SENIOR_HALF_MIN = 35
EXTRA_HALF_MIN = 10
SIN_BIN_MIN = 10
MAX_SUBS = 5

# Roles that the 2026 4/3 structure rule pins in place.
# Four in the defensive half (goalkeeper allowed) and three outfield
# players in the opposition half.
OWN_HALF_ROLES = ("gk", "rcb", "fb", "lcb")
ATTACK_HALF_ROLES = ("rff", "ff", "lff")

FORMATION = {
    # depth 0 = own goal line, 1 = opposition goal line. z 0–1 across the pitch.
    "gk": (0.025, 0.50),
    "rcb": (0.11, 0.78),
    "fb": (0.09, 0.50),
    "lcb": (0.11, 0.22),
    "rhb": (0.27, 0.84),
    "chb": (0.25, 0.50),
    "lhb": (0.27, 0.16),
    "mf1": (0.47, 0.64),
    "mf2": (0.47, 0.36),
    "rhf": (0.63, 0.80),
    "chf": (0.66, 0.50),
    "lhf": (0.63, 0.20),
    "rff": (0.84, 0.74),
    "ff": (0.87, 0.50),
    "lff": (0.84, 0.26),
}

ROLE_ORDER = [
    "gk", "rcb", "fb", "lcb", "rhb", "chb", "lhb",
    "mf1", "mf2", "rhf", "chf", "lhf", "rff", "ff", "lff",
]

# Fictional sponsors only — no real brands, no GAA or EA marks.
SPONSORS = [
    "CUL ENERGY", "ATLANTIC AIR", "SHANNON BANK", "EMERALD",
    "BOG OAK", "PEIL 26", "RIVER RADIO", "SAFFRON",
    "WESTWAVE", "NIGHTLIGHT", "ANMHAR", "CROKE LANE",
]

RULES_TEXT = """
PEIL 26  ·  2026 GAELIC FOOTBALL RULES
Official Guide playing rules in force for the 2026 season
(Special Congress, October 2025, effective 1 January 2026).
This is an unofficial game. It is not affiliated with the GAA or LGFA.
Ladies' football uses a separate rulebook and is not simulated here.
Third-level trials (4-point goals, a fisted-point ban, a 3-handpass
limit) are NOT part of the official 2026 rulebook and are not used.

SCORING
  Goal under the crossbar = 3 points. Shown as goals-points (total).
  Point over the bar, kicked from inside the 40 m arc = 1.
  Two-pointer: kicked over the bar with at least one foot on or
  outside the 40 m arc. A teammate's touch after the kick makes it 1.
  A defender's touch does not cancel the two. The ball may bounce over.
  A 45 or a sideline kick is always worth 1, even from outside the arc.
  A hand pass or fist over the bar is not a point.
  A fist or hand pass into the net is a goal.
  Own scores count.

THE BALL IN HAND
  Four steps, then you must solo (toe-tap), bounce, or release it.
  A bounce cannot be followed by another bounce. A solo clears it.
  You may solo more than once in a row. Standing still is legal.
  The step meter under your name shows the count. A skill solo is F.
  Changing hands by throwing the ball is illegal in the men's game;
  the actions in this game are all legal strikes, solos, or bounces.

KICK-OUT
  Taken from the centre of the 20 m line.
  Every player must be 13 m from the ball.
  The ball must travel beyond the 20 m line and the 40 m arc before
  a teammate of the kicker may play it. The other team may intercept.
  Playing it early is a free, brought to the arc.
  Encroaching inside 13 m is a 50 m penalty.

1 V 1 THROW-IN
  One player from each side contests the throw-in at halfway.
  Everyone else stays behind their own 45. Breaking early is a free
  from halfway. Time the jump (SPACE) as the ball reaches the top.

4 / 3 STRUCTURE
  During play each team keeps at least 4 players (goalkeeper included)
  in its own half and at least 3 outfield players in the other half.
  A breach is a free against you, and the free may be taken from the
  40 m arc as a two-point attempt. Your teammates hold the shape.
  The HUD shows SHAPE. If you drag the last defender up, it breaks.

SOLO AND GO
  Fouled outside the opposition 20 m line, you may solo immediately,
  within 4 m of the foul, and not backwards. Press F in the window.
  You cannot be challenged for 4 m. A challenge inside that is a
  50 m penalty. Inside the 20 m line the free is dead-ball only.

MARKS
  Kick-out mark: clean catch from a kick-out on or past the 45.
  Advanced mark: clean catch on or inside the opposition 20 m line
  from a kick played on or beyond the opposition 45, in play or from
  a kick-out mark. G claims the free. SPACE plays on.
  Opponents stay 13 m from a mark free. Delaying it is penalised.

GOALKEEPER
  A teammate may pass to the goalkeeper only if both are inside the
  large rectangle, or if the goalkeeper is in the opposition half.
  Anything else is a free out.

SQUARE BALL
  An attacker already inside the small rectangle when the ball is
  played in concedes a square ball and the score is disallowed.
  From open play an attacker may enter the square after the kick.

FOULS, CARDS, PENALTY
  Legal: shoulder to shoulder with a foot on the ground, a tap of the
  ball from the hand, a block down of a kick.
  Illegal: pulling, tripping, charging from behind, charging in the air.
  A personal foul by the defence inside the large rectangle is a penalty
  (11 m). A cynical pull or trip there is a black card and a penalty.
  Yellow is a caution. Two yellows is a red. A black card is 10 minutes
  in the sin bin with no substitute — the team plays with 14. A second
  black, or a black after a yellow, is a red. A red is an off, no return.
  Opponents retreat 13 m from a free. Failure to retreat advances it.

HOOTER AND CLOCK
  The clock stops for stoppages, as in the 2026 stop-clock.
  The half ends when the hooter sounds, unless the ball is already in
  flight and a score results with no further attacking touch, or a
  free, 45, sideline or penalty has already been awarded and is taken.
  Senior exhibition halves are 35 game-minutes. Extra time is 10 a side
  if the match is level. Five substitutions.

RESTARTS
  Wide (attack put it over the endline, no score): kick-out.
  Defence put it over their own endline: 45 to the attack.
  Over the sideline: sideline kick to the other team.
""".strip()

CONTROLS_TEXT = """
CONTROLS  ·  KEYBOARD AND GAMEPAD

MOVE            W A S D  or  left stick
SPRINT          Left Shift  or  RB
AIM             Mouse on the pitch  or  right stick
KICK / SHOT     Space (hold for power)  or  A  or  left click
                Aim under the crossbar for a goal, over it for a point.
                From on or outside the 40 m arc a point is worth two.
HAND PASS       Q  or  X  or  right click
FIST PASS       E          longer hand strike, can fist a goal
HOOK KICK       H          punt with swerve
SOLO            F          toe-tap. Also SOLO AND GO after a foul
BOUNCE          R          once only, until you solo
SIDESTEP        V          dummy and burst. Beats a tackle
TACKLE          X (keyboard) or  LB     legal from the side or front
SHOULDER        Sprint into an opponent side-on, one foot grounded
BLOCK DOWN      Hold Z as they kick
CLAIM MARK      G
CALL FOR BALL   Q while a teammate has it
SWITCH PLAYER   C  or  Tab
JUMP AT THROW   Space as the ball tops out
CAMERA          1 broadcast   2 follow   3 goal   4 tactical   5 low
PAUSE           Esc
MUTE            M
FULLSCREEN      F11
ARC OPTION      2    bring a awarded free out to the 40 m arc
CONFIRM         Enter

Gamepad (Xbox layout): A kick, X hand pass, B bounce, Y solo,
LB tackle, RB sprint, Start pause, right stick aim.

The player you control has a gold ring. Teammates support, hold the
4/3 shape, and solo on their own. You take frees, penalties, 45s,
marks and kick-outs for your team.
""".strip()
