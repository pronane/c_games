#!/usr/bin/env python3
"""
gen_match_video.py — render an "Aussie Rules 3D" gameplay highlight video.

Reads the MatchSim telemetry captured by tools/video/export_match.mjs
(tools/video/match_frames.json), rebuilds the game's Blender assets
(stadium, rigged players, ball) in-scene, animates them per frame and
renders an MP4 (Cycles, FFMPEG H264) showing YOU (Melbourne, team 0)
playing against the computer (Collingwood, team 1).

Run headless:
    cd tools/blender && ./headless_stubs.sh
    LD_LIBRARY_PATH=$PWD/stubs .venv/bin/python gen_match_video.py --benchmark 3
    LD_LIBRARY_PATH=$PWD/stubs .venv/bin/python gen_match_video.py --full
"""
import argparse
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ard_lib as ard          # noqa: E402
import gen_player              # noqa: E402
import gen_ball                # noqa: E402
import gen_stadium             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TELEMETRY = os.path.join(ROOT, "tools", "video", "match_frames.json")
OUT_MP4 = os.path.join(ROOT, "docs", "gameplay.mp4")

FPS = 24
RES_X, RES_Y = 854, 480

# Field geometry mirrors src/rules/types.ts FIELD
FIELD_A, FIELD_B, FIELD_N = 85.5, 73.0, 2.4
GOAL_LINE_X = 69.0
GOAL_POST_HALF = 3.2
BEHIND_POST_HALF = 9.6
GOAL_SQ_DEPTH = 9.0
CENTRE_SQ_HALF = 25.0

TEAM0 = ("MELBOURNE", (0.045, 0.095, 0.23))   # you
TEAM1 = ("COLLINGWOOD", (0.05, 0.05, 0.05))   # CPU

# Highlight edit list: telemetry frame ranges (goal at ~57% of each window).
WINDOWS = [(75, 225), (1520, 1670), (3903, 4053), (5275, 5425)]
INTRO_FRAMES = 60
OUTRO_FRAMES = 48

SEGMENTS = (
    [("intro", None)]
    + [("live", w) for w in WINDOWS]
    + [("outro", None)]
)


# --------------------------------------------------------------------------- #
#  Telemetry
# --------------------------------------------------------------------------- #

def load_telemetry():
    with open(TELEMETRY, "r") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
#  Pitch texture (grass + painted lines, PIL) — matches the in-game markings
# --------------------------------------------------------------------------- #

def super_point(theta, a=FIELD_A, b=FIELD_B, n=FIELD_N):
    c, s = math.cos(theta), math.sin(theta)
    x = math.copysign(abs(c) ** (2.0 / n), c) * a
    y = math.copysign(abs(s) ** (2.0 / n), s) * b
    return x, y


def build_pitch_texture(path, w=2048, h=1738):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def to_px(x, z):
        return ((x + FIELD_A) / (2 * FIELD_A) * w, (z + FIELD_B) / (2 * FIELD_B) * h)

    # grass base with mow stripes (along x)
    grass1 = (63, 122, 60, 255)
    grass2 = (72, 134, 68, 255)
    stripes = 22
    for i in range(stripes):
        x0 = i * w / stripes
        draw.rectangle([x0, 0, (i + 1) * w / stripes, h], fill=grass1 if i % 2 else grass2)

    # alpha mask: superellipse playing surface
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    poly = [to_px(*super_point(t / 288 * 2 * math.pi)) for t in range(288)]
    mdraw.polygon(poly, fill=255)
    img.putalpha(mask)

    white = (250, 250, 250, 255)
    lw = 4

    # boundary (superellipse wings + straight goal lines at x=±69)
    draw.line(poly + [poly[0]], fill=white, width=lw)
    gz = FIELD_B * (1 - (GOAL_LINE_X / FIELD_A) ** FIELD_N) ** (1 / FIELD_N)
    for sx in (-1, 1):
        p0 = to_px(sx * GOAL_LINE_X, -gz)
        p1 = to_px(sx * GOAL_LINE_X, gz)
        draw.line([p0, p1], fill=white, width=lw)

    # goal squares
    for sx in (-1, 1):
        x0, _ = to_px(sx * (GOAL_LINE_X - GOAL_SQ_DEPTH), 0)
        x1, _ = to_px(sx * GOAL_LINE_X, 0)
        _, z0 = to_px(0, -GOAL_POST_HALF)
        _, z1 = to_px(0, GOAL_POST_HALF)
        draw.rectangle([min(x0, x1), z0, max(x0, x1), z1], outline=white, width=lw)

    # 50 m arcs (radius 50 around each goal-line centre)
    for sx in (-1, 1):
        cx, cy = to_px(sx * GOAL_LINE_X, 0)
        rx = 50.0 / (2 * FIELD_A) * w
        ry = 50.0 / (2 * FIELD_B) * h
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=white, width=lw)

    # centre square + centre circle
    x0, y0 = to_px(-CENTRE_SQ_HALF, -CENTRE_SQ_HALF)
    x1, y1 = to_px(CENTRE_SQ_HALF, CENTRE_SQ_HALF)
    draw.rectangle([x0, y0, x1, y1], outline=white, width=lw)
    cx, cy = to_px(0, 0)
    r = 5.0 / (2 * FIELD_A) * w
    draw.ellipse([cx - r, cy - r * w / h, cx + r, cy + r * w / h], outline=white, width=lw)

    img.save(path)
    return path


