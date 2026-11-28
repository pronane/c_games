// Arena Motion Engine: shared clip metadata. Pure C#; safe in desktop,
// server tests, and the browser's equivalent GDScript manifest reader.
using System;
using System.Numerics;

namespace ArenaFC.Core.Animation;

public enum BallState { None, Possessed, Approaching, Contested, Aerial }

/// <summary>Side used to preserve same-foot contact when mapping plant events across clips.</summary>
public enum FootSide { Left, Right }

public enum ClipCategory
{
    Locomotion, Approach, FirstTouch, Shield, Cut, Kick, Pass, Tackle,
    KeeperDive, Celebrate, Idle, Recovery,
    /// <summary>Goalkeeper-only stances and handling (never chosen for outfield movement).</summary>
    Keeper,
    /// <summary>Skill moves: only ever played for the skill that names them.</summary>
    Skill,
    /// <summary>Violent conduct (punch, headbutt): only ever played for that action.</summary>
    Conduct
}

/// <summary>Metadata only; actual poses stay in the Sprite Forge GLB / baked JSON.</summary>
public sealed class ClipMeta
{
    public string Id { get; set; } = "";
    public string PoseDataKey { get; set; } = "";
    public ClipCategory Category { get; set; }
    public float Duration { get; set; }
    /// <summary>Normalized 0..1 contact time, or -1 when the clip has no contact event.</summary>
    public float ContactFraction { get; set; } = -1f;
    /// <summary>Normalized plant phases in clip-cycle coordinates.</summary>
    public float[] FootPlantFrames { get; set; } = Array.Empty<float>();
    /// <summary>Side for each plant event. Missing legacy metadata alternates Left, Right.</summary>
    public FootSide[] FootPlantSides { get; set; } = Array.Empty<FootSide>();

    public FootSide FootPlantSideAt(int index) => FootPlantSides.Length == FootPlantFrames.Length
        ? FootPlantSides[index] : (index % 2 == 0 ? FootSide.Left : FootSide.Right);
    public Vector3 RootVelocityAvg { get; set; }
    public float PreferredSpeed { get; set; }
    public float PreferredTurnRate { get; set; }
    public BallState BallState { get; set; }
    public string[] Tags { get; set; } = Array.Empty<string>();
    public int BoneCount { get; set; } = 18;
    public bool Loop { get; set; }
    /// <summary>Ground speed the loop's stride is authored for (m/s, GLB-baked: how fast a foot
    /// that is flat on the ground moves back under the body).  0 = unknown, use PreferredSpeed.
    /// Playing a loop at speed / StrideSpeed keeps the planted foot still in the world.</summary>
    public float StrideSpeed { get; set; }

    // Hypermotion data plumbing (manifest v2): sampled curves for grounded IK/contact.
    /// <summary>Uniformly sampled left-plant weight over clip duration (0..1). Empty = use FootPlantFrames.</summary>
    public float[] PlantCurveLeft { get; set; } = Array.Empty<float>();
    /// <summary>Uniformly sampled right-plant weight over clip duration (0..1). Empty = use FootPlantFrames.</summary>
    public float[] PlantCurveRight { get; set; } = Array.Empty<float>();
    /// <summary>Normalized contact window start (0..1), or -1 when no contact.</summary>
    public float ContactWindowStart { get; set; } = -1f;
    /// <summary>Normalized contact window end (0..1), or -1 when no contact.</summary>
    public float ContactWindowEnd { get; set; } = -1f;
    /// <summary>Uniformly sampled root velocity in facing-local XZ, interleaved [x0,z0,x1,z1,...] m/s.</summary>
    public float[] RootVelocitySamples { get; set; } = Array.Empty<float>();

    public bool HasContact => ContactFraction >= 0f && ContactFraction <= 1f;
    public bool HasPlantCurves => PlantCurveLeft.Length > 1 && PlantCurveRight.Length == PlantCurveLeft.Length;
    public bool HasContactWindow => ContactWindowStart >= 0f && ContactWindowEnd >= ContactWindowStart && ContactWindowEnd <= 1f;
    /// <summary>Authored for one engine action (tag "dedicated"): never picked by category.</summary>
    public bool Dedicated => Array.Exists(Tags, t => string.Equals(t, "dedicated", StringComparison.OrdinalIgnoreCase));

    public float SamplePlantWeight(bool left, float phase01)
    {
        var curve = left ? PlantCurveLeft : PlantCurveRight;
        if (curve.Length < 2)
        {
            // Fallback to discrete plant events.
            if (FootPlantFrames.Length == 0) return 0f;
            bool planted = false;
            for (int i = 0; i < FootPlantFrames.Length; i++)
                if (FootPlantSideAt(i) == (left ? FootSide.Left : FootSide.Right)
                    && MathF.Abs(CircularDiff(phase01, FootPlantFrames[i])) <= .035f) { planted = true; break; }
            return planted ? 1f : 0f;
        }
        float p = phase01 - MathF.Floor(phase01);
        float f = p * (curve.Length - 1);
        int i0 = (int)f;
        int i1 = Math.Min(i0 + 1, curve.Length - 1);
        float t = f - i0;
        return curve[i0] + (curve[i1] - curve[i0]) * t;
    }

    public Vector2 SampleRootVelocity(float phase01)
    {
        if (RootVelocitySamples.Length < 4 || RootVelocitySamples.Length % 2 != 0)
            return new Vector2(RootVelocityAvg.X, RootVelocityAvg.Z);
        int count = RootVelocitySamples.Length / 2;
        float p = phase01 - MathF.Floor(phase01);
        float f = p * (count - 1);
        int i0 = (int)f;
        int i1 = Math.Min(i0 + 1, count - 1);
        float t = f - i0;
        float x = RootVelocitySamples[i0 * 2] + (RootVelocitySamples[i1 * 2] - RootVelocitySamples[i0 * 2]) * t;
        float z = RootVelocitySamples[i0 * 2 + 1] + (RootVelocitySamples[i1 * 2 + 1] - RootVelocitySamples[i0 * 2 + 1]) * t;
        return new Vector2(x, z);
    }

    private static float CircularDiff(float a, float b)
    {
        float d = (a - b) % 1f;
        if (d > .5f) d -= 1f;
        if (d < -.5f) d += 1f;
        return d;
    }
}
