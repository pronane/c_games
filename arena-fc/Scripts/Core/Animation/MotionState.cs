// Runtime animation state is presentation data. It is intentionally separate
// from MatchState so visuals can never alter authoritative match outcomes.
namespace ArenaFC.Core.Animation;

public enum PlayerIntent
{
    None, Move, Sprint, SprintStop, Pass, ThroughBall, Shoot, Trap, Shield,
    Cut, Tackle, Dive, Celebrate
}

public sealed class MotionState
{
    public string CurrentClipId = "";
    /// <summary>Normalized source phase (0..1). Loops wrap; one-shots clamp.</summary>
    public float Phase;
    public float BlendWeight = 1f;
    public string NextClipId = "";
    public float NextPhase;
    public float CrossfadeRemaining;
    public float CrossfadeDuration = .12f;
    public float PlaybackScale = 1f;
    /// <summary>Feature row the last motion-matching search chose; -1 = rule selector.</summary>
    public int MotionMatchRowIndex = -1;
    /// <summary>Seconds since the last motion-matching search (locomotion re-queries ~10x/s).</summary>
    public float SinceQuery;
    /// <summary>The pose shown on the previous update (survives a one-shot reset), so
    /// the next search starts from where the body actually is.</summary>
    public string LastPoseClipId = "";
    public float LastPosePhase;
    public float Speed;
    public float TurnRate;
    public BallState Ball;
    public PlayerIntent LastIntent;
    public float TimeSinceContact;
    public bool ContactCrossed;
    public bool FootPlantedLeft;
    public bool FootPlantedRight;

    // Hypermotion/ML-Flow-style ball approach (presentation-only, deterministic).
    public float ApproachWeight;
    public float DistanceToBall = float.MaxValue;
    public float TimeToBallContact = -1f;
    public bool IsApproachingBall;

    public string RenderClipId => NextClipId.Length > 0 ? NextClipId : CurrentClipId;
    public float RenderPhase => NextClipId.Length > 0 ? NextPhase : Phase;
}

/// <summary>Migration-ready timed-touch data; not yet wired into MatchEngine.</summary>
public sealed class DribbleState
{
    public int OwnerId = -1;
    public float LocalOffsetX, LocalOffsetZ;
    public float TouchTimer;
    public float Separation;
    public bool Shielding;
    public float ShieldStrength;
    public float LastTouchSpeed;
}
