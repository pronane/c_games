"""Pitch-side people for field sports: substitutes, managers, ball kids, photographers (v11.39, fed back from Arena FC).

Arena FC played in front of a full crowd with empty dugouts, no managers in the technical areas and nobody
round the boards.  This pack gives a game what it needs to fill the touchline with the same skinned squad
figures it already draws:

  clips   sub_sit, sub_lean, sub_cheer, manager_watch, manager_shout, staff_stand, ballkid_ready,
          photographer_kneel, photographer_stand - authored in Sprite Forge's semantic pose channels, looping
          (except `sub_cheer`, the bench jumping up for a goal), registered in the motion library
  looks   `LOOKS`: what each role wears - colours as rules on the team's kit (a sub's bib over his long
          sleeves, a manager's dark coat and trousers, a ball kid's tracksuit, a photographer's numbered
          bib) - for `tailor`'s kit plus `keeper_garments` sleeves and `staff_garments` trousers
  props   `props_glb(path)`: a photographer's camera with a long lens (grip at the origin, +Y up, lens along
          +Z), ready to hang off the right hand
  places  `placements(stadium_json, half_length, half_width)`: where everyone goes round a `sforge.stadium`
          ground - subs on the dugout seats, the managers and an assistant in their technical areas, ball
          kids behind the boards, photographers kneeling along the goal lines - with facing and clip

    from sforge import pitchside as PS
    PS.register()                      # idempotent; done on import
    PS.qa_all()                        # {} when every clip passes
    spots = PS.placements(json.load(open("stadium_bowl.json")), 52.5, 34.0)
"""
from __future__ import annotations

import math

import numpy as np

from .motions import LIB, STAND, K, M, P

# ------------------------------------------------------------------ poses
SIT = dict(hips=(-4, 0, 0), spine=(-3, 0, 0), chest=(2, 0, 0), neck=(4, 0, 0),
           leg_L=(84, 9, 0), leg_R=(82, 11, 0), knee_L=86, knee_R=82, ankle_L=-4, ankle_R=-2,
           arm_L=(22, 12, 0), arm_R=(24, 14, 0), elbow_L=34, elbow_R=32)                 # hands on the thighs
# leaning in, the pelvis tips forward: the hips flex less so the thighs stay flat on the seat
LEAN = dict(SIT, hips=(18, 0, 0), spine=(14, 0, 0), chest=(10, 0, 0), neck=(-22, 0, 0),
            leg_L=(66, 9, 0), leg_R=(64, 11, 0),
            arm_L=(64, 4, 0), arm_R=(62, 6, 0), elbow_L=96, elbow_R=98)                   # elbows on the knees
FOLDED = dict(STAND, arm_L=(38, -26, 0), arm_R=(36, -28, 0), elbow_L=118, elbow_R=122, chest=(-2, 0, 0))
CAMERA = dict(arm_L=(72, -22, 0), arm_R=(66, -6, 0), elbow_L=124, elbow_R=128, neck=(-4, 0, 0))
KNEEL = dict(hips=(10, 0, 0), spine=(8, 0, 0), chest=(2, 0, 0),
             leg_L=(84, 10, 0), knee_L=92, ankle_L=-6,                                   # left foot planted
             leg_R=(-6, 8, 0), knee_R=112, ankle_R=40)                                   # right knee down
BEHIND = dict(arm_L=(-18, 12, 0), arm_R=(-18, 12, 0), elbow_L=64, elbow_R=64)           # hands behind the back
UP2 = dict(arm_L=(168, 14, 0), arm_R=(168, 14, 0), elbow_L=10, elbow_R=10)

