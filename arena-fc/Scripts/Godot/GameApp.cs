// Arena FC - application shell: main menu, match settings, character editor, match.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using ArenaFC.Core.Input;
using ArenaFC.Core.Net;
using Godot;

namespace ArenaFC.GodotGame;

public partial class GameApp : Node3D
{
    public static GameApp? Instance;
    public MatchOptions Options = new();
    public List<CharacterSpec>? CustomHome;

    private Node3D _menuWorld = null!;
    private Camera3D _menuCam = null!;
    private MeshInstance3D _menuBall = null!;
    private CharacterRig _menuRig = null!;
    private float _t;
    private bool _menu;

    // ---- PLAY WITH FRIENDS (protocol v2 desktop client) ----
    private OnlineMatch? _online;
    private CanvasLayer? _onlineLayer;
    private Label? _onlineStatus;
    private LineEdit? _urlEdit, _roomEdit, _nameEdit;
    private Button? _createBtn, _joinBtn, _readyBtn, _startBtn;
    private bool _onlineReady;
    private string _resumeToken = "";

    public static void Create(Node3D root)
    {
        var app = new GameApp { Name = "GameApp" };
        root.AddChild(app);
        app.Boot();
    }

    private void Boot()
    {
        Instance = this;
        // Lives on the Window, outside Clear(), so it survives every menu/match swap.
        if (GetTree().Root.GetNodeOrNull<PadMenuNavigator>("PadMenuNavigator") == null)
            GetTree().Root.AddChild(new PadMenuNavigator());
        ShowMenu();
    }

    private void Clear()
    {
        _menu = false;
        foreach (Node c in GetChildren()) { RemoveChild(c); c.QueueFree(); }
    }

    private static void Place(Control c, float ax, float ay, float x, float y, float w, float h)
    {
        c.AnchorLeft = c.AnchorRight = ax; c.AnchorTop = c.AnchorBottom = ay;
        c.OffsetLeft = x; c.OffsetTop = y; c.OffsetRight = x + w; c.OffsetBottom = y + h;
    }

