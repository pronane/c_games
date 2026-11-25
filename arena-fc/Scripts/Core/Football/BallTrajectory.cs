using System;
using System.Collections.Generic;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Core.Football;

public readonly struct BallSample
{
    public readonly float Time;
    public readonly Vector3 Position;
    public readonly Vector3 Velocity;
    public BallSample(float time, Vector3 position, Vector3 velocity)
    {
        Time = time;
        Position = position;
        Velocity = velocity;
    }
}

/// <summary>
/// Deterministic short-horizon ball predictor. Mirrors the authoritative
/// MatchEngine ball integration closely enough for AI/animation decisions, but
/// is never authoritative.
/// </summary>
public sealed class BallTrajectory
{
    public const float Dt = 1f / 60f;
    public readonly List<BallSample> Samples = new();

    public static BallTrajectory Predict(Vector3 pos, Vector3 vel, Vector3 spin,
        float horizonSeconds, bool raining = false, float windX = 0f, float windZ = 0f)
    {
        var t = new BallTrajectory();
        float h = Math.Clamp(horizonSeconds, 0f, 5f);
        int steps = Math.Max(1, (int)MathF.Ceiling(h / Dt));
        Vector3 p = pos;
        Vector3 v = vel;
        Vector3 s = spin;
        t.Samples.Add(new BallSample(0f, p, v));
        for (int i = 1; i <= steps; i++)
        {
            Step(ref p, ref v, ref s, Dt, raining, windX, windZ);
            t.Samples.Add(new BallSample(i * Dt, p, v));
        }
        return t;
    }

    public BallSample At(float seconds)
    {
        if (Samples.Count == 0) return default;
        if (seconds <= Samples[0].Time) return Samples[0];
        for (int i = 1; i < Samples.Count; i++)
        {
            if (Samples[i].Time < seconds) continue;
            var a = Samples[i - 1];
            var b = Samples[i];
            float span = MathF.Max(0.0001f, b.Time - a.Time);
            float u = Math.Clamp((seconds - a.Time) / span, 0f, 1f);
            return new BallSample(seconds, Vector3.Lerp(a.Position, b.Position, u), Vector3.Lerp(a.Velocity, b.Velocity, u));
        }
        return Samples[^1];
    }

    public bool TryFirstGroundedBelow(float maxHeight, out BallSample sample)
    {
        for (int i = 0; i < Samples.Count; i++)
        {
            if (Samples[i].Position.Y <= maxHeight)
            {
                sample = Samples[i];
                return true;
            }
        }
        sample = default;
        return false;
    }

    public bool TryInterceptXZ(Vector3 origin, float maxSpeed, float acceleration, out BallSample sample, float minT = 0f)
    {
        sample = default;
        bool found = false;
        float bestT = float.MaxValue;
        for (int i = 0; i < Samples.Count; i++)
        {
            var s = Samples[i];
            if (s.Time < minT) continue;
            float tReach = PlayerPerception.TimeToReach(origin, Vector3.Zero, s.Position, maxSpeed, acceleration);
            if (tReach <= s.Time + 0.03f && s.Time < bestT)
            {
                bestT = s.Time;
                sample = s;
                found = true;
            }
        }
        return found;
    }

    private static void Step(ref Vector3 pos, ref Vector3 vel, ref Vector3 spin, float dt,
        bool raining, float windX, float windZ)
    {
        Vector3 v = vel;
        v.Y += Mx.Gravity * dt;
        v += Vector3.Cross(spin, v) * (.055f * dt);
        float speed = v.Length();
        float dragCoeff = 0.0035f;
        if (raining) dragCoeff *= 1.5f;
        v -= v * (dragCoeff * speed * dt);
        bool airborne = v.Y > 0f || pos.Y > Mx.BallRadius + .05f;
        if (airborne)
        {
            v.X += windX * dt * 0.5f;
            v.Z += windZ * dt * 0.5f;
            v *= 1f - .045f * dt;
        }
        pos += v * dt;

        if (pos.Y < Mx.BallRadius)
        {
            pos.Y = Mx.BallRadius;
            if (v.Y < 0f) v.Y = -v.Y * .48f;
            if (MathF.Abs(v.Y) < .45f) v.Y = 0f;
            if (v.Y == 0f)
            {
                float flat = MathF.Sqrt(v.X * v.X + v.Z * v.Z);
                float next = MathF.Max(0f, flat * (1f - 0.30f * dt) - 1.0f * dt);
                float k = flat > 1e-4f ? next / flat : 0f;
                v.X *= k; v.Z *= k;
            }
            else
            {
                v.X *= MathF.Max(0f, 1f - .55f * dt);
                v.Z *= MathF.Max(0f, 1f - .55f * dt);
            }
            spin *= MathF.Max(0f, 1f - 2f * dt);
        }
        vel = v;
    }
}
