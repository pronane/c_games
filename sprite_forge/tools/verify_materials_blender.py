"""Blender oracle (test only): print material slot names of an imported GLB / FBX as JSON.
  python tools/verify_materials_blender.py model.glb   (pip bpy)   or   blender -b -P tools/verify_materials_blender.py -- model.fbx"""
import json, os, sys
import bpy
argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
p = args[0]
if p.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=p)
else:
    bpy.ops.import_scene.gltf(filepath=p)
out = {"materials": sorted(m.name for m in bpy.data.materials), "slots": {}}
for o in bpy.data.objects:
    if o.type == "MESH":
        out["slots"][o.name] = [s.material.name if s.material else None for s in o.material_slots]
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
out["bones"] = len(arm[0].data.bones) if arm else 0
out["actions"] = sorted(a.name for a in bpy.data.actions)
print("SFS_JSON " + json.dumps(out))
