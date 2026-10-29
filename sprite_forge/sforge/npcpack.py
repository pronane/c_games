"""Sprite Forge Studio v9 - enemy / NPC preset pack.

Move presets (forge.py build --preset npc_civilian ...) and character presets (--npc goblin -> a spec; a starting
point for --variants, colours and accessories).  All characters are fictional procedural mannequins - no likeness."""
from __future__ import annotations
from .moves import MoveSpec

def _m(name, frames, fps, loop=False, motion="", cat="NPC", label=""):
    return MoveSpec(name=name, label=label or name.replace("_", " ").title(), category=cat, frames=frames, fps=fps, loop=loop,
                    motion=motion or name)

MOVE_PRESETS = {
    "npc_civilian": ("Civilian NPC (8 moves)", [_m("idle", 6, 8, True), _m("walk", 8, 10, True), _m("run", 8, 12, True),
                     _m("talk", 8, 8, True), _m("wave", 8, 10, True), _m("look_around", 8, 6, True), _m("cower", 6, 10, True),
                     _m("sit", 4, 6, True)]),
    "npc_guard": ("Guard NPC (8 moves)", [_m("idle", 6, 8, True), _m("patrol", 8, 8, True), _m("look_around", 8, 6, True),
                  _m("alert", 6, 12), _m("attack", 8, 14, motion="swing_attack"), _m("run", 8, 12, True), _m("hit", 4, 12),
                  _m("die", 8, 10)]),
    "enemy_grunt": ("Enemy grunt (8 moves)", [_m("idle", 6, 8, True, "fight_idle"), _m("walk", 8, 10, True, "fight_walk"),
                    _m("run", 8, 12, True), _m("attack", 8, 14, motion="swing_attack"), _m("lunge", 7, 14), _m("hit", 4, 12),
                    _m("die", 8, 10), _m("taunt", 8, 8)]),
    "enemy_caster": ("Enemy caster (7 moves)", [_m("idle", 6, 8, True, "hover"), _m("walk", 8, 8, True, "patrol"),
                     _m("cast", 8, 12), _m("special", 8, 12, motion="special_1"), _m("hit", 4, 12), _m("die", 8, 10),
                     _m("victory", 8, 8)]),
    "enemy_creature": ("Small creature (6 moves)", [_m("idle", 6, 8, True), _m("hop", 8, 12, True), _m("lunge", 7, 14),
                       _m("hit", 4, 12), _m("die", 8, 10), _m("limp", 8, 8, True)]),
    "boss": ("Boss (12 moves)", [_m("idle", 6, 8, True, "fight_idle"), _m("walk", 8, 8, True, "fight_walk"), _m("roar", 10, 10),
             _m("punch", 6, 14), _m("kick", 7, 14), _m("attack", 8, 12, motion="swing_attack"), _m("special1", 8, 12, motion="special_1"),
             _m("special2", 10, 14, motion="special_2"), _m("block", 3, 10, motion="guard"), _m("hit", 4, 12), _m("die", 8, 10),
             _m("victory", 10, 8)]),
    "zombie": ("Zombie / undead (6 moves)", [_m("idle", 6, 6, True), _m("walk", 8, 6, True, "limp"), _m("attack", 8, 10, motion="lunge"),
               _m("hit", 4, 12), _m("die", 8, 10), _m("get_up", 8, 8)]),
}

