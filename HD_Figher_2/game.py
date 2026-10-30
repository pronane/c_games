"""
Original HD 2D Fighting Game — 6 characters, versus mode, character select,
parallax stages, hit-stop/screen-shake/supers/throws, gamepad + keyboard.
All artwork is ORIGINAL (procedurally generated) — no Capcom assets included.
"""
import json
import math
import os
import random
import sys

import pygame

# ------------------------------------------------------------------ constants
SCREEN_W, SCREEN_H = 1280, 720
BASE_W, BASE_H = 96, 128          # sprite canvas size used at generation time
SCALE = 2                         # HD upscale
FPS = 60

PLAYER_W = BASE_W * SCALE         # 192
PLAYER_H = BASE_H * SCALE         # 256
GROUND_Y = SCREEN_H - 160

ROUND_TIME = 99
MAX_ROUNDS = 3
SUPER_METER_MAX = 500

JOY_DEADZONE = 0.25

# ------------------------------------------------------------------ paths
# Robust asset resolution: handles dev, PyInstaller onedir (_internal), and onefile (_MEIPASS)
# F2 toggles between procedural V2 (assets/) and HD AI (assets_hd/)
GRAPHICS_MODES = ["CLASSIC", "HD"]  # CLASSIC=procedural V2, HD=AI portraits+BGs
CURRENT_MODE = [0]  # index into GRAPHICS_MODES, mutable for hot-swap
def _find_assets(mode="CLASSIC"):
    folder = "assets" if mode=="CLASSIC" else "assets_hd"
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, folder))
        candidates.append(os.path.join(exe_dir, "_internal", folder))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, folder))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), folder))
    for p in candidates:
        if os.path.exists(os.path.join(p, "meta.json")):
            return p
    return candidates[0]

def _current_assets():
    mode = GRAPHICS_MODES[CURRENT_MODE[0]]
    return _find_assets(mode)

ASSETS = _current_assets()
SPRITES = os.path.join(ASSETS, "sprites")
STAGES = os.path.join(ASSETS, "stages")
FX = os.path.join(ASSETS, "fx")
SELECT = os.path.join(ASSETS, "select")

def toggle_graphics():
    CURRENT_MODE[0] = 1 - CURRENT_MODE[0]
    global ASSETS, SPRITES, STAGES, FX, SELECT, META, CHARACTERS, STAGE_DATA, EFFECTS, PORTRAITS
    ASSETS = _current_assets()
    SPRITES = os.path.join(ASSETS, "sprites")
    STAGES = os.path.join(ASSETS, "stages")
    FX = os.path.join(ASSETS, "fx")
    SELECT = os.path.join(ASSETS, "select")
    _img_cache.clear()
    with open(os.path.join(ASSETS, "meta.json")) as fh:
        META = json.load(fh)
    CHARACTERS = META["characters"]
    STAGE_DATA = META["stages"]
    EFFECTS = META["effects"]
    PORTRAITS = META["select"]
    return GRAPHICS_MODES[CURRENT_MODE[0]]

with open(os.path.join(ASSETS, "meta.json")) as fh:
    META = json.load(fh)

CHARACTERS = META["characters"]
STAGE_DATA = META["stages"]
EFFECTS = META["effects"]
PORTRAITS = META["select"]

# Fighter display names (must be defined before Fighter class uses it)
FIGHTER_INFO = {
    "kairo": {"name": "KAIRO", "style": "MUAY THAI"},
    "lyra": {"name": "LYRA", "style": "CAPOEIRA"},
    "brutus": {"name": "BRUTUS", "style": "BRAWLER"},
    "naomi": {"name": "NAOMI", "style": "KENJUTSU"},
    "zap": {"name": "ZAP", "style": "ELECTRIC"},
    "void": {"name": "VOID", "style": "MYSTIC"},
}

# ------------------------------------------------------------------ asset cache
_img_cache = {}


def load_img(path, size=None, alpha=True):
    key = (path, size)
    if key in _img_cache:
        return _img_cache[key]
    img = pygame.image.load(path).convert_alpha() if alpha else pygame.image.load(path).convert()
    if size:
        img = pygame.transform.scale(img, size)
    _img_cache[key] = img
    return img


class SpriteSheet:
    def __init__(self, path, frame_w, frame_h, frame_count, duration_per_frame):
        img = load_img(path, (frame_w * SCALE * frame_count, frame_h * SCALE))
        self.frames = []
        for i in range(frame_count):
            sub = img.subsurface((i * frame_w * SCALE, 0, frame_w * SCALE, frame_h * SCALE))
            self.frames.append(sub)
        self.durations = [duration_per_frame / FPS] * frame_count
        self.total = sum(self.durations)


class FighterAssets:
    def __init__(self, tag):
        self.tag = tag
        meta = CHARACTERS[tag]
        self.sheets = {}
        for state, (fname, frames, dur) in meta.items():
            self.sheets[state] = SpriteSheet(
                os.path.join(ASSETS, fname), BASE_W, BASE_H, frames, dur)


# ------------------------------------------------------------------ input
KEY_LEFT = {pygame.K_LEFT, pygame.K_a}
KEY_RIGHT = {pygame.K_RIGHT, pygame.K_d}
KEY_UP = {pygame.K_UP, pygame.K_w}
KEY_DOWN = {pygame.K_DOWN, pygame.K_s}
KEY_LP = {pygame.K_z, pygame.K_j}
KEY_HP = {pygame.K_x, pygame.K_k}
KEY_LK = {pygame.K_c, pygame.K_n}
KEY_HK = {pygame.K_v, pygame.K_m}
KEY_START = {pygame.K_RETURN, pygame.K_SPACE}

