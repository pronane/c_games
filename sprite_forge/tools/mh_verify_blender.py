"""Verify Sprite Forge's MakeHuman characters against MakeHuman's own code in Blender (MPFB2), and render them there.

    python3 tools/mh_verify_blender.py --squad ../Gaelic_Football_3d/assets/source/squad.txt --out /tmp/verify

For every look (an appearance block, the same keys as the Studio sliders):
  1. Sprite Forge turns the look into MakeHuman target weights + asset choices (sforge.appearance) and morphs the CC0
     base mesh itself (sforge.mhlib / sforge.mhchar).
  2. Blender builds the same human with MPFB2 (MakeHuman for Blender, HumanService.deserialize_from_dict).
  3. Body: MPFB's feature delta (human with the targets minus the same human without them) is compared vertex by
     vertex with Forge's delta.  Assets (hair, eyebrows, eyelashes, eyes): Forge's .mhclo fitting is run on MPFB's
     morphed body and compared with the meshes MPFB fitted.
  4. Cycles renders a portrait of MPFB's human (skin, hair, brows, lashes, eyes from MakeHuman's own materials).
Writes verify.json and blender_<n>.png.  Needs Blender as a Python module (pip install bpy) with MPFB2 installed
(tools/mh_install_mpfb.py) and the MakeHuman library (forge.py human --setup --full)."""
from __future__ import annotations
import argparse, json, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import bpy, addon_utils                                   # noqa: E402
from mathutils import Vector                              # noqa: E402
from sforge import mhlib                                  # noqa: E402
from gaelic_squad import read_squad                       # noqa: E402

EXT = "bl_ext.user_default.mpfb"


def enable_mpfb():
    bpy.ops.wm.read_userpref()
    if EXT not in bpy.context.preferences.addons:
        addon_utils.enable(EXT, default_set=True)
    if EXT not in bpy.context.preferences.addons:
        raise RuntimeError("MPFB2 is not installed in this Blender (run tools/mh_install_mpfb.py)")
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    return HumanService


def ensure_assets(pack_zip):
    from bl_ext.user_default.mpfb.services.locationservice import LocationService
    ud = LocationService.get_user_data()
    if not os.path.isdir(os.path.join(ud, "hair")) and pack_zip:
        bpy.ops.mpfb.load_pack(filepath=pack_zip)


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)


def shape_coords(ob):
    """mixed shape-key coordinates of the basemesh (all 19,158 vertices, helpers included) in Blender space"""
    me = ob.data
    n = len(me.vertices)
    keys = me.shape_keys.key_blocks if me.shape_keys else []
    if not keys:
        co = np.zeros(n * 3); me.vertices.foreach_get("co", co); return co.reshape(n, 3)
    basis = np.zeros(n * 3); keys[0].data.foreach_get("co", basis); basis = basis.reshape(n, 3)
    out = basis.copy()
    for k in keys[1:]:
        if k.value == 0 or k.mute:
            continue
        c = np.zeros(n * 3); k.data.foreach_get("co", c)
        out += k.value * (c.reshape(n, 3) - basis)
    return out


def to_mh(P):
    """Blender (Z up, metres) -> MakeHuman base space (Y up, decimetres)"""
    return np.stack([P[:, 0], P[:, 2], -P[:, 1]], 1) / 0.1


def build(HS, info):
    clear()
    st = HS.get_default_deserialization_settings(); st["subdiv_levels"] = 0
    bm = HS.deserialize_from_dict(info, st)
    parts = {}
    for o in bpy.data.objects:
        if o.type == "MESH" and o is not bm:
            parts[o.name.split(".", 1)[-1].lower()] = o          # MPFB names fitted assets "<human>.<asset name>"
    return bm, parts


def chamfer(A, B):
    from scipy.spatial import cKDTree
    d1, _ = cKDTree(B).query(A)
    return float(d1.mean()), float(np.percentile(d1, 99)), float(d1.max())


