#!/usr/bin/env python3
"""Zip the Studio for sharing (pure Python - no zip / rsync needed):
    python tools/make_release_zip.py OUT.zip [--max-mb 25] [--drop previews_v2,previews_v3]
Leaves out build outputs, virtual envs, downloaded models and caches. If the zip is larger than --max-mb it is
split into OUT.part1.zip, OUT.part2.zip ... (each a normal zip; extract all into the same folder)."""
import argparse, os, sys, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", ".venv", "venv_pose", "models", ".git", "third_party", "python312"}
SKIP_TOP = {"out", "out_scan", "out_video", "out_mocap", "out_test"}
SKIP_SUB = {os.path.join("spriteforge", "bin"), os.path.join("examples_raylib3d", "bin"), os.path.join("assets", "makehuman")}


def files(drop):
    for dp, dn, fn in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT)
        top = rel.split(os.sep)[0]
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not (rel == "." and (d in SKIP_TOP or d.startswith("out_") or d in drop))
                 and os.path.normpath(os.path.join(rel, d)) not in SKIP_SUB]
        for f in fn:
            if f.endswith((".pyc", ".zip")):
                continue
            yield os.path.normpath(os.path.join(rel, f))


def add(z, path, arc):
    if arc.endswith(".bat"):     # cmd.exe needs CRLF (LF-only batch files can break goto / labels)
        b = open(path, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        zi = zipfile.ZipInfo.from_file(path, arc); zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, b)
    elif arc.endswith(".sh"):    # and shell scripts need LF + the executable bit
        b = open(path, "rb").read().replace(b"\r\n", b"\n")
        zi = zipfile.ZipInfo.from_file(path, arc); zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = (0o100755 << 16); z.writestr(zi, b)
    else:
        z.write(path, arc)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--max-mb", type=float, default=25)
    ap.add_argument("--drop", default=""); ap.add_argument("--prefix", default="sprite_forge_studio")
    a = ap.parse_args(); drop = {d for d in a.drop.split(",") if d}
    fl = sorted(files(drop)); lim = a.max_mb * 1e6
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in fl:
            add(z, os.path.join(ROOT, f), a.prefix + "/" + f.replace(os.sep, "/"))
    sz = os.path.getsize(a.out)
    print("%s  %d files  %.1f MB" % (a.out, len(fl), sz / 1e6))
    if sz <= lim:
        return 0
    os.remove(a.out); base = a.out[:-4]; part, cur, z, parts = 1, 0, None, []
    for f in fl:
        p = os.path.join(ROOT, f); s = os.path.getsize(p)
        if z is None or cur + s > lim * 0.92:
            if z: z.close()
            parts.append("%s.part%d.zip" % (base, part)); z = zipfile.ZipFile(parts[-1], "w", zipfile.ZIP_DEFLATED, compresslevel=9); part += 1; cur = 0
        add(z, p, a.prefix + "/" + f.replace(os.sep, "/")); cur += s
    z.close()
    for p in parts:
        print("  %s  %.1f MB" % (p, os.path.getsize(p) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
