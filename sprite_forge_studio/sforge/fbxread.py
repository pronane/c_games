"""FBX 7.x reader (binary AND ASCII) -> normalized Rig (pure Python + numpy).

Covers: Model hierarchy (LimbNode / Root / Null / Mesh), the full FBX local transform
(T * Roff * Rp * Rpre * R * Rpost^-1 * Rp^-1 * Soff * Sp * S * Sp^-1, any RotationOrder), Geometry
(control points, n-gons triangulated, UVs, vertex colours, per-polygon materials, geometric transforms),
Skin / Cluster deformers (weights, TransformLink bind pose; SDK and Blender cluster conventions),
Materials (DiffuseColor) and Textures (embedded Video content or a file next to the FBX), and every
AnimationStack (first layer, Lcl Translation / Rotation / Scaling curves sampled linearly at 30 fps).
GlobalSettings UpAxis / FrontAxis / CoordAxis and UnitScaleFactor are converted to Y-up metres.

NOT read (honest limits): blend shapes / morph targets, constraints, IK, animated scale is baked into
the bone matrices then removed (rotation + translation only), curve tangents (keys are sampled linearly),
additional animation layers, cameras / lights, FBX 6.x ASCII (name-based connections).
"""
from __future__ import annotations
import base64
import io
import math
import os
import re
import numpy as np
from PIL import Image

from .rigrec import Rig, polar, m4, FPS
from . import fbx as FB

KTIME = 46186158000.0


# ----------------------------------------------------------------- ASCII parser -> same dicts as fbx.read_fbx
_TOK = re.compile(r'''\s*(?:(;[^\n]*)|("[^"]*")|([A-Za-z_][\w|\-]*)\s*:|(\*\d+)|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|(,)|(\{)|(\})|([A-Za-z_][\w.\-]*))''')


def read_ascii(path):
    txt = open(path, "r", encoding="utf-8", errors="replace").read()
    pos, n = 0, len(txt)
    root = {"name": "", "props": [], "kids": []}
    stack = [root]
    cur = None             # node currently collecting values
    while pos < n:
        m = _TOK.match(txt, pos)
        if not m or m.end() == pos:
            if txt[pos:].strip() == "":
                break
            pos += 1; continue
        pos = m.end()
        com, s, key, cnt, num, comma, lb, rb, word = m.groups()
        if com:
            continue
        if key is not None:
            cur = {"name": key, "props": [], "kids": []}
            stack[-1]["kids"].append(cur)
            if key == "a" and stack[-1].get("_array"):
                # fast path: numeric array body up to the closing brace
                end = txt.index("}", pos)
                body = txt[pos:end]
                arr = np.array([float(x) for x in body.replace("\n", ",").split(",") if x.strip()])
                par = stack[-1]
                par["props"] = [arr]; par["kids"].remove(cur)
                cur = None; pos = end
            continue
        if lb:
            if cur is None:
                cur = {"name": "", "props": [], "kids": []}; stack[-1]["kids"].append(cur)
            stack.append(cur); cur = None; continue
        if rb:
            nd = stack.pop()
            nd.pop("_array", None)
            cur = None; continue
        if comma:
            continue
        if cur is None:
            continue
        if cnt:
            cur["_array"] = True; continue
        if s is not None:
            cur["props"].append(s[1:-1])
        elif num is not None:
            cur["props"].append(float(num) if any(c in num for c in ".eE") else int(num))
        elif word is not None:
            cur["props"].append(word)
    return root["kids"]


def read_any(path):
    head = open(path, "rb").read(32)
    if head.startswith(b"Kaydara FBX Binary"):
        return FB.read_fbx(path), "binary"
    return read_ascii(path), "ascii"


# ----------------------------------------------------------------- helpers
def _kid(n, name):
    for k in n["kids"]:
        if k["name"] == name:
            return k
    return None


def _kids(n, name):
    return [k for k in n["kids"] if k["name"] == name]


def _arr(n, name, dt=float):
    k = _kid(n, name) if n else None
    if k is None or not k["props"]:
        return None
    v = k["props"][0]
    if isinstance(v, np.ndarray):
        return v.astype(dt)
    return np.array(k["props"], dt)


