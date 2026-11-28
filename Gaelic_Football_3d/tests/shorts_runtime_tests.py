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
for fps in (30, 60):
    report = compare(model, tool, 3.0, fps, scenario='turn-transition')
    summary = report['scenario_summary']
    assert report['samples'] == fps*5
    assert summary['turn_frames'] >= fps - 1 and summary['crossfade_frames'] > 0
    for clip in ('jog', 'sidestep', 'run', 'idle'): assert summary['clip_frame_counts'].get(clip, 0) > 0
    for mesh in report['frame_steps']:
        for side in mesh['sides'].values():
            assert all(name in side and side[name]['samples'] > 0 for name in ('turn', 'crossfade', 'steady'))
    print(f"turn_transition fps={fps} clips={summary['clip_frame_counts']} crossfade={summary['crossfade_frames']} (synthetic, no rendering)")
control = compare(model, tool, 3.0, 30, no_ik=True, scenario='turn-transition')
assert not control['ik_applied']
for mesh in control['paired_ik_delta']:
    for side in mesh['sides'].values(): assert side['max_abs_vertex_delta_m'] == 0
print('shorts runtime skinning checks passed')
