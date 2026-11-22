#!/usr/bin/env python3
"""v11.28 rigrec.write_glb_parts: several textured mesh parts on one skeleton.

    python tools/test_glb_parts.py

Writes a two-identity, two-part figure on a three-bone rig with one clip and checks that
the GLB reads back: a node per part, smooth normals and UVs kept, alpha / double-sided
materials, a linear mip-mapped sampler, JPEG and PNG images, and the clip on every bone.
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sforge import rigrec as RR  # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok: passed += 1; print("  PASS  " + name)
    else: failed += 1; print("  FAIL  " + name + ("  " + detail if detail else ""))


r = RR.Rig("t")
r.bones = ["Hips", "Spine", "Head"]
r.parent = np.array([-1, 0, 1])
r.bind = np.array([RR.m4(None, np.array([0, y, 0.0])) for y in (1.0, 1.3, 1.6)])
r.meta = {"hips_index": 0}
c = RR.Clip("sway", np.tile(np.array([0, 0, 0, 1.0]), (10, 3, 1)), np.tile(r.rest_local()[:, :3, 3], (10, 1, 1)), fps=30.0)
r.clips = {"sway": c}


def quad(y0):
    V = np.array([[-.1, y0, 0], [.1, y0, 0], [.1, y0 + .2, 0], [-.1, y0 + .2, 0]], float)
    return dict(V=V, N=np.tile([0, 0, 1.0], (4, 1)), UV=np.array([[0, 0], [1, 0], [1, 1], [0, 1.0]]),
                J=np.zeros((4, 4), int), W=np.tile([1.0, 0, 0, 0], (4, 1)), F=np.array([[0, 1, 2], [0, 2, 3]]))


parts = []
for v in ("v0", "v1"):
    parts.append(dict(quad(1.0), name=v + "_body", material="skin_" + v))
    parts.append(dict(quad(1.5), name=v + "_hair", material="hair"))
jpg = io.BytesIO(); Image.new("RGB", (8, 8), (200, 150, 120)).save(jpg, "JPEG")
png = io.BytesIO(); Image.new("RGBA", (8, 8), (90, 60, 30, 128)).save(png, "PNG")
images = {"skin_v0": (jpg.getvalue(), "image/jpeg"), "skin_v1": (jpg.getvalue(), "image/jpeg"), "hair": png.getvalue()}
mats = [dict(name="skin_v0", image="skin_v0"), dict(name="skin_v1", image="skin_v1"),
        dict(name="hair", image="hair", alpha="MASK", double=True)]
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "t.glb")
    rep = RR.write_glb_parts(r, path, parts, mats, images, clips=["sway"])
    raw = open(path, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    g = json.loads(raw[20:20 + jl])
names = [n["name"] for n in g["nodes"] if "mesh" in n]
check("a node per part", names == ["v0_body", "v0_hair", "v1_body", "v1_hair"], str(names))
prim = g["meshes"][0]["primitives"][0]
check("normals, UVs and indices kept", all(k in prim["attributes"] for k in ("NORMAL", "TEXCOORD_0")) and "indices" in prim)
hair = next(m for m in g["materials"] if m["name"] == "hair")
check("hair material is alpha-masked and double-sided", hair.get("alphaMode") == "MASK" and hair.get("doubleSided"))
check("linear mip-mapped sampler", g["samplers"][0] == {"magFilter": 9729, "minFilter": 9987})
check("JPEG and PNG images", sorted({i["mimeType"] for i in g["images"]}) == ["image/jpeg", "image/png"])
check("clip animates every bone", len({ch["target"]["node"] for ch in g["animations"][0]["channels"]}) == 3)
check("report counts parts and tris", rep["parts"] == 4 and rep["tris"] == 8, str(rep))
print("RESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
