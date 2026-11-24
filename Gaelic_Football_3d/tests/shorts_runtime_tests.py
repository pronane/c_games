#!/usr/bin/env python3
"""Integration test: actual headless gait poses + skinned shorts vertices."""
import math
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
from inspect_shorts_runtime import compare

if len(sys.argv) != 3:
    raise SystemExit('usage: shorts_runtime_tests.py MOTION_HEADLESS MODEL.glb')
tool, model = sys.argv[1:]
# A no-IK control must compare exactly equal at every selected vertex.
control = compare(model, tool, 3.5, 30, no_ik=True)
assert not control['ik_applied'] and control['samples'] == 90
for mesh in control['paired_ik_delta']:
    for side in mesh['sides'].values():
        assert side['max_abs_vertex_delta_m'] == 0 and side['max_abs_mean_hem_delta_m'] == 0

for fps in (30, 60):
    report = compare(model, tool, 3.5, fps)
    assert report['ik_applied'] and report['samples'] == fps * 3
    assert len(report['paired_ik_delta']) == 9
    largest = 0
    for mesh in report['paired_ik_delta']:
        for side in mesh['sides'].values():
            for value in side.values(): assert math.isfinite(value) and value >= 0
            largest = max(largest, side['max_abs_vertex_delta_m'])
    assert 1e-7 < largest < .1, largest
    print(f'shorts_runtime fps={fps} max_vertex_delta_m={largest:.6f} (headless, no rendering)')
print('shorts runtime skinning checks passed')
