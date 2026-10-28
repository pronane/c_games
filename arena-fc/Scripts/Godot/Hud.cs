// Arena FC - match HUD: scoreboard, clock, stats, commentary, power/stamina bars,
// minimap, pause menu and on-screen touch controls (identical command path on all devices).
using System;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Minimap : Control
{
    public MatchEngine? Engine;
    public override void _Draw()
    {
        var s = Size;
        DrawRect(new Rect2(0, 0, s.X, s.Y), new Color(.045f, .16f, .09f, .92f));
        float pad = 6f;
        float w = s.X - pad * 2f, h = s.Y - pad * 2f;
        DrawRect(new Rect2(pad, pad, w, h), new Color(1, 1, 1, .28f), false, 1.5f);
        DrawLine(new Vector2(s.X * .5f, pad), new Vector2(s.X * .5f, s.Y - pad), new Color(1, 1, 1, .22f), 1f);
        DrawCircle(new Vector2(s.X * .5f, s.Y * .5f), 7f, new Color(1, 1, 1, .18f), false, 1f);
        if (Engine == null) return;
        float Px(float x) => pad + (x / Mx.PitchLength + .5f) * w;
        float Py(float z) => pad + (z / Mx.PitchWidth + .5f) * h;
        foreach (var p in Engine.State.Players)
            DrawCircle(new Vector2(Px(p.Pos.X), Py(p.Pos.Z)), p.IsKeeper ? 2.6f : 2.2f,
                p.Team == 0 ? new Color(.95f, .25f, .3f) : new Color(.35f, .6f, 1f));
        if (Engine.State.Controlled >= 0 && Engine.State.Controlled < Engine.State.Players.Length)
        {
            var c = Engine.State.Players[Engine.State.Controlled];
            DrawCircle(new Vector2(Px(c.Pos.X), Py(c.Pos.Z)), 4.2f, new Color(.2f, 1f, .55f), false, 1.4f);
        }
        DrawCircle(new Vector2(Px(Engine.State.Ball.Pos.X), Py(Engine.State.Ball.Pos.Z)), 2.2f, new Color(1f, .95f, .65f));
    }
}

public partial class VirtualStick : Control
{
    public Vector2 Value;
    private Vector2 _knob;
    private bool _active;
    private int _index = -1;

    public VirtualStick()
    {
        MouseFilter = Control.MouseFilterEnum.Stop;
        CustomMinimumSize = new Vector2(150, 150);
    }

    public override void _GuiInput(InputEvent e)
    {
        if (e is InputEventScreenTouch st)
        {
            if (st.Pressed && (!_active || _index == st.Index)) { _active = true; _index = st.Index; Set(st.Position); }
            else if (!st.Pressed && st.Index == _index) { _active = false; _index = -1; Value = Vector2.Zero; _knob = Vector2.Zero; }
            QueueRedraw();
        }
        else if (e is InputEventScreenDrag sd && sd.Index == _index) { Set(sd.Position); QueueRedraw(); }
        else if (e is InputEventMouseButton mb && mb.ButtonIndex == MouseButton.Left)
        {
            if (mb.Pressed) { _active = true; Set(mb.Position); }
            else { _active = false; Value = Vector2.Zero; _knob = Vector2.Zero; }
            QueueRedraw();
        }
        else if (e is InputEventMouseMotion mm && _active) { Set(mm.Position); QueueRedraw(); }
    }

    private void Set(Vector2 globalPos)
    {
        Vector2 local = globalPos - GetGlobalRect().Position;
        Vector2 c = Size * .5f;
        Vector2 d = local - c;
        float r = MathF.Min(c.X, c.Y) - 12f;
        if (d.Length() > r) d = d.Normalized() * r;
        _knob = d;
        Value = new Vector2(d.X / r, d.Y / r);
    }

    public override void _Draw()
    {
        Vector2 c = Size * .5f;
        float r = MathF.Min(c.X, c.Y) - 12f;
        DrawCircle(c, r, new Color(.8f, .95f, .9f, .09f));
        DrawArc(c, r, 0, MathF.Tau, 48, new Color(.4f, .95f, .7f, .35f), 2f);
        DrawCircle(c + _knob, 22f, new Color(.15f, .85f, .55f, .55f));
    }
}

public partial class Hud : CanvasLayer
{
    public InputHub Input = new();
    public Action? OnQuit, OnResume, OnCamera, OnTouchToggle;
    public bool Paused;

    private Label _score = null!, _clock = null!, _stats = null!, _feed = null!, _toast = null!, _hint = null!, _cam = null!;
    private ProgressBar _power = null!, _stamina = null!;
    private PanelContainer _pauseMenu = null!;
    private Minimap _minimap = null!;
    private Control _touchLayer = null!;
    private VirtualStick _stick = null!;
    private MatchEngine? _engine;
    private float _toastTimer;

