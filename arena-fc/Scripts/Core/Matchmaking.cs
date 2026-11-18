// Arena FC — online matchmaking with lobbies and ranking.
// Public lobbies, skill-based matchmaking, and seasonal rankings.
using System;
using System.Collections.Generic;

namespace ArenaFC.Core;

/// <summary>Player ranking.</summary>
public class PlayerRanking
{
    public string PlayerId = "";
    public string DisplayName = "";
    public int Rating = 1000; // ELO-style
    public int Wins, Losses, Draws;
    public int Streak;
    public int BestStreak;
    public string Tier = "Bronze"; // Bronze, Silver, Gold, Platinum, Diamond

    public void RecordResult(bool won, bool draw, int opponentRating)
    {
        double expected = 1.0 / (1.0 + Math.Pow(10.0, (opponentRating - Rating) / 400.0));
        int actual = won ? 1 : draw ? 0 : 0;
        if (draw) actual = 0; // simplified
        int k = 32;
        Rating += (int)(k * (actual - expected));

        if (won) { Wins++; Streak++; BestStreak = Math.Max(BestStreak, Streak); }
        else if (draw) { Draws++; Streak = 0; }
        else { Losses++; Streak = 0; }

        Tier = Rating switch
        {
            >= 2000 => "Diamond",
            >= 1700 => "Platinum",
            >= 1400 => "Gold",
            >= 1100 => "Silver",
            _ => "Bronze",
        };
    }
}

/// <summary>Public lobby for matchmaking.</summary>
public class Lobby
{
    public string Id = "";
    public string HostName = "";
    public int MaxPlayers = 2;
    public int CurrentPlayers = 1;
    public string Mode = "Kickoff"; // Kickoff, Tournament, Training
    public string Map = "Arena Stadium";
    public bool IsPrivate;
    public string Password = "";
    public int MinRating = 0;
    public int MaxRating = 9999;
    public DateTime CreatedAt = DateTime.UtcNow;

    public bool IsFull => CurrentPlayers >= MaxPlayers;
    public bool CanJoin(PlayerRanking player)
    {
        if (IsFull) return false;
        if (player.Rating < MinRating || player.Rating > MaxRating) return false;
        return true;
    }
}

/// <summary>Matchmaking service.</summary>
public class MatchmakingService
{
    private readonly List<Lobby> _lobbies = new();
    private readonly Dictionary<string, PlayerRanking> _rankings = new();

    public void CreateLobby(Lobby lobby) => _lobbies.Add(lobby);
    public void RemoveLobby(string id) => _lobbies.RemoveAll(l => l.Id == id);

    public List<Lobby> FindLobbies(PlayerRanking player)
    {
        var results = new List<Lobby>();
        foreach (var lobby in _lobbies)
        {
            if (!lobby.IsPrivate && lobby.CanJoin(player))
                results.Add(lobby);
        }
        return results;
    }

    public Lobby FindBestMatch(PlayerRanking player)
    {
        // Find lobby with closest rating range
        Lobby best = null;
        int bestDiff = int.MaxValue;
        foreach (var lobby in _lobbies)
        {
            if (lobby.IsPrivate || lobby.IsFull) continue;
            int diff = Math.Abs(lobby.MinRating - player.Rating);
            if (diff < bestDiff)
            {
                bestDiff = diff;
                best = lobby;
            }
        }
        return best;
    }

    public PlayerRanking GetRanking(string playerId)
    {
        if (!_rankings.TryGetValue(playerId, out var ranking))
        {
            ranking = new PlayerRanking { PlayerId = playerId };
            _rankings[playerId] = ranking;
        }
        return ranking;
    }

    public int LobbyCount => _lobbies.Count;
}
