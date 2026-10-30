"""Counties, kits, and fictional squads. No real player likenesses."""

from __future__ import annotations

import random

from peil26.settings import FORMATION, ROLE_ORDER

# Traditional colours, simplified so neighbouring counties stay distinct
# on a broadcast camera. Badges are original letter-marks, not crests.
COUNTIES = [
    {"name": "Dublin", "short": "DUB", "jersey": (92, 168, 222), "shorts": (16, 28, 64), "socks": (92, 168, 222), "trim": (230, 236, 242)},
    {"name": "Kerry", "short": "KER", "jersey": (0, 132, 58), "shorts": (0, 96, 42), "socks": (242, 196, 42), "trim": (242, 196, 42)},
    {"name": "Galway", "short": "GAL", "jersey": (122, 24, 48), "shorts": (236, 236, 236), "socks": (122, 24, 48), "trim": (236, 236, 236)},
    {"name": "Mayo", "short": "MAY", "jersey": (16, 118, 64), "shorts": (176, 28, 36), "socks": (176, 28, 36), "trim": (176, 28, 36)},
    {"name": "Armagh", "short": "ARM", "jersey": (232, 118, 28), "shorts": (236, 236, 236), "socks": (232, 118, 28), "trim": (236, 236, 236)},
    {"name": "Tyrone", "short": "TYR", "jersey": (236, 236, 236), "shorts": (176, 28, 36), "socks": (176, 28, 36), "trim": (176, 28, 36)},
    {"name": "Donegal", "short": "DON", "jersey": (242, 196, 42), "shorts": (0, 96, 42), "socks": (0, 96, 42), "trim": (0, 96, 42)},
    {"name": "Cork", "short": "COR", "jersey": (176, 28, 36), "shorts": (236, 236, 236), "socks": (176, 28, 36), "trim": (236, 236, 236)},
    {"name": "Derry", "short": "DER", "jersey": (176, 28, 36), "shorts": (176, 28, 36), "socks": (236, 236, 236), "trim": (236, 236, 236)},
    {"name": "Down", "short": "DOW", "jersey": (176, 28, 36), "shorts": (18, 18, 18), "socks": (18, 18, 18), "trim": (18, 18, 18)},
    {"name": "Roscommon", "short": "ROS", "jersey": (28, 70, 150), "shorts": (242, 206, 70), "socks": (28, 70, 150), "trim": (242, 206, 70)},
    {"name": "Monaghan", "short": "MON", "jersey": (236, 236, 236), "shorts": (18, 18, 18), "socks": (28, 70, 150), "trim": (28, 70, 150)},
    {"name": "Meath", "short": "MEA", "jersey": (0, 118, 52), "shorts": (0, 86, 40), "socks": (242, 196, 42), "trim": (20, 20, 20)},
    {"name": "Kildare", "short": "KIL", "jersey": (236, 236, 236), "shorts": (236, 236, 236), "socks": (236, 236, 236), "trim": (20, 20, 20)},
    {"name": "Clare", "short": "CLA", "jersey": (28, 78, 160), "shorts": (214, 150, 42), "socks": (214, 150, 42), "trim": (214, 150, 42)},
    {"name": "Louth", "short": "LOU", "jersey": (176, 28, 36), "shorts": (176, 28, 36), "socks": (236, 236, 236), "trim": (18, 18, 18)},
]

FIRST = [
    "Sean", "Cillian", "Conor", "Padraig", "Darragh", "Oisin", "Tadhg", "Eoin",
    "Brian", "Niall", "Cathal", "Diarmuid", "Fionn", "Rian", "Liam", "Ciaran",
    "Shane", "Enda", "Colm", "Aidan", "Kevin", "Jack", "Cormac", "Dara",
    "Eoghan", "Senan", "Oran", "Cian", "Dylan", "Aaron", "Mark", "Stephen",
    "Rory", "Patrick", "Thomas", "Evan", "Callum", "Odhran", "Lorcan", "Naoise",
]

SURNAMES = [
    "Murphy", "Kelly", "Walsh", "Byrne", "Ryan", "Doyle", "Gallagher", "Kennedy",
    "Lynch", "Murray", "Quinn", "Moore", "Carroll", "Dunne", "Brennan", "Foley",
    "Hayes", "Griffin", "Healy", "Power", "Nugent", "Sweeney", "Keane", "Brosnan",
    "McGrath", "McLoughlin", "McManus", "Daly", "Flynn", "Reilly", "Crowley",
    "Sheehan", "Horan", "Duggan", "Flanagan", "Molloy", "Barrett", "Downey",
    "Kearney", "Deegan", "Rooney", "Burns", "Maguire", "Donnelly", "Farrell",
]

# Avoid accidental full-name matches with well-known inter-county players.
BLOCK = {
    "David Clifford", "Sean O'Shea", "Seán O'Shea", "Con O'Callaghan",
    "Brian Fenton", "Cillian O'Connor", "Aidan O'Shea", "Paul Mannion",
    "Diarmuid Connolly", "James O'Donoghue",
}


