// Arena FC - persistence.
//
// Before this existed the game kept nothing: match settings, camera, tactics,
// Ultimate Team coins, tournament progress and online ranking all died with the
// process (only character JSON and per-pad bindings were written to disk).
//
// The save is a single JSON document owned by the Godot-free core so it can be
// tested headlessly and reused by the server/web builds.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ArenaFC.Core;

/// <summary>Everything the player can change in the options screens.</summary>
public sealed class SettingsDto
{
    public int TeamSize = 11;
    public float HalfMinutes = 45f;
    public float TimeSpeed = 15f;
    public int Difficulty = 1;
    public int HomeClub;
    public int AwayClub = 1;
    public string HomeFormation = "4-4-2";
    public string AwayFormation = "4-3-3";
    public bool Offside = true;
    public bool Fouls = true;
    public bool TimedFinishing = true;
    public bool WeakFoot = true;
    public int SwitchMode;
    public int CameraMode;
    public int Quality = (int)QualityPreset.Auto;
    public int BenchSize = 7;
    // In-match tactics defaults (A5).
    public int Mentality = (int)ArenaFC.Core.Mentality.Balanced;
    public float PressingIntensity = .5f;
    public float Width = .5f;
    public float Tempo = .5f;

    public void CopyFrom(MatchOptions o, Tactics t)
    {
        TeamSize = o.TeamSize; HalfMinutes = o.HalfMinutes; TimeSpeed = o.TimeSpeed;
        Difficulty = o.Difficulty; HomeClub = o.HomeClub; AwayClub = o.AwayClub;
        HomeFormation = o.HomeFormation; AwayFormation = o.AwayFormation;
        Offside = o.Offside; Fouls = o.Fouls; TimedFinishing = o.TimedFinishing; WeakFoot = o.WeakFoot;
        SwitchMode = o.SwitchMode; CameraMode = o.CameraMode; Quality = (int)o.Quality;
        Mentality = (int)t.Mentality; PressingIntensity = t.PressingIntensity;
        Width = t.Width; Tempo = t.Tempo;
    }

    public void ApplyTo(MatchOptions o, Tactics t)
    {
        o.TeamSize = TeamSize is 5 or 7 or 11 ? TeamSize : 11;
        o.HalfMinutes = Math.Clamp(HalfMinutes, 1f, 120f);
        o.TimeSpeed = Math.Clamp(TimeSpeed, 1f, 90f);
        o.Difficulty = Math.Clamp(Difficulty, 0, 3);
        o.HomeClub = Math.Clamp(HomeClub, 0, Clubs.All.Length - 1);
        o.AwayClub = Math.Clamp(AwayClub, 0, Clubs.All.Length - 1);
        if (o.HomeClub == o.AwayClub) o.AwayClub = (o.HomeClub + 1) % Clubs.All.Length;
        o.HomeFormation = HomeFormation; o.AwayFormation = AwayFormation;
        o.Offside = Offside; o.Fouls = Fouls; o.TimedFinishing = TimedFinishing; o.WeakFoot = WeakFoot;
        o.SwitchMode = Math.Clamp(SwitchMode, 0, 2);
        o.CameraMode = Math.Max(0, CameraMode);
        o.Quality = (QualityPreset)Math.Clamp(Quality, 0, 3);
        t.Mentality = (Mentality)Math.Clamp(Mentality, 0, 4);
        t.PressingIntensity = Math.Clamp(PressingIntensity, 0f, 1f);
        t.Width = Math.Clamp(Width, 0f, 1f);
        t.Tempo = Math.Clamp(Tempo, 0f, 1f);
    }
}

/// <summary>Career progress, including the league state CareerMode owns.</summary>
public sealed class CareerDto
{
    public CareerState State = new();
    public UltimateTeamState UltimateTeam = new();
    public bool Started;
}

/// <summary>The whole save file.</summary>
public sealed class SaveGame
{
    public const int CurrentVersion = 1;

    public int Version = CurrentVersion;
    public string SavedAtUtc = "";
    public SettingsDto Settings = new();
    public TournamentSystem? Tournament;
    public CareerDto? Career;
    public UltimateTeam? Ultimate;
    public RankedLadder Ranked = new();
    /// <summary>Last five results, newest first: "HAR 3-1 NOR (H)".</summary>
    public List<string> RecentResults = new();
    /// <summary>Unlocked achievement names (prefixed "unlocked:") plus seeds.</summary>
    public List<string> Achievements = new();
    /// <summary>Saved replay clips: description plus the trimmed frame range.</summary>
    public List<string> ReplayClips = new();
    /// <summary>Best score per skill game (key: SkillGame name).</summary>
    public Dictionary<string, int> SkillBest = new();

    /// <summary>Record a skill-game score; true when it is a new best.</summary>
    public bool RecordSkill(SkillGame game, int score)
    {
        string k = game.ToString();
        bool best = !SkillBest.TryGetValue(k, out int old) || score > old;
        if (best) SkillBest[k] = score;
        return best;
    }

    public int BestSkill(SkillGame game) => SkillBest.TryGetValue(game.ToString(), out int v) ? v : 0;

    public static readonly JsonSerializerOptions Json = new()
    {
        IncludeFields = true,
        WriteIndented = false,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        PropertyNameCaseInsensitive = true,
        NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
    };

    public string ToJson()
    {
        SavedAtUtc = DateTime.UtcNow.ToString("O");
        return JsonSerializer.Serialize(this, Json);
    }

    /// <summary>Parse a save; a corrupt or foreign file yields a fresh game
    /// rather than an exception the UI would have to catch.</summary>
    public static SaveGame FromJson(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return new SaveGame();
        try
        {
            var game = JsonSerializer.Deserialize<SaveGame>(json, Json) ?? new SaveGame();
            game.Normalize();
            return game;
        }
        catch (JsonException) { return new SaveGame(); }
        catch (NotSupportedException) { return new SaveGame(); }
    }

    /// <summary>Repair anything a hand-edited, older or truncated save could get
    /// wrong, then rehydrate the objects whose private state is not serialised.</summary>
    public void Normalize()
    {
        Settings ??= new SettingsDto();
        Ranked ??= new RankedLadder();
        RecentResults ??= new List<string>();
        Achievements ??= new List<string>();
        ReplayClips ??= new List<string>();
        if (Version > CurrentVersion) Version = CurrentVersion;

        Ranked.Mmr = Math.Clamp(Ranked.Mmr, 200, 2600);
        Ranked.Season = Math.Max(1, Ranked.Season);
        Ranked.PlacementMatchesLeft = Math.Clamp(Ranked.PlacementMatchesLeft, 0, 5);
        Ranked.Wins = Math.Max(0, Ranked.Wins);
        Ranked.Draws = Math.Max(0, Ranked.Draws);
        Ranked.Losses = Math.Max(0, Ranked.Losses);

        Tournament?.Rehydrate();
        if (Tournament != null && Tournament.Fixtures == null)
            Tournament = null;

        if (RecentResults.Count > 8) RecentResults.RemoveRange(8, RecentResults.Count - 8);
        if (ReplayClips.Count > 20) ReplayClips.RemoveRange(20, ReplayClips.Count - 20);
    }

    public void PushResult(string line)
    {
        RecentResults.Insert(0, line);
        if (RecentResults.Count > 8) RecentResults.RemoveRange(8, RecentResults.Count - 8);
    }
}
