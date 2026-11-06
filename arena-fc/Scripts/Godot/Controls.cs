// Arena FC - one input layer for keyboard, mouse, gamepad and touch.
// Produces the same PlayerCommand on every platform.
//
// USB / EasySMX support (see Scripts/Core/Input/PadLayout.cs and Web/Controllers.gd):
//   * the bundled SDL gamecontrollerdb.txt is actually loaded now, plus built-in
//     EasySMX / generic-USB mappings so an export without the .txt still works;
//   * every connected pad is discovered (not just device 0);
//   * pads Godot cannot map are read raw with the EasySMX D-input button order;
//   * buttons can be remapped per pad name and are saved to user://pads.json.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using ArenaFC.Core;
using ArenaFC.Core.Input;
using Godot;

namespace ArenaFC.GodotGame;

public sealed class InputHub
{
    // Set by the on-screen touch controls.
    public Vector2 TouchMove;
    public bool TouchSprint, TouchPass, TouchThrough, TouchTackle, TouchSwitch, TouchShoot,
               TouchLob, TouchDribble;
    public bool TouchEnabled;

    private bool _pShoot, _pPass, _pThrough, _pTackle, _pSlide, _pSwitch, _pPause, _pCamera, _pLob;
    private float _charge, _cameraHold;
    public float Charge => _charge;
    public bool PausePressed { get; private set; }
    public bool CameraPressed { get; private set; }

    private readonly int _playerIndex;
    private readonly bool _twoPlayer;

    public InputHub(int playerIndex = 0, bool twoPlayer = false)
    {
        _playerIndex = playerIndex;
        _twoPlayer = twoPlayer;
        EnsureMappings();
        LoadBindings();
    }

    private static bool Edge(bool now, ref bool prev)
    {
        bool r = now && !prev;
        prev = now;
        return r;
    }

    // ---- SDL mapping database + saved per-pad bindings -----------------------------------------

    private static int _mappingsLoaded = -1;
    private static Dictionary<string, Dictionary<string, int>> _saved = new();

    public static int MappingsLoaded => _mappingsLoaded;

    /// <summary>Load once, before any pad is polled. Built-ins cover EasySMX/generic USB even if the DB is absent.</summary>
    public static void EnsureMappings()
    {
        if (_mappingsLoaded >= 0) return;
        _mappingsLoaded = 0;
        string platform = OS.GetName();
        foreach (string line in PadLayout.BuiltinMappings(platform))
            if (TryAddMapping(line)) _mappingsLoaded++;
        // ArenaFC.csproj enables ImplicitUsings, which also imports System.IO.FileAccess.
        // Always qualify Godot.FileAccess here or .NET 9 reports CS0104.
        try
        {
            foreach (string line in PadLayout.ParseSdlDatabase(Godot.FileAccess.GetFileAsString(PadLayout.DbPath), platform))
                if (TryAddMapping(line)) _mappingsLoaded++;
        }
        catch (Exception) { /* built-ins above still cover EasySMX and generic USB pads */ }
    }

    private static bool TryAddMapping(string line)
    {
        try { Input.AddJoyMapping(line, true); return true; }
        catch (Exception) { return false; }
    }

    public static void LoadBindings()
    {
        try
        {
            string text = Godot.FileAccess.GetFileAsString(PadLayout.SavePath);
            if (string.IsNullOrEmpty(text)) return;
            var d = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, int>>>(text);
            if (d != null) _saved = d;
        }
        catch (Exception) { /* corrupt/old pads.json: fall back to the default layouts */ }
    }

    public static void SaveBindings()
    {
        try
        {
            using var f = Godot.FileAccess.Open(PadLayout.SavePath, Godot.FileAccess.ModeFlags.Write);
            f?.StoreString(JsonSerializer.Serialize(_saved));
        }
        catch (Exception) { }
    }

    public static void SetBinding(string padName, string action, int button)
    {
        if (string.IsNullOrEmpty(padName)) return;
        if (!_saved.ContainsKey(padName)) _saved[padName] = new Dictionary<string, int>();
        _saved[padName][action] = button;
    }

    public static void ResetBindings()
    {
        _saved.Clear();
        SaveBindings();
    }

    /// <summary>Text for the CONTROLLER SETUP screen: connected pads, kind, layout and bindings.</summary>
    public static string DescribePads()
    {
        EnsureMappings();
        var lines = new List<string>();
        int[] connected = ConnectedDevices();
        lines.Add($"SDL mappings loaded: {_mappingsLoaded}   |   pads connected: {connected.Length}");
        if (connected.Length == 0)
        {
            lines.Add("No gamepad detected. Plug in a USB / EasySMX pad and press any button once " +
                      "(Windows needs the pad to be awake before Godot can see it).");
            return string.Join("\n", lines);
        }
        foreach (int dev in connected)
        {
            string name = Input.GetJoyName(dev);
            bool known = Input.IsJoyKnown(dev);
            var b = PadLayout.Bindings(name, known, _saved);
            lines.Add($"Pad {dev + 1}: {name}   [{PadLayout.PadKind(name, known)}]");
            lines.Add($"   pass={b["pass"]}  through={b["through"]}  shoot={b["shoot"]}  " +
                      $"tackle={b["tackle"]}  switch={b["switch"]}  sprint={b["sprint"]}");
        }
        lines.Add("Left stick / D-pad moves. Every connected pad drives player 1. " +
                  "Use REMAP if a button is in the wrong place; bindings are saved per pad name.");
        lines.Add("Back/Select = long ball  ·  LT/L3 = close-control dribble + shield  ·  R3 = camera");
        return string.Join("\n", lines);
    }

