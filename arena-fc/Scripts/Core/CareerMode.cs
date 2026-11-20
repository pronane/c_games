// Arena FC — Career and Ultimate Team progression modes (Phase 2).
// Player progression, transfer market, season structure, youth academy,
// contract negotiations, morale/form effects.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Career mode state.</summary>
public class CareerState
{
    public string TeamName = "Arena FC";
    public int Season = 1;
    public int Week = 1;
    public int Points = 0;
    public int Wins, Draws, Losses;
    public int GoalsFor, GoalsAgainst;
    public int TransferBudget = 1000000;
    public int WageBudget = 500000;
    public List<PlayerProgress> Squad = new();
    public List<Fixture> Fixtures = new();
    public List<LeagueTableEntry> Table = new();
    public List<TransferOffer> TransferMarket = new();
    public List<PlayerProgress> Academy = new();
    public int Division = 2; // 1 = top, 2 = second, 3 = third
    public int PromotionSpots = 2;
    public int RelegationSpots = 2;

    public int GoalDifference => GoalsFor - GoalsAgainst;
    public int TotalPlayed => Wins + Draws + Losses;
}

/// <summary>A league fixture.</summary>
public class Fixture
{
    public int Week;
    public string HomeTeam = "";
    public string AwayTeam = "";
    public int HomeScore = -1;
    public int AwayScore = -1;
    public bool Played => HomeScore >= 0;
}

/// <summary>League table entry.</summary>
public class LeagueTableEntry
{
    public string Team = "";
    public int Played, Won, Drawn, Lost;
    public int GF, GA, Points;
    public int GoalDifference => GF - GA;
}

/// <summary>Transfer market offer.</summary>
public class TransferOffer
{
    public PlayerProgress Player = new();
    public int Price;
    public string SellingClub = "";
    public int WageDemand;
    public bool Accepted;
}

/// <summary>Individual player progression.</summary>
public class PlayerProgress
{
    public string Name = "";
    public int Age = 20;
    public int Overall;
    public int Pace, Shooting, Passing, Defending, Goalkeeping;
    public int Morale = 75;
    public int Fitness = 100;
    public int Goals, Assists, Appearances;
    public int Potential; // max overall they can reach
    public int XP;
    public int XPToNextLevel = 100;
    public int Wage = 10000;
    public int ContractYears = 3;
    public string Position = "CM";
    public List<int> FormHistory = new(); // last 5 match ratings
    public int AverageRating => FormHistory.Count > 0 ? (int)FormHistory.Average() : 75;

    public void Train(string attribute, int amount = 1)
    {
        switch (attribute)
        {
            case "pace": Pace = Math.Min(Potential, Pace + amount); break;
            case "shooting": Shooting = Math.Min(Potential, Shooting + amount); break;
            case "passing": Passing = Math.Min(Potential, Passing + amount); break;
            case "defending": Defending = Math.Min(Potential, Defending + amount); break;
            case "goalkeeping": Goalkeeping = Math.Min(Potential, Goalkeeping + amount); break;
        }
        RecalculateOverall();
    }

    public void RecalculateOverall()
    {
        Overall = (Pace + Shooting + Passing + Defending + Goalkeeping) / 5;
    }

    public void PlayMatch(bool won, int goals, int assists, int rating = 75)
    {
        Appearances++;
        Goals += goals;
        Assists += assists;
        // Morale: win +5, loss -3, draw +1; rating >80 boosts morale
        Morale = Math.Clamp(Morale + (won ? 5 : won == false && rating < 60 ? -5 : -3) + (rating > 80 ? 2 : 0), 0, 100);
        Fitness = Math.Max(0, Fitness - 15);
        // XP gain: base 10 + goals*5 + assists*3 + rating bonus
        int xpGain = 10 + goals * 5 + assists * 3 + Math.Max(0, (rating - 70) / 5);
        XP += xpGain;
        // Level up: increase attributes based on position
        while (XP >= XPToNextLevel)
        {
            XP -= XPToNextLevel;
            XPToNextLevel = (int)(XPToNextLevel * 1.2);
            LevelUp();
        }
        // Form history
        FormHistory.Add(rating);
        if (FormHistory.Count > 5) FormHistory.RemoveAt(0);
        // Morale affects attributes: high morale = +1 to key attribute
        if (Morale > 85 && Overall < Potential)
        {
            Train(Position switch
            {
                "ST" or "LW" or "RW" => "shooting",
                "CM" or "CAM" or "CDM" => "passing",
                "CB" or "LB" or "RB" => "defending",
                "GK" => "goalkeeping",
                _ => "pace",
            }, 1);
        }
    }

