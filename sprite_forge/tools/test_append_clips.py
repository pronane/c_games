#!/usr/bin/env python3
"""officials.append_clips binds channels by bone name, not node index.

Regression for the bug where appending clips to a GLB whose node order differs
from skin-joint order (e.g. an extra container node in front) raised
"GLB node i is ..." — or worse, had it not raised, mis-bound rotations.
Skeleton-only fixture: no meshes required to exercise the channel mapping.
"""
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from sforge import officials  # noqa: E402
from sforge.rigrec import Clip, Rig  # noqa: E402


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


def skeleton_glb(path, node_names):
    nodes = [{"name": n} for n in node_names]
    # container root with the real bones as children, like shipped AFL/GAA GLBs
    doc = {
        "asset": {"version": "2.0", "generator": "test_append_clips fixture"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": node_names[0], "children": list(range(1, len(node_names)))}]
                  + nodes[1:],
        "animations": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [{"byteLength": 0}],
    }
    write_glb(path, doc, b"")


def make_rig():
    rig = Rig("fixture")
    rig.bones = ["pelvis", "spine_01"]
    rig.parent = np.array([-1, 0], int)
    rig.bind = np.array([np.eye(4), np.eye(4)], float)
    rig.meta = dict(hips_index=0)
    return rig


def make_clip():
    frames = 3
    R = np.zeros((frames, 2, 4))
    R[..., 3] = 1.0  # identity quaternions (xyzw)
    T = np.zeros((frames, 2, 3))
    T[:, 0, 1] = np.linspace(0.9, 1.0, frames)  # bob the pelvis
    return Clip("wave", R, T, 30, False, "test")


def main():
    tmp = tempfile.mkdtemp(prefix="append_clips_")
    src = os.path.join(tmp, "src.glb")
    dst = os.path.join(tmp, "dst.glb")
    # node order DELIBERATELY differs from rig bone order: container first, spine before pelvis
    skeleton_glb(src, ["RootNode", "spine_01", "pelvis"])
    rig = make_rig()
    n = officials.append_clips(src, dst, rig, {"wave": make_clip()}, root_motion="inplace", replace=False)
    assert os.path.getsize(dst) == n and n > 0

    from sforge.glbpack import read_glb
    j, _buf = read_glb(dst)
    anims = {a["name"]: a for a in j["animations"]}
    assert "wave" in anims, anims.keys()
    node_names = [nd.get("name") for nd in j["nodes"]]
    targets = {}
    for ch in anims["wave"]["channels"]:
        targets.setdefault((node_names[ch["target"]["node"]]), set()).add(ch["target"]["path"])
    # rotation on BOTH bones, translation on the pelvis only (hips / parent<0)
    assert targets.get("pelvis") == {"rotation", "translation"}, targets
    assert targets.get("spine_01") == {"rotation"}, targets
    # nodes must be untouched by the bind
    assert node_names == ["RootNode", "spine_01", "pelvis"], node_names

    # a forge-order GLB (bone i == node i) must keep working unchanged
    src2 = os.path.join(tmp, "src2.glb")
    dst2 = os.path.join(tmp, "dst2.glb")
    skeleton_glb(src2, ["pelvis", "spine_01"])
    # strip the container structure: two flat bones, node order == bone order
    from sforge.glbpack import read_glb as _rg
    j2, _ = _rg(src2)
    j2["nodes"] = [{"name": "pelvis"}, {"name": "spine_01"}]
    j2["scenes"] = [{"nodes": [0, 1]}]
    buf2 = b""
    write_glb(src2, j2, buf2)
    officials.append_clips(src2, dst2, rig, {"wave": make_clip()}, root_motion="inplace", replace=False)
    j3, _ = _rg(dst2)
    names3 = [nd.get("name") for nd in j3["nodes"]]
    anims3 = {a["name"]: a for a in j3["animations"]}
    assert names3 == ["pelvis", "spine_01"], names3
    for ch in anims3["wave"]["channels"]:
        assert ch["target"]["node"] in (0, 1)
    print("test_append_clips OK")


if __name__ == "__main__":
    main()
