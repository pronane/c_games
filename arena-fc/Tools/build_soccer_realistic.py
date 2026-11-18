#!/usr/bin/env python3
"""Build the Sprite Forge **realistic** soccer player for Arena FC.

Option 2 of the realistic-player comparison (Option 1 = build_soccer_player.py, the
18-bone sculpted stylized player).  Option 2 swaps the stylized sculpt for the
MakeHuman-derived realistic footballer that ships in Gaelic_Football_3d and
Hurling_3d: real anatomy mesh with baked skin / eye / hair / beard atlases, the
full 52-joint MakeHuman skeleton (fingers, neck, ball of the foot), and smooth
normals - not marching cubes.

Pipeline:
  1. Read the source squad GLB (Gaelic_Football_3d/assets/models/gaelic_player.glb)
     and keep three identities (v0, v2, v6) sharing the one 52-joint skeleton and
     skin, exactly like the Gaelic source file.
  2. Replace the GAA-torso `kit` material with four flat, per-club tintable
     slots: jersey / shorts / socks / boots (white base PNGs the engine multiplies
     with the club colours; socks carry two subtle hoops).  Skin, eyes, hair,
     brows, lashes, beard and facial-hair atlases are kept untouched so faces
     stay real.
  3. Animations: every clip in Tools/soccer_motions.py (71 clips) is baked on the
     Sprite Forge mannequin and retargeted onto the MH skeleton twice:
       - tgtA (desktop GLB): retargeted against the rig as loaded from the source
         (bind = source rest world transforms) so rotation tracks match the MH
         rest orientations carried by the nodes, and
       - tgtB (browser soccer_rig.json): retargeted against an identity-rest MH
         skeleton (bind = pure translations), matching ProceduralRig3D.build()
         which binds every bone with Basis.IDENTITY.
  4. Write:
       Data/models/soccer_player.glb       desktop C# (GltfDocument + AnimationPlayer)
       Data/soccer_rig.json                browser GDScript (ProceduralRig3D schema,
                                           plus variant_sets for v2/v6)
       Data/soccer_player_manifest.json    clip list, aliases, material order, variants

Needs the Sprite Forge core deps (see build_soccer_player.py) plus numpy/PIL.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)
sys.path.insert(0, HERE)

import soccer_motions as SM  # noqa: E402
from sforge import bonemap as BM  # noqa: E402
from sforge import rigrec as RR  # noqa: E402
from sforge import retarget as RT  # noqa: E402
from sforge.glbpack import read_glb, _acc_bytes, _Out  # noqa: E402
from sforge.gltfread import load as glb_load  # noqa: E402

TEMPLATE = os.path.abspath(os.path.join(ARENA, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb"))
VARIANTS = ("v0", "v2", "v6")
# body part order within each variant, matching the Gaelic source's node suffixes
PARTS = ("body", "jersey", "shorts", "socks", "boots", "eyes", "lashes", "brows",
         "hairinner", "hair", "beardshell0", "beardshell1", "facialhair")
# not every identity has facial hair (v0 and v6 are clean-shaven in the source)
KIT_SPLIT = ("jersey", "shorts", "socks", "boots")          # these carry the GAA-torso `kit` material
FLAT_KEYS = {k: k for k in KIT_SPLIT}
# hair family -> tint with CharacterSpec.HairColor at runtime; skin/eyes stay natural
HAIR_FAMILY = ("hair_short02", "hair_short01", "hair_afro01",
               "eyelashes_eyelashes02", "eyebrows_eyebrow003", "eyebrows_eyebrow009",
               "beard_shell", "facial_hair")
EYE_MATERIALS = ("eyes_brown", "eyes_bluegreen", "eyes_brownlight")
# material name -> keep alpha MASK + doubleSided from the source file (shells / decals)
ALPHA_MATERIALS = ("hair_short02", "hair_short01", "hair_afro01",
                   "eyelashes_eyelashes02", "eyebrows_eyebrow003", "eyebrows_eyebrow009",
                   "beard_shell", "facial_hair")

# slot indices for the browser (ProceduralRig3D.material_for)
LAYER_SLOT = {"skin": 0, "jersey": 1, "shorts": 2, "socks": 3, "hair": 6, "boots": 8, "eyes": 9}


# -------------------------------------------------------------------- helpers
def _idx(j, n):
    return n.get("mesh")


def _part_nodes(j):
    """(variant, part) -> node index, for kept variant mesh nodes."""
    out = {}
    for i, n in enumerate(j["nodes"]):
        if "mesh" not in n:
            continue
        nm = n.get("name", "")
        v = nm.split("_", 1)[0]
        if v in VARIANTS:
            out[(v, nm[len(v) + 1:])] = i
    return out


def _read_primitive(j, buf, prim):
    at = prim["attributes"]
    P = np.frombuffer(_acc_bytes(j, buf, at["POSITION"]), np.float32).reshape(-1, 3).astype(np.float64)
    N = np.frombuffer(_acc_bytes(j, buf, at["NORMAL"]), np.float32).reshape(-1, 3).astype(np.float64)
    UV = np.frombuffer(_acc_bytes(j, buf, at["TEXCOORD_0"]), np.float32).reshape(-1, 2).astype(np.float64)
    jt = {5121: np.uint8, 5123: np.uint16}[j["accessors"][at["JOINTS_0"]]["componentType"]]
    J = np.frombuffer(_acc_bytes(j, buf, at["JOINTS_0"]), jt).astype(np.int32).reshape(-1, 4)
    W = np.frombuffer(_acc_bytes(j, buf, at["WEIGHTS_0"]), np.float32).reshape(-1, 4).astype(np.float64)
    idx_dt = np.uint32 if j["accessors"][prim["indices"]]["componentType"] == 5125 else np.uint16
    F = np.frombuffer(_acc_bytes(j, buf, prim["indices"]), idx_dt).astype(np.int32).reshape(-1, 3)
    return P, N, UV, J, W, F


def _world_transforms(j):
    """node index -> world 4x4 (nodes carry translation + rotation(+scale))."""
    parent = {}
    for i, n in enumerate(j["nodes"]):
        for c in n.get("children", []) or []:
            parent[c] = i

    def qmat(q):
        x, y, z, w = q
        n = x * x + y * y + z * z + w * w
        if n == 0:
            return np.eye(3, dtype=np.float64)
        s = 2.0 / n
        xx, yy, zz = x * x * s, y * y * s, z * z * s
        xy, xz, yz = x * y * s, x * z * s, y * z * s
        wx, wy, wz = w * x * s, w * y * s, w * z * s
        return np.array([[1 - (yy + zz), xy - wz, xz + wy],
                         [xy + wz, 1 - (xx + zz), yz - wx],
                         [xz - wy, yz + wx, 1 - (xx + yy)]], dtype=np.float64)

    cache = {}

    def world(i):
        if i in cache:
            return cache[i]
        n = j["nodes"][i]
        if "matrix" in n:
            M = np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
        else:
            t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
            q = np.array(n.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
            s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
            M = np.eye(4, dtype=np.float64)
            M[:3, :3] = qmat(q) * s[None, :]
            M[:3, 3] = t
        p = parent.get(i)
        cache[i] = world(p) @ M if p is not None else M
        return cache[i]

    return {i: world(i) for i in range(len(j["nodes"]))}


def _flat_png(color, hoops=False):
    img = Image.new("RGB", (32, 64), color)
    if hoops:
        px = img.load()
        for y in range(9, 15):
            for x in range(32):
                px[x, y] = (int(color[0] * 0.82), int(color[1] * 0.82), int(color[2] * 0.82))
        for y in range(27, 33):
            for x in range(32):
                px[x, y] = (int(color[0] * 0.82), int(color[1] * 0.82), int(color[2] * 0.82))
    bio = io.BytesIO()
    img.save(bio, "PNG")
    return bio.getvalue()


def _clips_on(tgt, src, src_rec, mean_err_box):
    trec = BM.detect(tgt)
    if trec["missing"]:
        raise SystemExit("bonemap missing on MH rig: %s" % trec["missing"])
    clips = {}
    for name in SM.ALL_CLIPS:
        cl, rep = RT.retarget(src, src_rec, name, tgt, trec, root_motion="inplace", name=name)
        clips[name] = cl
        if rep.get("mean_dir_err_deg") is not None:
            mean_err_box.append(rep["mean_dir_err_deg"])
    return clips, trec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=os.path.join(ARENA, "Data"))
    ap.add_argument("--template", default=TEMPLATE)
    a = ap.parse_args()

    t0 = time.time()
    errs = SM.validate()
    if errs:
        print("soccer motions invalid:", errs)
        return 1

    print("== Option 2: realistic Sprite Forge soccer player ==")
    src = RR.from_mannequin(name="soccer_src", clips=SM.ALL_CLIPS)
    src_rec = BM.detect(src)
    if src_rec["missing"]:
        print("mannequin bonemap missing:", src_rec["missing"])
        return 1

    # ---- desktop retarget (real MH rest frames, matches the GLB's nodes) -------
    print("loading template rig:", a.template)
    tgtA = glb_load(a.template)
    errA = []
    clipsA, recA = _clips_on(tgtA, src, src_rec, errA)
    print("  retargeted %d clips onto MH rig (real rest, mean dir err %.2f deg)" %
          (len(clipsA), float(np.mean(errA)) if errA else 0.0))

    # ---- browser retarget (identity rest, matches ProceduralRig3D.build) --------
    j0, buf0 = read_glb(a.template)
    src_skins = j0["skins"][0]
    joint_nodes = list(src_skins["joints"])
    xform = _world_transforms(j0)
    origins = [xform[i][:3, 3].copy() for i in joint_nodes]
    names = [j0["nodes"][i]["name"] for i in joint_nodes]
    parent = np.full(len(joint_nodes), -1, int)
    index_of = {nd: k for k, nd in enumerate(joint_nodes)}
    par_raw = {}
    for i, n in enumerate(j0["nodes"]):
        for c in n.get("children", []) or []:
            par_raw[c] = i
    for k, nd in enumerate(joint_nodes):
        p = par_raw.get(nd)
        while p is not None and p not in index_of:
            p = par_raw.get(p)
        parent[k] = index_of[p] if p is not None else -1
    tgtB = RR.Rig("arenafc_mh_identity")
    tgtB.bones = names
    tgtB.parent = parent
    tgtB.bind = np.array([RR.m4(None, o) for o in origins], float)
    tgtB.meta = {"convention": "makehuman", "hips_index": names.index("pelvis")}
    errB = []
    clipsB, recB = _clips_on(tgtB, src, src_rec, errB)
    print("  retargeted %d clips onto identity-rest MH rig (mean dir err %.2f deg)" %
          (len(clipsB), float(np.mean(errB)) if errB else 0.0))

    # ---- parts extraction -------------------------------------------------------
    part_nodes = _part_nodes(j0)
    for v in VARIANTS:
        essential = [p for p in ("body", "jersey", "shorts", "socks", "boots", "eyes")]
        missing = [p for p in essential if (v, p) not in part_nodes]
        if missing:
            raise SystemExit("variant %s is missing essential parts: %s" % (v, missing))
    parts = []          # dict(name, V, N, UV, J, W, F, key)
    total_tris = 0
    for v in VARIANTS:
        for p in PARTS:
            if (v, p) not in part_nodes:
                continue
            ni = part_nodes[(v, p)]
            pr = j0["meshes"][j0["nodes"][ni]["mesh"]]["primitives"][0]
            V, N, UV, J, W, F = _read_primitive(j0, buf0, pr)
            mat = j0["materials"][pr["material"]]["name"]
            key = p if p in KIT_SPLIT else mat   # kit parts -> flat slot keys
            parts.append(dict(name="%s_%s" % (v, p), V=V, N=N, UV=UV, J=J, W=W, F=F, key=key, mat=mat))
            total_tris += len(F)
    print("  parts: %d meshes, %d tris total (%s)" % (len(parts), total_tris, ", ".join(VARIANTS)))

    # ---- images ------------------------------------------------------------------
    keep_images = {}
    img_bytes_by_name = {}
    for im in j0.get("images", []):
        bv = j0["bufferViews"][im["bufferView"]]
        img_bytes_by_name[im.get("name", "")] = buf0[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
    flat_png = {k: _flat_png((255, 255, 255), hoops=(k == "socks")) for k in KIT_SPLIT}
    src_image_by_mat = {}
    for m in j0.get("materials", []):
        pb = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" not in pb:
            src_image_by_mat[m["name"]] = None
            continue
        tname = j0.get("textures", [])[pb["baseColorTexture"]["index"]].get("source")
        im = j0.get("images", [])[tname]
        src_image_by_mat[m["name"]] = im.get("name")
    used_src = set()
    for p in parts:
        if p["key"] in FLAT_KEYS:
            continue
        iname = src_image_by_mat.get(p["mat"])
        if iname:
            used_src.add(iname)
    images = {k: v for k, v in flat_png.items()}
    for nm in sorted(used_src):
        if nm in img_bytes_by_name:
            images[nm] = img_bytes_by_name[nm]
        else:
            print("  WARNING: source image %r for material bytes not found" % nm)
    print("  images: %d (flats: %s; atlas kept: %d)" % (len(images), ",".join(sorted(flat_png)), len(used_src)))

    # ---- materials -----------------------------------------------------------------
    mat_alpha = {m["name"]: (m.get("alphaMode"), m.get("doubleSided", False)) for m in j0.get("materials", [])}

    def mat_def(name):
        if name in FLAT_KEYS:
            return {"name": name, "key": name, "alpha": (None, False)}
        return {"name": name, "key": src_image_by_mat.get(name), "alpha": mat_alpha.get(name, (None, False))}

    materials = []
    seen = set()
    for p in parts:
        k = p["key"]
        if k not in seen:
            seen.add(k)
            materials.append(mat_def(k))

    # ---- remap helpers for the output document ------------------------------------
    drop = {i for i, nd in enumerate(j0["nodes"]) if "mesh" in nd}
    keep = [i for i in range(len(j0["nodes"])) if i not in drop]
    remap = {o: k for k, o in enumerate(keep)}
    joint_node_in_out = {nd: remap[nd] for nd in joint_nodes}

    out = _Out()
    nodes = []
    for o in keep:
        nd = dict(j0["nodes"][o])
        if "children" in nd:
            nd["children"] = [remap[c] for c in nd["children"] if c in remap]
            if not nd["children"]:
                nd.pop("children")
        nd.pop("skin", None)
        nodes.append(nd)

    sk = dict(src_skins)
    sk["joints"] = [remap[x] for x in src_skins["joints"]]
    if "skeleton" in sk:
        sk["skeleton"] = remap.get(sk["skeleton"], sk["joints"][0])
    sk["inverseBindMatrices"] = out.copy_acc(j0, buf0, src_skins["inverseBindMatrices"])

    mat_index = {m["name"]: i for i, m in enumerate(materials)}
    img_index = {}
    mats_out, texs_out, imgs_out = [], [], []
    for m in materials:
        key = m["key"]
        assert key is not None and key in images, "material %r has no image" % m["name"]
        if key not in img_index:
            img_index[key] = len(imgs_out)
            imgs_out.append({"bufferView": out.view(images[key]), "mimeType": "image/png", "name": key})
            texs_out.append({"source": img_index[key], "sampler": 0})
        md = {"name": m["name"], "pbrMetallicRoughness": {"baseColorTexture": {"index": img_index[key]},
                                                          "metallicFactor": 0.0, "roughnessFactor": 0.85}}
        am, dbl = m["alpha"]
        if am == "MASK":
            md["alphaMode"] = "MASK"
            md["alphaCutoff"] = 0.5
        if dbl:
            md["doubleSided"] = True
        mats_out.append(md)

    meshes = []
    scene = dict(j0["scenes"][j0.get("scene", 0)])
    scene["nodes"] = [remap[n] for n in scene["nodes"] if n in remap]
    total_v = 0
    for p in parts:
        V = p["V"].astype(np.float32)
        N = p["N"]
        ln = np.linalg.norm(N, axis=1)
        N[ln < 1e-6] = (0, 1.0, 0)
        N = (N / np.linalg.norm(N, axis=1, keepdims=True)).astype(np.float32)
        F = p["F"]
        J = p["J"]
        W = p["W"].astype(np.float32)
        attrs = {"POSITION": out.add(V, 5126, "VEC3", 34962, True),
                 "NORMAL": out.add(N, 5126, "VEC3", 34962),
                 "TEXCOORD_0": out.add(p["UV"].astype(np.float32), 5126, "VEC2", 34962),
                 "JOINTS_0": out.add(J.astype(np.uint16), 5123, "VEC4", 34962),
                 "WEIGHTS_0": out.add(W, 5126, "VEC4", 34962)}
        idx_t = (np.uint16, 5123) if len(V) < 65535 else (np.uint32, 5125)
        ind = out.add(F.astype(idx_t[0]).reshape(-1), idx_t[1], "SCALAR", 34963)
        meshes.append({"name": p["name"], "primitives": [{"attributes": attrs, "indices": ind,
                                                          "material": mat_index[p["key"]]}]})
        nodes.append({"name": p["name"], "mesh": len(meshes) - 1, "skin": 0})
        scene["nodes"].append(len(nodes) - 1)
        total_v += len(V)

    anims = []
    pelvis_node = joint_node_in_out[joint_nodes[names.index("pelvis")]]
    for cname in SM.ALL_CLIPS:
        cl = clipsA[cname]
        t = (np.arange(cl.frames) / cl.fps).astype(np.float32)
        ta = out.add(t, 5126, "SCALAR", minmax=True)
        sm = []
        ch = []
        for i in range(len(names)):
            bnode = joint_node_in_out[joint_nodes[i]]
            sm.append({"input": ta, "output": out.add(cl.R[:, i].astype(np.float32), 5126, "VEC4"),
                       "interpolation": "LINEAR"})
            ch.append({"sampler": len(sm) - 1, "target": {"node": bnode, "path": "rotation"}})
        Tstrip = RR.strip_root_motion(tgtA, cl)
        sm.append({"input": ta, "output": out.add(Tstrip[:, names.index("pelvis")].astype(np.float32),
                                                  5126, "VEC3"), "interpolation": "LINEAR"})
        ch.append({"sampler": len(sm) - 1, "target": {"node": pelvis_node, "path": "translation"}})
        anims.append({"name": cname, "channels": ch, "samplers": sm})

    gl = {"asset": {"version": "2.0",
                    "generator": "Sprite Forge Studio (AO v11.17) - Arena FC realistic soccer player"},
          "scene": 0, "scenes": [scene], "nodes": nodes, "skins": [sk], "animations": anims,
          "meshes": meshes, "materials": mats_out, "textures": texs_out,
          "samplers": [{"magFilter": 9729, "minFilter": 9987}], "images": imgs_out,
          "accessors": out.acc, "bufferViews": out.views,
          "buffers": [{"byteLength": 0}],
          "extras": {"arena_fc": {"look": "realistic", "skeleton": "makehuman-52",
                                  "variants": list(VARIANTS),
                                  "variant_prefixes": ["%s_" % v for v in VARIANTS]}}}
    b = out.b
    while len(b) % 4:
        b.append(0)
    gl["buffers"][0]["byteLength"] = len(b)
    js = json.dumps(gl, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    import struct
    glb_path = os.path.join(a.out_dir, "models", "soccer_player.glb")
    os.makedirs(os.path.dirname(glb_path), exist_ok=True)
    with open(glb_path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(b))
                + struct.pack("<II", len(js), 0x4E4F534A) + js
                + struct.pack("<II", len(b), 0x004E4942) + bytes(b))
    print("  wrote %s (%.1f MB)" % (glb_path, os.path.getsize(glb_path) / 1e6))

    # ---- browser JSON -------------------------------------------------------------
    def baked_set(variant):
        def slot_of(p):
            part = p["name"].split("_", 1)[1]
            if part == "body":
                return LAYER_SLOT["skin"]
            if part == "eyes":
                return LAYER_SLOT["eyes"]
            return LAYER_SLOT.get(p["key"], 6)

        pos, nrm, uv, bi, w, idx = [], [], [], [], [], [[] for _ in range(10)]
        for p in parts:
            if p["name"].split("_", 1)[0] != variant:
                continue
            V = p["V"]; N = p["N"]; F = p["F"]
            base = len(pos) // 3
            pos.extend(np.round(V, 4).ravel().tolist())
            nrm.extend(np.round(N, 4).ravel().tolist())
            uv.extend(np.round(p["UV"], 4).ravel().tolist())
            bi.extend(p["J"].reshape(-1, 4).ravel().tolist())
            w.extend(np.round(p["W"], 4).ravel().tolist())
            slot = slot_of(p)
            idx[slot].extend((F + base).reshape(-1).astype(int).tolist())
        vs = {"pos": pos, "nrm": nrm, "uv": uv, "bi": bi, "w": w, "idx": idx}
        return vs

    def bone_entries(clip):
        ent = {}
        for i, bname in enumerate(names):
            e = {"r": np.round(clip.R[:, i], 4).reshape(-1).tolist()}
            if bname == "pelvis":
                e["t"] = np.round(RR.strip_root_motion(tgtB, clip)[:, names.index("pelvis")], 4).reshape(-1).tolist()
            ent[bname] = e
        return ent

    def events_for(cname, frames):
        ev = SM.CLIP_EVENTS.get(cname, {"ball_contact": -1.0, "footsteps": [],
                                        "hit_start": -1.0, "hit_end": -1.0})
        def _fr(frac):
            return int(round(frac * (frames - 1))) if frac >= 0 else -1
        return {
            "ball_contact": _fr(ev["ball_contact"]),
            "ball_contact_frac": float(ev["ball_contact"]),
            "footsteps": [_fr(f) for f in ev.get("footsteps", [])],
            "hit_start": _fr(ev.get("hit_start", -1.0)),
            "hit_end": _fr(ev.get("hit_end", -1.0)),
        }

    clips_out = {}
    for cname in SM.ALL_CLIPS:
        cl = clipsB[cname]
        clips_out[cname] = {
            "fps": float(cl.fps), "frames": int(cl.frames),
            "loop": bool(cname in SM.LOOP_CLIPS),
            "bones": bone_entries(cl),
            "events": events_for(cname, int(cl.frames)),
        }

    bones_json = [{"n": names[i], "p": int(parent[i]),
                   "h": [round(float(o[0]), 4), round(float(o[1]), 4), round(float(o[2]), 4)]}
                  for i, o in enumerate(origins)]
    base = baked_set(VARIANTS[0])
    data = {
        "generator": "ArenaFC realistic soccer rig (Tools/build_soccer_realistic.py, Sprite Forge v11.17)",
        "look": "realistic",
        "bones": bones_json,
        "pos": base["pos"], "nrm": base["nrm"], "uv": base["uv"],
        "bi": base["bi"], "w": base["w"], "idx": base["idx"],
        "mats": sorted({int(s) for s, tris in enumerate(base["idx"]) if tris}),
        "height": round(float(np.max(base["pos"][1::3])), 4),
        "clips": clips_out,
        "variants": list(VARIANTS),
        "variant_sets": {v: baked_set(v) for v in VARIANTS[1:]},
    }
    json_path = os.path.join(a.out_dir, "soccer_rig.json")
    with open(json_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("  wrote %s (%.1f MB)" % (json_path, os.path.getsize(json_path) / 1e6))

    # ---- manifest ------------------------------------------------------------------
    manifest = {
        "generator": "ArenaFC realistic soccer rig (Tools/build_soccer_realistic.py)",
        "sprite_forge": "v11.17 (main 49be53a)",
        "skeleton": "makehuman-52",
        "bones": names,
        "materials": [m["name"] for m in materials],
        "skin_materials": ["skin_v%d" % int(v[1:]) for v in VARIANTS],
        "look": "realistic",
        "source": "Gaelic_Football_3d/assets/models/gaelic_player.glb",
        "variants": list(VARIANTS),
        "variant_prefixes": ["%s_" % v for v in VARIANTS],
        "clips": [
            {"name": n, "loop": bool(n in SM.LOOP_CLIPS), "category": SM.CLIP_CATEGORIES[n],
             "source": SM.CLIP_SOURCES[n], "frames": int(clipsA[n].frames), "fps": float(clipsA[n].fps),
             "events": events_for(n, int(clipsA[n].frames))}
            for n in SM.ALL_CLIPS
        ],
        "action_aliases": SM.ACTION_ALIASES,
        "stats": {
            "tris_total_all_variants": int(total_tris),
            "height_m": round(max(base["pos"][1::3]), 4),
            "variants": {v: int(sum(len(p["F"]) for p in parts if p["name"].split("_", 1)[0] == v)) for v in VARIANTS},
            "mean_dir_err_deg": round(float(np.mean(errA + errB)) if (errA or errB) else 0.0, 3),
            "seconds": round(time.time() - t0, 1),
        },
    }
    with open(os.path.join(a.out_dir, "soccer_player_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("  wrote manifest (%d clips, %d aliases)" % (len(manifest["clips"]), len(manifest["action_aliases"])))
    print("done in %.1f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
