// Arena FC — Tournament & League system.
//
// This used to be a demo stub: GenerateWorldCup put eight teams in one "group"
// with a full round robin (28 fixtures), AdvanceToKnockout took the top four,
// created two semi-finals and threw the final away, and nothing ever simulated
// the AI's fixtures - so a player's group table could never resolve.  The game
// additionally built one of these objects and immediately discarded it.
//
// The engine here is a real competition: deterministic groups, group tables,
// a proper knockout bracket that ends in a champion, AI fixtures simulated from
// team strength, and a single entry point the UI can drive one match at a time.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Tournament types.</summary>
public enum TournamentType
{
    League,
    ChampionsLeague,
    WorldCup,
    Euros,
    CopaAmerica,
    DomesticCup,
    Friendly,
}

/// <summary>Tournament stage.</summary>
public enum TournamentStage
{
    GroupStage,
    RoundOf16,
    QuarterFinal,
    SemiFinal,
    Final,
    LeaguePhase,
    Knockout,
}

/// <summary>A tournament fixture. Scores are -1 until it is played.</summary>
public class TournamentFixture
{
    public string HomeTeam = "";
    public string AwayTeam = "";
    public int HomeScore = -1;
    public int AwayScore = -1;
    public TournamentStage Stage;
    public int Round;
    /// <summary>A knockout tie cannot be drawn: it is settled on penalties.</summary>
    public bool DecidedOnPenalties;
    public string PenaltyWinner = "";

    public bool Played => HomeScore >= 0;
    public bool IsDraw => Played && HomeScore == AwayScore;
    public string Winner => !Played ? "" : HomeScore > AwayScore ? HomeTeam
                          : AwayScore > HomeScore ? AwayTeam : PenaltyWinner;
    public string Loser => !Played ? "" : Winner == HomeTeam ? AwayTeam : HomeTeam;
    public string ScoreLine => !Played ? "v" : IsDraw ? $"{HomeScore}-{AwayScore} (pens)" : $"{HomeScore}-{AwayScore}";
}

/// <summary>Group table entry.</summary>
public class GroupTableEntry
{
    public string Team = "";
    public string Group = "";
    public int Played, Won, Drawn, Lost;
    public int GF, GA, Points;
    public int GoalDifference => GF - GA;
}

/// <summary>A group of four (or fewer) teams.</summary>
public class TournamentGroup
{
    public string Name = "";
    public List<string> Teams = new();
}

/// <summary>International team (for World Cup / Euros / Copa).</summary>
public class InternationalTeam
{
    public string Name = "";
    public string Short = "";
    public string Confederation = ""; // UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC
    public float Strength = 0.75f;
    public string FlagColor = "#ffffff";
}

/// <summary>
/// Drives one competition. The UI asks for <see cref="NextPlayerFixture"/>,
/// plays that match, calls <see cref="RecordResult"/>, and the engine updates
/// tables, settles every other fixture in the round, and opens the next round -
/// until <see cref="Champion"/> is set.
/// </summary>
public class TournamentSystem
{
    public TournamentType Type;
    public TournamentStage CurrentStage = TournamentStage.GroupStage;
    public List<TournamentFixture> Fixtures = new();
    public List<GroupTableEntry> GroupTable = new();
    public List<TournamentGroup> Groups = new();
    public List<string> Teams = new();
    public string PlayerTeam = "";
    public bool IsPlayerEliminated;
    public string Champion = "";
    public string RunnerUp = "";
    public int Seed = 789;
    public string Title = "Tournament";

    private readonly Dictionary<string, float> _strength = new(StringComparer.OrdinalIgnoreCase);
    private Rng _rng = new(789);

    public TournamentSystem() : this(789) { }

    public TournamentSystem(int seed)
    {
        Seed = seed;
        _rng = new Rng(seed);
    }

    // ---------------------------------------------------------------- queries

    public bool IsComplete => Champion.Length > 0;
    public bool InvolvesPlayer(TournamentFixture f) =>
        f.HomeTeam.Equals(PlayerTeam, StringComparison.OrdinalIgnoreCase) ||
        f.AwayTeam.Equals(PlayerTeam, StringComparison.OrdinalIgnoreCase);

