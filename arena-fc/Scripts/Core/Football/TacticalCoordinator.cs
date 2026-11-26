using System;
using System.Collections.Generic;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Core.Football;

/// <summary>
/// Deterministic tactical coordinator. Authoritative team-level source for
/// press/chase/cover/support/recovery roles and movement targets. Simulation
/// remains authoritative; this only decides intent/targets.
/// </summary>
public sealed class TacticalCoordinator
{
    public sealed class Assignment
    {
        public int PlayerIndex;
        public string Role = "hold";
        public string Intent = "hold";
        public Vector3 MovementTarget;
        public Vector3 FacingTarget;
        public float SpeedLimit = 8f;
        public bool ShouldSprint;
        public bool Pressing;
        public int MarkTarget = -1;
        public float Priority;
    }

    private readonly Dictionary<int, string> _prevRole = new();
    private readonly Dictionary<int, int> _roleHoldTicks = new();
    private readonly int[] _prevPresserByTeam = { -1, -1 };

    public void ClearState()
    {
        _prevRole.Clear();
        _roleHoldTicks.Clear();
        _prevPresserByTeam[0] = -1;
        _prevPresserByTeam[1] = -1;
    }

    public List<Assignment> BuildAssignments(MatchState s, int team, BallTrajectory? ballPred = null)
    {
        var list = new List<Assignment>();
        int opp = 1 - team;
        var oppPos = new List<Vector3>();
        var oppVel = new List<Vector3>();
        foreach (var p in s.Players) if (p.Team == opp && !p.SentOff) { oppPos.Add(p.Pos); oppVel.Add(p.Vel); }
        Vector3 ballNow = s.Ball.Pos;
        Vector3 ballRef = ballNow;
        if (ballPred != null && ballPred.Samples.Count > 0) ballRef = ballPred.At(0.35f).Position;
        else ballRef = ballNow + Mx.Flat(s.Ball.Vel) * 0.35f;

        bool teamInPoss = s.Ball.Owner >= 0 && s.Ball.Owner < s.Players.Length && s.Players[s.Ball.Owner].Team == team;
        int attackSign = team == 0 ? 1 : -1;
        Vector3 ownGoal = team == 0 ? new Vector3(-Mx.HalfLength, 0, 0) : new Vector3(Mx.HalfLength, 0, 0);
        Vector3 oppGoal = team == 0 ? new Vector3(Mx.HalfLength, 0, 0) : new Vector3(-Mx.HalfLength, 0, 0);

        // Rank by time to predicted ball using actual player capabilities.
        var byReach = new List<(int idx, float t, float dist)>();
        foreach (var p in s.Players)
        {
            if (p.Team != team || p.SentOff || p.IsKeeper) continue;
            float maxSpd = PlayerMaxSpeed(p);
            float accel = PlayerAccel(p);
            float t = PlayerPerception.TimeToReach(p.Pos, p.Vel, ballRef, maxSpd, accel);
            float d = Mx.FlatDist(p.Pos, ballRef);
            byReach.Add((p.Index, t, d));
        }
        byReach.Sort((a, b) =>
        {
            int c = a.t.CompareTo(b.t);
            return c != 0 ? c : a.dist.CompareTo(b.dist);
        });

        int presser = -1, cover = -1, support = -1;
        if (!teamInPoss)
        {
            presser = byReach.Count > 0 ? byReach[0].idx : -1;
            // Hysteresis: keep current presser if close enough to avoid oscillation.
            if (presser >= 0 && (!_prevRole.TryGetValue(presser, out var prRole) || prRole != "press"))
            {
                int prevPresser = (team >= 0 && team < _prevPresserByTeam.Length) ? _prevPresserByTeam[team] : -1;
                if (prevPresser >= 0 && prevPresser != presser && prevPresser < s.Players.Length)
                {
                    var pp = s.Players[prevPresser];
                    if (pp.Team == team && !pp.SentOff && !pp.IsKeeper)
                    {
                        float prevT = PlayerPerception.TimeToReach(pp.Pos, pp.Vel, ballRef, PlayerMaxSpeed(pp), PlayerAccel(pp));
                        float newT = byReach[0].t;
                        if (prevT <= newT + 0.18f) presser = prevPresser; // stability margin
                    }
                }
            }
            cover = byReach.Count > 1 ? (byReach[0].idx == presser ? byReach[1].idx : byReach[0].idx) : -1;
            if (cover == presser && byReach.Count > 1) cover = byReach[1].idx;
            for (int i = 0; i < byReach.Count; i++)
            {
                if (byReach[i].idx == presser || byReach[i].idx == cover) continue;
                support = byReach[i].idx; break;
            }
        }
        else
        {
            for (int i = 0; i < byReach.Count; i++)
            {
                if (s.Ball.Owner == byReach[i].idx) continue;
                if (support < 0) { support = byReach[i].idx; continue; }
                if (cover < 0) { cover = byReach[i].idx; break; }
            }
        }

        Vector3[] oppPosArr = oppPos.ToArray();
        Vector3[] oppVelArr = oppVel.ToArray();
        Vector3 ballVel = Mx.Flat(s.Ball.Vel);
        bool transitionThreat = !teamInPoss && ballVel.LengthSquared() > 25f && (ballVel.X * -attackSign) > 2.5f;

        foreach (var p in s.Players)
        {
            if (p.Team != team || p.SentOff) continue;
            var a = new Assignment { PlayerIndex = p.Index, MovementTarget = p.Pos, FacingTarget = ballNow };
            if (p.IsKeeper)
            {
                a.Role = "keeper"; a.Intent = teamInPoss ? "support_keeper" : "protect_goal";
                a.MovementTarget = ownGoal + new Vector3(attackSign * 2.5f, 0, Math.Clamp(ballRef.Z * 0.25f, -4f, 4f));
                a.SpeedLimit = 6f;
                list.Add(a); continue;
            }

            float space = PlayerPerception.SpaceScore(p.Pos, oppPosArr);
            if (teamInPoss)
            {
                if (s.Ball.Owner == p.Index)
                {
                    a.Role = "carrier"; a.Intent = "carrier"; a.FacingTarget = oppGoal; a.SpeedLimit = PlayerMaxSpeed(p);
                }
                else if (p.Index == support)
                {
                    a.Role = "support"; a.Intent = "support";
                    a.MovementTarget = SupportTarget(p, s, team, attackSign, ballRef, oppPosArr);
                    a.FacingTarget = ballNow;
                    a.SpeedLimit = 7.2f;
                }
                else if (p.Index == cover)
                {
                    a.Role = "cover"; a.Intent = "support_cover";
                    a.MovementTarget = CoverTarget(p, ownGoal, ballRef, attackSign, 0.35f);
                    a.FacingTarget = ballNow;
                    a.SpeedLimit = 6.8f;
                }
                else
                {
                    a.Role = space > 0.40f ? "support" : "recycle";
                    a.Intent = a.Role;
                    a.MovementTarget = SupportTarget(p, s, team, attackSign, ballRef, oppPosArr);
                    a.SpeedLimit = 6.8f;
                }
            }
            else
            {
                if (p.Index == presser && !transitionThreat)
                {
                    a.Role = "press"; a.Intent = "press"; a.Pressing = true; a.ShouldSprint = byReach.Count > 0 && byReach[0].t < 1.5f;
                    a.MovementTarget = PressTarget(p, s, ballRef, ownGoal);
                    a.FacingTarget = ballNow;
                    a.SpeedLimit = PlayerMaxSpeed(p);
                    a.Priority = 1f;
                }
                else if (p.Index == presser && transitionThreat)
                {
                    a.Role = "recover"; a.Intent = "transition_recover";
                    a.MovementTarget = RecoverTarget(p, ownGoal, ballRef, attackSign, true);
                    a.SpeedLimit = 8.0f;
                }
                else if (p.Index == cover)
                {
                    a.Role = "cover"; a.Intent = transitionThreat ? "transition_cover" : "cover";
                    a.MovementTarget = CoverTarget(p, ownGoal, ballRef, attackSign, transitionThreat ? 0.22f : 0.38f);
                    a.FacingTarget = ballNow;
                    a.SpeedLimit = 7.5f;
                }
                else
                {
                    a.Role = "recover"; a.Intent = transitionThreat ? "transition_shape" : "shape";
                    a.MovementTarget = RecoverTarget(p, ownGoal, ballRef, attackSign, transitionThreat);
                    a.MarkTarget = FindMark(p, s, opp, ballNow, ownGoal);
                    a.SpeedLimit = transitionThreat ? 7.8f : 6.8f;
                }
            }

            // Stability bookkeeping: track how long the assigned role has been held.
            // (True target-consistent hysteresis enforcement is a follow-up; this fixes the broken counter.)
            bool roleChanged = _prevRole.TryGetValue(p.Index, out var prev) && prev != a.Role;
            _roleHoldTicks[p.Index] = roleChanged ? 0 : (_roleHoldTicks.TryGetValue(p.Index, out int h) ? h + 1 : 1);
            _prevRole[p.Index] = a.Role;
            list.Add(a);
        }
        int newPresser = -1;
        foreach (var a in list) if (a.Role == "press") { newPresser = a.PlayerIndex; break; }
        if (team >= 0 && team < _prevPresserByTeam.Length) _prevPresserByTeam[team] = newPresser;
        return list;
    }

