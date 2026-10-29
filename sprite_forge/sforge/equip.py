"""v7 Equip: outfits (skinned clothes / armour) and props (rigid items on sockets) merged onto a base rig.

Library kinds (forge.py library add FILE --kind outfit|prop):
  outfits/<name>   a mesh skinned to ANY humanoid skeleton (Mixamo, UE5, Unity, MakeHuman, sforge ...).  At build time
                   its bones are matched through the canonical bone map, its rest shape is fitted onto the base rig bone
                   by bone (direction + length of every canonical segment), and its skin weights are moved onto the
                   base rig's bones - so it deforms with every animation, in sprites and in model.glb / model.fbx.
                   meta: hide = body regions to mask under it (torso, hips, arms, upperarms, forearms, hands, legs,
                   thighs, shins, feet, head, neck) and slot = material slot it belongs to (Jersey, Shorts, Socks,
                   Shoes, Trim, Hair or a custom name like Armour -> Armour_Mat).
  props/<name>     (meta prop.fit: none | height = scale with the base height / 1.8 m | head = fit the head width)
                   a rigid mesh (sword, shield, hat, backpack ...).  Authoring convention: the item stands upright
                   (+Y), front +Z, and the grip / attachment point is the bottom centre (that is where library add puts
                   the origin).  It is skinned 100 % to one socket bone of the base rig:
                   hand_r hand_l head back hip foot_r foot_l (foot = foot_r).
Build config (forge.py build --outfit NAME --prop NAME[@SOCKET][:ox,oy,oz[:rx,ry,rz[:scale]]] --slot-color SLOT=#hex):
  every part's licence is copied into build_report.json["parts"].
No new bones are added, so the animation files, retargeted clips and console exports keep the base skeleton.
"""
from __future__ import annotations
import copy
import re
import numpy as np

from . import bonemap as BM
from .rigrec import rot_between, m4

SOCKET_BONE = {"hand_r": "hand_R", "hand_l": "hand_L", "head": "head", "back": "upperchest", "hip": "hips",
               "foot_r": "foot_R", "foot_l": "foot_L", "foot": "foot_R"}
SOCKET_FALLBACK = {"upperchest": ["chest", "spine"], "hand_R": ["forearm_R"], "hand_L": ["forearm_L"]}
# default placement of an upright item per socket: rotation (deg XYZ) - blades point forward from a hand, items on
# the hip hang down
SOCKET_ROT = {"hand_r": (90, 0, 0), "hand_l": (90, 0, 0), "hip": (180, 0, 0)}
REGIONS = {
    "torso": ["spine", "chest", "upperchest"], "hips": ["hips"], "neck": ["neck"], "head": ["head"],
    "shoulders": ["shoulder_L", "shoulder_R"],
    "upperarms": ["upperarm_L", "upperarm_R"], "forearms": ["forearm_L", "forearm_R"], "hands": ["hand_L", "hand_R"],
    "thighs": ["thigh_L", "thigh_R"], "shins": ["shin_L", "shin_R"], "feet": ["foot_L", "foot_R", "toe_L", "toe_R"],
}
REGIONS["arms"] = REGIONS["shoulders"] + REGIONS["upperarms"] + REGIONS["forearms"]
REGIONS["legs"] = REGIONS["thighs"] + REGIONS["shins"]
REGIONS["body"] = REGIONS["torso"] + REGIONS["hips"]
REGION_ALIASES = {"shoulder": "shoulders", "upperarm": "upperarms", "forearm": "forearms", "hand": "hands", "thigh": "thighs",
                  "shin": "shins", "foot": "feet", "arm": "arms", "leg": "legs", "chest": "torso", "pelvis": "hips"}


def region_name(r):
    r = r.strip().lower()
    return REGION_ALIASES.get(r, r)


def _canon_of(rig, rec):
    """bone index -> canonical name (nearest mapped ancestor for unmapped bones)."""
    inv = {}
    for c, b in rec.get("map", {}).items():
        i = rig.index(b)
        if i >= 0:
            inv[i] = c
    out = {}
    for i in range(rig.nb):
        j = i
        while j >= 0 and j not in inv:
            j = rig.parent[j]
        out[i] = inv.get(j, "hips")
    return out


def _seg(rig, rec, c):
    """(head, tail or None) world rest positions of canonical bone c."""
    m = rec.get("map", {})
    i = rig.index(m.get(c, ""))
    if i < 0:
        return None, None
    h = rig.bind[i, :3, 3]
    for ch in BM.child_candidates(c):
        j = rig.index(m.get(ch, ""))
        if j >= 0:
            return h, rig.bind[j, :3, 3]
    return h, None


