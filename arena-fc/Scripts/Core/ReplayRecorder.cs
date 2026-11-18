// Arena FC - replay recorder: captures match state snapshots for slow-mo
// playback and camera cuts.  Phase 3.5.
//
// Records player positions, ball state and camera angles at 10 Hz into a
// ring buffer (last 30 seconds).  On a goal or highlight, the recorder
// plays back the last 5 seconds at 0.25x speed with a cinematic camera.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>A single replay frame: player positions + ball state.</summary>
public sealed class ReplayFrame
{
    public float Time;
    public Vector3[] PlayerPos = Array.Empty<Vector3>();
    public Vector3[] PlayerFacing = Array.Empty<Vector3>();
    public Vector3 BallPos, BallVel;
    public int BallOwner;
    public string[] PlayerActions = Array.Empty<string>();
}

/// <summary>Records match state for replay/slow-mo playback.</summary>
public sealed class ReplayRecorder
{
    private const int MaxFrames = 300; // 30s at 10 Hz
    private readonly List<ReplayFrame> _frames = new();
    private float _accumulator;

    public bool IsRecording { get; private set; }
    public bool IsPlaying { get; private set; }
    public float PlaybackSpeed = 1f;
    public int PlaybackIndex;

    public void StartRecording() => IsRecording = true;
    public void StopRecording() => IsRecording = false;

    /// <summary>Record one frame (called at 10 Hz from the match loop).</summary>
    public void Record(MatchState state, float dt)
    {
        if (!IsRecording) return;
        _accumulator += dt;
        if (_accumulator < 0.1f) return; // 10 Hz
        _accumulator = 0f;
        var frame = new ReplayFrame
        {
            Time = state.Clock,
            PlayerPos = new Vector3[state.Players.Length],
            PlayerFacing = new Vector3[state.Players.Length],
            PlayerActions = new string[state.Players.Length],
            BallPos = state.Ball.Pos,
            BallVel = state.Ball.Vel,
            BallOwner = state.Ball.Owner,
        };
        for (int i = 0; i < state.Players.Length; i++)
        {
            frame.PlayerPos[i] = state.Players[i].Pos;
            frame.PlayerFacing[i] = state.Players[i].Facing;
            frame.PlayerActions[i] = state.Players[i].Action;
        }
        _frames.Add(frame);
        if (_frames.Count > MaxFrames) _frames.RemoveAt(0);
    }

    /// <summary>Start replaying the last N seconds (for goals/highlights).</summary>
    public void PlayLast(float seconds, float speed = 0.25f)
    {
        if (_frames.Count < 2) return;
        int framesToPlay = Math.Min((int)(seconds * 10f), _frames.Count);
        PlaybackIndex = _frames.Count - framesToPlay;
        PlaybackSpeed = speed;
        IsPlaying = true;
    }

    public ReplayFrame? CurrentFrame => IsPlaying && PlaybackIndex < _frames.Count
        ? _frames[PlaybackIndex] : null;

    public void Advance(float dt)
    {
        if (!IsPlaying) return;
        // Advance at playback speed (10 Hz * speed).
        _accumulator += dt * PlaybackSpeed;
        if (_accumulator >= 0.1f)
        {
            _accumulator = 0f;
            PlaybackIndex++;
            if (PlaybackIndex >= _frames.Count)
            {
                IsPlaying = false;
                PlaybackIndex = 0;
            }
        }
    }

    public void Stop() { IsPlaying = false; PlaybackIndex = 0; }
    public void Clear() { _frames.Clear(); PlaybackIndex = 0; }
    public int FrameCount => _frames.Count;
}
