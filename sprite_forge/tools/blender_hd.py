"""Build an HD Fighter character in Blender (bpy) and render its sprite sheets - the Blender reference build.

    python3 tools/blender_hd.py --spec ../HD_Fighter/sprite_specs/kairo.txt --out /tmp/bl --states idle,hp

The costume design is the same data Sprite Forge uses (sforge.sculpt presets, chosen by the text spec), but every
step after that is Blender's: primitive meshes (UV spheres, round-cone tubes, bevelled boxes, bisected), Boolean
carve, voxel remesh per garment layer, Corrective Smooth + Subdivision Surface, an Armature with automatic
(bone-heat) weights, Principled BSDF materials with vertex colours (skin with subsurface, satin, metal), a three-point
light rig with coloured rims, Cycles with denoising, and Freestyle ink lines.  Poses come from sforge.hdfighter.
"""
from __future__ import annotations
import argparse, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bpy, bmesh                                  # noqa: E402
from mathutils import Matrix, Vector               # noqa: E402
from sforge.spec import load_spec                  # noqa: E402
from sforge import sculpt as SC, hdfighter as HF   # noqa: E402
from sforge.rig import JOINT_NAMES, PARENT, HEIGHT  # noqa: E402
from sforge.mathutil import euler, ry, rx          # noqa: E402

C3 = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)      # Forge (Y up, faces +Z) -> Blender (Z up, faces -Y)
C4 = np.eye(4); C4[:3, :3] = C3


def M4(a):
    return Matrix([list(r) for r in a])


def bvec(p):
    return Vector(C3 @ np.asarray(p, float))