    /// <summary>The player's next unplayed fixture, or null when the run is over.</summary>
    public TournamentFixture? NextPlayerFixture =>
        IsPlayerEliminated ? null : Fixtures.FirstOrDefault(f => !f.Played && InvolvesPlayer(f));

    public List<TournamentFixture> PlayerFixtures =>
        Fixtures.Where(InvolvesPlayer).OrderBy(f => f.Round).ToList();

    public string StageLabel => IsComplete ? "COMPLETE"
        : Type == TournamentType.League ? "LEAGUE"
        : CurrentStage == TournamentStage.GroupStage ? "GROUP STAGE"
        : CurrentStage == TournamentStage.QuarterFinal ? "QUARTER-FINALS"
        : CurrentStage == TournamentStage.SemiFinal ? "SEMI-FINALS"
        : CurrentStage == TournamentStage.Final ? "FINAL"
        : CurrentStage.ToString().ToUpperInvariant();

    public string TrophyName => Type switch
    {
        TournamentType.WorldCup => "WORLD CUP",
        TournamentType.Euros => "EUROPEAN CHAMPIONSHIP",
        TournamentType.CopaAmerica => "COPA AMERICA",
        TournamentType.ChampionsLeague => "CHAMPIONS LEAGUE",
        TournamentType.League => "LEAGUE TITLE",
        _ => "TROPHY",
    };

    public float StrengthOf(string team) =>
        _strength.TryGetValue(team, out float s) ? s : .72f;

    public List<GroupTableEntry> TableFor(string group) =>
        GroupTable.Where(t => t.Group == group).OrderByDescending(t => t.Points)
            .ThenByDescending(t => t.GoalDifference).ThenByDescending(t => t.GF)
            .ThenBy(t => t.Team, StringComparer.Ordinal).ToList();

    public List<GroupTableEntry> GetTable() =>
        GroupTable.OrderByDescending(t => t.Points)
            .ThenByDescending(t => t.GoalDifference).ThenByDescending(t => t.GF).ToList();

    public int PlayedCount => Fixtures.Count(f => f.Played);
    public int TotalCount => Fixtures.Count;

    // ---------------------------------------------------------------- set-up

    /// <summary>Group fixtures for 1, 2 or 4 groups of four - the only sizes that
    /// produce a clean bracket (2, 4 or 8 qualifiers).</summary>
    private void BuildGroups(IEnumerable<string> teams, IEnumerable<InternationalTeam>? info = null)
    {
        var list = teams.ToList();
        if (info != null)
            foreach (var t in info) _strength[t.Name] = t.Strength;

        int groupCount = list.Count >= 16 ? 4 : list.Count >= 8 ? 2 : 1;
        int size = Math.Min(4, Math.Max(2, list.Count / groupCount));
        Groups.Clear();
        GroupTable.Clear();
        Fixtures.Clear();
        for (int g = 0; g < groupCount; g++)
        {
            var group = new TournamentGroup { Name = ((char)('A' + g)).ToString() };
            group.Teams.AddRange(list.Skip(g * size).Take(size));
            if (group.Teams.Count < 2) continue;
            Groups.Add(group);
            foreach (var team in group.Teams)
                GroupTable.Add(new GroupTableEntry { Team = team, Group = group.Name });

            int round = 1;
            for (int i = 0; i < group.Teams.Count; i++)
                for (int j = i + 1; j < group.Teams.Count; j++)
                    Fixtures.Add(new TournamentFixture
                    {
                        HomeTeam = group.Teams[i], AwayTeam = group.Teams[j],
                        Stage = TournamentStage.GroupStage, Round = round++,
                    });
        }
        Teams = GroupTable.Select(t => t.Team).ToList();
        CurrentStage = TournamentStage.GroupStage;
        Champion = RunnerUp = "";
        IsPlayerEliminated = false;
    }

    public void GenerateWorldCup(List<InternationalTeam> teams)
    {
        Type = TournamentType.WorldCup;
        Title = "WORLD CUP";
        BuildGroups(teams.OrderByDescending(t => t.Strength).Take(16).Select(t => t.Name), teams);
    }

