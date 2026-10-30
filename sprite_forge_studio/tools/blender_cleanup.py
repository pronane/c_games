"""OPTIONAL Blender clean-up pass (forge.py library add --blender-cleanup).  Not needed for normal use.
  blender -b -P tools/blender_cleanup.py -- in.fbx out.glb      or   python tools/blender_cleanup.py in.fbx out.glb (pip bpy)
Imports the file, applies every object transform (rotation / scale baked into the data: fixes rigs lying flat on
their back from a Z-up / -90 deg X export), removes duplicate meshes (same vertex count + same bounds, or a
.001 copy), and exports a GLB that Sprite Forge's own reader then normalises.  Prints SFS_CLEANUP {json}."""
import json
import os
import sys
import bpy

argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
src, out = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(src)[1].lower()
if ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src, automatic_bone_orientation=False)
elif ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    raise SystemExit("unsupported " + ext)
rep = {"applied": [], "removed": []}
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
seen = {}
for o in sorted(meshes, key=lambda o: (o.name.count("."), o.name)):
    bb = tuple(round(v, 4) for c in o.bound_box for v in (o.matrix_world @ __import__("mathutils").Vector(c)))
    key = (len(o.data.vertices), bb)
    if key in seen:
        rep["removed"].append(dict(name=o.name, duplicate_of=seen[key]))
        bpy.data.objects.remove(o, do_unlink=True)
    else:
        seen[key] = o.name
for o in bpy.data.objects:
    o.select_set(o.type in ("MESH", "ARMATURE"))
    if o.type in ("MESH", "ARMATURE") and (any(abs(x) > 1e-6 for x in o.rotation_euler) or any(abs(s - 1) > 1e-6 for s in o.scale)):
        rep["applied"].append(o.name)
bpy.context.view_layer.objects.active = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if rep["applied"]:
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True, export_skins=True)

print("SFS_CLEANUP " + json.dumps(rep), flush=True)
sys.stdout.flush(); sys.stderr.flush()
os._exit(0)          # pip bpy can segfault while tearing down at interpreter exit; the GLB is already written
