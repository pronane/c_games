"""racerkit.spec - read a plain key=value character description and turn it into a
complete set of drawing parameters (colours, proportions, features) for spec_draw.

Every key is optional; unknown keys are kept and ignored.  `ethnicity` only picks
default skin / hair / eye colours and hair texture - any explicit key wins.
"""
import re

NAMED = {
    # hair
    "black": (28, 24, 26), "jet black": (16, 14, 18), "dark brown": (60, 38, 26), "brown": (96, 60, 36),
    "chestnut": (120, 66, 34), "light brown": (150, 105, 66), "auburn": (140, 52, 30), "red": (178, 60, 28),
    "ginger": (204, 96, 40), "strawberry blonde": (222, 160, 110), "blonde": (232, 196, 120),
    "platinum": (240, 232, 205), "grey": (160, 160, 165), "gray": (160, 160, 165), "silver": (200, 202, 210),
    "white": (240, 240, 240), "pink": (255, 120, 180), "blue": (60, 110, 230), "green": (60, 170, 90),
    "purple": (130, 70, 190), "teal": (20, 150, 160), "orange": (250, 140, 30), "yellow": (250, 215, 50),
    "navy": (30, 40, 90), "maroon": (110, 25, 40), "beige": (205, 185, 160), "cream": (240, 230, 205),
    "lilac": (190, 160, 230), "mint": (160, 230, 200), "khaki": (170, 160, 110), "denim": (70, 100, 150),
    "hazel": (130, 100, 50), "amber": (190, 130, 40), "dark": (40, 34, 30),
}
EYES = {"blue": (70, 130, 210), "light blue": (120, 175, 230), "grey": (130, 145, 160), "gray": (130, 145, 160),
        "green": (80, 150, 90), "hazel": (140, 110, 55), "brown": (100, 60, 30), "dark brown": (60, 36, 20),
        "black": (35, 25, 20), "amber": (190, 130, 40), "violet": (140, 90, 200)}
SKIN = {"very fair": (255, 226, 210), "fair": (250, 214, 192), "pale": (250, 220, 205), "light": (240, 200, 170),
        "medium": (220, 170, 130), "olive": (200, 160, 110), "tan": (196, 145, 100), "brown": (160, 108, 70),
        "dark brown": (118, 76, 48), "dark": (96, 62, 40), "deep": (74, 48, 32), "rosy": (250, 205, 190)}
ETHNIC = {   # skin, hair, eyes, hair texture (only defaults)
    "irish": ("fair", "auburn", "blue", "straight"), "scottish": ("fair", "ginger", "blue", "straight"),
    "nordic": ("very fair", "blonde", "light blue", "straight"), "scandinavian": ("very fair", "blonde", "light blue", "straight"),
    "european": ("light", "brown", "blue", "straight"), "white": ("light", "brown", "blue", "straight"),
    "caucasian": ("light", "brown", "blue", "straight"), "mediterranean": ("olive", "dark brown", "brown", "wavy"),
    "italian": ("olive", "dark brown", "brown", "wavy"), "spanish": ("olive", "dark brown", "brown", "wavy"),
    "hispanic": ("tan", "dark brown", "brown", "wavy"), "latino": ("tan", "dark brown", "brown", "wavy"),
    "latina": ("tan", "dark brown", "brown", "wavy"), "middle eastern": ("olive", "black", "brown", "wavy"),
    "arab": ("olive", "black", "brown", "wavy"), "persian": ("olive", "black", "brown", "wavy"),
    "south asian": ("brown", "black", "dark brown", "straight"), "indian": ("brown", "black", "dark brown", "straight"),
    "pakistani": ("brown", "black", "dark brown", "straight"), "east asian": ("light", "black", "dark brown", "straight"),
    "chinese": ("light", "black", "dark brown", "straight"), "japanese": ("light", "black", "dark brown", "straight"),
    "korean": ("light", "black", "dark brown", "straight"), "southeast asian": ("tan", "black", "dark brown", "straight"),
    "filipino": ("tan", "black", "dark brown", "straight"), "african": ("dark", "black", "dark brown", "coily"),
    "black": ("dark brown", "black", "dark brown", "coily"), "caribbean": ("dark brown", "black", "dark brown", "coily"),
    "mixed": ("medium", "dark brown", "brown", "curly"), "pacific islander": ("brown", "black", "dark brown", "wavy"),
    "indigenous": ("tan", "black", "dark brown", "straight"),
}


