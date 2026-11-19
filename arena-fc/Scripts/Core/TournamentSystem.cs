// Arena FC — Tournament & League system (Phase 8).
// League mode, Champions League, World Cup, Euros, Copa America,
// domestic cups, international tournaments.
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

/// <summary>A tournament fixture.</summary>
public class TournamentFixture
{
    public string HomeTeam = "";
    public string AwayTeam = "";
    public int HomeScore = -1;
    public int AwayScore = -1;
    public TournamentStage Stage;
    public int Round;
    public bool Played => HomeScore >= 0;
    public string Winner => Played ? (HomeScore > AwayScore ? HomeTeam : AwayTeam) : "";
}

/// <summary>Group table entry.</summary>
public class GroupTableEntry
{
    public string Team = "";
    public int Played, Won, Drawn, Lost;
    public int GF, GA, Points;
    public int GoalDifference => GF - GA;
}

/// <summary>International team (for World Cup/Euros/Copa).</summary>
public class InternationalTeam
{
    public string Name = "";
    public string Short = "";
    public string Confederation = ""; // UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC
    public float Strength = 0.75f;
    public string FlagColor = "#ffffff";
}

/// <summary>Tournament manager.</summary>
public class TournamentSystem
{
    private readonly Random _rng = new(789);
    public TournamentType Type;
    public TournamentStage CurrentStage;
    public List<TournamentFixture> Fixtures = new();
    public List<GroupTableEntry> GroupTable = new();
    public List<string> Teams = new();
    public string PlayerTeam = "";
    public bool IsPlayerEliminated;

