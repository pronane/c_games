// Arena FC - desktop graphics tiers with an automatic fallback for machines that can't carry them.
//
//   Ultra        Forward+ : SSAO + SSIL (bounce light) + SSR (wet pitch, LED reflections), TAA, 4K soft
//                shadows, floodlight beams (volumetric fog) and shadow-casting floodlights at night
//   High         Forward+ : lighter SSAO, FXAA + MSAA 2x, 2K shadows, no SSIL / SSR / beams
//   Performance  Compatibility (GL) renderer - the renderer every build used before; web and mobile stay here
//
// Choice "auto" (the default) runs a short benchmark on the first desktop launch: a few seconds of a real
// 11-a-side match, GPU frame time measured with the viewport's render-time counters (v-sync does not hide
// it).  Too slow for Forward+ -> "Performance" is saved and the game restarts on the GL renderer before the
// player sees a menu, and every later launch goes straight there.  Settings > Graphics overrides it.
// Presentation only: nothing here touches the match simulation.
using System;
using System.Collections.Generic;
using System.Linq;
using Godot;

namespace ArenaFC.GodotGame;

public enum RenderTier { Performance = 0, High = 1, Ultra = 2 }

public static class RenderProfile
{
    private const string FilePath = "user://render_profile.cfg";
    public static readonly string[] Choices = { "auto", "ultra", "high", "performance" };

    /// <summary>What the player picked (auto = benchmark decides).</summary>
    public static string Choice { get; private set; } = "auto";
    /// <summary>Tier the benchmark settled on (auto only).</summary>
    public static RenderTier Measured { get; private set; } = RenderTier.Ultra;
    public static bool Benchmarked { get; private set; }
    public static float MeasuredMs { get; private set; }
    /// <summary>Tier in force this session.</summary>
    public static RenderTier Tier { get; private set; } = RenderTier.Performance;

    // GPU ms per frame the benchmark allows (11v11, full crowd, broadcast camera).  60 fps is 16.7 ms; keep
    // headroom for busier moments (goalmouth scrambles, replays, night games).
    public const float UltraBudgetMs = 11.5f, HighBudgetMs = 16f;

    public static bool ForwardPlus => RenderingServer.GetCurrentRenderingMethod() is "forward_plus" or "mobile";
    public static bool Headless => DisplayServer.GetName() == "headless";
    private static bool Desktop => !OS.HasFeature("web") && !OS.HasFeature("mobile");

    public static void Load()
    {
        var cfg = new ConfigFile();
        if (cfg.Load(FilePath) != Error.Ok) return;
        Choice = (string)cfg.GetValue("render", "choice", "auto");
        if (!Choices.Contains(Choice)) Choice = "auto";
        Benchmarked = (bool)cfg.GetValue("render", "benchmarked", false);
        Measured = (RenderTier)Math.Clamp((int)cfg.GetValue("render", "measured_tier", (int)RenderTier.Ultra), 0, 2);
        MeasuredMs = (float)cfg.GetValue("render", "measured_ms", 0f);
    }

    public static void Save()
    {
        var cfg = new ConfigFile();
        cfg.SetValue("render", "choice", Choice);
        cfg.SetValue("render", "benchmarked", Benchmarked);
        cfg.SetValue("render", "measured_tier", (int)Measured);
        cfg.SetValue("render", "measured_ms", MeasuredMs);
        cfg.SetValue("render", "adapter", RenderingServer.GetVideoAdapterName());
        cfg.Save(FilePath);
        WriteOverride();
    }

    private const string OverridePath = "user://render_override.cfg";
    /// <summary>project.godot points application/config/project_settings_override here: when this machine
    /// runs on the GL renderer the file says so, and later launches start on it directly (no restart).</summary>
    private static void WriteOverride()
    {
        if (!Desktop) return;
        if (Wanted == RenderTier.Performance)
        {
            var o = new ConfigFile();
            o.SetValue("rendering", "renderer/rendering_method", "gl_compatibility");
            o.Save(OverridePath);
        }
        else if (Godot.FileAccess.FileExists(OverridePath)) DirAccess.RemoveAbsolute(ProjectSettings.GlobalizePath(OverridePath));
    }

    /// <summary>The tier a choice means on this machine (before the renderer check).</summary>
    public static RenderTier Wanted => Choice switch
    {
        "ultra" => RenderTier.Ultra,
        "high" => RenderTier.High,
        "performance" => RenderTier.Performance,
        _ => Benchmarked ? Measured : RenderTier.Ultra,
    };

