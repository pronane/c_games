"""v7 exact material slots for game engines.

Every exported mannequin / library rig carries the four core slots
    Skin_Mat  Jersey_Mat  Shorts_Mat  Socks_Mat
plus optional extra named slots Trim_Mat, Hair_Mat, Shoes_Mat (and, for the mannequin's face detail,
Eye_Mat / EyeWhite_Mat / Mouth_Mat).  slots="core4" folds everything into the four core slots.

How faces are assigned:
  * materials whose names already say what they are (shirt/jersey/top, shorts/pants, socks, skin, hair, boots/shoes,
    trim ...) are renamed to the slot (texture and colour kept);
  * a mesh with ONE material (or only unrecognised names) is split ("auto"): each face goes to a slot by the
    canonical bone that dominates its vertices (bone map) and by its height as a fraction of the rest-pose bounding
    box: torso -> Jersey, thighs -> Shorts, shins -> Socks, feet -> Shoes, the rest (head, arms, hands, knees)
    -> Skin.  Without a skeleton only the height fractions are used.
Kits (home/away/... and library kits) recolour Jersey/Shorts/Socks/Trim; the sprite renderer uses the same
materials, so sprites and 3D match.
"""
from __future__ import annotations
import copy
import fnmatch
import numpy as np

CORE = ["Skin_Mat", "Jersey_Mat", "Shorts_Mat", "Socks_Mat"]
EXTRA = ["Trim_Mat", "Hair_Mat", "Shoes_Mat"]
DETAIL = ["Eye_Mat", "EyeWhite_Mat", "Mouth_Mat"]
ALL = CORE + EXTRA + DETAIL
# name -> slot (shell patterns, lower case; first match wins)
NAME_RULES = [("*jersey*|*shirt*|*top*|*torso_cloth*|*tshirt*|*vest*", "Jersey_Mat"),
              ("*short*|*pant*|*trouser*|*skirt*", "Shorts_Mat"),
              ("*sock*|*stocking*", "Socks_Mat"),
              ("*trim*|*accent*|*stripe*", "Trim_Mat"),
              ("*hair*|*eyebrow*|*eyelash*|*beard*", "Hair_Mat"),
              ("*shoe*|*boot*|*sneaker*|*cleat*|*foot*wear*", "Shoes_Mat"),
              ("eye_white|*sclera*", "EyeWhite_Mat"),
              ("eye|*eye_l*|*eye_r*|*iris*|*pupil*", "Eye_Mat"),
              ("*mouth*|*teeth*|*tongue*|*lip*", "Mouth_Mat"),
              ("*skin*|*body*|*head*|*face*|*arm*|*hand*|*leg*", "Skin_Mat")]
FOLD_CORE4 = {"Trim_Mat": "Jersey_Mat", "Hair_Mat": "Skin_Mat", "Shoes_Mat": "Skin_Mat", "Eye_Mat": "Skin_Mat",
              "EyeWhite_Mat": "Skin_Mat", "Mouth_Mat": "Skin_Mat", "Teeth_Mat": "Skin_Mat",
              "JerseyPattern_Mat": "Jersey_Mat", "Accessory_Mat": "Jersey_Mat", "Accessory2_Mat": "Jersey_Mat",
              "Emissive_Mat": "Jersey_Mat"}
# default colours for slots created by an auto split of an untextured single material
DEFAULT_COL = {"Skin_Mat": [0.80, 0.62, 0.50], "Jersey_Mat": [0.10, 0.40, 0.18], "Shorts_Mat": [0.93, 0.93, 0.93],
               "Socks_Mat": [0.10, 0.40, 0.18], "Shoes_Mat": [0.12, 0.12, 0.12], "Trim_Mat": [0.95, 0.95, 0.95],
               "Hair_Mat": [0.20, 0.13, 0.08]}
# bounding-box height fractions (0 = soles, 1 = top of head) used when there is no skeleton
FRAC = dict(shoes=0.045, socks=0.27, knee=0.30, shorts=0.52, jersey=0.82)


def slot_for_name(name):
    n = (name or "").lower().strip()
    if n in [s.lower() for s in ALL]:
        return next(s for s in ALL if s.lower() == n)
    for pats, slot in NAME_RULES:
        if any(fnmatch.fnmatchcase(n, p) for p in pats.split("|")):
            return slot
    return None


