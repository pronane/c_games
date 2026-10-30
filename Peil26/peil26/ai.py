"""Team intelligence for PEIL 26.

The side should look like Gaelic football: a held 4/3 shape, solos under
pressure, fist and hand passes into space, kick passes aimed at an
advanced mark, and shots chosen as goals, points, or two-pointers.
"""

from __future__ import annotations

import math

from peil26.rules import dist, dist_to_goal
from peil26.settings import CENTER_Z, PITCH_L, PITCH_W

DIFF = {
    "easy": 0.82,
    "medium": 1.0,
    "hard": 1.12,
}


def decide(match, p) -> dict:
    if not p.active:
        return _hold(p.x, p.z)
    if p.role == "gk":
        return _gk(match, p)
    holder = match.ball.holder
    if holder is p:
        return _carrier(match, p)
    return _off_ball(match, p)


def _hold(x, z, sprint=False, action=None, aim=None, aim_y=1.2, power=0.55):
    return {
        "tx": x, "tz": z, "sprint": sprint, "action": action,
        "aim": aim, "aim_y": aim_y, "power": power,
    }


def _skill(match) -> float:
    return DIFF.get(match.difficulty, 1.0)


def _mates(match, p):
    return [o for o in match.players if o.team == p.team and o.active and o is not p]


def _opps(match, p):
    return [o for o in match.players if o.team != p.team and o.active]


def _nearest(players, x, z, ignore=None):
    best, bd = None, 1e9
    for o in players:
        if o is ignore:
            continue
        d = dist(o.x, o.z, x, z)
        if d < bd:
            best, bd = o, d
    return best, bd


def _shape_target(match, p, possess: bool) -> tuple[float, float]:
    """Formation slot, shifted toward the ball, with the 4/3 pins applied."""
    depth, zf = match.slot(p)
    ball = match.ball
    # Drift toward the ball laterally, but not so far that a line collapses.
    zf = zf * 0.62 + (ball.z / PITCH_W) * 0.38
    if possess and p.role not in ("gk", "rcb", "fb", "lcb"):
        depth = min(0.92, depth + 0.04)
    if not possess and p.role not in ("rff", "ff", "lff", "gk"):
        depth = max(0.04, depth - 0.03)
    x, z = match.slot_world(p.team, depth, zf)
    # Pin the structure roles so the whistle is not a coin toss.
    sign = match.attack_sign(p.team)
    half = PITCH_L * 0.5
    if p.role in ("gk", "rcb", "fb", "lcb"):
        if sign > 0:
            x = min(x, half - 1.5)
        else:
            x = max(x, half + 1.5)
    if p.role in ("rff", "ff", "lff"):
        if sign > 0:
            x = max(x, half + 2.0)
        else:
            x = min(x, half - 2.0)
    if p.role == "gk":
        gx = match.own_goal_x(p.team)
        x = gx + sign * 1.4
        z = CENTER_Z + max(-3.1, min(3.1, (ball.z - CENTER_Z) * 0.35))
    return x, z


def _gk(match, p) -> dict:
    gx = match.own_goal_x(p.team)
    sign = match.attack_sign(p.team)
    b = match.ball
    tx = gx + sign * 0.9
    tz = CENTER_Z + max(-3.0, min(3.0, (b.z - CENTER_Z) * 0.9))
    action = None
    aim = None
    aim_y = 2.2
    power = 0.75
    sprint = False
    # Come only for a dropping ball inside the small square. Otherwise stay on the line
    # and narrow the angle — running out to every kick makes every shot a save.
    if b.holder is None and b.y > 1.6 and dist(p.x, p.z, b.x, b.z) < 5.5 and abs(b.x - gx) < 6:
        tx, tz = b.x, max(CENTER_Z - 3.2, min(CENTER_Z + 3.2, b.z))
        sprint = True
    if b.holder is p:
        # Distribute beyond the arc. Pick a free teammate past the 45.
        tx, tz = p.x, p.z
        target = _kickout_target(match, p)
        aim = target
        aim_y = 2.4
        power = 0.82
        action = "kick"
    return _hold(tx, tz, sprint, action, aim, aim_y, power)


def _kickout_target(match, p):
    sign = match.attack_sign(p.team)
    gx = match.own_goal_x(p.team)
    mates = _mates(match, p)
    best, bs = None, -1e9
    for m in mates:
        depth = (m.x - gx) * sign
        if depth < 46:
            continue
        opp, od = _nearest(_opps(match, p), m.x, m.z)
        score = depth * 0.4 + od * 2.0 - abs(m.z - CENTER_Z) * 0.05
        if score > bs:
            best, bs = m, score
    if best:
        return (best.x + sign * 2.0, best.z)
    return (gx + sign * 52.0, CENTER_Z + match.rng.choice((-14, 14, 0)))


