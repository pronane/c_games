"""v11.23 rosters: a whole team, or a fighting game's cast, built in one go.

    forge.py roster --game soccer --out teams/                  two sides (home and away), 5 players each, keeper in gk
    forge.py roster --game fighting --size 6 --out cast/        six fighters, every fighter type, different bodies
    forge.py roster --file my_roster.json --out teams/          your own list (any mix of mannequins, rigs, captures)

Each player is an ordinary `forge.py build --game PACK ...` (sprites, atlas, game_character.json, loaders, 3D model),
in OUT/<player>/. Then every player gets portrait.png (head and shoulders, from the model), and the roster gets:

  roster.json        the game, the sides and every player: name, side, number, kit, type, body, folder, portrait
  select_screen.png  the portraits in a grid, a fighter select screen
  team_sheet.png     each side's line-up, full body (idle frame 0)

A roster file is {"game": "soccer", "players": [{"name": "keeper", "side": "Home", "number": 1, "kit": "gk",
"type": "keeper", "look": {"hair_style": "short02", "hair_colour": "black", "skin": "young_african_male"}},
{"name": "mike", "rig": "captures/mike/out/mike.glb"}, {"name": "sub", "body": {"gender": 0, "muscle": 0.6}}, ...]}.
"rig" is a library rig name or a GLB / FBX file (a capture). "look" (v11.24) is MakeHuman appearance keys
(forge.py look --keys: hair style and colour, facial hair, skin, eyes, brows, face and muscle sliders): the player is
a realistic MakeHuman character in the roster's kit with the squad number on the back. Without "rig" or "look" the
player is the mannequin with that "body".

v11.24: default rosters give every player a look of their own - hair style and colour, facial hair, skin tone, eye
colour, face shape, and muscles to suit their type - so a team or a cast no longer looks like copies of one figure.
That needs the MakeHuman library (forge.py human --setup --full); without it the players fall back to the mannequin
with different bodies, and roster.json says so.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAM_GAMES = {"soccer": 5, "gaelic": 5, "basketball": 5}
FIGHT_GAMES = ("boxing", "fighting", "wrestling", "beat_em_up")
FIGHTER_ORDER = ["balanced", "quick_striker", "heavy_brawler", "small_agile", "big_boss"]
FIGHTER_KITS = ["red", "blue", "black", "home", "away"]
FIGHTER_NAMES = ["ace", "blaze", "brick", "pixie", "titan", "nova", "rook", "vex"]
OUTFIELD = ["playmaker", "balanced", "quick_striker", "balanced", "playmaker", "quick_striker", "balanced"]
# v11.24 looks: deterministic per player, so a roster rebuilds identically
# long01, bob01 and braid01 hang over the face on this body, so default looks leave them out (a roster file may use them)
HAIR_STYLES = ["short02", "buzz", "short01", "afro01", "short04", "bald", "ponytail01", "short03"]
HAIR_COLOURS = ["#1b1410", "#3b2614", "#6b4a2b", "#a8743f", "#c9a465", "#8a3b1c", "#2a2a2a", "#7a7570"]
SKINS = ["young_caucasian_male", "young_african_male", "young_asian_male", "young_caucasian_male2",
         "middleage_african_male", "middleage_caucasian_male", "middleage_asian_male"]
FACIAL = ["none", "stubble", "none", "goatee", "none", "beard", "moustache", "stubble"]
EYES = ["brown", "blue", "green", "brownlight", "grey", "bluegreen", "lightblue"]
FACE_KEYS = ["nose_size", "nose_width", "lips", "jaw", "chin", "cheekbones", "cheeks", "eye_size", "ears", "brow_height"]
MUSCLE = {"heavy_brawler": 0.8, "big_boss": 0.9, "quick_striker": 0.35, "small_agile": -0.2, "keeper": 0.3,
          "playmaker": 0.0, "balanced": 0.2}


def look_for(i, t="balanced", salt=0):
    """player i's look (appearance keys): hair, colour, facial hair, skin, eyes, brows, face shape, muscles for type t"""
    import random
    r = random.Random(1009 * (i + 1) + 7919 * salt)
    hs = HAIR_STYLES[(i * 5 + salt) % len(HAIR_STYLES)]
    lk = dict(hair_style=hs, hair_colour=HAIR_COLOURS[(i * 3 + salt) % len(HAIR_COLOURS)],
              facial_hair=FACIAL[(i * 7 + salt) % len(FACIAL)], skin=SKINS[(i * 2 + salt) % len(SKINS)],
              eye_colour=EYES[(i + salt) % len(EYES)], brow_style="eyebrow%03d" % (1 + (i * 5 + salt) % 12))
    if hs == "bald":
        lk["facial_hair"] = "beard"
    for k in FACE_KEYS:
        lk[k] = round(r.uniform(-0.6, 0.6), 2)
    m = MUSCLE.get(t, 0.2)
    for k in ("muscle_arms", "muscle_shoulders", "muscle_chest", "muscle_back", "muscle_legs"):
        lk[k] = round(max(-1.0, min(1.0, m + r.uniform(-0.15, 0.15))), 2)
    lk["shoulder_width"] = round(max(-1.0, min(1.0, m * 0.6 + r.uniform(-0.2, 0.2))), 2)
    return lk