    public void GenerateEuros(List<InternationalTeam> teams)
    {
        Type = TournamentType.Euros;
        Title = "EUROPEAN CHAMPIONSHIP";
        BuildGroups(teams.Where(t => t.Confederation == "UEFA")
            .OrderByDescending(t => t.Strength).Take(8).Select(t => t.Name), teams);
    }

    public void GenerateCopaAmerica(List<InternationalTeam> teams)
    {
        Type = TournamentType.CopaAmerica;
        Title = "COPA AMERICA";
        BuildGroups(teams.Where(t => t.Confederation == "CONMEBOL")
            .OrderByDescending(t => t.Strength).Take(8).Select(t => t.Name), teams);
    }

    public void GenerateChampionsLeague(List<string> teams)
    {
        Type = TournamentType.ChampionsLeague;
        Title = "CHAMPIONS LEAGUE";
        BuildGroups(teams.Take(16), null);
        // Club sides have no international strength table: rank by club rating.
        foreach (var club in Clubs.All)
            _strength[club.Name] = club.Strength;
    }

    public void GenerateDomesticCup(List<string> teams)
    {
        Type = TournamentType.DomesticCup;
        Title = "DOMESTIC CUP";
        BuildGroups(teams.Take(16), null);
        foreach (var club in Clubs.All) _strength[club.Name] = club.Strength;
    }

