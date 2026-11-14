#!/usr/bin/env python3
"""
Headless checks for the desktop build's fight rules (game.py).

These cover the bugs the demo clip exposed.  Each one made the desktop build
look fine in a screenshot but play wrong: a fighter who never stood up after
being hit, a block that hurt more than a clean hit, a P2 keyboard that did
nothing, fighters standing inside each other, and a damage flash that never
faded.  Run it headless:

    python3 HD_Fighter/tools/test_fight_rules.py
Needs: pip install pygame numpy
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import importlib.util  # noqa: E402

import pygame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAME = os.path.join(ROOT, 'HD_Fighter', 'game.py')

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print('FAIL', msg)


class KeyTable(dict):
    """pygame.key.get_pressed() answers False for keys nobody holds."""

    def __missing__(self, key):
        return False


def load_game():
    os.chdir(os.path.dirname(GAME))
    spec = importlib.util.spec_from_file_location('hd_fighter_game', GAME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pygame.init()
    pygame.display.set_mode((module.SCREEN_W, module.SCREEN_H))
    module.toggle_graphics()          # the Padel trio only exists as HD art
    return module


def step(module, match, keys, frames):
    for _ in range(frames):
        dt = 1.0 / 60
        match.p1.update(dt, match.p2, keys, [], match.projectiles, match.hitstop, match.screenshake)
        match.p2.update(dt, match.p1, keys, [], match.projectiles, match.hitstop, match.screenshake)
        match.check_hits()
        match.hitstop.update(dt)
        match.screenshake.update(dt)
        match.update_sparks(dt)


def main():
    module = load_game()
    key1 = {action: sorted(codes)[0] for action, codes in module.KEYSETS[1].items()}
    key2 = {action: sorted(codes)[0] for action, codes in module.KEYSETS[2].items()}

    # ---- 1. each player has its own keyboard -------------------------------
    check(module.KEYSETS[1]['left'] != module.KEYSETS[2]['left'],
          'P1 and P2 have different movement keys')
    check(module.KEYSETS[1]['hp'] != module.KEYSETS[2]['hp'],
          'P1 and P2 have different attack keys')
    check(module.K_LEFT not in module.KEYSETS[1]['left'] if hasattr(module, 'K_LEFT') else True,
          'P1 does not share the arrow keys with P2')
    # pressing P2's right arrow must not move P1
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 400, 900
    x0, x1 = m.p1.x, m.p2.x
    step(module, m, KeyTable({key2['right']: True}), 20)
    check(abs(m.p1.x - x0) < 1, 'P2 holding right does not move P1')
    # P2 faces left, so "right" walks it away from P1
    check(m.p2.x > x1, f'P2 holding right moves P2 (from {x1} to {m.p2.x:.0f})')

    # ---- 2. a hit fighter recovers ---------------------------------------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 620, 760
    m.p2.take_damage(10, 0.5, 0, 1)
    step(module, m, KeyTable(), 120)
    check(m.p2.state != 'hit', f'fighter leaves the hit pose (state {m.p2.state})')
    check(m.p2.hitstun <= 0, 'hitstun runs out')

    # ---- 3. blocking reduces damage --------------------------------------
    m = module.Match('mike', 'daragh', 0)
    m.p2.state = 'block'
    hp0 = m.p2.hp
    m.p2.take_damage(20, 0.4, 0, 1, is_blocked=True)
    blocked_loss = hp0 - m.p2.hp
    m2 = module.Match('mike', 'daragh', 0)
    hp0 = m2.p2.hp
    m2.p2.take_damage(20, 0.4, 0, 1, is_blocked=False)
    clean_loss = hp0 - m2.p2.hp
    check(blocked_loss < clean_loss, f'a blocked hit ({blocked_loss}) hurts less than a clean one ({clean_loss})')
    check(clean_loss == 20, f'a clean hit does full damage ({clean_loss})')

    # ---- 4. fighters keep a body-width apart ------------------------------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 700, 760
    step(module, m, KeyTable(), 2)
    check(abs(m.p1.x - m.p2.x) >= 115,
          f'fighters are pushed apart (gap {abs(m.p1.x - m.p2.x):.0f})')
    # ...but not further apart than a punch can reach, or nothing can connect
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 640, 760
    m.p2.hp = 100
    for _ in range(8):
        step(module, m, KeyTable({key1['hp']: True}), 6)
        step(module, m, KeyTable(), 20)
    check(m.p2.hp < 100, f'punches connect at body-collision range (daragh hp {m.p2.hp})')

    # ---- 5. the damage flash fades ---------------------------------------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 400, 900
    m.p2.take_damage(5, 0.1, 0, 1)
    check(m.p2.flash_timer > 0, 'a hit starts the flash')
    step(module, m, KeyTable(), 60)
    check(m.p2.flash_timer <= 0, 'the damage flash fades within a second')

    # ---- 6. the specials are reachable from the documented button --------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 400, 900
    step(module, m, KeyTable({key1['special1']: True}), 2)
    check(m.p1.state == 'special1', f'special1 button reaches special1 (state {m.p1.state})')
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 400, 900
    step(module, m, KeyTable({key1['special2']: True}), 2)
    check(m.p1.state == 'special2', f'special2 button reaches special2 (state {m.p1.state})')

    # ---- 7. holding block puts the fighter in the block state ------------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 400, 900
    step(module, m, KeyTable({key1['block']: True}), 2)
    check(m.p1.state == 'block', f'block button blocks (state {m.p1.state})')

    # ---- 8. hits actually land and a fight can be finished ---------------
    m = module.Match('mike', 'daragh', 0)
    m.p1.x, m.p2.x = 620, 780
    for _ in range(40):
        step(module, m, KeyTable({key1['hp']: True}), 6)
        step(module, m, KeyTable(), 24)
    check(m.p2.hp < 100, f'attacks land damage in a stand-up fight (daragh hp {m.p2.hp})')

    if failures:
        print(f'\n{len(failures)} fight-rule check(s) failed')
        return 1
    print('PASS fight rules (keyboard split, hitstun, block, spacing, flash, specials)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
