// Arena FC — advantage, VAR, and injury system (G9).
// Referee decisions beyond simple foul chance.
using System;

namespace ArenaFC.Core;

/// <summary>Referee decision types.</summary>
public enum RefereeDecision
{
    PlayOn,           // advantage — play continues
    FreeKick,         // foul, stop play
    Penalty,          // foul in box
    YellowCard,       // caution
    RedCard,          // sending off
    VarReview,        // VAR check
    GoalAwarded,      // VAR confirms goal
    GoalDisallowed,   // VAR disallows goal
    Injury,           // player injured, needs treatment
}

/// <summary>
/// Referee system with advantage, VAR reviews, and injuries.
/// Decisions based on foul severity, game state, and randomness.
/// </summary>
public class RefereeSystem
{
    private readonly Random _rng = new(12345);
    private int _foulCount;
    private int _yellowCount;
    private bool _varAvailable = true;

    /// <summary>Decide on a foul.</summary>
    public RefereeDecision DecideFoul(bool inBox, bool lastMan, bool dangerous,
                                       bool attackingTeamHasBall, float severity)
    {
        _foulCount++;

        // Advantage: if attacking team has clear chance, play on
        if (attackingTeamHasBall && severity < 0.5f && _rng.NextDouble() < 0.6)
            return RefereeDecision.PlayOn;

        // Penalty for foul in box
        if (inBox && severity > 0.3f)
            return RefereeDecision.Penalty;

        // Red card for dangerous / last man
        if ((dangerous || lastMan) && severity > 0.7f)
            return RefereeDecision.RedCard;

        // Yellow card for repeated fouls
        if (_foulCount > 5 && _rng.NextDouble() < 0.3)
        {
            _yellowCount++;
            return RefereeDecision.YellowCard;
        }

        // Injury for dangerous fouls
        if (dangerous && severity > 0.6f && _rng.NextDouble() < 0.2)
            return RefereeDecision.Injury;

        return RefereeDecision.FreeKick;
    }

    /// <summary>VAR review for a goal.</summary>
    public RefereeDecision VarCheckGoal(bool offside, bool handball, bool foulInBuildup)
    {
        if (!_varAvailable) return RefereeDecision.GoalAwarded;

        if (offside || handball || foulInBuildup)
            return RefereeDecision.GoalDisallowed;

        return RefereeDecision.GoalAwarded;
    }

    /// <summary>Check if a player should be injured from a foul.</summary>
    public bool CheckInjury(float severity, bool dangerous)
    {
        if (!dangerous) return false;
        return severity > 0.6f && _rng.NextDouble() < 0.25;
    }

    public int FoulCount => _foulCount;
    public int YellowCount => _yellowCount;
    public void SetVarAvailable(bool available) => _varAvailable = available;
}
