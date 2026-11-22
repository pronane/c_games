// Arena FC - the ground, crowd and boards built by Sprite Forge (sforge.stadium / crowd / adboards, v11.32).
// Tools/build_stadiums.py writes Data/stadiums/*; this loads the preset that fits the home club's ground,
// tints the ends and the crowd with the two clubs' colours, instances the crowd from the seat map and puts
// real light sources where the masts / roof lamps are.  Presentation only.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Stadium
{
    public const string GroundDir = "res://Data/stadiums/";
    /// <summary>Clubs' colours for the ends and the crowd (set before Build).</summary>
    public Color HomeColour = new(.84f, .15f, .24f), AwayColour = new(.11f, .30f, .85f);
    public string GroundPreset { get; private set; } = "";
    public int CrowdShown { get; private set; }
    private ShaderMaterial? _crowdFigMat, _ledMat;
    private float _goalFlash;

    /// <summary>bowl / classic / ground from the club's stadium (capacity, roof).</summary>
    public static string PresetFor(StadiumInfo s)
        => s.Capacity >= 45000 && s.Roof ? "bowl" : s.Roof ? "classic" : "ground";

    public static bool GroundAvailable(string preset)
        => Godot.FileAccess.FileExists(GroundDir + $"stadium_{preset}.glb")
           && Godot.FileAccess.FileExists(GroundDir + $"stadium_{preset}.seats");

    /// <summary>Spectators drawn for a quality tier (the seat map holds 6-19k seats).</summary>
    public static int CrowdBudget(QualityPreset q) => q switch
    {
        QualityPreset.Low => 1500,
        QualityPreset.Medium => 3500,
        _ => 6000,         // ~690k triangles at 114 each
    };

    private bool BuildSpriteForgeGround(StadiumInfo info, QualityPreset q, bool fullCrowd)
    {
        string preset = PresetFor(info);
        if (!GroundAvailable(preset)) return false;
        var doc = new GltfDocument();
        var st = new GltfState();
        if (doc.AppendFromFile(GroundDir + $"stadium_{preset}.glb", st) != Error.Ok) return false;
        if (doc.GenerateScene(st) is not Node3D ground) return false;
        ground.Name = "Ground";
        AddChild(ground);
        GroundPreset = preset;
        var seatsMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/stand_seats.gdshader") };
        seatsMat.SetShaderParameter("home", HomeColour);
        seatsMat.SetShaderParameter("away", AwayColour);
        _ledMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/led_ads.gdshader") };
        if (Godot.FileAccess.FileExists(GroundDir + "ad_boards.png"))
            _ledMat.SetShaderParameter("atlas", LoadPng(GroundDir + "ad_boards.png"));
        _ledMat.SetShaderParameter("flash_a", HomeColour);
        foreach (var n in ground.FindChildren("*", "MeshInstance3D", true, false))
        {
            if (n is not MeshInstance3D mi) continue;
            string name = mi.Name.ToString();
            mi.CastShadow = name is "roof" or "roof_columns" or "floodlight_masts" or "dugouts"
                ? GeometryInstance3D.ShadowCastingSetting.On : GeometryInstance3D.ShadowCastingSetting.Off;
            if (name.StartsWith("stand_seats")) mi.MaterialOverride = seatsMat;
            else if (name.StartsWith("ad_ring")) mi.MaterialOverride = _ledMat;
            else if (name.StartsWith("screens"))
            {
                // the big screens show the scoreline (World3D.UpdateJumbotron writes the label in front)
                mi.MaterialOverride = new StandardMaterial3D { AlbedoColor = new Color(.02f, .03f, .05f), EmissionEnabled = true,
                    Emission = new Color(.05f, .09f, .16f), EmissionEnergyMultiplier = 1.4f };
            }
            else if (mi.GetActiveMaterial(0) is BaseMaterial3D bm)
            {
                bm.VertexColorUseAsAlbedo = true;
                bm.VertexColorIsSrgb = true;      // glTF import stores them sRGB-encoded
                if (name is "floodlight_lamps" or "roof_fascia") { bm.EmissionEnabled = true; bm.Emission = new Color(1f, .96f, .85f); bm.EmissionEnergyMultiplier = name == "floodlight_lamps" ? 5f : 1.1f; }
            }
        }
        var meta = ReadJson(GroundDir + $"stadium_{preset}.json");
        if (meta != null)
        {
            BuildLights(meta.Value, info.Floodlights);
            PlaceScreens(meta.Value);
        }
        if (fullCrowd) BuildFigureCrowd(preset, CrowdBudget(q), info.Capacity);
        return true;
    }

    private static Texture2D? LoadPng(string path)
    {
        // imported resource first (works in exported builds); the raw file in the editor / headless tools
        if (ResourceLoader.Exists(path) && GD.Load<Texture2D>(path) is Texture2D tex) return tex;
        var img = Image.LoadFromFile(ProjectSettings.GlobalizePath(path));
        if (img == null || img.IsEmpty()) img = Image.LoadFromFile(path);
        if (img == null || img.IsEmpty()) return null;
        img.GenerateMipmaps();
        return ImageTexture.CreateFromImage(img);
    }

    private static JsonElement? ReadJson(string path)
    {
        if (!Godot.FileAccess.FileExists(path)) return null;
        return JsonDocument.Parse(Godot.FileAccess.GetFileAsString(path)).RootElement.Clone();
    }

    private void BuildLights(JsonElement meta, bool floodlights)
    {
        if (!floodlights || !meta.TryGetProperty("lights", out var lights)) return;
        int k = 0;
        foreach (var l in lights.EnumerateArray())
        {
            var p = l.GetProperty("pos");
            var pos = new Vector3(p[0].GetSingle(), p[1].GetSingle(), p[2].GetSingle());
            bool mast = l.GetProperty("kind").GetString() == "mast";
            if (!mast && k++ % 2 == 1) continue;            // roof strips: every other cluster is a light source
            var spot = new SpotLight3D
            {
                Name = "Floodlight", LightColor = new Color(1f, .96f, .88f), LightEnergy = (mast ? .9f : .45f) * FloodMul,
                SpotRange = 220f, SpotAngle = mast ? 38f : 46f, SpotAttenuation = .6f, ShadowEnabled = false,
            };
            AddChild(spot);
            spot.LookAtFromPosition(pos, new Vector3(pos.X * .15f, 0, pos.Z * .15f), Vector3.Up);
        }
    }

    private void PlaceScreens(JsonElement meta)
    {
        if (!meta.TryGetProperty("screens", out var screens) || screens.GetArrayLength() == 0) return;
        var s0 = screens[0];
        var c = s0.GetProperty("centre");
        var f = s0.GetProperty("faces");
        float fx = f[0].GetSingle();
        var pos = new Vector3(c[0].GetSingle() + fx * .1f, c[1].GetSingle(), c[2].GetSingle());
        _jumbotronAnchor = pos;
        _jumbotronYaw = fx > 0 ? 90f : -90f;
    }

    private Vector3? _jumbotronAnchor;
    private float _jumbotronYaw;

    /// <summary>Instance the crowd on the seat map: ends in the clubs' colours (scarves and flags among
    /// them), the sides mixed; attendance from the ground's capacity; a deterministic pick so every match at a
    /// ground looks the same.</summary>
    private void BuildFigureCrowd(string preset, int budget, int capacity)
    {
        string seatsPath = GroundDir + $"stadium_{preset}.seats";
        string crowdPath = GroundDir + "crowd.glb";
        if (!Godot.FileAccess.FileExists(seatsPath) || !Godot.FileAccess.FileExists(crowdPath)) return;
        var bytes = Godot.FileAccess.GetFileAsBytes(seatsPath);
        int n = BitConverter.ToInt32(bytes, 0);
        var doc = new GltfDocument();
        var st = new GltfState();
        if (doc.AppendFromFile(crowdPath, st) != Error.Ok || doc.GenerateScene(st) is not Node3D figs) return;
        Godot.Mesh? seated = null, flag = null;
        foreach (var c in figs.FindChildren("*", "MeshInstance3D", true, false))
            if (c is MeshInstance3D mi)
            {
                if (mi.Name == "seated") seated = mi.Mesh;
                else if (mi.Name == "flag") flag = mi.Mesh;
            }
        figs.QueueFree();
        if (seated == null) return;
        // attendance: big grounds sell out, small ones are 80% full; then the render budget
        float fill = Math.Clamp(.8f + capacity / 300000f, .8f, .97f);
        float keep = Math.Min(fill, budget / (float)n);
        var rng = new Rng(4242 + n);
        var xf = new List<Transform3D>();
        var custom = new List<Color>();
        var flagXf = new List<Transform3D>();
        var flagCustom = new List<Color>();
        Color[] neutral =
        {
            new(.92f, .92f, .94f), new(.12f, .13f, .16f), new(.35f, .38f, .45f), new(.55f, .2f, .18f),
            new(.18f, .3f, .55f), new(.75f, .62f, .25f), new(.25f, .45f, .3f),
        };
        for (int i = 0; i < n; i++)
        {
            if (rng.Next() > keep) continue;
            int o = 4 + i * 24;
            float x = BitConverter.ToSingle(bytes, o), y = BitConverter.ToSingle(bytes, o + 4), z = BitConverter.ToSingle(bytes, o + 8);
            float yaw = BitConverter.ToSingle(bytes, o + 12), end = BitConverter.ToSingle(bytes, o + 20);
            float sc = .92f + rng.Next() * .16f;
            var basis = new Basis(Vector3.Up, yaw).Scaled(new Vector3(sc, sc, sc));
            xf.Add(new Transform3D(basis, new Vector3(x, y + .02f, z)));
            Color shirt;
            if (end != 0 && rng.Next() < .82f)
                shirt = (end < 0 ? HomeColour : AwayColour).Lightened(rng.Next() * .2f);
            else if (rng.Next() < .3f)
                shirt = (rng.Next() < .5f ? HomeColour : AwayColour).Darkened(rng.Next() * .2f);
            else shirt = neutral[rng.RangeInt(0, neutral.Length - 1)] * (.8f + rng.Next() * .3f);
            // rgb shirt, a = end slot (0 home, 1 side, 2 away) + seed - see crowd_figure.gdshader
            custom.Add(new Color(shirt.R, shirt.G, shirt.B, (end < 0 ? 0f : end > 0 ? 2f : 1f) + rng.Next() * .999f));
            if (flag != null && end != 0 && rng.Next() < .035f)
            {
                // a flag in the right hand: grip at the hand, pole up
                var hand = new Vector3(.24f, .55f, .12f) * sc;
                flagXf.Add(new Transform3D(new Basis(Vector3.Up, yaw), new Vector3(x, y, z) + new Basis(Vector3.Up, yaw) * hand));
                flagCustom.Add(new Color(rng.Next(), 0, end, 0));
            }
        }
        _crowdFigMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/crowd_figure.gdshader") };
        _crowdFigMat.SetShaderParameter("home", HomeColour);
        _crowdFigMat.SetShaderParameter("away", AwayColour);
        AddChild(Instanced("Crowd", seated, xf, null, custom, _crowdFigMat));
        if (flag != null && flagXf.Count > 0)
        {
            var flagMat = new ShaderMaterial { Shader = FlagShader() };
            flagMat.SetShaderParameter("home", HomeColour);
            flagMat.SetShaderParameter("away", AwayColour);
            AddChild(Instanced("CrowdFlags", flag, flagXf, null, flagCustom, flagMat));
        }
        CrowdShown = xf.Count;
    }

    private static MultiMeshInstance3D Instanced(string name, Godot.Mesh mesh, List<Transform3D> xf, List<Color>? cols,
                                                 List<Color> custom, Material mat)
    {
        var mm = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D, UseColors = cols != null, UseCustomData = true,
            Mesh = mesh, InstanceCount = xf.Count,
        };
        for (int k = 0; k < xf.Count; k++)
        {
            mm.SetInstanceTransform(k, xf[k]);
            if (cols != null) mm.SetInstanceColor(k, cols[k]);
            mm.SetInstanceCustomData(k, custom[k]);
        }
        return new MultiMeshInstance3D
        {
            Name = name, Multimesh = mm, MaterialOverride = mat,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.Off,
        };
    }

    private static Shader? _flagShader;
    private static Shader FlagShader()
    {
        if (_flagShader != null) return _flagShader;
        _flagShader = new Shader
        {
            Code = @"shader_type spatial;
render_mode cull_disabled, diffuse_lambert, specular_disabled;
uniform vec3 home : source_color; uniform vec3 away : source_color;
uniform float excite = 0.12;
varying float v_cloth; varying vec3 v_col; varying vec2 v_uv;
void vertex() {
	float seed = INSTANCE_CUSTOM.x;
	v_cloth = step(0.9, COLOR.r);
	// waved side to side from the grip, harder when the crowd is up; the cloth ripples along its length
	float a = sin(TIME * (2.0 + seed) + seed * 20.0) * (0.25 + 0.5 * excite);
	vec3 v = VERTEX;
	v.xy = vec2(v.x * cos(a) - v.y * sin(a), v.x * sin(a) + v.y * cos(a));
	v.z += v_cloth * sin(UV.x * 6.0 - TIME * 7.0 + seed * 9.0) * 0.08 * UV.x;
	VERTEX = v;
	v_col = INSTANCE_CUSTOM.z < 0.0 ? home : away;
	v_uv = UV;
}
void fragment() {
	vec3 c = mix(vec3(0.1), v_col, v_cloth);
	// a band of white across the cloth: club flags, not plain sheets
	c = mix(c, vec3(1.0), v_cloth * step(abs(v_uv.y - 0.5), 0.12));
	ALBEDO = c; ROUGHNESS = 0.9;
}",
        };
        return _flagShader;
    }

    /// <summary>Crowd mood each frame: excitement (goal), chanting ends, LED flash after a goal.</summary>
    private void UpdateFigureCrowd(float dt, float excite)
    {
        if (_crowdFigMat != null)
        {
            _crowdFigMat.SetShaderParameter("excite", excite);
            _crowdFigMat.SetShaderParameter("chant", .55f + .45f * MathF.Sin(Time.GetTicksMsec() / 9000f));
        }
        _goalFlash = MathF.Max(0f, _goalFlash - dt * .35f);
        _ledMat?.SetShaderParameter("flash", _goalFlash > 0f ? Math.Min(1f, _goalFlash) * (.6f + .4f * MathF.Sin(Time.GetTicksMsec() / 80f)) : 0f);
    }
}

