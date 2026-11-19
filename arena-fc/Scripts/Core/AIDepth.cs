// Arena FC — AI Depth system (Phase 7).
// Player personalities, team mentality shifts, substitutions,
// injuries, morale, set piece routines.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Player personality types.</summary>
public enum Personality
{
    Aggressive,   // tackles more, fouls more, high press
    Playmaker,    // better passing, creates chances
    TargetMan,    // holds up ball, physical, headers
    Engine,       // high stamina, covers ground
    Trickster,    // skill moves, dribbles
    Wall,         // defensive, blocks shots
    Balanced,
}

/// <summary>Team mentality for mid-game shifts.</summary>
public enum TeamMentality
{
    VeryDefensive,
    Defensive,
    Balanced,
    Attacking,
    VeryAttacking,
}

/// <summary>Set piece routine types.</summary>
public enum SetPieceRoutine
{
    NearPost,     // attack near post
    FarPost,      // attack far post
    EdgeOfBox,    // second ball
    ShortCorner,  // short corner
    Direct,       // direct shot
}

/// <summary>Player personality data.</summary>
public class PersonalityData
{
    public Personality Type;
    public float Aggression;      // 0-1, tackle/foul frequency
    public float Creativity;      // 0-1, passing/vision
    public float Physicality;     // 0-1, strength, headers
    public float Stamina;         // 0-1, work rate
    public float Skill;           // 0-1, dribbling
    public float DefensiveFocus;  // 0-1, positioning

    public static PersonalityData For(Personality type)
    {
        return type switch
        {
            Personality.Aggressive => new() { Type = type, Aggression = 0.9f, Creativity = 0.5f, Physicality = 0.7f, Stamina = 0.7f, Skill = 0.5f, DefensiveFocus = 0.4f },
            Personality.Playmaker => new() { Type = type, Aggression = 0.4f, Creativity = 0.95f, Physicality = 0.4f, Stamina = 0.6f, Skill = 0.7f, DefensiveFocus = 0.5f },
            Personality.TargetMan => new() { Type = type, Aggression = 0.6f, Creativity = 0.5f, Physicality = 0.95f, Stamina = 0.5f, Skill = 0.4f, DefensiveFocus = 0.3f },
            Personality.Engine => new() { Type = type, Aggression = 0.7f, Creativity = 0.6f, Physicality = 0.6f, Stamina = 0.95f, Skill = 0.5f, DefensiveFocus = 0.6f },
            Personality.Trickster => new() { Type = type, Aggression = 0.5f, Creativity = 0.7f, Physicality = 0.4f, Stamina = 0.6f, Skill = 0.95f, DefensiveFocus = 0.3f },
            Personality.Wall => new() { Type = type, Aggression = 0.5f, Creativity = 0.3f, Physicality = 0.8f, Stamina = 0.6f, Skill = 0.3f, DefensiveFocus = 0.95f },
            _ => new() { Type = type, Aggression = 0.5f, Creativity = 0.5f, Physicality = 0.5f, Stamina = 0.5f, Skill = 0.5f, DefensiveFocus = 0.5f },
        };
    }
}

/// <summary>Substitution record.</summary>
public class Substitution
{
    public int PlayerOff;
    public int PlayerOn;
    public int Minute;
    public string Reason = ""; // "Tired", "Injury", "Tactical"
}

/// <summary>Injury record.</summary>
public class Injury
{
    public int PlayerIndex;
    public int Minute;
    public int Severity; // 1=minor (play on), 2=major (sub off), 3=serious (out for match)
    public bool NeedsSub;
}

/// <summary>AI Depth manager.</summary>
public class AIDepth
{
    private readonly Random _rng = new(456);
    private readonly List<Substitution> _subs = new();
    private readonly List<Injury> _injuries = new();
    private readonly Dictionary<int, PersonalityData> _personalities = new();
    private readonly Dictionary<int, float> _morale = new();
    private readonly Dictionary<int, int> _formStreak = new(); // W/D/L streak

    public IReadOnlyList<Substitution> Substitutions => _subs;
    public IReadOnlyList<Injury> Injuries => _injuries;
    public TeamMentality HomeMentality = TeamMentality.Balanced;
    public TeamMentality AwayMentality = TeamMentality.Balanced;
    public SetPieceRoutine CornerRoutine = SetPieceRoutine.NearPost;
    public SetPieceRoutine FreeKickRoutine = SetPieceRoutine.Direct;

    /// <summary>Assign personality to a player.</summary>
    public void AssignPersonality(int playerIndex, Personality type)
    {
        _personalities[playerIndex] = PersonalityData.For(type);
        _morale[playerIndex] = 75f;
        _formStreak[playerIndex] = 0;
    }

