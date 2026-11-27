// Arena FC — first-touch variant selection (priority 2 ball/contact fidelity).
// Pure C#, deterministic. Does not mutate MatchState.
using System;

namespace ArenaFC.Core;

/// <summary>First-touch outcome families used to pick trap / redirect clips and sim behaviour.</summary>
public enum FirstTouchKind
{
    Trap,       // kill the ball at the feet
    Cushion,    // soft take into space (thigh/chest feel)
    Redirect,   // first-time lay-off / steered touch
    Clear,      // emergency boot away under pressure
}

/// <summary>
/// Chooses a first-touch variant from approach speed, ball height, and pressure.
/// Presentation can map the result to trap / thigh_control / chest_control clips;
/// sim can bias DirectedTouch vs kill-at-feet.
/// </summary>
public static class FirstTouch
{
    /// <summary>Select a first-touch kind.</summary>
    /// <param name="approachSpeed">Ball closing speed relative to receiver (m/s).</param>
    /// <param name="ballHeight">Ball Y at expected contact (metres).</param>
    /// <param name="pressureDistance">Nearest opponent distance (metres); large = free.</param>
    /// <param name="controlAttr">Player control attribute 0-1.</param>
    public static FirstTouchKind Select(
        float approachSpeed, float ballHeight, float pressureDistance, float controlAttr)
    {
        approachSpeed = Math.Max(0f, approachSpeed);
        ballHeight = Math.Max(0f, ballHeight);
        pressureDistance = Math.Max(0f, pressureDistance);
        controlAttr = Math.Clamp(controlAttr, 0f, 1f);

        // Emergency clear under heavy pressure and a hot ball.
        if (pressureDistance < 2.2f && approachSpeed > 9f)
            return FirstTouchKind.Clear;

        // Aerial / chest-thigh window.
        if (ballHeight > 1.15f && ballHeight < 2.2f)
            return controlAttr > 0.45f ? FirstTouchKind.Cushion : FirstTouchKind.Trap;

        // Steered first touch into space when free and the ball is not a rocket.
        if (pressureDistance > 4.5f && approachSpeed < 11f && controlAttr > 0.55f)
            return FirstTouchKind.Redirect;

        // Soft cushion for moderate balls.
        if (approachSpeed < 7f && controlAttr > 0.4f)
            return FirstTouchKind.Cushion;

        return FirstTouchKind.Trap;
    }

    /// <summary>Preferred action / clip token for the selected kind.</summary>
    public static string ActionToken(FirstTouchKind kind) => kind switch
    {
        FirstTouchKind.Cushion => "thigh_control",
        FirstTouchKind.Redirect => "trap",
        FirstTouchKind.Clear => "clear",
        _ => "trap",
    };

    /// <summary>Contact fraction bias: clearer first touches contact slightly earlier.</summary>
    public static float ContactFractionBias(FirstTouchKind kind) => kind switch
    {
        FirstTouchKind.Clear => 0.28f,
        FirstTouchKind.Redirect => 0.36f,
        FirstTouchKind.Cushion => 0.42f,
        _ => 0.40f,
    };
}