def skel_height(rig, rec):
    """height from the skeleton (head joint - lowest foot joint), so a partial outfit mesh does not skew it."""
    m = rec.get("map", {})
    ys = [rig.bind[rig.index(m[c]), 1, 3] for c in ("foot_L", "foot_R", "toe_L", "toe_R") if rig.index(m.get(c, "")) >= 0]
    h = rig.index(m.get("head", ""))
    if h >= 0 and ys:
        return max(1e-6, rig.bind[h, 1, 3] - min(ys))
    return max(1e-6, float(np.ptp(rig.bind[:, 1, 3])))


def fit_rest(src, srec, dst, drec):
    """outfit rest vertices -> base rig rest space, canonical segment by segment (LBS of per-segment similarities)."""
    k = skel_height(dst, drec) / skel_height(src, srec)
    can = _canon_of(src, srec)
    cache = {}

    def T(c):
        if c in cache:
            return cache[c]
        hs, ts = _seg(src, srec, c); ht, tt = _seg(dst, drec, c)
        if hs is None or ht is None:
            M = np.eye(4); M[:3, :3] *= k
            # keep it near the base hips when the bone is missing on one side
            hs0, _ = _seg(src, srec, "hips"); ht0, _ = _seg(dst, drec, "hips")
            if hs0 is not None and ht0 is not None:
                M[:3, 3] = ht0 - k * hs0
        elif ts is None or tt is None:
            M = np.eye(4); M[:3, :3] *= k; M[:3, 3] = ht - k * hs
        else:
            ds, dt = ts - hs, tt - ht
            ls, lt = np.linalg.norm(ds), np.linalg.norm(dt)
            s = ds / max(ls, 1e-9)
            A = k * np.eye(3) + (lt / max(ls, 1e-9) - k) * np.outer(s, s)      # axial: length ratio, lateral: height ratio
            R = rot_between(ds, dt)
            L = R @ A
            M = np.eye(4); M[:3, :3] = L; M[:3, 3] = ht - L @ hs
        cache[c] = M
        return M
    Vh = np.c_[src.V, np.ones(len(src.V))]
    out = np.zeros((len(src.V), 3))
    for kk in range(4):
        w = src.W[:, kk]
        if not np.any(w):
            continue
        Ms = np.array([T(can[int(b)]) for b in range(src.nb)])
        M = Ms[src.J[:, kk]]
        out += w[:, None] * np.einsum("nij,nj->ni", M[:, :3, :], Vh)
    ws = src.W.sum(1)
    out[ws < 1e-9] = (Vh[ws < 1e-9] @ T("hips").T)[:, :3]
    return out


def remap_weights(src, srec, dst, drec):
    """outfit bone indices -> base rig bone indices (same name, else canonical, else nearest canonical ancestor)."""
    can = _canon_of(src, srec)
    dm = drec.get("map", {})
    hips = dst.index(dm.get("hips", "")) if dm.get("hips") else 0
    lut = np.zeros(src.nb, int)
    for i, b in enumerate(src.bones):
        j = dst.index(b)
        if j < 0:
            c = can[i]
            while c and dst.index(dm.get(c, "")) < 0:
                c = BM.canon_parent(c, dm) if BM.canon_parent(c, dm) != c else None
            j = dst.index(dm.get(c, "")) if c else -1
        lut[i] = j if j >= 0 else max(hips, 0)
    return lut[src.J]