CLIPS = {
    "sub_sit": dict(desc="substitute sitting on the bench, watching the play go by", dur=6.0, loop=True, keys=K(
        (0.0, P(SIT)),
        (0.25, P(SIT, neck=(4, 14, 0), chest=(2, 4, 0))),
        (0.5, P(SIT, neck=(2, 2, 0), arm_R=(30, 14, 0), elbow_R=44)),
        (0.75, P(SIT, neck=(4, -12, 0), chest=(2, -3, 0))),
        (1.0, P(SIT)))),
    "sub_lean": dict(desc="substitute leaning forward, elbows on the knees", dur=5.0, loop=True, keys=K(
        (0.0, P(LEAN)),
        (0.3, P(LEAN, neck=(-20, 10, 0))),
        (0.6, P(LEAN, neck=(-24, -8, 0), elbow_L=104)),
        (1.0, P(LEAN)))),
    "sub_cheer": dict(desc="the bench jumps up for a goal: up off the seat, arms high, and back down", dur=3.0,
                      loop=False, keys=K(
        (0.0, P(SIT)),
        (0.22, P(STAND, UP2, chest=(-6, 0, 0), neck=(-10, 0, 0))),
        (0.38, P(STAND, UP2, chest=(-8, 0, 0), neck=(-12, 0, 0), lift=.12)),
        (0.55, P(STAND, UP2, chest=(-6, 0, 0))),
        (0.72, P(STAND, arm_L=(60, 30, 0), arm_R=(60, 30, 0), elbow_L=70, elbow_R=70)),
        (1.0, P(SIT)))),
    "manager_watch": dict(desc="manager in the technical area, arms folded, weight shifting", dur=7.0, loop=True,
                          keys=K(
        (0.0, P(FOLDED)),
        (0.3, P(FOLDED, hips=(0, 0, 3), leg_L=(5, 6, 0), neck=(2, 10, 0))),
        (0.6, P(FOLDED, hips=(0, 0, -3), leg_R=(4, 6, 0), neck=(2, -10, 0))),
        (1.0, P(FOLDED)))),
    "manager_shout": dict(desc="manager calling instructions: arm sweeping out to the play, a step forward",
                          dur=3.2, loop=True, keys=K(
        (0.0, P(STAND)),
        (0.2, P(STAND, arm_R=(84, 18, 0), elbow_R=14, chest=(6, 6, 0), neck=(-4, 6, 0), leg_R=(14, 4, 0), knee_R=10)),
        (0.4, P(STAND, arm_R=(72, 40, 0), elbow_R=20, arm_L=(30, 18, 0), elbow_L=70, chest=(6, -4, 0))),
        (0.6, P(STAND, arm_R=(88, 10, 0), elbow_R=10, chest=(8, 4, 0), neck=(-6, 4, 0))),
        (0.8, P(STAND, arm_R=(30, 14, 0), elbow_R=40)),
        (1.0, P(STAND)))),
    "staff_stand": dict(desc="coach / fourth-official-side staff standing, hands on the hips", dur=6.0, loop=True,
                        keys=K(
        (0.0, P(STAND, arm_L=(10, 34, 0), arm_R=(10, 34, 0), elbow_L=96, elbow_R=96)),
        (0.5, P(STAND, arm_L=(10, 34, 0), arm_R=(10, 34, 0), elbow_L=96, elbow_R=96, neck=(2, 12, 0))),
        (1.0, P(STAND, arm_L=(10, 34, 0), arm_R=(10, 34, 0), elbow_L=96, elbow_R=96)))),
    "ballkid_ready": dict(desc="ball kid behind the boards, hands behind the back, rocking on the feet",
                          dur=5.0, loop=True, keys=K(
        (0.0, P(STAND, BEHIND)),
        (0.35, P(STAND, BEHIND, hips=(2, 0, 2), neck=(0, 12, 0))),
        (0.7, P(STAND, BEHIND, hips=(2, 0, -2), neck=(0, -10, 0))),
        (1.0, P(STAND, BEHIND)))),
    "photographer_kneel": dict(desc="photographer kneeling at the goal line, camera to the eye, tracking play",
                               dur=6.0, loop=True, keys=K(
        (0.0, P(KNEEL, CAMERA)),
        (0.3, P(KNEEL, CAMERA, chest=(2, 10, 0), hips=(10, 4, 0))),
        (0.55, P(KNEEL, CAMERA, chest=(4, -2, 0), arm_R=(40, 8, 0), elbow_R=70)),           # checks the screen
        (0.8, P(KNEEL, CAMERA, chest=(2, -10, 0), hips=(10, -4, 0))),
        (1.0, P(KNEEL, CAMERA)))),
    "photographer_stand": dict(desc="photographer standing, camera to the eye", dur=5.0, loop=True, keys=K(
        (0.0, P(STAND, CAMERA)),
        (0.5, P(STAND, CAMERA, chest=(0, 12, 0), hips=(0, 6, 0))),
        (1.0, P(STAND, CAMERA)))),
}

