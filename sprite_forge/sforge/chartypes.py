"""v11.4 character types — motion personality as data, not a costume.

A type is one JSON file. It does not change clothes, colours or the mesh (that is
variants.py). Applied to the same shared-skeleton clip it changes four things:

  timing   how long the action takes. 1 = unchanged. Above 1 is slower: the strike
           peaks later in the clip, and playback fps drops so the sheet lasts longer.
  stance   how wide the character stands and guards. Above 1 is wider.
  reach    how far the arms and legs extend. Above 1 swings further and straightens
           the elbow / knee; below 1 shortens the reach.
  weight   how heavy it feels. Above 1 adds knee bend, a wind-up and a follow-through.
           Below 1 is lighter and snappier.

Shipped types live in character_types/*.json. A new type is a new file — drop it in
that folder, or pass a path to forge.py build --character-type. Names are not
special-cased in the engine.

This wraps motions the mannequin / spec / sculpt / library-rig pipeline samples
(procedural presets and motion-library clips). It does not redraw photo-puppet 2D
poses; those keep their own channels. Playback fps is still scaled, so a heavy type
plays a photo sheet slower.
"""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .motions import Motion
from .rig import evaluate

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPE_DIR = os.path.join(HERE, "character_types")

# clamps so a bad file cannot fold the body inside out
_LIM = {
    "timing": (0.45, 2.5),
    "stance": (0.55, 2.2),
    "reach": (0.55, 1.8),
    "weight": (0.45, 2.2),
}
_AXES = ("timing", "stance", "reach", "weight")


def _clip(name, v):
    lo, hi = _LIM[name]
    return min(hi, max(lo, float(v)))


def list_types():
    """names of the shipped JSON types (a path is also a valid type)."""
    if not os.path.isdir(TYPE_DIR):
        return []
    out = []
    for f in sorted(os.listdir(TYPE_DIR)):
        if f.endswith(".json"):
            out.append(os.path.splitext(f)[0])
    return out


def path_of(name_or_path):
    if not name_or_path:
        raise ValueError("character type name is empty")
    if os.path.isfile(name_or_path):
        return name_or_path
    p = name_or_path if name_or_path.endswith(".json") else name_or_path + ".json"
    if os.path.isfile(p):
        return p
    cand = os.path.join(TYPE_DIR, os.path.basename(p))
    if os.path.isfile(cand):
        return cand
    raise FileNotFoundError("character type '%s' not found (have: %s)" % (name_or_path, ", ".join(list_types()) or "none"))


def load(name_or_path):
    """-> spec dict with name, label, games, timing, stance, reach, weight, notes, path."""
    p = path_of(name_or_path)
    with open(p, encoding="utf-8") as f:
        try:
            d = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("%s is not valid JSON: %s" % (p, e))
    if not isinstance(d, dict):
        raise ValueError("%s must be a JSON object" % p)
    name = str(d.get("name") or os.path.splitext(os.path.basename(p))[0])
    spec = {
        "name": name,
        "label": str(d.get("label") or name.replace("_", " ")),
        "games": list(d.get("games") or []),
        "notes": str(d.get("notes") or ""),
        "path": p,
    }
    for k in _AXES:
        if k in d and not isinstance(d[k], (int, float)):
            raise ValueError("%s: '%s' must be a number" % (p, k))
        spec[k] = _clip(k, d.get(k, 1.0))
    return spec


def all_types():
    return [load(n) for n in list_types()]


def _v3(pose, key):
    v = pose.get(key, (0.0, 0.0, 0.0))
    if isinstance(v, (int, float)):
        return [float(v), 0.0, 0.0]
    t = [float(x) for x in list(v)[:3]]
    while len(t) < 3:
        t.append(0.0)
    return t


def _put3(pose, key, t):
    pose[key] = (float(t[0]), float(t[1]), float(t[2]))


def _warp(t, timing, weight):
    """Map output time -> source time. timing>1 delays the action. weight>1 eases the ends."""
    t = min(1.0, max(0.0, float(t)))
    ts = t ** timing
    if abs(weight - 1.0) < 1e-3:
        return ts
    a = min(1.0, abs(weight - 1.0))
    if weight >= 1.0:
        eased = 0.5 - 0.5 * math.cos(math.pi * ts)          # slow in, slow out
        return ts * (1.0 - a) + eased * a
    # lighter: steeper middle, short ends
    sharp = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * ts))) / math.pi
    return ts * (1.0 - a) + sharp * a


