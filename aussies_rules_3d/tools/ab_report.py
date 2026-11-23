#!/usr/bin/env python3
"""A/B report: shipped squad GLB vs the LOD candidate — Aussies Rules Motion A/B.

Compares public/assets/gaelic_player.glb (the file the game ships) against
tools/out/gaelic_player.lod.glb (the skinlod bake) and prints a markdown
comparison table. Writes machine-readable JSON to tools/out/ab_report.json.

Exit code: 1 if the candidate breaks the squad contract (skins / joints /
clips / nine looks / kit parts / clip parity / LOD material parity) — the CI
workflow turns that red. Everything else is reported, not gated.

    python3 tools/ab_report.py [original.glb] [lod.glb]
"""
from __future__ import annotations
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BASE_PARTS = ["body", "jersey", "shorts", "socks", "boots", "eyes", "lashes", "brows", "hair", "hairinner",
              "facialhair", "beardshell0", "beardshell1"]


def read_glb(path: str):
    d = open(path, "rb").read()
    assert d[:4] == b"glTF", "not a GLB: %s" % path
    L = struct.unpack("<I", d[12:16])[0]
    j = json.loads(d[20:20 + L])
    o = 20 + L
    bl = struct.unpack("<I", d[o:o + 4])[0]
    return j, bytes(d[o + 8:o + 8 + bl]), d


def tris_of_mesh(j, mi: int) -> int:
    total = 0
    for pr in j["meshes"][mi]["primitives"]:
        if "indices" in pr:
            total += j["accessors"][pr["indices"]]["count"]
        else:
            total += j["accessors"][pr["attributes"]["POSITION"]]["count"]
    return total // 3


def summarize(path: str) -> dict:
    j, buf, raw = read_glb(path)
    node_tris = {}
    for i, nd in enumerate(j["nodes"]):
        if "mesh" in nd:
            node_tris[nd.get("name", "")] = tris_of_mesh(j, nd["mesh"])
    base_tris = sum(t for n, t in node_tris.items() if "_lod" not in n)
    lod1_tris = sum(t for n, t in node_tris.items() if n.endswith("_lod1"))
    lod2_tris = sum(t for n, t in node_tris.items() if n.endswith("_lod2"))
    per_variant = {}
    for v in range(9):
        pre = "v%d_" % v
        per_variant[pre] = {
            "base": sum(t for n, t in node_tris.items() if n.startswith(pre) and "_lod" not in n),
            "lod1": sum(t for n, t in node_tris.items() if n.startswith(pre) and n.endswith("_lod1")),
            "lod2": sum(t for n, t in node_tris.items() if n.startswith(pre) and n.endswith("_lod2")),
            "full": sum(t for n, t in node_tris.items() if n.startswith(pre)),
        }
    clips = sorted(a.get("name") for a in j.get("animations", []))
    mat_of = {}
    for i, nd in enumerate(j["nodes"]):
        if "mesh" in nd:
            mat_of[nd.get("name", "")] = j["meshes"][nd["mesh"]]["primitives"][0].get("material")
    return {
        "path": path,
        "file": os.path.basename(path),
        "size_mb": round(len(raw) / 1048576, 2),
        "buffer_mb": round(len(buf) / 1048576, 2),
        "meshes": len(j.get("meshes", [])),
        "nodes": len(j.get("nodes", [])),
        "materials": len(j.get("materials", [])),
        "images": len(j.get("images", [])),
        "skins": len(j.get("skins", [])),
        "joints": len(j["skins"][0]["joints"]) if j.get("skins") else 0,
        "clips": clips,
        "tris_base": base_tris,
        "tris_lod1": lod1_tris,
        "tris_lod2": lod2_tris,
        "lod_nodes": sum(1 for n in node_tris if "_lod" in n),
        "per_variant": per_variant,
        "node_names": set(node_tris),
        "mat_of": mat_of,
    }


def fmt(n: int) -> str:
    return format(n, ",")