    private void LevelUp()
    {
        // Increase 1-2 attributes based on position, up to Potential
        var attrs = Position switch
        {
            "ST" or "LW" or "RW" => new[] { "shooting", "pace" },
            "CM" or "CAM" => new[] { "passing", "pace" },
            "CDM" => new[] { "passing", "defending" },
            "CB" or "LB" or "RB" => new[] { "defending", "pace" },
            "GK" => new[] { "goalkeeping", "defending" },
            _ => new[] { "pace", "passing" },
        };
        foreach (var attr in attrs)
        {
            if (Overall < Potential)
                Train(attr, 1);
        }
    }

    public void Rest()
    {
        Fitness = Math.Min(100, Fitness + 30);
    }

    /// <summary>Effective overall accounting for morale and fitness.</summary>
    public int EffectiveOverall
    {
        get
        {
            int eff = Overall;
            if (Morale < 40) eff -= 3;
            else if (Morale > 80) eff += 2;
            if (Fitness < 50) eff -= 2;
            return Math.Max(30, eff);
        }
    }

    public int MarketValue => (int)(Overall * Overall * 500 + Potential * 100);
}

/// <summary>Ultimate Team mode state.</summary>
public class UltimateTeamState
{
    public int Coins = 5000;
    public int TeamRating;
    public int Chemistry;
    public List<PlayerProgress> Squad = new();
    public Dictionary<string, int> Consumables = new();

    public void AddCoins(int amount) => Coins += amount;
    public bool SpendCoins(int amount)
    {
        if (Coins < amount) return false;
        Coins -= amount;
        return true;
    }
}

/// <summary>Career mode manager (Phase 2).</summary>
public class CareerMode
{
    private readonly Random _rng = new(42);
    public CareerState State = new();
    public UltimateTeamState UltimateTeam = new();

    public void AdvanceWeek()
    {
        State.Week++;
        if (State.Week > MatchWeeks)
        {
            EndSeason();
        }
        foreach (var p in State.Squad) p.Rest();
        // Pay wages weekly
        int totalWages = State.Squad.Sum(p => p.Wage / 52);
        State.WageBudget -= totalWages;
    }

    public void RecordResult(bool won, bool draw, int gf, int ga)
    {
        if (won) { State.Wins++; State.Points += 3; }
        else if (draw) { State.Draws++; State.Points += 1; }
        else State.Losses++;
        State.GoalsFor += gf;
        State.GoalsAgainst += ga;

        // Mark the player's fixture for this week.
        var fixture = State.Fixtures.FirstOrDefault(f =>
            f.Week == State.Week && !f.Played &&
            (f.HomeTeam == State.TeamName || f.AwayTeam == State.TeamName));
        if (fixture != null)
        {
            if (fixture.HomeTeam == State.TeamName) { fixture.HomeScore = gf; fixture.AwayScore = ga; }
            else { fixture.HomeScore = ga; fixture.AwayScore = gf; }
        }
        RebuildTable();
        // Everyone who played loses fitness, gains an appearance and moves on form.
        foreach (var p in State.Squad) p.PlayMatch(won, 0, 0, 70 + (won ? 8 : draw ? 4 : 0));
    }

    /// <summary>Recompute the league table from the fixtures that have been played.
    /// Incremental updates drifted (the opponent's row was never credited).</summary>
    public void RebuildTable()
    {
        foreach (var e in State.Table)
        {
            e.Played = e.Won = e.Drawn = e.Lost = e.GF = e.GA = e.Points = 0;
        }
        foreach (var f in State.Fixtures)
        {
            if (!f.Played) continue;
            ApplyToTable(f.HomeTeam, f.HomeScore, f.AwayTeam, f.AwayScore);
        }
    }

    private void ApplyToTable(string home, int hs, string away, int aScore)
    {
        var h = State.Table.FirstOrDefault(t => t.Team == home);
        var a = State.Table.FirstOrDefault(t => t.Team == away);
        if (h == null || a == null) return;
        h.Played++; a.Played++;
        h.GF += hs; h.GA += aScore; a.GF += aScore; a.GA += hs;
        if (hs > aScore) { h.Won++; a.Lost++; h.Points += 3; }
        else if (aScore > hs) { a.Won++; h.Lost++; a.Points += 3; }
        else { h.Drawn++; a.Drawn++; h.Points++; a.Points++; }
    }