EVENTS = {"sub_cheer": {"peak": .38}}
for _n in CLIPS:
    EVENTS.setdefault(_n, {})
    EVENTS[_n].update({"ball_contact": -1.0, "footsteps": [], "hit_start": -1.0, "hit_end": -1.0})

SEATED = {"sub_sit", "sub_lean"}
KNEELING = {"photographer_kneel"}


def register() -> None:
    """Add every pitch-side clip to `sforge.motions.LIB` (idempotent)."""
    for name, spec in CLIPS.items():
        if name in LIB:
            continue
        M(name, "Pitchside", spec["desc"], keys=spec["keys"], loop=spec["loop"])
        LIB[name].duration_s = spec["dur"]


def qa(name: str, samples: int = 24) -> list[str]:
    """[] when the clip reads: loops end where they start, the seated clips keep the hips and knees bent like
    a seat (the bench in a dugout is about knee height), the kneeling clip keeps one knee on the ground, the
    camera clips keep both hands up at the face, and the cheer gets both arms high."""
    register()
    m = LIB.get(name)
    if m is None:
        return ["unknown clip " + name]
    errs = []
    poses = [m.sample(i / samples)[0] for i in range(samples + 1)]

    def ch(p, k, i=0):
        v = p.get(k, 0)
        return float(v[i] if isinstance(v, (tuple, list)) else v)
    if CLIPS[name]["loop"]:
        a, b = poses[0], poses[-1]
        for k in set(a) | set(b):
            va, vb = np.atleast_1d(a.get(k, 0)).astype(float), np.atleast_1d(b.get(k, 0)).astype(float)
            if va.shape == vb.shape and np.abs(va - vb).max() > 1.0:
                errs.append("%s: does not loop (%s)" % (name, k))
                break
    if name in SEATED:
        for p in poses:
            thigh = min(ch(p, "leg_L"), ch(p, "leg_R")) + ch(p, "hips")          # thigh angle from vertical
            if not 70 <= thigh <= 100 or min(ch(p, "knee_L"), ch(p, "knee_R")) < 70:
                errs.append(name + ": not sitting (hips / knees straighten)")
                break
    if name in KNEELING:
        for p in poses:
            if ch(p, "knee_R") < 95 or ch(p, "leg_R") > 10 or ch(p, "leg_L") < 70:
                errs.append(name + ": not kneeling")
                break
    if "photographer" in name:
        for p in poses[:3] + poses[-3:]:
            if ch(p, "elbow_L") < 100 or ch(p, "arm_L") < 55:
                errs.append(name + ": camera not at the face")
                break
    if name == "sub_cheer":
        top = max(min(ch(p, "arm_L"), ch(p, "arm_R")) for p in poses)
        if top < 150:
            errs.append("sub_cheer: arms never go high (%.0f)" % top)
        if min(ch(poses[0], "knee_L"), ch(poses[-1], "knee_L")) < 70:
            errs.append("sub_cheer: does not start and end seated")
    return errs


def qa_all():
    return {n: e for n, e in ((n, qa(n)) for n in CLIPS) if e}


