"""forge.py doctor - what is installed, where it came from, and what each missing piece disables."""
from __future__ import annotations
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ver(mod):
    try:
        m = importlib.import_module(mod)
        return getattr(m, "__version__", None) or getattr(m, "VERSION", None) or "yes"
    except Exception:
        return None


def _tk():
    try:
        import tkinter
        r = tkinter.Tcl().eval("info patchlevel")
        return r
    except Exception:
        return None


def tk_install_hint():
    if sys.platform.startswith("linux"):
        for mgr, cmd in (("apt-get", "sudo apt install python3-tk"), ("dnf", "sudo dnf install python3-tkinter"),
                         ("pacman", "sudo pacman -S tk"), ("zypper", "sudo zypper install python3-tk"), ("apk", "sudo apk add py3-tkinter")):
            if shutil.which(mgr):
                return cmd
        return "install your distro's python3-tk / tkinter package"
    if sys.platform == "darwin":
        return "brew install python-tk  (or use the python.org installer)"
    if os.environ.get("MSYSTEM"):
        return "pacman -S mingw-w64-ucrt-x86_64-tk  (or use the python.org Python, which includes tkinter)"
    return "re-run the python.org installer and tick 'tcl/tk and IDLE'"


def checks():
    from . import media
    rows = []

    def add(name, status, detail, disables, kind):
        rows.append({"name": name, "ok": bool(status), "detail": detail or "", "disables": "" if status else disables, "kind": kind})

    pv = sys.version.split()[0]
    add("Python", sys.version_info >= (3, 9), "%s (%s) %s" % (pv, sys.executable, "venv" if sys.prefix != sys.base_prefix else "system"),
        "everything - needs Python 3.9+", "required")
    for mod, label, dis, kind in (
            ("numpy", "numpy", "everything", "required"),
            ("PIL", "Pillow", "everything", "required"),
            ("scipy", "scipy", "mocap skeleton fit, cut-out clean-up, scan mesh clean-up (fallbacks are slower/rougher)", "core"),
            ("cv2", "opencv-python-headless", "scan stereo (scan --run dense), fast video cut-out (4x slower numpy fallback)", "core"),
            ("skimage", "scikit-image", "scan --run marching cubes", "core"),
            ("imageio_ffmpeg", "imageio-ffmpeg", "bundled ffmpeg binary (falls back to system ffmpeg / OpenCV decode)", "core"),
            ("pycolmap", "pycolmap", "scan --run without a COLMAP install (falls back to colmap CLI on PATH)", "extra"),
            ("trimesh", "trimesh", "scan --mesh for .stl/.dae/.gltf variants (OBJ/PLY/GLB work without it)", "extra"),
            ("fast_simplification", "fast-simplification", "quadric decimation for scan LODs (falls back to open3d, Blender, then vertex clustering)", "extra"),
            ("open3d", "open3d", "second quadric decimation backend (not needed if fast-simplification is installed)", "extra"),
            ("rembg", "rembg", "AI background removal for photos (built-in cut-out still works)", "extra"),
            ("av", "PyAV", "second video decoder fallback (not needed when imageio-ffmpeg is installed)", "extra")):
        v = _ver(mod)
        add(label, v is not None, str(v) if v else "not installed", dis, kind)
    tv = _tk()
    add("tkinter (GUI)", tv is not None, ("Tk %s" % tv) if tv else "missing - " + tk_install_hint(),
        "the visual Studio (run_studio); the CLI forge.py still works", "core")
    ff, src = media.ffmpeg_exe()
    vb = media.backend()
    fv = ""
    if ff:
        try:
            fv = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]
        except Exception:
            fv = "?"
    add("video decode/encode", vb is not None, "%s %s" % (vb or "none", ("- " + fv) if fv else ""),
        "video / mocap / scan --video modes, PHOTO --video moves", "core")
    add("slow-motion interpolation", ff is not None, "ffmpeg minterpolate" if ff else "needs an ffmpeg executable",
        "--slowmo (clips are analysed at normal speed)", "core")
    add("FBX export", True, "built-in pure-Python FBX 7.4 writer (sforge/fbx.py) - no Blender needed", "", "builtin")
    add("FBX / GLB import", True, "built-in pure-Python FBX 7.x (binary + ASCII) and glTF/GLB readers (sforge/fbxread.py, gltfread.py)", "", "builtin")
    try:
        from . import library as _L
        lib = _L.Library(); man = lib.scan(import_inbox=False, log=lambda s: None)[0]
        n = len(man.get("assets", [])); bad = [a["kind"] + "/" + a["name"] for a in man.get("assets", []) if not a.get("licence_ok")]
        inbox = [f for f in os.listdir(os.path.join(lib.dir, "inbox")) if os.path.isfile(os.path.join(lib.dir, "inbox", f))] \
            if os.path.isdir(os.path.join(lib.dir, "inbox")) else []
        add("library", n > 0, "%s: %d assets%s%s" % (lib.dir, n, ("; licence incomplete: " + ", ".join(bad[:5])) if bad else "",
                                                     ("; %d file(s) waiting in inbox/ (forge.py library scan)" % len(inbox)) if inbox else ""),
            "library rigs as templates (install packs/sfs_starter_cc0.sfpack: forge.py library install ...)", "core")
    except Exception as e:
        add("library", False, "error: %s" % e, "library rigs as templates", "core")
    from .scan import sfm_backend
    sb = sfm_backend()
    add("SfM for scan --run", sb is not None, {"pycolmap": "pycolmap %s (pip, CPU)" % _ver("pycolmap"), "colmap": "colmap CLI on PATH"}.get(sb, "none"),
        "forge.py scan --run (project prep and --mesh still work)", "extra")
    from .mocap import find_pose_python, find_model
    pp = find_pose_python(); pm = find_model("full")
    add("MediaPipe pose (mocap)", pp is not None, pp or "no Python with mediapipe - run: python tools/setup_pose.py",
        "forge.py mocap (video -> 3D animation)", "pose")
    add("pose model", pm is not None, pm or "models/pose_landmarker_full.task missing - run: python tools/setup_pose.py",
        "forge.py mocap", "pose")
    from .build import find_blender
    bl = find_blender("")
    add("Blender (optional)", bl is not None, " ".join(bl[:1]) if bl else "not found (not needed)",
        "only the optional --fbx-writer blender and Blender-based LOD decimation", "optional")
    gcc = shutil.which("gcc") or shutil.which("cc")
    add("C compiler (optional)", gcc is not None, gcc or "not found", "only the raylib C example in spriteforge/", "optional")
    ray = None
    for d in ("/usr/include", "/usr/local/include", "/opt/homebrew/include", os.path.join(os.environ.get("MSYS2", "C:/msys64"), "ucrt64", "include"),
              os.path.join(HERE, "spriteforge", "third_party", "raylib", "src")):
        if os.path.isfile(os.path.join(d, "raylib.h")):
            ray = d; break
    add("raylib (optional)", ray is not None, ray or "not found (make -C spriteforge raylib fetches + builds it)", "only the C example", "optional")
    try:
        from . import human as _H
        ha = _H.have_assets()
        add("MakeHuman assets (optional)", ha, _H.assets_dir() if ha else "not installed - run: python forge.py human --setup (~28 MB, CC0)",
            "MakeHuman mode (forge.py human / build --human) - builds fall back to the parametric mannequin", "optional")
    except Exception as e:
        add("MakeHuman assets (optional)", False, "error: %s" % e, "MakeHuman mode", "optional")
    return rows


