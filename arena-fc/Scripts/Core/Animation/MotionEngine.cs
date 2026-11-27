// Deterministic, engine-free clip selection and phase policy for the Arena Motion Engine.
// This class never mutates PlayerState or MatchState; callers supply sampled inputs.
using System;
using System.Collections.Generic;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Core.Animation;

public sealed class MotionEngine
{
    public const float DefaultCrossfadeSeconds = .12f;
    private readonly Dictionary<string, ClipMeta> _clips = new(StringComparer.Ordinal);
    private readonly List<ClipMeta> _ordered = new();

    public int ClipCount => _ordered.Count;
    public AnimationMetrics Metrics { get; } = new();

    /// <summary>Pose-level motion matching (schema v2 feature table).  When set, every
    /// clip switch - and running cycles about ten times a second - searches the
    /// baked frames for the best continuation: the pose the body is in, the path it
    /// is about to take and, for ball actions, the wind-up time left before contact.
    /// Without it the rule selector below runs exactly as before.</summary>
    public MotionDatabase? Database { get; set; }
    public const float LocomotionQueryInterval = .1f;

    public void LoadClips(IEnumerable<ClipMeta> clips)
    {
        _clips.Clear();
        _ordered.Clear();
        foreach (var clip in clips)
        {
            if (clip == null || string.IsNullOrWhiteSpace(clip.Id) || clip.Duration <= 0f)
                throw new ArgumentException("Motion clips require a non-empty id and positive duration.", nameof(clips));
            if (clip.BoneCount != 18)
                throw new ArgumentException($"Clip '{clip.Id}' has {clip.BoneCount} bones; Arena rigs require 18.", nameof(clips));
            if (_clips.ContainsKey(clip.Id))
                throw new ArgumentException($"Duplicate motion clip id '{clip.Id}'.", nameof(clips));
            _clips.Add(clip.Id, clip);
            _ordered.Add(clip);
        }
        _ordered.Sort((a, b) => string.CompareOrdinal(a.Id, b.Id));
    }

    public bool TryGetClip(string id, out ClipMeta meta) => _clips.TryGetValue(id, out meta!);

    public static float InitialPhase(int playerIndex)
    {
        // Stable, index-derived staggering; no RNG stream and no platform dependence.
        uint x = unchecked((uint)(playerIndex + 1) * 0x9E3779B9u);
        x ^= x >> 16; x *= 0x7FEB352Du; x ^= x >> 15;
        return (x & 0x00FFFFFFu) / (float)0x01000000u;
    }

