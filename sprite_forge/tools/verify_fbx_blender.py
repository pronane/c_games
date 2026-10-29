"""Re-import an FBX in Blender and print mesh height, bone count and takes.
  blender -b -P tools/verify_fbx_blender.py -- model.fbx     (or: python verify_fbx_blender.py model.fbx with bpy)"""
import sys
import bpy
from mathutils import Vector
argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=args[0])
dg = bpy.context.evaluated_depsgraph_get()
zs = []
for o in bpy.data.objects:
    if o.type == "MESH":
        for v in o.evaluated_get(dg).data.vertices:
            zs.append((o.matrix_world @ v.co).z)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
print("VERIFY objects=%d meshes=%d armatures=%d bones=%d actions=%d height=%.3f m" % (
    len(bpy.data.objects), sum(o.type == "MESH" for o in bpy.data.objects), len(arm),
    len(arm[0].data.bones) if arm else 0, len(bpy.data.actions), (max(zs) - min(zs)) if zs else 0))
print("VERIFY actions:", ", ".join(sorted(a.name for a in bpy.data.actions)[:50]))
sys.stdout.flush()
import os
os._exit(0)
