"""v7 import clean-up: duplicate / nested mesh removal and orientation checks (pure Python + numpy).

dedupe(rig, report)      removes mesh parts that are copies of another part:
  * same name apart from a Blender/Maya copy suffix (Body.001, Body_1, "Body (2)") AND the same vertex set
  * any two parts with identical vertex sets (rounded to 0.1 mm), whatever their names
  * lower-detail duplicates: a part named like *_LOD1 / *_lod2 / *.001 whose bounding box matches another part
    (>= 95 % box-volume overlap, >= 85 % for explicit *_LODn names) but which has fewer faces - the higher-detail part is kept
  Every removal is listed in report["cleanup"]["removed"] (name, faces, reason).  Nothing is removed from parts
  that merely touch or overlap partly (clothes over a body are kept).
fix_orientation(rig, rec, report)   after bonemap.orient() (rest pose up = +Y, faces +Z, metres, grounded):
  * checks every clip: when the clip's first frame lies flat (head-hips at > 60 deg from +Y, e.g. an FBX take
    keyed on a Z-up armature) the whole clip is rotated upright about its hips (axis-snapped 90/180 deg);
  * reports the decision in report["cleanup"]["orientation"].
"""
from __future__ import annotations
import re
import numpy as np

COPY_SUFFIX = re.compile(r"(\.\d{3}|_\d+|\s*\(\d+\)|[_\.\- ]?copy\d*)$", re.I)
LOD_RX = re.compile(r"[_\.\- ]?lod[_\- ]?(\d+)$", re.I)


def _stem(n):
    n = (n or "").strip()
    n2 = LOD_RX.sub("", n)
    n2 = COPY_SUFFIX.sub("", n2)
    return n2.lower()


def _vkey(rig, f0, f1):
    vi = np.unique(rig.F[f0:f1].reshape(-1))
    P = np.round(rig.V[vi] / 1e-4).astype(np.int64)
    P = P[np.lexsort(P.T[::-1])]
    return P.tobytes(), P


def _bbox(rig, f0, f1):
    vi = np.unique(rig.F[f0:f1].reshape(-1))
    return rig.V[vi].min(0), rig.V[vi].max(0)


def _overlap(a, b):
    lo = np.maximum(a[0], b[0]); hi = np.minimum(a[1], b[1])
    inter = np.prod(np.clip(hi - lo, 0, None))
    va = np.prod(np.maximum(a[1] - a[0], 1e-9)); vb = np.prod(np.maximum(b[1] - b[0], 1e-9))
    return inter / max(va, vb)


def keep_faces(rig, keep):
    """drop faces (bool mask keep) and unused vertices, keeping per-face data aligned."""
    keep = np.asarray(keep, bool)
    rig.F = rig.F[keep]
    for a in ("fmat",):
        setattr(rig, a, getattr(rig, a)[keep])
    if rig.fuv is not None:
        rig.fuv = rig.fuv[keep]
    if rig.fcol is not None:
        rig.fcol = rig.fcol[keep]
    used = np.unique(rig.F.reshape(-1))
    remap = -np.ones(len(rig.V), int); remap[used] = np.arange(len(used))
    rig.V = rig.V[used]; rig.J = rig.J[used]; rig.W = rig.W[used]
    rig.F = remap[rig.F]
    rig._tri_cache = {}


