"""Match officials: signals, kits and props for field sports (v11.31, fed back from Arena FC).

Arena FC refereed every match invisibly - fouls, cards, offsides and VAR all happened with nobody on the
pitch to give them.  This pack gives a game what it needs to put a referee, two assistants and a fourth
official on the field:

  clips   ref_whistle, ref_card, ref_advantage, ref_penalty, ref_direct, ref_indirect, ref_goal,
          ar_flag_up, ar_offside, ar_flag_corner, ar_flag_throw, fourth_board - authored in Sprite Forge's
          semantic pose channels, right-handed (card / whistle / flag in the right hand), registered in the
          motion library like any other clip, with event fractions (`EVENTS`: "signal" = the moment the
          signal is clearest, which a game holds while it shows the decision)
  kits    `KITS`: original official colourways on the `sforge.tailor` / `sforge.kitdesign` atlas (no number,
          no name; a badge and trim)
  props   `props_glb(path)`: assistant's flag (two-tone, on a stick), yellow and red cards, whistle, the
          fourth official's board - small static meshes with their grip at the origin, +Y up, ready to hang
          off a hand bone
  glb     `append_clips(glb_in, glb_out, rig, clips)`: add baked clips to an existing skinned GLB, keeping its
          meshes and every animation already in it (a squad GLB whose motion-capture sources are not at hand)

    from sforge import officials as O
    O.register()                         # idempotent; done on import
    O.qa("ar_offside")                   # [] when the clip passes
    O.props_glb("officials_props.glb")

Positioning (the diagonal system, an assistant level with the second-last defender) is game logic and
stays in the game; `ROLES` documents it so other games built on Sprite Forge place officials the same way.
"""
from __future__ import annotations

import json
import struct

import numpy as np

from .motions import LIB, STAND, K, M, P

# ------------------------------------------------------------------ clips
# arm_X = (raise forward, raise sideways, twist) in degrees, (0, 0, 0) hanging; elbow in degrees of bend.
UP_R = dict(arm_R=(172, 8, 0), elbow_R=4)                         # straight up
FWD_R = dict(arm_R=(86, 6, 0), elbow_R=6)                         # straight out in front
SIDE_R = dict(arm_R=(12, 86, 0), elbow_R=6)                       # straight out to the side
FLAG_DOWN = dict(arm_R=(10, 12, 0), elbow_R=14)                   # flag held down by the leg
ALERT = dict(hips=(4, 0, 0), spine=(3, 0, 0), neck=(-4, 0, 0), leg_L=(6, 4, 0), leg_R=(2, 4, 0),
             knee_L=8, knee_R=6, arm_L=(8, 12, 0), arm_R=(8, 12, 0), elbow_L=20, elbow_R=20)

