"""Procedurally generated SAMPLE rigs and animations for the starter library (v6).

Everything here is synthetic: simple capsule / box figures built from code, no scans, no likeness of anyone,
no third-party assets.  Licensed CC0 (public domain dedication) by the Sprite Forge Studio authors.
The rigs deliberately differ in proportions, rest pose, naming convention and bone orientation so they
exercise the importer, the bone-map detector and the retargeter:

  sample_chibi      1.10 m, big head, T-pose, Unity-humanoid names, identity bone orientations
  sample_lanky      2.00 m, long limbs, A-pose, Mixamo names (mixamorig:*), Y-along-bone orientations, end bones
  sample_stocky     1.60 m, wide, arms-down, Rigify DEF- names (.L/.R), twist bones (unmapped on purpose)
  sample_moves      animation-only file: Mixamo-named 1.75 m skeleton with new clips (wave, squat, hop, bow, spin)
"""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageDraw

from .rigrec import Rig, m4, rot_between, FPS
from . import bonemap as BM

CC0 = dict(spdx="CC0-1.0", custom_text="", author="Sprite Forge Studio (procedurally generated)", source_url="",
           redistribution="yes", attribution="", notes="Synthetic sample made by samplerigs.py; no third-party content.")

NAMES = {
    "unity": {"hips": "Hips", "spine": "Spine", "chest": "Chest", "upperchest": "UpperChest", "neck": "Neck", "head": "Head",
              "shoulder_%s": "%sShoulder", "upperarm_%s": "%sUpperArm", "forearm_%s": "%sLowerArm", "hand_%s": "%sHand",
              "thigh_%s": "%sUpperLeg", "shin_%s": "%sLowerLeg", "foot_%s": "%sFoot", "toe_%s": "%sToes", "_side": ("Left", "Right")},
    "mixamo": {"hips": "mixamorig:Hips", "spine": "mixamorig:Spine", "chest": "mixamorig:Spine1", "upperchest": "mixamorig:Spine2",
               "neck": "mixamorig:Neck", "head": "mixamorig:Head", "shoulder_%s": "mixamorig:%sShoulder", "upperarm_%s": "mixamorig:%sArm",
               "forearm_%s": "mixamorig:%sForeArm", "hand_%s": "mixamorig:%sHand", "thigh_%s": "mixamorig:%sUpLeg",
               "shin_%s": "mixamorig:%sLeg", "foot_%s": "mixamorig:%sFoot", "toe_%s": "mixamorig:%sToeBase", "_side": ("Left", "Right"),
               "_end": {"head": "mixamorig:HeadTop_End", "toe_%s": "mixamorig:%sToe_End"}},
    "rigify": {"hips": "DEF-spine", "spine": "DEF-spine.001", "chest": "DEF-spine.002", "upperchest": "DEF-spine.003",
               "neck": "DEF-spine.004", "head": "DEF-spine.006", "shoulder_%s": "DEF-shoulder.%s", "upperarm_%s": "DEF-upper_arm.%s",
               "forearm_%s": "DEF-forearm.%s", "hand_%s": "DEF-hand.%s", "thigh_%s": "DEF-thigh.%s", "shin_%s": "DEF-shin.%s",
               "foot_%s": "DEF-foot.%s", "toe_%s": "DEF-toe.%s", "_side": ("L", "R"),
               "_twist": {"upperarm_%s": "DEF-upper_arm.%s.001", "thigh_%s": "DEF-thigh.%s.001"}, "_extra_neck": "DEF-spine.005"},
}

