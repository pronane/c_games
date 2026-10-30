"""Prints the control points / water channels for the four v7 courses (pasted into tracks.c)."""
import sys, math, bisect; sys.path.insert(0, '.')
from design_v7 import *
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'

def at_frac(d, cum, f):
    t = f * cum[-1]
    i = min(bisect.bisect_left(cum, t), len(d) - 1)
    a = d[i]; b = d[(i + 1) % len(d)]
    fx, fz = b[0] - a[0], b[1] - a[1]; l = math.hypot(fx, fz) or 1
    return (a[0], a[1]), (fx / l, fz / l), a[3]

for nm, fn in (('A', closeA), ('B', closeB), ('C', closeC), ('D', closeD)):
    res = fn(); cm = res[0]
    pts, end, mk = run(cm)
    if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 8: pts = pts[:-1]
    xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
    ox, oz = -round((min(xs) + max(xs)) / 2), -round((min(zs) + max(zs)) / 2)
    pts = [(p[0] + ox, p[1] + oz, p[2], p[3]) for p in pts]
    d, cum = dense(pts, 100)
    F = {k: frac_of_pt(cum, v) for k, v in mk.items()}
    def P(f, lat=0.0):
        p, fw, w = at_frac(d, cum, f); r = (-fw[1], fw[0])
        return (p[0] + r[0] * lat, p[1] + r[1] * lat)
    river = []
    if nm == 'A':   # lake to the left of the final straight
        a, b = F['stands'], 0.985
        for i in range(7):
            q = P(a + 0.03 + (b - a - 0.06) * i / 6, -62); river.append((q[0], q[1], 30 if 0 < i < 6 else 22))
    if nm == 'B':   # river: under the gorge jump, along the riverside straight (left), under the rope bridge
        gm = P((F['gapA'] + F['gapB']) / 2); bm = P((F['bridgeA'] + F['bridgeB']) / 2)
        river += [(gm[0], gm[1] + 420, 15), (gm[0], gm[1] + 60, 14), (gm[0], gm[1], 13)]
        for i in range(9):
            q = P(F['river'] + 0.01 + (F['riverEnd'] - F['river'] - 0.02) * i / 8, -40); river.append((q[0], q[1], 12))
        river += [(bm[0], bm[1], 12), (bm[0], bm[1] - 60, 13), (bm[0], bm[1] - 420, 15)]
    if nm == 'C':   # two sea channels under the ramp jumps
        for g in (('gap1', 'rock'), ('gap2', 'land')):
            f = (F[g[0]] + F[g[1]]) / 2
            a = P(f, 30); b = P(f, -150)
            if river: river.append((0, 0, 0))
            river += [(a[0], a[1], 9), (b[0], b[1], 13)]
    print('//', nm, 'len %.0f' % cum[-1], 'offset', ox, oz, 'pts', len(pts))
    print('//   ' + ' '.join('%s=%.4f' % (k, v) for k, v in F.items()))
    print('        .numPts = %d, .pts = { %s },' % (len(pts), ', '.join('{%.0f,%.0f,%.1f,%.0f}' % p for p in pts)))
    if river:
        print('        .numRiver = %d, .river = { %s },' % (len(river), ', '.join('{%.0f,%.0f,%.0f}' % r for r in river)))
    polys, cur = [], []
    for r in river:
        if r[2] == 0: polys.append(cur); cur = []
        else: cur.append(r)
    if cur: polys.append(cur)
    extra = [([(q[0], q[1]) for q in pl], (40, 110, 220), pl[len(pl)//2][2] * 2) for pl in polys if len(pl) > 1]
    draw(pts, mk, '%s/layout_%s.png' % (OUT, nm), extra)
