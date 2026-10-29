"""Procedural motion library for the mannequin rig.

Every motion is a function of normalised time t in [0, 1] -> semantic pose.
Motions are either key-framed (list of (t, pose)) or analytic cycles.
These are hand-authored, procedural animations: they read clearly as game
moves but are not motion capture.
"""
from __future__ import annotations
import math
from .mathutil import smooth


def P(*bases, **kw):
    d = {}
    for b in bases:
        d.update(b)
    d.update(kw)
    return d


# ---------------------------------------------------------------- stances
STAND = dict(arm_L=(3, 9, 0), arm_R=(3, 9, 0), elbow_L=12, elbow_R=12,
             leg_L=(3, 3, 0), leg_R=(-2, 3, 0), knee_L=5, knee_R=4, neck=(2, 0, 0))
READY = dict(hips=(12, 0, 0), spine=(6, 0, 0), chest=(4, 0, 0), neck=(-16, 0, 0),
             leg_L=(32, 6, 0), leg_R=(24, 6, 0), knee_L=48, knee_R=42,
             arm_L=(22, 16, 0), arm_R=(22, 16, 0), elbow_L=55, elbow_R=55)
FIGHT = dict(hips=(4, -28, 0), spine=(4, 10, 0), chest=(2, 14, 0), neck=(-6, 4, 0),
             leg_L=(22, 7, 0), leg_R=(-14, 7, 0), knee_L=24, knee_R=20,
             arm_L=(62, 10, 0), arm_R=(48, 18, 0), elbow_L=105, elbow_R=125)
HOLD = dict(arm_L=(38, -14, 0), arm_R=(38, -14, 0), elbow_L=88, elbow_R=88, ball="hands")
CROUCH = dict(hips=(18, 0, 0), spine=(10, 0, 0), neck=(-22, 0, 0),
              leg_L=(88, 8, 0), leg_R=(72, 8, 0), knee_L=125, knee_R=118,
              arm_L=(35, 14, 0), arm_R=(35, 14, 0), elbow_L=60, elbow_R=60)
LIE_FRONT = dict(hips=(88, 0, 0), spine=(0, 0, 0), neck=(-40, 0, 0), flat=0,
                 arm_L=(150, 20, 0), arm_R=(140, 25, 0), elbow_L=30, elbow_R=40,
                 leg_L=(5, 6, 0), leg_R=(-3, 6, 0), knee_L=10, knee_R=25, ankle_L=40, ankle_R=40)
LIE_BACK = dict(hips=(-88, 0, 0), neck=(30, 0, 0), flat=0,
                arm_L=(15, 40, 0), arm_R=(10, 45, 0), elbow_L=20, elbow_R=30,
                leg_L=(10, 8, 0), leg_R=(25, 8, 0), knee_L=20, knee_R=45, ankle_L=30, ankle_R=30)


class Motion:
    def __init__(self, name, keys=None, func=None, loop=False, desc="", category="General"):
        self.name, self.keys, self.func = name, keys, func
        self.loop, self.desc, self.category = loop, desc, category

    def sample(self, t):
        """-> (pose, ball_mix)"""
        if self.func is not None:
            p = self.func(t)
            return p, None
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1], None
        if t >= ks[-1][0]:
            return ks[-1][1], None
        for (t0, p0), (t1, p1) in zip(ks, ks[1:]):
            if t0 <= t <= t1:
                a = smooth((t - t0) / max(1e-6, t1 - t0))
                return _lerp_pose(p0, p1, a), (p0.get("ball"), p1.get("ball"), a)
        return ks[-1][1], None


def _lerp_pose(p0, p1, a):
    out = {}
    for k in set(p0) | set(p1):
        if k in ("ball", "ground"):
            out[k] = p0.get(k) if a < 0.5 else p1.get(k)
            continue
        v0, v1 = p0.get(k, 0), p1.get(k, 0)
        if k == "flat":
            v0, v1 = p0.get(k, 1.0), p1.get(k, 1.0)
        if isinstance(v0, (int, float)) and isinstance(v1, (int, float)):
            out[k] = v0 + (v1 - v0) * a
        else:
            t0 = tuple(v0) if not isinstance(v0, (int, float)) else (v0,)
            t1 = tuple(v1) if not isinstance(v1, (int, float)) else (v1,)
            n = max(len(t0), len(t1))
            t0 = t0 + (0,) * (n - len(t0)); t1 = t1 + (0,) * (n - len(t1))
            out[k] = tuple(x + (y - x) * a for x, y in zip(t0, t1))
    return out


# ---------------------------------------------------------------- cycles
def loco(stride, knee, arm, elbow, lean, air=0.0, carry=False, guard=False, bounce=False):
    def f(t):
        p = 2 * math.pi * t
        s, c = math.sin(p), math.cos(p)
        pose = dict(
            hips=(lean * 0.5, -arm * 0.08 * s, 0), spine=(lean * 0.3, arm * 0.12 * s, 0),
            chest=(lean * 0.2, arm * 0.1 * s, 0), neck=(-lean * 0.9, -arm * 0.1 * s, 0),
            leg_L=(stride * s + stride * 0.15, 3, 0), leg_R=(-stride * s + stride * 0.15, 3, 0),
            knee_L=8 + knee * max(0.0, c) ** 1.2 + knee * 0.15, knee_R=8 + knee * max(0.0, -c) ** 1.2 + knee * 0.15,
            ankle_L=10 * max(0.0, -s), ankle_R=10 * max(0.0, s),
            arm_L=(-arm * s + arm * 0.15, 10, 0), arm_R=(arm * s + arm * 0.15, 10, 0),
            elbow_L=elbow + elbow * 0.25 * s, elbow_R=elbow - elbow * 0.25 * s,
            lift=air * (abs(s) ** 2),
        )
        if carry:
            pose.update(HOLD)
            pose["arm_L"] = (40 + 4 * s, -14, 0); pose["arm_R"] = (40 + 4 * s, -14, 0)
        if guard:
            pose.update(hips=(4, -25, 0), chest=(0, 14, 0),
                        arm_L=(62, 10, 0), arm_R=(48, 18, 0), elbow_L=105, elbow_R=125)
        if bounce:
            h = abs(math.cos(math.pi * 2 * t))
            pose["arm_R"] = (45 - 25 * (1 - h), 10, 0)
            pose["elbow_R"] = 35 + 40 * h
            pose["ball"] = ("world", -0.22, 0.11 + 0.72 * h, 0.42)
        return pose
    return f


