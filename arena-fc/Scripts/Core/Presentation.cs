// Arena FC — Presentation & Broadcast system (Phase 4).
// Pre-match lineups, half-time analysis, post-match ratings,
// broadcast graphics data, team management.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Pre-match presentation data.</summary>
public class PreMatchData
{
    public string HomeTeam = "";
    public string AwayTeam = "";
    public string HomeFormation = "4-4-2";
    public string AwayFormation = "4-3-3";
    public List<string> HomeLineup = new();
    public List<string> AwayLineup = new();
    public int HomeStrength;
    public int AwayStrength;
    public int HomeForm; // last 5: W=3, D=1, L=0
    public int AwayForm;
    public string HeadToHead = "";
    public string Weather = "Clear";
    public string Stadium = "Arena Stadium";
}

/// <summary>Half-time analysis data.</summary>
public class HalfTimeData
{
    public int HomeScore, AwayScore;
    public int HomeShots, AwayShots;
    public int HomeShotsOnTarget, AwayShotsOnTarget;
    public float HomePossessionPct;
    public int HomePasses, AwayPasses;
    public int HomeFouls, AwayFouls;
    public int HomeCorners, AwayCorners;
    public string TopScorer = "";
    public string Analysis = "";
    public List<string> KeyEvents = new();
}

/// <summary>Post-match presentation data.</summary>
public class PostMatchData
{
    public int HomeScore, AwayScore;
    public string HomeTeam = "";
    public string AwayTeam = "";
    public string ManOfTheMatch = "";
    public int MotMRating;
    public List<PlayerRating> HomeRatings = new();
    public List<PlayerRating> AwayRatings = new();
    public List<string> Highlights = new();
    public string ResultSummary = "";
}

/// <summary>Individual player rating.</summary>
public class PlayerRating
{
    public string Name = "";
    public int Rating; // 1-10 scaled to 10-100
    public int Goals, Assists;
    public bool IsMotM;
}

/// <summary>Broadcast graphic types.</summary>
public enum BroadcastGraphic
{
    ScoreBug,
    LowerThird,
    StatsOverlay,
    Lineup,
    HeadToHead,
    FormGuide,
    Highlight,
}

/// <summary>Presentation manager.</summary>
public class Presentation
{
    private readonly Random _rng = new(123);

    /// <summary>Generate pre-match data.</summary>
    public PreMatchData GeneratePreMatch(string homeTeam, string awayTeam, string homeFormation, string awayFormation)
    {
        var data = new PreMatchData
        {
            HomeTeam = homeTeam,
            AwayTeam = awayTeam,
            HomeFormation = homeFormation,
            AwayFormation = awayFormation,
            HomeStrength = _rng.Next(70, 90),
            AwayStrength = _rng.Next(70, 90),
            HomeForm = _rng.Next(5, 15),
            AwayForm = _rng.Next(5, 15),
            Weather = _rng.Next(4) switch
            {
                0 => "Clear",
                1 => "Overcast",
                2 => "Rain",
                _ => "Windy",
            },
            HeadToHead = $"{homeTeam} { _rng.Next(3) }-{ _rng.Next(3) } {awayTeam} (last meeting)",
        };
        // Generate lineups (11 players each)
        data.HomeLineup = GenerateLineup(homeTeam);
        data.AwayLineup = GenerateLineup(awayTeam);
        return data;
    }

    private List<string> GenerateLineup(string team)
    {
        string[] names = { "GK", "LB", "CB", "CB", "RB", "CM", "CM", "LM", "RM", "ST", "ST" };
        var lineup = new List<string>();
        for (int i = 0; i < 11; i++)
        {
            lineup.Add($"{names[i]} #{i + 1}");
        }
        return lineup;
    }

    /// <summary>Generate half-time analysis.</summary>
    public HalfTimeData GenerateHalfTime(MatchState state)
    {
        var data = new HalfTimeData
        {
            HomeScore = state.Score[0],
            AwayScore = state.Score[1],
            HomeShots = state.Shots[0],
            AwayShots = state.Shots[1],
            HomeShotsOnTarget = state.ShotsOnTarget[0],
            AwayShotsOnTarget = state.ShotsOnTarget[1],
            HomePasses = state.Passes[0],
            AwayPasses = state.Passes[1],
            HomeFouls = state.Fouls[0],
            AwayFouls = state.Fouls[1],
            HomeCorners = state.Corners[0],
            AwayCorners = state.Corners[1],
        };
        float total = state.PossessionTime[0] + state.PossessionTime[1];
        data.HomePossessionPct = total > 0.1f ? state.PossessionTime[0] / total * 100f : 50f;

        // Analysis text
        if (data.HomeScore > data.AwayScore)
            data.Analysis = "Home team in control. Away team needs to push forward.";
        else if (data.AwayScore > data.HomeScore)
            data.Analysis = "Away team leading. Home team must increase tempo.";
        else if (data.HomeShots > data.AwayShots + 3)
            data.Analysis = "Home team dominating chances but missing the target.";
        else
            data.Analysis = "Evenly matched first half. Second half will be crucial.";

        return data;
    }

