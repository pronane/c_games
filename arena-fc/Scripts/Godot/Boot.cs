// Arena FC - entry point.
//   godot --path .                                   normal game (main menu)
//   godot --headless --path . -- --selftest          in-engine integration tests
//   godot --headless --path . -- --no-game           boot-only smoke test
//   godot --path . -- --match                       jump straight into a 5v5 match
//   godot --path . -- --editor                      jump straight into the character editor
//   godot --path . -- --rigshot                     close-up of one rig (debug)
//   godot --path . -- --screenshot                   save one rendered frame to user://screenshot.png
//   godot --path . -- --record DIR --frames N        dump N viewport frames as PNG (video capture)
//   godot --headless --path . -- --dump-rig         regenerate Data/rig_default.json for the web build
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Boot : Node3D
{
    private bool _shot;
    private int _frames;

    // Deterministic frame recorder used to produce real gameplay videos.
    // Launch with: --fixed-fps 24 ... -- --match --record /abs/path --frames 480
    private string? _recordDir;
    private int _recordMax;
    private int _recordCount;
    private bool _recording;

    public override void _Ready()
    {
        var args = OS.GetCmdlineUserArgs().Concat(OS.GetCmdlineArgs()).ToArray();
        bool Has(string a) => args.Any(x => x.Equals(a, StringComparison.OrdinalIgnoreCase));
        string? Value(string a)
        {
            for (int i = 0; i < args.Length; i++)
                if (args[i].Equals(a, StringComparison.OrdinalIgnoreCase))
                    return i + 1 < args.Length ? args[i + 1] : null;
            return null;
        }

        if (Has("--selftest")) { CallDeferred(nameof(RunSelfTest)); return; }
        if (Has("--no-game")) { GD.Print("ARENA_FC_HEADLESS_OK"); CallDeferred(nameof(QuitClean)); return; }
        if (Has("--dump-rig")) { DumpRig(); CallDeferred(nameof(QuitClean)); return; }

        if (Has("--rigshot"))
        {
            var env = new Godot.Environment { BackgroundMode = Godot.Environment.BGMode.Color, BackgroundColor = new Color(.08f, .12f, .15f), AmbientLightSource = Godot.Environment.AmbientSource.Color, AmbientLightColor = new Color(1, 1, 1), AmbientLightEnergy = 1f };
            AddChild(new WorldEnvironment { Environment = env });
            AddChild(new DirectionalLight3D { LightEnergy = 2f, RotationDegrees = new Vector3(-35, -35, 0) });
            AddChild(RigFactory.Create(new CharacterSpec { KitPrimary = "#d7263d", KitSecondary = "#ffffff", ShortsColor = "#14213d" }));
            var c = new Camera3D { Position = new Vector3(1.7f, 1.5f, 3.1f), Fov = 45 };
            c.LookAtFromPosition(c.Position, new Vector3(0, .95f, 0), Vector3.Up);
            AddChild(c);
            c.MakeCurrent();
            _shot = true;
            return;
        }

        if (Has("--match"))
        {
            var view = new MatchView();
            view.Init(new MatchOptions { TeamSize = 5, Seed = 2026, TimeSpeed = 15f }, null, () => GetTree().Quit());
            AddChild(view);
        }
        else if (Has("--editor"))
        {
            var ed = new CharacterEditor();
            ed.Init(Clubs.CreateRoster(0, 11));
            AddChild(ed);
        }
        else GameApp.Create(this);

        _shot = Has("--screenshot");
        var rec = Value("--record");
        if (!string.IsNullOrEmpty(rec))
        {
            _recordDir = Path.GetFullPath(rec);
            Directory.CreateDirectory(_recordDir);
            _recordMax = int.TryParse(Value("--frames"), out int n) ? Math.Clamp(n, 1, 20000) : 240;
            _recording = true;
            GD.Print($"ARENA_FC_RECORD_START dir={_recordDir} frames={_recordMax}");
        }
        GD.Print("ARENA_FC_BOOT_OK");
    }

    public override void _Process(double delta)
    {
        if (_recording && GetViewport()?.GetTexture() is Texture2D recTex)
        {
            string file = Path.Combine(_recordDir!, $"f{_recordCount:D5}.png");
            // Image is a refcounted native resource: release it every frame or
            // long deterministic captures slowly exhaust RAM on small machines.
            var recImg = recTex.GetImage();
            recImg.SavePng(file);
            recImg.Dispose();
            if (++_recordCount >= _recordMax)
            {
                _recording = false;
                GD.Print($"ARENA_FC_RECORD_DONE frames={_recordCount}");
                GetTree().Quit(0);
                return;
            }
        }

        if (!_shot) return;
        if (++_frames < 24) return;
        _shot = false;
        var tex = GetViewport().GetTexture();
        if (tex == null) { GD.Print("ARENA_FC_SCREENSHOT_SKIPPED (headless)"); GetTree().Quit(0); return; }
        string path = "user://screenshot.png";
        var img = tex.GetImage();
        var err = img.SavePng(path);
        GD.Print($"ARENA_FC_SCREENSHOT {ProjectSettings.GlobalizePath(path)} err={err} size={img.GetWidth()}x{img.GetHeight()}");
        img.Dispose();
        GetTree().Quit(0);
    }

    private void RunSelfTest() => SelfTest.Run(this);
    private void QuitClean() => GetTree().Quit(0);

    /// <summary>Writes the procedural rig as compact JSON so the GDScript-only
    /// Browser Edition can rebuild the identical skinned skeleton on the web.</summary>
    private void DumpRig()
    {
        var g = RigBuilder.Build(new CharacterSpec());
        float R(float v) => MathF.Round(v * 10000f) / 10000f;
        var pos = new List<float>(g.Positions.Length * 3);
        var nrm = new List<float>(g.Normals.Length * 3);
        var uv = new List<float>(g.Uvs.Length * 2);
        foreach (var v in g.Positions) { pos.Add(R(v.X)); pos.Add(R(v.Y)); pos.Add(R(v.Z)); }
        foreach (var v in g.Normals) { nrm.Add(R(v.X)); nrm.Add(R(v.Y)); nrm.Add(R(v.Z)); }
        foreach (var v in g.Uvs) { uv.Add(R(v.X)); uv.Add(R(v.Y)); }
        var bones = new List<object>();
        for (int i = 0; i < g.Bones.Length; i++)
        {
            var b = g.Bones[i];
            bones.Add(new Dictionary<string, object>
            {
                ["n"] = b.Name, ["p"] = b.Parent,
                ["h"] = new[] { R(b.Head.X), R(b.Head.Y), R(b.Head.Z) },
                ["t"] = new[] { R(b.Tail.X), R(b.Tail.Y), R(b.Tail.Z) },
            });
        }
        var payload = new Dictionary<string, object>
        {
            ["generator"] = "ArenaFC C# RigBuilder 1.0",
            ["bones"] = bones,
            ["pos"] = pos, ["nrm"] = nrm, ["uv"] = uv,
            ["bi"] = g.BoneIndices.Select(x => (object)x).ToList(),
            ["w"] = g.Weights.Select(x => (object)R(x)).ToList(),
            ["idx"] = g.Indices,
            ["mats"] = g.SurfaceMaterials,
            ["height"] = R(g.BoundsMax.Y),
        };
        string path = ProjectSettings.GlobalizePath("res://Data/rig_default.json");
        File.WriteAllText(path, JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = false }));
        GD.Print($"ARENA_FC_RIG_DUMP {path} bones={g.Bones.Length} verts={g.VertexCount} tris={g.TriangleCount}");
    }
}
