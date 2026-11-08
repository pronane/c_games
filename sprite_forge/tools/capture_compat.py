#!/usr/bin/env python3
"""Does a `forge.py capture` character open everywhere? Checks it with other people's tools (v11.1, optional).

    python tools/capture_compat.py OUT_DIR NAME [--blender PATH] [--godot PATH] [--node-tools DIR]

  Khronos glTF-Validator   the reference validator for glTF 2.0 (npm gltf-validator): errors / warnings in NAME.glb
  Assimp                   the Open Asset Import Library (npm assimpjs, the same C++ code compiled to WASM) loads the
                           GLB, FBX and OBJ: meshes, UVs, skinned bones, animations, texture reference
  Godot 4                  headless import of NAME.glb and NAME.fbx (Godot's FBX importer is ufbx): skeleton bones,
                           animations, textured material
  Blender                  Blender's own glTF / FBX / OBJ importers (tools/capture_check_blender.py) and a saved
                           NAME.blend (tools/capture_makehuman_blender.py)
  MakeHuman (MPFB2)        NAME.mhm loaded by MPFB2's .mhm importer: the human MakeHuman builds from it is compared
                           vertex by vertex with Sprite Forge's own body; saved as NAME_makehuman.blend
Missing tools are reported as skipped. Writes OUT_DIR/COMPAT.md + compat.json."""
from __future__ import annotations
import argparse
import json
import os
import pickle
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def run(cmd, cwd=None, timeout=900):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def khronos(node_dir, glb):
    js = os.path.join(node_dir, "validate.mjs")
    if not os.path.isfile(js):
        return dict(skipped="node tools not installed")
    out = run(["node", js, glb], cwd=node_dir)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:                                           # noqa: BLE001
        return dict(error=out[-400:])


def assimp(node_dir, files):
    js = os.path.join(node_dir, "assimp_check.mjs")
    if not os.path.isfile(js):
        return dict(skipped="node tools not installed")
    out = run(["node", js] + files, cwd=node_dir)
    res = {}
    for line in out.splitlines():
        if line.startswith("{"):
            d = json.loads(line); res[d["file"]] = d
    return res


def godot(godot_bin, glb, fbx, work):
    if not godot_bin or not os.path.isfile(godot_bin):
        return dict(skipped="Godot not found")
    os.makedirs(work, exist_ok=True)
    open(os.path.join(work, "project.godot"), "w").write('config_version=5\n[application]\nconfig/name="capture_check"\n')
    open(os.path.join(work, "check.gd"), "w").write(GD)
    for src, dst in ((glb, "model.glb"), (fbx, "model.fbx")):
        if src and os.path.isfile(src):
            shutil.copy(src, os.path.join(work, dst))
    run([godot_bin, "--headless", "--path", work, "--import"], timeout=600)
    out = run([godot_bin, "--headless", "--path", work, "-s", "check.gd"], timeout=600)
    res = {}
    for line in out.splitlines():
        if line.startswith("GODOT "):
            _, f, rest = line.split(" ", 2)
            res[f] = json.loads(rest) if rest.startswith("{") else rest
    return res


GD = '''extends SceneTree
func _walk(n, acc):
	if n is Skeleton3D: acc["bones"] = max(acc["bones"], n.get_bone_count())
	if n is MeshInstance3D:
		acc["meshes"] += 1
		var m = n.get_active_material(0)
		if m is StandardMaterial3D and m.albedo_texture: acc["textured"] += 1
	if n is AnimationPlayer: acc["anims"] = max(acc["anims"], n.get_animation_list().size())
	for c in n.get_children(): _walk(c, acc)
func _init():
	for f in ["model.glb", "model.fbx"]:
		if not FileAccess.file_exists("res://" + f): continue
		var ps = load("res://" + f)
		if ps == null:
			print("GODOT ", f, " load-failed"); continue
		var acc = {"bones": 0, "meshes": 0, "anims": 0, "textured": 0}
		_walk(ps.instantiate(), acc)
		print("GODOT ", f, " ", JSON.stringify(acc))
	quit()
'''


def blender(blender_bin, out_dir, name):
    if not blender_bin or not os.path.isfile(blender_bin):
        return dict(skipped="Blender not found")
    res = {}
    for script, args in (("capture_check_blender.py", ["--frames", "idle:0,walk:8,kick:12"]),
                         ("capture_makehuman_blender.py", [])):
        out = run([blender_bin, "-b", "-P", os.path.join(HERE, "tools", script), "--", out_dir, name] + args, timeout=1800)
        for line in out.splitlines():
            if line.startswith("CHECK {"):
                d = json.loads(line[6:])
                if "kind" in d:
                    res[d["kind"]] = d
                else:
                    res.update(d)
    return res


