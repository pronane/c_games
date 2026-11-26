#!/usr/bin/env python3
"""Scripted cradle poses with real bind rotations; not live/rendered validation."""
import sys
import subprocess
import json
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from inspect_hand_grip import compare, compare_renderer_bind, bind_rotations, joint_spans
from inspect_shorts_skin import load_glb

assert compare_renderer_bind('x 0 0 0 1\n','x 0 0 0 -1\n')==0
for other in ('x 1 0 0 0\n','y 0 0 0 1\n'):
    try: compare_renderer_bind('x 0 0 0 1\n',other)
    except ValueError: pass
    else: raise AssertionError('renderer mismatch accepted')
if len(sys.argv)!=3: raise SystemExit('usage: hand_grip_tests.py TOOL MODEL')
for bad in ('nan', '0', '0.061', 'garbage'):
    result=subprocess.run([sys.argv[1], '--export-grip-poses', sys.argv[2], '/dev/null', '/dev/null', bad], capture_output=True)
    assert result.returncode != 0
# Exercise the optional offline offset without the expensive surface screen.
with tempfile.TemporaryDirectory() as tmp:
    bind=Path(tmp)/'bind'; doc,blob=load_glb(sys.argv[2]); bind.write_text(bind_rotations(doc,blob))
    exports=[]
    for offset,follow,replant in (((0,0,0),0,0),((-.08,0,-.08),0,0),((-.08,0,-.08),1,0),((0,0,0),1,0),((-.08,0,-.08),1,1)):
        out=Path(tmp)/'poses.json'
        cmd=[sys.argv[1],'--export-grip-poses',sys.argv[2],str(out),str(bind),'0.012',*(str(v) for v in offset),str(follow),str(replant)]
        subprocess.run(cmd,check=True,capture_output=True)
        exports.append(json.loads(out.read_text()))
    for a,b in zip(exports[0]['frames'], exports[1]['frames']):
        if a['state'].startswith('sprint'):
            assert a['raw']!=b['raw']
        else:
            assert a==b
    assert exports[0]['frames']==exports[3]['frames']
    for a,b in zip(exports[0]['frames'],exports[2]['frames']):
        if not a['state'].startswith('sprint'): assert a==b
    for a,b in zip(exports[2]['frames'],exports[4]['frames']):
        assert a['ball_center']==b['ball_center'] and b['raw']==b['adjusted']
        if a['state'].startswith('sprint'): assert a['raw']!=b['raw']
        else: assert a==b
    base,changed,following=[joint_spans(doc,x) for x in exports[:3]]
    for state in ('sprint-a','sprint-b'):
        for f in ('index','middle','ring','pinky','thumb'):
            assert changed[state]['r']['wrist_to_finger_roots'][f]['length_m'] > base[state]['r']['wrist_to_finger_roots'][f]['length_m']
            assert abs(following[state]['r']['wrist_to_finger_roots'][f]['length_m']-base[state]['r']['wrist_to_finger_roots'][f]['length_m']) < 1e-5
        for part in ('upper_arm','forearm'):
            assert abs(changed[state]['r'][part]['length_m']-base[state]['r'][part]['length_m']) < 1e-5
    for bad in ('nan','0.201','', 'garbage'):
        cmd=[sys.argv[1],'--export-grip-poses',sys.argv[2],str(out),str(bind),'0.012',bad,'0','0']
        assert subprocess.run(cmd,capture_output=True).returncode != 0
    for bad in ('nan','-0.1','1.1','','garbage'):
        cmd=[sys.argv[1],'--export-grip-poses',sys.argv[2],str(out),str(bind),'0.012','-.08','0','-.08',bad]
        assert subprocess.run(cmd,capture_output=True).returncode != 0
    for follow,replant in (('1','2'),('0','1'),('1','nan')):
        cmd=[sys.argv[1],'--export-grip-poses',sys.argv[2],str(out),str(bind),'0.012','-.08','0','-.08',follow,replant]
        assert subprocess.run(cmd,capture_output=True).returncode != 0
r=compare(sys.argv[2],sys.argv[1])
assert 0.012 <= r['clearance_m'] <= 0.06
assert r['samples']==12 and len(r['states'])==12
assert all(r['hand_surface_triangles'][s] >= sum(r['triangle_counts'][s+'_'+f] for f in ('index','middle','ring','pinky','thumb')) for s in ('l','r'))
assert {'stand','jog-a','jog-b','sprint-a','sprint-b'}==set(r['ball_available'])
for row in r['states']:
    for side in row['sides'].values(): assert side['raw']==side['adjusted']
    for side in row.get('ball_triangle_overlap',{}).values(): assert side['raw']==side['adjusted']
    for side in row.get('ball_proximity',{}).values():
        assert side['raw']==side['adjusted']
        assert 0 <= side['raw']['triangles_within_10mm'] <= side['raw']['triangle_count']
        assert side['raw']['min_surface_gap_m'] >= -0.11
    for side in row.get('ball_hand_surface',{}).values():
        assert side['raw']==side['adjusted']
        h=side['raw']
        assert 0 <= h['triangles_inside_sphere'] <= h['triangles_within_10mm'] <= h['triangle_count']
        assert 0 <= h['palm_influenced_triangles_inside_sphere'] <= h['palm_influenced_triangle_count'] <= h['triangle_count']
        assert h['palm_influenced_triangles_inside_sphere'] <= h['triangles_inside_sphere']
        assert (h['palm_influenced_min_surface_gap_m'] < 0) == (h['palm_influenced_triangles_inside_sphere'] > 0)
        assert h['palm_influenced_min_surface_gap_m'] >= h['min_surface_gap_m'] - 1e-9
        assert h['wrist_distance_m'] >= 0
        assert (h['min_surface_gap_m'] < 0) == (h['triangles_inside_sphere'] > 0)
    for key, side in row.get('ball_proximity',{}).items():
        assert (side['raw']['min_surface_gap_m'] < 0) == (row['ball_triangle_overlap'][key]['raw'] > 0)
print('scripted grip checks passed (selected surfaces only; no live or rendered validation)')
