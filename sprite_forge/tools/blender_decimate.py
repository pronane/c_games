"""Decimate a PLY to a triangle budget with Blender's Collapse decimator (keeps vertex colours).
  python blender_decimate.py in.ply out.ply TARGET_TRIS   (bpy)  |  blender -b -P blender_decimate.py -- in out N"""
import sys, os
import bpy
a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
src, dst, target = a[0], a[1], int(a[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.ply_import(filepath=src)
ob = bpy.context.selected_objects[0]; bpy.context.view_layer.objects.active = ob
n = len(ob.data.polygons)
m = ob.modifiers.new("dec", "DECIMATE"); m.ratio = min(1.0, target / max(1, n)); m.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier="dec")
bpy.ops.wm.ply_export(filepath=dst, export_selected_objects=True, export_triangulated_mesh=True, export_colors="SRGB",
                      export_normals=False, export_uv=False, ascii_format=False, forward_axis="Y", up_axis="Z")
sys.stdout.flush(); os._exit(0)
