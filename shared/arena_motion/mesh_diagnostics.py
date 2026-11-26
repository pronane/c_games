"""Portable CPU mesh diagnostic primitives (no game or rendering dependencies).

These functions do not detect triangle intersections or judge human anatomy.
Callers own coordinate systems, vertex selection, skin matrices and provenance.
"""
import math


def distance(a, b):
    if len(a) != 3 or len(b) != 3 or any(not math.isfinite(v) for v in (*a,*b)):
        raise ValueError('expected finite 3D points')
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def centroid(points):
    if not points: raise ValueError('empty point set')
    if any(len(p) != 3 or any(not math.isfinite(x) for x in p) for p in points):
        raise ValueError('invalid point set')
    return [sum(p[k] for p in points)/len(points) for k in range(3)]


def sampled_min_distance(a, b):
    if not a or not b: raise ValueError('empty point set')
    return min(distance(x,y) for x in a for y in b)


def skin_point(point, ids, weights, mats):
    if len(point) != 3 or len(ids) != len(weights) or not ids or any(not math.isfinite(x) for x in point):
        raise ValueError('invalid skinned vertex')
    if any(not math.isfinite(w) or w < 0 for w in weights) or abs(sum(weights)-1) > .01:
        raise ValueError('invalid skin weights')
    result = [0.,0.,0.]
    for j,w in zip(ids,weights):
        if not isinstance(j,int) or j < 0 or j >= len(mats): raise ValueError('invalid skin influence')
        m=mats[j]
        if len(m) != 4 or any(len(row)!=4 or any(not math.isfinite(v) for v in row) for row in m):
            raise ValueError('invalid skin matrix')
        if w:
            for k in range(3): result[k] += w*(sum(m[k][c]*point[c] for c in range(3)) + m[k][3])
    return result
