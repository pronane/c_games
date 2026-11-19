// Arena FC — Pro Clubs & Online system (Phase 10).
// 11v11 fixed positions, co-op modes, ranked seasons,
// anti-cheat, skill games, practice arena.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Pro Clubs position.</summary>
public enum ProClubPosition
{
    GK, LB, CB, RB, CDM, CM, CAM, LM, RM, LW, RW, ST,
}

/// <summary>Co-op mode.</summary>
public enum CoopMode
{
    Solo,       // 1v1 vs AI
    Duo,        // 2v2
    Trio,       // 3v3
    Squad,      // 5v5
    ProClubs,   // 11v11 fixed positions
}

/// <summary>Skill game type.</summary>
public enum SkillGame
{
    Passing,    // hit targets
    Shooting,   // score goals
    Dribbling,  // weave through cones
    Crossing,   // cross to target
    FreeKicks,  // score from free kicks
}

/// <summary>Pro Clubs player.</summary>
public class ProClubPlayer
{
    public string Name = "";
    public ProClubPosition Position;
    public int Overall;
    public int Goals, Assists, CleanSheets;
    public int MatchesPlayed;
    public bool IsHuman;
}

/// <summary>Ranked season.</summary>
public class RankedSeason
{
    public int SeasonNumber = 1;
    public int Division = 10;
    public int Points;
    public int Wins, Draws, Losses;
    public List<string> Rewards = new();

    public void RecordResult(bool won, bool draw)
    {
        if (won) { Wins++; Points += 3; }
        else if (draw) { Draws++; Points += 1; }
        else Losses++;
    }

    public void EndSeason()
    {
        // Rewards based on division
        if (Division <= 3) Rewards.Add("Gold Pack");
        if (Division <= 5) Rewards.Add("Silver Pack");
        if (Division <= 7) Rewards.Add("Bronze Pack");
        if (Division == 1) Rewards.Add("Icon Card");
        SeasonNumber++;
        Points = 0;
        Wins = Draws = Losses = 0;
    }
}

/// <summary>Anti-cheat validator.</summary>
public class AntiCheat
{
    private readonly Dictionary<int, float> _lastInputTime = new();
    private readonly Dictionary<int, int> _inputCount = new();
    private const float MaxInputsPerSecond = 30f;
    private const float MaxSpeed = 10f; // m/s

    /// <summary>Validate player input (speed, frequency).</summary>
    public bool ValidateInput(int playerIndex, float speed, float timestamp)
    {
        // Speed check
        if (speed > MaxSpeed) return false;

        // Frequency check
        if (_lastInputTime.TryGetValue(playerIndex, out var lastTime))
        {
            float dt = timestamp - lastTime;
            if (dt > 0)
            {
                float rate = 1f / dt;
                if (rate > MaxInputsPerSecond) return false;
            }
        }
        _lastInputTime[playerIndex] = timestamp;
        return true;
    }

    /// <summary>Validate position (no teleporting).</summary>
    public bool ValidatePosition(Vector3 lastPos, Vector3 newPos, float dt)
    {
        float distance = Vector3.Distance(lastPos, newPos);
        float maxDistance = MaxSpeed * dt;
        return distance <= maxDistance;
    }

    /// <summary>Clear player data.</summary>
    public void ClearPlayer(int playerIndex)
    {
        _lastInputTime.Remove(playerIndex);
        _inputCount.Remove(playerIndex);
    }
}

/// <summary>Skill game result.</summary>
public class SkillGameResult
{
    public SkillGame Game;
    public int Score;
    public int BestScore;
    public bool IsNewBest;
}

/// <summary>Pro Clubs manager.</summary>
public class ProClubs
{
    private readonly Random _rng = new(111);
    public CoopMode Mode = CoopMode.ProClubs;
    public List<ProClubPlayer> Team = new();
    public RankedSeason Season = new();
    public AntiCheat AntiCheat = new();
    public Dictionary<SkillGame, SkillGameResult> SkillResults = new();

    /// <summary>Generate Pro Clubs team (11 fixed positions).</summary>
    public void GenerateTeam()
    {
        Team.Clear();
        var positions = new[]
        {
            ProClubPosition.GK, ProClubPosition.LB, ProClubPosition.CB, ProClubPosition.CB, ProClubPosition.RB,
            ProClubPosition.CDM, ProClubPosition.CM, ProClubPosition.CAM,
            ProClubPosition.LW, ProClubPosition.RW, ProClubPosition.ST,
        };
        string[] names = { "You", "Alex", "Marco", "Nico", "Jamie", "Rafael", "Yuki", "Omar", "Luca", "Elias", "Tomas" };
        for (int i = 0; i < 11; i++)
        {
            Team.Add(new ProClubPlayer
            {
                Name = names[i],
                Position = positions[i],
                Overall = _rng.Next(70, 90),
                IsHuman = i == 0, // first player is human
            });
        }
    }

    /// <summary>Set co-op mode (team size).</summary>
    public void SetCoopMode(CoopMode mode)
    {
        Mode = mode;
        int teamSize = mode switch
        {
            CoopMode.Solo => 1,
            CoopMode.Duo => 2,
            CoopMode.Trio => 3,
            CoopMode.Squad => 5,
            CoopMode.ProClubs => 11,
            _ => 11,
        };
        // Adjust team (simplified: keep 11 for Pro Clubs, trim for others)
        if (teamSize < 11)
        {
            Team = Team.Take(teamSize).ToList();
        }
        else if (Team.Count < 11)
        {
            GenerateTeam();
        }
    }

    /// <summary>Record a skill game result.</summary>
    public void RecordSkillGame(SkillGame game, int score)
    {
        if (!SkillResults.TryGetValue(game, out var result))
        {
            result = new SkillGameResult { Game = game, BestScore = 0 };
            SkillResults[game] = result;
        }
        result.Score = score;
        if (score > result.BestScore)
        {
            result.BestScore = score;
            result.IsNewBest = true;
        }
        else
        {
            result.IsNewBest = false;
        }
    }

    /// <summary>Get best score for a skill game.</summary>
    public int GetBestScore(SkillGame game)
    {
        return SkillResults.TryGetValue(game, out var result) ? result.BestScore : 0;
    }
}
