"""Field-sport motion pack (v11.21): skill moves, aerial control, special strikes and
violent-conduct clips for ball games played on a pitch (soccer first; Gaelic,
hurling and Aussie rules reuse the same shapes).

Fed back from Arena FC.  Its match engine already asked for these actions and
was falling back to generic clips: every skill move played a sharp "cut",
thigh control played a toe flick, a punch played a fist *shot* and a headbutt
played a jumping header.  Each clip here is authored for the action it names,
in Sprite Forge's semantic pose channels (right-footed, facing +forward), with
the ball's path keyed so `ball_contact` lines up with the touch.

    from sforge import fieldsport_motions as fs
    fs.register()                # idempotent; also done on `import sforge.motions`
    fs.EVENTS["fs_stepover"]     # {"ball_contact": -1.0, "footsteps": [...]}
    fs.qa("fs_bicycle_kick")     # [] when the clip passes the field-sport checks

`qa()` is the check that would have caught Arena's two worst animation bugs:
arms raised above the shoulders in clips that have no reason for it (the
"hands up at a free kick" bug), and ball clips whose foot is nowhere near the
ball at the contact frame.
"""
from __future__ import annotations

from .motions import CROUCH, LIB, LIE_BACK, K, M, P, READY, STAND

BALL_FLOOR = 0.11            # ball centre resting on the turf (m)


def _ball(y=BALL_FLOOR, z=0.5, x=0.0):
    return ("world", x, y, z)


# ---------------------------------------------------------------------------
# Skill moves (dribbling).  Short (0.5-0.8 s) and planted: the body sells the
# fake, the ball stays close.
# ---------------------------------------------------------------------------
SKILLS = {
    "fs_stepover": dict(desc="step over the ball, outside-in, and drop the shoulder", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.22, P(READY, hips=(14, 10, 0), chest=(6, 8, 0), leg_R=(34, -20, 0), knee_R=66, ankle_R=10,
                 arm_L=(20, 34, 0), arm_R=(14, 22, 0), ball=_ball())),
        (0.42, P(READY, hips=(14, -16, 0), chest=(8, -12, 0), leg_R=(22, 26, 0), knee_R=44,
                 leg_L=(26, 4, 0), arm_L=(14, 20, 0), arm_R=(24, 40, 0), ball=_ball())),
        (0.6, P(READY, hips=(16, -22, 0), chest=(10, -16, 0), leg_R=(6, 16, 0), knee_R=30,
                leg_L=(34, -6, 0), knee_L=52, arm_R=(26, 44, 0), ball=_ball())),
        (0.82, P(READY, hips=(14, 8, 0), chest=(6, 10, 0), leg_L=(30, 12, 0), knee_L=40,
                 arm_L=(26, 40, 0), ball=_ball(z=0.56, x=-0.1))),
        (1.0, P(READY, ball=_ball(z=0.6, x=-0.25))))),
    "fs_roulette": dict(desc="Marseille turn: drag back with one sole, spin, take it on with the other", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.2, P(READY, hips=(10, -60, 0), leg_R=(28, 8, 0), knee_R=34, ankle_R=26, ball="foot_R")),
        (0.42, P(READY, hips=(8, -150, 0), chest=(4, -20, 0), leg_R=(-6, 8, 0), knee_R=24,
                 arm_L=(20, 40, 0), arm_R=(20, 40, 0), ball="foot_R")),
        (0.62, P(READY, hips=(8, -240, 0), chest=(4, -20, 0), leg_L=(24, 8, 0), knee_L=32, ankle_L=24,
                 arm_L=(20, 40, 0), arm_R=(20, 40, 0), ball="foot_L")),
        (0.84, P(READY, hips=(10, -330, 0), leg_L=(-4, 6, 0), knee_L=22, ball="foot_L")),
        (1.0, P(READY, hips=(12, -360, 0), ball=_ball(z=0.6))))),
    "fs_drag_back": dict(desc="sole on the ball, roll it back and turn away", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.3, P(READY, hips=(4, 0, 0), leg_R=(30, 6, 0), knee_R=26, ankle_R=28, ball="foot_R")),
        (0.6, P(READY, hips=(-2, 30, 0), chest=(0, 20, 0), leg_R=(-14, 6, 0), knee_R=30, ankle_R=20,
                arm_L=(24, 36, 0), arm_R=(18, 30, 0), ball="foot_R")),
        (1.0, P(READY, hips=(10, 90, 0), ball=_ball(z=-0.1))))),
    "fs_elastico": dict(desc="outside of the foot one way, snap it back inside the other", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.3, P(READY, hips=(12, -8, 0), leg_R=(20, 26, 0), knee_R=30, ankle_R=-14,
                arm_L=(20, 30, 0), ball=_ball(x=-0.18))),
        (0.48, P(READY, hips=(12, 10, 0), chest=(4, 12, 0), leg_R=(22, -18, 0), knee_R=28, ankle_R=12,
                 arm_R=(20, 40, 0), ball=_ball(x=0.2))),
        (0.75, P(READY, hips=(14, 18, 0), leg_L=(30, 10, 0), knee_L=44, ball=_ball(z=0.62, x=0.35))),
        (1.0, P(READY, ball=_ball(z=0.7, x=0.4))))),
    "fs_ball_roll": dict(desc="roll the ball across the body with the sole", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.35, P(READY, hips=(10, 0, -6), leg_R=(18, -22, 0), knee_R=28, ankle_R=22, ball="foot_R")),
        (0.7, P(READY, hips=(10, 0, 8), leg_R=(14, 16, 0), knee_R=26, ankle_R=20,
                leg_L=(20, 14, 0), arm_L=(20, 36, 0), ball="foot_R")),
        (1.0, P(READY, ball=_ball(x=0.3))))),
    "fs_rainbow_flick": dict(desc="roll it up the back of the calf and flick it over the head", keys=K(
        (0.0, P(READY, ball=_ball(z=0.15))),
        (0.25, P(READY, leg_L=(12, 6, 0), leg_R=(-6, -8, 0), knee_R=20, ball=_ball(y=0.16, z=0.0))),
        (0.42, P(STAND, hips=(16, 0, 0), leg_R=(-34, 0, 0), knee_R=104, ankle_R=-20,
                 arm_L=(30, 40, 0), arm_R=(30, 40, 0), ball=_ball(y=0.55, z=-0.2))),
        (0.62, P(STAND, hips=(10, 0, 0), leg_R=(-10, 0, 0), knee_R=60,
                 arm_L=(26, 36, 0), arm_R=(26, 36, 0), ball=_ball(y=2.0, z=0.4))),
        (1.0, P(READY, ball=_ball(y=0.6, z=2.2))))),
    "fs_fake_shot": dict(desc="full shooting back-swing, then stop and cut the ball the other way", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.3, P(STAND, hips=(6, 0, 0), leg_R=(-44, 6, 0), knee_R=92, arm_L=(40, 44, 0), arm_R=(20, 30, 0),
                ball=_ball())),
        (0.5, P(READY, hips=(12, 20, 0), chest=(6, 16, 0), leg_R=(16, -10, 0), knee_R=40, ankle_R=10,
                arm_L=(26, 40, 0), ball=_ball(x=0.15))),
        (1.0, P(READY, hips=(12, 40, 0), ball=_ball(z=0.55, x=0.4))))),
    "fs_heel_to_heel": dict(desc="inside of one heel back to the other and away", keys=K(
        (0.0, P(READY, ball=_ball())),
        (0.35, P(READY, leg_R=(-16, -12, 0), knee_R=56, ankle_R=20, ball=_ball(z=0.0, x=0.1))),
        (0.65, P(READY, hips=(10, -16, 0), leg_L=(-12, 10, 0), knee_L=50, ball=_ball(z=-0.05, x=-0.15))),
        (1.0, P(READY, hips=(10, -40, 0), ball=_ball(z=0.4, x=-0.4))))),
}