JOY_BTN_LP = 0
JOY_BTN_HP = 1
JOY_BTN_LK = 2
JOY_BTN_HK = 3
JOY_BTN_THROW = 4
JOY_BTN_SUPER = 5


def keys_pressed(keys, key_set):
    return any(keys[k] for k in key_set)


# ------------------------------------------------------------------ combat helpers
class HitStop:
    def __init__(self):
        self.timer = 0.0

    def trigger(self, frames):
        self.timer = frames / FPS

    def update(self, dt):
        if self.timer > 0:
            self.timer = max(0, self.timer - dt)
            return True
        return False

    def active(self):
        return self.timer > 0


class ScreenShake:
    def __init__(self):
        self.timer = 0.0
        self.magnitude = 0

    def trigger(self, frames, magnitude=8):
        self.timer = frames / FPS
        self.magnitude = magnitude

    def update(self, dt):
        if self.timer > 0:
            self.timer = max(0, self.timer - dt)

    def offset(self):
        if self.timer > 0:
            return (random.uniform(-self.magnitude, self.magnitude),
                    random.uniform(-self.magnitude, self.magnitude))
        return (0, 0)


# ------------------------------------------------------------------ projectile
class Projectile:
    def __init__(self, x, y, facing, owner, kind="fireball"):
        self.x = float(x)
        self.y = float(y)
        self.facing = facing
        self.owner = owner
        self.kind = kind
        self.active = True
        self.anim = 0
        if kind == "fireball":
            self.speed = 16 * facing
            self.width = 40 * SCALE
            self.height = 40 * SCALE
            self.life = 45
            self.damage = 12
            self.hitstun = 0.4
            self.knockback = 240
        elif kind == "elecball":
            self.speed = 12 * facing
            self.width = 36 * SCALE
            self.height = 36 * SCALE
            self.life = 60
            self.damage = 14
            self.hitstun = 0.55
            self.knockback = 300
        else:
            self.speed = 14 * facing
            self.width = 34 * SCALE
            self.height = 34 * SCALE
            self.life = 40
            self.damage = 10
            self.hitstun = 0.4
            self.knockback = 220

    def update(self):
        self.x += self.speed
        self.anim += 1
        self.life -= 1
        if self.life <= 0:
            self.active = False
        if self.x < -120 or self.x > SCREEN_W + 120:
            self.active = False

    def draw(self, surf, sheets):
        sheet = sheets[self.kind]
        frame = min(int(self.anim * 8), len(sheet.frames) - 1)
        img = sheet.frames[frame]
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, (int(self.x - self.width / 2), int(self.y - self.height / 2)))

    def rect(self):
        return pygame.Rect(int(self.x - self.width / 2), int(self.y - self.height / 2),
                           self.width, self.height)


