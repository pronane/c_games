// Arena FC — shielding body positioning (P3 polish).
// Visible body lean/rotation when shielding the ball from opponents.
using System;

namespace ArenaFC.Core;

/// <summary>
/// Shielding body positioning — visible lean and rotation
/// when protecting the ball from nearby opponents.
/// </summary>
public static class Shielding
{
    /// <summary>Calculate shielding pose offsets.</summary>
    /// <param name="opponentDirection">Direction to nearest opponent (normalised)</param>
    /// <param name="opponentDistance">Distance to nearest opponent (metres)</param>
    /// <param name="strength">Player strength attribute (0-99)</param>
    /// <returns>(leanX, leanZ, rotationY) — body lean and turn offsets</returns>
    public static (float leanX, float leanZ, float rotationY) GetPose(
        float opponentDirX, float opponentDirZ,
        float opponentDistance, int strength)
    {
        // Shielding activates when opponent is close
        if (opponentDistance > 3f) return (0f, 0f, 0f);

        // Lean away from opponent (protect ball)
        float leanAmount = Math.Clamp(1f - opponentDistance / 3f, 0f, 1f);
        float leanX = -opponentDirX * leanAmount * 0.15f;
        float leanZ = -opponentDirZ * leanAmount * 0.15f;

        // Turn body to face opponent (shield position)
        float rotationY = (float)Math.Atan2(opponentDirX, opponentDirZ) * 0.3f;

        // Stronger players shield more effectively (less lean needed)
        float strengthFactor = 1f - (strength / 100f) * 0.3f;
        leanX *= strengthFactor;
        leanZ *= strengthFactor;

        return (leanX, leanZ, rotationY);
    }

    /// <summary>Calculate shielding effectiveness (tackle resistance).</summary>
    public static float Effectiveness(float opponentDistance, int strength, float stamina)
    {
        if (opponentDistance > 3f) return 0f;

        float baseEffect = 1f - opponentDistance / 3f;
        float strengthBonus = strength / 100f * 0.3f;
        float staminaPenalty = stamina < 0.3f ? 0.2f : 0f;

        return Math.Clamp(baseEffect + strengthBonus - staminaPenalty, 0f, 0.8f);
    }
}