# ------------------------------------------------------------------ looks (rules on the team's colours)
# "team" = the team's primary, "team2" its secondary; anything else is a colour.  Garments: kit (jersey,
# shorts, socks, boots), "sleeves" (keeper_garments base layer), "trousers" (staff_garments).
LOOKS = {
    "sub": dict(jersey="bib", sleeves="team", shorts="team_shorts", socks="team_socks", boots="team_boots",
                garments=("sleeves",), bibs=("#d9f99d", "#fb923c", "#f472b6", "#fde047", "#67e8f9")),
    "manager": dict(jersey="#1c1f26", trim="#2a2f3a", sleeves="#1c1f26", trousers="#22252d", socks="#22252d",
                    boots="#0b0b0d", garments=("sleeves", "trousers"), number=0, name=False),
    "assistant": dict(jersey="team_dark", trim="team", sleeves="team_dark", trousers="#1f2229", socks="#1f2229",
                      boots="#0b0b0d", garments=("sleeves", "trousers"), number=0, name=False),
    "ballkid": dict(jersey="#0f2b46", trim="#e9eaee", sleeves="#0f2b46", trousers="#0f2b46", socks="#0f2b46",
                    boots="#e9eaee", garments=("sleeves", "trousers"), number=0, name=False, height=1.48),
    "photographer": dict(jersey="#f97316", trim="#1f2937", sleeves="#2b2f36", trousers="#2b2f36",
                         socks="#2b2f36", boots="#111111", garments=("sleeves", "trousers"), number=0, name=False,
                         prop="camera"),
}


def darker(hex_col: str, k: float = .45) -> str:
    h = hex_col.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


# ------------------------------------------------------------------ props
def _box(c, s):
    c, s = np.asarray(c, float), np.asarray(s, float) / 2
    V, F = [], []
    for ax in range(3):
        for sg in (-1, 1):
            n = np.zeros(3); n[ax] = sg
            u, v = [a for a in range(3) if a != ax]
            q = []
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = c + n * s
                p = p.copy(); p[u] += du * s[u]; p[v] += dv * s[v]
                q.append(p)
            base = len(V)
            V += q
            F += [(base, base + 1, base + 2), (base, base + 2, base + 3)] if sg > 0 else [(base, base + 2, base + 1), (base, base + 3, base + 2)]
    return np.array(V), np.array(F)


def _cyl_z(c, r, L, n=14):
    c = np.asarray(c, float)
    V, F = [], []
    for k in range(n):
        a = 2 * math.pi * k / n
        for z in (0.0, L):
            V.append(c + (r * math.cos(a), r * math.sin(a), z))
    for k in range(n):
        a0, b0, a1, b1 = 2 * k, 2 * k + 1, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1
        F += [(a0, a1, b1), (a0, b1, b0)]
    ca, cb = len(V), len(V) + 1
    V += [c, c + (0, 0, L)]
    for k in range(n):
        F += [(ca, 2 * ((k + 1) % n), 2 * k), (cb, 2 * k + 1, 2 * ((k + 1) % n) + 1)]
    return np.array(V), np.array(F)


def camera():
    """A DSLR body with a long telephoto lens and hood: grip at the origin, +Y up, lens along +Z."""
    parts = [(_box((0.0, .045, .0), (.15, .11, .08)), (.08, .08, .09)),          # body
             (_cyl_z((0.0, .05, .04), .048, .30), (.82, .82, .80)),               # white telephoto barrel
             (_cyl_z((0.0, .05, .34), .062, .09), (.08, .08, .09)),               # hood
             (_box((0.0, .115, -.02), (.05, .03, .05)), (.08, .08, .09))]         # prism hump
    return parts


def props_glb(path):
    """camera -> one GLB node per prop (vertex colours)."""
    meshes = {"camera": camera()}
    gl_nodes = {}
    for name, parts in meshes.items():
        Vs, Fs, Cs = [], [], []
        base = 0
        for (V, F), col in parts:
            Vs.append(V); Fs.append(F + base); Cs.append(np.tile(col, (len(V), 1)))
            base += len(V)
        gl_nodes[name] = (np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Cs))
    return _write_props(path, gl_nodes)


