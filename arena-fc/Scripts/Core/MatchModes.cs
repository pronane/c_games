// Arena FC - Training ground and penalty shootout rules for the match engine.
//
// Before this file both modes were normal matches in disguise: Training only
// switched fouls/offside off, and the shootout restarted into open play with
// all 22 players free after the first penalty.  Here:
//   * Shootout: only the taker and the defending keeper move; everyone else
//     waits in the centre circle; the clock is stopped; best of five then
//     sudden death, decided as soon as one side cannot be caught.
//   * Training: no clock, endless stamina, and short resettable drills
//     (Attack: your team vs their keeper; Defend: 1v1 against an attacker)
//     that the TrainingCoach switches between lesson by lesson.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>Training drill layouts.</summary>
public enum TrainingDrill
{
    /// <summary>Your whole team with the ball against their keeper only.</summary>
    Attack,
    /// <summary>One attacker runs at your back line; you defend.</summary>
    Defend,
}

public sealed partial class MatchEngine
{
    public const int ModeTraining = 2;
    public const int ModeShootout = 3;
    public bool IsTraining => Options.Mode == ModeTraining;
    public bool IsShootout => Options.Mode == ModeShootout;

    /// <summary>Current training drill (Mode 2 only).</summary>
    public TrainingDrill Drill { get; private set; } = TrainingDrill.Attack;
    /// <summary>The live attacker in the Defend drill.</summary>
    public int TrainingAttacker { get; private set; } = -1;
    private float _trainingResetTimer = -1f;
    private float _trainingLooseTime;

    /// <summary>Does this player take part in the simulation this tick?
    /// Inactive players stand still, never pick the ball up and never tackle.</summary>
    public bool IsActive(PlayerState p)
    {
        if (p.SentOff) return false;
        var S = State;
        if (IsShootout)
        {
            if (p.IsKeeper) return p.Team != S.ShootoutTakerSide;
            return p.Index == S.ShootoutTaker && !S.ShootoutShotTaken;
        }
        if (IsSkill) return SkillActive(p);
        if (IsTraining)
        {
            if (p.IsKeeper) return true;
            if (Drill == TrainingDrill.Attack) return p.Team == 0;
            return p.Index == TrainingAttacker || p.Index == S.Controlled;
        }
        return true;
    }

    private static void HoldStill(PlayerState p)
    {
        p.Vel = Vector3.Zero;
        p.Target = p.Pos;
        p.Pressing = false;
        p.Shielding = false;
        if (p.ActionTimer <= 0f) p.Action = "idle";
    }

    // ------------------------------------------------------------------ shootout

    /// <summary>Taker rotation: every outfield player in turn, then round again.</summary>
    private int ShootoutTakerFor(int side)
    {
        int kicks = side == 0 ? State.ShootoutKicksHome : State.ShootoutKicksAway;
        int outfield = Math.Max(1, Options.TeamSize - 1);
        for (int k = 0; k < outfield; k++)
        {
            int idx = side * Options.TeamSize + 1 + ((kicks + k) % outfield);
            if (!State.Players[idx].SentOff) return idx;
        }
        return side * Options.TeamSize + 1;
    }

    /// <summary>Put the ball on the spot, the taker behind it, the defending keeper on
    /// his line and everybody else in the centre circle.</summary>
    private void SetupShootoutKick()
    {
        var S = State;
        int side = S.ShootoutTakerSide;
        int sign = SideSign(side);
        var b = S.Ball;
        b.Owner = -1; b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1;
        b.Vel = Vector3.Zero; b.Spin = Vector3.Zero; b.NoPickup = 0;
        b.Pos = new Vector3(sign * (Mx.HalfLength - 11f), Mx.BallRadius, 0);
        int taker = ShootoutTakerFor(side);
        S.ShootoutTaker = taker;
        int[] waiting = new int[2];
        foreach (var p in S.Players)
        {
            p.Vel = Vector3.Zero; p.ActionTimer = 0f; p.Action = "idle";
            p.PossessionLock = 0f; p.MustPlayBall = false;
            if (p.SentOff) continue;
            if (p.Index == taker)
            {
                p.Pos = b.Pos - new Vector3(sign * 1.2f, 0, 0);
                p.Facing = new Vector3(sign, 0, 0);
            }
            else if (p.IsKeeper && p.Team != side)
            {
                p.Pos = new Vector3(sign * (Mx.HalfLength - .3f), 0, 0);
                p.Facing = new Vector3(-sign, 0, 0);
            }
            else if (p.IsKeeper)
            {
                // The shooting side's keeper waits on the edge of the area.
                p.Pos = new Vector3(sign * (Mx.HalfLength - 19f), 0, Mx.GoalHalfWidth * 3.2f);
                p.Facing = new Vector3(sign, 0, 0);
            }
            else
            {
                int n = waiting[p.Team]++;
                float x = (p.Team == 0 ? -1.4f : 1.4f) + (n % 2 == 0 ? 0f : (p.Team == 0 ? -1f : 1f));
                p.Pos = new Vector3(x, 0, -6f + n * 1.2f);
                p.Facing = new Vector3(sign, 0, 0);
            }
            p.Target = p.Pos;
        }
        // The user always takes their own penalties; on the computer's kicks no
        // one is human-driven, but the ring sits on our keeper for the HUD.
        S.Controlled = side == 0 ? taker : 0;
        S.ControlLock = 99f;
        S.ShootoutShotTaken = false;
        S.ShootoutTimer = 0f;
        S.RestartSide = side;
        S.RestartPos = b.Pos;
    }