def idle_func(base, amp=1.0, ball=None):
    def f(t):
        s = math.sin(2 * math.pi * t)
        p = dict(base)
        sp = list(p.get("chest", (0, 0, 0))); sp[0] += 2.0 * amp * s
        p["chest"] = tuple(sp)
        for k in ("knee_L", "knee_R"):
            p[k] = p.get(k, 0) + 3 * amp * (1 - s) / 2
        for k in ("arm_L", "arm_R"):
            a = list(p.get(k, (0, 0, 0))); a[0] += 2 * amp * s; a[1] += 1.5 * amp * (1 + s) / 2
            p[k] = tuple(a)
        if ball:
            p["ball"] = ball
        return p
    return f


def K(*pairs):
    return list(pairs)


# ---------------------------------------------------------------- library
LIB = {}


def M(name, category, desc, keys=None, func=None, loop=False):
    LIB[name] = Motion(name, keys, func, loop, desc, category)


# --- locomotion
M("idle", "Locomotion", "default standing pose", func=idle_func(STAND), loop=True)
M("walk", "Locomotion", "standard walk cycle", func=loco(24, 42, 22, 15, 4), loop=True)
M("run", "Locomotion", "jogging", func=loco(36, 80, 42, 80, 10, air=0.03), loop=True)
M("sprint", "Locomotion", "full speed run", func=loco(48, 105, 62, 92, 18, air=0.07), loop=True)
M("stop", "Locomotion", "come to a stop", keys=K(
    (0, P(READY, leg_L=(45, 5, 0), leg_R=(-20, 5, 0), knee_L=20, knee_R=40, hips=(14, 0, 0))),
    (0.35, P(READY, hips=(-8, 0, 0), spine=(-4, 0, 0), leg_L=(55, 6, 0), leg_R=(-10, 6, 0), knee_L=15, knee_R=55,
             arm_L=(40, 30, 0), arm_R=(-10, 30, 0), neck=(0, 0, 0))),
    (0.7, P(READY, hips=(0, 0, 0), leg_L=(30, 6, 0), leg_R=(5, 6, 0), knee_L=35, knee_R=30)),
    (1, P(STAND))))
M("change_direction", "Locomotion", "left / right cut", keys=K(
    (0, P(READY)),
    (0.3, P(READY, hips=(10, 30, -12), chest=(4, 15, -10), leg_L=(20, 30, 0), leg_R=(30, -5, 0), knee_L=60, knee_R=30,
            arm_L=(10, 45, 0), arm_R=(40, 10, 0))),
    (0.65, P(READY, hips=(10, -25, 12), chest=(4, -15, 10), leg_L=(30, 0, 0), leg_R=(20, 30, 0), knee_L=30, knee_R=60,
             arm_L=(40, 10, 0), arm_R=(10, 45, 0))),
    (1, P(READY))))
M("sidestep", "Locomotion", "evasive move", keys=K(
    (0, P(READY)),
    (0.35, P(READY, hips=(10, 0, 14), leg_L=(30, 32, 0), leg_R=(25, -6, 0), knee_L=30, knee_R=60, chest=(4, 0, -12),
             arm_L=(15, 40, 0), arm_R=(30, 20, 0), pos=(0.15, 0))),
    (0.7, P(READY, hips=(10, 0, -6), leg_L=(30, 10, 0), leg_R=(25, 20, 0), pos=(0.25, 0))),
    (1, P(READY))))
M("juke_feint", "Locomotion", "fake move", keys=K(
    (0, P(READY, HOLD)),
    (0.3, P(READY, HOLD, hips=(14, -30, -14), chest=(8, -20, -8), leg_R=(40, -20, 0), knee_R=70, leg_L=(10, 10, 0), knee_L=25)),
    (0.6, P(READY, HOLD, hips=(12, 28, 12), chest=(6, 20, 8), leg_L=(40, 20, 0), knee_L=70, leg_R=(10, 10, 0), knee_R=25)),
    (1, P(READY, HOLD))))
M("spin", "Locomotion", "spin move", keys=K(
    (0, P(READY, HOLD, hips=(10, 0, 0))),
    (0.25, P(READY, HOLD, hips=(10, 90, 0), leg_L=(40, 15, 0), knee_L=70)),
    (0.5, P(READY, HOLD, hips=(10, 180, 0), leg_R=(40, 15, 0), knee_R=70)),
    (0.75, P(READY, HOLD, hips=(10, 270, 0), leg_L=(40, 15, 0), knee_L=70)),
    (1, P(READY, HOLD, hips=(10, 360, 0)))))
M("jump", "Locomotion", "vertical jump", keys=K(
    (0, P(STAND)),
    (0.18, P(CROUCH, arm_L=(-40, 12, 0), arm_R=(-40, 12, 0), elbow_L=20, elbow_R=20)),
    (0.4, P(STAND, arm_L=(160, 15, 0), arm_R=(160, 15, 0), elbow_L=15, elbow_R=15, ankle_L=40, ankle_R=40, lift=0.35)),
    (0.6, P(STAND, arm_L=(150, 20, 0), arm_R=(150, 20, 0), leg_L=(30, 5, 0), leg_R=(20, 5, 0), knee_L=50, knee_R=45,
            ankle_L=30, ankle_R=30, lift=0.45)),
    (0.82, P(CROUCH, leg_L=(60, 8, 0), leg_R=(50, 8, 0), knee_L=90, knee_R=85, arm_L=(50, 30, 0), arm_R=(50, 30, 0))),
    (1, P(STAND))))
M("crouch", "Locomotion", "crouch down", keys=K((0, P(FIGHT)), (0.5, P(CROUCH, arm_L=(70, 10, 0), arm_R=(55, 15, 0), elbow_L=110, elbow_R=120)),
                                              (1, P(CROUCH, arm_L=(70, 10, 0), arm_R=(55, 15, 0), elbow_L=110, elbow_R=120))))

# --- ball handling
M("pick_up_ground", "Ball handling", "collect ball from ground", keys=K(
    (0, P(READY, ball=("world", 0, 0.11, 0.55))),
    (0.35, P(READY, hips=(50, 0, 0), spine=(12, 0, 0), neck=(-35, 0, 0), leg_L=(85, 6, 0), leg_R=(40, 6, 0), knee_L=70, knee_R=30,
             arm_L=(80, -10, 0), arm_R=(80, -10, 0), elbow_L=10, elbow_R=10, ball=("world", 0, 0.11, 0.55))),
    (0.5, P(READY, hips=(50, 0, 0), spine=(12, 0, 0), neck=(-35, 0, 0), leg_L=(85, 6, 0), leg_R=(40, 6, 0), knee_L=70, knee_R=30,
            arm_L=(80, -10, 0), arm_R=(80, -10, 0), elbow_L=10, elbow_R=10, ball="hands")),
    (1, P(STAND, HOLD))))