    /// <summary>Update once per fixed match tick. `secondsUntilContact` is presentation
    /// input derived from ActionDuration/ActionContactAt; it never schedules the sim event.</summary>
    public void Update(MotionState motion, float speed, float turnRate, BallState ball,
        PlayerIntent intent, float dt, float secondsUntilContact = -1f,
        float bodyTypeFactor = 1f, string? styleTag = null,
        Vector2 localVelocity = default, Vector2 desiredLocalVelocity = default, string? forcedClipId = null)
    {
        if (motion == null) throw new ArgumentNullException(nameof(motion));
        dt = Math.Max(0f, dt);
        motion.ContactCrossed = false;
        motion.FootstepLeft = false;
        motion.FootstepRight = false;
        motion.Speed = Math.Max(0f, speed);
        motion.TurnRate = turnRate;
        motion.Ball = ball;
        motion.LastIntent = intent;
        motion.TimeSinceContact += dt;

        // Hypermotion-style ball approach: ramp a presentation-only weight when
        // the player is closing on the ball / a timed contact is imminent. This biases
        // selection toward contact-timed clips and shortens stride on approach.
        float ttc = secondsUntilContact > 0f ? secondsUntilContact : -1f;
        bool approaching = (ball == BallState.Approaching || ttc > 0f) && (ttc < 1.5f || ball == BallState.Approaching);
        float targetApproach = approaching ? 1f : 0f;
        motion.ApproachWeight = MoveToward(motion.ApproachWeight, targetApproach, 3.5f * dt);
        motion.IsApproachingBall = motion.ApproachWeight > 0.05f;
        motion.TimeToBallContact = ttc;
        motion.DistanceToBall = ttc > 0f ? ttc * Math.Max(0.1f, speed) : (ball == BallState.Approaching ? 3f : float.MaxValue);

        ClipMeta? selected = SelectClip(intent, ball, speed, turnRate, bodyTypeFactor, styleTag, motion.ApproachWeight, ttc);
        if (forcedClipId != null && _clips.TryGetValue(forcedClipId, out var forcedClip)) selected = forcedClip;
        float? matchedPhase = null;
        motion.SinceQuery += dt;
        if (selected != null && Database != null)
        {
            bool switching = !string.Equals(selected.Id, motion.RenderClipId, StringComparison.Ordinal);
            bool gait = selected.Loop && IsLocomotion(selected.Category);
            if (switching || (gait && motion.SinceQuery >= LocomotionQueryInterval))
            {
                motion.SinceQuery = 0f;
                var m = Match(motion, selected, ball, intent, turnRate, styleTag, localVelocity,
                              desiredLocalVelocity, secondsUntilContact, forcedClipId);
                if (m != null && _clips.TryGetValue(m.Value.Row.ClipId, out var mc))
                {
                    // A running cycle that already plays the matched clip near the matched
                    // phase carries on (no needless restart); anything else enters at the match.
                    bool sameSpot = string.Equals(mc.Id, motion.RenderClipId, StringComparison.Ordinal)
                                    && CircularDistance(motion.RenderPhase, m.Value.Row.Phase) < .15f;
                    if (!sameSpot || switching) { selected = mc; matchedPhase = m.Value.Row.Phase; }
                    motion.MotionMatchRowIndex = m.Value.RowIndex;
                }
            }
        }
        bool switchingToSelected = selected != null && !string.Equals(selected.Id, motion.RenderClipId, StringComparison.Ordinal);
        // ML-Flow-style contact lock: when approaching a timed contact, prefer the
        // selected clip's contact frame to land near the predicted arrival.
        if (selected != null && selected.HasContact && ttc > 0f && motion.IsApproachingBall)
        {
            if (switchingToSelected || motion.CurrentClipId.Length == 0)
            {
                float phaseMatched = selected.Loop ? Wrap01(motion.Phase) : 0f;
                matchedPhase = BallApproach.ContactLockedStartPhase(selected, ttc, phaseMatched, motion.ApproachWeight);
            }
        }
        if (selected == null)
        {
            if (motion.NextClipId.Length > 0) CommitTransition(motion);
            motion.PlaybackScale = 1f;
            UpdateFootPlants(motion, null, motion.Phase);
            return;
        }

        if (motion.CurrentClipId.Length == 0 && motion.NextClipId.Length == 0)
        {
            motion.CurrentClipId = selected.Id;
            motion.Phase = matchedPhase ?? (selected.Loop ? Wrap01(motion.Phase) : 0f);
            motion.BlendWeight = 1f;
        }
        else if (switchingToSelected || (matchedPhase != null && switchingToSelected))
        {
            // If a transition is interrupted, begin from its visible destination phase.
            if (motion.NextClipId.Length > 0) CommitTransition(motion);
            if (!_clips.TryGetValue(motion.CurrentClipId, out var from)) from = selected;
            float start = matchedPhase ?? ComputeStartPhase(from, selected, motion.Phase, intent, motion.ApproachWeight, ttc);
            if (selected.HasContact && ttc > 0f)
            {
                float contactPhase = selected.ContactFraction;
                float predPhase = Wrap01(start + ttc / MathF.Max(0.001f, selected.Duration));
                Metrics.RecordContact(CircularDistance(predPhase, contactPhase));
            }
            motion.NextClipId = selected.Id;
            motion.NextPhase = selected.Loop ? Wrap01(start) : Clamp01(start);
            motion.CrossfadeDuration = DefaultCrossfadeSeconds;
            motion.CrossfadeRemaining = motion.CrossfadeDuration;
            motion.BlendWeight = 0f;
        }
        else if (matchedPhase != null && string.Equals(selected.Id, motion.RenderClipId, StringComparison.Ordinal))
        {
            // Same clip: only nudge phase if far off contact alignment (avoid self-transition jitter).
            float currentP = motion.RenderPhase;
            if (CircularDistance(currentP, matchedPhase.Value) > 0.20f)
            {
                if (motion.NextClipId.Length > 0) CommitTransition(motion);
                motion.Phase = selected.Loop ? Wrap01(matchedPhase.Value) : Clamp01(matchedPhase.Value);
            }
        }

        var current = _clips.TryGetValue(motion.CurrentClipId, out var c) ? c : selected;
        float scale = PlaybackScale(selected, speed, intent, secondsUntilContact,
            motion.NextClipId.Length > 0 ? motion.NextPhase : motion.Phase);
        motion.PlaybackScale = scale;
        float oldPhase = motion.NextClipId.Length > 0 ? motion.NextPhase : motion.Phase;
        if (motion.NextClipId.Length > 0)
        {
            if (_clips.TryGetValue(motion.NextClipId, out var next))
                motion.NextPhase = AdvancePhase(next, motion.NextPhase, dt, scale);
            motion.Phase = AdvancePhase(current, motion.Phase, dt, PlaybackScale(current, speed, intent, secondsUntilContact, motion.Phase));
            motion.CrossfadeRemaining = Math.Max(0f, motion.CrossfadeRemaining - dt);
            motion.BlendWeight = motion.CrossfadeDuration <= 0f ? 1f
                : Mx.Clamp(1f - motion.CrossfadeRemaining / motion.CrossfadeDuration, 0f, 1f);
            if (motion.CrossfadeRemaining <= 0f) CommitTransition(motion);
        }
        else
        {
            motion.Phase = AdvancePhase(current, motion.Phase, dt, scale);
        }

        var visible = _clips.TryGetValue(motion.RenderClipId, out var visibleClip) ? visibleClip : selected;
        float visiblePhase = motion.RenderPhase;
        if (visible.HasContact && Crossed(oldPhase, visiblePhase, visible.ContactFraction, visible.Loop))
        {
            motion.ContactCrossed = true;
            motion.TimeSinceContact = 0f;
        }
        UpdateFootPlants(motion, visible, visiblePhase);
        var rv = visible.SampleRootVelocity(visiblePhase);
        motion.RootVelocitySampleX = rv.X;
        motion.RootVelocitySampleZ = rv.Y;
        motion.InContactWindow = visible.HasContactWindow
            ? (visiblePhase >= visible.ContactWindowStart && visiblePhase <= visible.ContactWindowEnd)
            : (visible.HasContact && CircularDistance(visiblePhase, visible.ContactFraction) < 0.08f);
        motion.LastPoseClipId = motion.RenderClipId;
        motion.LastPosePhase = motion.RenderPhase;
    }