CLIPS = {
    "ref_whistle": dict(desc="whistle to the mouth and blow", dur=1.0, keys=K(
        (0.0, P(ALERT)),
        (0.25, P(ALERT, arm_R=(52, -18, 0), elbow_R=128, neck=(-8, 0, 0))),
        (0.45, P(ALERT, arm_R=(56, -22, 0), elbow_R=136, chest=(-3, 0, 0), neck=(-10, 0, 0))),
        (0.7, P(ALERT, arm_R=(54, -20, 0), elbow_R=132, neck=(-6, 0, 0))),
        (1.0, P(ALERT)))),
    "ref_card": dict(desc="card from the pocket, held high at arm's length to the player", dur=1.8, keys=K(
        (0.0, P(ALERT)),
        (0.18, P(ALERT, arm_R=(-14, 10, 0), elbow_R=50, chest=(2, -8, 0))),          # hand to the back pocket
        (0.38, P(ALERT, arm_R=(110, 6, 0), elbow_R=30, chest=(-2, 4, 0))),
        (0.5, P(ALERT, UP_R, chest=(-4, 6, 0), neck=(-6, 0, 0))),                     # shown
        (0.82, P(ALERT, UP_R, chest=(-4, 6, 0), neck=(-6, 0, 0))),
        (1.0, P(ALERT)))),
    "ref_advantage": dict(desc="play on: both arms swept forward, palms up", dur=1.2, keys=K(
        (0.0, P(ALERT)),
        (0.3, P(ALERT, arm_L=(70, 18, 0), arm_R=(70, 18, 0), elbow_L=12, elbow_R=12, leg_L=(14, 4, 0), knee_L=16)),
        (0.55, P(ALERT, arm_L=(84, 4, 0), arm_R=(84, 4, 0), elbow_L=6, elbow_R=6, leg_L=(20, 4, 0), knee_L=18)),
        (0.8, P(ALERT, arm_L=(80, 6, 0), arm_R=(80, 6, 0), elbow_L=8, elbow_R=8)),
        (1.0, P(ALERT)))),
    "ref_penalty": dict(desc="whistle, then point firmly at the penalty spot", dur=1.6, keys=K(
        (0.0, P(ALERT, arm_R=(54, -20, 0), elbow_R=132)),
        (0.2, P(ALERT, arm_R=(54, -20, 0), elbow_R=132)),
        (0.42, P(ALERT, arm_R=(64, 2, 0), elbow_R=4, chest=(8, 0, 0), neck=(6, 0, 0), leg_R=(16, 4, 0), knee_R=14)),
        (0.85, P(ALERT, arm_R=(62, 2, 0), elbow_R=4, chest=(8, 0, 0), neck=(6, 0, 0), leg_R=(16, 4, 0), knee_R=14)),
        (1.0, P(ALERT)))),
    "ref_direct": dict(desc="direct free kick: arm out pointing the way it goes", dur=1.4, keys=K(
        (0.0, P(ALERT)),
        (0.3, P(ALERT, SIDE_R, chest=(0, -8, 0))),
        (0.8, P(ALERT, SIDE_R, chest=(0, -8, 0))),
        (1.0, P(ALERT)))),
    "ref_indirect": dict(desc="indirect free kick: arm straight up and held", dur=1.8, keys=K(
        (0.0, P(ALERT)),
        (0.25, P(ALERT, UP_R)),
        (0.85, P(ALERT, UP_R)),
        (1.0, P(ALERT)))),
    "ref_goal": dict(desc="goal given: point back to the centre circle and jog off", dur=1.4, keys=K(
        (0.0, P(ALERT)),
        (0.3, P(ALERT, arm_R=(76, -24, 0), elbow_R=6, hips=(2, -20, 0), chest=(0, -16, 0))),
        (0.8, P(ALERT, arm_R=(76, -24, 0), elbow_R=6, hips=(2, -20, 0), chest=(0, -16, 0))),
        (1.0, P(ALERT)))),
    "ar_flag_up": dict(desc="assistant: flag raised straight up and held", dur=1.6, keys=K(
        (0.0, P(ALERT, FLAG_DOWN)),
        (0.2, P(ALERT, UP_R, chest=(-2, 0, 0))),
        (0.9, P(ALERT, UP_R, chest=(-2, 0, 0))),
        (1.0, P(ALERT, UP_R)))),
    "ar_offside": dict(desc="assistant: flag up, then held out level across the pitch (offside position)", dur=2.4,
                       keys=K(
        (0.0, P(ALERT, FLAG_DOWN)),
        (0.15, P(ALERT, UP_R)),
        (0.45, P(ALERT, UP_R)),
        (0.6, P(ALERT, FWD_R)),
        (0.92, P(ALERT, FWD_R)),
        (1.0, P(ALERT, FLAG_DOWN)))),
    "ar_flag_corner": dict(desc="assistant: flag pointed down at the corner arc", dur=1.4, keys=K(
        (0.0, P(ALERT, FLAG_DOWN)),
        (0.3, P(ALERT, arm_R=(52, 30, 0), elbow_R=4, chest=(4, 0, 0))),
        (0.85, P(ALERT, arm_R=(52, 30, 0), elbow_R=4, chest=(4, 0, 0))),
        (1.0, P(ALERT, FLAG_DOWN)))),
    "ar_flag_throw": dict(desc="assistant: flag held up at 45 degrees towards the attacking direction", dur=1.4,
                          keys=K(
        (0.0, P(ALERT, FLAG_DOWN)),
        (0.3, P(ALERT, arm_R=(128, 8, 0), elbow_R=4)),
        (0.85, P(ALERT, arm_R=(128, 8, 0), elbow_R=4)),
        (1.0, P(ALERT, FLAG_DOWN)))),
    "fourth_board": dict(desc="fourth official: substitution / added-time board held up in both hands", dur=2.4,
                         keys=K(
        (0.0, P(STAND)),
        (0.2, P(STAND, arm_L=(160, -12, 0), arm_R=(160, -12, 0), elbow_L=24, elbow_R=24)),
        (0.9, P(STAND, arm_L=(160, -12, 0), arm_R=(160, -12, 0), elbow_L=24, elbow_R=24)),
        (1.0, P(STAND)))),
}

