// Arena FC - application shell: main menu, match settings, character editor, match.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
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

    public static void Create(Node3D root)
    {
        var app = new GameApp { Name = "GameApp" };
        root.AddChild(app);
        app.Boot();
    }

    private void Boot()
    {
        Instance = this;
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
        Clear();
        _menu = true;
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
        menu.AddChild(Ui.Btn("CHARACTER EDITOR", ShowEditor));
        menu.AddChild(Ui.Btn("MATCH SETTINGS", ShowSettings));
        menu.AddChild(Ui.Btn("CONTROLS", ShowControls));
        menu.AddChild(Ui.Btn("QUIT", () => GetTree().Quit()));
        var panel = Ui.PanelC(menu, Ui.Panel);
        Place(panel, 0, .5f, 60, -190, 330, 300);
        root.AddChild(panel);

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

    public void ShowEditor()
    {
        Clear();
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
        v.AddChild(Ui.Btn("Back", () => { layer.QueueFree(); onBack?.Invoke(); }, true));
        var panel = Ui.PanelC(v, Ui.Panel);
        Place(panel, .5f, .5f, -300, -260, 600, 520);
        layer.AddChild(panel);
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
            "KEYBOARD", "WASD / Arrows — move", "SHIFT — sprint", "E — pass", "Q — through ball",
            "R — lofted chip pass", "SPACE (hold then release) — charged shot", "F — tackle / press",
            "TAB / middle mouse — switch player", "C — change camera", "ESC — pause", "",
            "GAMEPAD", "Left stick / D-pad — move", "A — pass · X — shoot (hold) · Y — through ball",
            "B — tackle · RB — sprint · LB — switch · Start — pause", "",
            "TOUCH (Android / iOS / browser)", "Virtual stick on the left, six action buttons on the right.",
            "Hold SHOOT to charge; release to strike.", "",
            "All three input paths produce the same commands — the match simulation is platform independent."
        }) v.AddChild(Ui.Lbl(line, line is "KEYBOARD" or "GAMEPAD" or "TOUCH (Android / iOS / browser)" ? 19 : 14,
                               line is "KEYBOARD" or "GAMEPAD" or "TOUCH (Android / iOS / browser)" ? Ui.Accent : Ui.Sub));
        Overlay("CONTROLS", v, () => { });
    }
}
