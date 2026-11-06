// Arena FC - USB / EasySMX gamepad support, platform-independent part.
//
// This file deliberately has NO Godot dependency: the headless CoreTests project
// compiles it (Tests/CoreTests.csproj globs ../Scripts/Core/**/*.cs).  The Godot
// facing adapter is Scripts/Godot/Controls.cs; the browser edition mirrors these
// rules in Web/Controllers.gd.  Keep the constants in both places in sync --
// Tools/test_pads.py asserts that they agree.
//
// Why this exists: the desktop build used to read only device 0 through Godot's
// standard JoyButton enums, so a generic USB pad (and an EasySMX pad in D-input
// / "PC" mode) showed up as an unmapped joystick and did nothing.  The bundled
// Data/input/gamecontrollerdb.txt was never loaded either.  Now we:
//   1. feed the SDL mapping database (plus built-in EasySMX/USB fallbacks) to
//      Godot at boot, so known pads get a standard layout;
//   2. discover every connected pad instead of assuming device 0;
//   3. read unmapped pads with the common EasySMX D-mode raw layout
//      (b0=Y b1=B b2=A b3=X b4=LB b5=RB b6=LT b7=RT b8=Back b9=Start ...),
//      handling hat-as-buttons, hat-as-axes and trigger buttons/axes;
//   4. let the player remap any button, saved per pad name.

using System;
using System.Collections.Generic;

namespace ArenaFC.Core.Input
{
    public struct PadVector
    {
        public float X, Y;
        public PadVector(float x, float y) { X = x; Y = y; }
        public float Length { get { return (float)Math.Sqrt(X * X + Y * Y); } }
        public PadVector Normalized()
        {
            float l = Length;
            return l > 1e-6f ? new PadVector(X / l, Y / l) : new PadVector(0f, 0f);
        }
    }

    public static class PadLayout
    {
        public const float Deadzone = 0.25f;
        public const string DbPath = "res://Data/input/gamecontrollerdb.txt";
        public const string SavePath = "user://pads.json";

        public static readonly string[] Actions = { "pass", "through", "shoot", "tackle", "switch", "sprint" };

        // Godot JoyButton order for a pad with an SDL mapping (Xbox / XInput).
        public static readonly Dictionary<string, int> Standard = new Dictionary<string, int>
        {
            { "pass", 0 }, { "through", 3 }, { "shoot", 2 }, { "tackle", 1 }, { "switch", 9 }, { "sprint", 10 }
        };

        // Raw button order used by EasySMX in D-input/PC mode and most cheap USB pads.
        // This is the fix: the old web RAW table assumed the standard A,B,X,Y order.
        public static readonly Dictionary<string, int> Raw = new Dictionary<string, int>
        {
            { "pass", 2 }, { "through", 0 }, { "shoot", 3 }, { "tackle", 1 }, { "switch", 4 }, { "sprint", 5 }
        };

        public static readonly Dictionary<string, int> SystemStandard = new Dictionary<string, int>
        {
            { "pause", 6 }, { "camera", 8 }
        };
        public static readonly Dictionary<string, int> SystemRaw = new Dictionary<string, int>
        {
            // Raw b10 is L3 (close control); b11 is R3 (camera).
            { "pause", 9 }, { "camera", 11 }
        };

        public static readonly Dictionary<string, int> DpadStandard = new Dictionary<string, int>
        {
            { "up", 11 }, { "down", 12 }, { "left", 13 }, { "right", 14 }
        };
        public static readonly Dictionary<string, int> DpadRaw = new Dictionary<string, int>
        {
            { "up", 12 }, { "down", 13 }, { "left", 14 }, { "right", 15 }
        };

        public static readonly int[] HatAxes = { 6, 7 };
        public static readonly int[] TriggerAxes = { 4, 5 };
        public static readonly int[] TriggerButtons = { 6, 7 };
        public static readonly int[] StickAxes = { 0, 1 };

        public static readonly string[] EasySmxTokens = { "easysmx", "easy smx", "esm-", "esm_" };
        public static readonly string[] GenericTokens =
            { "usb", "generic", "gamepad", "controller", "joystick", "adapter", "shanwan", "szmy", "esm" };

