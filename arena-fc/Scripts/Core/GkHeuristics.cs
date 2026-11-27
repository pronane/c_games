// Arena FC — deterministic goalkeeper heuristics (priority 3 AI depth).
// Pure C#, no RNG. Callers supply sampled state; this never mutates MatchState.
using System;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>
/// GK positioning and dive decision helpers. Keepers stay on the angle of the
/// ball to the near post, step off the line with shot distance, and only dive
/// when the ball is closing inside a commit window.
/// </summary>
public static class GkHeuristics
{
    /// <summary>Desired GK standing position between the goal plane and the ball.</summary>
    /// <param name="goalCenter">Center of the goal this keeper protects (world XZ on pitch plane).</param>
    /// <param name="goalHalfWidth">Half goal mouth width (metres).</param>
    /// <param name="ballPos">Current ball position.</param>
    /// <param name="lineDepth">How far off the line the keeper stands at rest (metres, positive toward pitch).</param>
    public static Vector3 DesiredPosition(
        Vector3 goalCenter, float goalHalfWidth, Vector3 ballPos, float lineDepth = 1.2f)
    {
        // Angle cover: project ball onto the goal line, clamp to posts, then step out.
        float lateral = Math.Clamp(ballPos.Z - goalCenter.Z, -goalHalfWidth * 0.92f, goalHalfWidth * 0.92f);
        // Depth scales with distance — closer shots pull the keeper slightly off the line.
        float dist = MathF.Max(0.5f, MathF.Sqrt(
            (ballPos.X - goalCenter.X) * (ballPos.X - goalCenter.X) +
            (ballPos.Z - goalCenter.Z) * (ballPos.Z - goalCenter.Z)));
        float depth = Math.Clamp(lineDepth + Math.Clamp(18f - dist, 0f, 6f) * 0.08f, 0.6f, 3.5f);
        // Goal faces along +/- X; step into the pitch along the goal normal.
        float towardPitch = MathF.Sign(goalCenter.X) == 0f ? 1f : -MathF.Sign(goalCenter.X);
        return new Vector3(goalCenter.X + towardPitch * depth, 0f, goalCenter.Z + lateral * 0.55f);
    }

    /// <summary>True when the keeper should commit to a dive rather than set.</summary>
    public static bool ShouldDive(
        Vector3 keeperPos, Vector3 ballPos, Vector3 ballVel,
        float reactionSeconds = 0.18f, float commitRadius = 4.5f)
    {
        Vector3 toBall = ballPos - keeperPos;
        float dist = toBall.Length();
        if (dist > commitRadius) return false;

        float approach = -Vector3.Dot(Vector3.Normalize(toBall.LengthSquared() > 1e-6f ? toBall : Vector3.UnitX),
                                      ballVel);
        // Closing speed toward the keeper and inside the window.
        if (approach < 2.5f) return false;
        float ttc = dist / MathF.Max(0.1f, approach);
        return ttc <= reactionSeconds + 0.55f;
    }

    /// <summary>Preferred dive direction in XZ (unit-ish); zero when a set is better.</summary>
    public static Vector3 DiveDirection(Vector3 keeperPos, Vector3 ballPos, Vector3 ballVel)
    {
        if (!ShouldDive(keeperPos, ballPos, ballVel)) return Vector3.Zero;
        Vector3 predict = ballPos + ballVel * 0.22f;
        Vector3 delta = predict - keeperPos;
        delta.Y = 0f;
        float len = delta.Length();
        return len > 1e-4f ? delta / len : Vector3.Zero;
    }
}
