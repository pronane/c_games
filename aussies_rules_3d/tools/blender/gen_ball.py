"""Generate `ball.glb` — a Sherrin-style oval leather football.

Run:  .venv/bin/python gen_ball.py
Out:  ../../assets/ball.glb
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from ard_lib import (
    add_box,
    add_cylinder,
    add_sphere,
    assign_material,
    clear_scene,
    export_glb,
    join_objects,
    make_material,
)

OUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "public", "assets", "ball.glb")
)


def main():
    clear_scene()
    leather = make_material("leather", (0.42, 0.10, 0.07), roughness=0.42)
    lace = make_material("lace", (0.72, 0.62, 0.52), roughness=0.6)
    seam = make_material("seam", (0.30, 0.07, 0.05), roughness=0.5)

    parts = []
    ball = add_sphere("bladder", 0.5, (0, 0, 0), seg=32, rings=20)
    ball.scale = (1.45, 0.88, 0.88)          # oval: long axis = X
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(ball, leather)
    parts.append(ball)

    # seam rings around the two ends
    for sx in (-1, 1):
        ring = add_cylinder(f"seam{sx}", 0.51, 0.045, (sx * 0.44, 0, 0), rot=(0, 1.5708, 0), verts=28)
        ring.scale = (1.0, 0.9, 0.9)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        assign_material(ring, seam)
        parts.append(ring)

    # laces: raised bars along the top spine
    for i, x in enumerate((-0.135, -0.045, 0.045, 0.135)):
        bar = add_box(f"lace{i}", (0.062, 0.115, 0.045), (x, 0, 0.435))
        bar.rotation_euler = (0, 0, 0)
        assign_material(bar, lace)
        parts.append(bar)
    spine = add_box("lacespine", (0.46, 0.035, 0.035), (0, 0, 0.445))
    assign_material(spine, lace)
    parts.append(spine)

    ob = join_objects(parts, "Ball")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    export_glb(OUT)
    print("[ball] exported")


if __name__ == "__main__":
    main()
