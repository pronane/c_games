// Arena FC - networked/deterministic half of MatchEngine.
//
// Kept in a partial file so the offline game loop in Match.cs stays untouched.
// This is the layer the missing snapshot talked about: one authoritative tick can
// carry commands for several humans, and a complete engine checkpoint can be
// captured/restored for rollback, mid-match resume and peer-host handoff.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using ArenaFC.Core.Net;

namespace ArenaFC.Core;

public sealed class EngineCheckpoint
{
    public int Tick;
    public MatchState State = new();
    public uint Rng;
    public float Acc;
    public float GlobalTime;
    public List<MatchEvent> Events = new();
}

public sealed partial class MatchEngine
{
    public int CurrentTick
    {
        get => _tick;
        set => _tick = value;
    }

    /// <summary>Everything needed to re-seat a peer host / hard-reset a predictor.</summary>
    public (uint Rng, float Gt, int Tick, float Acc) Timing => (Rng.State, _globalTime, _tick, _acc);

    /// <summary>Clone another engine's complete live state into this one (same options).</summary>
    public void CopyFrom(MatchEngine other)
    {
        OverwriteState(other.State);
        Rng.State = other.Rng.State;
        _acc = other._acc;
        _globalTime = other._globalTime;
        _tick = other._tick;
        Events.Clear();
        Events.AddRange(other.Events.Select(CloneEvent));
    }

    /// <summary>One authoritative fixed tick with per-player human commands.</summary>
    public void StepNetwork(float dt, Dictionary<int, PlayerCommand> cmds) =>
        Tick(dt <= 0f ? Dt : dt, PlayerCommand.None, cmds);

    /// <summary>Exact 1/60 s step (used by replay, checkpoints and the server loop).</summary>
    public void StepOneTick(Dictionary<int, PlayerCommand> cmds) =>
        Tick(Dt, PlayerCommand.None, cmds);

    /// <summary>Nearest outfield player of the requested team to a world position.</summary>
    public int FindNearestForTeam(int team, Vector3 pos, bool excludeKeeper = true)
    {
        int start = team * Options.TeamSize;
        int best = -1;
        float bd = float.MaxValue;
        for (int i = start; i < start + Options.TeamSize && i < State.Players.Length; i++)
        {
            var p = State.Players[i];
            if (excludeKeeper && p.IsKeeper) continue;
            float d = Mx.FlatDist2(p.Pos, pos);
            if (d < bd) { bd = d; best = i; }
        }
        return best;
    }

    public EngineCheckpoint Capture() => new()
    {
        Tick = _tick,
        State = CloneState(State),
        Rng = Rng.State,
        Acc = _acc,
        GlobalTime = _globalTime,
        Events = Events.Select(CloneEvent).ToList(),
    };

    public void Restore(EngineCheckpoint c)
    {
        OverwriteState(c.State);
        Rng.State = c.Rng;
        _acc = c.Acc;
        _globalTime = c.GlobalTime;
        _tick = c.Tick;
        Events.Clear();
        Events.AddRange(c.Events.Select(CloneEvent));
    }

    /// <summary>Rewind to an authoritative snapshot state (rollback / reconnect).</summary>
    public void RestoreFrom(MatchState authoritative, uint rng, float globalTime, int tick)
    {
        OverwriteState(authoritative);
        Rng.State = rng;
        _globalTime = globalTime;
        _acc = 0f;
        _tick = tick;
    }

    /// <summary>Set only the timing/RNG words (snapshot application on a mirror engine).</summary>
    public void RestoreTiming(uint rng, float globalTime, int tick)
    {
        Rng.State = rng;
        _globalTime = globalTime;
        _acc = 0f;
        _tick = tick;
    }