    private MotionMatch? Match(MotionState motion, ClipMeta selected, BallState ball, PlayerIntent intent,
        float turnRate, string? styleTag, Vector2 localVel, Vector2 desiredVel, float secondsUntilContact,
        string? forcedClipId)
    {
        Span<float> pose = stackalloc float[8];
        string poseClip = motion.RenderClipId.Length > 0 ? motion.RenderClipId : motion.LastPoseClipId;
        float posePhase = motion.RenderClipId.Length > 0 ? motion.RenderPhase : motion.LastPosePhase;
        if (poseClip.Length == 0 || !Database!.TryGetPoseFeatures(poseClip, posePhase, pose)) pose.Clear();
        float ttc = secondsUntilContact > 0f ? secondsUntilContact : MotionFeatureLayout.NoContact;
        var features = MotionQuery.BuildFeatures(pose, localVel.X, localVel.Y, turnRate,
            desiredVel.X, desiredVel.Y, turnRate, ttc);
        string? forced = forcedClipId != null && _clips.ContainsKey(forcedClipId) ? forcedClipId
                       : selected.Dedicated ? selected.Id : null;
        var query = new MotionQuery(features, selected.Category, ball, intent, styleTag,
            selected.Loop ? motion.RenderClipId : null, motion.RenderPhase, forcedClipId: forced);
        return Database!.TrySearch(query, out var m) ? m : null;
    }