# ------------------------------------------------------------------ primitive meshes
def prim_bmesh(pr: SC.Prim, Wb):
    bm = bmesh.new()
    g = pr.grow
    if pr.kind == "ell":
        bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=18, radius=1.0)
        S = np.diag(list(np.asarray(pr.b, float) + g) + [1.0])
        R = np.eye(4); R[:3, :3] = euler(*pr.rot)
        T = np.eye(4); T[:3, 3] = pr.a
        L = T @ R @ S
    elif pr.kind == "box":
        bmesh.ops.create_cube(bm, size=2.0)
        h = np.asarray(pr.b, float) + g
        S = np.diag(list(h) + [1.0])
        R = np.eye(4); R[:3, :3] = euler(*pr.rot)
        T = np.eye(4); T[:3, 3] = pr.a
        L = T @ R @ S
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(pr.rb / max(h.min(), 1e-3), 0.95), segments=3, affect="EDGES",
                        profile=0.5)
    else:   # round cone: rings along the axis with spherical end caps
        a, b = np.asarray(pr.a, float), np.asarray(pr.b, float)
        ra, rb = pr.ra + g, pr.rb + g
        ax = b - a; L_ = np.linalg.norm(ax); ax = ax / max(L_, 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0, 0])
        u = np.cross(ref, ax); u /= np.linalg.norm(u); w = np.cross(ax, u)
        seg = 20; rows = []
        prof = []
        for k in range(6, 0, -1):                       # cap at a
            t = (k / 6) * math.pi / 2
            prof.append((-ra * math.sin(t), ra * math.cos(t), a))
        for k in range(9):
            s = k / 8
            prof.append((L_ * s, ra + (rb - ra) * s, a))
        for k in range(1, 7):
            t = (k / 6) * math.pi / 2
            prof.append((L_ + rb * math.sin(t), rb * math.cos(t), a))
        verts_rows = []
        for (d, r, _) in prof:
            c = a + ax * d
            if r < 1e-5:
                verts_rows.append([bm.verts.new(tuple(c))])
            else:
                verts_rows.append([bm.verts.new(tuple(c + (u * math.cos(2 * math.pi * i / seg) + w * math.sin(2 * math.pi * i / seg)) * r)) for i in range(seg)])
        for r0, r1 in zip(verts_rows, verts_rows[1:]):
            if len(r0) == 1 and len(r1) > 1:
                for i in range(seg):
                    bm.faces.new((r0[0], r1[(i + 1) % seg], r1[i]))
            elif len(r1) == 1 and len(r0) > 1:
                for i in range(seg):
                    bm.faces.new((r0[i], r0[(i + 1) % seg], r1[0]))
            else:
                for i in range(seg):
                    bm.faces.new((r0[i], r0[(i + 1) % seg], r1[(i + 1) % seg], r1[i]))
        L = np.eye(4)
    bmesh.ops.transform(bm, matrix=M4(L), verts=bm.verts)
    for n, off in pr.cuts:
        n = np.asarray(n, float); n = n / np.linalg.norm(n)
        res = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), plane_co=tuple(n * off),
                                     plane_no=tuple(n), clear_outer=True)
        edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if edges:
            bmesh.ops.holes_fill(bm, edges=list(bm.edges), sides=0)
    # bone-local -> bind world -> Blender
    M = C4 @ Wb[pr.bone]
    bmesh.ops.transform(bm, matrix=M4(M), verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def new_obj(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    return ob


def apply_mods(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def build_layer(name, prims, Wb, voxel, smooth_iter=6):
    """join the layer's primitives, carve its subtractive prims, voxel-remesh into one closed surface"""
    adds = [p for p in prims if not p.sub]
    subs = [p for p in prims if p.sub]
    bm = bmesh.new()
    for p in adds:
        b2 = prim_bmesh(p, Wb); me = bpy.data.meshes.new("tmp"); b2.to_mesh(me); b2.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    ob = new_obj(name, bm)
    rm = ob.modifiers.new("remesh", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = voxel; rm.adaptivity = 0.0
    apply_mods(ob)
    for i, p in enumerate(subs):
        cut = new_obj(name + "_cut%d" % i, prim_bmesh(p, Wb))
        bo = ob.modifiers.new("carve%d" % i, "BOOLEAN"); bo.operation = "DIFFERENCE"; bo.object = cut; bo.solver = "EXACT"
        apply_mods(ob); bpy.data.objects.remove(cut)
    if subs:
        rm = ob.modifiers.new("remesh2", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = voxel
        apply_mods(ob)
    sm = ob.modifiers.new("smooth", "CORRECTIVE_SMOOTH"); sm.iterations = smooth_iter; sm.smooth_type = "LENGTH_WEIGHTED"
    sm.use_only_smooth = True
    apply_mods(ob)
    return ob


# ------------------------------------------------------------------ armature
def build_armature(Wb):
    arm = bpy.data.armatures.new("rig"); ob = bpy.data.objects.new("rig", arm)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    child = {}
    for n in JOINT_NAMES:
        p = PARENT[n]
        if p and n != "ball":
            child.setdefault(p, n)
    pref = {"chest": "neck", "hips": "spine", "upperarm_L": "forearm_L", "upperarm_R": "forearm_R", "thigh_L": "shin_L", "thigh_R": "shin_R"}
    for n in JOINT_NAMES:
        if n in ("ball", "root"):
            continue
        eb = arm.edit_bones.new(n)
        head = C3 @ Wb[n][:3, 3]
        c = pref.get(n, child.get(n))
        if c and c != "ball":
            tail = C3 @ Wb[c][:3, 3]
        else:
            ext = {"head": (0, 0.2, 0), "hand_L": (0, -0.1, 0), "hand_R": (0, -0.1, 0), "foot_L": (0, -0.05, 0.16), "foot_R": (0, -0.05, 0.16)}.get(n, (0, 0.1, 0))
            tail = C3 @ (Wb[n][:3, :3] @ np.array(ext) + Wb[n][:3, 3])
        eb.head = Vector(head); eb.tail = Vector(tail)
        if np.linalg.norm(tail - head) < 1e-3:
            eb.tail = Vector(head + np.array([0, 0, 0.05]))
    for n in JOINT_NAMES:
        if n in ("ball", "root"):
            continue
        p = PARENT[n]
        if p and p != "root":
            arm.edit_bones[n].parent = arm.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    rest = {pb.name: np.array(pb.bone.matrix_local) for pb in ob.pose.bones}
    return ob, rest


def skin_to(ob, rig, Wb, fallback_prims):
    """automatic (bone heat) weights; any vertex left without weight gets distance weights to the bone segments"""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as e:
        print("  bone heat failed on", ob.name, e)
    me = ob.data
    names = [vg.name for vg in ob.vertex_groups]
    tot = np.zeros(len(me.vertices))
    for v in me.vertices:
        tot[v.index] = sum(g.weight for g in v.groups)
    bad = np.nonzero(tot < 1e-3)[0]
    if len(bad):
        # nearest bone segments from the Forge rig (pure geometry, no Forge weights)
        segs = []
        for n in JOINT_NAMES:
            if n in ("ball", "root"):
                continue
            pb = rig.data.bones[n]
            segs.append((n, np.array(pb.head_local), np.array(pb.tail_local)))
        P = np.array([tuple(me.vertices[i].co) for i in bad])
        D = []
        for n, a, b in segs:
            ab = b - a; t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
            D.append(np.linalg.norm(P - (a + t[:, None] * ab), axis=1))
        D = np.array(D)
        for k, i in enumerate(bad):
            order = np.argsort(D[:, k])[:2]
            w = 1.0 / (D[order, k] + 0.01) ** 2; w /= w.sum()
            for j, wt in zip(order, w):
                n = segs[j][0]
                vg = ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)
                vg.add([int(i)], float(wt), "REPLACE")
    if not ob.modifiers.get("Armature"):
        m = ob.modifiers.new("Armature", "ARMATURE"); m.object = rig
    ob.parent = rig
    return len(bad)


# ------------------------------------------------------------------ materials
def material(name, kind, rim=False):
    mt = bpy.data.materials.new(name); mt.use_nodes = True
    nt = mt.node_tree; bs = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], bs.inputs["Base Color"])
    rough = {"skin": 0.42, "cloth": 0.85, "silk": 0.38, "leather": 0.45, "hair": 0.35, "metal": 0.18, "rubber": 0.32, "eye": 0.2, "glow": 0.5}[kind]
    bs.inputs["Roughness"].default_value = rough
    if kind == "metal":
        bs.inputs["Metallic"].default_value = 1.0
    if kind == "skin":
        bs.inputs["Subsurface Weight"].default_value = 0.12
        bs.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
        bs.inputs["Subsurface Scale"].default_value = 0.01
    if kind == "silk":
        bs.inputs["Sheen Weight"].default_value = 0.6
    if kind == "cloth":
        bs.inputs["Sheen Weight"].default_value = 0.3
    # emissive paint (glow) from a second colour attribute
    ec = nt.nodes.new("ShaderNodeVertexColor"); ec.layer_name = "Em"
    nt.links.new(ec.outputs["Color"], bs.inputs["Emission Color"])
    bs.inputs["Emission Strength"].default_value = 4.0
    return mt


def paint_object(ob, ch, layer_prims, inv):
    """vertex colours from the costume paints (owner = the layer primitive the vertex lies on)"""
    me = ob.data
    P = np.array([C3.T @ np.array(v.co) for v in me.vertices])
    D = np.array([SC.prim_sdf(p, SC.to_local(P, p.bone, inv)) if not p.sub else np.full(len(P), 9.0) for p in layer_prims])
    owner = np.argmin(np.abs(D), axis=0)
    names = sorted({p.paint for p in layer_prims})
    idx = {n: i for i, n in enumerate(names)}
    pid = np.array([idx[layer_prims[o].paint] for o in owner])
    sm = SC.SculptMesh(P, np.zeros((0, 3), int), P, None, None, None, pid, names, None)
    rgb, em = SC.vertex_colours(ch, sm, P, pid)
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    ea = me.color_attributes.new("Em", "FLOAT_COLOR", "POINT")
    # Blender works in linear light: paints are authored in sRGB
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    ca.data.foreach_set("color", np.concatenate([lin, np.ones((len(P), 1))], 1).ravel().astype(np.float32))
    ea.data.foreach_set("color", np.concatenate([lin * em[:, None], np.ones((len(P), 1))], 1).ravel().astype(np.float32))
    mats = [layer_prims[o].mat for o in owner]
    return max(set(mats), key=mats.count)


# ------------------------------------------------------------------ scene
def setup_scene(ch, cell=(192, 256), figure_h=158.0, baseline=244, anchor=92, yaw=90.0, pitch=4.0, scale=2):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4; sc.cycles.diffuse_bounces = 2; sc.cycles.glossy_bounces = 2; sc.cycles.transmission_bounces = 2
    sc.render.film_transparent = True
    sc.render.resolution_x = cell[0] * scale; sc.render.resolution_y = cell[1] * scale; sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    bg = world.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (0.20, 0.21, 0.26, 1); bg.inputs["Strength"].default_value = 0.55
    # orthographic camera matching Forge's projection (anchor/baseline pixel = world origin on the ground)
    view = rx(pitch) @ ry(yaw)
    px_per_m = figure_h * ch.scale / HEIGHT
    qx = (cell[0] / 2 - anchor) / px_per_m; qy = (baseline - cell[1] / 2) / px_per_m
    right, up, back = view.T[:, 0], view.T[:, 1], view.T[:, 2]
    pos = right * qx + up * qy + back * 10.0
    cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"; cam_d.ortho_scale = max(cell) / px_per_m
    cam_d.clip_end = 40
    cam = bpy.data.objects.new("cam", cam_d); bpy.context.collection.objects.link(cam); sc.camera = cam
    R = np.eye(4); R[:3, 0] = C3 @ right; R[:3, 1] = C3 @ up; R[:3, 2] = C3 @ back; R[:3, 3] = C3 @ pos
    cam.matrix_world = M4(R)

    def sun(name, d_view, energy, color, size=8.0):
        d = view.T @ np.asarray(d_view, float); d /= np.linalg.norm(d)
        L = bpy.data.lights.new(name, "SUN"); L.energy = energy; L.color = color; L.angle = math.radians(size)
        o = bpy.data.objects.new(name, L); bpy.context.collection.objects.link(o)
        z = C3 @ d                                    # sun shines along -Z of the object
        zq = Vector(z).to_track_quat("Z", "Y")
        o.rotation_euler = zq.to_euler()
        return o
    sun("key", (-0.30, 0.62, 0.72), 3.6, (1.0, 0.96, 0.9))
    sun("fill", (0.75, 0.10, 0.45), 0.9, (0.75, 0.82, 1.0), 25)
    sun("rim_l", (-0.85, 0.35, -0.55), 4.0, tuple(ch.rim), 4)
    sun("rim_r", (0.85, 0.25, -0.5), 2.6, (0.65, 0.75, 1.0), 4)
    # Freestyle ink
    sc.render.use_freestyle = True; sc.render.line_thickness_mode = "ABSOLUTE"; sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]; vl.use_freestyle = True
    fs = vl.freestyle_settings
    ls = fs.linesets[0] if fs.linesets else fs.linesets.new("ink")
    ls.select_by_visibility = True; ls.select_by_edge_types = True
    ls.select_silhouette = True; ls.select_border = True; ls.select_crease = True; ls.select_material_boundary = True
    ls.select_external_contour = True
    fs.crease_angle = math.radians(120)
    lst = ls.linestyle; lst.color = tuple(np.array(ch.outline) / 255.0); lst.thickness = 2.4 * scale / 2
    lst.thickness_position = "INSIDE"
    return sc


def pose_rig(rig, rest, state, Wb):
    order = [n for n in JOINT_NAMES if n not in ("ball", "root")]
    for n in order:
        D = C4 @ state.world[n] @ np.linalg.inv(Wb[n]) @ np.linalg.inv(C4)
        rig.pose.bones[n].matrix = M4(D @ rest[n])
        bpy.context.view_layer.update()


def build(spec_path, log=print):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    sp = load_spec(spec_path)
    if "sculpt" not in sp.extra:
        sp.extra["sculpt"] = sp.name
    ch = SC.build_character(sp)
    Wb = SC.bind_world(); inv = SC._world_inv()
    t = time.time()
    rig, rest = build_armature(Wb)
    layers = {}
    for p in ch.prims:
        layers.setdefault((p.layer, p.fine), []).append(p)
    objs = []
    for (layer, fine), prims in sorted(layers.items()):
        vox = 0.003 if fine else 0.005
        ob = build_layer("%s%s" % (layer, "_head" if fine else ""), prims, Wb, vox)
        kind = paint_object(ob, ch, prims, inv)
        ob.data.materials.append(material(ob.name + "_m", kind))
        for f in ob.data.polygons:
            f.use_smooth = True
        bad = skin_to(ob, rig, Wb, prims)
        bpy.ops.object.select_all(action="DESELECT")
        objs.append(ob)
        log("  %-14s %6d verts  %s  unweighted->distance: %d" % (ob.name, len(ob.data.vertices), kind, bad))
    # rigid props (katana, hairpin) parented to their bone
    for i, pr in enumerate(ch.props):
        bm = bmesh.new()
        T = pr.tris.reshape(-1, 3)
        vs = [bm.verts.new(tuple(v)) for v in T]
        for k in range(len(pr.tris)):
            try:
                bm.faces.new((vs[3 * k], vs[3 * k + 1], vs[3 * k + 2]))
            except ValueError:
                pass
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.transform(bm, matrix=M4(C4 @ Wb[pr.bone]), verts=bm.verts)
        ob = new_obj("prop%d" % i, bm)
        me = ob.data
        rgb = np.asarray(ch.paints[pr.paint].fn(np.zeros((1, 3)), np.zeros((1, 3)))[0][0])
        lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT"); ea = me.color_attributes.new("Em", "FLOAT_COLOR", "POINT")
        for d in ca.data:
            d.color = (*lin, 1)
        for d in ea.data:
            d.color = (0, 0, 0, 1)
        me.materials.append(material("prop%d_m" % i, pr.mat))
        vg = ob.vertex_groups.new(name=pr.bone); vg.add(list(range(len(me.vertices))), 1.0, "REPLACE")
        m = ob.modifiers.new("Armature", "ARMATURE"); m.object = rig; ob.parent = rig
    # energy glows (Void's hands, Zap's fist): emissive spheres + point lights, parented to the hand bones
    for i, (bone, off, c, rad) in enumerate(ch.fx):
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=rad * 0.32)
        p = C3 @ (Wb[bone][:3, :3] @ np.array(off) + Wb[bone][:3, 3])
        bmesh.ops.translate(bm, vec=Vector(p), verts=bm.verts)
        ob = new_obj("glow%d" % i, bm)
        mt = bpy.data.materials.new("glow%d" % i); mt.use_nodes = True
        nt = mt.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
        em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*c, 1); em.inputs["Strength"].default_value = 6
        tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.7
        nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        ob.data.materials.append(mt)
        ob.visible_shadow = False
        vg = ob.vertex_groups.new(name=bone); vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
        m = ob.modifiers.new("Armature", "ARMATURE"); m.object = rig; ob.parent = rig
        Ld = bpy.data.lights.new("glowL%d" % i, "POINT"); Ld.energy = 6.0; Ld.color = c; Ld.shadow_soft_size = 0.05
        lo = bpy.data.objects.new("glowL%d" % i, Ld); bpy.context.collection.objects.link(lo)
        lo.parent = rig; lo.parent_type = "BONE"; lo.parent_bone = bone
        lo.matrix_world = M4(np.eye(4)); lo.location = Vector(p)
        lo.matrix_world = Matrix.Translation(Vector(p))
    log("  built in %.1fs" % (time.time() - t))
    return sp, ch, rig, rest, Wb