    /// <summary>Call first thing at boot.  Returns true when the game is restarting on another renderer.</summary>
    public static bool EnsureRenderer()
    {
        Load();
        if (!Desktop || Headless) { Tier = RenderTier.Performance; return false; }
        var args = OS.GetCmdlineArgs();
        // Godot consumes --rendering-method itself (it is not in GetCmdlineArgs): a renderer other than the
        // project setting (incl. the user override) means it was forced on the command line.  QA runs that
        // pick a tier with --render-profile are never restarted either.
        string setting = (string)ProjectSettings.GetSetting("rendering/renderer/rendering_method", "forward_plus");
        bool forced = RenderingServer.GetCurrentRenderingMethod() != setting
                      || OS.GetCmdlineUserArgs().Contains("--render-profile")
                      || args.Any(a => a.StartsWith("--rendering-method") || a.StartsWith("--rendering-driver"));
        var want = Wanted;
        if (!forced && want == RenderTier.Performance && ForwardPlus)
        {
            Restart(args.Concat(new[] { "--rendering-method", "gl_compatibility" }).ToArray());
            return true;
        }
        // Forward+ unavailable (no Vulkan / D3D12: Godot fell back to GL) or forced GL: Performance
        Tier = ForwardPlus ? (want == RenderTier.Performance ? RenderTier.High : want) : RenderTier.Performance;
        return false;
    }

    /// <summary>First desktop launch on Auto, on Forward+, not a QA / tool run.</summary>
    public static bool NeedsBenchmark(string[] userArgs)
        => Desktop && !Headless && ForwardPlus && Choice == "auto" && !Benchmarked && userArgs.Length == 0;

    public static void Restart(string[] engineArgs)
    {
        // engine args, then the game's own args after "--" (OS.GetCmdlineArgs does not return those)
        var all = new List<string>(engineArgs);
        var user = OS.GetCmdlineUserArgs();
        if (user.Length > 0) { all.Add("--"); all.AddRange(user); }
        OS.SetRestartOnExit(true, all.ToArray());
        (Engine.GetMainLoop() as SceneTree)?.Quit(0);
    }

    /// <summary>Settings > Graphics.  Returns true when the change needs a restart (renderer switch).</summary>
    public static bool SetChoice(string choice)
    {
        Choice = Choices.Contains(choice) ? choice : "auto";
        Save();
        if (ForwardPlus && Wanted != RenderTier.Performance) Tier = Wanted;
        bool wantGl = Wanted == RenderTier.Performance;
        return wantGl == ForwardPlus;
    }

    /// <summary>Restart now on the renderer the current choice needs.</summary>
    public static void RestartForChoice()
    {
        var args = OS.GetCmdlineArgs().Where(a => a is not ("gl_compatibility" or "forward_plus" or "--rendering-method")).ToList();
        if (Wanted == RenderTier.Performance) { args.Add("--rendering-method"); args.Add("gl_compatibility"); }
        else { args.Add("--rendering-method"); args.Add("forward_plus"); }
        Restart(args.ToArray());
    }

    /// <summary>QA / benchmark: use a tier for this run without saving it.</summary>
    public static void ForceTier(string tier)
    {
        var t = tier switch { "ultra" => RenderTier.Ultra, "high" => RenderTier.High, _ => RenderTier.Performance };
        Tier = ForwardPlus ? (t == RenderTier.Performance ? RenderTier.High : t) : RenderTier.Performance;
    }

    public static void RecordBenchmark(float gpuMs)
    {
        MeasuredMs = gpuMs;
        Measured = gpuMs <= UltraBudgetMs ? RenderTier.Ultra : gpuMs <= HighBudgetMs ? RenderTier.High : RenderTier.Performance;
        Benchmarked = true;
        Save();
    }

    public static string Describe()
    {
        string t = Tier switch { RenderTier.Ultra => "Ultra", RenderTier.High => "High", _ => "Performance" };
        string how = Choice == "auto" ? (Benchmarked ? $"auto, measured {MeasuredMs:0.0} ms" : "auto") : "chosen";
        return $"{t} ({how}) · {RenderingServer.GetCurrentRenderingMethod()} · {RenderingServer.GetVideoAdapterName()}";
    }

