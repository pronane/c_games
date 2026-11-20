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
    /// <summary>Attack / defence shapes and playstyle (FluidFormations).  Used to
    /// nudge the AI modifiers below so the shape choice is not cosmetic.</summary>
    public FluidFormation Shape = new();

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

        // Blend in the fluid-formation playstyle so the chosen shape changes how
        // the AI presses and how long it looks for a pass.
        var (shapePress, shapePass, shapeRun) = Shape.GetPlaystyleModifiers();
        pressMultiplier *= Math.Clamp(.75f + shapePress, .5f, 1.6f);
        runAggression *= Math.Clamp(.75f + shapeRun, .5f, 1.6f);
        passLength *= Math.Clamp(.8f + shapePass * .5f, .5f, 1.6f);

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