def looks_available():
    """the MakeHuman library and a template are here, so players can have looks"""
    try:
        from .mhlib import Library
        from . import look as LK
        return Library().available() and LK.default_template(make=True) is not None
    except Exception:                                                      # noqa: BLE001
        return False


# body per character type (MakeHuman macros 0..1): a heavy brawler is big, a small agile fighter light
BODY = {
    "balanced": dict(muscle=0.55, weight=0.5, height=0.5),
    "quick_striker": dict(muscle=0.6, weight=0.35, height=0.45),
    "heavy_brawler": dict(muscle=0.8, weight=0.8, height=0.6),
    "small_agile": dict(muscle=0.5, weight=0.3, height=0.25),
    "big_boss": dict(muscle=0.85, weight=0.8, height=0.85),
    "playmaker": dict(muscle=0.5, weight=0.4, height=0.4),
    "keeper": dict(muscle=0.6, weight=0.6, height=0.8),
}


def default_roster(game, size=0):
    """the roster a game gets when you don't give one: two sides for team sports, a cast for fighting games"""
    players = []
    if game in TEAM_GAMES:
        n = size or TEAM_GAMES[game]
        for side, kit, g0 in (("Home", "home", 1.0), ("Away", "away", 0.0)):
            for i in range(n):
                t = "keeper" if i == 0 else OUTFIELD[(i - 1) % len(OUTFIELD)]
                body = dict(BODY[t]); body["gender"] = g0 if i % 2 == 0 else 1.0 - g0
                body["height"] = round(min(1.0, body["height"] + 0.07 * ((i * 3) % 5 - 2)), 2)
                players.append(dict(name="%s_%d" % (side.lower(), i + 1), side=side, number=i + 1,
                                    kit="gk" if t == "keeper" else kit, type=t, body=body,
                                    look=look_for(i, t, salt=0 if side == "Home" else 3),
                                    role="Keeper" if t == "keeper" else t.replace("_", " ").title()))
    elif game in FIGHT_GAMES:
        n = size or 5
        for i in range(n):
            t = FIGHTER_ORDER[i % len(FIGHTER_ORDER)]
            body = dict(BODY[t]); body["gender"] = 1.0 if i % 3 != 2 else 0.0
            players.append(dict(name=FIGHTER_NAMES[i % len(FIGHTER_NAMES)] + ("" if i < len(FIGHTER_NAMES) else str(i)),
                                side="Cast", number=i + 1, kit=FIGHTER_KITS[i % len(FIGHTER_KITS)], type=t, body=body,
                                look=look_for(i, t, salt=1), role=t.replace("_", " ").title()))
    else:
        n = size or 4
        for i in range(n):
            t = ["balanced", "small_agile", "big_boss", "balanced"][i % 4]
            body = dict(BODY[t]); body["gender"] = 1.0 if i % 2 == 0 else 0.0
            players.append(dict(name="hero_%d" % (i + 1), side="Cast", number=i + 1,
                                kit=FIGHTER_KITS[i % len(FIGHTER_KITS)], type=t, body=body, look=look_for(i, t, salt=2),
                                role=t.replace("_", " ").title()))
    return dict(game=game, players=players)