def dedupe(rig, report=None, mode="auto"):
    rep = {"removed": [], "parts": 0}
    if report is not None:
        report.setdefault("cleanup", {})["dedupe"] = rep
    parts = rig.meta.get("mesh_parts") or []
    rep["parts"] = len(parts)
    if mode == "off" or len(parts) < 2 or not rig.has_mesh():
        return rep
    info = []
    for p in parts:
        f0, f1 = int(p["f0"]), int(p["f1"])
        if f1 <= f0:
            continue
        k, _ = _vkey(rig, f0, f1)
        info.append(dict(name=p["name"], f0=f0, f1=f1, key=k, bb=_bbox(rig, f0, f1), nf=f1 - f0, stem=_stem(p["name"]),
                         suffix=bool(COPY_SUFFIX.search(p["name"] or "")), lod=LOD_RX.search(p["name"] or "")))
    drop = set()
    for i, a in enumerate(info):
        if i in drop:
            continue
        for j in range(i + 1, len(info)):
            b = info[j]
            if j in drop:
                continue
            if a["key"] == b["key"]:
                # identical vertex set: keep the one without a copy suffix (else the first)
                victim = j if (b["suffix"] or not a["suffix"]) else i
                reason = "identical vertex set to '%s'" % info[i if victim == j else j]["name"]
                if a["stem"] == b["stem"]:
                    reason += " (copy-suffix name)"
                drop.add(victim); rep["removed"].append(dict(name=info[victim]["name"], faces=info[victim]["nf"], reason=reason))
                if victim == i:
                    break
                continue
            thr = 0.85 if (a["lod"] or b["lod"]) else 0.95       # decimated LODs shrink a little (volume overlap)
            if a["stem"] == b["stem"] and (a["lod"] or b["lod"] or a["suffix"] or b["suffix"]) and _overlap(a["bb"], b["bb"]) >= thr:
                victim = j if b["nf"] < a["nf"] else i
                other = i if victim == j else j
                drop.add(victim)
                rep["removed"].append(dict(name=info[victim]["name"], faces=info[victim]["nf"],
                                           reason="lower-detail duplicate of '%s' (%d faces, same bounds)" % (info[other]["name"], info[other]["nf"])))
                if victim == i:
                    break
    if drop:
        keep = np.ones(len(rig.F), bool)
        for k in drop:
            keep[info[k]["f0"]:info[k]["f1"]] = False
        # rebuild the part table for the faces that stay
        newparts, off = [], 0
        for k, p in enumerate(info):
            if k in drop:
                continue
            n = p["f1"] - p["f0"]; newparts.append(dict(name=p["name"], f0=off, f1=off + n)); off += n
        keep_faces(rig, keep)
        rig.meta["mesh_parts"] = newparts
    return rep


def _up_of(rig, rec, Wd):
    from .bonemap import index_map
    im = index_map(rig, rec)
    if "head" in im and "hips" in im:
        u = Wd[im["head"], :3, 3] - Wd[im["hips"], :3, 3]
        n = np.linalg.norm(u)
        return u / n if n > 1e-9 else None
    return None


def fix_orientation(rig, rec, report=None, mode="auto"):
    """rotate clips whose first frame lies flat back upright (after the rest pose was fixed)."""
    from .rigrec import rot_between, m4
    from .bonemap import _snap_axis, index_map
    rep = {"rest_fixes": list((report or {}).get("fixes", [])), "clips_fixed": []}
    if report is not None:
        report.setdefault("cleanup", {})["orientation"] = rep
    if mode == "off":
        return rep
    im = index_map(rig, rec)
    hips = im.get("hips", rig.meta.get("hips_index", 0))
    for cn, c in list(rig.clips.items()):
        Wf = rig.clip_worlds(c)
        u = _up_of(rig, rec, Wf[0])
        if u is None or u[1] > np.cos(np.radians(60)):
            continue
        e = _snap_axis(u)
        R = rot_between(e, [0, 1, 0])
        piv = Wf[0, hips, :3, 3].copy()
        G = m4(None, piv) @ m4(R) @ m4(None, -piv)
        W2 = np.einsum("ij,fbjk->fbik", G, Wf)
        rig.clips[cn] = rig.clip_from_worlds(cn, W2, c.fps, c.loop, c.source)
        rep["clips_fixed"].append(dict(clip=cn, up_was=[round(float(x), 3) for x in e]))
    return rep


def ground_report(rig):
    y0 = float(rig.V[:, 1].min()) if rig.has_mesh() else float(rig.bind[:, 1, 3].min())
    return round(y0, 5)