    // ------------------------------------------------------------------ applying a tier
    /// <summary>Anti-aliasing and resolution for the match viewport.</summary>
    public static void ApplyViewport(Viewport vp)
    {
        if (!ForwardPlus) return;
        if (Tier == RenderTier.Ultra)
        {
            vp.UseTaa = true;
            vp.Msaa3D = Viewport.Msaa.Disabled;
            vp.ScreenSpaceAA = Viewport.ScreenSpaceAAEnum.Disabled;
            vp.UseDebanding = true;
            RenderingServer.DirectionalShadowAtlasSetSize(4096, true);
            RenderingServer.DirectionalSoftShadowFilterSetQuality(RenderingServer.ShadowQuality.SoftHigh);
            RenderingServer.PositionalSoftShadowFilterSetQuality(RenderingServer.ShadowQuality.SoftMedium);
        }
        else
        {
            vp.UseTaa = false;
            vp.Msaa3D = Viewport.Msaa.Msaa2X;
            vp.ScreenSpaceAA = Viewport.ScreenSpaceAAEnum.Fxaa;
            RenderingServer.DirectionalShadowAtlasSetSize(2048, true);
            RenderingServer.DirectionalSoftShadowFilterSetQuality(RenderingServer.ShadowQuality.SoftMedium);
        }
    }

    /// <summary>Lighting effects and the broadcast colour grade (D3) for the match environment.</summary>
    public static void ApplyEnvironment(Godot.Environment env, string lighting, DirectionalLight3D? sun)
    {
        // Broadcast grade on every tier: a touch more contrast and colour, the look of a TV feed.
        env.AdjustmentEnabled = true;
        env.AdjustmentContrast = 1.07f;
        env.AdjustmentSaturation = 1.08f;
        env.AdjustmentBrightness = 1.0f;
        if (!ForwardPlus) return;
        bool night = lighting == "night";
        // AgX: filmic highlight roll-off (floodlights, white kits in sun) without ACES's hue shifts
        env.TonemapMode = Godot.Environment.ToneMapper.Agx;
        env.TonemapExposure = night ? 1.25f : 1.15f;
        // AgX is flatter than ACES: give back the TV feed's punch
        env.AdjustmentContrast = 1.14f;
        env.AdjustmentSaturation = 1.12f;
        // Forward+ fog is physically based and far heavier than the GL path at the same density: keep only
        // a whisper of aerial perspective across the bowl
        env.FogDensity = night ? .0003f : .00035f;
        env.FogAerialPerspective = .15f;
        env.FogSkyAffect = .2f;
        env.SsaoEnabled = true;
        env.SsaoRadius = 1.2f;
        env.SsaoIntensity = Tier == RenderTier.Ultra ? 1.6f : 1.2f;
        env.SsaoPower = 1.5f;
        env.SsaoDetail = .6f;
        env.SsaoLightAffect = .15f;
        env.GlowEnabled = true;
        env.GlowIntensity = night ? .55f : .3f;
        env.GlowBloom = night ? .1f : .04f;
        env.GlowHdrThreshold = 1.1f;
        if (Tier == RenderTier.Ultra)
        {
            env.SsilEnabled = true;            // grass-green bounce on legs, kit colour on the turf
            env.SsilIntensity = .8f;
            env.SsilRadius = 4f;
            env.SsrEnabled = true;             // wet pitch, boots, LED boards
            env.SsrMaxSteps = 48;
            env.SsrFadeIn = .2f;
            env.SsrFadeOut = 2f;
            env.SsrDepthTolerance = .3f;
            if (night)
            {
                // floodlight beams through the night air
                env.VolumetricFogEnabled = true;
                env.VolumetricFogDensity = .0012f;
                env.VolumetricFogSkyAffect = 0f;        // a black night sky; the haze hangs round the lights
                env.VolumetricFogAlbedo = new Color(.85f, .88f, .95f);
                env.VolumetricFogAnisotropy = .7f;
                env.VolumetricFogLength = 160f;
                env.FogEnabled = false;
            }
        }
        if (sun != null)
        {
            sun.ShadowBlur = Tier == RenderTier.Ultra ? 1.2f : 1f;
            sun.DirectionalShadowMode = DirectionalLight3D.ShadowMode.Parallel4Splits;
            sun.DirectionalShadowMaxDistance = 140f;
            sun.LightAngularDistance = night ? 0f : .55f;   // sun disc: contact-hardening soft shadows
        }
    }

    /// <summary>Whether a floodlight should cast shadows (night, Ultra: the classic multi-shadow look).</summary>
    public static bool FloodlightShadows(string lighting) => ForwardPlus && Tier == RenderTier.Ultra && lighting == "night";
}
