"""CPU software renderer for Arena FC gameplay capture.

Renders the soccer player mesh with baked clips using a simple rasterizer.
No GPU required — runs on any machine.

Usage:
    python render_gameplay.py --mode gameplay --frames 200 --out media/
    python render_gameplay.py --mode closeup --frames 100 --out media/
    python render_gameplay.py --mode player --frames 150 --out media/
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "Data")


def load_rig():
    """Load soccer_rig.json: mesh + bones + clips."""
    with open(os.path.join(DATA, "soccer_rig.json")) as f:
        d = json.load(f)
    bones = d["bones"]
    bone_index = {b["n"]: i for i, b in enumerate(bones)}
    pos = np.array(d["pos"], dtype=np.float32).reshape(-1, 3)
    idx_list = d["idx"]
    idx = np.concatenate([np.array(a, dtype=np.int32).reshape(-1, 3) for a in idx_list])
    bi = np.array(d["bi"], dtype=np.int32).reshape(-1, 4)
    w = np.array(d["w"], dtype=np.float32).reshape(-1, 4)
    mats = np.concatenate([
        np.full(len(np.array(a, dtype=np.int32)) // 3, i, dtype=np.int32)
        for i, a in enumerate(idx_list)
    ])
    clips = d["clips"]
    return bones, bone_index, pos, idx, bi, w, mats, clips


# ---------------------------------------------------------------------------
# Quaternion / matrix helpers
# ---------------------------------------------------------------------------

def quat_to_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)],
    ], dtype=np.float32)


def quat_slerp(q0, q1, t):
    dot = np.dot(q0, q1)
    if dot < 0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        q = q0 + t * (q1 - q0)
        return q / np.linalg.norm(q)
    theta = math.acos(max(-1, min(1, dot)))
    sin_theta = math.sin(theta)
    a = math.sin((1 - t) * theta) / sin_theta
    b = math.sin(t * theta) / sin_theta
    return a * q0 + b * q1


def mat_to_quat(m):
    trace = m[0,0] + m[1,1] + m[2,2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (m[2,1] - m[1,2]) * s
        y = (m[0,2] - m[2,0]) * s
        z = (m[1,0] - m[0,1]) * s
    elif m[0,0] > m[1,1] and m[0,0] > m[2,2]:
        s = 2.0 * math.sqrt(1.0 + m[0,0] - m[1,1] - m[2,2])
        w = (m[2,1] - m[1,2]) / s
        x = 0.25 * s
        y = (m[0,1] + m[1,0]) / s
        z = (m[0,2] + m[2,0]) / s
    elif m[1,1] > m[2,2]:
        s = 2.0 * math.sqrt(1.0 + m[1,1] - m[0,0] - m[2,2])
        w = (m[0,2] - m[2,0]) / s
        x = (m[0,1] + m[1,0]) / s
        y = 0.25 * s
        z = (m[1,2] + m[2,1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + m[2,2] - m[0,0] - m[1,1])
        w = (m[1,0] - m[0,1]) / s
        x = (m[0,2] + m[2,0]) / s
        y = (m[1,2] + m[2,1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=np.float32)
    return q / np.linalg.norm(q)


# ---------------------------------------------------------------------------
# Skeleton / skinning
# ---------------------------------------------------------------------------

def build_bone_transforms(bones, bone_index, clip_data, frame_f):
    fps = clip_data["fps"]
    frames = clip_data["frames"]
    loop = clip_data["loop"]
    f = frame_f % frames if loop else min(frame_f, frames - 1)
    f0 = int(math.floor(f))
    f1 = min(f0 + 1, frames - 1)
    frac = f - f0

    n_bones = len(bones)
    local_rot = np.zeros((n_bones, 4), dtype=np.float32)
    local_rot[:, 3] = 1.0
    local_trans = np.zeros((n_bones, 3), dtype=np.float32)

    clip_bones = clip_data["bones"]
    for bname, entry in clip_bones.items():
        if bname not in bone_index:
            continue
        bi = bone_index[bname]
        r = entry["r"]
        q0 = np.array(r[f0*4:f0*4+4], dtype=np.float32)
        q1 = np.array(r[f1*4:f1*4+4], dtype=np.float32)
        local_rot[bi] = quat_slerp(q0, q1, frac)
        if "t" in entry:
            t = entry["t"]
            tp0 = np.array(t[f0*3:f0*3+3], dtype=np.float32)
            tp1 = np.array(t[f1*3:f1*3+3], dtype=np.float32)
            local_trans[bi] = tp0 + frac * (tp1 - tp0)

    world_rot = np.zeros((n_bones, 4), dtype=np.float32)
    world_rot[:, 3] = 1.0
    world_trans = np.zeros((n_bones, 3), dtype=np.float32)

    for i, bone in enumerate(bones):
        parent = bone["p"]
        if parent >= 0:
            pr = quat_to_matrix(world_rot[parent])
            lr = quat_to_matrix(local_rot[i])
            wr = pr @ lr
            world_rot[i] = mat_to_quat(wr)
            offset = np.array(bone["h"], dtype=np.float32) - np.array(bones[parent]["h"], dtype=np.float32)
            world_trans[i] = world_trans[parent] + pr @ (offset + local_trans[i])
        else:
            world_rot[i] = local_rot[i]
            world_trans[i] = np.array(bone["h"], dtype=np.float32) + local_trans[i]

    return world_rot, world_trans


def skin_mesh(pos, bi, w, world_rot, world_trans, bones):
    n_verts = pos.shape[0]
    skinned = np.zeros_like(pos)
    for vi in range(n_verts):
        p = pos[vi]
        result = np.zeros(3, dtype=np.float32)
        total_w = 0.0
        for k in range(4):
            bidx = bi[vi, k]
            bw = w[vi, k]
            if bw < 1e-6 or bidx < 0 or bidx >= len(bones):
                continue
            rot = quat_to_matrix(world_rot[bidx])
            local = p - bones[bidx]["h"]
            transformed = world_trans[bidx] + rot @ local
            result += transformed * bw
            total_w += bw
        if total_w > 1e-6:
            skinned[vi] = result / total_w
        else:
            skinned[vi] = p
    return skinned


# ---------------------------------------------------------------------------
# Scene geometry
# ---------------------------------------------------------------------------

def make_pitch():
    """Create a pitch plane with line markings. Returns (verts, tris, colors)."""
    # Pitch dimensions: 105 x 68 metres (FIFA standard).
    # We'll render a section around the centre circle.
    verts = []
    tris = []
    colors = []

    # Grass plane (large quad).
    grass_c = np.array([0.10, 0.35, 0.14], dtype=np.float32)
    grass_c2 = np.array([0.12, 0.40, 0.16], dtype=np.float32)
    line_c = np.array([0.95, 0.95, 0.95], dtype=np.float32)

    # Ground plane: 60 x 40 m centred at origin, subdivided into grid.
    # Winding order: CCW when viewed from above (normal +Y).
    gw, gd = 30.0, 20.0
    n_sub = 12  # 12x8 grid of quads
    for iz in range(n_sub):
        for ix in range(n_sub):
            x0 = -gw + (2*gw) * ix / n_sub
            x1 = -gw + (2*gw) * (ix+1) / n_sub
            z0 = -gd + (2*gd) * iz / n_sub
            z1 = -gd + (2*gd) * (iz+1) / n_sub
            base = len(verts)
            verts.extend([[x0, 0, z0], [x0, 0, z1], [x1, 0, z1], [x1, 0, z0]])
            tris.append([base, base+1, base+2])
            tris.append([base, base+2, base+3])
            colors.extend([grass_c]*4)

    # Mowing stripes (alternating lighter/darker bands along x).
    stripe_w = 5.0
    for i in range(int(gw * 2 / stripe_w)):
        x0 = -gw + i * stripe_w
        x1 = x0 + stripe_w
        if i % 2 == 0:
            continue  # base grass already there
        base = len(verts)
        verts.extend([[x0, 0.001, -gd], [x0, 0.001, gd], [x1, 0.001, gd], [x1, 0.001, -gd]])
        tris.append([base, base+1, base+2])
        tris.append([base, base+2, base+3])
        colors.extend([grass_c2]*4)

    # Centre circle (radius 9.15m).
    cx, cz, cr = 0.0, 0.0, 9.15
    n_seg = 64
    line_w = 0.12
    for i in range(n_seg):
        a0 = 2 * math.pi * i / n_seg
        a1 = 2 * math.pi * (i+1) / n_seg
        base = len(verts)
        verts.extend([
            [cx + (cr - line_w) * math.cos(a0), 0.002, cz + (cr - line_w) * math.sin(a0)],
            [cx + (cr - line_w) * math.cos(a1), 0.002, cz + (cr - line_w) * math.sin(a1)],
            [cx + cr * math.cos(a1), 0.002, cz + cr * math.sin(a1)],
            [cx + cr * math.cos(a0), 0.002, cz + cr * math.sin(a0)],
        ])
        tris.append([base, base+1, base+2])
        tris.append([base, base+2, base+3])
        colors.extend([line_c]*4)

    # Centre line.
    base = len(verts)
    verts.extend([[0, 0.002, -gd], [0, 0.002, gd], [0.12, 0.002, gd], [0.12, 0.002, -gd]])
    tris.append([base, base+1, base+2])
    tris.append([base, base+2, base+3])
    colors.extend([line_c]*4)

    # Centre spot.
    base = len(verts)
    verts.extend([[-0.11, 0.002, -0.11], [-0.11, 0.002, 0.11], [0.11, 0.002, 0.11], [0.11, 0.002, -0.11]])
    tris.append([base, base+1, base+2])
    tris.append([base, base+2, base+3])
    colors.extend([line_c]*4)

    return np.array(verts, dtype=np.float32), np.array(tris, dtype=np.int32), np.array(colors, dtype=np.float32)


def make_ball(radius=0.11):
    """Create a simple ball (icosphere approximation)."""
    verts = []
    tris = []
    colors = []

    # UV sphere.
    n_lat, n_lon = 12, 16
    for i in range(n_lat + 1):
        theta = math.pi * i / n_lat
        for j in range(n_lon):
            phi = 2 * math.pi * j / n_lon
            x = radius * math.sin(theta) * math.cos(phi)
            y = radius * math.cos(theta)
            z = radius * math.sin(theta) * math.sin(phi)
            verts.append([x, y, z])
            # Pentagon pattern: alternate white/black by lat/lon.
            if (i + j) % 3 == 0:
                colors.append([0.05, 0.05, 0.05])
            else:
                colors.append([0.95, 0.95, 0.95])

    for i in range(n_lat):
        for j in range(n_lon):
            a = i * n_lon + j
            b = i * n_lon + (j + 1) % n_lon
            c = (i + 1) * n_lon + j
            d = (i + 1) * n_lon + (j + 1) % n_lon
            tris.append([a, c, b])
            tris.append([b, c, d])

    return np.array(verts, dtype=np.float32), np.array(tris, dtype=np.int32), np.array(colors, dtype=np.float32)


def make_shadow_blob(radius=0.5):
    """Create a dark ellipse on the ground for player shadow."""
    verts = []
    tris = []
    colors = []
    n = 16
    verts.append([0, 0.003, 0])
    colors.append([0.0, 0.0, 0.0])
    for i in range(n):
        a = 2 * math.pi * i / n
        verts.append([radius * math.cos(a), 0.003, radius * 0.6 * math.sin(a)])
        colors.append([0.0, 0.0, 0.0])
    for i in range(n):
        tris.append([0, 1 + i, 1 + (i + 1) % n])
    return np.array(verts, dtype=np.float32), np.array(tris, dtype=np.int32), np.array(colors, dtype=np.float32)


# ---------------------------------------------------------------------------
# Rasterizer
# ---------------------------------------------------------------------------

MAT_COLORS = np.array([
    [0.85, 0.65, 0.50],  # 0 skin
    [0.85, 0.15, 0.24],  # 1 jersey (red)
    [0.08, 0.13, 0.26],  # 2 shorts (dark blue)
    [0.97, 0.97, 0.95],  # 3 socks (white)
    [1.00, 0.82, 0.40],  # 4 boots (gold)
    [0.14, 0.09, 0.07],  # 5 hair (dark)
    [0.10, 0.10, 0.10],  # 6 dark
    [0.50, 0.50, 0.50],  # 7 grey
    [0.20, 0.20, 0.20],  # 8 dark grey
    [0.62, 0.75, 0.85],  # 9 eyes (bright iris)
], dtype=np.float32)


def compute_normals(verts, tris):
    """Compute per-vertex normals from triangle faces."""
    normals = np.zeros_like(verts)
    for t in tris:
        v0, v1, v2 = verts[t[0]], verts[t[1]], verts[t[2]]
        n = np.cross(v1 - v0, v2 - v0)
        length = np.linalg.norm(n)
        if length > 1e-8:
            n = n / length
        normals[t[0]] += n
        normals[t[1]] += n
        normals[t[2]] += n
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths < 1e-8] = 1.0
    return normals / lengths


def render_scene(objects, camera_pos, camera_target, width, height,
                 sky_top=(0.20, 0.35, 0.60), sky_bot=(0.55, 0.65, 0.80)):
    """Render a list of (verts, tris, colors, normals) objects.

    Colors can be per-vertex or per-triangle (matched by tri index).
    """
    img = np.zeros((height, width, 3), dtype=np.float32)
    # Sky gradient.
    for y in range(height):
        t = y / height
        img[y, :, 0] = sky_bot[0] * (1 - t) + sky_top[0] * t
        img[y, :, 1] = sky_bot[1] * (1 - t) + sky_top[1] * t
        img[y, :, 2] = sky_bot[2] * (1 - t) + sky_top[2] * t

    # Camera basis.
    fwd = camera_target - camera_pos
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0, 1, 0], dtype=np.float32))
    if np.linalg.norm(right) < 1e-6:
        right = np.array([1, 0, 0], dtype=np.float32)
    right = right / np.linalg.norm(right)
    up = np.cross(right, fwd)

    # Light direction (sun from upper-left-front).
    light_dir = np.array([-0.4, 0.8, 0.3], dtype=np.float32)
    light_dir = light_dir / np.linalg.norm(light_dir)
    ambient = 0.35

    zbuf = np.full((height, width), np.inf, dtype=np.float32)
    fov = 1.2

    for verts, tris, colors, normals in objects:
        # Transform to camera space.
        rel = verts - camera_pos
        cam_x = rel @ right
        cam_y = rel @ up
        cam_z = rel @ fwd
        valid = cam_z > 0.05

        screen_x = np.zeros_like(cam_x)
        screen_y = np.zeros_like(cam_y)
        screen_x[valid] = (cam_x[valid] / cam_z[valid]) * fov * width * 0.5 + width * 0.5
        screen_y[valid] = height * 0.5 - (cam_y[valid] / cam_z[valid]) * fov * height * 0.5

        # Per-vertex colors (if colors match vertex count) or per-tri.
        per_vertex = len(colors) == len(verts)

        for ti in range(tris.shape[0]):
            v0, v1, v2 = tris[ti]
            if not (valid[v0] and valid[v1] and valid[v2]):
                continue
            x0, y0 = screen_x[v0], screen_y[v0]
            x1, y1 = screen_x[v1], screen_y[v1]
            x2, y2 = screen_x[v2], screen_y[v2]
            z0, z1, z2 = cam_z[v0], cam_z[v1], cam_z[v2]

            min_x = max(0, int(min(x0, x1, x2)))
            max_x = min(width - 1, int(max(x0, x1, x2)) + 1)
            min_y = max(0, int(min(y0, y1, y2)))
            max_y = min(height - 1, int(max(y0, y1, y2)) + 1)
            if min_x > max_x or min_y > max_y:
                continue

            denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(denom) < 1e-8:
                continue

            # Face normal for lighting.
            if normals is not None:
                fn = normals[v0] * 0.33 + normals[v1] * 0.33 + normals[v2] * 0.33
                fn_len = np.linalg.norm(fn)
                if fn_len > 1e-8:
                    fn = fn / fn_len
                else:
                    fn = np.array([0, 1, 0], dtype=np.float32)
            else:
                fn = np.array([0, 1, 0], dtype=np.float32)

            ndl = max(0.0, float(np.dot(fn, light_dir)))
            brightness = ambient + (1.0 - ambient) * ndl

            if per_vertex:
                c0, c1, c2 = colors[v0], colors[v1], colors[v2]
            else:
                c = colors[ti % len(colors)]
                c0 = c1 = c2 = c

            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
                    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = w0 * z0 + w1 * z1 + w2 * z2
                    if z < zbuf[py, px]:
                        zbuf[py, px] = z
                        col = (c0 * w0 + c1 * w1 + c2 * w2) * brightness
                        img[py, px] = col

    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# PNG writer
# ---------------------------------------------------------------------------

def write_png(path, img):
    import zlib
    h, w, _ = img.shape
    raw = b""
    for y in range(h):
        raw += b"\x00" + img[y].tobytes()
    compressed = zlib.compress(raw)
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
        return c
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CPU renderer for Arena FC")
    parser.add_argument("--mode", default="player", choices=["player", "gameplay", "closeup"])
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--out", default="media")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=544)
    parser.add_argument("--clip", default="soccer_run")
    args = parser.parse_args()

    print("Loading rig data...")
    bones, bone_index, pos, idx, bi, w, mats, clips = load_rig()
    print(f"  {len(bones)} bones, {pos.shape[0]} verts, {idx.shape[0]} tris, {len(clips)} clips")

    if args.clip not in clips:
        print(f"  Clip {args.clip} not found, using soccer_run")
        args.clip = "soccer_run"

    clip_data = clips[args.clip]
    print(f"  Clip: {args.clip} ({clip_data['frames']} frames @ {clip_data['fps']} fps, loop={clip_data['loop']})")

    # Pre-build scene geometry.
    pitch_v, pitch_t, pitch_c = make_pitch()
    pitch_n = compute_normals(pitch_v, pitch_t)
    ball_v, ball_t, ball_c = make_ball()
    ball_n = compute_normals(ball_v, ball_t)
    shadow_v, shadow_t, shadow_c = make_shadow_blob()

    # Player material colors per triangle.
    player_colors = MAT_COLORS[mats % len(MAT_COLORS)]

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, "screenshots"), exist_ok=True)

    # Camera setup by mode.
    if args.mode == "closeup":
        cam_pos = np.array([1.5, 2.0, 2.5], dtype=np.float32)
        cam_target = np.array([0, 0.9, 0], dtype=np.float32)
    elif args.mode == "gameplay":
        cam_pos = np.array([0, 18.0, 28.0], dtype=np.float32)
        cam_target = np.array([0, 0, 0], dtype=np.float32)
    else:  # player
        cam_pos = np.array([2.5, 3.0, 4.0], dtype=np.float32)
        cam_target = np.array([0, 0.8, 0], dtype=np.float32)

    print(f"Rendering {args.frames} frames ({args.mode})...")
    for fi in range(args.frames):
        frame_f = fi * (clip_data["fps"] / 20.0)
        world_rot, world_trans = build_bone_transforms(bones, bone_index, clip_data, frame_f)
        skinned = skin_mesh(pos, bi, w, world_rot, world_trans, bones)
        player_n = compute_normals(skinned, idx)

        # Ball position: in front of player, bouncing slightly.
        ball_y = 0.11 + 0.05 * abs(math.sin(fi * 0.3))
        ball_pos = np.array([0.4, ball_y, 0.8], dtype=np.float32)
        ball_verts = ball_v + ball_pos

        objects = [
            (pitch_v, pitch_t, pitch_c, pitch_n),
            (ball_verts, ball_t, ball_c, ball_n),
            (skinned, idx, player_colors, player_n),
        ]

        img = render_scene(objects, cam_pos, cam_target, args.width, args.height)
        out_path = os.path.join(args.out, "screenshots", f"frame_{fi:04d}.png")
        write_png(out_path, img)

        if fi % 20 == 0:
            print(f"  Frame {fi}/{args.frames}")

    print(f"Done. Frames saved to {args.out}/screenshots/")


if __name__ == "__main__":
    main()
