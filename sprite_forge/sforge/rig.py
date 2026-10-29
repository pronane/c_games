"""Procedural humanoid skeleton (generic mannequin - not a likeness of anyone).

Coordinate system: Y up, character faces +Z, units = metres (glTF convention).
Poses are written with *semantic* channels so motions are easy to author:

  hips   (pitch, yaw, roll)          whole upper+lower body around the pelvis
  spine / chest / neck (fwd, twist, side)
  arm_L / arm_R  (fwd, out, twist)   shoulder swing forward / abduction / twist
  elbow_L / elbow_R  bend             forearm flexes forward
  wrist_L / wrist_R  bend
  leg_L / leg_R  (fwd, out, twist)   hip swing forward / abduction
  knee_L / knee_R    bend             shin folds backwards
  ankle_L / ankle_R  extra toe-down   (feet are auto-flattened unless flat=0)
  pos   (x, z)  in-place offset of the root (metres)
  lift  metres above the ground       (after automatic grounding)
  flat  0..1  auto flat-foot weight
  ball  None | 'hands' | 'hand_R' | 'hand_L' | 'foot_R' | 'foot_L' | 'chest'
        | ('world', x, y, z)  ball position relative to the root on the ground
"""
from __future__ import annotations
import numpy as np
from .mathutil import euler, mat4

# name, parent, rest offset from parent (metres)
JOINTS = [
    ("root", None, (0.0, 0.0, 0.0)),
    ("hips", "root", (0.0, 0.95, 0.0)),
    ("spine", "hips", (0.0, 0.10, 0.0)),
    ("chest", "spine", (0.0, 0.20, 0.0)),
    ("neck", "chest", (0.0, 0.21, 0.0)),
    ("head", "neck", (0.0, 0.08, 0.0)),
    ("upperarm_L", "chest", (0.20, 0.15, 0.0)),
    ("forearm_L", "upperarm_L", (0.0, -0.28, 0.0)),
    ("hand_L", "forearm_L", (0.0, -0.26, 0.0)),
    ("upperarm_R", "chest", (-0.20, 0.15, 0.0)),
    ("forearm_R", "upperarm_R", (0.0, -0.28, 0.0)),
    ("hand_R", "forearm_R", (0.0, -0.26, 0.0)),
    ("thigh_L", "hips", (0.10, -0.04, 0.0)),
    ("shin_L", "thigh_L", (0.0, -0.42, 0.0)),
    ("foot_L", "shin_L", (0.0, -0.41, 0.0)),
    ("thigh_R", "hips", (-0.10, -0.04, 0.0)),
    ("shin_R", "thigh_R", (0.0, -0.42, 0.0)),
    ("foot_R", "shin_R", (0.0, -0.41, 0.0)),
    ("ball", "root", (0.0, 1.0, 0.3)),
]
JOINT_NAMES = [j[0] for j in JOINTS]
PARENT = {j[0]: j[1] for j in JOINTS}
OFFSET = {j[0]: np.array(j[2], dtype=np.float64) for j in JOINTS}
BALL_RADIUS = 0.11
HEIGHT = 1.80  # standing height incl. head


def rest_world():
    """World-space rest (bind) position of every joint."""
    out = {}
    for n in JOINT_NAMES:
        p = PARENT[n]
        out[n] = OFFSET[n] + (out[p] if p else 0)
    return out


def _v(pose, key, n=3):
    v = pose.get(key, 0)
    if isinstance(v, (int, float)):
        return (float(v),) + (0.0,) * (n - 1) if n > 1 else float(v)
    v = tuple(float(x) for x in v)
    return v + (0.0,) * (n - len(v))


def local_rotations(pose):
    """Semantic pose -> local rotation matrix per joint."""
    R = {n: np.eye(3) for n in JOINT_NAMES}
    hp, hy, hr = _v(pose, "hips")
    R["hips"] = euler(hp, hy, hr)
    for j in ("spine", "chest"):
        f, t, s = _v(pose, j)
        R[j] = euler(f, t, -s)
    f, t, s = _v(pose, "neck")
    R["head"] = euler(f, t, -s)
    for side, sg in (("L", 1.0), ("R", -1.0)):
        f, o, tw = _v(pose, "arm_" + side)
        R["upperarm_" + side] = euler(-f, sg * tw, sg * o)
        R["forearm_" + side] = euler(-_v(pose, "elbow_" + side, 1), 0, 0)
        R["hand_" + side] = euler(-_v(pose, "wrist_" + side, 1), 0, 0)
        f, o, tw = _v(pose, "leg_" + side)
        R["thigh_" + side] = euler(-f, sg * tw, sg * o)
        k = _v(pose, "knee_" + side, 1)
        R["shin_" + side] = euler(k, 0, 0)
        flat = float(pose.get("flat", 1.0))
        a = _v(pose, "ankle_" + side, 1) + flat * (f - k - hp)
        R["foot_" + side] = euler(a, 0, 0)
    return R


