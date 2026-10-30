"""Facility 64 - headless Blender generator for the Enhanced-mode models.

Builds ORIGINAL placeholder assets (no third-party/copyrighted meshes):
  * rigged humanoids (5 outfits) with clips idle/walk/run/aim/shoot/death/reload
  * world weapons (attached to the 'gun' bone at runtime)
  * first-person viewmodels (arms + weapon, clips idle/shoot/reload)
  * props (crate, barrel, desk, rack)
and exports them as GLB into assets/models.

Run with Blender's Python (no GUI needed):
  blender -b -P tools/make_models.py -- <texture_dir> <out_dir>
  or with the pip 'bpy' module:  python tools/make_models.py <texture_dir> <out_dir>
Textures come from tools/make_textures.py.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Quaternion, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
TEX = os.path.abspath(argv[0] if len(argv) > 0 else "build_tex")
OUT = os.path.abspath(argv[1] if len(argv) > 1 else "assets/models")
ONLY = argv[2].split(",") if len(argv) > 2 else None
os.makedirs(OUT, exist_ok=True)
FPS = 30

def V(*a): return Vector(a)

# ============================================================ scene/material helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _imgcache.clear()
    bpy.context.scene.render.fps = FPS

_imgcache = {}
def image(name):
    if name in _imgcache: return _imgcache[name]
    img = bpy.data.images.load(os.path.join(TEX, name + ".png"))
    _imgcache[name] = img
    return img

def material(name, texname=None, color=(1, 1, 1), rough=0.6, metal=0.0, emissive=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if texname:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = image(texname)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if emissive:
            nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.0
    return m

# ============================================================ geometry accumulator
class Part:
    """Accumulates polygons with material index, per-corner UVs and per-vertex bone weights."""
    def __init__(self):
        self.V = []; self.F = []; self.FM = []; self.UV = []; self.W = []; self.SMOOTH = []

    def add_bm(self, bm, mat, xf=Matrix(), bone=None, uv="box", uvs=3.0, smooth=True, weights=None, uvfunc=None):
        bm.verts.ensure_lookup_table(); bm.verts.index_update()
        base = len(self.V)
        nm = xf.to_3x3().inverted().transposed()
        for v in bm.verts:
            self.V.append(tuple(xf @ v.co))
            if weights is not None: self.W.append(weights(xf @ v.co))
            else: self.W.append([(bone, 1.0)] if bone else [])
        uvl = bm.loops.layers.uv.active
        for f in bm.faces:
            idx = [base + v.index for v in f.verts]
            self.F.append(idx); self.FM.append(mat); self.SMOOTH.append(smooth)
            n = (nm @ f.normal).normalized()
            cs = []
            for l in f.loops:
                p = xf @ l.vert.co
                if uvfunc: cs.append(uvfunc(p, n, l))
                elif uv == "keep" and uvl is not None: cs.append(tuple(l[uvl].uv))
                else:
                    ax = max(range(3), key=lambda k: abs(n[k]))
                    if ax == 0: cs.append((p.y*uvs*(1 if n.x > 0 else -1), p.z*uvs))
                    elif ax == 1: cs.append((p.x*uvs*(-1 if n.y > 0 else 1), p.z*uvs))
                    else: cs.append((p.x*uvs, p.y*uvs*(1 if n.z > 0 else -1)))
            self.UV.append(cs)
        bm.free()

    def build(self, name, mats, arm_obj=None, bones=None, sharp_angle=40):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.V, [], self.F)
        me.update()
        uvl = me.uv_layers.new(name="UVMap")
        li = 0
        for pi, poly in enumerate(me.polygons):
            poly.material_index = self.FM[pi]
            poly.use_smooth = self.SMOOTH[pi]
            for k in range(poly.loop_total):
                uvl.data[poly.loop_start + k].uv = self.UV[pi][k]
        if sharp_angle:
            try: me.set_sharp_from_angle(angle=math.radians(sharp_angle))
            except Exception: pass
        for m in mats: me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        if arm_obj is not None:
            groups = {b: ob.vertex_groups.new(name=b) for b in bones}
            for vi, ws in enumerate(self.W):
                tot = sum(w for _, w in ws) or 1.0
                for b, w in ws:
                    if w > 1e-4: groups[b].add([vi], w/tot, "REPLACE")
            ob.parent = arm_obj
            mod = ob.modifiers.new("Armature", "ARMATURE"); mod.object = arm_obj
        return ob

# ---- bmesh primitive helpers (all return a fresh bmesh)
def bm_box(sx, sy, sz, bevel=0.0, seg=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x*sx, v.co.y*sy, v.co.z*sz))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(sx, sy, sz)*0.45), segments=seg, affect="EDGES", profile=0.5)
    return bm

def bm_cyl(r1, r2, depth, seg=16, caps=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=depth)
    return bm

def bm_sphere(r, us=16, vs=10):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=us, v_segments=vs, radius=r)
    return bm

def bm_loft(sections, cap=True):
    """sections: list of lists of Vector (same count, closed rings) -> skinned tube"""
    bm = bmesh.new()
    rings = [[bm.verts.new(p) for p in s] for s in sections]
    n = len(sections[0])
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm

def rect(cx, cy, cz, hw, hh, plane="xz"):
    """rectangle ring in a plane perpendicular to Y (x/z) - for lofts along Y"""
    return [V(cx - hw, cy, cz - hh), V(cx + hw, cy, cz - hh), V(cx + hw, cy, cz + hh), V(cx - hw, cy, cz + hh)]

def T(x=0, y=0, z=0): return Matrix.Translation((x, y, z))
def RX(a): return Matrix.Rotation(a, 4, "X")
def RY(a): return Matrix.Rotation(a, 4, "Y")
def RZ(a): return Matrix.Rotation(a, 4, "Z")
def S(x, y=None, z=None):
    y = x if y is None else y; z = x if z is None else z
    return Matrix.Diagonal((x, y, z, 1))

# ============================================================ armature + posing
class Rig:
    def __init__(self, name, bones):
        """bones: list of (name, head, tail, parent) parents first"""
        arm = bpy.data.armatures.new(name)
        ob = bpy.data.objects.new(name, arm)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        for n, h, t, p in bones:
            eb = arm.edit_bones.new(n)
            eb.head = h; eb.tail = t; eb.roll = 0.0
            if p: eb.parent = arm.edit_bones[p]
        bpy.ops.object.mode_set(mode="OBJECT")
        self.ob = ob
        self.order = [b[0] for b in bones]
        self.parent = {b[0]: b[3] for b in bones}
        self.children = {n: [b[0] for b in bones if b[3] == n] for n in self.order}
        self.head = {}; self.tail = {}; self.R = {}
        for b in arm.bones:
            self.head[b.name] = b.head_local.copy(); self.tail[b.name] = b.tail_local.copy()
            self.R[b.name] = b.matrix_local.to_quaternion()
        for pb in ob.pose.bones: pb.rotation_mode = "QUATERNION"
        self.clips = []

    def fk(self, Q, off):
        """Q: bone -> Quaternion in armature axes (relative to parent); off: bone -> Vector translation
        returns (Qacc, headPosed, tailPosed)"""
        qa, hp, tp = {}, {}, {}
        for b in self.order:
            p = self.parent[b]
            q = Q.get(b, Quaternion())
            o = off.get(b, Vector())
            if p is None:
                qa[b] = q.copy(); hp[b] = self.head[b] + o
            else:
                qa[b] = qa[p] @ q
                hp[b] = hp[p] + qa[p] @ (self.head[b] - self.head[p] + o)
            tp[b] = hp[b] + qa[b] @ (self.tail[b] - self.head[b])
        return qa, hp, tp

    def ik2(self, Q, off, upper, fore, target, pole):
        qa, hp, tp = self.fk(Q, off)
        Sx = hp[upper]
        a = (self.tail[upper] - self.head[upper]).length
        b = (self.tail[fore] - self.head[fore]).length
        d_vec = target - Sx
        d = max(min(d_vec.length, a + b - 1e-4), abs(a - b) + 1e-4)
        dirT = d_vec.normalized()
        pn = pole - dirT*pole.dot(dirT)
        if pn.length < 1e-6: pn = Vector((0, 0, -1)) - dirT*(-dirT.z)
        pn.normalize()
        cosA = max(-1.0, min(1.0, (a*a + d*d - b*b)/(2*a*d)))
        sinA = math.sqrt(max(0.0, 1 - cosA*cosA))
        E = Sx + dirT*(a*cosA) + pn*(a*sinA)
        W = Sx + dirT*d
        pu = self.parent[upper]
        qp = qa[pu] if pu else Quaternion()
        cur = qp @ (self.tail[upper] - self.head[upper]).normalized()
        rot = cur.rotation_difference((E - Sx).normalized())
        qau = rot @ qp
        Q[upper] = qp.inverted() @ qau
        cur2 = qau @ (self.tail[fore] - self.head[fore]).normalized()
        rot2 = cur2.rotation_difference((W - E).normalized())
        qaf = rot2 @ qau
        Q[fore] = qau.inverted() @ qaf
        return qaf

    def add_clip(self, name, nframes, posefn, loop=True):
        """posefn(t in [0,1]) -> (Q, off). Keys every frame (baked)."""
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        self.ob.animation_data_create()
        self.ob.animation_data.action = act
        last = nframes if loop else nframes - 1
        prev = {}
        for f in range(0, last + 1):
            t = (f % nframes)/nframes if loop else f/max(1, nframes - 1)
            Q, off = posefn(t)
            for b in self.order:
                pb = self.ob.pose.bones[b]
                R = self.R[b]
                qb = R.inverted() @ Q.get(b, Quaternion()) @ R
                if b in prev and prev[b].dot(qb) < 0: qb.negate()
                prev[b] = qb.copy()
                pb.rotation_quaternion = qb
                pb.keyframe_insert("rotation_quaternion", frame=f, group=b)
                if b in off or self.parent[b] is None:
                    pb.location = R.inverted() @ off.get(b, Vector())
                    pb.keyframe_insert("location", frame=f, group=b)
        for fc in act.fcurves:
            for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
        tr = self.ob.animation_data.nla_tracks.new(); tr.name = name
        tr.strips.new(name, 0, act)
        self.ob.animation_data.action = None
        self.clips.append(name)

def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")
    has_arm = any(o.type == "ARMATURE" for o in objs)
    if has_arm:
        kw.update(export_skins=True, export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
                  export_all_influences=False, export_def_bones=False, export_optimize_animation_size=False,
                  export_anim_single_armature=True, export_reset_pose_bones=True)
    else:
        kw.update(export_animations=False, export_skins=False)
    bpy.ops.export_scene.gltf(**kw)
    print("  wrote", os.path.basename(path), os.path.getsize(path)//1024, "KB")

# ============================================================ skinning helpers
def seg_dist(p, a, b):
    ab = b - a; t = max(0.0, min(1.0, (p - a).dot(ab)/max(ab.length_squared, 1e-9)))
    return (p - (a + ab*t)).length, t

def capsule_weights(rig, bones, blend=0.05, exclude=()):
    """nearest-segment skinning with smooth blends only between parent/child at joints"""
    segs = [(b, rig.head[b], rig.tail[b]) for b in bones if b not in exclude]
    def fn(p):
        ds = sorted(((seg_dist(p, h, t)[0], b) for b, h, t in segs))
        d1, b1 = ds[0]
        adj = [b for b in (rig.parent[b1],) if b] + rig.children[b1]
        cand = [(d, b) for d, b in ds[1:] if b in adj]
        if not cand: return [(b1, 1.0)]
        d2, b2 = cand[0]
        t = max(0.0, min(1.0, (d2 - d1)/blend))
        w1 = 0.5 + 0.5*t
        return [(b1, w1), (b2, 1 - w1)]
    return fn

# ============================================================ HUMANOID
HUMAN_BONES = None
def humanoid_bones():
    A = math.radians(48)                  # rest arm angle from vertical (A-pose)
    bones = [("hips", V(0, 0, 0.98), V(0, 0, 1.10), None),
             ("spine", V(0, 0, 1.10), V(0, 0, 1.30), "hips"),
             ("chest", V(0, 0, 1.30), V(0, 0, 1.50), "spine"),
             ("neck", V(0, 0, 1.50), V(0, 0, 1.61), "chest"),
             ("head", V(0, 0, 1.61), V(0, 0, 1.86), "neck")]
    for s, sx in (("L", 1), ("R", -1)):
        sh = V(sx*0.19, 0.01, 1.45)
        d = V(sx*math.sin(A), 0, -math.cos(A))
        el = sh + d*0.29; wr = el + d*0.265; ha = wr + d*0.17
        bones += [("upperarm." + s, sh, el, "chest"), ("forearm." + s, el, wr, "upperarm." + s), ("hand." + s, wr, ha, "forearm." + s)]
        hp = V(sx*0.10, 0.0, 0.93); kn = V(sx*0.11, -0.01, 0.52); an = V(sx*0.115, 0.03, 0.09); to = V(sx*0.12, -0.12, 0.03)
        bones += [("thigh." + s, hp, kn, "hips"), ("shin." + s, kn, an, "thigh." + s), ("foot." + s, an, to, "shin." + s)]
    # weapon socket: child of the right hand, points forward (-Y), origin = grip point in the palm
    wrR = [b for b in bones if b[0] == "hand.R"][0]
    palm = wrR[1] + (wrR[2] - wrR[1])*0.45
    bones.append(("gun", palm, palm + V(0, -0.2, 0), "hand.R"))
    return bones

def skin_body(rig, style, mats):
    """organic body from a Skin modifier graph + subdivision, returned as Part data"""
    H = rig.head; Tl = rig.tail
    verts, edges, radii = [], [], []
    def vtx(p, r):
        verts.append(tuple(p)); radii.append(r if isinstance(r, tuple) else (r, r)); return len(verts) - 1
    bulk = style.get("bulk", 1.0)
    pel = vtx(V(0, 0.005, 0.95), (0.155*bulk, 0.11*bulk))
    wai = vtx(V(0, 0.0, 1.10), (0.145*bulk, 0.10*bulk))
    ch = vtx(V(0, -0.005, 1.30), (0.175*bulk, 0.115*bulk))
    up = vtx(V(0, 0.005, 1.44), (0.165*bulk, 0.10*bulk))
    nk = vtx(V(0, 0.012, 1.52), 0.064)
    nt = vtx(V(0, 0.016, 1.60), 0.057)
    edges += [(pel, wai), (wai, ch), (ch, up), (up, nk), (nk, nt)]
    for s, sx in (("L", 1), ("R", -1)):
        sh = vtx(H["upperarm." + s] + V(-sx*0.01, 0, -0.01), 0.068*bulk)
        edges.append((up, sh))
        ua = vtx(H["upperarm." + s].lerp(Tl["upperarm." + s], 0.5), 0.058*bulk)
        el = vtx(Tl["upperarm." + s], 0.046*bulk)
        fa = vtx(H["forearm." + s].lerp(Tl["forearm." + s], 0.45), 0.047*bulk)
        wr = vtx(Tl["forearm." + s], 0.033)
        hd = H["hand." + s]; d = (Tl["hand." + s] - hd).normalized()
        palm = vtx(hd + d*0.06, (0.042, 0.02))
        tip = vtx(hd + d*0.15, (0.036, 0.016))
        side = V(0, -1, 0)
        th0 = vtx(hd + d*0.035 + side*0.025, 0.014)
        th1 = vtx(hd + d*0.08 + side*0.04, 0.011)
        edges += [(sh, ua), (ua, el), (el, fa), (fa, wr), (wr, palm), (palm, tip), (wr, th0), (th0, th1)]
        hp = vtx(H["thigh." + s] + V(0, 0, 0.0), 0.095*bulk)
        edges.append((pel, hp))
        th = vtx(H["thigh." + s].lerp(Tl["thigh." + s], 0.45), 0.085*bulk)
        kn = vtx(Tl["thigh." + s], 0.058*bulk)
        ca = vtx(H["shin." + s].lerp(Tl["shin." + s], 0.35), 0.062*bulk)
        an = vtx(Tl["shin." + s] + V(0, 0, 0.02), 0.048)
        heel = vtx(V(sx*0.115, 0.06, 0.045), 0.045)
        toe = vtx(V(sx*0.12, -0.14, 0.04), (0.046, 0.035))
        edges += [(hp, th), (th, kn), (kn, ca), (ca, an), (an, heel), (an, toe)]
    me = bpy.data.meshes.new("skinbody"); me.from_pydata(verts, edges, []); me.update()
    ob = bpy.data.objects.new("skinbody", me); bpy.context.scene.collection.objects.link(ob)
    sk = ob.modifiers.new("Skin", "SKIN"); sk.use_smooth_shade = True; sk.branch_smoothing = 0.6
    for i, r in enumerate(radii):
        me.skin_vertices[0].data[i].radius = r
    me.skin_vertices[0].data[pel].use_root = True
    sub = ob.modifiers.new("Sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 2
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    m2 = bpy.data.meshes.new_from_object(ev)
    bm = bmesh.new(); bm.from_mesh(m2)
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(m2)
    return bm

def head_mesh(rig, style):
    c = V(0, -0.004, 1.705)
    rx, ry, rz = 0.086, 0.103, 0.121
    bm = bm_sphere(1.0, 32, 20)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        us = []
        for l in f.loops:
            p = l.vert.co
            u = 0.5 + math.atan2(p.x, -p.y)/(2*math.pi)
            v = 0.5 + math.asin(max(-1, min(1, p.z)))/math.pi
            us.append([u, v])
        umin = min(u for u, _ in us); umax = max(u for u, _ in us)
        if umax - umin > 0.5:
            for uv in us:
                if uv[0] < 0.5: uv[0] += 1.0
        for l, uv in zip(f.loops, us): l[uvl].uv = uv
    for v in bm.verts:
        p = v.co.copy()
        x, y, z = p.x*rx, p.y*ry, p.z*rz
        if z < 0:                       # jaw taper + chin
            k = (-p.z)**1.6
            x *= 1 - 0.22*k
            y *= 1 - 0.12*k
            if p.y < 0: y -= 0.012*k*max(0, -p.y)
        if p.y < -0.3 and abs(p.z) < 0.5:   # flatter face plane, brow ridge
            y += 0.008
        if p.y > 0.2 and p.z > -0.2:        # rounder back of skull
            y += 0.01*p.y
        v.co = c + V(x, y, z)
    return bm, c

def build_humanoid(name, style):
    reset()
    bones = humanoid_bones()
    rig = Rig(name + "_rig", bones)
    deform = [b[0] for b in bones if b[0] != "gun"]
    # ---- materials
    M = {}
    def mat(key, tex, rough=0.7, metal=0.0):
        M[key] = len(M); mats.append(material(name + "_" + key, tex, rough=rough, metal=metal))
    mats = []
    mat("top", style["top"]); mat("legs", style["legs"]); mat("skin", style["skin"], 0.55)
    mat("face", style["face"], 0.55); mat("boots", "ch_leather", 0.4); mat("belt", style.get("belt", "ch_leather"), 0.5)
    mat("hands", style.get("hands", style["skin"]), 0.5)
    if style.get("shirt"): mat("shirt", style["shirt"], 0.7); mat("tie", style["tie"], 0.6)
    if style.get("vest"): mat("vest", style["vest"], 0.8)
    if style.get("hat"): mat("hat", style["hat_tex"], 0.6)
    if style.get("hair_tex"): mat("hair", style["hair_tex"], 0.8)
    part = Part()
    wfn = capsule_weights(rig, deform, exclude=())
    # ---- body
    bm = skin_body(rig, style, M)
    # material per face from region
    faces_mat = []
    for f in bm.faces:
        c = f.calc_center_median(); n = f.normal
        d, nearest = min(((seg_dist(c, rig.head[b], rig.tail[b])[0], b) for b in deform))
        m = M["top"]
        if nearest.startswith(("thigh", "shin")): m = M["legs"]
        if nearest.startswith("foot") or (nearest.startswith("shin") and c.z < 0.17): m = M["boots"]
        if nearest == "hips": m = M["legs"] if c.z < 1.0 else M["top"]
        if nearest.startswith("hand"): m = M["hands"]
        if nearest.startswith("forearm"):
            _, t = seg_dist(c, rig.head[nearest], rig.tail[nearest])
            if t > 0.93: m = M["hands"] if style.get("gloves") else (M["shirt"] if style.get("shirt") else M["skin"])
            elif style.get("rolled") and t > 0.45: m = M["skin"]
        if nearest in ("neck", "head"): m = M["skin"] if not style.get("neck_cover") else M["top"]
        if nearest == "neck" and c.z < 1.495: m = M["top"]
        if style.get("shirt") and nearest in ("chest", "neck") and n.y < -0.35:
            # suit: white shirt V and tie on the chest front
            vz = c.z - 1.25
            if vz > 0 and c.z < 1.50 and abs(c.x) < vz*0.36: m = M["tie"] if abs(c.x) < 0.016 + (1.47 - c.z)*0.06 and c.z < 1.47 else M["shirt"]
        if style.get("shirt") and nearest == "neck" and c.z < 1.55 and abs(c.x) < 0.075: m = M["shirt"]
        if abs(c.z - 1.0) < 0.03 and nearest in ("hips", "spine"): m = M["belt"]
        faces_mat.append(m)
    # split by material: add_bm takes one mat, so do it manually
    bm.verts.index_update()
    base = len(part.V)
    for v in bm.verts:
        part.V.append(tuple(v.co)); part.W.append(wfn(v.co))
    for f, m in zip(bm.faces, faces_mat):
        part.F.append([base + v.index for v in f.verts]); part.FM.append(m); part.SMOOTH.append(True)
        n = f.normal; cs = []
        for l in f.loops:
            p = l.vert.co
            ax = max(range(3), key=lambda k: abs(n[k]))
            sc = 3.0
            cs.append((p.y*sc, p.z*sc) if ax == 0 else ((p.x*sc, p.z*sc) if ax == 1 else (p.x*sc, p.y*sc)))
        part.UV.append(cs)
    bm.free()
    # ---- head
    hb, hc = head_mesh(rig, style)
    part.add_bm(hb, M["face"], bone="head", uv="keep")
    # nose
    nb = bm_sphere(1.0, 10, 8)
    part.add_bm(nb, M["face"], T(hc.x, hc.y - 0.100, hc.z - 0.020) @ S(0.0105, 0.016, 0.022), bone="head",
                uvfunc=lambda p, n, l: (0.5, 0.47))
    for sx in (1, -1):   # ears
        eb = bm_sphere(1.0, 10, 8)
        part.add_bm(eb, M["skin"], T(hc.x + sx*0.085, hc.y + 0.008, hc.z - 0.005) @ S(0.012, 0.022, 0.032), bone="head")
    # hair volume (simple cap above the scalp)
    if style.get("hair_tex"):
        hb2 = bm_sphere(1.0, 24, 12)
        bmesh.ops.delete(hb2, geom=[v for v in hb2.verts if v.co.z < -0.05 or (v.co.y < -0.55 and v.co.z < 0.55)], context="VERTS")
        part.add_bm(hb2, M["hair"], T(hc.x, hc.y + 0.008, hc.z + 0.012) @ S(0.086, 0.104, 0.118), bone="head", uvs=8.0)
    # ---- headgear
    hat = style.get("hat")
    if hat == "helmet":
        b = bm_sphere(1.0, 24, 12)
        bmesh.ops.delete(b, geom=[v for v in b.verts if v.co.z < -0.02], context="VERTS")
        part.add_bm(b, M["hat"], T(hc.x, hc.y + 0.005, hc.z + 0.040) @ S(0.112, 0.128, 0.12), bone="head", uvs=6)
        rim = bm_cyl(1.0, 1.0, 1.0, 24, caps=False)
        part.add_bm(rim, M["hat"], T(hc.x, hc.y + 0.005, hc.z + 0.036) @ S(0.118, 0.134, 0.012), bone="head", uvs=6)
        strap = bm_cyl(1.0, 1.0, 1.0, 16, caps=False)
        part.add_bm(strap, M["belt"], T(hc.x, hc.y + 0.01, hc.z - 0.045) @ RY(0) @ S(0.084, 0.06, 0.006) , bone="head")
    elif hat == "cap":
        b = bm_cyl(1.0, 0.92, 1.0, 24)
        part.add_bm(b, M["hat"], T(hc.x, hc.y + 0.005, hc.z + 0.068) @ S(0.094, 0.110, 0.055), bone="head", uvs=6)
        top = bm_cyl(1.0, 1.0, 1.0, 24)
        part.add_bm(top, M["hat"], T(hc.x, hc.y - 0.010, hc.z + 0.100) @ S(0.108, 0.128, 0.012), bone="head", uvs=6)
        brim = bm_cyl(1.0, 1.0, 1.0, 20)
        bmesh.ops.delete(brim, geom=[v for v in brim.verts if v.co.y > 0.1], context="VERTS")
        part.add_bm(brim, M["belt"], T(hc.x, hc.y - 0.085, hc.z + 0.038) @ RX(0.22) @ S(0.090, 0.080, 0.008), bone="head")
        badge = bm_box(0.030, 0.004, 0.022, bevel=0.002)
        part.add_bm(badge, M["belt"], T(hc.x, hc.y - 0.113, hc.z + 0.072) @ RX(-0.2), bone="head")
    elif hat == "beanie":
        b = bm_sphere(1.0, 24, 12)
        bmesh.ops.delete(b, geom=[v for v in b.verts if v.co.z < 0.05], context="VERTS")
        part.add_bm(b, M["hat"], T(hc.x, hc.y + 0.008, hc.z + 0.012) @ S(0.090, 0.108, 0.125), bone="head", uvs=10)
        fold = bm_cyl(1.0, 1.0, 1.0, 24, caps=False)
        part.add_bm(fold, M["hat"], T(hc.x, hc.y + 0.008, hc.z + 0.03) @ S(0.091, 0.109, 0.022), bone="head", uvs=10)
    # ---- vest + pouches + belt
    if style.get("vest"):
        vb = bm_loft([[V(x*0.195, y*0.13, z) for x, y in ((-1, -1), (1, -1), (1.05, 0), (1, 1), (-1, 1), (-1.05, 0))] for z in (1.08, 1.47)][:1] +
                     [[V(x*0.195, y*0.13, 1.47) for x, y in ((-0.6, -1), (0.6, -1), (0.7, 0), (0.6, 1), (-0.6, 1), (-0.7, 0))]])
        part.add_bm(vb, M["vest"], weights=capsule_weights(rig, ["hips", "spine", "chest"]), uvs=4)
        for sx in (-1, 0, 1):
            pb = bm_box(0.07, 0.04, 0.085, bevel=0.01)
            part.add_bm(pb, M["vest"], T(sx*0.085, -0.155, 1.19), weights=capsule_weights(rig, ["spine", "chest"]), uvs=6)
    belt = bm_cyl(1.0, 1.0, 1.0, 24, caps=False)
    part.add_bm(belt, M["belt"], T(0, 0.004, 0.995) @ S(0.162*style.get("bulk", 1), 0.117*style.get("bulk", 1), 0.025), bone="hips", uvs=6)
    buckle = bm_box(0.045, 0.01, 0.03, bevel=0.004)
    part.add_bm(buckle, M["belt"], T(0, -0.122*style.get("bulk", 1), 0.995), bone="hips")
    if style.get("holster"):
        hb3 = bm_box(0.04, 0.09, 0.13, bevel=0.012)
        part.add_bm(hb3, M["belt"], T(-0.17, 0.0, 0.92) @ RX(0.15), bone="hips")
    if style.get("collar"):
        cb = bm_cyl(1.0, 0.85, 1.0, 20, caps=False)
        part.add_bm(cb, M["top"], T(0, 0.012, 1.535) @ S(0.072, 0.07, 0.035), bone="neck", uvs=6)
    if style.get("epaulettes"):
        for sx in (1, -1):
            eb2 = bm_box(0.05, 0.11, 0.012, bevel=0.004)
            part.add_bm(eb2, M["top"], T(sx*0.15, 0.005, 1.505) @ RY(sx*0.35), weights=capsule_weights(rig, ["chest"]))
    ob = part.build(name, mats, rig.ob, deform)
    # smooth shading everywhere for the organic parts
    humanoid_clips(rig)
    export(os.path.join(OUT, name + ".glb"), [rig.ob, ob])

# ---------------- humanoid animation
def humanoid_clips(rig):
    hips_h = rig.head["hips"]
    gun_rest = rig.R["gun"]
    off_gun = rig.head["gun"] - rig.head["hand.R"]

    def q(axis, ang):
        return Quaternion(Vector(axis), ang)

    def gun_frame(fwd, up):
        f = fwd.normalized(); u = (up - f*up.dot(f)).normalized(); x = f.cross(u)
        M3 = Matrix((x, f, u)).transposed()           # columns X, Y(=fwd), Z(=up)
        return M3.to_quaternion() @ gun_rest.inverted()

    def hold(Q, off, P, fwd, up, left=True, ltarget=None):
        """place the weapon socket at P (armature space) with orientation fwd/up; right arm IK, left arm IK to foregrip"""
        qg = gun_frame(fwd, up)
        wrist = P - qg @ off_gun
        qf = rig.ik2(Q, off, "upperarm.R", "forearm.R", wrist, V(-0.8, 0.5, -0.6))
        Q["hand.R"] = qf.inverted() @ qg
        if left:
            fg = ltarget if ltarget is not None else P + qg @ V(0.0, -0.27, -0.03)
            rig.ik2(Q, off, "upperarm.L", "forearm.L", fg + qg @ V(0.035, 0.05, -0.035), V(0.9, 0.3, -0.6))
            qa, _, _ = rig.fk(Q, off)
            # left palm faces up/inwards under the handguard
            Q["hand.L"] = qa["forearm.L"].inverted() @ gun_frame(fwd, up) @ q((0, 1, 0), -1.2) @ q((1, 0, 0), 0.6)
        return qg

    def legs(Q, swing, knee, side):
        Q["thigh." + side] = q((1, 0, 0), -swing)
        Q["shin." + side] = q((1, 0, 0), knee)
        Q["foot." + side] = q((1, 0, 0), swing - knee*0.9)

    def chest_pos(Q, off):
        qa, hp, tp = rig.fk(Q, off)
        return qa, hp

    def base_stance(t, Q, off, breathe=0.01):
        b = math.sin(t*2*math.pi)
        Q["spine"] = q((1, 0, 0), 0.03 + breathe*b)
        Q["chest"] = q((1, 0, 0), 0.02 + breathe*b)
        legs(Q, 0.06, 0.10, "L"); legs(Q, -0.06, 0.12, "R")
        Q["thigh.L"] = Q["thigh.L"] @ q((0, 1, 0), -0.06)
        Q["thigh.R"] = Q["thigh.R"] @ q((0, 1, 0), 0.06)
        off["hips"] = V(0, 0, -0.015 + 0.004*b)

    def low_ready(qa, hp, Q, off, dz=0.0):
        c = hp["chest"]
        P = c + qa["chest"] @ V(-0.11, -0.25, -0.30 + dz)
        fwd = qa["chest"] @ V(0.35, -1.0, -0.55)
        up = qa["chest"] @ V(-0.25, 0, 1)
        return P, fwd, up

    def aim_pose(qa, hp, Q, off):
        c = hp["chest"]
        P = c + qa["chest"] @ V(-0.10, -0.28, 0.03)
        fwd = qa["chest"] @ V(0.06, -1.0, 0.0)
        up = qa["chest"] @ V(-0.05, 0, 1)
        return P, fwd, up

    def idle(t):
        Q, off = {}, {}
        base_stance(t, Q, off)
        Q["head"] = q((0, 0, 1), 0.08*math.sin(t*2*math.pi))
        qa, hp = chest_pos(Q, off)
        P, f, u = low_ready(qa, hp, Q, off, 0.006*math.sin(t*2*math.pi))
        hold(Q, off, P, f, u)
        return Q, off

    def walk_like(t, amp, knee_amp, bob, lean, armswing, run=False):
        Q, off = {}, {}
        ph = t*2*math.pi
        sL = amp*math.sin(ph); sR = -sL
        kL = 0.12 + knee_amp*max(0.0, math.cos(ph))**1.5
        kR = 0.12 + knee_amp*max(0.0, -math.cos(ph))**1.5
        legs(Q, sL, kL, "L"); legs(Q, sR, kR, "R")
        Q["hips"] = q((0, 0, 1), 0.07*math.sin(ph)) @ q((1, 0, 0), lean*0.4)
        Q["spine"] = q((0, 0, 1), -0.06*math.sin(ph)) @ q((1, 0, 0), lean*0.6)
        Q["chest"] = q((0, 0, 1), -0.03*math.sin(ph))
        off["hips"] = V(0, 0, -0.02 - (0.05 if run else 0.0) + bob*abs(math.cos(ph)))
        qa, hp = chest_pos(Q, off)
        if run:
            c = hp["chest"]
            P = c + qa["chest"] @ V(-0.12, -0.24, -0.20)
            f = qa["chest"] @ V(0.85, -0.6, 0.45)
            u = qa["chest"] @ V(-0.3, -0.3, 1)
        else:
            P, f, u = low_ready(qa, hp, Q, off, 0.01*math.sin(ph*2))
        hold(Q, off, P, f, u)
        return Q, off

    def aim(t):
        Q, off = {}, {}
        b = math.sin(t*2*math.pi)
        legs(Q, 0.28, 0.30, "L"); legs(Q, -0.18, 0.18, "R")
        Q["thigh.L"] = Q["thigh.L"] @ q((0, 1, 0), -0.08)
        Q["thigh.R"] = Q["thigh.R"] @ q((0, 1, 0), 0.10)
        Q["hips"] = q((0, 0, 1), 0.25)
        Q["spine"] = q((0, 0, 1), -0.12) @ q((1, 0, 0), 0.06 + 0.006*b)
        Q["chest"] = q((0, 0, 1), -0.12) @ q((1, 0, 0), 0.02)
        Q["head"] = q((0, 0, 1), -0.02) @ q((1, 0, 0), 0.05)
        off["hips"] = V(0, 0, -0.04)
        qa, hp = chest_pos(Q, off)
        P, f, u = aim_pose(qa, hp, Q, off)
        # weapon points straight ahead in world space regardless of the torso twist
        f = V(0.0, -1.0, 0.0); u = V(0, 0, 1)
        hold(Q, off, P, f, u)
        return Q, off

    def shoot(t):
        Q, off = aim(0.0)
        k = math.exp(-t*7.0)*min(1.0, t*12 + 0.3)
        qa, hp = chest_pos(Q, off)
        Q["chest"] = Q["chest"] @ q((1, 0, 0), -0.05*k)
        Q["head"] = Q["head"] @ q((1, 0, 0), -0.03*k)
        qa, hp = chest_pos(Q, off)
        P, f, u = aim_pose(qa, hp, Q, off)
        f = V(0.0, -1.0, 0.0); u = V(0, 0, 1)
        f = (f + V(0, 0, 0.22*k)).normalized()
        P = P + V(0, 0.045*k, 0.01*k)
        hold(Q, off, P, f, u)
        return Q, off

    def reload(t):
        Q, off = {}, {}
        base_stance(0.25, Q, off)
        Q["head"] = q((1, 0, 0), 0.25)
        qa, hp = chest_pos(Q, off)
        c = hp["chest"]
        tilt = math.sin(min(1.0, t/0.85)*math.pi)
        P = c + qa["chest"] @ V(-0.08, -0.30, -0.18)
        f = qa["chest"] @ V(0.3, -1.0, -0.15 - 0.10*tilt)
        u = qa["chest"] @ V(-0.4 - 0.6*tilt, 0, 1)
        qg = gun_frame(f, u)
        mag = P + qg @ V(0.0, -0.10, -0.16)
        pouch = hp["hips"] + V(0.14, -0.14, 0.05)
        # left hand: magwell -> pouch -> magwell -> foregrip
        if t < 0.15: lt = (P + qg @ V(0, -0.27, -0.03)).lerp(mag, t/0.15)
        elif t < 0.40: lt = mag.lerp(pouch, (t - 0.15)/0.25)
        elif t < 0.65: lt = pouch.lerp(mag, (t - 0.40)/0.25)
        elif t < 0.80: lt = mag
        else: lt = mag.lerp(P + qg @ V(0, -0.27, -0.03), (t - 0.80)/0.20)
        hold(Q, off, P, f, u, ltarget=lt)
        return Q, off

    def death(t):
        Q, off = {}, {}
        e = lambda a, b: max(0.0, min(1.0, (t - a)/(b - a)))
        s1 = e(0.0, 0.30); s1 = s1*s1*(3 - 2*s1)
        s2 = e(0.22, 0.75); s2 = s2*s2
        s3 = e(0.70, 0.85)
        bounce = math.sin(s3*math.pi)*0.03
        legs(Q, 0.5*s1 - 0.4*s2, 1.3*s1 - 1.0*s2, "L")
        legs(Q, 0.3*s1 - 0.25*s2, 1.0*s1 - 0.8*s2, "R")
        Q["hips"] = q((1, 0, 0), -1.50*s2) @ q((0, 0, 1), 0.3*s2)
        Q["spine"] = q((1, 0, 0), 0.35*s1 - 0.25*s2)
        Q["chest"] = q((1, 0, 0), 0.2*s1 - 0.15*s2)
        Q["head"] = q((1, 0, 0), 0.5*s1 - 0.7*s2) @ q((0, 0, 1), 0.5*s2)
        off["hips"] = V(0, 0.32*s2, -0.30*s1 - 0.53*s2 + bounce)
        # arms: let go and flop outwards
        Q["upperarm.R"] = q((0, 1, 0), -0.6*s1 - 0.9*s2) @ q((1, 0, 0), -0.8*s1 + 0.4*s2)
        Q["forearm.R"] = q((1, 0, 0), -0.9*s1 + 0.5*s2)
        Q["upperarm.L"] = q((0, 1, 0), 0.5*s1 + 0.8*s2) @ q((1, 0, 0), -0.5*s1 + 0.3*s2)
        Q["forearm.L"] = q((1, 0, 0), -0.7*s1 + 0.4*s2)
        Q["hand.R"] = q((0, 1, 0), 1.2)
        return Q, off

    rig.add_clip("idle", 60, idle)
    rig.add_clip("walk", 30, lambda t: walk_like(t, 0.42, 0.75, 0.025, 0.04, 0.0))
    rig.add_clip("run", 20, lambda t: walk_like(t, 0.75, 1.25, 0.05, 0.22, 0.0, run=True))
    rig.add_clip("aim", 30, aim)
    rig.add_clip("shoot", 9, shoot, loop=False)
    rig.add_clip("reload", 48, reload, loop=False)
    rig.add_clip("death", 36, death, loop=False)

# ============================================================ WEAPONS (built in socket space: origin = grip, forward -Y, up +Z)
def gun_mats(kind):
    if kind == "golden":
        return [material("gold", "gun_gold", rough=0.25, metal=1.0), material("gold_dark", "gun_gold", color=(0.55, 0.45, 0.25), rough=0.3, metal=1.0),
                material("gold_grip", "gun_grip", color=(0.9, 0.85, 0.8), rough=0.5), material("sight", None, color=(0.95, 0.95, 0.9), rough=0.4)]
    return [material("blued", "gun_blued", rough=0.35, metal=0.9), material("park", "gun_park", rough=0.55, metal=0.7),
            material("grip", "gun_grip" if kind != "kf7" else "gun_wood", rough=0.6), material("sight", None, color=(0.95, 0.95, 0.9), rough=0.4)]

def build_pistol(part, mats_base, bone_body="gun", bone_slide=None, bone_mag=None, silencer=False, xf=Matrix()):
    BL, PK, GR, SI = mats_base
    sb = bone_slide or bone_body; mb = bone_mag or bone_body
    # slide (flat-sided with bevels, front taper)
    part.add_bm(bm_box(0.027, 0.175, 0.034, bevel=0.0035, seg=2), BL, xf @ T(0, -0.050, 0.043), bone=sb, uvs=6)
    for i in range(7):   # rear serrations
        part.add_bm(bm_box(0.0285, 0.0022, 0.022, bevel=0.0), PK, xf @ T(0, 0.022 - i*0.0055, 0.042), bone=sb)
    part.add_bm(bm_box(0.004, 0.030, 0.013, bevel=0.001), PK, xf @ T(-0.0125, -0.04, 0.050), bone=sb)  # ejection port
    part.add_bm(bm_box(0.006, 0.006, 0.007, bevel=0.001), SI, xf @ T(0, -0.128, 0.0625), bone=sb)    # front sight
    part.add_bm(bm_box(0.020, 0.008, 0.008, bevel=0.001), PK, xf @ T(0, 0.025, 0.063), bone=sb)      # rear sight
    for sx in (-0.006, 0.006):
        part.add_bm(bm_box(0.003, 0.003, 0.003), SI, xf @ T(sx, 0.0205, 0.0645), bone=sb)
    # barrel / muzzle
    part.add_bm(bm_cyl(0.0065, 0.0065, 0.012, 16), PK, xf @ T(0, -0.140, 0.046) @ RX(math.pi/2), bone=sb)
    part.add_bm(bm_cyl(0.0042, 0.0042, 0.013, 12), mats_base[0], xf @ T(0, -0.1405, 0.046) @ RX(math.pi/2), bone=sb)
    # frame + dust cover rail
    part.add_bm(bm_box(0.025, 0.135, 0.020, bevel=0.003), PK, xf @ T(0, -0.045, 0.017), bone=bone_body, uvs=6)
    # trigger guard
    tg = bm_loft([rect(0, y, z, 0.004, 0.003) for y, z in ((-0.040, 0.008), (-0.050, -0.010), (-0.038, -0.024), (-0.012, -0.026), (0.004, -0.012))], cap=True)
    part.add_bm(tg, PK, xf, bone=bone_body)
    part.add_bm(bm_box(0.006, 0.006, 0.020, bevel=0.002), BL, xf @ T(0, -0.020, -0.006) @ RX(-0.25), bone=bone_body)  # trigger
    # grip (raked)
    g = xf @ T(0, 0.020, -0.045) @ RX(-0.30)
    part.add_bm(bm_box(0.029, 0.040, 0.095, bevel=0.006, seg=3), GR, g, bone=bone_body,
                uvfunc=lambda p, n, l: ((p.y*9 if abs(n.x) > 0.5 else p.x*9), p.z*9))
    part.add_bm(bm_box(0.031, 0.030, 0.008, bevel=0.002), PK, g @ T(0, 0.004, 0.040), bone=bone_body)
    part.add_bm(bm_box(0.010, 0.010, 0.012, bevel=0.002), BL, xf @ T(0, 0.040, 0.050) @ RX(0.5), bone=bone_body)  # hammer
    part.add_bm(bm_box(0.006, 0.030, 0.006, bevel=0.002), BL, xf @ T(0.014, -0.010, 0.030), bone=bone_body)       # slide stop
    # magazine (mostly inside the grip, baseplate visible)
    part.add_bm(bm_box(0.022, 0.032, 0.090, bevel=0.002), BL, g @ T(0, 0.0, -0.008), bone=mb)
    part.add_bm(bm_box(0.030, 0.043, 0.010, bevel=0.003), PK, g @ T(0, 0.0, -0.052), bone=mb)
    if silencer:
        part.add_bm(bm_cyl(0.0145, 0.0145, 0.145, 24), PK, xf @ T(0, -0.215, 0.046) @ RX(math.pi/2), bone=sb, smooth=True)
        for k in range(5):
            part.add_bm(bm_cyl(0.0152, 0.0152, 0.004, 24), BL, xf @ T(0, -0.16 - k*0.025, 0.046) @ RX(math.pi/2), bone=sb)
        part.add_bm(bm_cyl(0.005, 0.005, 0.004, 12), SI, xf @ T(0, -0.288, 0.046) @ RX(math.pi/2), bone=sb)

def build_rifle(part, mats_base, bone_body="gun", bone_mag=None, bone_bolt=None, xf=Matrix(), wood=None):
    BL, PK, GR, SI = mats_base
    WD = wood if wood is not None else GR
    mb = bone_mag or bone_body; bb = bone_bolt or bone_body
    part.add_bm(bm_box(0.046, 0.33, 0.070, bevel=0.006), PK, xf @ T(0, -0.055, 0.070), bone=bone_body, uvs=5)      # receiver
    cover = bm_cyl(0.023, 0.023, 0.29, 20)
    part.add_bm(cover, BL, xf @ T(0, -0.065, 0.104) @ RX(math.pi/2) @ S(1, 1, 1), bone=bone_body, uvs=5)          # top cover
    part.add_bm(bm_box(0.012, 0.03, 0.012, bevel=0.003), BL, xf @ T(-0.030, -0.12, 0.088), bone=bb)               # charging handle
    part.add_bm(bm_box(0.004, 0.11, 0.022, bevel=0.002), BL, xf @ T(-0.024, -0.02, 0.070), bone=bone_body)        # selector
    part.add_bm(bm_box(0.020, 0.030, 0.020, bevel=0.004), BL, xf @ T(0, -0.10, 0.126), bone=bone_body)            # rear sight base
    part.add_bm(bm_box(0.010, 0.020, 0.008, bevel=0.002), SI, xf @ T(0, -0.10, 0.138), bone=bone_body)
    # handguards (lower + upper) in wood
    lg = bm_loft([rect(0, y, 0.066, w, h) for y, w, h in ((-0.215, 0.027, 0.028), (-0.30, 0.026, 0.026), (-0.415, 0.024, 0.024))])
    bmesh.ops.bevel(lg, geom=list(lg.edges), offset=0.008, segments=3, affect="EDGES", profile=0.5)
    part.add_bm(lg, WD, xf, bone=bone_body, uvfunc=lambda p, n, l: (p.y*3, (p.z if abs(n.x) > 0.5 else p.x)*6))
    ug = bm_loft([rect(0, y, 0.106, w, 0.011) for y, w in ((-0.235, 0.019), (-0.39, 0.017))])
    bmesh.ops.bevel(ug, geom=list(ug.edges), offset=0.006, segments=2, affect="EDGES", profile=0.5)
    part.add_bm(ug, WD, xf, bone=bone_body, uvfunc=lambda p, n, l: (p.y*3, p.x*6))
    part.add_bm(bm_box(0.05, 0.012, 0.075, bevel=0.003), BL, xf @ T(0, -0.215, 0.080), bone=bone_body)           # handguard retainer
    part.add_bm(bm_cyl(0.0095, 0.0095, 0.25, 16), BL, xf @ T(0, -0.53, 0.072) @ RX(math.pi/2), bone=bone_body)      # barrel
    part.add_bm(bm_cyl(0.0105, 0.0105, 0.13, 16), PK, xf @ T(0, -0.46, 0.100) @ RX(math.pi/2), bone=bone_body)      # gas tube
    part.add_bm(bm_box(0.022, 0.026, 0.046, bevel=0.004), PK, xf @ T(0, -0.53, 0.088), bone=bone_body)             # gas block
    part.add_bm(bm_box(0.018, 0.018, 0.035, bevel=0.003), PK, xf @ T(0, -0.62, 0.090), bone=bone_body)             # front sight block
    part.add_bm(bm_cyl(0.011, 0.011, 0.008, 16, caps=False), PK, xf @ T(0, -0.62, 0.118) @ RX(math.pi/2), bone=bone_body)
    part.add_bm(bm_box(0.003, 0.003, 0.014), SI, xf @ T(0, -0.62, 0.118), bone=bone_body)
    mz = bm_cyl(0.014, 0.0125, 0.055, 16)
    part.add_bm(mz, BL, xf @ T(0, -0.675, 0.072) @ RX(math.pi/2), bone=bone_body)                                  # muzzle brake
    for k in range(3):
        part.add_bm(bm_box(0.031, 0.006, 0.006), PK, xf @ T(0, -0.660 - k*0.013, 0.072), bone=bone_body)
    # pistol grip
    g = xf @ T(0, 0.025, -0.020) @ RX(-0.35)
    part.add_bm(bm_box(0.030, 0.042, 0.105, bevel=0.008, seg=3), GR, g, bone=bone_body, uvfunc=lambda p, n, l: (p.y*8, p.z*8))
    tg = bm_loft([rect(0, y, z, 0.004, 0.003) for y, z in ((-0.058, 0.040), (-0.062, 0.010), (-0.045, -0.002), (-0.005, 0.000), (0.012, 0.036))])
    part.add_bm(tg, PK, xf, bone=bone_body)
    part.add_bm(bm_box(0.006, 0.006, 0.022, bevel=0.002), BL, xf @ T(0, -0.025, 0.020) @ RX(-0.2), bone=bone_body)
    # stock (wood, dropped comb)
    st = bm_loft([rect(0, y, z, w, h) for y, z, w, h in ((0.105, 0.072, 0.022, 0.035), (0.20, 0.052, 0.020, 0.045), (0.36, 0.035, 0.021, 0.060))])
    bmesh.ops.bevel(st, geom=list(st.edges), offset=0.010, segments=3, affect="EDGES", profile=0.5)
    part.add_bm(st, WD, xf, bone=bone_body, uvfunc=lambda p, n, l: (p.y*3, (p.z if abs(n.x) > 0.5 else p.x)*6))
    part.add_bm(bm_box(0.045, 0.012, 0.125, bevel=0.004), PK, xf @ T(0, 0.366, 0.035), bone=bone_body)            # butt plate
    # curved magazine (loft along an arc)
    secs = []
    cl = []
    for i in range(8):
        s_ = i/7
        cl.append((-0.090 - 0.075*s_*s_, 0.040 - 0.215*s_))
    for i, (cy, cz) in enumerate(cl):
        j0, j1 = max(0, i - 1), min(len(cl) - 1, i + 1)
        ty, tz = cl[j1][0] - cl[j0][0], cl[j1][1] - cl[j0][1]
        L_ = math.hypot(ty, tz); ty, tz = ty/L_, tz/L_
        ny, nz = tz, -ty            # perpendicular in the y/z plane
        if ny > 0: ny, nz = -ny, -nz
        hw = 0.030 + 0.004*(i/7)
        secs.append([V(sx*0.0135, cy + d*ny*hw, cz + d*nz*hw) for sx, d in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    mag = bm_loft(secs)
    bmesh.ops.bevel(mag, geom=list(mag.edges), offset=0.004, segments=2, affect="EDGES", profile=0.5)
    part.add_bm(mag, BL, xf, bone=mb, uvs=6)
    part.add_bm(bm_box(0.032, 0.07, 0.012, bevel=0.003), PK, xf @ T(0, secs[-1][0].y + 0.0, secs[-1][0].z - 0.004) @ RX(0.45), bone=mb)

def build_world_weapon(name, kind):
    reset()
    part = Part()
    mats = gun_mats(kind if kind == "golden" else ("kf7" if kind == "kf7" else "pp7"))
    wood = None
    if kind == "kf7":
        mats.append(material("wood", "gun_wood", rough=0.5)); wood = 4
    if kind == "kf7": build_rifle(part, (0, 1, 2, 3), bone_body=None, wood=wood)
    else: build_pistol(part, (0, 1, 2, 3), bone_body=None, silencer=(kind == "pp7s"))
    ob = part.build(name, mats)
    export(os.path.join(OUT, name + ".glb"), [ob])

# ============================================================ VIEWMODELS (camera space: eye at origin, forward -Y, up +Z, right = -X)
def build_viewmodel(name, kind):
    reset()
    rifle = kind == "kf7"
    # weapon socket rest position
    P = V(-0.15, -0.50, -0.185) if rifle else V(-0.15, -0.40, -0.125)
    shR = V(-0.20, 0.10, -0.28) if not rifle else V(-0.21, -0.02, -0.30)
    shL = V(0.21, 0.06, -0.30) if not rifle else V(0.20, -0.06, -0.32)
    # rest wrists
    wR = P + V(0.0, 0.075, -0.035)
    fg = P + V(0.0, -0.27, -0.03)
    wL = (fg + V(0.035, 0.05, -0.035)) if rifle else V(0.12, -0.20, -0.42)
    def elbow(s, w, pole, a=0.29, b=0.265):
        d = w - s; L = d.length; dn = d.normalized()
        L = min(L, a + b - 1e-3)
        pn = (pole - dn*pole.dot(dn)).normalized()
        ca = (a*a + L*L - b*b)/(2*a*L); sa = math.sqrt(max(0, 1 - ca*ca))
        return s + dn*a*ca + pn*a*sa, s + dn*L
    eR, wR = elbow(shR, wR, V(-0.8, 0.3, -0.6))
    eL, wL = elbow(shL, wL, V(0.8, 0.3, -0.6))
    hR = P + V(0, -0.03, 0.0)
    hL = fg + V(0, -0.02, 0.01) if rifle else wL + (wL - eL).normalized()*0.12
    bones = [("root", V(0, 0, -0.5), V(0, 0, -0.4), None),
             ("upperarm.R", shR, eR, "root"), ("forearm.R", eR, wR, "upperarm.R"), ("hand.R", wR, hR, "forearm.R"),
             ("gun", P, P + V(0, -0.2, 0), "hand.R"),
             ("slide", P + V(0, 0, 0.045), P + V(0, -0.1, 0.045), "gun"),
             ("mag", P + V(0, 0, -0.04), P + V(0, 0, -0.14), "gun"),
             ("upperarm.L", shL, eL, "root"), ("forearm.L", eL, wL, "upperarm.L"), ("hand.L", wL, hL, "forearm.L")]
    rig = Rig(name + "_rig", bones)
    mats = gun_mats("golden" if kind == "golden" else ("kf7" if rifle else "pp7"))
    wood = None
    if rifle: mats.append(material("wood", "gun_wood", rough=0.5)); wood = len(mats) - 1
    SLEEVE = len(mats); mats.append(material("sleeve", "ch_charcoal", rough=0.8))
    CUFF = len(mats); mats.append(material("cuff", "ch_white", rough=0.7))
    SKIN = len(mats); mats.append(material("skin", "ch_skin_a", rough=0.5))
    part = Part()
    if rifle: build_rifle(part, (0, 1, 2, 3), "gun", bone_mag="mag", bone_bolt="slide", xf=T(*P), wood=wood)
    else: build_pistol(part, (0, 1, 2, 3), "gun", bone_slide="slide", bone_mag="mag", silencer=(kind == "pp7s"), xf=T(*P))
    # arms: tapered sleeves (loft along the bones) + cuffs + hands
    def tube(a, b, r1, r2, mat, bones_w, n=14, rings=6, flare=0.0):
        d = (b - a); L = d.length; dn = d.normalized()
        up = V(0, 0, 1) if abs(dn.z) < 0.9 else V(1, 0, 0)
        x = dn.cross(up).normalized(); y = dn.cross(x).normalized()
        secs = []
        for k in range(rings + 1):
            t = k/rings; r = r1 + (r2 - r1)*t + flare*math.sin(t*math.pi)
            c = a + d*t
            secs.append([c + (x*math.cos(i/n*2*math.pi)*r) + (y*math.sin(i/n*2*math.pi)*r*0.9) for i in range(n)])
        bm = bm_loft(secs, cap=False)
        part.add_bm(bm, mat, weights=bones_w, uvs=6)
    for s, sh, el, wr in (("R", shR, eR, wR), ("L", shL, eL, wL)):
        wfn = capsule_weights(rig, ["upperarm." + s, "forearm." + s, "hand." + s], blend=0.06)
        tube(sh, el, 0.058, 0.050, SLEEVE, wfn, flare=0.006)
        tube(el - (el - sh).normalized()*0.02, wr - (wr - el).normalized()*0.02, 0.050, 0.043, SLEEVE, wfn, flare=0.004)
        cdir = (wr - el).normalized()
        tube(wr - cdir*0.035, wr - cdir*0.005, 0.039, 0.037, CUFF, lambda p, s=s: [("forearm." + s, 1.0)])
        tube(wr - cdir*0.04, wr + cdir*0.012, 0.024, 0.026, SKIN, lambda p, s=s: [("hand." + s, 1.0)], n=12, rings=2)
    # right hand wrapped round the grip (socket space -> world via xf)
    def hand(xf, bone, mirror=1, curl=1.0):
        part.add_bm(bm_box(0.030, 0.050, 0.075, bevel=0.012, seg=3), SKIN, xf @ T(mirror*0.010, 0.030, -0.045), bone=bone, uvs=8)  # palm (back/right of the grip)
        for i in range(4):
            z = -0.012 - i*0.020
            base = xf @ T(mirror*0.018, 0.010, z)
            for j, (L, ang) in enumerate(((0.030, 0.0), (0.024, 1.2*curl), (0.020, 2.2*curl))):
                pass
            # fingers: three phalanges wrapping round the front of the grip
            pts = [V(mirror*0.019, 0.022, z), V(mirror*0.020, -0.010, z), V(mirror*0.004, -0.030, z), V(-mirror*0.016, -0.018, z)]
            for a, b in zip(pts[:-1], pts[1:]):
                d = (b - a); m = (a + b)*0.5
                rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
                part.add_bm(bm_cyl(0.0095, 0.0085, d.length + 0.010, 10), SKIN, xf @ T(*m) @ rot, bone=bone, smooth=True)
        # thumb along the side
        pts = [V(-mirror*0.017, 0.030, -0.012), V(-mirror*0.019, 0.008, -0.004), V(-mirror*0.018, -0.010, 0.000)]
        for a, b in zip(pts[:-1], pts[1:]):
            d = (b - a); m = (a + b)*0.5
            rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
            part.add_bm(bm_cyl(0.0095, 0.008, d.length + 0.008, 10), SKIN, xf @ T(*m) @ rot, bone=bone, smooth=True)
    hand(T(*P) @ T(0, 0.022, -0.002 if rifle else -0.016) @ RX(-0.32), "hand.R", mirror=-1)
    if rifle:
        hand(T(*fg) @ T(0, 0.0, -0.01) @ RX(0.25), "hand.L", mirror=1)
    else:
        d = (hL - wL).normalized()
        rot = d.to_track_quat("-Y", "Z").to_matrix().to_4x4()
        hand(T(*(wL + d*0.07)) @ rot, "hand.L", mirror=1)
    ob = part.build(name, mats, rig.ob, [b[0] for b in bones])
    vm_clips(rig, rifle, P, fg)
    export(os.path.join(OUT, name + ".glb"), [rig.ob, ob])

def vm_clips(rig, rifle, P0, fg0):
    gun_rest = rig.R["gun"]
    off_gun = rig.head["gun"] - rig.head["hand.R"]
    restL = rig.head["hand.L"]
    def q(ax, a): return Quaternion(Vector(ax), a)
    def place(Q, off, P, qg, ltarget=None, lwrist=None):
        wrist = P - qg @ off_gun
        qf = rig.ik2(Q, off, "upperarm.R", "forearm.R", wrist, V(-0.8, 0.3, -0.6))
        Q["hand.R"] = qf.inverted() @ qg
        if ltarget is not None:
            qfl = rig.ik2(Q, off, "upperarm.L", "forearm.L", ltarget, V(0.8, 0.3, -0.6))
            Q["hand.L"] = qfl.inverted() @ qg
    def lwrist_on_grip(P, qg):
        return P + qg @ (rig.head["hand.L"] - rig.head["gun"])
    def idle(t):
        Q, off = {}, {}
        ph = t*2*math.pi
        P = P0 + V(0.002*math.sin(ph), 0, 0.003*math.sin(ph*2))
        qg = q((1, 0, 0), 0.01*math.sin(ph))
        place(Q, off, P, qg, lwrist_on_grip(P, qg) if rifle else rig.head["hand.L"])
        return Q, off
    def shoot(t):
        Q, off = {}, {}
        k = math.exp(-t*6.0)*min(1.0, t*10 + 0.25)
        P = P0 + V(0, 0.035*k, 0.012*k)
        qg = q((1, 0, 0), (0.10 if rifle else 0.22)*k)
        # slide/bolt travel (0..1 over the first 40%)
        sk = max(0.0, 1 - abs(t - 0.12)/0.12) if t < 0.30 else 0.0
        off["slide"] = V(0, 0.030*sk if not rifle else 0.06*sk, 0)
        place(Q, off, P, qg, lwrist_on_grip(P, qg) if rifle else rig.head["hand.L"])
        return Q, off
    def reload(t):
        Q, off = {}, {}
        e = lambda a, b: max(0.0, min(1.0, (t - a)/(b - a)))
        sm = lambda x: x*x*(3 - 2*x)
        tilt = sm(e(0.0, 0.18)) - sm(e(0.82, 1.0))
        P = P0 + V(0.02*tilt, 0.04*tilt, -0.05*tilt)
        qg = q((0, 1, 0), (0.5 if rifle else -0.35)*tilt) @ q((1, 0, 0), 0.25*tilt)
        # magazine out (drop), back in
        out = sm(e(0.18, 0.35)); back = sm(e(0.55, 0.75))
        drop = out*(1 - back)
        off["mag"] = V(0, -0.02*drop if rifle else 0.0, -0.22*drop)
        # left hand comes to the magwell with the fresh mag
        magw = P + qg @ (rig.head["mag"] - rig.head["gun"] + V(0, -0.0, -0.05))
        low = V(0.10, -0.25, -0.50)
        if rifle:
            grip = lwrist_on_grip(P, qg)
            if t < 0.20: lt = grip.lerp(magw, sm(e(0.05, 0.20)))
            elif t < 0.45: lt = magw.lerp(low, sm(e(0.20, 0.42)))
            elif t < 0.75: lt = low.lerp(magw, sm(e(0.45, 0.70)))
            else: lt = magw.lerp(grip, sm(e(0.75, 0.92)))
            # mag rides with the left hand between out and in
        else:
            rest = rig.head["hand.L"]
            if t < 0.35: lt = rest
            elif t < 0.60: lt = rest.lerp(magw, sm(e(0.35, 0.58)))
            elif t < 0.80: lt = magw
            else: lt = magw.lerp(rest, sm(e(0.80, 1.0)))
            sl = sm(e(0.78, 0.84)) - sm(e(0.86, 0.90))
            off["slide"] = V(0, 0.03*sl, 0)
        if rifle:
            sl = sm(e(0.80, 0.86)) - sm(e(0.88, 0.93))
            off["slide"] = V(0, 0.07*sl, 0)
        place(Q, off, P, qg, lt)
        return Q, off
    rig.add_clip("idle", 60, idle)
    rig.add_clip("shoot", 8, shoot, loop=False)
    rig.add_clip("reload", 45 if rifle else 36, reload, loop=False)

# ============================================================ PROPS (y-up conversion done by exporter; Blender Z = height)
def uv_cyl(p, n, l, h=1.0):
    a = math.atan2(p.y, p.x)/(2*math.pi) + 0.5
    return (a*2.0, p.z/h)

def build_crate(name):
    reset(); part = Part()
    mats = [material("crate", "pr_crate", rough=0.8), material("metal", "pr_darkmetal", rough=0.4, metal=0.8)]
    s = 1.1
    b = bm_box(s, s, s, bevel=0.012, seg=2)
    def uvf(p, n, l):
        ax = max(range(3), key=lambda k: abs(n[k]))
        if ax == 0: return (p.y/s + 0.5, p.z/s)
        if ax == 1: return (p.x/s + 0.5, p.z/s)
        return (p.x/s + 0.5, p.y/s + 0.5)
    part.add_bm(b, 0, T(0, 0, s/2), uvfunc=uvf)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (0, 1):
                part.add_bm(bm_box(0.14, 0.14, 0.14, bevel=0.01), 1, T(sx*(s/2 - 0.06), sy*(s/2 - 0.06), 0.06 + sz*(s - 0.12)), uvs=4)
    ob = part.build(name, mats); export(os.path.join(OUT, name + ".glb"), [ob])

def build_barrel(name):
    reset(); part = Part()
    mats = [material("drum", "pr_barrel", rough=0.45, metal=0.6), material("lid", "pr_barrel_top", rough=0.45, metal=0.6), material("rim", "pr_metal", rough=0.35, metal=0.9)]
    H = 1.15; R = 0.37
    secs = []
    prof = [(0.0, 0.36), (0.02, R), (0.36, R), (0.37, R + 0.018), (0.39, R + 0.018), (0.40, R), (0.75, R), (0.76, R + 0.018), (0.78, R + 0.018), (0.79, R), (1.13, R), (1.15, 0.36)]
    n = 28
    for z, r in prof:
        secs.append([V(math.cos(i/n*2*math.pi)*r, math.sin(i/n*2*math.pi)*r, z) for i in range(n)])
    bm = bm_loft(secs, cap=False)
    part.add_bm(bm, 0, uvfunc=lambda p, nn, l: uv_cyl(p, nn, l, H))
    lid = bm_cyl(0.36, 0.36, 0.01, n)
    part.add_bm(lid, 1, T(0, 0, H - 0.012), uvfunc=lambda p, nn, l: (p.x/0.72 + 0.5, p.y/0.72 + 0.5))
    rim = bm_cyl(0.375, 0.375, 0.03, n, caps=False)
    part.add_bm(rim, 2, T(0, 0, H - 0.005), uvs=4)
    part.add_bm(bm_cyl(0.04, 0.04, 0.02, 12), 2, T(0.2, 0, H), uvs=4)
    ob = part.build(name, mats); export(os.path.join(OUT, name + ".glb"), [ob])

def build_desk(name):
    """desk: 1.7 x 0.85, top at 0.78. Monitor at local x -0.25 facing +Z(game) -> Blender -Y"""
    reset(); part = Part()
    mats = [material("top", "pr_desk_top", rough=0.6), material("steel", "pr_metal", rough=0.4, metal=0.8),
            material("beige", "pr_beige", rough=0.6), material("screen", "pr_screen", rough=0.2, emissive=True),
            material("keys", "pr_keyboard", rough=0.6), material("dark", "pr_darkmetal", rough=0.5)]
    # game axes: x = x, game z = -Blender y (exporter: blender (x,y,z) -> gltf (x,z,-y))
    part.add_bm(bm_box(1.7, 0.85, 0.05, bevel=0.01), 0, T(0, 0, 0.755), uvs=1.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            part.add_bm(bm_box(0.05, 0.05, 0.73, bevel=0.008), 1, T(sx*0.79, sy*0.37, 0.365), uvs=4)
    part.add_bm(bm_box(1.5, 0.025, 0.45, bevel=0.005), 5, T(0, 0.37, 0.47), uvs=3)                       # modesty panel (game -z side)
    part.add_bm(bm_box(0.45, 0.72, 0.70, bevel=0.01), 1, T(0.50, 0, 0.36), uvs=3)                       # drawer unit
    for k in range(3):
        part.add_bm(bm_box(0.41, 0.012, 0.20, bevel=0.004), 5, T(0.50, -0.362, 0.13 + k*0.225), uvs=3)
        part.add_bm(bm_box(0.12, 0.02, 0.018, bevel=0.005), 1, T(0.50, -0.375, 0.20 + k*0.225), uvs=4)
    # CRT monitor (original chunky design)
    mx, my = -0.25, 0.12      # game z = -0.12 -> blender y = +0.12
    part.add_bm(bm_box(0.30, 0.25, 0.04, bevel=0.01), 2, T(mx, my, 0.80), uvs=3)                       # foot
    part.add_bm(bm_box(0.10, 0.10, 0.06, bevel=0.01), 2, T(mx, my, 0.84), uvs=3)
    body = bm_loft([rect(mx, y, 1.04, w, h) for y, w, h in ((my - 0.20, 0.25, 0.21), (my + 0.02, 0.24, 0.20), (my + 0.26, 0.15, 0.13))])
    bmesh.ops.bevel(body, geom=list(body.edges), offset=0.02, segments=3, affect="EDGES", profile=0.5)
    part.add_bm(body, 2, uvs=3)
    # bezel + screen on the front (blender -y)
    part.add_bm(bm_box(0.44, 0.015, 0.36, bevel=0.008), 2, T(mx, my - 0.205, 1.04), uvs=3)
    scr = bmesh.new()
    vs = [scr.verts.new(V(mx + x, my - 0.2135, 1.04 + z)) for x, z in ((-0.185, -0.145), (0.185, -0.145), (0.185, 0.145), (-0.185, 0.145))]
    scr.faces.new(vs)
    part.add_bm(scr, 3, uvfunc=lambda p, n, l: ((p.x - mx + 0.185)/0.37, (p.z - 1.04 + 0.145)/0.29))
    part.add_bm(bm_box(0.012, 0.006, 0.012), 5, T(mx + 0.17, my - 0.214, 0.885), uvs=3)
    # keyboard (game z +0.28 -> blender y -0.28)
    kb = bm_box(0.48, 0.17, 0.025, bevel=0.006)
    part.add_bm(kb, 4, T(-0.2, -0.28, 0.795) @ RX(0.06), uvfunc=lambda p, n, l: ((p.x + 0.44)/0.48, (p.y + 0.365)/0.17) if n.z > 0.5 else (0.02, 0.02))
    # paper stack + mug
    part.add_bm(bm_box(0.22, 0.30, 0.02, bevel=0.002), 2, T(0.45, -0.10, 0.79) @ RZ(0.2), uvs=1)
    part.add_bm(bm_cyl(0.04, 0.04, 0.10, 16), 5, T(0.62, 0.15, 0.83), uvs=4)
    ob = part.build(name, mats); export(os.path.join(OUT, name + ".glb"), [ob])

def build_rack(name):
    """server rack 1.1 x 0.8 x 2.2; front panel faces game +Z (blender -Y). The game rotates it to face the room."""
    reset(); part = Part()
    mats = [material("body", "pr_darkmetal", rough=0.45, metal=0.7), material("front", "pr_rack", rough=0.4, metal=0.3, emissive=False),
            material("handle", "pr_metal", rough=0.3, metal=0.9)]
    part.add_bm(bm_box(1.1, 0.8, 2.2, bevel=0.02), 0, T(0, 0, 1.1), uvs=1.5)
    fr = bmesh.new()
    vs = [fr.verts.new(V(x, -0.402, z)) for x, z in ((-0.5, 0.1), (0.5, 0.1), (0.5, 2.1), (-0.5, 2.1))]
    fr.faces.new(vs)
    part.add_bm(fr, 1, uvfunc=lambda p, n, l: (p.x + 0.5, (p.z - 0.1)/2.0))
    part.add_bm(bm_box(0.03, 0.04, 0.5, bevel=0.01), 2, T(0.46, -0.43, 1.1), uvs=4)
    part.add_bm(bm_box(1.14, 0.84, 0.04, bevel=0.01), 0, T(0, 0, 2.2), uvs=1.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            part.add_bm(bm_cyl(0.03, 0.03, 0.04, 10), 2, T(sx*0.48, sy*0.33, 0.02), uvs=4)
    ob = part.build(name, mats); export(os.path.join(OUT, name + ".glb"), [ob])

# ============================================================ outfits
STYLES = {
    "guard_soldier": dict(top="ch_camo", legs="ch_camo", skin="ch_skin_a", face="face_soldier", vest="ch_vest_olive",
                          hat="helmet", hat_tex="ch_helmet", gloves=False, rolled=False, bulk=1.04),
    "guard_cap": dict(top="ch_bluegrey", legs="ch_navy", skin="ch_skin_b", face="face_guard", hat="cap", hat_tex="ch_cap",
                      rolled=True, holster=True, epaulettes=True, collar=True),
    "commando": dict(top="ch_black", legs="ch_black", skin="ch_skin_c", face="face_commando", vest="ch_vest_black",
                     hat="beanie", hat_tex="ch_knit", gloves=True, hands="ch_leather", neck_cover=True, bulk=1.06),
    "agent1": dict(top="ch_charcoal", legs="ch_charcoal", skin="ch_skin_a", face="face_agent1", shirt="ch_white", tie="ch_tie_dark",
                   hair_tex="ch_hair_dark"),
    "agent2": dict(top="ch_tan", legs="ch_tan", skin="ch_skin_c", face="face_agent2", shirt="ch_white", tie="ch_tie_red",
                   hair_tex="ch_hair_fair"),
}

if __name__ == "__main__":
    want = lambda n: ONLY is None or n in ONLY
    for n, st in STYLES.items():
        if want(n):
            print("humanoid", n); build_humanoid(n, st)
    for n, k in (("w_kf7", "kf7"), ("w_pp7", "pp7"), ("w_pp7s", "pp7s"), ("w_golden", "golden")):
        if want(n): build_world_weapon(n, k)
    for n, k in (("vm_pp7", "pp7"), ("vm_pp7s", "pp7s"), ("vm_kf7", "kf7"), ("vm_golden", "golden")):
        if want(n): print("viewmodel", n); build_viewmodel(n, k)
    if want("prop_crate"): build_crate("prop_crate")
    if want("prop_barrel"): build_barrel("prop_barrel")
    if want("prop_desk"): build_desk("prop_desk")
    if want("prop_rack"): build_rack("prop_rack")
    print("done")
