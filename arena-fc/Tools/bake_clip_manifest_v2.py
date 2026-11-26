#!/usr/bin/env python3
"""Phase 1+ Hypermotion data plumbing: enrich clip_manifest.json with v2 fields.

Prefers real GLB/pose sampling from the authored soccer_player GLB when available,
falling back to deterministic v1-metadata heuristics. Outputs:
  - plantCurveLeft/Right: uniformly sampled foot-plant weights (0..1)
  - contactWindowStart/End: normalized contact window
  - rootVelocitySamples: facing-local XZ root velocity samples [x0,z0,...] m/s

The bake is deterministic. Re-run when clips/manifests change.
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
from typing import Dict, List, Optional, Tuple

SAMPLES = 32
GLB_DEFAULT = "arena-fc/Data/models/soccer_player.glb"


# ---------------------------- math/helpers ----------------------------

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def v3_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v3_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v3_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v3_lerp(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def q_norm(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / n, y / n, z / n, w / n)


def q_slerp(a, b, t):
    ax, ay, az, aw = q_norm(a)
    bx, by, bz, bw = q_norm(b)
    dot = ax * bx + ay * by + az * bz + aw * bw
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
        dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > 0.9995:
        q = (lerp(ax, bx, t), lerp(ay, by, t), lerp(az, bz, t), lerp(aw, bw, t))
        return q_norm(q)
    theta = math.acos(dot)
    s = math.sin(theta)
    wa = math.sin((1.0 - t) * theta) / s
    wb = math.sin(t * theta) / s
    return (ax * wa + bx * wb, ay * wa + by * wb, az * wa + bz * wb, aw * wa + bw * wb)


def q_rotate(q, v):
    x, y, z, w = q_norm(q)
    vx, vy, vz = v
    # q * v * q^-1
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def mat4_from_trs(t, r, s):
    x, y, z, w = q_norm(r)
    sx, sy, sz = s
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    # column-major 4x4
    return [
        (1 - 2 * (yy + zz)) * sx, (2 * (xy + wz)) * sx, (2 * (xz - wy)) * sx, 0.0,
        (2 * (xy - wz)) * sy, (1 - 2 * (xx + zz)) * sy, (2 * (yz + wx)) * sy, 0.0,
        (2 * (xz + wy)) * sz, (2 * (yz - wx)) * sz, (1 - 2 * (xx + yy)) * sz, 0.0,
        t[0], t[1], t[2], 1.0,
    ]


def mat4_mul(a, b):
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = (
                a[0 * 4 + r] * b[c * 4 + 0]
                + a[1 * 4 + r] * b[c * 4 + 1]
                + a[2 * 4 + r] * b[c * 4 + 2]
                + a[3 * 4 + r] * b[c * 4 + 3]
            )
    return out


def mat4_transform_point(m, p):
    x, y, z = p
    px = m[0] * x + m[4] * y + m[8] * z + m[12]
    py = m[1] * x + m[5] * y + m[9] * z + m[13]
    pz = m[2] * x + m[6] * y + m[10] * z + m[14]
    pw = m[3] * x + m[7] * y + m[11] * z + m[15]
    if abs(pw) > 1e-8 and abs(pw - 1.0) > 1e-8:
        return (px / pw, py / pw, pz / pw)
    return (px, py, pz)


def circ_diff(a, b):
    d = (a - b) % 1.0
    if d > 0.5:
        d -= 1.0
    if d < -0.5:
        d += 1.0
    return d


# ---------------------------- GLB sampling ----------------------------

class GltfSampler:
    def __init__(self, times: List[float], values: List[Tuple[float, ...]], path: str):
        self.times = times
        self.values = values
        self.path = path

    def sample(self, t: float):
        times = self.times
        vals = self.values
        if not times:
            return None
        if t <= times[0]:
            return vals[0]
        if t >= times[-1]:
            return vals[-1]
        # binary search
        lo, hi = 0, len(times) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if times[mid] <= t:
                lo = mid
            else:
                hi = mid
        t0, t1 = times[lo], times[hi]
        dt = t1 - t0
        u = 0.0 if dt <= 1e-8 else (t - t0) / dt
        a, b = vals[lo], vals[hi]
        if self.path == "rotation":
            return q_slerp(a, b, u)
        if self.path in ("translation", "scale"):
            return tuple(lerp(a[i], b[i], u) for i in range(len(a)))
        return tuple(lerp(a[i], b[i], u) for i in range(len(a)))


class GlbAnimations:
    def __init__(self, path: str):
        self.path = path
        self.gltf = None
        self.blob = b""
        self.nodes = []
        self.parent: Dict[int, Optional[int]] = {}
        self.node_name_to_idx: Dict[str, int] = {}
        self.joints: List[int] = []
        self.animations: Dict[str, dict] = {}
        self._load()

    def _load(self):
        with open(self.path, "rb") as f:
            header = f.read(12)
            if len(header) != 12:
                raise ValueError("Invalid GLB header")
            magic, version, _length = struct.unpack("<4sII", header)
            if magic != b"glTF":
                raise ValueError("Not a GLB file")
            # JSON chunk
            clen, ctype = struct.unpack("<II", f.read(8))
            json_bytes = f.read(clen)
            if ctype != 0x4E4F534A:
                raise ValueError("Expected JSON chunk")
            self.gltf = json.loads(json_bytes.decode("utf-8"))
            # BIN chunk (optional)
            rest = f.read(8)
            if len(rest) == 8:
                blen, btype = struct.unpack("<II", rest)
                self.blob = f.read(blen)
        self.nodes = self.gltf.get("nodes", [])
        self.parent = {i: None for i in range(len(self.nodes))}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                if 0 <= c < len(self.nodes):
                    self.parent[c] = i
            name = n.get("name")
            if name:
                self.node_name_to_idx[name] = i
        skins = self.gltf.get("skins", [])
        if skins:
            self.joints = list(skins[0].get("joints", []))
        for anim in self.gltf.get("animations", []):
            name = anim.get("name")
            if name:
                self.animations[name] = anim

    def _read_accessor(self, idx: int) -> List[Tuple[float, ...]]:
        gltf = self.gltf
        acc = gltf["accessors"][idx]
        bv = gltf["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        comp_type = acc["componentType"]
        ctype = acc["type"]
        count = acc["count"]
        fmt_map = {
            5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
            5125: ("I", 4), 5126: ("f", 4),
        }
        if comp_type not in fmt_map:
            raise ValueError(f"Unsupported componentType {comp_type}")
        fmt, size = fmt_map[comp_type]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[ctype]
        stride = bv.get("byteStride", size * ncomp)
        out = []
        blob = self.blob
        for i in range(count):
            base = off + i * stride
            vals = struct.unpack("<" + fmt * ncomp, blob[base : base + size * ncomp])
            out.append(tuple(float(v) for v in vals))
        return out

    def _node_base_trs(self, node_idx: int):
        n = self.nodes[node_idx]
        t = tuple(float(x) for x in n.get("translation", [0, 0, 0]))
        r = tuple(float(x) for x in n.get("rotation", [0, 0, 0, 1]))
        s = tuple(float(x) for x in n.get("scale", [1, 1, 1]))
        return t, q_norm(r), s

    def sample_clip_curves(self, clip_name: str, samples: int = SAMPLES) -> Optional[dict]:
        anim = self.animations.get(clip_name)
        if anim is None:
            return None
        samplers = []
        for s in anim.get("samplers", []):
            times = [v[0] for v in self._read_accessor(s["input"])]
            values = self._read_accessor(s["output"])
            samplers.append((times, values, s.get("interpolation", "LINEAR")))
        node_samplers: Dict[int, Dict[str, GltfSampler]] = {}
        max_t = 0.0
        for ch in anim.get("channels", []):
            target = ch.get("target", {})
            node = target.get("node")
            path = target.get("path")
            if node is None or path not in ("translation", "rotation", "scale"):
                continue
            si = ch.get("sampler")
            if si is None or si < 0 or si >= len(samplers):
                continue
            times, values, _interp = samplers[si]
            if times:
                max_t = max(max_t, times[-1])
            node_samplers.setdefault(node, {})[path] = GltfSampler(times, values, path)
        if max_t <= 1e-6:
            max_t = 1.0

        # Relevant nodes: joints + ancestors
        relevant = set(self.joints)
        for j in list(relevant):
            p = self.parent.get(j)
            while p is not None and p not in relevant:
                relevant.add(p)
                p = self.parent.get(p)
        # Ensure feet/hips included by name
        for nm in ("Hips", "LFoot", "RFoot", "LToes", "RToes"):
            idx = self.node_name_to_idx.get(nm)
            if idx is not None:
                relevant.add(idx)
                p = self.parent.get(idx)
                while p is not None and p not in relevant:
                    relevant.add(p)
                    p = self.parent.get(p)

        ordered = sorted(relevant, key=lambda n: self._node_depth(n))
        hips_idx = self.node_name_to_idx.get("Hips")
        lfoot_idx = self.node_name_to_idx.get("LFoot")
        rfoot_idx = self.node_name_to_idx.get("RFoot")
        if lfoot_idx is None or rfoot_idx is None or hips_idx is None:
            return None

        def eval_world_at(t: float):
            world: Dict[int, List[float]] = {}
            for node in ordered:
                bt, br, bs = self._node_base_trs(node)
                ns = node_samplers.get(node, {})
                if "translation" in ns:
                    bt = tuple(float(x) for x in ns["translation"].sample(t))
                if "rotation" in ns:
                    br = q_norm(tuple(float(x) for x in ns["rotation"].sample(t)))
                if "scale" in ns:
                    bs = tuple(float(x) for x in ns["scale"].sample(t))
                local = mat4_from_trs(bt, br, bs)
                p = self.parent.get(node)
                world[node] = mat4_mul(world[p], local) if p in world else local
            return world

        # sample poses
        poses = []
        for i in range(samples):
            u = i / (samples - 1) if samples > 1 else 0.0
            t = u * max_t
            world = eval_world_at(t)
            lpos = mat4_transform_point(world[lfoot_idx], (0, 0, 0))
            rpos = mat4_transform_point(world[rfoot_idx], (0, 0, 0))
            hpos = mat4_transform_point(world[hips_idx], (0, 0, 0))
            poses.append((u, t, lpos, rpos, hpos))

        # Plant curves from real foot motion: low height + low horizontal speed.
        l_y = [p[2][1] for p in poses]
        r_y = [p[3][1] for p in poses]
        # ground reference: robust minimum near contact
        l_ground = sorted(l_y)[max(0, int(len(l_y) * 0.1))]
        r_ground = sorted(r_y)[max(0, int(len(r_y) * 0.1))]
        l_curve = []
        r_curve = []
        for i in range(samples):
            dt = max(1e-4, (poses[min(samples - 1, i + 1)][1] - poses[max(0, i - 1)][1]))
            lpos = poses[i][2]
            rpos = poses[i][3]
            lprev = poses[max(0, i - 1)][2]
            lnext = poses[min(samples - 1, i + 1)][2]
            rprev = poses[max(0, i - 1)][3]
            rnext = poses[min(samples - 1, i + 1)][3]
            lvx = (lnext[0] - lprev[0]) / dt
            lvz = (lnext[2] - lprev[2]) / dt
            rvx = (rnext[0] - rprev[0]) / dt
            rvz = (rnext[2] - rprev[2]) / dt
            lspeed = math.sqrt(lvx * lvx + lvz * lvz)
            rspeed = math.sqrt(rvx * rvx + rvz * rvz)
            lh = max(0.0, lpos[1] - l_ground)
            rh = max(0.0, rpos[1] - r_ground)
            # Height threshold and speed threshold in model units/meters.
            l_h_w = clamp01(1.0 - lh / 0.06)
            r_h_w = clamp01(1.0 - rh / 0.06)
            l_v_w = clamp01(1.0 - lspeed / 0.55)
            r_v_w = clamp01(1.0 - rspeed / 0.55)
            l_curve.append(round(clamp01(l_h_w * (0.65 + 0.35 * l_v_w)), 6))
            r_curve.append(round(clamp01(r_h_w * (0.65 + 0.35 * r_v_w)), 6))

        # Root velocity samples from hips XZ delta (model-space; manifest treats as facing-local XZ).
        rv = []
        for i in range(samples):
            i0 = max(0, i - 1)
            i1 = min(samples - 1, i + 1)
            dt = max(1e-4, poses[i1][1] - poses[i0][1])
            h0 = poses[i0][4]
            h1 = poses[i1][4]
            vx = (h1[0] - h0[0]) / dt
            vz = (h1[2] - h0[2]) / dt
            rv.extend([round(vx, 6), round(vz, 6)])

        return {
            "plantCurveLeft": l_curve,
            "plantCurveRight": r_curve,
            "rootVelocitySamples": rv,
            "source": "glb",
        }

    def _node_depth(self, node: int) -> int:
        d = 0
        p = self.parent.get(node)
        seen = set()
        while p is not None and p not in seen:
            seen.add(p)
            d += 1
            p = self.parent.get(p)
        return d


# ---------------------------- heuristic fallback ----------------------------

def plant_curve_heuristic(frames, sides, side, samples=SAMPLES):
    curve = [0.0] * samples
    for f, s in zip(frames, sides):
        if str(s).lower() != side:
            continue
        for i in range(samples):
            p = i / (samples - 1)
            d = abs(circ_diff(p, float(f)))
            w = math.exp(-(d * d) / (2 * 0.035 * 0.035))
            if w > curve[i]:
                curve[i] = w
    return [round(clamp01(v), 6) for v in curve]


def contact_window(contact_frac):
    if contact_frac is None or float(contact_frac) < 0:
        return -1.0, -1.0
    cf = float(contact_frac)
    start = max(0.0, cf - 0.20)
    end = min(1.0, cf + 0.05)
    return round(start, 6), round(end, 6)


def root_velocity_samples_heuristic(vx, vz, samples=SAMPLES):
    return [round(float(vx), 6), round(float(vz), 6)] * samples


# ---------------------------- main ----------------------------

def enrich_clip(c, glb: Optional[GlbAnimations], stats: Dict[str, int]):
    frames = c.get("footPlantFrames", []) or []
    sides = c.get("footPlantSides", []) or []
    if len(sides) != len(frames):
        sides = ["Left" if i % 2 == 0 else "Right" for i in range(len(frames))]
    c["footPlantSides"] = sides

    clip_id = c.get("id") or c.get("poseDataKey") or ""
    sampled = None
    if glb is not None and clip_id:
        try:
            sampled = glb.sample_clip_curves(clip_id, SAMPLES)
        except Exception:
            sampled = None

    if sampled is not None:
        c["plantCurveLeft"] = sampled["plantCurveLeft"]
        c["plantCurveRight"] = sampled["plantCurveRight"]
        rv = sampled["rootVelocitySamples"]
        # In-place GLB clips yield zero hips translation; fall back to
        # authored/metadata speed so motion-matching features are meaningful.
        if rv and all(abs(float(x)) < 1e-6 for x in rv):
            vx = float(c.get("rootVelocityX", 0.0) or 0.0)
            vz = float(c.get("rootVelocityZ", 0.0) or 0.0)
            speed = float(c.get("preferredSpeed", 0.0) or 0.0)
            cat = str(c.get("category", "")).lower()
            if abs(vx) < 1e-6 and abs(vz) < 1e-6 and speed > 0.1 and cat in ("locomotion", "dribble", "carry", "goalkeeper"):
                # Facing-local XZ: x=right, z=forward.
                vx, vz = 0.0, speed
            if abs(vx) > 1e-6 or abs(vz) > 1e-6:
                rv = root_velocity_samples_heuristic(vx, vz, len(rv) // 2)
        c["rootVelocitySamples"] = rv
        c["source"] = "glb"
        c["provenance"] = {"type": "glb", "glb": os.path.basename(glb.path) if glb else GLB_DEFAULT}
        stats["glb"] += 1
    else:
        c["plantCurveLeft"] = plant_curve_heuristic(frames, sides, "left")
        c["plantCurveRight"] = plant_curve_heuristic(frames, sides, "right")
        vx = float(c.get("rootVelocityX", 0.0) or 0.0)
        vz = float(c.get("rootVelocityZ", 0.0) or 0.0)
        if abs(vx) < 1e-6 and abs(vz) < 1e-6:
            speed = float(c.get("preferredSpeed", 0.0) or 0.0)
            cat = str(c.get("category", "")).lower()
            if speed > 0.1 and cat in ("locomotion", "dribble", "carry", "goalkeeper"):
                vx, vz = 0.0, speed
        c["rootVelocitySamples"] = root_velocity_samples_heuristic(vx, vz)
        c["source"] = "heuristic"
        c["provenance"] = {"type": "heuristic"}
        stats["heuristic"] += 1

    ws, we = contact_window(c.get("contactFraction", -1.0))
    c["contactWindowStart"] = ws
    c["contactWindowEnd"] = we
    return c


def main():
    args = sys.argv[1:]
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    manifest_path = args[0] if len(args) > 0 else "arena-fc/Data/clips/clip_manifest.json"
    glb_path = args[1] if len(args) > 1 else GLB_DEFAULT
    # Allow running from repo root or from arena-fc/ directory.
    if not os.path.exists(manifest_path) and os.path.exists(os.path.basename(manifest_path).join(["Data/clips/", ""])):
        pass
    if not os.path.exists(manifest_path):
        alt = manifest_path.replace("arena-fc/", "", 1)
        if os.path.exists(alt):
            manifest_path = alt
    if not os.path.exists(glb_path):
        alt = glb_path.replace("arena-fc/", "", 1)
        if os.path.exists(alt):
            glb_path = alt

    glb = None
    if os.path.exists(glb_path):
        try:
            glb = GlbAnimations(glb_path)
            print(f"loaded GLB: {glb_path} ({len(glb.animations)} animations)")
        except Exception as e:
            print(f"warning: failed to load GLB {glb_path}: {e}; using heuristics")
            glb = None
    else:
        print(f"warning: GLB not found at {glb_path}; using heuristics")

    with open(manifest_path) as f:
        original = f.read()
    data = json.loads(original)
    data["version"] = 2
    data["hypermotionDataPlumbing"] = {
        "phase": 1,
        "samples": SAMPLES,
        "source": "glb+heuristic-fallback" if glb else "heuristic-v1-metadata",
        "note": "Plant/contact/root-velocity curves baked from authored GLB animation sampling when available; deterministic heuristic fallback otherwise.",
    }
    stats = {"glb": 0, "heuristic": 0}
    for c in data.get("clips", []):
        enrich_clip(c, glb, stats)
    out = json.dumps(data, indent=2) + "\n"
    if check:
        if out != original:
            print(f"FAIL: {manifest_path} is stale; run python3 arena-fc/Tools/bake_clip_manifest_v2.py")
            sys.exit(1)
        print(f"ok: {manifest_path} is up to date (glb={stats['glb']}, heuristic={stats['heuristic']})")
        return
    with open(manifest_path, "w") as f:
        f.write(out)
    print(f"enriched {len(data.get('clips', []))} clips -> {manifest_path} (glb={stats['glb']}, heuristic={stats['heuristic']})")


if __name__ == "__main__":
    main()