# ------------------------------------------------------------------ fighter
class Fighter:
    def __init__(self, tag, x, facing, player_id, assets, controls, is_cpu=False):
        self.tag = tag
        self.name = None  # filled below
        self.x = float(x)
        self.y = float(GROUND_Y)
        self.facing = facing
        self.player_id = player_id
        self.assets = assets
        self.controls = controls
        self.is_cpu = is_cpu
        self.joy = None

        # look up name
        for t, c in FIGHTER_INFO.items():
            if t == tag:
                self.name = c["name"]
                break

        self.hp = 100
        self.max_hp = 100
        self.state = "idle"
        self.state_timer = 0.0
        self.frame = 0
        self.frame_timer = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.blocking = False
        self.hitstun = 0.0
        self.attacking = False
        self.throwing = False
        self.attack_hitboxes = []
        self.defeated = False
        self.won = False
        self.flash_timer = 0.0
        self.attack_cooldown = 0.0
        self.super_meter = 0.0
        self.combo = 0
        self.combo_timer = 0.0
        self.can_block = True
        self.set_state("idle", force=True)

    # ---------------------------------------------------------------- input
    def get_input(self, keys, joysticks):
        act = {"left": False, "right": False, "up": False, "down": False,
               "lp": False, "hp": False, "lk": False, "hk": False,
               "throw": False, "super": False}

        if keys_pressed(keys, KEY_LEFT):
            act["left"] = True
        if keys_pressed(keys, KEY_RIGHT):
            act["right"] = True
        if keys_pressed(keys, KEY_UP):
            act["up"] = True
        if keys_pressed(keys, KEY_DOWN):
            act["down"] = True
        if keys_pressed(keys, KEY_LP):
            act["lp"] = True
        if keys_pressed(keys, KEY_HP):
            act["hp"] = True
        if keys_pressed(keys, KEY_LK):
            act["lk"] = True
        if keys_pressed(keys, KEY_HK):
            act["hk"] = True

        if self.joy is not None:
            j = self.joy
            ax = j.get_axis(0)
            ay = j.get_axis(1)
            if ax < -JOY_DEADZONE:
                act["left"] = True
            if ax > JOY_DEADZONE:
                act["right"] = True
            if ay < -JOY_DEADZONE:
                act["up"] = True
            if ay > JOY_DEADZONE:
                act["down"] = True
            if j.get_button(JOY_BTN_LP):
                act["lp"] = True
            if j.get_button(JOY_BTN_HP):
                act["hp"] = True
            if j.get_button(JOY_BTN_LK):
                act["lk"] = True
            if j.get_button(JOY_BTN_HK):
                act["hk"] = True
            if j.get_button(JOY_BTN_THROW):
                act["throw"] = True
            if j.get_button(JOY_BTN_SUPER):
                act["super"] = True

        return act

    # ---------------------------------------------------------------- state
    def set_state(self, state, force=False):
        if state == self.state and not force:
            return
        if self.hitstun > 0 and state not in ("hit",):
            return
        if self.state in ("super", "special1", "special2", "hp", "hk") and self.state_timer < 0.2 and not force:
            return
        self.state = state
        self.state_timer = 0.0
        self.frame = 0
        self.frame_timer = 0.0
        sheet = self.assets.sheets[state]
        self.frame_durations = sheet.durations

    def update(self, dt, other, keys, joysticks, projectiles, hitstop, screenshake):
        if self.defeated:
            self.set_state("lose")
            self.animate(dt)
            return
        if self.won:
            self.set_state("win")
            self.animate(dt)
            return

        # combo timer
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0

        # super meter decay (very slow)
        if self.super_meter > 0:
            self.super_meter = max(0, self.super_meter - 2 * dt)

        if hitstop.active():
            self.animate(dt)
            return

        if self.hitstun > 0:
            self.hitstun -= dt
            self.vx *= 0.82
            self.x += self.vx * dt
            self.set_state("hit")
            self.animate(dt)
            self.apply_gravity(dt)
            return

        act = self.get_input(keys, joysticks)

        # facing toward opponent
        if other.x > self.x:
            self.facing = 1
        else:
            self.facing = -1

        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        # --- movement states ---
        if self.state in ("idle", "walk", "crouch", "block"):
            if act["down"]:
                self.set_state("crouch")
            # block: hold back (away from opponent)
            toward = (act["right"] if self.facing > 0 else act["left"])
            away = (act["left"] if self.facing > 0 else act["right"])
            if away and not toward and self.state != "block":
                self.set_state("block")
            elif not away and self.state == "block":
                self.set_state("idle")
            elif act["left"] or act["right"]:
                if not self.blocking:
                    self.set_state("walk")
                    spd = 140 if self.tag != "brutus" else 100
                    if act["left"]:
                        self.x -= spd * dt
                    if act["right"]:
                        self.x += spd * dt
                    self.x = max(70, min(SCREEN_W - 70, self.x))
            else:
                if self.state == "block":
                    self.set_state("idle")
                elif self.state != "crouch":
                    self.set_state("idle")

        self.blocking = (self.state == "block")

        # --- jump ---
        if act["up"] and self.on_ground and self.state not in ("jump",):
            self.set_state("jump", force=True)
            self.vy = -540
            self.on_ground = False
            self.vx = self.facing * 70

        # --- attacks ---
        can_atk = (self.state not in ("jump", "crouch", "block", "hit")
                   and self.attack_cooldown <= 0)

        if can_atk:
            # throw: close range + throw button
            dist = abs(other.x - self.x)
            if act["throw"] and dist < 70 * SCALE:
                self.set_state("throw", force=True)
                self.throwing = True
                self.attack_cooldown = 1.0
            elif act["super"] and self.super_meter >= SUPER_METER_MAX:
                self.set_state("super", force=True)
                self.attacking = True
                self.attack_cooldown = 1.6
                self.super_meter = 0
                screenshake.trigger(10, 12)
            elif act["down"] and (act["lp"] or act["hp"]) and self.state != "special1":
                self.set_state("special1", force=True)
                self.attacking = True
                self.attack_cooldown = 0.9
            elif act["hp"] and self.state != "hp":
                self.set_state("hp", force=True)
                self.attacking = True
                self.attack_cooldown = 0.75
            elif act["hk"] and self.state != "hk":
                self.set_state("hk", force=True)
                self.attacking = True
                self.attack_cooldown = 0.85
            elif act["lp"] and self.state != "lp":
                self.set_state("lp", force=True)
                self.attacking = True
                self.attack_cooldown = 0.45
            elif act["lk"] and self.state != "lk":
                self.set_state("lk", force=True)
                self.attacking = True
                self.attack_cooldown = 0.55

        # --- state physics ---
        if self.state == "jump":
            self.apply_gravity(dt)
            self.x += self.vx * dt
            self.vx *= 0.95
            if self.y >= GROUND_Y:
                self.y = GROUND_Y
                self.on_ground = True
                self.vy = 0
                self.vx = 0
                self.set_state("idle")
        elif self.state in ("crouch", "block"):
            self.y = GROUND_Y
        elif self.state == "throw":
            self.y = GROUND_Y
            if 0.2 < self.state_timer < 0.5:
                self.x += self.facing * 40 * dt
        elif self.state == "super":
            self.y = GROUND_Y
        else:
            self.blocking = False
            if self.state == "hp" and 0.18 < self.state_timer < 0.38:
                self.x += self.facing * 75 * dt
            self.y = GROUND_Y

        self.x = max(70, min(SCREEN_W - 70, self.x))

        # --- attack hitboxes ---
        self.attack_hitboxes = []
        if self.attacking:
            st = self.state_timer
            if self.state == "lp" and 0.12 < st < 0.32:
                reach = 78 * SCALE
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (24 * self.facing) * SCALE - reach / 2),
                                int(self.y - 90 * SCALE), reach, 70 * SCALE),
                    9, 0.4, 250))
            elif self.state == "hp" and 0.22 < st < 0.5:
                reach = 120 * SCALE
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (28 * self.facing) * SCALE - reach / 2),
                                int(self.y - 100 * SCALE), reach, 80 * SCALE),
                    16, 0.6, 360))
            elif self.state == "lk" and 0.12 < st < 0.32:
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (22 * self.facing) * SCALE - 45 * SCALE),
                                int(self.y - 30 * SCALE), 80 * SCALE, 55 * SCALE),
                    7, 0.3, 160))
            elif self.state == "hk" and 0.22 < st < 0.55:
                reach = 130 * SCALE
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (28 * self.facing) * SCALE - reach / 2),
                                int(self.y - 100 * SCALE), reach, 100 * SCALE),
                    14, 0.55, 330))
            elif self.state == "throw" and 0.25 < st < 0.55:
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (30 * self.facing) * SCALE - 40 * SCALE),
                                int(self.y - 40 * SCALE), 80 * SCALE, 100 * SCALE),
                    0, 1.2, 0))
            elif self.state == "special1" and 0.35 < st < 0.6:
                if not getattr(self, "_proj_spawned", False):
                    self._proj_spawned = True
                    kind = "elecball" if self.tag == "zap" else "fireball"
                    fx = self.x + (70 * self.facing)
                    fy = self.y - 90
                    projectiles.append(Projectile(fx, fy, self.facing, self, kind))
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (30 * self.facing) * SCALE - 50 * SCALE),
                                int(self.y - 60 * SCALE), 100 * SCALE, 80 * SCALE),
                    10, 0.5, 280))
            elif self.state == "special2" and 0.15 < st < 0.6:
                self.x += self.facing * 220 * dt
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x - 40 * SCALE), int(self.y - 90 * SCALE),
                                80 * SCALE, 160 * SCALE),
                    12, 0.5, 300))
            elif self.state == "super" and 0.3 < st < 0.75:
                reach = 160 * SCALE
                self.attack_hitboxes.append((
                    pygame.Rect(int(self.x + (30 * self.facing) * SCALE - reach / 2),
                                int(self.y - 110 * SCALE), reach, 140 * SCALE),
                    24, 1.0, 450))

        # --- throw connect ---
        if self.throwing and self.state == "throw" and 0.3 < self.state_timer < 0.55:
            hurt = pygame.Rect(int(other.x - 40 * SCALE), int(other.y - 110 * SCALE),
                               80 * SCALE, 150 * SCALE)
            grab = pygame.Rect(int(self.x + (30 * self.facing) * SCALE - 40 * SCALE),
                               int(self.y - 40 * SCALE), 80 * SCALE, 100 * SCALE)
            if grab.colliderect(hurt) and not other.defeated:
                other.take_throw(self.facing)
                self.throwing = False

        # --- end of attack ---
        sheet = self.assets.sheets[self.state]
        if self.state_timer > sheet.total and self.attacking:
            self.attacking = False
            self.throwing = False
            if hasattr(self, "_proj_spawned"):
                del self._proj_spawned
            self.set_state("idle")

        self.animate(dt)

    def apply_gravity(self, dt):
        self.vy += 1150 * dt
        self.y += self.vy * dt

    def animate(self, dt):
        self.state_timer += dt
        sheet = self.assets.sheets[self.state]
        dur = self.frame_durations[min(self.frame, len(self.frame_durations) - 1)]
        self.frame_timer += dt
        if self.frame_timer >= dur:
            self.frame_timer = 0
            self.frame += 1
            if self.frame >= len(sheet.frames):
                self.frame = len(sheet.frames) - 1

    def take_damage(self, damage, stun, knockback, facing, is_blocked=False):
        if self.defeated or self.won:
            return
        if self.state == "block" and not is_blocked:
            self.hp -= max(1, damage // 5)
            self.hitstun = 0.12
            self.flash_timer = 0.1
            self.super_meter = min(SUPER_METER_MAX, self.super_meter + 15)
        else:
            self.hp -= damage
            self.hitstun = stun
            self.flash_timer = 0.15
            self.vx = knockback * facing
            self.vy = -220
            self.on_ground = False
            self.super_meter = min(SUPER_METER_MAX, self.super_meter + 30)
        if self.hp <= 0:
            self.hp = 0
            self.defeated = True

    def take_throw(self, facing):
        if self.defeated or self.won:
            return
        self.hp -= 18
        self.hitstun = 0.9
        self.flash_timer = 0.2
        self.vx = facing * 300
        self.vy = -300
        self.on_ground = False
        self.defeated = (self.hp <= 0)
        if self.hp <= 0:
            self.hp = 0
            self.defeated = True

    def current_image(self):
        sheet = self.assets.sheets[self.state]
        img = sheet.frames[min(self.frame, len(sheet.frames) - 1)]
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        if self.flash_timer > 0:
            flash = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 170))
            img = img.copy()
            img.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        return img

    def draw(self, surf):
        img = self.current_image()
        rect = img.get_rect(midbottom=(int(self.x), int(self.y + 8)))
        surf.blit(img, rect)


