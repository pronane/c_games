#!/usr/bin/env python3
"""
Import the three Padel Wars fighters (PADEL MIKE, DARAGH, DANGEROUS DEC) from
egyptian_fighter/assets/char_* into HD Fighter 2's roster.

HD Fighter 2 draws a fighter by slicing ONE horizontal strip per state into
cells of (image_width / frame_count) x image_height, and the existing six
fighters all use 192x256 cells holding a 157 px figure whose feet sit on
y=243.  The Egyptian Fighter art is already a uniform grid (cell 624x800 for
Mike and Daragh, 480x800 for Dec, feet on a common baseline, standing height
560 px), so the importer

  * re-cells every pose so the torso is centred on the cell's middle (that is
    where HD Fighter puts fighter.x) and the feet land on y=243,
  * scales every pose of a character by one factor so it stands exactly as
    tall as KAIRO,
  * drops the 1 px background fringe the source sheets carry,
  * removes the red damage tint baked into the source `hit` frames,
  * gives the three fighters the two states their source art lacks (super and
    lose) by restyling frames they do have,
  * writes assets_hd/sprites/<id>_<state>.png, assets_hd/select/portrait_<id>.png
    and registers them in assets_hd/meta.json.

Run from the repository root:
    python3 HD_Fighter/tools/import_padel_fighters.py
    python3 HD_Fighter/tools/import_padel_fighters.py --preview /tmp/preview
Needs: pip install pillow numpy
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_ASSETS = os.path.join(ROOT, 'egyptian_fighter', 'assets')
OUT = os.path.join(ROOT, 'HD_Fighter', 'assets_hd')
# assets_hd/ is a byte-identical copy of the online client's public/assets_hd, used
# by the desktop game (game.py).  Write both so the two rosters cannot drift.
OUT_WEB = os.path.join(ROOT, 'HD_Fighter', 'multiplayer', 'public', 'assets_hd')

# Same geometry as the six original fighters (kairo_idle.png is 960x256: five
# 192x256 cells, figure 157 px tall, feet on y=243).
CELL_W, CELL_H = 192, 256
# The photos are thinner than the drawn originals, so a photorealistic fighter
# at exactly KAIRO's height looks small on stage; 1.12x gives it the same
# visual weight without changing the cell or the feet line.
STAND_H = 176
FEET_Y = 243
FRINGE_ALPHA = 40      # source pixels fainter than this are background noise
RED_LIMIT = 18         # red above max(green, blue) by more than this is a damage tint

# HD state -> (source sheet, frames wanted, frames this long).  Egyptian Fighter
# splits its moves into one punch sheet and one kick sheet; HD Fighter wants light
# and heavy versions of each, taken from the early and the late part of the sheet.
# The third number is the state's tick length from game.js's DUR table, which the
# desktop build (game.py) also reads as "frames per sprite frame".
STATES = [
    ('idle',     'idle',           6, 6),
    ('walk',     'walk',           7, 4),
    ('crouch',   'crouch',         4, 8),
    ('jump',     'jump',           5, 5),
    ('lp',       'punch',          3, 3),   # jab: wind-up, snap, follow-through
    ('hp',       'punch',          3, 4),   # heavy: fully extended
    ('lk',       'kick',           3, 3),
    ('hk',       'kick',           3, 4),
    ('block',    'block',          4, 8),
    ('throw',    'throw',          5, 4),
    ('hit',      'hit',            4, 5),
    ('special1', 'pyramid_blast',  6, 4),
    ('special2', 'bum_fireball',   5, 3),
    ('super',    'kick',           5, 4),   # restyled, see build_super
    ('win',      'victory',        6, 6),
    ('lose',     'hit',            4, 8),   # restyled, see build_lose
]

# Light attacks read the first frames of the source sheet, heavies the last.
FRAME_PICKS = {('punch', 'lp'): 'first', ('punch', 'hp'): 'last',
               ('kick', 'lk'): 'first', ('kick', 'hk'): 'last'}

CHARS = [
    {'src': 'char_mike',   'id': 'mike',   'name': 'PADEL MIKE',    'style': 'PADEL SMASH'},
    {'src': 'char_daragh', 'id': 'daragh', 'name': 'DARAGH',        'style': 'THE FLYNN'},
    {'src': 'char_dec',    'id': 'dec',    'name': 'DANGEROUS DEC', 'style': 'SUITED & BOOTED'},
]


def read_cfg(folder):
    """cell width, baseline and per-sheet frame counts out of sprites.cfg."""
    cfg = {'cell': 624, 'baseline': 787, 'anim': {}}
    with open(os.path.join(SRC_ASSETS, folder, 'sprites.cfg')) as fh:
        for line in fh:
            parts = line.split()
            if not parts or parts[0].startswith('#'):
                continue
            if parts[0] == 'cell' and len(parts) >= 3:
                cfg['cell'] = int(parts[1])
            elif parts[0] == 'baseline' and len(parts) >= 2:
                cfg['baseline'] = int(parts[1])
            elif parts[0] == 'anim' and len(parts) >= 4:
                cfg['anim'][parts[1]] = int(parts[3])
    return cfg


def load_frames(folder, sheet, cell):
    """Split one source strip into RGBA frames with the fringe removed."""
    path = os.path.join(SRC_ASSETS, folder, sheet + '.png')
    if not os.path.exists(path):
        return []
    im = Image.open(path).convert('RGBA')
    n = max(1, im.width // cell)
    arr = np.array(im)
    arr[..., 3] = np.where(arr[..., 3] < FRINGE_ALPHA, 0, arr[..., 3])
    im = Image.fromarray(arr)
    return [im.crop((i * cell, 0, (i + 1) * cell, im.height)) for i in range(n)]


def trim(fr):
    """Crop a frame to its visible pixels, or (None, None) if it is empty."""
    a = np.array(fr)[..., 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0:
        return None
    return fr.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def neutralise_red(im):
    """Remove the red damage flash Egyptian Fighter bakes into its hit frames.

    Only the red channel is capped, at the level of the green/blue of the same
    pixel, so skin and the green shirt print keep their colour.
    """
    a = np.array(im).astype(np.int32)
    rgb = a[..., :3]
    cap = np.maximum(rgb[..., 1], rgb[..., 2]) + RED_LIMIT
    rgb[..., 0] = np.minimum(rgb[..., 0], cap)
    a[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(a.astype(np.uint8), 'RGBA')


def anchor_x(im):
    """x of the torso centre: alpha centroid of the upper body.

    Legs swing, arms punch and the padel racket hangs off to one side, so the
    bounding box is a poor anchor.  Head, shoulders and torso stay over the
    feet, which is where HD Fighter draws fighter.x.
    """
    a = np.array(im)[..., 3].astype(np.float32)
    rows = np.where(a.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    torso = a[top:top + max(1, int((bottom - top) * 0.45))]
    cols = torso.sum(axis=0)
    if cols.sum() <= 0:
        cols = a.sum(axis=0)
    xs = np.arange(len(cols))
    return float((cols * xs).sum() / cols.sum())


def aura(im, colour=(255, 198, 60), size=5, strength=1.0, pulsing=False):
    """Gold rim light, how the game marks a super (the Egyptian art bakes it in)."""
    alpha = im.getchannel('A')
    grown = alpha.filter(ImageFilter.GaussianBlur(size / 2)).point(lambda v: 255 if v > 24 else 0)
    rim = np.clip((np.array(grown).astype(np.float32) - np.array(alpha).astype(np.float32)), 0, 255)
    layer = np.zeros((im.height, im.width, 4), np.uint8)
    layer[..., 0], layer[..., 1], layer[..., 2] = colour
    layer[..., 3] = np.clip(rim * (0.85 if pulsing else 1.0) * strength, 0, 255).astype(np.uint8)
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    out.alpha_composite(Image.fromarray(layer, 'RGBA'))
    out.alpha_composite(im)
    return out


def desaturate(im, amount=0.65):
    """Drain the colour, for the lose/KO pose."""
    a = np.array(im).astype(np.float32)
    grey = a[..., :3].mean(axis=2, keepdims=True)
    a[..., :3] = a[..., :3] * (1 - amount) + grey * amount
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')


def pick(frames, want):
    """Resample a source strip down to at most `want` frames."""
    if len(frames) <= want:
        return list(frames)
    idx = np.linspace(0, len(frames) - 1, want).round().astype(int)
    return [frames[i] for i in idx]


def place(fr, scale, effect=None):
    """Scale one pose into a CELL_W x CELL_H transparent cell."""
    img = trim(fr)
    if img is None:
        return None
    ax = anchor_x(img)
    w = max(1, int(round(img.width * scale)))
    h = max(1, int(round(img.height * scale)))
    img = img.resize((w, h), Image.LANCZOS)
    ax *= scale
    if effect == 'aura':
        img = aura(img)
    elif effect == 'aura_soft':
        img = aura(img, strength=0.55, pulsing=True)
    elif effect == 'ko':
        img = desaturate(img)
    cell = Image.new('RGBA', (CELL_W, CELL_H), (0, 0, 0, 0))
    x = int(round(CELL_W / 2 - ax))
    y = FEET_Y - h
    # HD Fighter never crops a frame, so keep the pose inside its cell and let
    # a raised-arm jump poke up out of the top rather than sink into the floor.
    x = max(0, min(x, CELL_W - w))
    if y >= 0:
        cell.alpha_composite(img, (x, y))
    else:
        cell.alpha_composite(img.crop((0, 0, w, h + y)), (x, 0))
    return cell


def stand_height(frames):
    """Median visible height of a character's idle poses, in source pixels."""
    heights = []
    for fr in frames:
        img = trim(fr)
        if img is not None:
            heights.append(img.height)
    return float(np.median(heights)) if heights else 560.0