    private static float PlayerMaxSpeed(PlayerState p) => p.MaxSpeed;

    private static float PlayerAccel(PlayerState p)
        => Math.Clamp(9f + p.Spec.Pace * 6f + p.Spec.Defending * 3f, 8f, 18f);

    private static Vector3 PressTarget(PlayerState p, MatchState s, Vector3 ballRef, Vector3 ownGoal)
    {
        // Close to ball but stay goal-side when near own box.
        Vector3 goalDir = Mx.FlatDir(ballRef, ownGoal);
        float dGoal = Mx.FlatDist(ballRef, ownGoal);
        float standoff = dGoal < 28f ? 1.2f : 2.0f;
        Vector3 t = ballRef + goalDir * standoff;
        return ClampPitch(t);
    }

    private static Vector3 CoverTarget(PlayerState p, Vector3 ownGoal, Vector3 ballRef, int attackSign, float lerp)
    {
        Vector3 goalSide = Vector3.Lerp(ballRef, ownGoal, 0.40f);
        goalSide.X += -attackSign * 1.0f;
        goalSide.Z = Math.Clamp(p.Pos.Z * 0.65f + ballRef.Z * 0.35f, -Mx.HalfWidth + 2f, Mx.HalfWidth - 2f);
        return ClampPitch(Vector3.Lerp(p.Pos, goalSide, Math.Clamp(lerp + 0.25f, 0f, 1f)));
    }