    /// <summary>Get personality data for a player.</summary>
    public PersonalityData GetPersonality(int playerIndex)
    {
        return _personalities.TryGetValue(playerIndex, out var data) ? data : PersonalityData.For(Personality.Balanced);
    }

    /// <summary>Get morale (0-100) for a player.</summary>
    public float GetMorale(int playerIndex)
    {
        return _morale.TryGetValue(playerIndex, out var m) ? m : 75f;
    }

    /// <summary>Update morale based on match events.</summary>
    public void UpdateMorale(int playerIndex, bool won, bool scored, bool conceded)
    {
        float morale = GetMorale(playerIndex);
        if (won) morale += 5;
        else if (conceded) morale -= 3;
        if (scored) morale += 8;
        _morale[playerIndex] = Math.Clamp(morale, 0, 100);

        // Form streak
        int streak = _formStreak.TryGetValue(playerIndex, out var s) ? s : 0;
        if (won) streak = streak > 0 ? streak + 1 : 1;
        else if (conceded) streak = streak < 0 ? streak - 1 : -1;
        _formStreak[playerIndex] = streak;
    }

    /// <summary>Get morale modifier for performance (-0.1 to +0.1).</summary>
    public float GetMoraleModifier(int playerIndex)
    {
        float morale = GetMorale(playerIndex);
        int streak = _formStreak.TryGetValue(playerIndex, out var s) ? s : 0;
        float modifier = (morale - 75f) / 250f; // -0.3 to +0.1
        if (streak >= 3) modifier += 0.05f; // hot streak
        if (streak <= -3) modifier -= 0.05f; // cold streak
        return Math.Clamp(modifier, -0.15f, 0.15f);
    }

    /// <summary>Check if AI should substitute (tired players after 60').</summary>
    public bool ShouldSubstitute(int playerIndex, float stamina, int minute)
    {
        if (minute < 60) return false;
        if (stamina < 0.3f) return true; // very tired
        if (minute > 75 && stamina < 0.5f) return true; // tired late
        return false;
    }

    /// <summary>Record a substitution.</summary>
    public void RecordSubstitution(int off, int on, int minute, string reason)
    {
        _subs.Add(new Substitution
        {
            PlayerOff = off,
            PlayerOn = on,
            Minute = minute,
            Reason = reason,
        });
    }

    /// <summary>Check for injury (random, more likely for aggressive players).</summary>
    public Injury? CheckInjury(int playerIndex, int minute, bool wasTackled)
    {
        if (!wasTackled) return null;
        var personality = GetPersonality(playerIndex);
        float injuryChance = 0.02f + personality.Aggression * 0.03f;
        if (_rng.NextDouble() > injuryChance) return null;

        int severity = _rng.Next(1, 4); // 1-3
        var injury = new Injury
        {
            PlayerIndex = playerIndex,
            Minute = minute,
            Severity = severity,
            NeedsSub = severity >= 2,
        };
        _injuries.Add(injury);
        return injury;
    }

    /// <summary>Auto-shift team mentality based on score and time.</summary>
    public TeamMentality GetAutoMentality(int scoreFor, int scoreAgainst, int minute)
    {
        int diff = scoreFor - scoreAgainst;
        if (minute > 75)
        {
            if (diff < 0) return TeamMentality.VeryAttacking; // chasing game
            if (diff > 0) return TeamMentality.VeryDefensive; // protecting lead
        }
        if (minute > 60)
        {
            if (diff < 0) return TeamMentality.Attacking;
            if (diff > 1) return TeamMentality.Defensive;
        }
        if (diff == 0) return TeamMentality.Balanced;
        if (diff > 0) return TeamMentality.Defensive;
        return TeamMentality.Attacking;
    }

    /// <summary>Get set piece routine for corners.</summary>
    public SetPieceRoutine GetCornerRoutine()
    {
        // Randomize or based on team style
        return (SetPieceRoutine)_rng.Next(0, 4); // NearPost, FarPost, EdgeOfBox, ShortCorner
    }

    /// <summary>Get set piece routine for free kicks.</summary>
    public SetPieceRoutine GetFreeKickRoutine(float distanceToGoal)
    {
        if (distanceToGoal < 25f) return SetPieceRoutine.Direct; // shoot
        return (SetPieceRoutine)_rng.Next(0, 3); // NearPost, FarPost, EdgeOfBox
    }

    /// <summary>Clear all data (new match).</summary>
    public void Clear()
    {
        _subs.Clear();
        _injuries.Clear();
        _personalities.Clear();
        _morale.Clear();
        _formStreak.Clear();
    }
}
