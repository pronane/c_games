// Arena FC — Replay & Highlights system (Phase 5).
// Instant replay, slow-motion, highlight reel, spectator mode.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Replay camera angles.</summary>
public enum ReplayCamera
{
    Broadcast,
    Tactical,
    GoalLine,
    Spider,
    PlayerCam,
}

/// <summary>A recorded highlight moment.</summary>
public class Highlight
{
    public string Description = "";
    public int StartTick;
    public int EndTick;
    public EventKind Kind;
    public float Importance; // 0-1
    public ReplayCamera BestCamera;
}

/// <summary>Replay state.</summary>
public class ReplayState
{
    public bool IsReplaying;
    public bool IsSlowMotion;
    public float PlaybackSpeed = 1f;
    public int CurrentTick;
    public int StartTick;
    public int EndTick;
    public ReplayCamera Camera = ReplayCamera.Broadcast;
    public bool IsSpectatorMode;
}

/// <summary>Replay and highlight manager.</summary>
public class ReplaySystem
{
    private readonly List<Highlight> _highlights = new();
    private readonly List<MatchEvent> _eventBuffer = new();
    private int _tickCounter;
    private const int BufferSize = 600; // 10 seconds at 60Hz

    public ReplayState State = new();
    public IReadOnlyList<Highlight> Highlights => _highlights;
    // Feature 8: Replay editor
    public ReplayEditor Editor = new();

    /// <summary>Record an event for potential replay.</summary>
    public void RecordEvent(MatchEvent evt, int tick)
    {
        _eventBuffer.Add(evt);
        if (_eventBuffer.Count > 100) _eventBuffer.RemoveAt(0);

        // Auto-create highlights for big moments
        if (evt.Kind == EventKind.Goal)
        {
            _highlights.Add(new Highlight
            {
                Description = evt.Text,
                StartTick = Math.Max(0, tick - 300), // 5s before
                EndTick = tick + 300, // 5s after
                Kind = evt.Kind,
                Importance = 1f,
                BestCamera = ReplayCamera.GoalLine,
            });
        }
        else if (evt.Kind == EventKind.Shot)
        {
            _highlights.Add(new Highlight
            {
                Description = evt.Text,
                StartTick = Math.Max(0, tick - 180),
                EndTick = tick + 180,
                Kind = evt.Kind,
                Importance = 0.7f,
                BestCamera = ReplayCamera.Broadcast,
            });
        }
        else if (evt.Kind == EventKind.Save)
        {
            _highlights.Add(new Highlight
            {
                Description = evt.Text,
                StartTick = Math.Max(0, tick - 120),
                EndTick = tick + 120,
                Kind = evt.Kind,
                Importance = 0.8f,
                BestCamera = ReplayCamera.GoalLine,
            });
        }
    }

    /// <summary>Start instant replay of a highlight.</summary>
    public void StartReplay(Highlight highlight)
    {
        State.IsReplaying = true;
        State.StartTick = highlight.StartTick;
        State.EndTick = highlight.EndTick;
        State.CurrentTick = highlight.StartTick;
        State.Camera = highlight.BestCamera;
        State.PlaybackSpeed = 1f;
        State.IsSlowMotion = false;
    }

    /// <summary>Start slow-motion replay.</summary>
    public void StartSlowMotion(Highlight highlight)
    {
        StartReplay(highlight);
        State.IsSlowMotion = true;
        State.PlaybackSpeed = 0.25f; // quarter speed
    }

    /// <summary>Stop replay and return to live.</summary>
    public void StopReplay()
    {
        State.IsReplaying = false;
        State.IsSlowMotion = false;
        State.PlaybackSpeed = 1f;
    }

    /// <summary>Set replay camera angle.</summary>
    public void SetCamera(ReplayCamera camera)
    {
        State.Camera = camera;
    }

    /// <summary>Step replay forward by one tick (frame-by-frame).</summary>
    public void StepForward()
    {
        if (State.IsReplaying && State.CurrentTick < State.EndTick)
        {
            State.CurrentTick++;
        }
    }

    /// <summary>Step replay backward by one tick.</summary>
    public void StepBackward()
    {
        if (State.IsReplaying && State.CurrentTick > State.StartTick)
        {
            State.CurrentTick--;
        }
    }

    /// <summary>Get top highlights sorted by importance.</summary>
    public List<Highlight> GetTopHighlights(int count = 5)
    {
        return _highlights.OrderByDescending(h => h.Importance).Take(count).ToList();
    }

    /// <summary>Enable spectator mode (AI vs AI, no human input).</summary>
    public void EnableSpectatorMode()
    {
        State.IsSpectatorMode = true;
    }

    /// <summary>Disable spectator mode.</summary>
    public void DisableSpectatorMode()
    {
        State.IsSpectatorMode = false;
    }

    /// <summary>Clear all highlights (new match).</summary>
    public void Clear()
    {
        _highlights.Clear();
        _eventBuffer.Clear();
        _tickCounter = 0;
        StopReplay();
    }

    /// <summary>Tick counter (call each physics frame).</summary>
    public void Tick()
    {
        _tickCounter++;
        if (State.IsReplaying)
        {
            State.CurrentTick += (int)(State.PlaybackSpeed * 1);
            if (State.CurrentTick >= State.EndTick)
            {
                StopReplay();
            }
        }
    }
}
