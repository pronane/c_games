// Arena FC - procedural stadium, goals, nets, crowd, lighting, ball, broadcast
// camera and the skeletal animation driver. No external art assets required.
using System;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class Stadium : Node3D
{
    public const float LineY = 0.012f;

    public void Build(bool fullCrowd = true)
    {
        Name = "Stadium";

        // --- Environment / sky / sun ---
        var skyMat = new ProceduralSkyMaterial
        {
            SkyTopColor = new Color(.045f, .12f, .27f),
            SkyHorizonColor = new Color(.30f, .42f, .56f),
            GroundBottomColor = new Color(.055f, .10f, .07f),
            GroundHorizonColor = new Color(.16f, .24f, .18f),
            SunAngleMax = 12f,
            SunCurve = .12f,
        };
        var env = new Godot.Environment
        {
            BackgroundMode = Godot.Environment.BGMode.Sky,
            Sky = new Sky { SkyMaterial = skyMat },
            AmbientLightSource = Godot.Environment.AmbientSource.Sky,
            AmbientLightColor = new Color(.55f, .62f, .72f),
            AmbientLightEnergy = .55f,
            TonemapMode = Godot.Environment.ToneMapper.Filmic,
            TonemapExposure = 1.12f,
            GlowEnabled = true,
            GlowIntensity = .22f,
            GlowBloom = .08f,
            FogEnabled = true,
            FogLightColor = new Color(.36f, .45f, .55f),
            FogDensity = .0012f,
        };
        var world = new WorldEnvironment { Name = "WorldEnvironment", Environment = env };
        AddChild(world);

        var sun = new DirectionalLight3D
        {
            Name = "Sun",
            LightColor = new Color(1f, .96f, .88f),
            LightEnergy = 1.45f,
            RotationDegrees = new Vector3(-52f, -38f, 0),
            ShadowEnabled = true,
            DirectionalShadowMaxDistance = 220f,
        };
        AddChild(sun);

        // --- Pitch + outer apron ---
        var apron = Mesh(new BoxMesh { Size = new Vector3(Mx.PitchLength + 34f, .3f, Mx.PitchWidth + 30f) },
            Mat(new Color(.055f, .16f, .085f)), new Vector3(0, -.18f, 0), "Apron");
        AddChild(apron);

        var pitchShader = GD.Load<Shader>("res://Shaders/pitch.gdshader");
        var pitchMat = new ShaderMaterial { Shader = pitchShader };
        var pitch = new MeshInstance3D
        {
            Name = "Pitch",
            Mesh = new PlaneMesh { Size = new Vector2(Mx.PitchLength, Mx.PitchWidth) },
            MaterialOverride = pitchMat,
            Position = new Vector3(0, LineY, 0),
        };
        AddChild(pitch);

        // --- Goals ---
        foreach (int sign in new[] { -1, 1 })
        {
            var goal = new Node3D { Name = sign < 0 ? "GoalLeft" : "GoalRight" };
            AddChild(goal);
            var white = Mat(new Color(.95f, .97f, 1f), .35f, .15f);
            foreach (float z in new[] { -Mx.GoalHalfWidth, Mx.GoalHalfWidth })
                goal.AddChild(Mesh(new CylinderMesh { TopRadius = .06f, BottomRadius = .06f, Height = Mx.GoalHeight, RadialSegments = 10 },
                    white, new Vector3(sign * Mx.HalfLength, Mx.GoalHeight * .5f, z), "Post"));
            var bar = Mesh(new CylinderMesh { TopRadius = .06f, BottomRadius = .06f, Height = Mx.GoalHalfWidth * 2f, RadialSegments = 10 },
                white, new Vector3(sign * Mx.HalfLength, Mx.GoalHeight, 0), "Crossbar");
            bar.RotationDegrees = new Vector3(90, 0, 0);
            goal.AddChild(bar);

            var netMat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/net.gdshader") };
            float backX = sign * (Mx.HalfLength + 2.0f);
            var back = Mesh(new QuadMesh { Size = new Vector2(Mx.GoalHalfWidth * 2f, Mx.GoalHeight) },
                netMat, new Vector3(backX, Mx.GoalHeight * .5f, 0), "NetBack");
            back.RotationDegrees = new Vector3(0, 90, 0);
            goal.AddChild(back);
            foreach (float z in new[] { -Mx.GoalHalfWidth, Mx.GoalHalfWidth })
            {
                var side = Mesh(new QuadMesh { Size = new Vector2(2f, Mx.GoalHeight) }, netMat,
                    new Vector3(sign * (Mx.HalfLength + 1f), Mx.GoalHeight * .5f, z), "NetSide");
                goal.AddChild(side);
            }
            var top = Mesh(new QuadMesh { Size = new Vector2(Mx.GoalHalfWidth * 2f, 2f) }, netMat,
                new Vector3(sign * (Mx.HalfLength + 1f), Mx.GoalHeight, 0), "NetTop");
            top.RotationDegrees = new Vector3(90, 0, 0);
            goal.AddChild(top);
        }

        // --- Stands + crowd ---
        var concrete = Mat(new Color(.16f, .18f, .22f));
        var seat = Mat(new Color(.11f, .14f, .20f));
        int rows = 9;
        for (int side = 0; side < 4; side++)
        {
            bool alongX = side < 2;
            float s = side % 2 == 0 ? -1f : 1f;
            for (int r = 0; r < rows; r++)
            {
                float dist = (alongX ? Mx.HalfWidth + 8f : Mx.HalfLength + 8f) + r * 2.1f;
                float height = .8f + r * 1.25f;
                Vector3 pos = alongX ? new Vector3(0, height * .5f - .35f, s * dist)
                                     : new Vector3(s * dist, height * .5f - .35f, 0);
                Vector3 size = alongX ? new Vector3(Mx.PitchLength + 42f + r * 3f, height, 2.1f)
                                      : new Vector3(2.1f, height, Mx.PitchWidth + 42f + r * 3f);
                AddChild(Mesh(new BoxMesh { Size = size }, r % 2 == 0 ? concrete : seat, pos, $"Stand{side}_{r}"));
            }
        }
        if (fullCrowd) AddChild(BuildCrowd(2400));

        // --- Advertising boards ---
        string[] boards = { "ARENA FC", "FAIR PLAY", "GODOT 4.7", "ANY DEVICE", "EST. 2026", "MATCH DAY", "GLB EXPORT", "OPEN RIGS" };
        for (int i = 0; i < 8; i++)
        {
            bool alongX = true;
            float t = i / 7f;
            var label = new Label3D
            {
                Text = boards[i % boards.Length],
                FontSize = 56,
                PixelSize = .016f,
                Modulate = new Color(.95f, .95f, .95f),
                OutlineSize = 0,
                DoubleSided = true,
            };
            if (alongX) { label.Position = new Vector3(Mx.Lerp(-Mx.HalfLength, Mx.HalfLength, t), .9f, -Mx.HalfWidth - 1.1f); }
            else
            {
                label.Position = new Vector3(Mx.HalfLength + 1.1f, .9f, Mx.Lerp(-Mx.HalfWidth, Mx.HalfWidth, t));
                label.RotationDegrees = new Vector3(0, -90, 0);
            }
            AddChild(label);
        }

        // --- Floodlights ---
        for (int i = 0; i < 4; i++)
        {
            float x = (i < 2 ? -1 : 1) * (Mx.HalfLength + 18f);
            float z = (i % 2 == 0 ? -1 : 1) * (Mx.HalfWidth + 14f);
            AddChild(Mesh(new CylinderMesh { TopRadius = .35f, BottomRadius = .6f, Height = 32f, RadialSegments = 8 },
                concrete, new Vector3(x, 16f, z), "FloodPole"));
            var panel = Mesh(new BoxMesh { Size = new Vector3(6f, 3f, .5f) },
                Mat(new Color(1f, .97f, .85f), .4f, 0f, new Color(1.6f, 1.5f, 1.2f)),
                new Vector3(x, 33f, z), "FloodPanel");
            panel.RotationDegrees = new Vector3(0, x > 0 ? -90 : 90, 0);
            AddChild(panel);
            var lamp = new OmniLight3D
            {
                LightColor = new Color(1f, .95f, .86f),
                LightEnergy = 2.2f,
                OmniRange = 95f,
                Position = new Vector3(x, 31f, z),
            };
            AddChild(lamp);
        }
    }

    private Node3D BuildCrowd(int count)
    {
        var mm = new MultiMesh
        {
            TransformFormat = MultiMesh.TransformFormatEnum.Transform3D,
            UseColors = true,
            Mesh = new BoxMesh { Size = new Vector3(.38f, .55f, .32f) },
            InstanceCount = count,
        };
        var rng = new Rng(9182);
        Color[] palette =
        {
            new(.85f,.15f,.2f), new(.12f,.3f,.75f), new(.95f,.95f,.9f), new(.15f,.6f,.35f),
            new(.95f,.7f,.15f), new(.3f,.3f,.35f), new(.6f,.2f,.6f), new(.1f,.1f,.12f),
        };
        for (int i = 0; i < count; i++)
        {
            int side = i % 4;
            bool alongX = side < 2;
            float s = side % 2 == 0 ? -1f : 1f;
            int row = rng.RangeInt(0, 8);
            float spread = alongX ? Mx.PitchLength + 40f : Mx.PitchWidth + 40f;
            float u = rng.Range(-.5f, .5f) * spread;
            float dist = (alongX ? Mx.HalfWidth + 8f : Mx.HalfLength + 8f) + row * 2.1f;
            float y = .8f + row * 1.25f + .35f;
            Vector3 p = alongX ? new Vector3(u, y, s * dist) : new Vector3(s * dist, y, u);
            mm.SetInstanceTransform(i, new Transform3D(Basis.Identity, p));
            mm.SetInstanceColor(i, palette[rng.RangeInt(0, palette.Length - 1)] * rng.Range(.72f, 1.15f));
        }
        var crowd = new MultiMeshInstance3D { Name = "Crowd", Multimesh = mm, MaterialOverride = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/crowd.gdshader") } };
        return crowd;
    }

    public static StandardMaterial3D Mat(Color color, float roughness = .8f, float metallic = 0f, Color? emission = null)
    {
        var m = new StandardMaterial3D { AlbedoColor = color, Roughness = roughness, Metallic = metallic };
        if (emission.HasValue) { m.EmissionEnabled = true; m.Emission = emission.Value; m.EmissionEnergyMultiplier = 1.2f; }
        return m;
    }

    public static MeshInstance3D Mesh(Godot.Mesh mesh, Material mat, Vector3 pos, string name)
        => new() { Name = name, Mesh = mesh, MaterialOverride = mat, Position = pos, CastShadow = GeometryInstance3D.ShadowCastingSetting.On };
}

public static class BallFactory
{
    public static MeshInstance3D Create()
    {
        var mesh = new SphereMesh { Radius = Mx.BallRadius, Height = Mx.BallRadius * 2f, RadialSegments = 24, Rings = 16 };
        var mat = new ShaderMaterial { Shader = GD.Load<Shader>("res://Shaders/ball.gdshader") };
        return new MeshInstance3D
        {
            Name = "Ball",
            Mesh = mesh,
            MaterialOverride = mat,
            CastShadow = GeometryInstance3D.ShadowCastingSetting.On,
        };
    }
}

public partial class BroadcastCamera : Camera3D
{
    public int Mode;
    private Vector3 _pos, _look;
    private bool _init;

    public void Cycle() { Mode = (Mode + 1) % 3; _init = false; }
    public string ModeName => Mode switch { 0 => "Broadcast", 1 => "Player cam", _ => "Tactical" };

    public void UpdateCamera(Vector3 ball, Vector3 player, Vector3 facing, float dt)
    {
        Vector3 target, look;
        float fov = 55f;
        switch (Mode)
        {
            case 1:
                var fwd = MxToG(Mx.Norm(Gx(facing)));
                target = player - fwd * 7.5f + new Vector3(0, 3.1f, 0);
                look = player + fwd * 9f + new Vector3(0, 1.2f, 0);
                fov = 68f;
                break;
            case 2:
                target = new Vector3(ball.X * .45f, 88f, ball.Z * .25f + .01f);
                look = new Vector3(ball.X * .6f, 0, ball.Z * .5f);
                fov = 58f;
                break;
            default:
                // Classic broadcast angle: ~50 m of pitch in frame at 720p.
                target = new Vector3(ball.X - 6f, 28f + Mathf.Abs(ball.Z) * .05f, ball.Z + 46f);
                look = new Vector3(ball.X, 1.2f, ball.Z);
                fov = 50f + Mathf.Clamp(Mathf.Abs(ball.Z) * .05f, 0f, 5f);
                break;
        }
        if (!_init) { _pos = target; _look = look; _init = true; }
        float k = 1f - Mathf.Exp(-dt * (Mode == 1 ? 6f : 3.2f));
        _pos = _pos.Lerp(target, k);
        _look = _look.Lerp(look, k);
        Position = _pos;
        LookAtFromPosition(_pos, _look, Vector3.Up);
        Fov = Mathf.Lerp(Fov, fov, k);
    }

    private static Vector3 MxToG(System.Numerics.Vector3 v) => new(v.X, v.Y, v.Z);
    private static System.Numerics.Vector3 Gx(Vector3 v) => new(v.X, v.Y, v.Z);
}

/// <summary>Procedural skeletal animation: writes quaternions straight into Skeleton3D bone poses.</summary>
public static class RigAnimator
{
    public static void Pose(CharacterRig rig, PlayerState p, float dt, float time, System.Numerics.Vector3 ballPos)
    {
        if (rig.Skeleton == null) return;
        float speed = Mx.Flat(p.Vel).Length();
        float amp = Math.Clamp(speed / 6f, 0f, 1f);
        float phase = p.AnimPhase * 1.65f;
        float swing = MathF.Sin(phase) * amp * .72f;
        float swing2 = MathF.Sin(phase + MathF.PI) * amp * .72f;
        float kneeL = MathF.Max(0f, -MathF.Sin(phase)) * amp * .85f;
        float kneeR = MathF.Max(0f, -MathF.Sin(phase + MathF.PI)) * amp * .85f;

        Set(rig, "LThigh", swing, 0, 0);
        Set(rig, "RThigh", swing2, 0, 0);
        Set(rig, "LShin", kneeL, 0, 0);
        Set(rig, "RShin", kneeR, 0, 0);
        Set(rig, "LUpperArm", -swing * .65f, 0, -.16f - amp * .16f);
        Set(rig, "RUpperArm", -swing2 * .65f, 0, .16f + amp * .16f);
        Set(rig, "LForearm", -.25f - amp * .35f, 0, 0);
        Set(rig, "RForearm", -.25f - amp * .35f, 0, 0);
        Set(rig, "Chest", amp * .07f, MathF.Sin(phase) * amp * .06f, 0);
        Set(rig, "Head", 0, 0, 0);
        Set(rig, "LFoot", -swing * .25f, 0, 0);
        Set(rig, "RFoot", -swing2 * .25f, 0, 0);

        if (p.IsKeeper)
        {
            Set(rig, "LUpperArm", -.25f, 0, -1.15f);
            Set(rig, "RUpperArm", -.25f, 0, 1.15f);
            Set(rig, "LForearm", -.3f, 0, -.2f);
            Set(rig, "RForearm", -.3f, 0, .2f);
        }
        if (p.Action == "kick" && p.ActionTimer > 0f)
        {
            float k = 1f - p.ActionTimer / .4f;
            float kick = MathF.Sin(k * MathF.PI) * 1.25f;
            Set(rig, "RThigh", -kick, 0, 0);
            Set(rig, "RShin", MathF.Max(0f, .4f - kick) * .8f, 0, 0);
            Set(rig, "Chest", -kick * .12f, 0, 0);
        }
        else if (p.Action == "tackle" && p.ActionTimer > 0f)
        {
            float k = 1f - p.ActionTimer / .45f;
            Set(rig, "Chest", 0, 0, MathF.Sin(k * MathF.PI) * .85f);
            Set(rig, "LThigh", -1.1f, 0, 0);
            Set(rig, "RThigh", .5f, 0, 0);
        }
        else if (p.Action == "celebrate")
        {
            float w = MathF.Sin(time * 7f);
            Set(rig, "LUpperArm", 0, 0, -2.4f - w * .2f);
            Set(rig, "RUpperArm", 0, 0, 2.4f + w * .2f);
            Set(rig, "LForearm", 0, 0, -.4f);
            Set(rig, "RHand", 0, 0, .4f);
        }
        else if (p.Action == "dive" && p.ActionTimer > 0f)
        {
            float k = 1f - p.ActionTimer / .65f;
            Set(rig, "Chest", 0, 0, MathF.Sin(k * MathF.PI) * 1.2f);
            Set(rig, "LThigh", -.7f, 0, 0);
            Set(rig, "RThigh", .4f, 0, 0);
        }
        if (rig.EditorMode) return;

        // small vertical bob so sprinting reads as weight-bearing
        float bob = MathF.Abs(MathF.Sin(phase)) * amp * .035f;
        rig.Skeleton.Position = new Vector3(0, bob, 0);
    }

    private static void Set(CharacterRig rig, string bone, float x, float y, float z)
    {
        if (!rig.BoneIndex.TryGetValue(bone, out int idx)) return;
        var o = rig.Spec.GetBoneRotation(bone);
        var over = Quaternion.FromEuler(new Vector3(Mathf.DegToRad(o[0]), Mathf.DegToRad(o[1]), Mathf.DegToRad(o[2])));
        var anim = Quaternion.FromEuler(new Vector3(x, y, z));
        rig.Skeleton.SetBonePoseRotation(idx, over * anim);
    }

    /// <summary>Editor preview animation (idle / run / kick / celebrate) with no match state.</summary>
    public static void Preview(CharacterRig rig, string clip, float time)
    {
        var dummy = new PlayerState { Action = clip, AnimPhase = time * 3.2f, ActionTimer = 999f };
        dummy.Vel = clip == "run" ? new System.Numerics.Vector3(5, 0, 0) : System.Numerics.Vector3.Zero;
        if (clip == "kick") dummy.ActionTimer = .4f - (time % .4f);
        Pose(rig, dummy, 1f / 60f, time, System.Numerics.Vector3.Zero);
        rig.Skeleton.Position = Vector3.Zero;
    }
}
