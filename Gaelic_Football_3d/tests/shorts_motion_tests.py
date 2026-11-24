#!/usr/bin/env python3
"""Validate the shorts GLB skinning diagnostic without a renderer."""
import math
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
import inspect_shorts_motion as motion
from inspect_shorts_skin import load_glb


def fixture(mixed=False):
    doc = {'nodes': [{'name':'pelvis', 'children':[1,2]}, {'name':'thigh_l'}, {'name':'thigh_r'},
                     {'name':'shorts', 'mesh':0, 'skin':0}],
           'skins':[{'joints':[1,2], 'inverseBindMatrices':0}],
           'meshes':[{'name':'test_shorts', 'primitives':[{'attributes':{}}]}],
           'animations':[{'name':'jog', 'channels':[{'sampler':0, 'target':{'node':1,'path':'rotation'}}],
                          'samplers':[{'input':4, 'output':5, 'interpolation':'LINEAR'}]}],
           'accessors':[], 'bufferViews':[]}
    blob = bytearray()
    def add(kind, code, rows, component):
        start = len(blob); width = len(rows[0]); fmt = '<'+code*width
        for row in rows: blob.extend(struct.pack(fmt, *row))
        doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(blob)-start})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'type':kind,'componentType':component,'count':len(rows)})
        return len(doc['accessors'])-1
    identity = (1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
    add('MAT4','f',[identity,identity],5126)
    pos = add('VEC3','f',[(.1,-.2,0),(-.1,-.2,0)],5126)
    ids = add('VEC4','H',[(0,1,0,0),(1,0,0,0)],5123)
    weights = add('VEC4','f',[(.5,.5,0,0) if mixed else (1,0,0,0),(1,0,0,0)],5126)
    add('SCALAR','f',[(0,),(1,)],5126)
    add('VEC4','f',[(0,0,0,1),(math.sqrt(.5),0,0,math.sqrt(.5))],5126)
    doc['meshes'][0]['primitives'][0]['attributes'] = {'POSITION':pos,'JOINTS_0':ids,'WEIGHTS_0':weights}
    return doc, bytes(blob)


def ranges(data):
    item = motion.measure(*data, frames=20)['shorts'][0]['sides']
    return item['positive_x']['mean_thigh_local_y_range_m'], item['negative_x']['mean_thigh_local_y_range_m']

assert motion.sample([.5, 1], [(1,2,3), (2,3,4)], 'LINEAR', 'translation', 0) == (1,2,3)
left, right = ranges(fixture())
assert left < 1e-6 and right < 1e-6, (left, right)
left, right = ranges(fixture(mixed=True))
assert left > .04 and right < 1e-6, (left, right)
model = load_glb(root / 'assets/models/gaelic_player.glb')
report = motion.measure(*model, frames=60)
assert len(report['shorts']) == 9
for item in report['shorts']:
    for side in item['sides'].values():
        assert math.isfinite(side['mean_thigh_local_y_range_m'])
        assert 0 <= side['mean_thigh_local_y_range_m'] < .1
print('animated shorts skinning tests passed (GLB clip only, no renderer or IK)')
