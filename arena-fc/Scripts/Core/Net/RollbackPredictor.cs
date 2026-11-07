// Arena FC - client-side rollback prediction for the 20 Hz authoritative server.
//
// The local human is simulated immediately (zero perceived RTT).  Every few frames
// a snapshot arrives for an older tick; we rewind to that tick, correct the
// state with the server's authoritative positions, then re-run the unconfirmed
// tail using the recorded inputs.  Re-simulation is capped at
// NetProtocol.MaxRollbackTicks; anything older degrades to a bounded hard reset.
using System;
using System.Collections.Generic;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public sealed class ReconcileResult
{
    public bool Applied;
    public bool HardReset;
    public float Error;
    public int Replayed;
}

public sealed class RollbackPredictor
{
    private readonly Dictionary<int, Dictionary<int, PlayerCommand>> _buffer = new();
    private readonly Dictionary<int, EngineCheckpoint> _checkpoints = new();
    private int _confirmedTick;
    private int _predictedTick;

    public RollbackPredictor(MatchOptions? options = null)
    {
        Engine = new MatchEngine(options ?? new MatchOptions());
        _checkpoints[0] = Engine.Capture();
    }

    public MatchEngine Engine { get; }

    /// <summary>Keep this many input frames / checkpoints (a little over one second).</summary>
    public int MaxHistory { get; set; } = NetProtocol.MaxRollbackTicks * 5;

    public int PredictedTick => _predictedTick;
    public int ConfirmedTick => _confirmedTick;
    public int BufferedFrames => _buffer.Count;
    public int ReplayedTicks { get; private set; }
    public int Corrections { get; private set; }

    /// <summary>Start (or restart) from a fully authoritative engine state.</summary>
    public void HardReset(MatchEngine authoritative, int tick)
    {
        Engine.CopyFrom(authoritative);
        Engine.CurrentTick = tick;
        _confirmedTick = tick;
        _predictedTick = tick;
        _buffer.Clear();
        _checkpoints.Clear();
        _checkpoints[tick] = Engine.Capture();
    }

    /// <summary>Advance one local tick with the local player's freshly sampled input.</summary>
    public void Predict(Dictionary<int, PlayerCommand> cmds)
    {
        _predictedTick++;
        _buffer[_predictedTick] = new Dictionary<int, PlayerCommand>(cmds);
        Engine.StepOneTick(cmds);
        _checkpoints[_predictedTick] = Engine.Capture();
        Trim();
    }

    /// <summary>Correct against an authoritative snapshot for `confirmedTick`.</summary>
    public ReconcileResult Reconcile(int confirmedTick, MatchState authoritativeState,
        uint rng, float globalTime,
        Dictionary<int, Dictionary<int, PlayerCommand>>? serverInputs = null,
        int local = -1)
    {
        var res = new ReconcileResult();
        // Old / duplicate snapshots must not rewind the client.
        if (confirmedTick <= _confirmedTick) return res;

        res.Error = MaxError(Engine.State, authoritativeState);
        int tail = _predictedTick - confirmedTick;
        if (tail > NetProtocol.MaxRollbackTicks ||
            !_checkpoints.TryGetValue(confirmedTick, out var ck))
        {
            Engine.RestoreFrom(authoritativeState, rng, globalTime, confirmedTick);
            _confirmedTick = confirmedTick;
            _predictedTick = confirmedTick;
            _buffer.Clear();
            _checkpoints.Clear();
            _checkpoints[confirmedTick] = Engine.Capture();
            res.Applied = true;
            res.HardReset = true;
            Corrections++;
            return res;
        }

        // The checkpoint holds the full internal state at that tick; the wire
        // snapshot only holds the renderer fields, so overlay those on top.
        Engine.Restore(ck);
        Engine.ApplyAuthoritative(authoritativeState, rng, globalTime, confirmedTick);

        for (int t = confirmedTick + 1; t <= _predictedTick; t++)
        {
            if (serverInputs != null && serverInputs.TryGetValue(t, out var authoritative))
                _buffer[t] = new Dictionary<int, PlayerCommand>(authoritative);
            else if (!_buffer.TryGetValue(t, out authoritative))
                authoritative = new Dictionary<int, PlayerCommand>();
            Engine.StepOneTick(authoritative);
            _checkpoints[t] = Engine.Capture();
            res.Replayed++;
        }
        ReplayedTicks += res.Replayed;
        _confirmedTick = confirmedTick;
        Corrections++;
        res.Applied = true;
        return res;
    }

    /// <summary>Largest pitch-space disagreement between two states, in metres.</summary>
    public static float MaxError(MatchState a, MatchState b)
    {
        float m = 0f;
        int n = Math.Min(a.Players.Length, b.Players.Length);
        for (int i = 0; i < n; i++)
            m = MathF.Max(m, Mx.FlatDist(a.Players[i].Pos, b.Players[i].Pos));
        m = MathF.Max(m, (a.Ball.Pos - b.Ball.Pos).Length());
        return m;
    }

    private void Trim()
    {
        int cutoff = _predictedTick - MaxHistory;
        var old = new List<int>();
        foreach (int k in _buffer.Keys) if (k < cutoff) old.Add(k);
        foreach (int k in old) _buffer.Remove(k);
        old.Clear();
        foreach (int k in _checkpoints.Keys) if (k < cutoff) old.Add(k);
        foreach (int k in old) _checkpoints.Remove(k);
    }
}