M("pick_up_aerial", "Ball handling", "catch dropping ball", keys=K(
    (0, P(READY, ball=("world", 0, 2.4, 0.5))),
    (0.4, P(STAND, arm_L=(150, -5, 0), arm_R=(150, -5, 0), elbow_L=20, elbow_R=20, neck=(-30, 0, 0), ball=("world", 0, 2.05, 0.35))),
    (0.55, P(STAND, arm_L=(140, -5, 0), arm_R=(140, -5, 0), elbow_L=30, elbow_R=30, neck=(-25, 0, 0), ball="hands")),
    (1, P(STAND, HOLD))))
M("hold", "Ball handling", "hold ball in hands", func=idle_func(P(STAND, HOLD)), loop=True)
M("carry", "Ball handling", "run with ball", func=loco(34, 75, 0, 0, 10, air=0.03, carry=True), loop=True)
M("bounce_solo", "Ball handling", "solo the ball (dribble)", func=loco(30, 70, 35, 60, 10, air=0.02, bounce=True), loop=True)
M("hand_pass", "Ball handling", "pass with hands", keys=K(
    (0, P(READY, HOLD)),
    (0.35, P(READY, hips=(10, 30, 0), chest=(4, 20, 0), arm_L=(70, -10, 0), elbow_L=40, arm_R=(20, 20, 0), elbow_R=110,
             wrist_R=-20, ball="hand_L")),
    (0.6, P(READY, hips=(10, -15, 0), chest=(4, -20, 0), arm_L=(70, -10, 0), elbow_L=40, arm_R=(85, -10, 0), elbow_R=10,
            ball=("world", 0.0, 1.25, 0.95))),
    (1, P(READY, arm_R=(70, 0, 0), elbow_R=20, ball=("world", 0.0, 1.4, 2.0)))))


def _kick(height, ball_flight):
    hi = height
    return K(
        (0, P(READY, HOLD)),
        (0.25, P(READY, hips=(-4, 0, 0), leg_R=(-45, 5, 0), knee_R=90, leg_L=(10, 5, 0), knee_L=20,
                 arm_L=(70, 20, 0), elbow_L=30, arm_R=(30, 35, 0), elbow_R=30, ball="hand_L")),
        (0.42, P(READY, hips=(-6, 0, 0), leg_R=(10, 5, 0), knee_R=60, arm_L=(40, 30, 0), arm_R=(20, 45, 0),
                 ball=("world", -0.12, 0.35, 0.45))),
        (0.55, P(READY, hips=(-12, 0, 0), spine=(-6, 0, 0), leg_R=(50 + hi, 5, 0), knee_R=8, ankle_R=35,
                 leg_L=(5, 5, 0), knee_L=15, arm_L=(-20, 50, 0), arm_R=(60, 40, 0), ball="foot_R")),
        (0.8, P(READY, hips=(-14, 0, 0), spine=(-8, 0, 0), leg_R=(75 + hi, 5, 0), knee_R=5, ankle_R=35,
                leg_L=(0, 5, 0), knee_L=10, arm_L=(-30, 50, 0), arm_R=(70, 45, 0), ball=ball_flight)),
        (1, P(READY, ball=None)))


M("low_kick_pass", "Kicking", "short kick", keys=_kick(-10, ("world", -0.1, 0.6, 2.6)))
M("high_kick_pass", "Kicking", "long kick", keys=_kick(15, ("world", -0.1, 2.2, 2.6)))
M("shoot_point", "Kicking", "kick over bar", keys=_kick(30, ("world", -0.1, 2.6, 2.4)))
M("shoot_goal", "Kicking", "kick to goal", keys=_kick(0, ("world", -0.1, 1.1, 3.0)))
M("catch_ground", "Ball handling", "catch low ball", keys=K(
    (0, P(READY, ball=("world", 0, 0.5, 2.0))),
    (0.45, P(READY, hips=(35, 0, 0), knee_L=70, knee_R=65, leg_L=(60, 6, 0), leg_R=(50, 6, 0), arm_L=(60, -8, 0), arm_R=(60, -8, 0),
             elbow_L=20, elbow_R=20, ball=("world", 0, 0.5, 0.75))),
    (0.6, P(READY, hips=(35, 0, 0), knee_L=70, knee_R=65, leg_L=(60, 6, 0), leg_R=(50, 6, 0), arm_L=(60, -8, 0), arm_R=(60, -8, 0),
            elbow_L=20, elbow_R=20, ball="hands")),
    (1, P(READY, HOLD))))
M("catch_aerial", "Ball handling", "leap and catch", keys=K(
    (0, P(READY, ball=("world", 0, 2.6, 1.2))),
    (0.3, P(CROUCH, arm_L=(-30, 10, 0), arm_R=(-30, 10, 0), ball=("world", 0, 2.6, 0.7))),
    (0.55, P(STAND, arm_L=(165, -5, 0), arm_R=(165, -5, 0), elbow_L=15, elbow_R=15, leg_L=(40, 5, 0), knee_L=80,
             neck=(-30, 0, 0), lift=0.45, ball="hands")),
    (0.8, P(STAND, HOLD, leg_L=(40, 5, 0), knee_L=60, lift=0.2)),
    (1, P(READY, HOLD))))
M("leap_catch", "Ball handling", "high catch", keys=K(
    (0, P(READY, ball=("world", 0, 3.0, 1.5))),
    (0.25, P(CROUCH, arm_L=(-35, 10, 0), arm_R=(-35, 10, 0), ball=("world", 0, 3.0, 0.9))),
    (0.5, P(STAND, arm_L=(170, -5, 0), arm_R=(170, -5, 0), elbow_L=10, elbow_R=10, leg_L=(70, 5, 0), knee_L=110,
            leg_R=(-10, 5, 0), knee_R=30, neck=(-35, 0, 0), lift=0.7, ball=("world", 0, 2.95, 0.3))),
    (0.62, P(STAND, arm_L=(165, -5, 0), arm_R=(165, -5, 0), elbow_L=20, elbow_R=20, leg_L=(70, 5, 0), knee_L=110,
             neck=(-30, 0, 0), lift=0.7, ball="hands")),
    (0.85, P(STAND, HOLD, leg_L=(30, 5, 0), knee_L=50, lift=0.25)),
    (1, P(READY, HOLD))))
