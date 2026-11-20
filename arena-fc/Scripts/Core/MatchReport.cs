// Arena FC - post-match report: per-player ratings, expected goals and the
// match-analysis feed.
//
// Two thirds of the review's "implemented but never called" list was analysis
// machinery: ExpectedGoals, HeatMap, MatchAnalysis.  This file gives them a
// caller.  Ratings are deliberately heuristic - the simulation does not track
// every duel per player - but they move with the things a player can feel:
// goals for and against, saves, cards, fitness left in the tank.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

public static class MatchReport
{
    /// <summary>Expected goals for a shot, in the same currency the HUD shows.</summary>
    public static float ShotXg(float distanceToGoal, float angleToGoal, bool oneOnOne) =>
        new ExpectedGoals().CalculateXG(distanceToGoal, angleToGoal, oneOnOne);

    /// <summary>Individual match rating (3.0 .. 10.0).</summary>
    public static float Rating(MatchState s, int index)
    {
        if (index < 0 || index >= s.Players.Length) return 6.0f;
        var p = s.Players[index];
        int side = p.Team, other = 1 - side;
        float r = 6.3f;
        r += .55f * s.Score[side] - .40f * s.Score[other];
        if (p.IsKeeper)
        {
            int saves = Math.Max(0, s.ShotsOnTarget[other] - s.Score[other]);
            r += .18f * Math.Min(6, saves);
        }
        else if (s.Score[other] == 0 && p.Role == Role.Defender) r += .55f;
        if (!p.IsKeeper && p.Role == Role.Forward && s.Score[side] > 0) r += .25f;
        r += .5f * (p.Stamina - .7f);          // running out of legs costs you
        r -= .35f * p.Cards;
        if (p.SentOff) r -= 1.6f;
        return Math.Clamp(MathF.Round(r * 10f) / 10f, 3f, 10f);
    }

    /// <summary>Every player on a side, best rating first.</summary>
    public static List<(PlayerState player, float rating)> Ratings(MatchState s, int side) =>
        s.Players.Where(p => p.Team == side)
            .Select(p => (p, Rating(s, p.Index)))
            .OrderByDescending(t => t.Item2)
            .ToList();

    public static (string name, float rating) BestPlayer(MatchState s, int side)
    {
        var best = Ratings(s, side).FirstOrDefault();
        return best.player == null ? ("-", 0f) : (Display(best.player), best.rating);
    }

    public static string Display(PlayerState p) =>
        string.IsNullOrWhiteSpace(p.Spec.DisplayName)
            ? (string.IsNullOrWhiteSpace(p.Spec.Name) ? "Player" : p.Spec.Name)
            : p.Spec.DisplayName;

    /// <summary>xG overperformance: goals minus expected goals.</summary>
    public static string XgLine(MatchState s, int side) =>
        $"{s.Score[side]} goals from {s.Xg[side]:0.00} xG";

    /// <summary>Where the play happened, bucketed into a cols x rows grid.</summary>
    public static int[,] HeatGrid(HeatMap heat, int cols = 9, int rows = 5)
    {
        var grid = new int[cols, rows];
        foreach (var (x, z, count) in heat.Zones)
        {
            int cx = Math.Clamp((int)((x / Mx.PitchLength + .5f) * cols), 0, cols - 1);
            int cz = Math.Clamp((int)((z / Mx.PitchWidth + .5f) * rows), 0, rows - 1);
            grid[cx, cz] += count;
        }
        return grid;
    }

    /// <summary>One-line verdict on the performance, for the analysis screen.</summary>
    public static string Verdict(MatchState s)
    {
        float xgGap = (s.Score[0] - s.Xg[0]) - (s.Score[1] - s.Xg[1]);
        if (Math.Abs(xgGap) > 1.0f)
            return xgGap > 0
                ? "Clinical: the scoreline flatters you against the chances created."
                : "Wasteful: the chances were there, the finishing was not.";
        if (s.Score[0] == s.Score[1]) return "Level, and the numbers agree it was level.";
        return s.Score[0] > s.Score[1] ? "Deserved win on the balance of play." : "Beaten by the better chances.";
    }
}