# ------------------------------------------------------------------ stage
class Stage:
    def __init__(self, data):
        self.data = data
        self.bg = load_img(os.path.join(ASSETS, data["bg"]), (SCREEN_W, SCREEN_H), alpha=False)
        self.mid = load_img(os.path.join(ASSETS, data["mid"]), (SCREEN_W, SCREEN_H))
        self.fg = load_img(os.path.join(ASSETS, data["fg"]), (SCREEN_W, SCREEN_H))
        self.scroll_x = 0.0

    def update(self, p1, p2):
        mid_x = (p1.x + p2.x) / 2
        target = mid_x - SCREEN_W / 2
        target = max(0, min(target, 0))
        self.scroll_x = target

    def draw(self, surf, shake):
        ox, oy = shake.offset()
        surf.blit(self.bg, (int(ox), int(oy)))
        surf.blit(self.mid, (int(ox), int(oy)))
        pygame.draw.line(surf, (50, 50, 50), (0, int(GROUND_Y + oy)), (SCREEN_W, int(GROUND_Y + oy)), 4)
        surf.blit(self.fg, (int(ox), int(oy)))


# ------------------------------------------------------------------ match
class Match:
    def __init__(self, p1_tag, p2_tag, stage_index):
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("HD Fighter 2 — Original HD Fighting Game")

        self.stage = Stage(STAGE_DATA[stage_index])

        self.assets_p1 = FighterAssets(p1_tag)
        self.assets_p2 = FighterAssets(p2_tag)

        self.p1 = Fighter(p1_tag, 320, 1, 1, self.assets_p1, {}, False)
        self.p2 = Fighter(p2_tag, 960, -1, 2, self.assets_p2, {}, False)

        self.effect_sheets = {}
        for kind in ("fireball", "elecball"):
            e = EFFECTS[kind]
            self.effect_sheets[kind] = SpriteSheet(os.path.join(ASSETS, e[0]), 40, 40, e[1], e[2])
        self.spark_sheet = SpriteSheet(os.path.join(ASSETS, EFFECTS["spark"][0]), 28, 28, EFFECTS["spark"][1], EFFECTS["spark"][2])
        self.block_sheet = SpriteSheet(os.path.join(ASSETS, EFFECTS["block_spark"][0]), 28, 28, EFFECTS["block_spark"][1], EFFECTS["block_spark"][2])

        self.projectiles = []
        self.hitstop = HitStop()
        self.screenshake = ScreenShake()

        self.timer = ROUND_TIME
        self.timer_acc = 0.0
        self.round = 1
        self.p1_wins = 0
        self.p2_wins = 0
        self.round_over = False
        self.round_over_timer = 0.0
        self.game_over = False

        self.font = pygame.font.SysFont("dejavusans", 32, bold=True)
        self.font_big = pygame.font.SysFont("dejavusans", 64, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 22)

        self.joysticks = []
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            j.init()
            self.joysticks.append(j)
        self._assign_joysticks()

    def _assign_joysticks(self):
        self.p1.joy = None
        self.p2.joy = None
        if self.joysticks:
            self.p1.joy = self.joysticks[0]
        if len(self.joysticks) > 1:
            self.p2.joy = self.joysticks[1]

    # ---------------------------------------------------------------- combat
    def check_hits(self):
        pairs = ((self.p1, self.p2), (self.p2, self.p1))
        for atk, other in pairs:
            if other.defeated or other.won:
                continue
            for entry in list(atk.attack_hitboxes):
                rect, dmg, stun, kb = entry
                hurt = pygame.Rect(int(other.x - 42 * SCALE), int(other.y - 120 * SCALE),
                                   84 * SCALE, 160 * SCALE)
                if rect.colliderect(hurt):
                    if atk.state == "throw":
                        continue
                    blocked = other.blocking
                    actual_dmg = max(1, dmg // 5) if blocked else dmg
                    other.take_damage(actual_dmg, stun, kb, atk.facing, is_blocked=blocked)
                    self.spawn_spark(rect.centerx, rect.centery, blocked)
                    if not blocked:
                        self.hitstop.trigger(6 if dmg >= 14 else 4)
                        self.screenshake.trigger(5 if dmg >= 14 else 3, 6 if dmg >= 14 else 4)
                        atk.combo += 1
                        atk.combo_timer = 1.2
                        atk.super_meter = min(SUPER_METER_MAX, atk.super_meter + 20)
                    else:
                        atk.super_meter = min(SUPER_METER_MAX, atk.super_meter + 8)
                    atk.attack_hitboxes.remove(entry)
                    break

            for pr in list(self.projectiles):
                if pr.owner is not atk or not pr.active:
                    continue
                hurt = pygame.Rect(int(other.x - 38 * SCALE), int(other.y - 100 * SCALE),
                                   76 * SCALE, 140 * SCALE)
                if pr.rect().colliderect(hurt):
                    blocked = other.blocking
                    actual_dmg = max(1, pr.damage // 5) if blocked else pr.damage
                    other.take_damage(actual_dmg, pr.hitstun, pr.knockback, pr.facing, is_blocked=blocked)
                    self.spawn_spark(pr.x, pr.y, blocked)
                    pr.active = False
                    if not blocked:
                        self.hitstop.trigger(4)
                        self.screenshake.trigger(4, 5)
                    break

    def spawn_spark(self, x, y, blocked):
        sheet = self.block_sheet if blocked else self.spark_sheet
        img = sheet.frames[0]
        self.screen.blit(img, (int(x - img.get_width() / 2), int(y - img.get_height() / 2)))

    # ---------------------------------------------------------------- round flow
    def end_round(self):
        self.round_over = True
        self.round_over_timer = 0.0
        if self.p1.defeated and self.p2.defeated:
            pass
        elif self.p1.defeated:
            self.p2_wins += 1
            self.p2.won = True
        elif self.p2.defeated:
            self.p1_wins += 1
            self.p1.won = True
        else:
            if self.p1.hp > self.p2.hp:
                self.p1_wins += 1
                self.p1.won = True
            elif self.p2.hp > self.p1.hp:
                self.p2_wins += 1
                self.p2.won = True

        if self.p1_wins >= (MAX_ROUNDS // 2 + 1):
            self.game_over = True
        elif self.p2_wins >= (MAX_ROUNDS // 2 + 1):
            self.game_over = True

    def next_round(self):
        self.round += 1
        self.round_over = False
        self.timer = ROUND_TIME
        self.p1 = Fighter(self.p1.tag, 320, 1, 1, self.assets_p1, {}, False)
        self.p2 = Fighter(self.p2.tag, 960, -1, 2, self.assets_p2, {}, False)
        self._assign_joysticks()
        self.projectiles = []

    # ---------------------------------------------------------------- main loop
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            keys = pygame.key.get_pressed()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "menu"
                    if event.key == pygame.K_F2:
                        mode = toggle_graphics()
                        # reload stage + fighters with new art (keep same picks)
                        self.stage = Stage(STAGE_DATA[STAGE_DATA.index(self.stage.data)] if self.stage.data in STAGE_DATA else STAGE_DATA[0])
                        for p in (self.p1, self.p2):
                            p.assets = FighterAssets(p.tag)
                        self.effect_sheets = {}
                        for kind in ("fireball", "elecball"):
                            e = EFFECTS[kind]
                            self.effect_sheets[kind] = SpriteSheet(os.path.join(ASSETS, e[0]), 40, 40, e[1], e[2])
                        self.spark_sheet = SpriteSheet(os.path.join(ASSETS, EFFECTS["spark"][0]), 28, 28, EFFECTS["spark"][1], EFFECTS["spark"][2])
                        self.block_sheet = SpriteSheet(os.path.join(ASSETS, EFFECTS["block_spark"][0]), 28, 28, EFFECTS["block_spark"][1], EFFECTS["block_spark"][2])
                    if self.game_over and event.key == pygame.K_r:
                        self.__init__(self.p1.tag, self.p2.tag, STAGE_DATA.index(self.stage.data))
                elif event.type == pygame.JOYDEVICEADDED:
                    j = pygame.joystick.Joystick(event.device_index)
                    j.init()
                    self.joysticks.append(j)
                    self._assign_joysticks()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    self.joysticks = [j for j in self.joysticks if j.get_instance_id() != event.instance_id]
                    self._assign_joysticks()

            if not self.round_over and not self.game_over:
                self.p1.update(dt, self.p2, keys, self.joysticks, self.projectiles,
                               self.hitstop, self.screenshake)
                self.p2.update(dt, self.p1, keys, self.joysticks, self.projectiles,
                               self.hitstop, self.screenshake)
                for pr in self.projectiles:
                    pr.update()
                self.projectiles = [p for p in self.projectiles if p.active]
                self.check_hits()

                self.stage.update(self.p1, self.p2)
                self.hitstop.update(dt)
                self.screenshake.update(dt)

                if not self.hitstop.active():
                    self.timer_acc += dt
                    if self.timer_acc >= 1.0:
                        self.timer_acc = 0.0
                        if self.timer > 0:
                            self.timer -= 1

                if (self.p1.defeated or self.p2.defeated or self.timer <= 0) and not self.round_over:
                    self.end_round()
            else:
                self.round_over_timer += dt
                if self.round_over_timer > 2.5 and not self.game_over:
                    self.next_round()

            self.draw()
            pygame.display.flip()

        return "menu"

    # ---------------------------------------------------------------- drawing
    def draw(self):
        self.stage.draw(self.screen, self.screenshake)

        for pr in self.projectiles:
            pr.draw(self.screen, self.effect_sheets)

        first, second = (self.p1, self.p2) if self.p1.x < self.p2.x else (self.p2, self.p1)
        first.draw(self.screen)
        second.draw(self.screen)

        if self.hitstop.active():
            flash = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 60))
            self.screen.blit(flash, (0, 0))

        self.draw_hud()

        if self.round_over and not self.game_over:
            txt = self.font_big.render("ROUND OVER", True, (255, 255, 255))
            self.screen.blit(txt, (SCREEN_W // 2 - txt.get_width() // 2, 200))
        if self.game_over:
            txt = self.font_big.render("GAME OVER", True, (220, 50, 50))
            self.screen.blit(txt, (SCREEN_W // 2 - txt.get_width() // 2, 180))
            txt2 = self.font.render("Press R to return to select", True, (255, 255, 255))
            self.screen.blit(txt2, (SCREEN_W // 2 - txt2.get_width() // 2, 300))

    def draw_hud(self):
        p1_w = int((self.p1.hp / self.p1.max_hp) * 400)
        pygame.draw.rect(self.screen, (40, 40, 40), (70, 24, 400, 36))
        pygame.draw.rect(self.screen, (0, 160, 240), (70, 24, p1_w, 36))
        n1 = self.font.render(self.p1.name, True, (0, 160, 240))
        self.screen.blit(n1, (70, 2))

        p2_w = int((self.p2.hp / self.p2.max_hp) * 400)
        pygame.draw.rect(self.screen, (40, 40, 40), (SCREEN_W - 70 - 400, 24, 400, 36))
        pygame.draw.rect(self.screen, (240, 70, 70), (SCREEN_W - 70 - 400 + (400 - p2_w), 24, p2_w, 36))
        n2 = self.font.render(self.p2.name, True, (240, 70, 70))
        self.screen.blit(n2, (SCREEN_W - 70 - n2.get_width(), 2))

        t_txt = self.font_big.render(f"{max(0, self.timer):02d}", True, (255, 255, 255))
        self.screen.blit(t_txt, (SCREEN_W // 2 - t_txt.get_width() // 2, 6))

        r_txt = self.font_small.render(f"ROUND {self.round}", True, (255, 255, 255))
        self.screen.blit(r_txt, (SCREEN_W // 2 - r_txt.get_width() // 2, 78))

        m1 = int((self.p1.super_meter / SUPER_METER_MAX) * 200)
        pygame.draw.rect(self.screen, (60, 60, 80), (70, 70, 200, 10))
        if m1 > 0:
            col = (100, 200, 255) if self.p1.super_meter >= SUPER_METER_MAX else (100, 160, 255)
            pygame.draw.rect(self.screen, col, (70, 70, m1, 10))
        s_txt = self.font_small.render("SUPER", True, (160, 160, 180))
        self.screen.blit(s_txt, (70, 84))

        m2 = int((self.p2.super_meter / SUPER_METER_MAX) * 200)
        pygame.draw.rect(self.screen, (60, 60, 80), (SCREEN_W - 70 - 200, 70, 200, 10))
        if m2 > 0:
            col = (100, 200, 255) if self.p2.super_meter >= SUPER_METER_MAX else (100, 160, 255)
            pygame.draw.rect(self.screen, col, (SCREEN_W - 70 - 200 + (200 - m2), 70, m2, 10))
        # graphics mode indicator + hint
        mode_txt = self.font_small.render(f"F2:{GRAPHICS_MODES[CURRENT_MODE[0]]}  (toggle)", True, (160,180,200))
        self.screen.blit(mode_txt, (SCREEN_W - mode_txt.get_width() - 12, SCREEN_H - 22))
        self.screen.blit(s_txt, (SCREEN_W - 70 - 200, 84))

        if self.p1.combo > 1:
            c_txt = self.font.render(f"{self.p1.combo} HIT COMBO", True, (255, 255, 0))
            self.screen.blit(c_txt, (70, SCREEN_H - 60))
        if self.p2.combo > 1:
            c_txt = self.font.render(f"{self.p2.combo} HIT COMBO", True, (255, 255, 0))
            self.screen.blit(c_txt, (SCREEN_W - 70 - c_txt.get_width(), SCREEN_H - 60))


# ------------------------------------------------------------------ character select
class CharacterSelect:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("HD Fighter 2 — Character Select")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusans", 36, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 20)

        self.tags = list(FIGHTER_INFO.keys())
        self.p1_sel = 0
        self.p2_sel = len(self.tags) - 1
        self.p1_confirmed = False
        self.p2_confirmed = False
        self.stage_sel = 0

        self.portraits = {}
        for tag in self.tags:
            self.portraits[tag] = load_img(os.path.join(ASSETS, PORTRAITS[tag]), (128, 128))

        self.joysticks = []
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            j.init()
            self.joysticks.append(j)

    def _joy_input(self):
        out = {"p1": {"left": False, "right": False, "a": False, "b": False},
               "p2": {"left": False, "right": False, "a": False, "b": False}}
        if self.joysticks:
            j = self.joysticks[0]
            ax = j.get_axis(0)
            if ax < -JOY_DEADZONE:
                out["p1"]["left"] = True
            if ax > JOY_DEADZONE:
                out["p1"]["right"] = True
            if j.get_button(0):
                out["p1"]["a"] = True
            if j.get_button(1):
                out["p1"]["b"] = True
        if len(self.joysticks) > 1:
            j = self.joysticks[1]
            ax = j.get_axis(0)
            if ax < -JOY_DEADZONE:
                out["p2"]["left"] = True
            if ax > JOY_DEADZONE:
                out["p2"]["right"] = True
            if j.get_button(0):
                out["p2"]["a"] = True
            if j.get_button(1):
                out["p2"]["b"] = True
        return out

    def run(self):
        last = {"p1_left": False, "p1_right": False, "p1_a": False,
                "p2_left": False, "p2_right": False, "p2_a": False}
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            keys = pygame.key.get_pressed()
            joy = self._joy_input()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key == pygame.K_F2:
                        mode = toggle_graphics()
                        # reload portraits
                        self.portraits = {}
                        for tag in self.tags:
                            self.portraits[tag] = load_img(os.path.join(ASSETS, PORTRAITS[tag]), (128, 128))
                    if event.key in KEY_START and self.p1_confirmed and self.p2_confirmed:
                        return (self.tags[self.p1_sel], self.tags[self.p2_sel], self.stage_sel)
                elif event.type == pygame.JOYDEVICEADDED:
                    j = pygame.joystick.Joystick(event.device_index)
                    j.init()
                    self.joysticks.append(j)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    self.joysticks = [j for j in self.joysticks if j.get_instance_id() != event.instance_id]

            p1_l = keys_pressed(keys, KEY_LEFT) or joy["p1"]["left"]
            p1_r = keys_pressed(keys, KEY_RIGHT) or joy["p1"]["right"]
            p1_a = keys_pressed(keys, KEY_LP) or keys_pressed(keys, KEY_START) or joy["p1"]["a"]

            p2_l = keys_pressed(keys, {pygame.K_LEFT}) or joy["p2"]["left"]
            p2_r = keys_pressed(keys, {pygame.K_RIGHT}) or joy["p2"]["right"]
            p2_a = keys_pressed(keys, {pygame.K_z}) or keys_pressed(keys, KEY_START) or joy["p2"]["a"]

            if p1_l and not last["p1_left"]:
                self.p1_sel = (self.p1_sel - 1) % len(self.tags)
            if p1_r and not last["p1_right"]:
                self.p1_sel = (self.p1_sel + 1) % len(self.tags)
            if p1_a and not last["p1_a"]:
                self.p1_confirmed = not self.p1_confirmed

            if p2_l and not last["p2_left"]:
                self.p2_sel = (self.p2_sel - 1) % len(self.tags)
            if p2_r and not last["p2_right"]:
                self.p2_sel = (self.p2_sel + 1) % len(self.tags)
            if p2_a and not last["p2_a"]:
                self.p2_confirmed = not self.p2_confirmed

            last["p1_left"], last["p1_right"], last["p1_a"] = p1_l, p1_r, p1_a
            last["p2_left"], last["p2_right"], last["p2_a"] = p2_l, p2_r, p2_a

            if self.p1_confirmed and self.p2_confirmed and self.p1_sel == self.p2_sel:
                self.p2_confirmed = False

            self.draw()
            pygame.display.flip()

        return None

    def draw(self):
        self.screen.fill((18, 22, 34))
        title = self.font.render("CHARACTER SELECT", True, (255, 255, 255))
        self.screen.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 40))

        subtitle = self.font_small.render("P1: A/D move, Z/Enter confirm   P2: Arrows move, J/Enter confirm", True, (180, 180, 190))
        self.screen.blit(subtitle, (SCREEN_W // 2 - subtitle.get_width() // 2, 95))

        st_txt = self.font_small.render(f"STAGE: {STAGE_DATA[self.stage_sel]['name']}", True, (200, 200, 100))
        self.screen.blit(st_txt, (SCREEN_W // 2 - st_txt.get_width() // 2, 135))

        box_w, box_h = 160, 260
        gap = 12
        total_w = len(self.tags) * box_w + (len(self.tags) - 1) * gap
        start_x = max(0, (SCREEN_W - total_w) // 2)
        base_y = 160

        for i, tag in enumerate(self.tags):
            x = start_x + i * (box_w + gap)
            info = FIGHTER_INFO[tag]
            selected_p1 = (i == self.p1_sel)
            selected_p2 = (i == self.p2_sel)
            confirmed_p1 = self.p1_confirmed and selected_p1
            confirmed_p2 = self.p2_confirmed and selected_p2

            border = 0
            if confirmed_p1:
                border = (0, 200, 255)
            elif confirmed_p2:
                border = (255, 80, 80)
            elif selected_p1:
                border = (0, 120, 200)
            elif selected_p2:
                border = (200, 60, 60)

            pygame.draw.rect(self.screen, (35, 40, 55), (x, base_y, box_w, box_h), border_radius=10)
            if border:
                pygame.draw.rect(self.screen, border, (x, base_y, box_w, box_h), 5, border_radius=10)

            port = self.portraits[tag]
            self.screen.blit(port, (x + (box_w - 128) // 2, base_y + 20))

            n_txt = self.font.render(info["name"], True, (255, 255, 255))
            self.screen.blit(n_txt, (x + (box_w - n_txt.get_width()) // 2, base_y + 162))

            style = {"kairo": "MUAY THAI", "lyra": "CAPOEIRA", "brutus": "BRAWLER",
                     "naomi": "KENJUTSU", "zap": "ELECTRIC", "void": "MYSTIC"}[tag]
            s_txt = self.font_small.render(style, True, (160, 160, 170))
            self.screen.blit(s_txt, (x + (box_w - s_txt.get_width()) // 2, base_y + 198))

            if confirmed_p1:
                c_txt = self.font_small.render("P1 SELECTED", True, (0, 220, 255))
                self.screen.blit(c_txt, (x + (box_w - c_txt.get_width()) // 2, base_y + 232))
            if confirmed_p2:
                c_txt = self.font_small.render("P2 SELECTED", True, (255, 100, 100))
                self.screen.blit(c_txt, (x + (box_w - c_txt.get_width()) // 2, base_y + 232))

        if self.p1_confirmed and self.p2_confirmed:
            r_txt = self.font.render("PRESS ENTER TO FIGHT", True, (100, 255, 100))
            self.screen.blit(r_txt, (SCREEN_W // 2 - r_txt.get_width() // 2, SCREEN_H - 80))
        hint = self.font_small.render(f"F2 toggles CLASSIC ↔ HD  [{GRAPHICS_MODES[CURRENT_MODE[0]]}]  Esc quit", True, (140,160,190))
        self.screen.blit(hint, (SCREEN_W//2 - hint.get_width()//2, SCREEN_H - 28))





# ------------------------------------------------------------------ main
def main():
    pygame.init()
    pygame.joystick.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H))

    while True:
        sel = CharacterSelect().run()
        if sel is None:
            break
        p1_tag, p2_tag, stage_index = sel
        match = Match(p1_tag, p2_tag, stage_index)
        result = match.run()
        if result == "menu":
            continue
        break

    pygame.quit()


if __name__ == "__main__":
    main()