def _props70(n):
    out = {}
    p = _kid(n, "Properties70") or _kid(n, "Properties60")
    if p is None:
        return out
    for P in p["kids"]:
        if P["props"]:
            out[str(P["props"][0])] = P["props"][4:] if P["name"] == "P" else P["props"][3:]
    return out


def _vec(props, key, default):
    v = props.get(key)
    if v is None or len(v) < len(default):
        return np.array(default, float)
    try:
        return np.array([float(x) for x in v[:len(default)]])
    except (TypeError, ValueError):
        return np.array(default, float)


def _scalar(props, key, default):
    v = props.get(key)
    try:
        return type(default)(v[0]) if v else default
    except (TypeError, ValueError):
        return default


def _split_name(raw, binary):
    raw = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
    if "\x00\x01" in raw:
        name, cls = raw.split("\x00\x01", 1); return cls, name
    if "::" in raw:
        cls, name = raw.split("::", 1); return cls, name
    return "", raw


def _rot(axis, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    if axis == 0:
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == 1:
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


ORDERS = {0: (0, 1, 2), 1: (0, 2, 1), 2: (1, 2, 0), 3: (1, 0, 2), 4: (2, 0, 1), 5: (2, 1, 0)}


def euler_mat(e, order=0):
    """FBX euler (degrees), order XYZ means X is applied first: R = R3 R2 R1."""
    o = ORDERS.get(int(order), (0, 1, 2))
    R = np.eye(3)
    for ax in o:
        R = _rot(ax, e[ax]) @ R
    return R


def _T(v):
    return m4(None, v)


def local_matrix(pr, T=None, R=None, S=None):
    T = _vec(pr, "Lcl Translation", [0, 0, 0]) if T is None else T
    R = _vec(pr, "Lcl Rotation", [0, 0, 0]) if R is None else R
    S = _vec(pr, "Lcl Scaling", [1, 1, 1]) if S is None else S
    ro = _scalar(pr, "RotationOrder", 0)
    active = _scalar(pr, "RotationActive", 1 if ("PreRotation" in pr or "PostRotation" in pr) else 0)
    pre = euler_mat(_vec(pr, "PreRotation", [0, 0, 0])) if active else np.eye(3)
    post = euler_mat(_vec(pr, "PostRotation", [0, 0, 0])) if active else np.eye(3)
    Roff = _vec(pr, "RotationOffset", [0, 0, 0]); Rp = _vec(pr, "RotationPivot", [0, 0, 0])
    Soff = _vec(pr, "ScalingOffset", [0, 0, 0]); Sp = _vec(pr, "ScalingPivot", [0, 0, 0])
    Sm = np.diag(list(S) + [1.0])
    return (_T(T) @ _T(Roff) @ _T(Rp) @ m4(pre) @ m4(euler_mat(R, ro)) @ m4(post.T) @ _T(-Rp)
            @ _T(Soff) @ _T(Sp) @ Sm @ _T(-Sp))


def geometric_matrix(pr):
    return (_T(_vec(pr, "GeometricTranslation", [0, 0, 0])) @ m4(euler_mat(_vec(pr, "GeometricRotation", [0, 0, 0])))
            @ np.diag(list(_vec(pr, "GeometricScaling", [1, 1, 1])) + [1.0]))


def _mat16(v):
    return np.asarray(v, float).reshape(4, 4).T


def axis_matrix(gs):
    """file axes -> Y up, +Z front, +X 'coord' axis."""
    up = _scalar(gs, "UpAxis", 1); ups = _scalar(gs, "UpAxisSign", 1)
    fr = _scalar(gs, "FrontAxis", 2); frs = _scalar(gs, "FrontAxisSign", 1)
    co = _scalar(gs, "CoordAxis", 0); cos_ = _scalar(gs, "CoordAxisSign", 1)
    if len({up, fr, co}) != 3:
        return np.eye(3)
    E = np.eye(3)
    B = np.column_stack([E[co] * cos_, E[up] * ups, E[fr] * frs])   # columns = file X', Y', Z' targets
    return B.T


# ----------------------------------------------------------------- scene
def load(path, report=None):
    report = report if report is not None else {}
    top, kind = read_any(path)
    report["fbx_format"] = kind
    hdr = next((n for n in top if n["name"] == "FBXHeaderExtension"), None)
    ver = _kid(hdr, "FBXVersion") if hdr else None
    report["fbx_version"] = int(ver["props"][0]) if ver and ver["props"] else None
    if report["fbx_version"] and report["fbx_version"] < 7000:
        raise ValueError("FBX %s is too old (only FBX 7.x is supported; re-export as FBX 7.4 binary or ASCII)" % report["fbx_version"])
    binary = kind == "binary"
    gsn = next((n for n in top if n["name"] == "GlobalSettings"), None)
    gs = _props70(gsn) if gsn else {}
    unit = _scalar(gs, "UnitScaleFactor", 1.0) / 100.0
    A = axis_matrix(gs)
    report["unit_scale_m"] = unit
    report["axes"] = dict(up=_scalar(gs, "UpAxis", 1), front=_scalar(gs, "FrontAxis", 2), coord=_scalar(gs, "CoordAxis", 0))
    objs_n = next((n for n in top if n["name"] == "Objects"), {"kids": []})
    conns_n = next((n for n in top if n["name"] == "Connections"), {"kids": []})
    objs = {}
    for o in objs_n["kids"]:
        if not o["props"]:
            continue
        oid = int(o["props"][0])
        cls, name = _split_name(o["props"][1] if len(o["props"]) > 1 else "", binary)
        sub = o["props"][2] if len(o["props"]) > 2 else ""
        objs[oid] = dict(id=oid, type=o["name"], cls=cls, name=name, sub=str(sub), node=o, props=_props70(o))
    conns = []
    for c in conns_n["kids"]:
        if c["name"] != "C" or len(c["props"]) < 3:
            continue
        conns.append((str(c["props"][0]), int(c["props"][1]), int(c["props"][2]), str(c["props"][3]) if len(c["props"]) > 3 else ""))
    kids_of, parents_of = {}, {}
    for t, a, b, p in conns:
        kids_of.setdefault(b, []).append((a, t, p)); parents_of.setdefault(a, []).append((b, t, p))

    models = {i: o for i, o in objs.items() if o["type"] == "Model"}
    mparent = {}
    for i in models:
        for b, t, _ in parents_of.get(i, []):
            if t == "OO" and b in models:
                mparent[i] = b; break

    # ---- rest (Lcl) world of every model
    Lrest = {i: local_matrix(o["props"]) for i, o in models.items()}

    def worlds(L):
        out = {}
        def w(i):
            if i in out:
                return out[i]
            p = mparent.get(i)
            out[i] = L[i] if p is None else w(p) @ L[i]
            return out[i]
        for i in L:
            w(i)
        return out
    Wrest = worlds(Lrest)

    # ---- skin clusters
    clusters = [o for o in objs.values() if o["type"] == "Deformer" and o["sub"] == "Cluster"]
    cl_bone = {}
    for c in clusters:
        for a, t, _ in kids_of.get(c["id"], []):
            if a in models:
                cl_bone[c["id"]] = a
    bone_ids = set(cl_bone.values())
    for i, o in models.items():
        if o["sub"] in ("LimbNode", "Root", "Limb"):
            bone_ids.add(i)
    meshes = [i for i, o in models.items() if o["sub"] == "Mesh"]
    # bones: keep hierarchy order (parents first)
    def depth(i):
        d = 0
        while i in mparent:
            i = mparent[i]; d += 1
        return d
    blist = sorted(bone_ids, key=lambda i: (depth(i), i))
    if not blist:
        # static mesh / no skeleton: one root bone
        report.setdefault("warnings", []).append("no skeleton in the file: a single 'root' bone was added (static mesh)")
    bidx = {b: k for k, b in enumerate(blist)}

    def bone_parent(i):
        p = mparent.get(i)
        while p is not None and p not in bidx:
            p = mparent.get(p)
        return bidx[p] if p is not None else -1

    # bind world (file space): TransformLink where available, else parent-bind @ rest-local
    TL = {}
    for c in clusters:
        b = cl_bone.get(c["id"])
        v = _arr(c["node"], "TransformLink")
        if b is not None and v is not None and len(v) == 16:
            TL[b] = _mat16(v)
    bindF = {}
    for b in blist:
        if b in TL:
            bindF[b] = TL[b]
        else:
            p = bone_parent(b)
            if p >= 0:
                pb = blist[p]
                bindF[b] = bindF[pb] @ np.linalg.inv(Wrest[pb]) @ Wrest[b]
            else:
                bindF[b] = Wrest[b]

    rig = Rig(os.path.splitext(os.path.basename(path))[0])
    rig.bones = [models[b]["name"] for b in blist] or ["root"]
    rig.parent = np.array([bone_parent(b) for b in blist] or [-1], int)

    def norm(M):
        """file-space world matrix -> scale-free, Y-up metres."""
        out = np.eye(4)
        out[:3, :3] = A @ polar(M[:3, :3])
        out[:3, 3] = A @ (M[:3, 3] * unit)
        return out
    rig.bind = np.array([norm(bindF[b]) for b in blist] if blist else [np.eye(4)])

    # ---- geometry
    mats_all, matkey = [], {}
    Vs, Fs, Js, Ws, FM, FUV, FCOL = [], [], [], [], [], [], []
    have_uv = have_col = False
    tex_store = {}
    voff = 0
    parts = []; foff = 0
    stats = dict(meshes=0, polygons=0, ngons=0, skinned=0)
    for mi in meshes:
        mo = models[mi]
        geo = next((objs[a] for a, t, _ in kids_of.get(mi, []) if a in objs and objs[a]["type"] == "Geometry" and objs[a]["sub"] == "Mesh"), None)
        if geo is None:
            continue
        g = geo["node"]
        P = _arr(g, "Vertices")
        PVI = _arr(g, "PolygonVertexIndex", int)
        if P is None or PVI is None:
            continue
        P = P.reshape(-1, 3)
        stats["meshes"] += 1
        # polygons
        polys, cur = [], []
        for k, v in enumerate(PVI):
            if v < 0:
                cur.append((~v, k)); polys.append(cur); cur = []
            else:
                cur.append((v, k))
        stats["polygons"] += len(polys); stats["ngons"] += sum(1 for p in polys if len(p) > 4)
        # material layer
        lm = _kid(g, "LayerElementMaterial")
        pmat = np.zeros(len(polys), int)
        if lm is not None:
            mm = _kid(lm, "MappingInformationType")
            ma = _arr(lm, "Materials", int)
            if ma is not None and len(ma):
                if mm and str(mm["props"][0]) == "AllSame":
                    pmat[:] = ma[0]
                elif len(ma) >= len(polys):
                    pmat = ma[:len(polys)]
        mlist = [a for a, t, _ in kids_of.get(mi, []) if a in objs and objs[a]["type"] == "Material"]
        gmap = []
        for a in mlist or [None]:
            if a is None:
                key = "default"; md = dict(name="default", color=[0.7, 0.7, 0.7])
            else:
                key = a; md = _material(objs[a], objs, kids_of, path, tex_store, report)
            if key not in matkey:
                matkey[key] = len(mats_all); mats_all.append(md)
            gmap.append(matkey[key])
        # UV / colour layers (per corner)
        uvc = _layer(g, "LayerElementUV", "UV", "UVIndex", 2, len(P), len(PVI))
        colc = _layer(g, "LayerElementColor", "Colors", "ColorIndex", 4, len(P), len(PVI))
        # triangulate (fan)
        tri, trimat, tricorner = [], [], []
        for pi, poly in enumerate(polys):
            for k in range(1, len(poly) - 1):
                tri.append([poly[0][0], poly[k][0], poly[k + 1][0]])
                tricorner.append([poly[0][1], poly[k][1], poly[k + 1][1]])
                trimat.append(gmap[min(len(gmap) - 1, max(0, int(pmat[pi])))])
        tri = np.array(tri, int).reshape(-1, 3); tricorner = np.array(tricorner, int).reshape(-1, 3)
        # skin
        skin = next((objs[a] for a, t, _ in kids_of.get(geo["id"], []) if a in objs and objs[a]["type"] == "Deformer" and objs[a]["sub"] == "Skin"), None)
        wj = [[] for _ in range(len(P))]
        mesh_world = None
        if skin is not None:
            cand_sdk, cand_bl = [], []
            for a, t, _ in kids_of.get(skin["id"], []):
                c = objs.get(a)
                if not c or c["sub"] != "Cluster":
                    continue
                b = cl_bone.get(a)
                ix = _arr(c["node"], "Indexes", int); wt = _arr(c["node"], "Weights")
                Tm = _arr(c["node"], "Transform"); Tl = _arr(c["node"], "TransformLink")
                if Tm is not None and Tl is not None:
                    cand_sdk.append(_mat16(Tm)); cand_bl.append(_mat16(Tl) @ _mat16(Tm))
                if b is None or ix is None or wt is None:
                    continue
                for v, w in zip(ix, wt):
                    if 0 <= v < len(P) and w > 0:
                        wj[v].append((bidx[b], float(w)))
            def spread(c):
                return max(np.abs(x - c[0]).max() for x in c) if c else 1e9
            if cand_sdk:
                s1, s2 = spread(cand_sdk), spread(cand_bl)
                mesh_world = cand_sdk[0] if s1 <= s2 * 1.0001 else cand_bl[0]
                report["cluster_convention"] = "sdk (Transform = mesh bind)" if s1 <= s2 * 1.0001 else "blender (TransformLink*Transform = mesh bind)"
            stats["skinned"] += 1
        if mesh_world is None:
            mesh_world = Wrest[mi]
        Mg = mesh_world @ geometric_matrix(mo["props"])
        Pw = (np.c_[P, np.ones(len(P))] @ Mg.T)[:, :3]
        Pw = (Pw * unit) @ A.T
        # rigid fallback bone for unweighted vertices
        rb = mparent.get(mi)
        while rb is not None and rb not in bidx:
            rb = mparent.get(rb)
        rbi = bidx[rb] if rb is not None else 0
        J = np.zeros((len(P), 4), int); W = np.zeros((len(P), 4))
        for v, lst in enumerate(wj):
            if not lst:
                J[v, 0] = rbi; W[v, 0] = 1; continue
            agg = {}
            for b, w in lst:
                agg[b] = agg.get(b, 0) + w
            top4 = sorted(agg.items(), key=lambda x: -x[1])[:4]
            s = sum(w for _, w in top4) or 1
            for k, (b, w) in enumerate(top4):
                J[v, k] = b; W[v, k] = w / s
        Vs.append(Pw); Fs.append(tri + voff); Js.append(J); Ws.append(W); FM.append(np.array(trimat, int))
        parts.append(dict(name=str(mo.get("name", "mesh")), f0=foff, f1=foff + len(tri))); foff += len(tri)
        voff += len(P)
        if uvc is not None:
            have_uv = True; FUV.append(uvc[tricorner])
        else:
            FUV.append(np.zeros((len(tri), 3, 2)))
        if colc is not None:
            have_col = True; FCOL.append(colc[tricorner][..., :3])
        else:
            FCOL.append(np.ones((len(tri), 3, 3)))
    if Vs:
        rig.V = np.concatenate(Vs); rig.F = np.concatenate(Fs); rig.J = np.concatenate(Js); rig.W = np.concatenate(Ws)
        rig.fmat = np.concatenate(FM)
        rig.fuv = np.concatenate(FUV) if have_uv else None
        rig.fcol = np.concatenate(FCOL) if have_col else None
        rig.meta["mesh_parts"] = parts
    rig.materials = mats_all
    rig.textures = tex_store
    report["mesh"] = stats

    # ---- animation stacks
    stacks = [o for o in objs.values() if o["type"] == "AnimationStack"]
    curve_nodes = {i: o for i, o in objs.items() if o["type"] == "AnimationCurveNode"}
    names_seen = set()
    for st in stacks:
        layers = [a for a, t, _ in kids_of.get(st["id"], []) if a in objs and objs[a]["type"] == "AnimationLayer"]
        if not layers:
            continue
        if len(layers) > 1:
            report.setdefault("warnings", []).append("take '%s': %d animation layers, only the first is used" % (st["name"], len(layers)))
        lay = layers[0]
        chans = {}      # model -> {"T"/"R"/"S": [curve or default]*3}
        tmin, tmax = None, None
        for cn, t, _ in kids_of.get(lay, []):
            if cn not in curve_nodes:
                continue
            target = None
            for b, tt, p in parents_of.get(cn, []):
                if tt == "OP" and b in models:
                    target = (b, p)
            if target is None:
                continue
            mid, prop = target
            key = {"Lcl Translation": "T", "Lcl Rotation": "R", "Lcl Scaling": "S"}.get(prop)
            if key is None:
                continue
            cp = curve_nodes[cn]["props"]
            comp = [None, None, None]
            for ax, nm in enumerate(("d|X", "d|Y", "d|Z")):
                comp[ax] = ("const", _scalar(cp, nm, float("nan")))
            for cv, tt, p in kids_of.get(cn, []):
                if cv in objs and objs[cv]["type"] == "AnimationCurve":
                    ax = {"d|X": 0, "d|Y": 1, "d|Z": 2}.get(p)
                    if ax is None:
                        continue
                    kt = _arr(objs[cv]["node"], "KeyTime", float)
                    kv = _arr(objs[cv]["node"], "KeyValueFloat", float)
                    if kt is None or kv is None or not len(kt):
                        continue
                    kt = kt / KTIME
                    comp[ax] = ("curve", kt, kv[:len(kt)])
                    tmin = kt[0] if tmin is None else min(tmin, kt[0]); tmax = kt[-1] if tmax is None else max(tmax, kt[-1])
            chans.setdefault(mid, {})[key] = comp
        if not chans:
            continue
        sp = st["props"]
        t0 = _scalar(sp, "LocalStart", None) if "LocalStart" in sp else None
        t1 = _scalar(sp, "LocalStop", None) if "LocalStop" in sp else None
        t0 = t0 / KTIME if t0 is not None else (tmin or 0.0)
        t1 = t1 / KTIME if t1 is not None and t1 / KTIME > t0 else (tmax if tmax is not None else t0)
        if tmax is not None and t1 - t0 < 1e-6:
            t1 = tmax
        nfr = max(1, int(round((t1 - t0) * FPS)) + 1)
        Wf = np.zeros((nfr, rig.nb, 4, 4))
        for f in range(nfr):
            tt = t0 + f / FPS
            L = {}
            for i, o in models.items():
                ch = chans.get(i)
                if not ch:
                    L[i] = Lrest[i]; continue
                vals = {}
                for k2, dflt in (("T", "Lcl Translation"), ("R", "Lcl Rotation"), ("S", "Lcl Scaling")):
                    base = _vec(o["props"], dflt, [1, 1, 1] if k2 == "S" else [0, 0, 0])
                    comp = ch.get(k2)
                    if comp:
                        for ax in range(3):
                            c = comp[ax]
                            if c[0] == "curve":
                                base[ax] = float(np.interp(tt, c[1], c[2]))
                            elif not math.isnan(c[1]):
                                base[ax] = c[1]
                    vals[k2] = base
                L[i] = local_matrix(o["props"], vals["T"], vals["R"], vals["S"])
            Wd = worlds(L)
            for k, b in enumerate(blist):
                Wf[f, k] = norm(Wd[b])
        nm = st["name"].split("|")[-1].strip() or "take"
        if nm.lower() in ("mixamo.com", "take 001", "take001", "default take", "unreal take"):
            nm = rig.name if len(stacks) == 1 else "%s_%d" % (rig.name, len(names_seen))
        base = re.sub(r"[^A-Za-z0-9_\-]+", "_", nm).strip("_").lower() or "take"
        nm = base; k = 2
        while nm in names_seen:
            nm = "%s_%d" % (base, k); k += 1
        names_seen.add(nm)
        rig.clips[nm] = rig.clip_from_worlds(nm, Wf, FPS, None, "FBX take '%s'" % st["name"])
    report["takes"] = [(k, round(c.duration, 3), c.frames) for k, c in rig.clips.items()]
    report["bones"] = rig.nb
    if any(objs[i]["type"] == "Geometry" and objs[i]["sub"] == "Shape" for i in objs):
        report.setdefault("warnings", []).append("blend shapes / morph targets found: NOT imported (limit)")
    if any(o["type"] == "Constraint" for o in objs.values()):
        report.setdefault("warnings", []).append("constraints found: NOT evaluated (bake them into the animation before export)")
    return rig


def _layer(g, lname, vname, iname, ncomp, ncp, ncorner):
    L = _kid(g, lname)
    if L is None:
        return None
    vals = _arr(L, vname)
    if vals is None:
        return None
    vals = vals.reshape(-1, ncomp)
    idx = _arr(L, iname, int)
    mp = _kid(L, "MappingInformationType"); rf = _kid(L, "ReferenceInformationType")
    mp = str(mp["props"][0]) if mp else "ByPolygonVertex"; rf = str(rf["props"][0]) if rf else "Direct"
    if rf == "IndexToDirect" and idx is not None:
        vals = vals[np.clip(idx, 0, len(vals) - 1)]
    out = None
    if mp in ("ByPolygonVertex",):
        if len(vals) >= ncorner:
            out = vals[:ncorner]
    elif mp in ("ByVertice", "ByVertex", "ByControlPoint"):
        if len(vals) >= ncp:
            out = ("cp", vals)
    if out is None:
        return None
    if ncomp == 2:
        if isinstance(out, tuple):
            out = ("cp", np.c_[out[1][:, 0], 1.0 - out[1][:, 1]])
        else:
            out = np.c_[out[:, 0], 1.0 - out[:, 1]]          # FBX v is bottom-up -> glTF top-down
    if isinstance(out, tuple):
        # control point attribute: expand per corner via PolygonVertexIndex
        PVI = _arr(g, "PolygonVertexIndex", int)
        cp = np.where(PVI < 0, ~PVI, PVI)
        return out[1][cp]
    return out


def _material(o, objs, kids_of, fbxpath, store, report):
    pr = o["props"]
    col = None
    for k in ("DiffuseColor", "Diffuse", "BaseColor", "Maya|baseColor"):
        if k in pr:
            try:
                col = [float(x) for x in pr[k][:3]]; break
            except (TypeError, ValueError):
                pass
    md = dict(name=o["name"], color=col or [0.75, 0.75, 0.75])
    for a, t, p in kids_of.get(o["id"], []):
        tx = objs.get(a)
        if not tx or tx["type"] != "Texture":
            continue
        if t == "OP" and not any(s in p.lower() for s in ("diffuse", "basecolor", "base_color", "base color")):
            continue
        img, fname = None, None
        for v, tt, _ in kids_of.get(a, []):
            vd = objs.get(v)
            if vd and vd["type"] == "Video":
                cont = _kid(vd["node"], "Content")
                if cont and cont["props"]:
                    raw = cont["props"][0]
                    if isinstance(raw, str):
                        try:
                            raw = base64.b64decode("".join(x for x in cont["props"] if isinstance(x, str)))
                        except Exception:
                            raw = b""
                    if raw:
                        try:
                            img = Image.open(io.BytesIO(bytes(raw))).convert("RGBA")
                        except Exception:
                            img = None
                for fk in ("RelativeFilename", "Filename", "FileName"):
                    k = _kid(vd["node"], fk)
                    if k and k["props"] and not fname:
                        fname = str(k["props"][0])
        for fk in ("RelativeFilename", "FileName", "Filename"):
            k = _kid(tx["node"], fk)
            if k and k["props"] and not fname:
                fname = str(k["props"][0])
        if img is None and fname:
            base = os.path.dirname(os.path.abspath(fbxpath))
            stem = os.path.splitext(fbxpath)[0]
            cands = [fname, os.path.join(base, fname), os.path.join(base, os.path.basename(fname.replace("\\", "/"))),
                     os.path.join(stem + ".fbm", os.path.basename(fname.replace("\\", "/"))),
                     os.path.join(base, "textures", os.path.basename(fname.replace("\\", "/")))]
            for c in cands:
                if c and os.path.isfile(c):
                    try:
                        img = Image.open(c).convert("RGBA"); break
                    except Exception:
                        pass
            if img is None:
                report.setdefault("warnings", []).append("texture '%s' not found next to the FBX: material colour used" % fname)
        if img is not None:
            if max(img.size) > 1024:
                img.thumbnail((1024, 1024))
            rel = "textures/%s.png" % re.sub(r"[^A-Za-z0-9_\-]+", "_", os.path.splitext(os.path.basename((fname or tx["name"]).replace("\\", "/")))[0] or "tex%d" % len(store))
            while rel in store:
                rel = rel[:-4] + "_b.png"
            store[rel] = img
            md["texture"] = rel
        break
    return md
