// Arena FC - on-screen coach for Training, and the penalty tally for Shootouts.
//
// The coach is a speech bubble on the left of the pitch: what the move is,
// which Xbox-layout button to press (EasySMX and other XInput pads use the
// same A/B/X/Y labels and colours), the keyboard equivalent, a short tip,
// and a progress bar.  Lessons complete automatically (TrainingCoach).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class ModeOverlay : CanvasLayer
{
    private PanelContainer? _coachPanel, _shootPanel;
    private Label? _section, _title, _tip, _progressText, _feedback, _shootTally, _shootScore;
    private RichTextLabel? _padLine, _keyLine, _footer, _shootHint;
    private ProgressBar? _bar;
    private int _shownLesson = -1;
    private int _mode;

    private static readonly Dictionary<string, (string bg, string fg)> Glyphs = new()
    {
        ["A"] = ("#3a9d46", "#ffffff"), ["B"] = ("#cf3a33", "#ffffff"),
        ["X"] = ("#2f6bd1", "#ffffff"), ["Y"] = ("#e0b21a", "#1a1a1a"),
        ["LB"] = ("#3b4448", "#ffffff"), ["RB"] = ("#3b4448", "#ffffff"),
        ["LT"] = ("#3b4448", "#ffffff"), ["RT"] = ("#3b4448", "#ffffff"),
        ["LS"] = ("#3b4448", "#ffffff"), ["RS"] = ("#3b4448", "#ffffff"),
        ["VIEW"] = ("#3b4448", "#ffffff"), ["MENU"] = ("#3b4448", "#ffffff"),
    };

    /// <summary>"[A]" → coloured button chip, "&lt;E&gt;" → keyboard key cap, as BBCode.</summary>
    public static string ToBbcode(string text)
    {
        var sb = new StringBuilder();
        int i = 0;
        while (i < text.Length)
        {
            char c = text[i];
            if (c == '[' || c == '<')
            {
                char close = c == '[' ? ']' : '>';
                int end = text.IndexOf(close, i + 1);
                if (end > i)
                {
                    string tok = text.Substring(i + 1, end - i - 1);
                    if (c == '[' && Glyphs.TryGetValue(tok, out var g))
                    {
                        sb.Append($"[bgcolor={g.bg}][color={g.fg}][b] {tok} [/b][/color][/bgcolor]");
                        i = end + 1; continue;
                    }
                    if (c == '<' && tok.Length is > 0 and <= 10)
                    {
                        sb.Append($"[bgcolor=#e9eef0][color=#14191b][b] {tok} [/b][/color][/bgcolor]");
                        i = end + 1; continue;
                    }
                }
                sb.Append(c == '[' ? "[lb]" : "<");
                i++; continue;
            }
            if (c == ']') { sb.Append("[rb]"); i++; continue; }
            sb.Append(c);
            i++;
        }
        return sb.ToString();
    }

    private static RichTextLabel Rich(int size)
    {
        var r = new RichTextLabel
        {
            BbcodeEnabled = true, FitContent = true, ScrollActive = false,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            MouseFilter = Control.MouseFilterEnum.Ignore,
            CustomMinimumSize = new Vector2(380, 0),
        };
        r.AddThemeFontSizeOverride("normal_font_size", size);
        r.AddThemeFontSizeOverride("bold_font_size", size);
        r.AddThemeColorOverride("default_color", Ui.Text);
        return r;
    }

    public void Setup(int mode)
    {
        _mode = mode;
        Layer = 30;
        Name = "ModeOverlay";
        if (mode == MatchEngine.ModeTraining) BuildCoach();
        else if (mode == MatchEngine.ModeShootout) BuildShootout();
    }

    private void BuildCoach()
    {
        var v = new VBoxContainer();
        v.AddThemeConstantOverride("separation", 6);
        _section = Ui.Lbl("", 12, Ui.Accent);
        _title = Ui.Lbl("", 24, Ui.Text);
        var coachTag = Ui.Lbl("COACH SAYS", 11, Ui.Sub);
        _padLine = Rich(17);
        _keyLine = Rich(14);
        _tip = Ui.Lbl("", 14, Ui.Sub);
        _tip.CustomMinimumSize = new Vector2(380, 0);
        _bar = new ProgressBar { MinValue = 0, MaxValue = 1, ShowPercentage = false, CustomMinimumSize = new Vector2(380, 10) };
        _bar.AddThemeStyleboxOverride("background", Ui.Box(new Color(1, 1, 1, .08f), null, 5, 0));
        _bar.AddThemeStyleboxOverride("fill", Ui.Box(Ui.Accent, null, 5, 0));
        var row = new HBoxContainer();
        _progressText = Ui.Lbl("", 14, Ui.Text);
        _progressText.AutowrapMode = TextServer.AutowrapMode.Off;
        _feedback = Ui.Lbl("", 15, Ui.Accent);
        _feedback.AutowrapMode = TextServer.AutowrapMode.Off;
        _feedback.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        _feedback.HorizontalAlignment = HorizontalAlignment.Right;
        row.AddChild(_progressText); row.AddChild(_feedback);
        _footer = Rich(11);
        _footer.Text = ToBbcode("Skip drill: hold [LB]+[RB] or <N>   ·   Back: <B>   ·   Quit: [MENU] / <Esc>");
        _footer.AddThemeColorOverride("default_color", Ui.Sub);

        v.AddChild(_section); v.AddChild(_title); v.AddChild(coachTag);
        v.AddChild(_padLine); v.AddChild(_keyLine); v.AddChild(_tip);
        v.AddChild(_bar); v.AddChild(row); v.AddChild(_footer);

        _coachPanel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        var box = Ui.Box(new Color(.035f, .06f, .07f, .90f), Ui.Accent, 16, 2);
        box.ContentMarginLeft = 18; box.ContentMarginRight = 18; box.ContentMarginTop = 14; box.ContentMarginBottom = 12;
        _coachPanel.AddThemeStyleboxOverride("panel", box);
        _coachPanel.AddChild(v);
        _coachPanel.Position = new Vector2(18, 108);
        _coachPanel.CustomMinimumSize = new Vector2(420, 0);
        AddChild(_coachPanel);
    }

    private void BuildShootout()
    {
        var v = new VBoxContainer();
        v.AddThemeConstantOverride("separation", 4);
        v.AddChild(Ui.Lbl("PENALTY SHOOTOUT", 13, Ui.Accent));
        v.SizeFlagsVertical = Control.SizeFlags.ShrinkBegin;
        _shootScore = Ui.Lbl("", 26, Ui.Text);
        _shootScore.HorizontalAlignment = HorizontalAlignment.Center;
        _shootTally = Ui.Lbl("", 20, Ui.Text);
        _shootTally.HorizontalAlignment = HorizontalAlignment.Center;
        _shootHint = Rich(15);
        // Wrapping + FitContent measured at zero width reports a huge height in
        // Godot 4 and stretched the whole panel down the screen: keep it one line.
        _shootHint.AutowrapMode = TextServer.AutowrapMode.Off;
        _shootHint.CustomMinimumSize = new Vector2(560, 24);
        v.AddChild(_shootScore); v.AddChild(_shootTally); v.AddChild(_shootHint);
        foreach (var child in v.GetChildren())
            if (child is Label lbl) lbl.AutowrapMode = TextServer.AutowrapMode.Off;
        _shootPanel = new PanelContainer { MouseFilter = Control.MouseFilterEnum.Ignore };
        var box = Ui.Box(new Color(.035f, .06f, .07f, .90f), Ui.Accent, 14, 2);
        box.ContentMarginLeft = 16; box.ContentMarginRight = 16; box.ContentMarginTop = 10; box.ContentMarginBottom = 10;
        _shootPanel.AddThemeStyleboxOverride("panel", box);
        _shootPanel.AddChild(v);
        _shootPanel.CustomMinimumSize = new Vector2(600, 0);
        AddChild(_shootPanel);
    }

    private static string Dots(List<bool> kicks)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < Math.Max(5, kicks.Count); i++)
            sb.Append(i < kicks.Count ? (kicks[i] ? "● " : "✕ ") : "○ ");
        return sb.ToString().TrimEnd();
    }

    public void UpdateOverlay(MatchEngine e, TrainingCoach? coach)
    {
        if (_mode == MatchEngine.ModeTraining && coach != null && _coachPanel != null)
        {
            var l = coach.Current;
            if (_shownLesson != coach.Index)
            {
                _shownLesson = coach.Index;
                _section!.Text = $"TRAINING · {l.Section} · {coach.Index + 1} / {coach.Lessons.Count}";
                _title!.Text = l.Title;
                _padLine!.Text = "[color=#8fb3ad][b]PAD [/b][/color] " + ToBbcode(l.Pad);
                _keyLine!.Text = "[color=#8fb3ad][b]KEYS[/b][/color]  " + ToBbcode(l.Keys);
                _tip!.Text = l.Tip;
                _bar!.Visible = l.Goal != LessonGoal.FreePlay;
                _coachPanel.ResetSize();
            }
            _bar!.Value = l.Target > 0 ? coach.Progress / l.Target : 0;
            _progressText!.Text = coach.ProgressText();
            _feedback!.Text = coach.LastFeedback;
            // Flash the border on success.
            float pulse = coach.CelebrateTimer > 0f ? 1f : 0f;
            _coachPanel.Modulate = new Color(1, 1, 1, 1f).Lerp(new Color(1.25f, 1.35f, 1.25f, 1f), pulse);
        }
        else if (_mode == MatchEngine.ModeShootout && _shootPanel != null)
        {
            var S = e.State;
            var vp = GetViewport().GetVisibleRect().Size;
            _shootPanel.Position = new Vector2((vp.X - _shootPanel.Size.X) * .5f, 96);
            string home = Clubs.All[Math.Clamp(e.Options.HomeClub, 0, Clubs.All.Length - 1)].Short;
            string away = Clubs.All[Math.Clamp(e.Options.AwayClub, 0, Clubs.All.Length - 1)].Short;
            _shootScore!.Text = $"{home}  {S.Score[0]} - {S.Score[1]}  {away}";
            _shootTally!.Text = $"{Dots(S.ShootoutHome)}     |     {Dots(S.ShootoutAway)}";
            string hint;
            if (S.Phase == Phase.FullTime)
                hint = S.Score[0] > S.Score[1] ? "You win the shootout!" : "You lost the shootout.";
            else if (S.ShootoutTakerSide == 0)
                hint = S.ShootoutShotTaken ? "…"
                    : "YOUR KICK: aim [LS] at a post, hold [X], release to shoot   ·   Keys: <WASD> + <Space>";
            else
                hint = "Their kick — your keeper is on the line.";
            string text = "[center]" + ToBbcode(hint) + "[/center]";
            if (_shootHint!.Text != text)
            {
                _shootHint.Text = text;
                _shootPanel.ResetSize();       // shrink to the new content
            }
        }
    }
}