    /// <summary>Generate league fixtures (round-robin).</summary>
    public void GenerateLeague(List<string> teams)
    {
        Type = TournamentType.League;
        Teams = teams;
        Fixtures.Clear();
        GroupTable.Clear();
        foreach (var team in teams)
        {
            GroupTable.Add(new GroupTableEntry { Team = team });
        }
        int round = 1;
        for (int i = 0; i < teams.Count; i++)
        {
            for (int j = i + 1; j < teams.Count; j++)
            {
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = teams[i],
                    AwayTeam = teams[j],
                    Stage = TournamentStage.LeaguePhase,
                    Round = round++,
                });
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = teams[j],
                    AwayTeam = teams[i],
                    Stage = TournamentStage.LeaguePhase,
                    Round = round++,
                });
            }
        }
    }

    /// <summary>Generate Champions League (group + knockout).</summary>
    public void GenerateChampionsLeague(List<string> teams)
    {
        Type = TournamentType.ChampionsLeague;
        Teams = teams;
        CurrentStage = TournamentStage.GroupStage;
        Fixtures.Clear();
        GroupTable.Clear();
        // 4 groups of 4 (simplified: 1 group of 8 for demo)
        foreach (var team in teams.Take(8))
        {
            GroupTable.Add(new GroupTableEntry { Team = team });
        }
        // Group fixtures
        var groupTeams = teams.Take(8).ToList();
        int round = 1;
        for (int i = 0; i < groupTeams.Count; i++)
        {
            for (int j = i + 1; j < groupTeams.Count; j++)
            {
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = groupTeams[i],
                    AwayTeam = groupTeams[j],
                    Stage = TournamentStage.GroupStage,
                    Round = round++,
                });
            }
        }
    }

    /// <summary>Generate World Cup (32 teams, groups + knockout).</summary>
    public void GenerateWorldCup(List<InternationalTeam> teams)
    {
        Type = TournamentType.WorldCup;
        Teams = teams.Select(t => t.Name).ToList();
        CurrentStage = TournamentStage.GroupStage;
        Fixtures.Clear();
        GroupTable.Clear();
        // 8 groups of 4 (simplified: 2 groups of 4 for demo)
        var groupTeams = teams.Take(8).Select(t => t.Name).ToList();
        foreach (var team in groupTeams)
        {
            GroupTable.Add(new GroupTableEntry { Team = team });
        }
        int round = 1;
        for (int i = 0; i < groupTeams.Count; i++)
        {
            for (int j = i + 1; j < groupTeams.Count; j++)
            {
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = groupTeams[i],
                    AwayTeam = groupTeams[j],
                    Stage = TournamentStage.GroupStage,
                    Round = round++,
                });
            }
        }
    }

    /// <summary>Generate Euros (24 teams, UEFA).</summary>
    public void GenerateEuros(List<InternationalTeam> teams)
    {
        Type = TournamentType.Euros;
        var uefaTeams = teams.Where(t => t.Confederation == "UEFA").Take(8).ToList();
        Teams = uefaTeams.Select(t => t.Name).ToList();
        CurrentStage = TournamentStage.GroupStage;
        Fixtures.Clear();
        GroupTable.Clear();
        foreach (var team in Teams)
        {
            GroupTable.Add(new GroupTableEntry { Team = team });
        }
        int round = 1;
        for (int i = 0; i < Teams.Count; i++)
        {
            for (int j = i + 1; j < Teams.Count; j++)
            {
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = Teams[i],
                    AwayTeam = Teams[j],
                    Stage = TournamentStage.GroupStage,
                    Round = round++,
                });
            }
        }
    }

    /// <summary>Generate Copa America (CONMEBOL).</summary>
    public void GenerateCopaAmerica(List<InternationalTeam> teams)
    {
        Type = TournamentType.CopaAmerica;
        var conmebolTeams = teams.Where(t => t.Confederation == "CONMEBOL").Take(8).ToList();
        Teams = conmebolTeams.Select(t => t.Name).ToList();
        CurrentStage = TournamentStage.GroupStage;
        Fixtures.Clear();
        GroupTable.Clear();
        foreach (var team in Teams)
        {
            GroupTable.Add(new GroupTableEntry { Team = team });
        }
        int round = 1;
        for (int i = 0; i < Teams.Count; i++)
        {
            for (int j = i + 1; j < Teams.Count; j++)
            {
                Fixtures.Add(new TournamentFixture
                {
                    HomeTeam = Teams[i],
                    AwayTeam = Teams[j],
                    Stage = TournamentStage.GroupStage,
                    Round = round++,
                });
            }
        }
    }

    /// <summary>Generate domestic cup (knockout).</summary>
    public void GenerateDomesticCup(List<string> teams)
    {
        Type = TournamentType.DomesticCup;
        Teams = teams;
        CurrentStage = TournamentStage.RoundOf16;
        Fixtures.Clear();
        // Pair teams randomly
        var shuffled = teams.OrderBy(_ => _rng.Next()).ToList();
        int round = 1;
        for (int i = 0; i < shuffled.Count - 1; i += 2)
        {
            Fixtures.Add(new TournamentFixture
            {
                HomeTeam = shuffled[i],
                AwayTeam = shuffled[i + 1],
                Stage = TournamentStage.RoundOf16,
                Round = round,
            });
        }
    }

    /// <summary>Record a match result.</summary>
    public void RecordResult(string homeTeam, string awayTeam, int homeScore, int awayScore)
    {
        var fixture = Fixtures.FirstOrDefault(f =>
            f.HomeTeam == homeTeam && f.AwayTeam == awayTeam && !f.Played);
        if (fixture != null)
        {
            fixture.HomeScore = homeScore;
            fixture.AwayScore = awayScore;
        }

        // Update group table
        var homeEntry = GroupTable.FirstOrDefault(t => t.Team == homeTeam);
        var awayEntry = GroupTable.FirstOrDefault(t => t.Team == awayTeam);
        if (homeEntry != null && awayEntry != null)
        {
            homeEntry.Played++;
            awayEntry.Played++;
            homeEntry.GF += homeScore;
            homeEntry.GA += awayScore;
            awayEntry.GF += awayScore;
            awayEntry.GA += homeScore;
            if (homeScore > awayScore)
            {
                homeEntry.Won++;
                homeEntry.Points += 3;
                awayEntry.Lost++;
            }
            else if (awayScore > homeScore)
            {
                awayEntry.Won++;
                awayEntry.Points += 3;
                homeEntry.Lost++;
            }
            else
            {
                homeEntry.Drawn++;
                awayEntry.Drawn++;
                homeEntry.Points += 1;
                awayEntry.Points += 1;
            }
        }

        // Check if player eliminated
        if (fixture != null && (fixture.HomeTeam == PlayerTeam || fixture.AwayTeam == PlayerTeam))
        {
            string winner = fixture.Winner;
            if (winner != PlayerTeam && fixture.Stage >= TournamentStage.RoundOf16)
            {
                IsPlayerEliminated = true;
            }
        }
    }

    /// <summary>Advance to knockout stage (top 2 from group).</summary>
    public void AdvanceToKnockout()
    {
        var sorted = GroupTable.OrderByDescending(t => t.Points)
            .ThenByDescending(t => t.GoalDifference).ToList();
        var qualified = sorted.Take(4).Select(t => t.Team).ToList(); // top 4
        CurrentStage = TournamentStage.QuarterFinal;
        Fixtures.Clear();
        // Semi-final pairings: 1v4, 2v3
        if (qualified.Count >= 4)
        {
            Fixtures.Add(new TournamentFixture
            {
                HomeTeam = qualified[0],
                AwayTeam = qualified[3],
                Stage = TournamentStage.SemiFinal,
                Round = 1,
            });
            Fixtures.Add(new TournamentFixture
            {
                HomeTeam = qualified[1],
                AwayTeam = qualified[2],
                Stage = TournamentStage.SemiFinal,
                Round = 1,
            });
        }
    }

    /// <summary>Get next fixture for player team.</summary>
    public TournamentFixture? GetNextFixture()
    {
        return Fixtures.FirstOrDefault(f =>
            !f.Played && (f.HomeTeam == PlayerTeam || f.AwayTeam == PlayerTeam));
    }

    /// <summary>Get league table sorted.</summary>
    public List<GroupTableEntry> GetTable()
    {
        return GroupTable.OrderByDescending(t => t.Points)
            .ThenByDescending(t => t.GoalDifference).ToList();
    }

    /// <summary>Get international teams for World Cup.</summary>
    public static List<InternationalTeam> GetWorldCupTeams()
    {
        return new List<InternationalTeam>
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
            new() { Name="Uruguay", Short="URU", Confederation="CONMEBOL", Strength=0.81f, FlagColor="#0038A8" },
            new() { Name="Colombia", Short="COL", Confederation="CONMEBOL", Strength=0.80f, FlagColor="#FCD116" },
            new() { Name="Mexico", Short="MEX", Confederation="CONCACAF", Strength=0.78f, FlagColor="#006847" },
            new() { Name="USA", Short="USA", Confederation="CONCACAF", Strength=0.77f, FlagColor="#3C3B6E" },
            new() { Name="Japan", Short="JPN", Confederation="AFC", Strength=0.79f, FlagColor="#BC002D" },
        };
    }
}