def _canon_of_vertex(rig, rec):
    """canonical region name per vertex (dominant skin bone, walked up to the nearest mapped ancestor)."""
    if rec is None or not len(rig.J):
        return None
    inv = {}
    for k, b in rec.get("map", {}).items():
        if b in rig.bones:
            inv[rig.index(b)] = k
    lab = []
    for i in range(rig.nb):
        j = i
        while j >= 0 and j not in inv:
            j = int(rig.parent[j])
        lab.append(inv.get(j, ""))
    dom = rig.J[np.arange(len(rig.J)), np.argmax(rig.W, axis=1)]
    return np.array(lab, object)[dom]


def auto_assign(rig, rec=None, shoes=True):
    """slot name per face from bone regions + rest-pose height fractions."""
    V = rig.V; F = rig.F
    c = V[F].mean(axis=1)
    y0, y1 = float(V[:, 1].min()), float(V[:, 1].max()); H = max(1e-6, y1 - y0)
    h = (c[:, 1] - y0) / H
    reg = _canon_of_vertex(rig, rec)
    fr = dict(FRAC)
    if reg is not None and rec is not None:
        # refine the fractions from the skeleton (knee, ankle, hip joints)
        def by(k):
            b = rec["map"].get(k)
            return None if b not in rig.bones else (rig.bind[rig.index(b), 1, 3] - y0) / H
        knee = [x for x in (by("shin_L"), by("shin_R")) if x is not None]
        hip = [x for x in (by("thigh_L"), by("thigh_R")) if x is not None]
        ank = [x for x in (by("foot_L"), by("foot_R")) if x is not None]
        if knee:
            fr["knee"] = float(np.mean(knee)); fr["socks"] = fr["knee"] - 0.035
        if hip:
            fr["shorts"] = float(np.mean(hip)) + 0.04
        if ank:
            fr["shoes"] = max(0.02, float(np.mean(ank)) * 0.75)
    out = np.array(["Skin_Mat"] * len(F), object)
    if reg is None:
        out[h < fr["jersey"]] = "Jersey_Mat"
        out[h < fr["shorts"]] = "Shorts_Mat"
        out[h < fr["knee"]] = "Skin_Mat"
        out[h < fr["socks"]] = "Socks_Mat"
        if shoes:
            out[h < fr["shoes"]] = "Shoes_Mat"
        return out, fr
    rf = np.array([reg[f] for f in F[:, 0]], object)          # region of the face's first vertex (rigid enough)
    vr = reg[F]                                                # majority vote of the 3 vertices
    for k in range(len(F)):
        a, b, cc = vr[k]
        rf[k] = a if (a == b or a == cc) else (b if b == cc else a)
    base = np.array([r[:-2] if r[-2:] in ("_L", "_R") else r for r in rf], object)
    torso = np.isin(base, ["hips", "spine", "chest", "upperchest", "root", "shoulder"])
    out[torso & (h >= fr["shorts"])] = "Jersey_Mat"
    out[torso & (h < fr["shorts"])] = "Shorts_Mat"
    # short sleeves: the upper half of the upper arm
    ua = base == "upperarm"
    if ua.any():
        for s in ("L", "R"):
            b0 = rec["map"].get("upperarm_" + s); b1 = rec["map"].get("forearm_" + s)
            if b0 in rig.bones and b1 in rig.bones:
                p0 = rig.bind[rig.index(b0), :3, 3]; p1 = rig.bind[rig.index(b1), :3, 3]
                d = p1 - p0; t = ((c - p0) @ d) / max(1e-9, d @ d)
                out[(rf == "upperarm_" + s) & (t < 0.5)] = "Jersey_Mat"
    out[(base == "thigh") & (h >= fr["knee"])] = "Shorts_Mat"
    out[(base == "thigh") & (h < fr["knee"]) & (h < fr["socks"])] = "Socks_Mat"
    out[(base == "shin") & (h < fr["socks"])] = "Socks_Mat"
    feet = np.isin(base, ["foot", "toe"])
    out[feet] = "Shoes_Mat" if shoes else "Socks_Mat"
    if shoes:
        out[(base == "shin") & (h < fr["shoes"])] = "Shoes_Mat"
    return out, fr


