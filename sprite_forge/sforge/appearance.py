"""Character appearance controls (v10.2): one table of features -> MakeHuman modifier weights, fitted assets and
colours.  Used by the text spec (key = value), Sprite Forge Studio's Appearance tab (sliders) and every builder
(sforge.mhchar for realistic MakeHuman characters).

Sliders are signed: 0 = the template's own shape, +1 = the most of a feature, -1 = the least (e.g. lips -1 thin,
+1 full).  Choices pick fitted CC0 assets from the MakeHuman library (sforge.mhlib)."""
from __future__ import annotations
from dataclasses import dataclass, field, fields
from .spec import parse_colour, HAIR_COLOURS, COLOURS

HAIR_STYLES = ["bald", "buzz", "short01", "short02", "short03", "short04", "long01", "ponytail01", "bob01", "bob02",
               "braid01", "afro01"]
HAIR_ALIASES = {"short": "short02", "crew": "short04", "crop": "short02", "messy": "short01", "fringe": "short03", "emo": "short03",
                "long": "long01", "ponytail": "ponytail01", "bob": "bob01", "braid": "braid01", "bun": "braid01",
                "afro": "afro01", "curly": "afro01", "none": "bald", "shaved": "buzz"}
FACIAL_HAIR = ["none", "stubble", "moustache", "goatee", "beard"]
BROW_STYLES = ["eyebrow%03d" % i for i in range(1, 13)]
EYE_COLOURS = ["brown", "brownlight", "green", "bluegreen", "blue", "lightblue", "deepblue", "grey", "ice"]
SKINS = ["young_caucasian_male", "young_caucasian_male2", "middleage_caucasian_male", "old_caucasian_male",
         "young_african_male", "middleage_african_male", "young_asian_male", "middleage_asian_male",
         "young_caucasian_female", "young_african_female", "young_asian_female"]

# key, kind, default, (min, max) or choices, label, group, [(target, side-pair?)...]
SLIDERS = [
    # body
    ("muscle_arms", "slider", 0.0, (-1, 1), "Arm muscle (biceps / triceps)", "Body",
     ["armslegs/{s}-upperarm-muscle", "armslegs/{s}-lowerarm-muscle"]),
    ("muscle_shoulders", "slider", 0.0, (-1, 1), "Shoulder muscle", "Body", ["armslegs/{s}-upperarm-shoulder-muscle"]),
    ("muscle_chest", "slider", 0.0, (-1, 1), "Chest (pectorals)", "Body", ["torso/torso-muscle-pectoral"]),
    ("muscle_back", "slider", 0.0, (-1, 1), "Back (lats)", "Body", ["torso/torso-muscle-dorsi", "torso/torso-vshape"]),
    ("muscle_legs", "slider", 0.0, (-1, 1), "Thigh muscle", "Body", ["armslegs/{s}-upperleg-muscle"]),
    ("muscle_calves", "slider", 0.0, (-1, 1), "Calf muscle", "Body", ["armslegs/{s}-lowerleg-muscle"]),
    ("shoulder_width", "slider", 0.0, (-1, 1), "Shoulder width", "Body", ["measure/measure-shoulder-dist"]),
    # face
    ("nose_size", "slider", 0.0, (-1, 1), "Nose size", "Face",
     ["nose/nose-scale-vert", "nose/nose-scale-horiz", "nose/nose-scale-depth", "nose/nose-volume"]),
    ("nose_width", "slider", 0.0, (-1, 1), "Nose width", "Face", ["nose/nose-width2", "nose/nose-nostrils-width"]),
    ("lips", "slider", 0.0, (-1, 1), "Lips (thin - full)", "Face",
     ["mouth/mouth-upperlip-volume", "mouth/mouth-lowerlip-volume"]),
    ("mouth_width", "slider", 0.0, (-1, 1), "Mouth width", "Face", ["mouth/mouth-scale-horiz"]),
    ("cheekbones", "slider", 0.0, (-1, 1), "Cheekbones", "Face", ["cheek/{s}-cheek-bones"]),
    ("cheeks", "slider", 0.0, (-1, 1), "Cheek fullness", "Face", ["cheek/{s}-cheek-volume"]),
    ("jaw", "slider", 0.0, (-1, 1), "Jaw width", "Face", ["chin/chin-width", "chin/chin-bones"]),
    ("chin", "slider", 0.0, (-1, 1), "Chin (receding - strong)", "Face", ["chin/chin-prominent"]),
    ("eye_size", "slider", 0.0, (-1, 1), "Eye size", "Face", ["eyes/{s}-eye-scale"]),
    ("ears", "slider", 0.0, (-1, 1), "Ear size", "Face", ["ears/{s}-ear-scale"]),
    ("brow_height", "slider", 0.0, (-1, 1), "Eyebrow height", "Face", [("eyebrows/eyebrows-trans-up", "eyebrows/eyebrows-trans-down")]),
    # hair and colour
    ("hair_style", "choice", "short02", HAIR_STYLES, "Hair style", "Hair", None),
    ("hair_colour", "colour", "#3b2614", None, "Hair colour", "Hair", None),
    ("hairline", "slider", 0.0, (0, 1), "Hairline (full - balding)", "Hair", None),
    ("facial_hair", "choice", "none", FACIAL_HAIR, "Facial hair", "Hair", None),
    ("facial_hair_colour", "colour", "", None, "Facial hair colour (blank = hair)", "Hair", None),
    ("brow_style", "choice", "eyebrow003", BROW_STYLES, "Eyebrow shape", "Hair", None),
    ("brow_thickness", "slider", 0.0, (-1, 1), "Eyebrows (thin - bushy)", "Hair", None),
    ("brow_colour", "colour", "", None, "Eyebrow colour (blank = hair)", "Hair", None),
    ("eye_colour", "choice", "brown", EYE_COLOURS, "Eye colour", "Skin & eyes", None),
    ("skin", "choice", "young_caucasian_male", SKINS, "Skin", "Skin & eyes", None),
    ("skin_tint", "colour", "", None, "Skin tint (blank = none)", "Skin & eyes", None),
]
KEYS = [s[0] for s in SLIDERS]
INFO = {s[0]: s for s in SLIDERS}
GROUPS = ["Body", "Face", "Hair", "Skin & eyes"]
SIZE_WORDS = {"tiny": -1.0, "small": -0.6, "thin": -0.6, "narrow": -0.6, "medium": 0.0, "normal": 0.0, "average": 0.0,
              "large": 0.6, "big": 0.6, "full": 0.6, "wide": 0.6, "huge": 1.0, "bushy": 0.8}


