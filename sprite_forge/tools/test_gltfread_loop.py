#!/usr/bin/env python3
"""gltfread.load(..., loop_overrides={...}) wins over the name keyword heuristic.

The default loop flag guesses 'locomotion-ish' from keywords
(idle/walk/run/jog/sprint/loop/cycle/drive). Cycle clips with unrelated names
('solo', 'keeper_ready') load as non-looping; callers with ground truth can
now force the flag explicitly.
"""
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from sforge import gltfread  # noqa: E402


def write_glb(path, doc, buf: bytes):
    js = json.dumps(doc, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    while len(buf) % 4:
        buf += b"\x00"
    data = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf))
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(buf), 0x004E4942) + buf)
    with open(path, "wb") as f:
        f.write(data)


def build_glb(path, clip_name="solo"):
    times = np.array([0.0, 0.5, 1.0], np.float32)
    rots = np.tile(np.array([0.0, 0.0, 0.0, 1.0], np.float32), (3, 1))
    buf = bytearray()

    def add(arr, ctype, typ):
        while len(buf) % 4:
            buf.append(0)
        view = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(arr.tobytes())}
        buf.extend(arr.tobytes())
        doc_views.append(view)
        acc = {"bufferView": len(doc_views) - 1, "componentType": ctype, "type": typ,
               "count": int(len(arr)), "min": [float(arr.min())], "max": [float(arr.max())]} if typ == "SCALAR" else \
              {"bufferView": len(doc_views) - 1, "componentType": ctype, "type": typ, "count": int(len(arr))}
        doc_accs.append(acc)
        return len(doc_accs) - 1

    doc_views, doc_accs = [], []
    t_acc = add(times, 5126, "SCALAR")
    r_acc = add(rots, 5126, "VEC4")
    doc = {
        "asset": {"version": "2.0", "generator": "test_gltfread_loop fixture"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "pelvis"}],
        "animations": [{
            "name": clip_name,
            "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}],
            "samplers": [{"input": t_acc, "output": r_acc, "interpolation": "LINEAR"}],
        }],
        "accessors": doc_accs,
        "bufferViews": doc_views,
        "buffers": [{"byteLength": len(buf)}],
    }
    write_glb(path, doc, bytes(buf))


def main():
    tmp = tempfile.mkdtemp(prefix="gltfread_loop_")
    path = os.path.join(tmp, "fixture.glb")
    build_glb(path, "solo")

    default = gltfread.load(path)
    assert default.clips["solo"].loop is False, "keyword heuristic must stay the default"

    forced = gltfread.load(path, loop_overrides={"solo": True})
    assert forced.clips["solo"].loop is True

    forced_ci = gltfread.load(path, loop_overrides={"SOLO": True})
    assert forced_ci.clips["solo"].loop is True, "override keys match case-insensitively"

    forced_off = gltfread.load(path, loop_overrides={"solo": False})
    assert forced_off.clips["solo"].loop is False

    print("test_gltfread_loop OK")


if __name__ == "__main__":
    main()
