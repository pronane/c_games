#!/usr/bin/env python3
"""Measure GLB jog deformation at skinned shorts-hem vertices.

Evaluates glTF joint animation and linear-blend skinning, without the game's
procedural IK, GPU/CPU renderer, occlusion or clothing physics. Hem selection
is a bind-space low-Y approximation. Outputs thigh-local offsets, not a visual
shorts-length verdict. Only TRS nodes and LINEAR/STEP animation are supported.
"""
import argparse
import bisect
import json
import math
from inspect_shorts_skin import accessor, load_glb


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def trs(t, q, s):
    n = math.sqrt(sum(x*x for x in q))
    if n < 1e-12: raise ValueError('zero-length quaternion')
    x, y, z, w = (v/n for v in q)
    r = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    return [[r[i][j]*s[j] for j in range(3)] + [t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def slerp(a, b, u):
    dot = sum(x*y for x, y in zip(a, b))
    if dot < 0: b = tuple(-v for v in b); dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > .9995: q = [x + u*(y-x) for x, y in zip(a, b)]
    else:
        theta = math.acos(dot); d = math.sin(theta)
        q = [(math.sin((1-u)*theta)*x + math.sin(u*theta)*y)/d for x, y in zip(a, b)]
    n = math.sqrt(sum(x*x for x in q))
    if n < 1e-12: raise ValueError('zero-length animation quaternion')
    return tuple(v/n for v in q)


def sample(times, values, mode, path, t):
    if t <= times[0]: return values[0]
    i = max(0, bisect.bisect_right(times, t)-1)
    if i >= len(times)-1 or mode == 'STEP': return values[i]
    u = (t-times[i])/(times[i+1]-times[i])
    if path == 'rotation': return slerp(values[i], values[i+1], u)
    return tuple(x+(y-x)*u for x, y in zip(values[i], values[i+1]))


def transform(m, p):
    return tuple(sum(m[i][k]*p[k] for k in range(4)) for i in range(3))


def local_y(m, point):
    # The model's joint transforms must be rigid; this uses inverse rotation.
    d = [point[i] - m[i][3] for i in range(3)]
    return sum(m[i][1]*d[i] for i in range(3))


def measure(doc, blob, clip='jog', frames=60, band=.025, world_frames=None, include_values=False):
    if frames < 2 or frames > 1000 or not 0 < band <= .1: raise ValueError('invalid sampling settings')
    nodes = doc['nodes']; parents = {}
    for i, node in enumerate(nodes):
        if 'matrix' in node: raise ValueError('matrix nodes are not supported')
        for child in node.get('children', []):
            if child in parents: raise ValueError('node has multiple parents')
            parents[child] = i
    anims = [a for a in doc['animations'] if a.get('name') == clip]
    if len(anims) != 1: raise ValueError('clip not found or ambiguous')
    channels, end = {}, 0.0
    for channel in anims[0]['channels']:
        target = channel['target']; path = target['path']
        if path not in ('translation', 'rotation', 'scale'): continue
        sampler = anims[0]['samplers'][channel['sampler']]; mode = sampler.get('interpolation', 'LINEAR')
        if mode not in ('LINEAR', 'STEP'): raise ValueError('unsupported animation interpolation')
        times = [x[0] for x in accessor(doc, blob, sampler['input'])]
        values = accessor(doc, blob, sampler['output'])
        if len(times) != len(values) or not times or any(times[i] >= times[i+1] for i in range(len(times)-1)):
            raise ValueError('invalid animation keys')
        if any(not math.isfinite(x) for x in times): raise ValueError('non-finite key time')
        if (target['node'], path) in channels: raise ValueError('duplicate animation target')
        if any(not math.isfinite(x) for row in values for x in row): raise ValueError('non-finite key value')
        channels[(target['node'], path)] = (times, values, mode)
        end = max(end, times[-1])
    if end <= 0: raise ValueError('empty clip')
    skin = doc['skins'][0]; joints = skin['joints']; names = [nodes[j].get('name', '') for j in joints]
    thigh_indices = [names.index('thigh_l'), names.index('thigh_r')]
    raw_ibm = accessor(doc, blob, skin['inverseBindMatrices'])
    if len(raw_ibm) != len(joints): raise ValueError('invalid inverse-bind matrices')
    ibm = [[[a[c*4+r] for c in range(4)] for r in range(4)] for a in raw_ibm]
    meshes = []
    for node in nodes:
        if 'mesh' not in node or node.get('skin') != 0: continue
        mesh = doc['meshes'][node['mesh']]
        if 'shorts' not in mesh.get('name', '').lower(): continue
        for prim in mesh['primitives']:
            attrs = prim['attributes']; points = accessor(doc, blob, attrs['POSITION'])
            ids = accessor(doc, blob, attrs['JOINTS_0']); weights = accessor(doc, blob, attrs['WEIGHTS_0'])
            if len(points) != len(ids) or len(points) != len(weights): raise ValueError('inconsistent vertices')
            sides = []
            for sign in (1, -1):
                side = [i for i,p in enumerate(points) if p[0]*sign > 0]
                if not side: raise ValueError('missing hem')
                low = min(points[i][1] for i in side)
                sides.append([i for i in side if points[i][1] <= low + band])
            meshes.append((mesh['name'], points, ids, weights, sides))
    if not meshes: raise ValueError('no shorts meshes')
    if len({m[0] for m in meshes}) != len(meshes): raise ValueError('duplicate shorts mesh names')
    if world_frames is not None:
        # The raylib 5.5 renderer derives inverse binds from node-world TRS,
        # rather than reading the GLB inverse-bind accessor. Reject a model if
        # those two bind conventions do not agree, instead of reporting a
        # misleading result for runtime poses.
        bind_cache = {}; bind_active = set()
        def bind_world(i):
            if i in bind_cache: return bind_cache[i]
            if i in bind_active: raise ValueError('cyclic node hierarchy')
            bind_active.add(i); node = nodes[i]
            local = trs(node.get('translation',(0,0,0)), node.get('rotation',(0,0,0,1)), node.get('scale',(1,1,1)))
            bind_cache[i] = mul(bind_world(parents[i]), local) if i in parents else local
            bind_active.remove(i); return bind_cache[i]
        for i, joint in enumerate(joints):
            product = mul(bind_world(joint), ibm[i])
            if any(abs(product[r][c]-(1 if r==c else 0)) > .001 for r in range(4) for c in range(4)):
                raise ValueError('GLB inverse binds differ from raylib bind convention')
        if len(world_frames) != frames or any(len(frame) != len(joints) for frame in world_frames):
            raise ValueError('runtime poses do not match frame or joint count')
    result = {name: [[], []] for name, *_ in meshes}
    vertex_values = {name: [[], []] for name, *_ in meshes} if include_values else None
    spans = {name: [[ [float('inf'), float('-inf')] for _ in side] for side in sides]
             for name, _, _, _, sides in meshes}
    for frame in range(frames):
        t = end*frame/frames
        cache = {}; active = set()
        def world(i):
            if i in cache: return cache[i]
            if i in active: raise ValueError('cyclic node hierarchy')
            active.add(i); node = nodes[i]; args = []
            for path, default in [('translation', (0,0,0)), ('rotation', (0,0,0,1)), ('scale', (1,1,1))]:
                channel = channels.get((i, path))
                args.append(sample(*channel, path, t) if channel else node.get(path, default))
            local = trs(*args)
            cache[i] = mul(world(parents[i]), local) if i in parents else local
            active.remove(i); return cache[i]
        if world_frames is None:
            world_joints = [world(i) for i in joints]
        else:
            world_joints = []
            for row in world_frames[frame]:
                if len(row) != 10 or any(not math.isfinite(x) for x in row):
                    raise ValueError('invalid runtime joint transform')
                world_joints.append(trs(row[:3], row[3:7], row[7:10]))
        for k in thigh_indices:
            m = world_joints[k]
            if any(abs(sum(m[i][a]*m[i][b] for i in range(3))-(1 if a==b else 0)) > .001 for a in range(3) for b in range(3)):
                raise ValueError('thigh world transform is not rigid')
        mats = [mul(m, inv) for m,inv in zip(world_joints,ibm)]
        for name, points, ids, weights, sides in meshes:
            for side, selected in enumerate(sides):
                total = 0; sample_values = []
                for index, v in enumerate(selected):
                    pos = [0.0,0.0,0.0]
                    for joint, weight in zip(ids[v], weights[v]):
                        if joint >= len(mats) or not math.isfinite(weight) or weight < 0: raise ValueError('invalid skin')
                        if weight:
                            p = transform(mats[joint], (*points[v], 1))
                            for axis in range(3): pos[axis] += p[axis]*weight
                    y = local_y(world_joints[thigh_indices[side]], pos)
                    total += y
                    if include_values: sample_values.append(y)
                    bounds = spans[name][side][index]
                    bounds[0] = min(bounds[0], y); bounds[1] = max(bounds[1], y)
                result[name][side].append(total/len(selected))
                if include_values: vertex_values[name][side].append(sample_values)
    report = {'clip':clip, 'samples':frames, 'duration_seconds':end, 'band_m':band,
            'limitation':'GLB clip and linear skinning only; no runtime IK, renderer or occlusion',
            'shorts':[{'mesh':name, 'sides':{side: {'mean_thigh_local_y_min_m':min(v), 'mean_thigh_local_y_max_m':max(v),
                    'mean_thigh_local_y_range_m':max(v)-min(v),
                    'max_vertex_thigh_local_y_range_m': max(high-low for low, high in spans[name][index])}
                    for index,(side,v) in enumerate(zip(('positive_x','negative_x'),values))}}
                    for name,values in result.items()]}
    if include_values: report['_vertex_values'] = vertex_values
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model'); parser.add_argument('--clip', default='jog'); parser.add_argument('--frames', type=int, default=60)
    args = parser.parse_args(); doc, blob = load_glb(args.model)
    print(json.dumps(measure(doc, blob, args.clip, args.frames), indent=2))


if __name__ == '__main__': main()
