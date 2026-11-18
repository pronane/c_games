// Arena FC — Career and Ultimate Team progression modes.
// Player progression, team management, and seasonal rewards.
using System;
using System.Collections.Generic;

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
    public List<PlayerProgress> Squad = new();

    public int GoalDifference => GoalsFor - GoalsAgainst;
    public int TotalPlayed => Wins + Draws + Losses;
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
        Overall = (Pace + Shooting + Passing + Defending + Goalkeeping) / 5;
    }

    public void PlayMatch(bool won, int goals, int assists)
    {
        Appearances++;
        Goals += goals;
        Assists += assists;
        Morale = Math.Clamp(Morale + (won ? 5 : -3), 0, 100);
        Fitness = Math.Max(0, Fitness - 15);
    }

    public void Rest()
    {
        Fitness = Math.Min(100, Fitness + 30);
    }
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

/// <summary>Career mode manager.</summary>
public class CareerMode
{
    public CareerState State = new();
    public UltimateTeamState UltimateTeam = new();

    public void AdvanceWeek()
    {
        State.Week++;
        if (State.Week > 38)
        {
            State.Season++;
            State.Week = 1;
            // Age players, reset fitness
            foreach (var p in State.Squad)
            {
                p.Age++;
                p.Fitness = 100;
                if (p.Age > 35) p.Potential = Math.Max(p.Overall, p.Potential - 2);
            }
        }
        foreach (var p in State.Squad) p.Rest();
    }

    public void RecordResult(bool won, bool draw, int gf, int ga)
    {
        if (won) { State.Wins++; State.Points += 3; }
        else if (draw) { State.Draws++; State.Points += 1; }
        else State.Losses++;
        State.GoalsFor += gf;
        State.GoalsAgainst += ga;
    }
}
