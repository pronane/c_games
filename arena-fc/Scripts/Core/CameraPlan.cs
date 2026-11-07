// Arena FC - pure-C# broadcast camera plan.
//
// The 06.11.2026 recording showed the old camera whipping around the pitch: the
// player/shoulder modes were built from the player's INSTANT facing, so every
// stick direction change spun the camera, and near a corner it ended up outside
// the pitch looking at the stands.  The first fix gave the ball-following modes a
// fixed sideline orientation.  The SECOND pass removes the remaining continuous
// drift: a dead-zone focus point only recentres after the ball/player leave the
// inner frame, and camera height no longer breathes with ball-player separation.
// The plan stays Godot-free so the headless core suite can assert the framing.
using System;
using System.Numerics;

namespace ArenaFC.Core;

public struct CameraPlan
{
    public Vector3 Target;
    public Vector3 Look;
    public Vector3 Up;
    public float Fov;
}

public static class BroadcastPlan
{
    public const int ModeCount = 5;

    public static string ModeName(int mode) => mode switch
    {
        0 => "Broadcast", 1 => "Ball follow", 2 => "Shoulder", 3 => "Sideline", _ => "Tactical"
    };

    private static Vector3 ClampPitch(Vector3 v, float marginX, float marginZ)
    {
        return new Vector3(
            Mx.Clamp(v.X, -Mx.HalfLength - marginX, Mx.HalfLength + marginX),
            v.Y,
            Mx.Clamp(v.Z, -Mx.HalfWidth - marginZ, Mx.HalfWidth + marginZ));
    }

    /// <summary>Weighted midpoint of the ball and the controlled player.  The
    /// renderer keeps this in a dead zone instead of chasing it every frame.</summary>
    public static Vector3 Focus(Vector3 ball, Vector3 player)
    {
        Vector3 focus = Vector3.Lerp(new Vector3(ball.X, 0f, ball.Z),
                                     new Vector3(player.X, 0f, player.Z), .45f);
        return ClampPitch(focus, 4f, 4f);
    }

    public static float FocusDeadzone(int mode) => mode == 4 ? 14f : 5.5f;

    /// <summary>Advance the held camera focus.  Small ball/player movement does not
    /// move the camera at all; a breakaway eases toward the desired focus but keeps
    /// it one dead-zone radius behind so the shot never snaps.</summary>
    public static Vector3 AdvanceFocus(Vector3 previous, Vector3 desired, float dt, int mode)
    {
        float dead = FocusDeadzone(mode);
        Vector3 delta = desired - previous;
        float d = delta.Length();
        if (d <= dead || d < 1e-5f) return previous;
        Vector3 destination = previous + delta * ((d - dead) / d);
        float rate = mode == 4 ? 1.1f : 1.8f;
        float k = 1f - MathF.Exp(-dt * rate);
        return Vector3.Lerp(previous, destination, k);
    }

    /// <summary>Stable camera framing for one render frame.  `heading` is the
    /// SMOOTHED player direction supplied by BroadcastCamera, never the raw
    /// per-tick facing.  Ball and controlled player are both kept in view.</summary>
    public static CameraPlan Compute(int mode, Vector3 ball, Vector3 player, Vector3 heading)
        => Compute(mode, ball, player, heading, Focus(ball, player));

    public static CameraPlan Compute(int mode, Vector3 ball, Vector3 player, Vector3 heading, Vector3 focus)
    {
        focus = ClampPitch(focus, 4f, 4f);
        float separation = Vector2.Distance(new Vector2(ball.X, ball.Z),
                                           new Vector2(player.X, player.Z));
        float widen = Mx.Clamp(separation * .18f, 0f, 9f);
        Vector3 h = heading.LengthSquared() > 1e-6f ? Vector3.Normalize(heading) : new Vector3(1f, 0f, 0f);
        Vector3 side = new(-h.Z, 0f, h.X);
        Vector3 up = new(0f, 1f, 0f);
        Vector3 target, look;
        float fov;

        switch (mode)
        {
            case 1: // closer ball-following sideline shot, like the reference clip
                target = ClampPitch(new Vector3(focus.X - 4f, 20f, focus.Z + 30f), 12f, 20f);
                look = ClampPitch(new Vector3(focus.X, 1.1f, focus.Z), 2f, 2f);
                fov = 56f + widen;
                break;
            case 2: // behind the player, but using a damped heading
                target = ClampPitch(player - h * 12f + new Vector3(0f, 7.5f, 0f) + side * 2.2f, 14f, 20f);
                look = ClampPitch(player + h * 6f + new Vector3(0f, 1.2f, 0f), 2f, 2f);
                fov = 62f + widen * .5f;
                break;
            case 3: // low, wide sideline
                target = ClampPitch(new Vector3(focus.X - 2f, 13f, focus.Z + 24f), 12f, 18f);
                look = ClampPitch(new Vector3(focus.X, 1.1f, focus.Z), 2f, 2f);
                fov = 58f + widen;
                break;
            case 4: // straight-down tactical: -Z is the stable screen-up vector
                target = new Vector3(focus.X * .35f, 62f, focus.Z * .2f + .001f);
                look = new Vector3(focus.X * .35f, 0f, focus.Z * .2f);
                up = new Vector3(0f, 0f, -1f);
                fov = 58f;
                break;
            default: // high broadcast: fixed world orientation, never spins with facing
                target = ClampPitch(new Vector3(focus.X - 8f, 32f, focus.Z + 48f), 14f, 22f);
                look = ClampPitch(new Vector3(focus.X, 1.2f, focus.Z), 2f, 2f);
                fov = 48f + widen;
                break;
        }
        // Looking straight down its own up axis is degenerate; the tactical mode
        // uses -Z and every other mode keeps a large +Z offset from the look point.
        if (mode != 4 && MathF.Abs(target.Z - look.Z) < 8f)
        {
            float dz = target.Z - look.Z;
            target.Z += dz >= 0f ? 8f : -8f;
        }
        return new CameraPlan { Target = target, Look = look, Up = up, Fov = fov };
    }
}
