"""Shared helpers for Aussie Rules 3D asset generation (Blender / bpy 4.5).

Everything is authored in Blender's Z-up space, facing -Y (which exports to
glTF / three.js as Y-up, facing -Z — the three.js default "forward").

The animation system is fully deterministic: poses are described as
armature-space Euler rotations applied around each bone's head, converted to
pose-bone matrices by FK (see `Pose` below). No context-heavy operators are
used for rigging or skinning.
"""

from __future__ import annotations

import math
import os
import random

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

DEG = math.pi / 180.0


# --------------------------------------------------------------------------- #
#  Scene management
# --------------------------------------------------------------------------- #

def clear_scene() -> None:
    """Remove every object, mesh, armature, material and action."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.fps = 24


# --------------------------------------------------------------------------- #
#  Materials
# --------------------------------------------------------------------------- #

def make_material(
    name: str,
    color,
    roughness: float = 0.6,
    metallic: float = 0.0,
    emission=None,
    emission_strength: float = 0.0,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = color[:3]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        er, eg, eb = emission[:3]
        bsdf.inputs["Emission Color"].default_value = (er, eg, eb, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = (r, g, b, 1.0)
    return mat


# --------------------------------------------------------------------------- #
#  Geometry helpers
# --------------------------------------------------------------------------- #

def add_box(name, size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return ob


def add_cylinder(name, radius=0.5, depth=1.0, loc=(0, 0, 0), rot=(0, 0, 0), verts=16):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot
    )
    ob = bpy.context.active_object
    ob.name = name
    return ob


def add_sphere(name, radius=0.5, loc=(0, 0, 0), seg=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=seg, ring_count=rings, radius=radius, location=loc
    )
    ob = bpy.context.active_object
    ob.name = name
    return ob


def add_torus(name, major=1.0, minor=0.2, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor, location=loc, rotation=rot
    )
    ob = bpy.context.active_object
    ob.name = name
    return ob


def join_objects(objects, name):
    """Join meshes into one object (materials are preserved as slots)."""
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    return ob


def assign_material(ob, mat, slot=None):
    if slot is None:
        ob.data.materials.append(mat)
    else:
        ob.data.materials[slot] = mat


# --------------------------------------------------------------------------- #
#  Armature helpers
# --------------------------------------------------------------------------- #

def build_armature(name, bones):
    """Create an armature from {bone_name: (head, tail, parent_name|None)}.

    All bones are created with roll 0. The armature sits at the origin,
    unrotated, so armature space == world space.
    """
    arm_data = bpy.data.armatures.new(name)
    arm_ob = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_ob)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="EDIT")
    ebones = arm_data.edit_bones
    created = {}
    for bname, (head, tail, parent) in bones.items():
        eb = ebones.new(bname)
        eb.head = Vector(head)
        eb.tail = Vector(tail)
        eb.roll = 0.0
        created[bname] = eb
    for bname, (_, _, parent) in bones.items():
        if parent:
            created[bname].parent = created[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_ob


def bone_head_matrix(head):
    """Armature-space matrix that pivots around `head`."""
    return Matrix.Translation(Vector(head))


class Pose:
    """Deterministic FK posing.

    A pose entry is (bone_name, (rx, ry, rz) in degrees, offset=(dx,dy,dz)):
    rotate the bone by an XYZ Euler expressed in armature space, pivoting
    around the bone's rest head, then translate it by `offset` (armature
    space). Matrices are computed with exact Blender pose math

        world[b] = world[p] @ inv(rest[p]) @ rest[b] @ basis[b]

    so no context or depsgraph updates are ever needed, and children follow
    their parents automatically.
    """

    def __init__(self, arm_ob, bone_heads):
        self.arm = arm_ob
        self.heads = {k: Vector(v) for k, v in bone_heads.items()}
        self.rest = {b.name: b.matrix_local.copy() for b in arm_ob.data.bones}
        self.parent_of = {
            b.name: (b.parent.name if b.parent else None) for b in arm_ob.data.bones
        }
        self.world = {}

    def apply(self, keys):
        """keys: list of (bone, (rx,ry,rz)[, offset]). Parents must come first."""
        for entry in keys:
            bone, deg = entry[0], entry[1]
            offset = Vector(entry[2]) if len(entry) > 2 else Vector((0, 0, 0))
            head = self.heads[bone]
            rot = Euler((deg[0] * DEG, deg[1] * DEG, deg[2] * DEG), "XYZ").to_matrix().to_4x4()
            pivot = (
                Matrix.Translation(offset)
                @ Matrix.Translation(head)
                @ rot
                @ Matrix.Translation(-head)
            )
            world = pivot @ self.rest[bone]
            self.world[bone] = world
            parent = self.parent_of[bone]
            if parent is not None:
                basis = (
                    self.rest[bone].inverted()
                    @ self.rest[parent]
                    @ self.world[parent].inverted()
                    @ world
                )
            else:
                basis = self.rest[bone].inverted() @ world
            pb = self.arm.pose.bones[bone]
            pb.rotation_mode = "QUATERNION"
            pb.matrix_basis = basis

    def key(self, frame, keys):
        """Set a pose and insert keyframes for every bone it touches."""
        self.apply(keys)
        for entry in keys:
            bone = entry[0]
            pb = self.arm.pose.bones[bone]
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)


# --------------------------------------------------------------------------- #
#  Skinning
# --------------------------------------------------------------------------- #

def proximity_skin(mesh_ob, arm_ob, bone_segments, max_influences=3, power=3.0):
    """Weight vertices to nearby bones (distance to bone segment).

    bone_segments: {bone_name: (head Vector, tail Vector)}.
    Deterministic, headless-safe replacement for automatic weights.
    """
    vg_map = {}
    for bname in bone_segments:
        vg_map[bname] = mesh_ob.vertex_groups.new(name=bname)

    mw = mesh_ob.matrix_world
    arm_inv = arm_ob.matrix_world.inverted()
    for v in mesh_ob.data.vertices:
        co = arm_inv @ (mw @ v.co)
        dists = []
        for bname, (h, t) in bone_segments.items():
            d = _point_segment_distance(co, h, t)
            dists.append((d, bname))
        dists.sort()
        dists = dists[:max_influences]
        weights = []
        total = 0.0
        for d, bname in dists:
            w = 1.0 / (d ** power + 1e-5)
            weights.append((bname, w))
            total += w
        for bname, w in weights:
            vg_map[bname].add([v.index], w / total, "REPLACE")

    mod = mesh_ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_ob
    mod.use_vertex_groups = True
    mesh_ob.parent = arm_ob


def _point_segment_distance(p, a, b):
    ab = b - a
    denom = ab.length_squared
    if denom < 1e-12:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / denom))
    return (p - (a + ab * t)).length


# --------------------------------------------------------------------------- #
#  Export
# --------------------------------------------------------------------------- #

def export_glb(path, animations=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(path),
        export_format="GLB",
        use_selection=False,
        export_animations=bool(animations),
        export_animation_mode="ACTIONS",
        export_skins=True,
        export_yup=True,
        export_apply=False,
        export_extras=True,
        export_cameras=False,
        export_lights=False,
    )
    size = os.path.getsize(path)
    print(f"[exported] {path} ({size/1024:.0f} KB)")
