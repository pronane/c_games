#!/usr/bin/env python3
"""Test paired CPU-skinned fingertip proxies; no render or intersection proof."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_hand_mesh import compare, select_tips, skin_point, sampled_min_distance, centroid, triangles_intersect, triangle_overlap_pairs, point_triangle_distance

try: select_tips([(0,0,0)]*5,[(0,)]*5,[(1,)]*5,0,(0,0,0),(0,0,0))
except ValueError: pass
else: raise AssertionError('degenerate axis accepted')
ident=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
assert skin_point((1,2,3),(0,),(1,),[ident]) == [1,2,3]
assert centroid([(0,0,0),(2,0,0)]) == [1,0,0]
assert sampled_min_distance([(0,0,0)],[(0,3,4)]) == 5
tri=[(0,0,0),(2,0,0),(0,2,0)]
assert triangles_intersect(tri,[(.2,.2,-1),(.2,.2,1),(.8,.2,0)])
assert triangles_intersect(tri,[(.2,.2,0),(.3,.2,0),(.2,.3,0)])
assert not triangles_intersect(tri,[(3,3,0),(4,3,0),(3,4,0)])
assert not triangles_intersect(tri,[(0,0,1),(2,0,1),(0,2,1)])
assert triangle_overlap_pairs([tri],[tri]) == 1
assert abs(point_triangle_distance((.2,.2,1),tri)-1)<1e-9
assert abs(point_triangle_distance((3,0,0),tri)-1)<1e-9
assert point_triangle_distance((.2,.2,0),tri)<1e-9
try: point_triangle_distance((0,0,0),[(0,0,0)]*3)
except ValueError: pass
else: raise AssertionError('degenerate ball-proximity triangle accepted')
try: triangles_intersect(tri,[(0,0,0)]*3)
except ValueError: pass
else: raise AssertionError('degenerate triangle accepted')
for fn in (lambda: skin_point((0,0,0),(-1,),(1,),[ident]), lambda: centroid([]), lambda: sampled_min_distance([],[(0,0,0)])):
    try: fn()
    except ValueError: pass
    else: raise AssertionError('invalid diagnostic input accepted')
if len(sys.argv) != 3: raise SystemExit('usage: hand_mesh_tests.py MOTION_HEADLESS MODEL.glb')
control=compare(sys.argv[2],sys.argv[1],0,30)
assert control['samples']==30
for data in control['sides'].values():
    assert data['max_tip_vertex_displacement_m'] < 1e-10
    assert data['mean_adjacent_tip_centroid_gap_raw_m'] == data['mean_adjacent_tip_centroid_gap_adjusted_m']
for mode in (1,2,3,4):
    for fps in (30,60):
        report=compare(sys.argv[2],sys.argv[1],mode,fps)
        assert report['samples']==fps and all(v>=3 for v in report['tip_vertex_counts'].values())
        for side in report['sides'].values():
            assert all(math.isfinite(x) and x>=0 for x in side.values())
            assert side['max_tip_vertex_displacement_m'] < .15
        print('hand_mesh mode=%d fps=%d max_tip_delta_m=%.5f (sampled vertices only)' % (mode,fps,max(s['max_tip_vertex_displacement_m'] for s in report['sides'].values())))
surface=compare(sys.argv[2],sys.argv[1],0,30,surface=True)
assert surface['surface_samples']==12 and len(surface['selected_surface_triangles'])==10
for side in surface['sampled_surface_overlap'].values():
    assert side['raw']==side['adjusted']
    assert 0 <= side['raw']['frames_with_overlap'] <= 12
print('hand mesh tests passed (selected sampled triangles only; no full-mesh validation)')