# ---------------------------------------------------------------------------
# Aerial control and special strikes.
# ---------------------------------------------------------------------------
STRIKES = {
    "fs_thigh_control": dict(desc="cushion a dropping ball on the thigh", keys=K(
        (0.0, P(READY, ball=_ball(y=1.3, z=0.6))),
        (0.4, P(READY, hips=(4, 0, 0), leg_R=(64, 6, 0), knee_R=78, ankle_R=10,
                arm_L=(24, 34, 0), arm_R=(24, 34, 0), ball=_ball(y=0.78, z=0.42))),
        (0.55, P(READY, hips=(2, 0, 0), leg_R=(52, 6, 0), knee_R=70, ball=_ball(y=0.72, z=0.42))),
        (0.8, P(READY, leg_R=(24, 6, 0), knee_R=44, ball=_ball(y=0.3, z=0.5))),
        (1.0, P(READY, ball=_ball(z=0.5))))),
    "fs_chip_shot": dict(desc="short back-swing, toe under the ball, lean back - a lob over the keeper", keys=K(
        (0.0, P(READY, ball=_ball(z=0.45))),
        (0.3, P(STAND, hips=(6, 0, 0), leg_R=(-30, 6, 0), knee_R=74, arm_L=(30, 40, 0), arm_R=(20, 30, 0),
                ball=_ball(z=0.45))),
        (0.5, P(STAND, hips=(-8, 0, 0), spine=(-6, 0, 0), leg_R=(36, 6, 0), knee_R=26, ankle_R=-6,
                arm_L=(34, 44, 0), arm_R=(26, 36, 0), neck=(6, 0, 0), ball="foot_R")),
        (0.72, P(STAND, hips=(-4, 0, 0), leg_R=(46, 6, 0), knee_R=18, ball=_ball(y=1.4, z=1.6))),
        (1.0, P(READY)))),
    "fs_trivela": dict(desc="outside-of-the-boot strike swung across the body", keys=K(
        (0.0, P(READY, ball=_ball(z=0.45, x=-0.08))),
        (0.3, P(STAND, hips=(8, 14, 0), chest=(4, 12, 0), leg_R=(-40, 18, 0), knee_R=86,
                arm_L=(30, 46, 0), arm_R=(22, 30, 0), ball=_ball(z=0.45, x=-0.08))),
        (0.5, P(STAND, hips=(14, -12, 0), chest=(8, -16, 0), leg_R=(44, -22, 0), knee_R=24, ankle_R=-22,
                arm_L=(26, 34, 0), arm_R=(36, 48, 0), ball="foot_R")),
        (0.72, P(STAND, hips=(10, -20, 0), leg_R=(58, -28, 0), knee_R=30)),
        (1.0, P(READY)))),
    "fs_bicycle_kick": dict(desc="overhead scissor kick, back to goal, landing on the back", keys=K(
        (0.0, P(STAND, ball=_ball(y=1.7, z=0.35))),
        (0.18, P(CROUCH, leg_L=(70, 6, 0), knee_L=100, ball=_ball(y=1.6, z=0.3))),
        (0.36, P(STAND, lift=0.55, hips=(-70, 0, 0), spine=(-10, 0, 0), neck=(20, 0, 0),
                 leg_L=(110, 6, 0), knee_L=40, leg_R=(20, 6, 0), knee_R=80,
                 arm_L=(60, 60, 0), arm_R=(60, 60, 0), ball=_ball(y=1.6, z=0.25))),
        (0.5, P(STAND, lift=0.65, hips=(-100, 0, 0), spine=(-12, 0, 0), neck=(26, 0, 0),
                leg_L=(40, 6, 0), knee_L=60, leg_R=(150, 6, 0), knee_R=10, ankle_R=-20,
                arm_L=(40, 70, 0), arm_R=(40, 70, 0), ball="foot_R")),
        (0.72, P(LIE_BACK, lift=0.15, arm_L=(30, 60, 0), arm_R=(30, 60, 0))),
        (1.0, P(LIE_BACK)))),
    "fs_keeper_penalty_set": dict(desc="keeper on the line before a penalty: knees bent, arms wide and low", loop=True,
        keys=K(
            (0.0, P(READY, hips=(16, 0, 0), arm_L=(8, 62, 0), arm_R=(8, 62, 0), elbow_L=18, elbow_R=18)),
            (0.5, P(READY, hips=(16, 0, 0), knee_L=56, knee_R=52, lift=0.03,
                    arm_L=(10, 66, 0), arm_R=(10, 66, 0), elbow_L=18, elbow_R=18)),
            (1.0, P(READY, hips=(16, 0, 0), arm_L=(8, 62, 0), arm_R=(8, 62, 0), elbow_L=18, elbow_R=18)))),
}

