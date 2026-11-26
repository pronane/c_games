using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using ArenaFC.Core;
using ArenaFC.Core.Animation;
using Godot;
using NVector3 = System.Numerics.Vector3;

namespace ArenaFC.GodotGame;

/// <summary>
/// Deterministic production animation evidence runner. Loads the committed GLB
/// through RigFactory/SoccerClipRig, runs it on translated/rotated flat and
/// sloped collision surfaces, and emits measurable evidence for CI.
/// </summary>
public partial class RuntimeEvidenceRunner : Node3D
{
    private const float Dt = 1f / 60f;

    public override async void _Ready()
    {
        try
        {
            await RunEvidence();
        }
        catch (Exception ex)
        {
            GD.PrintErr($"[RuntimeEvidence] FAILED: {ex}");
            GetTree().Quit(1);
        }
    }

    private async Task RunEvidence()
    {
        string output = System.Environment.GetEnvironmentVariable("ARENA_FC_EVIDENCE_DIR");
        if (string.IsNullOrWhiteSpace(output)) output = "/tmp/arena-runtime-evidence";
        Directory.CreateDirectory(output);

        var environment = new Godot.Environment
        {
            BackgroundMode = Godot.Environment.BGMode.Color,
            BackgroundColor = new Color("#7890a8"),
            AmbientLightSource = Godot.Environment.AmbientSource.Color,
            AmbientLightColor = new Color(.78f, .81f, .88f),
            AmbientLightEnergy = .8f
        };
        AddChild(new WorldEnvironment { Environment = environment });
        AddChild(new DirectionalLight3D
        {
            RotationDegrees = new Vector3(-42, -28, 0),
            LightEnergy = 1.25f
        });
        var camera = new Camera3D { Position = new Vector3(0, 2.0f, 8.0f), Fov = 34f };
        AddChild(camera);
        camera.LookAt(new Vector3(0, 1.0f, 0));
        camera.MakeCurrent();

        AddGround(-2f, 0f, .1f);
        // Raise the ramp's centre so its left edge meets the flat surface at x=0.
        AddGround(2f, .08f, .26f);

        var spec = new CharacterSpec
        {
            Name = "Runtime Evidence",
            DisplayName = "RUNTIME",
            Number = 99,
            Role = Role.Midfielder,
            Height = 1.82f,
            Pace = .85f
        };
        var rig = RigFactory.Create(spec);
        AddChild(rig);
        if (rig.Soccer == null || !SoccerClipRig.Available)
            throw new InvalidOperationException("Production SoccerClipRig/GLB was not loaded; refusing a procedural fallback capture.");
        if (rig.Soccer.Skel == null)
            throw new InvalidOperationException("Production rig has no Skeleton3D.");
        var missingFootBones = new List<string>();
        foreach (var side in new[] { "L", "R" })
        foreach (var bone in new[] { "thigh", "shin", "foot" })
            if (SoccerClipRig.FindBoneLoose(rig.Soccer.Skel, $"{bone}_{side}") < 0)
                missingFootBones.Add($"{bone}_{side}");
        if (missingFootBones.Count > 0)
        {
            var actualBones = Enumerable.Range(0, rig.Soccer.Skel.GetBoneCount())
                .Select(i => rig.Soccer.Skel.GetBoneName(i));
            throw new InvalidOperationException(
                $"Production skeleton is missing grounding bones: {string.Join(", ", missingFootBones)}. " +
                $"Available bones: {string.Join(", ", actualBones)}");
        }
        if (!rig.Soccer.HasFootIkBones)
            throw new InvalidOperationException(
                "Production skeleton bones were found by validation but were not cached by the runtime foot-IK solver.");

        var metrics = new AnimationMetrics();
        rig.Soccer.AnimMetrics = metrics;
        var motion = new MotionState
        {
            CurrentClipId = "soccer_run",
            LastIntent = PlayerIntent.Sprint,
            FootPlantedLeft = true,
            PlantWeightLeft = 1f,
            FootPlantedRight = false,
            PlantWeightRight = 0f
        };
        rig.Soccer.ApplyMotion(motion);

        var player = new PlayerState
        {
            Spec = spec,
            Action = "run",
            Sprinting = true,
            Facing = new NVector3(0, 0, 1)
        };

        var updateMs = new List<double>();
        var processMs = new List<double>();
        var physicsMs = new List<double>();
        var ankleClearance = new List<float>();
        Image? centeredEvidenceCapture = null;
        int frames = 0;

        // Each run has 3 deterministic clip segments on both a flat and an 8%
        // grade. Non-zero yaw and world translation exercise skeleton/world
        // conversions rather than a rig placed at the origin.
        rig.Rotation = new Vector3(0f, .55f, 0f);
        for (int i = 0; i < 360; i++)
        {
                float x = -3.8f + 7.6f * i / 359f;
                float y = .2f + MathF.Tan(.08f) * MathF.Max(0f, x);
                var worldPosition = new Vector3(x, y, 0f);
                rig.Position = worldPosition;
                player.Pos = new NVector3(worldPosition.X, worldPosition.Y, worldPosition.Z);
                player.Vel = new NVector3(1.27f, 0f, 0f);
                player.Facing = new NVector3(-MathF.Sin(.55f), 0f, -MathF.Cos(.55f));

                motion.CurrentClipId = i < 120 ? "soccer_run" : i < 240 ? "soccer_sprint" : "soccer_turn";
                motion.Phase = (motion.Phase + .012f) % 1f;
                bool left = (i / 20) % 2 == 0;
                motion.FootPlantedLeft = left;
                motion.FootPlantedRight = !left;
                motion.PlantWeightLeft = left ? 1f : 0f;
                motion.PlantWeightRight = left ? 0f : 1f;

                await ToSignal(GetTree(), SceneTree.SignalName.PhysicsFrame);
                var sw = Stopwatch.StartNew();
                rig.Soccer.Update(player, Dt);
                sw.Stop();
                updateMs.Add(sw.Elapsed.TotalMilliseconds);

                double frame = Performance.GetMonitor(Performance.Monitor.TimeProcess) * 1000.0;
                double physics = Performance.GetMonitor(Performance.Monitor.TimePhysicsProcess) * 1000.0;
                if (frame > 0 && double.IsFinite(frame)) processMs.Add(frame);
                if (physics > 0 && double.IsFinite(physics)) physicsMs.Add(physics);

                if (i % 6 == 0)
                {
                    SampleAnkleClearance(rig.Soccer.Skel, "foot_L", ankleClearance);
                    SampleAnkleClearance(rig.Soccer.Skel, "foot_R", ankleClearance);
                }

                // Capture near the centre of the deterministic traversal. Capturing
                // only after frame 359 leaves the translated production rig clipped
                // at the right edge and makes the evidence image hard to inspect.
                if (i == 180)
                {
                    await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
                    centeredEvidenceCapture = GetViewport().GetTexture().GetImage();
                }
                frames++;
        }

        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        if (metrics.Samples < 20)
            throw new InvalidOperationException($"Insufficient planted-foot measurements: {metrics.Samples}");
        if (metrics.TransitionEvents < 2)
            throw new InvalidOperationException($"Expected clip-transition measurements, got {metrics.TransitionEvents}");
        if (updateMs.Count != frames || ankleClearance.Count == 0)
            throw new InvalidOperationException("Runtime evidence collection was incomplete.");

        var report = new Dictionary<string, object>
        {
            ["commit_sha"] = System.Environment.GetEnvironmentVariable("ARENA_FC_COMMIT_SHA") ?? "local",
            ["godot_version"] = Engine.GetVersionInfo().ToString(),
            ["renderer"] = ProjectSettings.GetSetting("rendering/renderer/rendering_method").AsString(),
            ["scenario"] = "production_soccer_clip_rig_flat_and_8_percent_slope_translated_rotated",
            ["frames"] = frames,
            ["physics_tick_rate_hz"] = 60,
            ["frame_budget_ms_at_60hz"] = 1000.0 / 60.0,
            ["animation_metric_samples"] = metrics.Samples,
            ["avg_planted_foot_slide_mps"] = metrics.AvgFootSlide,
            ["foot_slide_metric_scope"] = "world_space_xz_velocity_during_contract_planted_frames",
            ["transition_events"] = metrics.TransitionEvents,
            ["avg_transition_discontinuity"] = metrics.AvgTransitionDiscontinuity,
            ["transition_metric_scope"] = "mean_raw_pose_offset_on_inertialized_upper_body_bones",
            ["contact_events"] = metrics.ContactEvents,
            ["avg_contact_frame_error"] = metrics.AvgContactFrameError,
            ["ground_clearance_metric"] = "ankle_bone_origin_to_collision_surface_not_sole_clearance",
            ["ankle_ground_clearance_min_m"] = ankleClearance.Min(),
            ["ankle_ground_clearance_max_m"] = ankleClearance.Max(),
            ["rig_update_avg_ms"] = updateMs.Average(),
            ["rig_update_p95_ms"] = Percentile(updateMs, .95),
            ["rig_update_max_ms"] = updateMs.Max(),
            ["engine_frame_avg_ms"] = processMs.Count > 0 ? processMs.Average() : 0,
            ["engine_physics_avg_ms"] = physicsMs.Count > 0 ? physicsMs.Average() : 0,
            ["static_memory_bytes"] = Performance.GetMonitor(Performance.Monitor.MemoryStatic),
            ["draw_calls"] = Performance.GetMonitor(Performance.Monitor.RenderTotalDrawCallsInFrame)
        };
        string json = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(Path.Combine(output, "runtime-evidence.json"), json);
        var image = centeredEvidenceCapture ?? GetViewport().GetTexture().GetImage();
        if (image.SavePng(Path.Combine(output, "production-rig-grounding.png")) != Error.Ok)
            throw new InvalidOperationException("Could not save production rig evidence image.");

        GD.Print("[RuntimeEvidence] " + json);
        GetTree().Quit(0);
    }