def build_sheets(folder):
    cfg = read_cfg(folder)
    cell = cfg['cell']
    cache = {}

    def sheet_frames(name):
        if name not in cache:
            cache[name] = load_frames(folder, name, cell)
        return cache[name]

    scale = STAND_H / stand_height(sheet_frames('idle'))
    sheets = {}
    for state, sheet, want, dur in STATES:
        frames = sheet_frames(sheet)
        if not frames:
            print(f'  ! {folder}: no {sheet}.png, skipping {state}')
            continue
        if state == 'hit':
            frames = [neutralise_red(f) for f in frames]
        if state == 'lp':
            chosen, effects = frames[:want], [None] * want
        elif state == 'hp':
            chosen, effects = frames[-want:], [None] * want
        elif state == 'lk':
            chosen, effects = frames[:want], [None] * want
        elif state == 'hk':
            chosen, effects = frames[-want:], [None] * want
        elif state == 'super':
            chosen = pick(frames, want)
            effects = ['aura' if 1 <= i < len(chosen) - 1 else 'aura_soft'
                       for i in range(len(chosen))]
        elif state == 'lose':
            chosen = list(reversed(frames))[:want]
            effects = ['ko'] * len(chosen)
        else:
            chosen = pick(frames, want)
            effects = [None] * len(chosen)
        cells = [c for c in (place(fr, scale, fx) for fr, fx in zip(chosen, effects))
                 if c is not None]
        if not cells:
            continue
        strip = Image.new('RGBA', (CELL_W * len(cells), CELL_H), (0, 0, 0, 0))
        for i, c in enumerate(cells):
            strip.alpha_composite(c, (i * CELL_W, 0))
        sheets[state] = (strip, len(cells), dur)
    return sheets