public partial class Stadium
{
    /// <summary>"day", "dusk" or "night" (MatchOptions.Lighting; set before Build).</summary>
    public string Lighting = "day";
    private ShaderMaterial? _turfMat;
    public static readonly string[] MowPatterns = { "stripes", "checker", "diagonal", "rings", "wide_stripes" };

    /// <summary>Floodlight strength: they're on all match, but they carry a night game.</summary>
    private float FloodMul => Lighting == "night" ? 2.6f : Lighting == "dusk" ? 1.6f : 1f;

    /// <summary>Turf from Sprite Forge sforge.pitch (v11.33): each ground has its groundsman's mowing pattern.</summary>
    private MeshInstance3D? BuildTurf(int stadiumIndex)
    {
        string mow = MowPatterns[Math.Abs(stadiumIndex) % MowPatterns.Length];
        string path = $"res://Data/pitch/pitch_soccer_{mow}.png";
        if (!Godot.FileAccess.FileExists(path)) return null;
        var meta = ReadJson($"res://Data/pitch/pitch_soccer_{mow}.json");
        var ext = new Vector2(56.5f, 38f);
        if (meta is JsonElement m && m.TryGetProperty("extent", out var e)) ext = new Vector2(e[0].GetSingle(), e[1].GetSingle());
        _turfMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/turf.gdshader") };
        _turfMat.SetShaderParameter("turf", LoadPng(path));
        _turfMat.SetShaderParameter("extent", ext);
        return new MeshInstance3D
        {
            Name = "Pitch", Mesh = new PlaneMesh { Size = ext * 2f }, MaterialOverride = _turfMat,
            Position = new Vector3(0, LineY, 0),
        };
    }