M("fist_pass", "Ball handling", "pass with fist", keys=K(
    (0, P(READY, HOLD)),
    (0.35, P(READY, hips=(8, -25, 0), arm_L=(60, 5, 0), elbow_L=40, arm_R=(-30, 20, 0), elbow_R=80, ball="hand_L")),
    (0.55, P(READY, hips=(8, 25, 0), arm_L=(50, 5, 0), elbow_L=40, arm_R=(95, -5, 0), elbow_R=5, ball=("world", 0, 1.5, 0.9))),
    (1, P(READY, arm_R=(80, 0, 0), elbow_R=10, ball=("world", 0, 1.9, 2.4)))))
M("fist_shoot", "Ball handling", "shoot with fist", keys=K(
    (0, P(READY, HOLD)),
    (0.3, P(READY, hips=(-5, -25, 0), arm_L=(120, 5, 0), elbow_L=20, arm_R=(-40, 20, 0), elbow_R=90, lift=0.1, ball="hand_L")),
    (0.5, P(READY, hips=(-5, 25, 0), arm_L=(100, 5, 0), elbow_L=20, arm_R=(160, -5, 0), elbow_R=5, lift=0.25,
            ball=("world", 0, 2.2, 0.55))),
    (1, P(READY, arm_R=(130, 0, 0), elbow_R=10, ball=("world", 0, 2.8, 2.6)))))

# --- defence / contact
M("tackle", "Defence", "attempt tackle", keys=K(
    (0, P(READY)),
    (0.35, P(READY, hips=(30, 0, 0), leg_L=(60, 6, 0), knee_L=80, leg_R=(-20, 6, 0), knee_R=20, arm_L=(80, 10, 0), arm_R=(80, 10, 0),
             elbow_L=30, elbow_R=30, neck=(-30, 0, 0), pos=(0, 0.2))),
    (0.6, P(READY, hips=(35, 0, 0), leg_L=(70, 6, 0), knee_L=85, leg_R=(-30, 6, 0), knee_R=10, arm_L=(95, -15, 0), arm_R=(95, -15, 0),
            elbow_L=60, elbow_R=60, neck=(-35, 0, 0), pos=(0, 0.35))),
    (1, P(READY, pos=(0, 0.3)))))
M("block", "Defence", "block kick / pass", keys=K(
    (0, P(READY)),
    (0.35, P(STAND, arm_L=(170, 15, 0), arm_R=(170, 15, 0), elbow_L=5, elbow_R=5, ankle_L=30, ankle_R=30, lift=0.25, neck=(-15, 0, 0))),
    (0.6, P(STAND, arm_L=(165, 25, 0), arm_R=(165, 25, 0), elbow_L=10, elbow_R=10, lift=0.3, leg_L=(20, 5, 0), knee_L=30)),
    (1, P(READY))))
M("guard", "Defence", "fighting guard / block", keys=K(
    (0, P(FIGHT)),
    (0.5, P(FIGHT, arm_L=(95, -5, 0), arm_R=(95, -5, 0), elbow_L=130, elbow_R=130, hips=(10, -10, 0), neck=(-12, 0, 0))),
    (1, P(FIGHT, arm_L=(95, -5, 0), arm_R=(95, -5, 0), elbow_L=130, elbow_R=130, hips=(10, -10, 0), neck=(-12, 0, 0)))))
M("fall", "Contact", "fall after contact", keys=K(
    (0, P(READY)),
    (0.3, P(READY, hips=(-25, 0, 10), spine=(-10, 0, 0), arm_L=(40, 60, 0), arm_R=(30, 60, 0), leg_L=(40, 6, 0), knee_L=30, neck=(15, 0, 0))),
    (0.6, P(LIE_BACK, hips=(-60, 0, 5), arm_L=(60, 50, 0), arm_R=(50, 55, 0))),
    (1, P(LIE_BACK))))
M("get_up", "Contact", "recover from fall", keys=K(
    (0, P(LIE_BACK)),
    (0.3, P(LIE_BACK, hips=(-40, 0, 0), spine=(40, 0, 0), chest=(20, 0, 0), arm_L=(-30, 20, 0), arm_R=(-30, 20, 0), elbow_L=10, elbow_R=10,
            knee_L=110, knee_R=100, leg_L=(80, 8, 0), leg_R=(75, 8, 0), neck=(0, 0, 0))),
    (0.6, P(CROUCH, arm_L=(20, 20, 0), arm_R=(-20, 25, 0), elbow_R=10)),
    (1, P(STAND))))
M("injured_idle", "Contact", "hold injury pose", func=idle_func(P(STAND, hips=(15, 0, 6), spine=(10, 0, 0), neck=(-15, 0, 0),
                                                                    leg_R=(30, 5, 0), knee_R=45, leg_L=(15, 5, 0), knee_L=15,
                                                                    arm_R=(55, -20, 0), elbow_R=70, arm_L=(55, -25, 0), elbow_L=70), 0.6),
  loop=True)
M("hit", "Contact", "take a hit / flinch", keys=K(
    (0, P(FIGHT)),
    (0.3, P(FIGHT, hips=(-10, -20, 0), spine=(-12, 0, 0), chest=(-10, 0, 0), neck=(25, 0, 0), arm_L=(30, 40, 0), arm_R=(20, 40, 0),
            elbow_L=40, elbow_R=40, pos=(0, -0.12))),
    (0.6, P(FIGHT, hips=(-6, -20, 0), spine=(-6, 0, 0), neck=(12, 0, 0), pos=(0, -0.15))),
    (1, P(FIGHT, pos=(0, -0.15)))))
M("ko", "Contact", "knocked out", keys=K(
    (0, P(FIGHT)), (0.35, P(FIGHT, hips=(-35, 0, 0), neck=(30, 0, 0), arm_L=(60, 70, 0), arm_R=(60, 70, 0), lift=0.1, pos=(0, -0.3))),
    (0.7, P(LIE_BACK, pos=(0, -0.7))), (1, P(LIE_BACK, pos=(0, -0.7)))))

# --- celebrations
M("celebrate_point", "Celebration", "short celebration", keys=K(
    (0, P(STAND)),
    (0.3, P(STAND, arm_R=(165, 15, 0), elbow_R=5, arm_L=(20, 15, 0), elbow_L=70, neck=(-10, 0, 0))),
    (0.5, P(STAND, arm_R=(150, 15, 0), elbow_R=30, arm_L=(20, 15, 0), elbow_L=80, neck=(-10, 0, 0))),
    (0.7, P(STAND, arm_R=(165, 15, 0), elbow_R=5, arm_L=(20, 15, 0), elbow_L=70, neck=(-10, 0, 0))),
    (1, P(STAND, arm_R=(150, 15, 0), elbow_R=30))))