    public override void _Ready()
    {
        var root = new Control { Name = "HudRoot", MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        AddChild(root);

        // Scoreboard (top centre-left)
        var box = Ui.VBox(2);
        _score = Ui.Lbl("HAR 0 - 0 NOR", 24);
        _clock = Ui.Lbl("00:00  1st HALF", 15, Ui.Sub);
        box.AddChild(_score); box.AddChild(_clock);
        var scorePanel = Ui.PanelC(box);
        Place(scorePanel, 0f, 0f, 16, 14, 300, 78);
        root.AddChild(scorePanel);

        // Stats (top right)
        _stats = Ui.Lbl("Possession 50% | Shots 0-0", 15, Ui.Sub);
        var statsPanel = Ui.PanelC(_stats);
        Place(statsPanel, 1f, 0f, -340, 14, 324, 44);
        root.AddChild(statsPanel);

        // Commentary feed (bottom left)
        _feed = Ui.Lbl("", 14, Ui.Sub);
        var feedPanel = Ui.PanelC(_feed);
        Place(feedPanel, 0f, 1f, 16, -152, 430, 96);
        root.AddChild(feedPanel);

        // Minimap (bottom right)
        _minimap = new Minimap { CustomMinimumSize = new Vector2(210, 136) };
        var mapPanel = Ui.PanelC(_minimap);
        Place(mapPanel, 1f, 1f, -242, -178, 226, 162);
        root.AddChild(mapPanel);

        // Bars
        _power = Bar(new Color(1f, .72f, .18f));
        Place(_power, .5f, 1f, -130, -52, 260, 14);
        root.AddChild(_power);
        _stamina = Bar(new Color(.18f, .9f, .55f));
        Place(_stamina, .5f, 1f, -130, -32, 260, 10);
        root.AddChild(_stamina);

        _hint = Ui.Lbl("WASD move  ·  SHIFT sprint  ·  E pass  ·  SPACE shoot (hold)  ·  Q through  ·  F tackle  ·  TAB switch  ·  C camera  ·  ESC pause",
                      12, Ui.Sub);
        Place(_hint, .5f, 1f, -470, -14, 940, 18);
        root.AddChild(_hint);

        _cam = Ui.Lbl("Broadcast", 13, Ui.Accent);
        Place(_cam, 0f, 0f, 330, 22, 200, 24);
        root.AddChild(_cam);

        _toast = Ui.Lbl("", 46, Ui.Accent);
        _toast.HorizontalAlignment = HorizontalAlignment.Center;
        Place(_toast, .5f, .5f, -400, -160, 800, 90);
        _toast.Visible = false;
        root.AddChild(_toast);

        BuildTouchControls(root);
        BuildPauseMenu(root);
        Layer = 10;
    }

    private ProgressBar Bar(Color c)
    {
        var b = new ProgressBar { MinValue = 0, MaxValue = 100, Value = 0, ShowPercentage = false };
        b.AddThemeStyleboxOverride("fill", Ui.Box(c, null, 3, 0));
        b.AddThemeStyleboxOverride("background", Ui.Box(new Color(.06f, .08f, .09f, .9f), null, 3, 0));
        return b;
    }

    private static void Place(Control c, float ax, float ay, float x, float y, float w, float h)
    {
        c.AnchorLeft = c.AnchorRight = ax;
        c.AnchorTop = c.AnchorBottom = ay;
        c.OffsetLeft = x; c.OffsetTop = y; c.OffsetRight = x + w; c.OffsetBottom = y + h;
    }

    private void BuildTouchControls(Control root)
    {
        _touchLayer = new Control { Name = "TouchControls", MouseFilter = Control.MouseFilterEnum.Ignore, Visible = false };
        _touchLayer.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(_touchLayer);

        _stick = new VirtualStick();
        Place(_stick, 0f, 1f, 24, -190, 160, 160);
        _touchLayer.AddChild(_stick);

        float bx = -250, by = -200;
        TouchBtn(_touchLayer, "PASS", 1f, 1f, bx, by, 84, 52, () => Input.TouchPass = true, () => Input.TouchPass = false);
        TouchBtn(_touchLayer, "SHOOT", 1f, 1f, bx + 92, by, 84, 52, () => Input.TouchShoot = true, () => Input.TouchShoot = false);
        TouchBtn(_touchLayer, "SPRINT", 1f, 1f, bx + 184, by, 84, 52, () => Input.TouchSprint = true, () => Input.TouchSprint = false);
        TouchBtn(_touchLayer, "THROUGH", 1f, 1f, bx, by + 60, 84, 52, () => Input.TouchThrough = true, () => Input.TouchThrough = false);
        TouchBtn(_touchLayer, "TACKLE", 1f, 1f, bx + 92, by + 60, 84, 52, () => Input.TouchTackle = true, () => Input.TouchTackle = false);
        TouchBtn(_touchLayer, "SWITCH", 1f, 1f, bx + 184, by + 60, 84, 52, () => Input.TouchSwitch = true, () => Input.TouchSwitch = false);
    }

    private static void TouchBtn(Control parent, string text, float ax, float ay, float x, float y, float w, float h, Action down, Action up)
    {
        var b = new Button { Text = text };
        Ui.Style(b);
        b.AddThemeFontSizeOverride("font_size", 13);
        b.ButtonDown += () => down();
        b.ButtonUp += () => up();
        b.Pressed += () => up();
        var c = b;
        c.AnchorLeft = c.AnchorRight = ax; c.AnchorTop = c.AnchorBottom = ay;
        c.OffsetLeft = x; c.OffsetTop = y; c.OffsetRight = x + w; c.OffsetBottom = y + h;
        parent.AddChild(c);
    }

    private void BuildPauseMenu(Control root)
    {
        var v = Ui.VBox(10);
        v.AddChild(Ui.Lbl("PAUSED", 30, Ui.Accent));
        v.AddChild(Ui.Btn("Resume", () => { SetPaused(false); OnResume?.Invoke(); }, true));
        v.AddChild(Ui.Btn("Change camera (C)", () => OnCamera?.Invoke()));
        v.AddChild(Ui.Btn("Toggle touch controls", () => { SetTouch(!Input.TouchEnabled); OnTouchToggle?.Invoke(); }));
        v.AddChild(Ui.Btn("Quit to main menu", () => { SetPaused(false); OnQuit?.Invoke(); }));
        v.AddChild(Ui.Lbl("Arena FC build " + ProjectSettings.GetSetting("application/config/version", "1.0"), 12, Ui.Sub));
        _pauseMenu = Ui.PanelC(v, Ui.Panel);
        Place(_pauseMenu, .5f, .5f, -180, -170, 360, 340);
        _pauseMenu.Visible = false;
        root.AddChild(_pauseMenu);
    }

    public void SetTouch(bool on)
    {
        Input.TouchEnabled = on;
        if (_touchLayer != null) _touchLayer.Visible = on;
    }

    public void SetPaused(bool on)
    {
        Paused = on;
        if (_pauseMenu != null) _pauseMenu.Visible = on;
    }

    public void ShowToast(string text, float seconds = 2.2f)
    {
        _toast.Text = text;
        _toast.Visible = true;
        _toastTimer = seconds;
    }

    public void Update(MatchEngine e, float dt, float charge, string cameraName)
    {
        _engine = e;
        var s = e.State;
        string home = Clubs.All[e.Options.HomeClub].Short, away = Clubs.All[e.Options.AwayClub].Short;
        _score.Text = $"{home}   {s.Score[0]}  -  {s.Score[1]}   {away}";
        _clock.Text = $"{e.ClockString()}   {(s.Half == 1 ? "1st" : "2nd")} HALF   ·   {e.Options.TeamSize}v{e.Options.TeamSize}";
        _stats.Text = $"Poss {e.PossessionPct(0):0}% - {e.PossessionPct(1):0}%   |   Shots {s.Shots[0]}-{s.Shots[1]}   |   Fouls {s.Fouls[0]}-{s.Fouls[1]}   |   Corners {s.Corners[0]}-{s.Corners[1]}";
        var recent = e.Events.Count > 0 ? e.Events.Skip(Math.Max(0, e.Events.Count - 3)).Select(x => x.Text) : Array.Empty<string>();
        _feed.Text = string.Join("\n", recent);
        _cam.Text = cameraName;
        _power.Value = charge * 100f;
        if (s.Controlled >= 0 && s.Controlled < s.Players.Length)
            _stamina.Value = s.Players[s.Controlled].Stamina * 100f;
        if (Input.TouchEnabled) Input.TouchMove = _stick.Value;
        _minimap.Engine = e;
        _minimap.QueueRedraw();

        if (s.Phase == Phase.Goal && _toastTimer <= 0) ShowToast("GOAL!", 2.8f);
        else if (s.Phase == Phase.HalfTime && _toastTimer <= 0) ShowToast("HALF TIME", 2.8f);
        else if (s.Phase == Phase.FullTime) ShowToast($"FULL TIME   {s.Score[0]} - {s.Score[1]}", 99f);
        if (_toastTimer > 0)
        {
            _toastTimer -= dt;
            if (_toastTimer <= 0 && s.Phase != Phase.FullTime) _toast.Visible = false;
        }
    }

    // Called by VirtualStick via CallDeferred("emit_stick", ...) fallback (kept for safety).
    public void EmitStick(Vector2 v) { Input.TouchMove = v; }
}