def build_portrait(folder, name):
    """128x128 select tile, like portrait_kairo.png."""
    src = os.path.join(SRC_ASSETS, folder, 'portrait.png')
    im = trim(Image.open(src).convert('RGBA'))
    if im is None:
        return None
    w, h = im.size
    s = min(122.0 / w, 122.0 / h)
    im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    tile = Image.new('RGBA', (128, 128), (10, 13, 26, 255))
    glow = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-24, 66, 152, 194), fill=(96, 62, 168, 110))
    tile.alpha_composite(glow)
    tile.alpha_composite(im, ((128 - im.width) // 2, 128 - im.height - 3))
    d = ImageDraw.Draw(tile)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 13)
    except OSError:
        font = ImageFont.load_default()
    label = name.split()[-1]
    tw = d.textlength(label, font=font)
    d.text(((128 - tw) / 2 + 1, 107), label, font=font, fill=(0, 0, 0, 230))
    d.text(((128 - tw) / 2, 106), label, font=font, fill=(255, 208, 0, 255))
    return tile.convert('RGB')


def write_both(strip, name, folder):
    for base in (OUT, OUT_WEB):
        strip.save(os.path.join(base, folder, name), optimize=True)


def contact_sheet(tiles, path):
    """Preview every new state next to a real HD Fighter frame."""
    ref = os.path.join(OUT, 'sprites', 'kairo_idle.png')
    if os.path.exists(ref):
        tiles.insert(0, ('kairo idle', Image.open(ref).convert('RGBA').crop((0, 0, CELL_W, CELL_H))))
    cols = 9
    rows = (len(tiles) + cols - 1) // cols
    cv = Image.new('RGBA', (cols * CELL_W, rows * (CELL_H + 18)), (24, 28, 44, 255))
    d = ImageDraw.Draw(cv)
    for i, (label, img) in enumerate(tiles):
        x, y = (i % cols) * CELL_W, (i // cols) * (CELL_H + 18)
        cv.alpha_composite(img, (x, y + 16))
        d.text((x + 4, y + 2), label, fill=(255, 210, 0, 255))
    cv.save(path)
    print('preview ->', path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview', help='write a contact sheet of the new frames here')
    args = ap.parse_args()

    for base in (OUT, OUT_WEB):
        os.makedirs(os.path.join(base, 'sprites'), exist_ok=True)
        os.makedirs(os.path.join(base, 'select'), exist_ok=True)
    with open(os.path.join(OUT, 'meta.json')) as fh:
        meta = json.load(fh)

    tiles = []
    for spec in CHARS:
        cid, folder = spec['id'], spec['src']
        cfg = read_cfg(folder)
        print(f'{folder} -> {cid}  (source cell {cfg["cell"]}x800)')
        sheets = build_sheets(folder)
        entry = {}
        for state, (strip, count, dur) in sheets.items():
            name = f'{cid}_{state}.png'
            write_both(strip, name, 'sprites')
            entry[state] = [f'sprites/{name}', count, dur]
            print(f'   {name:24s} {strip.width:4d}x{CELL_H}  {count} frames')
        portrait = build_portrait(folder, spec['name'])
        if portrait is not None:
            write_both(portrait, f'portrait_{cid}.png', 'select')
            print(f'   portrait_{cid}.png     128x128')
        tiles.append((f'{cid} idle', sheets['idle'][0].crop((0, 0, CELL_W, CELL_H))))
        if 'super' in sheets:
            tiles.append((f'{cid} super', sheets['super'][0].crop(((sheets['super'][1] // 2) * CELL_W, 0,
                                                                 (sheets['super'][1] // 2 + 1) * CELL_W, CELL_H))))
        meta['characters'][cid] = entry
        meta['select'][cid] = f'select/portrait_{cid}.png'

    # roster order: the six originals, then the padel trio
    order = [c['id'] for c in CHARS]
    chars = meta['characters']
    meta['characters'] = {k: chars[k] for k in chars if k not in order}
    meta['characters'].update({k: chars[k] for k in order})
    for base in (OUT, OUT_WEB):
        with open(os.path.join(base, 'meta.json'), 'w') as fh:
            json.dump(meta, fh, indent=2)
            fh.write('\n')
    print('meta.json updated:', ', '.join(order))

    if args.preview:
        contact_sheet(tiles, os.path.join(args.preview, 'padel_frames.png'))


if __name__ == '__main__':
    main()