# fictional character presets: spec fields (+ which move preset suits them)
CHARACTERS = {
    "villager":   ("npc_civilian", dict(build="average", top="tshirt", top_colour="#b08a5a", bottom="trousers", bottom_colour="#4b3b2a", shoes="boots", hair_style="short", hair_colour="brown", accessories="satchel")),
    "shopkeeper": ("npc_civilian", dict(build="heavy", weight_kg=95, top="longsleeve", top_colour="#e8e2d0", bottom="trousers", bottom_colour="#3a3a46", hair_style="bald", facial_hair="moustache", accessories="glasses,belt")),
    "kid":        ("npc_civilian", dict(height_cm=135, weight_kg=32, build="slim", top="tshirt", top_colour="#f2c14e", bottom="shorts", bottom_colour="#2b5ea7", shoes="trainers", hair_style="curly", accessories="cap,backpack")),
    "elder":      ("npc_civilian", dict(height_cm=166, build="slim", top="hoodie", top_colour="#6b5b8a", bottom="trousers", bottom_colour="#5a5a5a", hair_style="short", hair_colour="grey", facial_hair="beard", accessories="glasses,scarf")),
    "guard":      ("npc_guard", dict(build="muscular", top="longsleeve", top_colour="#33415c", trim_colour="#c9a227", bottom="trousers", bottom_colour="#1e2533", shoes="boots", accessories="helmet,armor,belt,gloves", accessory_colour="#9aa3ad")),
    "knight":     ("npc_guard", dict(build="muscular", top="longsleeve", top_colour="#8a9099", bottom="trousers", bottom_colour="#5d636b", accessories="helmet,armor,shoulder_pads,gloves,cape", accessory_colour="#b8c0c8", accessory2_colour="#7a1f2b")),
    "bandit":     ("enemy_grunt", dict(build="athletic", top="tank", top_colour="#5b3a29", bottom="trousers", bottom_colour="#2e2a24", hair_style="long", facial_hair="stubble", accessories="mask,wristbands,belt", accessory_colour="#1b1b1b")),
    "goblin":     ("enemy_grunt", dict(height_cm=120, weight_kg=40, build="slim", skin_tone="#6f9a3e", top="tank", top_colour="#6b4a2b", bottom="shorts", bottom_colour="#4a3520", shoes="barefoot", hair_style="bald", ears="large", nose="large", accessories="horns,belt", accessory_colour="#d8cfb0")),
    "orc_brute":  ("boss", dict(height_cm=205, weight_kg=140, build="heavy", skin_tone="#4f7a45", top="tank", top_colour="#3b2d22", bottom="trousers", bottom_colour="#2b231c", hair_style="bald", facial_hair="none", accessories="shoulder_pads,wristbands,belt", accessory_colour="#5b4636")),
    "ninja":      ("enemy_grunt", dict(build="slim", top="longsleeve", top_colour="#15171c", bottom="trousers", bottom_colour="#15171c", shoes="trainers", shoes_colour="#15171c", hair_style="bun", accessories="mask,headband,scarf", accessory_colour="#15171c", accessory2_colour="#b3202a")),
    "wizard":     ("enemy_caster", dict(build="slim", top="hoodie", top_colour="#3b2a6b", bottom="trousers", bottom_colour="#2b1f4f", hair_style="long", hair_colour="white", facial_hair="beard", accessories="cape,visor", accessory2_colour="#5fd3ff")),
    "skeleton":   ("zombie", dict(build="slim", weight_kg=50, skin_tone="#e8e2cf", top="tank", top_colour="#d8d2bf", bottom="shorts", bottom_colour="#cfc8b3", shoes="barefoot", hair_style="bald", eye_colour="#ff3b30")),
    "zombie":     ("zombie", dict(build="average", skin_tone="#8fa77a", top="tshirt", top_colour="#6d6a5e", bottom="trousers", bottom_colour="#3d4a5c", hair_style="short", hair_colour="black", eye_colour="#d9d36a")),
    "ghost":      ("enemy_caster", dict(build="slim", skin_tone="#dfe8f2", top="hoodie", top_colour="#e9eef5", bottom="trousers", bottom_colour="#d6dee8", shoes="barefoot", hair_style="long", hair_colour="white", accessories="cape", accessory_colour="#e9eef5")),
    "robot":      ("enemy_grunt", dict(build="muscular", skin_tone="#9aa3ad", top="longsleeve", top_colour="#5b6470", trim_colour="#ff8c1a", bottom="trousers", bottom_colour="#3d434b", hair_style="bald", accessories="helmet,visor,armor,gloves", accessory_colour="#7d8794", accessory2_colour="#30e0ff")),
    "slime_imp":  ("enemy_creature", dict(height_cm=95, weight_kg=25, build="heavy", skin_tone="#7b4fb8", top="tank", top_colour="#5a3590", bottom="shorts", bottom_colour="#5a3590", shoes="barefoot", hair_style="bald", accessories="horns", accessory_colour="#f0d060")),
    "boss_king":  ("boss", dict(height_cm=195, weight_kg=110, build="muscular", top="longsleeve", top_colour="#6b1020", trim_colour="#d4af37", bottom="trousers", bottom_colour="#2a0f14", hair_style="long", hair_colour="black", facial_hair="beard", accessories="crown,cape,shoulder_pads,belt", accessory_colour="#d4af37", accessory2_colour="#4a0a14")),
}


def register():
    """add the move presets to moves.PRESETS / PRESET_KEYS (idempotent)"""
    from . import moves
    for k, (label, mv) in MOVE_PRESETS.items():
        moves.PRESETS[label] = mv
        moves.PRESET_KEYS[k] = label


def character_spec(name, **over):
    from .spec import CharacterSpec
    if name not in CHARACTERS:
        raise ValueError("unknown NPC preset '%s' (choose: %s)" % (name, ", ".join(CHARACTERS)))
    mp, d = CHARACTERS[name]
    d = dict(d); d.update(over)
    sp = CharacterSpec(name=name, **{k: v for k, v in d.items() if hasattr(CharacterSpec, k) or k in CharacterSpec.__dataclass_fields__})
    return sp, mp


def listing():
    L = ["NPC / enemy move presets (--preset):"]
    for k, (label, mv) in MOVE_PRESETS.items():
        L.append("  %-15s %s: %s" % (k, label, ", ".join(m.name for m in mv)))
    L.append("NPC / enemy characters (--npc NAME, all fictional mannequins):")
    for k, (mp, d) in CHARACTERS.items():
        L.append("  %-11s moves %-15s %s" % (k, mp, ", ".join("%s=%s" % kv for kv in list(d.items())[:4])))
    return "\n".join(L)


register()
