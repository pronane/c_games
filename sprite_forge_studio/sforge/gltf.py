"""Pure-python GLB (glTF 2.0 binary) writer: skinned low-poly mannequin,
one material per colour, one animation clip per move (baked at 30 fps).
No external dependencies beyond numpy."""
from __future__ import annotations
import json
import struct
import numpy as np
from .rig import JOINT_NAMES, PARENT, OFFSET, rest_world
from .mesh import MATS
from .anim import sample_times
from .rig import evaluate
from .mathutil import quat_from_matrix

BAKE_FPS = 30


class _Buf:
    def __init__(self):
        self.data = bytearray(); self.views = []; self.accessors = []

    def add(self, arr, comp, typ, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        while len(self.data) % 4:
            self.data.append(0)
        off = len(self.data)
        self.data += arr.tobytes()
        v = {"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes}
        if target:
            v["target"] = target
        self.views.append(v)
        count = arr.shape[0]
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": count, "type": typ}
        if minmax:
            a2 = arr.reshape(count, -1)
            acc["min"] = [float(x) for x in a2.min(axis=0)]
            acc["max"] = [float(x) for x in a2.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _clip_states(motion, frames, fps, loop):
    dur = (frames if loop else max(1, frames - 1)) / float(fps)
    n = max(2, int(round(dur * BAKE_FPS)) + (0 if loop else 1))
    ts = [i / n for i in range(n + 1)] if loop else [i / (n - 1) for i in range(n)]
    times = [t * dur for t in ts]
    states = []
    for t in ts:
        pose, mix = motion.sample(t % 1.0 if (loop and t >= 1.0) else t)
        states.append(evaluate(pose, mix))
    return times, states


def write_glb(path, T, B, Mt, colours, clips, scale=1.0, name="Mannequin", extras=None, slots="full"):
    """clips: list of (clip_name, Motion, frames, fps, loop)."""
    s = float(scale)
    buf = _Buf()
    J = rest_world()
    ball_i = JOINT_NAMES.index("ball")
    # ---- geometry (flat shaded, un-indexed)
    P = T.copy()
    is_ball = B == ball_i
    P[~is_ball] *= s
    P[is_ball] = (P[is_ball] - J["ball"]) + J["ball"] * s
    e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
    N = np.cross(e1, e2); N /= (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
    from .matslots import mannequin_name
    prims, materials, mat_ix = [], [], {}
    for mi, mname in enumerate(MATS):
        sel = Mt == mi
        if not sel.any():
            continue
        pos = P[sel].reshape(-1, 3).astype(np.float32)
        nor = np.repeat(N[sel], 3, axis=0).astype(np.float32)
        jnt = np.zeros((pos.shape[0], 4), np.uint8); jnt[:, 0] = np.repeat(B[sel], 3)
        wgt = np.zeros((pos.shape[0], 4), np.float32); wgt[:, 0] = 1
        a_pos = buf.add(pos, 5126, "VEC3", 34962, True)
        a_nor = buf.add(nor, 5126, "VEC3", 34962)
        a_j = buf.add(jnt, 5121, "VEC4", 34962)
        a_w = buf.add(wgt, 5126, "VEC4", 34962)
        slot = mannequin_name(mname, slots)            # v7: engine material slots Skin_Mat / Jersey_Mat / ...
        if slot not in mat_ix:
            c = colours.get(mname, (0.7, 0.7, 0.7))
            mat_ix[slot] = len(materials)
            materials.append({"name": slot, "pbrMetallicRoughness": {"baseColorFactor": [c[0], c[1], c[2], 1.0],
                                                                     "metallicFactor": 0.0, "roughnessFactor": 0.85},
                              "extras": {"sforge_part": mname}})
        prims.append({"attributes": {"POSITION": a_pos, "NORMAL": a_nor, "JOINTS_0": a_j, "WEIGHTS_0": a_w},
                      "material": mat_ix[slot]})
    # ---- skeleton nodes
    nodes = []
    for n in JOINT_NAMES:
        node = {"name": n, "translation": [float(x) * s for x in OFFSET[n]]}
        kids = [JOINT_NAMES.index(k) for k in JOINT_NAMES if PARENT[k] == n]
        if kids:
            node["children"] = kids
        nodes.append(node)
    ibm = np.stack([np.linalg.inv(np.array([[1, 0, 0, J[n][0] * s], [0, 1, 0, J[n][1] * s], [0, 0, 1, J[n][2] * s], [0, 0, 0, 1]])).T
                    for n in JOINT_NAMES]).astype(np.float32)  # column-major
    a_ibm = buf.add(ibm.reshape(len(JOINT_NAMES), 16), 5126, "MAT4")
    mesh_node = len(nodes)
    nodes.append({"name": name, "mesh": 0, "skin": 0})
    # ---- animations
    anims = []
    for cname, motion, frames, fps, loop in clips:
        times, states = _clip_states(motion, frames, fps, loop)
        a_t = buf.add(np.array(times, np.float32).reshape(-1, 1), 5126, "SCALAR", None, True)
        samplers, channels = [], []
        for ji, jn in enumerate(JOINT_NAMES):
            if jn == "ball":
                continue
            q = np.stack([quat_from_matrix(st.local_R[jn]) for st in states])
            for i in range(1, len(q)):
                if np.dot(q[i], q[i - 1]) < 0:
                    q[i] = -q[i]
            if np.allclose(q, q[0], atol=1e-6) and jn != "hips":
                if np.allclose(q[0], [0, 0, 0, 1], atol=1e-6):
                    continue
            samplers.append({"input": a_t, "output": buf.add(q.astype(np.float32), 5126, "VEC4"), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": ji, "path": "rotation"}})
        rt = np.stack([st.root_t * s for st in states]).astype(np.float32)
        samplers.append({"input": a_t, "output": buf.add(rt, 5126, "VEC3"), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": 0, "path": "translation"}})
        bt, bs = [], []
        for st in states:
            if st.ball_pos is None:
                bt.append(OFFSET["ball"] * s); bs.append((0.001, 0.001, 0.001))
            else:
                bt.append((st.ball_pos - st.root_t) * s); bs.append((1, 1, 1))
        samplers.append({"input": a_t, "output": buf.add(np.array(bt, np.float32), 5126, "VEC3"), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": ball_i, "path": "translation"}})
        samplers.append({"input": a_t, "output": buf.add(np.array(bs, np.float32), 5126, "VEC3"), "interpolation": "STEP"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": ball_i, "path": "scale"}})
        anims.append({"name": cname, "samplers": samplers, "channels": channels})
    gl = {
        "asset": {"version": "2.0", "generator": "Sprite Forge Studio (procedural mannequin)"},
        "scene": 0, "scenes": [{"nodes": [0, mesh_node]}], "nodes": nodes,
        "meshes": [{"name": name, "primitives": prims}],
        "skins": [{"name": name + "_skin", "joints": list(range(len(JOINT_NAMES))), "inverseBindMatrices": a_ibm, "skeleton": 0}],
        "materials": materials, "animations": anims,
        "accessors": buf.accessors, "bufferViews": buf.views, "buffers": [{"byteLength": len(buf.data)}],
    }
    if extras:
        gl["asset"]["extras"] = extras
    js = json.dumps(gl, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    while len(buf.data) % 4:
        buf.data.append(0)
    total = 12 + 8 + len(js) + 8 + len(buf.data)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(buf.data), 0x004E4942)); f.write(bytes(buf.data))
    return path
