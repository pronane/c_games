"""Fighter motion pack for the 3D skeleton (v9.4): side-on 2D-fighter moves for photo3d / spec builds.

2D fighters are staged differently from 3D games: the fight axis runs across the screen, the legs are side-on and the
upper body is OPENED towards the camera (face and chest readable), then snaps back into profile for each strike so
fists and feet travel the full width of the sprite.  These clips are authored for that camera (yaw 90 = side-on,
facing right) with an `open` angle: how far the torso turns towards the camera at rest (default 55 = the face reads
like a 3/4 view).

    from sforge import fightpack
    fightpack.register(open_deg=55)          # adds f3d_<move> motions to the library
    fightpack.MAP['kick']                    # -> 'f3d_kick'

Moves: the fighter14 set (idle, walk, crouch, jump, punch, kick, special1, special2, block, hit, throw, jumpattack,
taunt, victory) + extras uppercut, sweep, low_block, hit_low, knockdown, getup, jab, roundhouse.
Key poses are spaced so that, at the fighter14 frame counts and with photo3d's pose-change sampling, no bone turns
more than ~60 degrees between frames; fast frames get a smear in the renderer instead of a bigger jump."""
from __future__ import annotations
import math
from .motions import P, K, M, LIB, idle_func

MOVES = ["idle", "walk", "crouch", "jump", "punch", "kick", "special1", "special2", "block", "hit", "throw",
         "jumpattack", "taunt", "victory", "uppercut", "sweep", "low_block", "hit_low", "knockdown", "getup", "jab",
         "roundhouse"]
MAP = {m: "f3d_" + m for m in MOVES}
MAP.update({"fight_idle": "f3d_idle", "jump_attack": "f3d_jumpattack", "special_1": "f3d_special1",
            "special_2": "f3d_special2", "pyramid_blast": "f3d_special1", "bum_fireball": "f3d_special2"})
_REG = {}


def stance(o, **kw):
    """fighting stance with the upper body opened `o` degrees towards the camera"""
    d = dict(hips=(4, -0.2 * o, 0), spine=(4, -0.3 * o, 0), chest=(2, -0.5 * o, 0), neck=(-6, 0.1 * o, 0),
             leg_L=(24, 7, 0), leg_R=(-16, 7, 0), knee_L=26, knee_R=22,
             arm_L=(64, 10, 0), arm_R=(50, 18, 0), elbow_L=108, elbow_R=128)
    d.update(kw)
    return d


def profile(o, f=1.0):
    """torso turned back towards the opponent: f = 1 full profile (strike), 0 = stance"""
    k = 1.0 - f
    return dict(hips=(4, -0.2 * o * k + 6 * f, 0), spine=(4, -0.3 * o * k + 6 * f, 0), chest=(2, -0.5 * o * k + 10 * f, 0),
                neck=(-6, 0.1 * o * k - 0.25 * o * f, 0))