    /// <summary>Generate season fixtures: a proper double round-robin where every
    /// team plays exactly once per match week.  The old version gave each *fixture*
    /// its own week (10 teams => 90 "weeks"), so a career ended after two games.</summary>
    public void GenerateFixtures(List<string> teams)
    {
        State.Fixtures.Clear();
        State.Table.Clear();
        foreach (var team in teams)
            State.Table.Add(new LeagueTableEntry { Team = team });

        var pool = new List<string>(teams);
        if (pool.Count % 2 == 1) pool.Add("BYE");
        int n = pool.Count;
        int rounds = n - 1;

        // Circle method: fix pool[0] and rotate the rest.  Each round is one
        // match week for the whole division; the second half is the reverse leg.
        for (int r = 0; r < rounds; r++)
        {
            for (int i = 0; i < n / 2; i++)
            {
                string a = pool[i], b = pool[n - 1 - i];
                if (a == "BYE" || b == "BYE") continue;
                // Alternate home advantage so no club is always at home.
                bool aAtHome = (r + i) % 2 == 0;
                string home = aAtHome ? a : b;
                string away = aAtHome ? b : a;
                State.Fixtures.Add(new Fixture { Week = r + 1, HomeTeam = home, AwayTeam = away });
                State.Fixtures.Add(new Fixture { Week = r + 1 + rounds, HomeTeam = away, AwayTeam = home });
            }
            // Rotate every club except the first.
            var last = pool[n - 1];
            pool.RemoveAt(n - 1);
            pool.Insert(1, last);
        }
        State.Week = 1;
        MatchWeeks = rounds * 2;
    }

    /// <summary>Number of match weeks in the current season.</summary>
    public int MatchWeeks = 38;

    // ---- Season driving API -------------------------------------------------

    /// <summary>Create a brand-new career: squad, league, market and academy.</summary>
    public void StartNew(string teamName, List<string> leagueTeams, int seed = 42)
    {
        var teams = new List<string>(leagueTeams);
        if (!teams.Contains(teamName))
        {
            if (teams.Count == 0) teams.Add(teamName);
            else teams[0] = teamName;
        }
        State = new CareerState
        {
            TeamName = teamName,
            Division = 2,
            Season = 1,
            Week = 1,
            TransferBudget = 2_500_000,
            WageBudget = 450_000,
            PromotionSpots = 2,
            RelegationSpots = 2,
        };
        State.Squad.AddRange(BuildSquad(seed));
        GenerateFixtures(teams);
        GenerateTransferMarket(10);
        GenerateAcademy(5);
        RebuildTable();
    }

    private static readonly string[] _positions = { "GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CM", "CAM", "RW", "LW", "ST", "ST", "CB", "CM", "ST" };
    private static readonly string[] _first = { "Alex", "Marco", "Nico", "Jamie", "Rafael", "Yuki", "Omar", "Luca", "Elias", "Tomas", "Kai", "Ivan", "Samir", "Diego", "Felix", "Noah" };
    private static readonly string[] _last = { "Varela", "Okafor", "Bianchi", "Kovac", "Silva", "Nakamura", "Haddad", "Rossi", "Lindqvist", "Mendes", "Adeyemi", "Petrov", "Costa", "Duarte", "Novak", "Berg" };

    private static List<PlayerProgress> BuildSquad(int seed)
    {
        var rng = new Random(seed);
        var squad = new List<PlayerProgress>(_positions.Length);
        for (int i = 0; i < _positions.Length; i++)
        {
            int overall = rng.Next(66, 79);
            var p = new PlayerProgress
            {
                Name = _first[rng.Next(_first.Length)] + " " + _last[rng.Next(_last.Length)],
                Age = rng.Next(18, 34),
                Overall = overall,
                Potential = Math.Min(99, overall + rng.Next(2, 12)),
                Position = _positions[i],
                Pace = Math.Clamp(overall + rng.Next(-6, 7), 40, 99),
                Shooting = Math.Clamp(overall + rng.Next(-8, 7), 40, 99),
                Passing = Math.Clamp(overall + rng.Next(-6, 7), 40, 99),
                Defending = Math.Clamp(overall + rng.Next(-8, 7), 40, 99),
                Goalkeeping = _positions[i] == "GK" ? Math.Clamp(overall + 4, 45, 99) : 10,
                Wage = rng.Next(8000, 24000),
                ContractYears = rng.Next(1, 5),
            };
            squad.Add(p);
        }
        return squad;
    }

