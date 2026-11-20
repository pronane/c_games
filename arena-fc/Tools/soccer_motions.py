"""Soccer move library for the Sprite Forge -> Arena FC rig pipeline.

The shipped Sprite Forge v11.13 motion library already has the building blocks
(idle, walk, run, sprint, kick, pass, shoot, tackle, goalkeeper dives, ...).
This module gives Arena FC a *named clip for every game action* and adds the
soccer-specific poses that the generic library does not have: shielding, slide
tackle, volley, header, chest trap, throw-in, shoulder charge and a goalkeeper
ready stance.  All clips are procedural joint angles, CC0-compatible, and use
the same semantic pose channels as `sforge.rig.evaluate`.

    from soccer_motions import register, ALL_CLIPS, ACTION_ALIASES
    register()
    rig = rigrec.from_mannequin(clips=ALL_CLIPS)
"""
from __future__ import annotations

import math

from sforge.motions import (
    CROUCH,
    FIGHT,
    HOLD,
    K,
    LIB,
    M,
    P,
    READY,
    STAND,
    idle_func,
    loco,
)

# ---------------------------------------------------------------------------
# Custom soccer poses.  Angles are degrees in Sprite Forge's semantic channels.
# ---------------------------------------------------------------------------

def _shield(t: float):
    s = math.sin(2 * math.pi * t)
    p = P(READY)
    p.update(
        hips=(8, -s * 4, 0), chest=(-6, 0, 0), neck=(-10, 0, 0),
        leg_L=(26, 10, 0), leg_R=(18, 10, 0), knee_L=48, knee_R=42,
        arm_L=(42, 34 + 4 * s, 0), arm_R=(42, 34 - 4 * s, 0),
        elbow_L=72, elbow_R=72, flat=1.0,
    )
    return p


def _dribble(t: float):
    # Quick feet, low centre of gravity, ball kept close.  Root travel is left
    # to the match engine; this is an in-place close-control loop. Keep the
    # arms compact here too; the generic carry loop lifts them as if protecting
    # a ball at chest height, which is not the close-control dribble pose.
    return _soccer_loco(18, 52, 26, 58, 12, air=0.0)(t)


def _keeper_ready(t: float):
    s = math.sin(2 * math.pi * t)
    p = P(CROUCH)
    p.update(
        hips=(22, 0, 0), spine=(10, 0, 0), chest=(6, 0, 0), neck=(-18, 0, 0),
        arm_L=(48, 28 + 5 * s, 0), arm_R=(48, 28 - 5 * s, 0),
        elbow_L=64, elbow_R=64, knee_L=112, knee_R=108, flat=1.0,
    )
    return p


# ---------------------------------------------------------------------------
# Phase 1.3 archetype locomotion presets (FC 26-style movement types).
# Each preset is a `loco()` parameter set; the runtime rig applies the same
# biases (stride/cadence/lean) via CharacterSpec.Archetype.  Keeping the
# generation presets and the runtime biases in sync is what makes the three
# archetypes visibly distinct.
# ---------------------------------------------------------------------------

ARCHETYPE_PRESETS = {
    # Explosive: short stride, high cadence, forward lean, quick accel.
    "explosive": dict(stride=14, knee=58, arm=30, elbow=62, lean=18, air=0.0,
                      carry=0.0, guard=0.0, bounce=0.10),
    # Lengthy: long stride, low cadence, upright, covers ground.
    "lengthy": dict(stride=26, knee=44, arm=22, elbow=50, lean=10, air=0.0,
                    carry=0.0, guard=0.0, bounce=0.04),
    # Controlled: balanced stride/cadence/lean.
    "controlled": dict(stride=20, knee=50, arm=26, elbow=56, lean=12, air=0.0,
                       carry=0.0, guard=0.0, bounce=0.06),
}


def archetype_loco(archetype: str):
    """Return a loco() motion function for the named archetype (Phase 1.3)."""
    p = ARCHETYPE_PRESETS[archetype]
    return loco(p["stride"], p["knee"], p["arm"], p["elbow"], p["lean"],
                p["air"], p["carry"], p["guard"], p["bounce"])


def _soccer_loco(stride, knee, arm, elbow, lean, air, arm_out=-55):
    """Football gait with the upper arms held down/out of the hands-up pose."""
    base = loco(stride, knee, arm, elbow, lean, air=air)
    def sample(t):
        pose = base(t)
        for side in ("L", "R"):
            f, _out, twist = pose["arm_" + side]
            pose["arm_" + side] = (f, arm_out, twist)
        return pose
    return sample


