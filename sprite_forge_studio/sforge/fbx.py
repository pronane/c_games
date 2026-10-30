"""Pure-Python binary FBX 7.4 writer (and a small reader for self-checks).  No Blender, no FBX SDK.

write_fbx_from_glb(glb, fbx) converts a Sprite Forge GLB (as written by gltf.write_glb or scan.write_glb_mesh) to FBX:
  * skeleton   -> one "Null" model (Rig, becomes the armature in Blender / root in Unity) + LimbNode models
  * mesh       -> one Mesh model + Geometry (welded control points, per-polygon-vertex normals, optional
                  vertex colours, per-polygon material index) + one Material per glTF material
  * skin       -> Deformer "Skin" + one "Cluster" SubDeformer per bone with Indexes/Weights,
                  Transform (= inverse bind) and TransformLink (= bone bind matrix) + a BindPose
  * animation  -> one AnimationStack + AnimationLayer per glTF animation ("take"), with T/R/S
                  AnimationCurveNodes and linear (step for STEP samplers) AnimationCurves; quaternions are
                  converted to continuous XYZ Euler degrees.
Axis system Y-up / +Z front / right-handed (same as glTF), UnitScaleFactor 100 (= metres).
"""
from __future__ import annotations
import io
import json
import math
import struct
import zlib
import numpy as np

KTIME = 46186158000          # FBX time units per second
VERSION = 7400
_HEAD = b"Kaydara FBX Binary  \x00\x1a\x00"
_FOOT_ID = b"\xfa\xbc\xab\x09\xd0\xc8\xd4\x66\xb1\x76\xfb\x83\x1c\xf7\x26\x7e"
_FOOT_MAGIC = b"\xf8\x5a\x8c\x6a\xde\xf5\xd9\x7e\xec\xe9\x0c\xe3\x75\x8f\x29\x0b"
_ALWAYS_SENTINEL = {"AnimationStack", "AnimationLayer"}


# ======================================================================= low-level encoder
class N:
    """FBX node: name, props [(type, value)], children."""
    __slots__ = ("name", "props", "kids")

    def __init__(self, name, *props):
        self.name = name; self.props = list(props); self.kids = []

    def add(self, name, *props):
        n = N(name, *props); self.kids.append(n); return n

    # typed property helpers -------------------------------------------------
    def P(self, *args):
        """Properties70 entry: P(name, type, label, flags, *values) with python-typed values."""
        n = self.add("P", *[S(a) for a in args[:4]])
        typ = args[1]
        for v in args[4:]:
            if isinstance(v, str):
                n.props.append(S(v))
            elif typ in ("KTime",):
                n.props.append(("L", int(v)))
            elif typ in ("int", "enum", "bool", "Integer", "Bool", "Enum", "Visibility Inheritance") and not isinstance(v, float):
                n.props.append(("I", int(v)))
            else:
                n.props.append(("D", float(v)))
        return n


def S(v):
    return ("S", v.encode("utf-8") if isinstance(v, str) else v)


def I(v): return ("I", int(v))
def L(v): return ("L", int(v))
def D(v): return ("D", float(v))
def Y(v): return ("Y", int(v))
def C(v): return ("C", bool(v))
def R(v): return ("R", bytes(v))
def ai(a): return ("i", np.asarray(a, "<i4").ravel())
def al(a): return ("l", np.asarray(a, "<i8").ravel())
def ad(a): return ("d", np.asarray(a, "<f8").ravel())
def af(a): return ("f", np.asarray(a, "<f4").ravel())


def _enc_prop(t, v):
    if t == "S" or t == "R":
        return t.encode() + struct.pack("<I", len(v)) + v
    if t in "ilfdb":
        raw = np.ascontiguousarray(v).tobytes()
        if len(raw) > 128:
            z = zlib.compress(raw, 6)
            return t.encode() + struct.pack("<III", len(v), 1, len(z)) + z
        return t.encode() + struct.pack("<III", len(v), 0, len(raw)) + raw
    fmt = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}[t]
    return t.encode() + struct.pack(fmt, v)


def _write_node(f, n):
    start = f.tell()
    pbytes = b"".join(_enc_prop(t, v) for t, v in n.props)
    name = n.name.encode()
    f.write(struct.pack("<III", 0, len(n.props), len(pbytes))); f.write(struct.pack("<B", len(name))); f.write(name); f.write(pbytes)
    if n.kids or (not n.props) or n.name in _ALWAYS_SENTINEL:
        for k in n.kids:
            _write_node(f, k)
        f.write(b"\0" * 13)
    end = f.tell()
    f.seek(start); f.write(struct.pack("<I", end)); f.seek(end)