@dataclass
class Appearance:
    values: dict = field(default_factory=lambda: {s[0]: s[2] for s in SLIDERS})

    def __getattr__(self, k):
        if k in KEYS:
            return self.values[k]
        raise AttributeError(k)

    def set(self, k, v):
        kind, rng = INFO[k][1], INFO[k][3]
        if kind == "slider":
            if isinstance(v, str):
                s = v.strip().lower()
                v = SIZE_WORDS[s] if s in SIZE_WORDS else float(s)
            v = max(rng[0], min(rng[1], float(v)))
        elif kind == "choice":
            v = str(v).strip().lower()
            if k == "hair_style":
                v = HAIR_ALIASES.get(v, v)
            if k == "facial_hair" and v == "moustache_beard":
                v = "beard"
            if v not in rng:
                raise ValueError("%s: '%s' is not one of %s" % (k, v, ", ".join(rng)))
        else:
            v = str(v).strip()
        self.values[k] = v
        return self

    # ---- colours
    def rgb(self, k):
        v = self.values[k]
        if not v:
            if k in ("facial_hair_colour", "brow_colour"):
                return self.rgb("hair_colour")
            return None
        return parse_colour(v, HAIR_COLOURS if "hair" in k or "brow" in k else COLOURS, (0.23, 0.15, 0.08))

    # ---- MakeHuman modifier weights
    def target_weights(self, lib=None):
        """-> {target_name: weight >= 0} for every slider that is not 0"""
        out = {}
        for key, kind, _d, _r, _l, _g, tg in SLIDERS:
            if kind != "slider" or not tg:
                continue
            v = float(self.values[key])
            if abs(v) < 1e-6:
                continue
            for t in tg:
                if isinstance(t, tuple):                          # (positive target, negative target)
                    name = t[0] if v > 0 else t[1]
                    names = [name]
                else:
                    names = [(t + ("-incr" if v > 0 else "-decr")).replace("{s}", s) for s in ("l", "r")] if "{s}" in t \
                        else [t + ("-incr" if v > 0 else "-decr")]
                for n in names:
                    if lib is None or lib.has_target(n):
                        out[n] = out.get(n, 0.0) + abs(v)
        return out

    # ---- spec round trip
    @classmethod
    def from_spec(cls, sp):
        """CharacterSpec -> Appearance: new keys from spec.extra, plus the old spec words (hair_style, nose ...)"""
        ap = cls()
        old = {"hair_style": getattr(sp, "hair_style", None), "hair_colour": getattr(sp, "hair_colour", None),
               "eye_colour": getattr(sp, "eye_colour", None), "facial_hair": getattr(sp, "facial_hair", None),
               "nose_size": getattr(sp, "nose", None), "lips": getattr(sp, "mouth", None), "ears": getattr(sp, "ears", None)}
        for k, v in old.items():
            if v in (None, ""):
                continue
            try:
                if k == "eye_colour" and str(v).lower() not in EYE_COLOURS:
                    v = {"dark_brown": "brown", "hazel": "brownlight", "amber": "brownlight", "black": "brown",
                         "gray": "grey"}.get(str(v).lower(), "brown")
                if k == "facial_hair" and str(v).lower() == "moustache":
                    v = "moustache"
                ap.set(k, v)
            except (ValueError, KeyError):
                pass
        for k in KEYS:
            if k in sp.extra:
                ap.set(k, sp.extra[k])
        return ap

    def spec_lines(self, only_changed=True):
        lines = []
        for key, kind, d, *_ in SLIDERS:
            v = self.values[key]
            if only_changed and v == d:
                continue
            lines.append("%-18s = %s" % (key, ("%.2f" % v) if kind == "slider" else v))
        return lines

    def apply_to_spec(self, sp):
        for key, kind, d, *_ in SLIDERS:
            v = self.values[key]
            sp.extra[key] = ("%.2f" % v) if kind == "slider" else v
        return sp
