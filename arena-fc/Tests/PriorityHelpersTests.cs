// Deterministic unit checks for priority 2/3 pure helpers.
// Invoked from MatchCoreTests host if registered; safe to compile standalone.
using System;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Tests;

public static class PriorityHelpersTests
{
    public static int Run()
    {
        int fails = 0;
        fails += Check("FirstTouch.ClearUnderPressure", () =>
        {
            var k = FirstTouch.Select(approachSpeed: 12f, ballHeight: 0.3f, pressureDistance: 1.5f, controlAttr: 0.7f);
            if (k != FirstTouchKind.Clear) throw new Exception("expected Clear, got " + k);
        });
        fails += Check("FirstTouch.CushionAerial", () =>
        {
            var k = FirstTouch.Select(6f, 1.4f, 8f, 0.7f);
            if (k != FirstTouchKind.Cushion) throw new Exception("expected Cushion, got " + k);
        });
        fails += Check("FirstTouch.TrapDefault", () =>
        {
            var k = FirstTouch.Select(10f, 0.2f, 3f, 0.3f);
            if (k != FirstTouchKind.Trap) throw new Exception("expected Trap, got " + k);
        });
        fails += Check("MomentumLimits.TurnSlowsWithSpeed", () =>
        {
            float slow = MomentumLimits.MaxTurnRate(1f, 0.5f);
            float fast = MomentumLimits.MaxTurnRate(9f, 0.5f);
            if (!(fast < slow)) throw new Exception($"fast {fast} should be < slow {slow}");
        });
        fails += Check("MomentumLimits.ClampYaw", () =>
        {
            float d = MomentumLimits.ClampYawDelta(2f, 8f, 1f / 60f, 0.5f);
            if (MathF.Abs(d) > 0.2f) throw new Exception("yaw delta too large at speed: " + d);
        });
        fails += Check("GkHeuristics.DesiredPositionClamped", () =>
        {
            var goal = new Vector3(-52.5f, 0, 0);
            var pos = GkHeuristics.DesiredPosition(goal, 3.66f, new Vector3(0, 0, 20f));
            if (MathF.Abs(pos.Z) > 3.66f) throw new Exception("lateral not clamped: " + pos.Z);
        });
        fails += Check("GkHeuristics.NoDiveWhenFar", () =>
        {
            if (GkHeuristics.ShouldDive(Vector3.Zero, new Vector3(30, 0, 0), new Vector3(-5, 0, 0)))
                throw new Exception("should not dive from 30m");
        });
        fails += Check("Shielding.InactiveWhenFar", () =>
        {
            var (lx, lz, r) = Shielding.GetPose(1f, 0f, 5f, 70);
            if (lx != 0f || lz != 0f || r != 0f) throw new Exception("expected zero pose when far");
        });
        return fails;
    }

    private static int Check(string name, Action body)
    {
        try { body(); Console.WriteLine("  ok  " + name); return 0; }
        catch (Exception ex) { Console.WriteLine("  FAIL " + name + ": " + ex.Message); return 1; }
    }
}
