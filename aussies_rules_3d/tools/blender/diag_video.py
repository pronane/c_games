import os, sys, math, bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VIDEO_SAMPLES", "4")
import gen_match_video as V
from mathutils import Vector

cap = V.load_telemetry()
scene, cam, ball_root = V.build_scene()
players = V.build_players(scene, cap)
hud = V.build_hud(cam)
ring, arrow = V.build_control_ring()
segs, total = V.segment_map()
V.STATE.update({
    "cap": cap, "players": players, "hud": hud, "cam": cam,
    "ball_root": ball_root, "ring": ring, "arrow": arrow,
    "segs": segs, "total": total, "last_kicker": None,
})

scene.frame_set(138)
V.frame_handler(scene)
bpy.context.view_layer.update()
fr = cap["frames"][153]
print("ball:", fr["ball"])
shown = 0
for p in fr["players"][:6]:
    pid = int(p[0])
    e = players.get(pid)
    if e is None:
        print("MISSING entry for", pid)
        continue
    print(f"pid={pid} tel=({p[1]},{p[2]}) arm_loc={tuple(round(v,1) for v in e['arm'].location)} "
          f"body_world={tuple(round(v,1) for v in e['body'].matrix_world.translation)} "
          f"hide={e['body'].hide_render} vgroups={len(e['body'].vertex_groups)}")
cam.location = (20, -120, 170)
cam.rotation_euler = (Vector((20, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_diag_wide.png")
bpy.ops.render.render(write_still=True)
print("wide rendered")
