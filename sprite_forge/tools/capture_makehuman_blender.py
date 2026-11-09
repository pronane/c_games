"""Open a `forge.py capture` character in MakeHuman's own code (MPFB2 in Blender) and in plain Blender (optional).

    blender -b -P tools/capture_makehuman_blender.py -- OUT_DIR NAME

1. MakeHuman: NAME.mhm is loaded with MPFB2's .mhm importer (the same code path as Blender > MPFB > Import MHM),
   given MPFB's game-engine rig, and the captured skin (NAME_skin.png, or NAME_texture.png) on its material.
   Its base-mesh vertices are written to NAME_mpfb_vertices.npy (tools/capture_compat.py compares them with
   Sprite Forge's own body) and the scene is saved as NAME_makehuman.blend - an MPFB human whose shape sliders,
   rig, clothes and expressions can all still be edited in MPFB.
2. Blender: NAME.glb is imported with Blender's glTF importer and saved as NAME.blend (armature, actions, materials,
   texture packed) - ready for Rigify, retargeting, sculpting or re-export.
Prints CHECK lines (JSON) for each step."""
import json
import os
import sys

import bpy
import addon_utils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir, name = argv[0], argv[1]
EXT = "bl_ext.user_default.mpfb"
rep = {}


def say(k, v):
    rep[k] = v
    print("CHECK", json.dumps({k: v}))
    sys.stdout.flush()


# ---------------------------------------------------------------- 1. MakeHuman / MPFB
try:
    bpy.ops.wm.read_userpref()
    if EXT not in bpy.context.preferences.addons:
        addon_utils.enable(EXT, default_set=True)
    from bl_ext.user_default.mpfb.services.humanservice import HumanService as HS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if EXT not in bpy.context.preferences.addons:
        addon_utils.enable(EXT, default_set=True)
    st = HS.get_default_deserialization_settings()
    st["subdiv_levels"] = 0
    st["load_clothes"] = False
    st["clothes_deep_search"] = False; st["bodypart_deep_search"] = False
    st["override_skin_model"] = "NONE"                     # the captured skin is applied below
    bm = HS.deserialize_from_mhm(os.path.join(out_dir, name + ".mhm"), st)
    me = bm.data
    n = len(me.vertices)
    keys = me.shape_keys.key_blocks if me.shape_keys else []
    basis = np.zeros(n * 3); (keys[0].data if keys else me.vertices).foreach_get("co", basis); basis = basis.reshape(n, 3)
    co = basis.copy()
    for k in list(keys)[1:]:
        if k.value and not k.mute:
            c = np.zeros(n * 3); k.data.foreach_get("co", c); co += k.value * (c.reshape(n, 3) - basis)
    np.save(os.path.join(out_dir, name + "_mpfb_vertices.npy"), np.stack([co[:, 0], co[:, 2], -co[:, 1]], 1))
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]       # the .mhm's "skeleton default.mhskel"
    rig_ok = bool(arms)
    skin = os.path.join(out_dir, name + "_skin.png")
    if not os.path.isfile(skin):
        skin = os.path.join(out_dir, name + "_texture.png")
    img = bpy.data.images.load(skin)
    img.pack()
    mat = bpy.data.materials.new(name + "_skin"); mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    me.materials.clear(); me.materials.append(mat)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_makehuman.blend"))
    say("makehuman", dict(loaded_mhm=True, vertices=n, shape_keys=max(0, len(keys) - 1), mpfb_rig=rig_ok, rig_bones=len(arms[0].data.bones) if arms else 0,
                          blend=name + "_makehuman.blend"))
except Exception as e:                                              # noqa: BLE001
    say("makehuman", dict(loaded_mhm=False, error=str(e)))

# ---------------------------------------------------------------- 2. plain Blender from the GLB
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(out_dir, name + ".glb"))
    arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.visible_get()]
    for im in bpy.data.images:
        if not im.packed_file:
            try:
                im.pack()
            except Exception:                                       # noqa: BLE001
                pass
    vg_ok = all(set(g.name for g in m.vertex_groups) <= set(b.name for b in arm[0].data.bones) for m in meshes) if arm else False
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + ".blend"))
    say("blender", dict(armature=bool(arm), bones=len(arm[0].data.bones) if arm else 0,
                        meshes=[m.name for m in meshes], actions=sorted(a.name for a in bpy.data.actions),
                        vertex_groups_match_bones=vg_ok, blend=name + ".blend"))
except Exception as e:                                              # noqa: BLE001
    say("blender", dict(error=str(e)))
json.dump(rep, open(os.path.join(out_dir, "makehuman_blender_check.json"), "w"), indent=1)
sys.stdout.flush()
os._exit(0)
