// Arena FC - the ball in the air: controlling a high ball (foot, thigh/knee,
// chest), jumping headers and aerial duels, player-directed first touches, and
// first-time headers / volleys at goal.
//
// Before: any ball above 1.55 m could not be played by anyone, the first touch
// always killed the ball dead at the receiver's feet whatever the stick said,
// and there was no way to head or volley at goal.
using System;
using System.Numerics;

namespace ArenaFC.Core;

public sealed partial class MatchEngine
{
    /// <summary>Where a ball in flight comes down to height <paramref name="h"/> (ballistic,
    /// with a little drag).  Falls back to the ground if it never rises to h.</summary>
    public static Vector3 LandingPoint(BallState b, float h)
    {
        const float g = 9.81f;
        float y0 = b.Pos.Y, vy = b.Vel.Y;
        float disc = vy * vy + 2f * g * (y0 - h);
        if (disc < 0f) { h = Mx.BallRadius; disc = vy * vy + 2f * g * (y0 - h); }
        float t = MathF.Max(0f, (vy + MathF.Sqrt(MathF.Max(0f, disc))) / g);
        return new Vector3(b.Pos.X + b.Vel.X * t * .93f, 0f, b.Pos.Z + b.Vel.Z * t * .93f);
    }

    /// <summary>Where players should go for the ball: the landing point of a loose
    /// ball in the air (chest/head height), otherwise the ball.  Chasing the ball's
    /// current position meant a high ball almost always dropped into space
    /// (a player was near it for ~1 s of the ~10 s per match it spent in the air).</summary>
    public Vector3 BallFocus()
    {
        var b = State.Ball;
        if (b.Owner < 0 && !b.HasPending && (b.Pos.Y > .7f || b.Vel.Y > 1.5f)) return LandingPoint(b, 1.3f);
        return b.Pos;
    }

    /// <summary>Highest ball a player can head, jumping.</summary>
    public static float HeaderReach(PlayerState p) => p.Spec.Height + .55f;

    /// <summary>Aerial duel strength: height, power and the relevant skill.</summary>
    private float AerialScore(PlayerState p, Vector3 ball)
        => p.Spec.Height * 2f + p.Spec.Bulk * .6f + MathF.Max(p.Spec.Defending, p.Spec.Shooting) * .8f
           - Mx.FlatDist(p.Pos, ball) * .8f + Rng.Next() * .5f;

    /// <summary>Which part of the body controls a ball arriving at this height.</summary>
    public static string TouchFor(float ballY, float fallSpeed)
        => ballY > 1.55f ? "header"
         : ballY > .95f ? (fallSpeed < -1.5f && ballY > 1.25f ? "header" : "chest_control")
         : ballY > .45f ? "thigh_control"
         : "trap";

    /// <summary>A human's stick at the moment of a first touch steers it:
    /// recorded every tick while the touch is in progress.</summary>
    private void RecordTouchIntent(PlayerState p, PlayerCommand cmd)
    {
        var b = State.Ball;
        if (!(b.HasPending && b.PendingKind == 2 && b.PendingFrom == p.Index)) return;
        p.TouchDir = cmd.Move;
        p.TouchKnock = cmd.Sprint;
    }

    /// <summary>Called when a first-touch capture completes: a steered touch sends the
    /// ball 1-3 m into space in the stick direction (further when sprinting) and the
    /// player runs onto it; no stick = the ball is killed at his feet.</summary>
    private bool DirectedTouch(PlayerState p)
    {
        var dir2 = p.TouchDir;
        p.TouchDir = Vector2.Zero;
        if (dir2.LengthSquared() < .2f) return false;
        var b = State.Ball;
        var dir = Vector3.Normalize(new Vector3(dir2.X, 0, dir2.Y));
        float quality = Mx.Clamp(p.FirstTouchQuality, .1f, 1f);
        float knock = (p.TouchKnock ? 6.0f : 3.2f) * (1.25f - quality * .35f);
        p.TouchKnock = false;
        b.Owner = -1;
        b.Pos = new Vector3(p.Pos.X, Mx.BallRadius, p.Pos.Z) + dir * .45f;
        b.Vel = dir * knock;
        b.FreeTime = 0f; b.NoPickup = .14f;
        b.LastTouch = p.Index; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
        p.PossessionLock = .14f;
        p.Target = p.Pos + dir * (knock * .7f);
        p.Facing = dir;
        return true;
    }