    /// <summary>Is the shootout settled?  Best of five, stopping as soon as one side
    /// cannot be caught; then sudden death after each pair of kicks.</summary>
    public static bool ShootoutDecided(int kicksHome, int kicksAway, int goalsHome, int goalsAway)
    {
        if (kicksHome <= 5 && kicksAway <= 5 && (kicksHome < 5 || kicksAway < 5))
        {
            int remHome = 5 - kicksHome, remAway = 5 - kicksAway;
            return goalsHome > goalsAway + remAway || goalsAway > goalsHome + remHome;
        }
        return kicksHome == kicksAway && goalsHome != goalsAway;
    }

    // ------------------------------------------------------------------ training

    /// <summary>Switch to a drill and lay it out.  Safe to call at any time.</summary>
    public void SetDrill(TrainingDrill drill)
    {
        if (!IsTraining) return;
        SetupDrill(drill);
    }

    /// <summary>Lay the current drill out again (ball back at your feet).</summary>
    public void ResetDrill() => SetDrill(Drill);

    private void SetupDrill(TrainingDrill drill)
    {
        var S = State;
        Drill = drill;
        _trainingResetTimer = -1f;
        _trainingLooseTime = 0f;
        ResetPositions(true);
        var b = S.Ball;
        b.Owner = -1; b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1;
        b.Vel = Vector3.Zero; b.Spin = Vector3.Zero; b.NoPickup = 0;
        int attack = SideSign(0);
        int ts = Options.TeamSize;
        // Computer outfielders not in the drill watch from beside the far touchline.
        int spot = 0;
        for (int i = 1; i < ts; i++)
        {
            var q = S.Players[ts + i];
            q.Pos = new Vector3(-12f + spot++ * 2.4f, 0, -(Mx.HalfWidth + 1.8f));
            q.Target = q.Pos; q.Vel = Vector3.Zero; q.Facing = Vector3.UnitZ;
            q.Action = "idle"; q.ActionTimer = 0f;
        }
        if (drill == TrainingDrill.Attack)
        {
            TrainingAttacker = -1;
            // Start in the opposition half with the ball at a midfielder's feet.
            int carrier = Math.Min(ts - 1, Math.Max(1, ts / 2));
            var c = S.Players[carrier];
            c.Pos = new Vector3(attack * 8f, 0, 0);
            c.Facing = new Vector3(attack, 0, 0);
            foreach (var p in S.Players)
                if (p.Team == 0 && !p.IsKeeper && p.Index != carrier)
                    p.Pos += new Vector3(attack * 18f, 0, 0);
            foreach (var p in S.Players) p.Target = p.Pos;
            b.Pos = c.Pos + new Vector3(attack * .6f, Mx.BallRadius, 0);
            b.Owner = carrier;
            b.LastTouch = carrier; b.LastTouchSide = 0;
            S.Controlled = carrier;
        }
        else
        {
            // One computer striker runs at goal; your nearest defender meets him.
            int striker = ts * 2 - 1;
            TrainingAttacker = striker;
            var a = S.Players[striker];
            float ownGoalX = OwnGoalPos(0).X;
            a.Pos = new Vector3(ownGoalX + attack * 34f, 0, 0);
            a.Facing = new Vector3(-attack, 0, 0);
            a.Target = a.Pos;
            int defender = 1;
            var d = S.Players[defender];
            d.Pos = new Vector3(ownGoalX + attack * 22f, 0, 0);
            d.Facing = new Vector3(attack, 0, 0);
            d.Target = d.Pos;
            b.Pos = a.Pos - new Vector3(attack * .6f, -Mx.BallRadius, 0);
            b.Owner = striker;
            b.LastTouch = striker; b.LastTouchSide = 1;
            S.Controlled = defender;
        }
        S.ControlLock = .6f;
        S.Phase = Phase.Play;
        S.PhaseTimer = 0f;
    }

    /// <summary>Per-tick training upkeep: endless stamina and automatic drill resets.</summary>
    private void TrainingTick(float dt)
    {
        var S = State;
        foreach (var p in S.Players) p.Stamina = 1f;
        if (S.Phase != Phase.Play) return;
        var b = S.Ball;
        bool reset = false;
        if (Drill == TrainingDrill.Attack)
        {
            // Their keeper has it, or the ball is lying dead: start the drill again.
            if (b.Owner >= 0 && S.Players[b.Owner].Team == 1) reset = true;
        }
        else
        {
            // You won it (or it went loose away from the attacker): go again.
            if (b.Owner >= 0 && S.Players[b.Owner].Team == 0) reset = true;
        }
        if (b.Owner < 0 && b.Vel.LengthSquared() < .04f) _trainingLooseTime += dt; else _trainingLooseTime = 0f;
        if (_trainingLooseTime > 2.5f) reset = true;
        if (reset && _trainingResetTimer < 0f) _trainingResetTimer = 1.4f;
        if (_trainingResetTimer >= 0f)
        {
            _trainingResetTimer -= dt;
            if (_trainingResetTimer < 0f) SetupDrill(Drill);
        }
    }
}