def write_nodes(path, nodes):
    f = io.BytesIO()
    f.write(_HEAD); f.write(struct.pack("<I", VERSION))
    for n in nodes:
        _write_node(f, n)
    f.write(b"\0" * 13)
    f.write(_FOOT_ID); f.write(b"\0" * 4)
    ofs = f.tell(); pad = ((ofs + 15) & ~15) - ofs
    f.write(b"\0" * (pad or 16)); f.write(struct.pack("<I", VERSION)); f.write(b"\0" * 120); f.write(_FOOT_MAGIC)
    with open(path, "wb") as fo:
        fo.write(f.getvalue())
    return path


# ======================================================================= reader (self-check)
def read_fbx(path):
    """-> list of top-level nodes as dicts {name, props, kids}.  Binary FBX 7.x (32- and 64-bit offsets)."""
    data = open(path, "rb").read()
    if not data.startswith(b"Kaydara FBX Binary"):
        raise ValueError("not a binary FBX: %s" % path)
    ver = struct.unpack_from("<I", data, 23)[0]
    wide = ver >= 7500
    hdr = struct.Struct("<QQQ" if wide else "<III")

    def prop(o):
        t = chr(data[o]); o += 1
        if t in "SR":
            n = struct.unpack_from("<I", data, o)[0]; o += 4
            v = data[o:o + n]; o += n
            return (v.decode("utf-8", "replace") if t == "S" else v), o
        if t in "ilfdb":
            n, enc, ln = struct.unpack_from("<III", data, o); o += 12
            raw = data[o:o + ln]; o += ln
            if enc == 1:
                raw = zlib.decompress(raw)
            dt = {"i": "<i4", "l": "<i8", "f": "<f4", "d": "<f8", "b": "?"}[t]
            return np.frombuffer(raw, dt, n), o
        fmt = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}[t]
        return struct.unpack_from(fmt, data, o)[0], o + struct.calcsize(fmt)

    def node(o):
        end, nprops, plen = hdr.unpack_from(data, o); o += hdr.size
        if end == 0:
            return None, o
        nl = data[o]; o += 1
        name = data[o:o + nl].decode(); o += nl
        props = []
        for _ in range(nprops):
            v, o = prop(o); props.append(v)
        kids = []
        while o < end:
            k, o = node(o)
            if k is None:
                break
            kids.append(k)
        return {"name": name, "props": props, "kids": kids}, end

    o = 27; out = []
    while o < len(data) - hdr.size:
        n, o = node(o)
        if n is None:
            break
        out.append(n)
    return out


def find(nodes, name):
    return [n for n in nodes if n["name"] == name]