def main() -> int:
    orig = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "public", "assets", "gaelic_player.glb")
    cand = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "tools", "out", "gaelic_player.lod.glb")
    a, b = summarize(orig), summarize(cand)

    failures, notes = [], []

    # ---- hard contract gates
    for label, x, want in (("skins", b["skins"], 1), ("joints", b["joints"], 52), ("clips", len(b["clips"]), 32)):
        if x != want:
            failures.append("candidate %s = %s, expected %s" % (label, x, want))
    if a["clips"] != b["clips"]:
        only_a = sorted(set(a["clips"]) - set(b["clips"]))
        only_b = sorted(set(b["clips"]) - set(a["clips"]))
        failures.append("clip sets differ (missing in candidate: %s; extra: %s)" % (only_a, only_b))
    for v in range(9):
        pre = "v%d_" % v
        for part in BASE_PARTS:
            if pre + part in a["node_names"] and pre + part not in b["node_names"]:
                failures.append("candidate dropped base part %s%s" % (pre, part))
    # LOD nodes share their base part's material (runtime kit tinting depends on it)
    mat_mismatch = []
    for name, mat in b["mat_of"].items():
        if "_lod" not in name:
            continue
        i = name.rfind("_lod")
        base = name[:i]
        if base in b["mat_of"] and b["mat_of"][base] != mat:
            mat_mismatch.append(name)
    if mat_mismatch:
        failures.append("%d LOD node(s) use a different material than their base part: %s" % (
            len(mat_mismatch), ", ".join(sorted(mat_mismatch)[:5])))
    # candidate must actually carry LODs
    if b["lod_nodes"] == 0:
        failures.append("candidate carries no LOD nodes")

    # ---- report-only observations
    for v in range(9):
        pre = "v%d_" % v
        missing = [p for p in BASE_PARTS if pre + p in a["node_names"] and pre + p not in b["node_names"]]
        if missing:
            failures.append("candidate dropped part(s) %s (present in shipped asset)" % ", ".join(
                "%s%s" % (pre, p) for p in missing))

    def mb(x):
        return "%.1f MB" % x

    print("# Aussies Rules Motion A/B — squad GLB")
    print()
    print("| | shipped `gaelic_player.glb` | LOD candidate |")
    print("|---|---|---|")
    print("| file size | %s | %s |" % (mb(a["size_mb"]), mb(b["size_mb"])))
    print("| meshes | %d | %d |" % (a["meshes"], b["meshes"]))
    print("| nodes | %d | %d |" % (a["nodes"], b["nodes"]))
    print("| materials / images | %d / %d | %d / %d |" % (a["materials"], a["images"], b["materials"], b["images"]))
    print("| skins / joints | %d / %d | %d / %d |" % (a["skins"], a["joints"], b["skins"], b["joints"]))
    print("| clips | %d | %d |" % (len(a["clips"]), len(b["clips"])))
    print("| triangles (base look) | %s | %s |" % (fmt(a["tris_base"]), fmt(b["tris_base"])))
    print("| triangles (LOD1 / LOD2) | — | %s / %s |" % (fmt(b["tris_lod1"]), fmt(b["tris_lod2"])))
    print("| LOD nodes | 0 | %d |" % b["lod_nodes"])
    print()
    print("## Squad budget per look")
    print()
    print("| look | base | LOD1 | LOD2 | LOD2 vs base |")
    print("|---|---|---|---|---|")
    for v in range(9):
        pa, pb = a["per_variant"]["v%d_" % v], b["per_variant"]["v%d_" % v]
        pct = (pb["lod2"] / pb["base"] * 100) if pb["base"] else 0
        print("| v%d | %s | %s | %s | %.0f%% |" % (v, fmt(pb["base"]), fmt(pb["lod1"]), fmt(pb["lod2"]), pct))
    print("| **squad total** | **%s** | **%s** | **%s** | **%.0f%%** |" % (
        fmt(b["tris_base"]), fmt(b["tris_lod1"]), fmt(b["tris_lod2"]),
        100 * b["tris_lod2"] / max(1, b["tris_base"]),
    ))
    print()
    if notes:
        print("## Notes")
        print()
        for n in notes:
            print("- %s" % n)
        print()
    print("## Verdict")
    print()
    if failures:
        for f in failures:
            print("- ❌ %s" % f)
    else:
        print("- ✅ candidate preserves the squad contract (1 skin / 52 joints / 32 clips / nine looks / materials)")
        print("- ✅ LOD nodes present and tinted by the same materials as their base parts")
    if failures:
        print()
        print("Candidate is NOT shippable as-is.")

    out = {
        "original": {k: v for k, v in a.items() if k not in ("node_names", "mat_of")},
        "candidate": {k: v for k, v in b.items() if k not in ("node_names", "mat_of")},
        "failures": failures,
        "notes": notes,
    }
    os.makedirs(os.path.join(ROOT, "tools", "out"), exist_ok=True)
    report_path = os.path.join(ROOT, "tools", "out", "ab_report.json")
    with open(report_path, "w") as fh:
        json.dump(out, fh, indent=1)
    print()
    print("JSON report → `%s`" % report_path)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
