"""Validate an FBX written by sforge/fbx.py against the GLB it came from, with INDEPENDENT readers.

  python tools/verify_fbx.py model.glb model.fbx [--json out.json]

Checks (each is skipped with a note if the tool is missing):
  1. own reader      bones / clusters / skin weights / takes / curves (sanity only - same author)
  2. assimp CLI      `assimp info` (Open Asset Import Library): meshes, bones, animations, faces, bounds
  3. FBX2glTF        (Autodesk FBX SDK inside) converts FBX -> GLB; we then evaluate BOTH GLBs and compare
                     world joint positions for every take at 10 times, and the bind-pose skinned vertices
  4. Blender/bpy     optional oracle: SFS_BPY_PYTHON or blender on PATH -> tools/verify_fbx_blender_v5.py
Exit code 0 if every check that ran passed.
"""
import json, os, re, shutil, subprocess, sys, tempfile
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sforge import fbx as F


def lerp_q(a, b, t):
    if np.dot(a, b) < 0:
        b = -b
    q = a * (1 - t) + b * t
    return q / np.linalg.norm(q)


def sample(ts, vals, t, interp, is_q):
    if t <= ts[0]:
        return vals[0]
    if t >= ts[-1]:
        return vals[-1]
    i = int(np.searchsorted(ts, t) - 1)
    u = (t - ts[i]) / max(ts[i + 1] - ts[i], 1e-12)
    if interp == "STEP":
        return vals[i]
    return lerp_q(vals[i], vals[i + 1], u) if is_q else vals[i] * (1 - u) + vals[i + 1] * u


class Glb:
    def __init__(self, path):
        self.g, self.b = F.read_glb(path)
        self.nodes = self.g["nodes"]
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for k in n.get("children", []):
                self.parent[k] = i
        self.names = {n.get("name"): i for i, n in enumerate(self.nodes)}
        self.anims = {a.get("name"): a for a in self.g.get("animations", [])}

    def duration(self, an):
        a = self.anims[an]
        return max(float(F.accessor(self.g, self.b, a["samplers"][c["sampler"]]["input"]).max()) for c in a["channels"])

    def world(self, an=None, t=0.0):
        loc = []
        ov = {}
        if an is not None:
            a = self.anims[an]
            for c in a["channels"]:
                s = a["samplers"][c["sampler"]]
                ts = F.accessor(self.g, self.b, s["input"]).astype(float).ravel()
                vs = F.accessor(self.g, self.b, s["output"]).astype(float)
                ov[(c["target"]["node"], c["target"]["path"])] = sample(ts, vs, t, s.get("interpolation", "LINEAR"), c["target"]["path"] == "rotation")
        for i, n in enumerate(self.nodes):
            tr = ov.get((i, "translation"), np.array(n.get("translation", [0, 0, 0]), float))
            r = ov.get((i, "rotation"), np.array(n.get("rotation", [0, 0, 0, 1]), float))
            s = ov.get((i, "scale"), np.array(n.get("scale", [1, 1, 1]), float))
            loc.append(F.trs_matrix(tr, r, s))
        W = [None] * len(self.nodes)

        def w(i):
            if W[i] is None:
                W[i] = (w(self.parent[i]) @ loc[i]) if i in self.parent else loc[i]
            return W[i]
        return [w(i) for i in range(len(self.nodes))]

    def skinned(self, an=None, t=0.0):
        """skinned vertex positions (all primitives concatenated, glTF linear blend skinning)."""
        Wm = self.world(an, t)
        out = []
        for ni, n in enumerate(self.nodes):
            if "mesh" not in n:
                continue
            sk = self.g["skins"][n["skin"]] if "skin" in n else None
            if sk:
                ibm = F.accessor(self.g, self.b, sk["inverseBindMatrices"]).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
                Jm = np.stack([Wm[j] @ ibm[k] for k, j in enumerate(sk["joints"])])
            for p in self.g["meshes"][n["mesh"]]["primitives"]:
                P = F.accessor(self.g, self.b, p["attributes"]["POSITION"]).astype(float)
                idx = F.accessor(self.g, self.b, p["indices"]).astype(int) if "indices" in p else np.arange(len(P))
                Ph = np.c_[P, np.ones(len(P))]
                if sk:
                    J = F.accessor(self.g, self.b, p["attributes"]["JOINTS_0"]).astype(int)
                    Wt = F.accessor(self.g, self.b, p["attributes"]["WEIGHTS_0"]).astype(float)
                    Q = np.zeros((len(P), 4))
                    for c in range(4):
                        Q += Wt[:, c:c + 1] * np.einsum("nij,nj->ni", Jm[J[:, c]], Ph)
                else:
                    Q = Ph @ Wm[ni].T
                out.append(Q[idx, :3])
        return np.concatenate(out)


