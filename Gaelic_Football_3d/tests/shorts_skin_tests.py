#!/usr/bin/env python3
"""Bind-space skin inspection tests; no graphics or deformation validation."""
import importlib.util
from pathlib import Path
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shorts_skin", root / "tools/inspect_shorts_skin.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

doc, blob = mod.load_glb(root / "assets/models/gaelic_player.glb")
report = mod.inspect(doc, blob, .025)
assert len(report) == 9
for mesh in report:
    for side in ("positive_x", "negative_x"):
        hem = mesh["hem"][side]
        assert hem["vertices"] > 0
        assert abs(sum(hem["mean_influence"].values()) - 1) < .001
    a, b = mesh["hem"]["positive_x"], mesh["hem"]["negative_x"]
    assert abs(a["minimum_y_m"] - b["minimum_y_m"]) < .005

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "bad.glb"
    path.write_bytes(b"not a valid glb")
    try:
        mod.load_glb(path)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated GLB accepted")
print("shorts bind-space inspection tests passed (no animated mesh validation)")