    private void ApplyLighting(Godot.Environment env, ProceduralSkyMaterial sky)
    {
        if (Lighting == "dusk")
        {
            sky.SkyTopColor = new Color(.09f, .14f, .32f);
            sky.SkyHorizonColor = new Color(.80f, .55f, .40f);
            sky.GroundHorizonColor = new Color(.30f, .24f, .22f);
            env.AmbientLightEnergy = .5f;
            env.FogLightColor = new Color(.42f, .38f, .40f);
        }
        else if (Lighting == "night")
        {
            sky.SkyTopColor = new Color(.008f, .015f, .04f);
            sky.SkyHorizonColor = new Color(.05f, .08f, .15f);
            sky.GroundHorizonColor = new Color(.03f, .04f, .06f);
            sky.GroundBottomColor = new Color(.01f, .01f, .02f);
            // under floodlights the bowl is evenly lit: a neutral fill instead of the black night sky
            env.AmbientLightSource = Godot.Environment.AmbientSource.Color;
            env.AmbientLightColor = new Color(.62f, .65f, .72f);
            env.AmbientLightEnergy = .55f;
            env.FogLightColor = new Color(.08f, .1f, .16f);
            env.GlowEnabled = true;
            env.GlowIntensity = .5f;
            env.GlowBloom = .12f;
        }
    }
}
