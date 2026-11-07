#!/usr/bin/env python3
"""Run the USB / EasySMX pad tests without installing Godot or the .NET SDK.

The browser edition's pad rules live in Web/Controllers.gd.  The block between
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
        raise RuntimeError("PURE START / PURE END markers missing from Web/Controllers.gd")
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
    gd = (ROOT / "Web" / "Controllers.gd").read_text(encoding="utf-8")
    py = translate_pure(gd)
    namespace: dict = {"_sqrt": math.sqrt}
    # Godot keycodes in the keyboard schemes are only data here; give them dummy values.
    for key in set(re.findall(r"\bKEY_[A-Z0-9_]+\b", gd)):
        namespace[key] = key
    exec(compile(py, "Web/Controllers.gd:PURE", "exec"), namespace)
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
    check("raw LT (b6) is close-control DRIBBLE",
          held(btns(6), empty, raw, False)["dribble"]
          and not held(btns(6), empty, raw, False)["sprint"])
    check("raw RT (b7) sprints", held(btns(7), empty, raw, False)["sprint"])
    check("raw Back (b8) is LONG BALL", held(btns(8), empty, raw, False)["lob"])
    check("raw L3 (b10) is DRIBBLE", held(btns(10), empty, raw, False)["dribble"])
    check("raw Start (b9) pauses", held(btns(9), empty, raw, False)["pause"])
    check("raw R3 (b11) changes camera", held(btns(11), empty, raw, False)["camera"])
    check("standard A = PASS", held(btns(0), empty, std, True)["pass"])
    check("standard Start (b6) pauses", held(btns(6), empty, std, True)["pause"])
    check("standard Back (b4) is LONG BALL", held(btns(4), empty, std, True)["lob"])
    check("standard L3 (b7) is DRIBBLE", held(btns(7), empty, std, True)["dribble"])
    check("analogue LT is DRIBBLE", held(btns(), axs(**{"4": 1.0}), std, True)["dribble"])
    check("analogue RT sprints", held(btns(), axs(**{"5": 1.0}), std, True)["sprint"])
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
    # The project enables ImplicitUsings, so System.IO.FileAccess is in scope and
    # an unqualified FileAccess is ambiguous with Godot.FileAccess under .NET 9.
    bare = []
    for f in (ROOT / "Scripts").rglob("*.cs"):
        code = re.sub(r"//[^\n]*", "", f.read_text(encoding="utf-8"))
        # Only a bare *usage* is ambiguous: FileAccess.Open / FileAccess.GetFileAsString.
        # "Godot FileAccess" in a string and the qualified Godot.FileAccess are fine.
        if re.search(r"(?<![.\w])FileAccess\s*\.", code):
            bare.append(f.relative_to(ROOT).as_posix())
    check("C# always qualifies Godot.FileAccess (System.IO clash)", not bare, str(bare))
    check("desktop has a CONTROLLER SETUP screen", "CONTROLLER SETUP" in gameapp and "SetBinding" in gameapp)
    check("browser loads SDL mappings at boot", "load_mappings(OS.get_name())" in boot)
    check("browser netplay uses the pad rules", "pad_ctl.move_of" in boot and "pad_ctl.held" in boot)
    check("browser remap uses device slots", "pads[slot]" in boot)
    check("menu is controllable with a pad + keyboard",
          "read_pad_menu" in boot and "menu_focus_step" in boot and "grab_focus" in boot)
    check("camera angles respond to the pad", 'get("camera", false)' in boot and "cam_mode" in boot)
    check("menu/camera input has a headless test",
          "test_input_camera.gd" in (ROOT / "Tools" / "run-gd-tests.sh").read_text())
    check("CAM buttons can be built in headless desktop tests",
          "func build_touch(force := false)" in boot
          and "build_touch(true)" in (ROOT / "Tests" / "gd" / "test_input_camera.gd").read_text())
    rig = (ROOT / "Scripts" / "Godot" / "ProceduralRig3D.gd").read_text(encoding="utf-8")
    net = (ROOT / "Web" / "NetClient.gd").read_text(encoding="utf-8")
    check("rig data still parses on Web builds without a glTF module",
          'ClassDB.class_exists("GLTFDocument")' in rig and "GLTFDocument.new()" not in rig)
    check("netplay script still parses on Web builds without a WebSocket module",
          'ClassDB.class_exists("WebSocketPeer")' in net and "WebSocketPeer.new()" not in net
          and "var ws: WebSocketPeer" not in net)
    check("Controllers.gd owns the pad rules (no fragile path extends)",
          "extends RefCounted" in controllers_gd and "PURE START" in controllers_gd
          and "func load_mappings" in controllers_gd and 'extends "res://' not in controllers_gd)
    check("web preset exports the DB",
          'include_filter="Data/input/*.txt"' in (ROOT / "Web" / "export_presets_web.cfg").read_text())
    check("desktop presets export the DB",
          'include_filter="Data/input/*.txt"' in (ROOT / "export_presets.cfg").read_text())

    section("Desktop gameplay / camera regressions")
    match_cs = (ROOT / "Scripts" / "Core" / "Match.cs").read_text(encoding="utf-8")
    game_app = (ROOT / "Scripts" / "Godot" / "GameApp.cs").read_text(encoding="utf-8")
    match_view = (ROOT / "Scripts" / "Godot" / "MatchView.cs").read_text(encoding="utf-8")
    world3d = (ROOT / "Scripts" / "Godot" / "World3D.cs").read_text(encoding="utf-8")
    hud_cs = (ROOT / "Scripts" / "Godot" / "Hud.cs").read_text(encoding="utf-8")
    workflow = (ROOT.parent / ".github" / "workflows" / "arena-fc-tests.yml").read_text(encoding="utf-8")
    check("owner PossessionLock does NOT release the ball every tick",
          "owner.PossessionLock > 0 ||" not in match_cs)
    check("the main menu seeds GUI focus",
          "Ui.FocusFirst(root)" in game_app and "Ui.FocusFirst(panel)" in game_app)
    check("WASD is rotated into camera space",
          "Cam.GlobalTransform.Basis" in match_view and "worldMove" in match_view)
    camera_plan = (ROOT / "Scripts" / "Core" / "CameraPlan.cs").read_text(encoding="utf-8")
    check("tactical camera is stable and the camera heading is damped",
          "new Vector3(0f, 0f, -1f)" in camera_plan
          and "f.LengthSquared() < 1e-6f" in world3d
          and "Mathf.Exp(-dt * 1.4f)" in world3d)
    check("five stable cameras incl. ball follow, shoulder and sideline",
          "ModeCount = 5" in camera_plan and "Shoulder" in camera_plan and "Sideline" in camera_plan
          and "case 2:" in camera_plan and "case 3:" in camera_plan and "case 4:" in camera_plan
          and "BroadcastPlan.Compute" in world3d)
    check("HUD hint advertises the pad camera button", "pad R3 camera" in hud_cs)
    check("C# core regression suite is wired into CI",
          (ROOT / "Tests" / "MatchCoreTests.cs").exists()
          and "MatchCoreTests.csproj" in workflow and "ArenaFC.sln" in workflow)
    ui_cs = (ROOT / "Scripts" / "Godot" / "Ui.cs").read_text(encoding="utf-8")
    nav_cs = (ROOT / "Scripts" / "Godot" / "PadMenuNavigator.cs").read_text(encoding="utf-8")
    check("menu Buttons are focusable (no mouse required)",
          "FocusMode = Control.FocusModeEnum.All" in ui_cs and "Ui.FocusFirst" in game_app)
    controls_cs = (ROOT / "Scripts" / "Godot" / "Controls.cs").read_text(encoding="utf-8")
    check("a pad navigator drives menu focus and activation",
          "ReadMenuPad" in nav_cs and "ButtonClicked" in nav_cs
          and "PadMenuNavigator" in game_app)
    check("menu accept is layout-independent (any face button)",
          "PadLayout.Button(buttons, i)" in controls_cs and "for (int i = 0; i <= 3; i++)" in controls_cs)
    check("opposition presses and tackles",
          "p.Pressing" in match_cs and "chaser3" in match_cs and "1.12f" in match_cs)
    check("slide tackle, shield and strength contest exist",
          "bool Slide" in match_cs and "bool Shield" in match_cs
          and "AttemptSlide" in match_cs and "between * .20f" in match_cs
          and "cmd.Slide" in controls_cs and "cmd.Shield" in controls_cs)
    check("auto-select keeps the controlled player near the ball",
          "ControlLock" in match_cs and "FindNearestHome(S.Ball.Pos, true)" in match_cs)
    check("fouls are rarer and now visible",
          "carrier.Action = \"foul\"" in match_cs and "FOUL · FREE KICK" in hud_cs
          and 'p.Action == "slide"' in world3d)
    check("player spacing avoids scrums",
          "1.05f - dd) * .60f" in match_cs and "State.Ball.Owner >= 0 && p.Index != State.Ball.Owner" in match_cs)
    rig_cs = (ROOT / "Scripts" / "Core" / "RigDefinition.cs").read_text(encoding="utf-8")
    gait_cs = (ROOT / "Scripts" / "Core" / "Gait.cs").read_text(encoding="utf-8")
    check("rig has visible hip/knee/ankle joints and shaped boots",
          "knee cap" in rig_cs and "toe box" in rig_cs and "RigMat.Detail" in rig_cs)
    check("gait is a shared pure-C# curve with forward thighs and bending knees",
          "Gait.Compute" in world3d and "float hipL = -(s * .66f" in gait_cs
          and "float kneeL = (.14f" in gait_cs and 'Set(rig, "LFoot"' in world3d
          and any(k in (ROOT / "Tests" / "MatchCoreTests.csproj").read_text(encoding="utf-8")
                  for k in ("Gait.cs", "Scripts/Core/**/*.cs")))
    browser = (ROOT / "Web" / "BrowserBoot.gd").read_text(encoding="utf-8")
    check("browser edition mirrors the corrected gait signs",
          "var hip_l: float = -(s * 0.66" in browser and "sin(ph + 0.40)" in browser)

    section("06.11.2026 camera / pad / gameplay fixes")
    match_core = (ROOT / "Scripts" / "Core" / "Match.cs").read_text(encoding="utf-8")
    packet = (ROOT / "Scripts" / "Core" / "Net" / "Packet.cs").read_text(encoding="utf-8")
    controls = (ROOT / "Scripts" / "Godot" / "Controls.cs").read_text(encoding="utf-8")
    pad_nav = (ROOT / "Scripts" / "Godot" / "PadMenuNavigator.cs").read_text(encoding="utf-8")
    ui = (ROOT / "Scripts" / "Godot" / "Ui.cs").read_text(encoding="utf-8")
    gait = (ROOT / "Scripts" / "Core" / "Gait.cs").read_text(encoding="utf-8")
    rig_factory = (ROOT / "Scripts" / "Godot" / "RigFactory.cs").read_text(encoding="utf-8")
    match_view = (ROOT / "Scripts" / "Godot" / "MatchView.cs").read_text(encoding="utf-8")
    hud = (ROOT / "Scripts" / "Godot" / "Hud.cs").read_text(encoding="utf-8")
    controllers_gd = (ROOT / "Web" / "Controllers.gd").read_text(encoding="utf-8")
    browser = (ROOT / "Web" / "BrowserBoot.gd").read_text(encoding="utf-8")
    check("human one-shot actions are consumed every fixed tick",
          "private void HumanActions" in match_core and "if (human) HumanActions(p, pc);" in match_core)
    check("released stick only auto-presses while defending",
          "p.Target = p.Pos;" in match_core and "Active stick input always wins" in match_core
          and "humanDefending && S.ControlLock <= 0f" in match_core)
    check("short pass, long ball, dribble and stronger sprint exist",
          "FindBestPassTarget(p, true, true)" in match_core and "bool Dribble" in match_core
          and "1.42f" in match_core and "owner.Dribbling" in match_core)
    check("dribble survives the v2 wire format",
          "Sd = c.Shield || c.Dribble" in packet and "Shield = Sd, Dribble = Sd" in packet)
    check("one-shot pad edges are buffered across accumulator frames",
          "MergePending(cmd)" in match_view and "Engine.CurrentTick != before" in match_view)
    check("HUD and MatchView share one InputHub",
          "Hud = new Hud { Input = Input }" in match_view)
    check("ball, owner and controlled player are separately marked",
          "BallRing" in match_view and "OwnerArrow" in match_view
          and "_possession" in hud and "BALL · LOOSE" in hud)
    check("menu START activates on the first press and focus is actionable",
          "if (eAccept && seeded != null) Activate(seeded);" in pad_nav
          and "c is BaseButton || c is Slider" in ui)
    check("menu accept and back no longer collide on R3",
          "PadLayout.Button(buttons, known ? 4 : 8)) back = true" in controls
          and 'PadLayout.Button(buttons, 8)' not in controls)
    check("camera button has an accidental-stick-click debounce",
          "_cameraHold > .12f" in controls)
    check("gait is smoothed and has out-of-plane joints",
          "Gait.Lerp" in world3d and "HipYawL" in gait
          and "SmoothPose" in rig_factory and "ActionEnvelope" in world3d)
    check("browser edition mirrors lob / dribble / long ball",
          'out["lob"]' in controllers_gd and 'out["dribble"]' in controllers_gd
          and 'cmd["sd"]' in browser and "Long ball." in browser)
    check("camera plan keeps a fixed sideline orientation",
          "fixed world orientation, never spins with facing" in camera_plan
          and "ClampPitch" in camera_plan)

    section("06.11.2026 second pass — latched taps, dead-zone camera, tracking")
    controls = (ROOT / "Scripts" / "Godot" / "Controls.cs").read_text(encoding="utf-8")
    pad_nav = (ROOT / "Scripts" / "Godot" / "PadMenuNavigator.cs").read_text(encoding="utf-8")
    camera_plan = (ROOT / "Scripts" / "Core" / "CameraPlan.cs").read_text(encoding="utf-8")
    world3d = (ROOT / "Scripts" / "Godot" / "World3D.cs").read_text(encoding="utf-8")
    match_core = (ROOT / "Scripts" / "Core" / "Match.cs").read_text(encoding="utf-8")
    gait = (ROOT / "Scripts" / "Core" / "Gait.cs").read_text(encoding="utf-8")
    match_view = (ROOT / "Scripts" / "Godot" / "MatchView.cs").read_text(encoding="utf-8")
    hud = (ROOT / "Scripts" / "Godot" / "Hud.cs").read_text(encoding="utf-8")
    check("quick joypad taps are event-latched",
          "PushJoyButton" in controls and "_pendingJoyPress" in controls
          and "InputEventJoypadButton" in pad_nav and "SetProcessInput(true)" in pad_nav
          and "PushJoyButton" in match_view)
    check("SELECT/Back activates on the main menu",
          "TryGoBack" in pad_nav and "eBack && seeded != null" in pad_nav
          and 'h["lob"]' in controls)
    check("camera holds a dead-zone focus instead of drifting",
          "AdvanceFocus" in camera_plan and "FocusDeadzone" in camera_plan
          and "BroadcastPlan.AdvanceFocus" in world3d and "_focus" in world3d)
    check("billboarded possession / pressure nameplates",
          "ControlName" in match_view and "OwnerName" in match_view
          and "BallName" in match_view and "PressureRing" in match_view
          and '"billboard"' in match_view)
    check("contextual HUD shows the actions that matter",
          "_actions" in hud and "CLOSE CONTROL" in hud and "pad R3 camera" in hud)
    check("gentle stick enters close control and short pass prefers a nearby man",
          "assistedCloseControl" in match_core and "moveMag < .60f" in match_core
          and "MathF.Max(0f, 12f - d)" in match_core)
    check("tackle / slide visibly lunges into range",
          "lungeDir" in match_core and "p.Target = carrier.Pos" in match_core
          and "p.Action == \"tackle\" || p.Action == \"slide\"" in match_core)
    check("players desynchronise and track the ball",
          "InitialPhase" in gait and "LookYaw" in gait and "HeadYaw" in gait
          and "Gait.InitialPhase(idx)" in match_core and "Gait.LookYaw" in world3d)
    browser = (ROOT / "Web" / "BrowserBoot.gd").read_text(encoding="utf-8")
    check("browser keeps per-player phase and ball-aware head yaw",
          "look_yaw" in browser and 'p["phase"]' in browser)

    section("Optional syntax parsers")
    try:
        import gdtoolkit  # noqa: F401
        gdparse = Path(sys.executable).parent / "gdparse"
        files = ["Web/Controllers.gd", "Web/BrowserBoot.gd", "Tests/gd/test_pads.gd"]
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
        for f in ["Scripts/Core/Input/PadLayout.cs", "Scripts/Core/CameraPlan.cs",
                  "Scripts/Core/Gait.cs", "Scripts/Core/Match.cs",
                  "Scripts/Godot/Controls.cs", "Scripts/Godot/GameApp.cs",
                  "Scripts/Godot/PadMenuNavigator.cs", "Scripts/Godot/MatchView.cs",
                  "Scripts/Godot/Hud.cs", "Scripts/Godot/World3D.cs",
                  "Tests/Program.cs", "Tests/MatchCoreTests.cs"]:
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