    /// <summary>Overlay the networked fields of an authoritative state on a restored
    /// checkpoint, keeping the checkpoint's internal timers (RNG, decision, locks…).
    /// This is the rollback correction: the wire snapshot is intentionally compact.</summary>
    public void ApplyAuthoritative(MatchState authoritative, uint rng, float globalTime, int tick)
    {
        var s = State;
        int n = Math.Min(s.Players.Length, authoritative.Players.Length);
        for (int i = 0; i < n; i++)
        {
            var src = authoritative.Players[i];
            var dst = s.Players[i];
            dst.Pos = src.Pos;
            dst.Vel = src.Vel;
            dst.Facing = src.Facing;
            dst.Action = src.Action;
        }
        s.Ball.Pos = authoritative.Ball.Pos;
        s.Ball.Vel = authoritative.Ball.Vel;
        s.Ball.Owner = authoritative.Ball.Owner;
        s.Score = (int[])authoritative.Score.Clone();
        s.Clock = authoritative.Clock;
        s.Phase = authoritative.Phase;
        s.Half = authoritative.Half;
        s.Controlled = authoritative.Controlled;
        s.ControlledAway = authoritative.ControlledAway;
        s.Commentary = authoritative.Commentary;
        RestoreTiming(rng, globalTime, tick);
    }

    /// <summary>Apply a full v2 state checkpoint (join / replay / host migration).
    /// Mutates the existing player objects so their immutable CharacterSpec survives.</summary>
    public void ApplyFull(FullStateDto f)
    {
        var s = State;
        int n = Math.Min(f.Players.Length, s.Players.Length);
        for (int i = 0; i < n; i++)
        {
            var d = f.Players[i];
            var p = s.Players[i];
            p.Pos = new Vector3(d.X, 0f, d.Z);
            p.Vel = new Vector3(d.Vx, 0f, d.Vz);
            p.Facing = new Vector3(d.Fx, 0f, d.Fz);
            p.Home = new Vector3(d.Hx, 0f, d.Hz);
            p.Target = new Vector3(d.Tx, 0f, d.Tz);
            p.Stamina = d.St; p.AnimPhase = d.Ap; p.ActionTimer = d.At;
            p.DecisionTimer = d.Dt; p.PossessionLock = d.Pl; p.TackleLock = d.Tl;
            p.Action = d.A; p.IsKeeper = d.Ik; p.Cards = d.C;
            p.Pressing = d.Pr; p.Shielding = d.Sh;
            p.Dribbling = d.Sh; p.Sprinting = false;
            p.Team = d.Team; p.Slot = d.Slot; p.Role = (Role)d.Role;
        }
        var b = f.Ball;
        s.Ball.Pos = new Vector3(b.X, b.Y, b.Z);
        s.Ball.Vel = new Vector3(b.Vx, b.Vy, b.Vz);
        s.Ball.Spin = new Vector3(b.Sx, b.Sy, b.Sz);
        s.Ball.Owner = b.O; s.Ball.LastTouch = b.Lt; s.Ball.LastTouchSide = b.Lts;
        s.Ball.PassFrom = b.Pf; s.Ball.PassReceiver = b.Pr;
        s.Ball.PassTarget = new Vector3(b.Px, 0f, b.Pz);
        s.Ball.LastTouchPos = new Vector3(b.Lx, b.Ly, b.Lz);
        s.Ball.FreeTime = b.Ft; s.Ball.NoPickup = b.Np;
        if (f.Score.Length >= 2) s.Score = (int[])f.Score.Clone();
        if (f.Shots.Length >= 2) s.Shots = (int[])f.Shots.Clone();
        if (f.Sot.Length >= 2) s.ShotsOnTarget = (int[])f.Sot.Clone();
        if (f.Passes.Length >= 2) s.Passes = (int[])f.Passes.Clone();
        if (f.Fouls.Length >= 2) s.Fouls = (int[])f.Fouls.Clone();
        if (f.Corners.Length >= 2) s.Corners = (int[])f.Corners.Clone();
        if (f.Poss.Length >= 2) s.PossessionTime = (float[])f.Poss.Clone();
        s.Phase = (Phase)f.Phase;
        s.PhaseTimer = f.Pt; s.Clock = f.Clock; s.Half = f.Half;
        s.Controlled = f.Ctrl; s.ControlledAway = f.CtrlA;
        s.KickoffSide = f.Ks; s.RestartSide = f.Rs; s.AttackSign = f.As;
        s.RestartPos = new Vector3(f.Rx, 0f, f.Rz);
        s.ControlLock = f.Cl; s.Commentary = f.Com; s.GoalScorer = f.Gs;
        Events.Clear();
        foreach (var text in f.Ev)
            Events.Add(new MatchEvent { Kind = EventKind.Info, Text = text, Clock = f.Clock, Side = 0 });
        RestoreTiming(f.Rng, f.Gt, f.Tick);
        _acc = f.Acc;
    }