# ---------------------------------------------------------------------------
# Phase 1.4 directional locomotion: strafe (sideways), backpedal (backwards)
# and jockey (defensive shuffle).  These are in-place loops; the match engine
# moves the root, the clip provides the leg/arm pattern.  Built from loco()
# with guard/carry offsets so the body faces one way while travelling
# another — the core of the blend-space directional set.
# ---------------------------------------------------------------------------

def _strafe(side: int):
    """Sideways shuffle: body faces forward, feet step laterally."""
    def f(t: float):
        p = loco(12, 54, 34, 66, 6, 0.0, 0.0, 0.0, 0.05)(t)
        s = math.sin(2 * math.pi * t)
        # Lateral weight shift + arms out for balance.
        p.update(hips=(4, side * 6 * s, side * 4), chest=(2, side * 4 * s, 0),
                 arm_L=(30, 44, 0), arm_R=(30, 44, 0), elbow_L=58, elbow_R=58)
        return p
    return f


def _backpedal(t: float):
    """Backwards run: high knees, upright, arms pumping in reverse."""
    p = loco(16, 56, 30, 60, -4, 0.0, 0.0, 0.0, 0.05)(t)
    p.update(hips=(-6, 0, 0), chest=(-4, 0, 0), neck=(8, 0, 0))
    return p


def _jockey(t: float):
    """Defensive jockey: low, wide stance, short choppy steps, arms ready."""
    s = math.sin(2 * math.pi * t)
    p = P(CROUCH)
    p.update(
        hips=(18, 0, side_sign(s) * 4), spine=(8, 0, 0), chest=(4, 0, 0),
        neck=(-12, 0, 0),
        leg_L=(38, 14, 0), leg_R=(38, -14, 0), knee_L=96, knee_R=96,
        arm_L=(52, 30, 0), arm_R=(52, 30, 0), elbow_L=70, elbow_R=70,
        flat=1.0,
    )
    return p


def side_sign(x: float) -> int:
    return 1 if x >= 0 else -1


