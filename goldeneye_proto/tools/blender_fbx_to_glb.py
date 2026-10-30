"""Facility 64 - convert FBX (or OBJ/DAE/GLTF) files to GLB with Blender, headless.

Usage:
  blender -b -P tools/blender_fbx_to_glb.py -- input.fbx [output.glb] [--scale 1.0]
  blender -b -P tools/blender_fbx_to_glb.py -- some_folder/          (converts every .fbx in it)

What it does:
  * imports the file (armature + skinned meshes + all animation takes)
  * keeps every action as its own glTF animation, named after the action/take, so you can
    map them in assets/models/models.cfg with  clip_walk = <name>  etc.
  * exports a binary .glb next to the input (or to the path you give), Y-up, +Z forward.
Run it with any Blender 3.6+ (also works with the pip 'bpy' module: python tools/blender_fbx_to_glb.py ...).
"""
import bpy, os, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
scale = 1.0
if "--scale" in argv:
    i = argv.index("--scale"); scale = float(argv[i + 1]); del argv[i:i + 2]
if not argv:
    print(__doc__); sys.exit(1)

def convert(src, dst):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(src)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=src, global_scale=scale, automatic_bone_orientation=True)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"): bpy.ops.wm.obj_import(filepath=src)
        else: bpy.ops.import_scene.obj(filepath=src)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=src)
    elif ext == ".dae":
        bpy.ops.wm.collada_import(filepath=src)
    else:
        print("skipping (unknown type):", src); return False
    # put every action on its own NLA track so the exporter writes one clip per action
    # drop bone display shapes (they would be exported as visible meshes)
    shapes = {pb.custom_shape for o in bpy.context.scene.objects if o.type == "ARMATURE" for pb in o.pose.bones if pb.custom_shape}
    for o in list(bpy.context.scene.objects):
        if o in shapes or (o.type == "MESH" and o.name.startswith("Icosphere") and not o.data.materials and o.parent is None):
            bpy.data.objects.remove(o, do_unlink=True)
    # FBX takes usually come in as "Armature|Take|walk": keep the last part (raylib keeps 31 chars)
    for act in bpy.data.actions:
        short = act.name.split("|")[-1].strip() or act.name
        if short != act.name and short not in bpy.data.actions: act.name = short
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    for arm in arms:
        ad = arm.animation_data or arm.animation_data_create()
        for act in bpy.data.actions:
            tr = ad.nla_tracks.new(); tr.name = act.name
            st = tr.strips.new(act.name, int(act.frame_range[0]), act)
            st.name = act.name
        ad.action = None
    names = [a.name for a in bpy.data.actions]
    kw = dict(filepath=dst, export_format="GLB", export_yup=True, export_apply=False,
              export_animations=True, export_skins=True)
    try:
        bpy.ops.export_scene.gltf(**kw, export_animation_mode="NLA_TRACKS")
    except TypeError:
        bpy.ops.export_scene.gltf(**kw, export_nla_strips=True)
    print("wrote %s  (clips: %s)" % (dst, ", ".join(names) if names else "none"))
    return True

src = os.path.abspath(argv[0])
if os.path.isdir(src):
    for f in sorted(os.listdir(src)):
        if f.lower().endswith(".fbx"):
            convert(os.path.join(src, f), os.path.join(src, os.path.splitext(f)[0] + ".glb"))
else:
    dst = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.splitext(src)[0] + ".glb"
    convert(src, dst)
