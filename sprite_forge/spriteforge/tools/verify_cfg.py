#!/usr/bin/env python3
"""
Check a SpriteForge character folder the same way spriteforge.h reads it.

  python tools/verify_cfg.py assets/dec [assets/other ...]
  python tools/verify_cfg.py --airborne-ok out/hero   (Sprite Forge Studio: frames may be ABOVE
        the ground line - jumps - but never below it, and every move has a grounded frame)

Python mirror of SF_ParseConfig / SF_FrameAt / SF_DrawEx: parses sprites.cfg, checks every
sheet exists and is big enough, and that in every frame the feet (lowest solid row) sit on
the ground line and the figure is inside the cell.  Exit code 1 on any error.

v7.1: also reads the Egyptian Fighter / Padel Wars grid format written by `forge.py export-ef`
(cell W H / baseline / stand_height / anim <state> <file> <frames> <frame_time> / projectile) and
mirrors that game's LoadSpritesGrid: frames = sheet width / cell width, one row, origin at the cell
centre on the baseline.  Extra checks there: the sheet width is exactly frames x cell, no visible pixel
touches a cell edge (clipping), and idle frame 0's height matches stand_height (one common height).
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
        if k == 'cell' and len(p) > 2: c['frameW'], c['frameH'] = int(p[1]), int(p[2]); c['ef'] = True
        elif k == 'baseline': c['ground'] = int(p[1])
        elif k == 'stand_height': c['height'] = int(p[1])
        elif k == 'projectile' and len(p) > 1: c['projectile'] = p[1]
        elif k == 'anim' and len(p) >= 5:
            ft = float(p[4])
            c['moves'].append(dict(name=p[1], file=p[2], frames=int(p[3]), w=c['frameW'], h=c['frameH'],
                                   fps=(1.0 / ft) if ft > 0 else 10.0, loop=p[1] in ('idle', 'walk', 'crouch', 'block', 'taunt', 'victory'),
                                   row=0, frame_time=ft))
        elif k == 'name' and len(p) > 1: c['name'] = p[1][:47]
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
        if c.get('ef'):     # the game takes frames = width / cell width
            if a.shape[1] % mv['w'] or a.shape[1] // mv['w'] != mv['frames']:
                errs.append(f"{mv['name']}: sheet width {a.shape[1]} is not {mv['frames']} x {mv['w']} (game would see {a.shape[1] // mv['w']} frames)")
            if a.shape[0] != mv['h']:
                errs.append(f"{mv['name']}: sheet height {a.shape[0]} != cell height {mv['h']}")
            edge = []
            for i in range(mv['frames']):
                al = a[:mv['h'], i * mv['w']:(i + 1) * mv['w'], 3] > 40
                if al[:, 0].any() or al[:, -1].any() or al[0].any():
                    edge.append(i)
            if edge:
                errs.append(f"{mv['name']}: frames {edge} touch the cell edge (clipped)")
            if mv['name'] == 'idle':
                al = a[:mv['h'], :mv['w'], 3] > 40
                rows = np.nonzero(al.any(1))[0]
                if len(rows) and abs((c['ground'] - rows.min()) - c['height']) > max(4, 0.02 * c['height']):
                    notes.append(f"WARN idle visible height {c['ground'] - rows.min()} != stand_height {c['height']} (draws {300.0 * (c['ground'] - rows.min()) / c['height']:.0f} px tall in game)")
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
        notes.append(f"{mv['name']:10s} {mv['frames']:2d}f {mv['fps']:5.1f}fps" + (f" ({mv['frame_time']:.3f}s)" if 'frame_time' in mv else '') + (" loop=game" if 'frame_time' in mv else f" loop={int(mv['loop'])}") + " "
                     f"t=1s->frame {frame_at(mv, 1.0)}  feet ok")
    fmt = ("EF grid format, projectile %s" % c.get('projectile', 'none')) if c.get('ef') else "SpriteForge v1 format"
    return errs, [f"{c['name'] or os.path.basename(os.path.abspath(d))}: cell {c['frameW']}x{c['frameH']} height {c['height']} ground {c['ground']} "
                  f"anchor {c['anchorX']}, {len(c['moves'])} moves ({fmt})"] + notes


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
