"""AFL motion library for the Aussie Rules 3D forge pipeline (v11.21 DSL).

Each clip is authored in Sprite Forge's semantic pose channels (right-footed,
facing +forward). Every ball clip keys the ball explicitly so the contact
fraction lines up with the touch. These are procedural key-framed mannequins
retargeted onto the GAA squad rig — game-readable, not broadcast mocap.

    from afl_motions import register, AFL_CLIPS, EVENTS
    register()
    qa_all()  # [] when every clip passes
"""
from __future__ import annotations
import math
import sys
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(_REPO, "..", "sprite_forge")))

from sforge.motions import CROUCH, FIGHT, HOLD, K, LIB, M, P, READY, STAND, loco  # noqa: E402

BALL_FLOOR = 0.11


def _ball(y=BALL_FLOOR, z=0.5, x=0.0):
    return ("world", x, y, z)


CLIPS = {
    "afl_mark_contest": dict(category="Skill", ballState="Aerial", duration=1.15, loop=False,
        desc="aerial mark contest: two-foot launch, arms and eyes to the sky, pluck the ball two-handed",
        keys=K(
            (0.00, P(READY, ball=_ball(y=2.35, z=0.5))),
            (0.18, P(READY, hips=(24, 0, 0), leg_L=(52, 6, 0), knee_L=78, leg_R=(44, 6, 0), knee_R=72,
                     spine=(10, 0, 0), arm_L=(60, 10, 0), arm_R=(55, 10, 0), ball=_ball(y=2.40, z=0.45))),
            (0.35, P(READY, hips=(10, 0, 0), leg_L=(18, 0, 0), knee_L=30, leg_R=(6, 0, 0), knee_R=22,
                     arm_L=(150, 8, 0), arm_R=(145, -8, 0), elbow_L=18, elbow_R=18,
                     lift=0.15, ball=_ball(y=2.45, z=0.40))),
            (0.48, P(READY, lift=0.52, leg_L=(42, 0, 0), knee_L=70, leg_R=(-24, 0, 0), knee_R=38,
                     arm_L=(168, 4, 0), arm_R=(163, -4, 0), elbow_L=6, elbow_R=6,
                     ball=_ball(y=2.15, z=0.30))),
            (0.55, P(READY, lift=0.58, leg_L=(38, 0, 0), knee_L=64, leg_R=(-30, 0, 0), knee_R=44,
                     arm_L=(172, 2, 0), arm_R=(168, -2, 0), elbow_L=4, elbow_R=4, ball="hands")),
            (0.70, P(READY, lift=0.25, leg_L=(28, 0, 0), knee_L=48, leg_R=(-8, 0, 0), knee_R=30,
                     arm_L=(120, 6, 0), arm_R=(115, -6, 0), elbow_L=34, elbow_R=34, ball="hands")),
            (0.85, P(READY, lift=0.02, leg_L=(46, 0, 0), knee_L=88, leg_R=(38, 0, 0), knee_R=80,
                     arm_L=(60, 8, 0), arm_R=(55, 8, 0), elbow_L=70, elbow_R=70, ball="hands")),
            (1.00, P(READY, ball="hands")))),

    "afl_spoil": dict(category="Skill", ballState="Aerial", duration=1.10, loop=False,
        desc="pack-mark spoil: attack the ball, one arm swat clears it before the mark is taken",
        keys=K(
            (0.00, P(READY, ball=_ball(y=2.30, z=0.5))),
            (0.20, P(READY, hips=(22, 0, 0), knee_L=80, knee_R=72, arm_L=(80, 15, 0), arm_R=(90, -10, 0),
                     elbow_L=30, elbow_R=30, ball=_ball(y=2.30, z=0.45))),
            (0.38, P(READY, lift=0.30, leg_L=(30, 0, 0), knee_L=55, leg_R=(-12, 0, 0), knee_R=28,
                     arm_L=(150, 6, 0), arm_R=(165, -6, 0), elbow_R=10, ball=_ball(y=2.20, z=0.35))),
            (0.50, P(READY, lift=0.45, leg_L=(36, 0, 0), knee_L=64, leg_R=(-20, 0, 0), knee_R=36,
                     arm_L=(140, 8, 0), arm_R=(178, -8, 0), elbow_L=20, elbow_R=2,
                     ball=_ball(y=2.05, z=0.28))),
            (0.62, P(READY, lift=0.30, arm_R=(150, -14, 0), elbow_R=12, ball=_ball(y=1.40, z=0.10))),
            (0.80, P(READY, lift=0.05, leg_L=(44, 0, 0), knee_L=85, leg_R=(40, 0, 0), knee_R=78,
                     ball=_ball(y=1.00, z=-0.20))),
            (1.00, P(READY, ball=_ball(y=0.50, z=-0.50))))),

    "afl_fend_off": dict(category="Skill", ballState="Possessed", duration=0.75, loop=False,
        desc="fend off a pursuer at full stride: right arm across the body, palm out, ball in the other arm",
        keys=K(
            (0.00, P(READY, arm_R=(40, -30, 0), ball="hands")),
            (0.20, P(READY, hips=(14, -10, 0), chest=(6, -8, 0), arm_R=(78, -42, 0),
                     elbow_R=18, ball="hands")),
            (0.38, P(READY, hips=(14, -18, 0), chest=(8, -16, 0), arm_R=(92, -55, 0), elbow_R=8,
                     arm_L=(35, -20, 0), ball="hands")),
            (0.55, P(READY, hips=(12, -8, 0), arm_R=(60, -30, 0), elbow_R=25, ball="hands")),
            (1.00, P(READY, ball="hands")))),

    "afl_ruck_tap": dict(category="Skill", ballState="Aerial", duration=0.95, loop=False,
        desc="ruck ball-up tap: two-foot jump, right hand swats the tap forward to the rover",
        keys=K(
            (0.00, P(READY, ball=_ball(y=2.60, z=0.15))),
            (0.22, P(READY, hips=(20, 0, 0), knee_L=74, knee_R=70, arm_R=(120, -6, 0), arm_L=(45, 10, 0),
                     ball=_ball(y=2.60, z=0.15))),
            (0.45, P(READY, lift=0.42, leg_L=(34, 0, 0), knee_L=60, leg_R=(0, 0, 0), knee_R=24,
                     arm_R=(165, -4, 0), elbow_R=6, arm_L=(30, 14, 0), ball=_ball(y=2.10, z=0.12))),
            (0.58, P(READY, lift=0.55, leg_L=(30, 0, 0), knee_L=56, leg_R=(-8, 0, 0), knee_R=30,
                     arm_R=(172, -10, 0), elbow_R=2, ball=_ball(y=1.90, z=0.35))),
            (0.78, P(READY, lift=0.08, knee_L=84, knee_R=76, ball=_ball(y=1.60, z=0.60))),
            (1.00, P(READY, ball=_ball(y=1.20, z=0.80))))),

    "afl_snap_kick": dict(category="Kick", ballState="Possessed", duration=1.05, loop=False,
        desc="running snap on the run: ball comes from the left, right boot across the body",
        keys=K(
            (0.00, P(READY, ball="hands")),
            (0.18, P(READY, hips=(10, -14, 0), leg_L=(35, 0, 0), knee_L=35, leg_R=(15, -10, 0),
                     chest=(4, -10, 0), ball="hands")),
            (0.35, P(READY, hips=(8, -24, 0), leg_R=(30, -18, 0), knee_R=48,
                     arm_L=(70, 30, 0), arm_R=(30, -20, 0), ball="hands")),
            (0.50, P(READY, hips=(6, -30, 0), leg_R=(-18, -14, 0), knee_R=20, ankle_R=18,
                     arm_L=(85, 35, 0), ball=_ball(y=0.35, z=0.35))),
            (0.58, P(READY, hips=(4, -32, 0), leg_R=(-32, -12, 0), knee_R=8, ankle_R=12,
                     ball="foot_R")),
            (0.72, P(READY, hips=(8, 18, 0), leg_R=(55, 8, 0), knee_R=6, ankle_R=8,
                     arm_L=(40, 20, 0), arm_R=(70, -15, 0), ball=_ball(y=0.60, z=1.10))),
            (0.88, P(READY, ball=_ball(y=1.60, z=2.20))),
            (1.00, P(READY, ball=_ball(y=2.40, z=3.00))))),

    "afl_throw_in": dict(category="Skill", ballState="None", duration=0.90, loop=False,
        desc="boundary throw-in: both hands behind the head, step and hurl forward over the line",
        keys=K(
            (0.00, P(READY, ball="hands")),
            (0.22, P(READY, arm_L=(120, -16, 0), arm_R=(120, 16, 0), elbow_L=150, elbow_R=150,
                     chest=(-4, 0, 0), ball="overhead")),
            (0.40, P(READY, chest=(6, 0, 0), arm_L=(150, -12, 0), arm_R=(150, 12, 0),
                     elbow_L=70, elbow_R=70, ball="overhead")),
            (0.52, P(READY, chest=(12, 0, 0), arm_L=(95, -18, 0), arm_R=(95, 18, 0),
                     elbow_L=8, elbow_R=8, ball="overhead")),
            (0.66, P(READY, chest=(10, 0, 0), arm_L=(60, -10, 0), arm_R=(60, 10, 0),
                     elbow_L=15, elbow_R=15, ball=_ball(y=1.60, z=0.80))),
            (1.00, P(READY, ball=_ball(y=1.00, z=2.20))))),

    "afl_bounce_pickup": dict(category="Approach", ballState="Approaching", duration=0.85, loop=False,
        desc="bounce-to-pickup chain: bend into the dying bounce and scoop the ball cleanly in stride",
        keys=K(
            (0.00, P(READY, ball=_ball(y=0.11, z=0.55))),
            (0.25, P(READY, hips=(30, 0, 0), chest=(18, 0, 0), leg_R=(45, 0, 0), knee_R=65,
                     leg_L=(70, 0, 0), knee_L=95, arm_R=(55, -15, 0), elbow_R=30,
                     ball=_ball(y=0.11, z=0.50))),
            (0.45, P(READY, hips=(38, 0, 0), chest=(26, 0, 0), leg_R=(60, 0, 0), knee_R=80,
                     leg_L=(80, 0, 0), knee_L=110, arm_R=(75, -20, 0), elbow_R=55,
                     ball=_ball(y=0.30, z=0.42))),
            (0.55, P(READY, hips=(24, 0, 0), chest=(14, 0, 0), arm_R=(60, -12, 0), elbow_R=70,
                     leg_R=(50, 0, 0), knee_R=70, ball="hands")),
            (0.75, P(READY, hips=(10, 0, 0), chest=(4, 0, 0), arm_R=(38, -8, 0), elbow_R=80,
                     leg_R=(35, 0, 0), knee_R=40, ball="hands")),
            (1.00, P(READY, ball="hands")))),

    "afl_siren_celebrate": dict(category="Celebrate", ballState="None", duration=1.60, loop=False,
        desc="the siren: hands to the head, then the double-armed roar at the full-time horn",
        keys=K(
            (0.00, P(READY)),
            (0.20, P(READY, arm_L=(135, -18, 0), arm_R=(135, 18, 0), elbow_L=145, elbow_R=145,
                     chest=(-3, 0, 0))),
            (0.38, P(READY, arm_L=(170, -14, 0), arm_R=(170, 14, 0), elbow_L=12, elbow_R=12,
                     chest=(-6, 0, 0), neck=(-24, 0, 0))),
            (0.55, P(READY, arm_L=(165, -12, 0), arm_R=(165, 12, 0), elbow_L=8, elbow_R=8,
                     neck=(-28, 0, 0), lift=0.12)),
            (0.75, P(READY, chest=(2, 0, 0), arm_L=(150, -16, 0), arm_R=(150, 16, 0), neck=(-20, 0, 0))),
            (1.00, P(READY, arm_L=(150, -16, 0), arm_R=(150, 16, 0), elbow_L=15, elbow_R=15)))),

    "afl_set_shot_celebrate": dict(category="Celebrate", ballState="None", duration=1.30, loop=False,
        desc="the set shot landed: right fist pumped twice skyward, chest out, eyes to the scoreboard",
        keys=K(
            (0.00, P(READY, ball="hands")),
            (0.18, P(READY, arm_R=(95, -20, 0), elbow_R=115, chest=(-2, -6, 0))),
            (0.32, P(READY, arm_R=(160, -14, 0), elbow_R=30, chest=(-8, -4, 0), neck=(-20, 0, 0))),
            (0.44, P(READY, arm_R=(95, -20, 0), elbow_R=115, chest=(-2, -4, 0))),
            (0.58, P(READY, arm_R=(160, -14, 0), elbow_R=25, chest=(-8, -2, 0), neck=(-22, 0, 0))),
            (0.74, P(READY, arm_R=(120, -16, 0), elbow_R=50, neck=(-12, 0, 0))),
            (1.00, P(READY, ball="hands")))),

    # Analytic loops ----------------------------------------------------------
    "afl_bounce_carry": dict(category="Locomotion", ballState="Possessed", duration=0.78, loop=True,
        desc="the AFL bounce in stride: foot strikes the ball ahead, ball arcs hip-to-knee",
        func=loco(22, 52, 20, 16, 5, bounce=True)),
    "afl_fifty_walk": dict(category="Locomotion", ballState="None", duration=1.90, loop=True,
        desc="the free-kick walk: upright, unhurried, head up — the 50-metre stroll to the mark",
        func=loco(16, 38, 18, 12, 2)),
}

