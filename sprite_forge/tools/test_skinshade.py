#!/usr/bin/env python3
"""Close-up shading maps and textured identities in a squad GLB (v11.34, fed back from Arena FC).

    python tools/test_skinshade.py

  1 the skin detail normal map tiles (opposite edges continue) and its normals are unit length, pointing out
  2 pores read as pits: the detail height has small dark spots over a smooth field
  3 presets cover skin, hair, eyes, lashes and beards with the keys a game needs
  4 export writes both maps and the presets
  5 replace_parts adds a part with a new textured material: the image, texture and material land in the GLB
  6 grade_iris pulls a red-brown iris to brown and leaves the sclera and a blue iris alone"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import skinshade as SS  # noqa: E402
from sforge import tailor as T  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402

SRC = os.path.join(HERE, "..", "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")
R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    h = SS.detail_height(256)
    n = SS.height_to_normal(h, 6.0)
    seam = max(np.abs(h[0] - h[-1]).mean(), np.abs(h[:, 0] - h[:, -1]).mean())
    inner = np.abs(np.diff(h, axis=0)).mean()
    rec("detail map tiles (edge step like any neighbour step)", seam < inner * 3, "edge %.4f vs %.4f" % (seam, inner))
    rec("normals unit length and facing out", np.allclose(np.linalg.norm(n, axis=-1), 1, atol=1e-5) and (n[..., 2] > .2).all())
    low = (h < np.percentile(h, 3)).mean()
    rec("pores are small pits", .01 < low < .05 and np.median(h) > .4, "median %.2f" % np.median(h))
    rec("presets for skin / hair / eyes / lashes / beard", set(SS.PRESETS) >= {"skin", "hair", "eyes", "lashes", "beard"}
        and "subsurface" in SS.PRESETS["skin"] and "anisotropy" in SS.PRESETS["hair"])
    with tempfile.TemporaryDirectory() as td:
        SS.export(td)
        ok = all(os.path.exists(os.path.join(td, f)) for f in ("skin_detail_normal.png", "skin_detail_rough.png", "materials.json"))
        rec("export writes the maps and presets", ok and Image.open(os.path.join(td, "skin_detail_normal.png")).size == (512, 512))
        parts = T.read_parts(SRC, "v0_")
        body = parts["body"]
        new = T.Part("vx_body", body.V, body.N, body.UV, body.J, body.W, body.F, "skin_test")
        png = open(os.path.join(td, "skin_detail_normal.png"), "rb").read()
        out = os.path.join(td, "o.glb")
        T.replace_parts(SRC, out, {"vx_": {"body": new}}, materials={"skin_test": {"image": "skin_test_img", "roughness": .5}},
                        images={"skin_test_img": png})
        j0, _ = read_glb(SRC)
        j1, _ = read_glb(out)
        m = next((x for x in j1["materials"] if x["name"] == "skin_test"), None)
        tex_ok = m is not None and "baseColorTexture" in m["pbrMetallicRoughness"]
        img = j1["textures"][m["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"] if tex_ok else -1
        rec("replace_parts adds a textured material for a new identity",
            tex_ok and j1["images"][img]["name"] == "skin_test_img" and len(j1["images"]) == len(j0["images"]) + 1
            and any(nd.get("name") == "vx_body" for nd in j1["nodes"]))
    import io
    eye = np.zeros((64, 64, 3), np.uint8)
    eye[:] = (225, 220, 215)                                  # sclera
    eye[16:32, 16:32] = (160, 55, 30)                         # red-brown iris
    eye[40:56, 40:56] = (60, 110, 190)                        # blue iris
    b = io.BytesIO()
    Image.fromarray(eye).save(b, "PNG")
    g = np.asarray(Image.open(io.BytesIO(SS.grade_iris(b.getvalue()))).convert("RGB")).astype(int)
    ir = g[24, 24]
    rec("grade_iris: red-brown iris -> brown, sclera and blue untouched",
        ir[0] < 140 and ir[1] / max(ir[0], 1) > .45 and np.abs(g[2, 2] - eye[2, 2]).max() <= 1
        and np.abs(g[48, 48] - eye[48, 48]).max() <= 1, "iris %s" % list(ir))
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