def validate(roster):
    """-> list of problems (empty = fine)"""
    from . import gamepack as GP
    from . import chartypes
    bad = []
    if roster.get("game") not in GP.list_packs():
        bad.append("unknown game %r" % roster.get("game"))
    names = [p.get("name", "") for p in roster.get("players", [])]
    if not names:
        bad.append("no players")
    if len(set(names)) != len(names):
        bad.append("two players share a name")
    for p in roster.get("players", []):
        n = p.get("name", "")
        if not n or any(c in n for c in " /\\:"):
            bad.append("bad name %r (letters, digits, _ and - only)" % n)
        if p.get("type") and p["type"] not in chartypes.list_types():
            bad.append("%s: unknown type %r" % (n, p["type"]))
        for k, v in (p.get("body") or {}).items():
            if not isinstance(v, (int, float)) or not 0 <= v <= 1:
                bad.append("%s: body %s=%r must be 0..1" % (n, k, v))
        if p.get("look"):
            from .appearance import Appearance, KEYS
            unknown = [k for k in p["look"] if k not in KEYS]
            if unknown:
                bad.append("%s: unknown look keys %s (forge.py look --keys)" % (n, unknown))
            else:
                ap = Appearance()
                for k, v in p["look"].items():
                    try:
                        ap.set(k, v)
                    except Exception as e:                                 # noqa: BLE001
                        bad.append("%s: look %s=%r: %s" % (n, k, v, e))
        if p.get("number") is not None and (not isinstance(p["number"], int) or not 0 <= p["number"] <= 99):
            bad.append("%s: number %r must be 0..99" % (n, p["number"]))
    return bad


def look_argv(p, glb_path):
    """a player with a look -> the `forge.py look` command line that makes their character GLB in their kit"""
    kit = "sf_%s" % (p.get("kit") or "home")
    if p.get("number") is not None:
        kit += "#%d" % int(p["number"])
    sets = ",".join("%s=%s" % (k, v) for k, v in p["look"].items())
    return ["look", "--set", sets, "--kit", kit, "--glb", glb_path]


def player_argv(game, p, out, glb=True, library="", look_glb=None):
    """one player -> its `forge.py build` command line (look_glb: their look's character, kit already painted)"""
    a = ["build", "--game", game, "--name", p["name"], "--out", out]
    if look_glb:
        a += ["--rig", look_glb]
    elif p.get("rig"):
        a += ["--rig", p["rig"]]
    else:
        a.append("--mannequin")
        b = p.get("body") or {}
        if b:
            a += ["--human", ",".join("%s=%.2f" % (k, float(v)) for k, v in sorted(b.items()))]
    if p.get("kit") and not look_glb:
        a += ["--kit", p["kit"]]
    if p.get("type") and p["type"] != "balanced":
        a += ["--character-type", p["type"]]
    if library:
        a += ["--motion-library", library]
    if not glb:
        a.append("--no-glb")
    return a