def county_by_name(name: str) -> dict:
    for c in COUNTIES:
        if c["name"].lower() == name.lower() or c["short"].lower() == name.lower():
            return c
    raise KeyError(name)


class Player:
    def __init__(self, pid: int, team: int, number: int, role: str, first: str, surname: str, attrs: dict):
        self.pid = pid
        self.team = team
        self.number = number
        self.role = role
        self.first = first
        self.surname = surname
        self.short = f"{first[0]}. {surname}"
        self.attrs = attrs
        self.x = 0.0
        self.z = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.facing = 0.0
        self.has_ball = False
        self.steps = 0.0
        self.bounce_used = False
        self.stamina = 1.0
        self.sin_bin = 0.0
        self.in_bin = False
        self.sent_off = False
        self.on_pitch = number <= 15
        self.yellow = 0
        self.black = 0
        self.anim = "idle"
        self.solo_t = 0.0
        self.bounce_t = 0.0
        self.kick_t = 0.0
        self.jump_t = 0.0
        self.stumble_t = 0.0
        self.dive = 0.0
        self.protect = 0.0
        self.solo_lock = 0.0
        self.action_cd = 0.0
        self.blocking = 0.0
        self.skin = attrs.get("skin", 0)
        self.hair = attrs.get("hair", 0)
        self.think = 0.0
        self.order = None
        self.carry_t = 0.0

    @property
    def active(self) -> bool:
        return self.on_pitch and not self.in_bin and not self.sent_off

    @property
    def pace(self) -> float:
        return self.attrs["pace"]

    @property
    def kick(self) -> float:
        return self.attrs["kick"]


class TeamSide:
    def __init__(self, index: int, county: dict):
        self.index = index
        self.county = county
        self.name = county["name"]
        self.short = county["short"]
        self.jersey = county["jersey"]
        self.shorts = county["shorts"]
        self.socks = county["socks"]
        self.trim = county["trim"]
        self.goals = 0
        self.points = 0
        self.subs_used = 0
        self.two_pointers = 0
        self.wides = 0
        self.fouls = 0
        self.frees = 0
        self.tackles = 0
        self.marks = 0
        self.solos = 0
        self.shots = 0
        self.kickouts = 0
        self.kickouts_won = 0
        self.yellow = 0
        self.black = 0
        self.red = 0
        self.possession = 0.0
        self.players: list[Player] = []

    @property
    def total(self) -> int:
        return self.goals * 3 + self.points

    def scoreline(self) -> str:
        return f"{self.goals}-{self.points:02d}"


def _attrs(role: str, rng: random.Random) -> dict:
    base = {"pace": 0.72, "kick": 0.66, "catch": 0.66, "tackle": 0.62, "vision": 0.64}
    if role == "gk":
        base.update(pace=0.48, kick=0.74, catch=0.90, tackle=0.40)
    elif role in ("ff", "rff", "lff", "chf"):
        base.update(kick=0.86, pace=0.80, catch=0.76, vision=0.70)
    elif role in ("fb", "rcb", "lcb", "chb"):
        base.update(tackle=0.86, catch=0.72, pace=0.74)
    elif role in ("mf1", "mf2"):
        base.update(pace=0.86, vision=0.82, catch=0.78)
    elif role in ("rhb", "lhb", "rhf", "lhf"):
        base.update(pace=0.82, vision=0.72)
    out = {k: max(0.35, min(0.98, v + rng.uniform(-0.05, 0.07))) for k, v in base.items()}
    out["skin"] = rng.randrange(5)
    out["hair"] = rng.randrange(5)
    return out


def build_squad(team_index: int, county: dict, rng: random.Random, pid_start: int) -> list[Player]:
    used = set()
    players = []
    roles = list(ROLE_ORDER) + ["gk", "mf1", "chf", "fb", "rhf"]
    for i, role in enumerate(roles):
        for _ in range(40):
            first = rng.choice(FIRST)
            last = rng.choice(SURNAMES)
            full = f"{first} {last}"
            if full not in used and full not in BLOCK:
                used.add(full)
                break
        players.append(
            Player(pid_start + i, team_index, i + 1, role if i < 15 else role, first, last, _attrs(role if i < 15 else "mf1", rng))
        )
        if i >= 15:
            players[-1].role = "sub_gk" if i == 15 else "sub"
            players[-1].on_pitch = False
    # Starters keep formation roles. Bench 16 is a goalkeeper.
    for i, role in enumerate(ROLE_ORDER):
        players[i].role = role
        players[i].on_pitch = True
    return players


def make_team(index: int, county_name: str, seed: int) -> TeamSide:
    county = county_by_name(county_name)
    rng = random.Random(seed + index * 997)
    side = TeamSide(index, county)
    side.players = build_squad(index, county, rng, pid_start=index * 30)
    return side


def formation_of(role: str) -> tuple[float, float]:
    return FORMATION.get(role, (0.5, 0.5))