M("celebrate_goal", "Celebration", "extended celebration", keys=K(
    (0, P(STAND)),
    (0.2, P(CROUCH, arm_L=(-20, 20, 0), arm_R=(-20, 20, 0))),
    (0.4, P(STAND, arm_L=(160, 35, 0), arm_R=(160, 35, 0), elbow_L=10, elbow_R=10, leg_L=(40, 6, 0), knee_L=80,
            ankle_R=40, lift=0.45, neck=(-25, 0, 0))),
    (0.6, P(STAND, arm_L=(150, 40, 0), arm_R=(150, 40, 0), leg_L=(30, 6, 0), knee_L=50, lift=0.2, neck=(-20, 0, 0))),
    (0.8, P(STAND, arm_L=(90, 80, 0), arm_R=(90, 80, 0), elbow_L=10, elbow_R=10, chest=(-10, 0, 0), neck=(-20, 0, 0))),
    (1, P(STAND, arm_L=(160, 35, 0), arm_R=(160, 35, 0), neck=(-20, 0, 0)))))
M("victory", "Celebration", "victory pose", keys=K(
    (0, P(FIGHT)),
    (0.35, P(STAND, arm_R=(170, 10, 0), elbow_R=10, arm_L=(30, 20, 0), elbow_L=100, neck=(-10, 0, 0))),
    (0.6, P(STAND, arm_R=(160, 10, 0), elbow_R=40, arm_L=(30, 20, 0), elbow_L=110, leg_L=(10, 10, 0), neck=(-10, 0, 0))),
    (1, P(STAND, arm_R=(170, 10, 0), elbow_R=10, arm_L=(30, 20, 0), elbow_L=100, leg_L=(10, 10, 0), neck=(-10, 0, 0)))))
M("taunt", "Celebration", "taunt the opponent", keys=K(
    (0, P(FIGHT)),
    (0.3, P(STAND, hips=(0, -20, 0), arm_L=(80, 10, 0), elbow_L=110, wrist_L=40, arm_R=(10, 35, 0), elbow_R=80, neck=(-5, 15, 0))),
    (0.5, P(STAND, hips=(0, -20, 0), arm_L=(80, 10, 0), elbow_L=70, wrist_L=-30, arm_R=(10, 35, 0), elbow_R=80, neck=(-5, 15, 0))),
    (0.7, P(STAND, hips=(0, -20, 0), arm_L=(80, 10, 0), elbow_L=110, wrist_L=40, arm_R=(10, 35, 0), elbow_R=80, neck=(-5, 15, 0))),
    (1, P(FIGHT))))

# --- goalkeeper
M("gk_save", "Goalkeeper", "save attempt", keys=K(
    (0, P(READY, arm_L=(40, 35, 0), arm_R=(40, 35, 0), ball=("world", 0, 1.2, 3.0))),
    (0.4, P(READY, arm_L=(80, 5, 0), arm_R=(80, 5, 0), elbow_L=15, elbow_R=15, ball=("world", 0, 1.25, 1.2))),
    (0.55, P(READY, arm_L=(80, -8, 0), arm_R=(80, -8, 0), elbow_L=30, elbow_R=30, ball="hands")),
    (1, P(READY, HOLD))))


def _dive(sign):
    return K(
        (0, P(READY, arm_L=(40, 35, 0), arm_R=(40, 35, 0))),
        (0.2, P(CROUCH, hips=(15, 0, sign * 15), leg_L=(70, 20, 0), leg_R=(70, 20, 0))),
        (0.45, P(STAND, hips=(0, 0, sign * 65), arm_L=(170, 0, 0), arm_R=(170, 0, 0), elbow_L=5, elbow_R=5,
                 leg_L=(10, 15, 0), leg_R=(-5, 10, 0), lift=0.45, pos=(sign * 0.6, 0), flat=0, ankle_L=40, ankle_R=40)),
        (0.7, P(STAND, hips=(0, 0, sign * 85), arm_L=(170, 0, 0), arm_R=(170, 0, 0), leg_L=(15, 15, 0), knee_L=20,
                lift=0.25, pos=(sign * 1.0, 0), flat=0, ankle_L=40, ankle_R=40)),
        (1, P(STAND, hips=(0, 0, sign * 88), arm_L=(165, -8, 0), arm_R=(165, -8, 0), elbow_L=20, elbow_R=20, leg_L=(30, 10, 0),
              knee_L=50, pos=(sign * 1.1, 0), flat=0, ankle_L=40, ankle_R=40)))


M("gk_dive_left", "Goalkeeper", "dive left", keys=_dive(1))
M("gk_dive_right", "Goalkeeper", "dive right", keys=_dive(-1))
M("gk_throw_out", "Goalkeeper", "throw out", keys=K(
    (0, P(STAND, HOLD)),
    (0.35, P(STAND, hips=(-8, -30, 0), leg_L=(30, 5, 0), knee_L=10, leg_R=(-25, 5, 0), arm_R=(-40, 30, 0), elbow_R=20, arm_L=(80, 10, 0),
             ball="hand_R")),
    (0.6, P(STAND, hips=(12, 20, 0), leg_L=(30, 5, 0), knee_L=30, leg_R=(-25, 5, 0), arm_R=(150, 10, 0), elbow_R=5, arm_L=(20, 20, 0),
            ball=("world", -0.2, 2.0, 0.6))),
    (1, P(READY, arm_R=(110, 10, 0), ball=("world", -0.2, 2.4, 2.4)))))

# --- fighter moves
M("fight_idle", "Fighter", "fighting stance (breathing)", func=idle_func(FIGHT, 1.2), loop=True)
M("fight_walk", "Fighter", "stance walk", func=loco(18, 30, 0, 0, 4, guard=True), loop=True)
M("punch", "Fighter", "straight punch", keys=K(
    (0, P(FIGHT)),
    (0.3, P(FIGHT, hips=(4, -35, 0), arm_R=(40, 25, 0), elbow_R=140)),
    (0.5, P(FIGHT, hips=(8, 5, 0), chest=(4, 25, 0), arm_R=(92, -2, 0), elbow_R=3, leg_L=(30, 7, 0), knee_L=35)),
    (0.7, P(FIGHT, hips=(8, 5, 0), chest=(4, 25, 0), arm_R=(90, -2, 0), elbow_R=8, leg_L=(30, 7, 0), knee_L=35)),
    (1, P(FIGHT))))