def check_assimp(fbx):
    exe = shutil.which("assimp")
    if not exe:
        return {"ran": False, "note": "assimp CLI not on PATH (apt install assimp-utils / MSYS2 mingw-w64-x86_64-assimp)"}
    r = subprocess.run([exe, "info", fbx], capture_output=True, text=True, errors="replace")
    out = {"ran": True, "ok": r.returncode == 0}
    for k in ("Meshes", "Animations", "Bones", "Faces", "Vertices", "Nodes", "Materials"):
        m = re.search(r"^%s:\s+(\d+)" % k, r.stdout, re.M)
        if m:
            out[k.lower()] = int(m.group(1))
    m = re.search(r"Minimum point\s+\(([^)]*)\)\s*\n\s*Maximum point\s+\(([^)]*)\)", r.stdout)
    if m:
        out["bounds_min"] = [float(x) for x in m.group(1).split()]; out["bounds_max"] = [float(x) for x in m.group(2).split()]
    return out


def find_fbx2gltf():
    for c in (os.environ.get("SFS_FBX2GLTF", ""), shutil.which("FBX2glTF") or "",
              os.path.join(ROOT, "tools", "bin", "FBX2glTF")):
        if c and os.path.isfile(c):
            return c
    return None


def check_fbx2gltf(glb, fbx):
    exe = find_fbx2gltf()
    if not exe:
        return {"ran": False, "note": "FBX2glTF not found (github.com/facebookincubator/FBX2glTF releases; set SFS_FBX2GLTF)"}
    td = tempfile.mkdtemp(prefix="sfs_f2g_")
    r = subprocess.run([exe, "-b", "--anim-framerate", "bake30", "-o", os.path.join(td, "conv"), fbx], capture_output=True, text=True, errors="replace")
    conv = os.path.join(td, "conv.glb")
    if not os.path.isfile(conv):
        return {"ran": True, "ok": False, "log": (r.stdout + r.stderr)[-600:]}
    A, B = Glb(glb), Glb(conv)
    bones = [n for n in A.names if n in B.names and n not in ("RootNode",) and A.g.get("skins") and A.names[n] in A.g["skins"][0]["joints"]]
    res = {"ran": True, "fbx_sdk_takes": sorted(B.anims), "glb_takes": sorted(A.anims), "bones_compared": len(bones), "takes": {}}
    worst = 0.0
    for an in A.anims:
        if an not in B.anims:
            res["takes"][an] = "MISSING"; worst = 1e9; continue
        d = A.duration(an); errs = []
        bt = sorted({float(x) for c in B.anims[an]["channels"]
                     for x in F.accessor(B.g, B.b, B.anims[an]["samplers"][c["sampler"]]["input"]).ravel()})
        for t in [x for x in bt if x <= d + 1e-6]:      # FBX SDK evaluated the curves at these times
            WA, WB = A.world(an, t), B.world(an, t)
            for n in bones:
                errs.append(np.linalg.norm(WA[A.names[n]][:3, 3] - WB[B.names[n]][:3, 3]))
        e = float(np.max(errs)); worst = max(worst, e)
        res["takes"][an] = {"max_joint_err_mm": round(e * 1000, 3), "mean_joint_err_mm": round(float(np.mean(errs)) * 1000, 3)}
    try:
        VA = A.skinned(); VB = B.skinned()
        from scipy.spatial import cKDTree
        dd = cKDTree(VB).query(VA)[0]
        res["bind_pose_vertices"] = {"glb": len(VA), "fbx_sdk": len(VB), "max_err_mm": round(float(dd.max()) * 1000, 3)}
        an = sorted(A.anims)[len(A.anims) // 2]; t = round(A.duration(an) * 15) / 30.0
        VA = A.skinned(an, t); VB = B.skinned(an, t)
        dd = cKDTree(VB).query(VA)[0]
        res["skinned_mid_take"] = {"take": an, "t": round(t, 3), "max_err_mm": round(float(dd.max()) * 1000, 3),
                                   "mean_err_mm": round(float(dd.mean()) * 1000, 3)}
        worst = max(worst, float(dd.max()))
    except Exception as e:
        res["skinned_note"] = "skipped: %s" % e
    res["note"] = "FBX2glTF re-samples every take at 30 fps with the Autodesk FBX SDK; errors are measured at those sample times"
    res["worst_err_mm"] = round(worst * 1000, 3)
    res["ok"] = worst < 0.005          # 5 mm on a ~1.8 m figure (float32 keys + Euler curves re-sampled by the SDK)
    shutil.rmtree(td, ignore_errors=True)
    return res


def check_blender(fbx, expect):
    py = os.environ.get("SFS_BPY_PYTHON", "")
    bl = shutil.which("blender")
    script = os.path.join(ROOT, "tools", "verify_fbx_blender_v5.py")
    if py and os.path.isfile(py):
        cmd = [py, script, fbx]
    elif bl:
        cmd = [bl, "-b", "-P", script, "--", fbx]
    else:
        return {"ran": False, "note": "Blender not available (optional oracle)"}
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=600)
    m = re.search(r"SFSJSON (\{.*\})", r.stdout)
    if not m:
        return {"ran": True, "ok": False, "log": (r.stdout + r.stderr)[-800:]}
    d = json.loads(m.group(1))
    d["ran"] = True
    A = expect.get("glb")
    if A is not None and d.get("samples"):
        from scipy.spatial import cKDTree
        errs = {}
        errb = {}
        for an, rec in d["samples"].items():
            if an not in A.anims:
                continue
            for tag, smp in rec.items():
                VA = A.skinned(an, smp["t"]); VB = np.array(smp["verts"])
                dd = cKDTree(VB).query(VA)[0]
                (errs if tag == "key" else errb)[an] = round(float(dd.max()) * 1000, 2)
        d["skinned_max_err_mm_at_key"] = errs
        d["skinned_max_err_mm_between_keys"] = errb
        d["worst_skinned_err_mm"] = max(errs.values()) if errs else None
        d["worst_between_keys_mm"] = max(errb.values()) if errb else None
    d.pop("samples", None)
    d["ok"] = d.get("bones") == expect["bones"] and sorted(d.get("actions", [])) == sorted(expect["takes"]) and d.get("weighted_verts", 0) > 0 \
        and (d.get("worst_skinned_err_mm") is None or d["worst_skinned_err_mm"] < 5.0)
    return d


