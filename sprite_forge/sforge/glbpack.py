"""Put a new skinned mesh into an existing character GLB, keeping its skeleton, skin and animations (v10.1).

    glbpack.pack(template_glb, out_glb, V, N, UV, F, joints, weights, texture_png_bytes)

Every node, the skin (joint order + inverse bind matrices) and every animation of the template are kept exactly;
the template's meshes, materials and images are dropped (their nodes too), and one primitive is added with
POSITION / NORMAL / TEXCOORD_0 / JOINTS_0 / WEIGHTS_0 and a baseColor texture.  The binary buffer is rebuilt so
nothing unused is carried over.  `joints` index the template skin's joint list."""
from __future__ import annotations
import json, struct
import numpy as np

COMP = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32, 5122: np.int16, 5120: np.int8}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    d = open(path, "rb").read()
    L = struct.unpack("<I", d[12:16])[0]; j = json.loads(d[20:20 + L]); o = 20 + L
    bl = struct.unpack("<I", d[o:o + 4])[0]
    return j, bytes(d[o + 8:o + 8 + bl])


def _acc_bytes(j, buf, i):
    a = j["accessors"][i]; bv = j["bufferViews"][a["bufferView"]]
    dt = COMP[a["componentType"]]; n = NCOMP[a["type"]]
    isz = np.dtype(dt).itemsize * n
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0); st = bv.get("byteStride", 0)
    if st and st != isz:
        return b"".join(buf[off + k * st: off + k * st + isz] for k in range(a["count"]))
    return buf[off: off + isz * a["count"]]


class _Out:
    def __init__(self):
        self.b = bytearray(); self.views = []; self.acc = []

    def view(self, data, target=None):
        while len(self.b) % 4:
            self.b.append(0)
        v = {"buffer": 0, "byteOffset": len(self.b), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.b += data; self.views.append(v)
        return len(self.views) - 1

    def add(self, arr, ctype, typ, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        a = {"bufferView": self.view(arr.tobytes(), target), "componentType": ctype, "type": typ, "count": int(arr.shape[0])}
        if minmax:
            a2 = arr.reshape(arr.shape[0], -1)
            a["min"] = [float(x) for x in a2.min(0)]; a["max"] = [float(x) for x in a2.max(0)]
        self.acc.append(a)
        return len(self.acc) - 1

    def copy_acc(self, j, buf, i):
        a = dict(j["accessors"][i]); data = _acc_bytes(j, buf, i)
        a["bufferView"] = self.view(data); a.pop("byteOffset", None); a.pop("sparse", None)
        self.acc.append(a)
        return len(self.acc) - 1


def pack(template, out_path, V, N, UV, F, joints, weights, png_bytes, name="player", extras=None):
    j, buf = read_glb(template)
    # ---- drop mesh nodes of the template, remap node indices everywhere
    drop = {i for i, nd in enumerate(j["nodes"]) if "mesh" in nd}
    keep = [i for i in range(len(j["nodes"])) if i not in drop]
    remap = {o: k for k, o in enumerate(keep)}
    nodes = []
    for o in keep:
        nd = dict(j["nodes"][o])
        if "children" in nd:
            nd["children"] = [remap[c] for c in nd["children"] if c in remap]
            if not nd["children"]:
                nd.pop("children")
        nd.pop("skin", None)
        nodes.append(nd)
    out = _Out()
    sk = dict(j["skins"][0])
    sk["joints"] = [remap[x] for x in sk["joints"]]
    if "skeleton" in sk:
        sk["skeleton"] = remap.get(sk["skeleton"], sk["joints"][0])
    sk["inverseBindMatrices"] = out.copy_acc(j, buf, j["skins"][0]["inverseBindMatrices"])
    anims = []
    for an in j.get("animations", []):
        sm = []
        for s in an["samplers"]:
            sm.append({"input": out.copy_acc(j, buf, s["input"]), "output": out.copy_acc(j, buf, s["output"]),
                       "interpolation": s.get("interpolation", "LINEAR")})
        ch = [{"sampler": c["sampler"], "target": {"node": remap[c["target"]["node"]], "path": c["target"]["path"]}}
              for c in an["channels"] if c["target"]["node"] in remap]
        anims.append({"name": an.get("name", "anim"), "channels": ch, "samplers": sm})
    # ---- the new mesh
    V = np.asarray(V, np.float32); N = np.asarray(N, np.float64); UV = np.asarray(UV, np.float32)
    F = np.asarray(F)
    # glTF requires unit normals: vertices that only touch degenerate triangles get their neighbours' average
    ln = np.linalg.norm(N, axis=1)
    bad = ln < 1e-6
    if bad.any():
        acc = np.zeros_like(N)
        for k in range(3):
            for c in range(3):
                np.add.at(acc, F[:, k], N[F[:, c]] * (~bad[F[:, c]])[:, None])
        N[bad] = acc[bad]
        ln = np.linalg.norm(N, axis=1)
        N[ln < 1e-6] = (0.0, 1.0, 0.0)
    N = (N / np.linalg.norm(N, axis=1, keepdims=True)).astype(np.float32)
    idx_t = (np.uint16, 5123) if len(V) < 65535 else (np.uint32, 5125)
    J = np.asarray(joints); jt = (np.uint8, 5121) if J.max() < 256 else (np.uint16, 5123)
    attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True), "NORMAL": out.add(N, 5126, "VEC3", 34962),
             "TEXCOORD_0": out.add(UV, 5126, "VEC2", 34962),
             "JOINTS_0": out.add(J.astype(jt[0]), jt[1], "VEC4", 34962),
             "WEIGHTS_0": out.add(np.asarray(weights, np.float32), 5126, "VEC4", 34962)}
    ind = out.add(F.astype(idx_t[0]).reshape(-1), idx_t[1], "SCALAR", 34963)
    img_view = out.view(png_bytes)
    mesh_node = {"name": name, "mesh": 0, "skin": 0}
    nodes.append(mesh_node)
    scene = dict(j["scenes"][j.get("scene", 0)])
    scene["nodes"] = [remap[n] for n in scene["nodes"] if n in remap] + [len(nodes) - 1]
    gl = {"asset": {"version": "2.0", "generator": "Sprite Forge glbpack (v10.1)"}, "scene": 0, "scenes": [scene],
          "nodes": nodes, "skins": [sk], "animations": anims,
          "meshes": [{"name": name, "primitives": [{"attributes": attrs, "indices": ind, "material": 0}]}],
          "materials": [{"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0,
                                                                "roughnessFactor": 1.0}}],
          "textures": [{"source": 0, "sampler": 0}], "samplers": [{"magFilter": 9729, "minFilter": 9987}],
          "images": [{"bufferView": img_view, "mimeType": "image/png", "name": "kit"}],
          "accessors": out.acc, "bufferViews": out.views, "buffers": [{"byteLength": 0}]}
    if extras:
        gl["asset"]["extras"] = extras
    b = out.b
    while len(b) % 4:
        b.append(0)
    gl["buffers"][0]["byteLength"] = len(b)
    js = json.dumps(gl, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    data = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(b)) + struct.pack("<II", len(js), 0x4E4F534A) + js + \
        struct.pack("<II", len(b), 0x004E4942) + bytes(b)
    open(out_path, "wb").write(data)
    return len(data)