def _carrier(match, p) -> dict:
    sign = match.attack_sign(p.team)
    gx = match.attack_goal_x(p.team)
    dgoal = dist_to_goal(p.x, p.z, gx)
    z_off = abs(p.z - CENTER_Z)
    opp, od = _nearest(_opps(match, p), p.x, p.z)
    pressed = od < 1.55
    skill = _skill(match)

    # In front of goal, strike. Pressure does not cancel a goal chance.
    if dgoal < 16 and z_off < 8:
        return _shot(match, p, gx, "goal")
    if dgoal < 22 and z_off < 7:
        return _shot(match, p, gx, "goal")
    # Wide and close: cut in toward the posts before shooting or passing.
    if dgoal < 38 and z_off > 6 and p.role != "gk":
        return _hold(gx - sign * 12.0, CENTER_Z, True, "solo" if p.steps > 3.1 else None, (gx, CENTER_Z), 1.0, 0.5)
    if 38.5 <= dgoal <= 52 and z_off < 16 and match.rng.random() < 0.42 * skill:
        return _shot(match, p, gx, "point")
    if 18 < dgoal < 36 and z_off < 12 and match.rng.random() < 0.28 * skill:
        return _shot(match, p, gx, "point")

    # Don't solo the ball into a cul-de-sac. Release it.
    if getattr(p, "carry_t", 0) > 2.4 or (pressed and dgoal > 16):
        kick_mate = _best_kick_mate(match, p)
        hand_mate = _best_hand_mate(match, p)
        if hand_mate is not None and 6 < dist(p.x, p.z, hand_mate.x, hand_mate.z) < 16:
            return _hold(p.x + sign * 3, p.z, True, "hand", (hand_mate.x + sign * 2, hand_mate.z), 1.3, 0.55)
        if kick_mate is not None:
            return _hold(
                p.x + sign * 2, p.z, True, "kick",
                (kick_mate.x + kick_mate.vx * 0.3, kick_mate.z + kick_mate.vz * 0.3),
                1.8, 0.66,
            )
        if dgoal < 55 and z_off < 20:
            return _shot(match, p, gx, "point" if dgoal > 16 else "goal")
        return _hold(p.x, p.z, False, "kick", (p.x + sign * 28, CENTER_Z), 1.7, 0.64)

    if p.steps >= 3.15 and p.solo_lock <= 0:
        return _carry_point(match, p, action="solo", sprint=True)

    kick_mate = _best_kick_mate(match, p)
    if kick_mate is not None and match.rng.random() < 0.38:
        kind = "kick" if dist(p.x, p.z, kick_mate.x, kick_mate.z) > 14 else "hand"
        return _hold(
            p.x + sign * 3, p.z, True, kind,
            (kick_mate.x + sign * 2.5, kick_mate.z),
            1.35 if kind == "hand" else 1.85, 0.62,
        )
    hand_mate = _best_hand_mate(match, p)
    if hand_mate is not None and match.rng.random() < 0.45:
        return _hold(p.x + sign, p.z, False, "hand", (hand_mate.x, hand_mate.z), 1.3, 0.5)

    if pressed and od < 1.6 and dgoal > 18:
        away = _evade_point(match, p, opp)
        return _hold(away[0], away[1], True, "sidestep" if match.rng.random() < 0.3 else None, away, 1.0, 0.4)
    return _carry_point(match, p, action=None, sprint=True)


def _carry_point(match, p, action, sprint):
    sign = match.attack_sign(p.team)
    # Carry on the angle, toward the corridor, not in a dead straight line.
    tx = p.x + sign * 8.0
    tz = p.z + (CENTER_Z - p.z) * 0.18
    tz = max(6.0, min(PITCH_W - 6.0, tz))
    tx = max(2.0, min(PITCH_L - 2.0, tx))
    return _hold(tx, tz, sprint, action, (tx, tz), 1.1, 0.5)


def _evade_point(match, p, opp):
    sign = match.attack_sign(p.team)
    if opp is None:
        return p.x + sign * 4, p.z
    # Away from the opponent, still forward if possible.
    ax, az = p.x - opp.x, p.z - opp.z
    mag = math.hypot(ax, az) or 1.0
    return (
        max(2.0, min(PITCH_L - 2.0, p.x + ax / mag * 3.5 + sign * 2.0)),
        max(3.0, min(PITCH_W - 3.0, p.z + az / mag * 3.5)),
    )


def _shot(match, p, gx, kind):
    sign = match.attack_sign(p.team)
    # Aim just inside a post for a goal, over the bar for a point.
    if kind == "goal":
        spread = 1.6 * (1.15 - p.kick)
        tz = CENTER_Z + match.rng.uniform(-spread, spread)
        ty = 0.85 + match.rng.uniform(0.0, 0.7)
        power = 0.72
    else:
        spread = 1.3 * (1.2 - p.kick)
        tz = CENTER_Z + match.rng.uniform(-spread, spread)
        ty = 3.55
        power = 0.78 if dist_to_goal(p.x, p.z, gx) > 38 else 0.66
    # Face the goal while striking.
    # Aim through the endline so the score can actually be registered.
    return _hold(p.x, p.z, False, "kick", (gx + sign * 2.4, tz), ty, power)


