// Arena FC — Forward+ renderer configuration for desktop.
// Enables SSGI, SDFGI, and volumetric fog on desktop only.
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
        env.SdfgiYScaleEnabled = true;
        env.SdfgiYScale = 0.2f;

        // SSGI (Screen Space Global Illumination)
        env.SsgiEnabled = true;
        env.SsgiQuality = Godot.Environment.SSGIQuality.High;

        // SSIL (Screen Space Indirect Lighting)
        env.SsilEnabled = true;
        env.SsilQuality = Godot.Environment.SSILQuality.High;

        // Volumetric fog
        env.VolumetricFogEnabled = true;
        env.VolumetricFogEmissionEnergy = 1.0f;
        env.VolumetricFogAnisotropy = 0.2f;
        env.VolumetricFogTemporalReprojection = true;
        env.VolumetricFogTemporalReprojectionMix = 0.1f;
        env.VolumetricFogTemporalReprojectionEmission = 1.0f;

        // Glow (bloom) — already configured in World3D, ensure enabled
        env.GlowEnabled = true;
        env.GlowLevels1 = 0.8f;
        env.GlowLevels2 = 0.6f;
        env.GlowLevels3 = 0.4f;
        env.GlowLevels4 = 0.2f;
        env.GlowLevels5 = 0.1f;
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