    private void AddGround(float centerX, float slope, float centerY)
    {
        var body = new StaticBody3D
        {
            Position = new Vector3(centerX, centerY, 0f),
            Rotation = new Vector3(0f, 0f, slope)
        };
        var shape = new BoxShape3D { Size = new Vector3(4.2f, .2f, 8f) };
        body.AddChild(new CollisionShape3D { Shape = shape });
        var material = new StandardMaterial3D { AlbedoColor = new Color("#39764a"), Roughness = .95f };
        body.AddChild(new MeshInstance3D
        {
            Mesh = new BoxMesh { Size = new Vector3(4.2f, .2f, 8f) },
            MaterialOverride = material
        });
        AddChild(body);
    }

    private void SampleAnkleClearance(Skeleton3D skeleton, string boneName, List<float> values)
    {
        if (skeleton == null) return;
        int index = SoccerClipRig.FindBoneLoose(skeleton, boneName);
        if (index < 0) return;
        Vector3 ankleWorld = (skeleton.GlobalTransform * skeleton.GetBoneGlobalPose(index)).Origin;
        var query = PhysicsRayQueryParameters3D.Create(
            ankleWorld + Vector3.Up * .5f, ankleWorld - Vector3.Up * .8f);
        var hit = GetWorld3D().DirectSpaceState.IntersectRay(query);
        if (hit.Count == 0 || !hit.ContainsKey("position")) return;
        var ground = (Vector3)hit["position"];
        float clearance = ankleWorld.Y - ground.Y;
        if (float.IsFinite(clearance)) values.Add(clearance);
    }

    private static double Percentile(List<double> values, double percentile)
    {
        if (values.Count == 0) return 0;
        var sorted = values.OrderBy(v => v).ToArray();
        int index = Math.Clamp((int)Math.Ceiling(percentile * sorted.Length) - 1, 0, sorted.Length - 1);
        return sorted[index];
    }
}