CUSTOM = {
    "soccer_idle_ready": dict(category="Soccer", desc="athletic ready stance", loop=True,
                              func=idle_func(P(READY, knee_L=30, knee_R=28), 0.8)),
    "soccer_keeper_ready": dict(category="Goalkeeper", desc="keeper set stance", loop=True,
                                func=_keeper_ready),
    "soccer_dribble": dict(category="Ball", desc="close-control dribble loop", loop=True,
                           func=_dribble),
    "soccer_shield": dict(category="Ball", desc="shield the ball with the body", loop=True,
                          func=_shield),
    # Phase 1.4 directional locomotion set.
    "soccer_strafe_l": dict(category="Locomotion", desc="strafe left", loop=True,
                            func=_strafe(-1)),
    "soccer_strafe_r": dict(category="Locomotion", desc="strafe right", loop=True,
                            func=_strafe(1)),
    "soccer_backpedal": dict(category="Locomotion", desc="backpedal", loop=True,
                             func=_backpedal),
    "soccer_jockey": dict(category="Defence", desc="defensive jockey", loop=True,
                          func=_jockey),
    # Compact football running: the generic Sprite Forge run/sprint presets
    # swing the upper arms 42-62 degrees and flex the elbows 80-92 degrees.
    # Retargeted to this rig those values lift the hands out beside the head.
    # Keep the arms pumping close to the torso, with a relaxed elbow bend.
    "soccer_jog": dict(category="Locomotion", desc="compact soccer jog", loop=True,
                        func=_soccer_loco(25, 62, 18, 44, 8, air=0.01)),
    "soccer_run": dict(category="Locomotion", desc="compact soccer run", loop=True,
                        func=_soccer_loco(35, 78, 22, 48, 11, air=0.025)),
    "soccer_sprint": dict(category="Locomotion", desc="compact soccer sprint", loop=True,
                           func=_soccer_loco(46, 98, 26, 52, 15, air=0.06)),
    # Feet-first slide.  The old keys only reclined the pelvis ~10 deg, so the
    # feet stayed the lowest point and the ground constraint left the player in
    # a crouch with one leg out.  Now the pelvis reclines ~50 deg, the lead leg
    # goes straight out along the turf, the trailing leg folds under and the
    # support hand goes down behind - the ground constraint lays the body on
    # the grass.  Match movement supplies the travel (no root run-up here).
    "soccer_slide_tackle": dict(category="Defence", desc="feet-first sliding tackle", loop=False, keys=K(
        (0.0, P(READY, arm_L=(16, -46, 0), arm_R=(16, -46, 0), elbow_L=40, elbow_R=40)),
        (0.14, P(READY, hips=(10, -4, 0), spine=(4, 0, 0), neck=(-6, 0, 0),
                 leg_L=(42, 8, 0), knee_L=64, leg_R=(8, -6, 0), knee_R=76,
                 arm_L=(20, 30, 0), arm_R=(-10, 30, 0), elbow_L=40, elbow_R=30)),
        (0.32, P(STAND, hips=(-58, -4, 52), spine=(14, 0, 0), chest=(8, 0, 0), neck=(34, 0, 0),
                 leg_L=(30, 6, 0), knee_L=6, ankle_L=-12,
                 leg_R=(-22, -6, 0), knee_R=112, ankle_R=20,
                 arm_L=(24, 34, 0), elbow_L=30, arm_R=(-38, 30, 0), elbow_R=14)),
        (0.68, P(STAND, hips=(-54, -4, 50), spine=(14, 0, 0), chest=(8, 0, 0), neck=(32, 0, 0),
                 leg_L=(28, 6, 0), knee_L=8, ankle_L=-10,
                 leg_R=(-20, -6, 0), knee_R=108, ankle_R=20,
                 arm_L=(22, 32, 0), elbow_L=30, arm_R=(-36, 30, 0), elbow_R=16)),
        (0.86, P(CROUCH, hips=(-10, 0, 0), spine=(8, 0, 0), chest=(2, 0, 0), neck=(4, 0, 0),
                 leg_L=(40, 6, 0), knee_L=70, leg_R=(20, -6, 0), knee_R=96,
                 arm_L=(14, 20, 0), arm_R=(-16, 24, 0), elbow_L=46, elbow_R=30)),
        (1.0, P(READY)))),
    "soccer_volley": dict(category="Ball", desc="first-time volley", loop=False, keys=K(
        (0.0, P(READY, ball=("world", 0, 0.55, 0.45))),
        (0.25, P(READY, hips=(-8, 0, 0), leg_R=(-52, 6, 0), knee_R=95,
                 arm_L=(64, 28, 0), arm_R=(30, 40, 0), ball=("world", 0, 0.60, 0.42))),
        (0.5, P(READY, hips=(16, 0, 0), spine=(12, 0, 0), leg_R=(72, 6, 0), knee_R=12,
                ankle_R=-24, arm_L=(38, 34, 0), arm_R=(72, 18, 0), neck=(14, 0, 0),
                ball=("foot_R",))),
        (0.72, P(READY, hips=(8, 0, 0), leg_R=(48, 6, 0), knee_R=55,
                 arm_L=(50, 24, 0), arm_R=(44, 28, 0))),
        (1.0, P(READY)))),
    "soccer_header": dict(category="Ball", desc="jump and head the ball", loop=False, keys=K(
        (0.0, P(STAND)),
        (0.2, P(CROUCH, arm_L=(-36, 12, 0), arm_R=(-36, 12, 0), elbow_L=20, elbow_R=20)),
        (0.42, P(STAND, lift=0.30, arm_L=(150, 18, 0), arm_R=(150, 18, 0),
                 elbow_L=18, elbow_R=18, neck=(-26, 0, 0), chest=(8, 0, 0))),
        (0.55, P(STAND, lift=0.34, arm_L=(120, 26, 0), arm_R=(120, 26, 0),
                 neck=(28, 0, 0), chest=(16, 0, 0), leg_L=(28, 5, 0), leg_R=(18, 5, 0))),
        (0.78, P(CROUCH, neck=(12, 0, 0), leg_L=(55, 8, 0), leg_R=(48, 8, 0))),
        (1.0, P(STAND)))),
    "soccer_chest_control": dict(category="Ball", desc="cushion an aerial ball on the chest", loop=False, keys=K(
        (0.0, P(READY, ball=("world", 0, 1.55, 0.55))),
        (0.35, P(READY, hips=(-14, 0, 0), chest=(-18, 0, 0), neck=(18, 0, 0),
                 arm_L=(52, 36, 0), arm_R=(52, 36, 0), knee_L=46, knee_R=44,
                 ball=("world", 0, 1.35, 0.40))),
        (0.55, P(READY, hips=(8, 0, 0), chest=(12, 0, 0), neck=(-10, 0, 0),
                 arm_L=(34, 22, 0), arm_R=(34, 22, 0), ball="chest")),
        (1.0, P(READY)))),
    "soccer_trap": dict(category="Ball", desc="kill a rolling ball under the boot", loop=False, keys=K(
        (0.0, P(READY, ball=("world", 0, 0.11, 0.56))),
        (0.35, P(READY, hips=(14, 0, 0), leg_R=(26, 8, 0), knee_R=42,
                 leg_L=(8, 6, 0), knee_L=24, ankle_R=28, ball=("world", 0, 0.11, 0.46))),
        (0.6, P(READY, hips=(8, 0, 0), leg_R=(18, 8, 0), knee_R=32, ankle_R=12,
                ball=("foot_R",))),
        (1.0, P(READY)))),
    "soccer_shoulder_charge": dict(category="Defence", desc="lean into a carrier to dispossess", loop=False, keys=K(
        (0.0, P(READY)),
        (0.3, P(READY, hips=(20, -10, 0), chest=(14, -8, 0), leg_L=(34, 8, 0),
                knee_L=40, arm_L=(44, 18, 0), arm_R=(30, 24, 0), pos=(0.12, 0))),
        (0.55, P(READY, hips=(28, 8, 0), chest=(18, 8, 0), leg_R=(-16, 8, 0),
                 knee_R=36, arm_L=(28, 26, 0), arm_R=(48, 16, 0), pos=(0.32, 0))),
        (0.8, P(READY, hips=(8, 0, 0), pos=(0.32, 0))),
        (1.0, P(READY, pos=(0.32, 0))))),
    "soccer_throw_in": dict(category="Restart", desc="two-hand overhead throw-in", loop=False, keys=K(
        (0.0, P(STAND, HOLD)),
        (0.28, P(STAND, hips=(-12, 0, 0), chest=(-10, 0, 0), neck=(-16, 0, 0),
                 arm_L=(168, 10, 0), arm_R=(168, 10, 0), elbow_L=24, elbow_R=24, ball="hands")),
        (0.52, P(STAND, hips=(16, 0, 0), spine=(14, 0, 0), chest=(12, 0, 0), neck=(18, 0, 0),
                 arm_L=(72, 8, 0), arm_R=(72, 8, 0), elbow_L=8, elbow_R=8, ball="hands")),
        (0.72, P(STAND, hips=(10, 0, 0), arm_L=(48, 14, 0), arm_R=(48, 14, 0))),
        (1.0, P(STAND)))),
    "soccer_toe_lift": dict(category="Ball", desc="flick the ball up with the toe", loop=False, keys=K(
        (0.0, P(READY, ball=("world", 0, 0.11, 0.48))),
        (0.4, P(READY, hips=(18, 0, 0), leg_R=(30, 8, 0), knee_R=58,
                ankle_R=-38, ball=("foot_R",))),
        (0.6, P(READY, hips=(6, 0, 0), leg_R=(42, 8, 0), knee_R=28,
                ankle_R=-42, ball=("world", 0, 0.55, 0.44))),
        (1.0, P(READY)))),
    "soccer_keeper_punch": dict(category="Goalkeeper", desc="punch a cross clear", loop=False, keys=K(
        (0.0, P(_keeper_ready(0.0))),
        (0.3, P(READY, lift=0.18, arm_L=(155, 18, 0), arm_R=(150, 18, 0),
                elbow_L=18, elbow_R=18, chest=(-10, 0, 0))),
        (0.5, P(STAND, lift=0.26, arm_L=(72, 12, 0), arm_R=(78, 12, 0),
                elbow_L=6, elbow_R=6, chest=(12, 0, 0), ball=("world", 0, 2.15, 0.55))),
        (0.75, P(CROUCH, arm_L=(60, 24, 0), arm_R=(60, 24, 0))),
        (1.0, P(_keeper_ready(0.0))))),
}