def _lane_clear(match, p, gx) -> bool:
    sign = match.attack_sign(p.team)
    for o in _opps(match, p):
        along = (o.x - p.x) * sign
        if 0.4 < along < 6.5 and abs(o.z - p.z) < 1.3:
            return False
    return True


def _best_kick_mate(match, p):
    sign = match.attack_sign(p.team)
    gx = match.attack_goal_x(p.team)
    best, bs = None, 8.0
    for m in _mates(match, p):
        if m.role == "gk":
            # Only find the keeper if the pass would be legal.
            if not match.gk_pass_would_be_legal(p, m):
                continue
        along = (m.x - p.x) * sign
        if along < 6 or along > 48:
            continue
        d = dist(p.x, p.z, m.x, m.z)
        opp, od = _nearest(_opps(match, p), m.x, m.z)
        # Bonus for a kick that can become an advanced mark.
        mark_bonus = 0.0
        md = dist_to_goal(m.x, m.z, gx)
        if md <= 20 and dist_to_goal(p.x, p.z, gx) >= 45:
            mark_bonus = 8.0
        if md < 18 and od > 2.5:
            mark_bonus += 6.0
        score = od + mark_bonus + along * 0.15 - abs(m.z - p.z) * 0.04
        if score > bs:
            best, bs = m, score
    return best


def _best_hand_mate(match, p):
    sign = match.attack_sign(p.team)
    best, bs = None, 4.0
    for m in _mates(match, p):
        if m.role == "gk" and not match.gk_pass_would_be_legal(p, m):
            continue
        d = dist(p.x, p.z, m.x, m.z)
        if d < 4 or d > 18:
            continue
        along = (m.x - p.x) * sign
        if along < -2:
            continue
        opp, od = _nearest(_opps(match, p), m.x, m.z)
        score = od + along * 0.3 - d * 0.1
        if score > bs:
            best, bs = m, score
    return best


def _off_ball(match, p) -> dict:
    b = match.ball
    holder = b.holder
    my_ball = holder is not None and holder.team == p.team
    opp_ball = holder is not None and holder.team != p.team
    loose = holder is None
    tx, tz = _shape_target(match, p, possess=my_ball or (loose and match.possession_team == p.team))
    sprint = False
    action = None
    aim = None

    # Closest player to a loose ball attacks it. Others hold shape.
    if loose and b.y < 3.2:
        me, myd = p, dist(p.x, p.z, b.x, b.z)
        rival, rd = _nearest(match.players, b.x, b.z, ignore=None)
        # Only the nearest teammate (or overall nearest) hunts the ball.
        nearest_mate, nmd = _nearest(_mates(match, p) + [p], b.x, b.z)
        if nearest_mate is p and myd < 18:
            # Lead the bouncing ball.
            tx = max(1.5, min(PITCH_L - 1.5, b.x + b.vx * 0.25))
            tz = max(1.5, min(PITCH_W - 1.5, b.z + b.vz * 0.25))
            sprint = myd > 2.5
            if b.y > 1.6 and myd < 3.5:
                action = "jump"

    if opp_ball:
        me_d = dist(p.x, p.z, holder.x, holder.z)
        chaser, cd = _nearest(_mates(match, p) + [p], holder.x, holder.z)
        if chaser is p and me_d < 22:
            # Press from the side, not straight up the back — that is a foul.
            face = holder.facing
            side = face + math.pi / 2
            tx = holder.x + math.cos(side) * 1.05 - math.cos(face) * 0.2
            tz = holder.z + math.sin(side) * 1.05 - math.sin(face) * 0.2
            sprint = me_d > 2.0
            if me_d < 1.55 and p.action_cd <= 0 and holder.protect <= 0:
                action = "tackle"
            if holder.kick_t > 0.05 and me_d < 2.4:
                action = "block"
        else:
            # Mark a nearby opponent, but don't abandon the shape pins.
            mark, md = _nearest(_opps(match, p), tx, tz)
            if mark and md < 12 and p.role not in ("gk",):
                tx = tx * 0.55 + mark.x * 0.45
                tz = tz * 0.55 + mark.z * 0.45

    if my_ball and holder is not p:
        # Support angle. Two nearest make a hand-pass option; the rest stay.
        ranked = sorted(_mates(match, holder), key=lambda m: dist(m.x, m.z, holder.x, holder.z))
        if p in ranked[:3] and p.role not in ("rcb", "fb", "lcb", "gk"):
            sign = match.attack_sign(p.team)
            tx = holder.x + sign * (14 if p in ranked[:1] else 9)
            tz = holder.z + (8 if p.pid % 2 == 0 else -8)
            sprint = True
        # Call-for-ball is human only.

    # Human teammate: don't crowd them.
    if match.human_team == p.team and match.controlled_player() is not None:
        ctrl = match.controlled_player()
        if ctrl is not p and dist(p.x, p.z, tx, tz) < 2.5 and dist(tx, tz, ctrl.x, ctrl.z) < 3:
            tx += 3.5

    tx = max(1.2, min(PITCH_L - 1.2, tx))
    tz = max(1.2, min(PITCH_W - 1.2, tz))
    return _hold(tx, tz, sprint, action, aim, 1.2, 0.5)
