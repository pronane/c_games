"""Pose-it-yourself moves (v9.4): keyframes you author (by hand, in the Pose Editor page, or exported from mocap)
become a library motion that any engine renders at any angle.

    forge.py build ... --custom-move moves/spin_kick.json [--custom-move another.json]

File format (JSON):
    {"name": "spin_kick", "frames": 8, "fps": 14, "loop": false, "base": "fighter",   # base: fighter | stand | none
     "keys": [{"t": 0.0, "pose": {}},
              {"t": 0.4, "pose": {"leg_R": [80, 6, 0], "knee_R": 100, "chest": [2, 10, 0]}},
              {"t": 0.6, "pose": {"leg_R": [92, 6, 0], "knee_R": 8, "lift": 0.05}},
              {"t": 1.0, "pose": {}}]}
Channels (degrees; the rig's own semantic pose, sforge/rig.py):
    hips / spine / chest / neck = [forward-bend, twist, side-bend]
    arm_L / arm_R = [forward, out, twist]     elbow_L / elbow_R = bend
    leg_L / leg_R = [forward, out, twist]     knee_L / knee_R = bend      ankle_*, wrist_* = bend
    lift = metres off the ground (jumps)      L = the person's left
A key's pose is applied ON TOP of the base pose (fighter = the fighter pack stance, opened to the camera), so a key
only lists what changes.  Between keys the motion eases (smoothstep) and photo3d samples frames by pose change."""
from __future__ import annotations
import json, os
from .motions import P, Motion, LIB, STAND

CHANNELS3 = ("hips", "spine", "chest", "neck", "arm_L", "arm_R", "leg_L", "leg_R")
CHANNELS1 = ("elbow_L", "elbow_R", "knee_L", "knee_R", "ankle_L", "ankle_R", "wrist_L", "wrist_R", "lift")


def _base(name, open_deg=55.0):
    if name == "fighter":
        from .fightpack import stance
        return stance(open_deg)
    if name == "stand":
        return dict(STAND)
    return {}


def _clean(pose):
    out = {}
    for k, v in pose.items():
        if k in CHANNELS3:
            v = list(v) + [0, 0, 0]
            out[k] = (float(v[0]), float(v[1]), float(v[2]))
        elif k in CHANNELS1:
            out[k] = float(v)
        else:
            raise ValueError("unknown pose channel '%s' (use %s)" % (k, ", ".join(CHANNELS3 + CHANNELS1)))
    return out


def load(path, open_deg=55.0):
    """-> (MoveSpec, Motion); the motion is registered in the library as 'custom_<name>'"""
    from .moves import MoveSpec, slug
    d = json.load(open(path))
    name = slug(d.get("name") or os.path.splitext(os.path.basename(path))[0])
    keys = d.get("keys") or []
    if len(keys) < 2:
        raise ValueError("%s: a move needs at least 2 keys" % path)
    base = _base(d.get("base", "fighter"), open_deg)
    ks = sorted(((float(k["t"]), P(base, _clean(k.get("pose", {})))) for k in keys), key=lambda x: x[0])
    mname = "custom_" + name
    mo = Motion(mname, ks, None, bool(d.get("loop", False)), d.get("desc", "custom move (%s)" % os.path.basename(path)),
                "Fighter3D" if d.get("base", "fighter") == "fighter" else "Custom")
    LIB[mname] = mo
    spec = MoveSpec(name=name, label=d.get("label", name.replace("_", " ").title()), category="Custom",
                    frames=int(d.get("frames", 8)), fps=int(d.get("fps", 12)), loop=bool(d.get("loop", False)), motion=mname)
    return spec, mo


def save(path, name, keys, frames=8, fps=12, loop=False, base="fighter"):
    json.dump({"name": name, "frames": frames, "fps": fps, "loop": loop, "base": base,
               "keys": [{"t": t, "pose": p} for t, p in keys]}, open(path, "w"), indent=1)
