using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Godot;

namespace ArenaFC.GodotGame;

/// <summary>
/// QA: `--graphics-report PATH` (with `--screenshot`) writes what the frame in the screenshot was
/// rendered with, for the graphics benchmark (Tools/graphics_benchmark.py):
/// the renderer, anti-aliasing, the environment's lighting features (SSAO, SSR, SDFGI, glow, fog,
/// tonemapper), shadows, what the frame drew (objects, primitives, draw calls), and how tall the
/// players are on screen and how many are in shot.
/// </summary>
public static class GraphicsReport
{
    public static string? PathFromArgs()
    {
        var args = OS.GetCmdlineUserArgs();
        int i = Array.IndexOf(args, "--graphics-report");
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    public static void Write(string path, Viewport vp, Image img)
    {
        var root = vp.GetTree().Root;
        var env = FindAll<WorldEnvironment>(root).FirstOrDefault()?.Environment;
        var suns = FindAll<DirectionalLight3D>(root).Where(l => l.Visible).ToList();
        var cam = vp.GetCamera3D();
        var r = new Dictionary<string, object>
        {
            ["renderer"] = RenderingServer.GetCurrentRenderingMethod(),
            ["video_adapter"] = RenderingServer.GetVideoAdapterName(),
            ["width"] = img.GetWidth(),
            ["height"] = img.GetHeight(),
            ["msaa_3d"] = vp.Msaa3D.ToString(),
            ["screen_space_aa"] = vp.ScreenSpaceAA.ToString(),
            ["taa"] = vp.UseTaa,
            ["scaling_3d_scale"] = vp.Scaling3DScale,
            ["objects_in_frame"] = Performance.GetMonitor(Performance.Monitor.RenderTotalObjectsInFrame),
            ["primitives_in_frame"] = Performance.GetMonitor(Performance.Monitor.RenderTotalPrimitivesInFrame),
            ["draw_calls_in_frame"] = Performance.GetMonitor(Performance.Monitor.RenderTotalDrawCallsInFrame),
            ["video_mem_mb"] = Math.Round(Performance.GetMonitor(Performance.Monitor.RenderVideoMemUsed) / 1048576.0, 1),
            ["shadow_casting_suns"] = suns.Count(l => l.ShadowEnabled),
        };
        if (env != null)
        {
            r["tonemapper"] = env.TonemapMode.ToString();
            r["ssao"] = env.SsaoEnabled;
            r["ssil"] = env.SsilEnabled;
            r["ssr"] = env.SsrEnabled;
            r["sdfgi"] = env.SdfgiEnabled;
            r["glow"] = env.GlowEnabled;
            r["volumetric_fog"] = env.VolumetricFogEnabled;
            r["fog"] = env.FogEnabled;
        }
        // players on screen: every CharacterRig in front of the camera
        var heights = new List<double>();
        if (cam != null)
            foreach (var rig in FindAll<CharacterRig>(root))
            {
                if (!rig.IsVisibleInTree()) continue;
                var feet = rig.GlobalPosition;
                var head = feet + Vector3.Up * 1.8f;
                if (!cam.IsPositionInFrustum(feet) && !cam.IsPositionInFrustum(head)) continue;
                if (cam.IsPositionBehind(feet)) continue;
                var a = cam.UnprojectPosition(feet);
                var b = cam.UnprojectPosition(head);
                heights.Add(Math.Abs(a.Y - b.Y));
            }
        heights.Sort();
        r["players_in_shot"] = heights.Count;
        r["player_height_px_median"] = heights.Count > 0 ? Math.Round(heights[heights.Count / 2], 1) : 0.0;
        r["player_height_px_max"] = heights.Count > 0 ? Math.Round(heights[^1], 1) : 0.0;
        r["player_height_frac_median"] = heights.Count > 0 ? Math.Round(heights[heights.Count / 2] / img.GetHeight(), 4) : 0.0;
        var dir = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(path, JsonSerializer.Serialize(r, new JsonSerializerOptions { WriteIndented = true }));
        GD.Print($"ARENA_FC_GRAPHICS_REPORT {path}");
    }

    private static IEnumerable<T> FindAll<T>(Node n) where T : Node
    {
        if (n is T t) yield return t;
        foreach (var c in n.GetChildren())
            foreach (var x in FindAll<T>(c)) yield return x;
    }
}
