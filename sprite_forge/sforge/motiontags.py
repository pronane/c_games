"""Motion categories, tags and training rights for imported moves (v11.40).

Imported moves used to land in catch-all categories ("Mocap", "Imported", "Recorded",
"Library") or in a game's own names ("Kick", "Pass", "Dribble"), so the library could not say
what a move *is*, and a learned model could not be trained on the right moves.  This files
every move into Sprite Forge's own action categories and adds structured tags:

    category  one of CATEGORIES (the categories the built-in motions use)
    tags      action     pass / lofted / cross / shot / free_kick / penalty / clearance / header /
                         first_touch / dribble / throw_in / tackle / block / save / dive /
                         celebration / juggle / skill / signal / run / walk / jog / sprint /
                         backpedal / sidestep / cut / stop / idle / recovery / fall / get_up
              gait       walk / jog / run / sprint            (moving loops, from speed or name)
              direction  forward / back / side                (moving loops)
              style      e.g. neutral, heavyset, crouched     (when the source names one)
              source     cmu / skillcorner / soccertrack / 100style / veo / rohr / mixamo / ...
              capture    studio / match_video / procedural / keyframe / recorded

and says whether its licence allows training machine-learning models on it (`ml_training`:
yes / no / unknown), which Learned Motion Matching and any motion generator must respect.

    from sforge import motiontags as MT
    MT.retag(rec)                       # files a catch-all record, adds rec["tags"] (in place)
    MT.training_allowed(rec["licence"]) # -> "yes" / "no" / "unknown"
"""
from __future__ import annotations

import math
import re

# the action categories the built-in library uses (sforge.motions + field sports + officials)
CATEGORIES = ("Locomotion", "Ball handling", "Kicking", "Ball", "Defence", "Contact", "Goalkeeper", "Celebration",
              "Skill", "Official", "Hurling", "Rugby", "Aussie rules", "Fighter", "Kart", "NPC")
CATCH_ALL = ("", "Mocap", "Imported", "Recorded", "Library", None)
# game-side names (Arena FC's clip categories, capture tools) -> library categories
GAME_TO_CATEGORY = {"Kick": "Kicking", "Pass": "Kicking", "Shoot": "Kicking", "FirstTouch": "Ball", "Header": "Ball",
                    "Dribble": "Ball handling", "Carry": "Ball handling", "Tackle": "Defence", "Block": "Defence",
                    "KeeperDive": "Goalkeeper", "Keeper": "Goalkeeper", "Save": "Goalkeeper", "Celebrate": "Celebration",
                    "Cut": "Locomotion", "Recovery": "Locomotion", "Locomotion": "Locomotion", "Skill": "Skill"}
# action -> category
ACTION_CATEGORY = {
    **{a: "Kicking" for a in ("pass", "lofted", "cross", "shot", "free_kick", "penalty", "clearance", "volley", "kick")},
    **{a: "Ball" for a in ("header", "first_touch", "trap", "control")},
    **{a: "Ball handling" for a in ("dribble", "carry", "throw_in")},
    **{a: "Defence" for a in ("tackle", "block", "ball_win", "jockey")},
    **{a: "Goalkeeper" for a in ("save", "dive", "keeper")},
    "celebration": "Celebration", "juggle": "Skill", "skill": "Skill", "signal": "Official",
    **{a: "Contact" for a in ("fall", "get_up", "hit")},
    "jump": "Locomotion", "crouch": "Locomotion",
    **{a: "Locomotion" for a in ("run", "walk", "jog", "sprint", "backpedal", "sidestep", "cut", "stop", "idle",
                                 "recovery", "turn")},
}
# words in a name / description -> action (first match wins; order matters: specific before general)
ACTION_WORDS = [
    ("free_kick", r"free.?kick"), ("penalty", r"penalt"), ("lofted", r"lofted|high.?pass|long.?ball"),
    ("cross", r"\bcross"), ("clearance", r"clear(ance)?\b"), ("header", r"header|heading"),
    ("first_touch", r"first.?touch|receive|reception|trap\b|control"), ("throw_in", r"throw.?in"),
    ("shot", r"\bshot|shoot|power.?kick|strike"), ("pass", r"\bpass|side.?foot"),
    ("save", r"\bsave|goalkeeper|keeper|\bgk\b"), ("dive", r"\bdive"),
    ("tackle", r"tackle|ball.?win|win.?ball|defending|lunge"), ("block", r"\bblock"),
    ("celebration", r"celebrat"), ("juggle", r"juggl|keepy"), ("signal", r"\bcard\b|whistle|\bflag|signal"),
    ("dribble", r"dribbl|\bcarry"), ("backpedal", r"back.?(run|walk|pedal)|backward"),
    ("sidestep", r"side.?(step|run|walk)|shuffle|strafe"), ("cut", r"\bcut\b|change.?direction"),
    ("stop", r"\bstop"), ("recovery", r"recover"), ("sprint", r"sprint"), ("jog", r"\bjog"),
    ("run", r"\brun"), ("walk", r"\bwalk"), ("idle", r"\bidle"), ("get_up", r"get.?up"), ("fall", r"\bfall"),
    ("kick", r"\bkick"), ("jump", r"\bjump|\bleap"), ("crouch", r"crouch"), ("punch", r"punch|uppercut"),
    ("throw", r"\bthrow"), ("celebration", r"victory|taunt"), ("hit", r"\bhit\b|hit_"),
]
SOURCES = [  # (tag, pattern over source / name / licence author)
    ("cmu", r"\bcmu\b|cgspeed|carnegie"), ("skillcorner", r"skillcorner|\bsc_"), ("soccertrack", r"soccertrack|\bst_"),
    ("100style", r"100style|\bss_"), ("veo", r"\bveo\b|own-footage|\bvo_"), ("rohr", r"rohr|\brr_"),
    ("mixamo", r"mixamo"), ("meshy", r"meshy"), ("rokoko", r"rokoko"),
]
CAPTURE = {"cmu": "studio", "100style": "studio", "rohr": "studio", "mixamo": "studio", "rokoko": "studio",
           "skillcorner": "match_video", "soccertrack": "match_video", "veo": "match_video"}