def glow_post(im, ch):
    """soft bloom around emissive pixels (the Forge renderer has the same pass)"""
    from PIL import ImageFilter, Image as I
    a = np.asarray(im).astype(np.float32) / 255
    rgb = a[..., :3]; al = a[..., 3:4]
    lum = rgb.max(-1)
    hot = np.clip((lum - 0.85) / 0.15, 0, 1)[..., None] * rgb * al
    if hot.max() <= 0:
        return im
    blur = np.stack([np.asarray(I.fromarray((hot[..., c] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5))) / 255 for c in range(3)], -1)
    out_rgb = rgb * al + blur * 0.9
    out_a = np.clip(al[..., 0] + blur.max(-1) * 0.9, 0, 1)[..., None]
    out_rgb = np.where(out_a > 1e-4, out_rgb / np.maximum(out_a, 1e-4), 0)
    return I.fromarray((np.clip(np.concatenate([out_rgb, out_a], -1), 0, 1) * 255).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--states", default=",".join(HF.STATES))
    ap.add_argument("--frames", default="", help="only these frame indices (e.g. 0,1)")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--blend", action="store_true", help="also save the .blend")
    ap.add_argument("--resume", action="store_true", help="skip states whose sheet already exists")
    a = ap.parse_args()
    from PIL import Image
    sp, ch, rig, rest, Wb = build(a.spec)
    sc = setup_scene(ch)
    sc.cycles.samples = a.samples
    os.makedirs(a.out, exist_ok=True)
    if a.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, sp.name + ".blend"))
    only = [int(x) for x in a.frames.split(",") if x != ""]
    tmp = os.path.join(a.out, "_frame.png")
    for s in a.states.split(","):
        if a.resume and os.path.exists(os.path.join(a.out, "%s_%s.png" % (sp.name, s))):
            continue
        sts = HF.states(s, char=sp.extra.get("sculpt", sp.name))
        cells = []
        for i, st in enumerate(sts):
            if only and i not in only:
                cells.append(None); continue
            pose_rig(rig, rest, st, Wb)
            t = time.time()
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            im = Image.open(tmp).convert("RGBA")
            im = glow_post(im, ch)
            cells.append(im.resize((192, 256), Image.LANCZOS))
            print("  %s %s[%d] %.1fs" % (sp.name, s, i, time.time() - t), flush=True)
        sheet = Image.new("RGBA", (192 * len(sts), 256), (0, 0, 0, 0))
        for i, c in enumerate(cells):
            if c is not None:
                sheet.paste(c, (192 * i, 0))
        sheet.save(os.path.join(a.out, "%s_%s.png" % (sp.name, s)))


if __name__ == "__main__":
    main()
