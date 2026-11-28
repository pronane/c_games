#!/usr/bin/env python3
"""Report bind-space shorts hem geometry and skin weights in a self-contained GLB.

This is not a measurement of the animated, rendered mesh or shorts length.
The low-Y band is an approximate hem, split by the model's bind-space X axis.
"""
import argparse
import json
import math
import struct
from collections import defaultdict
from pathlib import Path


def load_glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise ValueError("truncated GLB")
    magic, version, total = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise ValueError("expected a complete GLB v2 file")
    chunks, pos = {}, 12
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated chunk header")
        size, kind = struct.unpack_from("<I4s", data, pos)
        pos += 8
        if pos + size > len(data):
            raise ValueError("truncated chunk")
        chunks[kind] = data[pos:pos + size]
        pos += size
    if b"JSON" not in chunks or b"BIN\0" not in chunks:
        raise ValueError("missing JSON or BIN chunk")
    return json.loads(chunks[b"JSON"]), chunks[b"BIN\0"]


def accessor(doc, blob, index):
    a = doc["accessors"][index]
    if "sparse" in a or "bufferView" not in a:
        raise ValueError("sparse or missing-buffer accessors are not supported")
    view = doc["bufferViews"][a["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("external buffers are not supported")
    components = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    code, maximum = {5121: ("B", 255), 5123: ("H", 65535), 5126: ("f", 1)}[a["componentType"]]
    fmt = "<" + code * components
    item_size = struct.calcsize(fmt)
    stride = view.get("byteStride", item_size)
    offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    end = offset + max(0, a["count"] - 1) * stride + item_size
    if stride < item_size or end > len(blob) or end > view.get("byteOffset", 0) + view["byteLength"]:
        raise ValueError("invalid accessor bounds")
    rows = [struct.unpack_from(fmt, blob, offset + k * stride) for k in range(a["count"])]
    if a.get("normalized") and maximum != 1:
        rows = [tuple(v / maximum for v in row) for row in rows]
    return rows


def inspect(doc, blob, band):
    results = []
    for node in doc["nodes"]:
        if "mesh" not in node or "skin" not in node:
            continue
        mesh = doc["meshes"][node["mesh"]]
        if "shorts" not in mesh.get("name", "").lower():
            continue
        joints = doc["skins"][node["skin"]]["joints"]
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            points = accessor(doc, blob, attrs["POSITION"])
            ids = accessor(doc, blob, attrs["JOINTS_0"])
            weights = accessor(doc, blob, attrs["WEIGHTS_0"])
            if not points or len(points) != len(ids) or len(points) != len(weights):
                raise ValueError("inconsistent shorts vertex attributes")
            if any(not math.isfinite(value) for point in points for value in point):
                raise ValueError("non-finite vertex position")
            side_results = {}
            for side, sign in (("positive_x", 1), ("negative_x", -1)):
                candidates = [k for k, p in enumerate(points) if p[0] * sign > 0]
                if not candidates:
                    raise ValueError("shorts mesh has no vertices on one side")
                min_y = min(points[k][1] for k in candidates)
                hem = [k for k in candidates if points[k][1] <= min_y + band]
                influence = defaultdict(float)
                for k in hem:
                    for bone, weight in zip(ids[k], weights[k]):
                        if not math.isfinite(weight) or weight < 0 or bone >= len(joints):
                            raise ValueError("invalid skin weight or joint index")
                        if weight:
                            name = doc["nodes"][joints[bone]].get("name", str(bone))
                            influence[name] += weight / len(hem)
                side_results[side] = {
                    "vertices": len(hem), "minimum_y_m": round(min_y, 6),
                    "mean_influence": {k: round(v, 6) for k, v in sorted(influence.items(), key=lambda x: -x[1])},
                }
            results.append({"mesh": mesh["name"], "hem": side_results})
    if not results:
        raise ValueError("no skinned shorts meshes found")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--band", type=float, default=.025, help="height above each side's lowest vertex in metres")
    args = parser.parse_args()
    if not 0 < args.band <= .1:
        parser.error("band must be greater than 0 and at most 0.1 metres")
    doc, blob = load_glb(args.model)
    print(json.dumps({"model": str(args.model), "band_m": args.band,
                      "limitation": "bind-space approximation only, not rendered deformation",
                      "shorts": inspect(doc, blob, args.band)}, indent=2))


if __name__ == "__main__":
    main()