def portrait(path, bm):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.samples = 40; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
    sc.render.resolution_x = sc.render.resolution_y = 420
    if sc.world is None:
        sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (0.36, 0.52, 0.30, 1); bg.inputs["Strength"].default_value = 0.9
    for name, rot, e, c in (("key", (50, 0, 35), 3.4, (1, 0.96, 0.9)), ("rim", (70, 0, -140), 2.2, (0.7, 0.8, 1.0))):
        L = bpy.data.lights.new(name, "SUN"); L.energy = e; L.color = c; L.angle = math.radians(5)
        o = bpy.data.objects.new(name, L); bpy.context.collection.objects.link(o); o.rotation_euler = [math.radians(a) for a in rot]
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); bpy.context.collection.objects.link(cam); sc.camera = cam
    top = max((bm.matrix_world @ v.co).z for v in bm.data.vertices)
    t = Vector((0, 0, top - 0.13)); y = math.radians(25)
    cam.location = t + Vector((math.sin(y) * 0.95, -math.cos(y) * 0.95, 0.03))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = 85
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--squad", required=True)
    ap_.add_argument("--out", required=True)
    ap_.add_argument("--pack", default="", help="MakeHuman system asset pack zip (loaded into MPFB if missing)")
    ap_.add_argument("--only", default="")
    ap_.add_argument("--no-render", action="store_true")
    a = ap_.parse_args()
    os.makedirs(a.out, exist_ok=True)
    HS = enable_mpfb(); ensure_assets(a.pack)
    lib = mhlib.Library()
    looks = read_squad(a.squad)
    only = {int(x) for x in a.only.split(",") if x}
    report = []
    for n, ap in enumerate(looks):
        if only and n not in only:
            continue
        t0 = time.time()
        tw = ap.target_weights(lib)
        hs = ap.hair_style if ap.hair_style not in ("bald", "buzz") else ""
        info = mhlib.human_info(tw, hair=hs, eyebrows=ap.brow_style, eye_colour=ap.eye_colour, skin=ap.skin)
        info0 = mhlib.human_info({}, hair=hs, eyebrows=ap.brow_style, eye_colour=ap.eye_colour, skin=ap.skin)
        bm0, _ = build(HS, info0); V0 = to_mh(shape_coords(bm0))
        bm, parts = build(HS, info); V1 = to_mh(shape_coords(bm))
        mpfb_delta = V1 - V0
        Vb = lib.base()[0]
        forge_delta = np.zeros_like(Vb)
        for t, w in tw.items():
            i, d = lib.target(t); forge_delta[i] += d * w
        err = np.linalg.norm(mpfb_delta - forge_delta, axis=1) * 100.0            # dm -> mm
        r = {"look": n, "targets": len(tw), "body_delta_max_mm": round(float(err.max()), 3),
             "body_delta_mean_mm": round(float(err.mean()), 4),
             "largest_feature_shift_mm": round(float(np.linalg.norm(forge_delta, axis=1).max() * 100), 1)}
        for kind, aname in (("hair", hs), ("eyebrows", ap.brow_style), ("eyelashes", "eyelashes01"), ("eyes", "high-poly")):
            if not aname or aname.lower() not in parts:
                continue
            ob = parts[aname.lower()]
            P = np.array([tuple(ob.matrix_world @ v.co) for v in ob.data.vertices])
            mine = lib.proxy(kind, aname).fit(V1)                                     # Forge's fit on MPFB's body
            mm = chamfer(to_mh(P), mine)
            r[kind + "_fit_mm"] = {"mean": round(mm[0] * 100, 3), "p99": round(mm[1] * 100, 3), "max": round(mm[2] * 100, 3)}
        if not a.no_render:
            portrait(os.path.join(a.out, "blender_%d.png" % n), bm)
        r["seconds"] = round(time.time() - t0, 1)
        report.append(r); print(json.dumps(r), flush=True)
    json.dump(report, open(os.path.join(a.out, "verify.json"), "w"), indent=1)
    worst = max(x["body_delta_max_mm"] for x in report)
    print("VERIFY body max error %.3f mm over %d looks" % (worst, len(report)))


if __name__ == "__main__":
    main()
