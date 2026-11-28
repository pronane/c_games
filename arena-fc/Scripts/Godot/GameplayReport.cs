using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

/// <summary>
/// QA: `--gameplay-report PATH` makes a match write what happened while it ran (usually
/// alongside `--ai-vs-ai` and Godot's `--write-movie`), so CI can check a recording of the
/// game against targets: was there football (passes, shots, the ball and players moving,
/// possession changing), did the players animate (clips used, planted-foot slide, lock
/// coverage, contact timing), and what each frame cost (simulation step, rig sync).
/// Timings come from the CI machine and software rendering, so they are compared with
/// generous budgets; the football and animation numbers are the real checks.
/// </summary>
public sealed class GameplayReport
{
    public static string? PathFromArgs()
    {
        var args = OS.GetCmdlineUserArgs();
        int i = Array.IndexOf(args, "--gameplay-report");
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    private readonly string _path;
    private readonly List<double> _stepMs = new(), _syncMs = new(), _frameMs = new();
    private readonly HashSet<string> _clips = new(StringComparer.Ordinal);
    private int _frames, _ticksStart = -1, _ticks, _possessionChanges, _lastPossTeam = -2;
    private float _clockStart = -1f, _clock;
    private double _ballDistance, _playerDistance;
    private System.Numerics.Vector3 _lastBall;
    private System.Numerics.Vector3[]? _lastPlayers;
    private bool _written;

    public GameplayReport(string path) { _path = path; }

    public static long Now() => Stopwatch.GetTimestamp();
    public static double Ms(long since) => (Stopwatch.GetTimestamp() - since) * 1000.0 / Stopwatch.Frequency;

    public void AddStep(double ms) => _stepMs.Add(ms);
    public void AddSync(double ms) => _syncMs.Add(ms);

    /// <summary>Once per physics frame, after the rigs are synced.</summary>
    public void Frame(MatchEngine engine, CharacterRig[] rigs, double frameDelta)
    {
        var s = engine.State;
        _frames++;
        _frameMs.Add(frameDelta * 1000.0);
        if (_ticksStart < 0) { _ticksStart = engine.CurrentTick; _clockStart = s.Clock; _lastBall = s.Ball.Pos; }
        _ticks = engine.CurrentTick - _ticksStart;
        _clock = s.Clock - _clockStart;
        var ball = s.Ball.Pos;
        _ballDistance += Mx.FlatDist(ball, _lastBall);
        _lastBall = ball;
        if (_lastPlayers == null || _lastPlayers.Length != s.Players.Length)
            _lastPlayers = s.Players.Select(p => p.Pos).ToArray();
        for (int i = 0; i < s.Players.Length; i++)
        {
            _playerDistance += Mx.FlatDist(s.Players[i].Pos, _lastPlayers[i]);
            _lastPlayers[i] = s.Players[i].Pos;
        }
        int team = s.Ball.Owner >= 0 && s.Ball.Owner < s.Players.Length ? s.Players[s.Ball.Owner].Team : -1;
        if (team >= 0)
        {
            if (_lastPossTeam >= 0 && team != _lastPossTeam) _possessionChanges++;
            _lastPossTeam = team;
        }
        foreach (var r in rigs)
            if (r?.Soccer != null && r.Soccer.CurrentClip.Length > 0) _clips.Add(r.Soccer.CurrentClip);
    }

    public void Write(MatchEngine engine, CharacterRig[] rigs, ArenaFC.Core.Animation.AnimationMetrics metrics)
    {
        if (_written) return;
        _written = true;
        var s = engine.State;
        int plantFrames = 0, lockedFrames = 0; double contractSlide = 0; int rigsWithPlants = 0;
        foreach (var r in rigs)
        {
            if (r?.Soccer == null) continue;
            plantFrames += r.Soccer.PlantFrames;
            lockedFrames += r.Soccer.LockedPlantFrames;
            if (r.Soccer.PlantFrames > 0) { contractSlide += r.Soccer.ContractPlantSlide; rigsWithPlants++; }
        }
        static double P(List<double> v, double q)
        {
            if (v.Count == 0) return 0;
            var a = v.OrderBy(x => x).ToList();
            return a[Math.Clamp((int)Math.Ceiling(q * a.Count) - 1, 0, a.Count - 1)];
        }
        var events = engine.Events.GroupBy(e => e.Kind.ToString()).ToDictionary(g => g.Key, g => g.Count());
        double seconds = _frameMs.Sum() / 1000.0;
        var report = new Dictionary<string, object>
        {
            ["frames"] = _frames,
            ["seconds"] = Math.Round(seconds, 2),
            ["sim_ticks"] = _ticks,
            ["game_clock_seconds"] = Math.Round(_clock, 1),
            ["players"] = s.Players.Length,
            ["score"] = new[] { s.Score[0], s.Score[1] },
            ["shots"] = s.Shots[0] + s.Shots[1],
            ["shots_on_target"] = s.ShotsOnTarget[0] + s.ShotsOnTarget[1],
            ["passes"] = s.Passes[0] + s.Passes[1],
            ["possession_changes"] = _possessionChanges,
            ["ball_distance_m"] = Math.Round(_ballDistance, 1),
            ["player_distance_m"] = Math.Round(_playerDistance, 1),
            ["events"] = events,
            ["distinct_clips"] = _clips.Count,
            ["clips"] = _clips.OrderBy(c => c).ToArray(),
            ["planted_foot_slide_mps"] = Math.Round(metrics.AvgFootSlide, 4),
            ["planted_foot_slide_samples"] = metrics.Samples,
            ["plant_window_lock_coverage"] = plantFrames > 0 ? Math.Round((double)lockedFrames / plantFrames, 4) : 0.0,
            ["plant_window_slide_mps_all_frames"] = rigsWithPlants > 0 ? Math.Round(contractSlide / rigsWithPlants, 4) : 0.0,
            ["footsteps"] = metrics.FootstepEvents,
            ["clip_transitions"] = metrics.TransitionEvents,
            ["avg_transition_discontinuity"] = Math.Round(metrics.AvgTransitionDiscontinuity, 4),
            ["contact_events"] = metrics.ContactEvents,
            ["avg_contact_frame_error"] = Math.Round(metrics.AvgContactFrameError, 3),
            ["sim_step_ms_p50"] = Math.Round(P(_stepMs, .5), 3),
            ["sim_step_ms_p95"] = Math.Round(P(_stepMs, .95), 3),
            ["sim_step_ms_max"] = Math.Round(P(_stepMs, 1), 3),
            ["rig_sync_ms_p50"] = Math.Round(P(_syncMs, .5), 3),
            ["rig_sync_ms_p95"] = Math.Round(P(_syncMs, .95), 3),
            ["rig_sync_ms_max"] = Math.Round(P(_syncMs, 1), 3),
            ["timing_note"] = "CI machine with software rendering; compare against generous budgets only",
        };
        var dir = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(_path));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(_path, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        GD.Print($"ARENA_FC_GAMEPLAY_REPORT {_path}");
    }
}
