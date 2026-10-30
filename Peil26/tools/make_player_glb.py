"""Build an original skinned Gaelic footballer as a GLB.

The mesh, skeleton and clips are original. No third-party character is embedded.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_from_euler(x, y, z):
    cx, sx = math.cos(x * 0.5), math.sin(x * 0.5)
    cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
    cz, sz = math.cos(z * 0.5), math.sin(z * 0.5)
    return (
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    )


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


class Blob:
    def __init__(self):
        self.buf = bytearray()

    def align(self, n=4):
        while len(self.buf) % n:
            self.buf.append(0)

    def pack(self, fmt, *vals):
        self.align(4)
        start = len(self.buf)
        self.buf += struct.pack(fmt, *vals)
        return start, len(self.buf)


def capsule(p0, p1, radius, rings=5, segs=12):
    p0 = tuple(p0)
    p1 = tuple(p1)
    axis = tuple(p1[i] - p0[i] for i in range(3))
    length = math.sqrt(sum(c * c for c in axis)) or 1.0
    ay = tuple(c / length for c in axis)
    helper = (1.0, 0.0, 0.0) if abs(ay[1]) < 0.9 else (0.0, 0.0, 1.0)
    ax = (
        helper[1] * ay[2] - helper[2] * ay[1],
        helper[2] * ay[0] - helper[0] * ay[2],
        helper[0] * ay[1] - helper[1] * ay[0],
    )
    al = math.sqrt(sum(c * c for c in ax)) or 1.0
    ax = tuple(c / al for c in ax)
    az = (
        ay[1] * ax[2] - ay[2] * ax[1],
        ay[2] * ax[0] - ay[0] * ax[2],
        ay[0] * ax[1] - ay[1] * ax[0],
    )
    verts, norms = [], []
    for i in range(rings + 1):
        t = i / rings
        center = tuple(p0[k] + axis[k] * t for k in range(3))
        bulge = 1.0
        for j in range(segs):
            ang = math.tau * j / segs
            radial = tuple(math.cos(ang) * ax[k] + math.sin(ang) * az[k] for k in range(3))
            # Slight taper so limbs read as athletic, not pipes.
            r = radius * (0.92 + 0.08 * math.sin(t * math.pi)) * bulge
            verts.append(tuple(center[k] + radial[k] * r for k in range(3)))
            norms.append(radial)
    # End caps so elbows and knees close.
    for end, sign in ((p0, -1), (p1, 1)):
        for j in range(segs):
            ang = math.tau * j / segs
            radial = tuple(math.cos(ang) * ax[k] + math.sin(ang) * az[k] for k in range(3))
            normal = tuple(radial[k] * 0.75 + ay[k] * sign * 0.65 for k in range(3))
            nl = math.sqrt(sum(c * c for c in normal)) or 1.0
            normal = tuple(c / nl for c in normal)
            verts.append(tuple(end[k] + normal[k] * radius * 0.92 for k in range(3)))
            norms.append(normal)
    idx = []
    for i in range(rings):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            c = (i + 1) * segs + j
            d = (i + 1) * segs + (j + 1) % segs
            idx += [a, c, b, b, c, d]
    return verts, norms, idx


def sphere(center, radius, lat=10, lon=14, squash=(1, 1, 1)):
    verts, norms, idx = [], [], []
    for i in range(lat + 1):
        v = i / lat
        phi = math.pi * (v - 0.5)
        cp, sp = math.cos(phi), math.sin(phi)
        for j in range(lon):
            u = j / lon
            th = math.tau * u
            n = (math.cos(th) * cp, sp, math.sin(th) * cp)
            nl = math.sqrt(sum(c * c for c in n)) or 1.0
            n = tuple(c / nl for c in n)
            verts.append(tuple(center[k] + n[k] * radius * squash[k] for k in range(3)))
            norms.append(n)
    for i in range(lat):
        for j in range(lon):
            a = i * lon + j
            b = i * lon + (j + 1) % lon
            c = (i + 1) * lon + j
            d = (i + 1) * lon + (j + 1) % lon
            idx += [a, c, b, b, c, d]
    return verts, norms, idx


def paint_face(verts, norms, colors):
    out = []
    for v, n in zip(verts, norms):
        col = (0.93, 0.76, 0.64)
        # Eyes sit on the front of the head, slightly up.
        for side in (-1, 1):
            eye = (side * 0.032, 1.70, 0.09)
            d = math.dist(v, eye)
            if d < 0.018:
                col = (0.08, 0.07, 0.08)
            elif d < 0.028:
                col = (0.95, 0.95, 0.96)
        if v[1] < 1.64 and v[2] > 0.07 and abs(v[0]) < 0.02:
            col = (0.72, 0.48, 0.42)
        out.append(col)
    return out


BONES = [
    ("root", None, (0.0, 0.0, 0.0)),
    ("hips", "root", (0.0, 0.98, 0.0)),
    ("spine", "hips", (0.0, 0.14, 0.0)),
    ("chest", "spine", (0.0, 0.18, 0.0)),
    ("neck", "chest", (0.0, 0.20, 0.0)),
    ("head", "neck", (0.0, 0.08, 0.0)),
    ("armU.L", "chest", (-0.18, 0.10, 0.0)),
    ("armL.L", "armU.L", (0.0, -0.28, 0.02)),
    ("armU.R", "chest", (0.18, 0.10, 0.0)),
    ("armL.R", "armU.R", (0.0, -0.28, 0.02)),
    ("legU.L", "hips", (-0.09, -0.02, 0.0)),
    ("legL.L", "legU.L", (0.0, -0.42, 0.0)),
    ("foot.L", "legL.L", (0.0, -0.40, 0.02)),
    ("legU.R", "hips", (0.09, -0.02, 0.0)),
    ("legL.R", "legU.R", (0.0, -0.42, 0.0)),
    ("foot.R", "legL.R", (0.0, -0.40, 0.02)),
]


def world_positions():
    by_name = {n: (p, t) for n, p, t in BONES}
    cache = {}

    def world(name):
        if name in cache:
            return cache[name]
        parent, local = by_name[name]
        if parent is None:
            cache[name] = local
        else:
            pw = world(parent)
            cache[name] = tuple(pw[i] + local[i] for i in range(3))
        return cache[name]

    return {n: world(n) for n, _, _ in BONES}


def nearest_bones(point, worlds):
    # Weight by distance to the bone origin, with a bias toward the limb the
    # vertex was built around (passed in separately when very close).
    scored = []
    for name, pos in worlds.items():
        if name == "root":
            continue
        d = math.dist(point, pos)
        scored.append((d, name))
    scored.sort()
    a, b = scored[0], scored[1]
    wa = 1.0 / (a[0] + 0.02)
    wb = 1.0 / (b[0] + 0.02)
    s = wa + wb
    return a[1], b[1], wa / s, wb / s


def build_parts(worlds):
    parts = []

    def add(name, material, verts, norms, idx, colors=None):
        parts.append((name, material, verts, norms, idx, colors))

    def limb(material, a, b, radius):
        return capsule(worlds[a], worlds[b], radius)

    add("jersey", "Jersey", *limb("Jersey", "spine", "chest", 0.155))
    add("jersey2", "Jersey", *limb("Jersey", "chest", "neck", 0.125))
    # Sleeves
    add("sleeveL", "Jersey", *capsule(worlds["chest"], worlds["armU.L"], 0.07))
    add("sleeveR", "Jersey", *capsule(worlds["chest"], worlds["armU.R"], 0.07))
    add("shorts", "Shorts", *capsule(worlds["hips"], worlds["spine"], 0.145))
    add("thighL", "Shorts", *capsule(worlds["legU.L"], tuple(worlds["legU.L"][i] + (worlds["legL.L"][i] - worlds["legU.L"][i]) * 0.42 for i in range(3)), 0.078))
    add("thighR", "Shorts", *capsule(worlds["legU.R"], tuple(worlds["legU.R"][i] + (worlds["legL.R"][i] - worlds["legU.R"][i]) * 0.42 for i in range(3)), 0.078))
    add("shinL", "Socks", *limb("Socks", "legL.L", "foot.L", 0.052))
    add("shinR", "Socks", *limb("Socks", "legL.R", "foot.R", 0.052))
    add("bootL", "Boots", *capsule(worlds["foot.L"], (worlds["foot.L"][0], 0.04, worlds["foot.L"][2] + 0.12), 0.048))
    add("bootR", "Boots", *capsule(worlds["foot.R"], (worlds["foot.R"][0], 0.04, worlds["foot.R"][2] + 0.12), 0.048))
    add("armL", "Skin", *limb("Skin", "armU.L", "armL.L", 0.048))
    add("foreL", "Skin", *capsule(worlds["armL.L"], (worlds["armL.L"][0], worlds["armL.L"][1] - 0.24, worlds["armL.L"][2] + 0.03), 0.04))
    add("armR", "Skin", *limb("Skin", "armU.R", "armL.R", 0.048))
    add("foreR", "Skin", *capsule(worlds["armL.R"], (worlds["armL.R"][0], worlds["armL.R"][1] - 0.24, worlds["armL.R"][2] + 0.03), 0.04))
    hv, hn, hi = sphere(worlds["head"], 0.105, squash=(0.92, 1.05, 0.96))
    add("head", "Skin", hv, hn, hi, paint_face(hv, hn, None))
    add("neck", "Skin", *limb("Skin", "neck", "head", 0.045))
    hair_c = (worlds["head"][0], worlds["head"][1] + 0.02, worlds["head"][2] - 0.01)
    add("hair", "Hair", *sphere(hair_c, 0.112, lat=8, lon=12, squash=(0.98, 0.62, 0.95)))
    # Collar trim so the kit reads at broadcast size.
    add("trim", "Trim", *capsule((0, 1.46, 0.02), (0, 1.50, 0.05), 0.055, rings=2, segs=10))
    return parts


def clip(name, duration, samples, tracks):
    times = [duration * i / (samples - 1) for i in range(samples)]
    out = {}
    for bone, fn in tracks.items():
        keys = [qnorm(quat_from_euler(*fn(t))) for t in times]
        out[bone] = keys
    return name, times, out


def clips():
    def idle(t):
        b = math.sin(t * math.tau) * 0.04
        return {
            "spine": lambda u, b=b: (b, 0, 0),
            "armU.L": lambda u: (0.18, 0, 0.08),
            "armU.R": lambda u: (0.18, 0, -0.08),
            "armL.L": lambda u: (0.25, 0, 0),
            "armL.R": lambda u: (0.25, 0, 0),
        }

    # Rebuild properly with time-varying functions.
    result = []

    def make(name, duration, samples, fn):
        times = [duration * i / (samples - 1) for i in range(samples)]
        bones = {}
        for t in times:
            pose = fn(t / duration)
            for bone, eul in pose.items():
                bones.setdefault(bone, []).append(qnorm(quat_from_euler(*eul)))
        result.append((name, times, bones))

    def idle_fn(u):
        b = math.sin(u * math.tau) * 0.035
        return {
            "spine": (b, 0.0, 0.0),
            "armU.L": (0.22, 0.0, 0.06),
            "armU.R": (0.22, 0.0, -0.06),
            "armL.L": (0.35, 0.0, 0.0),
            "armL.R": (0.35, 0.0, 0.0),
            "legU.L": (0.02, 0.0, 0.0),
            "legU.R": (-0.02, 0.0, 0.0),
            "legL.L": (0.08, 0.0, 0.0),
            "legL.R": (0.08, 0.0, 0.0),
        }

    def run_fn(u):
        s = math.sin(u * math.tau)
        c = math.cos(u * math.tau)
        return {
            "hips": (0.08, s * 0.06, 0.0),
            "spine": (0.12, s * 0.10, 0.0),
            "legU.L": (-s * 0.95, 0.0, 0.0),
            "legU.R": (s * 0.95, 0.0, 0.0),
            "legL.L": (0.25 + max(0.0, -s) * 0.95, 0.0, 0.0),
            "legL.R": (0.25 + max(0.0, s) * 0.95, 0.0, 0.0),
            "armU.L": (s * 0.8, 0.0, 0.05),
            "armU.R": (-s * 0.8, 0.0, -0.05),
            "armL.L": (0.7, 0.0, 0.0),
            "armL.R": (0.7, 0.0, 0.0),
            "foot.L": (max(0.0, s) * 0.4, 0.0, 0.0),
            "foot.R": (max(0.0, -s) * 0.4, 0.0, 0.0),
        }

    def kick_fn(u):
        # Wind up, then through the ball with the right foot.
        if u < 0.35:
            k = u / 0.35
            leg, knee = 0.55 * k, 1.1 * k
        elif u < 0.62:
            k = (u - 0.35) / 0.27
            leg = 0.55 + (-1.35 - 0.55) * k
            knee = 1.1 * (1 - k)
        else:
            k = (u - 0.62) / 0.38
            leg = -1.35 + 0.5 * k
            knee = 0.15
        return {
            "spine": (-0.18, -0.15, 0.0),
            "legU.R": (leg, 0.0, 0.0),
            "legL.R": (knee, 0.0, 0.0),
            "legU.L": (0.15, 0.0, 0.0),
            "legL.L": (0.2, 0.0, 0.0),
            "armU.L": (-0.4, 0.0, 0.4),
            "armU.R": (0.5, 0.0, -0.3),
        }

    def solo_fn(u):
        tap = max(0.0, math.sin(u * math.tau))
        return {
            "legU.R": (-0.35 - tap * 0.25, 0.0, 0.0),
            "legL.R": (0.9 - tap * 0.5, 0.0, 0.0),
            "armU.L": (0.2, 0.0, 0.1),
            "armU.R": (0.15, 0.0, -0.2),
        }

    def hand_fn(u):
        swing = math.sin(min(1.0, u * 1.4) * math.pi)
        return {
            "spine": (0.0, -0.25 * swing, 0.0),
            "armU.R": (-1.5 * swing, 0.0, -0.2),
            "armL.R": (0.4 * (1 - swing), 0.0, 0.0),
            "armU.L": (0.3, 0.0, 0.2),
        }

    def catch_fn(u):
        lift = math.sin(min(1.0, u) * math.pi)
        return {
            "armU.L": (-1.7 * lift, 0.0, 0.35),
            "armU.R": (-1.7 * lift, 0.0, -0.35),
            "armL.L": (0.8, 0.0, 0.0),
            "armL.R": (0.8, 0.0, 0.0),
            "spine": (-0.1 * lift, 0.0, 0.0),
        }

    def block_fn(u):
        return {
            "armU.L": (-1.35, 0.0, 0.25),
            "armU.R": (-1.35, 0.0, -0.25),
            "armL.L": (0.2, 0.0, 0.0),
            "armL.R": (0.2, 0.0, 0.0),
            "spine": (0.12, 0.0, 0.0),
        }

    make("idle", 1.6, 16, idle_fn)
    make("run", 0.62, 16, run_fn)
    make("kick", 0.48, 14, kick_fn)
    make("solo", 0.36, 10, solo_fn)
    make("hand", 0.38, 10, hand_fn)
    make("catch", 0.45, 10, catch_fn)
    make("block", 0.30, 8, block_fn)
    return result


def write_glb(path: Path):
    worlds = world_positions()
    parts = build_parts(worlds)
    names = [n for n, _, _ in BONES]
    index_of = {n: i for i, n in enumerate(names)}
    blob = Blob()
    accessors = []
    views = []

    def add_view(data, target=None):
        blob.align(4)
        start = len(blob.buf)
        blob.buf += data
        view = {"buffer": 0, "byteOffset": start, "byteLength": len(data)}
        if target:
            view["target"] = target
        views.append(view)
        return len(views) - 1

    def add_acc(view, count, typ, comp, mins=None, maxs=None):
        acc = {
            "bufferView": view,
            "componentType": comp,
            "count": count,
            "type": typ,
        }
        if mins is not None:
            acc["min"] = mins
            acc["max"] = maxs
        accessors.append(acc)
        return len(accessors) - 1

    primitives = []
    for _name, material, verts, norms, idx, colors in parts:
        joints, weights = [], []
        for v in verts:
            b0, b1, w0, w1 = nearest_bones(v, worlds)
            joints.append((index_of[b0], index_of[b1], 0, 0))
            weights.append((w0, w1, 0.0, 0.0))
        pos = b"".join(struct.pack("<3f", *v) for v in verts)
        nor = b"".join(struct.pack("<3f", *n) for n in norms)
        jnt = b"".join(struct.pack("<4B", *j) for j in joints)
        wgt = b"".join(struct.pack("<4f", *w) for w in weights)
        ind = b"".join(struct.pack("<H", i) for i in idx)
        xs, ys, zs = zip(*verts)
        pacc = add_acc(add_view(pos, 34962), len(verts), "VEC3", 5126, [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        nacc = add_acc(add_view(nor, 34962), len(verts), "VEC3", 5126)
        jacc = add_acc(add_view(jnt, 34962), len(verts), "VEC4", 5121)
        wacc = add_acc(add_view(wgt, 34962), len(verts), "VEC4", 5126)
        iacc = add_acc(add_view(ind, 34963), len(idx), "SCALAR", 5123)
        prim = {
            "attributes": {"POSITION": pacc, "NORMAL": nacc, "JOINTS_0": jacc, "WEIGHTS_0": wacc},
            "indices": iacc,
            "material": {"Skin": 0, "Hair": 1, "Jersey": 2, "Trim": 3, "Shorts": 4, "Socks": 5, "Boots": 6}[material],
        }
        if colors:
            col = b"".join(struct.pack("<3f", *c) for c in colors)
            prim["attributes"]["COLOR_0"] = add_acc(add_view(col, 34962), len(colors), "VEC3", 5126)
        primitives.append(prim)

    # Inverse bind matrices, column-major. Bind rotations are identity, so the
    # world matrix is a pure translation and the inverse is -translation.
    ibms = b""
    for name in names:
        x, y, z = worlds[name]
        m = [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            -x, -y, -z, 1,
        ]
        ibms += struct.pack("<16f", *m)
    ibm_acc = add_acc(add_view(ibms), len(names), "MAT4", 5126)

    anim_defs = clips()
    animations = []
    nodes_for_anim = []
    for aname, times, bones in anim_defs:
        tbytes = struct.pack("<" + "f" * len(times), *times)
        tacc = add_acc(add_view(tbytes), len(times), "SCALAR", 5126, [times[0]], [times[-1]])
        channels = []
        samplers = []
        for bone, keys in bones.items():
            data = b"".join(struct.pack("<4f", *q) for q in keys)
            oacc = add_acc(add_view(data), len(keys), "VEC4", 5126)
            samplers.append({"input": tacc, "output": oacc, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": index_of[bone] + 1, "path": "rotation"}})
        animations.append({"name": aname, "samplers": samplers, "channels": channels})

    nodes = [{"name": "Player", "mesh": 0, "skin": 0}]
    children = {n: [] for n in names}
    for name, parent, _ in BONES:
        if parent:
            children[parent].append(index_of[name] + 1)
    for name, parent, local in BONES:
        node = {"name": name, "translation": list(local)}
        kids = children[name]
        if kids:
            node["children"] = kids
        nodes.append(node)

    materials = [
        {"name": "Skin", "pbrMetallicRoughness": {"baseColorFactor": [0.86, 0.67, 0.54, 1], "roughnessFactor": 0.62, "metallicFactor": 0.0}},
        {"name": "Hair", "pbrMetallicRoughness": {"baseColorFactor": [0.12, 0.08, 0.06, 1], "roughnessFactor": 0.7, "metallicFactor": 0.0}},
        {"name": "Jersey", "pbrMetallicRoughness": {"baseColorFactor": [0.10, 0.36, 0.78, 1], "roughnessFactor": 0.48, "metallicFactor": 0.02}},
        {"name": "Trim", "pbrMetallicRoughness": {"baseColorFactor": [0.93, 0.93, 0.95, 1], "roughnessFactor": 0.4, "metallicFactor": 0.0}},
        {"name": "Shorts", "pbrMetallicRoughness": {"baseColorFactor": [0.08, 0.12, 0.22, 1], "roughnessFactor": 0.55, "metallicFactor": 0.0}},
        {"name": "Socks", "pbrMetallicRoughness": {"baseColorFactor": [0.10, 0.36, 0.78, 1], "roughnessFactor": 0.5, "metallicFactor": 0.0}},
        {"name": "Boots", "pbrMetallicRoughness": {"baseColorFactor": [0.08, 0.08, 0.09, 1], "roughnessFactor": 0.38, "metallicFactor": 0.08}},
    ]
    gltf = {
        "asset": {"version": "2.0", "generator": "PEIL 26"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": nodes,
        "meshes": [{"name": "Footballer", "primitives": primitives}],
        "skins": [{"name": "Body", "joints": [i + 1 for i in range(len(names))], "inverseBindMatrices": ibm_acc, "skeleton": 1}],
        "materials": materials,
        "animations": animations,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob.buf)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "
    bin_chunk = bytes(blob.buf)
    while len(bin_chunk) % 4:
        bin_chunk += b"\x00"
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(bin_chunk))
    out += struct.pack("<I4s", len(js), b"JSON")
    out += js
    out += struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
    out += bin_chunk
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    print(f"wrote {path} ({len(out)} bytes, {len(primitives)} primitives, {len(animations)} clips)")


if __name__ == "__main__":
    write_glb(Path("/home/user/Peil26/public/models/player.glb"))
