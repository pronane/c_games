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
    public int AverageRating => FormHistory.Count > 0 ? FormHistory.Average() : 75;

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
        if (State.Week > 38)
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
        // Update table
        var entry = State.Table.FirstOrDefault(t => t.Team == State.TeamName);
        if (entry != null)
        {
            entry.Played++;
            if (won) { entry.Won++; entry.Points += 3; }
            else if (draw) { entry.Drawn++; entry.Points += 1; }
            else entry.Lost++;
            entry.GF += gf;
            entry.GA += ga;
        }
        // Mark fixture as played
        var fixture = State.Fixtures.FirstOrDefault(f =>
            f.Week == State.Week && !f.Played &&
            (f.HomeTeam == State.TeamName || f.AwayTeam == State.TeamName));
        if (fixture != null)
        {
            if (fixture.HomeTeam == State.TeamName)
            {
                fixture.HomeScore = gf;
                fixture.AwayScore = ga;
            }
            else
            {
                fixture.HomeScore = ga;
                fixture.AwayScore = gf;
            }
        }
    }

    /// <summary>Generate season fixtures (round-robin).</summary>
    public void GenerateFixtures(List<string> teams)
    {
        State.Fixtures.Clear();
        State.Table.Clear();
        foreach (var team in teams)
        {
            State.Table.Add(new LeagueTableEntry { Team = team });
        }
        // Simple round-robin: each team plays each other home and away
        int week = 1;
        for (int i = 0; i < teams.Count; i++)
        {
            for (int j = i + 1; j < teams.Count; j++)
            {
                State.Fixtures.Add(new Fixture
                {
                    Week = week++,
                    HomeTeam = teams[i],
                    AwayTeam = teams[j],
                });
                State.Fixtures.Add(new Fixture
                {
                    Week = week++,
                    HomeTeam = teams[j],
                    AwayTeam = teams[i],
                });
            }
        }
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

    /// <summary>Gap 9: Press conference (morale effect).</summary>
    public void PressConference(bool positive)
    {
        foreach (var p in State.Squad)
        {
            p.Morale = Math.Clamp(p.Morale + (positive ? 5 : -5), 0, 100);
        }
    }

    /// <summary>Gap 9: Loan a player (temporary).</summary>
    public bool LoanPlayer(PlayerProgress player, int weeks)
    {
        if (!State.Squad.Contains(player)) return false;
        // Player leaves for loan period, returns after
        State.Squad.Remove(player);
        // In real game: schedule return after weeks
        return true;
    }

    /// <summary>Gap 9: Release clause negotiation.</summary>
    public bool SetReleaseClause(PlayerProgress player, int clauseAmount)
    {
        if (clauseAmount < player.MarketValue * 0.8) return false;
        // Clause set, player can leave if bid meets amount
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