STYLES = ("neutral", "rushed", "bigsteps", "proud", "heavyset", "bentknees", "crouched")


def action_of(text):
    t = (text or "").lower().replace("-", "_")
    for a, pat in ACTION_WORDS:
        if re.search(pat, t.replace("_", " ")):
            return a
    return None


def gait_of(speed):
    if speed is None:
        return None
    return "walk" if speed < 1.4 else "jog" if speed < 3.0 else "run" if speed < 5.5 else "sprint"


def retag(rec, refile="catch_all"):
    """add rec["tags"] and file the record into CATEGORIES (in place).  -> rec
    refile="catch_all" (default, what the import paths use) re-files only "Mocap"/"Imported"/"Recorded"/
    "Library"; refile=True also maps game-side names ("Kick", "Dribble"...); False only tags.
    A record already in one of CATEGORIES keeps it; one whose action can't be told and isn't a loop
    keeps its catch-all and gets tags["needs_category"]."""
    imp = rec.get("import") or {}
    name, desc = str(rec.get("name", "")), str(rec.get("desc", ""))
    hay = " ".join([name, desc, str(imp.get("sub", "")), str(rec.get("source", "")), str(imp.get("from_take", ""))])
    action = imp.get("sub") if imp.get("sub") in ACTION_CATEGORY else None
    action = action or action_of(name) or action_of(hay)  # the name first: "block" whose desc says "block a pass"
    if action == "carry":
        action = "dribble"
    tags = dict(rec.get("tags") or {})
    if action:
        tags["action"] = action
    vel = imp.get("root_velocity")
    if rec.get("loop") and isinstance(vel, (list, tuple)) and len(vel) == 2:
        vx, vz = float(vel[0]), float(vel[1])
        tags.setdefault("gait", gait_of(math.hypot(vx, vz)))
        tags.setdefault("direction", "side" if abs(vx) > abs(vz) else "back" if vz < 0 else "forward")
    elif action in ("backpedal",):
        tags.setdefault("direction", "back")
    elif action in ("sidestep",):
        tags.setdefault("direction", "side")
    elif action in ("walk", "jog", "run", "sprint"):
        tags.setdefault("gait", action)
    for st in STYLES:
        if re.search(r"(^|[_ ])%s($|[_ ])" % st, name.lower() + " " + desc.lower()):
            tags.setdefault("style", st); break
    lic = rec.get("licence")
    author = str(lic.get("author", "")) if isinstance(lic, dict) else str(lic or "")
    src_hay = " ".join([str(rec.get("source", "")), name, author]).lower()
    for tag, pat in SOURCES:
        if re.search(pat, src_hay):
            tags.setdefault("source", tag)
            tags.setdefault("capture", CAPTURE.get(tag, "studio")); break
    if "capture" not in tags:
        origin = str(rec.get("origin", ""))
        tags["capture"] = "recorded" if rec.get("category") == "Recorded" else (
            "procedural" if origin in ("builtin", "procedural", "") and not imp else "keyframe" if not imp else "studio")
    rec["tags"] = {k: v for k, v in tags.items() if v}
    cat = rec.get("category")
    if cat in CATEGORIES or not refile or (refile == "catch_all" and cat not in CATCH_ALL):
        return rec
    new = GAME_TO_CATEGORY.get(cat) if cat not in CATCH_ALL else None
    if action and (new is None or cat in ("Kick", "Pass")):
        new = ACTION_CATEGORY.get(action, new)
    if new is None and cat in CATCH_ALL and rec.get("loop"):
        new = "Locomotion"
    if new:
        rec.setdefault("import", {})["category_was"] = cat
        rec["category"] = new
    else:
        rec["tags"]["needs_category"] = True
    return rec


# --------------------------------------------------------------------------- training rights
TRAINING = ("yes", "no", "unknown")
_TRAIN_YES = re.compile(r"^(CC0|CC-BY|MIT|Apache|BSD|Unlicense|LicenseRef-owner)", re.I)  # after the NO check
_TRAIN_NO = re.compile(r"(^|-)(NC|ND)(-|$)|Mixamo|NonCommercial|NoDerivatives", re.I)


def training_allowed(lic):
    """may machine-learning models be trained on this asset?  An explicit `ml_training` in the licence
    record wins; otherwise it is read from the licence: CC0 / CC-BY / MIT / Apache / BSD / your own
    footage -> yes; non-commercial, no-derivatives or Mixamo (Adobe forbids training) -> no; anything
    else (store EULAs, free packs whose terms are silent) -> unknown, which training leaves out."""
    if isinstance(lic, str):  # older records keep only an SPDX id
        lic = {"spdx": lic}
    lic = lic or {}
    v = lic.get("ml_training")
    if v in TRAINING:
        return v
    spdx = str(lic.get("spdx") or "")
    text = " ".join(str(lic.get(k) or "") for k in ("custom_text", "author", "notes"))
    if _TRAIN_NO.search(spdx) or re.search(r"mixamo|non.?commercial", text, re.I):
        return "no"
    if _TRAIN_YES.match(spdx):
        return "yes"
    return "unknown"


def training_set(records):
    """split records -> (allowed, excluded with reason)"""
    ok, out = [], []
    for r in records:
        v = training_allowed(r.get("licence"))
        (ok if v == "yes" else out).append(r if v == "yes" else (r, "ml_training = %s" % v))
    return ok, out
