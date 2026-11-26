#!/usr/bin/env python3
"""Scripted cradle poses with real bind rotations; not live/rendered validation."""
import sys
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from inspect_hand_grip import compare, compare_renderer_bind

assert compare_renderer_bind('x 0 0 0 1\n','x 0 0 0 -1\n')==0
for other in ('x 1 0 0 0\n','y 0 0 0 1\n'):
    try: compare_renderer_bind('x 0 0 0 1\n',other)
    except ValueError: pass
    else: raise AssertionError('renderer mismatch accepted')
if len(sys.argv)!=3: raise SystemExit('usage: hand_grip_tests.py TOOL MODEL')
for bad in ('nan', '0', '0.061', 'garbage'):
    result=subprocess.run([sys.argv[1], '--export-grip-poses', sys.argv[2], '/dev/null', '/dev/null', bad], capture_output=True)
    assert result.returncode != 0
r=compare(sys.argv[2],sys.argv[1])
assert 0.012 <= r['clearance_m'] <= 0.06
assert r['samples']==12 and len(r['states'])==12
assert {'stand','jog-a','jog-b','sprint-a','sprint-b'}==set(r['ball_available'])
for row in r['states']:
    for side in row['sides'].values(): assert side['raw']==side['adjusted']
    for side in row.get('ball_triangle_overlap',{}).values(): assert side['raw']==side['adjusted']
print('scripted grip checks passed (selected surfaces only; no live or rendered validation)')