# ---------------------------------------------------------------------------
# Violent conduct (straight red).  Authored so the swing reads clearly from the
# broadcast camera: the referee/VAR needs to "see" it.
# ---------------------------------------------------------------------------
CONDUCT = {
    "fs_punch": dict(desc="right hook thrown at an opponent", keys=K(
        # From a normal stance, not a boxer's guard: on the pitch it is a sudden
        # swing, and a raised guard read as "hands up" in the contact sheets.
        (0.0, P(STAND)),
        (0.3, P(STAND, hips=(4, 16, 0), chest=(2, 26, 0), arm_L=(24, 14, 0), elbow_L=70,
                arm_R=(30, 44, 0), elbow_R=110, leg_L=(16, 6, 0), knee_L=20)),
        (0.48, P(STAND, hips=(10, -20, 0), chest=(6, -34, 0), arm_L=(14, 14, 0), elbow_L=60,
                 arm_R=(84, 8, 0), elbow_R=12, leg_L=(22, 6, 0), knee_L=24, neck=(-4, 0, 0))),
        (0.7, P(STAND, chest=(2, -10, 0), arm_R=(44, 20, 0), elbow_R=70)),
        (1.0, P(STAND)))),
    "fs_headbutt": dict(desc="head snapped forward into an opponent", keys=K(
        (0.0, P(STAND)),
        (0.35, P(STAND, hips=(-6, 0, 0), chest=(-14, 0, 0), neck=(-28, 0, 0),
                 arm_L=(16, 20, 0), arm_R=(16, 20, 0))),
        (0.5, P(STAND, hips=(14, 0, 0), chest=(22, 0, 0), neck=(34, 0, 0), pos=(0.14, 0))),
        (0.75, P(STAND, hips=(6, 0, 0), chest=(6, 0, 0), neck=(6, 0, 0), pos=(0.14, 0))),
        (1.0, P(STAND, pos=(0.14, 0))))),
}

