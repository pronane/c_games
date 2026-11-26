using System;
using System.Collections.Generic;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Core.Football;

/// <summary>
/// Deterministic tactical coordinator. Assigns team roles (press, cover, support,
/// recover) from shared perception. Simulation remains authoritative.
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
        if (ballPred != null && ballPred.Samples.Count > 0) ballRef = ballPred.At(0.25f).Position;

        // Rank by time to ball
        var byReach = new List<(int idx, float t)>();
        foreach (var p in s.Players)
        {
            if (p.Team != team || p.SentOff || p.IsKeeper) continue;
            float t = PlayerPerception.TimeToReach(p.Pos, p.Vel, ballRef, 7.5f, 12f);
            byReach.Add((p.Index, t));
        }
        byReach.Sort((a,b) => a.t.CompareTo(b.t));
        int presser = byReach.Count > 0 ? byReach[0].idx : -1;
        int cover = byReach.Count > 1 ? byReach[1].idx : -1;

        foreach (var p in s.Players)
        {
            if (p.Team != team || p.SentOff) continue;
            var a = new Assignment { PlayerIndex = p.Index, MovementTarget = p.Pos, FacingTarget = ballNow };
            if (p.IsKeeper) { a.Role = "keeper"; a.Intent = "hold"; list.Add(a); continue; }
            bool teamInPoss = s.Ball.Owner >= 0 && s.Ball.Owner < s.Players.Length && s.Players[s.Ball.Owner].Team == team;
            if (teamInPoss)
            {
                if (s.Ball.Owner == p.Index) { a.Role = "carrier"; a.Intent = "carrier"; }
                else
                {
                    float space = PlayerPerception.SpaceScore(p.Pos, oppPos.ToArray());
                    a.Role = space > 0.45f ? "support" : "recycle";
                    a.Intent = a.Role;
                    a.SpeedLimit = 7.0f;
                }
            }
            else
            {
                float attackSign = team == 0 ? 1f : -1f;
                Vector3 bVel = Mx.Flat(s.Ball.Vel);
                bool transitionThreat = bVel.LengthSquared() > 36f && (bVel.X * -attackSign) > 3f;
                if (p.Index == presser && !transitionThreat) { a.Role = "press"; a.Intent = "press"; a.Pressing = true; a.ShouldSprint = true; a.MovementTarget = ballRef; a.SpeedLimit = 8.5f; }
                else if (p.Index == presser && transitionThreat) { a.Role = "recover"; a.Intent = "transition_recover"; a.MovementTarget = Vector3.Lerp(p.Pos, new Vector3(p.Pos.X - attackSign * 8f, 0, p.Pos.Z), 0.6f); a.SpeedLimit = 8.0f; }
                else if (p.Index == cover) { a.Role = "cover"; a.Intent = transitionThreat ? "transition_cover" : "cover"; a.MovementTarget = Vector3.Lerp(p.Pos, ballRef, transitionThreat ? 0.20f : 0.35f); a.SpeedLimit = 7.5f; }
                else { a.Role = "recover"; a.Intent = transitionThreat ? "transition_shape" : "shape"; a.MovementTarget = Vector3.Lerp(p.Pos, new Vector3(p.Pos.X - attackSign * (transitionThreat ? 6f : 0f), 0, ballRef.Z * 0.3f), transitionThreat ? 0.45f : 0f); a.SpeedLimit = 7.0f; }
            }
            list.Add(a);
        }
        return list;
    }
}
