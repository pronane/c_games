// Arena FC - pure-C# broadcast camera plan.
//
// The 06.11.2026 recording showed the old camera whipping around the pitch: the
// player/shoulder modes were built from the player's INSTANT facing, so every
// stick direction change spun the camera, and near a corner it ended up outside
// the pitch looking at the stands.  This plan keeps a fixed sideline orientation
// for the ball-following modes, smooths the one behind-the-player mode in
// World3D.cs, and clamps the camera to the stadium bowl.  It is Godot-free so
// the headless core suite can assert the framing never degenerates.
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

    /// <summary>Stable camera framing for one render frame.  `heading` is the
    /// SMOOTHED player direction supplied by BroadcastCamera, never the raw
    /// per-tick facing.  Ball and controlled player are both kept in view.</summary>
    public static CameraPlan Compute(int mode, Vector3 ball, Vector3 player, Vector3 heading)
    {
        Vector3 focus = Vector3.Lerp(new Vector3(ball.X, 0f, ball.Z),
                                     new Vector3(player.X, 0f, player.Z), .35f);
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
                target = ClampPitch(new Vector3(focus.X - 4f, 19f + separation * .10f, focus.Z + 28f), 12f, 20f);
                look = ClampPitch(new Vector3(focus.X, 1.1f, focus.Z), 2f, 2f);
                fov = 58f + widen;
                break;
            case 2: // behind the player, but using a damped heading
                target = ClampPitch(player - h * 12f + new Vector3(0f, 7.5f, 0f) + side * 2.2f, 14f, 20f);
                look = ClampPitch(player + h * 6f + new Vector3(0f, 1.2f, 0f), 2f, 2f);
                fov = 62f + widen * .5f;
                break;
            case 3: // low, wide sideline
                target = ClampPitch(new Vector3(focus.X - 2f, 12f, focus.Z + 22f), 12f, 18f);
                look = ClampPitch(new Vector3(focus.X, 1.1f, focus.Z), 2f, 2f);
                fov = 60f + widen;
                break;
            case 4: // straight-down tactical: -Z is the stable screen-up vector
                target = new Vector3(focus.X * .35f, 62f, focus.Z * .2f + .001f);
                look = new Vector3(focus.X * .35f, 0f, focus.Z * .2f);
                up = new Vector3(0f, 0f, -1f);
                fov = 58f;
                break;
            default: // high broadcast: fixed world orientation, never spins with facing
                target = ClampPitch(new Vector3(focus.X - 8f, 30f + separation * .08f, focus.Z + 46f), 14f, 22f);
                look = ClampPitch(new Vector3(focus.X, 1.2f, focus.Z), 2f, 2f);
                fov = 50f + widen;
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