        // Always available, even if the .txt database is missing from an export.
        // Copied verbatim from Data/input/gamecontrollerdb.txt (SDL 2.0.16 format).
        public static readonly string[] Builtin =
        {
            "03000000bc2000000091000000000000,EasySMX Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Windows,",
            "03000000c11100000191000011010000,EasySMX,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Linux,",
            "03000000242f00009100000000010000,EasySMX ESM-9101,a:b0,b:b1,back:b6,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b8,leftshoulder:b4,leftstick:b9,lefttrigger:a2,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b10,righttrigger:a5,rightx:a3,righty:a4,start:b7,x:b2,y:b3,platform:Linux,",
            "030000000b0400003065000000000000,USB Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a5,start:b9,x:b3,y:b0,platform:Windows,",
            "03000000300f00000701000000000000,USB Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a3,righty:a2,start:b9,x:b3,y:b0,platform:Windows,",
            "030000006b1400000203000000000000,USB Controller,a:b0,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b12,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b2,y:b3,platform:Windows,"
        };

        // ---- SDL mapping database ---------------------------------------------------------------

        public static string NormalizePlatform(string platform)
        {
            string p = (platform ?? "").Trim().ToLowerInvariant();
            if (p == "mac os x" || p == "macos" || p == "osx" || p == "darwin" || p == "mac") return "macos";
            if (p == "windows" || p == "win32" || p == "win64" || p == "win") return "windows";
            if (p == "linux" || p == "linuxbsd" || p == "x11" || p == "xorg") return "linux";
            if (p == "android") return "android";
            if (p == "ios") return "ios";
            if (p == "web" || p == "html5") return "web";
            return p;
        }

        /// <summary>The platform: tag of an SDL line, or "" when the line is platform agnostic.</summary>
        public static string MappingPlatform(string line)
        {
            string[] parts = (line ?? "").Split(',');
            for (int i = 0; i < parts.Length; i++)
            {
                string part = parts[i].Trim().ToLowerInvariant();
                if (part.StartsWith("platform:", StringComparison.Ordinal))
                    return NormalizePlatform(part.Substring(9));
            }
            return "";
        }

        public static bool PlatformMatches(string line, string platform)
        {
            string tag = MappingPlatform(line);
            return tag.Length == 0 || tag == NormalizePlatform(platform);
        }

        public static bool IsValidMapping(string line)
        {
            if (string.IsNullOrEmpty(line)) return false;
            int comma = line.IndexOf(',');
            if (comma < 0) return false;
            string guid = line.Substring(0, comma).Trim();
            if (guid.Length != 32) return false;
            foreach (char c in guid)
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
            // A mapping needs at least a GUID, a name and one binding.
            return line.Split(',').Length >= 4;
        }

        /// <summary>Usable SDL mapping lines for this OS (comments, blanks and other platforms dropped).</summary>
        public static List<string> ParseSdlDatabase(string text, string platform)
        {
            var result = new List<string>();
            if (string.IsNullOrEmpty(text)) return result;
            string[] lines = text.Replace("\r\n", "\n").Split('\n');
            foreach (string raw in lines)
            {
                string line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                if (!IsValidMapping(line)) continue;
                if (!PlatformMatches(line, platform)) continue;
                result.Add(line);
            }
            return result;
        }

        public static List<string> BuiltinMappings(string platform)
        {
            var result = new List<string>();
            // Browser Gamepad API IDs do not carry an OS tag: keep every built-in
            // line on Web so EasySMX / USB fallbacks are always registered there.
            bool web = NormalizePlatform(platform) == "web";
            foreach (string line in Builtin)
                if (web || PlatformMatches(line, platform)) result.Add(line);
            return result;
        }

        // ---- Pad identification ------------------------------------------------------------------

        public static bool HasToken(string name, string[] tokens)
        {
            string low = (name ?? "").ToLowerInvariant();
            foreach (string t in tokens)
                if (low.IndexOf(t, StringComparison.Ordinal) >= 0) return true;
            return false;
        }

        public static bool IsEasySMX(string name) { return HasToken(name, EasySmxTokens); }
        public static bool IsGenericUsb(string name) { return HasToken(name, GenericTokens); }

        public static string PadKind(string name, bool known)
        {
            if (IsEasySMX(name)) return known ? "EasySMX (XInput)" : "EasySMX (USB / D-input)";
            if (IsGenericUsb(name)) return known ? "USB gamepad" : "USB controller (raw)";
            return known ? "Standard gamepad" : "Unknown joystick (raw)";
        }