def _shape(pose, spec, t, loop):
    """stance / reach / weight on one pose. t is output time, used for the wind-up."""
    pose = dict(pose)
    stance, reach, weight = spec["stance"], spec["reach"], spec["weight"]
    widen = (stance - 1.0) * 12.0
    for key in ("leg_L", "leg_R"):
        v = _v3(pose, key)
        v[0] *= reach
        v[1] = v[1] * stance + widen
        _put3(pose, key, v)
    guard = (stance - 1.0) * 6.0
    for key in ("arm_L", "arm_R"):
        v = _v3(pose, key)
        v[0] *= reach
        v[1] = v[1] * (0.5 + 0.5 * stance) + guard
        _put3(pose, key, v)
    for key in ("elbow_L", "elbow_R", "knee_L", "knee_R"):
        pose[key] = float(pose.get(key, 0) or 0) / reach
    knee_add = (weight - 1.0) * 22.0
    pose["knee_L"] = float(pose.get("knee_L", 0) or 0) + knee_add
    pose["knee_R"] = float(pose.get("knee_R", 0) or 0) + knee_add
    hips = _v3(pose, "hips")
    hips[0] += (weight - 1.0) * 4.0
    hips[2] *= stance
    _put3(pose, "hips", hips)
    if not loop and abs(weight - 1.0) > 1e-3:
        pull = (weight - 1.0) * 16.0
        if t < 0.22:
            s = math.sin(math.pi * t / 0.22)
            for key in ("arm_L", "arm_R", "leg_L", "leg_R"):
                v = _v3(pose, key)
                v[0] -= pull * s
                _put3(pose, key, v)
        if t > 0.78:
            s = math.sin(math.pi * (t - 0.78) / 0.22)
            over = (weight - 1.0) * 12.0
            for key in ("arm_L", "arm_R"):
                v = _v3(pose, key)
                v[0] += over * s
                _put3(pose, key, v)
    return pose


class TypedMotion(Motion):
    """One source motion performed in a character type. sample() is the only hook."""

    def __init__(self, src, spec):
        Motion.__init__(self, src.name, loop=src.loop,
                        desc=((src.desc or src.name) + " [%s]" % spec["label"]).strip(),
                        category=getattr(src, "category", "General"))
        self.src = src
        self.spec = spec
        self.duration_s = float(getattr(src, "duration_s", 0.0) or 0.0) * spec["timing"]

    def sample(self, t):
        ts = _warp(t, self.spec["timing"], self.spec["weight"])
        pose, mix = self.src.sample(ts)
        return _shape(pose, self.spec, t, self.loop), mix


def wrap(motion, type_name):
    """-> motion whose sample() applies the type. Unknown names raise."""
    if motion is None:
        return None
    spec = type_name if isinstance(type_name, dict) else load(type_name)
    return TypedMotion(motion, spec)


def apply_moves(moves, type_name):
    """Tag each move and scale its playback fps by the type's timing. Idempotent."""
    spec = type_name if isinstance(type_name, dict) else load(type_name)
    scale = spec["timing"]
    for m in moves:
        m.character_type = spec["name"]
        if not getattr(m, "timing_scaled", 0):
            m.fps = min(60, max(1, int(round(float(m.fps) / scale))))
            m.timing_scaled = scale
    return spec


def _arm_forward(pose):
    v = pose.get("arm_R", (0.0, 0.0, 0.0))
    return float(v[0] if isinstance(v, (tuple, list)) else v)


def measure(motion, n=32):
    """Numbers a test (or a report) can compare between two types of the same clip.

    stance_m   mean distance between the ankles, metres
    reach_m    mean distance from the chest to the hands, metres.
               A straight arm is always the same length, so shoulder-to-hand does not
               move; chest-to-hand does, because a longer reach straightens the elbow
               and swings the hand out from the body.
    peak_t     when the right arm's forward swing is greatest, 0..1
    weight     mean knee bend plus how far the arm pulls back in the first quarter
    """
    n = max(2, int(n))
    poses, sts = [], []
    for i in range(n):
        t = i / (n - 1)
        pose, mix = motion.sample(t)
        poses.append(pose)
        sts.append(evaluate(pose, mix))
    sep, reach, knees, arm = [], [], [], []
    for pose, st in zip(poses, sts):
        fl = st.world["foot_L"][:3, 3]
        fr = st.world["foot_R"][:3, 3]
        sep.append(abs(float(fl[0] - fr[0])))
        chest = st.world["chest"][:3, 3]
        hands = [float(np.linalg.norm(st.world["hand_" + s][:3, 3] - chest)) for s in ("L", "R")]
        reach.append(max(hands))
        knees.append(float(pose.get("knee_L", 0) or 0) + float(pose.get("knee_R", 0) or 0))
        arm.append(_arm_forward(pose))
    k = max(2, n // 4)
    pull = arm[0] - min(arm[:k])
    return {
        "stance_m": float(np.mean(sep)),
        "reach_m": float(np.mean(reach)),
        "peak_t": float(int(np.argmax(arm)) / (n - 1)),
        "weight": float(np.mean(knees) + 4.0 * max(0.0, pull)),
        "knee_mean": float(np.mean(knees)),
        "anticipation_deg": float(max(0.0, pull)),
    }
