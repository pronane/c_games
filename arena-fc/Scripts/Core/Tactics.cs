// Arena FC — in-match tactics (A4).
// Mentality, width, pressing intensity — adjustable during play.
using System;

namespace ArenaFC.Core;

/// <summary>Team mentality.</summary>
public enum Mentality
{
    VeryDefensive,
    Defensive,
    Balanced,
    Attacking,
    VeryAttacking,
}

/// <summary>
/// In-match tactics that can be adjusted during play.
/// Affects AI positioning, pressing, and risk-taking.
/// </summary>
public class Tactics
{
    public Mentality Mentality = Mentality.Balanced;
    public float Width = 0.5f;           // 0 = narrow, 1 = wide
    public float PressingIntensity = 0.5f; // 0 = drop off, 1 = high press
    public float Tempo = 0.5f;           // 0 = slow build-up, 1 = direct

    /// <summary>Get AI modifiers from current tactics.</summary>
    public (float pressMultiplier, float runAggression, float passLength,
            float defensiveLine, float widthMultiplier) GetModifiers()
    {
        float mentalityFactor = Mentality switch
        {
            Mentality.VeryDefensive => -0.4f,
            Mentality.Defensive => -0.2f,
            Mentality.Balanced => 0f,
            Mentality.Attacking => 0.2f,
            Mentality.VeryAttacking => 0.4f,
            _ => 0f,
        };

        float pressMultiplier = 0.5f + PressingIntensity * 0.8f + mentalityFactor * 0.3f;
        float runAggression = 0.7f + mentalityFactor * 0.5f + Tempo * 0.3f;
        float passLength = 0.8f + Tempo * 0.5f;
        float defensiveLine = 0.5f + mentalityFactor * 0.4f; // 0 = deep, 1 = high
        float widthMultiplier = 0.6f + Width * 0.8f;

        return (pressMultiplier, runAggression, passLength, defensiveLine, widthMultiplier);
    }

    /// <summary>Adjust mentality up/down.</summary>
    public void ShiftMentality(int direction)
    {
        int current = (int)Mentality;
        current = Math.Clamp(current + direction, 0, 4);
        Mentality = (Mentality)current;
    }

    /// <summary>Adjust pressing intensity.</summary>
    public void AdjustPressing(float delta)
    {
        PressingIntensity = Math.Clamp(PressingIntensity + delta, 0f, 1f);
    }

    /// <summary>Adjust width.</summary>
    public void AdjustWidth(float delta)
    {
        Width = Math.Clamp(Width + delta, 0f, 1f);
    }

    /// <summary>Adjust tempo.</summary>
    public void AdjustTempo(float delta)
    {
        Tempo = Math.Clamp(Tempo + delta, 0f, 1f);
    }
}