    // ---- Raw pad state -------------------------------------------------------------------------

    private static bool[] ReadButtons(int dev)
    {
        var b = new bool[21];
        for (int i = 0; i < b.Length; i++) b[i] = Input.IsJoyButtonPressed(dev, (JoyButton)i);
        return b;
    }

    private static float[] ReadAxes(int dev)
    {
        var a = new float[10];
        for (int i = 0; i < a.Length; i++) a[i] = Input.GetJoyAxis(dev, (JoyAxis)i);
        return a;
    }

    /// <summary>Device ids, independent of whether Godot's binding returns int[] or Array&lt;int&gt;.</summary>
    public static int[] ConnectedDevices()
    {
        var pads = Input.GetConnectedJoypads();
        return pads == null ? new int[0] : pads.Select(x => (int)x).ToArray();
    }

    // ---- Menu navigation from any pad (mapped XInput or raw EasySMX D-input) -------------

    private static bool _menuPadReady;

    /// <summary>Godot's default ui_* actions also carry joypad events.  If we leave those
    /// in place a pad A press would both activate the focused Button through Godot and
    /// through PadMenuNavigator (double click).  We own menu pads, so strip only the
    /// joypad events and keep keyboard Enter / arrows / Space working as before.</summary>
    public static void EnsureMenuPadActions()
    {
        if (_menuPadReady) return;
        _menuPadReady = true;
        foreach (string action in new[] { "ui_accept", "ui_up", "ui_down", "ui_left", "ui_right", "ui_cancel" })
        {
            if (!InputMap.HasAction(action)) continue;
            foreach (var e in InputMap.ActionGetEvents(action))
                if (e is InputEventJoypadButton || e is InputEventJoypadMotion)
                    InputMap.ActionEraseEvent(action, e);
        }
    }

    /// <summary>Aggregated d-pad / stick direction and A / Start / B / back for menu use.
    /// Uses the same PadLayout tables as gameplay, so unmapped EasySMX pads work too.</summary>
    public static void ReadMenuPad(out bool up, out bool down, out bool left, out bool right,
                                   out bool accept, out bool back)
    {
        // The menu can be the first code to poll a pad; load SDL mappings now.
        EnsureMappings();
        up = down = left = right = accept = back = false;
        foreach (int dev in PadLayout.DevicesFor(ConnectedDevices(), false, 0))
        {
            bool[] buttons = ReadButtons(dev);
            float[] axes = ReadAxes(dev);
            bool known = Input.IsJoyKnown(dev);
            var binds = PadLayout.Bindings(Input.GetJoyName(dev), known, _saved);
            PadVector m = PadLayout.Move(buttons, axes, known);
            if (m.Y < -.45f) up = true;
            if (m.Y > .45f) down = true;
            if (m.X < -.45f) left = true;
            if (m.X > .45f) right = true;
            var h = PadLayout.Held(buttons, axes, binds, known);
            // Layout-independent: ANY face button (A/B/X/Y, 0..3) or Start selects.
            // The old code also made button 8 both ACCEPT and BACK, so a single
            // press fired both handlers and START appeared to do nothing.
            bool face = false;
            for (int i = 0; i <= 3; i++) if (PadLayout.Button(buttons, i)) { face = true; break; }
            if (face || h["pass"] || h["pause"] || PadLayout.Button(buttons, 6)
                || PadLayout.Button(buttons, 9)) accept = true;
            // Back/Select is the only pad cancel; R3 remains the gameplay camera.
            if (PadLayout.Button(buttons, known ? 4 : 8)) back = true;
        }
    }

