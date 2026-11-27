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
    /// <summary>Calculate shielding pose offsets.
    /// Orient the body so the torso sits between the ball and the nearest threat,
    /// lean into the contact, and face the opponent (FC-style hold-up).</summary>
    public static (float leanX, float leanZ, float rotationY) GetPose(
        float opponentDirX, float opponentDirZ,
        float opponentDistance, int strength)
        => GetPose(opponentDirX, opponentDirZ, opponentDistance, strength, 0f, 0f);

    /// <summary>Same as GetPose, with optional ball direction so the lean keeps
    /// the body between the ball and the opponent when both are known.</summary>
    public static (float leanX, float leanZ, float rotationY) GetPose(
        float opponentDirX, float opponentDirZ,
        float opponentDistance, int strength,
        float ballDirX, float ballDirZ)
    {
        if (opponentDistance > 3f) return (0f, 0f, 0f);

        float invLen = 1f / MathF.Max(1e-4f, MathF.Sqrt(opponentDirX * opponentDirX + opponentDirZ * opponentDirZ));
        float oX = opponentDirX * invLen;
        float oZ = opponentDirZ * invLen;

        // Protective face: toward the opponent (primary). When a ball direction is
        // available, bias slightly so the chest still covers the ball side.
        float faceX = oX, faceZ = oZ;
        float bLen = MathF.Sqrt(ballDirX * ballDirX + ballDirZ * ballDirZ);
        if (bLen > 1e-3f)
        {
            float bX = ballDirX / bLen, bZ = ballDirZ / bLen;
            faceX = oX * 0.85f - bX * 0.15f;
            faceZ = oZ * 0.85f - bZ * 0.15f;
            float fLen = MathF.Sqrt(faceX * faceX + faceZ * faceZ);
            if (fLen > 1e-4f) { faceX /= fLen; faceZ /= fLen; }
        }

        float leanAmount = Math.Clamp(1f - opponentDistance / 3f, 0f, 1f);
        // Lean into the opponent (absorb contact) rather than purely away.
        float leanX = faceX * leanAmount * 0.12f;
        float leanZ = faceZ * leanAmount * 0.12f;

        float rotationY = MathF.Atan2(faceX, faceZ) * 0.35f;

        // Stronger players need less exaggerated lean to hold position.
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
