"""Generate `stadium.glb` — a Melbourne arena in the style of the MCG.

A fully enclosed three-tier oval stadium: boundary fence, advertising ring,
lower/upper seating bowls with concrete fascia, cantilever roof, six light
towers, two big screens, padded goal and behind posts, behind flags, and the
interchange benches on the wing.

All ring geometry is built along a superellipse (a true footy-oval shape).
Playing-surface markings (lines, arcs, stripes) are drawn at runtime by the
engine onto a grass texture, so they stay crisp at every resolution.

Run:  .venv/bin/python gen_stadium.py
Out:  ../../assets/stadium.glb
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from ard_lib import (
    add_box,
    add_cylinder,
    add_sphere,
    assign_material,
    clear_scene,
    export_glb,
    make_material,
)

OUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "public", "assets", "stadium.glb")
)

# Playing surface semi-axes (metres): x = goal-to-goal, z = wing to wing.
FIELD_A = 85.5
FIELD_B = 73.0
N_SHAPE = 2.4            # superellipse exponent (2 = ellipse, higher = squarer)

# Boundary fence sits just outside the field.
FENCE_A = FIELD_A + 2.2
FENCE_B = FIELD_B + 2.2

GOAL_LINE_X = 69.0       # goal line distance from centre
GOAL_POST_GAP = 6.4      # between the two tall goal posts
BEHIND_POST_GAP = 6.4    # from goal post to behind post

SEGS = 224               # ring segments around the bowl


def super_point(theta, a, b, n=N_SHAPE):
    c, s = math.cos(theta), math.sin(theta)
    x = math.copysign(abs(c) ** (2.0 / n), c) * a
    y = math.copysign(abs(s) ** (2.0 / n), s) * b
    return (x, y)


def ring_mesh(name, profile, a0, b0, mats, row_materials=None, segs=SEGS):
    """Build a stepped ring from a profile of (offset, height) points.

    The ring surface runs along the superellipse with semi-axes (a0+off, b0+off).
    row_materials: optional list of material indices, one per profile segment.
    """
    verts, faces, face_mats = [], [], []
    rows = []
    for off, h in profile:
        row = []
        for i in range(segs):
            theta = 2 * math.pi * i / segs
            x, y = super_point(theta, a0 + off, b0 + off)
            row.append(len(verts))
            verts.append((x, y, h))
        rows.append(row)

    for r in range(len(rows) - 1):
        mat_index = row_materials[r] if row_materials else 0
        for i in range(segs):
            j = (i + 1) % segs
            faces.append((rows[r][i], rows[r][j], rows[r + 1][j], rows[r + 1][i]))
            face_mats.append(mat_index)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for mat in mats:
        mesh.materials.append(mat)
    for poly, mi in zip(mesh.polygons, face_mats):
        poly.material_index = mi
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    return ob


def vertical_ring(name, a0, b0, z0, z1, mat, segs=SEGS, inward=False):
    verts, faces = [], []
    for z in (z0, z1):
        for i in range(segs):
            theta = 2 * math.pi * i / segs
            x, y = super_point(theta, a0, b0)
            verts.append((x, y, z))
    for i in range(segs):
        j = (i + 1) % segs
        if inward:
            faces.append((i, j, segs + j, segs + i))
        else:
            faces.append((i, segs + i, segs + j, j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    return ob


def tier_profile(start_off, rows, depth, rise, z_start):
    prof = [(start_off, z_start)]
    off, z = start_off, z_start
    for _ in range(rows):
        off += depth
        z += rise
        prof.append((off, z))       # tread (flat)
        prof.append((off, z + 0.06))  # small riser lip for seating look
        z += 0.06
    return prof


def main():
    clear_scene()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    concrete = make_material("concrete", (0.62, 0.61, 0.58), roughness=0.9)
    concrete_dark = make_material("concrete_dark", (0.38, 0.38, 0.40), roughness=0.9)
    seat = make_material("seat", (0.13, 0.16, 0.24), roughness=0.75)
    seat_alt = make_material("seat_alt", (0.17, 0.21, 0.30), roughness=0.75)
    roof = make_material("roof", (0.86, 0.87, 0.88), roughness=0.35, metallic=0.55)
    metal = make_material("metal", (0.25, 0.26, 0.28), roughness=0.45, metallic=0.7)
    white = make_material("white", (0.92, 0.92, 0.92), roughness=0.5)
    pad = make_material("pad", (0.95, 0.95, 0.95), roughness=0.7)
    dark = make_material("dark", (0.10, 0.10, 0.11), roughness=0.8)
    screen = make_material("screen", (0.02, 0.02, 0.03), roughness=0.3,
                           emission=(0.05, 0.06, 0.10), emission_strength=1.2)
    lightpanel = make_material("lightpanel", (0.9, 0.9, 0.85), roughness=0.4,
                               emission=(1.0, 0.97, 0.88), emission_strength=6.0)
    grass_park = make_material("grass_park", (0.23, 0.34, 0.16), roughness=1.0)
    ad_red = make_material("ad_red", (0.55, 0.08, 0.08), roughness=0.6)
    ad_blue = make_material("ad_blue", (0.08, 0.16, 0.45), roughness=0.6)
    flag_yellow = make_material("flag_yellow", (0.95, 0.78, 0.10), roughness=0.6)
    glass = make_material("glass", (0.12, 0.15, 0.20), roughness=0.15, metallic=0.4,
                          emission=(0.10, 0.13, 0.20), emission_strength=0.6)

    # ---- parkland & concourse -------------------------------------------- #
    bpy.ops.mesh.primitive_plane_add(size=520, location=(0, 0, -0.35))
    park = bpy.context.active_object
    park.name = "Park"
    assign_material(park, grass_park)

    # ---- boundary fence (white rail on dark wall) ------------------------- #
    vertical_ring("FenceWall", FENCE_A, FENCE_B, 0.0, 1.15, dark)
    vertical_ring("FenceRail", FENCE_A + 0.12, FENCE_B + 0.12, 1.15, 1.32, white)

    # advertising ring just outside the fence
    ad_a, ad_b = FENCE_A + 0.4, FENCE_B + 0.4
    ring_mesh("AdsLower", [(0.4, 0.0), (0.4, 0.92)], ad_a, ad_b,
              [ad_red, ad_blue], row_materials=[0])
    vertical_ring("AdsGlass", ad_a + 0.45, ad_b + 0.45, 0.0, 1.4, glass)

    # ---- seating bowl ----------------------------------------------------- #
    # concrete apron between fence and first row
    ring_mesh("Apron", [(0.6, 0.0), (5.2, 0.0), (5.2, 1.6), (6.0, 1.6)],
              FENCE_A, FENCE_B, [concrete, concrete_dark], row_materials=[0, 1, 1])

    # lower tier: 26 rows
    prof1 = tier_profile(6.0, 26, 0.82, 0.42, 1.6)
    ring_mesh("TierLower", prof1, FENCE_A, FENCE_B,
              [seat, seat_alt, concrete],
              row_materials=[(i % 2) for i in range(len(prof1) - 1)])
    z1 = prof1[-1][1]

    # fascia / middle band
    ring_mesh("Fascia", [(prof1[-1][0], z1), (prof1[-1][0] + 2.5, z1),
                         (prof1[-1][0] + 2.5, z1 + 4.2), (prof1[-1][0] + 3.2, z1 + 4.2)],
              FENCE_A, FENCE_B, [concrete_dark, glass], row_materials=[0, 1, 0])

    # upper tier: 22 rows
    prof2 = tier_profile(prof1[-1][0] + 3.2, 22, 0.86, 0.52, z1 + 4.2)
    ring_mesh("TierUpper", prof2, FENCE_A, FENCE_B,
              [seat, seat_alt, concrete],
              row_materials=[(i % 2) for i in range(len(prof2) - 1)])
    z2 = prof2[-1][1]

    # ---- roof ------------------------------------------------------------- #
    outer = prof2[-1][0] + 2.0
    ring_mesh("Roof", [
        (outer, z2 + 1.2), (outer, z2 + 5.0),
        (outer - 26.0, z2 + 8.2), (outer - 30.0, z2 + 7.6),
    ], FENCE_A, FENCE_B, [roof, metal], row_materials=[0, 1, 1])
    # roof edge beam
    ring_mesh("RoofEdge", [(outer - 30.0, z2 + 7.6), (outer - 30.0, z2 + 8.1)],
              FENCE_A, FENCE_B, [metal])

    # ---- light towers ----------------------------------------------------- #
    tower_angles = [35, 90, 145, 215, 270, 325]  # degrees
    for idx, deg in enumerate(tower_angles):
        th = math.radians(deg)
        px, py = super_point(th, FENCE_A + 62, FENCE_B + 62)
        tower = add_box(f"Tower{idx}", (7.0, 7.0, 62.0), (px, py, 31.0))
        assign_material(tower, metal)
        head = add_box(f"TowerHead{idx}", (14.0, 3.2, 9.0), (px, py, 66.0))
        head.rotation_euler = (0, 0, th + math.pi / 2)
        assign_material(head, dark)
        # light panel face, angled toward the ground
        panel = add_box(f"TowerPanel{idx}", (12.6, 0.7, 7.6),
                        (px - 1.4 * math.sin(th + math.pi / 2),
                         py + 1.4 * math.cos(th + math.pi / 2), 65.4))
        panel.rotation_euler = (math.radians(-28), 0, th + math.pi / 2)
        assign_material(panel, lightpanel)

    # ---- big screens at each end ------------------------------------------ #
    for sx in (-1, 1):
        scr = add_box(f"Screen.{'B' if sx < 0 else 'A'}",
                      (1.8, 46.0, 16.0), (sx * (FENCE_A + 55), 0, 52.0))
        assign_material(scr, screen)
        frame = add_box(f"ScreenFrame{sx}", (2.6, 50.0, 19.5),
                        (sx * (FENCE_A + 55.6), 0, 52.0))
        assign_material(frame, metal)

    # ---- goal & behind posts (padded, white) ------------------------------ #
    post_mats = []
    for sx in (-1, 1):                       # -1 = west goal, +1 = east goal
        gx = sx * GOAL_LINE_X
        for sz in (-1, 1):
            for pz, tag in ((GOAL_POST_GAP / 2, "G"), (GOAL_POST_GAP / 2 + BEHIND_POST_GAP, "B")):
                z = sz * pz
                if tag == "G":
                    post = add_cylinder(f"GoalPost.{sx}.{sz}", 0.22, 9.6,
                                        (gx, z, 4.8), verts=14)
                    cap = add_sphere(f"GoalPostCap.{sx}.{sz}", 0.24, (gx, z, 9.62), seg=12, rings=8)
                    assign_material(cap, pad)
                else:
                    post = add_cylinder(f"BehindPost.{sx}.{sz}", 0.18, 6.0,
                                        (gx, z, 3.0), verts=12)
                    cap = add_sphere(f"BehindPostCap.{sx}.{sz}", 0.20, (gx, z, 6.02), seg=12, rings=8)
                    assign_material(cap, pad)
                assign_material(post, pad)

        # behind flags on short poles beside the behind posts
        for sz in (-1, 1):
            pole = add_cylinder(f"FlagPole.{sx}.{sz}", 0.05, 3.2,
                                (gx, sz * (GOAL_POST_GAP / 2 + BEHIND_POST_GAP + 1.4), 1.6),
                                verts=8)
            assign_material(pole, white)
            flag = add_box(f"Flag.{sx}.{sz}", (0.05, 0.85, 0.55),
                           (gx, sz * (GOAL_POST_GAP / 2 + BEHIND_POST_GAP + 1.85), 2.85))
            assign_material(flag, flag_yellow)

    # ---- interchange benches on both wings -------------------------------- #
    for sz in (-1, 1):
        by = sz * (FENCE_B + 3.2)
        base = add_box(f"BenchBase.{sz}", (26.0, 3.4, 0.55), (0, by, 0.28))
        assign_material(base, concrete_dark)
        for k in range(3):
            seatbox = add_box(f"BenchSeat.{sz}.{k}", (24.0, 0.85, 0.5),
                              (0, by - sz * (0.35 + k * 0.75), 0.62 + k * 0.18))
            assign_material(seatbox, seat)
        canopy = add_box(f"BenchCanopy.{sz}", (27.0, 4.6, 0.5), (0, by, 3.6))
        assign_material(canopy, roof)
        for cx in (-12.5, 12.5):
            strut = add_box(f"BenchStrut.{sz}.{cx}", (0.45, 0.45, 3.3),
                            (cx, by + sz * 1.7, 1.7))
            assign_material(strut, metal)

    export_glb(OUT)
    print("[stadium] exported")


if __name__ == "__main__":
    main()
