#!/usr/bin/env python3
"""Bake LOD1/LOD2 for the GAA squad (Sprite Forge skinlod v11.38) into a COPY.

Writes tools/out/gaelic_player.lod.glb — NEVER overwrites the shipped asset.
Two stages:
  1. a TEXCOORD_0-zero injection pass (the 11 flat-tinted kit garments ship
     without UVs; tailor.read_parts hard-requires them),
  2. per variant prefix v0_..v8_: read parts, skinlod.lod_parts (0.45 / 0.22
     triangle ratios, small parts dropped at level 2), replace_parts.

    ../sfvenv/bin/python tools/build_afl_lods.py
"""
from __future__ import annotations
import json
import os
import struct
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(REPO, "sprite_forge"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GLB = os.path.join(ROOT, "public", "assets", "gaelic_player.glb")
OUT_DIR = os.path.join(ROOT, "tools", "out")
UVFIX = os.path.join(OUT_DIR, "gaelic_player.uvfix.glb")
OUT = os.path.join(OUT_DIR, "gaelic_player.lod.glb")
PREFIXES = ["v%d_" % i for i in range(9)]


def inject_uv(src: str, dst: str) -> int:
    """Copy a GLB, adding an all-zero TEXCOORD_0 to primitives that lack one."""
    from sforge import glbpack, officials
    j, buf = glbpack.read_glb(src)
    out = glbpack._Out()
    amap = {}

    def keep(i):
        if i not in amap:
            amap[i] = out.copy_acc(j, buf, i)
        return amap[i]

    n_injected = 0
    meshes = []
    for m in j.get("meshes", []):
        prs = []
        for pr in m.get("primitives", []):
            p2 = dict(pr)
            at = {k: keep(v) for k, v in pr["attributes"].items()}
            if "TEXCOORD_0" not in at:
                n = j["accessors"][pr["attributes"]["POSITION"]]["count"]
                at["TEXCOORD_0"] = out.add(np.zeros((n, 2), np.float32), 5126, "VEC2", 34962)
                n_injected += 1
            if "indices" in pr:
                p2["indices"] = keep(pr["indices"])
            p2["attributes"] = at
            p2.pop("targets", None)
            prs.append(p2)
        meshes.append(dict(m, primitives=prs))
    skins = []
    for sk in j.get("skins", []):
        s2 = dict(sk)
        if "inverseBindMatrices" in sk:
            s2["inverseBindMatrices"] = keep(sk["inverseBindMatrices"])
        skins.append(s2)
    anims = []
    for an in j.get("animations", []):
        sm = [{"input": keep(s["input"]), "output": keep(s["output"]),
               "interpolation": s.get("interpolation", "LINEAR")} for s in an["samplers"]]
        anims.append({"name": an.get("name", "anim"), "channels": an["channels"], "samplers": sm})
    imgs = []
    for im in j.get("images", []):
        im2 = dict(im)
        if "bufferView" in im:
            bv = j["bufferViews"][im["bufferView"]]
            o = bv.get("byteOffset", 0)
            im2["bufferView"] = out.view(bytes(buf[o:o + bv["byteLength"]]))
        imgs.append(im2)
    gl = dict(j)
    gl.update({"meshes": meshes, "skins": skins, "animations": anims,
               "accessors": out.acc, "bufferViews": out.views,
               "buffers": [{"byteLength": 0}]})
    if imgs:
        gl["images"] = imgs
    os.makedirs(OUT_DIR, exist_ok=True)
    officials._write(gl, out.b, dst)
    return n_injected


def strip_untextured_uvs(path: str) -> int:
    """Drop TEXCOORD_0 from primitives whose material samples no texture, then compact the buffer.

    The zero UVs were a bake placeholder for parts that ship without any; the shipped asset carries no
    UVs for these kit garments either, so the candidate should not either.
    """
    from sforge import glbpack
    j, buf = glbpack.read_glb(path)

    def mat_uses_texture(mi) -> bool:
        mt = j["materials"][mi]
        pbr = mt.get("pbrMetallicRoughness", {})
        if any(pbr.get(k) is not None for k in ("baseColorTexture", "metallicRoughnessTexture")):
            return True
        if any(mt.get(k) is not None for k in ("normalTexture", "occlusionTexture", "emissiveTexture")):
            return True
        for ext in (mt.get("extensions") or {}).values():
            if isinstance(ext, dict):
                for v in ext.values():
                    if isinstance(v, dict) and "index" in v:
                        return True
        return False

    drop_acc = set()
    for m in j.get("meshes", []):
        for pr in m.get("primitives", []):
            mi = pr.get("material")
            if mi is None or mat_uses_texture(mi):
                continue
            ai = pr.get("attributes", {}).pop("TEXCOORD_0", None)
            if ai is not None:
                drop_acc.add(ai)
    if not drop_acc:
        return 0

    # a bufferView goes with its accessor only if no other kept accessor uses it
    drop_view = set()
    for i, a in enumerate(j["accessors"]):
        if i in drop_acc:
            bv = a.get("bufferView")
            if bv is not None and all(
                k == i or j["accessors"][k].get("bufferView") != bv for k in range(len(j["accessors"]))
            ):
                drop_view.add(bv)

    view_remap, new_views = {}, []
    new_buf = bytearray()
    for i, bv in enumerate(j["bufferViews"]):
        if i in drop_view:
            continue
        view_remap[i] = len(new_views)
        while len(new_buf) % 4:
            new_buf.append(0)
        off = bv.get("byteOffset", 0)
        nv = dict(bv)
        nv["byteOffset"] = len(new_buf)
        nv["buffer"] = 0
        new_buf += buf[off: off + bv["byteLength"]]
        new_views.append(nv)

    acc_keep = [i for i in range(len(j["accessors"])) if i not in drop_acc]
    acc_remap = {old: new for new, old in enumerate(acc_keep)}
    new_acc = []
    for i in acc_keep:
        a = dict(j["accessors"][i])
        if "bufferView" in a:
            a["bufferView"] = view_remap[a["bufferView"]]
        new_acc.append(a)

    def remap_acc(ai):
        return acc_remap[ai]

    for m in j.get("meshes", []):
        for pr in m.get("primitives", []):
            pr["attributes"] = {k: acc_remap[v] for k, v in pr.get("attributes", {}).items()}
            if "indices" in pr:
                pr["indices"] = acc_remap[pr["indices"]]
            if "targets" in pr:
                pr["targets"] = [{k: acc_remap[v] for k, v in t.items()} for t in pr["targets"]]
    for an in j.get("animations", []):
        for smp in an.get("samplers", []):
            smp["input"] = acc_remap[smp["input"]]
            smp["output"] = acc_remap[smp["output"]]
    for sk in j.get("skins", []):
        if "inverseBindMatrices" in sk:
            sk["inverseBindMatrices"] = acc_remap[sk["inverseBindMatrices"]]
    for im in j.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = view_remap[im["bufferView"]]
    j["accessors"], j["bufferViews"] = new_acc, new_views
    j["buffers"] = [{"byteLength": len(new_buf)}]
    _write_glb(j, bytes(new_buf), path)
    return len(drop_acc)


def _write_glb(j: dict, buf: bytes, path: str) -> None:
    js = json.dumps(j, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "
    bpad = bytearray(buf)
    while len(bpad) % 4:
        bpad.append(0)
    total = 12 + 8 + len(js) + 8 + len(bpad)
    with open(path, "wb") as fh:
        fh.write(b"glTF" + struct.pack("<II", 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(bpad), 0x004E4942))
        fh.write(bpad)


def add_bufferview_targets(path: str) -> int:
    """Set bufferView.target (ARRAY_BUFFER/ELEMENT_ARRAY_BUFFER) the way the shipped asset carries it.

    The tailor/replace_parts repack omits `target` (valid glTF, only a validator info); this restores
    the shipped hygiene without touching the geometry bytes. Idempotent.
    """
    from sforge import glbpack
    j, buf = glbpack.read_glb(path)
    idx_views, attr_views = set(), set()
    for m in j.get("meshes", []):
        for pr in m.get("primitives", []):
            views = j["accessors"]
            if "indices" in pr:
                bv = views[pr["indices"]].get("bufferView")
                if bv is not None:
                    idx_views.add(bv)
            for attr_acc in pr.get("attributes", {}).values():
                bv = views[attr_acc].get("bufferView")
                if bv is not None:
                    attr_views.add(bv)
    n = 0
    for i, bv in enumerate(j.get("bufferViews", [])):
        if "target" in bv:
            continue
        if i in idx_views:
            bv["target"] = 34963
            n += 1
        elif i in attr_views:
            bv["target"] = 34962
            n += 1
    _write_glb(j, buf, path)
    return n


def main() -> int:
    n = inject_uv(GLB, UVFIX)
    print("uv-injected %d primitive(s) -> %s (%.1f MB)" % (n, UVFIX, os.path.getsize(UVFIX) / 1e6))

    from sforge import skinlod as SL, tailor as T
    # The stock plan collapses the shin tube to a chord (nearest-vertex 95th-pct dev ~50 mm at L1,
    # ~25 mm even at 0.75 ratio). Bump socks the way the stock plan already bumps jersey/shorts.
    plan = dict(SL.LOD_PLAN)
    plan["min_ratio"] = dict(SL.LOD_PLAN["min_ratio"], socks=(0.75, 0.7))
    t0 = time.time()
    by_prefix, table = {}, {}
    report = {}
    for pre in PREFIXES:
        parts = {k: v for k, v in T.read_parts(UVFIX, pre).items() if "_lod" not in k}
        lods = SL.lod_parts(parts, plan=plan)
        add = {}
        tri0 = sum(len(p.F) for p in parts.values())
        level_tris = []
        for k in range(len(SL.LOD_PLAN["ratios"])):
            level_tris.append(int(sum(len(q[k].F) for q in lods.values() if q[k] is not None)))
        dev = {}
        for name, levels in lods.items():
            row = []
            for k, q in enumerate(levels, start=1):
                if q is None:
                    row.append(-1)
                elif q is parts[name]:
                    row.append(0)
                else:
                    add["%s_lod%d" % (name, k)] = q
                    row.append(1)
            table[pre + ":" + name] = row
            src_part = parts[name]
            dev[name] = [
                round(float(SL.deviation(src_part, q)), 6) if q is not None and q is not parts[name] else 0.0
                for q in levels
            ]
        by_prefix[pre] = add
        report[pre] = {"tris_full": int(tri0), "tris_per_level": level_tris, "deviation_m": dev}
        print("  %s %d -> %s tris (%.0fs)" % (pre, tri0, " / ".join(map(str, level_tris)), time.time() - t0))

    size = T.replace_parts(UVFIX, OUT, by_prefix)
    print("wrote %s (%.1f MB)" % (OUT, size / 1e6))

    # verify the candidate round-trips through the game's own loader path
    from sforge import gltfread
    rig = gltfread.load(OUT)
    names = rig.bones
    clips = list(rig.clips)
    assert rig.nb == 52, "joint count changed: %d" % rig.nb
    assert len(clips) == 32, "clip count changed: %d" % len(clips)
    doc_names = []
    from sforge import glbpack
    j, _ = glbpack.read_glb(OUT)
    doc_names = [nd.get("name") for nd in j["nodes"]]
    lod_nodes = sum(1 for nm in doc_names if nm and ("_lod1" in nm or "_lod2" in nm))
    print("candidate OK: 52 joints, 32 clips, %d LOD nodes" % lod_nodes)
    with open(os.path.join(OUT_DIR, "lod_report.json"), "w") as fh:
        json.dump({"parts": table, "variants": report, "lod_nodes": lod_nodes}, fh, indent=1)
    u = strip_untextured_uvs(OUT)
    print("stripped %d placeholder UV accessor(s) from untextured primitives" % u)
    t = add_bufferview_targets(OUT)
    print("bufferView.target restored on %d view(s)" % t)
    print("report -> %s" % os.path.join(OUT_DIR, "lod_report.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
