"""Pure 2026 Gaelic football rule helpers. No pygame, no match state."""

from __future__ import annotations

import math

from peil26.settings import (
    ARC_R,
    CENTER_Z,
    CROSSBAR,
    GOAL_HALF_W,
    LARGE_DEPTH,
    LARGE_HALF_W,
    PITCH_L,
    PITCH_W,
    SMALL_DEPTH,
    SMALL_HALF_W,
    SOLO_GO_R,
)


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def dist(x1: float, z1: float, x2: float, z2: float) -> float:
    return math.hypot(x1 - x2, z1 - z2)


def dist_to_goal(x: float, z: float, goal_x: float) -> float:
    return math.hypot(x - goal_x, z - CENTER_Z)


def depth_from_goal(x: float, goal_x: float) -> float:
    return x if goal_x < 1.0 else (PITCH_L - x)


def in_small_square(x: float, z: float, goal_x: float) -> bool:
    d = depth_from_goal(x, goal_x)
    return 0.0 <= d <= SMALL_DEPTH and abs(z - CENTER_Z) <= SMALL_HALF_W


def in_large_rectangle(x: float, z: float, goal_x: float) -> bool:
    d = depth_from_goal(x, goal_x)
    return 0.0 <= d <= LARGE_DEPTH and abs(z - CENTER_Z) <= LARGE_HALF_W


def on_or_outside_arc(x: float, z: float, goal_x: float) -> bool:
    """A foot on the 40 m arc still counts as a two-point strike."""
    return dist_to_goal(x, z, goal_x) >= ARC_R - 0.12


def inside_20(x: float, goal_x: float) -> bool:
    return depth_from_goal(x, goal_x) <= 20.0


def on_or_beyond_45_from_goal(x: float, goal_x: float) -> bool:
    """True when x is on the 45 or further from that goal (toward midfield / beyond)."""
    return depth_from_goal(x, goal_x) >= 45.0 - 0.15


def between_posts(z: float, margin: float = 0.0) -> bool:
    return abs(z - CENTER_Z) <= GOAL_HALF_W + margin


def structure_ok(own_half: int, opp_outfield: int, active: int) -> bool:
    """4 in the defensive half, 3 outfield in the attacking half.

    Suspended if a team has been reduced below 7, because the numbers
    cannot be met after multiple sendings-off.
    """
    if active < 7:
        return True
    return own_half >= 4 and opp_outfield >= 3


def two_point_strike(kick_type: str, kicker_dist: float, set_kind: str | None) -> bool:
    """Whether the strike itself is a two-point attempt.

    A later touch by a teammate reduces a score to one. A defender's
    touch does not. 45s and sideline kicks are always one.
    """
    if kick_type in ("hand", "fist"):
        return False
    if set_kind in ("fortyfive", "sideline", "45"):
        return False
    if kick_type in ("45", "sideline"):
        return False
    return kicker_dist >= ARC_R - 0.12


def point_is_legal_kick(kick_type: str) -> bool:
    return kick_type not in ("hand", "fist")


def classify_crossing(
    y: float,
    z: float,
    kick_type: str,
    kicker_dist: float,
    teammate_touched: bool,
    set_kind: str | None,
    square: bool,
) -> tuple[str, int]:
    """Classify a ball that has crossed an endline.

    Returns (result, column_value). A goal returns ('goal', 3). A point
    returns ('point', 1) or ('point', 2) for a two-pointer. The two is
    added to the points column, not kept as a separate scoreboard figure.
    """
    z_off = abs(z - CENTER_Z)
    inside = z_off < GOAL_HALF_W - 0.08
    on_post = abs(z_off - GOAL_HALF_W) <= 0.13 and 0.0 <= y <= 8.0
    if on_post and not (inside and y > CROSSBAR + 0.18):
        return "post", 0
    if inside and abs(y - CROSSBAR) <= 0.10:
        return "crossbar", 0
    if inside and 0.04 < y < CROSSBAR - 0.08:
        if square:
            return "square", 0
        return "goal", 3
    if inside and y > CROSSBAR + 0.08:
        if not point_is_legal_kick(kick_type):
            return "wide", 0
        if square:
            return "square", 0
        if two_point_strike(kick_type, kicker_dist, set_kind) and not teammate_touched:
            return "point", 2
        return "point", 1
    return "wide", 0


