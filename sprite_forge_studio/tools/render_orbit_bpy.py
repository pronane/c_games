"""Procedural ORBIT test video for the photogrammetry route (no real person involved):
the studio's mannequin (model.glb) with a procedural surface texture, on a textured floor,
filmed by a camera that walks a circle around it.  Writes frames + orbit.mp4 + cameras.json (truth).

  python tools/render_orbit_bpy.py model.glb OUTDIR [--frames 72] [--size 640x480]   (needs bpy)
"""
import os as _os, sys as _sys, shutil as _sh
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
try:
    from sforge.media import ffmpeg_exe as _ffx
    FFMPEG = _ffx()[0] or "ffmpeg"
except Exception:
    FFMPEG = "ffmpeg"
FFPROBE = _sh.which("ffprobe") or "ffprobe"

import sys, os, math, json, subprocess
import bpy
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
glb, outd = args[0], args[1]
nfr = int(args[args.index("--frames") + 1]) if "--frames" in args else 72
W, H = (640, 480)
if "--size" in args:
    W, H = [int(v) for v in args[args.index("--size") + 1].split("x")]
os.makedirs(os.path.join(outd, "frames"), exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene
for o in list(sc.objects):
    if o.type == "ARMATURE":
        o.animation_data_clear() if o.animation_data else None
for a in bpy.data.actions:
    pass
# procedural "painted" material on the figure: base colour * noise/voronoi detail (texture for feature matching)
def painted(name, scale, tint):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = scale; n1.inputs["Detail"].default_value = 8
    v1 = nt.nodes.new("ShaderNodeTexVoronoi"); v1.inputs["Scale"].default_value = scale * 2.2
    mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = "MULTIPLY"; mix.inputs[0].default_value = 0.75
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (tint[0] * 0.25, tint[1] * 0.25, tint[2] * 0.25, 1)
    ramp.color_ramp.elements[1].color = (min(1, tint[0] * 1.3), min(1, tint[1] * 1.3), min(1, tint[2] * 1.3), 1)
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"]); nt.links.new(tc.outputs["Object"], v1.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs[1]); nt.links.new(v1.outputs["Color"], mix.inputs[2])
    nt.links.new(mix.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.8
    return m
fig = painted("fig", 9.0, (0.75, 0.55, 0.35))
for o in sc.objects:
    if o.type == "MESH":
        o.data.materials.clear(); o.data.materials.append(fig)
bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
floor = bpy.context.active_object; floor.data.materials.append(painted("floor", 3.0, (0.45, 0.5, 0.55)))
# a few textured boxes around so the background has structure too
for k, (x, y) in enumerate([(2.6, 1.2), (-2.3, 2.0), (-1.8, -2.4), (2.2, -2.2)]):
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(x, y, 0.25))
    bpy.context.active_object.data.materials.append(painted("box%d" % k, 5.0, (0.6, 0.3 + 0.1 * k, 0.4)))
bpy.ops.object.light_add(type="SUN", location=(3, -3, 6)); bpy.context.active_object.data.energy = 3.5
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.6, 0.68, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 30; cam_d.sensor_width = 36
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = "CYCLES"; sc.cycles.samples = 24; sc.cycles.device = "CPU"
try:
    sc.cycles.use_denoising = False
except Exception:
    pass
sc.render.resolution_x, sc.render.resolution_y = W, H; sc.render.resolution_percentage = 100
target = Vector((0, 0, 0.9)); R = 3.2; cams = []
for i in range(nfr):
    a = 2 * math.pi * i / nfr
    pos = Vector((R * math.cos(a), R * math.sin(a), 1.45 + 0.25 * math.sin(2 * a)))
    cam.location = pos
    d = target - pos; cam.rotation_mode = "QUATERNION"; cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(outd, "frames", "orbit_%03d.png" % i)
    bpy.ops.render.render(write_still=True)
    cams.append({"frame": i, "location": list(pos), "quat_wxyz": list(cam.rotation_quaternion)})
f_px = cam_d.lens / cam_d.sensor_width * W
json.dump({"cameras": cams, "f_px": f_px, "size": [W, H], "target": list(target)}, open(os.path.join(outd, "cameras.json"), "w"), indent=1)
subprocess.run([FFMPEG, "-y", "-v", "error", "-framerate", "24", "-i", os.path.join(outd, "frames", "orbit_%03d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", os.path.join(outd, "orbit.mp4")])
print("SFS orbit: %d frames -> %s" % (nfr, os.path.join(outd, "orbit.mp4")))
sys.stdout.flush(); os._exit(0)
