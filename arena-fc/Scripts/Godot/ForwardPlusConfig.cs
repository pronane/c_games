// Arena FC — Forward+ renderer configuration for desktop.
// Enables SDFGI and volumetric fog on desktop only.
// Browser stays on Compatibility renderer.
using Godot;

namespace ArenaFC.GodotGame;

/// <summary>
/// Configures Forward+ renderer features for desktop.
/// Call from World3D.Build() when quality is High and platform is desktop.
/// </summary>
public static class ForwardPlusConfig
{
    /// <summary>Apply Forward+ features to the environment.</summary>
    public static void Apply(Godot.Environment env, bool isDesktop)
    {
        if (!isDesktop) return;

        // SDFGI (Signed Distance Field Global Illumination)
        env.SdfgiEnabled = true;
        env.SdfgiCascades = 4;
        env.SdfgiMinCellSize = 0.2f;
        env.SdfgiMaxDistance = 100f;
        // SdfgiYScale left at default (1.0) — enum member names vary by binding version

        // SSIL (Screen Space Indirect Lighting)
        env.SsilEnabled = true;

        // Volumetric fog
        env.VolumetricFogEnabled = true;
        env.VolumetricFogEmissionEnergy = 1.0f;
        env.VolumetricFogAnisotropy = 0.2f;

        // Glow (bloom) — already configured in World3D, ensure enabled
        env.GlowEnabled = true;
        env.GlowIntensity = 0.8f;
        env.GlowStrength = 1.2f;
        env.GlowBloom = 0.1f;
        env.GlowBlendMode = Godot.Environment.GlowBlendModeEnum.Additive;

        // Adjustments (colour grading)
        env.AdjustmentEnabled = true;
        env.AdjustmentBrightness = 1.0f;
        env.AdjustmentContrast = 1.05f;
        env.AdjustmentSaturation = 1.1f;
    }

    /// <summary>Check if Forward+ is available on this platform.</summary>
    public static bool IsAvailable()
    {
        string os = OS.GetName();
        // Forward+ not available on web/mobile
        return os != "Android" && os != "iOS" && os != "Web";
    }
}