    public ClipMeta? SelectClip(PlayerIntent intent, BallState ball, float speed, float turnRate,
        float bodyTypeFactor = 1f, string? styleTag = null, float approachWeight = 0f, float timeToBallContact = -1f)
    {
        ClipCategory category = SelectCategory(intent, ball);
        if (category == ClipCategory.Locomotion && ball != BallState.Possessed && speed < .35f)
        {
            ClipMeta? idle = SelectBest(ClipCategory.Idle, BallState.None, 0f, 0f, 1f, styleTag, 0f, -1f);
            if (idle != null) return idle;
        }
        ClipMeta? best = SelectBest(category, ball, speed, turnRate, bodyTypeFactor, styleTag, approachWeight, timeToBallContact);
        if (best != null) return best;
        if (category != ClipCategory.Locomotion)
        {
            best = SelectBest(ClipCategory.Locomotion, ball, speed, turnRate, bodyTypeFactor, styleTag, approachWeight, timeToBallContact);
            if (best != null) return best;
        }
        return SelectBest(ClipCategory.Idle, BallState.None, 0f, 0f, 1f, null, 0f, -1f);
    }

    public static ClipCategory SelectCategory(PlayerIntent intent, BallState ball) => intent switch
    {
        PlayerIntent.Pass or PlayerIntent.ThroughBall => ClipCategory.Pass,
        PlayerIntent.Shoot => ClipCategory.Kick,
        PlayerIntent.Trap => ClipCategory.FirstTouch,
        PlayerIntent.Shield => ClipCategory.Shield,
        PlayerIntent.Cut => ClipCategory.Cut,
        PlayerIntent.Tackle => ClipCategory.Tackle,
        PlayerIntent.Dive => ClipCategory.KeeperDive,
        PlayerIntent.Celebrate => ClipCategory.Celebrate,
        PlayerIntent.SprintStop => ClipCategory.Recovery,
        _ when ball == BallState.Approaching => ClipCategory.Approach,
        _ when ball == BallState.Possessed => ClipCategory.Locomotion,
        _ => ClipCategory.Locomotion,
    };

    public static float ComputeStartPhase(ClipMeta from, ClipMeta to, float currentPhase, PlayerIntent intent,
        float approachWeight = 0f, float timeToBallContact = -1f)
    {
        if (!to.Loop || IsOneShot(to.Category) || intent is PlayerIntent.Pass or PlayerIntent.ThroughBall
            or PlayerIntent.Shoot or PlayerIntent.Trap or PlayerIntent.Tackle or PlayerIntent.Dive
            or PlayerIntent.Celebrate)
        {
            float start = 0f;
            if (to.HasContact && timeToBallContact > 0f && approachWeight > 0.05f)
                start = BallApproach.ContactLockedStartPhase(to, timeToBallContact, 0f, approachWeight);
            return start;
        }
        if (from.Loop && IsLocomotion(from.Category) && IsLocomotion(to.Category))
        {
            float phase = AlignToNearestFootEvent(from, to, currentPhase);
            if (to.HasContact && timeToBallContact > 0f && approachWeight > 0.05f)
                phase = BallApproach.ContactLockedStartPhase(to, timeToBallContact, phase, approachWeight);
            return phase;
        }
        float basePhase = Clamp01(currentPhase);
        if (to.HasContact && timeToBallContact > 0f && approachWeight > 0.05f)
            basePhase = BallApproach.ContactLockedStartPhase(to, timeToBallContact, basePhase, approachWeight);
        return basePhase;
    }

