"""v7 course layouts (turtle commands) -- see make_layouts.py. Run emit_v7.py to regenerate tracks.c data."""
import sys; sys.path.insert(0, '.')
from make_layouts import *

def A(e, th=70):
    # Grand Tumble Raceway: clockwise kidney / pinched oval
    return [('w', 30), ('S', 90, 0), ('mark', 'sweepR'), ('T', 180, 95, 0.5), ('mark', 'sweepREnd'), ('S', 40, 0.5), ('mark', 'overpass'), ('S', 40, 0),
            ('mark', 'dip'), ('S', 40, -6.5), ('mark', 'tunnelA'), ('S', 100, -6.5), ('mark', 'tunnelB'), ('S', 40, 0),
            ('mark', 'sharpL'), ('T', -th, 42, 0.8), ('S', 20, 1.2), ('mark', 'sweep2'), ('T', (180 + th)/2, 80, 0.6), ('S', e, 0.3), ('T', (180 + th)/2, 80, 0), ('mark', 'final')]

def closeA():
    e = solve(lambda e: run(A(e)), 0, 500, lambda r: r[1][0])
    cm = A(e); pts, end, mk = run(cm)
    cm += [('mark', 'stands'), ('S', -end[1], 0)]
    return cm, e, end

def B(u, r):
    # Canopy River Parkway: counter-clockwise, start in the SE heading N
    return [('w', 22), ('S', 40, 0), ('mark', 'footbridge'), ('S', 50, 0.6), ('T', 25, 140, 0.3), ('S', 40, 0), ('T', -20, 140, 0.4),
            ('S', 40, 0.8), ('T', 40, 120, 0.5), ('S', 30, 0.4),
            ('mark', 'sweepL'), ('T', -135, 80, 1.0, 24), ('mark', 'sweepEnd'), ('S', u, 1.0, 20), ('mark', 'ramp'), ('S', 36, 3.2, 20), ('mark', 'gapA'), ('S', 32, 1.8), ('mark', 'gapB'),
            ('S', 30, 0.6, 22), ('mark', 'L90a'), ('T', -90, 24, 0.3), ('mark', 'river'),
            ('S', r*0.3, 0.3), ('T', -15, 200, 0.4), ('S', 110, 0.2), ('T', 30, 200, 0.3), ('S', 110, 0.3), ('T', -15, 200, 0.3), ('S', r*0.2, 0.3), ('mark', 'riverEnd'),
            ('T', -90, 24, 0.6),
            ('S', 4, 1.4, 16), ('mark', 'bridgeA'), ('S', 56, 1.6, 16), ('mark', 'bridgeB'), ('S', 40, 1.4, 20),
            ('mark', 'caveA'), ('T', -90, 42, 9.0, 18), ('S', 30, 9.5), ('mark', 'caveB'), ('mark', 'drop'), ('T', 30, 90, 1.5, 22), ('T', -30, 90, 0)]

def solve2(fn, lo1, hi1, lo2, hi2, ztarget):
    def inner(p2):
        return solve(lambda p1: run(fn(p1, p2)), lo1, hi1, lambda q: q[1][0])
    p2 = solve(lambda p2: (inner(p2), p2), lo2, hi2, lambda t: run(fn(t[0], t[1]))[1][1] - ztarget, 40)
    return inner(p2), p2

def closeB():
    u, r = solve2(B, 0, 800, 100, 900, -70)
    cm = B(u, r); pts, end, mk = run(cm)
    return cm + [('S', -end[1], 0)], u, r, end

def C(w, s):
    # Shellby Shores: clockwise island loop, sea on the left
    return [('w', 24), ('S', 40, -0.2), ('mark', 'tide'), ('S', 140, -0.9), ('S', 30, -0.2),
            ('T', 70, 70, 0.4), ('mark', 'ramp1'), ('S', 36, 2.0), ('mark', 'gap1'), ('S', 30, 1.6), ('mark', 'rock'), ('S', 64, 2.2),
            ('mark', 'ramp2'), ('S', 30, 3.2), ('mark', 'gap2'), ('S', 32, 1.4), ('mark', 'land'), ('S', 30, 0.8),
            ('T', 50, 80, 1.5), ('S', s, 2.5), ('mark', 'cliff'), ('T', 100, 52, 3.0), ('mark', 'arch'), ('S', 60, 3.0), ('mark', 'cliffEnd'), ('S', 1, 3.0), ('mark', 'cliffEnd2'),
            ('T', -30, 80, 2.0), ('S', 60, 1.0), ('T', 80, 70, 0.6), ('mark', 'south'), ('S', w, 0.2), ('T', 90, 60, -0.2)]

def closeC():
    w, s = solve2(C, 0, 900, 0, 500, -60)
    cm = C(w, s); pts, end, mk = run(cm)
    return cm + [('S', -end[1], -0.2)], w, s, end

def D(r1):
    # Clover Creek Farm: wide counter-clockwise loop with a crest
    return [('w', 28), ('S', 120, 0), ('mark', 'turn1'), ('T', -180, r1, 0.5), ('S', 40, 0.5), ('mark', 'crest'), ('S', 70, 4.0), ('S', 70, 0.5),
            ('mark', 'moles1'), ('S', 60, 0), ('T', -25, 120, 0), ('S', 40, 0), ('T', 25, 120, 0), ('mark', 'turn2'), ('T', -180, 75, 0), ('mark', 'turn2End'), ('mark', 'moles2')]

def closeD():
    s = solve(lambda s: run(D(s)), 40, 300, lambda q: q[1][0])
    cm = D(s); pts, end, mk = run(cm)
    return cm + [('S', -end[1], 0)], s, end
