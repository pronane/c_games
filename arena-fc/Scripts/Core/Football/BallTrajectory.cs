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

    // Samples are integrated on demand: most callers read the first few tenths of a
    // second (At(0.35), the earliest intercept), so a 2.5 s prediction used to integrate
    // 150 steps to answer a question about the first 20.  Every sample is computed by the
    // same Step sequence, in order, so values are identical to integrating them all up front.
    private readonly List<BallSample> _samples = new();
    private int _steps;
    private Vector3 _p, _v, _s;
    private bool _raining;
    private float _windX, _windZ;

    /// <summary>All samples (forces the whole horizon to be integrated).</summary>
    public List<BallSample> Samples { get { Fill(_steps); return _samples; } }
    /// <summary>Number of samples over the horizon (start sample included).</summary>
    public int Count => _steps + 1;
    /// <summary>Sample i (0 = start, i * Dt seconds ahead), integrated if not yet.</summary>
    public BallSample this[int i] { get { Fill(i); return _samples[i]; } }

    private void Fill(int index)
    {
        if (index > _steps) index = _steps;
        while (_samples.Count <= index)
        {
            Step(ref _p, ref _v, ref _s, Dt, _raining, _windX, _windZ);
            _samples.Add(new BallSample(_samples.Count * Dt, _p, _v));
        }
    }

    /// <summary>
    /// Base-flight prediction using Step() physics only. Excludes post-Step match events:
    /// post/crossbar/keeper/boundary/goal collisions and knuckleball RNG wobble.
    /// Use for short-horizon AI/animation decisions; never authoritative.
    /// </summary>
    public static BallTrajectory Predict(Vector3 pos, Vector3 vel, Vector3 spin,
        float horizonSeconds, bool raining = false, float windX = 0f, float windZ = 0f)
    {
        var t = new BallTrajectory();
        float h = Math.Clamp(horizonSeconds, 0f, 5f);
        t._steps = Math.Max(1, (int)MathF.Ceiling(h / Dt));
        t._p = pos; t._v = vel; t._s = spin;
        t._raining = raining; t._windX = windX; t._windZ = windZ;
        t._samples.Add(new BallSample(0f, pos, vel));
        return t;
    }

    public BallSample At(float seconds)
    {
        var first = this[0];
        if (seconds <= first.Time) return first;
        for (int i = 1; i <= _steps; i++)
        {
            var b = this[i];
            if (b.Time < seconds) continue;
            var a = _samples[i - 1];
            float span = MathF.Max(0.0001f, b.Time - a.Time);
            float u = Math.Clamp((seconds - a.Time) / span, 0f, 1f);
            return new BallSample(seconds, Vector3.Lerp(a.Position, b.Position, u), Vector3.Lerp(a.Velocity, b.Velocity, u));
        }
        return this[_steps];
    }

    public bool TryFirstGroundedBelow(float maxHeight, out BallSample sample)
    {
        for (int i = 0; i <= _steps; i++)
        {
            var s = this[i];
            if (s.Position.Y <= maxHeight)
            {
                sample = s;
                return true;
            }
        }
        sample = default;
        return false;
    }

    public bool TryInterceptXZ(Vector3 origin, float maxSpeed, float acceleration, out BallSample sample, float minT = 0f, Vector3 currentVelocity = default)
    {
        sample = default;
        bool found = false;
        float bestT = float.MaxValue;
        for (int i = 0; i <= _steps; i++)
        {
            var s = this[i];
            if (s.Time < minT) continue;
            float tReach = PlayerPerception.TimeToReach(origin, currentVelocity, s.Position, maxSpeed, acceleration);
            if (tReach <= s.Time + 0.03f && s.Time < bestT)
            {
                bestT = s.Time;
                sample = s;
                found = true;
                // Samples are in time order, so the first reachable one is the earliest:
                // nothing later can beat it (this loop used to scan the whole horizon).
                break;
            }
        }
        return found;
    }

    /// <summary>
    /// Authoritative core ball integration: gravity, Magnus, optional knuckleball
    /// wobble, drag, wind, air/ground friction and bounce. Does not apply
    /// collisions, goals, saves or out-of-bounds — those are sim-only.
    /// </summary>
    public static void Step(ref Vector3 pos, ref Vector3 vel, ref Vector3 spin, float dt,
        bool raining, float windX, float windZ, Func<float>? randomSigned = null)
    {
        Vector3 v = vel;
        v.Y += Mx.Gravity * dt;
        // Magnus effect from spin (side curve + dip).
        v += Vector3.Cross(spin, v) * (.055f * dt);
        // Knuckleball wobble for power shots (sim-only; predictor omits RNG).
        if (randomSigned != null && spin.LengthSquared() < 0.1f && v.Length() > 20f)
        {
            v.X += randomSigned() * 0.5f * dt;
            v.Z += randomSigned() * 0.5f * dt;
        }
        // Ball drag: air resistance proportional to velocity squared.
        float speed = v.Length();
        float dragCoeff = 0.0035f;
        if (raining) dragCoeff *= 1.5f;
        v -= v * (dragCoeff * speed * dt);
        // Wind: lateral force on airborne ball (matches MatchEngine.BallPhysics).
        if (pos.Y > Mx.BallRadius + 0.5f)
        {
            v.X += windX * dt * 0.5f;
            v.Z += windZ * dt * 0.5f;
        }
        // Air drag when airborne; rolling friction when on ground.
        bool airborne = v.Y > 0f || pos.Y > Mx.BallRadius + .05f;
        if (airborne) v *= 1f - .045f * dt;
        pos += v * dt;

        if (pos.Y < Mx.BallRadius)
        {
            pos.Y = Mx.BallRadius;
            if (v.Y < 0f) v.Y = -v.Y * .48f;
            if (MathF.Abs(v.Y) < .45f) v.Y = 0f;
            if (v.Y == 0f)
            {
                float flat = MathF.Sqrt(v.X * v.X + v.Z * v.Z);
                float next = MathF.Max(0f, flat * (1f - MatchEngine.RollDrag * dt) - MatchEngine.RollResistance * dt);
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