# "signal": the fraction where the decision reads clearest (a game may freeze there while it holds the call)
EVENTS = {
    "ref_whistle": {"signal": .45}, "ref_card": {"signal": .5}, "ref_advantage": {"signal": .55},
    "ref_penalty": {"signal": .42}, "ref_direct": {"signal": .3}, "ref_indirect": {"signal": .25},
    "ref_goal": {"signal": .3}, "ar_flag_up": {"signal": .2}, "ar_offside": {"signal": .6},
    "ar_flag_corner": {"signal": .3}, "ar_flag_throw": {"signal": .3}, "fourth_board": {"signal": .2},
}
for _n, _e in EVENTS.items():
    _e.update({"ball_contact": -1.0, "footsteps": [], "hit_start": -1.0, "hit_end": -1.0})

# signals whose whole point is a raised arm (the field-sport "hands up" QA must not flag them)
ARM_UP = {"ref_card", "ref_indirect", "ar_flag_up", "ar_offside", "ar_flag_throw", "fourth_board"}


def register() -> None:
    """Add every officials clip to `sforge.motions.LIB` (idempotent)."""
    for name, spec in CLIPS.items():
        if name in LIB:
            continue
        M(name, "Official", spec["desc"], keys=spec["keys"], loop=False)
        LIB[name].duration_s = spec["dur"]


def qa(name: str, samples: int = 32) -> list[str]:
    """[] when the clip reads: the signalling arm reaches its pose and holds it for at least a fifth of the
    clip, no arm swings behind the back past 30 deg except to the pocket, and the clip starts and ends in a
    neutral stance (so a game can chain it into running)."""
    register()
    m = LIB.get(name)
    if m is None:
        return ["unknown clip " + name]
    errs = []
    poses = [m.sample(i / samples)[0] for i in range(samples + 1)]
    ar = np.array([p.get("arm_R", (0, 0, 0))[0] for p in poses], float)
    if name in ARM_UP and ar.max() < 120:
        errs.append("%s: signalling arm never goes up (max %.0f deg)" % (name, ar.max()))
    hold = np.sum(np.abs(ar - ar.max()) < 6) / len(ar) if name in ARM_UP else 1
    if hold < .2:
        errs.append("%s: signal held for only %.0f%% of the clip" % (name, hold * 100))
    for p in (poses[0], poses[-1]):
        if max(abs(p.get("arm_L", (0, 0, 0))[0]), abs(p.get("arm_L", (0, 0, 0))[1])) > 30:
            errs.append(name + ": left arm not neutral at the ends")
    if name not in EVENTS:
        errs.append(name + ": no event entry")
    return errs


def qa_all():
    return {n: qa(n) for n in CLIPS}


# ------------------------------------------------------------------ roles (documentation for games)
ROLES = {
    "referee": "diagonal system: stays 12-20 m from the ball on the line from the near-right corner to the "
               "far-left corner (as seen from his own half), goal-side of play, out of passing lanes; faces the ball.",
    "assistant": "one per touchline, each owning one half: level with the second-last defender of the side "
                 "defending his half (or the ball if it is nearer the goal line), on the line, facing the pitch; "
                 "sidesteps, sprints when play breaks.",
    "fourth": "between the technical areas at the halfway line; holds up the board for substitutions and "
              "added time.",
}

# ------------------------------------------------------------------ kits (tailor / kitdesign atlas)
KITS = {
    "classic": dict(primary="#111318", secondary="#111318", trim="#e9eaee", shorts="#111318", socks="#111318",
                    pattern="plain", boots="#111318"),
    "volt": dict(primary="#d9f99d", secondary="#bef264", trim="#111318", shorts="#111318", socks="#111318",
                 pattern="pinstripes", boots="#111318"),
    "crimson": dict(primary="#b91c1c", secondary="#991b1b", trim="#111318", shorts="#111318", socks="#111318",
                    pattern="band", boots="#111318"),
    "teal": dict(primary="#0f766e", secondary="#115e59", trim="#e9eaee", shorts="#111318", socks="#0f766e",
                 pattern="chevron", boots="#111318"),
    "royal": dict(primary="#1e3a8a", secondary="#1e40af", trim="#facc15", shorts="#111318", socks="#1e3a8a",
                  pattern="plain", boots="#111318"),
}


def kit_for(home_primary: str, away_primary: str) -> str:
    """the first official kit far enough from both teams' shirts (RGB distance)."""
    def rgb(h):
        h = h.lstrip("#")
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255
    a, b = rgb(home_primary), rgb(away_primary)
    for name, k in KITS.items():
        c = rgb(k["primary"])
        if np.linalg.norm(c - a) / np.sqrt(3) > .3 and np.linalg.norm(c - b) / np.sqrt(3) > .3:
            return name
    return "volt"


