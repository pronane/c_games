"""Re-import a model.fbx in Blender (headless) and render a 4-angle + animation contact sheet, to show the FBX
really loads with its rig and takes.
  blender -b -P tools/render_fbx_preview.py -- model.fbx out.png      (or: python render_fbx_preview.py ... with bpy)"""
import sys, os, math
import bpy
from mathutils import Vector
argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
fbx, out = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
sc = bpy.context.scene
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
acts = sorted(bpy.data.actions, key=lambda a: a.name)
def bounds():
    dg = bpy.context.evaluated_depsgraph_get(); pts = []
    for o in meshes:
        e = o.evaluated_get(dg)
        pts += [e.matrix_world @ v.co for v in e.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi
lo, hi = bounds(); h = hi.z - lo.z; c = (lo + hi) / 2
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = h * 1.7
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.rotation_euler = (0.8, 0.2, 0.6)
sc.render.engine = "BLENDER_WORKBENCH"; sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "MATERIAL"
sc.render.resolution_x = 320; sc.render.resolution_y = 400; sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.16, 0.17, 0.22)
tmp = os.path.splitext(out)[0] + "_tmp"; os.makedirs(tmp, exist_ok=True)
shots = []
def snap(name, yaw_deg, act=None, frame=None):
    if arm and act is not None:
        arm[0].animation_data_create(); arm[0].animation_data.action = act
        sc.frame_set(int(frame))
    r = h * 3; a = math.radians(yaw_deg)
    cam.location = (c.x + r * math.sin(a), c.y - r * math.cos(a), c.z + h * 0.12)
    cam.rotation_euler = (math.radians(90), 0, a)
    p = os.path.join(tmp, name + ".png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); shots.append((p, name))
idle = ([a for a in acts if a.name.split("|")[-1].lower().startswith("idle")] or acts or [None])[0]
for y, n in ((0, "front"), (90, "side"), (180, "back"), (45, "3/4")):
    snap(n.replace("/", "_") + " (idle)", y, idle, idle.frame_range[0] if idle else 0)
pick = [a for a in acts if any(k in a.name.lower() for k in ("run", "jump", "kick", "punch"))][:4] or acts[:4]
for a in pick:
    f0, f1 = a.frame_range
    snap(a.name.split("|")[-1][:14], 30, a, (f0 + f1) / 2)
print("VERIFY fbx=%s meshes=%d armatures=%d bones=%d actions=%d height=%.3f" % (os.path.basename(fbx), len(meshes), len(arm),
      len(arm[0].data.bones) if arm else 0, len(acts), h))
with open(os.path.splitext(out)[0] + "_verify.txt", "w") as f:
    f.write("meshes=%d armatures=%d bones=%d actions=%d height=%.2f m\nactions: %s\n" % (
        len(meshes), len(arm), len(arm[0].data.bones) if arm else 0, len(acts), h, ", ".join(a.name.split("|")[-1] for a in acts)))
open(os.path.join(tmp, "list.txt"), "w").write("\n".join("%s\t%s" % s for s in shots))
sys.stdout.flush(); os._exit(0)
