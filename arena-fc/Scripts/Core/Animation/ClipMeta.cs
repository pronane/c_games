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
    KeeperDive, Celebrate, Idle, Recovery
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

    public bool HasContact => ContactFraction >= 0f && ContactFraction <= 1f;
}