# ---------------------------------------------------------------------------
# Every clip the game can ask for.  `base` is a shipped Sprite Forge motion;
# custom names above are registered as-is.  `action` aliases are written into
# soccer_player_manifest.json so the C# / GDScript loaders stay data-driven.
# ---------------------------------------------------------------------------

CLIP_SPECS = [
    # name, base motion or None (custom), loop, category, description
    ("soccer_idle", "idle", True, "Locomotion", "standing idle"),
    ("soccer_idle_ready", None, True, "Soccer", "athletic ready stance"),
    ("soccer_walk", "walk", True, "Locomotion", "walk"),
    ("soccer_jog", None, True, "Locomotion", "compact soccer jog"),
    ("soccer_run", None, True, "Locomotion", "compact soccer run"),
    ("soccer_sprint", None, True, "Locomotion", "compact soccer sprint"),
    ("soccer_run_ball", "carry", True, "Ball", "carry the ball at pace"),
    ("soccer_dribble", None, True, "Ball", "close-control dribble"),
    ("soccer_shield", None, True, "Ball", "shield the ball"),
    ("soccer_short_pass", "low_kick_pass", False, "Ball", "short pass"),
    ("soccer_long_pass", "high_kick_pass", False, "Ball", "long pass / cross"),
    ("soccer_through_ball", "low_kick_pass", False, "Ball", "weighted through ball"),
    ("soccer_cross", "high_kick_pass", False, "Ball", "cross from wide"),
    ("soccer_shoot", "shoot_goal", False, "Ball", "shot at goal"),
    ("soccer_volley", None, False, "Ball", "first-time volley"),
    ("soccer_header", None, False, "Ball", "jump and head the ball"),
    ("soccer_chest_control", None, False, "Ball", "chest control"),
    ("soccer_trap", None, False, "Ball", "trap under the boot"),
    ("soccer_toe_lift", None, False, "Ball", "toe lift"),
    ("soccer_pickup", "pick_up_ground", False, "Ball", "pick the ball up"),
    ("soccer_tackle", "tackle", False, "Defence", "standing tackle"),
    ("soccer_slide_tackle", None, False, "Defence", "slide tackle"),
    ("soccer_shoulder_charge", None, False, "Defence", "shoulder charge"),
    ("soccer_dispossess", "tackle", False, "Defence", "win the ball back"),
    ("soccer_block", "block", False, "Defence", "block a pass or shot"),
    ("soccer_foul", "hit", False, "Contact", "fouled / flinch"),
    ("soccer_stumble", "fall", False, "Contact", "stumble"),
    ("soccer_trip", "fall", False, "Contact", "trip"),
    ("soccer_fall", "fall", False, "Contact", "fall"),
    ("soccer_get_up", "get_up", False, "Contact", "recover to feet"),
    ("soccer_knocked_down", "ko", False, "Contact", "knocked down"),
    ("soccer_pushed", "hit", False, "Contact", "pushed"),
    ("soccer_hit_react", "hit", False, "Contact", "hit reaction"),
    ("soccer_keeper_idle", "idle", True, "Goalkeeper", "keeper idle"),
    ("soccer_keeper_ready", None, True, "Goalkeeper", "keeper set stance"),
    ("soccer_keeper_catch", "catch_aerial", False, "Goalkeeper", "high catch"),
    ("soccer_keeper_ground_catch", "catch_ground", False, "Goalkeeper", "low catch"),
    ("soccer_keeper_save", "gk_save", False, "Goalkeeper", "save"),
    ("soccer_keeper_dive_left", "gk_dive_left", False, "Goalkeeper", "dive left"),
    ("soccer_keeper_dive_right", "gk_dive_right", False, "Goalkeeper", "dive right"),
    ("soccer_keeper_dive_high", "leap_catch", False, "Goalkeeper", "high dive"),
    ("soccer_keeper_punch", None, False, "Goalkeeper", "punch clear"),
    ("soccer_keeper_throw", "gk_throw_out", False, "Goalkeeper", "throw out"),
    ("soccer_keeper_kick", "high_kick_pass", False, "Goalkeeper", "goal kick"),
    ("soccer_kick_place", "low_kick_pass", False, "Restart", "placed kick"),
    ("soccer_kick_run", "shoot_goal", False, "Restart", "running kick"),
    ("soccer_kick_out", "high_kick_pass", False, "Restart", "kick out"),
    ("soccer_drop_kick", "high_kick_pass", False, "Restart", "drop kick"),
    ("soccer_throw_in", None, False, "Restart", "throw-in"),
    ("soccer_corner_kick", "high_kick_pass", False, "Restart", "corner"),
    ("soccer_free_kick", "shoot_goal", False, "Restart", "free kick"),
    ("soccer_penalty_kick", "shoot_goal", False, "Restart", "penalty"),
    ("soccer_goal_kick", "high_kick_pass", False, "Restart", "goal kick"),
    ("soccer_strafe_l", None, True, "Locomotion", "strafe left"),
    ("soccer_strafe_r", None, True, "Locomotion", "strafe right"),
    ("soccer_backpedal", None, True, "Locomotion", "backpedal"),
    ("soccer_jockey", None, True, "Defence", "defensive jockey"),
    ("soccer_sidestep", "sidestep", False, "Locomotion", "sidestep"),
    ("soccer_juke_feint", "juke_feint", False, "Locomotion", "feint"),
    ("soccer_stop", "stop", False, "Locomotion", "stop"),
    ("soccer_turn", "change_direction", False, "Locomotion", "turn / cut"),
    ("soccer_change_direction", "change_direction", False, "Locomotion", "change direction"),
    ("soccer_spin", "spin", False, "Locomotion", "spin move"),
    ("soccer_celebrate", "celebrate_goal", False, "Celebration", "goal celebration"),
    ("soccer_celebrate_jump", "jump", False, "Celebration", "celebration jump"),
    ("soccer_taunt", "taunt", False, "Celebration", "taunt"),
    ("soccer_victory", "victory", False, "Celebration", "victory pose"),
    ("soccer_hand_pass", "hand_pass", False, "Ball", "hand pass (Gaelic-style)"),
    ("soccer_solo", "bounce_solo", True, "Ball", "solo / bounce"),
    ("soccer_fist_pass", "fist_pass", False, "Ball", "fist pass"),
    ("soccer_fist_shoot", "fist_shoot", False, "Ball", "fist shot"),
]

