// Arena FC - Ball approach planning for Hypermotion/ML-Flow-style locomotion.
// Pure C#, deterministic. Computes approach weight, stride shortening bias,
// and contact-timing cost used by MotionEngine clip selection.
using System;
using System.Numerics;

namespace ArenaFC.Core.Animation;

/// <summary>Presentation-only ball approach state derived from match sampling.</summary>
public struct BallApproachState
{
    public float DistanceToBall;
    public float TimeToBallContact;
    public float ApproachWeight;      // 0..1 smooth ramp
    public bool IsApproachingBall;
    public Vector3 BallRelativeFlat;  // ball relative to player in facing-local XZ
}

public static class BallApproach
{
    public const float DefaultApproachDistance = 4.5f;
    public const float ContactTolerance = 0.30f;

    /// <summary>Update approach state from current player/ball sample. Deterministic.</summary>
    public static BallApproachState Update(
        Vector3 playerPos, Vector3 playerVel, Vector3 playerFacing,
        Vector3 ballPos, Vector3 ballVel,
        bool hasBallInterest, float dt, float previousWeight)
    {
        var state = new BallApproachState();
        Vector3 toBall = ballPos - playerPos;
        toBall.Y = 0f;
        state.DistanceToBall = toBall.Length();

        Vector3 toBallDir = state.DistanceToBall > 1e-5f ? toBall / state.DistanceToBall : Vector3.UnitX;
        float closing = MathF.Max(0.15f, Vector3.Dot(MxFlat(playerVel), toBallDir) - Vector3.Dot(MxFlat(ballVel), toBallDir));
        state.TimeToBallContact = Math.Clamp(state.DistanceToBall / closing, 0.05f, 2.5f);

        Vector3 desired = MxFlat(playerVel).LengthSquared() > 0.01f ? Vector3.Normalize(MxFlat(playerVel)) : MxFlat(playerFacing);
        bool movingToward = desired.LengthSquared() > 0.01f && Vector3.Dot(desired, toBallDir) > 0.35f;
        state.IsApproachingBall = hasBallInterest && state.DistanceToBall < DefaultApproachDistance && movingToward;

        float target = state.IsApproachingBall ? 1f : 0f;
        float ramp = 3.5f * Math.Max(0f, dt);
        state.ApproachWeight = MoveToward(previousWeight, target, ramp);

        // Facing-local ball position (x=right, z=forward)
        Vector3 fwd = MxFlat(playerFacing);
        if (fwd.LengthSquared() < 1e-6f) fwd = Vector3.UnitZ;
        fwd = Vector3.Normalize(fwd);
        Vector3 right = new Vector3(-fwd.Z, 0f, fwd.X);
        state.BallRelativeFlat = new Vector3(Vector3.Dot(toBall, right), 0f, Vector3.Dot(toBall, fwd));
        return state;
    }

    /// <summary>Additional cost for clips whose contact timing mismatches predicted arrival.</summary>
    public static float ContactTimingCost(ClipMeta clip, float timeToBallContact)
    {
        if (clip == null || !clip.HasContact) return 2.2f;
        float diff = MathF.Abs(clip.ContactFraction * clip.Duration - timeToBallContact);
        float posPenalty = clip.ContactFraction > 0.65f ? 0.35f : 0f;
        return Math.Clamp((diff + posPenalty) / ContactTolerance, 0f, 2.8f);
    }

    /// <summary>Bias toward shorter-stride/slower clips as approach weight rises.</summary>
    public static float StrideShorteningCost(ClipMeta clip, float desiredSpeed, float approachWeight)
    {
        if (clip == null) return 0f;
        float targetSpeed = Lerp(desiredSpeed, desiredSpeed * 0.55f, Math.Clamp(approachWeight, 0f, 1f));
        return MathF.Abs(clip.PreferredSpeed - targetSpeed) * 0.7f;
    }

    /// <summary>Preferred start phase so a clip's contact lands near predicted arrival.</summary>
    public static float ContactLockedStartPhase(ClipMeta clip, float timeToBallContact, float phaseMatchedStart, float approachWeight)
    {
        if (clip == null || !clip.HasContact || timeToBallContact <= 0f) return phaseMatchedStart;
        float idealStart = Math.Clamp(clip.ContactFraction - (timeToBallContact / MathF.Max(0.001f, clip.Duration)), 0f, clip.ContactFraction);
        return Lerp(phaseMatchedStart, idealStart, Math.Clamp(approachWeight, 0f, 1f) * 0.75f);
    }

    private static Vector3 MxFlat(Vector3 v) => new Vector3(v.X, 0f, v.Z);
    private static float Lerp(float a, float b, float t) => a + (b - a) * Math.Clamp(t, 0f, 1f);
    private static float MoveToward(float current, float target, float maxDelta)
    {
        if (MathF.Abs(target - current) <= maxDelta) return target;
        return current + MathF.Sign(target - current) * maxDelta;
    }
}
