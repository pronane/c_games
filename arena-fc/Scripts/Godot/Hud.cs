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
    // Phase 4: Broadcast graphics
    private Label _lowerThird = null!, _statsOverlay = null!;
    private PanelContainer _lowerThirdPanel = null!, _statsOverlayPanel = null!;
    private float _lowerThirdTimer;
    private ProgressBar _power = null!, _stamina = null!;
    private Label? _chargeFeedback;
    private PanelContainer _pauseMenu = null!;
    private PanelContainer _statsPanel = null!, _hintPanel = null!, _feedPanel = null!;
    // 9.4 HUD footprint: the legend tucks away after the opening seconds (H/F1
    // brings it back for good) and the commentary fades when nothing is new.
    private float _feedAge;
    private bool _hintPinned;
    private string _lastFeed = "";
    private PanelContainer _fpsCounterPanel = null!;
    private Label _fpsCounterLabel = null!;
    private Control _pauseButtons = null!;
    private Minimap _minimap = null!;
    private PanelContainer _minimapPanel = null!;
    private Control _touchLayer = null!;
    private VirtualStick _stick = null!;
    private MatchEngine? _engine;
    private float _toastTimer;
    private float _fpsRefreshTimer;

    public override void _Ready()
    {
        var root = new Control { Name = "HudRoot", MouseFilter = Control.MouseFilterEnum.Ignore };
        _root = root;
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
        _statsPanel = Ui.PanelC(_stats);
        _statsPanel.Name = "MatchStatsPanel";
        Place(_statsPanel, 1f, 0f, -340, 14, 324, 44);
        _statsPanel.Visible = false;
        root.AddChild(_statsPanel);

        _fpsCounterLabel = Ui.Lbl("FPS --", 13, Ui.Accent);
        _fpsCounterLabel.Name = "FpsCounterText";
        _fpsCounterPanel = Ui.PanelC(_fpsCounterLabel);
        _fpsCounterPanel.Name = "FpsCounterPanel";
        Place(_fpsCounterPanel, 1f, 0f, -138, 64, 122, 28);
        _fpsCounterPanel.Visible = false;
        root.AddChild(_fpsCounterPanel);

        // Phase 4: Lower third (bottom centre, for player names/events)
        _lowerThird = Ui.Lbl("", 18, Ui.Text);
        _lowerThirdPanel = Ui.PanelC(_lowerThird);
        _lowerThirdPanel.Name = "LowerThirdPanel";
        Place(_lowerThirdPanel, 0.5f, 1f, -250, -180, 500, 40);
        root.AddChild(_lowerThirdPanel);
        _lowerThirdPanel.Visible = false;

        // Phase 4: Stats overlay (right side, toggled)
        _statsOverlay = Ui.Lbl("", 14, Ui.Sub);
        _statsOverlayPanel = Ui.PanelC(_statsOverlay);
        _statsOverlayPanel.Name = "StatsOverlayPanel";
        Place(_statsOverlayPanel, 1f, 0.5f, -220, -100, 204, 200);
        root.AddChild(_statsOverlayPanel);
        _statsOverlayPanel.Visible = false;

        // Big top-centre focus panel: camera, ball carrier, controlled player and
        // the buttons that matter right now.  The old left-edge labels sat under
        // the webcam overlay in the recording.
        var focusBox = Ui.VBox(2);
        _cam = Ui.Lbl("Broadcast", 13, Ui.Accent);
        _possession = Ui.Lbl("BALL · LOOSE", 18, new Color(1f, .92f, .45f));
        _focus = Ui.Lbl("YOU · —", 14, Ui.Sub);
        _actions = Ui.Lbl("A PASS · X SHOOT · LT DRIBBLE · RT SPRINT", 13, Ui.Text);
        // Keep persistent play context to two compact lines. Camera/debug details
        // and duplicate action copy live in the dismissible controls overlay.
        focusBox.AddChild(_possession);
        focusBox.AddChild(_focus);
        var focusPanel = Ui.PanelC(focusBox, Ui.Panel);
        Place(focusPanel, .5f, 0f, -190, 12, 380, 66);
        root.AddChild(focusPanel);

        // Commentary feed (bottom left)
        _feed = Ui.Lbl("", 14, Ui.Sub);
        _feedPanel = Ui.PanelC(_feed);
        _feedPanel.Name = "CommentaryPanel";
        Place(_feedPanel, 0f, 1f, 16, -170, 400, 84);
        root.AddChild(_feedPanel);

        // Minimap (bottom right) - larger and higher contrast than the tiny 210px map.
        _minimap = new Minimap { CustomMinimumSize = new Vector2(214, 140) };
        _minimapPanel = Ui.PanelC(_minimap);
        _minimapPanel.Name = "MinimapPanel";
        Place(_minimapPanel, 1f, 1f, -252, -252, 236, 166);
        root.AddChild(_minimapPanel);

        // Bars sit above the action legend instead of obscuring it.
        _power = Bar(new Color(1f, .72f, .18f));
        Place(_power, .5f, 1f, -130, -112, 260, 14);
        root.AddChild(_power);
        _chargeFeedback = Ui.Lbl("", 12, Ui.Accent);
        _chargeFeedback.HorizontalAlignment = HorizontalAlignment.Center;
        Place(_chargeFeedback, .5f, 1f, -130, -130, 260, 16);
        root.AddChild(_chargeFeedback);
        _stamina = Bar(new Color(.18f, .9f, .55f));
        Place(_stamina, .5f, 1f, -130, -94, 260, 10);
        root.AddChild(_stamina);

        // Compact two-line legend.  "pad R3 camera" stays advertised, but the
        // actions the player complained about are now impossible to miss.
        // Two lines that actually fit in two lines at 720p; every move is on the
        // pause menu's Controls page and in Training.
        _hint = Ui.Lbl("A/E PASS  ·  X/SPACE SHOOT  ·  Y/Q THROUGH  ·  VIEW/R LOB  ·  RT/SHIFT SPRINT  ·  LT/X DRIBBLE\n" +
                       "B/F TACKLE  ·  RT+B SLIDE  ·  LB/TAB SWITCH  ·  R3/C CAMERA  ·  ESC PAUSE (all controls)  ·  H HIDE",
                       13, Ui.Sub);
        _hint.HorizontalAlignment = HorizontalAlignment.Center;
        _hintPanel = Ui.PanelC(_hint);
        _hintPanel.Name = "ActionHintsPanel";
        Place(_hintPanel, .5f, 1f, -430, -78, 860, 58);
        root.AddChild(_hintPanel);

        _toast = Ui.Lbl("", 46, Ui.Accent);
        _toast.HorizontalAlignment = HorizontalAlignment.Center;
        Place(_toast, .5f, .5f, -400, -160, 800, 90);
        _toast.Visible = false;
        root.AddChild(_toast);

        BuildTouchControls(root);
        BuildPauseMenu(root);
        Layer = 10;
    }

    public override void _Process(double delta)
    {
        if (!_fpsCounterPanel.Visible) return;

        _fpsRefreshTimer -= (float)delta;
        if (_fpsRefreshTimer > 0f) return;

        _fpsRefreshTimer = .25f;
        _fpsCounterLabel.Text = $"FPS {Godot.Engine.GetFramesPerSecond()}";
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is not InputEventKey key || !key.Pressed || key.Echo)
            return;

        if (key.Keycode == Key.F3) ToggleFpsCounter();
        else if (key.Keycode == Key.F1 || key.Keycode == Key.H) ToggleControls();
        else if (key.Keycode == Key.F2) ToggleMatchStats();
        else return;
        GetViewport().SetInputAsHandled();
    }

    public void ToggleControls()
    {
        _hintPinned = true;
        if (_hintPanel != null) _hintPanel.Visible = !_hintPanel.Visible;
    }

    public void ToggleMatchStats()
    {
        if (_statsPanel != null) _statsPanel.Visible = !_statsPanel.Visible;
    }

    public void ToggleFpsCounter()
    {
        _fpsCounterPanel.Visible = !_fpsCounterPanel.Visible;
        if (!_fpsCounterPanel.Visible) return;

        _fpsRefreshTimer = 0f;
        _fpsCounterLabel.Text = $"FPS {Godot.Engine.GetFramesPerSecond()}";
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
        v.AddChild(Ui.Btn("Controls - every move", ShowControlsCard));
        v.AddChild(Ui.Btn("Substitutions", ShowSubstitutions));
        v.AddChild(Ui.Btn("Match analysis", ShowAnalysis));
        v.AddChild(Ui.Btn("Photo mode", TogglePhotoMode));
        v.AddChild(Ui.Btn("Change camera (C)", () => OnCamera?.Invoke()));
        v.AddChild(Ui.Btn("Toggle controls (H)", ToggleControls));
        v.AddChild(Ui.Btn("Match stats (F2)", ToggleMatchStats));
        v.AddChild(Ui.Btn("Toggle FPS counter (F3)", ToggleFpsCounter));
        v.AddChild(Ui.Btn("Toggle touch controls", () => { SetTouch(!Input.TouchEnabled); OnTouchToggle?.Invoke(); }));
        v.AddChild(Ui.Btn("Quit to main menu", () => { SetPaused(false); OnQuit?.Invoke(); }));
        v.AddChild(Ui.Lbl("Arena FC build " + ProjectSettings.GetSetting("application/config/version", "1.0"), 12, Ui.Sub));
        _pauseMenu = Ui.PanelC(v, Ui.Panel);
        Place(_pauseMenu, .5f, .5f, -190, -290, 380, 580);
        _pauseMenu.Visible = false;
        root.AddChild(_pauseMenu);
        // Focus is seeded in SetPaused(true) when the panel actually becomes visible.
        _pauseButtons = v;
    }

    private Control? _controlsCard;
    private Control? _root;

    /// <summary>Every move with its Xbox-layout (EasySMX etc.) button and keyboard key,
    /// from the same list the Training coach teaches, so the two can never disagree.</summary>
    private void ShowControlsCard()
    {
        if (_pauseMenu != null) _pauseMenu.Visible = false;   // the card replaces the pause list
        if (_controlsCard != null) { _controlsCard.Visible = true; return; }
        var list = new VBoxContainer();
        list.AddThemeConstantOverride("separation", 4);
        list.AddChild(Ui.Lbl("CONTROLS", 24, Ui.Accent));
        string section = "";
        foreach (var l in TrainingCoach.BuildLessons())
        {
            if (l.Goal == LessonGoal.FreePlay) continue;
            if (l.Section != section) { section = l.Section; list.AddChild(Ui.Lbl(section, 13, Ui.Accent)); }
            var row = new RichTextLabel { BbcodeEnabled = true, FitContent = true, ScrollActive = false,
                AutowrapMode = TextServer.AutowrapMode.Off, CustomMinimumSize = new Vector2(820, 22),
                MouseFilter = Control.MouseFilterEnum.Ignore };
            row.AddThemeFontSizeOverride("normal_font_size", 14);
            row.AddThemeFontSizeOverride("bold_font_size", 14);
            row.Text = $"[b]{l.Title}[/b]   " + ModeOverlay.ToBbcode(l.Pad) + "   [color=#8fb3ad]|[/color]   " + ModeOverlay.ToBbcode(l.Keys);
            list.AddChild(row);
        }
        list.AddChild(Ui.Lbl("Violent conduct (straight red, VAR if unseen): hold LB+RB then B = punch, Y = headbutt; keys G / T.", 12, Ui.Sub));
        list.AddChild(Ui.Btn("Back", () =>
        {
            if (_controlsCard != null) _controlsCard.Visible = false;
            if (_pauseMenu != null) _pauseMenu.Visible = Paused;
        }, true));
        var scroll = new ScrollContainer { CustomMinimumSize = new Vector2(880, 600) };
        scroll.AddChild(list);
        _controlsCard = Ui.PanelC(scroll, new Color(.03f, .05f, .06f, .97f));
        Place(_controlsCard, .5f, .5f, -450, -320, 900, 640);
        _root?.AddChild(_controlsCard);
    }

    public void SetTouch(bool on)
    {
        Input.TouchEnabled = on;
        if (_touchLayer != null) _touchLayer.Visible = on;
        if (_minimapPanel != null) _minimapPanel.Visible = !on;
    }

    public void SetPaused(bool on)
    {
        Paused = on;
        if (_pauseMenu != null) _pauseMenu.Visible = on;
        if (!on && _controlsCard != null) _controlsCard.Visible = false;
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

    /// <summary>Phase 4: Show lower third graphic (player name, event).</summary>
    public void ShowLowerThird(string text, float seconds = 3f)
    {
        _lowerThird.Text = text;
        _lowerThird.Visible = true;
        _lowerThirdPanel.Visible = true;
        _lowerThirdTimer = seconds;
    }

    /// <summary>Phase 4: Show stats overlay.</summary>
    public void ShowStatsOverlay(string text)
    {
        _statsOverlay.Text = text;
        _statsOverlay.Visible = true;
        _statsOverlayPanel.Visible = true;
    }

    /// <summary>Phase 4: Hide stats overlay.</summary>
    public void HideStatsOverlay()
    {
        _statsOverlay.Visible = false;
        _statsOverlayPanel.Visible = false;
    }

    /// <summary>Add a commentary line to the feed (Phase 1).</summary>
    public void AddCommentary(string line)
    {
        if (string.IsNullOrEmpty(line)) return;
        var lines = _feed.Text.Split('\n').ToList();
        lines.Add(line);
        while (lines.Count > 3) lines.RemoveAt(0);
        _feed.Text = string.Join("\n", lines);
    }

    public void Update(MatchEngine e, float dt, float charge, string cameraName)
    {
        _engine = e;
        var s = e.State;
        string home = e.ShortFor(0), away = e.ShortFor(1);
        _score.Text = $"{home}   {s.Score[0]}  -  {s.Score[1]}   {away}";
        string stoppage = e.InStoppageTime ? $"  +{e.AddedMinutesShown}'" : "";
        // Training and shootouts have no match clock or halves (9.6).
        _clock.Text = e.IsShootout ? "PENALTY SHOOTOUT"
                    : e.IsTraining ? "TRAINING GROUND   ·   no clock"
                    : $"{e.ClockString()}{stoppage}   {(s.Half == 1 ? "1st" : "2nd")} HALF   ·   {e.Options.TeamSize}v{e.Options.TeamSize}";
        _stats.Text = $"Poss {e.PossessionPct(0):0}% - {e.PossessionPct(1):0}%   |   Shots {s.Shots[0]}-{s.Shots[1]}   |   Fouls {s.Fouls[0]}-{s.Fouls[1]}   |   Corners {s.Corners[0]}-{s.Corners[1]}   |   xG {s.Xg[0]:0.00}-{s.Xg[1]:0.00}"
                    + (s.YellowCards[0] + s.YellowCards[1] + s.RedCards[0] + s.RedCards[1] > 0
                        ? $"   |   Yellow {s.YellowCards[0]}-{s.YellowCards[1]}  Red {s.RedCards[0]}-{s.RedCards[1]}"
                        : "");
        var recent = e.Events.Count > 0 ? e.Events.Skip(Math.Max(0, e.Events.Count - 3)).Select(x => x.Text) : Array.Empty<string>();
        _feed.Text = string.Join("\n", recent);
        if (_feed.Text != _lastFeed) { _lastFeed = _feed.Text; _feedAge = 0f; } else _feedAge += dt;
        _feedPanel.Modulate = new Color(1, 1, 1, Math.Clamp(1.6f - _feedAge / 5f, 0f, 1f));
        // Hide once five match minutes have been played (~20 s at normal speed);
        // keyed to the match clock so slow frames don't keep it up longer.
        if (!_hintPinned && s.Phase == Phase.Play && s.Clock >= 300f && _hintPanel.Visible)
        { _hintPanel.Visible = false; _hintPinned = true; }
        _cam.Text = cameraName;
        // Phase 4: lower third timer
        if (_lowerThirdTimer > 0)
        {
            _lowerThirdTimer -= dt;
            if (_lowerThirdTimer <= 0)
            {
                _lowerThird.Visible = false;
                _lowerThirdPanel.Visible = false;
            }
        }
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
        // ShotMeter (Features 1): the perfect window, spoken in words, not a colour.
        if (charge > 0.02f && _chargeFeedback != null)
        {
            var app = GameApp.Instance;
            _chargeFeedback.Text = app != null ? app.ShotFeedback(charge) : "";
        }
        if (validCtrl) _stamina.Value = s.Players[ctrl].Stamina * 100f;
        if (Input.TouchEnabled) Input.TouchMove = _stick.Value;
        _minimap.Engine = e;
        _minimap.QueueRedraw();

        if (s.Phase == Phase.Goal && _toastTimer <= 0) ShowToast("GOAL!", 2.8f);
        else if (s.Phase == Phase.HalfTime && _toastTimer <= 0) ShowToast("HALF TIME", 2.8f);
        else if (s.Phase == Phase.FullTime) ShowToast($"FULL TIME   {s.Score[0]} - {s.Score[1]}", 99f);
        // A free kick used to appear from nowhere: make the whistle decision visible.
        else if (s.Phase == Phase.Penalty && _toastTimer <= 0 && !e.IsShootout) ShowToast("FOUL · PENALTY!", 2.2f);
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
