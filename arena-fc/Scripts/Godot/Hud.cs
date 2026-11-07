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
            DrawCircle(new Vector2(Px(p.Pos.X), Py(p.Pos.Z)), p.IsKeeper ? 3.2f : 2.8f,
                p.Team == 0 ? new Color(.95f, .25f, .3f) : new Color(.35f, .6f, 1f));
        var bp = new Vector2(Px(Engine.State.Ball.Pos.X), Py(Engine.State.Ball.Pos.Z));
        int ctrl = Engine.State.Controlled;
        if (ctrl >= 0 && ctrl < Engine.State.Players.Length)
        {
            var c = Engine.State.Players[ctrl];
            var cp = new Vector2(Px(c.Pos.X), Py(c.Pos.Z));
            DrawLine(cp, bp, new Color(.2f, 1f, .55f, .75f), 1.8f);
            DrawCircle(cp, 5.2f, new Color(.2f, 1f, .55f), false, 2f);
            // Nearest opposition presser gets a blue outline, matching the 3D
            // PressureRing so the minimap and the pitch tell the same story.
            int press = -1; float pd = float.MaxValue;
            foreach (var q in Engine.State.Players)
            {
                if (q.Team == c.Team || q.IsKeeper) continue;
                float d = Mx.FlatDist(q.Pos, Engine.State.Ball.Pos);
                if (d < pd) { pd = d; press = q.Index; }
            }
            if (press >= 0)
            {
                var q = Engine.State.Players[press];
                DrawCircle(new Vector2(Px(q.Pos.X), Py(q.Pos.Z)), 5.0f,
                    new Color(.35f, .65f, 1f), false, 1.8f);
            }
        }
        int owner = Engine.State.Ball.Owner;
        if (owner >= 0 && owner < Engine.State.Players.Length)
        {
            var o = Engine.State.Players[owner];
            DrawCircle(new Vector2(Px(o.Pos.X), Py(o.Pos.Z)), 6.2f,
                new Color(1f, .72f, .18f), false, 2.2f);
        }
        DrawCircle(bp, 3.4f, new Color(1f, .95f, .65f));
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

    private Label _score = null!, _clock = null!, _stats = null!, _feed = null!, _toast = null!,
                  _hint = null!, _cam = null!, _possession = null!, _focus = null!, _actions = null!;
    private ProgressBar _power = null!, _stamina = null!;
    private PanelContainer _pauseMenu = null!;
    private Control _pauseButtons = null!;
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

        // Big top-centre focus panel: camera, ball carrier, controlled player and
        // the buttons that matter right now.  The old left-edge labels sat under
        // the webcam overlay in the recording.
        var focusBox = Ui.VBox(2);
        _cam = Ui.Lbl("Broadcast", 13, Ui.Accent);
        _possession = Ui.Lbl("BALL · LOOSE", 18, new Color(1f, .92f, .45f));
        _focus = Ui.Lbl("YOU · —", 14, Ui.Sub);
        _actions = Ui.Lbl("A PASS · X SHOOT · LT DRIBBLE · RT SPRINT", 13, Ui.Text);
        focusBox.AddChild(_cam); focusBox.AddChild(_possession);
        focusBox.AddChild(_focus); focusBox.AddChild(_actions);
        var focusPanel = Ui.PanelC(focusBox, Ui.Panel);
        Place(focusPanel, .5f, 0f, -230, 12, 460, 118);
        root.AddChild(focusPanel);

        // Commentary feed (bottom left)
        _feed = Ui.Lbl("", 14, Ui.Sub);
        var feedPanel = Ui.PanelC(_feed);
        Place(feedPanel, 0f, 1f, 16, -152, 430, 96);
        root.AddChild(feedPanel);

        // Minimap (bottom right) - larger and higher contrast than the tiny 210px map.
        _minimap = new Minimap { CustomMinimumSize = new Vector2(250, 164) };
        var mapPanel = Ui.PanelC(_minimap);
        Place(mapPanel, 1f, 1f, -292, -214, 276, 196);
        root.AddChild(mapPanel);

        // Bars sit above the action legend instead of obscuring it.
        _power = Bar(new Color(1f, .72f, .18f));
        Place(_power, .5f, 1f, -130, -112, 260, 14);
        root.AddChild(_power);
        _stamina = Bar(new Color(.18f, .9f, .55f));
        Place(_stamina, .5f, 1f, -130, -94, 260, 10);
        root.AddChild(_stamina);

        // Compact two-line legend.  "pad R3 camera" stays advertised, but the
        // actions the player complained about are now impossible to miss.
        _hint = Ui.Lbl("E / A SHORT PASS  ·  R / SELECT LONG BALL  ·  SPACE / X SHOOT (hold)  ·  X / LT CLOSE CONTROL  ·  SHIFT / RT SPRINT\n" +
                       "F / B TACKLE  ·  SHIFT+F / RB+B SLIDE  ·  Q / Y THROUGH  ·  TAB / LB SWITCH  ·  C / pad R3 camera  ·  ESC / START pause",
                       13, Ui.Sub);
        _hint.HorizontalAlignment = HorizontalAlignment.Center;
        var hintPanel = Ui.PanelC(_hint);
        Place(hintPanel, .5f, 1f, -430, -78, 860, 58);
        root.AddChild(hintPanel);

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
        TouchBtn(_touchLayer, "LONG", 1f, 1f, bx, by + 120, 84, 52, () => Input.TouchLob = true, () => Input.TouchLob = false);
        TouchBtn(_touchLayer, "DRIBBLE", 1f, 1f, bx + 92, by + 120, 84, 52, () => Input.TouchDribble = true, () => Input.TouchDribble = false);
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
        // Focus is seeded in SetPaused(true) when the panel actually becomes visible.
        _pauseButtons = v;
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
        // The pause menu is a menu: hand control to the pad navigator and focus
        // "Resume" so A / d-pad / arrow keys work without a mouse.
        PadMenuNavigator.Active = on;
        if (on && _pauseButtons != null) Ui.FocusFirst(_pauseButtons);
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
        int owner = s.Ball.Owner;
        int ctrl = s.Controlled;
        bool validCtrl = ctrl >= 0 && ctrl < s.Players.Length;
        if (owner < 0 || owner >= s.Players.Length)
        {
            _possession.Text = "BALL · LOOSE";
            _possession.AddThemeColorOverride("font_color", new Color(1f, .92f, .45f));
        }
        else
        {
            var carrier = s.Players[owner];
            string side = carrier.Team == 0 ? "YOU" : "AWAY";
            _possession.Text = $"BALL · {side} · {carrier.Spec.DisplayName.ToUpperInvariant()}";
            _possession.AddThemeColorOverride("font_color",
                carrier.Team == 0 ? Ui.Accent : new Color(1f, .55f, .25f));
        }
        if (validCtrl)
        {
            var c = s.Players[ctrl];
            string state = c.Dribbling ? "CLOSE CONTROL" : c.Sprinting ? "SPRINT" : c.Pressing ? "PRESS" : "READY";
            _focus.Text = $"YOU · {c.Spec.DisplayName.ToUpperInvariant()}   ·   {state}";
        }
        else _focus.Text = "YOU · AUTO";
        if (owner >= 0 && owner == ctrl)
            _actions.Text = "A SHORT PASS · X SHOOT (hold) · LT CLOSE CONTROL · BACK LONG BALL · RT SPRINT";
        else if (owner < 0)
            _actions.Text = "RT CHASE · B PRESS · A FIRST-TOUCH PASS · X CLEARANCE";
        else
            _actions.Text = "RT SPRINT · B TACKLE · RB+B SLIDE · LB SWITCH · R3 CAMERA";
        _power.Value = charge * 100f;
        if (validCtrl) _stamina.Value = s.Players[ctrl].Stamina * 100f;
        if (Input.TouchEnabled) Input.TouchMove = _stick.Value;
        _minimap.Engine = e;
        _minimap.QueueRedraw();

        if (s.Phase == Phase.Goal && _toastTimer <= 0) ShowToast("GOAL!", 2.8f);
        else if (s.Phase == Phase.HalfTime && _toastTimer <= 0) ShowToast("HALF TIME", 2.8f);
        else if (s.Phase == Phase.FullTime) ShowToast($"FULL TIME   {s.Score[0]} - {s.Score[1]}", 99f);
        // A free kick used to appear from nowhere: make the whistle decision visible.
        else if (s.Phase == Phase.Penalty && _toastTimer <= 0) ShowToast("FOUL · PENALTY!", 2.2f);
        else if (s.Phase == Phase.FreeKick && _toastTimer <= 0) ShowToast("FOUL · FREE KICK", 1.8f);
        if (_toastTimer > 0)
        {
            _toastTimer -= dt;
            if (_toastTimer <= 0 && s.Phase != Phase.FullTime) _toast.Visible = false;
        }
    }

    // Called by VirtualStick via CallDeferred("emit_stick", ...) fallback (kept for safety).
    public void EmitStick(Vector2 v) { Input.TouchMove = v; }
}
