"""Check a `forge.py capture` character in Blender (optional - Sprite Forge itself never needs Blender).

    blender -b -P tools/capture_check_blender.py -- OUT_DIR NAME [--frames walk:8,kick:12,punch:8,idle:0]

Imports NAME.glb, NAME.fbx and NAME.obj from OUT_DIR with Blender's own importers and prints, for each:
mesh / armature / bone / action counts, the height, whether the texture arrived. Then renders the GLB character
with Cycles (CPU, few samples) at a few clip frames from three angles into OUT_DIR/blender_check.png, and writes
OUT_DIR/blender_check.json."""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_dir, name = argv[0], argv[1]
shots = "idle:0,walk:8,kick:12,punch:8"
if "--frames" in argv:
    shots = argv[argv.index("--frames") + 1]
shots = [(s.split(":")[0], int(s.split(":")[1])) for s in shots.split(",")]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def stats(kind):
    dg = bpy.context.evaluated_depsgraph_get()
    zs = []
    tex = False
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.visible_get()]   # not the importer's bone shapes
    for o in meshes:
        if True:
            for v in o.evaluated_get(dg).data.vertices:
                zs.append((o.matrix_world @ v.co).z)
            for m in o.data.materials:
                if m and m.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in m.node_tree.nodes):
                    tex = True
    arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    return dict(kind=kind, meshes=len(meshes), armatures=len(arm),
                bones=len(arm[0].data.bones) if arm else 0, actions=sorted(a.name for a in bpy.data.actions),
                height=round(max(zs) - min(zs), 3) if zs else 0, texture=tex)


report = {}
for kind, imp in (("glb", lambda p: bpy.ops.import_scene.gltf(filepath=p)),
                  ("fbx", lambda p: bpy.ops.import_scene.fbx(filepath=p)),
                  ("obj", lambda p: bpy.ops.wm.obj_import(filepath=p))):
    p = os.path.join(out_dir, "%s.%s" % (name, kind))
    if not os.path.isfile(p):
        continue
    reset()
    try:
        imp(p)
        report[kind] = stats(kind)
    except Exception as e:                                  # noqa: BLE001
        report[kind] = dict(kind=kind, error=str(e))
    print("CHECK", json.dumps(report[kind]))

# ---- render the GLB through its clips
reset()
bpy.ops.import_scene.gltf(filepath=os.path.join(out_dir, name + ".glb"))
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 12
sc.cycles.use_denoising = False
sc.render.resolution_x, sc.render.resolution_y = 240, 360
sc.render.film_transparent = False
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.85, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 2.0; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
tiles = []
for clip, fr in shots:
    act = bpy.data.actions.get(clip) or next((a for a in bpy.data.actions if a.name.startswith(clip)), None)
    if arm.animation_data is None:
        arm.animation_data_create()
    if act:
        arm.animation_data.action = act
        if hasattr(arm.animation_data, "action_slot") and act.slots:
            arm.animation_data.action_slot = act.slots[0]
    sc.frame_set(fr)
    for yaw in (0, 45, 90):
        a = math.radians(yaw)
        cam.location = Vector((4.2 * math.sin(a), -4.2 * math.cos(a), 0.95))
        cam.rotation_euler = (math.radians(90), 0, a)
        f = os.path.join(out_dir, "_bl_%s_%d_%d.png" % (clip, fr, yaw))
        sc.render.filepath = f
        bpy.ops.render.render(write_still=True)
        tiles.append(f)
report["renders"] = [os.path.basename(t) for t in tiles]
try:
    import numpy as np
    ims = [bpy.data.images.load(t) for t in tiles]
    W, H = ims[0].size
    cols = 3; rows = len(ims) // cols
    sheet = np.zeros((rows * H, cols * W, 4), np.float32)
    for k, im in enumerate(ims):
        a = np.array(im.pixels[:], np.float32).reshape(H, W, 4)[::-1]
        r_, c_ = divmod(k, cols); sheet[r_ * H:(r_ + 1) * H, c_ * W:(c_ + 1) * W] = a
    out = bpy.data.images.new("sheet", cols * W, rows * H, alpha=True)
    out.pixels[:] = sheet[::-1].ravel(); out.filepath_raw = os.path.join(out_dir, "blender_check.png"); out.file_format = "PNG"; out.save()
    for t in tiles:
        os.remove(t)
except Exception as e:                                       # noqa: BLE001
    print("CHECK sheet failed", e)
json.dump(report, open(os.path.join(out_dir, "blender_check.json"), "w"), indent=1)
print("CHECK renders", len(tiles))
sys.stdout.flush()
os._exit(0)
