// Arena FC - deterministic 3D football simulation. Pure C#: no Godot, no Unity.
// 11v11 / 7v7 / 5v5, AI, ball physics with spin, passing, shooting, tackling,
// goalkeepers, offside, fouls, set pieces, match clock, stats and commentary feed.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;

namespace ArenaFC.Core;

public enum Phase { Kickoff, Play, Goal, HalfTime, FullTime, ThrowIn, Corner, GoalKick, FreeKick, Penalty, Paused }
public enum EventKind { Info, Pass, Shot, Save, Goal, Tackle, Foul, Offside, Out, Card, Whistle }

public sealed class MatchOptions
{
    public int TeamSize = 11;                 // 5, 7 or 11 per side
    public float HalfMinutes = 45f;          // *game* minutes
    public float TimeSpeed = 15f;            // game seconds per real second
    public int Difficulty = 1;               // 0 easy .. 3 legendary
    public int Seed = 2026;
    public bool Offside = true;
    public bool Fouls = true;
    public int HomeClub = 0;
    public int AwayClub = 1;
    public string HomeFormation = "4-4-2";
    public string AwayFormation = "4-3-3";
    public List<CharacterSpec>? CustomHome;
}

public struct PlayerCommand
{
    public Vector2 Move;
    public bool Sprint, Pass, Shoot, Through, Tackle, Switch, Lob;
    public float Charge;
    public static PlayerCommand None => default;
}

public sealed class MatchEvent
{
    public EventKind Kind;
    public string Text = "";
    public float Clock;
    public int Side;
    public override string ToString() => $"[{Clock:000.0}] {Text}";
}

public sealed class PlayerState
{
    public CharacterSpec Spec = new();
    public int Index, Team, Slot;
    public Role Role;
    public Vector3 Pos, Vel, Facing, Home, Target;
    public float Stamina = 1f, AnimPhase, ActionTimer, DecisionTimer, PossessionLock, TackleLock;
    public string Action = "idle";
    public bool IsKeeper;
    public int Cards;
    public float MaxSpeed => (3.6f + Spec.Pace * 3.5f) * (IsKeeper ? .94f : 1f);
}

public sealed class BallState
{
    public Vector3 Pos, Vel, Spin, PassTarget;
    public int Owner = -1;
    public int LastTouch = -1, LastTouchSide = -1, PassFrom = -1, PassReceiver = -1;
    public Vector3 LastTouchPos;
    public float FreeTime, NoPickup;
}

public sealed class MatchState
{
    public Phase Phase = Phase.Kickoff;
    public float PhaseTimer, Clock;
    public int Half = 1;
    public int[] Score = new int[2];
    public int[] Shots = new int[2], ShotsOnTarget = new int[2], Passes = new int[2], Fouls = new int[2], Corners = new int[2];
    public float[] PossessionTime = new float[2];
    public PlayerState[] Players = Array.Empty<PlayerState>();
    public BallState Ball = new();
    public int Controlled = -1, KickoffSide = 0, RestartSide = 0, AttackSign = 1;
    public Vector3 RestartPos;
    public string Commentary = "Kick off!";
    public int GoalScorer = -1;
}

public sealed class MatchEngine
{
    public const float Dt = 1f / 60f;
    public readonly MatchOptions Options;
    public readonly MatchState State = new();
    public readonly List<MatchEvent> Events = new();
    public readonly Rng Rng;
    private float _acc;
    private float _globalTime;
    private int _tick;
    private readonly (float x, float z, Role role)[] _slots;

