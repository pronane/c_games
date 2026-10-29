#!/usr/bin/env python3
"""Rebuild Flame and Dragon (the user's own SF-style sheets) as uniform grid sheets.

The original strips are NOT on a uniform grid (6 or 8 equal slices cut through
neighbouring poses, so the old loader showed bits of the next figure).  This uses the
same segmentation as tools/build_sprites.py: every pose is cut out on its own, scaled
so the fighter is the same height in every sheet, and placed feet-down in its own cell.
The bust-only sheets (block, victory, Flame's bum_fireball) are put on top of the
fighter's own legs from a guard-stance frame.

  python3 tools/legacy_fighters.py --out assets            (needs sprite_sources/flame|dragon)
The original sheets are only read, never changed.
"""
import argparse, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import build_sprites as B

T = B.TARGET_STAND

FIGHTERS = {
    'char_flame': {
        'idle':   dict(src='flame/taunt.png', stand_h=835, ft=0.12),
        'walk':   dict(src='flame/walk.png', stand_h=646, ft=0.09),
        'crouch': dict(src='flame/crouch.png', stand_h=620, pick=[0, 2, 4, 5], ft=0.06),
        'jump':   dict(src='flame/jump.png', stand_h=366, ft=0.065),
        'punch':  dict(src='flame/punch.png', stand_h=772, ft=0.07),
        'kick':   dict(src='flame/kick.png', stand_h=760, pick=[0, 1, 2, 4, 5, 6], ft=0.07),
        'pyramid_blast': dict(src='flame/pyramid_blast.png', stand_h=530, ft=0.08),
        'hit':    dict(src='flame/hit.png', stand_h=790, ft=0.10),
        'throw':  dict(src='flame/throw.png', stand_h=646, nsplit=6, ft=0.07),
        'jump_attack': dict(src='flame/jump_attack.png', stand_h=517, ft=0.06),
        'block':  dict(bust='flame/block.png', nsplit=6, legs=('flame/walk.png', 646, 0), ft=0.12),
        'victory': dict(bust='flame/victory.png', legs=('flame/walk.png', 646, 0), ft=0.12),
        'bum_fireball': dict(bust='flame/bum_fireball.png', nsplit=6, legs=('flame/walk.png', 646, 0), ft=0.08),
    },
    'char_dragon': {
        'idle':   dict(src='dragon/idle.png', stand_h=903, nsplit=6, ft=0.12),
        'walk':   dict(src='dragon/walk.png', stand_h=498, ft=0.09),
        'crouch': dict(src='dragon/crouch.png', stand_h=760, pick=[0, 2, 4, 5], ft=0.06),
        'jump':   dict(src='dragon/jump.png', stand_h=504, ft=0.10),
        'punch':  dict(src='dragon/punch.png', stand_h=732, ft=0.07),
        'kick':   dict(src='dragon/kick.png', stand_h=649, pick=[0, 1, 2, 4, 5, 6], ft=0.07),
        'pyramid_blast': dict(src='dragon/pyramid_blast.png', stand_h=549, ft=0.08),
        'bum_fireball': dict(src='dragon/bum_fireball.png', stand_h=600, nsplit=10, ft=0.08),
        'hit':    dict(src='dragon/hit.png', stand_h=788, ft=0.10),
        'throw':  dict(src='dragon/throw.png', stand_h=582, ft=0.07),
        'jump_attack': dict(src='dragon/jump_attack.png', stand_h=646, ft=0.06),
        'taunt':  dict(src='dragon/taunt.png', stand_h=760, ft=0.12),
        'block':  dict(bust='dragon/block.png', legs=('dragon/punch.png', 732, 0), ft=0.12),
        'victory': dict(bust='dragon/victory.png', legs=('dragon/punch.png', 732, 0), ft=0.12),
    },
}
# bust geometry, in SOURCE pixels of the bust sheet: head height (crown to chin) and the
# x of the face centre inside a trimmed bust frame (fraction of its width)
BUST = {
    'flame/block.png':        dict(head=205, face_x=0.42),
    'flame/victory.png':      dict(head=159, face_x=0.45),
    'flame/bum_fireball.png': dict(head=138, face_x=0.22),
    'dragon/block.png':       dict(head=200, face_x=0.45),
    'dragon/victory.png':     dict(head=131, face_x=0.40),
}
HEAD_FRAC = 0.116        # head height / standing height of these fighters
PROJ = {'char_flame': 'fire', 'char_dragon': 'fire_blue'}

def head_top(f):
    """first row whose opaque run is head-wide (skips raised fists)"""
    a = f[..., 3] > 40
    w = a.sum(1)
    return int(np.argmax(w > 0))

