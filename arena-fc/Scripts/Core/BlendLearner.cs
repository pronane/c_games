// Arena FC - blend weight learner: adjusts locomotion blend-space weights
// from recorded play data.  Phase 3.9 (first ML step).
//
// Learns which clips are used most in which situations (speed/turn/ball
// state) and adjusts the blend-space thresholds.  Exported weights are
// written to the manifest so the runtime can use them.
//
// This is a simple frequency-based learner, not a neural network.  It
// counts clip usage in each blend-space cell and adjusts the cell
// boundaries to favour the most-used clips.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>A blend-space cell: (speed band, turn band, ball state).</summary>
public struct BlendCell : IEquatable<BlendCell>
{
    public int SpeedBand;   // 0=idle, 1=walk, 2=jog, 3=run, 4=sprint
    public int TurnBand;    // 0=straight, 1=turn, 2=sharp turn
    public int BallState;   // 0=no ball, 1=has ball, 2=dribbling

    public bool Equals(BlendCell other) =>
        SpeedBand == other.SpeedBand && TurnBand == other.TurnBand && BallState == other.BallState;
    public override bool Equals(object? obj) => obj is BlendCell c && Equals(c);
    public override int GetHashCode() => (SpeedBand * 31 + TurnBand) * 31 + BallState;
}

/// <summary>Learned blend weights: clip preference per cell.</summary>
public sealed class BlendWeights
{
    public Dictionary<BlendCell, Dictionary<string, float>> CellWeights = new();
    public Dictionary<string, float> GlobalWeights = new();

    public void Record(BlendCell cell, string clip)
    {
        if (!CellWeights.TryGetValue(cell, out var weights))
        {
            weights = new Dictionary<string, float>();
            CellWeights[cell] = weights;
        }
        weights[clip] = weights.GetValueOrDefault(clip, 0f) + 1f;
        GlobalWeights[clip] = GlobalWeights.GetValueOrDefault(clip, 0f) + 1f;
    }

    /// <summary>Normalise weights to 0..1 per cell.</summary>
    public void Normalise()
    {
        foreach (var cell in CellWeights)
        {
            float max = 0f;
            foreach (var w in cell.Value.Values) max = Math.Max(max, w);
            if (max > 0f)
                foreach (var k in cell.Value.Keys.ToArray())
                    cell.Value[k] /= max;
        }
        float gmax = 0f;
        foreach (var w in GlobalWeights.Values) gmax = Math.Max(gmax, w);
        if (gmax > 0f)
            foreach (var k in GlobalWeights.Keys.ToArray())
                GlobalWeights[k] /= gmax;
    }

    /// <summary>Get the best clip for a cell (highest weight).</summary>
    public string? BestClip(BlendCell cell)
    {
        if (!CellWeights.TryGetValue(cell, out var weights)) return null;
        string? best = null; float bestW = 0f;
        foreach (var (clip, w) in weights)
            if (w > bestW) { bestW = w; best = clip; }
        return best;
    }
}

/// <summary>Learns blend weights from replay frames.</summary>
public sealed class BlendLearner
{
    public BlendWeights Weights { get; } = new();
    private int _framesProcessed;

    /// <summary>Learn from one replay frame.</summary>
    public void Learn(ReplayFrame frame, MatchState state)
    {
        for (int i = 0; i < state.Players.Length; i++)
        {
            var p = state.Players[i];
            var cell = Classify(p, state);
            Weights.Record(cell, p.Action);
        }
        _framesProcessed++;
    }

    /// <summary>Classify a player's state into a blend-space cell.</summary>
    public static BlendCell Classify(PlayerState p, MatchState state)
    {
        float speed = Mx.Flat(p.Vel).Length();
        int speedBand = speed switch
        {
            < 0.5f => 0,
            < 1.7f => 1,
            < 2.9f => 2,
            < 4.3f => 3,
            _ => 4,
        };
        // Turn rate from facing change (approximate from velocity alignment).
        Vector3 velDir = Mx.Norm(Mx.Flat(p.Vel));
        Vector3 facing = Mx.Norm(Mx.Flat(p.Facing));
        float dot = Vector3.Dot(velDir, facing);
        int turnBand = dot switch
        {
            > 0.9f => 0,    // straight
            > 0.5f => 1,    // turn
            _ => 2,         // sharp turn
        };
        int ballState = state.Ball.Owner == p.Index ? (p.Dribbling ? 2 : 1) : 0;
        return new BlendCell { SpeedBand = speedBand, TurnBand = turnBand, BallState = ballState };
    }

    public void Finalise() => Weights.Normalise();
    public int FramesProcessed => _framesProcessed;
}