def apply(rig, rec=None, split="auto", slots="full", log=None):
    """-> new Rig whose materials are exactly the named slots.  split: auto | off ('off' only renames
    recognisable names, unknown materials keep their names).  slots: full | core4."""
    log = log or (lambda s: None)
    r = copy.deepcopy(rig); r._tri_cache = {}
    rep = {"split": split, "slots": slots, "renamed": {}, "auto_split": False}
    if not r.has_mesh():
        return r, rep
    mats = r.materials or [dict(name="Material", color=[0.7, 0.7, 0.7])]
    names = [slot_for_name(m.get("name", "")) for m in mats]
    used = sorted(set(int(x) for x in np.unique(r.fmat))) if len(r.fmat) else [0]
    unknown_used = [i for i in used if names[i] is None]
    need_split = split == "auto" and (len(used) == 1 or len(unknown_used) == len(used))
    if need_split:
        src_mi = r.fmat.copy()
        face_slot, fr = auto_assign(r, rec)
        rep.update(auto_split=True, fractions={k: round(v, 3) for k, v in fr.items()})
        new_mats, idx = [], {}
        fm = np.zeros(len(r.F), int)
        for k in range(len(r.F)):
            s = face_slot[k]
            if slots == "core4":
                s = FOLD_CORE4.get(s, s)
            key = (s, int(src_mi[k]))
            if s not in idx:
                base = dict(mats[int(src_mi[k])])
                if not base.get("texture") and r.fcol is None:
                    base["color"] = DEFAULT_COL.get(s, base.get("color", [0.7, 0.7, 0.7]))
                base["name"] = s; base["source_material"] = mats[int(src_mi[k])].get("name", "")
                idx[s] = len(new_mats); new_mats.append(base)
            fm[k] = idx[s]
        order = sorted(range(len(new_mats)), key=lambda i: ALL.index(new_mats[i]["name"]) if new_mats[i]["name"] in ALL else 99)
        new_mats = [new_mats[i] for i in order]
        fm = np.argsort(order)[fm]
        r.materials, r.fmat = new_mats, fm
        log("  material slots: auto-split %d faces of '%s' into %s" % (len(r.F), mats[used[0]].get("name", ""),
            ", ".join("%s %d" % (m["name"], int((fm == i).sum())) for i, m in enumerate(new_mats))))
    else:
        # rename recognisable materials; merge materials mapping to the same slot
        new_mats, idx, remap = [], {}, {}
        for i, m in enumerate(mats):
            s = names[i] or m.get("name", "Material_%d" % i)
            if slots == "core4":
                s = FOLD_CORE4.get(s, s if s in CORE else "Skin_Mat")
            if s != m.get("name"):
                rep["renamed"][m.get("name", "")] = s
            if s in idx and not (m.get("texture") and m.get("texture") != new_mats[idx[s]].get("texture")):
                remap[i] = idx[s]; continue
            if s in idx:                                   # same slot, different texture: keep both, suffix
                s2 = s; n = 1
                while s2 in idx:
                    n += 1; s2 = "%s_%d" % (s, n)
                s = s2
            m2 = dict(m); m2["name"] = s; m2.setdefault("source_material", m.get("name", ""))
            idx[s] = len(new_mats); remap[i] = idx[s]; new_mats.append(m2)
        r.fmat = np.array([remap.get(int(x), 0) for x in r.fmat], int)
        r.materials = new_mats
        if rep["renamed"]:
            log("  material slots: " + ", ".join("%s->%s" % kv for kv in rep["renamed"].items()))
    # the four core slots always exist (an empty slot is kept as a named material for the engine)
    have = {m["name"] for m in r.materials}
    for s in CORE:
        if s not in have:
            r.materials.append(dict(name=s, color=DEFAULT_COL[s], empty=True))
    rep["materials"] = [m["name"] for m in r.materials]
    r.meta["material_slots"] = rep
    return r, rep


MANNEQUIN_SLOT = {"skin": "Skin_Mat", "shirt": "Jersey_Mat", "shorts": "Shorts_Mat", "socks": "Socks_Mat",
                  "trim": "Trim_Mat", "boots": "Shoes_Mat", "hair": "Hair_Mat", "eye": "Eye_Mat",
                  "eye_white": "EyeWhite_Mat", "mouth": "Mouth_Mat", "teeth": "Teeth_Mat",
                  "pattern": "JerseyPattern_Mat", "accessory": "Accessory_Mat", "accessory2": "Accessory2_Mat",
                  "emissive": "Emissive_Mat", "eyelid": "Skin_Mat", "brow": "Hair_Mat"}


def mannequin_name(mat, slots="full"):
    if slots in ("parts", "keep"):
        return mat                     # pre-v7 part names (skin, shirt, ...)
    s = MANNEQUIN_SLOT.get(mat)
    if s is None:
        return mat                     # ball / kart parts are props, not body slots
    return FOLD_CORE4.get(s, s) if slots == "core4" else s