def parse_color(v, table=NAMED, default=(128, 128, 128)):
    if v is None:
        return default
    v = v.strip().lower()
    if v in table:
        return table[v]
    if v in NAMED:
        return NAMED[v]
    m = re.match(r"^#?([0-9a-f]{6})$", v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    nums = re.findall(r"\d+", v)
    if len(nums) >= 3:
        return tuple(max(0, min(255, int(n))) for n in nums[:3])
    for k in sorted(table, key=len, reverse=True):     # "light brown-ish" -> "light brown"
        if k in v:
            return table[k]
    return default


def read_spec(path):
    d = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", ";", "[")) or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip().lower().replace(" ", "_").replace("colour", "color")] = v.strip()
    return d


def _num(v, default):
    try:
        return float(re.findall(r"[-+]?\d*\.?\d+", v)[0])
    except Exception:
        return default


def _pick(v, options, default):
    v = (v or "").lower()
    for o in options:
        if o in v:
            return o
    return default


def resolve(d):
    """spec dict -> drawing parameters (all keys present)"""
    eth = (d.get("ethnicity") or "").lower()
    e = None
    for k in sorted(ETHNIC, key=len, reverse=True):
        if k in eth:
            e = ETHNIC[k]
            break
    e = e or ("light", "brown", "brown", "straight")
    P = {}
    P["name"] = d.get("name", "New Racer")
    age = _pick(d.get("age"), ["baby", "toddler", "child", "kid", "teen", "adult", "elder", "old"], "adult")
    age = {"toddler": "baby", "kid": "child", "old": "elder"}.get(age, age)
    if "age" in d and re.search(r"\d", d["age"]):
        n = _num(d["age"], 30)
        age = "baby" if n < 3 else "child" if n < 12 else "teen" if n < 18 else "elder" if n >= 65 else "adult"
    P["age"] = age
    P["skin"] = parse_color(d.get("complexion") or d.get("skin") or e[0], SKIN, SKIN.get(e[0]))
    P["hair_color"] = parse_color(d.get("hair_color") or e[1], NAMED, NAMED.get(e[1]))
    if age == "elder" and "hair_color" not in d:
        P["hair_color"] = NAMED["silver"]
    P["eye_color"] = parse_color(d.get("eye_color") or e[2], EYES, EYES.get(e[2], (90, 60, 30)))
    tex = _pick(d.get("hair_texture"), ["straight", "wavy", "curly", "coily"], e[3])
    style = _pick(d.get("hair_style") or d.get("hair"), ["afro", "bald", "buzz", "bun", "ponytail", "pigtails", "bob",
                                                          "long", "short", "curly", "spiky", "towel", "mohawk", "wisps"],
                  "wisps" if age == "baby" else ("curly" if tex in ("curly", "coily") else "short"))
    P["hair_style"] = style
    P["hair_texture"] = tex
    # body: height (cm) and weight (kg) or words
    hdef = {"baby": 80, "child": 125, "teen": 165, "adult": 172, "elder": 168}[age]
    hv = d.get("height", "")
    height = _num(hv, hdef) if re.search(r"\d", hv) else {"short": hdef * 0.9, "tiny": hdef * 0.8, "average": hdef,
                                                           "tall": hdef * 1.1, "very tall": hdef * 1.18}.get(hv.lower(), hdef)
    if 1.0 < height < 2.6:
        height *= 100          # metres
    elif 4 < height < 8 and "'" in hv:
        ft = re.findall(r"\d+", hv)
        height = int(ft[0]) * 30.48 + (int(ft[1]) * 2.54 if len(ft) > 1 else 0)
    P["height_cm"] = max(50, min(230, height))
    bmi_def = {"baby": 16.5, "child": 16.5, "teen": 20, "adult": 23, "elder": 25}[age]
    wv = d.get("weight", "")
    if re.search(r"\d", wv):
        kg = _num(wv, 70) * (0.4536 if "lb" in wv.lower() else 1)
        bmi = kg / (P["height_cm"] / 100) ** 2
    else:
        bmi = bmi_def * {"light": 0.85, "slim": 0.85, "thin": 0.8, "medium": 1, "average": 1, "heavy": 1.25,
                         "stocky": 1.18, "chubby": 1.25, "large": 1.3}.get(wv.lower(), 1.0)
    build = _pick(d.get("build") or d.get("size"), ["skinny", "slim", "petite", "average", "athletic", "muscular", "stocky",
                                                     "chubby", "round", "large", "big", "small"], "average")
    bmul = {"skinny": 0.82, "slim": 0.9, "petite": 0.88, "small": 0.9, "average": 1, "athletic": 1.05, "muscular": 1.15,
            "stocky": 1.15, "chubby": 1.2, "round": 1.25, "large": 1.22, "big": 1.2}[build]
    P["width"] = max(0.75, min(1.5, (bmi / bmi_def) ** 0.6 * bmul))
    P["belly"] = max(0.0, min(1.0, (bmi / bmi_def - 1.05) * 2.2 + (0.4 if build in ("chubby", "round") else 0)))
    P["shoulders"] = 1.12 if build in ("athletic", "muscular") else 1.0
    P["build"] = build
    sz = lambda key, opts, dflt: _pick(d.get(key), opts, dflt)
    P["eye_size"] = {"small": 0.8, "medium": 1.0, "large": 1.2, "big": 1.2}[sz("eye_size", ["small", "medium", "large", "big"], "medium")]
    if age == "baby":
        P["eye_size"] *= 1.25
    P["eye_shape"] = sz("eye_shape", ["round", "almond", "hooded", "monolid"], "round")
    P["nose"] = sz("nose", ["button", "small", "snub", "wide", "broad", "large", "big", "long", "pointy", "hooked", "roman", "medium"],
                   "button" if age in ("baby", "child") else "medium")
    P["ears"] = sz("ears", ["small", "large", "big", "pointy", "sticking out", "protruding", "medium"], "medium")
    P["mouth"] = sz("mouth", ["small", "wide", "big", "medium"], "small" if age == "baby" else "medium")
    P["lips"] = sz("lips", ["thin", "full", "medium"], "medium")
    P["lip_color"] = parse_color(d.get("lip_color"), NAMED, None) if d.get("lip_color") else None
    P["hands"] = {"small": 0.8, "medium": 1.0, "large": 1.2, "big": 1.2}[sz("hands", ["small", "medium", "large", "big"], "medium")]
    P["feet"] = {"small": 0.8, "medium": 1.0, "large": 1.25, "big": 1.25}[sz("feet", ["small", "medium", "large", "big"], "medium")]
    P["face_shape"] = sz("face_shape", ["round", "oval", "long", "square", "heart"], "round" if age in ("baby", "child") else "oval")
    P["freckles"] = (d.get("freckles", "no").lower() in ("yes", "true", "1", "lots", "some"))
    P["blush"] = d.get("blush", "yes" if age in ("baby", "child") else "light").lower()
    P["glasses"] = sz("glasses", ["round", "square", "none", "no"], "none")
    if P["glasses"] == "no":
        P["glasses"] = "none"
    P["glasses_color"] = parse_color(d.get("glasses_color"), NAMED, (30, 30, 34))
    P["beard"] = sz("beard", ["full", "stubble", "goatee", "moustache", "mustache", "none", "no"], "none")
    P["brows"] = sz("eyebrows", ["thin", "thick", "bushy", "medium"], "thin" if age == "baby" else "medium")
    P["top"] = sz("top", ["hoodie", "jumper", "sweater", "t-shirt", "tshirt", "shirt", "dress", "jacket", "onesie", "vest"], "t-shirt")
    P["top_color"] = parse_color(d.get("top_color") or d.get("clothes_color") or d.get("shirt_color"), NAMED, (230, 70, 80))
    P["top_pattern"] = sz("top_pattern", ["stripes", "spots", "dots", "plain", "none"], "plain")
    P["pattern_color"] = parse_color(d.get("pattern_color"), NAMED, (255, 255, 255))
    P["trousers_color"] = parse_color(d.get("trousers_color") or d.get("pants_color") or d.get("legs_color"), NAMED, (60, 80, 140))
    P["shoes_color"] = parse_color(d.get("shoes_color"), NAMED, (240, 240, 240))
    P["hat"] = sz("hat", ["cap", "beanie", "crown", "bow", "headband", "none", "no"], "none")
    P["hat_color"] = parse_color(d.get("hat_color"), NAMED, (230, 40, 60))
    P["bib"] = d.get("bib", "no").lower() in ("yes", "true", "1")
    P["bib_color"] = parse_color(d.get("bib_color"), NAMED, (250, 240, 230))
    P["expression"] = sz("expression", ["happy", "cheeky", "serious", "sleepy", "grumpy", "neutral", "smile"], "smile")
    return P