AFL_CLIPS = list(CLIPS)

# ball_contact / bounce_contact / footsteps as normalized phases (-1 = none).
EVENTS = {
    "afl_mark_contest":     dict(ball_contact=0.55, bounce_contact=-1.0, footsteps=(0.88,)),
    "afl_spoil":            dict(ball_contact=0.50, bounce_contact=-1.0, footsteps=(0.82,)),
    "afl_fend_off":         dict(ball_contact=-1.0, bounce_contact=-1.0, footsteps=(), hit_start=0.30, hit_end=0.55),
    "afl_ruck_tap":         dict(ball_contact=0.55, bounce_contact=-1.0, footsteps=(0.80,)),
    "afl_snap_kick":        dict(ball_contact=0.58, bounce_contact=-1.0, footsteps=(0.30, 0.92)),
    "afl_throw_in":         dict(ball_contact=0.52, bounce_contact=-1.0, footsteps=()),
    "afl_bounce_pickup":    dict(ball_contact=0.55, bounce_contact=-1.0, footsteps=()),
    "afl_siren_celebrate":  dict(ball_contact=-1.0, bounce_contact=-1.0, footsteps=()),
    "afl_set_shot_celebrate": dict(ball_contact=-1.0, bounce_contact=-1.0, footsteps=()),
    "afl_bounce_carry":     dict(ball_contact=-1.0, bounce_contact=0.25, footsteps=(0.25, 0.75)),
    "afl_fifty_walk":       dict(ball_contact=-1.0, bounce_contact=-1.0, footsteps=(0.125, 0.375, 0.625, 0.875)),
}