    public PlayerCommand Read(float dt)
    {
        var cmd = new PlayerCommand();
        PausePressed = false;
        CameraPressed = false;

        // --- movement: WASD / arrows / left stick / D-pad / virtual stick ---
        Vector2 move = Vector2.Zero;
        if (Input.IsPhysicalKeyPressed(Key.A) || Input.IsPhysicalKeyPressed(Key.Left)) move.X -= 1;
        if (Input.IsPhysicalKeyPressed(Key.D) || Input.IsPhysicalKeyPressed(Key.Right)) move.X += 1;
        if (Input.IsPhysicalKeyPressed(Key.W) || Input.IsPhysicalKeyPressed(Key.Up)) move.Y -= 1;
        if (Input.IsPhysicalKeyPressed(Key.S) || Input.IsPhysicalKeyPressed(Key.Down)) move.Y += 1;

        // Every connected pad (1P), or just this player's pad (2P), merged together.
        int[] devices = PadLayout.DevicesFor(ConnectedDevices(), _twoPlayer, _playerIndex);
        Vector2 padMove = Vector2.Zero;
        bool padSprint = false, padPass = false, padThrough = false, padTackle = false,
             padSwitch = false, padShoot = false, padPause = false, padCamera = false,
             padShield = false, padLob = false, padDribble = false;
        foreach (int dev in devices)
        {
            bool[] buttons = ReadButtons(dev);
            float[] axes = ReadAxes(dev);
            bool known = Input.IsJoyKnown(dev);
            var binds = PadLayout.Bindings(Input.GetJoyName(dev), known, _saved);
            PadVector m = PadLayout.Move(buttons, axes, known);
            padMove += new Vector2(m.X, m.Y);
            var h = PadLayout.Held(buttons, axes, binds, known);
            padPass |= h["pass"];
            padThrough |= h["through"];
            padShoot |= h["shoot"];
            padTackle |= h["tackle"];
            padSwitch |= h["switch"];
            padSprint |= h["sprint"];
            padPause |= h["pause"];
            padCamera |= h["camera"];
            padLob |= h["lob"];
            padDribble |= h["dribble"];
            // LT / L3 is close control + shielding.  The old Back-button shield
            // clashed with the menu Back button and left no long-pass button.
            padShield |= h["dribble"];
        }
        if (padMove.LengthSquared() > 1f) padMove = padMove.Normalized();
        move += padMove;
        if (TouchEnabled) move += TouchMove;
        if (move.LengthSquared() > 1f) move = move.Normalized();
        cmd.Move = new System.Numerics.Vector2(move.X, move.Y);

        bool sprint = Input.IsPhysicalKeyPressed(Key.Shift) || padSprint || (TouchEnabled && TouchSprint);
        bool pass = Input.IsPhysicalKeyPressed(Key.E) || padPass || (TouchEnabled && TouchPass);
        bool through = Input.IsPhysicalKeyPressed(Key.Q) || padThrough || (TouchEnabled && TouchThrough);
        bool tackle = Input.IsPhysicalKeyPressed(Key.F) || padTackle || (TouchEnabled && TouchTackle);
        bool sw = Input.IsPhysicalKeyPressed(Key.Tab) || padSwitch || (TouchEnabled && TouchSwitch);
        bool shoot = Input.IsPhysicalKeyPressed(Key.Space) || padShoot || (TouchEnabled && TouchShoot);
        bool pause = Input.IsPhysicalKeyPressed(Key.Escape) || padPause;
        bool camera = Input.IsPhysicalKeyPressed(Key.C) || padCamera;
        bool lob = Input.IsPhysicalKeyPressed(Key.R) || padLob || (TouchEnabled && TouchLob);
        // SHIFT+F (or sprint+tackle on a pad) is a committed slide; X / pad LB / raw Back
        // is shield.  Keeping slide out of Tackle stops a single press doing both.
        bool slide = (Input.IsPhysicalKeyPressed(Key.Shift) && Input.IsPhysicalKeyPressed(Key.F))
                     || (padSprint && padTackle);
        bool shield = Input.IsPhysicalKeyPressed(Key.X) || padShield || (TouchEnabled && TouchDribble);
        bool dribble = shield;

        cmd.Sprint = sprint;
        cmd.Pass = Edge(pass, ref _pPass);
        cmd.Through = Edge(through, ref _pThrough);
        cmd.Tackle = Edge(tackle && !slide, ref _pTackle);
        cmd.Slide = Edge(slide, ref _pSlide);
        cmd.Shield = shield;
        cmd.Dribble = dribble;
        cmd.Switch = Edge(sw, ref _pSwitch) || Input.IsMouseButtonPressed(MouseButton.Middle);
        cmd.Lob = Edge(lob, ref _pLob);
        PausePressed = Edge(pause, ref _pPause);
        // A stick click while steering must not cycle the camera repeatedly.
        if (camera) _cameraHold += dt; else _cameraHold = 0f;
        bool cameraFire = Input.IsPhysicalKeyPressed(Key.C) || _cameraHold > .12f;
        CameraPressed = Edge(cameraFire, ref _pCamera);

        // Hold to charge a shot; release to shoot. Also works on touch & gamepad.
        if (shoot) _charge = MathF.Min(1f, _charge + dt / .95f);
        else if (_charge > 0f) { cmd.Shoot = true; cmd.Charge = MathF.Max(.22f, _charge); _charge = 0f; }
        _pShoot = shoot;
        return cmd;
    }

    public void Reset()
    {
        _charge = 0;
        _cameraHold = 0f;
        _pShoot = _pPass = _pThrough = _pTackle = _pSlide = _pSwitch = _pPause = _pCamera = _pLob = false;
    }
}
