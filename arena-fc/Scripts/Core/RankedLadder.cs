// Arena FC - ranked ladder (MMR, divisions, seasons).
//
// This is the model the ONLINE screen and the offline "ranked friendly" both
// feed: an Elo-style rating that survives restarts through SaveGame.  It is
// deliberately Godot-free and deterministic so the core suite can assert the
// promotion/relegation maths.
using System;

namespace ArenaFC.Core;

public sealed class RankedLadder
{
    public const int StartingMmr = 1000;
    public const int SeasonLengthMatches = 30;

    public int Mmr = StartingMmr;
    public int Season = 1;
    public int SeasonMatches;
    public int Wins, Draws, Losses;
    public int GoalsFor, GoalsAgainst;
    public int BestMmr = StartingMmr;
    public int Streak;                 // + wins in a row, - losses in a row
    public int PlacementMatchesLeft = 5;

    public int Played => Wins + Draws + Losses;
    public int Points => Wins * 3 + Draws;
    public float WinRate => Played == 0 ? 0f : Wins / (float)Played;
    public int GoalDifference => GoalsFor - GoalsAgainst;
    public bool Placed => PlacementMatchesLeft == 0;

    /// <summary>1 (elite) .. 10 (beginner). 100 MMR per division.</summary>
    public int Division => Math.Clamp(10 - (Mmr - 600) / 100, 1, 10);

    public string DivisionName => Division switch
    {
        1 => "ELITE",
        2 => "DIVISION 2",
        3 => "DIVISION 3",
        4 => "DIVISION 4",
        5 => "DIVISION 5",
        6 => "DIVISION 6",
        7 => "DIVISION 7",
        8 => "DIVISION 8",
        9 => "DIVISION 9",
        _ => "DIVISION 10",
    };

    /// <summary>MMR needed to reach the next division (0 when already elite).</summary>
    public int MmrToNextDivision =>
        Division <= 1 ? 0 : Math.Max(0, 600 + (11 - Division) * 100 - Mmr);

    /// <summary>Apply one competitive result.  Beating a stronger opponent is
    /// worth more than beating a weaker one, and goal difference nudges it.</summary>
    public int Record(bool win, bool draw, int goalsFor, int goalsAgainst, int opponentMmr = StartingMmr)
    {
        int before = Mmr;
        float expected = 1f / (1f + MathF.Pow(10f, (opponentMmr - Mmr) / 400f));
        float actual = win ? 1f : draw ? .5f : 0f;
        int k = PlacementMatchesLeft > 0 ? 60 : 32;
        float margin = Math.Clamp((goalsFor - goalsAgainst) * .12f, -.6f, .6f);
        int delta = (int)MathF.Round(k * (actual - expected) + (win ? margin * 12f : draw ? 0f : -margin * 12f));
        if (win) { Wins++; Streak = Streak >= 0 ? Streak + 1 : 1; }
        else if (draw) { Draws++; Streak = 0; }
        else { Losses++; Streak = Streak <= 0 ? Streak - 1 : -1; }
        GoalsFor += Math.Max(0, goalsFor);
        GoalsAgainst += Math.Max(0, goalsAgainst);
        Mmr = Math.Clamp(Mmr + delta, 200, 2600);
        BestMmr = Math.Max(BestMmr, Mmr);
        SeasonMatches++;
        if (PlacementMatchesLeft > 0) PlacementMatchesLeft--;
        return Mmr - before;
    }

    /// <summary>Roll the season over once the season length is reached.</summary>
    public bool TryRollSeason(out int seasonPoints)
    {
        seasonPoints = Points;
        if (SeasonMatches < SeasonLengthMatches) return false;
        Season++;
        SeasonMatches = 0;
        Wins = Draws = Losses = 0;
        GoalsFor = GoalsAgainst = 0;
        Streak = 0;
        // Soft reset: keep half of the surplus above the starting rating.
        Mmr = StartingMmr + (Mmr - StartingMmr) / 2;
        BestMmr = Mmr;
        PlacementMatchesLeft = 3;
        return true;
    }

    public string Summary =>
        $"{DivisionName} · {Mmr} MMR · {Wins}W {Draws}D {Losses}L · {Points} pts" +
        (Placed ? "" : $" · placement {5 - PlacementMatchesLeft}/5");
}