def mark_type(
    kick_type: str,
    origin_x: float,
    catch_x: float,
    attack_goal_x: float,
    bounced: bool,
    kickout_goal_x: float | None,
    set_kind: str | None = None,
    from_mark: bool = False,
) -> str | None:
    """Return 'advanced', 'kickout', or None.

    Kick-out mark: a clean catch from a kick-out on or past the 45.
    Advanced mark: a clean catch on or inside the opposition 20 from a
    kick in play, or from a kick-out mark, delivered on or beyond the
    opposition 45. A normal free, 45, sideline or penalty does not
    create an advanced mark. A hand pass never does.
    """
    if bounced or kick_type in ("hand", "fist", None):
        return None
    if kick_type == "kickout" and kickout_goal_x is not None:
        if on_or_beyond_45_from_goal(catch_x, kickout_goal_x):
            return "kickout"
        return None
    if kick_type in ("45", "sideline", "penalty"):
        return None
    if set_kind in ("free", "penalty", "fortyfive", "sideline", "45", "kickout") and not from_mark:
        return None
    if inside_20(catch_x, attack_goal_x) and on_or_beyond_45_from_goal(origin_x, attack_goal_x):
        if depth_from_goal(origin_x, attack_goal_x) + 0.2 < depth_from_goal(catch_x, attack_goal_x):
            return None
        if depth_from_goal(origin_x, attack_goal_x) > depth_from_goal(catch_x, attack_goal_x):
            return "advanced"
    return None


def gk_receive_legal(gk_in_opp_half: bool, both_in_large: bool) -> bool:
    return gk_in_opp_half or both_in_large


def solo_and_go_ok(
    spot_x: float,
    spot_z: float,
    new_x: float,
    new_z: float,
    attack_sign: float,
    attack_goal_x: float,
) -> tuple[bool, str]:
    """Solo-and-go must be immediate, within 4 m, not backwards, not inside the 20."""
    if inside_20(spot_x, attack_goal_x):
        return False, "inside20"
    if dist(spot_x, spot_z, new_x, new_z) > SOLO_GO_R + 0.25:
        return False, "too_far"
    forward = (new_x - spot_x) * attack_sign
    if forward < -0.35:
        return False, "backwards"
    return True, "ok"


def card_result(yellows: int, blacks: int, infraction: str) -> str:
    """Return the card actually shown: yellow, black, or red.

    A second yellow is red. A second black is red. A black after a
    yellow is red. A yellow after a black is red.
    """
    if infraction == "red":
        return "red"
    if infraction == "yellow":
        if yellows >= 1 or blacks >= 1:
            return "red"
        return "yellow"
    if infraction == "black":
        if yellows >= 1 or blacks >= 1:
            return "red"
        return "black"
    return infraction


def hooter_score_stands(in_flight_at_hooter: bool, attacker_touched_after: bool) -> bool:
    return in_flight_at_hooter and not attacker_touched_after


def ballistics(x: float, y: float, z: float, tx: float, ty: float, tz: float, flight: float) -> tuple[float, float, float]:
    flight = max(0.18, flight)
    vx = (tx - x) / flight
    vz = (tz - z) / flight
    vy = (ty - y + 0.5 * 9.8 * flight * flight) / flight
    return vx, vy, vz


def on_pitch(x: float, z: float, margin: float = 0.0) -> bool:
    return margin <= x <= PITCH_L - margin and margin <= z <= PITCH_W - margin
