// Arena FC - the referee enforces the Laws instead of the engine physically
// preventing things.  Players are free to encroach at a free kick, run off with
// a set piece or throw a punch; the consequences are what the Laws say:
//   * Law 13/15: an opponent inside 9.15 m at a free kick / corner / goal kick
//     (2 m at a throw-in) before the ball is played is cautioned and sent back;
//     a second one is a second yellow.
//   * Law 13: the taker touching the ball again before anyone else is an
//     indirect free kick to the opposition.
//   * A taker who carries the ball away instead of playing it: free kick to
//     the opposition (a throw-in to them if it was a throw-in).
//   * Law 12: striking or headbutting an opponent is violent conduct - a
//     straight red card and a direct free kick (penalty in the box).  If the
//     referee does not see it, VAR reviews it at the next stoppage (or stops
//     play itself within a few seconds) and the player is sent off.
using System;
using System.Numerics;

namespace ArenaFC.Core;

public sealed partial class MatchEngine
{
    /// <summary>Required distance for opponents at the current restart: 2 m at a
    /// throw-in, 9.15 m (10 yards) at free kicks, corners, goal kicks and penalties.</summary>
    private float RestartDistance(PlayerState taker) => IsThrowInHold(taker) ? 2f : 9.15f;

    /// <summary>Law 13/16: at a goal kick, or a free kick to the defending team inside
    /// its own penalty area, opponents must be outside the penalty area until the
    /// ball is in play (it no longer has to leave the area).</summary>
    private bool OwnAreaRestart(PlayerState taker)
    {
        if (!taker.MustPlayBall || IsThrowInHold(taker)) return false;
        var g = OwnGoalPos(taker.Team);
        return InArea(State.RestartPos, g.X);
    }

    internal static bool InArea(Vector3 pos, float goalX, float margin = 0f)
        => MathF.Abs(pos.X - goalX) < 16.5f + margin && MathF.Abs(pos.Z) < 20.16f + margin;

    /// <summary>Just outside the penalty area on the pitch side, keeping the
    /// player's channel.</summary>
    private static Vector3 OutsideArea(Vector3 from, float goalX)
        => new(goalX - MathF.Sign(goalX) * 17.6f, 0, Mx.Clamp(from.Z, -Mx.HalfWidth + 1f, Mx.HalfWidth - 1f));

    /// <summary>A spot on the restart circle, on the pitch: straight out from the ball
    /// if that is on the pitch, otherwise walking round the circle.  (Pushing a
    /// player straight out near a line put him off the pitch; the clamp then put him
    /// back inside the circle and the AI was cautioned for encroaching.)</summary>
    private static Vector3 OutsideCircle(Vector3 ball, Vector3 from, float r)
    {
        Vector3 d = Mx.FlatDir(ball, from);
        if (d.LengthSquared() < .5f) d = Vector3.UnitX;
        for (int k = 0; k <= 12; k++)
        {
            foreach (int sgn in new[] { 1, -1 })
            {
                float a = sgn * k * MathF.PI / 12f;
                var dir = new Vector3(d.X * MathF.Cos(a) - d.Z * MathF.Sin(a), 0, d.X * MathF.Sin(a) + d.Z * MathF.Cos(a));
                Vector3 c = ball + dir * r;
                if (MathF.Abs(c.X) < Mx.HalfLength - .3f && MathF.Abs(c.Z) < Mx.HalfWidth - .3f) return new Vector3(c.X, 0, c.Z);
                if (k == 0) break;
            }
        }
        return new Vector3(ball.X + d.X * r, 0, ball.Z + d.Z * r);
    }

    /// <summary>Caution a player; a second caution is a sending-off.</summary>
    private void Caution(PlayerState p, string reason)
    {
        AddStoppage(15f);
        p.Cards++;
        State.YellowCards[p.Team]++;
        if (p.Cards >= 2) SendOff(p, "Second yellow card (" + reason + ")");
        else Add(EventKind.Card, $"Yellow card - {p.Spec.DisplayName} ({ClubShort(p.Team)}) for {reason}.");
    }