def _merge(dst, V, F, J, W, fmat_names, fuv, fcol, mats, textures):
    """append geometry to dst; materials are matched by name (so slot names merge)."""
    names = [m.get("name") for m in dst.materials]
    remap = []
    for m in mats:
        if m.get("name") in names:
            remap.append(names.index(m["name"]))
        else:
            dst.materials.append(copy.deepcopy(m)); names.append(m.get("name")); remap.append(len(dst.materials) - 1)
    remap = np.array(remap or [0], int)
    n0 = len(dst.V); f0 = len(dst.F)
    nf = len(F)
    if dst.fuv is not None or fuv is not None:
        a = dst.fuv if dst.fuv is not None else np.zeros((f0, 3, 2))
        b = fuv if fuv is not None else np.zeros((nf, 3, 2))
        dst.fuv = np.concatenate([a, b])
    if dst.fcol is not None or fcol is not None:
        def _fc(x, n, like):
            if x is not None:
                return x
            sh = (n,) + tuple(like.shape[1:])
            return np.ones(sh)
        a = _fc(dst.fcol, f0, fcol if fcol is not None else dst.fcol)
        b = _fc(fcol, nf, dst.fcol if dst.fcol is not None else fcol)
        dst.fcol = np.concatenate([a, b])
    dst.V = np.concatenate([dst.V, V]); dst.F = np.concatenate([dst.F, F + n0])
    dst.J = np.concatenate([dst.J, J]); dst.W = np.concatenate([dst.W, W])
    dst.fmat = np.concatenate([dst.fmat, remap[fmat_names]])
    dst.textures.update(textures or {})
    parts = dst.meta.setdefault("mesh_parts", [])
    dst._tri_cache = {}
    return f0, f0 + nf


def hide_regions(rig, rec, regions, faces_limit=None):
    """mask (delete) body faces whose vertices are mostly driven by the given regions' bones. -> faces removed"""
    from .cleanup import keep_faces
    want = set()
    for r in regions:
        r = region_name(r)
        if r in REGIONS:
            want.update(REGIONS[r])
        elif r:
            want.add(r)
    if not want or not rig.has_mesh():
        return 0
    can = _canon_of(rig, rec)
    dom = rig.J[np.arange(len(rig.V)), np.argmax(rig.W, axis=1)]
    vin = np.array([can[int(b)] in want for b in dom])
    n = len(rig.F) if faces_limit is None else faces_limit
    hit = vin[rig.F[:n]].sum(1) >= 2
    keep = np.ones(len(rig.F), bool); keep[:n] = ~hit
    removed = int(hit.sum())
    if removed:
        cum = np.r_[0, np.cumsum(keep)]
        parts = rig.meta.get("mesh_parts") or []
        rig.meta["mesh_parts"] = [dict(p, f0=int(cum[p["f0"]]), f1=int(cum[p["f1"]])) for p in parts if cum[p["f1"]] > cum[p["f0"]]]
        keep_faces(rig, keep)
    return removed


def _rot(deg):
    rx, ry, rz = np.radians(deg)
    X = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Y = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Z = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    return Z @ Y @ X


def socket_frame(rig, rec, socket):
    """-> (bone index, attachment point in rest world space)"""
    c = SOCKET_BONE.get(socket)
    if c is None:
        raise ValueError("unknown socket '%s' (use: %s)" % (socket, ", ".join(SOCKET_BONE)))
    m = rec.get("map", {})
    for cc in [c] + SOCKET_FALLBACK.get(c, []):
        i = rig.index(m.get(cc, ""))
        if i >= 0:
            break
    else:
        raise ValueError("socket '%s' needs canonical bone '%s' on the base rig" % (socket, c))
    can = _canon_of(rig, rec)
    p = rig.bind[i, :3, 3].copy()
    if rig.has_mesh():
        dom = rig.J[np.arange(len(rig.V)), np.argmax(rig.W, axis=1)]
        mine = np.array([can[int(b)] == can[i] for b in dom])
        torso = np.array([can[int(b)] in REGIONS["torso"] for b in dom])
        if socket.startswith("hand") and mine.any():
            p = rig.V[mine].mean(0)
        elif socket.startswith("foot") and mine.any():
            p = rig.V[mine].mean(0); p[1] = rig.V[mine][:, 1].min()
        elif socket == "head" and mine.any():
            top = rig.V[mine]; p = np.array([top[:, 0].mean(), top[:, 1].max() - 0.02 * rig.height(), top[:, 2].mean()])
        elif socket == "back" and torso.any():
            T = rig.V[torso]
            sp = rig.index(m.get("spine", "")) if m.get("spine") else -1
            y = rig.bind[sp, 1, 3] if sp >= 0 else T[:, 1].mean()
            p = np.array([T[:, 0].mean(), y, T[:, 2].min()])
        elif socket == "hip":
            hp = np.array([can[int(b)] in ("hips", "thigh_R") for b in dom])
            if hp.any():
                H = rig.V[hp]; p = np.array([H[:, 0].min(), rig.bind[i, 1, 3], H[:, 2].mean()])
    return i, p


