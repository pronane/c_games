// Arena FC — 10 Features from other sports games.
// Shot meter, badges, heat maps, xG, photo mode, achievements,
// club system, replay editor, custom training, evolutions.
using System;
using System.Collections.Generic;
using System.Linq;

namespace ArenaFC.Core;

/// <summary>Feature 1: Shot meter (visual timing).</summary>
public class ShotMeter
{
    public float Charge; // 0-1
    public float PerfectStart = 0.7f;
    public float PerfectEnd = 0.85f;
    public bool IsPerfect => Charge >= PerfectStart && Charge <= PerfectEnd;
    public string GetFeedback() => IsPerfect ? "PERFECT!" : Charge < PerfectStart ? "EARLY" : "LATE";
}

/// <summary>Feature 2: Player badges (unlockable traits).</summary>
public enum Badge
{
    Deadeye,    // +10% shot accuracy
    Handles,    // +10% dribbling
    Playmaker,  // +10% passing
    Wall,       // +10% defending
    Engine,     // +20% stamina
    Trickster,  // +10% skill moves
    TargetMan,  // +10% physical
}

/// <summary>Feature 3: Heat map data.</summary>
public class HeatMap
{
    public List<(float x, float z, int count)> Zones = new();
    public void AddPosition(float x, float z)
    {
        var zone = Zones.FirstOrDefault(zn => Math.Abs(zn.x - x) < 5 && Math.Abs(zn.z - z) < 5);
        if (zone.count == 0) Zones.Add((x, z, 1));
        else Zones[Zones.IndexOf(zone)] = (zone.x, zone.z, zone.count + 1);
    }
}

/// <summary>Feature 4: Expected Goals (xG).</summary>
public class ExpectedGoals
{
    public float CalculateXG(float distance, float angle, bool isOneOnOne)
    {
        float xg = 0.1f;
        xg -= distance * 0.005f;
        xg -= angle * 0.02f;
        if (isOneOnOne) xg += 0.3f;
        return Math.Clamp(xg, 0.01f, 0.95f);
    }
}

/// <summary>Feature 5: Photo mode.</summary>
public class PhotoMode
{
    public bool IsActive;
    public int CameraIndex;
    public void Activate() => IsActive = true;
    public void Deactivate() => IsActive = false;
    public void CycleCamera() => CameraIndex = (CameraIndex + 1) % 7;
}

/// <summary>Feature 6: Achievements.</summary>
public class Achievement
{
    public string Name = "";
    public string Description = "";
    public bool Unlocked;
    public int Progress;
    public int Target;
}

/// <summary>Feature 7: Club system.</summary>
public class Club
{
    public string Name = "";
    public string Badge = "";
    public int Reputation;
    public List<string> Members = new();
    public int Wins, Losses;
}

/// <summary>Feature 8: Replay editor.</summary>
public class ReplayEditor
{
    public int StartFrame;
    public int EndFrame;
    public string TextOverlay = "";
    public bool SlowMotion;
    public void Trim(int start, int end) { StartFrame = start; EndFrame = end; }
}

/// <summary>Feature 9: Custom training.</summary>
public class CustomTraining
{
    public string Name = "";
    public SkillGame Type;
    public int TargetScore;
    public List<string> Steps = new();
}

/// <summary>Feature 10: Evolutions (upgrade cards).</summary>
public class Evolution
{
    public string Name = "";
    public int MinOverall;
    public int MaxOverall;
    public int Boost;
    public PlayerCard Apply(PlayerCard card)
    {
        if (card.Overall < MinOverall || card.Overall > MaxOverall) return card;
        var evolved = new PlayerCard
        {
            Name = card.Name,
            Overall = Math.Min(99, card.Overall + Boost),
            Position = card.Position,
            Club = card.Club,
            League = card.League,
            Nation = card.Nation,
            Pace = Math.Min(99, card.Pace + Boost),
            Shooting = Math.Min(99, card.Shooting + Boost),
            Passing = Math.Min(99, card.Passing + Boost),
            Defending = Math.Min(99, card.Defending + Boost),
            Physical = Math.Min(99, card.Physical + Boost),
        };
        return evolved;
    }
}