    /// <summary>AI players respect the restart distance by choice (their target is
    /// kept outside it); nothing physically stops a human from encroaching.</summary>
    private void RespectRestartDistance(PlayerState p)
    {
        var b = State.Ball;
        if (b.Owner < 0 || b.Owner == p.Index) return;
        var holder = State.Players[b.Owner];
        if (!holder.MustPlayBall || holder.Team == p.Team) return;
        // The keeper facing a penalty stays on his line (EnforceRestartLaws exempts
        // him too); walking him round the 10-yard circle pulled him off-centre.
        if (p.IsKeeper && !IsThrowInHold(holder) && MathF.Abs(b.Pos.X) > Mx.HalfLength - 12f) return;
        float need = RestartDistance(holder) + 1.4f;
        if (Mx.FlatDist(p.Target, b.Pos) < need)
        {
            Vector3 from = Mx.FlatDist(p.Pos, b.Pos) > .1f ? p.Pos : OwnGoalPos(p.Team);
            p.Target = OutsideCircle(b.Pos, from, need);
        }
        if (OwnAreaRestart(holder))
        {
            float gx = OwnGoalPos(holder.Team).X;
            if (InArea(p.Target, gx, 1f)) p.Target = OutsideArea(p.Target, gx);
        }
        p.Pressing = false;
    }

    /// <summary>Runs every tick after movement: the referee's set-piece rulings.</summary>
    private void EnforceRestartLaws(float dt)
    {
        var S = State;
        var b = S.Ball;
        if (S.Phase != Phase.Play) { S.SetPieceTaker = -1; return; }
        if (IsShootout) return;   // a shootout kick is only ever a goal or a miss

        // ---- double touch -------------------------------------------------
        if (S.SetPieceTaker >= 0)
        {
            var t = S.Players[S.SetPieceTaker];
            if (b.Owner != t.Index && !(b.HasPending && b.PendingFrom == t.Index)) S.SetPieceLeftFoot = true;
            S.SetPieceTimer += dt;
            if (S.SetPieceLeftFoot && b.Owner == t.Index)
            {
                S.SetPieceTaker = -1;
                Add(EventKind.Foul, $"Double touch by {t.Spec.DisplayName} - indirect free kick.");
                AwardFreeKick(1 - t.Team, b.Pos, false);
                return;
            }
            // Anyone else touching it (or a few seconds passing) ends the watch.
            if ((b.Owner >= 0 && b.Owner != t.Index) || S.SetPieceTimer > 6f) S.SetPieceTaker = -1;
        }

        if (b.Owner < 0) return;
        var holder = S.Players[b.Owner];
        if (!holder.MustPlayBall) return;

        // ---- taker carries the ball away instead of playing it -------------
        if (Mx.FlatDist(b.Pos, S.RestartPos) > 1.6f)
        {
            bool throwIn = MathF.Abs(S.RestartPos.Z) > Mx.HalfWidth - .6f && MathF.Abs(S.RestartPos.X) < Mx.HalfLength - 1.5f;
            holder.MustPlayBall = false;
            if (throwIn)
            {
                Add(EventKind.Foul, $"Foul throw by {holder.Spec.DisplayName} - throw-in to {ClubShort(1 - holder.Team)}.");
                b.Owner = -1; b.Vel = Vector3.Zero;
                S.RestartSide = 1 - holder.Team;
                S.Phase = Phase.ThrowIn; S.PhaseTimer = 1.1f;
            }
            else
            {
                Add(EventKind.Foul, $"{holder.Spec.DisplayName} didn't take the set piece - free kick to {ClubShort(1 - holder.Team)}.");
                AwardFreeKick(1 - holder.Team, b.Pos, false);
            }
            return;
        }

        // ---- encroachment ----------------------------------------------------
        float need = RestartDistance(holder);
        bool areaRule = OwnAreaRestart(holder);
        float areaGx = OwnGoalPos(holder.Team).X;
        foreach (var q in S.Players)
        {
            if (q.Team == holder.Team || q.SentOff) continue;
            // In the area but beyond 10 yards at a goal kick: the referee waves him
            // out (no caution unless he is also inside 9.15 m).
            if (areaRule && InArea(q.Pos, areaGx, -.3f) && Mx.FlatDist(q.Pos, b.Pos) >= need - .35f)
            {
                q.Pos = OutsideArea(q.Pos, areaGx); q.Target = q.Pos; q.Vel = Vector3.Zero;
                continue;
            }
            if (q.IsKeeper && !IsThrowInHold(holder) && MathF.Abs(b.Pos.X) > Mx.HalfLength - 12f) continue; // keeper on his line at a penalty
            float d = Mx.FlatDist(q.Pos, b.Pos);
            if (d < need - .35f)
            {
                if (q.EncroachedAt != S.RestartId)
                {
                    q.EncroachedAt = S.RestartId;     // one caution per restart; after that he is just sent back
                    Add(EventKind.Foul, $"Encroachment - {q.Spec.DisplayName} wasn't back the full {(need < 3f ? "2 metres" : "10 yards")}.");
                    Caution(q, "encroachment");
                }
                if (!q.SentOff)
                {
                    // The referee sends him back; the kick is retaken.
                    q.Pos = OutsideCircle(b.Pos, d > .1f ? q.Pos : OwnGoalPos(q.Team), need + .5f);
                    q.Target = q.Pos; q.Vel = Vector3.Zero;
                }
            }
        }
    }