def parse_prop(s):
    """'sword@hand_r:0,0,0.02:0,0,0:1.0' -> dict(name, socket, offset, rotation, scale)"""
    parts = s.split(":")
    nm, _, sock = parts[0].partition("@")
    d = dict(name=nm.strip(), socket=sock.strip() or None, offset=None, rotation=None, scale=None)
    if len(parts) > 1 and parts[1]:
        d["offset"] = [float(x) for x in parts[1].split(",")]
    if len(parts) > 2 and parts[2]:
        d["rotation"] = [float(x) for x in parts[2].split(",")]
    if len(parts) > 3 and parts[3]:
        d["scale"] = float(parts[3])
    return d


def attach_prop(dst, drec, prop, socket, offset=None, rotation=None, scale=None, name="prop"):
    meta = prop.meta.get("prop", {})
    socket = socket or meta.get("socket") or "hand_r"
    bi, p = socket_frame(dst, drec, socket)
    rot = rotation if rotation is not None else (meta.get("rotation") if any(meta.get("rotation") or []) else SOCKET_ROT.get(socket, (0, 0, 0)))
    sc = scale if scale is not None else float(meta.get("scale") or 1.0)
    off = np.array(offset if offset is not None else (meta.get("offset") or [0, 0, 0]), float)
    PV = prop.V.copy()
    if socket == "back":
        PV[:, 2] -= PV[:, 2].max()          # the item's front face rests on the back
    fit = meta.get("fit", "none")
    if fit == "height":
        sc *= dst.height() / 1.8
    elif fit == "head" and dst.has_mesh():
        can = _canon_of(dst, drec)
        dom = dst.J[np.arange(len(dst.V)), np.argmax(dst.W, axis=1)]
        hv = dst.V[np.array([can[int(b)] == "head" for b in dom])]
        if len(hv):
            sc *= 1.08 * np.ptp(hv[:, 0]) / max(1e-6, np.ptp(PV[:, 0]))
    R = _rot(rot)
    V = (R @ (sc * PV).T).T + p + off
    J = np.zeros((len(V), 4), int); J[:, 0] = bi
    W = np.zeros((len(V), 4)); W[:, 0] = 1
    mats = [dict(m, name=_prop_mat(name, m.get("name"))) for m in prop.materials] or [dict(name=_prop_mat(name, "mat"), color=[0.7, 0.7, 0.7])]
    f0, f1 = _merge(dst, V, prop.F, J, W, prop.fmat if len(prop.fmat) else np.zeros(len(prop.F), int), prop.fuv, prop.fcol, mats, prop.textures)
    dst.meta.setdefault("mesh_parts", []).append(dict(name="prop:" + name, f0=f0, f1=f1))
    return dict(name=name, socket=socket, bone=dst.bones[bi], at=[round(float(x), 4) for x in p], rotation=list(rot), scale=sc, faces=int(f1 - f0))


def _prop_mat(name, m):
    m = m or "mat"
    if re.search(r"_Mat$", m) and m.split("_")[0] in ("Skin", "Jersey", "Shorts", "Socks", "Trim", "Hair", "Shoes"):
        return m
    return "Prop_%s_%s" % (re.sub(r"\W+", "", name), re.sub(r"\W+", "", m))


def _slot_mat(slot):
    s = slot.strip()
    if not s:
        return None
    s = s[:-4] if s.lower().endswith("_mat") else s
    return s[:1].upper() + s[1:] + "_Mat"


def attach_outfit(dst, drec, out, orec, name="outfit", hide=None, slot=None):
    meta = out.meta.get("outfit", {})
    hide = meta.get("hide", []) if hide is None else hide
    slot = slot or meta.get("slot")
    removed = hide_regions(dst, drec, hide) if hide else 0
    V = fit_rest(out, orec, dst, drec)
    J = remap_weights(out, orec, dst, drec)
    sm = _slot_mat(slot) if slot else None
    if sm:
        col = (out.materials[0].get("color") if out.materials else None) or [0.6, 0.6, 0.6]
        mats = [dict(name=sm, color=col)]; fm = np.zeros(len(out.F), int); fuv = None if not out.textures else out.fuv
    else:
        mats = [dict(m, name="Outfit_%s_%s" % (re.sub(r"\W+", "", name), re.sub(r"\W+", "", m.get("name") or "mat"))) for m in out.materials] or [dict(name="Outfit_" + name, color=[0.6, 0.6, 0.6])]
        fm = out.fmat if len(out.fmat) else np.zeros(len(out.F), int); fuv = out.fuv
    f0, f1 = _merge(dst, V, out.F, J, out.W.copy(), fm, fuv, out.fcol, mats, out.textures)
    dst.meta.setdefault("mesh_parts", []).append(dict(name="outfit:" + name, f0=f0, f1=f1))
    return dict(name=name, slot=sm, hide=list(hide or []), body_faces_hidden=removed, faces=int(f1 - f0))