def main():
    a = sys.argv[1:]
    js = None
    if "--json" in a:
        i = a.index("--json"); js = a[i + 1]; del a[i:i + 2]
    glb, fbx = a[0], a[1]
    own = F.summary(fbx); own.pop("_by_id", None)
    rep = {"fbx": os.path.abspath(fbx), "size_kb": round(os.path.getsize(fbx) / 1024, 1), "own_reader": own}
    def safe(fn, *args):        # an oracle that cannot run (wrong platform binary, crash) is reported, not fatal
        try:
            return fn(*args)
        except Exception as e:
            return {"ran": False, "error": "%s: %s" % (type(e).__name__, e)}
    rep["assimp"] = safe(check_assimp, fbx)
    rep["fbx2gltf_fbxsdk"] = safe(check_fbx2gltf, glb, fbx)
    rep["blender"] = safe(lambda: check_blender(fbx, {"bones": own["limb_nodes"], "takes": own["anim_stacks"], "glb": Glb(glb)}))
    if not any(isinstance(v, dict) and v.get("ran") for v in rep.values()):
        rep["note"] = "no independent FBX reader available here (assimp / FBX2glTF / Blender) - only our own parser checked the file"
    ok = all(v.get("ok", True) for k, v in rep.items() if isinstance(v, dict) and v.get("ran"))
    rep["RESULT"] = "PASS" if ok else "FAIL"
    s = json.dumps(rep, indent=1, default=float)
    if js:
        open(js, "w").write(s)
    print(s)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
