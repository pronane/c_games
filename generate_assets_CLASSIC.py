"""
HD sprite-sheet, stage, and FX generator for the original fighting game.
All art is ORIGINAL and procedurally drawn - no Capcom / Street Fighter II
assets are used or reproduced.
"""
import json
import math
import os
import pygame

pygame.init()
pygame.display.set_mode((1, 1))

# ------------------------------------------------------------------ config
SCALE = 2                      # HD upscale factor (2x crisp)
BASE_W, BASE_H = 96, 128       # base "pixel art" resolution per frame
FPS = 60
GROUND_OFFSET = 10             # feet sit this many px above canvas bottom

OUT = os.path.join(os.path.dirname(__file__), "assets")
SPR = os.path.join(OUT, "sprites")
STG = os.path.join(OUT, "stages")
FX = os.path.join(OUT, "fx")
SEL = os.path.join(OUT, "select")
for d in (OUT, SPR, STG, FX, SEL):
    os.makedirs(d, exist_ok=True)

# ------------------------------------------------------------------ palette
C = {
    "bg":        (20, 24, 32),
    "skin_light":(245, 210, 175),
    "skin_mid":  (210, 165, 125),
    "skin_dark": (170, 125, 90),
    "white":     (240, 240, 245),
    "black":     (30, 30, 35),
    "gray":      (160, 160, 170),
    "red":       (220, 60, 50),
    "blue":      (60, 120, 220),
    "green":     (80, 200, 100),
    "yellow":    (255, 220, 80),
    "purple":    (180, 90, 220),
    "orange":    (255, 140, 50),
    "cyan":      (100, 220, 255),
    "electric":  (200, 255, 100),
}

# 6 original fighters - distinct designs, NOT Capcom clones
FIGHTERS = {
    "kairo": {   # Muay Thai striker - elbows/knees, aggressive, red/gold
        "name": "KAIRO",
        "palette": dict(skin=C["skin_light"], skin_d=C["skin_mid"],
                        primary=C["red"], secondary=C["black"],
                        accent=C["yellow"], hair=C["black"],
                        glove=C["white"], boot=C["black"], belt=C["yellow"]),
        "body": "lean", "headgear": "headband", "outfit": "shorts", "weapon": None,
        "fx": None,
    },
    "lyra": {    # Capoeira acrobat - fluid, handstands, teal/white
        "name": "LYRA",
        "palette": dict(skin=C["skin_mid"], skin_d=C["skin_dark"],
                        primary=C["cyan"], secondary=C["white"],
                        accent=C["green"], hair=C["purple"],
                        glove=C["white"], boot=C["white"], belt=C["green"]),
        "body": "slim", "headgear": "none", "outfit": "dojo", "weapon": None,
        "fx": "aura",
    },
    "brutus": {  # Heavyweight brawler - slow, armored, throws, gray/orange
        "name": "BRUTUS",
        "palette": dict(skin=C["skin_light"], skin_d=C["skin_mid"],
                        primary=C["gray"], secondary=C["black"],
                        accent=C["orange"], hair=C["black"],
                        glove=C["gray"], boot=C["gray"], belt=C["black"]),
        "body": "heavy", "headgear": "none", "outfit": "tank", "weapon": None,
        "fx": None,
    },
    "naomi": {   # Swordswoman - katana, spacing, counter, purple/white
        "name": "NAOMI",
        "palette": dict(skin=C["skin_light"], skin_d=C["skin_mid"],
                        primary=C["purple"], secondary=C["white"],
                        accent=C["red"], hair=C["black"],
                        glove=C["white"], boot=C["black"], belt=C["red"]),
        "body": "slim", "headgear": "ribbon", "outfit": "kimono", "weapon": "katana",
        "fx": None,
    },
    "zap": {     # Electric wrestler - grapples + lightning, blue/yellow
        "name": "ZAP",
        "palette": dict(skin=C["skin_light"], skin_d=C["skin_mid"],
                        primary=C["blue"], secondary=C["black"],
                        accent=C["yellow"], hair=C["yellow"],
                        glove=C["yellow"], boot=C["blue"], belt=C["yellow"]),
        "body": "lean", "headgear": "mask", "outfit": "suit", "weapon": None,
        "fx": "electric",
    },
    "void": {    # Mystical martial artist - teleport, energy, black/cyan
        "name": "VOID",
        "palette": dict(skin=C["skin_dark"], skin_d=C["black"],
                        primary=C["black"], secondary=C["cyan"],
                        accent=C["electric"], hair=C["cyan"],
                        glove=C["cyan"], boot=C["black"], belt=C["cyan"]),
        "body": "lean", "headgear": "hood", "outfit": "robe", "weapon": None,
        "fx": "void",
    },
}