def summary(path):
    """Counts read back by OUR reader: models by type, clusters, weights, stacks, curves, units."""
    top = read_fbx(path)
    objs = find(top, "Objects")[0]["kids"]
    conns = [tuple(c["props"][:3]) for c in find(find(top, "Connections")[0]["kids"], "C")]
    models = [o for o in objs if o["name"] == "Model"]
    by_id = {o["props"][0]: o for o in objs}
    gs = {p["props"][0]: p["props"][4:] for p in find(find(find(top, "GlobalSettings")[0]["kids"], "Properties70")[0]["kids"], "P")}
    clusters = [o for o in objs if o["name"] == "Deformer" and o["props"][2] == "Cluster"]
    nweights = 0
    for c in clusters:
        w = find(c["kids"], "Weights")
        nweights += len(w[0]["props"][0]) if w else 0
    stacks = [o["props"][1].split("\x00")[0] for o in objs if o["name"] == "AnimationStack"]
    geo = [o for o in objs if o["name"] == "Geometry"]
    nv = sum(len(find(g["kids"], "Vertices")[0]["props"][0]) // 3 for g in geo)
    npoly = sum(int((find(g["kids"], "PolygonVertexIndex")[0]["props"][0] < 0).sum()) for g in geo)
    return {"version": struct.unpack_from("<I", open(path, "rb").read(27), 23)[0],
            "limb_nodes": sum(1 for m in models if m["props"][2] == "LimbNode"),
            "meshes": sum(1 for m in models if m["props"][2] == "Mesh"),
            "control_points": nv, "polygons": npoly, "clusters": len(clusters), "skin_weights": nweights,
            "materials": sum(1 for o in objs if o["name"] == "Material"),
            "anim_stacks": stacks, "anim_curves": sum(1 for o in objs if o["name"] == "AnimationCurve"),
            "connections": len(conns), "unit_scale_factor": gs.get("UnitScaleFactor", [None])[0],
            "up_axis": gs.get("UpAxis", [None])[0], "bones": [m["props"][1].split("\x00")[0] for m in models if m["props"][2] == "LimbNode"],
            "_by_id": None and by_id}


# ======================================================================= GLB reader
_CT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    b = open(path, "rb").read()
    magic, ver, total = struct.unpack_from("<III", b, 0)
    if magic != 0x46546C67:
        raise ValueError("not a GLB: %s" % path)
    o = 12; js = None; binc = b""
    while o < len(b):
        ln, typ = struct.unpack_from("<II", b, o); o += 8
        if typ == 0x4E4F534A:
            js = json.loads(b[o:o + ln])
        elif typ == 0x004E4942:
            binc = b[o:o + ln]
        o += ln
    return js, binc


def accessor(gl, binc, i):
    a = gl["accessors"][i]; v = gl["bufferViews"][a["bufferView"]]
    nc = _NC[a["type"]]; dt = np.dtype(_CT[a["componentType"]])
    off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = v.get("byteStride", 0)
    if stride and stride != nc * dt.itemsize:
        rows = [np.frombuffer(binc, dt, nc, off + k * stride) for k in range(a["count"])]
        arr = np.stack(rows)
    else:
        arr = np.frombuffer(binc, dt, a["count"] * nc, off).reshape(a["count"], nc)
    if a.get("normalized") and dt.kind in "iu":
        arr = arr.astype(np.float64) / np.iinfo(dt).max
    return arr.squeeze(-1) if nc == 1 else arr


# ======================================================================= maths
def quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_euler_xyz(M):
    """FBX eEulerXYZ: R = Rz(c) Ry(b) Rx(a).  -> (a, b, c) radians."""
    sb = -M[2, 0]
    sb = max(-1.0, min(1.0, sb))
    b = math.asin(sb)
    if abs(sb) < 0.999999:
        a = math.atan2(M[2, 1], M[2, 2]); c = math.atan2(M[1, 0], M[0, 0])
    else:
        a = math.atan2(-M[1, 2], M[1, 1]); c = 0.0
    return np.array([a, b, c])


def euler_xyz_to_mat(e):
    a, b, c = e
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]]); Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def quats_to_euler_deg(qs):
    """continuous Euler track (picks the equivalent solution closest to the previous key, then unwraps)."""
    out = []
    prev = None
    for q in qs:
        e = mat_to_euler_xyz(quat_to_mat(np.asarray(q, float) / (np.linalg.norm(q) + 1e-12)))
        if prev is not None:
            alt = np.array([e[0] + math.pi, math.pi - e[1], e[2] + math.pi])
            best = None
            for cand in (e, alt):
                c2 = prev + (cand - prev + math.pi) % (2 * math.pi) - math.pi
                d = np.abs(c2 - prev).sum()
                if best is None or d < best[0]:
                    best = (d, c2)
            e = best[1]
        out.append(e); prev = e
    return np.degrees(np.array(out))


def _resample(ts0, v0, ts, is_q):
    out = np.empty((len(ts), v0.shape[1]))
    for k, t in enumerate(ts):
        i = int(np.clip(np.searchsorted(ts0, t, "right") - 1, 0, len(ts0) - 1))
        if i >= len(ts0) - 1 or t <= ts0[0]:
            out[k] = v0[min(i, len(ts0) - 1)] if t > ts0[0] else v0[0]; continue
        u = (t - ts0[i]) / max(ts0[i + 1] - ts0[i], 1e-12)
        a, b = v0[i], v0[i + 1]
        if is_q:
            if np.dot(a, b) < 0:
                b = -b
            d = np.clip(np.dot(a, b), -1, 1); th = math.acos(d)
            q = a * (1 - u) + b * u if th < 1e-6 else (math.sin((1 - u) * th) * a + math.sin(u * th) * b) / math.sin(th)
            out[k] = q / np.linalg.norm(q)
        else:
            out[k] = a * (1 - u) + b * u
    return out


def trs_matrix(t, r, s):
    M = np.eye(4)
    M[:3, :3] = quat_to_mat(r) * np.asarray(s, float)[None, :]
    M[:3, 3] = t
    return M


