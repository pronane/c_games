#!/usr/bin/env python3
"""Test geometry proxy and real-model reference report, not visual quality."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_hand_references import angle, geometry, inspect
from inspect_shorts_skin import load_glb
assert abs(angle([1,0,0],[0,1,0])-90) < 1e-6
try: angle([0,0,0],[1,0,0])
except ValueError: pass
else: raise AssertionError('zero segment accepted')
points = {n: [(0,i,0),(1,i,0),(2,i,0)] for i,n in enumerate(('index','middle','ring','pinky'))}
g = geometry(points); assert g['mean_mid_joint_bend_deg'] == 0 and g['index_pinky_spread_deg'] == 0
model = Path(__file__).resolve().parents[1] / 'assets/models/gaelic_player.glb'
doc, blob = load_glb(model); report = inspect(doc,blob,4)
assert {'idle','run','jog','sidestep'}.issubset(report['clips'])
for clip in report['clips'].values():
    for side in clip['sides'].values():
        assert len(side) == 4
        assert all(math.isfinite(row['mean_mid_joint_bend_deg']) and 0 <= row['index_pinky_spread_deg'] <= 180 for row in side)
print('hand reference geometry tests passed (joint proxies, no mesh or anatomical validation)')
