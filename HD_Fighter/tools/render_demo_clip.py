#!/usr/bin/env python3
"""
Render the demo clip at the top of the web page: PADEL MIKE vs DARAGH, 10 s.

The clip is produced by the real game (game.py), not by a mock: this script
builds a Match, feeds each fighter a scripted input table, steps the game at a
fixed 1/60 s, and writes every frame. That way the clip shows what the engine
actually draws - the same sprite cells, hit sparks, hitstop flash, screen shake,
block sparks, super meter and KO banner a player sees.

    python3 HD_Fighter/tools/render_demo_clip.py
    python3 HD_Fighter/tools/render_demo_clip.py --out /tmp/demo.mp4 --keep-frames

Needs: pip install pygame imageio-ffmpeg
Run headless with SDL_VIDEODRIVER=dummy (the script sets it itself).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402  (after the SDL env vars)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAME_DIR = os.path.join(ROOT, 'HD_Fighter')
OUT_DEFAULT = os.path.join(ROOT, 'HD_Fighter', 'multiplayer', 'public', 'videos', 'demo.mp4')
OUT_MIRROR = os.path.join(ROOT, 'HD_Fighter', 'videos', 'demo.mp4')

FPS = 60
SECONDS = 10
OUT_W = 960        # the page embeds the clip at <=520 px wide
P1, P2 = 'mike', 'daragh'
STAGE = 0          # rooftop: the neon stage the clip opens on
ZOOM = 2.6         # camera crop on the pair, so they fill the frame

# The script says "hold right", "press hp"; each key set below is the one the
# game itself binds for that player (game.py: KEYSETS), so the clip exercises
# the same controls a person would press.
def keyset_for(module, player):
    bind = module.KEYSETS[player]
    out = {}
    for action, codes in bind.items():
        out[action] = sorted(codes)[0]      # one representative key per action
    return out

# One line per beat of the fight.  Frames are 1/60 s, so 60 frames = 1 s.
# (start_frame, end_frame, p1_keys, p2_keys)
SCRIPT = [
    # (start, end, mike, daragh) - frames at 60/s.  Everything is a plain
    # "hold this button" so the engine does the interpreting.
    (  0,  30, []            , []            ),               # square up
    ( 30,  66, ['right']     , []            ),               # Mike closes in
    ( 66,  78, ['hp']        , []            ),               # heavy punch
    ( 78,  98, []            , ['block']     ),               # Daragh blocks
    ( 86, 100, ['hp']        , []            ),               # second punch
    (100, 120, []            , ['hp']        ),               # Daragh counters
    (120, 142, []            , []            ),
    (142, 158, ['right']     , []            ),               # Mike steps back in
    (158, 170, ['lk']        , []            ),               # low kick
    (170, 186, []            , []            ),
    (186, 198, []            , ['lp']        ),               # Daragh jab
    (198, 214, []            , []            ),
    (214, 226, ['right']     , []            ),
    (226, 238, ['hk']        , []            ),               # spinning kick
    (238, 256, []            , []            ),
    (256, 268, []            , ['hk']        ),               # Daragh heavy kick
    (268, 284, []            , []            ),
    (284, 296, ['lp']        , []            ),               # jab
    (296, 306, ['lp']        , []            ),               # jab
    (306, 322, ['hp']        , []            ),               # heavy finisher
    (322, 372, []            , []            ),               # breathe
    (372, 390, ['right']     , []            ),
    (390, 404, ['special1']  , []            ),               # padel blast
    (404, 430, []            , ['block']     ),
    (430, 444, []            , ['hp']        ),               # Daragh answers
    (444, 460, []            , []            ),
    (460, 474, ['hk']        , []            ),
    (474, 494, []            , []            ),
    (494, 508, []            , ['special2']  ),               # Daragh special
    (508, 526, []            , []            ),
    (526, 540, ['right']     , []            ),
    (540, 556, ['hk']        , []            ),               # final kick
    (556, 600, []            , []            ),
]

class _KeyTable(dict):
    """A pygame-style key state table that answers False for anything unset."""

    def __missing__(self, key):
        return False


def render_frame(match, module, zoom=1.0):
    """Draw one frame and return it as a 1280x720 surface.

    The desktop build draws the full stage with the fighters at their true
    size, which leaves a lot of empty sky above them in a 10-second clip.  The
    camera closes in on the pair by cropping a window out of the frame that
    keeps the HUD (top 108 px) intact and places the ground line near the
    bottom, then scales that window back to 1280x720.  Every pixel is one the
    engine drew; only the framing changes.
    """
    match.draw()
    if zoom == 1.0:
        return match.screen

    w, h = match.screen.get_size()
    zw, zh = int(w / zoom), int(h / zoom)
    hud_h = 108
    # ground line sits at GROUND_Y; put it ~78% down the crop
    ground = module.GROUND_Y
    top = int(ground - zh * 0.78)
    top = max(hud_h - 6, min(top, h - zh))
    cx = (match.p1.x + match.p2.x) / 2
    cx = max(zw / 2, min(cx, w - zw / 2))
    crop = match.screen.subsurface((int(cx - zw / 2), top, zw, zh)).copy()

    out = pygame.Surface((w, h))
    # stage backdrop behind the HUD strip, so the bar keeps its own background
    frame = pygame.Surface((w, h))
    frame.blit(pygame.transform.smoothscale(crop, (w, h)), (0, 0))
    frame.blit(match.screen, (0, 0), pygame.Rect(0, 0, w, hud_h))
    return frame


def actions_at(frame):
    """What each player is holding on this frame, from the SCRIPT beats."""
    for start, end, p1, p2 in SCRIPT:
        if start <= frame < end:
            return p1, p2
    return [], []


ACTION_ALIASES = {'jump': 'up'}


def held(actions, table, bind):
    """Fill a pygame-style key table from a list of action names."""
    table.clear()
    for name in actions:
        table[bind[ACTION_ALIASES.get(name, name)]] = True
    return table


def build_frames(module):
    """Step the game for SECONDS and yield one RGB surface per frame."""
    pygame.init()
    pygame.display.set_mode((module.SCREEN_W, module.SCREEN_H))
    pygame.display.set_caption('render_demo_clip')

    match = module.Match(P1, P2, STAGE)
    # Facing is set from x each frame, so start the pair at a good distance.
    match.p1.x, match.p2.x = 470.0, 780.0


    p1_bind, p2_bind = keyset_for(module, 1), keyset_for(module, 2)
    p1_keys, p2_keys = {}, {}
    frames = SECONDS * FPS
    for frame in range(frames):
        p1_actions, p2_actions = actions_at(frame)
        held(p1_actions, p1_keys, p1_bind)
        held(p2_actions, p2_keys, p2_bind)
        # The engine reads one pygame-style key table and lets each fighter
        # test its own bindings, so both players' state lives in one mapping.
        # It indexes that mapping directly, so every key it asks about has to
        # answer - including the ones nobody is holding.
        both = _KeyTable()
        both.update(p1_keys)
        both.update(p2_keys)

        dt = 1.0 / FPS
        if not match.round_over and not match.game_over:
            match.p1.update(dt, match.p2, both, [], match.projectiles,
                            match.hitstop, match.screenshake)
            match.p2.update(dt, match.p1, both, [], match.projectiles,
                            match.hitstop, match.screenshake)
            for pr in match.projectiles:
                pr.update()
            match.projectiles = [p for p in match.projectiles if p.active]
            match.check_hits()
            match.stage.update(match.p1, match.p2)
            match.hitstop.update(dt)
            match.screenshake.update(dt)
            match.update_sparks(dt)
            if not match.hitstop.active():
                match.timer_acc += dt
                if match.timer_acc >= 1.0:
                    match.timer_acc = 0.0
                    match.timer = max(0, match.timer - 1)

        yield pygame.image.tostring(render_frame(match, module, zoom=ZOOM), 'RGB')


def encode(frames, out_path, keep_frames=False):
    ffmpeg = None
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('ffmpeg not found: pip install imageio-ffmpeg')

    work = tempfile.mkdtemp(prefix='hdf_demo_')
    try:
        for i, raw in enumerate(frames):
            path = os.path.join(work, f'{i:04d}.ppm')
            # PPM is a 2-line header plus raw RGB, so writing it is cheap and
            # needs no image library at all.
            with open(path, 'wb') as fh:
                fh.write(b'P6\n1280 720\n255\n')
                fh.write(raw)
        cmd = [
            ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
            '-framerate', str(FPS), '-i', os.path.join(work, '%04d.ppm'),
            '-vf', f'scale={OUT_W}:-2:flags=lanczos',
            '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '4.0',
            '-pix_fmt', 'yuv420p', '-preset', 'veryslow', '-crf', '30',
            '-movflags', '+faststart', '-an', out_path,
        ]
        subprocess.run(cmd, check=True)
    finally:
        if keep_frames:
            print('frames kept in', work)
        else:
            shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--keep-frames', action='store_true')
    args = ap.parse_args()

    sys.path.insert(0, GAME_DIR)
    os.chdir(GAME_DIR)
    import importlib.util
    spec = importlib.util.spec_from_file_location('hd_fighter_game', os.path.join(GAME_DIR, 'game.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.toggle_graphics()          # the Padel trio only exists as HD art
    assert P1 in module.FIGHTER_INFO and P2 in module.FIGHTER_INFO, 'fighters missing from roster'

    print(f'rendering {P1} vs {P2}, {SECONDS}s at {FPS} fps...')
    encode(list(build_frames(module)), args.out, args.keep_frames)
    size = os.path.getsize(args.out)
    print(f'wrote {args.out} ({size / 1024:.0f} KB)')

    os.makedirs(os.path.dirname(OUT_MIRROR), exist_ok=True)
    shutil.copyfile(args.out, OUT_MIRROR)
    print(f'wrote {OUT_MIRROR}')


if __name__ == '__main__':
    main()