    /// <summary>The player's next unplayed fixture.</summary>
    public Fixture? NextFixture => State.Fixtures.FirstOrDefault(f => !f.Played &&
        (f.HomeTeam == State.TeamName || f.AwayTeam == State.TeamName));

    public List<LeagueTableEntry> TableSorted => State.Table
        .OrderByDescending(t => t.Points).ThenByDescending(t => t.GoalDifference)
        .ThenByDescending(t => t.GF).ThenBy(t => t.Team, StringComparer.Ordinal).ToList();

    public int Position => TableSorted.FindIndex(t => t.Team == State.TeamName) + 1;
    public string Form => $"{State.Wins}W {State.Draws}D {State.Losses}L";

    /// <summary>Play the next fixture for the player's club and settle the week.</summary>
    public bool PlayNextResult(int goalsFor, int goalsAgainst)
    {
        var f = NextFixture;
        if (f == null) return false;
        State.Week = f.Week;
        RecordResult(goalsFor > goalsAgainst, goalsFor == goalsAgainst, goalsFor, goalsAgainst);
        SimulateOtherMatches(f.Week);
        AdvanceWeek();
        RebuildTable();
        return true;
    }

    /// <summary>Simulate every other fixture in a week from club strength.</summary>
    public void SimulateOtherMatches(int week)
    {
        foreach (var f in State.Fixtures.Where(x => x.Week == week && !x.Played).ToList())
        {
            float h = Strength(f.HomeTeam), a = Strength(f.AwayTeam);
            int hs = GoalsFor(h, a), aScore = GoalsFor(a, h);
            f.HomeScore = hs; f.AwayScore = aScore;
        }
        RebuildTable();
    }

    /// <summary>Goals for a side, from the strength gap.  Deterministic so a saved
    /// career replays the same way.</summary>
    private static int GoalsFor(float attack, float defence)
    {
        float lambda = Math.Clamp(1.25f + (attack - defence) * 2f, .25f, 4f);
        var rng = new Rng((int)(attack * 100003f + defence * 7919f) | 1);
        float roll = rng.Next();
        return Math.Clamp((int)MathF.Round(lambda + (roll - .5f) * 2.4f), 0, 5);
    }

    /// <summary>Club strength from the fictional club table (0.6 when unknown).</summary>
    public static float Strength(string team)
    {
        var club = Clubs.All.FirstOrDefault(c => c.Name == team);
        return club?.Strength ?? .70f;
    }

    /// <summary>Skip the current week without playing (simulates the player's match).</summary>
    public void SimulateWeek()
    {
        var f = NextFixture;
        if (f == null) return;
        State.Week = f.Week;
        int gf = GoalsFor(Strength(State.TeamName), .70f);
        int ga = GoalsFor(.70f, Strength(State.TeamName));
        RecordResult(gf > ga, gf == ga, gf, ga);
        SimulateOtherMatches(f.Week);
        AdvanceWeek();
        RebuildTable();
    }



    /// <summary>End of season: promotion/relegation, aging, reset.</summary>
    private void EndSeason()
    {
        // Determine promotion/relegation
        var sorted = State.Table.OrderByDescending(t => t.Points)
            .ThenByDescending(t => t.GoalDifference).ToList();
        int position = sorted.FindIndex(t => t.Team == State.TeamName) + 1;

        if (position <= State.PromotionSpots && State.Division > 1)
        {
            State.Division--;
            State.TransferBudget += 500000; // promotion bonus
        }
        else if (position > sorted.Count - State.RelegationSpots && State.Division < 3)
        {
            State.Division++;
            State.TransferBudget = Math.Max(100000, State.TransferBudget - 200000);
        }

        State.Season++;
        State.Week = 1;
        State.Points = 0;
        State.Wins = State.Draws = State.Losses = 0;
        State.GoalsFor = State.GoalsAgainst = 0;
        // A new season needs new fixtures, not last season's played-out ones.
        GenerateFixtures(State.Table.Select(t => t.Team).ToList());

        // Age players, adjust potential
        foreach (var p in State.Squad)
        {
            p.Age++;
            p.Fitness = 100;
            p.Morale = 75;
            if (p.Age > 30)
            {
                // Decline after 30
                p.Pace = Math.Max(30, p.Pace - 1);
                if (p.Age > 35) p.Potential = Math.Max(p.Overall, p.Potential - 2);
            }
            p.ContractYears--;
            if (p.ContractYears <= 0)
            {
                // Player leaves if contract expired
                p.Morale = 0;
            }
        }
        // Remove expired contracts
        State.Squad.RemoveAll(p => p.ContractYears <= 0);
    }