    public MatchEngine(MatchOptions? options = null)
    {
        Options = options ?? new MatchOptions();
        Options.TeamSize = new[] { 5, 7, 11 }.Contains(Options.TeamSize) ? Options.TeamSize : 11;
        Rng = new Rng(Options.Seed);
        _slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)" : Options.HomeFormation, Options.TeamSize);
        var home = Options.CustomHome ?? Clubs.CreateRoster(Options.HomeClub, Options.TeamSize, Options.Seed);
        var away = Clubs.CreateRoster(Options.AwayClub, Options.TeamSize, Options.Seed + 313);
        State.Players = new PlayerState[Options.TeamSize * 2];
        for (int s = 0; s < 2; s++)
        {
            var roster = s == 0 ? home : away;
            for (int i = 0; i < Options.TeamSize; i++)
            {
                var spec = (i < roster.Count ? roster[i] : new CharacterSpec()).Clone();
                spec.Sanitize();
                int idx = s * Options.TeamSize + i;
                State.Players[idx] = new PlayerState
                {
                    Spec = spec, Index = idx, Team = s, Slot = i,
                    Role = i == 0 ? Role.Goalkeeper : _slots[Math.Min(i, _slots.Length - 1)].role,
                    IsKeeper = i == 0, Stamina = 1f, Facing = new Vector3(s == 0 ? 1 : -1, 0, 0),
                };
                if (i == 0) State.Players[idx].Spec.Role = Role.Goalkeeper;
            }
        }
        State.AttackSign = 1;
        ResetPositions(true);
        State.Phase = Phase.Kickoff;
        State.PhaseTimer = 1.2f;
        Add(EventKind.Info, "Welcome to Arena FC — kick off!");
    }

    public void Add(EventKind kind, string text)
    {
        Events.Add(new MatchEvent { Kind = kind, Text = text, Clock = State.Clock / 60f, Side = State.Ball.LastTouchSide });
        if (Events.Count > 250) Events.RemoveAt(0);
        State.Commentary = text;
    }

    public int SideSign(int side) => (side == 0 ? 1 : -1) * (State.Half == 1 ? 1 : -1);
    public Vector3 GoalPos(int side) => new(SideSign(side) * Mx.HalfLength, 0, 0); // goal being attacked by side
    public Vector3 OwnGoalPos(int side) => new(-SideSign(side) * Mx.HalfLength, 0, 0);

    public void ResetPositions(bool kickoff)
    {
        State.Ball.Pos = new Vector3(0, Mx.BallRadius, 0);
        State.Ball.Vel = Vector3.Zero;
        State.Ball.Spin = Vector3.Zero;
        State.Ball.Owner = -1;
        State.Ball.FreeTime = 0;
        State.Ball.NoPickup = 0;
        for (int s = 0; s < 2; s++)
        {
            int sign = SideSign(s);
            var slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)" : (s == 0 ? Options.HomeFormation : Options.AwayFormation), Options.TeamSize);
            for (int i = 0; i < Options.TeamSize; i++)
            {
                var p = State.Players[s * Options.TeamSize + i];
                var slot = slots[Math.Min(i, slots.Length - 1)];
                p.Home = Clubs.SlotToWorld(slot.x, slot.z, sign);
                p.Pos = p.Home;
                p.Target = p.Home;
                p.Vel = Vector3.Zero;
                p.Facing = Mx.FlatDir(p.Pos, GoalPos(s));
                p.Action = "idle";
                p.DecisionTimer = Rng.Range(0f, .15f);
            }
        }
        if (kickoff)
        {
            int taker = State.KickoffSide * Options.TeamSize + Math.Min(_slots.Length - 1, Options.TeamSize - 1);
            State.Ball.Owner = taker;
            State.Ball.LastTouch = taker;
            State.Ball.LastTouchSide = State.KickoffSide;
            State.Players[taker].Pos = new Vector3(-SideSign(State.KickoffSide) * .4f, 0, 0);
            int second = State.KickoffSide * Options.TeamSize + Math.Min(Options.TeamSize - 1, 4);
            if (second != taker) State.Players[second].Pos = new Vector3(-SideSign(State.KickoffSide) * 2.4f, 0, 2.2f);
            State.Controlled = FindNearestHome(State.Ball.Pos, true);
        }
    }

    private int FindNearestHome(Vector3 pos, bool excludeKeeper)
    {
        int best = -1; float bd = float.MaxValue;
        for (int i = 0; i < Options.TeamSize; i++)
        {
            var p = State.Players[i];
            if (excludeKeeper && p.IsKeeper) continue;
            float d = Mx.FlatDist2(p.Pos, pos);
            if (d < bd) { bd = d; best = p.Index; }
        }
        return best;
    }

    public void Step(float dt, PlayerCommand cmd)
    {
        _acc += Math.Clamp(dt, 0f, .12f);
        bool first = true;
        while (_acc >= Dt)
        {
            Tick(Dt, first ? cmd : PlayerCommand.None);
            _acc -= Dt;
            first = false;
            if (State.Phase == Phase.FullTime) break;
        }
    }

    private void Tick(float dt, PlayerCommand cmd)
    {
        _tick++;
        _globalTime += dt;
        var S = State;
        if (S.Phase == Phase.FullTime || S.Phase == Phase.Paused) return;

        S.Clock += dt * Options.TimeSpeed;
        float halfSeconds = Options.HalfMinutes * 60f;
        if (S.Phase == Phase.Play && S.Half == 1 && S.Clock >= halfSeconds)
        {
            S.Clock = halfSeconds;
            S.Phase = Phase.HalfTime;
            S.PhaseTimer = 3.0f;
            Add(EventKind.Whistle, "Half time!");
            return;
        }
        if (S.Phase == Phase.Play && S.Half == 2 && S.Clock >= halfSeconds * 2f)
        {
            S.Phase = Phase.FullTime;
            Add(EventKind.Whistle, $"Full time! {ScoreText()}");
            foreach (var p in S.Players) p.Action = S.Score[p.Team] > S.Score[1 - p.Team] ? "celebrate" : "idle";
            return;
        }

        if (S.Phase != Phase.Play)
        {
            S.PhaseTimer -= dt;
            if (S.PhaseTimer > 0) { AnimateOnly(dt); return; }
            switch (S.Phase)
            {
                case Phase.Kickoff:
                    S.Phase = Phase.Play;
                    if (S.Ball.Owner >= 0) KickoffPass(S.Ball.Owner);
                    break;
                case Phase.Goal:
                    ResetPositions(true);
                    S.Phase = Phase.Kickoff;
                    S.PhaseTimer = 1.1f;
                    break;
                case Phase.HalfTime:
                    S.Half = 2;
                    S.KickoffSide = 1;
                    ResetPositions(true);
                    S.Phase = Phase.Kickoff;
                    S.PhaseTimer = 1.1f;
                    Add(EventKind.Info, "Second half under way — ends have been switched.");
                    break;
                case Phase.ThrowIn: case Phase.Corner: case Phase.GoalKick: case Phase.FreeKick: case Phase.Penalty:
                    Restart(S.RestartSide, S.RestartPos, S.Phase == Phase.Penalty);
                    break;
            }
            return;
        }

        // ---- Human control ----
        if (cmd.Switch && S.Controlled >= 0) S.Controlled = FindNearestHome(S.Ball.Pos, true);
        var humans = new HashSet<int>();
        if (S.Controlled >= 0 && S.Controlled < S.Players.Length) humans.Add(S.Controlled);

        // ---- AI decisions ----
        foreach (var p in S.Players)
        {
            p.DecisionTimer -= dt;
            p.ActionTimer = MathF.Max(0, p.ActionTimer - dt);
            p.PossessionLock = MathF.Max(0, p.PossessionLock - dt);
            p.TackleLock = MathF.Max(0, p.TackleLock - dt);
            if (p.DecisionTimer <= 0)
            {
                p.DecisionTimer = Rng.Range(.08f, .18f);
                Decide(p, humans.Contains(p.Index) ? cmd : PlayerCommand.None, humans.Contains(p.Index));
            }
        }

        // ---- Movement ----
        foreach (var p in S.Players) MovePlayer(p, dt, humans.Contains(p.Index) ? cmd : PlayerCommand.None, humans.Contains(p.Index));

        // ---- Ball ----
        S.Ball.NoPickup = MathF.Max(0, S.Ball.NoPickup - dt);
        if (S.Ball.Owner >= 0 && S.Ball.Owner < S.Players.Length)
        {
            var owner = S.Players[S.Ball.Owner];
            if (owner.PossessionLock > 0 || Mx.FlatDist(owner.Pos, S.Ball.Pos) > 2.2f)
            {
                S.Ball.Owner = -1;
            }
            else
            {
                Vector3 f = Mx.Norm(Mx.Flat(owner.Facing));
                if (f.LengthSquared() < .1f) f = new Vector3(1, 0, 0);
                float bob = MathF.Sin(_globalTime * 13f) * .012f;
                S.Ball.Pos = owner.Pos + f * .46f + new Vector3(0, Mx.BallRadius + bob, 0);
                S.Ball.Vel = owner.Vel;
                S.Ball.Spin = Vector3.Zero;
                S.Ball.LastTouch = owner.Index;
                S.Ball.LastTouchSide = owner.Team;
                S.Ball.LastTouchPos = S.Ball.Pos;
                S.PossessionTime[owner.Team] += dt;
            }
        }
        if (S.Ball.Owner < 0) BallPhysics(dt);
        TryPossession(dt);
        ClampAll();
    }

    private void AnimateOnly(float dt)
    {
        foreach (var p in State.Players)
        {
            p.AnimPhase += dt * (p.Action == "run" ? 8f : 2f);
            p.Vel *= .9f;
        }
    }

    private string ScoreText() => $"{Clubs.All[Options.HomeClub].Short} {State.Score[0]} - {State.Score[1]} {Clubs.All[Options.AwayClub].Short}";

    private void KickoffPass(int from)
    {
        int team = from / Options.TeamSize;
        int mate = FindBestPassTarget(State.Players[from], false);
        if (mate < 0) return;
        PassTo(State.Players[from], State.Players[mate], 10f, false);
    }

    private void Decide(PlayerState p, PlayerCommand cmd, bool human)
    {
        var S = State;
        var ball = S.Ball;
        int attack = SideSign(p.Team);
        bool ourBall = ball.Owner >= 0 && S.Players[ball.Owner].Team == p.Team;
        Vector3 goal = GoalPos(p.Team);
        bool keeper = p.IsKeeper;

        // --- Human actions ---
        if (human)
        {
            if (cmd.Switch) { /* handled in Tick */ }
            if (ball.Owner == p.Index)
            {
                if (cmd.Shoot) { Shoot(p, MathF.Max(.25f, cmd.Charge)); return; }
                if (cmd.Pass) { int t = FindBestPassTarget(p, false); if (t >= 0) PassTo(p, S.Players[t], 14f, false); return; }
                if (cmd.Through) { int t = FindBestPassTarget(p, true); if (t >= 0) PassTo(p, S.Players[t], 17f, true); return; }
                if (cmd.Lob) { int t = FindBestPassTarget(p, true); if (t >= 0) PassTo(p, S.Players[t], 15f, true, true); return; }
            }
            else if (cmd.Tackle && p.TackleLock <= 0) { AttemptTackle(p); return; }
            if (cmd.Shoot && ball.Owner < 0 && Mx.FlatDist(p.Pos, ball.Pos) < 1.4f && ball.Pos.Y < 1.6f)
            {
                Shoot(p, MathF.Max(.25f, cmd.Charge), true); return;
            }
        }

        // --- Positional target ---
        Vector3 slotPos = FormationPosition(p, attack, ball.Pos);
        if (keeper)
        {
            float gx = OwnGoalPos(p.Team).X;
            float tx = gx + attack * (1.3f + Mx.Clamp((MathF.Abs(ball.Pos.X - gx) - 8f) * .10f, 0f, 3.2f));
            float tz = Mx.Clamp(ball.Pos.Z * .62f, -Mx.GoalHalfWidth * .92f, Mx.GoalHalfWidth * .92f);
            p.Target = new Vector3(tx, 0, tz);
            p.Action = "idle";
            float danger = Mx.FlatDist(ball.Pos, OwnGoalPos(p.Team));
            if (danger < 13f && ball.Owner < 0 && ball.Vel.Length() > 12f && p.ActionTimer <= 0)
            {
                p.Action = "dive"; p.ActionTimer = .65f;
                p.Target += Mx.FlatDir(p.Pos, ball.Pos) * 1.6f;
            }
            return;
        }

        if (ball.Owner == p.Index)
        {
            // Dribble toward goal, evade the nearest opponent.
            Vector3 dir = Mx.FlatDir(p.Pos, goal);
            var press = NearestOpponent(p, out float pd);
            if (press != null && pd < 4f)
                dir = Mx.Norm(dir * .75f + Mx.FlatDir(press.Pos, p.Pos) * .55f + new Vector3(0, 0, Mx.Clamp(-press.Pos.Z * .04f, -.5f, .5f)));
            p.Target = p.Pos + dir * 4f;
            p.Action = "run";
            if (!human)
            {
                float distGoal = Mx.FlatDist(p.Pos, goal);
                float shotChance = Mx.Clamp((25f - distGoal) / 25f, 0f, 1f) * .06f * (Options.Difficulty * .35f + 1f);
                if (distGoal < 26f && MathF.Abs(p.Pos.Z) < 22f && Rng.Next() < shotChance)
                { Shoot(p, Rng.Range(.55f, 1f)); return; }
                if ((press != null && pd < 2.1f && Rng.Next() < .20f) || Rng.Next() < .012f)
                {
                    int t = FindBestPassTarget(p, Rng.Next() < .25f);
                    if (t >= 0) { PassTo(p, S.Players[t], 14f, false); return; }
                }
            }
            return;
        }

        int chaser1 = ClosestToBall(p.Team, 0), chaser2 = ClosestToBall(p.Team, 1);
        if (ourBall)
        {
            // Support the carrier.
            Vector3 carrier = ball.Pos;
            Vector3 support = slotPos + Mx.FlatDir(p.Home, carrier) * 1.6f;
            support.X += attack * 3.5f;
            p.Target = support;
            if (p.Role == Role.Forward) p.Target.X += attack * 4f;
            p.Action = "run";
        }
        else
        {
            if (p.Index == chaser1 || p.Index == chaser2 || (ball.Owner < 0 && p.Index == chaser1))
            {
                Vector3 intercept = ball.Pos + Mx.Flat(ball.Vel) * Mx.Clamp(Mx.FlatDist(p.Pos, ball.Pos) / 14f, 0f, .7f);
                p.Target = intercept;
                p.Action = "run";
            }
            else
            {
                p.Target = slotPos;
                p.Action = "run";
            }
            if (ball.Owner >= 0)
            {
                var carrier = S.Players[ball.Owner];
                float d = Mx.FlatDist(p.Pos, carrier.Pos);
                float aggression = .10f + Options.Difficulty * .07f + (p.Spec.Defending - .5f) * .10f;
                if (p.Team == carrier.Team) { /* teammate */ }
                else if (d < 1.8f && p.TackleLock <= 0 && Rng.Next() < aggression)
                    AttemptTackle(p);
            }
        }
        // Goal celebration / foul reaction
        if (p.ActionTimer > 0 && p.Action == "celebrate") p.Target = p.Pos;
    }

    private Vector3 FormationPosition(PlayerState p, int attack, Vector3 ballPos)
    {
        var slots = Clubs.Slots(Options.TeamSize == 5 ? "1-2-1 (5s)" : Options.TeamSize == 7 ? "2-3-1 (7s)"
            : (p.Team == 0 ? Options.HomeFormation : Options.AwayFormation), Options.TeamSize);
        var slot = slots[Math.Min(p.Slot, slots.Length - 1)];
        float shift = Mx.Clamp(ballPos.X / (Mx.HalfLength * 2f), -.5f, .5f) * .30f;
        float zShift = Mx.Clamp(ballPos.Z / Mx.HalfWidth, -1f, 1f) * .10f;
        return Clubs.SlotToWorld(slot.x + shift, slot.z + zShift, attack);
    }

    private PlayerState? NearestOpponent(PlayerState p, out float dist)
    {
        dist = float.MaxValue; PlayerState? best = null;
        foreach (var q in State.Players)
        {
            if (q.Team == p.Team) continue;
            float d = Mx.FlatDist(p.Pos, q.Pos);
            if (d < dist) { dist = d; best = q; }
        }
        return best;
    }

    private int ClosestToBall(int team, int rank)
    {
        var list = State.Players.Where(p => p.Team == team && !p.IsKeeper)
            .OrderBy(p => Mx.FlatDist2(p.Pos, State.Ball.Pos)).ToArray();
        return rank < list.Length ? list[rank].Index : (list.Length > 0 ? list[0].Index : -1);
    }

    private int FindBestPassTarget(PlayerState from, bool through)
    {
        int best = -1; float bestScore = float.MinValue;
        int attack = SideSign(from.Team);
        foreach (var q in State.Players)
        {
            if (q.Team != from.Team || q.Index == from.Index || q.IsKeeper) continue;
            float d = Mx.FlatDist(from.Pos, q.Pos);
            if (d < 2.5f || d > 42f) continue;
            float forward = (q.Pos.X - from.Pos.X) * attack;
            float openness = NearestOpponent(q, out float od) is null ? 8f : MathF.Min(od, 8f);
            bool laneBlocked = false;
            foreach (var o in State.Players)
            {
                if (o.Team == from.Team) continue;
                float proj = Mx.Clamp(Vector3.Dot(Mx.Flat(o.Pos - from.Pos), Mx.Flat(q.Pos - from.Pos)) / MathF.Max(.01f, d * d), 0f, 1f);
                if (Mx.FlatDist(o.Pos, Mx.Lerp(from.Pos, q.Pos, proj)) < 1.5f && proj > .1f && proj < .9f) { laneBlocked = true; break; }
            }
            float score = forward * .22f + openness * .55f - d * .10f + (through ? forward * .28f : 0f) - (laneBlocked ? 6f : 0f);
            if (Options.Offside && IsOffside(q, from)) score -= 30f;
            score += Rng.Range(-1.2f, 1.2f);
            if (score > bestScore) { bestScore = score; best = q.Index; }
        }
        return best;
    }

    private bool IsOffside(PlayerState receiver, PlayerState passer)
    {
        int attack = SideSign(receiver.Team);
        if (receiver.Pos.X * attack <= 0f) return false;
        var defenders = State.Players.Where(p => p.Team != receiver.Team)
            .Select(p => p.Pos.X * attack).OrderByDescending(x => x).ToArray();
        if (defenders.Length < 2) return false;
        float secondLast = defenders[1];
        return receiver.Pos.X * attack > 0f && receiver.Pos.X * attack > secondLast;
    }

    private void PassTo(PlayerState from, PlayerState to, float power, bool through, bool lob = false)
    {
        var b = State.Ball;
        if (b.Owner != from.Index && b.Owner >= 0) return;
        b.Owner = -1;
        from.PossessionLock = .35f;
        from.Action = "kick"; from.ActionTimer = .34f;
        Vector3 aim = to.Pos + Mx.Flat(to.Vel) * (through ? .55f : .22f);
        if (through) aim += Mx.FlatDir(from.Pos, GoalPos(from.Team)) * 4f;
        Vector3 dir = Mx.FlatDir(b.Pos, aim);
        float skill = from.Spec.Passing;
        float err = (1f - skill) * 2.2f + (through ? .8f : 0f);
        dir = Mx.Norm(dir + new Vector3(Rng.Signed() * err * .12f, 0, Rng.Signed() * err * .12f));
        float dist = Mx.FlatDist(b.Pos, aim);
        float speed = Mx.Clamp(power + dist * .25f, 8f, 27f);
        b.Vel = dir * speed + new Vector3(0, lob ? 5.5f : (through ? .9f : .45f), 0);
        b.Spin = new Vector3(0, Rng.Signed() * .5f, 0);
        b.Pos = from.Pos + dir * .55f + new Vector3(0, Mx.BallRadius + .03f, 0);
        b.FreeTime = 0;
        b.NoPickup = .10f;
        b.LastTouch = from.Index; b.LastTouchSide = from.Team; b.LastTouchPos = b.Pos;
        b.PassFrom = from.Index; b.PassReceiver = to.Index; b.PassTarget = aim;
        State.Passes[from.Team]++;
        Add(EventKind.Pass, $"{from.Spec.DisplayName} → {to.Spec.DisplayName}");
        if (Options.Offside && IsOffside(to, from))
        {
            Add(EventKind.Offside, $"Offside! {to.Spec.DisplayName} was in an offside position.");
            AwardFreeKick(1 - from.Team, b.Pos, false);
        }
    }

    private void Shoot(PlayerState p, float charge, bool volley = false)
    {
        var b = State.Ball;
        if (b.Owner != p.Index && !volley) return;
        if (volley && Mx.FlatDist(p.Pos, b.Pos) > 1.6f) return;
        b.Owner = -1;
        p.PossessionLock = .55f;
        p.Action = "kick"; p.ActionTimer = .4f;
        int attack = SideSign(p.Team);
        Vector3 target = new(GoalPos(p.Team).X, Rng.Range(.4f, 2.0f), Rng.Range(-Mx.GoalHalfWidth * .78f, Mx.GoalHalfWidth * .78f));
        // Aim for the corners when skill is high.
        target.Z = MathF.Sign(target.Z) * Mx.Lerp(Mx.GoalHalfWidth * .2f, Mx.GoalHalfWidth * .86f, p.Spec.Shooting * Rng.Next());
        Vector3 dir = Mx.FlatDir(b.Pos, target);
        float dist = Mx.FlatDist(b.Pos, target);
        float err = (1f - p.Spec.Shooting) * 3.4f + (volley ? 1.2f : 0f) + MathF.Max(0f, dist - 20f) * .08f;
        dir = Mx.Norm(dir + new Vector3(0, 0, Rng.Signed() * err * .16f));
        float power = Mx.Lerp(17f, 31f, charge) * Mx.Lerp(.82f, 1.12f, p.Spec.Shooting);
        float loft = Mx.Lerp(.08f, .30f, charge) + (dist > 20f ? .06f : 0f);
        b.Vel = dir * power + new Vector3(0, power * loft, 0);
        b.Spin = new Vector3(0, Rng.Signed() * (1f + p.Spec.Shooting * 2.2f), 0);
        b.Pos += new Vector3(0, .05f, 0);
        b.FreeTime = 0;
        b.NoPickup = .22f;
        b.LastTouch = p.Index; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
        b.PassReceiver = -1;
        State.Shots[p.Team]++;
        Add(EventKind.Shot, $"{p.Spec.DisplayName} shoots!");
    }

    private void AttemptTackle(PlayerState p)
    {
        p.TackleLock = 1.1f;
        p.Action = "tackle"; p.ActionTimer = .45f;
        var b = State.Ball;
        if (b.Owner < 0) return;
        var carrier = State.Players[b.Owner];
        if (carrier.Team == p.Team) return;
        float d = Mx.FlatDist(p.Pos, carrier.Pos);
        if (d > 2.0f) return;
        float chance = .35f + p.Spec.Defending * .40f - carrier.Spec.Pace * .18f - (d - 1f) * .15f;
        if (Rng.Next() < chance)
        {
            b.Owner = p.Index;
            p.PossessionLock = .12f;
            carrier.PossessionLock = .45f;
            b.Vel = Vector3.Zero;
            Add(EventKind.Tackle, $"{p.Spec.DisplayName} wins the ball!");
        }
        else if (Options.Fouls && Rng.Next() < .18f + (d - 1f) * .12f)
        {
            State.Fouls[p.Team]++;
            p.Cards += Rng.Next() < .18f ? 1 : 0;
            float ownGoalX = OwnGoalPos(p.Team).X;
            bool inBox = MathF.Abs(b.Pos.X - ownGoalX) < 16.5f && MathF.Abs(b.Pos.Z) < 20.16f;
            Add(EventKind.Foul, p.Cards > 0 ? "Foul! Yellow card." : "Foul! Free kick.");
            if (inBox && Rng.Next() < .55f) AwardFreeKick(1 - p.Team, new Vector3(-SideSign(p.Team) * (Mx.HalfLength - 11f), 0, 0), true);
            else AwardFreeKick(1 - p.Team, b.Pos, false);
        }
    }

    private void AwardFreeKick(int side, Vector3 pos, bool penalty)
    {
        State.Ball.Owner = -1;
        State.Ball.Vel = Vector3.Zero;
        State.RestartSide = side;
        State.RestartPos = pos;
        State.Phase = penalty ? Phase.Penalty : Phase.FreeKick;
        State.PhaseTimer = 1.5f;
    }

    private void Restart(int side, Vector3 pos, bool penalty)
    {
        State.Ball.Pos = Mx.Clamp(pos.X, -Mx.HalfLength + 1f, Mx.HalfLength - 1f) * Vector3.UnitX
                        + new Vector3(0, Mx.BallRadius, Mx.Clamp(pos.Z, -Mx.HalfWidth + 1f, Mx.HalfWidth - 1f));
        State.Ball.Vel = Vector3.Zero;
        State.Ball.Spin = Vector3.Zero;
        State.Ball.NoPickup = 0;
        int best = -1; float bd = float.MaxValue;
        for (int i = 0; i < Options.TeamSize; i++)
        {
            var p = State.Players[side * Options.TeamSize + i];
            if (p.IsKeeper && !penalty) continue;
            float d = Mx.FlatDist2(p.Pos, State.Ball.Pos);
            if (d < bd) { bd = d; best = p.Index; }
        }
        if (best < 0) best = side * Options.TeamSize;
        var taker = State.Players[best];
        State.Ball.Owner = best;
        taker.Pos = State.Ball.Pos - new Vector3(SideSign(side) * .8f, 0, 0);
        taker.PossessionLock = 0;
        taker.Facing = Mx.FlatDir(taker.Pos, GoalPos(side));
        // Push opponents away from the set piece.
        foreach (var q in State.Players)
            if (q.Team != side && Mx.FlatDist(q.Pos, State.Ball.Pos) < 4f)
                q.Pos += Mx.FlatDir(State.Ball.Pos, q.Pos) * (4f - Mx.FlatDist(q.Pos, State.Ball.Pos));
        State.Phase = Phase.Play;
        if (penalty) { taker.Action = "kick"; Shoot(taker, .9f); }
        Add(EventKind.Info, penalty ? "Penalty!" : "Back under way.");
    }

    private void MovePlayer(PlayerState p, float dt, PlayerCommand cmd, bool human)
    {
        Vector3 wish = Vector3.Zero;
        bool sprint = false;
        if (human && cmd.Move.LengthSquared() > .01f)
        {
            wish = new Vector3(cmd.Move.X, 0, cmd.Move.Y);
            if (wish.LengthSquared() > 1f) wish = Vector3.Normalize(wish);
            sprint = cmd.Sprint;
            p.Target = p.Pos + wish * 3f;
        }
        else
        {
            Vector3 d = Mx.Flat(p.Target - p.Pos);
            if (d.Length() > .35f) wish = Mx.Norm(d);
            sprint = !human && Mx.FlatDist(p.Pos, p.Target) > 5f && p.Stamina > .25f;
        }
        float fatigue = Mx.Lerp(.72f, 1f, p.Stamina);
        float speed = p.MaxSpeed * fatigue * (sprint ? 1.24f : 1f);
        if (p.Action == "tackle") speed *= 1.35f;
        Vector3 targetVel = wish * speed;
        float accel = (human ? 18f : 12f) * dt;
        p.Vel = Mx.MoveTowards(p.Vel, targetVel, accel);
        p.Pos += p.Vel * dt;
        p.Pos.Y = 0;
        if (sprint) p.Stamina = MathF.Max(.08f, p.Stamina - dt * .055f);
        else p.Stamina = MathF.Min(1f, p.Stamina + dt * .022f);
        float planar = Mx.Flat(p.Vel).Length();
        if (planar > .15f) p.Facing = Mx.Norm(Mx.Lerp(p.Facing, Mx.Flat(p.Vel), MathF.Min(1f, dt * 9f)));
        else if (State.Ball.Owner == p.Index || p.IsKeeper) p.Facing = Mx.Norm(Mx.Lerp(p.Facing, Mx.FlatDir(p.Pos, GoalPos(p.Team)), MathF.Min(1f, dt * 5f)));
        p.AnimPhase += dt * (2.2f + planar * 1.5f);
        if (p.ActionTimer <= 0) p.Action = planar > 1.2f ? "run" : "idle";
        // Simple separation so players don't stack.
        foreach (var q in State.Players)
        {
            if (q.Index == p.Index) continue;
            Vector3 diff = Mx.Flat(p.Pos - q.Pos);
            float dd = diff.Length();
            if (dd > .001f && dd < .62f) p.Pos += Mx.Norm(diff) * (.62f - dd) * .38f;
        }
        p.Pos.X = Mx.Clamp(p.Pos.X, -Mx.HalfLength - 2.5f, Mx.HalfLength + 2.5f);
        p.Pos.Z = Mx.Clamp(p.Pos.Z, -Mx.HalfWidth - 2.5f, Mx.HalfWidth + 2.5f);
    }

    private void BallPhysics(float dt)
    {
        var b = State.Ball;
        b.FreeTime += dt;
        Vector3 v = b.Vel;
        v.Y += Mx.Gravity * dt;
        // Magnus effect from spin (side curve + dip).
        v += Vector3.Cross(b.Spin, v) * (.055f * dt);
        v *= 1f - (v.Y > 0f || b.Pos.Y > Mx.BallRadius + .05f ? .045f : 0f) * dt;
        b.Pos += v * dt;

        if (b.Pos.Y < Mx.BallRadius)
        {
            b.Pos.Y = Mx.BallRadius;
            if (v.Y < 0f) v.Y = -v.Y * .48f;
            if (MathF.Abs(v.Y) < .45f) v.Y = 0f;
            float roll = v.Y == 0f ? 1.55f : .55f;
            v.X *= MathF.Max(0f, 1f - roll * dt);
            v.Z *= MathF.Max(0f, 1f - roll * dt);
            b.Spin *= MathF.Max(0f, 1f - 2f * dt);
        }
        b.Vel = v;

        // --- Posts and crossbar ---
        foreach (int side in new[] { -1, 1 })
        {
            float gx = side * Mx.HalfLength;
            if (MathF.Abs(b.Pos.X - gx) < Mx.BallRadius + .09f)
            {
                foreach (float pz in new[] { -Mx.GoalHalfWidth, Mx.GoalHalfWidth })
                    if (MathF.Abs(b.Pos.Z - pz) < Mx.BallRadius + .09f && b.Pos.Y < Mx.GoalHeight + .1f)
                    {
                        b.Pos.X = gx - side * (Mx.BallRadius + .1f);
                        b.Vel.X *= -.45f; b.Vel.Z += Rng.Signed() * 1.5f;
                        Add(EventKind.Info, "Off the post!");
                    }
                if (MathF.Abs(b.Pos.Y - Mx.GoalHeight) < Mx.BallRadius + .08f && MathF.Abs(b.Pos.Z) < Mx.GoalHalfWidth)
                {
                    b.Pos.X = gx - side * (Mx.BallRadius + .1f);
                    b.Vel.X *= -.4f; b.Vel.Y *= -.5f;
                    Add(EventKind.Info, "Off the crossbar!");
                }
            }
        }

        // --- Goal ---
        if (MathF.Abs(b.Pos.X) > Mx.HalfLength + .02f && MathF.Abs(b.Pos.X) < Mx.HalfLength + 2f
            && MathF.Abs(b.Pos.Z) < Mx.GoalHalfWidth - .05f && b.Pos.Y < Mx.GoalHeight)
        {
            int scoringSide = b.Pos.X > 0 ? 0 : 1; // home attacks +X in first half
            if (State.Half == 2) scoringSide = 1 - scoringSide;
            Goal(scoringSide);
            return;
        }

        // --- Goalkeeper save ---
        foreach (var p in State.Players)
        {
            if (!p.IsKeeper) continue;
            float d = (p.Pos - b.Pos).Length();
            if (d < (p.Action == "dive" ? 1.65f : 1.15f) && b.Pos.Y < 2.5f && b.FreeTime > .1f)
            {
                b.Owner = p.Index;
                p.PossessionLock = .15f;
                p.Action = "catch"; p.ActionTimer = .4f;
                Add(EventKind.Save, $"{p.Spec.DisplayName} makes the save!");
                return;
            }
        }

        // --- Out of play ---
        if (MathF.Abs(b.Pos.Z) > Mx.HalfWidth + .2f)
        {
            int side = b.LastTouchSide >= 0 ? 1 - b.LastTouchSide : 0;
            State.RestartSide = side;
            State.RestartPos = new Vector3(Mx.Clamp(b.Pos.X, -Mx.HalfLength + 2f, Mx.HalfLength - 2f), 0,
                                           MathF.Sign(b.Pos.Z) * (Mx.HalfWidth - .5f));
            State.Phase = Phase.ThrowIn; State.PhaseTimer = 1.1f;
            Add(EventKind.Out, "Throw-in.");
            b.Vel = Vector3.Zero;
            return;
        }
        if (MathF.Abs(b.Pos.X) > Mx.HalfLength + .2f)
        {
            int last = b.LastTouchSide >= 0 ? b.LastTouchSide : 0;
            int defending = b.Pos.X > 0 ? (State.Half == 1 ? 1 : 0) : (State.Half == 1 ? 0 : 1);
            if (last == defending)
            {
                State.Corners[1 - defending]++;
                State.RestartSide = 1 - defending;
                State.RestartPos = new Vector3(MathF.Sign(b.Pos.X) * (Mx.HalfLength - .6f), 0,
                                               MathF.Sign(b.Pos.Z) * (Mx.HalfWidth - .6f));
                State.Phase = Phase.Corner; State.PhaseTimer = 1.3f;
                Add(EventKind.Out, "Corner kick.");
            }
            else
            {
                State.RestartSide = defending;
                State.RestartPos = new Vector3(MathF.Sign(b.Pos.X) * (Mx.HalfLength - 5.5f), 0, 0);
                State.Phase = Phase.GoalKick; State.PhaseTimer = 1.2f;
                Add(EventKind.Out, "Goal kick.");
            }
            b.Vel = Vector3.Zero;
        }
    }

    private void Goal(int side)
    {
        State.Score[side]++;
        State.GoalScorer = State.Ball.LastTouch;
        var scorer = State.GoalScorer >= 0 ? State.Players[State.GoalScorer].Spec.DisplayName : "Own goal";
        Add(EventKind.Goal, $"GOAL! {scorer} — {ScoreText()}");
        State.KickoffSide = 1 - side;
        State.Phase = Phase.Goal;
        State.PhaseTimer = 3.4f;
        State.Ball.Vel = Vector3.Zero;
        foreach (var p in State.Players)
        {
            p.Action = p.Team == side ? "celebrate" : "idle";
            p.ActionTimer = 2.5f;
        }
    }

    private void TryPossession(float dt)
    {
        var b = State.Ball;
        if (b.Owner >= 0) { b.FreeTime = 0; return; }
        if (b.FreeTime < .08f || b.NoPickup > 0f || b.Pos.Y > 1.55f) return;
        int best = -1; float bd = 1.05f * 1.05f;
        foreach (var p in State.Players)
        {
            if (p.PossessionLock > 0f) continue;
            if (b.PassReceiver == p.Index && b.FreeTime < .05f) continue;
            float d = Mx.FlatDist2(p.Pos, b.Pos);
            float radius = p.IsKeeper ? 1.5f : 1.0f;
            if (d < radius * radius && d < bd) { bd = d; best = p.Index; }
        }
        if (best >= 0)
        {
            b.Owner = best;
            b.Vel = Vector3.Zero;
            b.Spin = Vector3.Zero;
            b.FreeTime = 0;
            var p = State.Players[best];
            p.PossessionLock = .12f;
            b.LastTouch = best; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
            if (p.Team == 0) State.Controlled = best;
            if (b.PassFrom >= 0 && b.PassReceiver == best && b.PassFrom / Options.TeamSize == p.Team)
                b.PassFrom = -1;
        }
    }

    private void ClampAll()
    {
        var b = State.Ball;
        if (!Mx.IsFinite(b.Pos) || !Mx.IsFinite(b.Vel))
        {
            b.Pos = new Vector3(0, Mx.BallRadius, 0); b.Vel = Vector3.Zero; b.Owner = -1;
        }
        b.Pos.X = Mx.Clamp(b.Pos.X, -Mx.HalfLength - 3f, Mx.HalfLength + 3f);
        b.Pos.Z = Mx.Clamp(b.Pos.Z, -Mx.HalfWidth - 3f, Mx.HalfWidth + 3f);
        b.Pos.Y = Mx.Clamp(b.Pos.Y, Mx.BallRadius, 25f);
        foreach (var p in State.Players)
            if (!Mx.IsFinite(p.Pos) || !Mx.IsFinite(p.Vel)) { p.Pos = p.Home; p.Vel = Vector3.Zero; }
    }

    // ---- Read-only helpers for the front end ----
    public string ClockString()
    {
        float minutes = State.Clock / 60f;
        int m = (int)minutes;
        int s = (int)((minutes - m) * 60f);
        return $"{m:00}:{s:00}";
    }
    public float PossessionPct(int side)
    {
        float total = State.PossessionTime[0] + State.PossessionTime[1];
        return total < .1f ? 50f : State.PossessionTime[side] / total * 100f;
    }
    public int PlayerWithBall => State.Ball.Owner;
    public bool IsHomeAttackingRight => SideSign(0) > 0;
}
