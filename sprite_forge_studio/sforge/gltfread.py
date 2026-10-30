"""glTF 2.0 / GLB reader -> normalized Rig (pure Python + numpy + Pillow).

Reads the first skin (joints, inverse bind matrices), every mesh primitive that uses it (or rigid meshes
under a joint), materials (baseColorFactor + baseColorTexture), TEXCOORD_0 / COLOR_0, and all animations
(translation / rotation / scale, LINEAR / STEP / CUBICSPLINE value part) sampled at 30 fps.
Not read: morph targets (blend shapes), KHR extensions beyond basic textures, multiple skins (first one).
"""
from __future__ import annotations
import base64
import io
import json
import os
import re
import struct
import numpy as np
from PIL import Image

from .rigrec import Rig, polar, m4, mats_from_quat, FPS

COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def read(path):
    data = open(path, "rb").read()
    if data[:4] == b"glTF":
        _, _, ln = struct.unpack_from("<III", data, 0)
        o = 12; gl = None; binc = b""
        while o < ln:
            cl, ct = struct.unpack_from("<II", data, o); o += 8
            chunk = data[o:o + cl]; o += cl
            if ct == 0x4E4F534A:
                gl = json.loads(chunk.decode("utf-8"))
            elif ct == 0x004E4942:
                binc = chunk
        bufs = []
        for i, b in enumerate(gl.get("buffers", [])):
            bufs.append(binc if "uri" not in b else _uri(b["uri"], path))
        return gl, bufs
    gl = json.loads(data.decode("utf-8"))
    return gl, [_uri(b.get("uri", ""), path) for b in gl.get("buffers", [])]


def _uri(u, path):
    if u.startswith("data:"):
        return base64.b64decode(u.split(",", 1)[1])
    from urllib.parse import unquote
    return open(os.path.join(os.path.dirname(os.path.abspath(path)), unquote(u)), "rb").read()


def accessor(gl, bufs, i):
    a = gl["accessors"][i]
    n = NCOMP[a["type"]]; dt = COMP[a["componentType"]]
    cnt = a["count"]
    if "bufferView" not in a:
        out = np.zeros((cnt, n), dt)
    else:
        bv = gl["bufferViews"][a["bufferView"]]
        raw = bufs[bv.get("buffer", 0)]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        isz = np.dtype(dt).itemsize
        stride = bv.get("byteStride", 0) or n * isz
        if stride == n * isz:
            out = np.frombuffer(raw, dt, cnt * n, off).reshape(cnt, n)
        else:
            out = np.stack([np.frombuffer(raw, dt, n, off + k * stride) for k in range(cnt)])
    out = out.astype(np.float64) if dt == np.float32 or a.get("normalized") else out.copy()
    if a.get("normalized") and dt != np.float32:
        out = out / float(np.iinfo(dt).max)
    if "sparse" in a:
        sp = a["sparse"]
        iv = gl["bufferViews"][sp["indices"]["bufferView"]]; vv = gl["bufferViews"][sp["values"]["bufferView"]]
        idt = COMP[sp["indices"]["componentType"]]
        idx = np.frombuffer(bufs[iv.get("buffer", 0)], idt, sp["count"], iv.get("byteOffset", 0) + sp["indices"].get("byteOffset", 0))
        val = np.frombuffer(bufs[vv.get("buffer", 0)], dt, sp["count"] * n, vv.get("byteOffset", 0) + sp["values"].get("byteOffset", 0)).reshape(-1, n)
        out = out.astype(np.float64); out[idx] = val
    return out


def node_local(nd, T=None, R=None, S=None):
    if "matrix" in nd and T is None and R is None and S is None:
        return np.asarray(nd["matrix"], float).reshape(4, 4).T
    if "matrix" in nd:
        M = np.asarray(nd["matrix"], float).reshape(4, 4).T
        t0 = M[:3, 3]; s0 = np.linalg.norm(M[:3, :3], axis=0); R0 = M[:3, :3] / s0
        T = t0 if T is None else T; S = s0 if S is None else S
        Rm = R0 if R is None else mats_from_quat(R)
    else:
        T = np.asarray(nd.get("translation", [0, 0, 0]), float) if T is None else T
        Rm = mats_from_quat(np.asarray(nd.get("rotation", [0, 0, 0, 1]), float) if R is None else R)
        S = np.asarray(nd.get("scale", [1, 1, 1]), float) if S is None else S
    M = np.eye(4); M[:3, :3] = Rm * S[None, :]; M[:3, 3] = T
    return M


