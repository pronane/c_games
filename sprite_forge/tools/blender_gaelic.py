"""Blender reference build of the Gaelic Football 3D player (same design as tools/gaelic_forge.py).

    python3 tools/blender_gaelic.py --out /tmp/gf_blender [--tris 22000]

Blender does every modelling step its own way: the design's primitives as Blender meshes -> voxel remesh (one
closed body) -> Smooth -> Decimate (collapse) to the triangle budget -> Smart UV Project -> armature built from the
game skeleton with automatic (bone heat) weights -> Cycles bakes (ambient occlusion, bind position) -> kit textures.
The kit colours themselves come from the shared design's paints (sforge.footballer), evaluated at Blender's baked
texel positions.  The skinned mesh is packed into the game GLB with the same packer as the Forge build (skeleton +
32 clips kept), and also exported with Blender's own glTF exporter for the export-validity check."""
from __future__ import annotations
import argparse, io, json, math, os, shutil, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import bpy, bmesh                                                     # noqa: E402
from mathutils import Matrix, Vector                                  # noqa: E402
import blender_hd as BH                                               # noqa: E402  (prim meshes, helpers)
from sforge import footballer as FB, gamemesh as GM, glbpack           # noqa: E402

GAME = os.path.abspath(os.path.join(HERE, "..", "..", "Gaelic_Football_3d"))
C3 = BH.C3


