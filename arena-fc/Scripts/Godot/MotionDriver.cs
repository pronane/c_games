// Godot boundary for the pure-C# MotionEngine. It samples the authoritative
// MatchState after a fixed tick and sends presentation-only clip/phase state to rigs.
using System;
using System.Collections.Generic;
using ArenaFC.Core;
using ArenaFC.Core.Animation;
using Godot;

namespace ArenaFC.GodotGame;

public sealed class MotionDriver
{
    private sealed class Slot
    {
        public MotionState State = new();
        public float LastYaw;
        public bool HasYaw;
        public int LastTick;
        public bool HasTick;
        public string LastAction = "";
    }

    private readonly MotionEngine _engine = new();
    private Slot[] _slots = Array.Empty<Slot>();

    public bool IsLoaded => _engine.ClipCount > 0;
    public int ClipCount => _engine.ClipCount;

    public bool LoadManifest(string json)
    {
        try
        {
            _engine.LoadClips(ClipManifestLoader.Parse(json));
            return IsLoaded;
        }
        catch (Exception ex)
        {
            GD.PushWarning($"AME manifest disabled; keeping SoccerClipRig fallback: {ex.Message}");
            return false;
        }
    }

    public void EnsureCapacity(int count)
    {
        if (_slots.Length == count) return;
        var resized = new Slot[count];
        for (int i = 0; i < count; i++)
        {
            resized[i] = i < _slots.Length ? _slots[i] : new Slot
            {
                State = new MotionState { Phase = MotionEngine.InitialPhase(i) }
            };
        }
        _slots = resized;
    }

    /// <summary>Returns null when the manifest is absent, preserving the existing rig selector.</summary>
    public MotionState? UpdatePlayer(int index, PlayerState player, ArenaFC.Core.BallState ball,
        bool ownsBall, int currentTick)
    {
        if (!IsLoaded || index < 0 || index >= _slots.Length) return null;
        var slot = _slots[index];
        int elapsedTicks = slot.HasTick ? Math.Max(0, currentTick - slot.LastTick) : 0;
        slot.LastTick = Math.Max(slot.LastTick, currentTick);
        slot.HasTick = true;
        float dt = elapsedTicks * MatchEngine.Dt;
        float yaw = MathF.Atan2(player.Facing.X, player.Facing.Z);
        float turnRate = 0f;
        if (slot.HasYaw && dt > 1e-5f) turnRate = Mx.AngleDiff(yaw, slot.LastYaw) / dt;
        slot.LastYaw = yaw;
        slot.HasYaw = true;

        float distance = Mx.FlatDist(player.Pos, ball.Pos);
        ArenaFC.Core.Animation.BallState ballContext = ball.Pos.Y > 1.3f && ball.Owner < 0
            ? ArenaFC.Core.Animation.BallState.Aerial
            : ownsBall ? ArenaFC.Core.Animation.BallState.Possessed
            : ball.Owner >= 0 && distance < 3.5f ? ArenaFC.Core.Animation.BallState.Contested
            : distance < 7f ? ArenaFC.Core.Animation.BallState.Approaching : ArenaFC.Core.Animation.BallState.None;
        PlayerIntent intent = IntentFor(player);
        if (ball.HasPending && ball.PendingFrom == player.Index && ball.PendingReceiver >= 0)
            intent = PlayerIntent.Pass;
        bool actionClip = intent is PlayerIntent.Pass or PlayerIntent.ThroughBall or PlayerIntent.Shoot
            or PlayerIntent.Trap or PlayerIntent.Tackle or PlayerIntent.Dive or PlayerIntent.Celebrate or PlayerIntent.Cut;
        if (!actionClip) slot.LastAction = "";
        else if (!string.Equals(slot.LastAction, player.Action, StringComparison.Ordinal))
        {
            // A repeated one-shot (even the same clip) is a fresh presentation event.
            // Reset only render state; match action timers and ball events are untouched.
            slot.State.CurrentClipId = "";
            slot.State.NextClipId = "";
            slot.State.Phase = 0f;
            slot.State.NextPhase = 0f;
            slot.State.CrossfadeRemaining = 0f;
            slot.State.BlendWeight = 1f;
            slot.State.TimeSinceContact = 0f;
            slot.LastAction = player.Action;
        }
        float elapsedAction = Math.Max(0f, player.ActionDuration - player.ActionTimer);
        float untilContact = player.ActionContactAt > 0f
            ? Math.Max(0f, player.ActionContactAt - elapsedAction) : -1f;
        float speed = Mx.Flat(player.Vel).Length();
        _engine.Update(slot.State, speed, turnRate, ballContext, intent, dt, untilContact,
            styleTag: player.Spec.Archetype.ToString().ToLowerInvariant());
        return slot.State;
    }

    private static PlayerIntent IntentFor(PlayerState p)
    {
        if (p.ActionTimer > 0f)
        {
            return p.Action switch
            {
                "kick" or "volley" or "shoot" => PlayerIntent.Shoot,
                "pass" or "short_pass" => PlayerIntent.Pass,
                "through_ball" or "cross" or "throw_in" => PlayerIntent.ThroughBall,
                "trap" or "chest_control" or "header" or "pickup" => PlayerIntent.Trap,
                "tackle" or "slide" or "shoulder_charge" => PlayerIntent.Tackle,
                "dive" or "keeper_dive" => PlayerIntent.Dive,
                "celebrate" => PlayerIntent.Celebrate,
                "cut" or "turn" => PlayerIntent.Cut,
                _ => p.Shielding ? PlayerIntent.Shield : PlayerIntent.Move,
            };
        }
        if (p.Shielding) return PlayerIntent.Shield;
        if (p.Sprinting) return PlayerIntent.Sprint;
        if (p.Action == "turn") return PlayerIntent.Cut;
        return PlayerIntent.Move;
    }
}