def load(path, report=None):
    report = report if report is not None else {}
    gl, bufs = read(path)
    nodes = gl.get("nodes", [])
    parent = {}
    for i, nd in enumerate(nodes):
        for c in nd.get("children", []):
            parent[c] = i
    Lrest = [node_local(nd) for nd in nodes]

    def worlds(L):
        out = [None] * len(nodes)
        def w(i):
            if out[i] is None:
                p = parent.get(i)
                out[i] = L[i] if p is None else w(p) @ L[i]
            return out[i]
        for i in range(len(nodes)):
            w(i)
        return out
    Wrest = worlds(Lrest)
    skins = gl.get("skins", [])
    if len(skins) > 1:
        report.setdefault("warnings", []).append("%d skins: only the first is imported" % len(skins))
    mesh_nodes = [i for i, nd in enumerate(nodes) if "mesh" in nd]
    if skins:
        sk = skins[0]
        joints = list(sk["joints"])
        ibm = accessor(gl, bufs, sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1) if "inverseBindMatrices" in sk else np.array([np.eye(4)] * len(joints))
        skin_node = next((i for i in mesh_nodes if nodes[i].get("skin") == 0), None)
        G = Wrest[skin_node] if skin_node is not None else np.eye(4)
        Ginv = np.linalg.inv(G)
        bind_file = {j: np.linalg.inv(ibm[k]) for k, j in enumerate(joints)}
    else:
        # skeleton-only / animation-only file: every non-mesh node that is animated or has children
        anim_nodes = set()
        for an in gl.get("animations", []):
            for ch in an["channels"]:
                if "node" in ch["target"]:
                    anim_nodes.add(ch["target"]["node"])
        joints = [i for i, nd in enumerate(nodes) if "mesh" not in nd and (i in anim_nodes or nd.get("children"))]
        if not joints:
            joints = []
        Ginv = np.eye(4)
        bind_file = {j: Wrest[j] for j in joints}
    jset = set(joints)
    # order parents first
    def depth(i):
        d = 0
        while i in parent:
            i = parent[i]; d += 1
        return d
    order = sorted(joints, key=lambda j: (depth(j), joints.index(j)))
    bidx = {j: k for k, j in enumerate(order)}

    def bparent(j):
        p = parent.get(j)
        while p is not None and p not in jset:
            p = parent.get(p)
        return bidx[p] if p is not None else -1

    rig = Rig(os.path.splitext(os.path.basename(path))[0])
    rig.bones = [nodes[j].get("name") or "node%d" % j for j in order] or ["root"]
    # unique names
    seen = {}
    for k, b in enumerate(rig.bones):
        if b in seen:
            seen[b] += 1; rig.bones[k] = "%s_%d" % (b, seen[b])
        else:
            seen[b] = 0
    rig.parent = np.array([bparent(j) for j in order] or [-1], int)

    def norm(M):
        out = np.eye(4); out[:3, :3] = polar(M[:3, :3]); out[:3, 3] = M[:3, 3]
        return out
    rig.bind = np.array([norm(bind_file[j]) for j in order] if order else [np.eye(4)])
    # ---- meshes
    images = {}
    def image(ti):
        if ti in images:
            return images[ti]
        tex = gl["textures"][ti]; src = tex.get("source")
        img = None
        if src is not None:
            im = gl["images"][src]
            try:
                if "bufferView" in im:
                    bv = gl["bufferViews"][im["bufferView"]]
                    raw = bufs[bv.get("buffer", 0)][bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
                else:
                    raw = _uri(im["uri"], path)
                img = Image.open(io.BytesIO(bytes(raw))).convert("RGBA")
                if max(img.size) > 1024:
                    img.thumbnail((1024, 1024))
            except Exception as e:
                report.setdefault("warnings", []).append("texture %d unreadable (%s)" % (ti, e))
        images[ti] = (img, (gl["images"][src].get("name") or gl["images"][src].get("uri") or "tex%d" % ti) if src is not None else "tex%d" % ti)
        return images[ti]
    mats = []
    for k, m in enumerate(gl.get("materials", [])):
        pb = m.get("pbrMetallicRoughness", {})
        col = list(pb.get("baseColorFactor", [1, 1, 1, 1]))[:3]
        md = dict(name=m.get("name") or "mat%d" % k, color=[float(c) for c in col])
        if "baseColorTexture" in pb:
            img, nm = image(pb["baseColorTexture"]["index"])
            if img is not None:
                rel = "textures/%s.png" % (re.sub(r"[^A-Za-z0-9_\-]+", "_", os.path.splitext(os.path.basename(nm))[0]) or "tex")
                while rel in rig.textures:
                    rel = rel[:-4] + "_b.png"
                rig.textures[rel] = img; md["texture"] = rel
                if col != [1, 1, 1]:
                    md["tint_texture"] = True
        mats.append(md)
    if not mats:
        mats = [dict(name="default", color=[0.75, 0.75, 0.75])]
    rig.materials = mats
    Vs, Fs, Js, Ws, FM, FUV, FCOL = [], [], [], [], [], [], []
    have_uv = have_col = False
    voff = 0
    morph = False
    parts = []; foff = 0
    for ni in mesh_nodes:
        nd = nodes[ni]
        skinned = "skin" in nd and nd["skin"] == 0 and skins
        if "skin" in nd and nd["skin"] != 0:
            continue
        for pr in gl["meshes"][nd["mesh"]]["primitives"]:
            if pr.get("mode", 4) != 4:
                continue
            if pr.get("targets"):
                morph = True
            at = pr["attributes"]
            P = accessor(gl, bufs, at["POSITION"])[:, :3]
            idx = accessor(gl, bufs, pr["indices"]).reshape(-1).astype(int) if "indices" in pr else np.arange(len(P))
            F = idx.reshape(-1, 3)
            if skinned:
                Jv = accessor(gl, bufs, at["JOINTS_0"]).astype(int)
                Wv = accessor(gl, bufs, at["WEIGHTS_0"]).astype(float)
                Jv = np.vectorize(lambda k: bidx[joints[k]])(Jv) if len(Jv) else Jv
                s = Wv.sum(axis=1, keepdims=True); s[s == 0] = 1; Wv = Wv / s
                Pw = P          # skinned vertices are in bind space (IBM)
            else:
                Mw = Wrest[ni]
                Pw = (np.c_[P, np.ones(len(P))] @ Mw.T)[:, :3]
                p = ni
                while p is not None and p not in jset:
                    p = parent.get(p)
                Jv = np.zeros((len(P), 4), int); Jv[:, 0] = bidx[p] if p is not None else 0
                Wv = np.zeros((len(P), 4)); Wv[:, 0] = 1
                if p is not None and skins:
                    # rigid mesh under a joint: express in bind space
                    Pw = (np.c_[Pw, np.ones(len(Pw))] @ (bind_file[p] @ np.linalg.inv(Wrest[p])).T)[:, :3]
            Vs.append(Pw); Fs.append(F + voff); Js.append(Jv); Ws.append(Wv)
            pn = nd.get("name") or gl["meshes"][nd["mesh"]].get("name") or "mesh%d" % ni
            if parts and parts[-1]["node"] == ni:
                parts[-1]["f1"] = foff + len(F)
            else:
                parts.append(dict(name=pn, node=ni, f0=foff, f1=foff + len(F)))
            foff += len(F)
            FM.append(np.full(len(F), pr.get("material", 0) if gl.get("materials") else 0, int))
            if "TEXCOORD_0" in at:
                have_uv = True; FUV.append(accessor(gl, bufs, at["TEXCOORD_0"])[:, :2][F])
            else:
                FUV.append(np.zeros((len(F), 3, 2)))
            if "COLOR_0" in at:
                have_col = True; FCOL.append(accessor(gl, bufs, at["COLOR_0"])[:, :3][F])
            else:
                FCOL.append(np.ones((len(F), 3, 3)))
            voff += len(P)
    if morph:
        report.setdefault("warnings", []).append("morph targets (blend shapes) found: NOT imported (limit)")
    if Vs:
        rig.V = np.concatenate(Vs).astype(float); rig.F = np.concatenate(Fs); rig.J = np.concatenate(Js); rig.W = np.concatenate(Ws)
        rig.fmat = np.concatenate(FM)
        rig.fuv = np.concatenate(FUV) if have_uv else None
        rig.fcol = np.concatenate(FCOL) if have_col else None
        rig.meta["mesh_parts"] = [dict(name=p["name"], f0=int(p["f0"]), f1=int(p["f1"])) for p in parts]
    # ---- animations
    seen = set()
    for ai, an in enumerate(gl.get("animations", [])):
        ch_by = {}
        tmax = 0.0
        for ch in an["channels"]:
            nd = ch["target"].get("node"); path_ = ch["target"]["path"]
            if nd is None or path_ not in ("translation", "rotation", "scale"):
                continue
            sm = an["samplers"][ch["sampler"]]
            t = accessor(gl, bufs, sm["input"]).reshape(-1)
            v = accessor(gl, bufs, sm["output"])
            interp = sm.get("interpolation", "LINEAR")
            if interp == "CUBICSPLINE":
                v = v.reshape(len(t), 3, -1)[:, 1]
            ch_by.setdefault(nd, {})[path_] = (t, v, interp)
            tmax = max(tmax, float(t[-1]) if len(t) else 0)
        if not ch_by:
            continue
        nfr = max(1, int(round(tmax * FPS)) + 1)
        Wf = np.zeros((nfr, rig.nb, 4, 4))
        for f in range(nfr):
            tt = f / FPS
            L = list(Lrest)
            for ni, chs in ch_by.items():
                vals = {}
                for pth, (t, v, interp) in chs.items():
                    if interp == "STEP":
                        k = max(0, np.searchsorted(t, tt, side="right") - 1); val = v[k]
                    elif pth == "rotation":
                        k = np.searchsorted(t, tt)
                        if k <= 0:
                            val = v[0]
                        elif k >= len(t):
                            val = v[-1]
                        else:
                            a = (tt - t[k - 1]) / max(1e-9, t[k] - t[k - 1])
                            q0, q1 = v[k - 1], v[k]
                            if np.dot(q0, q1) < 0:
                                q1 = -q1
                            val = q0 * (1 - a) + q1 * a; val = val / (np.linalg.norm(val) + 1e-12)
                    else:
                        val = np.array([np.interp(tt, t, v[:, c]) for c in range(v.shape[1])])
                    vals[pth] = np.asarray(val, float)
                L[ni] = node_local(nodes[ni], vals.get("translation"), vals.get("rotation"), vals.get("scale"))
            Wd = worlds(L)
            for k, j in enumerate(order):
                Wf[f, k] = norm(Ginv @ Wd[j])
        nm = re.sub(r"[^A-Za-z0-9_\-]+", "_", (an.get("name") or "anim%d" % ai).split("|")[-1]).strip("_").lower() or "anim%d" % ai
        base = nm; k = 2
        while nm in seen:
            nm = "%s_%d" % (base, k); k += 1
        seen.add(nm)
        rig.clips[nm] = rig.clip_from_worlds(nm, Wf, FPS, None, "glTF animation '%s'" % an.get("name", ai))
    report["takes"] = [(k, round(c.duration, 3), c.frames) for k, c in rig.clips.items()]
    report["bones"] = rig.nb
    report["mesh"] = dict(tris=int(len(rig.F)), verts=int(len(rig.V)))
    return rig
