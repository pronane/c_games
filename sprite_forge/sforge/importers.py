"""Import any supported rig / animation file -> normalized Rig + bone map + report (v6)."""
from __future__ import annotations
import os
from . import bonemap as BM

EXTS = {".fbx": "fbx", ".glb": "gltf", ".gltf": "gltf", ".sfrig": "sforge", ".obj": "obj"}


def load_file(path, report=None, use_fallback=True, orient="auto", dedupe="auto", blender=False):
    """-> (rig, bonemap_record, report).  FBX (binary/ASCII 7.x), glTF/GLB and OBJ (static) are read in pure Python;
    a .zip (e.g. a Meshy / Sketchfab download: FBX + textures/) is unpacked to a temp folder first.
    Other formats (.dae .3ds .blend ...) only through the optional trimesh fallback (static meshes).
    v7 clean-up: duplicate / LOD mesh removal (dedupe), orientation fix of the rest pose AND of every clip
    (orient), grounding; blender=True first runs tools/blender_cleanup.py (apply transforms, drop duplicates)."""
    report = report if report is not None else {}
    ext = os.path.splitext(path)[1].lower()
    report["file"] = os.path.basename(path)
    if ext == ".zip":
        import tempfile, shutil
        tmp = tempfile.mkdtemp(prefix="sfs_zip_")
        try:
            inner = unzip_model(path, tmp, report)
            rig, rec, rep = load_file(inner, report, use_fallback, orient, dedupe, blender)
            rig.meta["source_file"] = os.path.basename(path)
            return rig, rec, rep
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if blender:
        path = blender_cleanup(path, report)
        ext = os.path.splitext(path)[1].lower()
    kind = EXTS.get(ext)
    if kind == "fbx":
        from . import fbxread
        rig = fbxread.load(path, report); report["reader"] = "sforge FBX reader (%s)" % report.get("fbx_format")
    elif kind == "gltf":
        from . import gltfread
        rig = gltfread.load(path, report); report["reader"] = "sforge glTF reader"
    elif kind == "obj":
        rig = load_obj(path, report); report["reader"] = "sforge OBJ reader (static mesh)"
    elif use_fallback:
        rig = _fallback(path, report)
    else:
        raise ValueError("unsupported file type %s (FBX, GLB, glTF, OBJ, ZIP)" % ext)
    from . import cleanup
    cleanup.dedupe(rig, report, dedupe)
    rig.weld()
    rec = BM.detect(rig)
    if orient != "off":
        BM.orient(rig, rec, report)
        cleanup.fix_orientation(rig, rec, report, orient)
    else:
        rig.ground()
    report["convention"] = rec["convention"]; report["mapped"] = len(rec["map"])
    report["unmapped"] = rec["unmapped"]; report["missing"] = rec["missing"]
    report["height_m"] = round(rig.height(), 3)
    rig.meta.setdefault("source_file", os.path.basename(path))
    if report.get("cleanup"):
        rig.meta["import_cleanup"] = report["cleanup"]
    return rig, rec, report