        /// <summary>Remapped bindings win; otherwise standard for mapped pads, EasySMX raw for the rest.</summary>
        public static Dictionary<string, int> Bindings(string name, bool known,
                                                       Dictionary<string, Dictionary<string, int>> saved)
        {
            if (!string.IsNullOrEmpty(name) && saved != null && saved.ContainsKey(name))
            {
                Dictionary<string, int>? b = saved[name];
                // Keep the null check as a real branch so nullable flow analysis knows
                // b is non-null before ContainsKey / the copy constructor.
                if (b != null)
                {
                    bool complete = true;
                    foreach (string a in Actions)
                        if (!b.ContainsKey(a)) { complete = false; break; }
                    if (complete) return new Dictionary<string, int>(b);
                }
            }
            return new Dictionary<string, int>(known ? Standard : Raw);
        }

        // ---- Raw state -> commands ---------------------------------------------------------------

        public static float Axis(float[] axes, int i)
        {
            return axes != null && i >= 0 && i < axes.Length ? axes[i] : 0f;
        }

        public static bool Button(bool[] buttons, int i)
        {
            return buttons != null && i >= 0 && i < buttons.Length && buttons[i];
        }

        public static PadVector Stick(float x, float y, float deadzone)
        {
            float l = (float)Math.Sqrt(x * x + y * y);
            if (l < deadzone) return new PadVector(0f, 0f);
            float scale = Math.Min(1f, (l - deadzone) / (1f - deadzone)) / l;
            return new PadVector(x * scale, y * scale);
        }

        public static PadVector Move(bool[] buttons, float[] axes, bool known)
        {
            PadVector m = Stick(Axis(axes, StickAxes[0]), Axis(axes, StickAxes[1]), Deadzone);
            // Godot's desktop drivers expose a hat as DPAD_* (11-14); the browser
            // Gamepad API exposes it as raw buttons 12-15.  Those ranges overlap,
            // so choose ONE table - OR-ing both would make button 12 mean up AND down.
            Dictionary<string, int> dpad = DpadStandard;
            if (!known)
            {
                bool rawHat = false;
                foreach (int idx in DpadRaw.Values)
                    if (Button(buttons, idx)) { rawHat = true; break; }
                if (rawHat) dpad = DpadRaw;
            }
            float dx = 0f, dy = 0f;
            if (Button(buttons, dpad["left"])) dx -= 1f;
            if (Button(buttons, dpad["right"])) dx += 1f;
            if (Button(buttons, dpad["up"])) dy -= 1f;
            if (Button(buttons, dpad["down"])) dy += 1f;
            if (!known)
            {
                // Some adapters report the hat as a pair of axes instead of buttons.
                float hx = Axis(axes, HatAxes[0]), hy = Axis(axes, HatAxes[1]);
                if (Math.Abs(hx) > 0.5f) dx += Math.Sign(hx);
                if (Math.Abs(hy) > 0.5f) dy += Math.Sign(hy);
            }
            var v = new PadVector(m.X + dx, m.Y + dy);
            return v.Length > 1f ? v.Normalized() : v;
        }

        public static Dictionary<string, bool> Held(bool[] buttons, float[] axes,
                                                     Dictionary<string, int> binds, bool known)
        {
            var result = new Dictionary<string, bool>();
            foreach (string a in Actions)
                result[a] = Button(buttons, binds != null && binds.ContainsKey(a) ? binds[a] : -1);
            Dictionary<string, int> sys = known ? SystemStandard : SystemRaw;
            result["pause"] = Button(buttons, sys["pause"]);
            result["camera"] = Button(buttons, sys["camera"]);
            // Back/Select is a dedicated long ball / cross; LT or L3 is close
            // control.  RT / RB stays sprint.  Previously BOTH analogue triggers
            // meant sprint, so there was no reachable dribble button at all.
            result["lob"] = Button(buttons, known ? 4 : 8);
            result["dribble"] = Axis(axes, TriggerAxes[0]) > 0.5f
                                || Button(buttons, known ? 7 : 10);
            bool sprint = result["sprint"];
            if (Axis(axes, TriggerAxes[1]) > 0.5f) sprint = true;
            if (!known)
            {
                if (Button(buttons, TriggerButtons[0])) result["dribble"] = true;
                if (Button(buttons, TriggerButtons[1])) sprint = true;
            }
            result["sprint"] = sprint;
            return result;
        }

        /// <summary>In one-player mode every pad drives P1; in 2P mode pad n drives player n.</summary>
        public static int[] DevicesFor(int[] connected, bool twoPlayer, int playerIndex)
        {
            if (connected == null || connected.Length == 0) return new int[0];
            if (!twoPlayer) return (int[])connected.Clone();
            if (playerIndex >= 0 && playerIndex < connected.Length) return new int[] { connected[playerIndex] };
            return new int[0];
        }
    }
}
