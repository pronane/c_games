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


def _sparse_target(buf, D, eps=1e-7):
    """morph target as a SPARSE accessor (only the moved vertices are stored; an unmoved part = all zeros)"""
    n = D.shape[0]
    idx = np.nonzero(np.abs(D).max(axis=1) > eps)[0].astype(np.uint32)
    acc = {"componentType": 5126, "count": int(n), "type": "VEC3", "min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    if len(idx):
        vals = D[idx]
        full = D.astype(np.float32).copy(); full[np.setdiff1d(np.arange(n), idx)] = 0.0
        acc["min"] = [float(x) for x in full.min(axis=0)]
        acc["max"] = [float(x) for x in full.max(axis=0)]
        def view(arr):
            arr = np.ascontiguousarray(arr)
            while len(buf.data) % 4:
                buf.data.append(0)
            off = len(buf.data); buf.data += arr.tobytes()
            buf.views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes})
            return len(buf.views) - 1
        acc["sparse"] = {"count": int(len(idx)), "indices": {"bufferView": view(idx), "componentType": 5125},
                         "values": {"bufferView": view(vals.astype(np.float32))}}
    buf.accessors.append(acc)
    return len(buf.accessors) - 1


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


def write_glb(path, T, B, Mt, colours, clips, scale=1.0, name="Mannequin", extras=None, slots="full",
              morphs=None, morph_tracks=None, chains=None, bake=False):
    """clips: list of (clip_name, Motion, frames, fps, loop).
    v9: morphs = {target_name: T_variant} (same triangles moved: facial expressions / mouth shapes -> blend shapes);
        morph_tracks = {clip_name: [target name per sprite frame]} -> a STEP 'weights' track per clip;
        chains = physics chains (sforge/physics.py) -> extra joints with baked swing rotations.
    v9 bake=True: every material is baked into ONE palette texture (model_baked.glb: 1 material, 1 primitive,
        1 draw call, TEXCOORD_0 + embedded PNG) - handy for engines/LODs where draw calls matter."""
    s = float(scale)
    buf = _Buf()
    J = rest_world()
    ball_i = JOINT_NAMES.index("ball")
    morphs = morphs or {}
    mnames = list(morphs)
    chains = chains or []
    nbase = len(JOINT_NAMES)
    if chains:
        from . import physics as PH
        cT, cJ, cM = PH.rest_tris(chains)
        T = np.concatenate([T, cT]); B = np.concatenate([B, nbase + cJ]); Mt = np.concatenate([Mt, np.array([MATS.index(m) for m in cM], Mt.dtype)])
        for k in mnames:
            morphs[k] = np.concatenate([morphs[k], cT])
        cnames = [jn for c in chains for jn in c.joint_names()]
    else:
        cnames = []
    # ---- geometry (flat shaded, un-indexed)
    def _scaled(TT):
        P = TT.copy()
        is_ball = B == ball_i
        P[~is_ball] *= s
        P[is_ball] = (P[is_ball] - J["ball"]) + J["ball"] * s
        return P
    P = _scaled(T)
    MP = {k: _scaled(v) - P for k, v in morphs.items()}
    e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
    N = np.cross(e1, e2); N /= (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
    from .matslots import mannequin_name
    prims, materials, mat_ix = [], [], {}
    images = []
    if bake:
        used = [mi for mi in range(len(MATS)) if (Mt == mi).any()]
        cell, cols = 8, 8
        rows = (len(used) + cols - 1) // cols
        tex = np.zeros((rows * cell, cols * cell, 4), np.uint8)
        uv_of = {}
        for k, mi in enumerate(used):
            r, c = divmod(k, cols)
            col = colours.get(MATS[mi], (0.7, 0.7, 0.7))
            tex[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = [int(round(255 * min(1, max(0, v)) ** (1 / 2.2))) for v in col[:3]] + [255]
            uv_of[mi] = ((c + 0.5) * cell / tex.shape[1], (r + 0.5) * cell / tex.shape[0])
        import io
        from PIL import Image as _I
        bio = io.BytesIO(); _I.fromarray(tex, "RGBA").save(bio, "PNG")
        png = bio.getvalue()
        while len(buf.data) % 4:
            buf.data.append(0)
        off = len(buf.data); buf.data.extend(png)
        buf.views.append({"buffer": 0, "byteOffset": off, "byteLength": len(png)})
        images.append({"name": "baked_palette", "mimeType": "image/png", "bufferView": len(buf.views) - 1})
        pos = P.reshape(-1, 3).astype(np.float32)
        nor = np.repeat(N, 3, axis=0).astype(np.float32)
        uv = np.repeat(np.array([uv_of[int(m)] for m in Mt], np.float32), 3, axis=0)
        jnt = np.zeros((pos.shape[0], 4), np.uint8); jnt[:, 0] = np.repeat(B, 3)
        wgt = np.zeros((pos.shape[0], 4), np.float32); wgt[:, 0] = 1
        prim = {"attributes": {"POSITION": buf.add(pos, 5126, "VEC3", 34962, True), "NORMAL": buf.add(nor, 5126, "VEC3", 34962),
                               "TEXCOORD_0": buf.add(uv, 5126, "VEC2", 34962), "JOINTS_0": buf.add(jnt, 5121, "VEC4", 34962),
                               "WEIGHTS_0": buf.add(wgt, 5126, "VEC4", 34962)}, "material": 0}
        if mnames:
            prim["targets"] = [{"POSITION": _sparse_target(buf, MP[k].reshape(-1, 3).astype(np.float32))} for k in mnames]
        prims.append(prim)
        materials.append({"name": "Baked_Mat", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0},
                          "metallicFactor": 0.0, "roughnessFactor": 0.85}, "extras": {"sforge_baked": [MATS[m] for m in used]}})
    for mi, mname in enumerate(MATS if not bake else []):
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
        prim = {"attributes": {"POSITION": a_pos, "NORMAL": a_nor, "JOINTS_0": a_j, "WEIGHTS_0": a_w}, "material": mat_ix[slot]}
        if mnames:
            prim["targets"] = [{"POSITION": _sparse_target(buf, MP[k][sel].reshape(-1, 3).astype(np.float32))} for k in mnames]
        prims.append(prim)
    # ---- skeleton nodes
    nodes = []
    for n in JOINT_NAMES:
        node = {"name": n, "translation": [float(x) * s for x in OFFSET[n]]}
        kids = [JOINT_NAMES.index(k) for k in JOINT_NAMES if PARENT[k] == n]
        if kids:
            node["children"] = kids
        nodes.append(node)
    # v9 physics chain joints: joint 0 hangs from its bone, the others follow each other
    rest_pos = [J[n] for n in JOINT_NAMES]
    for c in chains:
        bi = JOINT_NAMES.index(c.bone)
        for k in range(c.n):
            ji = len(nodes)
            t = (c.root - J[c.bone]) if k == 0 else c.dir * c.seg
            nodes.append({"name": c.joint_names()[k], "translation": [float(x) * s for x in t]})
            par = bi if k == 0 else ji - 1
            nodes[par].setdefault("children", []).append(ji)
            rest_pos.append(c.root + c.dir * c.seg * k)
    nj = len(rest_pos)
    ibm = np.stack([np.linalg.inv(np.array([[1, 0, 0, p[0] * s], [0, 1, 0, p[1] * s], [0, 0, 1, p[2] * s], [0, 0, 0, 1]])).T
                    for p in rest_pos]).astype(np.float32)  # column-major
    a_ibm = buf.add(ibm.reshape(nj, 16), 5126, "MAT4")
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
        if chains:
            sim = PH.simulate(chains, states, 1.0 / BAKE_FPS, loop)
            rots = [PH.joint_rotations(chains, pts, st) for pts, st in zip(sim, states)]
            for k in range(len(cnames)):
                q = np.stack([quat_from_matrix(r[k]) for r in rots])
                for i in range(1, len(q)):
                    if np.dot(q[i], q[i - 1]) < 0:
                        q[i] = -q[i]
                samplers.append({"input": a_t, "output": buf.add(q.astype(np.float32), 5126, "VEC4"), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": nbase + k, "path": "rotation"}})
        if mnames and morph_tracks and cname in morph_tracks:
            seq = morph_tracks[cname]
            dur = times[-1] if times[-1] > 0 else 1.0
            nf = len(seq)
            tt = [i * dur / nf for i in range(nf)] if loop else [i * dur / max(1, nf - 1) for i in range(nf)]
            w = np.zeros((nf, len(mnames)), np.float32)
            for i, e in enumerate(seq):
                for part in str(e).split("+"):
                    if part in mnames:
                        w[i, mnames.index(part)] = 1.0
            a_tw = buf.add(np.array(tt, np.float32).reshape(-1, 1), 5126, "SCALAR", None, True)
            samplers.append({"input": a_tw, "output": buf.add(w.reshape(-1), 5126, "SCALAR"), "interpolation": "STEP"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": mesh_node, "path": "weights"}})
        anims.append({"name": cname, "samplers": samplers, "channels": channels})
    gl = {
        "asset": {"version": "2.0", "generator": "Sprite Forge Studio (procedural mannequin)"},
        "scene": 0, "scenes": [{"nodes": [0, mesh_node]}], "nodes": nodes,
        "meshes": [dict({"name": name, "primitives": prims},
                        **({"weights": [0.0] * len(mnames), "extras": {"targetNames": mnames}} if mnames else {}))],
        "skins": [{"name": name + "_skin", "joints": [i for i in range(len(nodes)) if i != mesh_node], "inverseBindMatrices": a_ibm, "skeleton": 0}],
        "materials": materials, "animations": anims,
        **({"images": images, "textures": [{"source": 0, "sampler": 0}],
            "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}]} if images else {}),
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