def run(argv=()):
    as_json = "--json" in argv
    rows = checks()
    info = {"platform": platform.platform(), "python": sys.version.split()[0], "root": HERE, "checks": rows}
    if as_json:
        print(json.dumps(info, indent=1)); return 0
    print("Sprite Forge Studio doctor  -  %s  -  Python %s" % (info["platform"], info["python"]))
    print("%-27s %-7s %s" % ("component", "status", "details"))
    print("-" * 100)
    for r in rows:
        st = "OK" if r["ok"] else ("MISSING" if r["kind"] in ("required", "core") else "--")
        print("%-27s %-7s %s" % (r["name"], st, r["detail"]))
        if not r["ok"] and r["disables"]:
            print("%-27s %-7s   -> disables: %s" % ("", "", r["disables"]))
    req_bad = [r["name"] for r in rows if not r["ok"] and r["kind"] == "required"]
    core_bad = [r["name"] for r in rows if not r["ok"] and r["kind"] == "core"]
    print("-" * 100)
    if req_bad:
        print("NOT READY: missing %s  ->  run setup.bat (Windows) or ./setup.sh (Linux/macOS)" % ", ".join(req_bad))
        return 2
    print("READY: sprites, photo/spec builds, consoles, GLB + FBX export." +
          (" Missing core pieces: %s (see above)." % ", ".join(core_bad) if core_bad else " All core pieces present."))
    return 0
