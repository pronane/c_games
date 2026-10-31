"""HD Fighter frame library (v10): one explicitly authored pose per sprite frame for the 16 HD Fighter states.

Every frame is posed by hand instead of sampled from a curve, so the sprite sheets read cleanly at low frame counts
and every attack puts its strongest pose on frame 1 or 2 (0-based) - the only frames on which the shared online sim
(HD_Fighter/multiplayer/public/sim.mjs, hitbox()) registers hits.

Staging follows sforge.fightpack: side-on (yaw 90, facing right), legs in profile, upper body opened ~55 degrees
towards the camera so faces and chests read, snapping back into profile for strikes.  No pose uses `lift`, so feet
(or the lowest point) always sit on the baseline - the game moves fighters vertically itself.

    from sforge import hdfighter
    hdfighter.register()                 # adds hd_<state> motions to the motion library
    hdfighter.MOVES                      # the --moves string for the HD Fighter sheets (frame counts from meta.json)
    hdfighter.frames('hp')               # list of pose dicts, one per frame
"""
from __future__ import annotations
import math
from .fightpack import stance, profile
from .motions import P, M, LIB

OPEN = 55.0
# state: (frames, fps, loop) - frame counts match HD_Fighter/assets_hd/meta.json
STATES = {
    "idle": (5, 6, True), "walk": (7, 8, True), "crouch": (2, 8, False), "jump": (5, 10, False),
    "lp": (4, 12, False), "hp": (5, 12, False), "lk": (4, 12, False), "hk": (5, 12, False),
    "block": (2, 8, False), "throw": (5, 10, False), "special1": (6, 12, False), "special2": (5, 12, False),
    "super": (7, 12, False), "hit": (3, 10, False), "win": (5, 8, False), "lose": (3, 8, False),
}
ATTACKS = ("lp", "hp", "lk", "hk", "throw", "special1", "special2", "super")
MOVES = ",".join("%s=hd_%s:%d:%d%s" % (s, s, n, f, ":loop" if lp else "") for s, (n, f, lp) in STATES.items())