# ------------------------------------------------------------------ helpers
def new_canvas(w=BASE_W, h=BASE_H):
    return pygame.Surface((w, h), pygame.SRCALPHA)

def rect(s, x, y, w, h, col):
    pygame.draw.rect(s, col, (x, y, w, h))

def ellipse(s, x, y, w, h, col):
    pygame.draw.ellipse(s, col, (x, y, w, h))

def line(s, x1, y1, x2, y2, col, w=3):
    pygame.draw.line(s, col, (x1, y1), (x2, y2), w)

def poly(s, pts, col):
    pygame.draw.polygon(s, col, pts)

def save(surf, name, folder=SPR, do_scale=True):
    path = os.path.join(folder, name)
    if do_scale:
        big = pygame.transform.scale(surf, (surf.get_width() * SCALE,
                                            surf.get_height() * SCALE))
        pygame.image.save(big, path)
    else:
        pygame.image.save(surf, path)
    return path

# ------------------------------------------------------------------ body proportions
def body_dims(body):
    if body == "heavy":
        return dict(shoulder=18, waist=16, hip=22, limb_w=8, head=16)
    if body == "slim":
        return dict(shoulder=12, waist=10, hip=14, limb_w=5, head=13)
    return dict(shoulder=15, waist=13, hip=17, limb_w=6, head=14)  # lean