    /// <summary>Generate post-match data with ratings and MOTM.</summary>
    public PostMatchData GeneratePostMatch(MatchState state, string homeTeam, string awayTeam)
    {
        var data = new PostMatchData
        {
            HomeScore = state.Score[0],
            AwayScore = state.Score[1],
            HomeTeam = homeTeam,
            AwayTeam = awayTeam,
        };

        // Generate ratings (simplified: based on team performance)
        data.HomeRatings = GenerateRatings(homeTeam, state.Score[0], state.Shots[0]);
        data.AwayRatings = GenerateRatings(awayTeam, state.Score[1], state.Shots[1]);

        // Find MOTM (highest rating)
        var allRatings = data.HomeRatings.Concat(data.AwayRatings).ToList();
        var motm = allRatings.OrderByDescending(r => r.Rating).FirstOrDefault();
        if (motm != null)
        {
            data.ManOfTheMatch = motm.Name;
            data.MotMRating = motm.Rating;
            motm.IsMotM = true;
        }

        // Result summary
        if (data.HomeScore > data.AwayScore)
            data.ResultSummary = $"{homeTeam} win {data.HomeScore}-{data.AwayScore}!";
        else if (data.AwayScore > data.HomeScore)
            data.ResultSummary = $"{awayTeam} win {data.AwayScore}-{data.HomeScore}!";
        else
            data.ResultSummary = $"Draw {data.HomeScore}-{data.AwayScore}. Points shared.";

        // Highlights (from events)
        data.Highlights = (events ?? new List<MatchEvent>())
            .Where(e => e.Kind == EventKind.Goal || e.Kind == EventKind.Shot)
            .Select(e => e.Text)
            .Take(5)
            .ToList();

        return data;
    }

    private List<PlayerRating> GenerateRatings(string team, int goals, int shots)
    {
        var ratings = new List<PlayerRating>();
        string[] positions = { "GK", "LB", "CB", "CB", "RB", "CM", "CM", "LM", "RM", "ST", "ST" };
        for (int i = 0; i < 11; i++)
        {
            int baseRating = _rng.Next(60, 85);
            if (positions[i] == "ST" && goals > 0)
                baseRating += goals * 3;
            if (positions[i] == "GK" && goals == 0)
                baseRating += 5;
            ratings.Add(new PlayerRating
            {
                Name = $"{positions[i]} #{i + 1}",
                Rating = Math.Clamp(baseRating, 40, 95),
                Goals = positions[i] == "ST" ? goals / 2 : 0,
                Assists = _rng.Next(0, 2),
            });
        }
        return ratings;
    }

    /// <summary>Format form guide (W/D/L string).</summary>
    public static string FormatForm(int formPoints)
    {
        // formPoints: sum of last 5 (W=3, D=1, L=0), max 15
        return formPoints switch
        {
            >= 13 => "WWWWW",
            >= 10 => "WWWDW",
            >= 7 => "WDWDW",
            >= 4 => "DWDLW",
            _ => "LLLLL",
        };
    }

    /// <summary>Get broadcast graphic text.</summary>
    public static string GetBroadcastText(BroadcastGraphic type, PreMatchData pre, HalfTimeData half, PostMatchData post)
    {
        return type switch
        {
            BroadcastGraphic.ScoreBug => $"{pre.HomeTeam} vs {pre.AwayTeam}",
            BroadcastGraphic.LowerThird => $"{pre.HomeTeam} ({pre.HomeFormation}) vs {pre.AwayTeam} ({pre.AwayFormation})",
            BroadcastGraphic.StatsOverlay => $"Possession {half.HomePossessionPct:0}% | Shots {half.HomeShots}-{half.AwayShots}",
            BroadcastGraphic.Lineup => $"Home: {string.Join(", ", pre.HomeLineup.Take(3))}...",
            BroadcastGraphic.HeadToHead => pre.HeadToHead,
            BroadcastGraphic.FormGuide => $"Home: {FormatForm(pre.HomeForm)} | Away: {FormatForm(pre.AwayForm)}",
            BroadcastGraphic.Highlight => post.Highlights.FirstOrDefault() ?? "No highlights",
            _ => "",
        };
    }
}
