#!/usr/bin/env python3
"""Run the USB / EasySMX pad tests without installing Godot or the .NET SDK.

The browser edition's pad rules live in Web/PadSupport.gd.  The block between
PURE START / PURE END is deliberately written in a small side-effect-free subset
of GDScript; this script translates that *exact shipped source* to Python and
executes it, then checks it against:

  * Scripts/Core/Input/PadLayout.cs  - the desktop C# twin (constants must agree)
  * Data/input/gamecontrollerdb.txt   - the SDL database that is now loaded at boot
  * the Godot/C# adapters             - static wiring checks

If gdtoolkit / tree-sitter are installed it also parses the changed GDScript and
C# files for syntax errors.  Real engine tests are Tests/gd/test_pads.gd and the
PadLayout section of Tests/Program.cs (run via Tools/build.py --check).

    python3 Tools/test_pads.py
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


# --------------------------------------------------------------------------------------
# GDScript -> Python translation of the PURE block.  Only the constructs used by that
# block are handled; anything unexpected is reported instead of silently ignored.
# --------------------------------------------------------------------------------------
def translate_pure(gd: str) -> str:
    m = re.search(r"# ---- PURE START ----(.*?)# ---- PURE END ----", gd, re.S)
    if m is None:
        raise RuntimeError("PURE START / PURE END markers missing from Web/PadSupport.gd")
    src = m.group(1)
    out: list[str] = []
    assign = re.compile(r":=|(?<![=!<>])=(?!=)")
    func_def = re.compile(r"^(\s*)static func\s+(\w+)\s*\((.*?)\)\s*(?:->\s*[\w, \[\]]+)?\s*:\s*$")
    decl = re.compile(r"^(\s*)(var|const)\s+(.*)$")

    for raw in src.split("\n"):
        line = raw.replace("\t", "    ")
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        fm = func_def.match(line)
        if fm:
            params = re.sub(r"\b(\w+)\s*:\s*[A-Za-z_]\w*", r"\1", fm.group(3))
            out.append(f"{indent}def {fm.group(2)}({params}):")
            continue
        dm = decl.match(line)
        if dm:
            body = dm.group(3)
            am = assign.search(body)
            if am is None:
                raise RuntimeError(f"untranslated declaration: {raw!r}")
            left, right = body[: am.start()].strip(), body[am.end():].strip()
            name = left.split(":")[0].strip()
            out.append(f"{indent}{name} = {right}")
            continue
        out.append(line)

    text = "\n".join(out)
    # String / container helpers that differ between GDScript and Python.
    repl = [
        (r'\.split\(("[^"]*"), false\)', r".split(\1)"),
        (r"\.size\(\)", ".__len__()"),
        (r"\.length\(\)", ".__len__()"),
        (r"\.duplicate\(\)", ".copy()"),
        (r"\.strip_edges\(\)", ".strip()"),
        (r"\.to_lower\(\)", ".lower()"),
        (r"\.begins_with\(", ".startswith("),
        (r"\bsqrt\(", "_sqrt("),
        (r"\btrue\b", "True"),
        (r"\bfalse\b", "False"),
        (r"\bnull\b", "None"),
    ]
    for pattern, replacement in repl:
        text = re.sub(pattern, replacement, text)
    return text


def load_pure() -> dict:
    gd = (ROOT / "Web" / "PadSupport.gd").read_text(encoding="utf-8")
    py = translate_pure(gd)
    namespace: dict = {"_sqrt": math.sqrt}
    exec(compile(py, "Web/PadSupport.gd:PURE", "exec"), namespace)
    return namespace


# --------------------------------------------------------------------------------------
# Parsing the two source files for cross-language constant checks.
# --------------------------------------------------------------------------------------
def cs_dict(name: str, cs: str) -> dict:
    m = re.search(r"public static readonly Dictionary<string, int> " + name +
                  r"\s*=\s*new Dictionary<string, int>\s*\{(.*?)\};", cs, re.S)
    if m is None:
        raise RuntimeError(f"C# dictionary {name} not found")
    return {k: int(v) for k, v in re.findall(r'\{\s*"(\w+)"\s*,\s*(-?\d+)\s*\}', m.group(1))}


def cs_array(name: str, cs: str) -> list:
    m = re.search(r"public static readonly string\[\] " + name + r"\s*=\s*\{(.*?)\};", cs, re.S)
    if m is None:
        raise RuntimeError(f"C# array {name} not found")
    return re.findall(r'"([^"]*)"', m.group(1))


def cs_int_array(name: str, cs: str) -> list:
    m = re.search(r"public static readonly int\[\] " + name + r"\s*=\s*\{(.*?)\};", cs, re.S)
    if m is None:
        raise RuntimeError(f"C# array {name} not found")
    return [int(x) for x in re.findall(r"-?\d+", m.group(1))]


def cs_builtin(cs: str) -> list:
    m = re.search(r"public static readonly string\[\] Builtin\s*=\s*\{(.*?)\n\s*\};", cs, re.S)
    if m is None:
        raise RuntimeError("C# Builtin array not found")
    return re.findall(r'"([0-9a-f]{32},[^"]*)"', m.group(1))


# --------------------------------------------------------------------------------------
def main() -> int:
    p = load_pure()
    cs = (ROOT / "Scripts" / "Core" / "Input" / "PadLayout.cs").read_text(encoding="utf-8")
    db = (ROOT / "Data" / "input" / "gamecontrollerdb.txt").read_text(encoding="utf-8")

    section("GDScript pure block executes")
    check("PURE block translated and executed", callable(p["parse_db"]))
    check("deadzone agrees with C#", abs(p["DEADZONE"] - 0.25) < 1e-9 and "Deadzone = 0.25f" in cs)
    check("actions list agrees with C#", p["ACTIONS"] == cs_array("Actions", cs))
    for gd_name, cs_name in [("STANDARD", "Standard"), ("RAW", "Raw"),
                             ("SYSTEM_STANDARD", "SystemStandard"), ("SYSTEM_RAW", "SystemRaw"),
                             ("DPAD_STANDARD", "DpadStandard"), ("DPAD_RAW", "DpadRaw")]:
        check(f"{gd_name} == PadLayout.{cs_name}", p[gd_name] == cs_dict(cs_name, cs),
              f"gd={p[gd_name]} cs={cs_dict(cs_name, cs)}")
    for gd_name, cs_name in [("HAT_AXES", "HatAxes"), ("TRIGGER_AXES", "TriggerAxes"),
                             ("TRIGGER_BUTTONS", "TriggerButtons"), ("STICK_AXES", "StickAxes")]:
        check(f"{gd_name} == PadLayout.{cs_name}", p[gd_name] == cs_int_array(cs_name, cs))
    check("EasySMX name tokens agree", p["EASYSMX_TOKENS"] == cs_array("EasySmxTokens", cs))
    check("generic USB name tokens agree", p["GENERIC_TOKENS"] == cs_array("GenericTokens", cs))
    check("built-in fallback mappings agree", p["BUILTIN"] == cs_builtin(cs),
          f"gd={len(p['BUILTIN'])} cs={len(cs_builtin(cs))}")

    section("SDL database parsing (shipped GDScript functions)")
    sample = "\n".join(["# comment", "", p["BUILTIN"][0], p["BUILTIN"][3], p["BUILTIN"][1],
                        "not a mapping", "badguid,a:b0,platform:Windows,"])
    win = p["parse_db"](sample, "Windows")
    lin = p["parse_db"](sample, "Linux")
    check("comments / blanks / bad GUIDs skipped", len(win) == 2, f"got {len(win)}")
    check("Windows filter", all(p["platform_matches"](l, "Windows") for l in win))
    check("Linux filter", len(lin) == 1, f"got {len(lin)}")
    check("Mac OS X normalises to macOS", p["normalize_platform"]("Mac OS X") == "macos")
    check("X11 normalises to linux", p["normalize_platform"]("X11") == "linux")
    check("built-in Windows fallbacks = 4", len(p["builtin_mappings"]("Windows")) == 4)
    check("built-in Linux fallbacks = 2", len(p["builtin_mappings"]("Linux")) == 2)
    check("Web keeps every built-in fallback (no OS tag in browser IDs)",
          len(p["builtin_mappings"]("Web")) == len(p["BUILTIN"]))
    check("Windows built-ins include EasySMX",
          any("EasySMX" in l for l in p["builtin_mappings"]("Windows")))
    check("Linux built-ins include ESM-9101",
          any("ESM-9101" in l for l in p["builtin_mappings"]("Linux")))

    real_win = p["parse_db"](db, "Windows")
    real_lin = p["parse_db"](db, "Linux")
    check("shipped DB parses: Windows", len(real_win) > 800, f"{len(real_win)} lines")
    check("shipped DB parses: Linux", len(real_lin) > 700, f"{len(real_lin)} lines")
    check("shipped DB has Windows EasySMX", any("EasySMX Controller" in l for l in real_win))
    check("shipped DB has Linux EasySMX", any("EasySMX" in l for l in real_lin))
    check("shipped DB has generic USB controllers", any("USB Controller" in l for l in real_win))
    check("all built-in lines come from the shipped DB", all(l in db for l in p["BUILTIN"]))
    check("EasySMX GUIDs are 32-char hex",
          all(re.match(r"^[0-9a-f]{32},", l) for l in p["BUILTIN"]))
    check("no cross-platform leakage",
          all("platform:Linux" not in l for l in real_win) and
          all("platform:Windows" not in l for l in real_lin))

    section("EasySMX / USB raw-layout behaviour (shipped GDScript functions)")
    raw = p["binds_for_name"]("EasySMX Controller (D-mode)", False, {})
    std = p["binds_for_name"]("Xbox Wireless Controller", True, {})
    check("raw order is Y B A X / LB / RB",
          [raw[a] for a in p["ACTIONS"]] == [2, 0, 3, 1, 4, 5], str(raw))
    check("standard order is Godot JoyButton",
          [std[a] for a in p["ACTIONS"]] == [0, 3, 2, 1, 9, 10], str(std))
    check("EasySMX name detected", p["is_easysmx"]("EasySMX ESM-9101"))
    check("USB name detected", p["is_generic_usb"]("USB Controller"))
    check("Xbox is not EasySMX", not p["is_easysmx"]("Xbox One S Controller"))
    check("pad kind reports D-input vs XInput",
          "D-input" in p["pad_kind"]("EasySMX", False) and "XInput" in p["pad_kind"]("EasySMX", True))
    saved = {"My USB pad": {a: i for i, a in enumerate(p["ACTIONS"], start=7)}}
    check("saved per-pad remap wins", p["binds_for_name"]("My USB pad", False, saved)["pass"] == 7)
    check("incomplete remap falls back",
          p["binds_for_name"]("Other", False, {"Other": {"pass": 7}})["through"] == 0)

    def btns(*pressed: int) -> list:
        b = [False] * 21
        for i in pressed:
            b[i] = True
        return b

    def axs(**changes: float) -> list:
        a = [0.0] * 10
        for k, v in changes.items():
            a[int(k)] = float(v)
        return a

    held = p["held_from"]
    move = p["move_xy"]
    empty = axs()
    check("stick drift inside deadzone ignored", p["stick_xy"](0.1, 0.1, 0.25) == [0.0, 0.0])
    check("full deflection reaches 1.0", p["stick_xy"](1.0, 0.0, 0.25)[0] > 0.99)
    check("raw b2 = PASS", held(btns(2), empty, raw, False)["pass"]
          and not held(btns(2), empty, raw, False)["shoot"])
    check("raw b3 = SHOOT", held(btns(3), empty, raw, False)["shoot"])
    check("raw b0 = THROUGH", held(btns(0), empty, raw, False)["through"])
    check("raw b1 = TACKLE", held(btns(1), empty, raw, False)["tackle"])
    check("raw b4 = SWITCH", held(btns(4), empty, raw, False)["switch"])
    check("raw LT (b6) sprints", held(btns(6), empty, raw, False)["sprint"])
    check("raw Start (b9) pauses", held(btns(9), empty, raw, False)["pause"])
    check("raw R3 (b10) changes camera", held(btns(10), empty, raw, False)["camera"])
    check("standard A = PASS", held(btns(0), empty, std, True)["pass"])
    check("standard Start (b6) pauses", held(btns(6), empty, std, True)["pause"])
    check("analogue trigger sprints", held(btns(), axs(**{"4": 1.0}), std, True)["sprint"])
    check("raw hat button 12 moves up (no 11-14 conflict)", move(btns(12), empty, False, 0.25)[1] < -0.9)
    check("raw hat button 15 moves right", move(btns(15), empty, False, 0.25)[0] > 0.9)
    check("Godot hat button 11 works on an unmapped pad", move(btns(11), empty, False, 0.25)[1] < -0.9)
    check("hat axis 6 moves left", move(btns(), axs(**{"6": -1.0}), False, 0.25)[0] < -0.9)
    check("hat axis 7 moves down", move(btns(), axs(**{"7": 1.0}), False, 0.25)[1] > 0.9)
    check("mapped pads ignore raw hat button 15",
          move(btns(15), empty, True, 0.25) == [0.0, 0.0])
    check("mapped pad d-pad up (11) works", move(btns(11), empty, True, 0.25)[1] < -0.9)
    check("1P: all pads drive P1", len(p["devices_for"]([0, 3, 7], False, 0)) == 3)
    check("2P: P2 gets the 2nd pad", p["devices_for"]([0, 3, 7], True, 1) == [3])
    check("no pads -> no devices", p["devices_for"]([], False, 0) == []
          and p["devices_for"]([0], True, 1) == [])

    section("Runtime wiring (static checks)")
    controls = (ROOT / "Scripts" / "Godot" / "Controls.cs").read_text(encoding="utf-8")
    gameapp = (ROOT / "Scripts" / "Godot" / "GameApp.cs").read_text(encoding="utf-8")
    boot = (ROOT / "Web" / "BrowserBoot.gd").read_text(encoding="utf-8")
    controllers_gd = (ROOT / "Web" / "Controllers.gd").read_text(encoding="utf-8")
    check("desktop loads SDL mappings", "Input.AddJoyMapping" in controls and "EnsureMappings" in controls)
    check("desktop discovers pads", "GetConnectedJoypads" in controls)
    check("desktop uses the shared pure logic", "PadLayout.Move" in controls and "PadLayout.Held" in controls)
    check("desktop no longer hard-codes device 0", "IsJoyButtonPressed(0," not in controls)
    check("desktop has a CONTROLLER SETUP screen", "CONTROLLER SETUP" in gameapp and "SetBinding" in gameapp)
    check("browser loads SDL mappings at boot", "load_mappings(OS.get_name())" in boot)
    check("browser netplay uses PadSupport", "pad_ctl.move_of" in boot and "pad_ctl.held" in boot)
    check("browser remap uses device slots", "pads[slot]" in boot)
    check("Controllers.gd extends PadSupport.gd", 'extends "res://Web/PadSupport.gd"' in controllers_gd)
    check("web preset exports the DB",
          'include_filter="Data/input/*.txt"' in (ROOT / "Web" / "export_presets_web.cfg").read_text())
    check("desktop presets export the DB",
          'include_filter="Data/input/*.txt"' in (ROOT / "export_presets.cfg").read_text())

    section("Optional syntax parsers")
    try:
        import gdtoolkit  # noqa: F401
        gdparse = Path(sys.executable).parent / "gdparse"
        files = ["Web/PadSupport.gd", "Web/Controllers.gd", "Web/BrowserBoot.gd", "Tests/gd/test_pads.gd"]
        bad = []
        for f in files:
            r = subprocess.run([str(gdparse), str(ROOT / f)], capture_output=True, text=True)
            if r.returncode != 0:
                bad.append((f, (r.stderr or r.stdout).strip().split("\n")[0]))
        check("gdtoolkit parses changed GDScript files", not bad, str(bad))
    except (ImportError, FileNotFoundError):
        print("  SKIP  gdtoolkit not installed")
    try:
        import tree_sitter, tree_sitter_c_sharp  # noqa: F401
        from tree_sitter import Language, Parser
        lang = Language(tree_sitter_c_sharp.language())
        parser = Parser(lang)
        bad = []
        for f in ["Scripts/Core/Input/PadLayout.cs", "Scripts/Godot/Controls.cs",
                  "Scripts/Godot/GameApp.cs", "Tests/Program.cs"]:
            tree = parser.parse((ROOT / f).read_bytes())
            if tree.root_node.has_error:
                bad.append(f)
        check("tree-sitter parses changed C# files", not bad, str(bad))
    except (ImportError, AttributeError):
        print("  SKIP  tree-sitter-c-sharp not installed")

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
