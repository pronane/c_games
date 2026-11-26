"""Portable CPU mesh diagnostic primitives (no game or rendering dependencies).

Optional floating-point triangle overlap is approximate, not exact collision
or anatomical validation.
Callers own coordinate systems, vertex selection, skin matrices and provenance.
"""
import math
import bisect


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


def triangles_intersect(a, b, epsilon=1e-7):
    """Floating-point SAT overlap of two non-degenerate 3D triangles.

    Coplanar triangles are supported; touching within epsilon counts as overlap.
    Raises for degenerate/invalid triangles. Not a robust exact predicate or a
    replacement for closed-volume containment and full-mesh collision checks.
    """
    if len(a) != 3 or len(b) != 3 or not math.isfinite(epsilon) or epsilon < 0:
        raise ValueError('invalid triangle')
    for p in (*a,*b):
        if len(p) != 3 or any(not math.isfinite(x) for x in p): raise ValueError('invalid point')
    def sub(x,y): return [x[i]-y[i] for i in range(3)]
    def cross(x,y): return [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
    ea=[sub(a[(i+1)%3],a[i]) for i in range(3)]
    eb=[sub(b[(i+1)%3],b[i]) for i in range(3)]
    na=cross(ea[0],ea[1]); nb=cross(eb[0],eb[1])
    if sum(x*x for x in na)<1e-24 or sum(x*x for x in nb)<1e-24: raise ValueError('degenerate triangle')
    axes=[na,nb] + [cross(x,y) for x in ea for y in eb]
    # These in-plane axes are needed when the triangles are coplanar.
    axes += [cross(na,x) for x in ea] + [cross(nb,x) for x in eb]
    for axis in axes:
        n=math.sqrt(sum(x*x for x in axis))
        if n<1e-14: continue
        axis=[x/n for x in axis]
        pa=[sum(x*y for x,y in zip(p,axis)) for p in a]
        pb=[sum(x*y for x,y in zip(p,axis)) for p in b]
        if max(pa)+epsilon < min(pb) or max(pb)+epsilon < min(pa): return False
    return True


def triangle_overlap_pairs(a, b, epsilon=1e-7):
    """Count overlapping triangle pairs after an axis-aligned broad phase.

    Input items are triples of 3D points; degenerate triangles raise. This is a
    sampled-surface diagnostic, not containment, CCD or full-mesh validation.
    """
    def bounds(tri):
        if len(tri)!=3: raise ValueError('invalid triangle')
        return ([min(p[k] for p in tri) for k in range(3)], [max(p[k] for p in tri) for k in range(3)])
    bb=[(bounds(t),t) for t in b]; bb.sort(key=lambda item:item[0][0][0]); total=0
    starts=[item[0][0][0] for item in bb]
    for ta in a:
        lo,hi=bounds(ta)
        end=bisect.bisect_right(starts, hi[0]+epsilon)
        for (lb,hb),tb in bb[:end]:
            if any(hi[k]+epsilon<lb[k] or hb[k]+epsilon<lo[k] for k in range(3)): continue
            if triangles_intersect(ta,tb,epsilon): total+=1
    return total