    internal static MatchEvent CloneEvent(MatchEvent e) => new()
    {
        Kind = e.Kind, Text = e.Text, Clock = e.Clock, Side = e.Side,
    };

    private static PlayerState ClonePlayer(PlayerState p) => new()
    {
        Spec = p.Spec, Index = p.Index, Team = p.Team, Slot = p.Slot, Role = p.Role,
        Pos = p.Pos, Vel = p.Vel, Facing = p.Facing, Home = p.Home, Target = p.Target,
        Stamina = p.Stamina, AnimPhase = p.AnimPhase, ActionTimer = p.ActionTimer,
        DecisionTimer = p.DecisionTimer, PossessionLock = p.PossessionLock,
        TackleLock = p.TackleLock, Action = p.Action, IsKeeper = p.IsKeeper,
        Cards = p.Cards, Pressing = p.Pressing, Shielding = p.Shielding,
        Dribbling = p.Dribbling, Sprinting = p.Sprinting,
    };

    private static BallState CloneBall(BallState b) => new()
    {
        Pos = b.Pos, Vel = b.Vel, Spin = b.Spin, PassTarget = b.PassTarget,
        Owner = b.Owner, LastTouch = b.LastTouch, LastTouchSide = b.LastTouchSide,
        PassFrom = b.PassFrom, PassReceiver = b.PassReceiver,
        LastTouchPos = b.LastTouchPos, FreeTime = b.FreeTime, NoPickup = b.NoPickup,
    };

    internal static MatchState CloneState(MatchState s)
    {
        var copy = new MatchState
        {
            Phase = s.Phase, PhaseTimer = s.PhaseTimer, Clock = s.Clock, Half = s.Half,
            Score = (int[])s.Score.Clone(), Shots = (int[])s.Shots.Clone(),
            ShotsOnTarget = (int[])s.ShotsOnTarget.Clone(), Passes = (int[])s.Passes.Clone(),
            Fouls = (int[])s.Fouls.Clone(), Corners = (int[])s.Corners.Clone(),
            PossessionTime = (float[])s.PossessionTime.Clone(),
            Ball = CloneBall(s.Ball),
            Controlled = s.Controlled, ControlledAway = s.ControlledAway,
            KickoffSide = s.KickoffSide, RestartSide = s.RestartSide,
            AttackSign = s.AttackSign, ControlLock = s.ControlLock,
            RestartPos = s.RestartPos, Commentary = s.Commentary, GoalScorer = s.GoalScorer,
        };
        copy.Players = new PlayerState[s.Players.Length];
        for (int i = 0; i < s.Players.Length; i++) copy.Players[i] = ClonePlayer(s.Players[i]);
        return copy;
    }

    /// <summary>Copy a foreign state into THIS engine's State object without aliasing it.</summary>
    internal void OverwriteState(MatchState src)
    {
        var s = State;
        s.Phase = src.Phase; s.PhaseTimer = src.PhaseTimer; s.Clock = src.Clock; s.Half = src.Half;
        s.Score = (int[])src.Score.Clone(); s.Shots = (int[])src.Shots.Clone();
        s.ShotsOnTarget = (int[])src.ShotsOnTarget.Clone(); s.Passes = (int[])src.Passes.Clone();
        s.Fouls = (int[])src.Fouls.Clone(); s.Corners = (int[])src.Corners.Clone();
        s.PossessionTime = (float[])src.PossessionTime.Clone();
        s.Ball = CloneBall(src.Ball);
        s.Controlled = src.Controlled; s.ControlledAway = src.ControlledAway;
        s.KickoffSide = src.KickoffSide; s.RestartSide = src.RestartSide;
        s.AttackSign = src.AttackSign; s.ControlLock = src.ControlLock;
        s.RestartPos = src.RestartPos; s.Commentary = src.Commentary; s.GoalScorer = src.GoalScorer;
        s.Players = new PlayerState[src.Players.Length];
        for (int i = 0; i < src.Players.Length; i++) s.Players[i] = ClonePlayer(src.Players[i]);
    }
}
