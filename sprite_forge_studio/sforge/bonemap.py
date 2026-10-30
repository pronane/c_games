"""Bone naming detection and the canonical humanoid bone map (v6).

Canonical names (= the built-in mannequin's names, plus optional extras):
  root hips spine chest upperchest neck head
  shoulder_L upperarm_L forearm_L hand_L     (and _R)
  thigh_L shin_L foot_L toe_L                (and _R)
Detected conventions: mixamo (also Meshy), unity (humanoid avatar names), rigify (DEF-/ORG-/metarig), unreal (UE4/UE5), makehuman (v7), sforge, generic
(keywords + left/right tokens + a structural fallback).  Stored per rig as editable bonemap.json:
  {"convention": "mixamo", "map": {"hips": "mixamorig:Hips", ...}, "unmapped": [...], "missing": [...], "edited": false}
"""
from __future__ import annotations
import json
import re
import numpy as np

SIDES = ("L", "R")
CORE = ["root", "hips", "spine", "chest", "upperchest", "neck", "head"]
LIMBS = ["shoulder", "upperarm", "forearm", "hand", "thigh", "shin", "foot", "toe"]
CANON = CORE + ["%s_%s" % (l, s) for s in SIDES for l in LIMBS]
REQUIRED = ["hips", "spine", "head", "upperarm_L", "forearm_L", "hand_L", "upperarm_R", "forearm_R", "hand_R",
            "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
# canonical child used for the bone direction (first one present wins)
CHILD = {"hips": ["spine", "chest", "neck"], "spine": ["chest", "upperchest", "neck"], "chest": ["upperchest", "neck", "head"],
         "upperchest": ["neck", "head"], "neck": ["head"], "root": [],
         "shoulder_%s": ["upperarm_%s"], "upperarm_%s": ["forearm_%s"], "forearm_%s": ["hand_%s"],
         "thigh_%s": ["shin_%s"], "shin_%s": ["foot_%s"], "foot_%s": ["toe_%s"]}
PARENT_CANON = {"hips": "root", "spine": "hips", "chest": "spine", "upperchest": "chest", "neck": "upperchest", "head": "neck",
                "shoulder_%s": "upperchest", "upperarm_%s": "shoulder_%s", "forearm_%s": "upperarm_%s", "hand_%s": "forearm_%s",
                "thigh_%s": "hips", "shin_%s": "thigh_%s", "foot_%s": "shin_%s", "toe_%s": "foot_%s"}


def child_candidates(c):
    if c[-2:] in ("_L", "_R"):
        s = c[-1]; base = c[:-1] + "%s"
        return [x % s for x in CHILD.get(base, [])]
    return CHILD.get(c, [])


def canon_parent(c, m):
    """nearest mapped canonical ancestor of c."""
    while True:
        if c[-2:] in ("_L", "_R"):
            s = c[-1]; p = PARENT_CANON.get(c[:-1] + "%s")
            p = p % s if p and "%s" in p else p
        else:
            p = PARENT_CANON.get(c)
        if not p:
            return None
        if p in m:
            return p
        c = p


def _strip(name):
    n = name.split("|")[-1]
    n = re.sub(r"^.*:", "", n)           # namespaces: mixamorig:, mixamorig1:, Character1:
    return n


def _side_table(left, right, rows):
    out = {}
    for canon, pats in rows:
        if "%s" in canon:
            out[canon % "L"] = [p.replace("{S}", left) for p in pats]
            out[canon % "R"] = [p.replace("{S}", right) for p in pats]
        else:
            out[canon] = pats
    return out


CONVENTIONS = {
    "mixamo": _side_table("Left", "Right", [
        ("hips", ["hips"]), ("spine", ["spine"]), ("chest", ["spine1"]), ("upperchest", ["spine2"]), ("neck", ["neck"]),
        ("head", ["head"]), ("shoulder_%s", ["{S}shoulder"]), ("upperarm_%s", ["{S}arm"]), ("forearm_%s", ["{S}forearm"]),
        ("hand_%s", ["{S}hand"]), ("thigh_%s", ["{S}upleg"]), ("shin_%s", ["{S}leg"]), ("foot_%s", ["{S}foot"]), ("toe_%s", ["{S}toebase"])]),
    "unity": _side_table("Left", "Right", [
        ("hips", ["hips"]), ("spine", ["spine"]), ("chest", ["chest"]), ("upperchest", ["upperchest"]), ("neck", ["neck"]),
        ("head", ["head"]), ("shoulder_%s", ["{S}shoulder"]), ("upperarm_%s", ["{S}upperarm"]), ("forearm_%s", ["{S}lowerarm"]),
        ("hand_%s", ["{S}hand"]), ("thigh_%s", ["{S}upperleg"]), ("shin_%s", ["{S}lowerleg"]), ("foot_%s", ["{S}foot"]), ("toe_%s", ["{S}toes"])]),
    "rigify": _side_table("l", "r", [
        ("hips", ["(def|org)?-?spine", "hips", "pelvis"]), ("spine", ["(def|org)?-?spine\\.001", "spine"]),
        ("chest", ["(def|org)?-?spine\\.002", "chest"]), ("upperchest", ["(def|org)?-?spine\\.003", "upper_chest"]),
        ("neck", ["(def|org)?-?spine\\.004", "neck"]), ("head", ["(def|org)?-?spine\\.006", "head"]),
        ("shoulder_%s", ["(def|org)?-?shoulder[._]{S}"]), ("upperarm_%s", ["(def|org)?-?upper_arm[._]{S}"]),
        ("forearm_%s", ["(def|org)?-?forearm[._]{S}"]), ("hand_%s", ["(def|org)?-?hand[._]{S}"]),
        ("thigh_%s", ["(def|org)?-?thigh[._]{S}"]), ("shin_%s", ["(def|org)?-?shin[._]{S}"]),
        ("foot_%s", ["(def|org)?-?foot[._]{S}"]), ("toe_%s", ["(def|org)?-?toe[._]{S}"])]),
    "unreal": _side_table("l", "r", [
        ("root", ["root"]), ("hips", ["pelvis"]), ("spine", ["spine_01"]), ("chest", ["spine_02"]), ("upperchest", ["spine_03"]),
        ("neck", ["neck_01"]), ("head", ["head"]), ("shoulder_%s", ["clavicle_{S}"]), ("upperarm_%s", ["upperarm_{S}"]),
        ("forearm_%s", ["lowerarm_{S}"]), ("hand_%s", ["hand_{S}"]), ("thigh_%s", ["thigh_{S}"]), ("shin_%s", ["calf_{S}"]),
        ("foot_%s", ["foot_{S}"]), ("toe_%s", ["ball_{S}"])]),
    "makehuman": _side_table("l", "r", [
        ("hips", ["root"]), ("spine", ["spine04"]), ("chest", ["spine03"]), ("upperchest", ["spine02"]), ("neck", ["neck01"]),
        ("head", ["head"]), ("shoulder_%s", ["clavicle\\.{S}"]), ("upperarm_%s", ["upperarm01\\.{S}"]),
        ("forearm_%s", ["lowerarm01\\.{S}"]), ("hand_%s", ["wrist\\.{S}"]), ("thigh_%s", ["upperleg01\\.{S}"]),
        ("shin_%s", ["lowerleg01\\.{S}"]), ("foot_%s", ["foot\\.{S}"]), ("toe_%s", ["toe3-1\\.{S}", "toe1-1\\.{S}"])]),
    "sforge": {c: [re.escape(c.lower())] for c in CANON},
}
SKIP = re.compile(r"(twist|roll|_ik|ik_|\bik\b|pole|target|helper|_end$|end$|nub|mch|ctrl|wgt|tweak|_jnt_end|hairbone|breast|jaw|eye|finger|thumb|index|middle|ring|pinky|cheek|lip|brow|tongue|tooth|teeth|ear|pinkie|wing|tail|prop|weapon)", re.I)


def detect_convention(bones):
    scores = {}
    stripped = [_strip(b).lower() for b in bones]
    for conv, tab in CONVENTIONS.items():
        m = {}
        for canon, pats in tab.items():
            for p in pats:
                rx = re.compile("^(?:%s)$" % p, re.I)
                hit = next((bones[i] for i, s in enumerate(stripped) if rx.match(s) and bones[i] not in m.values()), None)
                if hit:
                    m[canon] = hit; break
        bonus = 0
        if conv == "mixamo" and any(b.lower().startswith("mixamorig") for b in bones):
            bonus = 5
        if conv == "rigify" and any(b.upper().startswith(("DEF-", "ORG-")) for b in bones):
            bonus = 5
        if conv == "rigify" and not any(re.search(r"[._][lr]$", s) for s in stripped):
            bonus = -10
        scores[conv] = (len(m) + bonus, m)
    best = max(scores, key=lambda k: scores[k][0])
    return best, scores[best][1], {k: v[0] for k, v in scores.items()}


def _side_of(n):
    s = n.lower()
    if re.search(r"(^|[^a-z])(left|l)([^a-z]|$)|[._\- ]l$|^l[._\-]|left", s):
        return "L"
    if re.search(r"(^|[^a-z])(right|r)([^a-z]|$)|[._\- ]r$|^r[._\-]|right", s):
        return "R"
    return None


GENERIC = [("hips", r"pelvis|hips?\b|hip$|^hips|root_?hips|cog"), ("upperchest", r"upper_?chest|spine_?0?3|spine3"),
           ("chest", r"chest|thorax|ribcage|spine_?0?2|spine2|spine1"), ("spine", r"spine|abdomen|waist|torso"),
           ("neck", r"neck"), ("head", r"head"),
           ("shoulder", r"clavicle|shoulder|collar"), ("forearm", r"fore_?arm|lower_?arm|elbow|lowarm|radius"),
           ("upperarm", r"upper_?arm|up_?arm|humerus|^arm|[^a-z]arm"), ("hand", r"hand|wrist|palm"),
           ("thigh", r"thigh|upper_?leg|up_?leg|femur|upleg"), ("shin", r"shin|calf|knee|lower_?leg|low_?leg|^leg|[^a-z]leg"),
           ("foot", r"foot|ankle"), ("toe", r"toe|ball")]


def generic_map(rig, m=None):
    m = dict(m or {})
    used = set(m.values())
    for canon, pat in GENERIC:
        rx = re.compile(pat, re.I)
        for i in rig.order():
            b = rig.bones[i]
            if b in used or SKIP.search(_strip(b)):
                continue
            s = _strip(b)
            if not rx.search(s):
                continue
            if canon in CORE:
                if _side_of(s) or canon in m:
                    continue
                key = canon
            else:
                sd = _side_of(s)
                if not sd:
                    x = rig.bind[i, 0, 3]
                    if abs(x) < 0.02:
                        continue
                    sd = "L" if x > 0 else "R"
                key = "%s_%s" % (canon, sd)
                if key in m:
                    continue
            m[key] = b; used.add(b)
    return structural(rig, m)


def structural(rig, m):
    """fill gaps from the hierarchy: legs = two downward chains from hips, arms = sideways chains from the chest."""
    used = set(m.values())
    idx = {b: i for i, b in enumerate(rig.bones)}
    P = rig.bind[:, :3, 3]
    def chain(i, n):
        out = [i]
        while len(out) < n:
            ch = [c for c in rig.children(out[-1]) if rig.bones[c] not in used and not SKIP.search(rig.bones[c])]
            if not ch:
                break
            out.append(max(ch, key=lambda c: len(_desc(rig, c))))
        return out
    if "hips" not in m:
        cand = [i for i in range(rig.nb) if len(rig.children(i)) >= 3]
        if cand:
            h = max(cand, key=lambda i: len(_desc(rig, i)) - abs(P[i, 1] - 0.53 * max(1e-3, P[:, 1].max())))
            m["hips"] = rig.bones[h]; used.add(rig.bones[h])
    if "hips" in m:
        h = idx[m["hips"]]
        for c in rig.children(h):
            if rig.bones[c] in used:
                continue
            d = P[c] - P[h]
            ch = chain(c, 4)
            low = P[ch[-1]]
            if low[1] < P[h, 1] - 0.2 * max(0.1, P[h, 1]) and abs(P[c, 0]) > 1e-3:
                s = "L" if P[c, 0] > 0 else "R"
                for nm, j in zip(["thigh", "shin", "foot", "toe"], ch):
                    k = "%s_%s" % (nm, s)
                    if k not in m:
                        m[k] = rig.bones[j]; used.add(rig.bones[j])
            elif "spine" not in m and d[1] > 0:
                m["spine"] = rig.bones[c]; used.add(rig.bones[c])
    return m


def _desc(rig, i):
    out, st = [], [i]
    while st:
        k = st.pop(); out.append(k); st += rig.children(k)
    return out


def detect(rig):
    conv, m, scores = detect_convention(rig.bones)
    m = generic_map(rig, m) if len(m) < len(REQUIRED) else m
    if conv == "sforge" and len(m) < 10:
        conv = "generic"
    if scores.get(conv, 0) < 6:
        conv = "generic"
    return make_record(rig, conv, m)


def make_record(rig, conv, m, edited=False):
    m = {k: v for k, v in m.items() if v in rig.bones}
    mapped = set(m.values())
    return dict(convention=conv, map={k: m[k] for k in CANON if k in m},
                unmapped=[b for b in rig.bones if b not in mapped],
                missing=[k for k in REQUIRED if k not in m], edited=edited)


def save(rec, path):
    json.dump(rec, open(path, "w", encoding="utf-8"), indent=1)


def load(path, rig=None):
    rec = json.load(open(path, encoding="utf-8"))
    if rig is not None:
        rec = make_record(rig, rec.get("convention", "custom"), rec.get("map", {}), rec.get("edited", False))
    return rec


def index_map(rig, rec):
    return {c: rig.index(b) for c, b in rec["map"].items() if rig.index(b) >= 0}


# ----------------------------------------------------------------- orientation / scale normalisation
def _snap_axis(v):
    a = int(np.argmax(np.abs(v)))
    e = np.zeros(3); e[a] = np.sign(v[a]) or 1
    return e


def orient(rig, rec, report):
    """make the rig stand on +Y, face +Z (its left = +X), metres, feet on the ground."""
    from .rigrec import rot_between, m4
    from .rigrec import mats_from_quat  # noqa
    im = index_map(rig, rec)
    P = rig.bind[:, :3, 3]
    up = None
    if "head" in im and "hips" in im:
        up = P[im["head"]] - P[im["hips"]]
    elif rig.has_mesh():
        ext = rig.V.max(0) - rig.V.min(0); up = np.eye(3)[int(np.argmax(ext))]
    if up is not None and np.linalg.norm(up) > 1e-9:
        e = _snap_axis(up)
        if e[1] < 0.5:
            R = rot_between(e, [0, 1, 0])
            rig.apply_global(m4(R)); report.setdefault("fixes", []).append("rotated so the head points up (+Y)")
            P = rig.bind[:, :3, 3]
    lr = None
    for a, b in (("thigh_L", "thigh_R"), ("upperarm_L", "upperarm_R"), ("shoulder_L", "shoulder_R"), ("foot_L", "foot_R")):
        if a in im and b in im:
            lr = P[im[a]] - P[im[b]]; break
    if lr is not None:
        lr[1] = 0
        if np.linalg.norm(lr) > 1e-6:
            ang = np.degrees(np.arctan2(-lr[2], lr[0]))        # rotation about +Y taking lr onto +X
            snap = round(ang / 90.0) * 90.0
            if abs(ang - snap) < 12:
                ang = snap
            if abs(ang) > 0.5:
                from .mathutil import ry
                rig.apply_global(m4(ry(-ang)))
                P2 = rig.bind[:, :3, 3]
                if (P2[im[a]] - P2[im[b]])[0] < 0:          # safety: wrong rotation sense -> turn round
                    rig.apply_global(m4(ry(180.0)))
                report.setdefault("fixes", []).append("turned %.0f deg about Y so the character faces +Z" % ang)
    h = rig.height()
    if h > 20:
        rig.apply_global(np.diag([0.01, 0.01, 0.01, 1])); report.setdefault("fixes", []).append("height %.1f m looked like centimetres: scaled x0.01" % h)
    elif 0 < h < 0.05:
        rig.apply_global(np.diag([100.0, 100.0, 100.0, 1])); report.setdefault("fixes", []).append("height %.3f m looked like a unit error: scaled x100" % h)
    rig.meta["hips_index"] = im.get("hips", 0)
    rig.ground()


def leg_length(rig, rec):
    im = index_map(rig, rec)
    P = rig.bind[:, :3, 3]
    if "hips" in im:
        feet = [P[im[k]][1] for k in ("foot_L", "foot_R") if k in im]
        return float(P[im["hips"]][1] - (min(feet) if feet else 0.0))
    return rig.height() * 0.5