# Match-engine / control actions -> clip name.  Keys cover the C# PlayerState
# Action strings, the pad/keyboard actions and the restart phases.
ACTION_ALIASES = {
    "idle": "soccer_idle",
    "ready": "soccer_idle_ready",
    "walk": "soccer_walk",
    "jog": "soccer_jog",
    "run": "soccer_run",
    "sprint": "soccer_sprint",
    "dribble": "soccer_dribble",
    "shield": "soccer_shield",
    "run_ball": "soccer_run_ball",
    "kick": "soccer_kick_place",
    "pass": "soccer_short_pass",
    "short_pass": "soccer_short_pass",
    "long_pass": "soccer_long_pass",
    "long_ball": "soccer_long_pass",
    "through": "soccer_through_ball",
    "through_ball": "soccer_through_ball",
    "cross": "soccer_cross",
    "shoot": "soccer_shoot",
    "volley": "soccer_volley",
    "header": "soccer_header",
    "chest_control": "soccer_chest_control",
    "trap": "soccer_trap",
    "toe_lift": "soccer_toe_lift",
    "pickup": "soccer_pickup",
    "catch": "soccer_keeper_catch",
    "tackle": "soccer_tackle",
    "slide": "soccer_slide_tackle",
    "slide_tackle": "soccer_slide_tackle",
    "shoulder_charge": "soccer_shoulder_charge",
    "dispossess": "soccer_dispossess",
    "block": "soccer_block",
    # The fouled player goes down (soccer_foul is an arms-up appeal and was
    # what showed at every free kick).
    "foul": "soccer_trip",
    "stumble": "soccer_stumble",
    "trip": "soccer_trip",
    "fall": "soccer_fall",
    "get_up": "soccer_get_up",
    "knocked_down": "soccer_knocked_down",
    "pushed": "soccer_pushed",
    "hit_react": "soccer_hit_react",
    "dive": "soccer_keeper_dive_left",
    "save": "soccer_keeper_save",
    "parry": "soccer_keeper_save",
    "keeper_idle": "soccer_keeper_idle",
    "keeper_ready": "soccer_keeper_ready",
    "keeper_catch": "soccer_keeper_catch",
    "keeper_ground_catch": "soccer_keeper_ground_catch",
    "keeper_save": "soccer_keeper_save",
    "keeper_dive_left": "soccer_keeper_dive_left",
    "keeper_dive_right": "soccer_keeper_dive_right",
    "keeper_dive_high": "soccer_keeper_dive_high",
    "keeper_punch": "soccer_keeper_punch",
    "keeper_throw": "soccer_keeper_throw",
    "keeper_kick": "soccer_keeper_kick",
    "kick_place": "soccer_kick_place",
    "kick_run": "soccer_kick_run",
    "kick_out": "soccer_kick_out",
    "drop_kick": "soccer_drop_kick",
    "throw_in": "soccer_throw_in",
    "corner_kick": "soccer_corner_kick",
    "free_kick": "soccer_free_kick",
    "penalty_kick": "soccer_penalty_kick",
    "goal_kick": "soccer_goal_kick",
    "sidestep": "soccer_sidestep",
    "strafe_l": "soccer_strafe_l",
    "strafe_r": "soccer_strafe_r",
    "strafe": "soccer_sidestep",
    "backpedal": "soccer_backpedal",
    "jockey": "soccer_jockey",
    "juke_feint": "soccer_juke_feint",
    "stop": "soccer_stop",
    "turn": "soccer_turn",
    "cut": "soccer_change_direction",
    "strafe": "soccer_sidestep",
    "change_direction": "soccer_change_direction",
    "spin": "soccer_spin",
    "celebrate": "soccer_celebrate",
    "celebrate_jump": "soccer_celebrate_jump",
    "taunt": "soccer_taunt",
    "victory": "soccer_victory",
    "hand_pass": "soccer_hand_pass",
    "solo": "soccer_solo",
    "fist_pass": "soccer_fist_pass",
    "fist_shoot": "soccer_fist_shoot",
}

