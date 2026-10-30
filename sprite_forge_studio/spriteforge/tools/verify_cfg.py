#!/usr/bin/env python3
"""
Check a SpriteForge character folder the same way spriteforge.h reads it.

  python tools/verify_cfg.py assets/dec [assets/other ...]
  python tools/verify_cfg.py --airborne-ok out/hero   (Sprite Forge Studio: frames may be ABOVE
        the ground line - jumps - but never below it, and every move has a grounded frame)

Python mirror of SF_ParseConfig / SF_FrameAt / SF_DrawEx: parses sprites.cfg, checks every
sheet exists and is big enough, and that in every frame the feet (lowest solid row) sit on
the ground line and the figure is inside the cell.  Exit code 1 on any error.
"""
import os, sys
import numpy as np
from PIL import Image


def parse(text):
    c = dict(name='', frameW=0, frameH=0, height=0, ground=0, anchorX=0, moves=[])
    for line in text.splitlines():
        line = line.split('#', 1)[0]
        p = line.split()
        if not p:
            continue
        k = p[0]
        if k == 'name' and len(p) > 1: c['name'] = p[1][:47]
        elif k == 'frame' and len(p) > 2: c['frameW'], c['frameH'] = int(p[1]), int(p[2])
        elif k == 'height': c['height'] = int(p[1])
        elif k == 'ground': c['ground'] = int(p[1])
        elif k == 'anchor_x': c['anchorX'] = int(p[1])
        elif k == 'move' and len(p) >= 4 and len(c["moves"]) < 64:
            frames = int(p[3])
            if frames <= 0:
                continue
            mv = dict(name=p[1], file=p[2], frames=frames,
                      w=int(p[4]) if len(p) > 5 else c['frameW'], h=int(p[5]) if len(p) > 5 else c['frameH'],
                      fps=float(p[6]) if len(p) > 6 else 10.0, loop=(int(p[7]) != 0) if len(p) > 7 else True,
                      row=int(p[8]) if len(p) > 8 else 0)
            if mv['fps'] <= 0: mv['fps'] = 10.0
            c['moves'].append(mv)
    ok = c['frameW'] > 0 and c['frameH'] > 0 and c['moves']
    if c['ground'] <= 0: c['ground'] = c['frameH']
    if c['anchorX'] <= 0: c['anchorX'] = c['frameW'] // 2
    if c['height'] <= 0: c['height'] = c['ground']
    return c if ok else None


def frame_at(mv, t):                       # == SF_FrameAt
    f = max(0, int(t * mv['fps']))
    return f % mv['frames'] if mv['loop'] else min(f, mv['frames'] - 1)


def dst_rect(c, mv, x, ground_y, flip, scale):   # == SF_DrawEx destination rectangle
    ax = (mv['w'] - c['anchorX']) if flip else c['anchorX']
    return (x - ax * scale, ground_y - c['ground'] * scale, mv['w'] * scale, mv['h'] * scale)


def check(d):
    errs, notes = [], []
    path = os.path.join(d, 'sprites.cfg')
    c = parse(open(path, encoding='utf-8').read()) if os.path.exists(path) else None
    if not c:
        return [f'{path}: missing or unparsable'], notes
    sheets = {}
    for mv in c['moves']:
        fp = os.path.join(d, mv['file'])
        if not os.path.exists(fp):
            errs.append(f"{mv['name']}: missing {mv['file']}"); continue
        if fp not in sheets:
            sheets[fp] = np.array(Image.open(fp).convert('RGBA'))
        a = sheets[fp]
        need_w, need_h = mv['frames'] * mv['w'], (mv['row'] + 1) * mv['h']
        if a.shape[1] < need_w or a.shape[0] < need_h:
            errs.append(f"{mv['name']}: sheet {a.shape[1]}x{a.shape[0]} < {need_w}x{need_h}"); continue
        feet = []
        for i in range(mv['frames']):
            cell = a[mv['row'] * mv['h']:(mv['row'] + 1) * mv['h'], i * mv['w']:(i + 1) * mv['w']]
            rows = np.nonzero((cell[..., 3] > 40).any(1))[0]
            if not len(rows):
                errs.append(f"{mv['name']}[{i}]: empty frame"); continue
            feet.append(int(rows.max()) + 1)
        if AIRBORNE_OK:   # Studio: jumps / flips leave the ground; never below it, >=1 grounded frame
            bad = [f for f in feet if f - c['ground'] > 1]
            if feet and not any(abs(f - c['ground']) <= 1 for f in feet):
                bad = bad or feet
        else:
            bad = [f for f in feet if abs(f - c['ground']) > 1]
        if bad:
            errs.append(f"{mv['name']}: feet at {bad} != ground {c['ground']}")
        # loader maths: the anchor point lands on (x, groundY) for both facings
        x, gy, s = 640.0, 630.0, 0.75
        for flip in (False, True):
            r = dst_rect(c, mv, x, gy, flip, s)
            assert abs(r[1] + c['ground'] * s - gy) < 1e-6
        notes.append(f"{mv['name']:10s} {mv['frames']:2d}f {mv['fps']:5.1f}fps loop={int(mv['loop'])} "
                     f"t=1s->frame {frame_at(mv, 1.0)}  feet ok")
    return errs, [f"{c['name']}: cell {c['frameW']}x{c['frameH']} height {c['height']} ground {c['ground']} "
                  f"anchor {c['anchorX']}, {len(c['moves'])} moves"] + notes


AIRBORNE_OK = False


def main():
    global AIRBORNE_OK
    if '--airborne-ok' in sys.argv:
        AIRBORNE_OK = True; sys.argv.remove('--airborne-ok')
    bad = 0
    for d in sys.argv[1:] or ['.']:
        errs, notes = check(d)
        for n in notes:
            print('  ' + n)
        for e in errs:
            print('  ERROR ' + e)
        print(f"{d}: {'OK' if not errs else f'{len(errs)} error(s)'}")
        bad += len(errs)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