def armature(sk):
    arm = bpy.data.armatures.new("rig"); ob = bpy.data.objects.new("rig", arm)
    bpy.context.collection.objects.link(ob); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    seg, kids = GM._segments(sk)
    for n in sk.names:
        A, Bp = seg[n]
        eb = arm.edit_bones.new(n); eb.head = Vector(C3 @ A); eb.tail = Vector(C3 @ Bp)
        if (eb.tail - eb.head).length < 1e-3:
            eb.tail = eb.head + Vector((0, 0, 0.03))
    for n in sk.names:
        p = sk.parent.get(n)
        if p in arm.edit_bones:
            arm.edit_bones[n].parent = arm.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def body_object(prims, voxel):
    ident = {p.bone: np.eye(4) for p in prims}
    bm = bmesh.new()
    for p in prims:
        if p.sub:
            continue
        b2 = BH.prim_bmesh(p, ident); me = bpy.data.meshes.new("t"); b2.to_mesh(me); b2.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    ob = BH.new_obj("footballer", bm)
    rm = ob.modifiers.new("remesh", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = voxel; rm.adaptivity = 0.0
    BH.apply_mods(ob)
    sm = ob.modifiers.new("smooth", "SMOOTH"); sm.factor = 0.6; sm.iterations = 6
    BH.apply_mods(ob)
    return ob


def decimate(ob, tris):
    n = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    dm = ob.modifiers.new("decimate", "DECIMATE"); dm.decimate_type = "COLLAPSE"; dm.ratio = min(1.0, tris / max(n, 1))
    dm.use_collapse_triangulate = True
    BH.apply_mods(ob)
    tri = ob.modifiers.new("tri", "TRIANGULATE"); BH.apply_mods(ob)
    for f in ob.data.polygons:
        f.use_smooth = True
    return n


def unwrap(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.006, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(margin=0.006)
    bpy.ops.object.mode_set(mode="OBJECT")


def _select(*obs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


def _unweighted(ob):
    return [v.index for v in ob.data.vertices if sum(g.weight for g in v.groups) < 1e-4]


def bind(ob, rig, scale=10.0):
    """automatic (bone heat) weights, the standard Blender way: clean mesh, solve at 10x scale (the heat solver
    fails on metre-scale meshes), then Blender's envelope weights for any vertex the heat solve left empty"""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
    bm.to_mesh(ob.data); bm.free(); ob.data.validate(clean_customdata=False); ob.data.update()
    for o in (ob, rig):
        o.scale = (scale, scale, scale)
    _select(ob, rig); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _select(ob, rig, active=rig); bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    heat_failed = len(_unweighted(ob))
    if heat_failed > len(ob.data.vertices) * 0.01:
        # standard rigging workaround: bone heat on a clean voxel proxy, then Data Transfer the weights across
        proxy = ob.copy(); proxy.data = ob.data.copy(); bpy.context.collection.objects.link(proxy)
        proxy.vertex_groups.clear(); proxy.modifiers.clear(); proxy.parent = None
        rm = proxy.modifiers.new("rm", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = 0.08; _select(proxy); BH.apply_mods(proxy)   # 8 mm: built in the 10x solve space
        _select(proxy, rig, active=rig); bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        proxy_failed = len(_unweighted(proxy))
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
        for vg in proxy.vertex_groups:
            ob.vertex_groups.new(name=vg.name)
        dt = ob.modifiers.new("dt", "DATA_TRANSFER"); dt.object = proxy; dt.use_vert_data = True
        dt.data_types_verts = {"VGROUP_WEIGHTS"}; dt.vert_mapping = "POLYINTERP_NEAREST"
        dt.layers_vgroup_select_src = "ALL"; dt.layers_vgroup_select_dst = "NAME"
        _select(ob); bpy.ops.object.modifier_move_to_index(modifier="dt", index=0); bpy.ops.object.modifier_apply(modifier="dt")
        bpy.data.objects.remove(proxy)
        print("  bone heat failed on %d verts; proxy weighted (%d proxy verts unsolved) and transferred" % (heat_failed, proxy_failed))
    if heat_failed:
        tmp = ob.copy(); tmp.data = ob.data.copy(); bpy.context.collection.objects.link(tmp)
        tmp.vertex_groups.clear(); tmp.parent = None; tmp.modifiers.clear()
        _select(tmp, rig, active=rig); bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
        ids = set(_unweighted(ob))
        for vg in tmp.vertex_groups:
            dst = ob.vertex_groups.get(vg.name) or ob.vertex_groups.new(name=vg.name)
            for v in tmp.data.vertices:
                if v.index in ids:
                    for g in v.groups:
                        if g.group == vg.index and g.weight > 0:
                            dst.add([v.index], g.weight, "REPLACE")
        bpy.data.objects.remove(tmp)
    still = len(_unweighted(ob))
    # back to metres: unparent first (a child would inherit the parent's scale as well as its own), scale both, re-parent
    _select(ob); bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in (ob, rig):
        o.scale = (1 / scale,) * 3
    _select(ob, rig); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.parent = rig; ob.matrix_parent_inverse = Matrix.Identity(4)
    am = ob.modifiers.get("Armature") or ob.modifiers.new("Armature", "ARMATURE"); am.object = rig
    return heat_failed, still


def bake_images(ob, res, samples=32):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = samples
    mt = bpy.data.materials.new("bake"); mt.use_nodes = True; nt = mt.node_tree
    ob.data.materials.clear(); ob.data.materials.append(mt)
    out = {}
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    for kind in ("AO", "POS"):
        img = bpy.data.images.new("bake_" + kind, res, res, float_buffer=True, alpha=False)
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img
        for n in nt.nodes:
            n.select = False
        tn.select = True; nt.nodes.active = tn
        if kind == "POS":
            geo = nt.nodes.new("ShaderNodeNewGeometry"); em = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(geo.outputs["Position"], em.inputs["Color"])
            nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
            sc.render.bake.margin = 16
            bpy.ops.object.bake(type="EMIT", margin=16)
        else:
            sc.render.bake.margin = 16
            sc.world = sc.world or bpy.data.worlds.new("w")
            bpy.ops.object.bake(type="AO", margin=16)
        out[kind] = np.array(img.pixels[:], np.float32).reshape(res, res, 4)[::-1, :, :3]   # top row first
    return out


def _uv_cover(ob, res):
    """texels actually inside a UV triangle (the bake margin paints beyond them)"""
    from PIL import Image, ImageDraw
    im = Image.new("L", (res, res), 0); d = ImageDraw.Draw(im)
    me = ob.data; uvl = me.uv_layers.active.data
    me.calc_loop_triangles()
    for tri in me.loop_triangles:
        d.polygon([(uvl[li].uv[0] * res, (1 - uvl[li].uv[1]) * res) for li in tri.loops], fill=255)
    return np.asarray(im) > 0


def export_data(ob, sk):
    """Blender mesh -> glTF-space arrays, vertices split at UV seams, 4 weights over the skeleton's joint order"""
    me = ob.data
    me.calc_loop_triangles() if hasattr(me, "calc_loop_triangles") else None
    uvl = me.uv_layers.active.data
    key = {}; V = []; N = []; UV = []; src = []
    F = []
    for tri in me.loop_triangles:
        f = []
        for li, vi in zip(tri.loops, tri.vertices):
            uv = uvl[li].uv
            k = (vi, round(uv[0], 6), round(uv[1], 6))
            if k not in key:
                key[k] = len(V); v = me.vertices[vi]
                V.append(C3.T @ np.array(v.co)); N.append(C3.T @ np.array(me.loops[li].normal if hasattr(me.loops[li], "normal") else v.normal))
                UV.append((uv[0], 1.0 - uv[1])); src.append(vi)
            f.append(key[k])
        F.append(f)
    V = np.array(V); N = np.array(N); UV = np.array(UV); F = np.array(F, np.int64); src = np.array(src)
    gi = {g.index: g.name for g in ob.vertex_groups}
    jidx = {n: i for i, n in enumerate(sk.names)}
    J = np.zeros((len(me.vertices), 4), np.uint16); Wt = np.zeros((len(me.vertices), 4), np.float32)
    for v in me.vertices:
        gs = sorted([(g.weight, jidx[gi[g.group]]) for g in v.groups if gi[g.group] in jidx and g.weight > 0], reverse=True)[:4]
        s = sum(w for w, _ in gs) or 1.0
        for k, (w, j) in enumerate(gs):
            J[v.index, k] = j; Wt[v.index, k] = w / s
    F = GM.orient(V, F)
    return V, N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12), UV, F, J[src], Wt[src]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=os.path.join(GAME, "assets", "models", "gaelic_player.glb"))
    ap.add_argument("--tris", type=int, default=22000)
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--voxel", type=float, default=0.0045)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tmpl = os.path.join(a.out, "_template.glb")
    if not os.path.exists(tmpl):
        shutil.copyfile(a.template, tmpl)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    T = {}; t0 = time.time()
    sk = FB.Skeleton.from_glb(tmpl)
    prims, _ = FB.design(sk, "home")
    rig = armature(sk)
    t = time.time(); ob = body_object(prims, a.voxel); T["remesh"] = time.time() - t
    hi = len(ob.data.polygons)
    t = time.time(); n0 = decimate(ob, a.tris); T["decimate"] = time.time() - t
    t = time.time(); unwrap(ob); T["unwrap"] = time.time() - t
    t = time.time(); heat_failed, unweighted = bind(ob, rig); T["weights"] = time.time() - t
    print("blender: remesh %d faces (%d tris) -> %d tris; bone heat missed %d verts (envelope filled), %d left" %
          (hi, n0, len(ob.data.polygons), heat_failed, unweighted))
    # glTF export with Blender's own exporter (mesh + armature; the game clips live in the template)
    t = time.time()
    bpy.ops.export_scene.gltf(filepath=os.path.join(a.out, "blender_native.glb"), export_format="GLB", use_selection=False,
                              export_animations=False)
    T["native_export"] = time.time() - t
    t = time.time(); bk = bake_images(ob, a.res); T["bake"] = time.time() - t
    pos = bk["POS"].reshape(-1, 3) @ C3                          # Blender Z-up -> glTF Y-up (rows: C3.T @ p)
    ao = bk["AO"][..., 0].reshape(-1)
    valid = np.linalg.norm(pos, axis=1) > 1e-6
    cover = _uv_cover(ob, a.res).reshape(-1)
    valid &= cover
    idx = np.nonzero(valid.reshape(a.res, a.res))
    P = pos[valid]
    # paint ownership against Blender's own geometry: voxel remesh is a hard union, so no smooth blend radii
    own = GM.layer_owners(P, prims, layer_k={l: 0.0 for l in set(p.layer for p in prims) | set(GM.LAYER_K) | {"skin"}})
    T["owners"] = time.time() - t
    V, N, UV, F, J, W = export_data(ob, sk)
    t = time.time(); pngs = {}
    from PIL import Image
    for kit in FB.KITS:
        pf = FB.paints(kit)
        rgb = np.zeros((len(P), 3)); pnt = np.array([prims[o].paint for o in own])
        for nme in set(pnt.tolist()):
            sel = pnt == nme
            c, _ = pf[nme].fn(P[sel], np.zeros((sel.sum(), 3))); rgb[sel] = c
        rgb *= (0.15 + 0.85 * np.clip(ao[valid], 0, 1))[:, None]
        img = np.zeros((a.res, a.res, 3)); vm = np.zeros((a.res, a.res), bool)
        img[idx] = np.clip(rgb, 0, 1); vm[idx] = True
        img = GM.dilate(img, vm)
        im = Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB"); im.save(os.path.join(a.out, "kit_%s.png" % kit), optimize=True)
        bio = io.BytesIO(); im.save(bio, "PNG", optimize=True); pngs[kit] = bio.getvalue()
    T["kits"] = time.time() - t
    size = glbpack.pack(tmpl, os.path.join(a.out, "gaelic_player.glb"), V, N, UV, F, J, W, pngs["home"], name="gaelic_footballer",
                        extras={"generator": "blender %s tools/blender_gaelic.py" % bpy.app.version_string})
    T["total"] = time.time() - t0
    stats = {"tris": int(len(F)), "verts": int(len(V)), "glb_bytes": size, "hi_faces": hi, "heat_failed_verts": heat_failed, "unweighted_verts": unweighted,
             "max_influences": int((W > 0).sum(1).max()), "mean_influences": float((W > 0).sum(1).mean()),
             "uv_coverage": float(valid.mean()), "seconds": {k: round(v, 1) for k, v in T.items()}}
    json.dump(stats, open(os.path.join(a.out, "stats.json"), "w"), indent=1)
    np.savez_compressed(os.path.join(a.out, "mesh.npz"), V=V, F=F, N=N, UV=UV, J=J, W=W)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
