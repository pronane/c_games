// Arena FC — crowd density system (P3 polish).
// Visual crowd density + audio ambience scaling by match importance.
using System;

namespace ArenaFC.Core;

/// <summary>Crowd density levels.</summary>
public enum CrowdDensity
{
    Sparse,    // training, low attendance
    Moderate,  // regular match
    Full,      // big match, derby
    Packed,    // final, sold out
}

/// <summary>
/// Manages crowd density and ambience.
/// Scales visual crowd count and audio volume by match importance.
/// </summary>
public class CrowdDensitySystem
{
    public CrowdDensity Density = CrowdDensity.Moderate;
    public float Excitement = 0.5f; // 0 = calm, 1 = electric

    /// <summary>Get crowd count for rendering.</summary>
    public int GetCrowdCount()
    {
        return Density switch
        {
            CrowdDensity.Sparse => 500,
            CrowdDensity.Moderate => 5000,
            CrowdDensity.Full => 20000,
            CrowdDensity.Packed => 60000,
            _ => 5000,
        };
    }

    /// <summary>Get audio ambience level (0-1).</summary>
    public float GetAudioLevel()
    {
        float baseLevel = Density switch
        {
            CrowdDensity.Sparse => 0.2f,
            CrowdDensity.Moderate => 0.5f,
            CrowdDensity.Full => 0.8f,
            CrowdDensity.Packed => 1.0f,
            _ => 0.5f,
        };
        return baseLevel * (0.5f + Excitement * 0.5f);
    }

    /// <summary>React to a goal (crowd erupts).</summary>
    public void OnGoal()
    {
        Excitement = Math.Min(1f, Excitement + 0.3f);
    }

    /// <summary>React to a save.</summary>
    public void OnSave()
    {
        Excitement = Math.Min(1f, Excitement + 0.15f);
    }

    /// <summary>Decay excitement over time.</summary>
    public void Update(float dt)
    {
        Excitement = Math.Max(0.3f, Excitement - dt * 0.02f);
    }

    /// <summary>Set density from match type.</summary>
    public void SetFromMatchType(string matchType)
    {
        Density = matchType switch
        {
            "training" => CrowdDensity.Sparse,
            "friendly" => CrowdDensity.Moderate,
            "league" => CrowdDensity.Full,
            "cup_final" => CrowdDensity.Packed,
            "derby" => CrowdDensity.Packed,
            _ => CrowdDensity.Moderate,
        };
    }
}