def _write_props(path, nodes):
    import json
    import struct
    buf = bytearray()
    views, accs, meshes, gnodes = [], [], [], []

    def add(arr, comp, typ, target=None, minmax=False):
        nonlocal buf
        b = arr.tobytes()
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(b), **({"target": target} if target else {})})
        buf += b
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        accs.append(a)
        return len(accs) - 1
    for name, (V, F, C) in nodes.items():
        V = V.astype(np.float32)
        tri = V[F]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        N = np.zeros_like(V)
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        at = {"POSITION": add(V, 5126, "VEC3", 34962, True), "NORMAL": add(N.astype(np.float32), 5126, "VEC3", 34962),
              "COLOR_0": add(np.asarray(C, np.float32), 5126, "VEC3", 34962)}
        ind = add(F.astype(np.uint32).reshape(-1), 5125, "SCALAR", 34963)
        meshes.append({"name": name, "primitives": [{"attributes": at, "indices": ind, "material": 0}]})
        gnodes.append({"name": name, "mesh": len(meshes) - 1})
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge pitchside v11.39"}, "scene": 0,
          "scenes": [{"nodes": list(range(len(gnodes)))}], "nodes": gnodes, "meshes": meshes,
          "materials": [{"name": "prop", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": .45}}],
          "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(buf)}]}
    js = json.dumps(gl).encode()
    while len(js) % 4:
        js += b" "
    while len(buf) % 4:
        buf.append(0)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(buf), 0x004E4942) + bytes(buf)
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


# ------------------------------------------------------------------ places
def placements(stadium, half_length, half_width, subs=7, ball_kids=6, photographers=8, seed=7):
    """-> list of dicts {role, team, pos [x, y, z], yaw (radians, facing +Z at 0), clip} round a ground.

    Subs take the dugout seats (`stadium["dugouts"][k]["bench"]` when the ground lists them, else spread
    along the seat block); each team's manager stands in his technical area in front of the dugout, an
    assistant coach beside the dugout; ball kids stand behind the boards - two on the far touchline, the rest
    behind the goals off to the side; photographers kneel behind each goal line, either side of the goal.
    Facing is towards the pitch (or the halfway line for the bench).  Works for any `sforge.stadium` sport."""
    rng = np.random.default_rng(seed)
    out = []

    def face(px, pz, tx, tz):
        return float(math.atan2(tx - px, tz - pz))
    for d in (stadium or {}).get("dugouts", []):
        team = int(d.get("team", 0))
        cx, _, cz = d["centre"]
        bench = d.get("bench")
        if not bench:
            n = int(d.get("seats", 10))
            bench = [[cx - 3.2 + s * .71, d.get("seat_top", .52), cz - .35] for s in range(n)]
        pick = sorted(rng.choice(len(bench), size=min(subs, len(bench)), replace=False))
        for k, i in enumerate(pick):
            x, y, z = bench[i]
            out.append({"role": "sub", "team": team, "pos": [float(x), float(y), float(z)],
                        "yaw": face(x, z, x * .3, 0.0), "clip": "sub_sit", "seated": True})
        fz = float(d.get("front_z", cz + 1.0))
        mx = cx + (-1.6 if cx < 0 else 1.6)
        out.append({"role": "manager", "team": team, "pos": [float(mx), 0.0, fz + 1.6],
                    "yaw": face(mx, fz + 1.6, 0.0, 0.0), "clip": "manager_watch"})
        ax = cx + (2.8 if cx < 0 else -2.8)
        out.append({"role": "assistant", "team": team, "pos": [float(ax), 0.0, fz + .7],
                    "yaw": face(ax, fz + .7, 0.0, 0.0), "clip": "staff_stand"})
    hl, hw = float(half_length), float(half_width)
    kid_spots = [(-hl * .45, hw + 3.2), (hl * .45, hw + 3.2), (-hl - 3.0, -hw * .6), (-hl - 3.0, hw * .6),
                 (hl + 3.0, -hw * .6), (hl + 3.0, hw * .6)]
    for x, z in kid_spots[:ball_kids]:
        out.append({"role": "ballkid", "team": -1, "pos": [x, 0.0, z], "yaw": face(x, z, 0.0, 0.0),
                    "clip": "ballkid_ready"})
    per_end = photographers // 2
    for sx in (-1, 1):
        for k in range(per_end):
            side = -1 if k % 2 == 0 else 1
            z = side * (5.6 + (k // 2) * 1.9 + rng.uniform(-.3, .3))
            x = sx * (hl + 2.4 + rng.uniform(0, .5))
            clip = "photographer_kneel" if k % 3 != 2 else "photographer_stand"
            out.append({"role": "photographer", "team": -1, "pos": [float(x), 0.0, float(z)],
                        "yaw": face(x, z, 0.0, z * .2), "clip": clip})
    return out
