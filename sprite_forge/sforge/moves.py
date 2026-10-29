"""Move (animation) presets.  A *move* is what the game asks for: a name,
frame count, playback fps, loop flag and which procedural motion drives the
3D mannequin for it ("motion").  Custom moves can reuse any library motion."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict, field


def slug(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("(", " ").replace(")", " ").replace("/", " ").replace("-", " ").replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


@dataclass
class MoveSpec:
    name: str              # file/animation id, e.g. "pick_up_ground"
    label: str = ""        # display name, e.g. "Pick Up (Ground)"
    category: str = "General"
    frames: int = 8
    fps: int = 12
    loop: bool = False
    motion: str = ""       # library motion that drives the mannequin ("" = same as name)
    desc: str = ""
    enabled: bool = True

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return MoveSpec(**{k: v for k, v in d.items() if k in MoveSpec.__dataclass_fields__})


def _m(label, cat, frames, fps, loop=False, motion="", desc=""):
    return MoveSpec(slug(label), label, cat, frames, fps, loop, motion, desc)


# 36 moves exactly as listed on the user's Gaelic football reference sheet
GAELIC_36 = [
    _m("Idle", "Locomotion", 8, 8, True, desc="default standing pose"),
    _m("Walk", "Locomotion", 8, 10, True, desc="standard walk cycle"),
    _m("Run", "Locomotion", 8, 12, True, desc="jogging"),
    _m("Sprint", "Locomotion", 8, 14, True, desc="full speed run"),
    _m("Stop", "Locomotion", 6, 12, desc="come to a stop"),
    _m("Change Direction", "Locomotion", 8, 12, desc="left/right cut"),
    _m("Pick Up (Ground)", "Ball handling", 8, 12, desc="collect ball from ground"),
    _m("Pick Up (Aerial)", "Ball handling", 8, 12, desc="catch dropping ball"),
    _m("Hold", "Ball handling", 6, 8, True, desc="hold ball in hands"),
    _m("Carry", "Ball handling", 8, 12, True, desc="run with ball"),
    _m("Bounce (Solo)", "Ball handling", 8, 12, True, desc="solo the ball (dribble)"),
    _m("Hand Pass", "Passing", 6, 12, desc="pass with hands"),
    _m("Low Kick (Pass)", "Kicking", 8, 14, desc="short kick"),
    _m("High Kick (Pass)", "Kicking", 8, 14, desc="long kick"),
    _m("Shoot (Point)", "Kicking", 8, 14, desc="kick over bar"),
    _m("Shoot (Goal)", "Kicking", 8, 14, desc="kick to goal"),
    _m("Catch (Ground)", "Ball handling", 6, 12, desc="catch low ball"),
    _m("Catch (Aerial)", "Ball handling", 8, 12, desc="leap and catch"),
    _m("Tackle", "Defence", 8, 12, desc="attempt tackle"),
    _m("Block", "Defence", 6, 12, desc="block kick/pass"),
    _m("Juke / Feint", "Evasion", 8, 12, desc="fake move"),
    _m("Sidestep", "Evasion", 8, 12, desc="evasive move"),
    _m("Spin", "Evasion", 8, 12, desc="spin move"),
    _m("Jump", "Locomotion", 8, 12, desc="vertical jump"),
    _m("Leap Catch", "Ball handling", 10, 12, desc="high catch"),
    _m("Fist Pass", "Passing", 6, 12, desc="pass with fist"),
    _m("Fist Shoot", "Kicking", 6, 12, desc="shoot with fist"),
    _m("Celebrate (Point)", "Celebration", 10, 10, desc="short celebration"),
    _m("Celebrate (Goal)", "Celebration", 12, 10, desc="extended celebration"),
    _m("Fall", "Contact", 8, 12, desc="fall after contact"),
    _m("Get Up", "Contact", 10, 10, desc="recover from fall"),
    _m("Injured (Idle)", "Contact", 8, 6, True, desc="hold injury pose"),
    _m("Goalkeeper Save", "Goalkeeper", 8, 12, motion="gk_save", desc="save attempt (GK)"),
    _m("Goalkeeper Dive Left", "Goalkeeper", 10, 14, motion="gk_dive_left", desc="dive left (GK)"),
    _m("Goalkeeper Dive Right", "Goalkeeper", 10, 14, motion="gk_dive_right", desc="dive right (GK)"),
    _m("Goalkeeper Throw Out", "Goalkeeper", 8, 12, motion="gk_throw_out", desc="throw out (GK)"),
]

# 14 moves used by the Egyptian Fighter / Padel Wars raylib projects
FIGHTER_14 = [
    _m("Idle", "Basic", 6, 8, True, motion="fight_idle", desc="fighting stance"),
    _m("Walk", "Basic", 8, 10, True, motion="fight_walk", desc="stance walk"),
    _m("Crouch", "Basic", 4, 10, motion="crouch", desc="crouch down"),
    _m("Jump", "Basic", 8, 10, motion="jump", desc="jump"),
    _m("Punch", "Attack", 6, 14, desc="straight punch"),
    _m("Kick", "Attack", 7, 14, desc="front kick"),
    _m("Special 1", "Attack", 8, 12, motion="special_1", desc="special move 1 (rising uppercut)"),
    _m("Special 2", "Attack", 10, 14, motion="special_2", desc="special move 2 (spinning kick)"),
    _m("Block", "Defence", 3, 10, motion="guard", desc="guard / block"),
    _m("Hit", "Defence", 4, 12, desc="take a hit"),
    _m("Throw", "Attack", 8, 12, desc="grab and throw"),
    _m("Jump Attack", "Attack", 6, 12, motion="jump_attack", desc="flying kick"),
    _m("Taunt", "Extra", 8, 8, desc="taunt"),
    _m("Victory", "Extra", 10, 8, desc="victory pose"),
]

# SpriteForge standard names (SF_SPECIAL1 ... in spriteforge.h): special1, special2, jumpattack
for _mv in FIGHTER_14:
    _mv.name = {"special_1": "special1", "special_2": "special2", "jump_attack": "jumpattack"}.get(_mv.name, _mv.name)

PLATFORMER_10 = [
    _m("Idle", "Basic", 8, 8, True), _m("Walk", "Basic", 8, 10, True), _m("Run", "Basic", 8, 12, True),
    _m("Jump", "Basic", 8, 12), _m("Crouch", "Basic", 4, 10), _m("Punch", "Attack", 6, 14),
    _m("Kick", "Attack", 7, 14), _m("Hit", "Damage", 4, 12), _m("Fall", "Damage", 8, 12), _m("Get Up", "Damage", 10, 10),
]

# TurboTumble64 kart racer (character seated in a kart; kart prop included in renders)
KART_12 = [
    _m("Idle", "Kart", 6, 8, True, motion="kart_idle", desc="sitting in the kart"),
    _m("Drive", "Kart", 8, 12, True, motion="kart_drive", desc="driving"),
    _m("Steer Left", "Kart", 4, 10, motion="steer_left", desc="steer left"),
    _m("Steer Right", "Kart", 4, 10, motion="steer_right", desc="steer right"),
    _m("Boost", "Kart", 6, 12, True, motion="boost", desc="turbo boost"),
    _m("Drift", "Kart", 6, 12, True, motion="drift", desc="power slide"),
    _m("Hit", "Kart", 6, 12, motion="kart_hit", desc="hit by an item"),
    _m("Spin Out", "Kart", 8, 14, motion="spin_out", desc="spin out"),
    _m("Item Throw", "Kart", 6, 12, motion="item_throw", desc="throw an item"),
    _m("Victory", "Kart", 8, 8, True, motion="kart_victory", desc="race won"),
    _m("Defeat", "Kart", 6, 6, motion="defeat", desc="race lost"),
    _m("Taunt", "Kart", 8, 10, motion="kart_taunt", desc="wave / taunt"),
]

PRESETS = {
    "Gaelic football (36 moves)": GAELIC_36,
    "Fighter (14 moves)": FIGHTER_14,
    "Platformer basics (10 moves)": PLATFORMER_10,
    "Kart racer - TurboTumble64 (12 moves)": KART_12,
}
PRESET_KEYS = {"gaelic36": "Gaelic football (36 moves)", "fighter14": "Fighter (14 moves)",
               "platformer10": "Platformer basics (10 moves)",
               "kart12": "Kart racer - TurboTumble64 (12 moves)"}


def preset(name):
    import copy
    key = PRESET_KEYS.get(name, name)
    return [copy.deepcopy(m) for m in PRESETS[key]]


def motion_for(spec: MoveSpec):
    from .motions import find_motion, LIB
    m = find_motion(spec.motion) if spec.motion else None
    if m is None:
        m = find_motion(spec.name)
    return m
