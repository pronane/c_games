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
        if (!rig.Soccer.HasSoleGeometry)
            throw new InvalidOperationException(
                "Production boot meshes did not provide sole vertices for both feet; refusing to substitute ankle-based measurements.");

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
        var soleClearance = new List<float>();
        float maxBoneStretchRatio = 0f;
        string maxBoneStretchName = "";
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

                var stretch = MeasureBoneStretch(rig.Soccer.Skel);
                if (stretch.ratio > maxBoneStretchRatio)
                {
                    maxBoneStretchRatio = stretch.ratio;
                    maxBoneStretchName = stretch.bone;
                }
                if (i % 6 == 0)
                {
                    SampleSoleClearance(rig.Soccer, "L", soleClearance);
                    SampleSoleClearance(rig.Soccer, "R", soleClearance);
                }

                // Capture near the centre of the deterministic traversal. Capturing
                // only after frame 359 leaves the translated production rig clipped
                // at the right edge and makes the evidence image hard to inspect.
                if (i == 60 || i == 180 || i == 300)
                {
                    camera.Position = new Vector3(x, y + 1.8f, 6.5f);
                    camera.LookAt(new Vector3(x, y + .9f, 0));
                    await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
                    var capture = GetViewport().GetTexture().GetImage();
                    string label = i == 60 ? "run-flat" : i == 180 ? "sprint-flat-to-ramp" : "turn-ramp";
                    if (capture.SavePng(Path.Combine(output, label + ".png")) != Error.Ok)
                        throw new InvalidOperationException("Could not save " + label + " evidence image.");
                    // Compact copy used to inspect workflow evidence when the
                    // artifact storage service is unreachable from a client.
                    var thumbnail = GetViewport().GetTexture().GetImage();
                    thumbnail.Resize(320, 180, Image.Interpolation.Bilinear);
                    if (thumbnail.SavePng(Path.Combine(output, label + "-thumbnail.png")) != Error.Ok)
                        throw new InvalidOperationException("Could not save evidence thumbnail.");
                    if (i == 180) centeredEvidenceCapture = capture;
                }
                frames++;
        }

        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        if (metrics.Samples < 20)
            throw new InvalidOperationException($"Insufficient planted-foot measurements: {metrics.Samples}");
        if (metrics.TransitionMeasurements < 2)
            throw new InvalidOperationException($"Expected clip-transition measurements, got {metrics.TransitionMeasurements}");
        if (updateMs.Count != frames || soleClearance.Count == 0 || maxBoneStretchRatio <= 0f)
            throw new InvalidOperationException("Runtime evidence collection was incomplete.");
        // Gross anatomical safety guard, not an animation-quality threshold.
        // Each child joint should remain near its authored parent offset; this
        // catches severe persistent global overrides that pull limbs apart.

        var passContact = RunMatchContactScenario(spec, shoot: false);
        var shotContact = RunMatchContactScenario(spec, shoot: true);
        if (!passContact.success || !shotContact.success)
            throw new InvalidOperationException($"Match-engine contact scenario failed: pass={passContact.detail}; shot={shotContact.detail}");
        double averageContactErrorFrames = (passContact.errorFrames + shotContact.errorFrames) * .5;

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
            ["transition_measurements"] = metrics.TransitionMeasurements,
            ["avg_transition_discontinuity"] = metrics.AvgTransitionDiscontinuity,
            ["transition_metric_scope"] = "mean_raw_pose_offset_on_inertialized_upper_body_bones",
            ["contact_events"] = 2,
            ["avg_contact_frame_error"] = averageContactErrorFrames,
            ["contact_measurement_scope"] = "actual MatchEngine pass/shot ball release sampled against the production kick clip authored ball_contact frame",
            ["match_contact_scenarios"] = new Dictionary<string, object>
            {
                ["pass"] = new { error_frames = passContact.errorFrames, detail = passContact.detail },
                ["shot"] = new { error_frames = shotContact.errorFrames, detail = shotContact.detail }
            },
            ["ground_clearance_metric"] = "lowest production boot mesh sole vertex to collision surface",
            ["max_bone_parent_distance_vs_rest"] = maxBoneStretchRatio,
            ["max_bone_parent_distance_bone"] = maxBoneStretchName,
            ["bone_stretch_metric_scope"] = "maximum parent-child joint distance divided by authored rest offset; not mesh deformation",
            ["sole_ground_clearance_min_m"] = soleClearance.Min(),
            ["sole_ground_clearance_max_m"] = soleClearance.Max(),
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
        // Write the evidence before failing so the bad frame remains inspectable.
        if (maxBoneStretchRatio > 2.5f)
            throw new InvalidOperationException($"Severe bone stretch: {maxBoneStretchName} ratio={maxBoneStretchRatio:F3}");
        GetTree().Quit(0);
    }

    private static (float ratio, string bone) MeasureBoneStretch(Skeleton3D skeleton)
    {
        skeleton.ForceUpdateAllBoneTransforms();
        float maximum = 0f;
        string name = "";
        for (int i = 0; i < skeleton.GetBoneCount(); i++)
        {
            int parent = skeleton.GetBoneParent(i);
            float restLength = skeleton.GetBoneRest(i).Origin.Length();
            if (parent < 0 || restLength < .02f) continue;
            float actualLength = skeleton.GetBoneGlobalPose(i).Origin.DistanceTo(skeleton.GetBoneGlobalPose(parent).Origin);
            float ratio = actualLength / restLength;
            if (!float.IsFinite(ratio)) throw new InvalidOperationException("Non-finite skeleton bone pose.");
            if (ratio > maximum) { maximum = ratio; name = skeleton.GetBoneName(i); }
        }
        return (maximum, name);
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

    private void SampleSoleClearance(SoccerClipRig soccer, string side, List<float> values)
    {
        Vector3 soleWorld = soccer.SoleWorldPosition(side);
        var query = PhysicsRayQueryParameters3D.Create(
            soleWorld + Vector3.Up * .5f, soleWorld - Vector3.Up * .8f);
        var hit = GetWorld3D().DirectSpaceState.IntersectRay(query);
        if (hit.Count == 0 || !hit.ContainsKey("position")) return;
        var ground = (Vector3)hit["position"];
        float clearance = soleWorld.Y - ground.Y;
        if (float.IsFinite(clearance)) values.Add(clearance);
    }

    private (bool success, double errorFrames, string detail) RunMatchContactScenario(CharacterSpec spec, bool shoot)
    {
        var engine = new MatchEngine(new MatchOptions { Seed = shoot ? 7319 : 7318, TeamSize = 11, TimeSpeed = 15f });
        engine.State.Phase = Phase.Play;
        engine.State.PhaseTimer = 0f;
        engine.State.ControlLock = 10f;
        engine.State.Controlled = 0;
        var player = engine.State.Players[0];
        player.DecisionTimer = 10f;
        player.PossessionLock = 0f;
        player.TackleLock = 0f;
        player.Stamina = 1f;
        player.Facing = NVector3.UnitX;
        player.Target = player.Pos;
        var receiver = engine.State.Players[1];
        receiver.Pos = player.Pos + new NVector3(8f, 0f, 2f);
        var ball = engine.State.Ball;
        ball.Owner = player.Index;
        ball.Vel = NVector3.Zero;
        ball.Spin = NVector3.Zero;
        ball.FreeTime = .2f;
        ball.NoPickup = 0f;
        ball.PassFrom = -1;
        ball.PassReceiver = -1;
        ball.Pos = player.Pos + new NVector3(.4f, Mx.BallRadius, 0f);

        var actionRig = RigFactory.Create(spec);
        AddChild(actionRig);
        if (actionRig.Soccer == null || actionRig.Soccer.Player == null)
            return (false, 0, "production action rig unavailable");
        const string actionClip = "soccer_kick_place"; // engine pass and standard shot both author the kick action
        float authoredContactTime = actionRig.Soccer.AuthoredContactTime(actionClip);
        float authoredFps = actionRig.Soccer.AuthoredClipFps(actionClip);
        if (authoredContactTime <= 0f || authoredFps <= 0f)
            return (false, 0, $"{actionClip} has no authored ball_contact frame in the production manifest");

        bool started = false;
        for (int tick = 0; tick < 60; tick++)
        {
            var command = tick == 0
                ? shoot ? new PlayerCommand { Shoot = true, Charge = .8f } : new PlayerCommand { Pass = true }
                : PlayerCommand.None;
            engine.Step(Dt, command);
            actionRig.Soccer.Update(player, Dt);
            if (player.ActionTimer > 0f && player.Action == "kick") started = true;
            if (started && !ball.HasPending && ball.Vel.LengthSquared() > .1f)
            {
                float animationTime = actionRig.Soccer.Player.CurrentAnimationPosition;
                double errorFrames = Math.Abs(animationTime - authoredContactTime) * authoredFps;
                return (true, errorFrames,
                    $"release_tick={tick} animation_time={animationTime:F4}s authored_contact={authoredContactTime:F4}s fps={authoredFps:F1}");
            }
        }
        return (false, 0, $"{(shoot ? "shot" : "pass")} did not release the ball during its 60-tick action window; action={player.Action}, pending={ball.HasPending}, speed={ball.Vel.Length():F3}");
    }

    private static double Percentile(List<double> values, double percentile)
    {
        if (values.Count == 0) return 0;
        var sorted = values.OrderBy(v => v).ToArray();
        int index = Math.Clamp((int)Math.Ceiling(percentile * sorted.Length) - 1, 0, sorted.Length - 1);
        return sorted[index];
    }
}