    // ------------------------------------------------------------------ violent conduct

    /// <summary>Punch or headbutt by a human player.  Only the human can do it; the
    /// referee or VAR deals with it.</summary>
    private void ViolentConduct(PlayerState p, bool headbutt)
    {
        if (p.ActionTimer > 0f && (p.Action == "punch" || p.Action == "headbutt")) return;
        PlayerState? victim = null; float best = headbutt ? 1.0f : 1.35f;
        foreach (var q in State.Players)
        {
            if (q.Team == p.Team || q.SentOff) continue;
            float d = Mx.FlatDist(p.Pos, q.Pos);
            if (d < best) { best = d; victim = q; }
        }
        SetAction(p, headbutt ? "headbutt" : "punch", .55f, .35f);
        if (victim == null) return;                       // swinging at thin air is no offence
        p.Facing = Mx.FlatDir(p.Pos, victim.Pos);
        SetAction(victim, "knocked_down", 1.6f, .3f);
        victim.Vel *= .1f;
        victim.PossessionLock = 1.2f;
        var b = State.Ball;
        if (b.Owner == victim.Index) { b.Owner = -1; b.Vel = victim.Vel; b.FreeTime = 0f; }

        // The referee follows the ball: the further from it, the likelier he misses it.
        float fromBall = Mx.FlatDist(p.Pos, b.Pos);
        float seen = Mx.Clamp(1.05f - fromBall / 45f, .25f, .95f);
        string what = headbutt ? "headbutt" : "punch";
        if (Rng.Next() < seen)
        {
            Add(EventKind.Foul, $"Violent conduct! {p.Spec.DisplayName} with a {what} on {victim.Spec.DisplayName}.");
            AwardViolentConduct(p, victim.Team, p.Pos);
        }
        else
        {
            // Unseen: VAR has it.  Play goes on for now.
            State.VarOffender = p.Index;
            State.VarVictimTeam = victim.Team;
            State.VarSpot = p.Pos;
            State.VarTimer = 0f;
            Add(EventKind.Info, "The referee waves play on...");
        }
    }

    private void AwardViolentConduct(PlayerState offender, int victimTeam, Vector3 spot)
    {
        AddStoppage(60f);
        State.Fouls[offender.Team]++;
        SendOff(offender, "Straight red card (violent conduct)");
        float ownGoalX = OwnGoalPos(offender.Team).X;
        bool inBox = MathF.Abs(spot.X - ownGoalX) < 16.5f && MathF.Abs(spot.Z) < 20.16f;
        if (inBox) AwardFreeKick(victimTeam, new Vector3(-SideSign(offender.Team) * (Mx.HalfLength - 11f), 0, 0), true);
        else AwardFreeKick(victimTeam, spot, false);
    }

    /// <summary>VAR: an unseen red-card offence is reviewed at the next stoppage, or
    /// play is stopped for it after a few seconds.</summary>
    private void UpdateVar(float dt)
    {
        var S = State;
        if (S.VarOffender < 0) return;
        S.VarTimer += dt;
        bool stoppage = S.Phase != Phase.Play;
        if (!stoppage && S.VarTimer < 6f) return;
        var off = S.Players[S.VarOffender];
        int victimTeam = S.VarVictimTeam;
        Vector3 spot = S.VarSpot;
        S.VarOffender = -1;
        if (off.SentOff) return;
        Add(EventKind.Info, $"VAR review: possible violent conduct by {off.Spec.DisplayName}...");
        Add(EventKind.Foul, $"After review - violent conduct by {off.Spec.DisplayName}.");
        if (stoppage && S.Phase is Phase.Goal)
        {
            // A goal scored by the offending side after the incident is cancelled.
            int scorer = 1 - S.KickoffSide;                // the side that just scored
            if (scorer == off.Team && S.Score[scorer] > 0) { S.Score[scorer]--; Add(EventKind.Info, "Goal disallowed after VAR review."); }
        }
        AwardViolentConduct(off, victimTeam, spot);
    }
}
