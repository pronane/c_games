#!/usr/bin/env python3
"""Turtle-style layout designer for the v7 tracks.

Each layout is a list of commands; the script turns them into control points
{x, z, height, width} for tracks.c (same uniform Catmull-Rom spline the game uses),
solves the two closing straights so the loop meets the start line, prints the C
arrays plus the lap fractions of the marked landmarks, and draws a preview PNG.
Coordinates: north = +z, east = -x (the game's 'right' of a +z heading is -x).
"""
import math, sys
from PIL import Image, ImageDraw

def dirv(a):  # a = compass heading in degrees, clockwise from north
    r = math.radians(a); return (-math.sin(r), math.cos(r))

def run(cmds, step=22.0):
    x, z, a, h, w = 0.0, 0.0, 0.0, 0.0, 24.0
    pts = [(x, z, h, w)]
    marks = {}
    acc = 0.0
    for c in cmds:
        k = c[0]
        if k == 'w': w = c[1]; continue
        if k == 'mark': marks[c[1]] = len(pts) - 1 + (acc / step if step else 0); continue
        if k == 'S':
            L, h1 = c[1], c[2] if len(c) > 2 and c[2] is not None else h
            w1 = c[3] if len(c) > 3 else w
            n = max(1, round(L / step)); d = dirv(a)
            h0, w0 = h, w
            for i in range(1, n + 1):
                t = i / n
                pts.append((x + d[0] * L * t, z + d[1] * L * t, h0 + (h1 - h0) * t, w0 + (w1 - w0) * t))
            x += d[0] * L; z += d[1] * L; h, w = h1, w1
        if k == 'T':
            ang, R = c[1], c[2]; h1 = c[3] if len(c) > 3 and c[3] is not None else h
            w1 = c[4] if len(c) > 4 else w
            L = abs(math.radians(ang)) * R
            n = max(2, round(L / step))
            # centre: to the right for +ang (right turn)
            s = 1 if ang > 0 else -1
            rd = dirv(a + 90 * s)
            cx, cz = x + rd[0] * R, z + rd[1] * R
            h0, w0 = h, w
            for i in range(1, n + 1):
                t = i / n; aa = a + ang * t
                pd = dirv(aa - 90 * s)
                pts.append((cx + pd[0] * R, cz + pd[1] * R, h0 + (h1 - h0) * t, w0 + (w1 - w0) * t))
            a += ang; pd = dirv(a - 90 * s)
            x, z = cx + pd[0] * R, cz + pd[1] * R; h, w = h1, w1
    return pts, (x, z, a % 360), marks

def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return [0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * t + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2 + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3) for i in range(4)]

def dense(pts, per=100):
    n = len(pts); out = []
    for i in range(n):
        for j in range(per):
            out.append(catmull(pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n], j / per))
    cum = [0.0]
    for i in range(1, len(out) + 1):
        a, b = out[i - 1], out[i % len(out)]
        cum.append(cum[-1] + math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2))
    return out, cum

def frac_of_pt(cum, p, per=100):
    return cum[int(round(p * per))] / cum[-1]

def check(pts, name):
    d, cum = dense(pts, 20)
    L = cum[-1]
    worst = 1e9; where = None
    m = len(d)
    for i in range(0, m, 3):
        for j in range(0, m, 3):
            gap = abs(cum[i] - cum[j]); gap = min(gap, L - gap)
            if gap < 90: continue
            dd = math.hypot(d[i][0] - d[j][0], d[i][1] - d[j][1]) - (d[i][3] + d[j][3]) * 0.5 - 14
            if dd < worst: worst, where = dd, (d[i][0], d[i][1])
    return L, worst, where

def draw(pts, marks, fn, extra=()):
    d, cum = dense(pts, 20)
    xs = [p[0] for p in d]; zs = [p[1] for p in d]
    mnx, mxx, mnz, mxz = min(xs) - 60, max(xs) + 60, min(zs) - 60, max(zs) + 60
    S = 900 / max(mxx - mnx, mxz - mnz)
    im = Image.new('RGB', (int((mxx - mnx) * S) + 1, int((mxz - mnz) * S) + 1), (30, 60, 30))
    dr = ImageDraw.Draw(im)
    P = lambda x, z: ((mxx - x) * S, (mxz - z) * S)   # east (-x) to the right, north up
    for poly, col, wid in extra:
        dr.line([P(*q) for q in poly], fill=col, width=int(wid * S))
    for i in range(len(d)):
        a, b = d[i], d[(i + 1) % len(d)]
        c = (int(120 + a[2] * 12) % 256, 120, 120)
        dr.line([P(a[0], a[1]), P(b[0], b[1])], fill=c, width=max(2, int(a[3] * S)))
    for i in range(0, len(d), 40):
        dr.text(P(d[i][0], d[i][1]), "%d" % (i // 20), fill=(255, 255, 0))
    dr.ellipse([P(0, 0)[0] - 6, P(0, 0)[1] - 6, P(0, 0)[0] + 6, P(0, 0)[1] + 6], fill=(255, 255, 255))
    im.save(fn)

def emit(name, pts):
    s = ", ".join("{%.0f,%.0f,%.1f,%.0f}" % p for p in pts)
    return "        .numPts = %d,\n        .pts = { %s },\n" % (len(pts), s)

def solve(build, lo, hi, f, iters=60):
    """bisection on one parameter so that f(result) == 0"""
    flo = f(build(lo))
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(build(mid))
        if (fm > 0) == (flo > 0): lo, flo = mid, fm
        else: hi = mid
    return (lo + hi) / 2
