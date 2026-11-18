// Arena FC - match analysis: last 10 matches, style charts, real-time advice.
// Phase 3.8 (eFootball v5.2 lesson).
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Summary of one completed match.</summary>
public sealed class MatchSummary
{
    public int HomeScore, AwayScore;
    public int HomeShots, AwayShots;
    public int HomePasses, AwayPasses;
    public int HomeFouls, AwayFouls;
    public float HomePossessionPct;
    public float DurationMinutes;
    public string HomeClub = "", AwayClub = "";
}

/// <summary>Tracks match history and provides style analysis + advice.</summary>
public sealed class MatchAnalysis
{
    private readonly List<MatchSummary> _history = new();
    private const int MaxHistory = 10;

    public IReadOnlyList<MatchSummary> History => _history;

    public void Record(MatchState state, string homeClub, string awayClub)
    {
        float total = state.PossessionTime[0] + state.PossessionTime[1];
        float possPct = total < .1f ? 50f : state.PossessionTime[0] / total * 100f;
        var summary = new MatchSummary
        {
            HomeScore = state.Score[0],
            AwayScore = state.Score[1],
            HomeShots = state.Shots[0],
            AwayShots = state.Shots[1],
            HomePasses = state.Passes[0],
            AwayPasses = state.Passes[1],
            HomeFouls = state.Fouls[0],
            AwayFouls = state.Fouls[1],
            HomePossessionPct = possPct,
            DurationMinutes = state.Clock / 60f,
            HomeClub = homeClub,
            AwayClub = awayClub,
        };
        _history.Add(summary);
        if (_history.Count > MaxHistory) _history.RemoveAt(0);
    }

    /// <summary>Style chart: possession, shots, passes, fouls (0..1 normalised).</summary>
    public (float possession, float shots, float passes, float fouls) StyleChart(int side)
    {
        if (_history.Count == 0) return (0.5f, 0.5f, 0.5f, 0.5f);
        float poss = (float)(_history.Average(m => side == 0 ? m.HomePossessionPct : 100f - m.HomePossessionPct) / 100.0);
        float shots = (float)_history.Average(m => side == 0 ? m.HomeShots : m.AwayShots);
        float passes = (float)_history.Average(m => side == 0 ? m.HomePasses : m.AwayPasses);
        float fouls = (float)_history.Average(m => side == 0 ? m.HomeFouls : m.AwayFouls);
        return (poss, Math.Min(shots / 15f, 1f), Math.Min(passes / 200f, 1f), Math.Min(fouls / 8f, 1f));
    }

    /// <summary>Real-time advice based on current match state.</summary>
    public string Advice(MatchState state, int side)
    {
        float total = state.PossessionTime[0] + state.PossessionTime[1];
        float poss = total < .1f ? 50f : state.PossessionTime[side] / total * 100f;
        int shots = state.Shots[side];
        int fouls = state.Fouls[side];
        if (poss < 35f) return "Keep the ball — try shorter passes and hold possession.";
        if (shots < 2 && state.Clock > 300f) return "Create more chances — push forwards higher.";
        if (fouls > 4) return "Too many fouls — time your tackles better.";
        if (poss > 65f) return "Dominating possession — be patient and create openings.";
        return "Good balance — keep pressing and creating chances.";
    }
}
