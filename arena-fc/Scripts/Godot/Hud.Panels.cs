// Arena FC - pause-menu panels: substitutions, in-match analysis and photo mode.
//
// The engine has had a bench since this branch (MatchEngine.Substitute), but the
// HUD had no way to reach it, so substitutions were "auto-sub only" - i.e. none.
// These panels are the caller.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Hud
{
    private CanvasLayer? _panelLayer;
    private readonly PhotoMode _photo = new();
    private int _subOutSlot = -1;
    private bool _hudHiddenForPhoto;

    /// <summary>Full-screen menu panel over the frozen match.</summary>
    private Control PanelRoot(string name)
    {
        ClosePanel();
        _panelLayer = new CanvasLayer { Layer = 60, Name = name + "Layer" };
        AddChild(_panelLayer);
        var dim = new ColorRect { Color = new Color(.01f, .03f, .035f, .86f) };
        dim.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _panelLayer.AddChild(dim);
        var root = new Control { Name = name, MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        _panelLayer.AddChild(root);
        return root;
    }

    private void PlacePanel(Control root, Control body)
    {
        var scroll = new ScrollContainer
        {
            CustomMinimumSize = new Vector2(560, 360),
            SizeFlagsHorizontal = Control.SizeFlags.ExpandFill,
            SizeFlagsVertical = Control.SizeFlags.ExpandFill,
        };
        body.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        scroll.AddChild(body);
        var panel = Ui.PanelC(scroll, Ui.Panel);
        panel.AnchorLeft = panel.AnchorRight = panel.AnchorTop = panel.AnchorBottom = .5f;
        panel.OffsetLeft = -320; panel.OffsetTop = -240;
        panel.OffsetRight = 320; panel.OffsetBottom = 240;
        root.AddChild(panel);
        PadMenuNavigator.Active = true;
        Ui.FocusFirst(body);
    }

    public void ClosePanel()
    {
        if (_panelLayer == null) { PadMenuNavigator.Active = Paused; return; }
        _panelLayer.QueueFree();
        _panelLayer = null;
        _subOutSlot = -1;
        PadMenuNavigator.Active = Paused;
        if (Paused && _pauseButtons != null) Ui.FocusFirst(_pauseButtons);
    }

    public bool PanelOpen => _panelLayer != null;

    // ------------------------------------------------------- substitutions

    public void ShowSubstitutions()
    {
        var e = _engine;
        if (e == null) return;
        var root = PanelRoot("Substitutions");
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("SUBSTITUTIONS", 26, Ui.Accent));
        v.AddChild(Ui.Lbl($"Home {e.SubsLeft(0)} of {MatchEngine.MaxSubstitutions} left  ·  " +
                          $"Away {e.SubsLeft(1)} of {MatchEngine.MaxSubstitutions} left", 14, Ui.Sub));

        const int side = 0;
        var bench = e.BenchOf(side);
        if (e.OnlineLocked)
        {
            v.AddChild(Ui.Lbl("Substitutions are disabled in online matches.", 15, Ui.Sub));
            v.AddChild(Ui.Btn("BACK", () =>
            {
                ClosePanel();
                SetPaused(true);
            }, true));
            PlacePanel(root, v);
            return;
        }
        if (bench.Count == 0)
        {
            v.AddChild(Ui.Lbl("No substitutes available (bench size 0 in Match Settings).", 15, Ui.Sub));
            v.AddChild(Ui.Btn("BACK", () => { ClosePanel(); SetPaused(true); }, true));
            PlacePanel(root, v);
            return;
        }

        if (_subOutSlot < 0)
        {
            v.AddChild(Ui.Lbl("STEP 1 — who comes off?", 15, Ui.Sub));
            var onPitch = e.State.Players
                .Where(p => p.Team == side && !p.IsKeeper && !p.SentOff)
                .OrderBy(p => p.Stamina)
                .ToList();
            foreach (var p in onPitch)
            {
                int slot = p.Slot;
                v.AddChild(Ui.Btn(
                    $"#{p.Spec.Number,2} {MatchReport.Display(p),-16} {p.Role,-10}  stamina {p.Stamina * 100f:0}%",
                    () => { _subOutSlot = slot; ShowSubstitutions(); }));
            }
        }
        else
        {
            var off = e.State.Players.FirstOrDefault(p => p.Team == side && p.Slot == _subOutSlot);
            v.AddChild(Ui.Lbl(off == null ? "Who replaces them?" : $"STEP 2 — {MatchReport.Display(off)} comes off. Who replaces them?", 15, Ui.Sub));
            for (int i = 0; i < bench.Count; i++)
            {
                int bi = i;
                var b = bench[i];
                string role = b.Role switch
                {
                    Role.Goalkeeper => "GK", Role.Defender => "DEF",
                    Role.Midfielder => "MID", _ => "FWD",
                };
                v.AddChild(Ui.Btn($"#{b.Number,2} {b.Name,-16} {role}  → bring on", () =>
                {
                    if (e.Substitute(side, _subOutSlot, bi)) ShowToast($"Substitution: {b.Name} on");
                    else ShowToast("Substitution rejected");
                    _subOutSlot = -1;
                    ShowSubstitutions();
                }));
            }
            v.AddChild(Ui.Btn("CANCEL", () => { _subOutSlot = -1; ShowSubstitutions(); }));
        }
        v.AddChild(Ui.Btn("BACK", () => { ClosePanel(); SetPaused(true); }, true));
        PlacePanel(root, v);
    }

    // ------------------------------------------------------------ analysis

    public void ShowAnalysis()
    {
        var e = _engine;
        if (e == null) return;
        var s = e.State;
        var root = PanelRoot("Analysis");
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("MATCH ANALYSIS", 26, Ui.Accent));

        float possTotal = MathF.Max(1f, s.PossessionTime[0] + s.PossessionTime[1]);
        int possHome = (int)MathF.Round(s.PossessionTime[0] / possTotal * 100f);
        v.AddChild(Ui.Lbl($"Score {s.Score[0]} - {s.Score[1]}   ·   possession {possHome}% - {100 - possHome}%", 16));
        v.AddChild(Ui.Lbl($"xG  {s.Xg[0]:0.00} - {s.Xg[1]:0.00}   ·   {MatchReport.Verdict(s)}", 15, Ui.Sub));
        v.AddChild(Ui.Lbl($"Shots {s.Shots[0]}-{s.Shots[1]}  (on target {s.ShotsOnTarget[0]}-{s.ShotsOnTarget[1]})" +
                          $"  ·  passes {s.Passes[0]}-{s.Passes[1]}  ·  fouls {s.Fouls[0]}-{s.Fouls[1]}", 14, Ui.Sub));

        v.AddChild(Ui.Lbl("RATINGS", 15, Ui.Accent));
        var best = MatchReport.Ratings(s, 0).Take(5).ToList();
        var awayBest = MatchReport.Ratings(s, 1).Take(3).ToList();
        foreach (var (p, r) in best)
            v.AddChild(Ui.Lbl($"{MatchReport.Display(p),-18} {r:0.0}", 14, Ui.Text));
        v.AddChild(Ui.Lbl("", 6));
        foreach (var (p, r) in awayBest)
            v.AddChild(Ui.Lbl($"{MatchReport.Display(p),-18} {r:0.0}", 14, Ui.Sub));

        v.AddChild(Ui.Lbl("HEAT MAP (play concentrated where it is bright)", 15, Ui.Accent));
        v.AddChild(HeatGrid(e.Heat));
        v.AddChild(Ui.Btn("BACK", () => { ClosePanel(); SetPaused(true); }, true));
        PlacePanel(root, v);
    }

    /// <summary>9x5 grid of colour swatches, sampled from the engine's heat map.</summary>
    internal static Control HeatGrid(HeatMap heat)
    {
        var grid = MatchReport.HeatGrid(heat, 9, 5);
        int max = 1;
        foreach (int c in grid) max = Math.Max(max, c);
        var box = new VBoxContainer { CustomMinimumSize = new Vector2(9 * 54, 5 * 26) };
        for (int row = 0; row < 5; row++)
        {
            var line = new HBoxContainer();
            for (int col = 0; col < 9; col++)
            {
                // Pitch runs left-to-right; low counts stay dark green, high counts glow.
                float t = grid[col, 4 - row] / (float)max;
                var colour = new Color(.05f + .95f * t, .22f + .68f * t, .10f, .35f + .6f * t);
                line.AddChild(new ColorRect
                {
                    Color = colour, CustomMinimumSize = new Vector2(52, 24),
                });
            }
            box.AddChild(line);
        }
        return box;
    }

    // ---------------------------------------------------------- photo mode

    public bool PhotoModeActive => _photo.IsActive;

    public void TogglePhotoMode()
    {
        _photo.IsActive = !_photo.IsActive;
        if (_photo.IsActive) _photo.CycleCamera();
        SetHudHidden(_photo.IsActive);
        ShowToast(_photo.IsActive
            ? $"PHOTO MODE — camera {_photo.CameraIndex + 1}/7 · press P or Esc to exit"
            : "Photo mode off");
    }

    private void SetHudHidden(bool hidden)
    {
        if (hidden == _hudHiddenForPhoto) return;
        _hudHiddenForPhoto = hidden;
        foreach (Node child in GetChildren())
        {
            if (child == _pauseMenu || child == _panelLayer) continue;
            if (child is CanvasItem item) item.Visible = !hidden;
        }
    }
}