    /// <summary>Straight double round-robin league. The table leader wins.</summary>
    public void GenerateLeague(List<string> teams)
    {
        Type = TournamentType.League;
        Title = "LEAGUE";
        Teams = teams.ToList();
        Fixtures.Clear();
        GroupTable.Clear();
        Groups.Clear();
        var group = new TournamentGroup { Name = "L" };
        group.Teams.AddRange(Teams);
        Groups.Add(group);
        foreach (var team in Teams) GroupTable.Add(new GroupTableEntry { Team = team, Group = "L" });
        foreach (var club in Clubs.All) _strength[club.Name] = club.Strength;
        int round = 1;
        for (int i = 0; i < Teams.Count; i++)
            for (int j = 0; j < Teams.Count; j++)
            {
                if (i == j) continue;
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = Teams[i], AwayTeam = Teams[j],
                    Stage = TournamentStage.LeaguePhase, Round = round++,
                });
            }
        CurrentStage = TournamentStage.LeaguePhase;
        Champion = RunnerUp = "";
        IsPlayerEliminated = false;
    }

    // ---------------------------------------------------------------- results

    /// <summary>Record the player's result, settle the rest of the round, advance.</summary>
    public void RecordResult(string homeTeam, string awayTeam, int homeScore, int awayScore)
    {
        var fixture = Fixtures.FirstOrDefault(f =>
            !f.Played && f.HomeTeam == homeTeam && f.AwayTeam == awayTeam);
        if (fixture == null)
        {
            // Accept the reverse order too - the UI may present the tie either way.
            fixture = Fixtures.FirstOrDefault(f =>
                !f.Played && f.HomeTeam == awayTeam && f.AwayTeam == homeTeam);
            if (fixture != null) (homeScore, awayScore) = (awayScore, homeScore);
        }
        if (fixture == null) return;
        ApplyResult(fixture, homeScore, awayScore, settleDraw: true);
        SettleRound(fixture);
        AdvanceIfRoundComplete();
    }

    /// <summary>Record the result of the player's next fixture by index-in-run.</summary>
    public bool RecordPlayerResult(int homeScore, int awayScore)
    {
        var next = NextPlayerFixture;
        if (next == null) return false;
        RecordResult(next.HomeTeam, next.AwayTeam, homeScore, awayScore);
        return true;
    }

    private void ApplyResult(TournamentFixture f, int homeScore, int awayScore, bool settleDraw)
    {
        f.HomeScore = Math.Max(0, homeScore);
        f.AwayScore = Math.Max(0, awayScore);
        if (f.Stage == TournamentStage.GroupStage || f.Stage == TournamentStage.LeaguePhase)
        {
            UpdateTable(f.HomeTeam, f.AwayTeam, f.HomeScore, f.AwayScore);
            return;
        }
        if (f.IsDraw && settleDraw)
        {
            f.DecidedOnPenalties = true;
            // Penalty shootouts are close to a coin flip, tilted by strength.
            float h = StrengthOf(f.HomeTeam), a = StrengthOf(f.AwayTeam);
            float homeChance = .5f + (h - a) * .6f;
            f.PenaltyWinner = _rng.Next() < homeChance ? f.HomeTeam : f.AwayTeam;
        }
    }

    private void UpdateTable(string home, string away, int hs, int aScore)
    {
        var h = GroupTable.FirstOrDefault(t => t.Team == home);
        var a = GroupTable.FirstOrDefault(t => t.Team == away);
        if (h == null || a == null) return;
        h.Played++; a.Played++;
        h.GF += hs; h.GA += aScore;
        a.GF += aScore; a.GA += hs;
        if (hs > aScore) { h.Won++; a.Lost++; h.Points += 3; }
        else if (aScore > hs) { a.Won++; h.Lost++; a.Points += 3; }
        else { h.Drawn++; a.Drawn++; h.Points++; a.Points++; }
    }

    /// <summary>Results a plausible opponent would produce, from team strength.</summary>
    private (int home, int away) SimulateScore(string home, string away)
    {
        float h = StrengthOf(home), a = StrengthOf(away);
        float edge = (h - a) * 2.2f;
        float lambdaHome = MathF.Max(.18f, 1.25f + edge);
        float lambdaAway = MathF.Max(.15f, 1.05f - edge);
        return (Poisson(lambdaHome), Poisson(lambdaAway));
    }

    private int Poisson(float lambda)
    {
        // Knuth's method - small lambdas, deterministic through the engine RNG.
        double l = Math.Exp(-lambda), p = 1.0;
        int k = 0;
        do { k++; p *= _rng.Next(); } while (p > l && k < 12);
        return k - 1;
    }

    /// <summary>Play every other unplayed fixture in the same stage/round.</summary>
    private void SettleRound(TournamentFixture played)
    {
        foreach (var f in Fixtures.Where(x => !x.Played && x.Stage == played.Stage && x.Round == played.Round).ToList())
        {
            var (hs, aScore) = SimulateScore(f.HomeTeam, f.AwayTeam);
            ApplyResult(f, hs, aScore, settleDraw: true);
        }
    }

    /// <summary>Simulate forward until the player has a fixture again or the
    /// competition is decided (used when the player is knocked out but wants to
    /// see who lifts the trophy).</summary>
    public void SimulateRemainingRound()
    {
        int guard = 0;
        while (guard++ < 32)
        {
            foreach (var f in Fixtures.Where(x => !x.Played && x.Stage == CurrentStage).ToList())
            {
                var (hs, aScore) = SimulateScore(f.HomeTeam, f.AwayTeam);
                ApplyResult(f, hs, aScore, settleDraw: true);
            }
            AdvanceIfRoundComplete();
            if (IsComplete || NextPlayerFixture != null) return;
        }
    }

    /// <summary>Simulate the whole competition, including the player's fixtures.</summary>
    public void SimulateAll()
    {
        int guard = 0;
        while (!IsComplete && guard++ < 64)
        {
            foreach (var f in Fixtures.Where(x => !x.Played).ToList())
            {
                var (hs, aScore) = SimulateScore(f.HomeTeam, f.AwayTeam);
                ApplyResult(f, hs, aScore, settleDraw: true);
            }
            AdvanceIfRoundComplete();
            if (Fixtures.All(f => f.Played) && !CheckComplete()) break;
        }
    }

    private void AdvanceIfRoundComplete()
    {
        if (Type == TournamentType.League)
        {
            if (Fixtures.All(f => f.Played))
            {
                var table = GetTable();
                Champion = table[0].Team;
                RunnerUp = table.Count > 1 ? table[1].Team : "";
                CurrentStage = TournamentStage.LeaguePhase;
            }
            return;
        }
        var current = Fixtures.Where(f => f.Stage == CurrentStage).ToList();
        if (current.Count == 0 || current.Any(f => !f.Played)) return;
        ApplyElimination();
        if (CheckComplete()) return;
        if (CurrentStage == TournamentStage.GroupStage) BuildKnockout();
        else BuildNextKnockoutRound();
    }

    private bool CheckComplete()
    {
        var final = Fixtures.FirstOrDefault(f => f.Stage == TournamentStage.Final && f.Played);
        if (final == null) return false;
        Champion = final.Winner;
        RunnerUp = final.Loser;
        return true;
    }

    private void ApplyElimination()
    {
        if (PlayerTeam.Length == 0) return;
        foreach (var f in Fixtures.Where(f => f.Played && InvolvesPlayer(f)))
            if (f.Stage != TournamentStage.GroupStage && f.Stage != TournamentStage.LeaguePhase
                && f.Winner != PlayerTeam)
                IsPlayerEliminated = true;
        if (Type == TournamentType.League) return;
        if (CurrentStage == TournamentStage.GroupStage && Fixtures.All(f => f.Played))
        {
            // Not in the qualifying places => out at the group stage.
            var qualified = QualifiedTeams();
            if (qualified.Count > 0 && !qualified.Contains(PlayerTeam, StringComparer.OrdinalIgnoreCase))
                IsPlayerEliminated = true;
        }
    }

    private List<string> QualifiedTeams()
    {
        var qualified = new List<string>();
        foreach (var g in Groups)
        {
            var table = TableFor(g.Name);
            qualified.AddRange(table.Take(2).Select(t => t.Team));
        }
        return qualified;
    }

    /// <summary>Kept for API compatibility: build the bracket from the tables.</summary>
    public void AdvanceToKnockout() => BuildKnockout();

    private void BuildKnockout()
    {
        // Seeded list: group winners first, then runners-up, in group order.
        var winners = new List<string>();
        var runners = new List<string>();
        foreach (var g in Groups)
        {
            var table = TableFor(g.Name);
            if (table.Count > 0) winners.Add(table[0].Team);
            if (table.Count > 1) runners.Add(table[1].Team);
        }
        var seeded = winners.Concat(runners).ToList();
        if (seeded.Count < 2) return;

        if (seeded.Count == 2)          // one group: winner v runner-up
        {
            AddRound(new List<(string, string)> { (seeded[0], seeded[1]) }, TournamentStage.Final, 1);
            return;
        }
        if (seeded.Count < 8)           // two groups: A1 v B2, B1 v A2
        {
            var semi = new List<(string, string)>();
            int half = winners.Count;
            for (int i = 0; i < half && i + 1 < seeded.Count; i++)
            {
                string w = winners[i];
                string r = runners[(i + 1) % Math.Max(1, runners.Count)];
                if (r != w) semi.Add((w, r));
            }
            if (semi.Count < 2) semi.Add((seeded[0], seeded[^1]));
            AddRound(semi.Distinct().ToList(), TournamentStage.SemiFinal, 1);
            return;
        }
        // Four groups: A1 v B2, B1 v A2, C1 v D2, D1 v C2
        var qf = new List<(string, string)>();
        for (int i = 0; i + 1 < winners.Count; i += 2)
        {
            qf.Add((winners[i], runners[i + 1]));
            qf.Add((winners[i + 1], runners[i]));
        }
        AddRound(qf, TournamentStage.QuarterFinal, 1);
    }

    private void BuildNextKnockoutRound()
    {
        var winners = Fixtures.Where(f => f.Stage == CurrentStage && f.Played)
            .OrderBy(f => f.Round).ThenBy(f => f.HomeTeam, StringComparer.Ordinal)
            .Select(f => f.Winner).ToList();
        if (winners.Count < 2) return;
        var pairs = new List<(string, string)>();
        for (int i = 0; i + 1 < winners.Count; i += 2) pairs.Add((winners[i], winners[i + 1]));
        if (pairs.Count == 0) return;
        AddRound(pairs, StageForSize(pairs.Count * 2), Fixtures.Max(f => f.Round) + 1);
    }

    private static TournamentStage StageForSize(int teamsLeft) => teamsLeft switch
    {
        >= 16 => TournamentStage.RoundOf16,
        8 => TournamentStage.QuarterFinal,
        4 => TournamentStage.SemiFinal,
        _ => TournamentStage.Final,
    };

    private void AddRound(List<(string home, string away)> pairs, TournamentStage stage, int round)
    {
        CurrentStage = stage;
        int r = 1;
        foreach (var (home, away) in pairs)
            Fixtures.Add(new TournamentFixture
            {
                HomeTeam = home, AwayTeam = away, Stage = stage, Round = r++,
            });
    }

    /// <summary>Legacy accessor kept for callers that want the player's next tie.</summary>
    public TournamentFixture? GetNextFixture() => NextPlayerFixture;

    // ---------------------------------------------------------------- data

    public static List<InternationalTeam> GetWorldCupTeams() => new()
    {
        new() { Name="Brazil", Short="BRA", Confederation="CONMEBOL", Strength=0.92f, FlagColor="#009739" },
        new() { Name="Argentina", Short="ARG", Confederation="CONMEBOL", Strength=0.91f, FlagColor="#74ACDF" },
        new() { Name="France", Short="FRA", Confederation="UEFA", Strength=0.90f, FlagColor="#002654" },
        new() { Name="England", Short="ENG", Confederation="UEFA", Strength=0.89f, FlagColor="#CE1124" },
        new() { Name="Spain", Short="ESP", Confederation="UEFA", Strength=0.88f, FlagColor="#F1BF00" },
        new() { Name="Germany", Short="GER", Confederation="UEFA", Strength=0.87f, FlagColor="#000000" },
        new() { Name="Portugal", Short="POR", Confederation="UEFA", Strength=0.86f, FlagColor="#046A38" },
        new() { Name="Netherlands", Short="NED", Confederation="UEFA", Strength=0.85f, FlagColor="#FF4F00" },
        new() { Name="Italy", Short="ITA", Confederation="UEFA", Strength=0.84f, FlagColor="#009246" },
        new() { Name="Belgium", Short="BEL", Confederation="UEFA", Strength=0.83f, FlagColor="#FCD116" },
        new() { Name="Croatia", Short="CRO", Confederation="UEFA", Strength=0.82f, FlagColor="#E63946" },
        new() { Name="Denmark", Short="DEN", Confederation="UEFA", Strength=0.79f, FlagColor="#C60C30" },
        new() { Name="Uruguay", Short="URU", Confederation="CONMEBOL", Strength=0.81f, FlagColor="#0038A8" },
        new() { Name="Colombia", Short="COL", Confederation="CONMEBOL", Strength=0.80f, FlagColor="#FCD116" },
        new() { Name="Ecuador", Short="ECU", Confederation="CONMEBOL", Strength=0.76f, FlagColor="#FFDD00" },
        new() { Name="Chile", Short="CHI", Confederation="CONMEBOL", Strength=0.75f, FlagColor="#D52B1E" },
        new() { Name="Peru", Short="PER", Confederation="CONMEBOL", Strength=0.73f, FlagColor="#D91023" },
        new() { Name="Paraguay", Short="PAR", Confederation="CONMEBOL", Strength=0.72f, FlagColor="#0038A8" },
        new() { Name="Mexico", Short="MEX", Confederation="CONCACAF", Strength=0.78f, FlagColor="#006847" },
        new() { Name="USA", Short="USA", Confederation="CONCACAF", Strength=0.77f, FlagColor="#3C3B6E" },
        new() { Name="Japan", Short="JPN", Confederation="AFC", Strength=0.79f, FlagColor="#BC002D" },
        new() { Name="South Korea", Short="KOR", Confederation="AFC", Strength=0.76f, FlagColor="#003478" },
        new() { Name="Morocco", Short="MAR", Confederation="CAF", Strength=0.80f, FlagColor="#C1272D" },
        new() { Name="Senegal", Short="SEN", Confederation="CAF", Strength=0.78f, FlagColor="#00853F" },
    };
}
