// Arena FC — Ultimate Team system (Phase 9).
// Card-based squad building, chemistry, packs, Squad Battles,
// Division Rivals, SBCs.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Card rarity tiers.</summary>
public enum CardRarity
{
    Bronze,   // 45-64 OVR
    Silver,   // 65-74 OVR
    Gold,     // 75-84 OVR
    Rare,     // 85-89 OVR
    Icon,     // 90+ OVR (legends)
}

/// <summary>Player card.</summary>
public class PlayerCard
{
    public string Name = "";
    public int Overall;
    public CardRarity Rarity;
    public string Position = "CM";
    public string Club = "";
    public string League = "";
    public string Nation = "";
    public int Pace, Shooting, Passing, Defending, Physical;
    public int ChemistryStyle; // 0-3
    public bool IsInForm;
    public int Price;

    public CardRarity GetRarity()
    {
        if (Overall >= 90) return CardRarity.Icon;
        if (Overall >= 85) return CardRarity.Rare;
        if (Overall >= 75) return CardRarity.Gold;
        if (Overall >= 65) return CardRarity.Silver;
        return CardRarity.Bronze;
    }

    public int GetPrice()
    {
        return Overall switch
        {
            >= 90 => 50000,
            >= 85 => 25000,
            >= 80 => 10000,
            >= 75 => 5000,
            >= 70 => 2000,
            >= 65 => 1000,
            _ => 500,
        };
    }
}

/// <summary>Squad Battles difficulty.</summary>
public enum SquadBattlesDifficulty
{
    Beginner,   // 60 OVR, 100 coins
    Amateur,    // 70 OVR, 250 coins
    Pro,        // 80 OVR, 500 coins
    WorldClass, // 85 OVR, 1000 coins
    Legendary,  // 90 OVR, 2500 coins
}

/// <summary>Division Rivals division.</summary>
public enum Division
{
    Division10, // lowest
    Division9,
    Division8,
    Division7,
    Division6,
    Division5,
    Division4,
    Division3,
    Division2,
    Division1,  // highest
}

/// <summary>SBC (Squad Building Challenge).</summary>
public class SBC
{
    public string Name = "";
    public string Description = "";
    public int MinRating;
    public int MinChemistry;
    public int MinPlayers;
    public List<PlayerCard> Reward = new();
    public bool Completed;
}

/// <summary>Ultimate Team manager.</summary>
public class UltimateTeam
{
    private readonly Random _rng = new(999);
    public int Coins = 5000;
    public List<PlayerCard> Club = new();
    public List<PlayerCard> Squad = new(); // starting 11
    public Division CurrentDivision = Division.Division10;
    public int DivisionPoints;
    public int SquadBattlesPoints;
    public List<SBC> SBCs = new();
    // Feature 10: Evolutions
    public List<Evolution> Evolutions = new();

    /// <summary>Generate a random player card.</summary>
    public PlayerCard GenerateCard(int minOverall = 45, int maxOverall = 95)
    {
        int overall = _rng.Next(minOverall, maxOverall + 1);
        string[] names = { "James", "Lucas", "Ethan", "Noah", "Mason", "Logan", "Owen", "Caleb", "Isaac", "Ryan", "Kai", "Leo", "Finn", "Hugo", "Oscar" };
        string[] positions = { "ST", "CM", "CB", "GK", "LW", "RW", "LB", "RB", "CDM", "CAM" };
        string[] clubs = { "Harrow Lions", "Northgate United", "Riverport City", "Aurora SC", "Golden Gate FC" };
        string[] leagues = { "Premier League", "La Liga", "Serie A", "Bundesliga" };
        string[] nations = { "England", "Brazil", "France", "Spain", "Germany", "Argentina" };

        var card = new PlayerCard
        {
            Name = names[_rng.Next(names.Length)] + " " + names[_rng.Next(names.Length)],
            Overall = overall,
            Position = positions[_rng.Next(positions.Length)],
            Club = clubs[_rng.Next(clubs.Length)],
            League = leagues[_rng.Next(leagues.Length)],
            Nation = nations[_rng.Next(nations.Length)],
            Pace = Math.Clamp(overall + _rng.Next(-5, 6), 30, 99),
            Shooting = Math.Clamp(overall + _rng.Next(-5, 6), 30, 99),
            Passing = Math.Clamp(overall + _rng.Next(-5, 6), 30, 99),
            Defending = Math.Clamp(overall + _rng.Next(-5, 6), 30, 99),
            Physical = Math.Clamp(overall + _rng.Next(-5, 6), 30, 99),
            IsInForm = _rng.Next(10) == 0, // 10% in form
        };
        card.Rarity = card.GetRarity();
        card.Price = card.GetPrice();
        return card;
    }

    /// <summary>Open a pack (costs coins, gives 3 cards).</summary>
    public List<PlayerCard> OpenPack(int packType = 0)
    {
        int cost = packType switch
        {
            0 => 500,   // Bronze pack
            1 => 1500,  // Silver pack
            2 => 5000,  // Gold pack
            _ => 10000, // Premium pack
        };
        if (Coins < cost) return new List<PlayerCard>();
        Coins -= cost;

        var cards = new List<PlayerCard>();
        for (int i = 0; i < 3; i++)
        {
            int minOvr = packType switch
            {
                0 => 45,
                1 => 65,
                2 => 75,
                _ => 80,
            };
            int maxOvr = packType switch
            {
                0 => 64,
                1 => 74,
                2 => 84,
                _ => 95,
            };
            var card = GenerateCard(minOvr, maxOvr);
            cards.Add(card);
            Club.Add(card);
        }
        return cards;
    }