    public static float AlignToNearestFootEvent(ClipMeta from, ClipMeta to, float phase)
    {
        if (from.FootPlantFrames.Length == 0 || to.FootPlantFrames.Length == 0)
            return Wrap01(phase);
        int nearest = 0;
        float bestDistance = float.MaxValue;
        for (int i = 0; i < from.FootPlantFrames.Length; i++)
        {
            float d = CircularDistance(phase, from.FootPlantFrames[i]);
            if (d < bestDistance) { bestDistance = d; nearest = i; }
        }

        float sourcePlant = from.FootPlantFrames[nearest];
        FootSide side = from.FootPlantSideAt(nearest);
        int targetIndex = -1;
        bestDistance = float.MaxValue;
        for (int i = 0; i < to.FootPlantFrames.Length; i++)
        {
            if (to.FootPlantSideAt(i) != side) continue;
            float d = CircularDistance(sourcePlant, to.FootPlantFrames[i]);
            if (d < bestDistance) { bestDistance = d; targetIndex = i; }
        }
        if (targetIndex < 0) return Wrap01(phase);
        return Wrap01(to.FootPlantFrames[targetIndex] + CircularDifference(phase, sourcePlant));
    }

    public static float AdvancePhase(ClipMeta clip, float phase, float dt, float playbackScale)
    {
        if (clip.Duration <= 1e-6f || dt <= 0f) return clip.Loop ? Wrap01(phase) : Clamp01(phase);
        float advanced = phase + dt * Math.Max(0f, playbackScale) / clip.Duration;
        return clip.Loop ? Wrap01(advanced) : Clamp01(advanced);
    }

    public static float ContactAlignedPlaybackScale(ClipMeta clip, float secondsUntilContact)
    {
        if (!clip.HasContact || clip.ContactFraction <= 0f || secondsUntilContact <= .001f) return 1f;
        return ActionTiming.ContactAlignedPlaybackScale(clip.Duration, clip.ContactFraction, secondsUntilContact);
    }

    private ClipMeta? SelectBest(ClipCategory category, BallState ball, float speed,
        float turnRate, float bodyTypeFactor, string? styleTag,
        float approachWeight = 0f, float timeToBallContact = -1f)
    {
        ClipMeta? best = null;
        float bestScore = float.MaxValue;
        bool exactBallStateExists = false;
        bool neutralBallStateExists = false;
        foreach (var c in _ordered)
        {
            if (c.Category != category) continue;
            if (c.BallState == ball) exactBallStateExists = true;
            if (c.BallState == BallState.None) neutralBallStateExists = true;
        }
        foreach (var c in _ordered)
        {
            if (c.Dedicated) continue;
            if (c.Category != category || (exactBallStateExists && c.BallState != ball)
                || (!exactBallStateExists && neutralBallStateExists && c.BallState != BallState.None)) continue;
            float speedError = MathF.Abs(c.PreferredSpeed - speed) * Math.Clamp(bodyTypeFactor, .5f, 1.5f);
            float turnError = MathF.Abs(c.PreferredTurnRate - turnRate) * .35f;
            float rootError = MathF.Abs(c.RootVelocityAvg.Length() - speed) * .15f;
            float tagBonus = styleTag != null && Array.Exists(c.Tags, t =>
                string.Equals(t, styleTag, StringComparison.OrdinalIgnoreCase)) ? -.1f : 0f;
            float score = speedError + turnError + rootError + tagBonus;
            if (approachWeight > 0.05f)
            {
                score += BallApproach.ContactTimingCost(c, timeToBallContact) * approachWeight;
                score += BallApproach.StrideShorteningCost(c, speed, approachWeight);
            }
            if (score < bestScore) { bestScore = score; best = c; }
        }
        return best;
    }

    private static float PlaybackScale(ClipMeta clip, float speed, PlayerIntent intent, float secondsUntilContact, float phase)
    {
        if (clip.HasContact && secondsUntilContact > 0f)
            return ContactAlignedPlaybackScale(clip, secondsUntilContact);
        if (clip.PreferredSpeed > 0.1f && speed > 0.05f && IsLocomotion(clip.Category))
            return Math.Clamp(speed / clip.PreferredSpeed, 0.55f, 1.65f);
        return 1f;
    }

