"""v11.4 motion library — one clip, on the shared skeleton, for any game.

A move is stored once as semantic pose keys (the same channels as sforge/motions.py
and sforge/mocap.py: hips, arm_L, knee_R, ...). That is the shared skeleton.
From there the clip can be:

  * played on the mannequin / spec / sculpt pipeline (forge.py build --moves punch=lib:punch)
  * retargeted onto any mapped FBX / GLB rig (the existing retargeter, via the mannequin)
  * cleaned: feet planted, weight shift, anticipation, follow-through

Record uses forge.py mocap (MediaPipe fit onto this skeleton). Import reads BVH,
FBX or GLB, retargets onto the mannequin, then projects the posed bones back into
the same channels. Nothing here is tied to the 14-move fighter list. Names are
generic (punch, kick, walk, tackle, shoot, ...). A game profile maps its own
move names onto them.

Shipped starter: motion_library/*.json, generated from this project's own
procedural motions, CC0. No Mixamo, Meshy, or other third-party clips.
User clips are written to library/motions/ (or --library / $SFS_MOTIONS) and
override the starter when the name matches.

Limits (also in `forge.py help motion`):
  * The projection back to semantic channels is a best fit of the mannequin's
    joints, not a copy of finger, twist or face tracks.
  * Foot planting is solved on the canonical thigh / shin / foot. Other bones
    keep the rotation retarget gave them. A GLB is not re-simulated.
  * Record needs the same MediaPipe setup as forge.py mocap.
"""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .library import blank_licence, validate_licence
from .motions import Motion
from .rigrec import FPS, inv_rigid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = os.path.join(HERE, "motion_library")

CC0 = dict(spdx="CC0-1.0", custom_text="", author="Sprite Forge Studio",
           source_url="", redistribution="yes", attribution="",
           notes="Generated from Sprite Forge's own procedural motions. No third-party clips.")

# generic name -> procedural motion it was baked from. Not a game move list.
STARTER = [
    ("idle", "idle"), ("walk", "walk"), ("run", "run"), ("jump", "jump"), ("crouch", "crouch"),
    ("punch", "punch"), ("kick", "kick"), ("block", "block"), ("hit", "hit"),
    ("tackle", "tackle"), ("shoot", "shoot_goal"), ("pass", "hand_pass"), ("save", "gk_save"),
    ("drive", "kart_drive"), ("wave", "wave"), ("cast", "cast"),
]

_SKIP = {"licence.json", "index.json"}


def builtin_dir():
    return BUILTIN


def user_dir():
    env = os.environ.get("SFS_MOTIONS", "").strip()
    if env:
        return env
    from .library import libdir
    return os.path.join(libdir(), "motions")