def build(roster, out, glb=True, library="", log=print, run=None):
    """build every player, then portraits, roster.json, select_screen.png and team_sheet.png. -> roster.json path"""
    from . import portrait as PT
    bad = validate(roster)
    if bad:
        raise ValueError("; ".join(bad))
    os.makedirs(out, exist_ok=True)
    game = roster["game"]
    done = []
    use_looks = any(p.get("look") and not p.get("rig") for p in roster["players"]) and looks_available()
    if any(p.get("look") and not p.get("rig") for p in roster["players"]) and not use_looks:
        log("roster: no MakeHuman library here (forge.py human --setup --full) - players are mannequins with their bodies")
    for i, p in enumerate(roster["players"]):
        look_glb = None
        if use_looks and p.get("look") and not p.get("rig"):
            look_glb = os.path.join(out, "_looks", p["name"] + ".glb")
            os.makedirs(os.path.dirname(look_glb), exist_ok=True)
            la = look_argv(p, look_glb)
            r = run(la) if run is not None else subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + la,
                                                                cwd=HERE, capture_output=True, text=True)
            rc = r if isinstance(r, int) else r.returncode
            if rc != 0 or not os.path.isfile(look_glb):
                log("roster:   %s's look failed - mannequin instead%s" % (p["name"], "" if isinstance(r, int) else ": " + (r.stdout + r.stderr)[-300:]))
                look_glb = None
        log("roster: [%d/%d] %s (%s, %s)" % (i + 1, len(roster["players"]), p["name"], p.get("type") or "balanced",
                                              "look" if look_glb else (p.get("rig") or "mannequin")))
        argv = player_argv(game, p, out, glb, library, look_glb)
        if run is not None:
            rc = run(argv)
        else:
            r = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + argv, cwd=HERE,
                               capture_output=True, text=True)
            rc = r.returncode
            if rc:
                log((r.stdout + r.stderr)[-800:])
        folder = os.path.join(out, p["name"])
        if rc != 0 or not os.path.isfile(os.path.join(folder, "game_character.json")):
            raise RuntimeError("roster: building %s failed (exit %s)" % (p["name"], rc))
        por, how = PT.portrait(folder)
        q = {}
        try:
            q = json.load(open(os.path.join(folder, "qa.json")))
        except (OSError, ValueError):
            pass
        rec = dict(p)
        rec.update(folder=p["name"], manifest=p["name"] + "/game_character.json",
                   built_as="look" if look_glb else ("rig" if p.get("rig") else "mannequin"),
                   portrait=p["name"] + "/portrait.png" if por else "", portrait_from=how,
                   model=p["name"] + "/model.glb" if os.path.isfile(os.path.join(folder, "model.glb")) else "",
                   qa_score=q.get("score"), qa_fail=q.get("fail"))
        done.append(rec)
        log("roster:   portrait (%s), QA %s" % (how, q.get("score")))
    sides = []
    for p in done:
        if p.get("side", "Cast") not in sides:
            sides.append(p.get("side", "Cast"))
    doc = dict(format="spriteforge.roster", version=1, game=game, sides=sides, players=done,
               select_screen="select_screen.png", team_sheet="team_sheet.png")
    title = "SELECT YOUR FIGHTER" if game in FIGHT_GAMES else ("PICK YOUR PLAYER" if game in TEAM_GAMES else "SELECT CHARACTER")
    PT.select_screen([(os.path.join(out, p["portrait"]) if p["portrait"] else None, p["name"],
                       "%s%s%s" % (("#%d " % p["number"]) if game in TEAM_GAMES and p.get("number") is not None else "",
                                   (p.get("side") + " - ") if game in TEAM_GAMES else "", p.get("role") or p.get("type") or ""))
                      for p in done], os.path.join(out, "select_screen.png"), title=title)

    def idle(p):
        mv = os.path.join(out, p["folder"], "moves")
        fs = sorted(f for f in os.listdir(mv) if f.startswith("idle_")) if os.path.isdir(mv) else []
        if not fs and os.path.isdir(mv):
            fs = sorted(os.listdir(mv))[:1]
        return os.path.join(mv, fs[0]) if fs else None
    PT.team_sheet([(s, [(idle(p), p["name"], (("#%d " % p["number"]) if game in TEAM_GAMES and p.get("number") is not None else "") + (p.get("role") or "")) for p in done if p.get("side", "Cast") == s]) for s in sides],
                  os.path.join(out, "team_sheet.png"), title="%s roster" % game.replace("_", " ").title())
    path = os.path.join(out, "roster.json")
    json.dump(doc, open(path, "w"), indent=1)
    log("roster: %d players -> %s" % (len(done), path))
    return path


def load(path):
    d = json.load(open(path))
    if "players" not in d:
        raise ValueError("%s has no players" % path)
    return d


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="forge.py roster", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="game pack (forge.py game list)")
    ap.add_argument("--file", help="a roster JSON (see above) instead of the default one")
    ap.add_argument("--size", type=int, default=0, help="players per side (team games) or fighters in the cast")
    ap.add_argument("--out", default="rosters")
    ap.add_argument("--motion-library", dest="library", default="")
    ap.add_argument("--no-glb", action="store_true", help="no 3D models (portraits then come from the sprites)")
    ap.add_argument("--show", action="store_true", help="print the roster that would be built, and stop")
    a = ap.parse_args(argv)
    if a.file:
        r = load(a.file)
        if a.game:
            r["game"] = a.game
    elif a.game:
        r = default_roster(a.game, a.size)
    else:
        ap.error("give --game or --file")
    bad = validate(r)
    if bad:
        print("roster: " + "; ".join(bad)); return 2
    if a.show:
        print(json.dumps(r, indent=1)); return 0
    out = os.path.join(a.out, r["game"]) if not a.file else a.out
    try:
        build(r, out, glb=not a.no_glb, library=a.library)
    except (RuntimeError, ValueError) as e:
        print(e); return 1
    return 0