ALL_CLIPS = [c[0] for c in CLIP_SPECS]
LOOP_CLIPS = {c[0] for c in CLIP_SPECS if c[2]}
CLIP_CATEGORIES = {c[0]: c[3] for c in CLIP_SPECS}
CLIP_DESCRIPTIONS = {c[0]: c[4] for c in CLIP_SPECS}
CLIP_SOURCES = {c[0]: (c[1] or "soccer_motions.CUSTOM") for c in CLIP_SPECS}

# ---------------------------------------------------------------------------
# Phase 0 event frames (fractions of clip duration, 0..1; -1 = none).
# Mirrors sprite_forge/game_packs/soccer.json events (ball_contact frame,
# footsteps) but as fractions so they survive the 31-frame @30fps bake.
# The sim (Match.cs) releases/captures the ball at ball_contact * ActionDuration;
# the animation layer speeds the clip so visual contact aligns.
# ---------------------------------------------------------------------------

def _ev(ball_contact=-1.0, footsteps=(), hit_start=-1.0, hit_end=-1.0):
    return {"ball_contact": float(ball_contact), "footsteps": [float(x) for x in footsteps],
            "hit_start": float(hit_start), "hit_end": float(hit_end)}


_LOCO_STEPS = (0.25, 0.75)
CLIP_EVENTS = {
    "soccer_idle": _ev(),
    "soccer_idle_ready": _ev(),
    "soccer_walk": _ev(footsteps=_LOCO_STEPS),
    "soccer_jog": _ev(footsteps=_LOCO_STEPS),
    "soccer_run": _ev(footsteps=_LOCO_STEPS),
    "soccer_sprint": _ev(footsteps=_LOCO_STEPS),
    "soccer_run_ball": _ev(footsteps=_LOCO_STEPS),
    "soccer_dribble": _ev(footsteps=_LOCO_STEPS),
    "soccer_shield": _ev(),
    "soccer_strafe_l": _ev(footsteps=_LOCO_STEPS),
    "soccer_strafe_r": _ev(footsteps=_LOCO_STEPS),
    "soccer_backpedal": _ev(footsteps=_LOCO_STEPS),
    "soccer_jockey": _ev(footsteps=_LOCO_STEPS),
    "soccer_short_pass": _ev(ball_contact=0.50),
    "soccer_long_pass": _ev(ball_contact=0.50),
    "soccer_through_ball": _ev(ball_contact=0.50),
    "soccer_cross": _ev(ball_contact=0.50),
    "soccer_shoot": _ev(ball_contact=0.50),
    "soccer_volley": _ev(ball_contact=0.50),
    "soccer_header": _ev(ball_contact=0.55),
    "soccer_chest_control": _ev(ball_contact=0.55),
    "soccer_trap": _ev(ball_contact=0.60),
    "soccer_toe_lift": _ev(ball_contact=0.40),
    "soccer_pickup": _ev(ball_contact=0.60),
    "soccer_tackle": _ev(hit_start=0.30, hit_end=0.60),
    "soccer_slide_tackle": _ev(hit_start=0.30, hit_end=0.65),
    "soccer_shoulder_charge": _ev(hit_start=0.35, hit_end=0.60),
    "soccer_dispossess": _ev(hit_start=0.30, hit_end=0.60),
    "soccer_block": _ev(ball_contact=0.50),
    "soccer_foul": _ev(hit_start=0.30, hit_end=0.60),
    "soccer_stumble": _ev(),
    "soccer_trip": _ev(),
    "soccer_fall": _ev(),
    "soccer_get_up": _ev(),
    "soccer_knocked_down": _ev(),
    "soccer_pushed": _ev(),
    "soccer_hit_react": _ev(),
    "soccer_keeper_idle": _ev(),
    "soccer_keeper_ready": _ev(),
    "soccer_keeper_catch": _ev(ball_contact=0.50),
    "soccer_keeper_ground_catch": _ev(ball_contact=0.50),
    "soccer_keeper_save": _ev(ball_contact=0.50),
    "soccer_keeper_dive_left": _ev(ball_contact=0.50),
    "soccer_keeper_dive_right": _ev(ball_contact=0.50),
    "soccer_keeper_dive_high": _ev(ball_contact=0.50),
    "soccer_keeper_punch": _ev(ball_contact=0.50),
    "soccer_keeper_throw": _ev(ball_contact=0.50),
    "soccer_keeper_kick": _ev(ball_contact=0.50),
    "soccer_kick_place": _ev(ball_contact=0.50),
    "soccer_kick_run": _ev(ball_contact=0.50),
    "soccer_kick_out": _ev(ball_contact=0.50),
    "soccer_drop_kick": _ev(ball_contact=0.50),
    "soccer_throw_in": _ev(ball_contact=0.52),
    "soccer_corner_kick": _ev(ball_contact=0.50),
    "soccer_free_kick": _ev(ball_contact=0.50),
    "soccer_penalty_kick": _ev(ball_contact=0.50),
    "soccer_goal_kick": _ev(ball_contact=0.50),
    "soccer_sidestep": _ev(footsteps=(0.50,)),
    "soccer_juke_feint": _ev(),
    "soccer_stop": _ev(footsteps=(0.50,)),
    "soccer_turn": _ev(footsteps=(0.50,)),
    "soccer_change_direction": _ev(footsteps=(0.50,)),
    "soccer_spin": _ev(footsteps=(0.50,)),
    "soccer_celebrate": _ev(),
    "soccer_celebrate_jump": _ev(),
    "soccer_taunt": _ev(),
    "soccer_victory": _ev(),
    "soccer_hand_pass": _ev(ball_contact=0.50),
    "soccer_solo": _ev(footsteps=_LOCO_STEPS),
    "soccer_fist_pass": _ev(ball_contact=0.50),
    "soccer_fist_shoot": _ev(ball_contact=0.50),
}
# Every clip must have an event entry (default: no events).
for _n in ALL_CLIPS:
    CLIP_EVENTS.setdefault(_n, _ev())


