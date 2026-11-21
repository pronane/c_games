using System;

namespace ArenaFC.Core.Animation;

/// <summary>A presentation-only, raw-unit feature query. The database applies its baked
/// mean/stddev and weights. Features are copied so callers cannot mutate a query while
/// a deterministic search is in progress.</summary>
public sealed class MotionQuery
{
    private readonly float[] _features;

    public ReadOnlySpan<float> Features => _features;
    public ClipCategory Category { get; }
    public BallState Ball { get; }
    public PlayerIntent Intent { get; }
    public string StyleTag { get; }
    public string CurrentClipId { get; }
    public float CurrentPhase { get; }
    public float SwitchPenalty { get; }
    public float TemporalPenalty { get; }
    /// <summary>When set, only this clip's rows are candidates (an action with its own
    /// clip): the search picks the entry frame, not the clip.</summary>
    public string ForcedClipId { get; }

    /// <summary>Build the shared 23D locomotion query from the last matched local foot
    /// pose, current/desired root motion, and a deterministic damped-pursuit trajectory.
    /// Velocity and facing inputs are already in the current facing-root XZ basis.</summary>
    public static float[] BuildFeatures(ReadOnlySpan<float> currentPoseFeatures,
        float rootVelX, float rootVelZ, float yawRate,
        float desiredVelX, float desiredVelZ, float desiredYawRate,
        float timeToContact = MotionFeatureLayout.NoContact)
    {
        if (currentPoseFeatures.Length != 8)
            throw new ArgumentException("Current pose must contain the 8 foot position/velocity features.", nameof(currentPoseFeatures));
        if (!float.IsFinite(rootVelX) || !float.IsFinite(rootVelZ) || !float.IsFinite(yawRate)
            || !float.IsFinite(desiredVelX) || !float.IsFinite(desiredVelZ) || !float.IsFinite(desiredYawRate))
            throw new ArgumentException("Motion query inputs must be finite.");
        var features = new float[MotionFeatureLayout.Dimensions];
        currentPoseFeatures.CopyTo(features);
        features[8] = rootVelX;
        features[9] = rootVelZ;
        features[10] = yawRate;
        for (int i = 0; i < MotionFeatureLayout.TrajectoryTimes.Length; i++)
        {
            float t = MotionFeatureLayout.TrajectoryTimes[i];
            float decay = MathF.Exp(-4f * t);
            float integratedGain = (1f - decay) * .25f;
            features[11 + i * 2] = desiredVelX * t + (rootVelX - desiredVelX) * integratedGain;
            features[12 + i * 2] = desiredVelZ * t + (rootVelZ - desiredVelZ) * integratedGain;
            float yaw = desiredYawRate * t;
            features[17 + i * 2] = MathF.Sin(yaw);
            features[18 + i * 2] = MathF.Cos(yaw);
        }
        features[MotionFeatureLayout.TimeToContact] = float.IsFinite(timeToContact) && timeToContact >= 0f
            ? MathF.Min(timeToContact, MotionFeatureLayout.NoContact) : MotionFeatureLayout.NoContact;
        return features;
    }

    public MotionQuery(float[] features, ClipCategory category, BallState ball,
        PlayerIntent intent = PlayerIntent.Move, string? styleTag = null,
        string? currentClipId = null, float currentPhase = 0f,
        float switchPenalty = .08f, float temporalPenalty = .12f, string? forcedClipId = null)
    {
        if (features == null) throw new ArgumentNullException(nameof(features));
        if (features.Length != MotionFeatureLayout.Dimensions)
            throw new ArgumentException($"Motion query needs {MotionFeatureLayout.Dimensions} features.", nameof(features));
        for (int i = 0; i < features.Length; i++)
            if (!float.IsFinite(features[i]))
                throw new ArgumentException($"Motion query feature {i} is not finite.", nameof(features));
        if (!float.IsFinite(currentPhase) || !float.IsFinite(switchPenalty) || switchPenalty < 0f
            || !float.IsFinite(temporalPenalty) || temporalPenalty < 0f)
            throw new ArgumentOutOfRangeException(nameof(currentPhase), "Phase and costs must be finite; penalties must be non-negative.");

        _features = (float[])features.Clone();
        Category = category;
        Ball = ball;
        Intent = intent;
        StyleTag = styleTag ?? "";
        CurrentClipId = currentClipId ?? "";
        CurrentPhase = currentPhase;
        SwitchPenalty = switchPenalty;
        TemporalPenalty = temporalPenalty;
        ForcedClipId = forcedClipId ?? "";
    }
}
