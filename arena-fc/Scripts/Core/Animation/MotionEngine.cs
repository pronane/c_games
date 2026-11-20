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
        float bodyTypeFactor = 1f, string? styleTag = null)
    {
        if (motion == null) throw new ArgumentNullException(nameof(motion));
        dt = Math.Max(0f, dt);
        motion.ContactCrossed = false;
        motion.Speed = Math.Max(0f, speed);
        motion.TurnRate = turnRate;
        motion.Ball = ball;
        motion.LastIntent = intent;
        motion.TimeSinceContact += dt;

        ClipMeta? selected = SelectClip(intent, ball, speed, turnRate, bodyTypeFactor, styleTag);
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
            motion.Phase = selected.Loop ? Wrap01(motion.Phase) : 0f;
            motion.BlendWeight = 1f;
        }
        else if (!string.Equals(selected.Id, motion.RenderClipId, StringComparison.Ordinal))
        {
            // If a transition is interrupted, begin from its visible destination phase.
            if (motion.NextClipId.Length > 0) CommitTransition(motion);
            if (!_clips.TryGetValue(motion.CurrentClipId, out var from)) from = selected;
            float start = ComputeStartPhase(from, selected, motion.Phase, intent);
            motion.NextClipId = selected.Id;
            motion.NextPhase = selected.Loop ? Wrap01(start) : Clamp01(start);
            motion.CrossfadeDuration = DefaultCrossfadeSeconds;
            motion.CrossfadeRemaining = motion.CrossfadeDuration;
            motion.BlendWeight = 0f;
        }

        var current = _clips.TryGetValue(motion.CurrentClipId, out var c) ? c : selected;
        float scale = PlaybackScale(selected, speed, intent, secondsUntilContact);
        motion.PlaybackScale = scale;
        float oldPhase = motion.NextClipId.Length > 0 ? motion.NextPhase : motion.Phase;
        if (motion.NextClipId.Length > 0)
        {
            if (_clips.TryGetValue(motion.NextClipId, out var next))
                motion.NextPhase = AdvancePhase(next, motion.NextPhase, dt, scale);
            motion.Phase = AdvancePhase(current, motion.Phase, dt, PlaybackScale(current, speed, intent, secondsUntilContact));
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
    }

    public ClipMeta? SelectClip(PlayerIntent intent, BallState ball, float speed, float turnRate,
        float bodyTypeFactor = 1f, string? styleTag = null)
    {
        ClipCategory category = SelectCategory(intent, ball);
        ClipMeta? best = SelectBest(category, ball, speed, turnRate, bodyTypeFactor, styleTag);
        if (best != null) return best;
        if (category != ClipCategory.Locomotion)
        {
            best = SelectBest(ClipCategory.Locomotion, ball, speed, turnRate, bodyTypeFactor, styleTag);
            if (best != null) return best;
        }
        return SelectBest(ClipCategory.Idle, BallState.None, 0f, 0f, 1f, null);
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

    public static float ComputeStartPhase(ClipMeta from, ClipMeta to, float currentPhase, PlayerIntent intent)
    {
        if (!to.Loop || IsOneShot(to.Category) || intent is PlayerIntent.Pass or PlayerIntent.ThroughBall
            or PlayerIntent.Shoot or PlayerIntent.Trap or PlayerIntent.Tackle or PlayerIntent.Dive
            or PlayerIntent.Celebrate)
            return 0f;
        if (from.Loop && IsLocomotion(from.Category) && IsLocomotion(to.Category))
            return AlignToNearestFootEvent(from, to, currentPhase);
        return Clamp01(currentPhase);
    }

    /// <summary>Map the nearest source plant to the nearest target plant for that same
    /// side, preserving the circular offset from the source event. Legacy metadata
    /// infers alternating Left/Right sides from event order.</summary>
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
        float turnRate, float bodyTypeFactor, string? styleTag)
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
            if (c.Category != category || (exactBallStateExists && c.BallState != ball)
                || (!exactBallStateExists && neutralBallStateExists && c.BallState != BallState.None)) continue;
            float speedError = MathF.Abs(c.PreferredSpeed - speed) * Math.Clamp(bodyTypeFactor, .5f, 1.5f);
            float turnError = MathF.Abs(c.PreferredTurnRate - turnRate) * .35f;
            float rootError = MathF.Abs(c.RootVelocityAvg.Length() - speed) * .15f;
            float tagBonus = styleTag != null && Array.Exists(c.Tags, t =>
                string.Equals(t, styleTag, StringComparison.OrdinalIgnoreCase)) ? -.1f : 0f;
            float score = speedError + turnError + rootError + tagBonus;
            if (score < bestScore) { bestScore = score; best = c; }
        }
        return best;
    }

    private static float PlaybackScale(ClipMeta clip, float speed, PlayerIntent intent, float secondsUntilContact)
    {
        if (clip.HasContact && secondsUntilContact > .001f)
            return ContactAlignedPlaybackScale(clip, secondsUntilContact);
        if (IsLocomotion(clip.Category) && clip.PreferredSpeed > .1f)
            return Math.Clamp(speed / clip.PreferredSpeed, .45f, 2.8f);
        return 1f;
    }

    private void CommitTransition(MotionState state)
    {
        if (state.NextClipId.Length == 0) return;
        state.CurrentClipId = state.NextClipId;
        state.Phase = state.NextPhase;
        state.NextClipId = "";
        state.NextPhase = state.Phase;
        state.CrossfadeRemaining = 0f;
        state.BlendWeight = 1f;
    }

    private static void UpdateFootPlants(MotionState state, ClipMeta? clip, float phase)
    {
        state.FootPlantedLeft = state.FootPlantedRight = false;
        if (clip == null || clip.FootPlantFrames.Length == 0) return;
        for (int i = 0; i < clip.FootPlantFrames.Length; i++)
        {
            if (!NearPlant(phase, clip.FootPlantFrames[i])) continue;
            if (clip.FootPlantSideAt(i) == FootSide.Left) state.FootPlantedLeft = true;
            else state.FootPlantedRight = true;
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
    private static float Wrap01(float v) => v - MathF.Floor(v);
    private static float Clamp01(float v) => Math.Clamp(v, 0f, 1f);
    private static bool IsOneShot(ClipCategory c) => c is ClipCategory.FirstTouch or ClipCategory.Cut
        or ClipCategory.Kick or ClipCategory.Pass or ClipCategory.Tackle or ClipCategory.KeeperDive
        or ClipCategory.Celebrate or ClipCategory.Recovery;
    private static bool IsLocomotion(ClipCategory c) => c is ClipCategory.Locomotion or ClipCategory.Idle;
}
