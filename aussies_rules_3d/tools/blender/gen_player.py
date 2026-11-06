"""Generate `player.glb` — the rigged, skinned, animated Aussie rules player.

Built with Blender (bpy 4.5) as a real 3D model:
  * a 20-bone humanoid armature (hips, spine, chest, neck, head, arms, legs),
  * a skinned body mesh (jersey, shorts, socks, boots, skin, hair materials),
  * 10 baked animation clips (idle, walk, run, sprint, run-with-ball, kick,
    handball, tackle, mark jump, celebrate, hit the deck).

Run:  .venv/bin/python gen_player.py
Out:  ../../assets/player.glb
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from ard_lib import (
    Pose,
    add_box,
    add_cylinder,
    add_sphere,
    assign_material,
    build_armature,
    clear_scene,
    export_glb,
    join_objects,
    make_material,
    proximity_skin,
)

OUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "public", "assets", "player.glb")
)

# --------------------------------------------------------------------------- #
#  Skeleton (Z-up, facing -Y). name: (head, tail, parent)
# --------------------------------------------------------------------------- #

SKELETON = {
    "Hips":       ((0, 0, 1.00), (0, 0, 1.14), None),
    "Spine":      ((0, 0, 1.14), (0, 0, 1.32), "Hips"),
    "Spine1":     ((0, 0, 1.32), (0, 0, 1.50), "Spine"),
    "Neck":       ((0, 0, 1.50), (0, 0, 1.60), "Spine1"),
    "Head":       ((0, 0, 1.60), (0, 0, 1.82), "Neck"),
    "Shoulder.L": ((0.04, 0, 1.46), (0.20, 0, 1.46), "Spine1"),
    "Arm.L":      ((0.20, 0, 1.46), (0.245, 0, 1.18), "Shoulder.L"),
    "ForeArm.L":  ((0.245, 0, 1.18), (0.265, 0, 0.94), "Arm.L"),
    "Hand.L":     ((0.265, 0, 0.94), (0.275, 0, 0.82), "ForeArm.L"),
    "Shoulder.R": ((-0.04, 0, 1.46), (-0.20, 0, 1.46), "Spine1"),
    "Arm.R":      ((-0.20, 0, 1.46), (-0.245, 0, 1.18), "Shoulder.R"),
    "ForeArm.R":  ((-0.245, 0, 1.18), (-0.265, 0, 0.94), "Arm.R"),
    "Hand.R":     ((-0.265, 0, 0.94), (-0.275, 0, 0.82), "ForeArm.R"),
    "UpLeg.L":    ((0.10, 0, 1.00), (0.11, 0, 0.55), "Hips"),
    "Leg.L":      ((0.11, 0, 0.55), (0.11, 0, 0.10), "UpLeg.L"),
    "Foot.L":     ((0.11, 0, 0.10), (0.11, -0.14, 0.03), "Leg.L"),
    "UpLeg.R":    ((-0.10, 0, 1.00), (-0.11, 0, 0.55), "Hips"),
    "Leg.R":      ((-0.11, 0, 0.55), (-0.11, 0, 0.10), "UpLeg.R"),
    "Foot.R":     ((-0.11, 0, 0.10), (-0.11, -0.14, 0.03), "Leg.R"),
}

BONE_HEADS = {name: data[0] for name, data in SKELETON.items()}


def build_body():
    """Body mesh parts as primitives, joined into one skinned mesh."""
    skin = make_material("skin", (0.85, 0.66, 0.53), roughness=0.55)
    jersey = make_material("jersey", (0.92, 0.92, 0.92), roughness=0.7)
    shorts = make_material("shorts", (0.95, 0.95, 0.95), roughness=0.7)
    socks = make_material("socks", (0.95, 0.95, 0.95), roughness=0.7)
    boots = make_material("boots", (0.08, 0.08, 0.09), roughness=0.5)
    hair = make_material("hair", (0.16, 0.11, 0.08), roughness=0.8)

    parts = []

    def part(ob, mat):
        assign_material(ob, mat)
        parts.append(ob)
        return ob

    # -- head & neck -------------------------------------------------------- #
    part(add_cylinder("neck", 0.058, 0.16, (0, 0, 1.545), verts=12), skin)
    head = part(add_sphere("head", 0.115, (0, 0, 1.705), seg=20, rings=14), skin)
    head.scale = (0.92, 1.0, 1.12)
    nose = part(add_box("nose", (0.035, 0.05, 0.055), (0, -0.115, 1.685)), skin)
    for sx, name in ((1, "earL"), (-1, "earR")):
        ear = part(add_sphere(name, 0.032, (sx * 0.108, 0.005, 1.70), seg=10, rings=8), skin)
        ear.scale = (0.55, 1.0, 1.25)
    hair_ob = part(add_sphere("hair", 0.118, (0, 0.022, 1.75), seg=18, rings=12), hair)
    hair_ob.scale = (0.95, 1.02, 0.92)

    # -- torso ------------------------------------------------------------- #
    part(add_box("pelvis", (0.30, 0.21, 0.22), (0, 0, 1.02)), shorts)
    part(add_box("belly", (0.335, 0.225, 0.20), (0, 0, 1.18)), jersey)
    chest = part(add_box("chest", (0.40, 0.245, 0.30), (0, 0, 1.385)), jersey)
    chest.scale = (1.0, 1.0, 1.0)
    for sx, name in ((1, "deltL"), (-1, "deltR")):
        part(add_sphere(name, 0.098, (sx * 0.205, 0, 1.44), seg=14, rings=10), jersey)
    # collar
    part(add_cylinder("collar", 0.078, 0.055, (0, 0, 1.545), verts=12), jersey)

    # -- arms -------------------------------------------------------------- #
    for sx, tag in ((1, "L"), (-1, "R")):
        sleeve = part(
            add_cylinder(f"sleeve{tag}", 0.072, 0.20, (sx * 0.225, 0, 1.345), verts=12),
            jersey,
        )
        part(add_cylinder(f"uparm{tag}", 0.056, 0.24, (sx * 0.235, 0, 1.17), verts=12), skin)
        part(add_cylinder(f"forearm{tag}", 0.049, 0.24, (sx * 0.256, 0, 0.985), verts=12), skin)
        part(add_box(f"hand{tag}", (0.068, 0.105, 0.145), (sx * 0.267, -0.01, 0.865)), skin)

    # -- legs -------------------------------------------------------------- #
    for sx, tag in ((1, "L"), (-1, "R")):
        part(add_box(f"shortleg{tag}", (0.185, 0.21, 0.26), (sx * 0.107, 0, 0.905)), shorts)
        part(add_cylinder(f"thigh{tag}", 0.088, 0.30, (sx * 0.108, 0, 0.70), verts=12), skin)
        part(add_cylinder(f"knee{tag}", 0.070, 0.10, (sx * 0.11, 0, 0.545), verts=12), skin)
        part(add_cylinder(f"shin{tag}", 0.058, 0.36, (sx * 0.11, 0, 0.33), verts=12), socks)
        part(add_cylinder(f"socktop{tag}", 0.068, 0.07, (sx * 0.11, 0, 0.505), verts=12), socks)
        part(add_box(f"boot{tag}", (0.105, 0.26, 0.105), (sx * 0.11, -0.055, 0.055)), boots)
        part(add_box(f"bootnose{tag}", (0.095, 0.06, 0.06), (sx * 0.11, -0.185, 0.035)), boots)

    body = join_objects(parts, "PlayerBody")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return body


# --------------------------------------------------------------------------- #
#  Animation clips.  Sign conventions (player faces -Y, Z up):
#     +X rotation:  hanging limbs swing BACK, torso leans FORWARD
#     -X rotation:  hanging limbs swing FORWARD, torso leans BACK
#     +Y rotation:  limbs swing to the player's LEFT (+X side)
#     +Z rotation:  yaw counter-clockwise (from above)
# --------------------------------------------------------------------------- #

def base_pose():
    """Neutral standing pose (all zeros)."""
    return [
        ("Hips", (0, 0, 0)), ("Spine", (0, 0, 0)), ("Spine1", (0, 0, 0)),
        ("Neck", (0, 0, 0)), ("Head", (0, 0, 0)),
        ("Shoulder.L", (0, 0, 0)), ("Arm.L", (0, 0, 0)), ("ForeArm.L", (0, 0, 0)),
        ("Shoulder.R", (0, 0, 0)), ("Arm.R", (0, 0, 0)), ("ForeArm.R", (0, 0, 0)),
        ("UpLeg.L", (0, 0, 0)), ("Leg.L", (0, 0, 0)), ("Foot.L", (0, 0, 0)),
        ("UpLeg.R", (0, 0, 0)), ("Leg.R", (0, 0, 0)), ("Foot.R", (0, 0, 0)),
    ]


def pose_with(overrides, root=(0, 0, 0)):
    p = dict((b, v) for b, v in base_pose())
    for b, v in overrides.items():
        p[b] = v
    out = [(b, v) for b, v in p.items()]
    out[0] = ("Hips", p["Hips"], root)
    return out


def make_action(arm_ob, name):
    if arm_ob.animation_data is None:
        arm_ob.animation_data_create()
    action = bpy.data.actions.new(name)
    arm_ob.animation_data.action = action
    return action


def build_anims(arm_ob):
    pose = Pose(arm_ob, BONE_HEADS)
    clips = {}

    def clip(name, keys):
        """keys: list of (frame, overrides, root_offset)."""
        make_action(arm_ob, name)
        for frame, over, root in keys:
            pose.key(frame, pose_with(over, root))
        clips[name] = arm_ob.animation_data.action
        return arm_ob.animation_data.action

    # ---- idle: gentle breathing, 2s loop --------------------------------- #
    sway = {"Spine1": (2.5, 0, 0), "Head": (-1.5, 0, 0),
            "Arm.L": (0, 0, -4), "Arm.R": (0, 0, 4),
            "ForeArm.L": (-8, 0, 0), "ForeArm.R": (-8, 0, 0)}
    clip("idle", [
        (1, {}, (0, 0, 0)),
        (13, sway, (0, 0, -0.012)),
        (25, {}, (0, 0, 0)),
        (37, sway, (0, 0, -0.012)),
        (48, {}, (0, 0, 0)),
    ])

    # ---- walk: 2s loop --------------------------------------------------- #
    def walk_frame(f, phase):
        """phase 0 or 1; legs alternate; arms counter-swing."""
        s = 1 if phase == 0 else -1
        return (f, {
            "UpLeg.L": (-26 * s, 0, 0), "Leg.L": (max(0, 18 * s) + 12, 0, 0),
            "Foot.L": (10 * s, 0, 0),
            "UpLeg.R": (26 * s, 0, 0), "Leg.R": (max(0, -18 * s) + 12, 0, 0),
            "Foot.R": (-10 * s, 0, 0),
            "Arm.L": (22 * s, 0, -6), "ForeArm.L": (-18, 0, 0),
            "Arm.R": (-22 * s, 0, 6), "ForeArm.R": (-18, 0, 0),
            "Spine": (3, 0, -3 * s), "Spine1": (2, 0, -2 * s),
            "Head": (-2, 0, 3 * s),
        }, (0, 0, -0.018 * (1 - abs(0))))
    clip("walk", [
        walk_frame(1, 0), walk_frame(13, 1), walk_frame(25, 0),
        walk_frame(37, 1), walk_frame(48, 0),
    ])

    # ---- run: 1s loop ---------------------------------------------------- #
    def run_frame(f, s, lean=9, amp=1.0, tuck=0.55):
        return (f, {
            "UpLeg.L": (-42 * amp * s, 0, 0), "Leg.L": ((12 + 48 * tuck) if s > 0 else 8, 0, 0),
            "Foot.L": (14 * s, 0, 0),
            "UpLeg.R": (42 * amp * s, 0, 0), "Leg.R": ((12 + 48 * tuck) if s < 0 else 8, 0, 0),
            "Foot.R": (-14 * s, 0, 0),
            "Arm.L": (38 * amp * s, 0, -8), "ForeArm.L": (-62, 0, 0),
            "Arm.R": (-38 * amp * s, 0, 8), "ForeArm.R": (-62, 0, 0),
            "Spine": (lean, 0, -4 * s), "Spine1": (4, 0, -3 * s),
            "Head": (-lean - 2, 0, 4 * s),
        }, (0, 0, -0.03))
    clip("run", [
        run_frame(1, 1), run_frame(7, 0), run_frame(13, -1),
        run_frame(19, 0), run_frame(25, 1),
    ])
    clip("sprint", [
        run_frame(1, 1, lean=14, amp=1.2), run_frame(6, 0, lean=14, amp=1.2, tuck=0.7),
        run_frame(11, -1, lean=14, amp=1.2), run_frame(16, 0, lean=14, amp=1.2, tuck=0.7),
        run_frame(21, 1, lean=14, amp=1.2),
    ])

    # ---- run with ball (right arm tucked) -------------------------------- #
    def runball_frame(f, s):
        return (f, {
            "UpLeg.L": (-38 * s, 0, 0), "Leg.L": (14 if s > 0 else 8, 0, 0),
            "UpLeg.R": (38 * s, 0, 0), "Leg.R": (14 if s < 0 else 8, 0, 0),
            "Arm.L": (34 * s, 0, -10), "ForeArm.L": (-55, 0, 0),
            "Arm.R": (10, 0, 10), "ForeArm.R": (-95, 0, -12),
            "Spine": (8, 0, -3 * s), "Spine1": (3, 0, -2 * s),
            "Head": (-10, 0, 3 * s),
        }, (0, 0, -0.028))
    clip("run_ball", [
        runball_frame(1, 1), runball_frame(7, 0), runball_frame(13, -1),
        runball_frame(19, 0), runball_frame(25, 1),
    ])

    # ---- drop punt kick --------------------------------------------------- #
    clip("kick", [
        (1, {"Spine": (2, 0, 0), "Arm.L": (0, 0, -12), "Arm.R": (0, 0, 12)}, (0, 0, 0)),
        # plant & wind-up: kicking leg (R) back, arms out
        (9, {
            "UpLeg.R": (38, 0, -6), "Leg.R": (58, 0, 0), "Foot.R": (-18, 0, 0),
            "UpLeg.L": (-12, 0, 0), "Leg.L": (16, 0, 0), "Foot.L": (8, 0, 0),
            "Spine": (-4, 8, 14), "Spine1": (-2, 4, 10),
            "Arm.L": (-26, 0, -38), "ForeArm.L": (-30, 0, 0),
            "Arm.R": (30, 0, 26), "ForeArm.R": (-24, 0, 0),
            "Head": (2, -6, -12),
        }, (0, 0, -0.02)),
        # contact: leg swings through
        (17, {
            "UpLeg.R": (-52, 0, -4), "Leg.R": (6, 0, 0), "Foot.R": (22, 0, 0),
            "UpLeg.L": (6, 0, 0), "Leg.L": (10, 0, 0), "Foot.L": (14, 0, 0),
            "Spine": (10, -6, 8), "Spine1": (6, -3, 6),
            "Arm.L": (-48, 0, -30), "ForeArm.L": (-40, 0, 0),
            "Arm.R": (42, 0, 22), "ForeArm.R": (-30, 0, 0),
            "Head": (-4, 4, -8),
        }, (0, 0, -0.055)),
        # follow-through
        (25, {
            "UpLeg.R": (-78, 0, -2), "Leg.R": (22, 0, 0), "Foot.R": (30, 0, 0),
            "UpLeg.L": (10, 0, 0), "Leg.L": (8, 0, 0),
            "Spine": (16, -4, 4), "Spine1": (8, -2, 3),
            "Arm.L": (-30, 0, -24), "ForeArm.L": (-34, 0, 0),
            "Arm.R": (26, 0, 18), "ForeArm.R": (-26, 0, 0),
            "Head": (-8, 2, -4),
        }, (0, 0, -0.04)),
        # recover
        (36, {"Arm.L": (0, 0, -10), "Arm.R": (0, 0, 10)}, (0, 0, 0)),
    ])

    # ---- handball (ball in left hand, punched with right fist) ------------ #
    clip("handball", [
        (1, {}, (0, 0, 0)),
        (7, {
            "Arm.L": (28, 0, -22), "ForeArm.L": (-105, 0, -18), "Hand.L": (-15, 0, 0),
            "Arm.R": (-18, 0, 16), "ForeArm.R": (-95, 0, 10),
            "Spine": (4, 0, -10), "Spine1": (2, 0, -8),
            "Head": (-2, 6, 8),
        }, (0, 0, -0.015)),
        (13, {
            "Arm.L": (36, 0, -14), "ForeArm.L": (-120, 0, -12), "Hand.L": (-20, 0, 0),
            "Arm.R": (-52, 0, 22), "ForeArm.R": (-70, 0, 6),
            "Spine": (7, 0, -16), "Spine1": (4, 0, -12),
            "Head": (-3, 8, 12),
        }, (0, 0, -0.03)),
        (20, {
            "Arm.L": (30, 0, -18), "ForeArm.L": (-110, 0, -14),
            "Arm.R": (-34, 0, 18), "ForeArm.R": (-82, 0, 8),
            "Spine": (5, 0, -12),
        }, (0, 0, -0.02)),
        (28, {}, (0, 0, 0)),
    ])

    # ---- tackle: lunge and wrap ------------------------------------------ #
    clip("tackle", [
        (1, {}, (0, 0, 0)),
        (8, {
            "UpLeg.L": (-26, 0, 0), "Leg.L": (28, 0, 0),
            "UpLeg.R": (16, 0, 0), "Leg.R": (18, 0, 0),
            "Spine": (14, 0, 0), "Spine1": (8, 0, 0),
            "Arm.L": (-52, 0, -18), "ForeArm.L": (-52, 0, 0),
            "Arm.R": (-52, 0, 18), "ForeArm.R": (-52, 0, 0),
            "Head": (-6, 0, 0),
        }, (0, -0.02, -0.05)),
        (16, {
            "UpLeg.L": (-34, 0, 0), "Leg.L": (36, 0, 0),
            "UpLeg.R": (22, 0, 0), "Leg.R": (22, 0, 0),
            "Spine": (22, 0, 0), "Spine1": (12, 0, 0),
            "Arm.L": (-72, 0, -22), "ForeArm.L": (-62, 0, -10),
            "Arm.R": (-72, 0, 22), "ForeArm.R": (-62, 0, 10),
            "Head": (-10, 0, 0),
        }, (0, -0.025, -0.07)),
        (24, {
            "Spine": (18, 0, 0), "Arm.L": (-62, 0, -20), "Arm.R": (-62, 0, 20),
        }, (0, -0.02, -0.055)),
        (32, {}, (0, 0, 0)),
    ])

    # ---- mark: crouch, leap, grab overhead, land -------------------------- #
    clip("mark_jump", [
        (1, {}, (0, 0, 0)),
        (8, {
            "UpLeg.L": (-36, 0, 0), "Leg.L": (48, 0, 0), "Foot.L": (-14, 0, 0),
            "UpLeg.R": (-36, 0, 0), "Leg.R": (48, 0, 0), "Foot.R": (-14, 0, 0),
            "Spine": (16, 0, 0), "Spine1": (8, 0, 0),
            "Arm.L": (28, 0, -14), "ForeArm.L": (-48, 0, 0),
            "Arm.R": (28, 0, 14), "ForeArm.R": (-48, 0, 0),
        }, (0, 0, -0.16)),
        # launch
        (14, {
            "UpLeg.L": (16, 0, 0), "Leg.L": (8, 0, 0), "Foot.L": (26, 0, 0),
            "UpLeg.R": (16, 0, 0), "Leg.R": (8, 0, 0), "Foot.R": (26, 0, 0),
            "Spine": (-6, 0, 0), "Spine1": (-4, 0, 0),
            "Arm.L": (-150, 0, -8), "ForeArm.L": (-12, 0, 0),
            "Arm.R": (-150, 0, 8), "ForeArm.R": (-12, 0, 0),
            "Head": (14, 0, 0),
        }, (0, 0, 0.24)),
        # apex grab
        (19, {
            "UpLeg.L": (10, 0, 0), "Leg.L": (22, 0, 0),
            "UpLeg.R": (10, 0, 0), "Leg.R": (22, 0, 0),
            "Spine": (-10, 0, 0),
            "Arm.L": (-168, 0, -6), "ForeArm.L": (-6, 0, 0),
            "Arm.R": (-168, 0, 6), "ForeArm.R": (-6, 0, 0),
            "Head": (18, 0, 0),
        }, (0, 0, 0.28)),
        # land
        (27, {
            "UpLeg.L": (-30, 0, 0), "Leg.L": (42, 0, 0), "Foot.L": (-10, 0, 0),
            "UpLeg.R": (-30, 0, 0), "Leg.R": (42, 0, 0), "Foot.R": (-10, 0, 0),
            "Spine": (14, 0, 0), "Spine1": (8, 0, 0),
            "Arm.L": (-120, 0, -12), "ForeArm.L": (-30, 0, 0),
            "Arm.R": (-120, 0, 12), "ForeArm.R": (-30, 0, 0),
            "Head": (-6, 0, 0),
        }, (0, 0, -0.12)),
        (36, {
            "Arm.L": (-90, 0, -12), "Arm.R": (-90, 0, 12), "Spine": (6, 0, 0),
        }, (0, 0, -0.03)),
        (42, {}, (0, 0, 0)),
    ])

    # ---- celebrate: bounce with arms waving ------------------------------- #
    clip("celebrate", [
        (1, {"Arm.L": (-150, 0, -16), "Arm.R": (-150, 0, 16),
             "ForeArm.L": (-16, 0, 0), "ForeArm.R": (-16, 0, 0),
             "Spine": (-4, 0, 0), "Head": (8, 0, 0)}, (0, 0, 0.02)),
        (10, {"Arm.L": (-170, 0, -28), "Arm.R": (-130, 0, 28),
              "ForeArm.L": (-30, 0, 0), "ForeArm.R": (-30, 0, 0),
              "Head": (10, 0, 0),
              "UpLeg.L": (-18, 0, 0), "Leg.L": (30, 0, 0),
              "UpLeg.R": (8, 0, 0), "Leg.R": (12, 0, 0)}, (0, 0, 0.12)),
        (20, {"Arm.L": (-150, 0, -16), "Arm.R": (-150, 0, 16),
              "ForeArm.L": (-16, 0, 0), "ForeArm.R": (-16, 0, 0),
              "Head": (8, 0, 0)}, (0, 0, 0.02)),
        (30, {"Arm.L": (-130, 0, -28), "Arm.R": (-170, 0, 28),
              "ForeArm.L": (-30, 0, 0), "ForeArm.R": (-30, 0, 0),
              "Head": (10, 0, 0),
              "UpLeg.L": (8, 0, 0), "Leg.L": (12, 0, 0),
              "UpLeg.R": (-18, 0, 0), "Leg.R": (30, 0, 0)}, (0, 0, 0.12)),
        (40, {"Arm.L": (-150, 0, -16), "Arm.R": (-150, 0, 16),
              "ForeArm.L": (-16, 0, 0), "ForeArm.R": (-16, 0, 0),
              "Head": (8, 0, 0)}, (0, 0, 0.02)),
        (48, {"Arm.L": (-150, 0, -16), "Arm.R": (-150, 0, 16),
              "ForeArm.L": (-16, 0, 0), "ForeArm.R": (-16, 0, 0),
              "Spine": (-4, 0, 0), "Head": (8, 0, 0)}, (0, 0, 0.02)),
    ])

    # ---- hit the deck: knocked to ground --------------------------------- #
    clip("hit_deck", [
        (1, {}, (0, 0, 0)),
        (10, {
            "Spine": (38, 10, 12), "Spine1": (22, 6, 8),
            "UpLeg.L": (-48, 0, 0), "Leg.L": (58, 0, 0),
            "UpLeg.R": (-32, 0, 0), "Leg.R": (72, 0, 0),
            "Arm.L": (-70, 0, -30), "ForeArm.L": (-50, 0, 0),
            "Arm.R": (-40, 0, 26), "ForeArm.R": (-70, 0, 0),
            "Head": (-20, 0, 0),
        }, (0.05, -0.10, -0.52)),
        (22, {
            "Spine": (52, 12, 14), "Spine1": (26, 8, 10),
            "UpLeg.L": (-60, 0, 0), "Leg.L": (76, 0, 0),
            "UpLeg.R": (-40, 0, 0), "Leg.R": (86, 0, 0),
            "Arm.L": (-90, 0, -36), "Arm.R": (-60, 0, 30),
            "Head": (-26, 0, 0),
        }, (0.08, -0.14, -0.62)),
        (36, {}, (0, 0, 0)),
    ])

    return clips


def main():
    clear_scene()
    body = build_body()
    arm = build_armature("PlayerRig", SKELETON)

    # proximity skinning: bone segments for distance weighting
    segments = {}
    for name, (head, tail, _) in SKELETON.items():
        segments[name] = (Vector(head), Vector(tail))
    proximity_skin(body, arm, segments, max_influences=3, power=3.2)

    clips = build_anims(arm)

    scene = bpy.context.scene
    scene.frame_end = 60
    export_glb(OUT, animations=clips)
    print(f"[player] {len(clips)} animation clips:", ", ".join(clips))


if __name__ == "__main__":
    main()