    /// <summary>Calculate team chemistry (0-100).</summary>
    public int CalculateChemistry()
    {
        if (Squad.Count < 11) return 0;
        int chemistry = 0;
        // Club links: same club = +2 per pair
        var clubGroups = Squad.GroupBy(c => c.Club);
        foreach (var group in clubGroups)
        {
            int count = group.Count();
            chemistry += count * (count - 1) / 2 * 2;
        }
        // League links: same league = +1 per pair
        var leagueGroups = Squad.GroupBy(c => c.League);
        foreach (var group in leagueGroups)
        {
            int count = group.Count();
            chemistry += count * (count - 1) / 2;
        }
        // Nation links: same nation = +1 per pair
        var nationGroups = Squad.GroupBy(c => c.Nation);
        foreach (var group in nationGroups)
        {
            int count = group.Count();
            chemistry += count * (count - 1) / 2;
        }
        return Math.Clamp(chemistry, 0, 100);
    }

    /// <summary>Calculate team rating (average OVR).</summary>
    public int CalculateRating()
    {
        if (Squad.Count == 0) return 0;
        return (int)Squad.Average(c => c.Overall);
    }

    /// <summary>Play Squad Battles (vs AI).</summary>
    public int PlaySquadBattles(SquadBattlesDifficulty difficulty, bool won, int goalsFor, int goalsAgainst)
    {
        int basePoints = difficulty switch
        {
            SquadBattlesDifficulty.Beginner => 100,
            SquadBattlesDifficulty.Amateur => 250,
            SquadBattlesDifficulty.Pro => 500,
            SquadBattlesDifficulty.WorldClass => 1000,
            SquadBattlesDifficulty.Legendary => 2500,
            _ => 100,
        };
        int points = basePoints;
        if (won) points += 100;
        points += goalsFor * 10;
        SquadBattlesPoints += points;
        Coins += points / 10; // convert to coins
        return points;
    }

    /// <summary>Play Division Rivals (online ranked).</summary>
    public void PlayDivisionRivals(bool won, bool draw)
    {
        if (won) DivisionPoints += 3;
        else if (draw) DivisionPoints += 1;
        else DivisionPoints -= 2;

        // Promotion/relegation
        if (DivisionPoints >= 15 && CurrentDivision < Division.Division1)
        {
            CurrentDivision++;
            DivisionPoints = 0;
            Coins += 1000; // promotion bonus
        }
        else if (DivisionPoints <= -10 && CurrentDivision > Division.Division10)
        {
            CurrentDivision--;
            DivisionPoints = 0;
        }
    }

    /// <summary>Generate SBCs.</summary>
    public void GenerateSBCs()
    {
        SBCs.Clear();
        SBCs.Add(new SBC
        {
            Name = "Bronze Upgrade",
            Description = "Submit 3 Bronze players (45-64 OVR)",
            MinRating = 45,
            MinPlayers = 3,
            Reward = new List<PlayerCard> { GenerateCard(65, 74) },
        });
        SBCs.Add(new SBC
        {
            Name = "Silver to Gold",
            Description = "Submit 5 Silver players (65-74 OVR)",
            MinRating = 65,
            MinPlayers = 5,
            Reward = new List<PlayerCard> { GenerateCard(75, 84) },
        });
        SBCs.Add(new SBC
        {
            Name = "Gold Rare",
            Description = "Submit 7 Gold players (75+ OVR)",
            MinRating = 75,
            MinPlayers = 7,
            Reward = new List<PlayerCard> { GenerateCard(85, 89) },
        });
        SBCs.Add(new SBC
        {
            Name = "Icon Challenge",
            Description = "Submit 11 players (80+ OVR, 50 chemistry)",
            MinRating = 80,
            MinChemistry = 50,
            MinPlayers = 11,
            Reward = new List<PlayerCard> { GenerateCard(90, 95) },
        });
    }

    /// <summary>Submit players to an SBC.</summary>
    public bool SubmitSBC(SBC sbc, List<PlayerCard> players)
    {
        if (players.Count < sbc.MinPlayers) return false;
        if (players.Average(p => p.Overall) < sbc.MinRating) return false;
        // Remove players from club
        foreach (var p in players)
        {
            Club.Remove(p);
        }
        // Add rewards
        foreach (var reward in sbc.Reward)
        {
            Club.Add(reward);
        }
        sbc.Completed = true;
        return true;
    }

    /// <summary>Buy a card from the transfer market.</summary>
    public bool BuyCard(PlayerCard card)
    {
        if (Coins < card.Price) return false;
        Coins -= card.Price;
        Club.Add(card);
        return true;
    }

    /// <summary>Sell a card.</summary>
    public bool SellCard(PlayerCard card)
    {
        if (!Club.Contains(card)) return false;
        Coins += (int)(card.Price * 0.8);
        Club.Remove(card);
        return true;
    }
}
