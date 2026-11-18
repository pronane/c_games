// Arena FC — Fluid Formations and Team Playstyles (eFootball v6.0 parity).
// Separate attacking/defensive shapes + Overload playstyle.
using System;
using System.Collections.Generic;

namespace ArenaFC.Core;

/// <summary>Team playstyle (eFootball v6.0).</summary>
public enum TeamPlaystyle
{
    Balanced,     // standard shape
    Overload,     // concentrate ball-side for numerical superiority
    Counter,      // sit deep, hit on break
    Possession,   // keep ball, short passes
    Direct,       // long balls, physical
    Gegenpress,   // high press, quick regain
}

/// <summary>
/// Fluid Formation: separate attacking and defensive shapes.
/// Players shift positions based on possession state.
/// </summary>
public class FluidFormation
{
    public string AttackShape = "4-3-3";
    public string DefenceShape = "4-5-1";
    public TeamPlaystyle Playstyle = TeamPlaystyle.Balanced;

    // Formation slot offsets (x, z) for each position index
    private readonly Dictionary<string, List<(float x, float z)>> _shapes = new();

    public FluidFormation()
    {
        // Attacking shape: push fullbacks forward, striker central
        _shapes["attack"] = new List<(float, float)>
        {
            (0, 0),      // GK
            (-20, -15),  // LB (pushed up)
            (-18, -5),   // LCB
            (-18, 5),    // RCB
            (-20, 15),   // RB (pushed up)
            (-5, -8),    // LCM
            (-5, 8),     // RCM
            (0, 0),      // CAM
            (15, -10),   // LW
            (20, 0),     // ST
            (15, 10),    // RW
        };

        // Defensive shape: compact, protect centre
        _shapes["defence"] = new List<(float, float)>
        {
            (0, 0),      // GK
            (-15, -12),  // LB
            (-12, -4),   // LCB
            (-12, 4),    // RCB
            (-15, 12),   // RB
            (-2, -10),   // LCM (dropped)
            (-2, 0),     // CDM
            (-2, 10),    // RCM (dropped)
            (5, -8),     // LM
            (8, 0),      // ST (lone striker)
            (5, 8),      // RM
        };
    }

    /// <summary>Get slot position for a player based on possession.</summary>
    public (float x, float z) GetSlot(int playerIndex, bool hasPossession)
    {
        var shape = hasPossession ? _shapes["attack"] : _shapes["defence"];
        if (playerIndex < shape.Count)
            return shape[playerIndex];
        return (0, 0);
    }

    /// <summary>Apply playstyle modifiers to AI decisions.</summary>
    public (float pressIntensity, float passLength, float runAggression) GetPlaystyleModifiers()
    {
        return Playstyle switch
        {
            TeamPlaystyle.Overload => (0.7f, 0.9f, 1.2f),    // less press, shorter passes, more runs
            TeamPlaystyle.Counter => (0.4f, 1.3f, 1.4f),     // low press, long passes, aggressive runs
            TeamPlaystyle.Possession => (0.5f, 0.8f, 0.8f),  // medium press, short passes, calm runs
            TeamPlaystyle.Direct => (0.6f, 1.4f, 1.1f),      // medium press, long passes, physical runs
            TeamPlaystyle.Gegenpress => (1.2f, 0.9f, 1.3f),  // high press, short passes, aggressive runs
            _ => (0.8f, 1.0f, 1.0f),                          // balanced
        };
    }
}

/// <summary>Link-Up Play: coordinated two-player move.</summary>
public class LinkUpPlay
{
    public string Name = "";
    public int PasserIndex;
    public int RunnerIndex;
    public string Type = "overlap"; // overlap, underlap, third_man, decoy
    public float TriggerDistance = 15f;
}

/// <summary>Manages Link-Up Plays for a team.</summary>
public class LinkUpPlays
{
    private readonly List<LinkUpPlay> _plays = new();

    public void AddPlay(LinkUpPlay play) => _plays.Add(play);

    /// <summary>Check if a Link-Up Play should trigger.</summary>
    public LinkUpPlay? CheckTrigger(int ballCarrierIndex, float ballX, float ballZ,
                                     List<(float x, float z)> playerPositions)
    {
        foreach (var play in _plays)
        {
            if (play.PasserIndex != ballCarrierIndex) continue;
            if (play.RunnerIndex >= playerPositions.Count) continue;

            var runnerPos = playerPositions[play.RunnerIndex];
            float dist = MathF.Sqrt(
                (runnerPos.x - ballX) * (runnerPos.x - ballX) +
                (runnerPos.z - ballZ) * (runnerPos.z - ballZ));

            if (dist < play.TriggerDistance)
                return play;
        }
        return null;
    }

    public int Count => _plays.Count;
}
