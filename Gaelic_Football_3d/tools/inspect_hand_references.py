#!/usr/bin/env python3
"""Compare candidate hand-reference poses using joint geometry, not mesh/anatomy.

Reports fingertip-chain bend and index-to-pinky direction spread for named
non-possession clips. These are proxies to guide visual review, not a method of
selecting a natural or safe pose. Uses the asset's native glTF local animation.
"""
import argparse
import json
import math
from inspect_shorts_skin import accessor, load_glb
from inspect_shorts_motion import mul, trs, sample

CLIPS = ('idle', 'run', 'jog', 'sidestep', 'keeper_idle', 'keeper_ready')
FINGERS = ('index', 'middle', 'ring', 'pinky')


def angle(a, b):
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    if min(na, nb) < 1e-8: raise ValueError('degenerate finger segment')
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b))/(na*nb)))))


def geometry(points):
    dirs = {}; bends = []
    for name in FINGERS:
        a, b, c = points[name]
        u = [b[i]-a[i] for i in range(3)]; v = [c[i]-b[i] for i in range(3)]
        dirs[name] = [c[i]-a[i] for i in range(3)]
        bends.append(angle(u, v))
    return {'mean_mid_joint_bend_deg': sum(bends)/len(bends),
            'index_pinky_spread_deg': angle(dirs['index'], dirs['pinky'])}


def inspect(doc, blob, frames=20):
    if not 2 <= frames <= 500: raise ValueError('invalid sample count')
    nodes = doc['nodes']; names = {n.get('name'): i for i,n in enumerate(nodes) if n.get('name')}
    parents = {}
    for i,n in enumerate(nodes):
        if 'matrix' in n: raise ValueError('matrix nodes not supported')
        for child in n.get('children', []):
            if child in parents: raise ValueError('multiple parents')
            parents[child] = i
    bone_ids = {side: {finger: [names[f'{finger}_{j:02d}_{side}'] for j in (1,2,3)]
                       for finger in FINGERS} for side in ('l','r')}
    report = {}
    for name in CLIPS:
        matches = [a for a in doc['animations'] if a.get('name') == name]
        if not matches: continue
        if len(matches) != 1: raise ValueError('ambiguous clip')
        channels = {}; end = 0
        for ch in matches[0]['channels']:
            target = ch['target']; path = target['path']
            if path not in ('translation', 'rotation', 'scale'): continue
            smp = matches[0]['samplers'][ch['sampler']]; mode = smp.get('interpolation','LINEAR')
            if mode not in ('LINEAR','STEP'): raise ValueError('unsupported interpolation')
            times = [v[0] for v in accessor(doc,blob,smp['input'])]; values = accessor(doc,blob,smp['output'])
            if not times or len(times) != len(values) or any(times[i]>=times[i+1] for i in range(len(times)-1)):
                raise ValueError('invalid keyframes')
            channels[(target['node'], path)] = (times, values, mode); end = max(end, times[-1])
        if end <= 0: raise ValueError('empty clip')
        sides = {'l': [], 'r': []}
        for frame in range(frames):
            t = end*frame/frames; cache = {}; active = set()
            def world(i):
                if i in cache: return cache[i]
                if i in active: raise ValueError('cyclic hierarchy')
                active.add(i); n = nodes[i]
                vals = []
                for path, default in [('translation',(0,0,0)),('rotation',(0,0,0,1)),('scale',(1,1,1))]:
                    c = channels.get((i,path)); vals.append(sample(*c,path,t) if c else n.get(path,default))
                m = trs(*vals); cache[i] = mul(world(parents[i]),m) if i in parents else m
                active.remove(i); return cache[i]
            for side in sides:
                points = {f: [tuple(world(i)[k][3] for k in range(3)) for i in ids] for f,ids in bone_ids[side].items()}
                sides[side].append({'time_s': t, **geometry(points)})
        report[name] = {'duration_s':end, 'sides':sides}
    return {'description':'Joint position proxies only; excludes thumb, final fingertip and skin. Lower spread is not proof of realism.',
            'samples_per_clip':frames, 'clips':report}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('model'); p.add_argument('--frames', type=int, default=20)
    a = p.parse_args(); doc,blob = load_glb(a.model)
    print(json.dumps(inspect(doc,blob,a.frames),indent=2))

if __name__ == '__main__': main()