PRESETS = {
    "sample_chibi": dict(H=1.10, leg=0.36, head=0.34, shoulder=0.14, hip=0.075, arm=0.85, girth=1.35, pose="T", names="unity",
                         orient="identity", kit=dict(shirt=(0.95, 0.55, 0.1), shorts=(0.2, 0.25, 0.6), socks=(0.95, 0.95, 0.95),
                                                     hair=(0.85, 0.2, 0.45), skin=(0.62, 0.78, 0.92)),
                         desc="1.10 m chibi: big head, short legs, T-pose, Unity humanoid bone names"),
    "sample_lanky": dict(H=2.00, leg=0.55, head=0.11, shoulder=0.12, hip=0.055, arm=1.12, girth=0.8, pose="A", names="mixamo",
                         orient="along", kit=dict(shirt=(0.15, 0.55, 0.55), shorts=(0.12, 0.12, 0.14), socks=(0.15, 0.55, 0.55),
                                                  hair=(0.1, 0.1, 0.1), skin=(0.72, 0.72, 0.76)),
                         desc="2.00 m lanky: long limbs, A-pose, Mixamo bone names, bones oriented along Y"),
    "sample_stocky": dict(H=1.60, leg=0.46, head=0.15, shoulder=0.17, hip=0.085, arm=0.95, girth=1.45, pose="I", names="rigify",
                          orient="along", kit=dict(shirt=(0.55, 0.15, 0.15), shorts=(0.85, 0.82, 0.7), socks=(0.55, 0.15, 0.15),
                                                   hair=(0.45, 0.3, 0.15), skin=(0.6, 0.85, 0.6)),
                          desc="1.60 m stocky: wide body, arms down, Rigify DEF- names with twist bones"),
}


def skeleton_points(P):
    H = P["H"]; legf = P["leg"]; headf = P["head"]
    hip_y = legf * H; foot_y = 0.045 * H
    head_h = headf * H
    neck_y = H - head_h - 0.03 * H
    T = neck_y - hip_y
    J = {"hips": (0, hip_y, 0), "spine": (0, hip_y + 0.18 * T, 0), "chest": (0, hip_y + 0.45 * T, 0),
         "upperchest": (0, hip_y + 0.72 * T, 0), "neck": (0, neck_y, 0), "head": (0, neck_y + 0.03 * H, 0),
         "head_top": (0, H, 0)}
    a = {"T": 0.0, "A": 42.0, "I": 82.0}[P["pose"]]
    ar = math.radians(a)
    up_l = 0.18 * H * P["arm"]; fo_l = 0.16 * H * P["arm"]; ha_l = 0.075 * H * P["arm"]
    for s, sg in (("L", 1), ("R", -1)):
        sh = np.array([sg * 0.03 * H, hip_y + 0.86 * T, 0.0])
        ua = np.array([sg * P["shoulder"] * H, hip_y + 0.86 * T, 0.0])
        d = np.array([sg * math.cos(ar), -math.sin(ar), 0.0])
        J["shoulder_" + s] = tuple(sh); J["upperarm_" + s] = tuple(ua)
        J["forearm_" + s] = tuple(ua + d * up_l); J["hand_" + s] = tuple(ua + d * (up_l + fo_l))
        J["handtip_" + s] = tuple(ua + d * (up_l + fo_l + ha_l))
        x = sg * P["hip"] * H
        J["thigh_" + s] = (x, hip_y - 0.03 * H, 0); J["shin_" + s] = (x, (hip_y - 0.03 * H + foot_y) * 0.5 + 0.01 * H, 0.0)
        J["foot_" + s] = (x, foot_y, 0); J["toe_" + s] = (x, 0.018 * H, 0.10 * H * max(0.8, P["arm"] * 0.9))
        J["toe_end_" + s] = (x, 0.015 * H, 0.15 * H * max(0.8, P["arm"] * 0.9))
    return {k: np.array(v, float) for k, v in J.items()}


CHAIN_PARENT = {"hips": None, "spine": "hips", "chest": "spine", "upperchest": "chest", "neck": "upperchest", "head": "neck",
                "shoulder_%s": "upperchest", "upperarm_%s": "shoulder_%s", "forearm_%s": "upperarm_%s", "hand_%s": "forearm_%s",
                "thigh_%s": "hips", "shin_%s": "thigh_%s", "foot_%s": "shin_%s", "toe_%s": "foot_%s"}
TIP = {"head": "head_top", "hand_%s": "handtip_%s", "toe_%s": "toe_end_%s"}


def _expand(tab, s):
    out = {}
    for k, v in tab.items():
        if k.startswith("_"):
            continue
        if "%s" in k:
            out[k % s] = (v % s) if v and "%s" in v else v
        elif s == "L":
            out[k] = v
    return out