class MotionLibrary:
    """Read shipped + user folders. Writes go to `write_dir` and never into the starter unless that is the folder you named."""

    def __init__(self, path=None):
        self.write_dir = os.path.abspath(path) if path else user_dir()
        dirs = [self.write_dir]
        b = os.path.abspath(BUILTIN)
        if os.path.abspath(self.write_dir) != b:
            dirs.append(b)
        self.dirs = dirs

    def _files(self):
        """name -> path, user folder winning over the starter."""
        found = {}
        for d in reversed(self.dirs):          # starter first, user overwrites
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if not f.endswith(".json") or f in _SKIP:
                    continue
                found[os.path.splitext(f)[0]] = os.path.join(d, f)
        return found

    def names(self):
        return sorted(self._files())

    def path_of(self, name):
        files = self._files()
        key = _slug(name)
        if key not in files:
            raise KeyError("motion library has no '%s' (have: %s)" % (name, ", ".join(sorted(files)) or "none"))
        return files[key]

    def load(self, name):
        with open(self.path_of(name), encoding="utf-8") as f:
            d = json.load(f)
        d["name"] = d.get("name") or _slug(name)
        d["_path"] = self.path_of(name)
        d["keys"] = [(_num(t), _py_pose(p)) for t, p in d.get("keys") or []]
        if not d["keys"]:
            raise ValueError("%s has no keys" % d["_path"])
        return d

    def save(self, rec):
        os.makedirs(self.write_dir, exist_ok=True)
        name = _slug(rec["name"])
        rec = dict(rec)
        rec["name"] = name
        keys = rec.get("keys") or []
        rec["keys"] = [[_num(t), _json_pose(p)] for t, p in keys]
        rec.pop("_path", None)
        path = os.path.join(self.write_dir, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        rec["_path"] = path
        return path

    def has(self, name):
        return _slug(name) in self._files()


def _slug(name):
    from .moves import slug
    s = slug(str(name).split(":", 1)[-1] if str(name).lower().startswith("lib:") else name)
    return s or "move"


def _num(v):
    return float(v)


def _json_pose(p):
    out = {}
    for k, v in dict(p).items():
        if isinstance(v, tuple):
            out[k] = [(float(x) if not isinstance(x, str) else x) for x in v]
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _py_pose(p):
    out = {}
    for k, v in dict(p).items():
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                out[k] = tuple(v)
            elif len(v) == 1:
                out[k] = float(v[0])
            else:
                out[k] = tuple(float(x) for x in v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _licence(base=None, **over):
    lic = dict(base or blank_licence())
    for k, v in over.items():
        if v is not None:
            lic[k] = v
    return lic


def open_library(path=None):
    return MotionLibrary(path)


def list_moves(path=None):
    return open_library(path).names()


def has_move(name, path=None):
    return open_library(path).has(name)


def load_move(name, path=None):
    return open_library(path).load(name)


def as_motion(name, path=None):
    """Library clip -> motions.Motion, or None if it is not in the library."""
    lib = open_library(path)
    if not lib.has(name):
        return None
    rec = lib.load(name)
    m = Motion(rec["name"], keys=rec["keys"], loop=bool(rec.get("loop")),
               desc=rec.get("desc") or rec.get("source") or "motion library",
               category=rec.get("category") or "Library")
    if rec.get("duration"):
        m.duration_s = float(rec["duration"])
    m.library = rec
    return m


def signature(path=None):
    """Cache key for whatever folders this library reads."""
    from .cache import file_sig
    lib = open_library(path)
    return "|".join(file_sig(d) if os.path.isdir(d) else "missing" for d in lib.dirs)


# ---------------------------------------------------------------- semantic projection
def _euler_xyz(R):
    """Inverse of mathutil.euler (R = Rx @ Ry @ Rz), degrees."""
    sy = float(np.clip(R[0, 2], -1.0, 1.0))
    y = math.degrees(math.asin(sy))
    if abs(sy) > 0.999:
        x = math.degrees(math.atan2(float(R[1, 0]), float(R[1, 1])))
        z = 0.0
    else:
        x = math.degrees(math.atan2(float(-R[1, 2]), float(R[2, 2])))
        z = math.degrees(math.atan2(float(-R[0, 1]), float(R[0, 0])))
    return x, y, z


def _local(W, joint, parent):
    if parent is None or parent not in W:
        return W[joint]
    return inv_rigid(W[parent]) @ W[joint]


def pose_from_world(W):
    """Mannequin world matrices (name -> 4x4) -> one semantic pose.

    This is the projection used when an imported clip has been retargeted onto
    the mannequin. Finger / twist / face bones are not in that skeleton, so they
    are dropped here.
    """
    from .rig import PARENT
    pose = {"flat": 0.0, "ground": False}

    def eul(j):
        return _euler_xyz(_local(W, j, PARENT.get(j))[:3, :3])

    if "hips" in W:
        pose["hips"] = eul("hips")
    for j in ("spine", "chest"):
        if j in W:
            f, t, s = eul(j)
            pose[j] = (f, t, -s)
    if "head" in W:
        f, t, s = eul("head")
        pose["neck"] = (f, t, -s)
    for side, sg in (("L", 1.0), ("R", -1.0)):
        ua = "upperarm_" + side
        if ua in W:
            x, y, z = eul(ua)
            pose["arm_" + side] = (-x, sg * z, sg * y)
        if "forearm_" + side in W:
            pose["elbow_" + side] = -eul("forearm_" + side)[0]
        if "hand_" + side in W:
            pose["wrist_" + side] = -eul("hand_" + side)[0]
        if "thigh_" + side in W:
            x, y, z = eul("thigh_" + side)
            pose["leg_" + side] = (-x, sg * z, sg * y)
        if "shin_" + side in W:
            pose["knee_" + side] = eul("shin_" + side)[0]
        if "foot_" + side in W:
            pose["ankle_" + side] = eul("foot_" + side)[0]
    if "root" in W:
        t = W["root"][:3, 3]
        pose["pos"] = (float(t[0]), float(t[2]))
        pose["lift"] = float(t[1])
    return pose


def worlds_dict(rig, row):
    return {rig.bones[i]: row[i] for i in range(rig.nb)}


def clip_to_keys(rig, clip):
    Wf = rig.clip_worlds(clip)
    n = len(Wf)
    keys = []
    for i in range(n):
        t = 0.0 if n == 1 else i / (n - 1)
        keys.append((t, pose_from_world(worlds_dict(rig, Wf[i]))))
    return keys


def projection_error(rig, clip, keys):
    """Mean / max metres between the clip's joints and the projected poses, on bones both have."""
    from .rig import evaluate
    Wf = rig.clip_worlds(clip)
    err = []
    for i, (_, pose) in enumerate(keys):
        st = evaluate(pose)
        for b in rig.bones:
            if b not in st.world or b == "ball":
                continue
            err.append(float(np.linalg.norm(Wf[i, rig.index(b), :3, 3] - st.world[b][:3, 3])))
    if not err:
        return 0.0, 0.0
    return float(np.mean(err)), float(np.max(err))


def bake_on_mannequin(motion, frames=None, duration=None):
    """Semantic motion -> mannequin Rig with that one clip. The rig is the retarget source."""
    from . import bonemap as BM
    from . import rigrec as RR
    man = RR.from_mannequin(clips=[])
    c = RR.motion_clip(man, motion.name, frames=frames, loop=motion.loop, duration=duration, motion=motion)
    if c is None:
        raise ValueError("could not bake '%s'" % motion.name)
    man.clips[c.name] = c
    return man, BM.detect(man), c


# ---------------------------------------------------------------- clean
def _fwd(pose, key):
    v = pose.get(key, (0.0, 0.0, 0.0))
    if isinstance(v, (int, float)):
        return float(v)
    return float(v[0])


def _set_fwd(pose, key, value):
    v = pose.get(key, (0.0, 0.0, 0.0))
    if not isinstance(v, (tuple, list)):
        pose[key] = (float(value), 0.0, 0.0)
        return
    t = [float(x) for x in list(v)[:3]]
    while len(t) < 3:
        t.append(0.0)
    t[0] = float(value)
    pose[key] = tuple(t)


def _dominant(keys):
    best, span = "arm_R", -1.0
    for k in ("arm_R", "arm_L", "leg_R", "leg_L"):
        vals = [_fwd(p, k) for _, p in keys]
        s = max(vals) - min(vals) if vals else 0.0
        if s > span:
            best, span = k, s
    return best, span


def _anticipation(keys):
    ch, span = _dominant(keys)
    if span < 12.0:
        return keys, 0.0
    vals = [_fwd(p, ch) for _, p in keys]
    peak = max(range(len(vals)), key=lambda i: abs(vals[i] - vals[0]))
    direction = 1.0 if vals[peak] >= vals[0] else -1.0
    pull = min(22.0, 0.30 * span)
    out = []
    for t, p in keys:
        p = dict(p)
        if t < 0.22:
            w = 1.0 - (t / 0.22)
            _set_fwd(p, ch, _fwd(p, ch) - direction * pull * w)
        out.append((t, p))
    return out, pull


def _follow(keys):
    ch, span = _dominant(keys)
    if span < 12.0:
        return keys, 0.0
    vals = [_fwd(p, ch) for _, p in keys]
    peak_i = int(np.argmax(vals))
    peak_t = keys[peak_i][0]
    over = min(16.0, 0.22 * span)
    out = []
    for t, p in keys:
        p = dict(p)
        if peak_t < t <= min(1.0, peak_t + 0.30):
            u = (t - peak_t) / 0.30
            _set_fwd(p, ch, _fwd(p, ch) + over * math.sin(math.pi * u))
        out.append((t, p))
    return out, over


def _weight_shift(keys, loop):
    out, amps = [], []
    for t, p in keys:
        p = dict(p)
        fL, fR = _fwd(p, "leg_L"), _fwd(p, "leg_R")
        shift = 0.04 * math.tanh((fR - fL) / 22.0)
        if abs(fR - fL) < 3.0 and loop:
            shift = 0.025 * math.sin(2.0 * math.pi * t)
        pos = p.get("pos", (0.0, 0.0))
        if not isinstance(pos, (tuple, list)):
            pos = (float(pos), 0.0)
        px = float(pos[0]) + shift
        pz = float(pos[1]) if len(pos) > 1 else 0.0
        p["pos"] = (px, pz)
        sp = p.get("spine", (0.0, 0.0, 0.0))
        if not isinstance(sp, (tuple, list)):
            sp = (float(sp), 0.0, 0.0)
        sp = [float(x) for x in list(sp)[:3]]
        while len(sp) < 3:
            sp.append(0.0)
        sp[2] -= shift * 90.0
        p["spine"] = tuple(sp)
        amps.append(abs(shift))
        out.append((t, p))
    return out, float(max(amps) if amps else 0.0)


def _match_ankle(pose, side, ankle, knee):
    """Fit this leg's semantic channels so the ankle (and knee) land on the planted targets."""
    from scipy.optimize import least_squares
    from .rig import evaluate
    leg = pose.get("leg_" + side, (0.0, 0.0, 0.0))
    if not isinstance(leg, (tuple, list)):
        leg = (float(leg), 0.0, 0.0)
    x0 = np.array([float(leg[0]), float(leg[1] if len(leg) > 1 else 0),
                   float(leg[2] if len(leg) > 2 else 0), float(pose.get("knee_" + side, 0) or 0)], float)

    def res(x):
        p = dict(pose)
        p["leg_" + side] = (float(x[0]), float(x[1]), float(x[2]))
        p["knee_" + side] = float(x[3])
        p["flat"] = 0.0
        st = evaluate(p)
        return np.r_[st.world["foot_" + side][:3, 3] - ankle,
                     0.35 * (st.world["shin_" + side][:3, 3] - knee)]

    sol = least_squares(res, x0, bounds=([-90, -50, -70, 0], [140, 80, 70, 165]), max_nfev=50)
    pose = dict(pose)
    pose["leg_" + side] = (float(sol.x[0]), float(sol.x[1]), float(sol.x[2]))
    pose["knee_" + side] = float(sol.x[3])
    pose["flat"] = 0.0
    return pose


def _plant_keys(keys, loop):
    """Foot lock on the shared skeleton, written back into the pose channels.

    footlock.py solves the mannequin's thigh and shin. The result is fitted back
    into leg / knee channels, so the cleaned clip stays in the library (it is not
    only a render-time fix). GLB twist bones and fingers are not part of this pose.
    """
    from . import footlock
    from .rig import evaluate
    poses = [dict(p) for _, p in keys]
    ts = [t for t, _ in keys]
    states = [evaluate(p) for p in poses]
    before = footlock.measure(states, loop)
    locked, info = footlock.lock(states, loop, fps=12)
    fitted = 0
    for i, st in enumerate(locked):
        for side, foot, shin in (("L", "foot_L", "shin_L"), ("R", "foot_R", "shin_R")):
            tgt = st.world[foot][:3, 3]
            cur = states[i].world[foot][:3, 3]
            if float(np.linalg.norm(tgt - cur)) < 0.004:
                continue
            poses[i] = _match_ankle(poses[i], side, tgt, st.world[shin][:3, 3])
            fitted += 1
    after_states = [evaluate(p) for p in poses]
    after = footlock.measure(after_states, loop)
    return list(zip(ts, poses)), {
        "before_cm": before, "after_cm": after, "fitted_legs": fitted,
        "segments": info.get("segments", 0), "frames": info.get("frames", 0),
    }


def clean_keys(keys, loop=False, feet=True, weight=True, anticipation=True, follow=True):
    """-> (keys, report). Keys are (t, pose) with t in 0..1."""
    report = {"feet": bool(feet), "weight": bool(weight), "anticipation": bool(anticipation), "follow": bool(follow)}
    keys = [(float(t), dict(p)) for t, p in keys]
    if anticipation and not loop:
        keys, pull = _anticipation(keys)
        report["anticipation_deg"] = round(pull, 2)
    if follow and not loop:
        keys, over = _follow(keys)
        report["followthrough_deg"] = round(over, 2)
    if weight:
        keys, amp = _weight_shift(keys, loop)
        report["weight_shift_m"] = round(amp, 4)
    if feet:
        keys, fre = _plant_keys(keys, loop)
        report["foot"] = fre
    report["glb_resolved"] = False
    report["note"] = ("Clean-up is stored on the shared skeleton (pose channels). "
                      "Foot planting refits thigh and knee to the mannequin foot lock. "
                      "On a retargeted GLB / FBX the same plant runs on the canonical thigh, shin and foot; "
                      "fingers, twist bones and extra spine bones are not re-solved.")
    return keys, report


def clean_move(name, path=None, feet=True, weight=True, anticipation=True, follow=True):
    lib = open_library(path)
    rec = lib.load(name)
    keys, report = clean_keys(rec["keys"], bool(rec.get("loop")), feet, weight, anticipation, follow)
    rec = dict(rec)
    rec["keys"] = keys
    rec["cleanup"] = report
    rec["source"] = (rec.get("source") or name) + " + clean"
    path_out = lib.save(rec)
    return rec, report, path_out


# ---------------------------------------------------------------- retarget + plant on a target rig
class _St:
    def __init__(self, world, root_t):
        self.world = world
        self.root_t = root_t


def plant_on_rig(rig, rec, clip):
    """Plant canonical feet on a retargeted clip. Children keep their local rotation.

    Returns (clip, report). If the rig has no mapped thigh/shin/foot, the clip is unchanged.
    This is not a full re-solve of a GLB: only those three bones a side are aimed, and
    everything else follows its parent.
    """
    from . import bonemap as BM
    from . import footlock
    im = BM.index_map(rig, rec)
    need = ["thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
    if any(k not in im for k in need):
        return clip, {"applied": False, "reason": "rig is missing a canonical leg bone (%s)" % ", ".join(k for k in need if k not in im)}
    Wf = rig.clip_worlds(clip)
    explicit = [im[k] for k in need]
    states = []
    for f in range(len(Wf)):
        world = {k: Wf[f, im[k]].copy() for k in need}
        hip = Wf[f, im["hips"], :3, 3] if "hips" in im else np.zeros(3)
        states.append(_St(world, np.array([hip[0], 0.0, hip[2]])))
    before = footlock.measure(states, clip.loop)
    locked, info = footlock.lock(states, clip.loop, clip.fps)
    for f, st in enumerate(locked):
        old = Wf[f].copy()
        for k in need:
            Wf[f, im[k]] = st.world[k]
        for i in rig.order():
            if i in explicit:
                continue
            p = int(rig.parent[i])
            if p < 0:
                continue
            local = inv_rigid(old[p]) @ old[i]
            Wf[f, i] = Wf[f, p] @ local
    out = rig.clip_from_worlds(clip.name, Wf, clip.fps, clip.loop, (clip.source or "") + " + foot plant")
    # measure on the written clip
    states2 = []
    W2 = rig.clip_worlds(out)
    for f in range(len(W2)):
        world = {k: W2[f, im[k]].copy() for k in need}
        hip = W2[f, im["hips"], :3, 3] if "hips" in im else np.zeros(3)
        states2.append(_St(world, np.array([hip[0], 0.0, hip[2]])))
    after = footlock.measure(states2, clip.loop)
    return out, {"applied": True, "before_cm": before, "after_cm": after,
                 "segments": info.get("segments", 0),
                 "note": "Canonical thigh/shin/foot were planted. Fingers, twist bones and the rest of the clip were not re-solved."}


def retarget_motion(name, target, path=None, character_type=None, root_motion="keep", plant=True, out_name=None):
    """Library move -> clip on `target` rig (a Rig, or a library name / file path).

    -> (target_rig, clip, report)
    """
    from . import bonemap as BM
    from . import importers
    from . import retarget as RT
    motion = as_motion(name, path)
    if motion is None:
        raise KeyError("motion library has no '%s'" % name)
    if character_type:
        from . import chartypes
        motion = chartypes.wrap(motion, character_type)
    if isinstance(target, str):
        if os.path.isfile(target):
            tgt, trec, _ = importers.load_file(target)
        else:
            from . import library as L
            lib = L.Library()
            tgt, trec = lib.load_rig(target), lib.bonemap(target)
    else:
        tgt = target
        trec = BM.detect(tgt)
    dur = getattr(motion, "duration_s", None) or None
    man, mrec, src = bake_on_mannequin(motion, duration=dur)
    if character_type:
        from . import chartypes
        spec = chartypes.load(character_type)
        src.fps = max(1.0, src.fps / spec["timing"])
    clip_name = out_name or name
    cl, rep = RT.retarget(man, mrec, src, tgt, trec, root_motion=root_motion, name=clip_name)
    rep = dict(rep)
    rep["source"] = "motion library:%s" % name
    if character_type:
        rep["character_type"] = character_type if isinstance(character_type, str) else character_type.get("name")
    if plant:
        cl, plant_rep = plant_on_rig(tgt, trec, cl)
        rep["plant"] = plant_rep
    else:
        rep["plant"] = {"applied": False, "reason": "plant disabled"}
    tgt.clips[cl.name] = cl
    return tgt, cl, rep


# ---------------------------------------------------------------- record / import
def record_keys(keys_path, name=None, path=None, loop=None, licence=None, category="Recorded"):
    """Store a mocap keys JSON (the file forge.py mocap writes) as a library move.

    The file is the output of the existing tracker, not a second tracker. Tests use
    synthetic keys in that same format — no video and no person.
    """
    from . import mocap
    nm, keys, file_loop = mocap.load_keys(keys_path)
    name = _slug(name or nm.replace("mocap_", "", 1))
    lp = file_loop if loop is None else bool(loop)
    lic = _licence(licence)
    rec = {
        "name": name, "category": category, "desc": "recorded onto the shared skeleton via mocap keys",
        "loop": lp, "source": "mocap:" + os.path.basename(keys_path), "origin": "record",
        "licence": lic, "keys": keys, "duration": 1.0 if lp else 0.8,
    }
    lib = open_library(path)
    out = lib.save(rec)
    return rec, out, validate_licence(lic)


def record_video(clip_arg, path=None, model="full", facing="auto", licence=None, name=None, loop=None):
    """Video -> existing mocap tracker -> library. Raises RuntimeError if MediaPipe is missing."""
    import tempfile
    from . import mocap
    from .moves import slug
    from .video import parse_clip, LOCO
    from .motions import find_motion
    mv, n, vpath, start, end, _ = parse_clip(clip_arg)
    key = slug(name or mv)
    lib_m = find_motion(slug(mv))
    if loop is None:
        loop = bool(lib_m and lib_m.loop) or any(k in key for k in LOCO)
    fd, tmp = tempfile.mkstemp(prefix="sfs_mocap_", suffix=".json")
    os.close(fd)
    try:
        d = mocap.track(vpath, tmp, model, start, end)
        keys, rep, _ = mocap.analyse(d, key, loop, n or 8, facing=facing)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    # write a keys file in the mocap format, then the same record path
    fd, kj = tempfile.mkstemp(prefix="sfs_keys_", suffix=".json")
    os.close(fd)
    try:
        mocap.save_keys(kj, key, keys, loop, rep)
        rec, out, probs = record_keys(kj, name=key, path=path, loop=loop, licence=licence, category="Recorded")
    finally:
        try:
            os.remove(kj)
        except OSError:
            pass
    rec["mocap"] = {"mean_bone_err_deg": rep.get("mean_bone_err_deg"), "facing": rep.get("facing"), "frames": rep.get("frames")}
    return rec, out, probs


def _scale_bind(rig, scale):
    if abs(scale - 1.0) < 1e-6:
        return
    rig.bind = rig.bind.copy()
    rig.bind[:, :3, 3] *= scale
    for c in rig.clips.values():
        c.T = c.T * scale


def load_bvh(path):
    """BVH -> Rig + bone map. Offsets over ~10 units are treated as centimetres.

    Rotations are applied in the channel order written in the file (R = R @ axis).
    Y-up files match the shared skeleton. Z-up files still import; the retarget
    step only sees the mapped bones, so a badly oriented file looks wrong — check
    the preview. This is a small reader for free-licence clips, not a full BVH suite.
    """
    from . import bonemap as BM
    from .rigrec import Clip, Rig, m4, quat_from_mats
    from .mathutil import rx, ry, rz
    text = open(path, encoding="utf-8", errors="replace").read()
    toks = text.replace(",", " ").replace("{", " { ").replace("}", " } ").split()
    if not toks or toks[0] != "HIERARCHY":
        raise ValueError("%s does not look like a BVH file (no HIERARCHY)" % os.path.basename(path))
    i = 1
    joints = []

    def take(s):
        nonlocal i
        if i >= len(toks) or toks[i] != s:
            raise ValueError("BVH: expected %s at token %d" % (s, i))
        i += 1

    def parse_joint(parent):
        nonlocal i
        kind = toks[i]; i += 1
        if kind == "End":
            take("Site"); take("{"); take("OFFSET")
            i += 3
            take("}")
            return
        if kind not in ("ROOT", "JOINT"):
            raise ValueError("BVH: unexpected %s" % kind)
        name = toks[i]; i += 1
        take("{"); take("OFFSET")
        off = np.array([float(toks[i]), float(toks[i + 1]), float(toks[i + 2])], float); i += 3
        channels = []
        if i < len(toks) and toks[i] == "CHANNELS":
            i += 1
            n = int(toks[i]); i += 1
            channels = toks[i:i + n]; i += n
        node = {"name": name, "parent": parent, "offset": off, "channels": channels}
        joints.append(node)
        me = len(joints) - 1
        while toks[i] != "}":
            parse_joint(me)
        i += 1

    parse_joint(-1)
    take("MOTION"); take("Frames:")
    nframes = int(toks[i]); i += 1
    if toks[i] != "Frame" or toks[i + 1] != "Time:":
        raise ValueError("BVH: expected Frame Time:")
    i += 2
    dt = float(toks[i]); i += 1
    nch = sum(len(j["channels"]) for j in joints)
    data = np.array([float(x) for x in toks[i:]], float)
    if data.size < nframes * nch:
        raise ValueError("BVH: motion block is short (%d numbers, need %d)" % (data.size, nframes * nch))
    data = data[:nframes * nch].reshape(nframes, nch)
    rig = Rig(os.path.splitext(os.path.basename(path))[0])
    rig.bones = [j["name"] for j in joints]
    rig.parent = np.array([j["parent"] for j in joints], int)
    # bind: offsets, identity rotation
    bind = np.zeros((len(joints), 4, 4))
    for idx, j in enumerate(joints):
        local = m4(None, j["offset"])
        bind[idx] = local if j["parent"] < 0 else bind[j["parent"]] @ local
    rig.bind = bind
    R = np.zeros((nframes, len(joints), 4))
    T = np.zeros((nframes, len(joints), 3))
    ax = {"Xrotation": rx, "Yrotation": ry, "Zrotation": rz}

    def frame_local(j, vals):
        trans = np.zeros(3)
        rot = np.eye(3)
        vi = 0
        has_pos = False
        for ch in j["channels"]:
            v = float(vals[vi]); vi += 1
            if ch == "Xposition":
                trans[0] = v; has_pos = True
            elif ch == "Yposition":
                trans[1] = v; has_pos = True
            elif ch == "Zposition":
                trans[2] = v; has_pos = True
            elif ch in ax:
                rot = rot @ ax[ch](v)
        if j["parent"] < 0 and has_pos:
            pos = trans
        elif has_pos:
            pos = j["offset"] + trans
        else:
            pos = j["offset"]
        return rot, pos

    for f in range(nframes):
        cursor = 0
        for idx, j in enumerate(joints):
            n = len(j["channels"])
            rot, pos = frame_local(j, data[f, cursor:cursor + n])
            cursor += n
            R[f, idx] = quat_from_mats(rot[None, ...])[0]
            T[f, idx] = pos
    fps = 1.0 / dt if dt > 1e-6 else FPS
    clip = Clip(rig.name, R, T, fps, None, "bvh:%s" % os.path.basename(path))
    rig.clips[clip.name] = clip
    # centimetres (a person-sized figure exported as 170) -> metres. Leave 0.4..8 alone.
    ys = bind[:, 1, 3]
    height = float(ys.max() - ys.min()) if len(ys) else 0.0
    if height > 20.0:
        _scale_bind(rig, 0.01)
    elif height > 8.0:
        _scale_bind(rig, 1.7 / height)
    rec = BM.detect(rig)
    return rig, rec


def import_file(path, name=None, clip=None, library=None, licence=None, loop=None, category=None):
    """BVH / FBX / GLB / glTF / mocap-json -> one library move on the shared skeleton.

    FBX and GLB go through the existing importer and retargeter. The clip is then
    projected onto the mannequin channels. That projection does not keep fingers,
    twist bones or facial tracks.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return record_keys(path, name=name, path=library, loop=loop, licence=licence,
                           category=category or "Imported")
    if ext == ".bvh":
        src, srec = load_bvh(path)
        clip_name = clip or next(iter(src.clips))
        reader = "bvh"
    elif ext in (".fbx", ".glb", ".gltf"):
        from . import importers
        src, srec, _ = importers.load_file(path)
        if not src.clips:
            raise ValueError("%s has no animation clips" % os.path.basename(path))
        if clip and clip not in src.clips:
            raise KeyError("no clip %r (has: %s)" % (clip, ", ".join(src.clips)))
        clip_name = clip or next(iter(src.clips))
        reader = ext[1:]
    else:
        raise ValueError("motion import supports .bvh .fbx .glb .gltf and mocap .json (got %s)" % ext)
    from . import bonemap as BM
    from . import retarget as RT
    from . import rigrec as RR
    man = RR.from_mannequin(clips=[])
    mrec = BM.detect(man)
    cl, rep = RT.retarget(src, srec, src.clips[clip_name], man, mrec, name=clip_name)
    keys = clip_to_keys(man, cl)
    mean_e, max_e = projection_error(man, cl, keys)
    nm = _slug(name or clip_name)
    lic = _licence(licence)
    rec = {
        "name": nm,
        "category": category or "Imported",
        "desc": "imported %s clip '%s' onto the shared skeleton" % (reader, clip_name),
        "loop": bool(src.clips[clip_name].loop) if loop is None else bool(loop),
        "source": "%s:%s:%s" % (reader, os.path.basename(path), clip_name),
        "origin": "import",
        "licence": lic,
        "duration": round(float(cl.duration), 4),
        "keys": keys,
        "import": {
            "reader": reader,
            "retarget_mean_dir_err_deg": rep.get("mean_dir_err_deg"),
            "projection_mean_m": round(mean_e, 4),
            "projection_max_m": round(max_e, 4),
            "common_bones": rep.get("common_bones"),
            "note": "Projected onto the mannequin's semantic joints. Fingers, twist bones and facial tracks are not kept.",
        },
    }
    out = open_library(library).save(rec)
    return rec, out, validate_licence(lic)


def seed_starter(folder=None, n=9):
    """Write the CC0 starter set from the built-in procedural motions. Overwrites that folder's move files."""
    from .motions import find_motion
    folder = folder or BUILTIN
    os.makedirs(folder, exist_ok=True)
    lib = MotionLibrary(folder)
    written = []
    for generic, src_name in STARTER:
        src = find_motion(src_name)
        if src is None:
            raise RuntimeError("starter source motion '%s' is missing" % src_name)
        if src.keys:
            keys = [(float(t), dict(p)) for t, p in src.keys]
        else:
            keys = []
            for i in range(n):
                t = i / (n - 1)
                pose, _ = src.sample(t)
                keys.append((t, dict(pose)))
        rec = {
            "name": generic,
            "category": src.category,
            "desc": src.desc or generic,
            "loop": bool(src.loop),
            "source": "procedural:" + src_name,
            "origin": "builtin",
            "from_motion": src_name,
            "licence": dict(CC0),
            "duration": 1.0 if src.loop else 0.8,
            "keys": keys,
            "cleanup": None,
        }
        lib.save(rec)
        written.append(generic)
    pack = dict(CC0)
    pack.update({
        "name": "sprite_forge_motion_starter",
        "moves": written,
        "notes": "CC0. Baked from Sprite Forge procedural motions (sforge/motions.py) by motionlib.seed_starter. "
                 "No Mixamo, Meshy, or other third-party motion. Safe to ship and to put in a pack.",
    })
    with open(os.path.join(folder, "licence.json"), "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=1)
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "sprite_forge_motion_starter", "moves": written, "licence": "licence.json"}, f, indent=1)
    return written