    public void ShowMenu()
    {
        // Leaving a match (or the lobby) always disconnects cleanly.
        if (_online != null) { _online.Close(); _online = null; }
        _onlineLayer = null;
        _onlineStatus = null;
        _onlineReady = false;
        Clear();
        _menu = true;
        PadMenuNavigator.Active = true;
        _menuWorld = new Node3D { Name = "MenuWorld" };
        AddChild(_menuWorld);
        var stadium = new Stadium();
        stadium.Build(true);
        _menuWorld.AddChild(stadium);

        _menuRig = RigFactory.Create(Clubs.CreateRoster(0, 11)[^1]);
        _menuRig.EditorMode = false;
        _menuRig.Position = new Vector3(-2.4f, 0, -.4f);
        _menuWorld.AddChild(_menuRig);
        _menuBall = BallFactory.Create();
        _menuBall.Position = new Vector3(2.1f, .11f, -.2f);
        _menuWorld.AddChild(_menuBall);
        _menuCam = new Camera3D { Name = "MenuCamera", Position = new Vector3(0, 2.4f, 7.4f), Fov = 48 };
        _menuCam.LookAtFromPosition(_menuCam.Position, new Vector3(0, 1.1f, 0), Vector3.Up);
        _menuWorld.AddChild(_menuCam);
        _menuCam.MakeCurrent();

        var layer = new CanvasLayer { Layer = 30 };
        AddChild(layer);
        var root = new Control { MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(root);

        var title = Ui.Lbl("ARENA  FC", 62, Ui.Accent);
        title.HorizontalAlignment = HorizontalAlignment.Center;
        Place(title, 0, 0, 60, 60, 460, 90);
        root.AddChild(title);
        var sub = Ui.Lbl("3D FOOTBALL  ·  RIGGED CHARACTER STUDIO  ·  BUILD FOR ANY DEVICE", 16, Ui.Sub);
        Place(sub, 0, 0, 66, 146, 520, 28);
        root.AddChild(sub);

        var menu = Ui.VBox(10);
        menu.AddChild(Ui.Btn("PLAY MATCH", StartMatch, true));
        menu.AddChild(Ui.Btn("PLAY WITH FRIENDS", ShowOnline));
        menu.AddChild(Ui.Btn("CHARACTER EDITOR", ShowEditor));
        menu.AddChild(Ui.Btn("MATCH SETTINGS", ShowSettings));
        menu.AddChild(Ui.Btn("CONTROLS", ShowControls));
        menu.AddChild(Ui.Btn("CONTROLLER SETUP", ShowPadSetup));
        menu.AddChild(Ui.Btn("QUIT", () => GetTree().Quit()));
        var panel = Ui.PanelC(menu, Ui.Panel);
        Place(panel, 0, .5f, 60, -220, 330, 360);
        root.AddChild(panel);
        // Seed GUI focus: arrow keys / Enter / the pad d-pad all act on the focused Control.
        Ui.FocusFirst(root);

        string custom = CustomHome == null ? "default" : "CUSTOM SQUAD";
        var info = Ui.Lbl(
            $"Godot 4.7 · C# · procedural rigged meshes\n" +
            $"18-bone skeleton · 4-weight skinning · glTF export\n" +
            $"{Options.TeamSize}v{Options.TeamSize} · {Clubs.All[Options.HomeClub].Short} vs {Clubs.All[Options.AwayClub].Short} · home squad: {custom}\n" +
            $"Platform: {OS.GetName()} / {OS.GetProcessorName()}\n" +
            $"v{ProjectSettings.GetSetting("application/config/version", "1.0")} · user data: {ProjectSettings.GlobalizePath("user://")}", 13, Ui.Sub);
        var infoPanel = Ui.PanelC(info, Ui.Panel);
        Place(infoPanel, 1f, 1f, -520, -160, 500, 144);
        root.AddChild(infoPanel);
    }

    public override void _Process(double delta)
    {
        if (_online != null && _onlineLayer != null && _menu)
        {
            // The socket pump is drained on the main thread; no Godot signals needed.
            _online.Client.Poll();
            if (_online.Client.Token.Length >= 32) _resumeToken = _online.Client.Token;
            RefreshOnlineUi();
            if (_online.Started) { StartOnlineMatch(); return; }
        }
        if (!_menu) return;
        _t += (float)delta;
        if (_menuCam != null)
        {
            _menuCam.Position = new Vector3(MathF.Sin(_t * .12f) * 1.5f, 2.4f + MathF.Sin(_t * .22f) * .3f, 7.4f);
            _menuCam.LookAtFromPosition(_menuCam.Position, new Vector3(0, 1.1f, 0), Vector3.Up);
        }
        if (_menuBall != null) _menuBall.RotationDegrees += new Vector3(0, (float)delta * 45f, (float)delta * 12f);
        if (_menuRig != null)
        {
            _menuRig.Rotation = new Vector3(0, MathF.Sin(_t * .35f) * .5f, 0);
            var d = new PlayerState { AnimPhase = _t * 2.4f, Vel = new System.Numerics.Vector3(1.4f, 0, 0) };
            RigAnimator.Pose(_menuRig, d, (float)delta, _t, System.Numerics.Vector3.Zero);
        }
    }

    public void StartMatch()
    {
        Clear();
        PadMenuNavigator.Active = false;
        var view = new MatchView();
        var opts = new MatchOptions
        {
            TeamSize = Options.TeamSize, HalfMinutes = Options.HalfMinutes, TimeSpeed = Options.TimeSpeed,
            Difficulty = Options.Difficulty, Offside = Options.Offside, Fouls = Options.Fouls,
            HomeClub = Options.HomeClub, AwayClub = Options.AwayClub, Seed = Options.Seed,
            HomeFormation = Options.HomeFormation, AwayFormation = Options.AwayFormation,
            CustomHome = CustomHome?.Select(x => x.Clone()).ToList(),
        };
        view.Init(opts, CustomHome, ShowMenu);
        AddChild(view);
    }

    // ---------------------------------------------------------------- online UI

    /// <summary>PLAY WITH FRIENDS: room-code lobby for the authoritative v2 hub.
    /// Everything network-facing lives in ArenaFC.Core.Net (Godot-free); this is
    /// only the widgets plus a once-per-frame Poll().</summary>
    public void ShowOnline()
    {
        ShowMenu();                       // 3D stadium backdrop + base menu
        _onlineReady = false;
        _onlineLayer = new CanvasLayer { Layer = 40, Name = "OnlineLayer" };
        AddChild(_onlineLayer);

        var dim = new ColorRect { Color = new Color(.015f, .035f, .04f, .90f), MouseFilter = Control.MouseFilterEnum.Ignore };
        dim.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _onlineLayer.AddChild(dim);

        var root = new Control { MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _onlineLayer.AddChild(root);

        var box = Ui.VBox(8);
        box.AddChild(Ui.Lbl("PLAY WITH FRIENDS", 30, Ui.Accent));
        box.AddChild(Ui.Lbl("Protocol v2  ·  server-authoritative  ·  reconnect + rollback", 13, Ui.Sub));
        box.AddChild(Ui.Lbl(
            "One friend starts the .NET server (run-server.sh / .bat), then everyone\n" +
            "enters ws://HOST-IP:7777 and shares the 6-letter room code.", 13, Ui.Sub));

        var urlEdit = Edit("ws://127.0.0.1:7777", "Server URL (ws:// or wss://)");
        var roomEdit = Edit("", "Room code (blank = create a new one)");
        var nameEdit = Edit("Player", "Your name");
        _urlEdit = urlEdit; _roomEdit = roomEdit; _nameEdit = nameEdit;
        box.AddChild(urlEdit); box.AddChild(roomEdit); box.AddChild(nameEdit);

        var row = new HBoxContainer();
        row.AddThemeConstantOverride("separation", 8);
        var createBtn = Ui.Btn("CREATE MATCH", () => ConnectOnline(true), true);
        var joinBtn = Ui.Btn("JOIN MATCH", () => ConnectOnline(false));
        _createBtn = createBtn; _joinBtn = joinBtn;
        row.AddChild(createBtn); row.AddChild(joinBtn);
        box.AddChild(row);

        var row2 = new HBoxContainer();
        row2.AddThemeConstantOverride("separation", 8);
        var readyBtn = Ui.Btn("READY", () =>
        {
            _onlineReady = !_onlineReady;
            _online?.Client.SendReady(_onlineReady);
        });
        var startBtn = Ui.Btn("START MATCH (HOST)", () => _online?.Client.SendStart());
        _readyBtn = readyBtn; _startBtn = startBtn;
        row2.AddChild(readyBtn); row2.AddChild(startBtn);
        box.AddChild(row2);

        var statusLbl = Ui.Lbl("Offline", 14, Ui.Text);
        _onlineStatus = statusLbl;
        box.AddChild(Ui.PanelC(statusLbl, Ui.Panel));
        box.AddChild(Ui.Btn("BACK", ShowMenu));

        var panel = Ui.PanelC(box, Ui.Bg);
        Place(panel, .5f, .5f, -300, -280, 600, 560);
        root.AddChild(panel);
        Ui.FocusFirst(root);
        RefreshOnlineUi();
    }

    private static LineEdit Edit(string text, string placeholder) => new()
    {
        Text = text,
        PlaceholderText = placeholder,
        CustomMinimumSize = new Vector2(560, 38),
        FocusMode = Control.FocusModeEnum.All,
    };

    private void ConnectOnline(bool create)
    {
        if (_urlEdit == null || _roomEdit == null || _nameEdit == null) return;
        _online?.Close();
        _online = new OnlineMatch(new MatchOptions
        {
            TeamSize = Options.TeamSize, Seed = Options.Seed, TimeSpeed = Options.TimeSpeed,
            HalfMinutes = Options.HalfMinutes, Difficulty = Options.Difficulty,
            HomeClub = Options.HomeClub, AwayClub = Options.AwayClub,
            HomeFormation = Options.HomeFormation, AwayFormation = Options.AwayFormation,
        });
        string? token = _resumeToken.Length >= 32 ? _resumeToken : null;
        _online.Connect(_urlEdit.Text, _roomEdit.Text, _nameEdit.Text, token, create);
        _onlineReady = false;
        RefreshOnlineUi();
    }

    private void RefreshOnlineUi()
    {
        var c = _online?.Client;
        if (_onlineStatus != null)
        {
            string s = c?.Status ?? "Offline";
            if (c != null && c.Names.Length > 0) s += "\nPlayers: " + string.Join(", ", c.Names);
            if (c != null && c.Room.Length > 0) s += $"\nRoom {c.Room}  ·  slot {c.Slot}  ·  host {c.HostSlot}";
            if (c != null && c.LastError.Length > 0) s += "\nError: " + c.LastError;
            if (_online != null && _online.Corrections > 0)
                s += $"\nRollback: {_online.Corrections} corrections · replay {_online.LastReplayed}t · err {_online.LastError:F2}m";
            _onlineStatus.Text = s;
        }
        bool joined = c != null && c.Slot >= 0;
        if (_createBtn != null) _createBtn.Disabled = joined;
        if (_joinBtn != null) _joinBtn.Disabled = joined;
        if (_readyBtn != null) _readyBtn.Disabled = !joined;
        if (_startBtn != null) _startBtn.Disabled = !joined || (c != null && (!c.IsHost || c.Started));
    }

    /// <summary>`begin`/`resume` arrived: swap the lobby for the normal MatchView,
    /// but hand it the online driver so no local simulation runs.</summary>
    private void StartOnlineMatch()
    {
        var online = _online;
        if (online == null || !online.Started) return;
        _onlineLayer = null;
        _onlineStatus = null;
        _createBtn = _joinBtn = _readyBtn = _startBtn = null;
        _urlEdit = _roomEdit = _nameEdit = null;
        Clear();                          // removes the lobby + 3D menu backdrop
        PadMenuNavigator.Active = false;
        var view = new MatchView();
        var o = online.Options;
        view.Init(new MatchOptions
        {
            TeamSize = o.TeamSize, HalfMinutes = o.HalfMinutes, TimeSpeed = o.TimeSpeed,
            Difficulty = o.Difficulty, Offside = true, Fouls = true,
            HomeClub = o.HomeClub, AwayClub = o.AwayClub, Seed = o.Seed,
            HomeFormation = o.HomeFormation, AwayFormation = o.AwayFormation,
            AwayHuman = o.AwayHuman, CameraMode = o.CameraMode, CameraZoom = o.CameraZoom,
        }, null, ShowMenu);
        view.Online = online;
        AddChild(view);
    }

    public void ShowEditor()
    {
        Clear();
        PadMenuNavigator.Active = true;
        var ed = new CharacterEditor();
        var roster = CustomHome?.Select(x => x.Clone()).ToList() ?? Clubs.CreateRoster(Options.HomeClub, Options.TeamSize);
        ed.Init(roster);
        ed.OnExit = ShowMenu;
        ed.OnPlay = list => { CustomHome = list; StartMatch(); };
        ed.OnApplyRoster = list => { CustomHome = list; };
        AddChild(ed);
    }

    private void Overlay(string title, Control body, Action onBack)
    {
        var layer = new CanvasLayer { Layer = 40 };
        AddChild(layer);
        var dim = new ColorRect { Color = new Color(0, 0, 0, .45f) };
        dim.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(dim);
        var v = Ui.VBox(10);
        v.AddChild(Ui.Lbl(title, 28, Ui.Accent));
        // Scroll long setting/control lists so the Back button stays reachable
        // on small screens instead of being pushed off the bottom of the panel.
        var scroll = new ScrollContainer
        {
            CustomMinimumSize = new Vector2(560, 300),
            SizeFlagsHorizontal = Control.SizeFlags.ExpandFill,
            SizeFlagsVertical = Control.SizeFlags.ExpandFill,
        };
        body.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        scroll.AddChild(body);
        v.AddChild(scroll);
        v.AddChild(Ui.Btn("Back", () =>
        {
            layer.QueueFree();
            onBack?.Invoke();
            PadMenuNavigator.Active = _menu;
            Callable.From(() => Ui.FocusFirst(this)).CallDeferred();
        }, true));
        var panel = Ui.PanelC(v, Ui.Panel);
        Place(panel, .5f, .5f, -300, -260, 600, 520);
        layer.AddChild(panel);
        PadMenuNavigator.Active = true;
        Ui.FocusFirst(panel);
    }

    public void ShowSettings()
    {
        var v = Ui.VBox(10);
        v.AddChild(Ui.Lbl("TEAM SIZE", 15, Ui.Sub));
        v.AddChild(Ui.Combo(new[] { "5-a-side", "7-a-side", "11v11" }, Options.TeamSize == 5 ? 0 : Options.TeamSize == 7 ? 1 : 2,
            i => Options.TeamSize = i == 0 ? 5 : i == 1 ? 7 : 11));
        v.AddChild(Ui.Lbl("MATCH LENGTH (REAL TIME)", 15, Ui.Sub));
        v.AddChild(Ui.Combo(new[] { "Short · 4 min", "Standard · 6 min", "Long · 10 min" }, 1,
            i => Options.TimeSpeed = i == 0 ? 22f : i == 1 ? 15f : 9f));
        v.AddChild(Ui.Lbl("AI DIFFICULTY", 15, Ui.Sub));
        v.AddChild(Ui.Combo(new[] { "Amateur", "Professional", "World class", "Legendary" }, Options.Difficulty, i => Options.Difficulty = i));
        v.AddChild(Ui.Lbl("HOME / AWAY CLUB", 15, Ui.Sub));
        v.AddChild(Ui.Combo(Clubs.All.Select(c => c.Name).ToArray(), Options.HomeClub, i => Options.HomeClub = i));
        v.AddChild(Ui.Combo(Clubs.All.Select(c => c.Name).ToArray(), Options.AwayClub, i => Options.AwayClub = i));
        v.AddChild(Ui.Lbl("HOME FORMATION", 15, Ui.Sub));
        v.AddChild(Ui.Combo(Clubs.Formations, 0, i => Options.HomeFormation = Clubs.Formations[i]));
        v.AddChild(Ui.Check("Offside rule", Options.Offside, on => Options.Offside = on));
        v.AddChild(Ui.Check("Fouls & free kicks", Options.Fouls, on => Options.Fouls = on));
        v.AddChild(Ui.Btn("Reset custom squad", () => { CustomHome = null; }));
        Overlay("MATCH SETTINGS", v, () => { });
    }

    private void ShowControls()
    {
        var v = Ui.VBox(8);
        foreach (var line in new[]
        {
            "KEYBOARD", "WASD / Arrows — move", "SHIFT — sprint (clearly faster)",
            "E — short pass", "Q — through ball", "R — long ball / cross",
            "SPACE (hold then release) — charged shot",
            "F — standing tackle / press", "SHIFT+F — slide tackle (longer reach, more foul risk)",
            "X (hold) — close-control dribble + shield: use strength between challenger and ball",
            "TAB / middle mouse — switch player (auto-select also keeps you near the ball)",
            "C — cycle camera (Broadcast · Ball follow · Shoulder · Sideline · Tactical)",
            "ESC — pause", "",
            "GAMEPAD (mapped / XInput)", "Left stick / D-pad — move",
            "A — short pass · X — shoot (hold) · Y — through ball",
            "B — standing tackle · RB+B — slide tackle",
            "RB / RT — sprint · LB — switch player",
            "Back / Select — long ball / cross · LT or L3 — close-control dribble + shield",
            "Start — pause · R3 — camera", "",
            "GAMEPAD (raw EasySMX D-input / PC mode)", "A=b2 B=b1 X=b3 Y=b0 LB=b4 RB=b5",
            "Back=b8 long ball · Start=b9 pause · L3=b10 dribble · R3=b11 camera", "",
            "GAMEPAD MENUS", "D-pad / left stick — move the highlighted item",
            "ANY face button (A/B/X/Y), START or SELECT — activate the highlighted item",
            "On overlays Back / Select goes back; on the main menu it also activates", "",
            "USB / EASYSMX PADS", "XInput mode uses the standard layout. D-input / PC mode uses the raw",
            "EasySMX order (Y B A X, LB, RB, LT, RT) automatically. CONTROLLER SETUP lists",
            "every connected pad and lets you remap any button per pad.",
            "Quick button taps are event-latched, so a press shorter than one frame is not lost.", "",
            "CAMERA / POSSESSION (06.11.2026 second pass)", "Broadcast camera holds a dead-zone focus; it no longer drifts with every touch.",
            "YOU / BALL / OPP nameplates, larger rings and a contextual action bar show who has the ball.",
            "A carrier moving the stick gently enters CLOSE CONTROL automatically; LT/L3 forces it.",
            "B / RB+B now lunge into the challenge so dispossession is visible.", "",
            "TOUCH (Android / iOS / browser)", "Virtual stick on the left, eight action buttons on the right.",
            "Hold SHOOT to charge; release to strike.", "",
            "All three input paths produce the same commands — the match simulation is platform independent."
        }) v.AddChild(Ui.Lbl(line, line is "KEYBOARD" or "GAMEPAD" or "USB / EASYSMX PADS" or "TOUCH (Android / iOS / browser)" ? 19 : 14,
                               line is "KEYBOARD" or "GAMEPAD" or "USB / EASYSMX PADS" or "TOUCH (Android / iOS / browser)" ? Ui.Accent : Ui.Sub));
        Overlay("CONTROLS", v, () => { });
    }

    // ---- Controller setup / USB & EasySMX remapping --------------------------------------------

    private int _remapDevice = -1;
    private int _remapStep = -1;
    private Label? _remapLabel;

    private void ShowPadSetup()
    {
        var v = Ui.VBox(8);
        var info = Ui.Lbl(InputHub.DescribePads(), 14, Ui.Sub);
        v.AddChild(info);
        v.AddChild(Ui.Btn("REMAP PAD 1 (press each button when asked)", () => BeginRemap(0, info)));
        v.AddChild(Ui.Btn("REMAP PAD 2", () => BeginRemap(1, info)));
        v.AddChild(Ui.Btn("RESET PADS TO DEFAULT", () => { InputHub.ResetBindings(); info.Text = InputHub.DescribePads(); }));
        v.AddChild(Ui.Lbl("Plug in a USB / EasySMX pad and press a button once so the OS exposes it. " +
                          "Unmapped pads are read with the EasySMX D-input layout; remapping is saved per pad name.", 13, Ui.Sub));
        Overlay("CONTROLLER SETUP", v, () => { _remapDevice = -1; _remapStep = -1; _remapLabel = null; });
    }

    private void BeginRemap(int slot, Label info)
    {
        int[] pads = InputHub.ConnectedDevices();
        if (slot >= pads.Length)
        {
            info.Text = $"Pad {slot + 1} is not connected.\n\n" + InputHub.DescribePads();
            return;
        }
        _remapDevice = pads[slot];
        _remapStep = 0;
        _remapLabel = info;
        UpdateRemapLabel($"Press the button for {PadLayout.Actions[0].ToUpperInvariant()} (pad {slot + 1})");
    }

    private void UpdateRemapLabel(string prompt)
    {
        if (_remapLabel == null) return;
        _remapLabel.Text = prompt + "\n\n" + InputHub.DescribePads();
    }

    public override void _Input(InputEvent @event)
    {
        if (_remapStep < 0 || @event is not InputEventJoypadButton jb || !jb.Pressed) return;
        if (jb.Device != _remapDevice) return;
        InputHub.SetBinding(Input.GetJoyName(_remapDevice), PadLayout.Actions[_remapStep], (int)jb.ButtonIndex);
        _remapStep++;
        if (_remapStep >= PadLayout.Actions.Length)
        {
            _remapStep = -1;
            _remapDevice = -1;
            InputHub.SaveBindings();
            UpdateRemapLabel("Saved. Bindings are remembered for this pad.");
        }
        else
        {
            UpdateRemapLabel($"Press the button for {PadLayout.Actions[_remapStep].ToUpperInvariant()}");
        }
        GetViewport().SetInputAsHandled();
    }
}