def bust_frames(spec):
    legs_src, legs_h, li = spec['legs']
    L = B.extract(dict(src=legs_src, stand_h=legs_h))[li]
    geo = BUST[spec['bust']]
    s = (HEAD_FRAC * T) / geo['head']             # bust px -> target px
    raw = B.extract(dict(src=spec['bust'], stand_h=T / s, nsplit=spec.get('nsplit', 1)) if 'nsplit' in spec
                    else dict(src=spec['bust'], stand_h=T / s))
    lh, lw = L.shape[:2]
    lax = B.body_anchor_x(L)
    out = []
    for bf in raw:
        bh, bw = bf.shape[:2]
        # face column of the bust goes over the legs frame's body column; the crown of the
        # bust's head goes where the legs frame's crown is
        fx = geo['face_x'] * bw
        # rows of the bust above its crown (raised fists): crown = first wide row
        wid = (bf[..., 3] > 40).sum(1)
        crown = int(np.argmax(wid > 0.35 * HEAD_FRAC * T))
        H = max(lh, lh - 0 + crown + 40)
        pad_top = crown
        W = max(lw, bw) * 2 + 40
        canvas = np.zeros((lh + pad_top + 20, W, 4), np.uint8)
        ox = W // 2 - int(lax)
        oy = pad_top + 20
        canvas[oy:oy + lh, ox:ox + lw] = L
        bx = W // 2 - int(fx)
        by = oy - crown
        # bust bottom edge fades into the legs frame (no hard line at the cut)
        b = bf.astype(float)
        fade = min(24, bh // 6)
        ramp = np.ones(bh); ramp[bh - fade:] = np.linspace(1, 0, fade)
        b[..., 3] *= ramp[:, None]
        # hide the legs frame's upper body under / beside the bust (its arms would poke out)
        cut = by + bh - fade
        canvas[:max(0, cut), :, 3] = 0
        im = Image.fromarray(canvas)
        im.alpha_composite(Image.fromarray(np.clip(b, 0, 255).astype(np.uint8)), (bx, max(0, by)))
        canvas = np.asarray(im)
        out.append(B.trim(canvas))
    return out

def build(folder, out_root, only=None):
    anims = FIGHTERS[folder]
    real = {}
    for name, spec in anims.items():
        if only and name not in only:
            continue
        real[name] = spec
    # build_character understands plain specs; give it pre-made frames for the busts
    orig_extract = B.extract
    def ext(spec):
        if 'bust' in spec:
            return bust_frames(spec)
        return orig_extract(spec)
    B.extract = ext
    try:
        B.PROJECTILE[folder] = PROJ[folder]
        res = B.build_character(folder, real, out_root)
    finally:
        B.extract = orig_extract
    # the user's own folder already holds the original idle.png, walk.png ...: the rebuilt
    # sheets are written as g_<anim>.png next to them, so nothing original is overwritten
    d = os.path.join(out_root, folder)
    cfg = open(os.path.join(d, 'sprites.cfg')).read().split('\n')
    new = []
    for line in cfg:
        p = line.split()
        if len(p) >= 3 and p[0] == 'anim' and not p[2].startswith('g_'):
            os.replace(os.path.join(d, p[2]), os.path.join(d, 'g_' + p[2]))
            p[2] = 'g_' + p[2]
            line = ' '.join(p)
        new.append(line)
    new.insert(1, '# Flame/Dragon rebuilt from the original sheets by tools/legacy_fighters.py;'
                  ' delete this file to go back to the original sheets')
    open(os.path.join(d, 'sprites.cfg'), 'w').write('\n'.join(new))
    write_portrait(d)
    return res

def write_portrait(d):
    # head-and-shoulders for the select screen / face-off, cut from idle frame 0
    cfg = open(os.path.join(d, 'sprites.cfg')).read().split()
    cw, chh = int(cfg[cfg.index('cell') + 1]), int(cfg[cfg.index('cell') + 2])
    a = np.array(Image.open(os.path.join(d, 'g_idle.png')).convert('RGBA'))[:chh, :cw]
    m = a[..., 3] > 60
    ys, xs = np.nonzero(m)
    y0, H = ys.min(), ys.max() - ys.min() + 1
    hx = np.nonzero(m[y0:y0 + int(H * 0.12)])[1].mean()
    ch = int(H * 0.36); w = int(ch * 0.82)
    x0 = int(round(hx - w / 2)); top = max(0, int(y0 - H * 0.03))
    out = np.zeros((ch, w, 4), np.uint8)
    sx0, sx1 = max(0, x0), min(a.shape[1], x0 + w)
    piece = a[top:top + ch, sx0:sx1]
    out[:piece.shape[0], sx0 - x0:sx0 - x0 + piece.shape[1]] = piece
    Image.fromarray(out).save(os.path.join(d, 'portrait.png'), optimize=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(B.ROOT, 'assets'))
    ap.add_argument('--only', default=None, help='char_flame or char_dragon')
    ap.add_argument('--anims', default=None)
    ap.add_argument('--preview', default=None)
    a = ap.parse_args()
    for folder in FIGHTERS:
        if a.only and folder != a.only:
            continue
        cw, sheets = build(folder, a.out, a.anims.split(',') if a.anims else None)
        if a.preview:
            os.makedirs(a.preview, exist_ok=True)
            B.contact_sheet(folder, cw, sheets, os.path.join(a.preview, f'contact_{folder}.png'))

if __name__ == '__main__':
    main()