def register(open_deg=55.0, force=False):
    o = float(open_deg)
    if not force and _REG.get("open") == o:
        return MAP
    S = stance(o)
    G = lambda **kw: P(S, **kw)                 # stance + changes
    PR = lambda f=1.0, **kw: P(S, profile(o, f), **kw)

    def walk(t):
        p = 2 * math.pi * t
        s, c = math.sin(p), math.cos(p)
        d = dict(S)
        d.update(leg_L=(24 + 10 * s, 7, 0), leg_R=(-16 - 10 * s, 7, 0), knee_L=26 + 14 * max(0, c), knee_R=22 + 14 * max(0, -c),
                 lift=0.012 * abs(s))
        d["arm_L"] = (64 + 4 * s, 10, 0)
        return d

    cat = "Fighter3D"
    M("f3d_idle", cat, "fighter stance, breathing bounce (open %g)" % o, func=idle_func(S, 1.4), loop=True)
    M("f3d_walk", cat, "guard shuffle", func=walk, loop=True)
    M("f3d_crouch", cat, "crouch guard", keys=K(
        (0, G()), (0.5, G(hips=(18, -0.2 * o, 0), leg_L=(70, 8, 0), leg_R=(40, 8, 0), knee_L=100, knee_R=95)),
        (1, G(hips=(22, -0.2 * o, 0), leg_L=(86, 8, 0), leg_R=(52, 8, 0), knee_L=122, knee_R=112, arm_L=(55, 10, 0), elbow_L=118))))
    M("f3d_jump", cat, "vertical jump, tuck at the top", keys=K(
        (0, G()), (0.14, G(leg_L=(60, 7, 0), leg_R=(30, 7, 0), knee_L=80, knee_R=70)),
        (0.3, G(leg_L=(20, 7, 0), leg_R=(-6, 7, 0), knee_L=12, knee_R=10, lift=0.35, arm_L=(90, 10, 0), arm_R=(80, 18, 0))),
        (0.5, G(leg_L=(80, 7, 0), leg_R=(60, 7, 0), knee_L=110, knee_R=100, lift=0.55)),
        (0.72, G(leg_L=(40, 7, 0), leg_R=(20, 7, 0), knee_L=40, knee_R=35, lift=0.3)),
        (0.88, G(leg_L=(60, 7, 0), leg_R=(30, 7, 0), knee_L=80, knee_R=70)), (1, G())))
    M("f3d_jab", cat, "lead-hand jab", keys=K(
        (0, G()), (0.35, PR(0.5, arm_L=(88, 2, 0), elbow_L=20)), (0.55, PR(0.6, arm_L=(90, 0, 0), elbow_L=4)),
        (0.8, PR(0.3, arm_L=(80, 6, 0), elbow_L=60)), (1, G())))
    M("f3d_punch", cat, "rear straight (cross): the torso turns into the punch", keys=K(
        (0, G()), (0.25, PR(0.4, arm_R=(70, 14, 0), elbow_R=100)),
        (0.45, PR(1.0, arm_R=(90, -4, 0), elbow_R=6, leg_L=(32, 7, 0), knee_L=36)),
        (0.62, PR(1.0, arm_R=(90, -4, 0), elbow_R=8, leg_L=(32, 7, 0), knee_L=36)),
        (0.82, PR(0.4, arm_R=(66, 14, 0), elbow_R=95)), (1, G())))
    M("f3d_kick", cat, "rear-leg side kick: chamber, extend, re-chamber", keys=K(
        (0, G()), (0.16, PR(0.4, leg_R=(30, 6, 0), knee_R=70)), (0.3, PR(0.8, leg_R=(70, 6, 0), knee_R=105)),
        (0.4, PR(1.0, leg_R=(86, 6, 0), knee_R=80, hips=(-8, 6, 0))),
        (0.46, PR(1.0, leg_R=(90, 6, 0), knee_R=42, ankle_R=-12, hips=(-11, 6, 0), spine=(-4, 6, 0))),     # v9.4 in-between
        (0.52, PR(1.0, leg_R=(92, 6, 0), knee_R=10, ankle_R=-25, hips=(-14, 6, 0), spine=(-8, 6, 0))),
        (0.66, PR(1.0, leg_R=(92, 6, 0), knee_R=8, ankle_R=-25, hips=(-14, 6, 0), spine=(-8, 6, 0))),
        (0.73, PR(0.85, leg_R=(84, 6, 0), knee_R=52, ankle_R=-10, hips=(-8, 6, 0))),                       # v9.4 in-between
        (0.8, PR(0.6, leg_R=(70, 6, 0), knee_R=100)), (0.9, PR(0.3, leg_R=(40, 6, 0), knee_R=70)), (1, G())))
    M("f3d_roundhouse", cat, "roundhouse kick (hip turns over)", keys=K(
        (0, G()), (0.25, PR(0.6, leg_R=(60, 30, 0), knee_R=110)),
        (0.5, PR(1.0, leg_R=(85, 25, 20), knee_R=12, hips=(-10, 25, 0))),
        (0.65, PR(1.0, leg_R=(85, 25, 20), knee_R=10, hips=(-10, 25, 0))),
        (0.82, PR(0.5, leg_R=(55, 20, 0), knee_R=100)), (1, G())))
    M("f3d_special1", cat, "two-hand energy push at chest height", keys=K(
        (0, G()), (0.22, PR(0.2, arm_L=(30, 20, 0), arm_R=(25, 22, 0), elbow_L=110, elbow_R=110, hips=(10, -0.2 * o, 0))),
        (0.42, PR(0.7, arm_L=(70, 8, 0), arm_R=(68, 8, 0), elbow_L=60, elbow_R=60)),
        (0.58, PR(1.0, arm_L=(90, 2, 0), arm_R=(90, 2, 0), elbow_L=6, elbow_R=6, leg_L=(34, 7, 0), knee_L=38)),
        (0.78, PR(1.0, arm_L=(90, 2, 0), arm_R=(90, 2, 0), elbow_L=6, elbow_R=6, leg_L=(34, 7, 0), knee_L=38)),
        (1, G())))
    M("f3d_uppercut", cat, "crouching rear uppercut", keys=K(
        (0, G()), (0.25, PR(0.3, hips=(20, -0.2 * o, 0), leg_L=(60, 8, 0), leg_R=(30, 8, 0), knee_L=80, knee_R=70,
                            arm_R=(30, 16, 0), elbow_R=100)),
        (0.5, PR(0.9, arm_R=(130, 6, 0), elbow_R=70, leg_L=(30, 8, 0), knee_L=30, lift=0.06)),
        (0.68, PR(1.0, arm_R=(165, 4, 0), elbow_R=40, lift=0.1)),
        (0.85, PR(0.5, arm_R=(90, 12, 0), elbow_R=100)), (1, G())))
    MAP["special2"] = "f3d_uppercut"           # fighter14 special2 = the uppercut
    M("f3d_special2", cat, "alias of the uppercut", keys=LIB["f3d_uppercut"].keys)
    M("f3d_block", cat, "high guard (forearms up in front of the face)", keys=K(
        (0, G()), (0.4, G(arm_L=(96, 8, 0), arm_R=(92, 12, 0), elbow_L=132, elbow_R=134, spine=(-4, -0.3 * o, 0))),
        (1, G(arm_L=(98, 8, 0), arm_R=(94, 12, 0), elbow_L=134, elbow_R=136, spine=(-6, -0.3 * o, 0)))))
    M("f3d_low_block", cat, "crouching low block", keys=K(
        (0, G()), (0.5, G(hips=(20, -0.2 * o, 0), leg_L=(80, 8, 0), leg_R=(50, 8, 0), knee_L=110, knee_R=100,
                          arm_L=(30, 10, 0), elbow_L=40, arm_R=(40, 14, 0), elbow_R=90)),
        (1, G(hips=(22, -0.2 * o, 0), leg_L=(84, 8, 0), leg_R=(52, 8, 0), knee_L=118, knee_R=108,
              arm_L=(26, 10, 0), elbow_L=30, arm_R=(40, 14, 0), elbow_R=90))))
    M("f3d_hit", cat, "hit high: head snaps back, guard knocked open, recover", keys=K(
        (0, G()), (0.2, G(neck=(18, 0.1 * o, 0), spine=(-14, -0.3 * o, 0), chest=(-8, -0.5 * o, 0), arm_L=(40, 30, 0),
                          arm_R=(30, 35, 0), elbow_L=60, elbow_R=70, leg_L=(14, 7, 0), knee_L=16)),
        (0.45, G(neck=(10, 0.1 * o, 0), spine=(-10, -0.3 * o, 0), arm_L=(48, 24, 0), arm_R=(40, 26, 0), elbow_L=80, elbow_R=90)),
        (0.75, G(neck=(2, 0.1 * o, 0), spine=(-3, -0.3 * o, 0))), (1, G())))
    M("f3d_hit_low", cat, "hit to the body: folds forward", keys=K(
        (0, G()), (0.25, G(spine=(22, -0.3 * o, 0), chest=(14, -0.5 * o, 0), neck=(-14, 0.1 * o, 0), arm_L=(30, 20, 0),
                           arm_R=(36, 20, 0), elbow_L=100, elbow_R=100, knee_L=40, knee_R=36)),
        (0.6, G(spine=(12, -0.3 * o, 0), knee_L=34)), (1, G())))
    M("f3d_throw", cat, "grab, turn and throw over the hip", keys=K(
        (0, G()), (0.2, PR(0.8, arm_L=(86, 6, 0), arm_R=(84, 8, 0), elbow_L=24, elbow_R=24)),
        (0.38, PR(1.0, arm_L=(88, 6, 0), arm_R=(86, 8, 0), elbow_L=70, elbow_R=70)),
        (0.48, P(S, hips=(8, 12, 0), spine=(6, 8, 0), chest=(4, 8, 0), neck=(-6, -10, 0), arm_L=(110, 14, 0),
                 arm_R=(104, 18, 0), elbow_L=55, elbow_R=55, leg_L=(36, 7, 0), knee_L=44)),
        (0.58, P(S, hips=(10, 30, 0), spine=(8, 20, 0), chest=(6, 20, 0), neck=(-6, -10, 0), arm_L=(130, 20, 0),
                 arm_R=(120, 26, 0), elbow_L=40, elbow_R=40, leg_L=(40, 7, 0), knee_L=50)),
        (0.66, P(S, hips=(13, 36, 0), spine=(11, 23, 0), chest=(8, 23, 0), arm_L=(96, 30, 0), arm_R=(86, 35, 0),
                 elbow_L=30, elbow_R=30, leg_L=(42, 7, 0), knee_L=53)),                                          # v9.4 in-between
        (0.74, P(S, hips=(16, 40, 0), spine=(14, 25, 0), chest=(10, 25, 0), arm_L=(60, 40, 0), arm_R=(50, 44, 0),
                 elbow_L=20, elbow_R=20, leg_L=(44, 7, 0), knee_L=56)),
        (0.88, P(S, hips=(10, 10, 0), spine=(8, 0, 0), chest=(6, -10, 0), arm_L=(62, 24, 0), arm_R=(50, 30, 0),
                 elbow_L=70, elbow_R=80, leg_L=(34, 7, 0), knee_L=40)),
        (1, G())))
    M("f3d_jumpattack", cat, "flying kick", keys=K(
        (0, G(leg_L=(60, 7, 0), leg_R=(30, 7, 0), knee_L=80, knee_R=70)),
        (0.25, PR(0.6, leg_L=(70, 7, 0), leg_R=(80, 7, 0), knee_L=100, knee_R=110, lift=0.35)),
        (0.38, PR(0.9, leg_L=(80, 7, 0), knee_L=55, leg_R=(74, 7, 0), knee_R=118, lift=0.45, hips=(-8, 6, 0))),
        (0.44, PR(0.95, leg_L=(84, 7, 0), knee_L=30, ankle_L=-12, leg_R=(72, 7, 0), knee_R=119, lift=0.48, hips=(-10, 6, 0))),
        (0.5, PR(1.0, leg_L=(86, 7, 0), knee_L=8, ankle_L=-25, leg_R=(70, 7, 0), knee_R=120, lift=0.5, hips=(-12, 6, 0))),
        (0.72, PR(1.0, leg_L=(86, 7, 0), knee_L=8, ankle_L=-25, leg_R=(70, 7, 0), knee_R=120, lift=0.42, hips=(-12, 6, 0))),
        (1, G(leg_L=(60, 7, 0), leg_R=(30, 7, 0), knee_L=80, knee_R=70))))
    M("f3d_sweep", cat, "low spinning leg sweep", keys=K(
        (0, G()), (0.25, G(hips=(26, -0.2 * o, 0), leg_L=(90, 8, 0), knee_L=130, leg_R=(30, 20, 0), knee_R=60, lift=-0.0)),
        (0.5, G(hips=(26, 10, 0), leg_L=(90, 8, 0), knee_L=130, leg_R=(60, 40, 0), knee_R=6, arm_L=(30, 30, 0), elbow_L=30)),
        (0.68, G(hips=(26, 20, 0), leg_L=(90, 8, 0), knee_L=130, leg_R=(60, 40, 0), knee_R=6)),
        (1, G())))
    M("f3d_knockdown", cat, "knocked down: falls back to the floor", keys=K(
        (0, G()), (0.3, G(spine=(-20, -0.3 * o, 0), neck=(20, 0, 0), arm_L=(30, 50, 0), arm_R=(20, 55, 0), elbow_L=40, elbow_R=40,
                          lift=0.15)),
        (0.65, P(dict(hips=(-60, -0.2 * o, 0), neck=(20, 0, 0), arm_L=(40, 60, 0), arm_R=(30, 60, 0), leg_L=(50, 8, 0),
                      leg_R=(30, 8, 0), knee_L=40, knee_R=30))),
        (1, P(dict(hips=(-88, -0.2 * o, 0), neck=(28, 0, 0), flat=0, arm_L=(15, 40, 0), arm_R=(10, 45, 0), elbow_L=20,
                   elbow_R=30, leg_L=(10, 8, 0), leg_R=(25, 8, 0), knee_L=20, knee_R=45)))))
    M("f3d_getup", cat, "get up from the floor", keys=K(
        (0, LIB["f3d_knockdown"].keys[-1][1]),
        (0.4, P(dict(hips=(40, -0.2 * o, 0), spine=(20, 0, 0), neck=(-20, 0, 0), leg_L=(100, 8, 0), leg_R=(80, 8, 0),
                     knee_L=130, knee_R=125, arm_L=(30, 20, 0), arm_R=(30, 20, 0)))),
        (0.75, G(hips=(16, -0.2 * o, 0), leg_L=(60, 8, 0), leg_R=(40, 8, 0), knee_L=70, knee_R=60)), (1, G())))
    M("f3d_taunt", cat, "come-on: lead hand beckons", keys=K(
        (0, G()), (0.2, G(arm_L=(80, 4, 0), elbow_L=20, wrist_L=-30)), (0.4, G(arm_L=(80, 4, 0), elbow_L=40, wrist_L=30)),
        (0.6, G(arm_L=(80, 4, 0), elbow_L=20, wrist_L=-30)), (0.8, G(arm_L=(80, 4, 0), elbow_L=40, wrist_L=30)), (1, G())))
    M("f3d_victory", cat, "fist pump", keys=K(
        (0, G()), (0.25, G(arm_R=(120, 10, 0), elbow_R=80, spine=(-4, -0.3 * o, 0))),
        (0.45, G(arm_R=(168, 8, 0), elbow_R=12, spine=(-6, -0.3 * o, 0), lift=0.03)),
        (0.65, G(arm_R=(150, 8, 0), elbow_R=50)), (0.85, G(arm_R=(168, 8, 0), elbow_R=12, lift=0.03)),
        (1, G(arm_R=(168, 8, 0), elbow_R=14))))
    _REG["open"] = o
    return MAP


def motion_for_move(name, pack="fighter3d", open_deg=55.0):
    """library motion for a move name in the pack, or None (then the normal library is used)"""
    if pack != "fighter3d":
        return None
    register(open_deg)
    key = MAP.get(name) or MAP.get(name.lower())
    return LIB.get(key) if key else None