def parse_outfit(s):
    """"name" | "name:hide=torso+arms" | "name:hide=none" | "name:slot=Jersey" -> str or dict for equip()"""
    if not isinstance(s, str) or ":" not in s:
        return s
    nm, rest = s.split(":", 1); d = dict(name=nm.strip())
    for kv in rest.split(":"):
        k, _, v = kv.partition("=")
        k = k.strip().lower(); v = v.strip()
        if k == "hide":
            d["hide"] = [] if v.lower() in ("none", "") else [x for x in v.replace(",", "+").split("+") if x]
            d["hide"] = [region_name(x) for x in d["hide"]]
            bad = [x for x in d["hide"] if x not in REGIONS]
            if bad:
                raise ValueError("outfit %s: unknown hide region(s) %s (use %s)" % (nm, ", ".join(bad), " ".join(REGIONS)))
        elif k == "slot":
            d["slot"] = v
        else:
            raise ValueError("outfit %s: unknown option '%s' (hide=REGIONS, slot=NAME)" % (nm, k))
    return d


def parse_colors(s):
    """'Jersey=#c8102e,Armour_Mat=#777777' -> {'Jersey_Mat': (r,g,b) 0..1}"""
    out = {}
    if not s:
        return out
    items = s.items() if isinstance(s, dict) else [x.split("=", 1) for x in re.split(r"[;,]\s*(?=[A-Za-z_])", s) if "=" in x]
    for k, v in items:
        k = k.strip(); v = str(v).strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", v):
            raise ValueError("slot colour '%s' must be #rrggbb" % v)
        key = k if ("_" in k or k.startswith("Prop") or k.startswith("Outfit")) else _slot_mat(k)
        out[key] = [int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return out


def apply_colors(rig, cols, log=None):
    done = []
    for m in rig.materials:
        n = m.get("name") or ""
        for k, c in cols.items():
            if n == k or n.lower() == k.lower():
                m["color"] = list(c); m["sforge_slot_color"] = True; done.append(n)
    if log and cols:
        miss = [k for k in cols if k not in done]
        log("slot colours: %s%s" % (", ".join(done) or "-", ("; not on this rig: " + ", ".join(miss)) if miss else ""))
    return done


def equip(rig, rec, lib, outfits=(), props=(), slot_colors=None, log=print):
    """-> (new rig, list of part records with licences)."""
    r = copy.deepcopy(rig)
    if not r.meta.get("mesh_parts"):
        r.meta["mesh_parts"] = [dict(name="body", f0=0, f1=len(r.F))]
    parts = []
    for o in outfits or ():
        nm = o if isinstance(o, str) else o.get("name")
        orig = lib.load_rig("outfits/" + nm if "/" not in nm else nm)
        orec = lib.bonemap("outfits/" + nm if "/" not in nm else nm, orig)
        info = attach_outfit(r, rec, orig, orec, nm, hide=None if isinstance(o, str) else o.get("hide"),
                             slot=None if isinstance(o, str) else o.get("slot"))
        info["kind"] = "outfit"; info["licence"] = lib.licence("outfits/" + nm if "/" not in nm else nm)
        parts.append(info)
        log("  equip outfit '%s': %d faces, slot %s, hid %d body faces (%s)" % (nm, info["faces"], info["slot"] or "own materials",
                                                                             info["body_faces_hidden"], ", ".join(info["hide"]) or "no mask"))
    for p in props or ():
        d = parse_prop(p) if isinstance(p, str) else dict(p)
        nm = d["name"]
        prig = lib.load_rig("props/" + nm if "/" not in nm else nm)
        info = attach_prop(r, rec, prig, d.get("socket"), d.get("offset"), d.get("rotation"), d.get("scale"), nm)
        info["kind"] = "prop"; info["licence"] = lib.licence("props/" + nm if "/" not in nm else nm)
        parts.append(info)
        log("  equip prop '%s' on %s (bone %s): %d faces" % (nm, info["socket"], info["bone"], info["faces"]))
    if slot_colors:
        apply_colors(r, parse_colors(slot_colors) if isinstance(slot_colors, str) else slot_colors, log)
    r._tri_cache = {}
    return r, parts