    private static Vector3 RecoverTarget(PlayerState p, Vector3 ownGoal, Vector3 ballRef, int attackSign, bool transition)
    {
        float depth = transition ? 0.50f : 0.38f;
        Vector3 t = Vector3.Lerp(ballRef, ownGoal, depth);
        // Preserve team width and avoid collapsing shape.
        t.Z = Math.Clamp(p.Pos.Z * 0.82f + ballRef.Z * 0.18f, -Mx.HalfWidth + 2f, Mx.HalfWidth - 2f);
        t.X += -attackSign * (transition ? 1.0f : 0f);
        return ClampPitch(t);
    }

    private static Vector3 SupportTarget(PlayerState p, MatchState s, int team, int attackSign, Vector3 ballRef, Vector3[] oppPos)
    {
        // Find a support spot: ahead/side of ball, in space, onside-safe.
        float best = float.MinValue;
        Vector3 bestPos = p.Pos;
        float baseX = ballRef.X + attackSign * 8f;
        float[] zOffs = { -18f, -12f, -6f, 0f, 6f, 12f, 18f };
        float[] xOffs = { 0f, 6f, 12f, -4f };
        foreach (float xo in xOffs)
        foreach (float zo in zOffs)
        {
            Vector3 c = ClampPitch(new Vector3(baseX + xo * attackSign, 0, Math.Clamp(ballRef.Z + zo, -Mx.HalfWidth + 2f, Mx.HalfWidth - 2f)));
            float space = PlayerPerception.SpaceScore(c, oppPos, 9f);
            float forward = (c.X - ballRef.X) * attackSign;
            float dist = Mx.FlatDist(p.Pos, c);
            float score = space * 3f + Math.Clamp(forward / 20f, -1f, 1f) * 1.5f - dist * 0.04f;
            if (p.Role == Role.Defender) score -= Math.Max(0f, forward - 5f) * 0.08f;
            if (p.Role == Role.Forward) score += Math.Max(0f, forward) * 0.03f;
            if (score > best) { best = score; bestPos = c; }
        }
        return bestPos;
    }

    private static int FindMark(PlayerState p, MatchState s, int opp, Vector3 ballNow, Vector3 ownGoal)
    {
        int mark = -1; float best = 14f;
        foreach (var q in s.Players)
        {
            if (q.Team != opp || q.SentOff || q.IsKeeper) continue;
            if (s.Ball.Owner == q.Index) continue;
            if (Mx.FlatDist(q.Pos, ballNow) < 6f) continue;
            float d = Mx.FlatDist(p.Pos, q.Pos);
            float goalSide = Mx.FlatDist(q.Pos, ownGoal);
            float score = d + goalSide * 0.05f;
            if (score < best) { best = score; mark = q.Index; }
        }
        return mark;
    }

    private static Vector3 ClampPitch(Vector3 v)
        => new(Math.Clamp(v.X, -Mx.HalfLength + 1f, Mx.HalfLength - 1f), 0, Math.Clamp(v.Z, -Mx.HalfWidth + 1f, Mx.HalfWidth - 1f));
}