# ======================================================================= GLB -> FBX
def write_fbx_from_glb(glb_path, fbx_path, creator="Sprite Forge Studio"):
    gl, binc = read_glb(glb_path)
    nodes_gl = gl.get("nodes", [])
    parent = {}
    for i, nd in enumerate(nodes_gl):
        for k in nd.get("children", []):
            parent[k] = i
    nid = [1000000]

    def new_id():
        nid[0] += 1; return nid[0]

    objects = N("Objects"); conns = N("Connections")

    def OO(child, par):
        conns.add("C", S("OO"), L(child), L(par))

    def OP(child, par, prop):
        conns.add("C", S("OP"), L(child), L(par), S(prop))

    def local_trs(nd):
        return (np.array(nd.get("translation", [0, 0, 0]), float), np.array(nd.get("rotation", [0, 0, 0, 1]), float),
                np.array(nd.get("scale", [1, 1, 1]), float))

    def world(i):
        M = trs_matrix(*local_trs(nodes_gl[i]))
        while i in parent:
            i = parent[i]; M = trs_matrix(*local_trs(nodes_gl[i])) @ M
        return M

    def model(name, typ, t, r, s):
        mid = new_id()
        m = objects.add("Model", L(mid), S(name + "\x00\x01Model"), S(typ))
        m.add("Version", I(232))
        p = m.add("Properties70")
        p.P("RotationActive", "bool", "", "", 1)
        p.P("InheritType", "enum", "", "", 1)
        p.P("ScalingMax", "Vector3D", "Vector", "", 0.0, 0.0, 0.0)
        p.P("DefaultAttributeIndex", "int", "Integer", "", 0)
        p.P("Lcl Translation", "Lcl Translation", "", "A", *[float(x) for x in t])
        e = np.degrees(mat_to_euler_xyz(quat_to_mat(r)))
        p.P("Lcl Rotation", "Lcl Rotation", "", "A", *[float(x) for x in e])
        p.P("Lcl Scaling", "Lcl Scaling", "", "A", *[float(x) for x in s])
        if typ == "LimbNode":
            p.P("Size", "double", "Number", "", 1.0)
        m.add("MultiLayer", I(0)); m.add("MultiTake", I(0))
        m.add("Shading", C(True)); m.add("Culling", S("CullingOff"))
        return mid

    skins = gl.get("skins", [])
    joint_set = set(skins[0]["joints"]) if skins else set()
    if not joint_set and not gl.get("meshes") and gl.get("animations"):
        # skeleton-only GLB (animation-only library asset): every node is a bone
        joint_set = {i for i, nd in enumerate(nodes_gl) if "mesh" not in nd and "camera" not in nd}
    model_of = {}
    stats = {"bones": 0, "clusters": 0, "weights": 0, "takes": [], "curves": 0}
    # ---------------------------------------------------------------- skeleton
    rig_id = None
    if joint_set:
        roots = [j for j in joint_set if parent.get(j) not in joint_set]
        rig_id = model("Rig", "Null", (0, 0, 0), (0, 0, 0, 1), (1, 1, 1))
        att = new_id(); a = objects.add("NodeAttribute", L(att), S("Rig\x00\x01NodeAttribute"), S("Null"))
        a.add("TypeFlags", S("Null")); OO(att, rig_id); OO(rig_id, 0)

        def add_bone(j, par_id):
            nd = nodes_gl[j]
            mid = model(nd.get("name", "bone%d" % j), "LimbNode", *local_trs(nd))
            att = new_id(); a = objects.add("NodeAttribute", L(att), S(nd.get("name", "") + "\x00\x01NodeAttribute"), S("LimbNode"))
            a.add("Properties70").P("Size", "double", "Number", "", 1.0); a.add("TypeFlags", S("Skeleton"))
            OO(att, mid); OO(mid, par_id); model_of[j] = mid; stats["bones"] += 1
            for k in nd.get("children", []):
                if k in joint_set:
                    add_bone(k, mid)
        for r in roots:
            add_bone(r, rig_id)
    # ---------------------------------------------------------------- mesh(es)
    pose_entries = []
    for ni, nd in enumerate(nodes_gl):
        if "mesh" not in nd:
            continue
        me = gl["meshes"][nd["mesh"]]
        P_, Nn, J_, W_, Cc, mat_idx, tris, UVs = [], [], [], [], [], [], [], []
        base = 0
        mats_used = []
        for pr in me["primitives"]:
            at = pr["attributes"]
            pos = accessor(gl, binc, at["POSITION"]).astype(np.float64)
            nor = accessor(gl, binc, at["NORMAL"]).astype(np.float64) if "NORMAL" in at else None
            jn = accessor(gl, binc, at["JOINTS_0"]).astype(np.int64) if "JOINTS_0" in at else None
            wt = accessor(gl, binc, at["WEIGHTS_0"]).astype(np.float64) if "WEIGHTS_0" in at else None
            col = accessor(gl, binc, at["COLOR_0"]).astype(np.float64) if "COLOR_0" in at else None
            idx = accessor(gl, binc, pr["indices"]).astype(np.int64) if "indices" in pr else np.arange(len(pos))
            mi = pr.get("material", -1)
            if mi not in mats_used:
                mats_used.append(mi)
            t = idx.reshape(-1, 3)
            tris.append(t + base); mat_idx.append(np.full(len(t), mats_used.index(mi)))
            P_.append(pos); Nn.append(nor if nor is not None else np.zeros_like(pos))
            J_.append(jn if jn is not None else np.zeros((len(pos), 4), np.int64))
            W_.append(wt if wt is not None else np.zeros((len(pos), 4)))
            if col is not None and col.shape[1] == 3:
                col = np.concatenate([col, np.ones((len(col), 1))], 1)
            Cc.append(col)
            UVs.append(accessor(gl, binc, at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(pos), 2)))
            base += len(pos)
        P_ = np.concatenate(P_); Nn = np.concatenate(Nn); J_ = np.concatenate(J_); W_ = np.concatenate(W_)
        tris = np.concatenate(tris); mat_idx = np.concatenate(mat_idx)
        if "skin" not in nd:                               # static mesh: bake the node's world transform
            Mw = world(ni)
            P_ = P_ @ Mw[:3, :3].T + Mw[:3, 3]
            Nn = Nn @ np.linalg.inv(Mw[:3, :3])
            Nn /= np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-12
        has_col = all(c is not None for c in Cc)
        Cc = np.concatenate(Cc) if has_col else None
        # weld control points (same position + same skin)
        key = np.concatenate([np.round(P_ * 1e5), J_, np.round(W_ * 1e4)], 1)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.ravel()
        V = P_[first]
        cp = inv[tris]                                     # (T,3) control point per corner
        pvi = cp.copy(); pvi[:, 2] = -pvi[:, 2] - 1        # last index of each polygon is bit-negated
        corner = tris.ravel()
        gid = new_id()
        g = objects.add("Geometry", L(gid), S(me.get("name", "mesh") + "\x00\x01Geometry"), S("Mesh"))
        g.add("Properties70")
        g.add("GeometryVersion", I(124))
        g.add("Vertices", ad(V))
        g.add("PolygonVertexIndex", ai(pvi))
        le = g.add("LayerElementNormal", I(0)); le.add("Version", I(101)); le.add("Name", S(""))
        le.add("MappingInformationType", S("ByPolygonVertex")); le.add("ReferenceInformationType", S("Direct"))
        le.add("Normals", ad(Nn[corner]))
        layer_elems = [("LayerElementNormal", 0)]
        if has_col:
            le = g.add("LayerElementColor", I(0)); le.add("Version", I(101)); le.add("Name", S("Col"))
            le.add("MappingInformationType", S("ByPolygonVertex")); le.add("ReferenceInformationType", S("IndexToDirect"))
            le.add("Colors", ad(np.clip(Cc[corner], 0, 1))); le.add("ColorIndex", ai(np.arange(len(corner))))
            layer_elems.append(("LayerElementColor", 0))
        tex_mats = [mi for mi in mats_used if mi >= 0 and "baseColorTexture" in gl["materials"][mi].get("pbrMetallicRoughness", {})]
        if tex_mats:                                       # v6: UVs + embedded textures (FBX v = 1 - glTF v)
            UV = np.concatenate(UVs)[corner].copy(); UV[:, 1] = 1.0 - UV[:, 1]
            le = g.add("LayerElementUV", I(0)); le.add("Version", I(101)); le.add("Name", S("UVMap"))
            le.add("MappingInformationType", S("ByPolygonVertex")); le.add("ReferenceInformationType", S("IndexToDirect"))
            le.add("UV", ad(UV)); le.add("UVIndex", ai(np.arange(len(corner))))
            layer_elems.append(("LayerElementUV", 0))
        le = g.add("LayerElementMaterial", I(0)); le.add("Version", I(101)); le.add("Name", S(""))
        le.add("MappingInformationType", S("ByPolygon")); le.add("ReferenceInformationType", S("IndexToDirect"))
        le.add("Materials", ai(mat_idx))
        layer_elems.append(("LayerElementMaterial", 0))
        lay = g.add("Layer", I(0)); lay.add("Version", I(100))
        for t, k in layer_elems:
            e = lay.add("LayerElement"); e.add("Type", S(t)); e.add("TypedIndex", I(k))
        mname = nd.get("name", me.get("name", "Mesh"))
        mid = model(mname, "Mesh", (0, 0, 0), (0, 0, 0, 1), (1, 1, 1))   # skinned meshes ignore node TRS (glTF rule)
        mesh_world = np.eye(4)
        OO(gid, mid); OO(mid, 0)
        pose_entries.append((mid, mesh_world))
        for mi in mats_used:
            md = gl["materials"][mi] if mi >= 0 else {"name": "default"}
            c = md.get("pbrMetallicRoughness", {}).get("baseColorFactor", [0.8, 0.8, 0.8, 1])
            if has_col:
                c = [1.0, 1.0, 1.0, 1.0]
            maid = new_id()
            ma = objects.add("Material", L(maid), S(md.get("name", "mat") + "\x00\x01Material"), S(""))
            ma.add("Version", I(102)); ma.add("ShadingModel", S("lambert")); ma.add("MultiLayer", I(0))
            p = ma.add("Properties70")
            p.P("DiffuseColor", "Color", "", "A", *[float(x) for x in c[:3]])
            p.P("DiffuseFactor", "Number", "", "A", 1.0)
            p.P("AmbientColor", "Color", "", "A", 0.0, 0.0, 0.0)
            p.P("Opacity", "double", "Number", "", float(c[3]) if len(c) > 3 else 1.0)
            OO(maid, mid)
            bct = md.get("pbrMetallicRoughness", {}).get("baseColorTexture") if mi >= 0 else None
            if bct is not None:
                im = gl["images"][gl["textures"][bct["index"]]["source"]]
                bv = gl["bufferViews"][im["bufferView"]]
                data = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
                fn = (im.get("name") or "tex%d" % bct["index"]).replace("/", "_")
                if not fn.lower().endswith(".png"):
                    fn += ".png"
                vid, tid = new_id(), new_id()
                vi = objects.add("Video", L(vid), S(fn + "\x00\x01Video"), S("Clip"))
                vi.add("Type", S("Clip"))
                vp = vi.add("Properties70"); vp.P("Path", "KString", "XRefUrl", "", fn)
                vi.add("UseMipMap", I(0)); vi.add("Filename", S(fn)); vi.add("RelativeFilename", S(fn)); vi.add("Content", R(data))
                tx = objects.add("Texture", L(tid), S(fn + "\x00\x01Texture"), S(""))
                tx.add("Type", S("TextureVideoClip")); tx.add("Version", I(202)); tx.add("TextureName", S(fn + "\x00\x01Texture"))
                tp = tx.add("Properties70"); tp.P("UVSet", "KString", "", "", "UVMap"); tp.P("UseMaterial", "bool", "", "", 1)
                tx.add("Media", S(fn + "\x00\x01Video")); tx.add("FileName", S(fn)); tx.add("RelativeFilename", S(fn))
                tx.add("ModelUVTranslation", D(0.0), D(0.0)); tx.add("ModelUVScaling", D(1.0), D(1.0))
                tx.add("Texture_Alpha_Source", S("None")); tx.add("Cropping", I(0), I(0), I(0), I(0))
                OO(vid, tid); OP(tid, maid, "DiffuseColor")
                stats["textures"] = stats.get("textures", 0) + 1
        # skin
        if "skin" in nd and joint_set:
            sk = skins[nd["skin"]]
            ibm = accessor(gl, binc, sk["inverseBindMatrices"]).astype(np.float64) if "inverseBindMatrices" in sk else None
            skid = new_id()
            d = objects.add("Deformer", L(skid), S("Skin\x00\x01Deformer"), S("Skin"))
            d.add("Version", I(101)); d.add("Link_DeformAcuracy", D(50.0))
            OO(skid, gid)
            Vj = J_[first]; Vw = W_[first]
            for k, j in enumerate(sk["joints"]):
                sel = (Vj == k) & (Vw > 0)
                vid = np.nonzero(sel.any(1))[0]
                w = (Vw * sel).sum(1)[vid]
                ibm_k = ibm[k].reshape(4, 4).T if ibm is not None else np.linalg.inv(world(j))   # row-major
                bind = np.linalg.inv(ibm_k)
                pose_entries.append((model_of[j], bind))
                if not len(vid):
                    continue
                cid = new_id()
                c = objects.add("Deformer", L(cid), S(nodes_gl[j].get("name", "") + "\x00\x01SubDeformer"), S("Cluster"))
                c.add("Version", I(100)); c.add("UserData", S(""), S(""))
                c.add("Indexes", ai(vid)); c.add("Weights", ad(w))
                c.add("Transform", ad((ibm_k @ mesh_world).T.ravel()))       # column-major like Blender/FBX SDK
                c.add("TransformLink", ad(bind.T.ravel()))
                OO(cid, skid); OO(model_of[j], cid)
                stats["clusters"] += 1; stats["weights"] += len(vid)
    if pose_entries:
        pid = new_id()
        po = objects.add("Pose", L(pid), S("BindPose\x00\x01Pose"), S("BindPose"))
        po.add("Type", S("BindPose")); po.add("Version", I(100)); po.add("NbPoseNodes", I(len(pose_entries)))
        for m_id, M in pose_entries:
            pn = po.add("PoseNode"); pn.add("Node", L(m_id)); pn.add("Matrix", ad(M.T.ravel()))
    # ---------------------------------------------------------------- animation takes
    t_max_all = 0.0
    for an in gl.get("animations", []):
        tname = an.get("name", "take")
        times_all = []
        stid = new_id(); lyid = new_id()
        st = objects.add("AnimationStack", L(stid), S(tname + "\x00\x01AnimStack"), S(""))
        ly = objects.add("AnimationLayer", L(lyid), S(tname + "\x00\x01AnimLayer"), S(""))
        OO(lyid, stid)
        bynode = {}
        for ch in an["channels"]:
            tgt = ch["target"]
            bynode.setdefault(tgt["node"], {})[tgt["path"]] = an["samplers"][ch["sampler"]]
        dur = max((float(accessor(gl, binc, s_["input"]).max()) for p_ in bynode.values() for s_ in p_.values()), default=0.0)
        # key grid = the GLB's own keys + an exact 30 fps grid, so every reader that bakes at 30/60 fps hits real keys
        grid = np.unique(np.round(np.concatenate([np.arange(0, dur + 1e-9, 1 / 30.0), [dur]] +
                                                  [accessor(gl, binc, s_["input"]).astype(np.float64).ravel()
                                                   for p_ in bynode.values() for s_ in p_.values()]), 6))
        for node_i in model_of:              # every bone gets T and R curves in every take (missing = rest pose),
            nd = nodes_gl[node_i]            # so switching takes in an engine never leaves a bone in the old pose
            paths = dict(bynode.get(node_i, {}))
            for path in ("translation", "rotation"):
                paths.setdefault(path, None)
            for path, smp in paths.items():
                if smp is None:
                    rest = np.array(nd.get(path, [0, 0, 0] if path == "translation" else [0, 0, 0, 1]), np.float64)
                    ts = np.array([0.0, max(dur, 1 / 30.0)]); vals = np.stack([rest, rest]); interp = "LINEAR"
                else:
                    ts0 = accessor(gl, binc, smp["input"]).astype(np.float64).ravel()
                    v0 = accessor(gl, binc, smp["output"]).astype(np.float64)
                    interp = smp.get("interpolation", "LINEAR")
                    if interp == "CUBICSPLINE":
                        v0 = v0.reshape(len(ts0), 3, -1)[:, 1]; interp = "LINEAR"
                    ts = grid[grid <= ts0.max() + 1e-6] if interp == "LINEAR" else ts0
                    vals = _resample(ts0, v0, ts, path == "rotation") if interp == "LINEAR" else v0
                times_all.append(ts)
                if path == "rotation":
                    vals = quats_to_euler_deg(vals); cn, prop = "R", "Lcl Rotation"
                elif path == "translation":
                    cn, prop = "T", "Lcl Translation"
                elif path == "scale":
                    cn, prop = "S", "Lcl Scaling"
                else:
                    continue
                cnid = new_id()
                cnode = objects.add("AnimationCurveNode", L(cnid), S(cn + "\x00\x01AnimCurveNode"), S(""))
                p = cnode.add("Properties70")
                for ax in range(3):
                    p.P("d|" + "XYZ"[ax], "Number", "", "A", float(vals[0, ax]))
                OO(cnid, lyid); OP(cnid, model_of[node_i], prop)
                kt = np.round(ts * KTIME).astype(np.int64)
                flag = 0x2 if interp == "STEP" else 0x4
                for ax in range(3):
                    cid = new_id()
                    cu = objects.add("AnimationCurve", L(cid), S("\x00\x01AnimCurve"), S(""))
                    cu.add("Default", D(float(vals[0, ax]))); cu.add("KeyVer", I(4009))
                    cu.add("KeyTime", al(kt)); cu.add("KeyValueFloat", af(vals[:, ax]))
                    cu.add("KeyAttrFlags", ai([flag])); cu.add("KeyAttrDataFloat", af([0, 0, 0, 0]))
                    cu.add("KeyAttrRefCount", ai([len(kt)]))
                    OP(cid, cnid, "d|" + "XYZ"[ax]); stats["curves"] += 1
        t1 = max((float(t.max()) for t in times_all), default=0.0); t_max_all = max(t_max_all, t1)
        p = st.add("Properties70")
        for k in ("LocalStart", "ReferenceStart"):
            p.P(k, "KTime", "Time", "", 0)
        for k in ("LocalStop", "ReferenceStop"):
            p.P(k, "KTime", "Time", "", int(round(t1 * KTIME)))
        stats["takes"].append((tname, round(t1, 3)))
    # ---------------------------------------------------------------- header / settings / definitions
    hx = N("FBXHeaderExtension")
    hx.add("FBXHeaderVersion", I(1003)); hx.add("FBXVersion", I(VERSION)); hx.add("EncryptionType", I(0))
    ts = hx.add("CreationTimeStamp")
    for k, v in (("Version", 1000), ("Year", 2026), ("Month", 1), ("Day", 1), ("Hour", 0), ("Minute", 0), ("Second", 0), ("Millisecond", 0)):
        ts.add(k, I(v))
    hx.add("Creator", S(creator))
    si = hx.add("SceneInfo", S("GlobalInfo\x00\x01SceneInfo"), S("UserData"))
    si.add("Type", S("UserData")); si.add("Version", I(100))
    mi = si.add("MetaData"); mi.add("Version", I(100))
    for k in ("Title", "Subject", "Author", "Keywords", "Revision", "Comment"):
        mi.add(k, S(""))
    gs = N("GlobalSettings"); gs.add("Version", I(1000)); p = gs.add("Properties70")
    for k, v in (("UpAxis", 1), ("UpAxisSign", 1), ("FrontAxis", 2), ("FrontAxisSign", 1), ("CoordAxis", 0), ("CoordAxisSign", 1),
                 ("OriginalUpAxis", 1), ("OriginalUpAxisSign", 1)):
        p.P(k, "int", "Integer", "", v)
    p.P("UnitScaleFactor", "double", "Number", "", 100.0); p.P("OriginalUnitScaleFactor", "double", "Number", "", 100.0)
    p.P("AmbientColor", "ColorRGB", "Color", "", 0.0, 0.0, 0.0)
    p.P("DefaultCamera", "KString", "", "", "Producer Perspective")
    p.P("TimeMode", "enum", "", "", 6); p.P("TimeProtocol", "enum", "", "", 2); p.P("SnapOnFrameMode", "enum", "", "", 0)
    p.P("TimeSpanStart", "KTime", "Time", "", 0); p.P("TimeSpanStop", "KTime", "Time", "", int(round(max(t_max_all, 1.0) * KTIME)))
    p.P("CustomFrameRate", "double", "Number", "", -1.0)
    docs = N("Documents"); docs.add("Count", I(1))
    doc = docs.add("Document", L(new_id()), S(""), S("Scene")); dp = doc.add("Properties70")
    dp.P("SourceObject", "object", "", ""); dp.P("ActiveAnimStackName", "KString", "", "", stats["takes"][0][0] if stats["takes"] else "")
    doc.add("RootNode", L(0))
    refs = N("References")
    counts = {}
    for o in objects.kids:
        counts[o.name] = counts.get(o.name, 0) + 1
    defs = N("Definitions"); defs.add("Version", I(100)); defs.add("Count", I(sum(counts.values()) + 1))
    ot = defs.add("ObjectType", S("GlobalSettings")); ot.add("Count", I(1))
    for k, v in counts.items():
        ot = defs.add("ObjectType", S(k)); ot.add("Count", I(v))
    takes = N("Takes"); takes.add("Current", S(stats["takes"][0][0] if stats["takes"] else ""))
    for tname, t1 in stats["takes"]:
        tk = takes.add("Take", S(tname)); tk.add("FileName", S(tname + ".tak"))
        tk.add("LocalTime", L(0), L(int(round(t1 * KTIME)))); tk.add("ReferenceTime", L(0), L(int(round(t1 * KTIME))))
    fid = N("FileId", R(b"\x28\xb3\x2a\xeb\xb6\x24\xcc\xc2\xbf\xc8\xb0\x2a\xa9\x2b\xfc\xf1"))
    ctime = N("CreationTime", S("1970-01-01 10:00:00:000")); cr = N("Creator", S(creator))
    write_nodes(fbx_path, [hx, fid, ctime, cr, gs, docs, refs, defs, objects, conns, takes])
    return stats