    /// <summary>First-time header or volley.  Shot = at goal (aim with the stick for a
    /// side of the goal), pass = to the best team-mate.  The ball is struck where it is.</summary>
    private void FirstTimeStrike(PlayerState p, bool atGoal, float charge, Vector2 aim)
    {
        var S = State; var b = S.Ball;
        bool header = b.Pos.Y > 1.25f;
        // 4.4: back to goal with the ball at head height - a good finisher goes for
        // the bicycle kick instead of a header (less accurate, much more power).
        bool bicycle = atGoal && b.Pos.Y > 1.1f && b.Pos.Y < 2.1f && p.Spec.Shooting > .55f
                       && Vector3.Dot(p.Facing, Mx.FlatDir(p.Pos, GoalPos(p.Team))) < -.3f;
        if (bicycle) header = false;
        Vector3 target;
        if (atGoal)
        {
            var goal = GoalPos(p.Team);
            float side = aim.LengthSquared() > .1f ? MathF.Sign(aim.Y != 0 ? aim.Y : aim.X) : (Rng.Next() < .5f ? -1f : 1f);
            float accuracy = (header ? MathF.Max(p.Spec.Shooting, p.Spec.Defending) : p.Spec.Shooting) * .6f + .3f;
            if (bicycle) accuracy *= .7f;
            float z = side * Mx.Lerp(Mx.GoalHalfWidth * .25f, Mx.GoalHalfWidth * .85f, accuracy * Rng.Next() + (1 - accuracy) * .5f);
            z += Rng.Signed() * (1.3f - accuracy) * 2.2f;
            target = new Vector3(goal.X, header ? .35f : Rng.Range(.3f, 1.6f), z);
            S.Shots[p.Team]++;
        }
        else
        {
            int t = FindBestPassTarget(p, false, false, aim);
            target = t >= 0 ? S.Players[t].Pos : p.Pos + p.Facing * 12f;
            S.Passes[p.Team]++;
        }
        Vector3 to = target - b.Pos;
        float flat = MathF.Sqrt(to.X * to.X + to.Z * to.Z);
        float speed = header ? 11f + charge * 9f : 17f + charge * 13f;
        if (!atGoal) speed = MathF.Min(speed, 8f + flat * .45f);
        Vector3 dirFlat = flat > .01f ? new Vector3(to.X / flat, 0, to.Z / flat) : p.Facing;
        float t2 = flat / speed;
        float vy = (to.Y + .5f * 9.81f * t2 * t2) / MathF.Max(t2, .05f);   // reach the target height
        vy = Mx.Clamp(vy, header ? -6f : -3f, 7f);
        b.Owner = -1; b.HasPending = false; b.PendingKind = 0; b.PendingFrom = -1;
        b.Vel = dirFlat * speed + new Vector3(0, vy, 0);
        b.FreeTime = 0f; b.NoPickup = .15f;
        if (bicycle)
        {
            // Struck over his own head: the ball leaves from the goal side of him (it
            // used to fly back through him and he headed it clear), and he is on his
            // back for a moment.
            b.Pos = new Vector3(p.Pos.X, MathF.Max(b.Pos.Y, 1.2f), p.Pos.Z) + dirFlat * .6f;
            b.NoPickup = .5f;
        }
        b.LastTouch = p.Index; b.LastTouchSide = p.Team; b.LastTouchPos = b.Pos;
        p.PossessionLock = bicycle ? .9f : .3f;
        if (!bicycle) p.Facing = dirFlat;
        SetAction(p, bicycle ? "bicycle" : header ? "header" : "volley", bicycle ? .9f : .45f, bicycle ? .5f : .4f);
        if (atGoal)
        {
            if (IsOnTarget(b.Pos, b.Vel, GoalPos(p.Team))) S.ShotsOnTarget[p.Team]++;
            S.Xg[p.Team] += XgFrom(p.Pos, p.Team, false) * (header ? .7f : .85f);
            Add(EventKind.Shot, bicycle ? $"{p.Spec.DisplayName} goes for the bicycle kick!"
                : header ? $"{p.Spec.DisplayName} goes for goal with a header!" : $"{p.Spec.DisplayName} hits it first time on the volley!");
        }
        else Add(EventKind.Pass, header ? $"{p.Spec.DisplayName} heads it on." : $"{p.Spec.DisplayName} volleys it on.");
    }

    /// <summary>Is a loose ball in the air within this player's strike range?</summary>
    private bool CanStrikeInAir(PlayerState p)
    {
        var b = State.Ball;
        return b.Owner < 0 && !b.HasPending && b.Pos.Y > .5f && b.Pos.Y < HeaderReach(p)
               && Mx.FlatDist(p.Pos, b.Pos) < 1.5f && p.PossessionLock <= 0f;
    }

    /// <summary>AI attackers attack crosses: header / volley at goal from inside ~18 m.</summary>
    private bool AiAttackHighBall(PlayerState p)
    {
        if (p.IsKeeper || !CanStrikeInAir(p)) return false;
        var b = State.Ball;
        if (b.LastTouchSide != p.Team && b.LastTouchSide >= 0 && Mx.FlatDist(p.Pos, GoalPos(p.Team)) > 18f) return false;
        if (Mx.FlatDist(p.Pos, GoalPos(p.Team)) > 18f) return false;
        FirstTimeStrike(p, true, Rng.Range(.45f, .9f), Vector2.Zero);
        return true;
    }

    /// <summary>AI wide player in the final third crosses into the box when a
    /// team-mate is there (crosses were almost never played, so the aerial game
    /// barely existed).</summary>
    private bool AiCross(PlayerState p)
    {
        var goal = GoalPos(p.Team);
        if (MathF.Abs(p.Pos.Z) < Mx.HalfWidth * .5f || MathF.Abs(goal.X - p.Pos.X) > 30f) return false;
        PlayerState? best = null; float bestD = 99f;
        foreach (var q in State.Players)
        {
            if (q.Team != p.Team || q.Index == p.Index || q.IsKeeper || q.SentOff) continue;
            float gd = Mx.FlatDist(q.Pos, goal);
            if (gd < 17f && MathF.Abs(q.Pos.Z) < 14f && gd < bestD) { bestD = gd; best = q; }
        }
        if (best == null || Rng.Next() > .22f) return false;
        PassTo(p, best, 18f, false, true);
        return true;
    }
}