M("kick", "Fighter", "front kick", keys=K(
    (0, P(FIGHT)),
    (0.3, P(FIGHT, leg_R=(70, 5, 0), knee_R=120, hips=(-5, -20, 0))),
    (0.5, P(FIGHT, leg_R=(95, 5, 0), knee_R=5, ankle_R=-30, hips=(-15, -20, 0), spine=(-8, 0, 0), arm_L=(40, 30, 0))),
    (0.7, P(FIGHT, leg_R=(90, 5, 0), knee_R=10, ankle_R=-30, hips=(-15, -20, 0), spine=(-8, 0, 0))),
    (0.85, P(FIGHT, leg_R=(60, 5, 0), knee_R=110)),
    (1, P(FIGHT))))
M("special_1", "Fighter", "rising uppercut", keys=K(
    (0, P(FIGHT)),
    (0.25, P(CROUCH, arm_R=(-20, 20, 0), elbow_R=100, hips=(15, -30, 0))),
    (0.5, P(STAND, hips=(-5, 20, 0), arm_R=(170, -5, 0), elbow_R=30, arm_L=(40, 20, 0), elbow_L=100, leg_L=(60, 5, 0), knee_L=90,
            ankle_R=40, lift=0.6)),
    (0.75, P(STAND, hips=(-5, 20, 0), arm_R=(170, -5, 0), elbow_R=20, leg_L=(50, 5, 0), knee_L=80, lift=0.4)),
    (1, P(FIGHT))))
M("special_2", "Fighter", "spinning kick", keys=K(
    (0, P(FIGHT)),
    (0.25, P(FIGHT, hips=(0, -120, 0), leg_R=(20, 30, 0), knee_R=40)),
    (0.5, P(FIGHT, hips=(-10, -220, 20), leg_R=(30, 85, 0), knee_R=5, arm_L=(30, 70, 0), arm_R=(30, 70, 0), lift=0.15)),
    (0.75, P(FIGHT, hips=(-5, -300, 10), leg_R=(30, 60, 0), knee_R=30, lift=0.05)),
    (1, P(FIGHT, hips=(4, -388, 0)))))
M("throw", "Fighter", "grab and throw", keys=K(
    (0, P(FIGHT)),
    (0.3, P(FIGHT, hips=(10, 0, 0), arm_L=(90, -10, 0), arm_R=(90, -10, 0), elbow_L=20, elbow_R=20)),
    (0.5, P(FIGHT, hips=(10, 0, 0), arm_L=(80, -15, 0), arm_R=(80, -15, 0), elbow_L=90, elbow_R=90, pos=(0, -0.1))),
    (0.75, P(FIGHT, hips=(-15, 160, 0), arm_L=(140, 20, 0), arm_R=(140, 20, 0), elbow_L=20, elbow_R=20, leg_L=(40, 5, 0), knee_L=50)),
    (1, P(FIGHT, hips=(4, 332, 0)))))
M("jump_attack", "Fighter", "flying kick", keys=K(
    (0, P(FIGHT)),
    (0.2, P(CROUCH)),
    (0.45, P(FIGHT, leg_L=(80, 5, 0), knee_L=120, leg_R=(20, 5, 0), knee_R=90, lift=0.6)),
    (0.65, P(FIGHT, hips=(-25, -10, 0), leg_R=(100, 5, 0), knee_R=5, ankle_R=-20, leg_L=(40, 5, 0), knee_L=110, lift=0.55,
             arm_L=(40, 40, 0), arm_R=(20, 50, 0))),
    (0.85, P(FIGHT, leg_L=(40, 5, 0), knee_L=60, leg_R=(30, 5, 0), knee_R=60, lift=0.15)),
    (1, P(FIGHT))))

ALIASES = {
    "pickup_ground": "pick_up_ground", "pickup_aerial": "pick_up_aerial", "pick_up": "pick_up_ground",
    "solo": "bounce_solo", "bounce": "bounce_solo", "dribble": "bounce_solo", "juke": "juke_feint", "feint": "juke_feint",
    "jog": "run", "pyramid_blast": "special_1", "bum_fireball": "special_2",  # Egyptian Fighter / Padel Wars special names
    "special1": "special_1", "special2": "special_2", "jumpattack": "jump_attack", "jump_kick": "jump_attack",
    "getup": "get_up", "injured": "injured_idle", "gk_throw": "gk_throw_out", "dive_left": "gk_dive_left",
    "dive_right": "gk_dive_right", "save": "gk_save", "celebrate": "celebrate_point", "knockout": "ko", "ko": "ko",
    "high_kick": "high_kick_pass", "low_kick": "low_kick_pass", "kick_pass": "low_kick_pass", "stance": "fight_idle",
}


def find_motion(name):
    """Resolve a move name (any case/spacing) to a library motion, or None."""
    from .moves import slug
    s = slug(name)
    if s in LIB:
        return LIB[s]
    if s in ALIASES:
        return LIB[ALIASES[s]]
    flat = s.replace("_", "")
    for k in LIB:
        if k.replace("_", "") == flat:
            return LIB[k]
    for k, v in ALIASES.items():
        if k.replace("_", "") == flat:
            return LIB[v]
    return None

# --- kart racer (seated in a kart; the kart prop follows the hips bone)
SEAT = dict(ground=False, lift=-0.58, flat=0, leg_L=(84, 8, 0), leg_R=(84, 8, 0), knee_L=28, knee_R=28,
            ankle_L=-10, ankle_R=-10, arm_L=(55, 6, 0), arm_R=(55, 6, 0), elbow_L=45, elbow_R=45,
            spine=(4, 0, 0), neck=(-4, 0, 0))


def _seat_cycle(**amp):
    def f(t):
        s = math.sin(2 * math.pi * t)
        p = dict(SEAT)
        p["lift"] = SEAT["lift"] + amp.get("bob", 0.008) * s
        p["chest"] = (amp.get("lean", 0) + 1.5 * s, 0, 0)
        return p
    return f


M("kart_idle", "Kart", "sitting in the kart (engine idle)", func=_seat_cycle(bob=0.006), loop=True)
M("kart_drive", "Kart", "driving, hands on the wheel", func=_seat_cycle(bob=0.012, lean=4), loop=True)
M("steer_left", "Kart", "steer left (lean in)", keys=K(
    (0, P(SEAT)), (0.5, P(SEAT, chest=(2, 8, 14), spine=(4, 6, 8), neck=(-4, 10, 6), arm_L=(45, 10, 0), arm_R=(62, 0, 0), hips=(0, 10, 0))),
    (1, P(SEAT, chest=(2, 8, 14), spine=(4, 6, 8), neck=(-4, 10, 6), arm_L=(45, 10, 0), arm_R=(62, 0, 0), hips=(0, 10, 0)))))