    /// <summary>Generate transfer market offers.</summary>
    public void GenerateTransferMarket(int count = 10)
    {
        State.TransferMarket.Clear();
        string[] names = { "James", "Lucas", "Ethan", "Noah", "Mason", "Logan", "Owen", "Caleb", "Isaac", "Ryan" };
        string[] positions = { "ST", "CM", "CB", "GK", "LW", "RW", "LB", "RB", "CDM", "CAM" };
        string[] clubs = { "Northgate", "Riverside", "Eastfield", "Westham", "Southport" };

        for (int i = 0; i < count; i++)
        {
            var player = new PlayerProgress
            {
                Name = names[_rng.Next(names.Length)] + " " + names[_rng.Next(names.Length)],
                Age = _rng.Next(18, 32),
                Position = positions[_rng.Next(positions.Length)],
                Pace = _rng.Next(55, 90),
                Shooting = _rng.Next(55, 90),
                Passing = _rng.Next(55, 90),
                Defending = _rng.Next(55, 90),
                Goalkeeping = _rng.Next(55, 90),
                Potential = _rng.Next(70, 95),
                Wage = _rng.Next(5000, 50000),
                ContractYears = _rng.Next(1, 5),
            };
            player.RecalculateOverall();
            State.TransferMarket.Add(new TransferOffer
            {
                Player = player,
                Price = player.MarketValue,
                SellingClub = clubs[_rng.Next(clubs.Length)],
                WageDemand = player.Wage,
            });
        }
    }

    /// <summary>Buy a player from the transfer market.</summary>
    public bool BuyPlayer(TransferOffer offer)
    {
        if (State.TransferBudget < offer.Price) return false;
        if (State.WageBudget < offer.WageDemand * 52) return false;
        State.TransferBudget -= offer.Price;
        State.Squad.Add(offer.Player);
        State.TransferMarket.Remove(offer);
        return true;
    }

    /// <summary>Sell a player.</summary>
    public bool SellPlayer(PlayerProgress player)
    {
        if (!State.Squad.Contains(player)) return false;
        State.TransferBudget += (int)(player.MarketValue * 0.8); // 80% of value
        State.Squad.Remove(player);
        return true;
    }

    /// <summary>Generate youth academy prospects.</summary>
    public void GenerateAcademy(int count = 5)
    {
        State.Academy.Clear();
        string[] names = { "Kai", "Leo", "Finn", "Hugo", "Oscar", "Felix", "Theo", "Max", "Sam", "Ben" };
        string[] positions = { "ST", "CM", "CB", "GK", "LW", "RW" };

        for (int i = 0; i < count; i++)
        {
            var prospect = new PlayerProgress
            {
                Name = names[_rng.Next(names.Length)] + " " + names[_rng.Next(names.Length)],
                Age = _rng.Next(16, 19),
                Position = positions[_rng.Next(positions.Length)],
                Pace = _rng.Next(50, 80),
                Shooting = _rng.Next(50, 80),
                Passing = _rng.Next(50, 80),
                Defending = _rng.Next(50, 80),
                Goalkeeping = _rng.Next(50, 80),
                Potential = _rng.Next(80, 99), // high potential
                Wage = _rng.Next(1000, 5000),
                ContractYears = 3,
            };
            prospect.RecalculateOverall();
            State.Academy.Add(prospect);
        }
    }

    /// <summary>Promote an academy player to the first team.</summary>
    public bool PromoteAcademy(PlayerProgress prospect)
    {
        if (!State.Academy.Contains(prospect)) return false;
        State.Academy.Remove(prospect);
        State.Squad.Add(prospect);
        return true;
    }

    /// <summary>Negotiate a new contract for a player.</summary>
    public bool NegotiateContract(PlayerProgress player, int newWage, int newYears)
    {
        // Player accepts if wage is reasonable for their overall
        int fairWage = player.Overall * 800;
        if (newWage < fairWage * 0.8) return false; // insulting offer
        if (State.WageBudget < newWage * newYears) return false;
        player.Wage = newWage;
        player.ContractYears = newYears;
        player.Morale = Math.Min(100, player.Morale + 10);
        return true;
    }
}
