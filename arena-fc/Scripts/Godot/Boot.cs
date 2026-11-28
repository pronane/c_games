// Arena FC - entry point.
//   godot --path .                                   normal game (main menu)
//   godot --headless --path . -- --selftest          in-engine integration tests
//   godot --headless --path . -- --no-game           boot-only smoke test
//   godot --path . -- --match                       jump straight into a 5v5 match
//   godot --path . -- --editor                      jump straight into the character editor
//   godot --path . -- --rigshot                     close-up of one rig (debug)
//   godot --path . -- --screenshot                   save one rendered frame to user://screenshot.png
//   godot --path . -- --record DIR --frames N        dump N viewport frames as PNG (video capture)
//   godot --path . -- --arena-profile-frames N       profile a live 5v5 render after warm-up
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
    private MatchView? _view;
    private int _offShot = -1;
    private Camera3D? _offCam;
    private int _touchShot = -1;
    private Camera3D? _touchCam;
    private int _shotFrame = 24;
    private int _frames;

    // Deterministic frame recorder used to produce real gameplay videos.
    // Launch with: --fixed-fps 24 ... -- --match --record /abs/path --frames 480
    private string? _recordDir;
    private int _recordMax;
    private int _recordCount;
    private bool _recording;

    private bool _profiling;
    private int _profileWarmupFrames;
    private int _profileFrameTarget;
    private readonly List<double> _profileFrameMs = new();
    private double _profilePhysicsMs, _profileDrawCalls, _profilePrimitives;

    public override void _Ready()
    {
        // Graphics tier first: a machine that can't carry Forward+ restarts on the GL renderer right here.
        if (RenderProfile.EnsureRenderer()) return;
        var args = OS.GetCmdlineUserArgs().Concat(OS.GetCmdlineArgs()).ToArray();
        bool Has(string a) => args.Any(x => x.Equals(a, StringComparison.OrdinalIgnoreCase));
        int ArgInt(string name, int fallback)
        {
            int i = Array.FindIndex(args, x => x.Equals(name, StringComparison.OrdinalIgnoreCase));
            return i >= 0 && i + 1 < args.Length && int.TryParse(args[i + 1], out int v) ? v : fallback;
        }
        string? Value(string a)
        {
            for (int i = 0; i < args.Length; i++)
                if (args[i].Equals(a, StringComparison.OrdinalIgnoreCase))
                    return i + 1 < args.Length ? args[i + 1] : null;
            return null;
        }

        if (Has("--selftest")) { CallDeferred(nameof(RunSelfTest)); return; }
        if (Has("--render-profile"))
        {
            // QA: --render-profile ultra|high|performance (this run only; Forward+ tiers need --rendering-method forward_plus)
            RenderProfile.ForceTier(Value("--render-profile") ?? "ultra");
        }
        if (Has("--no-game")) { GD.Print("ARENA_FC_HEADLESS_OK"); CallDeferred(nameof(QuitClean)); return; }
        if (Has("--dump-rig")) { DumpRig(); CallDeferred(nameof(QuitClean)); return; }

        if (Has("--rigshot"))
        {
            // --rigshot [--rigshot-club N] [--rigshot-player K] [--rigshot-back] [--rigshot-far]
            // close-up of one squad player in his club kit (kit / boots / face QA).
            var env = new Godot.Environment { BackgroundMode = Godot.Environment.BGMode.Color, BackgroundColor = new Color(.08f, .12f, .15f), AmbientLightSource = Godot.Environment.AmbientSource.Color, AmbientLightColor = new Color(1, 1, 1), AmbientLightEnergy = 1f, TonemapMode = Godot.Environment.ToneMapper.Aces };
            AddChild(new WorldEnvironment { Environment = env });
            AddChild(new DirectionalLight3D { LightEnergy = 2f, RotationDegrees = new Vector3(-35, -35, 0) });
            AddChild(new DirectionalLight3D { LightEnergy = .8f, RotationDegrees = new Vector3(-25, 145, 0) });
            var spec = new CharacterSpec { KitPrimary = "#d7263d", KitSecondary = "#ffffff", ShortsColor = "#14213d" };
            if (Has("--rigshot-club"))
            {
                var squad = Clubs.CreateRoster(ArgInt("--rigshot-club", 0), 11);
                spec = squad[Math.Clamp(ArgInt("--rigshot-player", 9), 0, squad.Count - 1)];
            }
            if (Has("--rigshot-lineup"))
            {
                // six of the squad in a row: faces, skin tones, builds (identity QA)
                var squad = Clubs.CreateRoster(ArgInt("--rigshot-club", 0), 11);
                for (int k = 0; k < 6; k++)
                {
                    var r = RigFactory.Create(squad[1 + k]);
                    r.Position = new Vector3(-2.5f + k * 1.0f, 0, 0);
                    AddChild(r);
                }
                var lc = new Camera3D { Fov = 40, Position = new Vector3(0, 1.45f, 5.2f) };
                lc.LookAtFromPosition(lc.Position, new Vector3(0, 1.0f, 0), Vector3.Up);
                AddChild(lc);
                lc.MakeCurrent();
                _shot = true;
                return;
            }
            AddChild(RigFactory.Create(spec));
            bool back = Has("--rigshot-back"), far = Has("--rigshot-far");
            float d = far ? 4.2f : Has("--rigshot-face") ? .75f : 2.3f;
            var c = new Camera3D { Position = new Vector3(back ? -.9f : .9f, 1.25f, back ? -d : d), Fov = 45 };
            // the GLB player is scaled to the spec's height: the face sits at ~93% of it
            float faceY = spec.Height * .925f;
            if (Has("--rigshot-face")) c.Position = new Vector3(back ? -.25f : .25f, faceY + .03f, back ? -d : d);
            c.LookAtFromPosition(c.Position, new Vector3(0, Has("--rigshot-face") ? faceY : .95f, 0), Vector3.Up);
            AddChild(c);
            c.MakeCurrent();
            _shot = true;
            return;
        }

        _profiling = Has("--arena-profile-frames");
        if (_profiling)
        {
            _profileFrameTarget = int.TryParse(Value("--arena-profile-frames"), out int n)
                ? Math.Clamp(n, 60, 3600) : 300;
            _profileWarmupFrames = 60;
        }

        if (Has("--skill"))
        {
            // Direct boot into one skill game (dev / QA): --skill shooting|passing|dribbling|crossing|freekicks
            var game = Enum.TryParse<SkillGame>(Value("--skill") ?? "Shooting", true, out var g) ? g : SkillGame.Shooting;
            var view = new MatchView();
            view.Init(new MatchOptions { TeamSize = 11, Seed = 2026, TimeSpeed = 15f, Mode = MatchEngine.ModeSkill,
                SkillGame = game, Fouls = false, Offside = false }, null, () => GetTree().Quit());
            AddChild(view);
        }
        else if (Has("--training") || Has("--shootout") || Has("--practice"))
        {
            // Direct boot into a mode (dev / QA): same engine paths as the menu.
            var view = new MatchView();
            view.Init(new MatchOptions { TeamSize = 11, Seed = 2026, TimeSpeed = 15f,
                Mode = Has("--shootout") ? MatchEngine.ModeShootout : MatchEngine.ModeTraining,
                Fouls = Has("--shootout"), Offside = Has("--shootout") }, null, () => GetTree().Quit());
            AddChild(view);
        }
        else if (Has("--match") || _profiling)
        {
            var view = new MatchView();
            // --size N (5/7/11) and --seed N for QA runs; defaults unchanged.
            int size = ArgInt("--size", 5); if (size != 7 && size != 11) size = 5;
            // --weather rain|windy|snow|fog for QA of the weather visuals/physics.
            var (wx, wind) = Presentation.WeatherFor(System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(Value("--weather") ?? "clear"));
            view.Init(new MatchOptions { TeamSize = size, Seed = ArgInt("--seed", 2026), TimeSpeed = 15f, Weather = wx, WindSpeed = wind,
                Lighting = (Value("--light") ?? "day").ToLowerInvariant() }, null, () => GetTree().Quit());
            AddChild(view);
            _view = view;
            // --officials-shot K: a QA camera that follows official K (0 ref, 1/2 assistants, 3 fourth)
            if (Has("--officials-shot"))
            {
                _offShot = Math.Clamp(ArgInt("--officials-shot", 1), 0, 3);
                _offCam = new Camera3D { Fov = 40, Far = 400f };
                AddChild(_offCam);
            }
            // --touchline-shot K: QA cameras on the touchline (0 home dugout, 1 photographers at a goal,
            // 2 corner flag, 3 a goal bulging the net)
            if (Has("--touchline-shot"))
            {
                _touchShot = Math.Clamp(ArgInt("--touchline-shot", 0), 0, 3);
                _touchCam = new Camera3D { Fov = 42, Far = 400f };
                AddChild(_touchCam);
            }
            // --camera N: start on a given broadcast camera (QA captures of close-ups / officials)
            if (Has("--camera")) view.Cam.Mode = Math.Clamp(ArgInt("--camera", 0), 0, BroadcastCamera.ModeCount - 1);
        }
        else if (Has("--editor"))
        {
            var ed = new CharacterEditor();
            ed.Init(Clubs.CreateRoster(0, 11));
            AddChild(ed);
        }
        else if (RenderProfile.NeedsBenchmark(OS.GetCmdlineUserArgs()))
        {
            // first launch on Auto: measure this machine on a real match, then on to the menu (or restart on GL)
            var bench = new GraphicsBenchmark();
            AddChild(bench);
            bench.Done = () => { bench.QueueFree(); GameApp.Create(this); };
        }
        else GameApp.Create(this);

        _shot = Has("--screenshot");
        // --shot-frame N: take the screenshot N rendered frames in (default 24)
        _shotFrame = Math.Max(2, ArgInt("--shot-frame", 24));
        var rec = Value("--record");
        if (!string.IsNullOrEmpty(rec))
        {
            _recordDir = Path.GetFullPath(rec);
            Directory.CreateDirectory(_recordDir);
            _recordMax = int.TryParse(Value("--frames"), out int n) ? Math.Clamp(n, 1, 20000) : 240;
            _recording = true;
            GD.Print($"ARENA_FC_RECORD_START dir={_recordDir} frames={_recordMax}");
        }
        if (_profiling)
            GD.Print($"ARENA_FC_PROFILE_START renderer={RenderingServer.GetCurrentRenderingMethod()} " +
                     $"driver={RenderingServer.GetCurrentRenderingDriverName()} " +
                     $"adapter={RenderingServer.GetVideoAdapterName()} " +
                     $"warmup={_profileWarmupFrames} frames={_profileFrameTarget}");
        GD.Print("ARENA_FC_RENDER " + RenderProfile.Describe());
        GD.Print("ARENA_FC_BOOT_OK");
    }

    public override void _Process(double delta)
    {
        if (_profiling && ProfileFrame(delta)) return;

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

        if (_offCam != null && _view?.Officials != null)
        {
            var r = _view.Officials.Rigs[_offShot];
            var f = new Vector3(Mathf.Sin(r.Rotation.Y), 0, Mathf.Cos(r.Rotation.Y));
            _offCam.Position = r.GlobalPosition + f * 4.2f + new Vector3(1.2f, 1.5f, 0);
            _offCam.LookAt(r.GlobalPosition + new Vector3(0, 1.0f, 0), Vector3.Up);
            _offCam.MakeCurrent();
        }

        if (_touchCam != null && _view != null)
        {
            float hl = Mx.HalfLength, hw = Mx.HalfWidth;
            var stadium = _view.GetNodeOrNull<Stadium>("Stadium");
            (Vector3 eye, Vector3 at) = _touchShot switch
            {
                0 => (new Vector3(-6.5f, 1.7f, -hw - 0.6f), new Vector3(-9.5f, .7f, -hw - 3.9f)),
                1 => (new Vector3(hl - 9f, 1.9f, 10.5f), new Vector3(hl + 2f, .7f, 5f)),
                2 => (new Vector3(hl - 3.2f, 1.3f, hw - 2.6f), new Vector3(hl, .9f, hw)),
                _ => (new Vector3(hl + 5.5f, 1.8f, 6.5f), new Vector3(hl + 1.2f, 1.1f, 0f)),
            };
            _touchCam.Position = eye;
            _touchCam.LookAt(at, Vector3.Up);
            _touchCam.MakeCurrent();
            if (_touchShot == 3 && _frames == Math.Max(1, _shotFrame - 4))
                stadium?.NetImpact(new Vector3(hl + .4f, 1.3f, .8f), new Vector3(26f, 1.5f, 1f));
        }

        if (!_shot) return;
        if (++_frames < _shotFrame) return;
        _shot = false;
        var tex = GetViewport().GetTexture();
        if (tex == null) { GD.Print("ARENA_FC_SCREENSHOT_SKIPPED (headless)"); GetTree().Quit(0); return; }
        // --shot-out PATH: where to save it (default user://screenshot.png)
        var ua = OS.GetCmdlineUserArgs();
        int so = Array.IndexOf(ua, "--shot-out");
        string path = so >= 0 && so + 1 < ua.Length ? ua[so + 1] : "user://screenshot.png";
        var img = tex.GetImage();
        var err = img.SavePng(path);
        GD.Print($"ARENA_FC_SCREENSHOT {ProjectSettings.GlobalizePath(path)} err={err} size={img.GetWidth()}x{img.GetHeight()}");
        if (GraphicsReport.PathFromArgs() is string gr) GraphicsReport.Write(gr, GetViewport(), img);
        img.Dispose();
        GetTree().Quit(0);
    }

    private bool ProfileFrame(double delta)
    {
        if (_profileWarmupFrames > 0)
        {
            _profileWarmupFrames--;
            return false;
        }

        _profileFrameMs.Add(delta * 1000.0);
        _profilePhysicsMs += Performance.GetMonitor(Performance.Monitor.TimePhysicsProcess) * 1000.0;
        _profileDrawCalls += Performance.GetMonitor(Performance.Monitor.RenderTotalDrawCallsInFrame);
        _profilePrimitives += Performance.GetMonitor(Performance.Monitor.RenderTotalPrimitivesInFrame);
        if (_profileFrameMs.Count < _profileFrameTarget) return false;

        _profiling = false;
        var sorted = _profileFrameMs.OrderBy(x => x).ToArray();
        double Percentile(double p) => sorted[Math.Clamp((int)Math.Ceiling(p * sorted.Length) - 1, 0, sorted.Length - 1)];
        double avgFrameMs = _profileFrameMs.Average();
        GD.Print($"ARENA_FC_PROFILE frames={sorted.Length} avg_fps={1000.0 / avgFrameMs:F1} " +
                 $"avg_frame_ms={avgFrameMs:F2} p95_frame_ms={Percentile(.95):F2} p99_frame_ms={Percentile(.99):F2} " +
                 $"avg_physics_ms={_profilePhysicsMs / sorted.Length:F2} " +
                 $"avg_draw_calls={_profileDrawCalls / sorted.Length:F1} " +
                 $"avg_primitives={_profilePrimitives / sorted.Length:F0}");
        GetTree().Quit(0);
        return true;
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