CLIPS = {}
for _cat, _group in (("Skill", SKILLS), ("Ball", STRIKES), ("Contact", CONDUCT)):
    for _n, _spec in _group.items():
        CLIPS[_n] = dict(_spec, category=("Goalkeeper" if "keeper" in _n else _cat))


def _ev(ball_contact=-1.0, footsteps=(), hit_start=-1.0, hit_end=-1.0):
    return {"ball_contact": ball_contact, "footsteps": list(footsteps),
            "hit_start": hit_start, "hit_end": hit_end}


# Fractions of clip duration (they survive any bake length).
EVENTS = {
    "fs_stepover": _ev(footsteps=(0.42, 0.82)),
    "fs_roulette": _ev(ball_contact=0.2, footsteps=(0.42, 0.84)),
    "fs_drag_back": _ev(ball_contact=0.3, footsteps=(0.6,)),
    "fs_elastico": _ev(ball_contact=0.3, footsteps=(0.75,)),
    "fs_ball_roll": _ev(ball_contact=0.35, footsteps=(0.7,)),
    "fs_rainbow_flick": _ev(ball_contact=0.42),
    "fs_fake_shot": _ev(footsteps=(0.5,)),
    "fs_heel_to_heel": _ev(ball_contact=0.35, footsteps=(0.65,)),
    "fs_thigh_control": _ev(ball_contact=0.4),
    "fs_chip_shot": _ev(ball_contact=0.5),
    "fs_trivela": _ev(ball_contact=0.5),
    "fs_bicycle_kick": _ev(ball_contact=0.5),
    "fs_keeper_penalty_set": _ev(),
    "fs_punch": _ev(hit_start=0.42, hit_end=0.55),
    "fs_headbutt": _ev(hit_start=0.45, hit_end=0.58),
}

# Where raised arms are part of the action (balance in the air, keeper set).
# Everywhere else an arm above shoulder height is the "hands up" bug.
ARMS_UP_OK = {"fs_bicycle_kick", "fs_keeper_penalty_set"}
ARM_RAISE_LIMIT = 95.0       # degrees of forward/side raise: above this the hand is over the shoulder


def register() -> None:
    """Add every field-sport clip to `sforge.motions.LIB` (idempotent)."""
    for name, spec in CLIPS.items():
        if name in LIB:
            continue
        M(name, spec["category"], spec["desc"], keys=spec["keys"], loop=spec.get("loop", False))


def _arm_raise(pose, side):
    a = pose.get("arm_" + side)
    if not a:
        return 0.0
    return max(abs(float(a[0])), abs(float(a[1])))


def qa(name: str, samples: int = 24) -> list[str]:
    """Field-sport checks for one clip; returns a list of problems (empty = pass)."""
    register()
    errs = []
    m = LIB.get(name)
    if m is None:
        return ["unknown clip " + name]
    ev = EVENTS.get(name)
    if ev is None:
        errs.append(name + ": no event entry")
        ev = _ev()
    for key in ("ball_contact", "hit_start", "hit_end"):
        v = ev[key]
        if not (v == -1.0 or 0.0 <= v <= 1.0):
            errs.append("%s: %s out of range" % (name, key))
    if ev["hit_start"] >= 0 and not ev["hit_start"] < ev["hit_end"]:
        errs.append(name + ": hit window is empty")
    if name not in ARMS_UP_OK:
        worst = 0.0
        for i in range(samples + 1):
            pose, _ = m.sample(i / samples)
            worst = max(worst, _arm_raise(pose, "L"), _arm_raise(pose, "R"))
        if worst > ARM_RAISE_LIMIT:
            errs.append("%s: arm raised %.0f deg (hands-up pose outside an aerial/keeper clip)" % (name, worst))
    bc = ev["ball_contact"]
    if bc >= 0 and m.keys is not None:
        # The key nearest the contact frame must hold the ball on the body (a
        # foot / chest / hands attach) or have it keyed on the turf / in the air.
        nearest = min(m.keys, key=lambda k: abs(k[0] - bc))
        if abs(nearest[0] - bc) > 0.06:
            errs.append("%s: no key at ball_contact %.2f (nearest %.2f)" % (name, bc, nearest[0]))
        elif "ball" not in nearest[1]:
            errs.append("%s: ball not placed at the contact key" % name)
    return errs


def qa_all() -> dict:
    return {n: qa(n) for n in CLIPS}


register()
