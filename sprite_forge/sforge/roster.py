"""v11.20 rosters: a whole team, or a fighting game's cast, built in one go.

    forge.py roster --game soccer --out teams/                  two sides (home and away), 5 players each, keeper in gk
    forge.py roster --game fighting --size 6 --out cast/        six fighters, every fighter type, different bodies
    forge.py roster --file my_roster.json --out teams/          your own list (any mix of mannequins, rigs, captures)

Each player is an ordinary `forge.py build --game PACK ...` (sprites, atlas, game_character.json, loaders, 3D model),
in OUT/<player>/. Then every player gets portrait.png (head and shoulders, from the model), and the roster gets:

  roster.json        the game, the sides and every player: name, side, number, kit, type, body, folder, portrait
  select_screen.png  the portraits in a grid, a fighter select screen
  team_sheet.png     each side's line-up, full body (idle frame 0)

A roster file is {"game": "soccer", "players": [{"name": "keeper", "side": "Home", "kit": "gk", "type": "keeper",
"body": {"gender": 1, "muscle": 0.6, "weight": 0.6, "height": 0.7}}, {"name": "mike", "rig": "captures/mike/out/mike.glb"},
...]}. "rig" is a library rig name or a GLB / FBX file (a capture); without it the player is the mannequin with that body.
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
                                    role="Keeper" if t == "keeper" else t.replace("_", " ").title()))
    elif game in FIGHT_GAMES:
        n = size or 5
        for i in range(n):
            t = FIGHTER_ORDER[i % len(FIGHTER_ORDER)]
            body = dict(BODY[t]); body["gender"] = 1.0 if i % 3 != 2 else 0.0
            players.append(dict(name=FIGHTER_NAMES[i % len(FIGHTER_NAMES)] + ("" if i < len(FIGHTER_NAMES) else str(i)),
                                side="Cast", number=i + 1, kit=FIGHTER_KITS[i % len(FIGHTER_KITS)], type=t, body=body,
                                role=t.replace("_", " ").title()))
    else:
        n = size or 4
        for i in range(n):
            t = ["balanced", "small_agile", "big_boss", "balanced"][i % 4]
            body = dict(BODY[t]); body["gender"] = 1.0 if i % 2 == 0 else 0.0
            players.append(dict(name="hero_%d" % (i + 1), side="Cast", number=i + 1,
                                kit=FIGHTER_KITS[i % len(FIGHTER_KITS)], type=t, body=body, role=t.replace("_", " ").title()))
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
    return bad


def player_argv(game, p, out, glb=True, library=""):
    """one player -> its `forge.py build` command line"""
    a = ["build", "--game", game, "--name", p["name"], "--out", out]
    if p.get("rig"):
        a += ["--rig", p["rig"]]
    else:
        a.append("--mannequin")
        b = p.get("body") or {}
        if b:
            a += ["--human", ",".join("%s=%.2f" % (k, float(v)) for k, v in sorted(b.items()))]
    if p.get("kit"):
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
    for i, p in enumerate(roster["players"]):
        log("roster: [%d/%d] %s (%s, %s)" % (i + 1, len(roster["players"]), p["name"], p.get("type") or "balanced",
                                              p.get("rig") or "mannequin"))
        argv = player_argv(game, p, out, glb, library)
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
                       "%s%s" % ((p.get("side") + " - ") if game in TEAM_GAMES else "", p.get("role") or p.get("type") or ""))
                      for p in done], os.path.join(out, "select_screen.png"), title=title)

    def idle(p):
        mv = os.path.join(out, p["folder"], "moves")
        fs = sorted(f for f in os.listdir(mv) if f.startswith("idle_")) if os.path.isdir(mv) else []
        if not fs and os.path.isdir(mv):
            fs = sorted(os.listdir(mv))[:1]
        return os.path.join(mv, fs[0]) if fs else None
    PT.team_sheet([(s, [(idle(p), p["name"], p.get("role") or "") for p in done if p.get("side", "Cast") == s]) for s in sides],
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