def _orient(pos, child, mode):
    if mode == "identity":
        return np.eye(3)
    y = child - pos
    n = np.linalg.norm(y)
    if n < 1e-9:
        return np.eye(3)
    y = y / n
    ref = np.array([0, 0, 1.0]) if abs(y[2]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(y, ref); x /= np.linalg.norm(x)
    z = np.cross(x, y)
    return np.column_stack([x, y, z])


def build(name, P=None):
    P = dict(PRESETS[name] if P is None else P)
    J = skeleton_points(P)
    tab = NAMES[P["names"]]
    sides = tab["_side"]
    names = {}
    for s, sv in zip(("L", "R"), sides):
        for k, v in tab.items():
            if k.startswith("_"):
                continue
            ck = k % s if "%s" in k else k
            names[ck] = v % sv if "%s" in v else v
    bones, parent, binds, canon_of = [], [], [], {}
    idx = {}

    def add(bname, pidx, pos, R):
        idx[bname] = len(bones); bones.append(bname); parent.append(pidx); binds.append(m4(R, pos))
        return idx[bname]
    order = ["hips", "spine", "chest", "upperchest", "neck", "head"] + \
            ["%s_%s" % (l, s) for s in ("L", "R") for l in ("shoulder", "upperarm", "forearm", "hand", "thigh", "shin", "foot", "toe")]
    twist = tab.get("_twist", {})
    for ck in order:
        base = ck[:-1] + "%s" if ck[-2:] in ("_L", "_R") else ck
        s = ck[-1] if ck[-2:] in ("_L", "_R") else None
        pk = CHAIN_PARENT[base]
        pk = (pk % s if pk and "%s" in pk else pk)
        if ck == "head" and "_extra_neck" in tab:
            mid = (J["neck"] + J["head"]) / 2
            if tab["_extra_neck"] not in idx:
                add(tab["_extra_neck"], idx[names["neck"]], mid, _orient(mid, J["head"], P["orient"]))
        pidx = -1 if pk is None else idx[names[pk]]
        if ck == "head" and "_extra_neck" in tab:
            pidx = idx[tab["_extra_neck"]]
        # child point for orientation
        tip = TIP.get(base)
        kids = [k for k in order if (CHAIN_PARENT.get(k[:-1] + "%s" if k[-2:] in ("_L", "_R") else k) or "").replace("%s", s or "") == ck]
        if tip:
            cpt = J[tip % s if "%s" in tip else tip]
        elif ck == "hips":
            cpt = J["spine"]
        elif ck == "upperchest":
            cpt = J["neck"]
        elif kids:
            cpt = J[kids[0]]
        else:
            cpt = J[ck] + np.array([0, 0.1, 0])
        if base in twist:
            # twist bone half-way along the segment; the next bone hangs off it
            pass
        bi = add(names[ck], pidx, J[ck], _orient(J[ck], cpt, P["orient"]))
        canon_of[bi] = ck
        if base in twist:
            nxt = {"upperarm_%s": "forearm_%s", "thigh_%s": "shin_%s"}[base] % s
            mid = (J[ck] + J[nxt]) / 2
            ti = add(twist[base] % (sides[0] if s == "L" else sides[1]) if "%s" in twist[base] else twist[base], bi, mid, _orient(mid, J[nxt], P["orient"]))
            names["_twist_" + ck] = bones[ti]
        if ck in ("forearm_L", "forearm_R", "shin_L", "shin_R") and ("_twist_" + {"forearm": "upperarm", "shin": "thigh"}[ck.split("_")[0]] + "_" + s) in names:
            # re-parent onto the twist bone
            parent[bi] = idx[names["_twist_" + {"forearm": "upperarm", "shin": "thigh"}[ck.split("_")[0]] + "_" + s]]
    ends = tab.get("_end", {})
    for ck, en in ends.items():
        for s, sv in zip(("L", "R"), sides):
            if "%s" in ck:
                c = ck % s; nm = en % sv; tip = TIP[ck] % s
            else:
                if s == "R":
                    continue
                c = ck; nm = en; tip = TIP[ck]
            add(nm, idx[names[c]], J[tip], np.array(binds[idx[names[c]]])[:3, :3])
    rig = Rig(name)
    rig.bones = bones; rig.parent = np.array(parent, int); rig.bind = np.array(binds, float)
    _mesh(rig, P, J, names)
    rig.meta = dict(source="procedurally generated sample (sforge.samplerigs) - synthetic, CC0", description=P.get("desc", ""),
                    hips_index=0, generator="samplerigs %s" % name)
    return rig


# ----------------------------------------------------------------- mesh
def _stripe_texture(c1, c2, num=None):
    im = Image.new("RGB", (64, 64), tuple(int(v * 255) for v in c1))
    dr = ImageDraw.Draw(im)
    for y in range(0, 64, 16):
        dr.rectangle([0, y, 63, y + 5], fill=tuple(int(v * 255) for v in c2))
    if num:
        dr.text((22, 24), num, fill=(255, 255, 255))
    return im.convert("RGBA")


def _mesh(rig, P, J, names):
    H = P["H"]; g = P["girth"]
    mats = [dict(name="skin", color=list(P["kit"]["skin"])), dict(name="shirt", color=[1, 1, 1], texture="textures/shirt.png"),
            dict(name="shorts", color=list(P["kit"]["shorts"])), dict(name="socks", color=list(P["kit"]["socks"])),
            dict(name="boots", color=[0.08, 0.08, 0.09]), dict(name="hair", color=list(P["kit"]["hair"])),
            dict(name="eye", color=[0.05, 0.05, 0.07])]
    MI = {m["name"]: i for i, m in enumerate(mats)}
    sh = P["kit"]["shirt"]
    rig.textures["textures/shirt.png"] = _stripe_texture(sh, tuple(min(1, c * 0.6 + 0.35) for c in sh))
    V, F, Jn, Wt, FM, UV = [], [], [], [], [], []
    bi = {b: i for i, b in enumerate(rig.bones)}

    def B(ck):
        return bi[names[ck]]

    def tube(a, b, r0, r1, bone, pbone, mat, sides=8, twist_bone=None, rings=(0.0, 0.25, 0.5, 0.75, 1.0)):
        a = np.asarray(a, float); b = np.asarray(b, float)
        d = b - a; L = np.linalg.norm(d); y = d / max(L, 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(y[2]) < 0.9 else np.array([1.0, 0, 0])
        x = np.cross(y, ref); x /= np.linalg.norm(x); z = np.cross(x, y)
        base = len(V)
        for k, u in enumerate(rings):
            r = r0 + (r1 - r0) * u
            for s_ in range(sides):
                th = 2 * math.pi * s_ / sides
                V.append(a + d * u + (x * math.cos(th) + z * math.sin(th)) * r)
                bb = twist_bone if (twist_bone is not None and u > 0.5) else bone
                if u == 0 and pbone is not None:
                    Jn.append([bb, pbone, 0, 0]); Wt.append([0.5, 0.5, 0, 0])
                elif u <= 0.25 and pbone is not None:
                    Jn.append([bb, pbone, 0, 0]); Wt.append([0.85, 0.15, 0, 0])
                else:
                    Jn.append([bb, 0, 0, 0]); Wt.append([1, 0, 0, 0])
        n = len(rings)
        for k in range(n - 1):
            for s_ in range(sides):
                a0 = base + k * sides + s_; a1 = base + k * sides + (s_ + 1) % sides
                b0 = a0 + sides; b1 = a1 + sides
                F.append([a0, a1, b1]); F.append([a0, b1, b0])
                for tri in ((a0, a1, b1), (a0, b1, b0)):
                    FM.append(MI[mat])
                    UV.append([[((t - base) % sides) / sides, ((t - base) // sides) / (n - 1)] for t in tri])
        # caps
        for k, sgn in ((0, -1), (n - 1, 1)):
            c = len(V); V.append(a + d * rings[k]); Jn.append(list(Jn[base + k * sides])); Wt.append(list(Wt[base + k * sides]))
            for s_ in range(sides):
                p0 = base + k * sides + s_; p1 = base + k * sides + (s_ + 1) % sides
                F.append([c, p1, p0] if sgn < 0 else [c, p0, p1]); FM.append(MI[mat]); UV.append([[0.5, 0.5]] * 3)

    def sphere(c, r, bone, lat=7, lon=10, hair_frac=0.45):
        base = len(V)
        for i in range(lat + 1):
            ph = math.pi * i / lat
            for j in range(lon):
                th = 2 * math.pi * j / lon
                V.append(c + r * np.array([math.sin(ph) * math.cos(th), math.cos(ph), math.sin(ph) * math.sin(th)]))
                Jn.append([bone, 0, 0, 0]); Wt.append([1, 0, 0, 0])
        for i in range(lat):
            for j in range(lon):
                a0 = base + i * lon + j; a1 = base + i * lon + (j + 1) % lon; b0 = a0 + lon; b1 = a1 + lon
                hair = i < lat * hair_frac or (i < lat * 0.75 and math.sin(2 * math.pi * (j + 0.5) / lon) < -0.3)
                for tri in ((a0, b1, a1), (a0, b0, b1)):
                    F.append(list(tri)); FM.append(MI["hair" if hair else "skin"]); UV.append([[0, 0]] * 3)

    def box(c0, c1, w, h, bone, mat):
        c0 = np.asarray(c0, float); c1 = np.asarray(c1, float)
        tube(c0, c1, w, w * 0.9, bone, None, mat, sides=4, rings=(0.0, 1.0))
    t = 0.055 * H * g
    tube(J["hips"] + [0, -0.06 * H, 0], J["spine"], t * 1.05, t, B("hips"), None, "shorts")
    tube(J["spine"], J["chest"], t, t * 0.95, B("spine"), B("hips"), "shirt")
    tube(J["chest"], J["upperchest"], t * 0.95, t * 1.1, B("chest"), B("spine"), "shirt")
    tube(J["upperchest"], J["neck"], t * 1.1, t * 0.7, B("upperchest"), B("chest"), "shirt")
    tube(J["neck"], J["head"], 0.025 * H * min(g, 1.2), 0.025 * H * min(g, 1.2), B("neck"), B("upperchest"), "skin", sides=6)
    hr = (H - J["head"][1]) * 0.5
    hc = J["head"] + np.array([0, hr, 0.01 * H])
    sphere(hc, hr, B("head"))
    for sx in (-1, 1):   # eyes
        e = hc + np.array([sx * hr * 0.35, hr * 0.05, hr * 0.93])
        box(e - [0, 0, 0.01 * hr], e + [0, 0, 0.12 * hr], hr * 0.12, hr * 0.12, B("head"), "eye")
    for s in ("L", "R"):
        tube(J["shoulder_" + s], J["upperarm_" + s], 0.03 * H * g, 0.032 * H * g, B("shoulder_" + s), B("upperchest"), "shirt", sides=6)
        tw = names.get("_twist_upperarm_" + s)
        tube(J["upperarm_" + s], J["forearm_" + s], 0.032 * H * g, 0.026 * H * g, B("upperarm_" + s), B("shoulder_" + s), "shirt",
             twist_bone=bi[tw] if tw else None)
        tube(J["forearm_" + s], J["hand_" + s], 0.025 * H * g, 0.019 * H * g, B("forearm_" + s), bi[tw] if tw else B("upperarm_" + s), "skin")
        tube(J["hand_" + s], J["handtip_" + s], 0.022 * H * g, 0.016 * H * g, B("hand_" + s), B("forearm_" + s), "skin", sides=4, rings=(0.0, 0.5, 1.0))
        tw = names.get("_twist_thigh_" + s)
        tube(J["thigh_" + s], J["shin_" + s], 0.05 * H * g, 0.04 * H * g, B("thigh_" + s), B("hips"), "shorts",
             twist_bone=bi[tw] if tw else None)
        tube(J["shin_" + s], J["foot_" + s], 0.036 * H * g, 0.026 * H * g, B("shin_" + s), bi[tw] if tw else B("thigh_" + s), "socks")
        f0 = J["foot_" + s] + np.array([0, -0.01 * H, -0.03 * H])
        tube(f0, J["toe_" + s] + [0, 0, 0], 0.028 * H * g, 0.026 * H * g, B("foot_" + s), B("shin_" + s), "boots", sides=4, rings=(0.0, 0.5, 1.0))
        tube(J["toe_" + s], J["toe_end_" + s], 0.024 * H * g, 0.02 * H * g, B("toe_" + s), B("foot_" + s), "boots", sides=4, rings=(0.0, 1.0))
    rig.V = np.array(V, float); rig.F = np.array(F, int)
    rig.J = np.array(Jn, int); rig.W = np.array(Wt, float)
    rig.fmat = np.array(FM, int); rig.fuv = np.array(UV, float)
    rig.materials = mats
    # feet on the floor
    rig.V[:, 1] -= min(0.0, rig.V[:, 1].min())


# ----------------------------------------------------------------- clips
STARTER_CLIPS = ["idle", "walk", "run", "jump", "kick", "punch", "celebrate"]


def new_motions():
    """new keyed clips for the animation-only sample (authored here, not from any capture)."""
    from .motions import Motion

    def wave(t):
        s = math.sin(2 * math.pi * 2 * t)
        return dict(arm_R=(20, 150, 0), elbow_R=40 + 35 * s, arm_L=(5, 8, 0), elbow_L=10, chest=(0, 0, 4), neck=(0, -10, 0))
    sq = [(0.0, {}), (0.45, dict(hips=(28, 0, 0), leg_L=(85, 6, 0), leg_R=(85, 6, 0), knee_L=110, knee_R=110, ankle_L=-15, ankle_R=-15,
                                  arm_L=(80, 5, 0), arm_R=(80, 5, 0), chest=(5, 0, 0))), (1.0, {})]
    hop = [(0.0, {}), (0.25, dict(leg_L=(30, 4, 0), leg_R=(30, 4, 0), knee_L=60, knee_R=60, arm_L=(-20, 10, 0), arm_R=(-20, 10, 0))),
           (0.5, dict(lift=0.35, leg_L=(10, 4, 0), leg_R=(10, 4, 0), knee_L=20, knee_R=20, arm_L=(30, 60, 0), arm_R=(30, 60, 0))),
           (0.75, dict(leg_L=(25, 4, 0), leg_R=(25, 4, 0), knee_L=50, knee_R=50)), (1.0, {})]
    bow = [(0.0, {}), (0.5, dict(hips=(45, 0, 0), leg_L=(45, 3, 0), leg_R=(45, 3, 0), spine=(10, 0, 0), neck=(10, 0, 0),
                                  arm_R=(60, -20, 0), elbow_R=90, arm_L=(-10, 5, 0))), (1.0, {})]   # leg = hips keeps the legs upright

    def spin(t):
        return dict(hips=(0, 360 * t, 0), arm_L=(0, 80, 0), arm_R=(0, 80, 0), leg_L=(0, 6, 0), leg_R=(0, 6, 0))
    return {"wave": Motion("wave", func=wave, loop=True), "squat": Motion("squat", keys=sq, loop=False),
            "hop": Motion("hop", keys=hop, loop=False), "bow": Motion("bow", keys=bow, loop=False),
            "spin": Motion("spin", func=spin, loop=True)}


def add_clips(rig, rec, clips=STARTER_CLIPS, mannequin=None):
    from . import rigrec as RR, retarget as RT
    m = mannequin or RR.from_mannequin(clips=list(clips))
    mrec = BM.detect(m)
    reps = []
    for c in clips:
        if c not in m.clips:
            continue
        cl, rp = RT.retarget(m, mrec, c, rig, rec)
        cl.source = "procedural motion '%s' (built-in, retargeted from the mannequin)" % c
        rig.clips[c] = cl; reps.append(rp)
    return reps


def moves_library():
    """animation-only sample: Mixamo-named skeleton (no mesh) carrying new clips."""
    from . import rigrec as RR, retarget as RT
    from . import motions as MO
    P = dict(PRESETS["sample_lanky"]); P.update(H=1.75, leg=0.53, head=0.13, arm=1.0, pose="T", girth=1.0)
    r = build("sample_moves", P)
    r.V = np.zeros((0, 3)); r.F = np.zeros((0, 3), int); r.J = np.zeros((0, 4), int); r.W = np.zeros((0, 4))
    r.fmat = np.zeros(0, int); r.fuv = None; r.materials = []; r.textures = {}
    rec = BM.detect(r)
    m = RR.from_mannequin(clips=[])
    mrec = BM.detect(m)
    for k, mot in new_motions().items():
        MO.LIB["_sample_" + k] = mot
        c = RR.motion_clip(m, "_sample_" + k, loop=mot.loop, duration=1.6 if k in ("wave", "spin") else 1.2)
        c.name = k
        cl, _ = RT.retarget(m, mrec, c, r, rec, name=k)
        cl.source = "new procedural clip '%s' (samplerigs.new_motions)" % k
        r.clips[k] = cl
        MO.LIB.pop("_sample_" + k, None)
    r.meta.update(description="animation-only: 1.75 m Mixamo-named skeleton with wave / squat / hop / bow / spin", hips_index=0)
    return r, rec
