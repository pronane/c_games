#!/usr/bin/env python3
"""Mocap setup, same on Windows / Linux / macOS / MSYS2 - no curl, no manual Python install.

  python tools/setup_pose.py [--heavy] [--model-only]

1. finds a Python 3.12 / 3.11 / 3.10 (py launcher, PATH, or `uv python find`);
   if none exists it installs `uv` with pip and lets uv download a standalone Python 3.12
2. creates venv_pose/ next to forge.py and pip-installs requirements-pose.txt (mediapipe ...)
3. downloads the MediaPipe pose model(s) to models/ with urllib (Apache-2.0, ~9 MB full / ~30 MB heavy)
4. checks that `import mediapipe` works in venv_pose
"""
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_%s/float16/latest/pose_landmarker_%s.task"
WIN = os.name == "nt"
VENV = os.path.join(ROOT, "venv_pose")
PYDIR = os.path.join(ROOT, "python312")        # uv-downloaded Python 3.12 (only if none was found)
VPY = os.path.join(VENV, "Scripts", "python.exe") if WIN else os.path.join(VENV, "bin", "python")


def say(*a):
    print("[setup_pose]", *a); sys.stdout.flush()


def version_of(cmd):
    try:
        r = subprocess.run(cmd + ["-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def find_uv():
    u = shutil.which("uv")
    if u:
        return [u]
    if subprocess.run([sys.executable, "-m", "uv", "--version"], capture_output=True).returncode == 0:
        return [sys.executable, "-m", "uv"]
    return None


def find_base_python():
    env = os.environ.get("SFS_POSE_BASE_PY")
    if env:
        return [env]
    if sys.version_info[:2] in ((3, 12), (3, 11), (3, 10)):
        return [sys.executable]
    cands = []
    if WIN and shutil.which("py"):
        cands += [["py", "-3.12"], ["py", "-3.11"], ["py", "-3.10"]]
    for n in ("python3.12", "python3.11", "python3.10"):
        p = shutil.which(n)
        if p:
            cands.append([p])
    for c in cands:
        v = version_of(c)
        if v in ("3.12", "3.11", "3.10"):
            return c
    import glob
    for c in sorted(glob.glob(os.path.join(PYDIR, "*", "bin", "python3.1[0-2]")) + glob.glob(os.path.join(PYDIR, "*", "python.exe"))):
        if version_of([c]) in ("3.12", "3.11", "3.10"):
            return [c]
    uv = find_uv()
    if uv:
        r = subprocess.run(uv + ["python", "find", "3.12"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return [r.stdout.strip().splitlines()[-1]]
    return None


def main():
    heavy = "--heavy" in sys.argv
    if "--model-only" not in sys.argv:
        if os.path.isfile(VPY) and version_of([VPY]) in ("3.12", "3.11", "3.10"):
            say("venv_pose exists (%s)" % VPY)
        else:
            base = find_base_python()
            if base is None:
                say("no Python 3.10-3.12 found -> installing uv (pip) and a standalone Python 3.12 (~30 MB download)")
                uv = find_uv()
                if uv is None:
                    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "uv"])
                    if r.returncode != 0:
                        say("could not pip install uv - install Python 3.12 from python.org (Windows) or your package manager, then re-run")
                        return 1
                    uv = find_uv()
                # private copy inside the Studio folder (python312/), no shims in ~/.local/bin, no registry entries
                env = dict(os.environ); env.setdefault("UV_PYTHON_INSTALL_DIR", PYDIR)
                flags = ["--no-bin", "--no-registry"] if os.name == "nt" else ["--no-bin"]
                r = subprocess.run(uv + ["python", "install", "3.12"] + flags, env=env)
                if r.returncode != 0:      # older uv without --no-bin
                    r = subprocess.run(uv + ["python", "install", "3.12"], env=env)
                if r.returncode != 0:
                    say("uv python install 3.12 failed (offline?)"); return 1
                base = find_base_python()
                if base is None:
                    say("uv installed Python 3.12 but it was not found"); return 1
            say("base Python for mocap: %s (%s)" % (" ".join(base), version_of(base)))
            shutil.rmtree(VENV, ignore_errors=True)
            r = subprocess.run(base + ["-m", "venv", VENV])
            if r.returncode != 0 or not os.path.isfile(VPY):
                uv = find_uv()
                if uv is None:
                    say("venv creation failed (Debian/Ubuntu: sudo apt install python3.12-venv)"); return 1
                say("python -m venv failed -> uv venv --seed")
                if subprocess.run(uv + ["venv", "--seed", "--python", base[-1], VENV]).returncode != 0:
                    return 1
        r = subprocess.run([VPY, "-m", "pip", "install", "--disable-pip-version-check", "-r", os.path.join(ROOT, "requirements-pose.txt")])
        if r.returncode != 0:
            say("pip install mediapipe failed"); return 1
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    for name in (["full", "heavy"] if heavy else ["full"]):
        dst = os.path.join(ROOT, "models", "pose_landmarker_%s.task" % name)
        if os.path.isfile(dst) and os.path.getsize(dst) > 1_000_000:
            say("model present:", dst); continue
        say("downloading", URL % (name, name))
        tmp = dst + ".part"
        with urllib.request.urlopen(URL % (name, name), timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, dst)
        say("saved %s (%.1f MB)" % (dst, os.path.getsize(dst) / 1e6))
    if os.path.isfile(VPY):
        r = subprocess.run([VPY, "-c", "import mediapipe, sys; print('mediapipe', mediapipe.__version__, 'on Python', sys.version.split()[0])"],
                           capture_output=True, text=True)
        say(r.stdout.strip() or ("mediapipe import FAILED: " + r.stderr[-300:]))
        if r.returncode != 0:
            return 1
    say("mocap ready.  Try:  forge mocap --clip walk:8=examples_video/walk_static.mp4 --name mocap_demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
