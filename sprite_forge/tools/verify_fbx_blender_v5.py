"""Blender oracle (optional, test only): import an FBX, print bones / actions / weights and, for every action,
the evaluated (skinned) mesh vertices at the action's middle as Y-up metres.
  blender -b -P tools/verify_fbx_blender_v5.py -- model.fbx      or   python verify_fbx_blender_v5.py model.fbx  (pip bpy)"""
import json, sys, os
import bpy
argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=args[0])
sc = bpy.context.scene
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
out = {"blender": bpy.app.version_string, "armatures": len(arm), "meshes": len(meshes),
       "bones": len(arm[0].data.bones) if arm else 0, "fps": sc.render.fps / sc.render.fps_base}
acts = list(bpy.data.actions)
out["actions"] = sorted(a.name.split("|")[-1] for a in acts)
wv = 0; vg = 0
for m in meshes:
    vg += len(m.vertex_groups)
    wv += sum(1 for v in m.data.vertices if len(v.groups))
out["vertex_groups"] = vg; out["weighted_verts"] = wv
out["modifiers"] = sorted({md.type for m in meshes for md in m.modifiers})


def verts():
    dg = bpy.context.evaluated_depsgraph_get(); P = []
    for m in meshes:
        e = m.evaluated_get(dg); me = e.to_mesh()
        for v in me.vertices:
            w = e.matrix_world @ v.co
            P.append((round(w.x, 5), round(w.z, 5), round(-w.y, 5)))   # Blender Z-up -> glTF Y-up
        e.to_mesh_clear()
    return P


samples = {}
if arm:
    ad = arm[0].animation_data or arm[0].animation_data_create()
    for a in acts:
        ad.action = a
        f0, f1 = a.frame_range
        xs = sorted({round(k.co.x, 4) for fc in a.fcurves for k in fc.keyframe_points})
        rec = {}
        for tag, fm in (("key", xs[len(xs) // 2]), ("between", (xs[len(xs) // 2] + xs[len(xs) // 2 + 1]) / 2.0)):
            sc.frame_set(int(fm), subframe=fm - int(fm))
            rec[tag] = {"frame": fm, "t": (fm - f0) / out["fps"], "verts": verts()}
        samples[a.name.split("|")[-1]] = rec
    ad.action = None
    sc.frame_set(0)
out["samples"] = samples
print("SFSJSON " + json.dumps(out))
sys.stdout.flush()
os._exit(0)