M("steer_right", "Kart", "steer right (lean in)", keys=K(
    (0, P(SEAT)), (0.5, P(SEAT, chest=(2, -8, -14), spine=(4, -6, -8), neck=(-4, -10, -6), arm_L=(62, 0, 0), arm_R=(45, 10, 0), hips=(0, -10, 0))),
    (1, P(SEAT, chest=(2, -8, -14), spine=(4, -6, -8), neck=(-4, -10, -6), arm_L=(62, 0, 0), arm_R=(45, 10, 0), hips=(0, -10, 0)))))
M("boost", "Kart", "turbo boost (pushed back)", keys=K(
    (0, P(SEAT)), (0.3, P(SEAT, spine=(-14, 0, 0), chest=(-8, 0, 0), neck=(10, 0, 0), arm_L=(70, 6, 0), arm_R=(70, 6, 0), elbow_L=15, elbow_R=15, lift=-0.55)),
    (0.65, P(SEAT, spine=(-10, 0, 0), chest=(-6, 0, 0), neck=(6, 0, 0), arm_L=(68, 6, 0), arm_R=(68, 6, 0), elbow_L=20, elbow_R=20, lift=-0.57)),
    (1, P(SEAT, spine=(-14, 0, 0), chest=(-8, 0, 0), neck=(10, 0, 0), arm_L=(70, 6, 0), arm_R=(70, 6, 0), elbow_L=15, elbow_R=15, lift=-0.55))))
M("drift", "Kart", "power slide", keys=K(
    (0, P(SEAT)), (0.35, P(SEAT, hips=(0, 28, 4), chest=(0, -14, 10), neck=(-4, -16, 0), arm_L=(40, 10, 0), arm_R=(66, 0, 0))),
    (0.7, P(SEAT, hips=(0, 32, 5), chest=(0, -16, 12), neck=(-4, -18, 0), arm_L=(38, 10, 0), arm_R=(68, 0, 0), lift=-0.575)),
    (1, P(SEAT, hips=(0, 28, 4), chest=(0, -14, 10), neck=(-4, -16, 0), arm_L=(40, 10, 0), arm_R=(66, 0, 0)))))
M("kart_hit", "Kart", "hit by an item (jolt)", keys=K(
    (0, P(SEAT)), (0.25, P(SEAT, hips=(-12, 0, 10), chest=(-10, 0, -8), neck=(20, 0, 0), arm_L=(100, 50, 0), arm_R=(100, 50, 0), elbow_L=20, elbow_R=20, lift=-0.4)),
    (0.6, P(SEAT, hips=(6, 0, -6), chest=(6, 0, 4), neck=(-10, 0, 0), arm_L=(70, 30, 0), arm_R=(70, 30, 0), lift=-0.55)),
    (1, P(SEAT))))
M("spin_out", "Kart", "spin out (full turn)", keys=K(
    (0, P(SEAT)), (0.25, P(SEAT, hips=(0, 90, 0), chest=(0, 0, 12), arm_L=(90, 40, 0), arm_R=(90, 40, 0))),
    (0.5, P(SEAT, hips=(0, 180, 0), chest=(0, 0, 14), arm_L=(110, 50, 0), arm_R=(110, 50, 0), neck=(15, 0, 0))),
    (0.75, P(SEAT, hips=(0, 270, 0), chest=(0, 0, 12), arm_L=(90, 40, 0), arm_R=(90, 40, 0))),
    (1, P(SEAT, hips=(0, 360, 0)))))
M("item_throw", "Kart", "throw an item over the shoulder", keys=K(
    (0, P(SEAT)), (0.3, P(SEAT, chest=(-6, -25, 0), arm_R=(-30, 20, 0), elbow_R=70, ball="hand_R")),
    (0.55, P(SEAT, chest=(6, 20, 0), arm_R=(150, 10, 0), elbow_R=10, ball=("world", -0.3, 1.6, 0.4))),
    (1, P(SEAT, ball=("world", -0.3, 2.2, 1.6)))))
M("kart_victory", "Kart", "victory - arms up in the kart", keys=K(
    (0, P(SEAT)), (0.35, P(SEAT, arm_L=(170, 20, 0), arm_R=(170, 20, 0), elbow_L=10, elbow_R=10, neck=(-12, 0, 0))),
    (0.6, P(SEAT, arm_L=(160, 30, 0), arm_R=(160, 30, 0), elbow_L=35, elbow_R=35, neck=(-12, 0, 0), chest=(-6, 0, 0))),
    (1, P(SEAT, arm_L=(170, 20, 0), arm_R=(170, 20, 0), elbow_L=10, elbow_R=10, neck=(-12, 0, 0)))))
M("defeat", "Kart", "defeated - slumped", keys=K(
    (0, P(SEAT)), (0.5, P(SEAT, spine=(18, 0, 0), chest=(12, 0, 0), neck=(30, 0, 0), arm_L=(20, 6, 0), arm_R=(20, 6, 0), elbow_L=10, elbow_R=10)),
    (1, P(SEAT, spine=(22, 0, 0), chest=(14, 0, 0), neck=(35, 0, 0), arm_L=(14, 6, 0), arm_R=(14, 6, 0), elbow_L=10, elbow_R=10))))
M("kart_taunt", "Kart", "wave / taunt from the kart", keys=K(
    (0, P(SEAT)), (0.3, P(SEAT, arm_R=(150, 40, 0), elbow_R=60, wrist_R=30, neck=(0, -20, 0))),
    (0.5, P(SEAT, arm_R=(150, 25, 0), elbow_R=30, wrist_R=-30, neck=(0, -20, 0))),
    (0.7, P(SEAT, arm_R=(150, 40, 0), elbow_R=60, wrist_R=30, neck=(0, -20, 0))),
    (1, P(SEAT))))


# ---------------------------------------------------------------- v9 NPC / enemy pack motions
def _wave(t):
    p = dict(STAND)
    s = math.sin(2 * math.pi * 2 * t)
    p.update(arm_R=(150, 25 + 18 * s, 0), elbow_R=35 + 20 * s, neck=(-4, 6, 0))
    return p


def _talk(t):
    p = idle_func(STAND, 0.6)(t)
    s = math.sin(2 * math.pi * t); c = math.cos(2 * math.pi * t)
    p.update(arm_R=(35 + 18 * s, 20, 0), elbow_R=70 + 20 * c, arm_L=(25 - 10 * s, 18, 0), elbow_L=60 + 15 * s,
             wrist_R=20 * c, neck=(-3, 8 * s, 0))
    return p