# ------------------------------------------------------------------ props
def _box(c, s):
    x, y, z = s[0] / 2, s[1] / 2, s[2] / 2
    v = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z], [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]]) + c
    f = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [3, 6, 2], [3, 7, 6], [0, 4, 7], [0, 7, 3],
         [1, 2, 6], [1, 6, 5]]
    V, F = [], []
    for t in f:                                   # flat faces: duplicate per triangle for crisp normals
        V += [v[t[0]], v[t[1]], v[t[2]]]
    F = np.arange(len(V)).reshape(-1, 3)
    return np.array(V), F


def _cyl(c, r, h, n=12):
    V, F = [], []
    for i in range(n):
        a0, a1 = 2 * np.pi * i / n, 2 * np.pi * (i + 1) / n
        p = [np.array([np.cos(a) * r, 0, np.sin(a) * r]) for a in (a0, a1)]
        b0, b1, t0, t1 = p[0] + c, p[1] + c, p[0] + c + [0, h, 0], p[1] + c + [0, h, 0]
        V += [b0, t1, b1, b0, t0, t1, c + [0, h, 0], t1, t0, c, b0, b1]
    V = np.array(V)
    return V, np.arange(len(V)).reshape(-1, 3)


def _flag():
    """assistant's flag: a 50 cm stick, a 40 x 33 cm cloth in four diagonal quarters (two colours)."""
    parts = []
    sv, sf = _cyl(np.zeros(3), .011, .55)
    parts.append((sv, sf, (0.08, 0.08, 0.09)))
    # cloth on the far side of the stick from the hand, upper part
    w, h = .40, .33
    y0 = .55 - h
    c = np.array([w / 2 + .012, y0 + h / 2, 0])
    corners = [c + [-w / 2, -h / 2, 0], c + [w / 2, -h / 2, 0], c + [w / 2, h / 2, 0], c + [-w / 2, h / 2, 0]]
    mid = c
    cols = [(1.0, .82, .05), (.95, .25, .05), (1.0, .82, .05), (.95, .25, .05)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        tri = np.array([a, b, mid])
        parts.append((np.concatenate([tri, tri[::-1]]), np.array([[0, 1, 2], [3, 4, 5]]), cols[i]))
    return parts


def _card(col):
    v, f = _box(np.array([0, .045, 0]), (.06, .09, .003))
    return [(v, f, col)]


def _whistle():
    v, f = _box(np.array([0, .012, .015]), (.018, .02, .045))
    v2, f2 = _cyl(np.array([0, 0, -.008]), .012, .024)
    return [(v, f, (.85, .86, .9)), (v2, f2, (.85, .86, .9))]


def _board():
    """fourth official's board: a 60 x 40 cm panel on a handle, a dark face (a game draws the numbers)."""
    hv, hf = _cyl(np.zeros(3), .015, .25)
    pv, pf = _box(np.array([0, .45, 0]), (.6, .4, .04))
    fv, ff = _box(np.array([0, .45, .021]), (.54, .34, .002))
    return [(hv, hf, (.1, .1, .12)), (pv, pf, (.18, .2, .25)), (fv, ff, (.02, .03, .04))]


PROPS = {"flag": _flag, "card_yellow": lambda: _card((1.0, .85, .05)), "card_red": lambda: _card((.85, .05, .07)),
         "whistle": _whistle, "board": _board}


def props_glb(path, names=None):
    """write the officials' props as one GLB: a node per prop (grip at the origin, +Y up), vertex colours."""
    from .glbpack import _Out
    out = _Out()
    nodes, meshes = [], []
    mat = {"name": "official_prop", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0,
                                                               "roughnessFactor": .6}, "doubleSided": True}
    for k in (names or PROPS):
        parts = PROPS[k]()
        V = np.concatenate([p[0] for p in parts]).astype(np.float32)
        Fs, C, o = [], [], 0
        for v, f, col in parts:
            Fs.append(np.asarray(f) + o)
            C.append(np.tile(list(col) + [1.0], (len(v), 1)))
            o += len(v)
        F = np.concatenate(Fs)
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        N = np.zeros_like(V)
        for c in range(3):
            np.add.at(N, F[:, c], fn)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True), "NORMAL": out.add(N.astype(np.float32), 5126, "VEC3", 34962),
                 "COLOR_0": out.add(np.concatenate(C).astype(np.float32), 5126, "VEC4", 34962)}
        ind = out.add(F.astype(np.uint16).reshape(-1), 5123, "SCALAR", 34963)
        meshes.append({"name": k, "primitives": [{"attributes": attrs, "indices": ind, "material": 0, "mode": 4}]})
        nodes.append({"name": k, "mesh": len(meshes) - 1})
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge officials.props_glb (v11.31)"}, "scene": 0,
          "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": [mat],
          "accessors": out.acc, "bufferViews": out.views, "buffers": [{"byteLength": 0}]}
    return _write(gl, out.b, path)