def unzip_model(zpath, dest, report):
    """safe-extract a model zip; -> the main model file inside (FBX > GLB > glTF > OBJ, the largest of its kind)."""
    import zipfile
    best = None
    with zipfile.ZipFile(zpath) as z:
        for zi in z.infolist():
            n = zi.filename.replace("\\", "/")
            if zi.is_dir() or n.startswith("/") or ".." in n.split("/") or ":" in n:
                continue
            out = os.path.join(dest, *n.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(zi) as src, open(out, "wb") as dst:
                dst.write(src.read())
            e = os.path.splitext(n)[1].lower()
            rank = {".fbx": 4, ".glb": 3, ".gltf": 2, ".obj": 1}.get(e)
            if rank and not n.split("/")[-1].startswith("._"):
                k = (rank, zi.file_size)
                if best is None or k > best[0]:
                    best = (k, out)
    if best is None:
        raise ValueError("%s: no .fbx / .glb / .gltf / .obj inside the zip" % os.path.basename(zpath))
    report["zip"] = dict(file=os.path.basename(zpath), model=os.path.relpath(best[1], dest).replace(os.sep, "/"))
    return best[1]


def blender_cleanup(path, report):
    """optional: Blender applies object transforms, removes duplicate meshes and re-exports a GLB we then read."""
    import subprocess, tempfile, sys
    from .build import find_blender
    cmd = find_blender("")
    if not cmd:
        report.setdefault("warnings", []).append("--blender clean-up requested but no Blender / bpy found: pure-Python clean-up only")
        return path
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(here, "tools", "blender_cleanup.py")
    out = os.path.join(tempfile.mkdtemp(prefix="sfs_bl_"), os.path.splitext(os.path.basename(path))[0] + "_clean.glb")
    full = cmd + [script] + (["--"] if len(cmd) > 1 else []) + [path, out]
    r = subprocess.run(full, capture_output=True, text=True, timeout=600)
    if not os.path.isfile(out) or ("SFS_CLEANUP " not in r.stdout and r.returncode != 0):
        report.setdefault("warnings", []).append("Blender clean-up failed (%s): pure-Python clean-up only" % (r.stderr or r.stdout)[-300:])
        return path
    for ln in r.stdout.splitlines():
        if ln.startswith("SFS_CLEANUP "):
            import json
            report.setdefault("cleanup", {})["blender"] = json.loads(ln[12:])
    return out


def load_obj(path, report):
    """Wavefront OBJ (v / vt / f / usemtl / g / o) -> a static single-bone rig; groups become mesh parts."""
    import numpy as np
    from .rigrec import Rig
    V, VT, F, FT, FM, parts = [], [], [], [], [], []
    mats, mi, cur = [], 0, None
    for ln in open(path, encoding="utf-8", errors="replace"):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            V.append([float(x) for x in t[1:4]])
        elif t[0] == "vt":
            VT.append([float(x) for x in t[1:3]])
        elif t[0] in ("g", "o"):
            nm = " ".join(t[1:]) or "mesh"
            if parts and parts[-1]["f0"] == len(F):
                parts[-1]["name"] = nm
            else:
                parts.append(dict(name=nm, f0=len(F), f1=len(F)))
        elif t[0] == "usemtl":
            nm = " ".join(t[1:]) or "default"
            if nm not in mats:
                mats.append(nm)
            mi = mats.index(nm)
        elif t[0] == "f":
            vs = [int(x.split("/")[0]) for x in t[1:]]
            ts = [x.split("/") for x in t[1:]]
            vs = [v - 1 if v > 0 else len(V) + v for v in vs]
            tt = [(int(x[1]) - 1 if int(x[1]) > 0 else len(VT) + int(x[1])) if len(x) > 1 and x[1] else -1 for x in ts]
            for k in range(1, len(vs) - 1):
                F.append([vs[0], vs[k], vs[k + 1]]); FT.append([tt[0], tt[k], tt[k + 1]]); FM.append(mi)
            if not parts:
                parts.append(dict(name="mesh", f0=0, f1=0))
            parts[-1]["f1"] = len(F)
    r = Rig(os.path.splitext(os.path.basename(path))[0])
    r.bones = ["root"]; r.parent = np.array([-1]); r.bind = np.eye(4)[None]
    r.V = np.array(V, float).reshape(-1, 3); r.F = np.array(F, int).reshape(-1, 3)
    r.J = np.zeros((len(r.V), 4), int); r.W = np.zeros((len(r.V), 4)); r.W[:, 0] = 1
    r.fmat = np.array(FM, int); r.materials = [dict(name=m, color=[0.75, 0.75, 0.75]) for m in mats] or [dict(name="default", color=[0.75, 0.75, 0.75])]
    FTa = np.array(FT, int).reshape(-1, 3)
    if VT and (FTa >= 0).all():
        uv = np.array(VT, float); uv[:, 1] = 1.0 - uv[:, 1]          # OBJ v is up; glTF convention v=0 top
        r.fuv = uv[FTa]
    r.meta["mesh_parts"] = [p for p in parts if p["f1"] > p["f0"]]
    report["mesh"] = dict(tris=int(len(r.F)), verts=int(len(r.V)), groups=len(r.meta["mesh_parts"]))
    report.setdefault("warnings", []).append("OBJ: static mesh, no skeleton - use `forge.py autoskin` to bind it to a skeleton")
    return r


def _fallback(path, report):
    """static mesh via trimesh (pip) if installed -> single-bone rig.  Skeletons / animation are NOT read this way."""
    try:
        import trimesh
    except ImportError:
        raise ValueError("%s: only FBX / GLB / glTF are read natively; for other formats `pip install trimesh` "
                         "(static meshes only) or convert to GLB" % os.path.basename(path))
    import numpy as np
    from .rigrec import Rig
    sc = trimesh.load(path, force="mesh")
    r = Rig(os.path.splitext(os.path.basename(path))[0])
    r.bones = ["root"]; r.parent = np.array([-1]); r.bind = np.eye(4)[None]
    r.V = np.asarray(sc.vertices, float); r.F = np.asarray(sc.faces, int)
    r.J = np.zeros((len(r.V), 4), int); r.W = np.zeros((len(r.V), 4)); r.W[:, 0] = 1
    r.fmat = np.zeros(len(r.F), int); r.materials = [dict(name="default", color=[0.75, 0.75, 0.75])]
    report["reader"] = "trimesh fallback (static mesh, no skeleton)"
    report.setdefault("warnings", []).append("read with the trimesh fallback: static mesh only (no bones / animation)")
    return r