# points (joint, local offset) used to find the lowest point for auto-grounding
_CONTACT = [
    ("foot_L", (0, -0.08, -0.06)), ("foot_L", (0, -0.08, 0.18)),
    ("foot_R", (0, -0.08, -0.06)), ("foot_R", (0, -0.08, 0.18)),
    ("shin_L", (0, 0, 0.06)), ("shin_R", (0, 0, 0.06)),
    ("hand_L", (0, -0.10, 0)), ("hand_R", (0, -0.10, 0)),
    ("forearm_L", (0, 0, 0)), ("forearm_R", (0, 0, 0)),
    ("head", (0, 0.27, 0)), ("head", (0, 0.10, 0.12)), ("head", (0, 0.10, -0.12)),
    ("hips", (0, -0.15, -0.12)), ("hips", (0.15, -0.1, 0)), ("hips", (-0.15, -0.1, 0)),
    ("chest", (0, 0.15, -0.12)), ("chest", (0, 0.15, 0.12)),
    ("upperarm_L", (0.05, 0, 0)), ("upperarm_R", (-0.05, 0, 0)),
]


def _fk(Rloc, root_t):
    W = {}
    for n in JOINT_NAMES:
        p = PARENT[n]
        t = root_t if n == "root" else OFFSET[n]
        L = mat4(Rloc[n], t)
        W[n] = L if p is None else W[p] @ L
    return W


def _pt(W, j, off):
    return (W[j] @ np.array([off[0], off[1], off[2], 1.0]))[:3]


class FrameState:
    """Result of evaluating a pose: world matrices + local transforms (for glTF)."""

    def __init__(self, world, local_R, root_t, ball_pos):
        self.world = world
        self.local_R = local_R
        self.root_t = root_t
        self.ball_pos = ball_pos  # world xyz or None (hidden)


def ball_point(W, spec, root_t):
    if spec is None:
        return None
    if isinstance(spec, (tuple, list)) and spec and spec[0] == "world":
        return np.array(spec[1:4], dtype=np.float64) + np.array([root_t[0], 0, root_t[2]])
    if spec in ("hand_R", "hand_L"):
        return _pt(W, spec, (0, -0.12, 0.10))
    if spec in ("foot_R", "foot_L"):
        return _pt(W, spec, (0, -0.0, 0.27))
    if spec == "hands":
        return (_pt(W, "hand_L", (0, -0.08, 0.04)) + _pt(W, "hand_R", (0, -0.08, 0.04))) / 2
    if spec == "chest":
        return _pt(W, "chest", (0, 0.05, 0.25))
    if spec == "overhead":
        return _pt(W, "head", (0, 0.45, 0.05))
    return None


def evaluate(pose, ball_mix=None):
    """pose dict -> FrameState.  ball_mix = (spec0, spec1, a) for interpolation."""
    Rloc = local_rotations(pose)
    px, pz = (list(pose.get("pos", (0, 0))) + [0, 0])[:2]
    root_t = np.array([px, 0.0, pz])
    W = _fk(Rloc, root_t)
    if pose.get("ground", True):
        low = min(_pt(W, j, o)[1] for j, o in _CONTACT)
        root_t[1] = -low
    root_t[1] += float(pose.get("lift", 0.0))
    W = _fk(Rloc, root_t)
    if ball_mix is None:
        bp = ball_point(W, pose.get("ball"), root_t)
    else:
        s0, s1, a = ball_mix
        p0, p1 = ball_point(W, s0, root_t), ball_point(W, s1, root_t)
        if p0 is None and p1 is None:
            bp = None
        elif p0 is None:
            bp = p1 if a > 0.5 else None
        elif p1 is None:
            bp = p0 if a < 0.5 else None
        else:
            bp = p0 * (1 - a) + p1 * a
    return FrameState(W, Rloc, root_t, bp)
