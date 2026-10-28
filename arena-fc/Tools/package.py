#!/usr/bin/env python3
"""Create the distributable ZIP from this source tree.
Includes the full source, build scripts, docs, screenshots and (when present)
the ready-to-run web + Linux builds."""
from pathlib import Path
import zipfile, sys

ROOT = Path(__file__).resolve().parent.parent
DEST = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "ArenaFC.zip"
SKIP_DIRS = {".godot", "build", "bin", "obj", "__pycache__", ".cache", ".git",
             ".mypy_cache", ".vs", ".idea", "replays"}
SKIP_SUFFIX = {".pyc", ".tmp", ".part", ".log"}
INCLUDE_FILES = [
    "README.md", "TEST_REPORT.md", "ROADMAP.md", "ONLINE.md", "LICENSE.txt",
    "project.godot", "ArenaFC.csproj", "Dockerfile",
    "ArenaFC.sln", "export_presets.cfg", "icon.svg", "icon.svg.import",
    "build.sh", "build.bat", "run.sh", "run.bat", "selftest.sh", "selftest.bat",
    "run-server.sh", "run-server.bat",
]
INCLUDE_DIRS = ["Scenes", "Scripts", "Shaders", "Data", "Web", "Tests", "Tools",
                "Server", "Assets", "screenshots", "media"]

def add(zf: zipfile.ZipFile, src: Path, arc: str):
    zf.write(src, arc)

def main():
    with zipfile.ZipFile(DEST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in INCLUDE_FILES:
            p = ROOT / f
            if p.exists(): add(z, p, f"ArenaFC/{f}")
        for d in INCLUDE_DIRS:
            base = ROOT / d
            if not base.exists(): continue
            for p in sorted(base.rglob("*")):
                if not p.is_file(): continue
                if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts): continue
                if p.suffix in SKIP_SUFFIX: continue
                add(z, p, f"ArenaFC/{p.relative_to(ROOT).as_posix()}")
        # ready-to-run artefacts, if a build has been made
        web = ROOT / "build" / "web"
        if (web / "index.html").exists():
            for p in sorted(web.iterdir()):
                if p.is_file() and p.suffix != ".import":
                    add(z, p, f"ArenaFC/prebuilt/web/{p.name}")
        linux_dir = ROOT / "build" / "linux"
        if (linux_dir / "ArenaFC.x86_64").exists():
            # A Godot .NET Linux export needs BOTH the executable and its
            # data_<...> folder of .NET assemblies. Keep them together.
            for p in sorted(linux_dir.rglob("*")):
                if p.is_file():
                    add(z, p, f"ArenaFC/prebuilt/linux/{p.relative_to(linux_dir).as_posix()}")
            z.writestr("ArenaFC/prebuilt/linux/README.txt",
                       "Run: chmod +x ArenaFC.x86_64 && ./ArenaFC.x86_64\n"
                       "Keep the data_ArenaFC_linuxbsd_x86_64/ folder next to the executable.\n"
                       "Self test: ./ArenaFC.x86_64 --headless -- --selftest\n")
    print(f"Created {DEST} ({DEST.stat().st_size/1e6:.1f} MB)")
    with zipfile.ZipFile(DEST) as z:
        print(f"  {len(z.namelist())} files, compressed {sum(i.compress_size for i in z.infolist())/1e6:.1f} MB")

if __name__ == "__main__":
    main()