def mpfb_vertices(out_dir, name, captures_dir):
    """MakeHuman's (MPFB2's) build of NAME.mhm vs Sprite Forge's body, same proportions and stature"""
    p = os.path.join(out_dir, name + "_mpfb_vertices.npy")
    fit = os.path.join(captures_dir, "fit.pkl")
    if not (os.path.isfile(p) and os.path.isfile(fit)):
        return dict(skipped="no MPFB vertices / fit")
    from sforge import capture_body as CB
    bm = CB.BodyModel()
    fp = pickle.load(open(fit, "rb"))
    rep = json.load(open(os.path.join(out_dir, "report.json"))) if os.path.isfile(os.path.join(out_dir, "report.json")) else {}
    H = rep.get("height_m") or fp.get("height_m") or 1.75
    ours = bm.shape(fp["mac"], fp["sl"], H).V
    M = np.load(p)[bm.used_v]
    M = M - [0.5 * (M[:, 0].min() + M[:, 0].max()), M[:, 1].min(), 0]
    d = np.linalg.norm((ours - ours.mean(0)) - (M - M.mean(0)), axis=1) * 1000
    return dict(height_ours_m=round(float(np.ptp(ours[:, 1])), 4), height_makehuman_m=round(float(np.ptp(M[:, 1])), 4),
                vertex_mm_mean=round(float(d.mean()), 2), vertex_mm_p95=round(float(np.percentile(d, 95)), 2),
                vertex_mm_max=round(float(d.max()), 2))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir"); ap.add_argument("name")
    ap.add_argument("--blender", default=os.environ.get("SFS_BLENDER"))
    ap.add_argument("--godot", default=os.environ.get("SFS_GODOT"))
    ap.add_argument("--node-tools", default=os.environ.get("SFS_NODE_TOOLS", ""))
    a = ap.parse_args(argv)
    d, n = a.out_dir, a.name
    f = lambda ext: os.path.join(d, n + ext)
    res = {"khronos_gltf_validator": khronos(a.node_tools, f(".glb")),
           "assimp": assimp(a.node_tools, [f(".glb"), f(".fbx"), f(".obj")]),
           "godot": godot(a.godot, f(".glb"), f(".fbx"), os.path.join(d, "_godot_check")),
           "blender": blender(a.blender, d, n)}
    res["makehuman_vs_sprite_forge"] = mpfb_vertices(d, n, os.path.dirname(os.path.abspath(d)))
    shutil.rmtree(os.path.join(d, "_godot_check"), ignore_errors=True)
    json.dump(res, open(os.path.join(d, "compat.json"), "w"), indent=1)
    L = ["# %s - compatibility with other tools" % n, ""]
    k = res["khronos_gltf_validator"]
    if "numErrors" in k:
        L.append("- Khronos glTF-Validator: %d errors, %d warnings (%s triangles, %s animations, skinned: %s)" % (
            k["numErrors"], k["numWarnings"], k["info"]["tris"], k["info"]["anim"], k["info"]["skins"]))
    for fn, v in (res["assimp"] or {}).items():
        if isinstance(v, dict) and "ok" in v:
            L.append("- Assimp %s: %s, %d mesh(es), %d vertices, UVs %s, %d skinned bones, %d animations, texture %s" % (
                fn, "loads" if v["ok"] else "FAILS", v.get("meshes", 0), v.get("verts", 0), v.get("uv"), v.get("skinned_bones", 0),
                v.get("animations", 0), v.get("texture_ref")))
    for fn, v in (res["godot"] or {}).items():
        if isinstance(v, dict) and "bones" in v:
            L.append("- Godot 4 %s: %d bones, %d meshes, %d animations, textured %s" % (fn, v["bones"], v["meshes"], v["anims"], v["textured"] > 0))
    b = res["blender"]
    for kind in ("glb", "fbx", "obj"):
        if kind in b and isinstance(b[kind], dict):
            v = b[kind]
            L.append("- Blender import %s: %s" % (kind.upper(), v.get("error") or "%d meshes, %d bones, %d actions, height %.2f m, texture %s" % (
                v.get("meshes", 0), v.get("bones", 0), len(v.get("actions", [])), v.get("height", 0), v.get("texture"))))
    if "blender" in b and isinstance(b["blender"], dict):
        L.append("- Blender .blend saved: %s (vertex groups match bones: %s)" % (b["blender"].get("blend"), b["blender"].get("vertex_groups_match_bones")))
    if "makehuman" in b and isinstance(b["makehuman"], dict):
        v = b["makehuman"]
        L.append("- MakeHuman (MPFB2) loads %s.mhm: %s, %s shape keys, MakeHuman rig %s bones, saved %s" % (
            n, v.get("loaded_mhm"), v.get("shape_keys"), v.get("rig_bones"), v.get("blend")))
    m = res["makehuman_vs_sprite_forge"]
    if "vertex_mm_mean" in m:
        L.append("- MakeHuman's build of the .mhm vs Sprite Forge's body: %.1f mm mean, %.1f mm max per vertex; stature %.3f vs %.3f m" % (
            m["vertex_mm_mean"], m["vertex_mm_max"], m["height_makehuman_m"], m["height_ours_m"]))
    open(os.path.join(d, "COMPAT.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
