// Arena FC — AI Control (P3 accessibility).
// Delegate hard moments to AI (eFootball AI Control parity).
// Player can toggle AI assistance for specific situations.
using System;

namespace ArenaFC.Core;

/// <summary>AI Control modes.</summary>
public enum AIControlMode
{
    Off,           // full manual control
    Defensive,     // AI handles defending when player is off-ball
    Attacking,     // AI handles attacking runs
    Full,          // AI handles everything except ball carrier
    Situational,   // AI activates in specific situations (1v1, counter)
}

/// <summary>
/// AI Control system — delegate hard moments to AI.
/// eFootball parity: player can hand control to AI for difficult situations.
/// </summary>
public class AIControl
{
    public AIControlMode Mode = AIControlMode.Off;
    public bool IsActive => Mode != AIControlMode.Off;

    /// <summary>Check if AI should take control in current situation.</summary>
    public bool ShouldTakeControl(bool hasBall, bool isDefending,
                                   bool isOneOnOne, bool isCounterAttack,
                                   float playerStamina)
    {
        return Mode switch
        {
            AIControlMode.Off => false,
            AIControlMode.Defensive => isDefending && !hasBall,
            AIControlMode.Attacking => !isDefending && !hasBall,
            AIControlMode.Full => !hasBall,
            AIControlMode.Situational =>
                (isOneOnOne && isDefending) ||
                (isCounterAttack && !hasBall) ||
                (playerStamina < 0.2f && !hasBall),
            _ => false,
        };
    }

    /// <summary>Get AI assistance level (0 = none, 1 = full).</summary>
    public float AssistanceLevel(bool hasBall, bool isDefending)
    {
        if (!IsActive) return 0f;
        if (hasBall) return 0f; // never assist ball carrier

        return Mode switch
        {
            AIControlMode.Defensive => isDefending ? 0.8f : 0.2f,
            AIControlMode.Attacking => !isDefending ? 0.8f : 0.2f,
            AIControlMode.Full => 0.9f,
            AIControlMode.Situational => 0.6f,
            _ => 0f,
        };
    }

    /// <summary>Toggle AI Control on/off.</summary>
    public void Toggle()
    {
        Mode = Mode == AIControlMode.Off ? AIControlMode.Situational : AIControlMode.Off;
    }
}