def register() -> None:
    """Register every soccer clip in `sforge.motions.LIB`. Idempotent."""
    for name, spec in CUSTOM.items():
        if name in LIB:
            continue
        M(name, spec["category"], spec["desc"],
          keys=spec.get("keys"), func=spec.get("func"), loop=spec.get("loop", False))
    for name, base, loop, category, desc in CLIP_SPECS:
        if name in LIB:
            continue
        if base is None:
            raise KeyError("custom clip %s missing from CUSTOM" % name)
        src = LIB[base]
        M(name, category, desc, keys=src.keys, func=src.func, loop=loop)
    missing = [n for n in ALL_CLIPS if n not in LIB]
    if missing:
        raise RuntimeError("soccer motions failed to register: " + ", ".join(missing))


def validate() -> list[str]:
    """Static checks used by Tools/test_soccer_forge.py."""
    errors = []
    register()
    for name in ALL_CLIPS:
        m = LIB.get(name)
        if m is None:
            errors.append("missing motion " + name)
            continue
        if m.keys is None and m.func is None:
            errors.append("motion %s has neither keys nor func" % name)
    for action, clip in ACTION_ALIASES.items():
        if clip not in ALL_CLIPS:
            errors.append("action %s -> unknown clip %s" % (action, clip))
    for name in LOOP_CLIPS:
        if not LIB[name].loop:
            errors.append("loop clip %s is marked non-looping" % name)
    for name, ev in CLIP_EVENTS.items():
        if name not in ALL_CLIPS:
            errors.append("event for unknown clip " + name)
        bc = ev.get("ball_contact", -1.0)
        if not (-1.0 <= bc <= 1.0):
            errors.append("clip %s ball_contact out of range" % name)
        for s in ev.get("footsteps", []):
            if not (0.0 <= s <= 1.0):
                errors.append("clip %s footsteps out of range" % name)
    # Ball clips must carry a contact frame so the sim can sync release.
    for name in ("soccer_short_pass", "soccer_shoot", "soccer_volley",
                 "soccer_header", "soccer_chest_control", "soccer_trap"):
        if CLIP_EVENTS[name]["ball_contact"] < 0:
            errors.append("ball clip %s missing ball_contact" % name)
    return errors