# ------------------------------------------------------------------ core drawing
def draw_head(s, cx, cy, char, frame, flip, d):
    p = char["palette"]
    f = 1 if not flip else -1
    hx, hy = cx, cy - d["head"] // 2 - 4
    # hair
    hair = p["hair"]
    if char["headgear"] == "headband":
        rect(s, hx - d["head"]//2 - 2, hy - 4, d["head"] + 4, 6, p["primary"])
        ellipse(s, hx - 6, hy - 8, 12, 12, p["skin"])
        ellipse(s, hx + 6, hy - 8, 12, 12, p["skin"])
    elif char["headgear"] == "mask":
        rect(s, hx - d["head"]//2 - 2, hy - 4, d["head"] + 4, 6, p["secondary"])
        ellipse(s, hx - 6, hy - 4, 12, 12, p["skin"])
        rect(s, hx - 6, hy - 2, 12, 8, p["secondary"])  # mask covers eyes
    elif char["headgear"] == "ribbon":
        rect(s, hx - d["head"]//2 - 2, hy - 6, d["head"] + 4, 8, p["primary"])
        ellipse(s, hx, hy - 6, d["head"], d["head"], p["skin"])
    elif char["headgear"] == "hood":
        rect(s, hx - d["head"]//2 - 4, hy - 8, d["head"] + 8, 14, p["secondary"])
        ellipse(s, hx, hy - 2, d["head"] - 4, d["head"], p["skin_d"])
    else:
        ellipse(s, hx - 6, hy - 8, 12, 14, p["skin"])
    # face detail (eyes)
    eye_col = p["accent"] if char["fx"] in ("electric", "void") else C["black"]
    line(s, hx - 4 * f, hy - 2, hx - 4 * f + 2 * f, hy, eye_col, 2)
    line(s, hx + 2 * f, hy - 2, hx + 2 * f + 2 * f, hy, eye_col, 2)

def draw_torso(s, cx, cy, char, flip, d):
    p = char["palette"]
    f = 1 if not flip else -1
    cx_t = cx
    cy_t = cy + 6
    if char["outfit"] == "shorts":
        rect(s, cx_t - d["shoulder"], cy_t - 4, d["shoulder"] * 2, 22, p["skin"])
        rect(s, cx_t - d["waist"], cy_t + 16, d["waist"] * 2, 8, p["primary"])
    elif char["outfit"] == "dojo":
        rect(s, cx_t - d["shoulder"], cy_t - 4, d["shoulder"] * 2, 26, p["secondary"])
        rect(s, cx_t - d["waist"], cy_t + 20, d["waist"] * 2, 8, p["accent"])
    elif char["outfit"] == "tank":
        rect(s, cx_t - d["shoulder"], cy_t - 4, d["shoulder"] * 2, 26, p["primary"])
        rect(s, cx_t - d["waist"], cy_t + 20, d["waist"] * 2, 8, p["secondary"])
    elif char["outfit"] == "kimono":
        rect(s, cx_t - d["shoulder"], cy_t - 4, d["shoulder"] * 2, 28, p["secondary"])
        rect(s, cx_t - 4, cy_t + 22, 8, 10, p["primary"])  # obi
    elif char["outfit"] == "suit":
        rect(s, cx_t - d["shoulder"], cy_t - 4, d["shoulder"] * 2, 26, p["secondary"])
        rect(s, cx_t - d["waist"], cy_t + 20, d["waist"] * 2, 8, p["primary"])
    else:  # robe
        rect(s, cx_t - d["shoulder"] - 4, cy_t - 4, d["shoulder"] * 2 + 8, 30, p["primary"])
        rect(s, cx_t - d["waist"], cy_t + 24, d["waist"] * 2, 8, p["accent"])

def draw_limbs(s, cx, cy, state, frame, flip, char, d, ground):
    p = char["palette"]
    f = 1 if not flip else -1
    lw = d["limb_w"]
    t = frame
    # arms
    if state in ("idle", "walk"):
        swing = math.sin(t * 0.6 + (0 if state == "idle" else t * 0.3)) * 4
        line(s, cx - d["shoulder"], cy + 6, cx - d["shoulder"] - 6 + f * swing,
             cy + 16, p["primary"] if char["outfit"] != "dojo" else p["secondary"], lw)
        line(s, cx + d["shoulder"], cy + 6, cx + d["shoulder"] + 6 - f * swing,
             cy + 16, p["primary"] if char["outfit"] != "dojo" else p["secondary"], lw)
        rect(s, cx - d["shoulder"] - 8 + f * swing, cy + 12, 6, 6, p["glove"])
        rect(s, cx + d["shoulder"] + 2 - f * swing, cy + 12, 6, 6, p["glove"])
    elif state == "crouch":
        line(s, cx - d["shoulder"], cy + 8, cx - 10, cy + 16, p["primary"], lw)
        line(s, cx + d["shoulder"], cy + 8, cx + 10, cy + 16, p["primary"], lw)
        rect(s, cx - 12, cy + 12, 6, 6, p["glove"])
        rect(s, cx + 6, cy + 12, 6, 6, p["glove"])
    elif state == "lp":
        line(s, cx + 8 * f, cy + 8, cx + 22 * f + 10, cy + 6, p["primary"], lw + 1)
        rect(s, cx + 20 * f + 8, cy + 2, 7, 8, p["glove"])
        line(s, cx - d["shoulder"], cy + 8, cx - 12, cy + 16, p["primary"], lw)
        rect(s, cx - 14, cy + 12, 6, 6, p["glove"])
    elif state == "hp":
        reach = 14 if t < 2 else (26 if t == 2 else (12 if t == 3 else 0))
        step = 6 if t >= 2 else 0
        cx2 = cx + step * f
        line(s, cx2 + 10 * f, cy + 8, cx2 + 24 * f + reach, cy + 4, p["primary"], lw + 2)
        rect(s, cx2 + 22 * f + reach, cy, 9, 10, p["glove"])
        line(s, cx2 - d["shoulder"], cy + 8, cx2 - 16, cy + 14, p["primary"], lw)
        rect(s, cx2 - 18, cy + 10, 6, 6, p["glove"])
    elif state == "lk":
        line(s, cx - d["shoulder"], cy + 8, cx - 14, cy + 16, p["primary"], lw)
        rect(s, cx - 16, cy + 12, 6, 6, p["glove"])
        line(s, cx + d["shoulder"], cy + 8, cx + 14, cy + 16, p["primary"], lw)
        rect(s, cx + 10, cy + 12, 6, 6, p["glove"])
    elif state == "hk":
        kick = 22 if t < 2 else (14 if t == 2 else (7 if t == 3 else 0))
        line(s, cx - d["shoulder"], cy + 8, cx - 14, cy + 14, p["primary"], lw)
        rect(s, cx - 16, cy + 10, 6, 6, p["glove"])
        line(s, cx + d["shoulder"], cy + 8, cx + 20 + kick * f, cy - 18, p["primary"], lw + 1)
        rect(s, cx + 18 + kick * f, cy - 22, 10, 8, p["boot"])
    elif state == "block":
        line(s, cx - 14, cy + 14, cx - 4, cy + 6, p["primary"], lw + 1)
        line(s, cx + 14, cy + 14, cx + 4, cy + 6, p["primary"], lw + 1)
        rect(s, cx - 16, cy + 2, 8, 8, p["glove"])
        rect(s, cx + 8, cy + 2, 8, 8, p["glove"])
    elif state == "throw":
        grab = 16 if t < 2 else (10 if t < 4 else 0)
        line(s, cx + 10 * f, cy + 8, cx + 18 * f + grab, cy + 6, p["primary"], lw + 1)
        rect(s, cx + 16 * f + grab, cy + 2, 7, 8, p["glove"])
    elif state == "special1":  # fireball / energy
        line(s, cx - d["shoulder"], cy + 10, cx - 18, cy + 18, p["primary"], lw)
        rect(s, cx - 20, cy + 14, 6, 6, p["glove"])
        line(s, cx + d["shoulder"], cy + 10, cx + 24 * f, cy + 8, p["accent"], lw + 1)
        rect(s, cx + 22 * f, cy + 4, 8, 10, p["glove"])
    elif state == "special2":  # dash / teleport
        line(s, cx - 6 * f, cy + 8, cx - 18 * f, cy + 10, p["primary"], lw)
        rect(s, cx - 20 * f, cy + 6, 6, 8, p["glove"])
    elif state == "super":
        line(s, cx - d["shoulder"], cy + 8, cx - 16, cy + 16, p["accent"], lw + 1)
        line(s, cx + d["shoulder"], cy + 8, cx + 16, cy + 16, p["accent"], lw + 1)
        rect(s, cx - 18, cy + 12, 6, 6, p["glove"])
        rect(s, cx + 12, cy + 12, 6, 6, p["glove"])
    elif state in ("hit", "win", "lose"):
        line(s, cx - d["shoulder"], cy + 8, cx - 12, cy + 16, p["primary"], lw)
        line(s, cx + d["shoulder"], cy + 8, cx + 12, cy + 16, p["primary"], lw)
        rect(s, cx - 14, cy + 12, 6, 6, p["glove"])
        rect(s, cx + 8, cy + 12, 6, 6, p["glove"])
    else:
        line(s, cx - d["shoulder"], cy + 8, cx - 12, cy + 16, p["primary"], lw)
        line(s, cx + d["shoulder"], cy + 8, cx + 12, cy + 16, p["primary"], lw)
        rect(s, cx - 14, cy + 12, 6, 6, p["glove"])
        rect(s, cx + 8, cy + 12, 6, 6, p["glove"])
    # legs
    if state in ("idle", "walk"):
        sway = math.sin(t * 0.7) * 2
        line(s, cx - 5, cy + 26, cx - 8 + sway, ground - 4, p["primary"], lw + 1)
        line(s, cx + 5, cy + 26, cx + 8 - sway, ground - 4, p["primary"], lw + 1)
        rect(s, cx - 11 + sway, ground - 8, 8, 8, p["boot"])
        rect(s, cx + 5 - sway, ground - 8, 8, 8, p["boot"])
    elif state == "crouch":
        rect(s, cx - 10, ground - 6, 12, 8, p["boot"])
        rect(s, cx - 2, ground - 6, 12, 8, p["boot"])
    elif state in ("lk", "hk", "throw"):
        line(s, cx - 5, cy + 26, cx - 10, ground - 4, p["primary"], lw + 1)
        line(s, cx + 5, cy + 26, cx + 10, ground - 4, p["primary"], lw + 1)
        rect(s, cx - 12, ground - 8, 8, 8, p["boot"])
        rect(s, cx + 4, ground - 8, 8, 8, p["boot"])
    elif state == "jump":
        line(s, cx - 5, cy + 26, cx - 6, ground - 12, p["primary"], lw + 1)
        line(s, cx + 5, cy + 26, cx + 6, ground - 12, p["primary"], lw + 1)
        rect(s, cx - 9, ground - 16, 8, 6, p["boot"])
        rect(s, cx + 3, ground - 16, 8, 6, p["boot"])
    else:
        line(s, cx - 5, cy + 26, cx - 8, ground - 4, p["primary"], lw + 1)
        line(s, cx + 5, cy + 26, cx + 8, ground - 4, p["primary"], lw + 1)
        rect(s, cx - 11, ground - 8, 8, 8, p["boot"])
        rect(s, cx + 5, ground - 8, 8, 8, p["boot"])

def draw_weapon(s, cx, cy, state, frame, flip, char, d):
    """Draw katana for Naomi."""
    if char["weapon"] != "katana" or state not in ("idle", "walk", "lp", "hp", "lk", "hk", "special1", "super"):
        return
    p = char["palette"]
    f = 1 if not flip else -1
    blade_w = 3
    if state == "idle":
        line(s, cx + 6 * f, cy + 10, cx + 14 * f, cy + 2, p["secondary"], blade_w)
        rect(s, cx + 12 * f, cy, 4, 4, p["secondary"])
    elif state == "hp":
        slash = 20 if frame == 2 else 0
        line(s, cx + 8 * f, cy + 6, cx + 28 * f + slash, cy - 10, p["secondary"], blade_w + 1)
        rect(s, cx + 26 * f + slash, cy - 14, 6, 6, p["secondary"])
    elif state == "special1":
        line(s, cx + 10 * f, cy + 8, cx + 30 * f, cy - 4, p["accent"], blade_w + 1)
        rect(s, cx + 28 * f, cy - 8, 6, 6, p["accent"])

def draw_effects(s, cx, cy, state, frame, flip, char, d):
    """Character-specific visual effects."""
    p = char["palette"]
    fx = char["fx"]
    if fx is None:
        return
    f = 1 if not flip else -1
    t = frame
    if fx == "aura" and state in ("idle", "walk", "special1", "super"):
        r = 14 + int(3 * math.sin(t * 0.8))
        for rr in range(r, 6, -4):
            col = (*p["accent"][:3], max(0, 100 - rr * 8))
            surf = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, col, (0, 0, rr * 2, rr * 2))
            s.blit(surf, (cx - rr, cy - 20 - rr))
    if fx == "electric" and state in ("idle", "special1", "super", "throw"):
        for k in range(4):
            a = math.radians(t * 60 + k * 90)
            ex = cx + math.cos(a) * (14 + t % 6)
            ey = cy - 10 + math.sin(a) * 8
            line(s, cx, cy - 10, ex, ey, p["accent"], 2)
            line(s, ex, ey, ex + math.cos(a) * 5, ey + math.sin(a) * 5, C["white"], 1)
    if fx == "void" and state in ("special2", "super"):
        r = 10 + int(4 * math.sin(t * 1.0))
        ellipse(s, cx - r, cy - 20 - r, r * 2, r * 2, (*p["accent"][:3], 0))  # placeholder
        pygame.draw.circle(s, p["accent"], (cx, cy - 20), r, 2)
        pygame.draw.circle(s, C["white"], (cx, cy - 20), 3)

# ------------------------------------------------------------------ animation strips
# state: (frame_count, duration_in_frames)
STATES = {
    "idle":     (5, 6),
    "walk":     (7, 4),
    "crouch":   (2, 8),
    "jump":     (5, 5),
    "lp":       (4, 3),
    "hp":       (5, 4),
    "lk":       (4, 3),
    "hk":       (5, 4),
    "block":    (2, 8),
    "throw":    (5, 4),
    "special1": (6, 4),
    "special2": (5, 3),
    "super":    (7, 4),
    "hit":      (3, 5),
    "win":      (5, 6),
    "lose":     (3, 8),
}

def build_character(tag, char):
    meta = {}
    d = body_dims(char["body"])
    ground = BASE_H - GROUND_OFFSET
    for state, (frames, duration) in STATES.items():
        strip = new_canvas(BASE_W * frames, BASE_H)
        for i in range(frames):
            s = new_canvas()
            # body center
            cx = BASE_W // 2
            cy = ground - 40  # head height approx
            # draw layers: torso first, then limbs overlay
            draw_torso(s, cx, cy, char, False, d)
            draw_limbs(s, cx, cy, state, i, False, char, d, ground)
            draw_head(s, cx, cy + 10, char, i, False, d)
            draw_weapon(s, cx, cy, state, i, False, char, d)
            draw_effects(s, cx, cy, state, i, False, char, d)
            strip.blit(s, (i * BASE_W, 0))
        fname = f"{tag}_{state}.png"
        save(strip, fname)
        meta[state] = [f"sprites/{fname}", frames, duration]
    return meta

meta = {"characters": {}, "stages": [], "effects": {}, "select": {}}

for tag, char in FIGHTERS.items():
    meta["characters"][tag] = build_character(tag, char)
    print(f"generated {tag} ({char['name']})")

# ------------------------------------------------------------------ FX sheets
def fireball_strip(name, color, count=6, size=40):
    strip = new_canvas(size * count, size)
    for i in range(count):
        s = new_canvas(size, size)
        r = 8 + int(4 * math.sin(i * 0.9))
        cx, cy = size // 2, size // 2
        for rr in range(r, 2, -2):
            shade = max(60, 255 - rr * 12)
            col = (min(255, shade + 40), min(255, shade + 80), min(255, shade + 140))
            pygame.draw.ellipse(s, col, (cx - rr, cy - rr, rr * 2, rr * 2))
        strip.blit(s, (i * size, 0))
    save(strip, name, FX)
    return [f"fx/{name}", count, 3]

def spark_strip(name, color, count=4, size=28):
    strip = new_canvas(size * count, size)
    for i in range(count):
        s = new_canvas(size, size)
        cx, cy = size // 2, size // 2
        for k in range(6):
            a = math.radians(k * 60 + i * 15)
            ex = cx + math.cos(a) * 10
            ey = cy + math.sin(a) * 10
            pygame.draw.line(s, color, (cx, cy), (ex, ey), 2)
        pygame.draw.circle(s, C["white"], (cx, cy), 3)
        strip.blit(s, (i * size, 0))
    save(strip, name, FX)
    return [f"fx/{name}", count, 2]

def flash_strip(name, color, size=100):
    s = new_canvas(size, size)
    pygame.draw.circle(s, (*color[:3], 140), (size // 2, size // 2), size // 2 - 6)
    pygame.draw.circle(s, C["white"], (size // 2, size // 2), size // 4)
    save(s, name, FX)
    return [f"fx/{name}", 1, 3]

meta["effects"]["fireball"] = fireball_strip("fireball.png", C["red"])
meta["effects"]["elecball"] = fireball_strip("elecball.png", C["yellow"])
meta["effects"]["spark"] = spark_strip("spark.png", C["yellow"])
meta["effects"]["block_spark"] = spark_strip("block_spark.png", C["white"])
meta["effects"]["hit_flash"] = flash_strip("hit_flash.png", C["red"])
meta["effects"]["super_flash"] = flash_strip("super_flash.png", C["cyan"])

# ------------------------------------------------------------------ stages (parallax layers)
W, H = 1280, 720

def stage_rooftop_layers():
    # background: night sky + distant city
    bg = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        col = (int(10 + 15 * t), int(12 + 20 * t), int(24 + 40 * t))
        pygame.draw.line(bg, col, (0, y), (W, y))
    # moon
    pygame.draw.circle(bg, (240, 240, 245), (1080, 100), 50)
    for i in range(40):
        pygame.draw.circle(bg, (255, 255, 255), (pygame.math.Vector2(i * 31 % W, i * 17 % H).x if False else (i * 31 % W, i * 17 % H)), 2)
    # distant buildings silhouettes
    for bx, bw, bh in [(100, 150, 260), (300, 120, 220), (520, 180, 300), (760, 140, 240), (960, 160, 280), (1150, 100, 200)]:
        pygame.draw.rect(bg, (14, 16, 24), (bx, H - 220 - bh, bw, bh))
        for wy in range(H - 200 - bh, H - 240, 20):
            for wx in range(bx + 14, bx + bw - 14, 18):
                if (bx + wx + wy) % 7 == 0:
                    pygame.draw.rect(bg, (255, 220, 150), (wx, wy, 10, 12))
    save(bg, "stage_rooftop_bg.png", STG, do_scale=False)

    # mid: rooftop structure + neon
    mid = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(mid, (30, 32, 44), (0, H - 260, W, 260))  # roof
    pygame.draw.rect(mid, (60, 64, 80), (0, H - 260, W, 5))    # ledge
    for i in range(0, W, 40):
        pygame.draw.rect(mid, (140, 140, 150), (i, H - 280, 5, 22))  # railing
    # neon signs
    for bx, by, col in [(300, H - 180, (255, 40, 120)), (700, H - 160, (0, 255, 200)), (1000, H - 140, (255, 255, 40))]:
        glow = pygame.Surface((120, 28), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*col, 70), (0, 0, 120, 28))
        mid.blit(glow, (bx - 6, by - 6))
        pygame.draw.rect(mid, col, (bx, by, 120, 24))
    save(mid, "stage_rooftop_mid.png", STG, do_scale=False)

    # foreground: rain + atmospheric
    fg = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(60):
        rx = (i * 97 + 100) % W
        ry = (i * 53) % H
        pygame.draw.line(fg, (180, 200, 255, 90), (rx, ry), (rx + 2, ry + 10), 1)
    save(fg, "stage_rooftop_fg.png", STG, do_scale=False)

def stage_temple_layers():
    bg = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        col = (int(255 * (1 - t * 0.3) + 180 * t * 0.3), int(200 * (1 - t * 0.2) + 160 * t * 0.2), int(120 * (1 - t * 0.4) + 100 * t * 0.4))
        pygame.draw.line(bg, col, (0, y), (W, y))
    # distant mountains
    pygame.draw.polygon(bg, (180, 140, 100), [(0, H - 240), (300, H - 460), (620, H - 240)])
    pygame.draw.polygon(bg, (150, 115, 80), [(500, H - 240), (850, H - 520), (1280, H - 240)])
    save(bg, "stage_temple_bg.png", STG, do_scale=False)

    mid = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(mid, (220, 190, 140), (0, H - 220, W, 220))  # floor
    pygame.draw.rect(mid, (160, 130, 90), (0, H - 220, W, 5))
    for i in range(0, W, 44):
        pygame.draw.rect(mid, (200, 170, 120), (i, H - 215, 40, 3))  # planks
    # lanterns
    for lx in (250, 650, 1050):
        pygame.draw.rect(mid, (130, 90, 60), (lx - 10, 130, 20, 140))
        pygame.draw.ellipse(mid, (255, 170, 100), (lx - 22, 110, 64, 44))
        pygame.draw.ellipse(mid, (255, 230, 190), (lx - 16, 116, 52, 32))
    # cherry tree
    pygame.draw.polygon(mid, (160, 50, 70), [(180, H - 220), (250, H - 420), (340, H - 220)])
    pygame.draw.line(mid, (90, 40, 50), (260, H - 220,), (260, H - 380,), 6)
    save(mid, "stage_temple_mid.png", STG, do_scale=False)

    fg = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(40):
        px = (i * 131 + 150) % W
        py = (i * 47 + 20) % H
        pygame.draw.circle(fg, (240, 100, 140, 110), (px, py), 4)
    save(fg, "stage_temple_fg.png", STG, do_scale=False)

def stage_industrial_layers():
    bg = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        col = (int(15 + 20 * t), int(18 + 25 * t), int(28 + 45 * t))
        pygame.draw.line(bg, col, (0, y), (W, y))
    # smokestacks
    for sx in (150, 420, 880, 1120):
        pygame.draw.rect(bg, (40, 42, 52), (sx, H - 380, 22, 380))
        pygame.draw.rect(bg, (60, 64, 76), (sx, H - 380, 22, 6))
    save(bg, "stage_industrial_bg.png", STG, do_scale=False)

    mid = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(mid, (50, 52, 64), (0, H - 260, W, 260))  # floor
    pygame.draw.rect(mid, (90, 94, 110), (0, H - 260, W, 5))
    for i in range(0, W, 60):
        pygame.draw.rect(mid, (120, 124, 140), (i, H - 255, 56, 3))
    # pipes
    pygame.draw.line(mid, (100, 104, 120), (60, H - 260), (60, H - 120), 5)
    pygame.draw.line(mid, (100, 104, 120), (60, H - 260), (160, H - 260), 5)
    pygame.draw.line(mid, (100, 104, 120), (900, H - 240), (900, H - 100), 5)
    # cranes
    pygame.draw.line(mid, (140, 144, 160), (300, H - 320), (300, H - 260), 6)
    pygame.draw.line(mid, (140, 144, 160), (300, H - 320), (500, H - 280), 6)
    save(mid, "stage_industrial_mid.png", STG, do_scale=False)

    fg = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(20):
        px = (i * 200 + 100) % W
        pygame.draw.rect(fg, (80, 84, 100, 90), (px, H - 60, 40, 6))
    save(fg, "stage_industrial_fg.png", STG, do_scale=False)

stage_rooftop_layers()
stage_temple_layers()
stage_industrial_layers()

meta["stages"] = [
    {"id": "rooftop", "name": "NEON ROOFTOP", "bg": "stages/stage_rooftop_bg.png", "mid": "stages/stage_rooftop_mid.png", "fg": "stages/stage_rooftop_fg.png"},
    {"id": "temple", "name": "ANCIENT TEMPLE", "bg": "stages/stage_temple_bg.png", "mid": "stages/stage_temple_mid.png", "fg": "stages/stage_temple_fg.png"},
    {"id": "industrial", "name": "INDUSTRIAL ZONE", "bg": "stages/stage_industrial_bg.png", "mid": "stages/stage_industrial_mid.png", "fg": "stages/stage_industrial_fg.png"},
]

# ------------------------------------------------------------------ character select portraits
def draw_portrait(tag, char):
    s = new_canvas(128, 128)
    p = char["palette"]
    d = body_dims(char["body"])
    # background panel
    rect(s, 0, 0, 128, 128, (40, 44, 60))
    rect(s, 4, 4, 120, 120, p["primary"])
    rect(s, 6, 6, 116, 116, (20, 24, 32))
    # head
    draw_head(s, 64, 50, char, 0, False, d)
    # name bar
    rect(s, 10, 110, 108, 14, (10, 12, 18))
    save(s, f"portrait_{tag}.png", SEL, do_scale=False)
    meta["select"][tag] = f"select/portrait_{tag}.png"

for tag, char in FIGHTERS.items():
    draw_portrait(tag, char)

with open(os.path.join(OUT, "meta.json"), "w") as fh:
    json.dump(meta, fh, indent=2)
print("meta.json written")
pygame.quit()
