// Arena FC - first-launch graphics benchmark (RenderProfile "auto").
// Plays a few seconds of a real 11-a-side match at the Ultra tier behind a "Tuning graphics" card,
// measures the GPU time of each frame (viewport render-time counters: v-sync does not hide it), and
// saves the tier this machine carries.  Too slow for Forward+ -> restart on the GL renderer.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public sealed partial class GraphicsBenchmark : Node
{
    public Action? Done;
    private MatchView? _view;
    private Label? _label;
    private readonly List<float> _gpu = new();
    private int _frame;
    private ulong _startMs;
    private const int Warmup = 45, Samples = 150;
    private const ulong MaxMs = 9000;      // a very slow machine is judged on what it managed

    public override void _Ready()
    {
        Name = "GraphicsBenchmark";
        RenderProfile.ForceTier("ultra");
        _view = new MatchView();
        _view.Init(new MatchOptions { TeamSize = 11, Seed = 77, TimeSpeed = 15f, Lighting = "night" }, null, () => { });
        AddChild(_view);
        RenderingServer.ViewportSetMeasureRenderTime(GetViewport().GetViewportRid(), true);
        var layer = new CanvasLayer { Layer = 100 };
        AddChild(layer);
        var bg = new ColorRect { Color = new Color(0.03f, 0.05f, 0.08f, .82f) };
        bg.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(bg);
        _label = new Label
        {
            Text = "TUNING GRAPHICS FOR THIS DEVICE…", HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
        };
        _label.AddThemeFontSizeOverride("font_size", 28);
        _label.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(_label);
        _startMs = Time.GetTicksMsec();
    }

    public override void _Process(double delta)
    {
        if (_view == null) return;
        _frame++;
        if (_frame > Warmup)
        {
            var rid = GetViewport().GetViewportRid();
            float gpu = (float)RenderingServer.ViewportGetMeasuredRenderTimeGpu(rid);
            float cpu = (float)RenderingServer.ViewportGetMeasuredRenderTimeCpu(rid);
            _gpu.Add(Math.Max(gpu, cpu));
        }
        if (_label != null) _label.Text = $"TUNING GRAPHICS FOR THIS DEVICE…  {Math.Min(100, _gpu.Count * 100 / Samples)}%";
        bool timeUp = Time.GetTicksMsec() - _startMs > MaxMs;
        if (_gpu.Count < Samples && !timeUp) return;
        Finish();
    }

    private void Finish()
    {
        var view = _view;
        _view = null;
        // 80th percentile: judge the busy frames, not the average
        float ms = _gpu.Count > 0 ? _gpu.OrderBy(x => x).ElementAt(Math.Min(_gpu.Count - 1, _gpu.Count * 8 / 10)) : 99f;
        if (_gpu.Count < 20) ms = 99f;   // couldn't even manage 20 frames in the time allowed
        RenderProfile.RecordBenchmark(ms);
        GD.Print($"ARENA_FC_BENCHMARK gpu_p80_ms={ms:0.00} frames={_gpu.Count} -> {RenderProfile.Measured}");
        view?.QueueFree();
        if (RenderProfile.EnsureRenderer()) return;      // Performance: restarting on the GL renderer
        Done?.Invoke();
    }
}