# --------------------------------------------------------------------------- #
#  Scene build
# --------------------------------------------------------------------------- #

def build_scene():
    # gen_stadium.main() starts with clear_scene() (full factory reset) and
    # rebuilds the arena; suppress only its GLB export.
    ard.export_glb = lambda *a, **k: None
    gen_stadium.export_glb = lambda *a, **k: None
    gen_stadium.main()
    scene = bpy.context.scene  # fresh ref AFTER factory reset

    # --- pitch ------------------------------------------------------------- #
    tex_path = os.path.join(HERE, "_pitch_tex.png")
    build_pitch_texture(tex_path)
    img = bpy.data.images.load(tex_path)
    mat = bpy.data.materials.new("PitchLines")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0.06))
    pitch = bpy.context.active_object
    pitch.name = "Pitch"
    pitch.scale = (FIELD_A, FIELD_B, 1)
    pitch.data.materials.append(mat)

    # --- crowd (joined scattered boxes on both tiers) ---------------------- #
    build_crowd(scene)

    # --- lighting ---------------------------------------------------------- #
    world = bpy.data.worlds.new("Sky") if scene.world is None else scene.world
    scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()
    sky = wnt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(38)
        sky.sun_rotation = math.radians(135)
        sky.sun_intensity = 0.55
    except Exception:
        pass
    bg = wnt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.55
    out = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    wnt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-40))

    # --- ball (built in place; its own clear_scene is suppressed) ---------- #
    gen_ball.clear_scene = lambda: None
    gen_ball.export_glb = lambda *a, **k: None
    gen_ball.main()
    ball_parts = [o for o in scene.objects if o.name.lower().startswith(
        ("ball", "bladder", "seam", "lace"))]
    ball_root = bpy.data.objects.new("BallRoot", None)
    scene.collection.objects.link(ball_root)
    for o in ball_parts:
        o.parent = ball_root
    # normalise ball size to a Sherrin (~0.32 m long)
    if ball_parts:
        max_dim = max(o.dimensions.length for o in ball_parts)
        if max_dim > 0:
            s = 0.6 / max_dim
            ball_root.scale = (s, s, s)

    # --- camera ------------------------------------------------------------ #
    cam_data = bpy.data.cameras.new("Broadcast")
    cam_data.lens = 29
    cam_data.clip_end = 1200
    cam = bpy.data.objects.new("Broadcast", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    return scene, cam, ball_root


def build_crowd(scene):
    rng = random.Random(20261106)
    verts, faces = [], []
    colors = []

    def add_person(cx, cy, cz, col):
        s = 0.28
        base = len(verts)
        for dx in (-s, s):
            for dy in (-s, s):
                for dz in (0, 1.7):
                    verts.append((cx + dx, cy + dy, cz + dz))
        box_faces = [
            (0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
            (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3),
        ]
        for f in box_faces:
            faces.append(tuple(base + i for i in f))
            colors.append(col)

    palette = [
        (0.12, 0.15, 0.25), (0.22, 0.24, 0.3), (0.5, 0.5, 0.52),
        (0.15, 0.2, 0.35), (0.6, 0.55, 0.5), (0.25, 0.12, 0.1),
    ]

    tiers = [
        # (offset_start, depth_per_row, rise, z_start, rows)
        (6.4, 0.82, 0.42, 1.75, 26),
        (30.2, 0.86, 0.52, 13.5, 22),
    ]
    for off, depth, rise, z0, rows in tiers:
        for r in range(rows):
            for th_i in range(150):
                th = (th_i + rng.random()) / 150 * 2 * math.pi
                px, py = super_point(th, FIELD_A + 2.2 + off + r * depth,
                                     FIELD_B + 2.2 + off + r * depth)
                pz = z0 + r * rise + rng.uniform(0, 0.15)
                add_person(px, py, pz, palette[rng.randrange(len(palette))])

    mesh = bpy.data.meshes.new("Crowd")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new("Crowd", mesh)
    scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("CrowdMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.9
    mesh.materials.append(mat)
    # per-face colours (4 corners per face)
    attr = mesh.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
    flat = [c for c in colors for _ in range(4)]
    for i, c in enumerate(flat):
        attr.data[i].color = (c[0], c[1], c[2], 1.0)
    bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
    node = mat.node_tree.nodes.new("ShaderNodeAttribute")
    node.attribute_name = "Col"
    mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])


# --------------------------------------------------------------------------- #
#  Players
# --------------------------------------------------------------------------- #

def make_kit(mat_name, base_rgb, stripes=False):
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.7
    if stripes:
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = 2.2
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.45
        ramp.color_ramp.elements[1].position = 0.55
        ramp.color_ramp.elements[0].color = (*base_rgb, 1)
        ramp.color_ramp.elements[1].color = (0.85, 0.85, 0.85, 1)
        nt.links.new(wave.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*base_rgb, 1)
    return mat


def build_players(scene, telemetry):
    # one shared skinned mesh per team + per-player armatures
    segs = {n: (Vector(h), Vector(t)) for n, (h, t, _) in gen_player.SKELETON.items()}

    template_body = gen_player.build_body()
    template_arm = ard.build_armature("RigTemplate", gen_player.SKELETON)
    ard.proximity_skin(template_body, template_arm, segs, max_influences=3, power=3.2)

    kits = {
        0: make_kit("Kit0", TEAM0[1], stripes=False),
        1: make_kit("Kit1", TEAM1[1], stripes=True),
    }

    team_meshes = {}
    for team in (0, 1):
        me = template_body.data.copy()
        # replace the jersey + socks slots by material name (slot order varies)
        for i, m in enumerate(me.materials):
            if m is None:
                continue
            if m.name.startswith("jersey"):
                me.materials[i] = kits[team]
            elif m.name.startswith("socks") and team == 1:
                me.materials[i] = make_kit(f"Socks{team}", (0.08, 0.08, 0.08))
        team_meshes[team] = me

    players = {}
    all_ids = [int(p[0]) for p in telemetry["frames"][0]["players"]]
    for pid in all_ids:
        team = 0 if pid < 100 else 1
        arm = template_arm.copy()
        arm.data = template_arm.data.copy()
        arm.name = f"Rig{pid}"
        scene.collection.objects.link(arm)
        body = template_body.copy()
        body.data = team_meshes[team]
        body.name = f"Body{pid}"
        scene.collection.objects.link(body)
        for m in list(body.modifiers):
            if m.type == "ARMATURE":
                m.object = arm
        body.parent = arm
        players[pid] = {
            "arm": arm,
            "body": body,
            "pose": ard.Pose(arm, gen_player.BONE_HEADS),
            "phase": random.Random(pid).random(),
            "oneshot": None,   # (kind, frame)
        }

    # hide templates far away
    template_arm.location = (0, 0, -50)
    template_body.location = (0, 0, -50)
    return players


# --------------------------------------------------------------------------- #
#  Poses
# --------------------------------------------------------------------------- #

def loco_overrides(kind, s):
    """Locomotion cycles (s = stride phase sine in [-1, 1])."""
    if kind == "walk":
        return {
            "UpLeg.L": (-26 * s, 0, 0), "Leg.L": (max(0, 18 * s) + 12, 0, 0),
            "Foot.L": (10 * s, 0, 0),
            "UpLeg.R": (26 * s, 0, 0), "Leg.R": (max(0, -18 * s) + 12, 0, 0),
            "Foot.R": (-10 * s, 0, 0),
            "Arm.L": (22 * s, 0, -6), "ForeArm.L": (-18, 0, 0),
            "Arm.R": (-22 * s, 0, 6), "ForeArm.R": (-18, 0, 0),
            "Spine": (3, 0, -3 * s), "Spine1": (2, 0, -2 * s),
            "Head": (-2, 0, 3 * s),
        }
    if kind == "carrier":
        return {
            "UpLeg.L": (-38 * s, 0, 0), "Leg.L": (14 if s > 0 else 8, 0, 0),
            "UpLeg.R": (38 * s, 0, 0), "Leg.R": (14 if s < 0 else 8, 0, 0),
            "Arm.L": (34 * s, 0, -10), "ForeArm.L": (-55, 0, 0),
            "Arm.R": (10, 0, 10), "ForeArm.R": (-95, 0, -12),
            "Spine": (8, 0, -3 * s), "Spine1": (3, 0, -2 * s),
            "Head": (-10, 0, 3 * s),
        }
    lean, amp, tuck = (14, 1.2, 0.7) if kind == "sprint" else (9, 1.0, 0.55)
    return {
        "UpLeg.L": (-42 * amp * s, 0, 0), "Leg.L": ((12 + 48 * tuck) if s > 0 else 8, 0, 0),
        "Foot.L": (14 * s, 0, 0),
        "UpLeg.R": (42 * amp * s, 0, 0), "Leg.R": ((12 + 48 * tuck) if s < 0 else 8, 0, 0),
        "Foot.R": (-14 * s, 0, 0),
        "Arm.L": (38 * amp * s, 0, -8), "ForeArm.L": (-62, 0, 0),
        "Arm.R": (-38 * amp * s, 0, 8), "ForeArm.R": (-62, 0, 0),
        "Spine": (lean, 0, -4 * s), "Spine1": (4, 0, -3 * s),
        "Head": (-lean - 2, 0, 4 * s),
    }


# one-shot clip poses: list of (progress, overrides, root_offset)
CLIPS = {
    "kick": [
        (0.0, {"Spine": (6, 0, 0)}, (0, 0, 0)),
        (0.28, {"UpLeg.R": (-38, 0, 0), "Leg.R": (52, 0, 0), "Foot.R": (18, 0, 0),
                "UpLeg.L": (6, 0, 0), "Arm.L": (-36, 0, -12), "ForeArm.L": (-32, 0, 0),
                "Arm.R": (30, 0, 12), "Spine": (7, 0, 0)}, (0, 0, -0.05)),
        (0.52, {"UpLeg.R": (34, 0, 0), "Leg.R": (8, 0, 0), "Foot.R": (26, 0, 0),
                "UpLeg.L": (-8, 0, 0), "Arm.L": (30, 0, -14), "ForeArm.L": (-20, 0, 0),
                "Arm.R": (-34, 0, 16), "Spine": (-6, 0, 0)}, (0, 0, -0.03)),
        (1.0, {"Spine": (2, 0, 0)}, (0, 0, 0)),
    ],
    "handball": [
        (0.0, {}, (0, 0, 0)),
        (0.35, {"Arm.R": (-52, 0, 8), "ForeArm.R": (-38, 0, 0), "Arm.L": (24, 0, -10),
                "Spine": (8, 0, 4)}, (0, 0, -0.03)),
        (0.65, {"Arm.R": (-18, 0, 10), "ForeArm.R": (-72, 0, 0), "Spine": (4, 0, 2)},
                (0, 0, -0.02)),
        (1.0, {}, (0, 0, 0)),
    ],
    "mark": [
        (0.0, {"Spine": (4, 0, 0)}, (0, 0, 0)),
        (0.35, {"UpLeg.L": (-30, 0, 0), "Leg.L": (42, 0, 0), "UpLeg.R": (-16, 0, 0),
                "Leg.R": (30, 0, 0), "Arm.L": (-72, 0, -14), "ForeArm.L": (-24, 0, 0),
                "Arm.R": (-72, 0, 14), "ForeArm.R": (-24, 0, 0), "Spine": (-6, 0, 0)},
                (0, 0, 0.22)),
        (0.62, {"UpLeg.L": (-22, 0, 0), "Leg.L": (30, 0, 0), "Arm.L": (-58, 0, -12),
                "Arm.R": (-58, 0, 12), "Spine": (-2, 0, 0)}, (0, 0, 0.08)),
        (1.0, {"Spine": (2, 0, 0)}, (0, 0, 0)),
    ],
    "celebrate": [
        (0.0, {"Arm.L": (-20, 0, -20), "Arm.R": (-20, 0, 20)}, (0, 0, 0)),
        (0.3, {"Arm.L": (-150, 0, -18), "Arm.R": (-150, 0, 18), "Spine": (-8, 0, 0),
               "Head": (-12, 0, 0)}, (0, 0, 0.12)),
        (0.55, {"Arm.L": (-120, 0, -18), "Arm.R": (-150, 0, 18), "Head": (-12, 0, 8)},
                (0, 0, 0.04)),
        (0.8, {"Arm.L": (-150, 0, -18), "Arm.R": (-120, 0, 18), "Head": (-12, 0, -8)},
               (0, 0, 0.12)),
        (1.0, {"Arm.L": (-20, 0, -20), "Arm.R": (-20, 0, 20)}, (0, 0, 0)),
    ],
    "tackle": [
        (0.0, {}, (0, 0, 0)),
        (0.4, {"Arm.L": (-62, 0, -16), "ForeArm.L": (-32, 0, 0), "Arm.R": (-62, 0, 16),
               "ForeArm.R": (-32, 0, 0), "Spine": (18, 0, 0), "UpLeg.L": (-22, 0, 0),
               "Leg.L": (28, 0, 0)}, (0, 0, -0.14)),
        (1.0, {}, (0, 0, 0)),
    ],
}
CLIP_DUR = {"kick": 14, "handball": 10, "mark": 18, "celebrate": 34, "tackle": 12}


def lerp_pose(clip, t):
    keys = CLIPS[clip]
    for i in range(len(keys) - 1):
        t0, o0, r0 = keys[i]
        t1, o1, r1 = keys[i + 1]
        if t0 <= t <= t1:
            u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            over = {}
            for b in set(list(o0) + list(o1)):
                a = o0.get(b, (0, 0, 0))
                c = o1.get(b, (0, 0, 0))
                over[b] = tuple(a[k] + (c[k] - a[k]) * u for k in range(3))
            root = tuple(r0[k] + (r1[k] - r0[k]) * u for k in range(3))
            return over, root
    return keys[-1][1], keys[-1][2]


# --------------------------------------------------------------------------- #
#  HUD
# --------------------------------------------------------------------------- #

def emission_mat(name, rgb, strength=4.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def make_text(name, body, size, loc, mat, align="CENTER"):
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    ob = bpy.data.objects.new(name, curve)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    curve.materials.append(mat)
    return ob


def build_hud(cam):
    hud = bpy.data.objects.new("HUD", None)
    bpy.context.scene.collection.objects.link(hud)
    hud.parent = cam
    hud.location = (0, 0, -2.0)

    white = emission_mat("HUDWhite", (1, 1, 1), 3.0)
    yellow = emission_mat("HUDYellow", (1, 0.82, 0.1), 3.5)

    bar_bg = make_text("ScoreBar", "", 0.072, (0, 0.505, 0), white)
    clock = make_text("Clock", "", 0.055, (0, 0.425, 0), white)
    callout = make_text("Callout", "", 0.22, (0, 0.05, 0), yellow)
    title = make_text("Title", "", 0.18, (0, 0.05, 0), white)
    for t in (bar_bg, clock, callout, title):
        t.parent = hud
    return {"root": hud, "score": bar_bg, "clock": clock,
            "callout": callout, "title": title}


def build_control_ring():
    mat = emission_mat("RingYellow", (1, 0.85, 0.1), 2.5)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.05, minor_radius=0.08,
                                     location=(0, 0, -50))
    ring = bpy.context.active_object
    ring.name = "ControlRing"
    ring.data.materials.append(mat)
    bpy.ops.mesh.primitive_cone_add(radius1=0.28, depth=0.55, location=(0, 0, -50))
    arrow = bpy.context.active_object
    arrow.name = "ControlArrow"
    arrow.rotation_euler = (math.pi, 0, 0)
    arrow.data.materials.append(mat)
    return ring, arrow


# --------------------------------------------------------------------------- #
#  Frame mapping
# --------------------------------------------------------------------------- #

def segment_map():
    """Return list of (out_frame_start, kind, data, length) and total length."""
    segs = []
    f = 0
    for kind, data in SEGMENTS:
        if kind == "intro":
            length = INTRO_FRAMES
        elif kind == "outro":
            length = OUTRO_FRAMES
        else:
            length = data[1] - data[0]
        segs.append((f, kind, data, length))
        f += length
    return segs, f


# --------------------------------------------------------------------------- #
#  Main render state (module-level so the handler can reach it)
# --------------------------------------------------------------------------- #

STATE = {}


def orient_arm(entry, x, z, facing):
    arm = entry["arm"]
    arm.location = (x, z, 0)          # TS z -> Blender y
    arm.rotation_euler = (0, 0, facing + math.pi / 2)


def frame_handler(scene, depsgraph=None):
    st = STATE
    f = scene.frame_current
    segs = st["segs"]
    total = st["total"]
    if f > total:
        return
    # locate segment
    seg = segs[0]
    for s in segs:
        if f >= s[0]:
            seg = s
    out_start, kind, data, length = seg
    local = f - out_start

    hud = st["hud"]
    cam = st["cam"]

    if kind == "intro":
        t = local / max(1, length)
        ang = -2.6 + t * 1.35
        r = 175 - 70 * t
        cam.location = (r * math.cos(ang), r * math.sin(ang), 88 - 40 * t)
        target = Vector((0, 0, 4 + 10 * (1 - t)))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        hud["title"].data.body = "AUSSIE RULES"
        hud["title"].hide_render = False
        hud["callout"].data.body = "YOU  vs  CPU   ·   MCG"
        hud["callout"].data.size = 0.095
        hud["callout"].location = (0, -0.10, 0)
        hud["callout"].hide_render = False
        hud["score"].hide_render = True
        hud["clock"].hide_render = True
        st["ring"].location = (0, 0, -50)
        st["arrow"].location = (0, 0, -50)
        return

    if kind == "outro":
        t = local / max(1, length)
        ang = 2.1 + t * 0.9
        r = 110 + 60 * t
        cam.location = (r * math.cos(ang), r * math.sin(ang), 42 + 46 * t)
        target = Vector((0, 0, 8))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cap = st["cap"]
        last = cap["frames"][WINDOWS[-1][1] - 1]
        s0, s1 = last["scores"]
        hud["title"].data.body = "FULL TIME"
        hud["title"].hide_render = False
        hud["callout"].data.body = f"{TEAM0[0]} {s0}   —   {TEAM1[0]} {s1}"
        hud["callout"].data.size = 0.085
        hud["callout"].location = (0, -0.10, 0)
        hud["callout"].hide_render = False
        hud["score"].hide_render = True
        hud["clock"].hide_render = True
        st["ring"].location = (0, 0, -50)
        st["arrow"].location = (0, 0, -50)
        return

    # ---------------- live window ---------------- #
    tel_f = data[0] + local
    cap = st["cap"]
    frames = cap["frames"]
    tel_f = min(tel_f, len(frames) - 1)
    fr = frames[tel_f]
    prev = frames[max(0, tel_f - 1)]

    # ball
    bx, by, bz = fr["ball"]
    st["ball_root"].location = (bx, bz, by)
    pvx = bx - prev["ball"][0]
    pvy = by - prev["ball"][1]
    if abs(pvx) + abs(pvy) > 0.01:
        st["ball_root"].rotation_euler[1] -= pvx * 2.2
        st["ball_root"].rotation_euler[0] += pvy * 2.2

    # players
    prev_map = {int(p[0]): p for p in prev["players"]}

    # --- one-shot triggers for this frame (pre-pass) ------------------------ #
    evs = fr.get("events", [])
    triggers = {}
    prev_holder = holder_of(prev)
    now_holder = holder_of(fr)
    if prev_holder is not None and prev_holder != now_holder:
        kinds = [e.get("text") or "" for e in evs if e["type"] == "stat"]
        triggers[prev_holder] = "handball" if any("handball" in k for k in kinds) else "kick"
        st["last_kicker"] = prev_holder
    if now_holder is not None and any(e["type"] == "mark" for e in evs):
        triggers[now_holder] = "mark"
    if any(e["type"] == "goal" for e in evs) and st.get("last_kicker") is not None:
        triggers[st["last_kicker"]] = "celebrate"

    for p in fr["players"]:
        pid, x, z, y, facing, speed, anim = int(p[0]), p[1], p[2], p[3], p[4], p[5], int(p[6])
        entry = st["players"].get(pid)
        if entry is None:
            continue
        orient_arm(entry, x, z, facing)
        pm = prev_map.get(pid)
        moved = 0.0
        if pm:
            moved = math.hypot(x - pm[1], z - pm[2])

        oneshot = entry["oneshot"]
        # hide bench / far-away figures (saves per-frame sync + BVH)
        far = abs(z) > 71.5 or (y == 0 and abs(x) > 84)
        entry["body"].hide_render = far
        entry["arm"].hide_render = far
        if far:
            continue

        # trigger one-shots from the pre-pass
        if pid in triggers and entry["oneshot"] is None:
            entry["oneshot"] = (triggers[pid], tel_f)

        if entry["oneshot"]:
            okind, of0 = entry["oneshot"]
            dur = CLIP_DUR[okind]
            t = (tel_f - of0) / dur
            if t >= 1:
                entry["oneshot"] = None
            else:
                over, root = lerp_pose(okind, max(0.0, t))
                entry["pose"].apply(gen_player.pose_with(over, root))
                continue

        # locomotion
        stride = 2.4 if anim == 1 else 3.4
        entry["phase"] = (entry["phase"] + moved / max(0.4, stride)) % 1.0
        s = math.sin(entry["phase"] * 2 * math.pi)
        kind_name = {0: "idle", 1: "walk", 2: "run", 3: "sprint", 4: "carrier"}[anim]
        if kind_name == "idle":
            sway = math.sin(tel_f * 0.09 + pid) * 2.0
            over = {"Spine1": (2.0, 0, sway), "Head": (-1.2, 0, -sway),
                    "Arm.L": (0, 0, -4), "Arm.R": (0, 0, 4),
                    "ForeArm.L": (-8, 0, 0), "ForeArm.R": (-8, 0, 0)}
            entry["pose"].apply(gen_player.pose_with(over, (0, 0, -0.01 * abs(s))))
        else:
            over = loco_overrides(kind_name, s)
            root_z = -0.02 - 0.02 * abs(s)
            entry["pose"].apply(gen_player.pose_with(over, (0, 0, root_z)))

    # control ring on YOU
    cid = fr.get("controlledId", -1)
    cp = next((p for p in fr["players"] if int(p[0]) == cid), None)
    if cp:
        bob = 2.2 + 0.12 * math.sin(tel_f * 0.35)
        st["ring"].location = (cp[1], cp[2], 0.05)
        st["ring"].rotation_euler = (0, 0, tel_f * 0.03)
        st["arrow"].location = (cp[1], cp[2], bob)
    else:
        st["ring"].location = (0, 0, -50)
        st["arrow"].location = (0, 0, -50)

    # camera: broadcast side-on tracking + short goal orbit
    bpos = Vector((bx, bz, max(by, 1.2)))
    goal_recent = False
    for back in range(0, 40):
        ff = frames[max(0, tel_f - back)]
        if any(e["type"] == "goal" for e in ff.get("events", [])):
            goal_recent = True
            break

    if goal_recent:
        ang = tel_f * 0.05
        focus = Vector((bx, bz, 2.2))
        cam.location = focus + Vector((17 * math.cos(ang), 17 * math.sin(ang), 7.5))
    else:
        vel = Vector((bx - prev["ball"][0], bz - prev["ball"][2], 0))
        if vel.length > 0.05:
            d = vel.normalized()
        else:
            d = Vector((1, 0, 0))
        side = Vector((-d.y, d.x, 0))
        want = bpos + d * -16.0 + side * 11.0 + Vector((0, 0, 12.5))
        prev_cam = st.get("cam_pos")
        if prev_cam is None or (want - prev_cam).length > 30:
            st["cam_pos"] = want
        else:
            st["cam_pos"] = prev_cam.lerp(want, 0.16)
        cam.location = st["cam_pos"]
    # aim between the ball and the players so the contest stays in frame
    n = len(fr["players"])
    ccx = sum(p[1] for p in fr["players"]) / n
    ccz = sum(p[2] for p in fr["players"]) / n
    look = Vector((bx * 0.5 + ccx * 0.5, bz * 0.5 + ccz * 0.5, 1.5))
    cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()

    # HUD
    s0, s1 = fr["scores"]
    q = fr.get("quarter", 1)
    mm = int(fr.get("clock", 0)) // 60
    ss = int(fr.get("clock", 0)) % 60
    hud["score"].data.body = f"{TEAM0[0]} {s0}    —    {TEAM1[0]} {s1}"
    hud["score"].hide_render = False
    hud["clock"].data.body = f"Q{q}   {mm}:{ss:02d}"
    hud["clock"].hide_render = False
    hud["title"].hide_render = True

    call = None
    for e in fr.get("events", []):
        if e["type"] == "goal":
            call = "GOAL!"
        elif e["type"] == "behind" and call is None:
            call = "BEHIND"
        elif e["type"] == "mark" and call is None:
            call = "MARK"
        elif e["type"] == "fiftyMetres" and call is None:
            call = "50m PENALTY"
        elif e["type"] == "freeKick" and call is None:
            call = "FREE KICK"
    if call is None:
        # fade tail: show recent callout for 1.5s
        for back in range(1, 37):
            ff = frames[max(0, tel_f - back)]
            for e in ff.get("events", []):
                if e["type"] == "goal":
                    call = "GOAL!"
                    break
                if e["type"] == "mark" and back < 22:
                    call = "MARK"
                    break
            if call:
                break
    if call:
        hud["callout"].data.body = call
        hud["callout"].data.size = 0.22 if call == "GOAL!" else 0.11
        hud["callout"].location = (0, 0.12 if call == "GOAL!" else 0.05, 0)
        hud["callout"].hide_render = False
    else:
        hud["callout"].hide_render = True


def holder_of(fr):
    # ball holder is not exported; approximate via anim code 4 (carrier)
    for p in fr["players"]:
        if int(p[6]) == 4:
            return int(p[0])
    return None


# --------------------------------------------------------------------------- #
#  Render
# --------------------------------------------------------------------------- #

def configure_render(scene, out_path, full):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(os.environ.get("VIDEO_SAMPLES", "10" if full else "16"))
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    scene.cycles.max_bounces = 3
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 1
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.render.use_persistent_data = True
    scene.render.resolution_x = int(os.environ.get("VIDEO_RES_X", RES_X))
    scene.render.resolution_y = int(os.environ.get("VIDEO_RES_Y", RES_Y))
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = out_path
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Punchy"
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="render the complete MP4")
    ap.add_argument("--benchmark", type=int, default=0, help="render N sample frames only")
    ap.add_argument("--start", type=int, default=1, help="first frame for --benchmark")
    ap.add_argument("--out", default=OUT_MP4)
    args = ap.parse_args()

    cap = load_telemetry()
    scene, cam, ball_root = build_scene()
    players = build_players(scene, cap)
    hud = build_hud(cam)
    ring, arrow = build_control_ring()
    segs, total = segment_map()

    STATE.update({
        "cap": cap, "players": players, "hud": hud, "cam": cam,
        "ball_root": ball_root, "ring": ring, "arrow": arrow,
        "segs": segs, "total": total, "last_kicker": None,
    })

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    configure_render(scene, args.out, full=args.full)

    scene.frame_start = 1
    scene.frame_end = total if args.full else max(1, args.benchmark)
    bpy.app.handlers.frame_change_pre.append(frame_handler)

    print(f"[video] segments={[(k, d, l) for _, k, d, l in segs]} total={total} frames")
    if args.benchmark and not args.full:
        scene.render.image_settings.file_format = "PNG"
        import time as _time
        for i in range(args.start, args.start + args.benchmark):
            t0 = _time.time()
            scene.frame_set(i)
            scene.render.filepath = os.path.join(HERE, f"_bench_{i:03d}.png")
            bpy.ops.render.render(write_still=True)
            print(f"[video] bench frame {i} written in {_time.time() - t0:.1f}s")
    else:
        bpy.ops.render.render(animation=True)
        print(f"[video] wrote {args.out}")


if __name__ == "__main__":
    main()
