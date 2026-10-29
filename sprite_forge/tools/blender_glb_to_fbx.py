"""Convert a Sprite Forge GLB (skinned + animated) to FBX using Blender.

Usage (Windows example):
  "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe" -b -P tools\\blender_glb_to_fbx.py -- in.glb out.fbx
or with the pip `bpy` module:   python tools/blender_glb_to_fbx.py in.glb out.fbx
Also usable to render/inspect.  Exports every glTF animation as an FBX take.
"""
import sys
import bpy

argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
src, dst = args[0], args[1]

SCALE_OPT = args[2] if len(args) > 2 and not args[2].startswith("--") else "FBX_SCALE_ALL"
LEAF = "--leaf" in args          # v6 oracle: Blender-style *_end leaf bones
EMBED = "--embed" in args        # v6 oracle: embed textures in the FBX
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30          # must be set BEFORE import (glTF seconds -> frames)
bpy.ops.import_scene.gltf(filepath=src)
# the glTF importer adds a helper "Icosphere" bone-shape object - remove it
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name.startswith("Icosphere"):
        bpy.data.objects.remove(o, do_unlink=True)
actions = list(bpy.data.actions)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
print("SFS imported: objects=%d actions=%d armature=%s" % (len(bpy.data.objects), len(actions), arm.name if arm else None))
scene = bpy.context.scene
if arm is not None:
    orig = arm.name
    arm.name = "Rig"; arm.data.name = "Rig"
    for act in actions:
        for suf in ("_" + orig, "_Mannequin_skin", "_Mannequin"):
            if act.name.endswith(suf):
                act.name = act.name[: -len(suf)]
                break
    arm.animation_data_create()
    # keep each action as its own NLA track so the FBX exporter writes one take per action
    for tr in list(arm.animation_data.nla_tracks):
        arm.animation_data.nla_tracks.remove(tr)
    for act in actions:
        act.use_fake_user = True
        tr = arm.animation_data.nla_tracks.new(); tr.name = act.name
        tr.strips.new(act.name, int(act.frame_range[0]), act)
    arm.animation_data.action = None
bpy.ops.export_scene.fbx(
    filepath=dst, use_selection=False, object_types={"ARMATURE", "MESH"},
    add_leaf_bones=LEAF, bake_anim=True, bake_anim_use_all_actions=True,
    bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
    bake_anim_simplify_factor=0.0, apply_unit_scale=True, apply_scale_options=SCALE_OPT, axis_forward="-Z", axis_up="Y",
    path_mode="COPY" if EMBED else "AUTO", embed_textures=EMBED, mesh_smooth_type="FACE")
print("SFS wrote", dst)
sys.stdout.flush()
if bpy.app.binary_path == "" or "--" not in sys.argv:
    import os
    os._exit(0)   # pip-bpy can crash during interpreter teardown; the file is already written
