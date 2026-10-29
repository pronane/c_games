#!/usr/bin/env python3
"""Download + unpack raylib source (no git / curl needed):  python tools/fetch_raylib.py [VERSION] [DEST]
Then:  make -C DEST/raylib/src PLATFORM=PLATFORM_DESKTOP   and   make RAYLIB=DEST/raylib/src
Linux build deps (headers): Debian/Ubuntu  sudo apt install build-essential libx11-dev libxrandr-dev libxinerama-dev
  libxcursor-dev libxi-dev libgl1-mesa-dev ;  Fedora  sudo dnf install gcc make libX11-devel libXrandr-devel
  libXinerama-devel libXcursor-devel libXi-devel mesa-libGL-devel ;  Arch  sudo pacman -S base-devel libx11 libxrandr
  libxinerama libxcursor libxi mesa.   Easiest instead: apt/dnf/pacman package 'raylib' / MSYS2 mingw-w64-ucrt-x86_64-raylib."""
import io, os, shutil, sys, tarfile, urllib.request
ver = sys.argv[1] if len(sys.argv) > 1 else "5.5"
dest = sys.argv[2] if len(sys.argv) > 2 else "third_party"
url = "https://github.com/raysan5/raylib/archive/refs/tags/%s.tar.gz" % ver
os.makedirs(dest, exist_ok=True)
out = os.path.join(dest, "raylib")
if os.path.isfile(os.path.join(out, "src", "raylib.h")):
    print("raylib already in", out); sys.exit(0)
print("downloading", url)
data = urllib.request.urlopen(url, timeout=120).read()
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
    t.extractall(dest)
shutil.rmtree(out, ignore_errors=True)
os.rename(os.path.join(dest, "raylib-%s" % ver), out)
print("raylib %s -> %s  (%.1f MB download)" % (ver, out, len(data) / 1e6))
