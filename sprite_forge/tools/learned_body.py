#!/usr/bin/env python3
"""Learned-body tier (v9.4): a body reconstructed by a neural model (GPU) or a 3D tool -> a library rig every motion,
view and export can use.  photo3d's inflated body stays the CPU fallback.

    python tools/learned_body.py import MESH --name NAME [--library DIR]          # .obj / .glb / .gltf / .fbx / .ply
    python tools/learned_body.py run PHOTO --name NAME --cmd "TEMPLATE" [--library DIR]

import  any static or rigged humanoid mesh - from LHM / HumanNOVA-class single-image models, Meshy / Tripo / 3D AI Studio
        exports, a photogrammetry scan (forge.py scan) - is bound to the Sprite Forge skeleton (forge.py autoskin, bone
        distance weights) and registered as library rig NAME.  Then:
            forge.py build --rig NAME --preset fighter14 --yaw 35 ...      (sprites, consoles, GLB/FBX, game adapters)
        Tested here with a static GLB: 919 vertices bound to 18 bones, 3 moves built.
run     runs a reconstruction model on a GPU machine and imports what it writes.  --cmd is a shell template with
        {photo} and {out}, for example (check the model's own README for its current entry point):
            --cmd "python /opt/LHM/app.py --image {photo} --export_mesh {out}/body.ply"
        The newest mesh found under {out} is imported.  NOT run in the Sprite Forge test environment (no GPU there) -
        the import step it hands over to is the tested part.
Requirements for a good result: an A- or T-pose mesh, Y up, facing +Z, roughly 1.6-2.0 units tall (metres)."""
from __future__ import annotations
import argparse, glob, os, shlex, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(HERE, "forge.py")
MESH_EXT = (".obj", ".glb", ".gltf", ".fbx", ".ply")


def do_import(mesh, name, library=None):
    if os.path.splitext(mesh)[1].lower() == ".ply":         # autoskin reads OBJ / GLB / FBX: convert a PLY mesh
        mesh = ply_to_obj(mesh)
    cmd = [sys.executable, FORGE, "autoskin", mesh, "--name", name, "--redistribution", "no"]
    if library:
        cmd += ["--library", library]
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print("learned body -> library rig '%s'.  Next: forge.py build --rig %s%s --preset fighter14 --yaw 35 --out out"
              % (name, name, (" --library " + library) if library else ""))
    return r.returncode


def ply_to_obj(path):
    """minimal ASCII / binary-little-endian PLY (vertices + triangle faces) -> OBJ"""
    import numpy as np
    with open(path, "rb") as f:
        head = []
        while True:
            line = f.readline().decode("ascii", "replace").strip(); head.append(line)
            if line == "end_header":
                break
        fmt = next(l.split()[1] for l in head if l.startswith("format"))
        nv = int(next(l.split()[2] for l in head if l.startswith("element vertex")))
        nf = int(next((l.split()[2] for l in head if l.startswith("element face")), 0))
        props = []
        el = None
        for l in head:
            if l.startswith("element"):
                el = l.split()[1]
            elif l.startswith("property") and el == "vertex":
                props.append(l.split()[-1])
        if fmt == "ascii":
            V = np.array([list(map(float, f.readline().split()[:len(props)])) for _ in range(nv)])
            F = [list(map(int, f.readline().split()[1:4])) for _ in range(nf)]
        else:
            V = np.frombuffer(f.read(nv * 4 * len(props)), "<f4").reshape(nv, len(props)).astype(float)
            F = []
            for _ in range(nf):
                c = f.read(1)[0]; F.append(list(np.frombuffer(f.read(4 * c), "<i4"))[:3])
    xi, yi, zi = props.index("x"), props.index("y"), props.index("z")
    out = tempfile.mktemp(suffix=".obj")
    with open(out, "w") as o:
        for v in V:
            o.write("v %f %f %f\n" % (v[xi], v[yi], v[zi]))
        for t in F:
            o.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("import"); p.add_argument("mesh"); p.add_argument("--name", required=True); p.add_argument("--library")
    p = sp.add_parser("run"); p.add_argument("photo"); p.add_argument("--name", required=True); p.add_argument("--cmd", required=True)
    p.add_argument("--library"); p.add_argument("--work")
    a = ap.parse_args(argv)
    if a.cmd == "import":
        return do_import(a.mesh, a.name, a.library)
    work = a.work or tempfile.mkdtemp(prefix="sf_learned_")
    cmd = a.cmd.format(photo=shlex.quote(os.path.abspath(a.photo)), out=shlex.quote(work))
    print("running:", cmd)
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        print("the reconstruction command failed (exit %d)" % r.returncode); return r.returncode
    meshes = sorted((p for p in glob.glob(os.path.join(work, "**", "*"), recursive=True) if p.lower().endswith(MESH_EXT)),
                    key=os.path.getmtime)
    if not meshes:
        print("no mesh (%s) written under %s" % (", ".join(MESH_EXT), work)); return 1
    return do_import(meshes[-1], a.name, a.library)


if __name__ == "__main__":
    sys.exit(main())