# Clips allowed to raise the arm above ~150 deg (overhead work); all others must not.
ARMS_UP_OK = {"afl_mark_contest", "afl_spoil", "afl_ruck_tap", "afl_throw_in",
              "afl_siren_celebrate", "afl_set_shot_celebrate"}
ARM_RAISE_LIMIT = 150.0


def register() -> None:
    for name, spec in CLIPS.items():
        if name in LIB:
            continue
        m = M(name, spec["category"], spec["desc"], keys=spec.get("keys"), func=spec.get("func"), loop=spec.get("loop", False))
        LIB[name].duration_s = spec["duration"]


def _arm_raise(pose, side):
    a = pose.get("arm_" + side)
    if not a:
        return 0.0
    return max(abs(float(a[0])), abs(float(a[1])))


def qa(name: str, samples: int = 24) -> list[str]:
    register()
    errs: list[str] = []
    m = LIB.get(name)
    if m is None:
        return ["unknown clip " + name]
    ev = EVENTS.get(name)
    if ev is None:
        errs.append(name + ": no event entry")
        ev = dict(ball_contact=-1.0, bounce_contact=-1.0, footsteps=())
    for key in ("ball_contact", "bounce_contact"):
        v = ev.get(key, -1.0)
        if not (v == -1.0 or 0.0 <= v <= 1.0):
            errs.append("%s: %s out of range" % (name, key))
    for s in ev.get("footsteps", ()):
        if not (0.0 <= s <= 1.0):
            errs.append("%s: footstep %s out of range" % (name, s))
    if "hit_start" in ev and not ev["hit_start"] < ev["hit_end"]:
        errs.append(name + ": hit window is empty")
    if name not in ARMS_UP_OK:
        worst = 0.0
        for i in range(samples + 1):
            pose, _ = m.sample(i / samples)
            worst = max(worst, _arm_raise(pose, "L"), _arm_raise(pose, "R"))
        if worst > ARM_RAISE_LIMIT:
            errs.append("%s: arm raised %.0f deg outside an overhead clip" % (name, worst))
    bc = ev.get("ball_contact", -1.0)
    if bc >= 0 and m.keys is not None:
        nearest = min(m.keys, key=lambda k: abs(k[0] - bc))
        if abs(nearest[0] - bc) > 0.06:
            errs.append("%s: no key at ball_contact %.2f (nearest %.2f)" % (name, bc, nearest[0]))
        elif "ball" not in nearest[1]:
            errs.append("%s: ball not placed at the contact key" % name)
    # World-space ball tracks must stay above the turf.
    for i in range(samples + 1):
        pose, _ = m.sample(i / samples)
        ball = pose.get("ball")
        if isinstance(ball, (tuple, list)) and ball and ball[0] == "world" and ball[2] < 0.05:
            errs.append("%s: world ball below turf at t=%.2f" % (name, i / samples))
            break
    return errs


def qa_all() -> dict[str, list[str]]:
    return {n: qa(n) for n in AFL_CLIPS}