    private void CommitTransition(MotionState state)
    {
        if (state.NextClipId.Length == 0) return;
        state.CurrentClipId = state.NextClipId;
        state.Phase = state.NextPhase;
        state.NextClipId = "";
        state.NextPhase = 0f;
        state.CrossfadeRemaining = 0f;
        state.BlendWeight = 1f;
        Metrics.TransitionEvents++;
    }

    private const float PlantEdgeThreshold = 0.5f;

    private void UpdateFootPlants(MotionState state, ClipMeta? clip, float phase)
    {
        float prevL = state.PlantWeightLeft;
        float prevR = state.PlantWeightRight;
        state.PrevPlantWeightLeft = prevL;
        state.PrevPlantWeightRight = prevR;
        state.FootPlantedLeft = state.FootPlantedRight = false;
        state.PlantWeightLeft = 0f;
        state.PlantWeightRight = 0f;
        if (clip == null) return;

        state.PlantWeightLeft = clip.SamplePlantWeight(true, phase);
        state.PlantWeightRight = clip.SamplePlantWeight(false, phase);

        if (clip.HasPlantCurves || clip.FootPlantFrames.Length == 0)
        {
            state.FootPlantedLeft = state.PlantWeightLeft >= PlantEdgeThreshold;
            state.FootPlantedRight = state.PlantWeightRight >= PlantEdgeThreshold;
        }
        else
        {
            for (int i = 0; i < clip.FootPlantFrames.Length; i++)
            {
                if (!NearPlant(phase, clip.FootPlantFrames[i])) continue;
                if (clip.FootPlantSideAt(i) == FootSide.Left) state.FootPlantedLeft = true;
                else state.FootPlantedRight = true;
            }
            if (state.FootPlantedLeft) state.PlantWeightLeft = MathF.Max(state.PlantWeightLeft, 1f);
            if (state.FootPlantedRight) state.PlantWeightRight = MathF.Max(state.PlantWeightRight, 1f);
        }

        if (state.PlantWeightLeft >= PlantEdgeThreshold && prevL < PlantEdgeThreshold)
        {
            state.FootstepLeft = true;
            Metrics.RecordFootstep();
        }
        if (state.PlantWeightRight >= PlantEdgeThreshold && prevR < PlantEdgeThreshold)
        {
            state.FootstepRight = true;
            Metrics.RecordFootstep();
        }
    }

    private static bool NearPlant(float phase, float plant) => CircularDistance(phase, plant) <= .035f;
    private static bool Crossed(float before, float after, float eventPhase, bool loop) =>
        loop ? (before <= after ? before < eventPhase && after >= eventPhase
                                : eventPhase > before || eventPhase <= after)
             : before < eventPhase && after >= eventPhase;
    private static float CircularDistance(float a, float b) => MathF.Abs(CircularDifference(a, b));
    private static float CircularDifference(float a, float b)
    {
        float d = (a - b) % 1f;
        if (d > .5f) d -= 1f;
        if (d < -.5f) d += 1f;
        return d;
    }
    private static float MoveToward(float current, float target, float maxDelta)
    {
        if (MathF.Abs(target - current) <= maxDelta) return target;
        return current + MathF.Sign(target - current) * maxDelta;
    }
    private static float Wrap01(float v) => v - MathF.Floor(v);
    private static float Clamp01(float v) => Math.Clamp(v, 0f, 1f);
    private static bool IsOneShot(ClipCategory c) => c is ClipCategory.FirstTouch or ClipCategory.Cut
        or ClipCategory.Kick or ClipCategory.Pass or ClipCategory.Tackle or ClipCategory.KeeperDive
        or ClipCategory.Celebrate or ClipCategory.Recovery;
    private static bool IsLocomotion(ClipCategory c) => c is ClipCategory.Locomotion or ClipCategory.Idle;
}