def _look(t):
    p = idle_func(STAND, 0.5)(t)
    y = 40 * math.sin(2 * math.pi * t)
    p.update(neck=(-4, y, 0), chest=(1, y * 0.25, 0))
    return p


def _cower(t):
    p = dict(CROUCH)
    s = math.sin(2 * math.pi * 3 * t)
    p.update(arm_L=(120, 40, 0), arm_R=(120, 40, 0), elbow_L=140, elbow_R=140, neck=(25, 0, 0),
             chest=(14 + 2 * s, 2 * s, 0))
    return p


def _hover(t):
    p = idle_func(STAND, 0.8)(t)
    s = math.sin(2 * math.pi * t)
    p.update(lift=0.18 + 0.05 * s, leg_L=(14, 4, 0), leg_R=(4, 4, 0), knee_L=35, knee_R=20, ankle_L=30, ankle_R=30,
             arm_L=(20, 40 + 8 * s, 0), arm_R=(20, 40 + 8 * s, 0))
    return p


def _hop(t):
    h = math.sin(math.pi * t)
    p = dict(READY) if h < 0.15 else dict(STAND)
    p.update(lift=0.35 * h, arm_L=(30, 25 + 40 * h, 0), arm_R=(30, 25 + 40 * h, 0), pos=(0.25 * t, 0))
    return p


M("wave", "NPC", "wave hello", func=_wave, loop=True)
M("talk", "NPC", "talking with hand gestures (pair with --talk for mouth shapes)", func=_talk, loop=True)
M("look_around", "NPC", "guard / patrol looks left and right", func=_look, loop=True)
M("cower", "NPC", "scared civilian, shaking", func=_cower, loop=True)
M("hover", "NPC", "floating idle (ghosts, spirits)", func=_hover, loop=True)
M("hop", "NPC", "small creature hop", func=_hop, loop=True)
M("patrol", "NPC", "slow patrol walk", func=loco(16, 30, 10, 20, 2), loop=True)
M("limp", "NPC", "injured / zombie shuffle", func=loco(12, 18, 6, 50, 14), loop=True)
M("alert", "NPC", "spots the player: jolt into a guard", keys=K(
    (0, P(STAND)), (0.25, P(STAND, chest=(-8, 0, 0), neck=(-14, 0, 0), arm_L=(20, 30, 0), arm_R=(20, 30, 0), lift=0.03)),
    (0.6, P(FIGHT)), (1, P(FIGHT))))
M("swing_attack", "NPC", "overhead club / sword swing (two hands)", keys=K(
    (0, P(FIGHT)),
    (0.35, P(FIGHT, hips=(-6, -20, 0), chest=(-14, 10, 0), arm_L=(175, 10, 0), arm_R=(175, 10, 0), elbow_L=50, elbow_R=50, neck=(-12, 0, 0))),
    (0.55, P(FIGHT, hips=(18, -10, 0), spine=(14, 0, 0), chest=(14, 0, 0), arm_L=(70, 5, 0), arm_R=(70, 5, 0), elbow_L=5, elbow_R=5,
             leg_L=(38, 7, 0), knee_L=45, pos=(0.12, 0))),
    (0.75, P(FIGHT, hips=(22, -10, 0), spine=(16, 0, 0), arm_L=(35, 5, 0), arm_R=(35, 5, 0), elbow_L=10, elbow_R=10, leg_L=(38, 7, 0), knee_L=45, pos=(0.12, 0))),
    (1, P(FIGHT))))
M("lunge", "NPC", "creature lunge / bite", keys=K(
    (0, P(READY)), (0.3, P(CROUCH, neck=(-30, 0, 0), arm_L=(-20, 20, 0), arm_R=(-20, 20, 0))),
    (0.55, P(READY, hips=(40, 0, 0), spine=(20, 0, 0), neck=(-45, 0, 0), arm_L=(110, 15, 0), arm_R=(110, 15, 0), elbow_L=20, elbow_R=20,
             leg_R=(-40, 6, 0), knee_R=10, lift=0.12, pos=(0.35, 0))),
    (0.8, P(READY, pos=(0.35, 0))), (1, P(READY, pos=(0.35, 0)))))
M("cast", "NPC", "spell cast: gather then thrust both hands forward", keys=K(
    (0, P(STAND)), (0.35, P(STAND, arm_L=(40, -10, 0), arm_R=(40, -10, 0), elbow_L=110, elbow_R=110, chest=(-6, 0, 0), neck=(-6, 0, 0))),
    (0.6, P(STAND, hips=(8, 0, 0), arm_L=(88, 6, 0), arm_R=(88, 6, 0), elbow_L=5, elbow_R=5, leg_L=(25, 5, 0), knee_L=25)),
    (0.8, P(STAND, hips=(8, 0, 0), arm_L=(92, 6, 0), arm_R=(92, 6, 0), elbow_L=5, elbow_R=5, leg_L=(25, 5, 0), knee_L=25)),
    (1, P(STAND))))
M("roar", "NPC", "boss roar: arms wide, head back", keys=K(
    (0, P(FIGHT)), (0.3, P(READY, chest=(12, 0, 0), arm_L=(30, 20, 0), arm_R=(30, 20, 0))),
    (0.6, P(STAND, chest=(-16, 0, 0), neck=(-30, 0, 0), arm_L=(60, 85, 0), arm_R=(60, 85, 0), elbow_L=40, elbow_R=40)),
    (0.85, P(STAND, chest=(-16, 0, 0), neck=(-30, 0, 0), arm_L=(64, 88, 0), arm_R=(64, 88, 0), elbow_L=30, elbow_R=30)),
    (1, P(FIGHT))))
M("die", "NPC", "fall forward and stay down", keys=K(
    (0, P(FIGHT)), (0.3, P(FIGHT, hips=(-20, 0, 0), neck=(30, 0, 0), arm_L=(40, 50, 0), arm_R=(40, 50, 0), pos=(0, -0.1))),
    (0.55, P(CROUCH, neck=(10, 0, 0), arm_L=(10, 20, 0), arm_R=(10, 20, 0))),
    (0.85, P(LIE_FRONT, pos=(0.3, 0))), (1, P(LIE_FRONT, pos=(0.3, 0)))))
M("sit", "NPC", "sitting idle (shopkeepers, villagers)", func=idle_func(dict(SEAT), 0.5), loop=True)
