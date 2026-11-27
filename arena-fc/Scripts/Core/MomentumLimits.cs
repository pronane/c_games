// Arena FC — momentum and turn-rate limits (priority 2 ball/contact fidelity).
// Pure C#, deterministic. Caps turn-in and speed change so sprints cannot
// snap 180° in a frame (FC-style weight).
using System;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>
/// Velocity-aware turn and acceleration clamps. Higher speed → lower max yaw rate
/// and slower lateral cut-in. Keeps presentation and sim feeling heavy at pace.
/// </summary>
public static class MomentumLimits
{
    /// <summary>Max yaw rate (rad/s) at the given planar speed.</summary>
    public static float MaxTurnRate(float planarSpeed, float agilityAttr = 0.5f)
    {
        planarSpeed = Math.Max(0f, planarSpeed);
        agilityAttr = Math.Clamp(agilityAttr, 0f, 1f);
        // ~4.2 rad/s standing, falls toward ~1.1 rad/s at full sprint.
        float baseRate = 4.2f - Math.Clamp(planarSpeed / 9f, 0f, 1f) * 3.1f;
        return baseRate * (0.85f + 0.3f * agilityAttr);
    }

    /// <summary>Clamp a desired facing delta to the speed-limited turn budget for dt.</summary>
    public static float ClampYawDelta(float desiredDeltaRad, float planarSpeed, float dt, float agilityAttr = 0.5f)
    {
        float max = MaxTurnRate(planarSpeed, agilityAttr) * Math.Max(0f, dt);
        return Math.Clamp(desiredDeltaRad, -max, max);
    }

    /// <summary>Scale max speed when turning hard (cut penalty).</summary>
    public static float SpeedScaleForTurn(float turnRateAbs, float planarSpeed)
    {
        turnRateAbs = Math.Max(0f, turnRateAbs);
        planarSpeed = Math.Max(0f, planarSpeed);
        // Sharp turns at speed bleed pace.
        float sharpness = Math.Clamp(turnRateAbs / 3.5f, 0f, 1f);
        float speedFactor = Math.Clamp(planarSpeed / 8f, 0f, 1f);
        return Math.Clamp(1f - sharpness * speedFactor * 0.35f, 0.55f, 1f);
    }

    /// <summary>Clamp planar velocity toward a desired velocity with accel limits.</summary>
    public static Vector3 IntegrateVelocity(Vector3 current, Vector3 desired, float maxAccel, float dt)
    {
        Vector3 delta = desired - current;
        float maxDelta = Math.Max(0f, maxAccel) * Math.Max(0f, dt);
        float len = delta.Length();
        if (len <= maxDelta || len < 1e-6f) return desired;
        return current + delta * (maxDelta / len);
    }
}