def _write(gl, b, path):
    while len(b) % 4:
        b.append(0)
    gl["buffers"][0]["byteLength"] = len(b)
    js = json.dumps(gl, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    data = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(b)) + struct.pack("<II", len(js), 0x4E4F534A) + js + \
        struct.pack("<II", len(b), 0x004E4942) + bytes(b)
    open(path, "wb").write(data)
    return len(data)


# ------------------------------------------------------------------ append clips to an existing GLB
def append_clips(glb_in, glb_out, rig, clips, root_motion="inplace", replace=True):
    """Add baked clips (rigrec.Clip on `rig`) to a skinned GLB, keeping every mesh, material,
    image and the animations already in it.  A clip with a name that is already there replaces it
    (replace=True).  Channels are bound to the GLB node whose name matches the rig bone, so GLBs
    whose node order differs from skin-joint order (e.g. an extra container node up front) work
    unchanged; the old bone-index == node-index requirement no longer applies."""
    from .glbpack import _Out, read_glb
    from .rigrec import strip_root_motion
    j, buf = read_glb(glb_in)
    node_names = [nd.get("name") for nd in j["nodes"]]
    dst_index = {}
    for i, n in enumerate(node_names):
        if n not in dst_index:
            dst_index[n] = i
    missing = [b for b in rig.bones if b not in dst_index]
    if missing:
        raise ValueError("GLB nodes do not cover rig bones: %s" % missing[:8])
    out = _Out()
    amap = {}

    def keep(i):
        if i not in amap:
            amap[i] = out.copy_acc(j, buf, i)
        return amap[i]
    meshes = []
    for m in j.get("meshes", []):
        prs = []
        for pr in m["primitives"]:
            p2 = dict(pr)
            p2["attributes"] = {k: keep(v) for k, v in pr["attributes"].items()}
            if "indices" in pr:
                p2["indices"] = keep(pr["indices"])
            p2.pop("targets", None)
            prs.append(p2)
        meshes.append(dict(m, primitives=prs))
    skins = []
    for sk in j.get("skins", []):
        s2 = dict(sk)
        if "inverseBindMatrices" in sk:
            s2["inverseBindMatrices"] = keep(sk["inverseBindMatrices"])
        skins.append(s2)
    new = set(clips)
    anims = []
    for an in j.get("animations", []):
        if replace and an.get("name") in new:
            continue
        sm = [{"input": keep(s["input"]), "output": keep(s["output"]), "interpolation": s.get("interpolation", "LINEAR")}
              for s in an["samplers"]]
        anims.append({"name": an.get("name", "anim"), "channels": an["channels"], "samplers": sm})
    hips = rig.meta.get("hips_index", 0)
    for cn, c in clips.items():
        t = (np.arange(c.frames) / c.fps).astype(np.float32)
        ta = out.add(t, 5126, "SCALAR", minmax=True)
        T = strip_root_motion(rig, c) if root_motion == "inplace" else c.T
        ch, sm = [], []
        for i in range(rig.nb):
            node = dst_index[rig.bones[i]]
            sm.append({"input": ta, "output": out.add(c.R[:, i].astype(np.float32), 5126, "VEC4"), "interpolation": "LINEAR"})
            ch.append({"sampler": len(sm) - 1, "target": {"node": node, "path": "rotation"}})
            if i == hips or rig.parent[i] < 0:
                sm.append({"input": ta, "output": out.add(T[:, i].astype(np.float32), 5126, "VEC3"), "interpolation": "LINEAR"})
                ch.append({"sampler": len(sm) - 1, "target": {"node": node, "path": "translation"}})
        anims.append({"name": cn, "channels": ch, "samplers": sm})
    imgs = []
    for im in j.get("images", []):
        im2 = dict(im)
        if "bufferView" in im:
            bv = j["bufferViews"][im["bufferView"]]
            o = bv.get("byteOffset", 0)
            im2["bufferView"] = out.view(bytes(buf[o:o + bv["byteLength"]]))
        imgs.append(im2)
    gl = dict(j)
    gl.update({"meshes": meshes, "skins": skins, "animations": anims, "accessors": out.acc, "bufferViews": out.views,
               "buffers": [{"byteLength": 0}]})
    if imgs:
        gl["images"] = imgs
    return _write(gl, out.b, glb_out)


register()