def _frames(o=OPEN):
    S = stance(o, ankle_R=42)             # rear foot on its ball (toes on the baseline)
    G = lambda **kw: P(S, **kw)
    PR = lambda f=1.0, **kw: P(S, profile(o, f), **kw)
    F = {}

    # ---- idle: breathing bounce, guard hands bob a little
    idle = []
    for i in range(5):
        s = math.sin(2 * math.pi * i / 5)
        idle.append(G(knee_L=26 + 5 * s, knee_R=22 + 5 * s, leg_L=(24 + 2 * s, 7, 0), leg_R=(-16 + 2 * s, 7, 0),
                      hips=(4 + 2 * s, -0.2 * o, 0), arm_L=(64 + 3 * s, 10, 0), arm_R=(50 + 3 * s, 18, 0),
                      elbow_L=108 - 4 * s, elbow_R=128 - 4 * s, neck=(-6 - 2 * s, 0.1 * o, 0)))
    F["idle"] = idle

    # ---- walk: guard shuffle (stepping, hips bob)
    walk = []
    for i in range(7):
        p = 2 * math.pi * i / 7
        s, c = math.sin(p), math.cos(p)
        walk.append(G(leg_L=(24 + 16 * s, 7, 0), leg_R=(-16 - 16 * s, 7, 0), knee_L=26 + 22 * max(0, c),
                      knee_R=22 + 22 * max(0, -c), arm_L=(64 + 5 * s, 10, 0), arm_R=(50 - 4 * s, 18, 0),
                      hips=(6, -0.2 * o + 3 * s, 0), chest=(2, -0.5 * o - 3 * s, 0)))
    F["walk"] = walk

    crouch_low = G(hips=(24, -0.2 * o, 0), spine=(8, -0.3 * o, 0), leg_L=(92, 8, 0), leg_R=(58, 8, 0),
                   knee_L=128, knee_R=120, arm_L=(58, 10, 0), elbow_L=116, arm_R=(44, 18, 0), elbow_R=126)
    F["crouch"] = [G(hips=(14, -0.2 * o, 0), leg_L=(64, 8, 0), leg_R=(34, 8, 0), knee_L=88, knee_R=80), crouch_low]

    # ---- jump (the game moves the fighter; the sprite only changes shape)
    tuck = G(leg_L=(96, 7, 0), leg_R=(74, 7, 0), knee_L=128, knee_R=120, arm_L=(78, 12, 0), arm_R=(66, 20, 0),
             elbow_L=96, elbow_R=110, hips=(10, -0.2 * o, 0))
    F["jump"] = [
        G(leg_L=(56, 7, 0), leg_R=(30, 7, 0), knee_L=78, knee_R=68, hips=(14, -0.2 * o, 0)),
        G(leg_L=(14, 7, 0), leg_R=(-14, 7, 0), knee_L=10, knee_R=24, arm_L=(110, 12, 0), arm_R=(96, 20, 0),
          elbow_L=40, elbow_R=50, ankle_L=40, ankle_R=40, flat=0),
        tuck,
        G(leg_L=(46, 7, 0), leg_R=(10, 7, 0), knee_L=50, knee_R=40, arm_L=(80, 14, 0), arm_R=(70, 22, 0), ankle_L=20, flat=0.4),
        G(leg_L=(60, 7, 0), leg_R=(32, 7, 0), knee_L=84, knee_R=74, hips=(16, -0.2 * o, 0)),
    ]

    # ---- light punch: lead jab - peak on frames 1 and 2
    jab = PR(0.75, arm_L=(92, 0, 0), elbow_L=2, leg_L=(30, 7, 0), knee_L=32, arm_R=(56, 16, 0), elbow_R=128)
    F["lp"] = [PR(0.4, arm_L=(80, 6, 0), elbow_L=70), jab, P(jab, arm_L=(90, 0, 0), elbow_L=6), PR(0.2, arm_L=(70, 8, 0), elbow_L=96)]

    # ---- heavy punch: rear cross with full hip turn
    cross = PR(1.0, arm_R=(92, -6, 0), elbow_R=2, leg_L=(36, 7, 0), knee_L=42, leg_R=(-24, 7, 0), knee_R=10,
               arm_L=(40, 18, 0), elbow_L=120, hips=(6, 14, 0), spine=(6, 10, 0))
    F["hp"] = [PR(0.2, arm_R=(56, 22, 0), elbow_R=120, hips=(2, -0.3 * o, 0), spine=(0, -0.4 * o, 0)),
               cross, P(cross, arm_R=(90, -4, 0), elbow_R=6),
               PR(0.6, arm_R=(70, 10, 0), elbow_R=70), G()]

    # ---- light kick: snapping front kick at mid height
    snap = PR(0.7, leg_L=(84, 6, 0), knee_L=4, ankle_L=-28, flat=0, hips=(-8, 4, 0), spine=(-4, 4, 0),
              leg_R=(-8, 7, 0), knee_R=14, arm_L=(70, 20, 0), elbow_L=100)
    F["lk"] = [PR(0.4, leg_L=(70, 6, 0), knee_L=100, flat=0), snap, P(snap, leg_L=(80, 6, 0), knee_L=14),
               PR(0.3, leg_L=(56, 6, 0), knee_L=80)]

    # ---- heavy kick: rear-leg side kick, chambered then fully extended at head height
    side = PR(1.0, leg_R=(100, 6, 0), knee_R=4, ankle_R=-22, flat=0, hips=(-18, 8, 0), spine=(-10, 8, 0),
              chest=(-4, 10, 0), leg_L=(-6, 7, 0), knee_L=16, arm_L=(40, 30, 0), elbow_L=90, arm_R=(30, 40, 0), elbow_R=80)
    F["hk"] = [PR(0.6, leg_R=(78, 6, 0), knee_R=118, flat=0, hips=(-6, 6, 0)), side,
               P(side, leg_R=(96, 6, 0), knee_R=10), PR(0.6, leg_R=(70, 6, 0), knee_R=104, flat=0), G()]

    F["block"] = [G(arm_L=(88, 8, 0), arm_R=(84, 12, 0), elbow_L=124, elbow_R=128),
                  G(arm_L=(98, 8, 0), arm_R=(94, 12, 0), elbow_L=136, elbow_R=138, spine=(-6, -0.3 * o, 0),
                    knee_L=34, knee_R=30)]

    # ---- throw: lunge-grab (peak reach on frame 1), heave on frame 2
    grab = PR(1.0, arm_L=(88, 4, 0), arm_R=(84, 6, 0), elbow_L=8, elbow_R=10, leg_L=(42, 7, 0), knee_L=50,
              leg_R=(-28, 7, 0), knee_R=8, hips=(12, 8, 0), spine=(10, 6, 0))
    heave = P(S, hips=(10, 34, 0), spine=(8, 22, 0), chest=(6, 22, 0), neck=(-6, -12, 0), arm_L=(124, 18, 0),
              arm_R=(116, 24, 0), elbow_L=44, elbow_R=44, leg_L=(42, 7, 0), knee_L=50, leg_R=(-20, 7, 0), knee_R=12)
    F["throw"] = [PR(0.6, arm_L=(70, 8, 0), arm_R=(66, 10, 0), elbow_L=50, elbow_R=56), grab, heave,
                  P(S, hips=(14, 40, 0), spine=(12, 24, 0), chest=(8, 24, 0), arm_L=(64, 40, 0), arm_R=(54, 44, 0),
                    elbow_L=24, elbow_R=24, leg_L=(42, 7, 0), knee_L=54), G()]

    # ---- special 1: two-palm energy thrust (fireball) - thrust on frames 1-2
    gather = PR(0.2, arm_L=(26, 22, 0), arm_R=(22, 24, 0), elbow_L=112, elbow_R=112, hips=(10, -0.25 * o, 0),
                knee_L=40, knee_R=36)
    push = PR(1.0, arm_L=(90, 2, 0), arm_R=(88, 2, 0), elbow_L=4, elbow_R=6, wrist_L=-35, wrist_R=-35,
              leg_L=(40, 7, 0), knee_L=46, leg_R=(-26, 7, 0), knee_R=8, hips=(8, 8, 0))
    F["special1"] = [gather, push, P(push, arm_L=(92, 2, 0), arm_R=(90, 2, 0)),
                     P(push, arm_L=(66, 8, 0), arm_R=(64, 8, 0), elbow_L=70, elbow_R=72, wrist_L=-10, wrist_R=-10), PR(0.4, arm_L=(70, 8, 0), elbow_L=70), G()]

    # ---- special 2: rising uppercut - fist at the top on frames 1-2
    load = PR(0.3, hips=(24, -0.2 * o, 0), leg_L=(70, 8, 0), leg_R=(36, 8, 0), knee_L=96, knee_R=84,
              arm_R=(26, 18, 0), elbow_R=110)
    rise = PR(1.0, arm_R=(168, 2, 0), elbow_R=26, leg_L=(20, 7, 0), knee_L=14, leg_R=(-10, 7, 0), knee_R=24,
              ankle_L=-24, ankle_R=-10, flat=0.3, spine=(-10, 10, 0), chest=(-6, 10, 0), arm_L=(40, 24, 0), elbow_L=100)
    F["special2"] = [load, rise, P(rise, arm_R=(172, 0, 0), elbow_R=14),
                     PR(0.6, arm_R=(110, 12, 0), elbow_R=80, knee_L=40), G()]

    # ---- super: flying kick, fully extended on frames 1-2, then a spinning follow-up and landing
    fly = PR(1.0, leg_L=(96, 7, 0), knee_L=4, ankle_L=-26, leg_R=(70, 7, 0), knee_R=124, flat=0, hips=(-20, 8, 0),
             spine=(-10, 8, 0), arm_L=(40, 40, 0), elbow_L=60, arm_R=(60, 40, 0), elbow_R=70)
    F["super"] = [G(leg_L=(68, 7, 0), leg_R=(40, 7, 0), knee_L=96, knee_R=84, hips=(18, -0.2 * o, 0),
                    arm_L=(30, 30, 0), arm_R=(30, 30, 0), elbow_L=90, elbow_R=90),
                  fly, P(fly, leg_L=(100, 7, 0), knee_L=2),
                  PR(0.8, leg_R=(70, 20, 0), knee_R=96, leg_L=(10, 7, 0), knee_L=30, flat=0, hips=(-8, 24, 0)),   # re-chamber
                  PR(0.6, leg_R=(60, 20, 0), knee_R=90, flat=0),
                  G(leg_L=(60, 7, 0), leg_R=(32, 7, 0), knee_L=88, knee_R=76, hips=(18, -0.2 * o, 0)), G()]

    F["hit"] = [G(neck=(22, 0.1 * o, 0), spine=(-18, -0.3 * o, 0), chest=(-10, -0.5 * o, 0), arm_L=(36, 34, 0),
                  arm_R=(28, 38, 0), elbow_L=56, elbow_R=66, leg_L=(10, 7, 0), knee_L=14, knee_R=30),
                G(neck=(12, 0.1 * o, 0), spine=(-10, -0.3 * o, 0), arm_L=(48, 24, 0), arm_R=(40, 26, 0), elbow_L=80, elbow_R=90),
                G(neck=(2, 0.1 * o, 0), spine=(-3, -0.3 * o, 0))]

    rest = dict(hips=(0, -0.3 * o, 0), spine=(0, -0.3 * o, 0), chest=(-2, -0.3 * o, 0), neck=(-4, 0.2 * o, 0),
                leg_L=(10, 9, 0), leg_R=(-8, 9, 0), knee_L=8, knee_R=6, arm_L=(14, 14, 0), elbow_L=40)
    F["win"] = [G(arm_R=(120, 10, 0), elbow_R=80),
                P(rest, arm_R=(170, 8, 0), elbow_R=10),
                P(rest, arm_R=(160, 8, 0), elbow_R=36, knee_L=14, knee_R=12),
                P(rest, arm_R=(172, 8, 0), elbow_R=8),
                P(rest, arm_R=(170, 8, 0), elbow_R=12, arm_L=(20, 18, 0), elbow_L=60)]

    # ---- lose: stagger, drop to the knees, slump forward (kneeling, so nothing leaves the cell)
    F["lose"] = [G(neck=(24, 0.1 * o, 0), spine=(-16, -0.3 * o, 0), arm_L=(20, 40, 0), arm_R=(14, 44, 0),
                   elbow_L=40, elbow_R=40, knee_L=40, knee_R=36),
                 P(dict(hips=(10, -0.2 * o, 0), spine=(10, -0.3 * o, 0), neck=(18, 0, 0), leg_L=(80, 8, 0), leg_R=(-6, 8, 0),
                        knee_L=100, knee_R=118, ankle_R=-50, flat=0.2, arm_L=(10, 18, 0), arm_R=(6, 20, 0), elbow_L=20, elbow_R=24)),
                 P(dict(hips=(30, -0.2 * o, 0), spine=(30, -0.3 * o, 0), chest=(14, -0.3 * o, 0), neck=(34, 0, 0),
                        leg_L=(30, 8, 0), leg_R=(30, 8, 0), knee_L=150, knee_R=150, ankle_L=-60, ankle_R=-60, flat=0,
                        arm_L=(40, 10, 0), arm_R=(30, 12, 0), elbow_L=30, elbow_R=40))]
    return F


_CACHE = {}

# per-character changes on top of the shared frames: {char: {state: {frame: {channel: value}}}}
# Naomi holds a katana in the rear hand: in the two-palm thrust a bent wrist lays the blade flat and out of the
# cell, so her sword wrist stays straight (blade forward and up, like her other strikes).
OVERRIDES = {
    "naomi": {"special1": {1: dict(wrist_R=0), 2: dict(wrist_R=0), 3: dict(wrist_R=0)}},
}


def frames(state, o=OPEN, char=None):
    if o not in _CACHE:
        _CACHE[o] = _frames(o)
    fr = _CACHE[o][state]
    ov = OVERRIDES.get(char or "", {}).get(state)
    if ov:
        fr = [P(p, **ov.get(i, {})) for i, p in enumerate(fr)]
    return fr


def motion_name(state, char=None):
    return "hd_%s_%s" % (char, state) if state in OVERRIDES.get(char or "", {}) else "hd_" + state


def moves_for(char=None):
    """the --moves string for one fighter (uses its overridden motions where it has any)"""
    return ",".join("%s=%s:%d:%d%s" % (s, motion_name(s, char), n, f, ":loop" if lp else "") for s, (n, f, lp) in STATES.items())


def register(o=OPEN):
    """add hd_<state> motions whose keys sit exactly on the frame sample times (anim.sample_times)"""
    if LIB.get("hd_idle") is not None and _CACHE.get("_reg") == o:
        return
    for s, (n, _f, loop) in STATES.items():
        fr = frames(s, o)
        assert len(fr) == n, (s, len(fr), n)
        if loop:
            keys = [(i / n, p) for i, p in enumerate(fr)] + [(1.0, fr[0])]
        else:
            keys = [(i / max(1, n - 1), p) for i, p in enumerate(fr)]
        M("hd_" + s, "HDFighter", "HD Fighter %s (%d hand-posed frames)" % (s, n), keys=keys, loop=loop)
    for ch, sts in OVERRIDES.items():
        for s in sts:
            n, _f, loop = STATES[s]
            fr = frames(s, o, ch)
            keys = [(i / n, p) for i, p in enumerate(fr)] + [(1.0, fr[0])] if loop else [(i / max(1, n - 1), p) for i, p in enumerate(fr)]
            M(motion_name(s, ch), "HDFighter", "HD Fighter %s %s" % (ch, s), keys=keys, loop=loop)
    _CACHE["_reg"] = o


def states(state, o=OPEN, char=None):
    """FrameState per frame of a state (exact authored poses)"""
    from .rig import evaluate
    return [evaluate(p) for p in frames(state, o, char)]
