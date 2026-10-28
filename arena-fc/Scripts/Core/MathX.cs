// Arena FC - pure C# math/random helpers (no Godot dependency).
using System;
using System.Numerics;

namespace ArenaFC.Core;

public static class Mx
{
    public const float PitchLength = 105f;
    public const float PitchWidth = 68f;
    public const float HalfLength = PitchLength * 0.5f;
    public const float HalfWidth = PitchWidth * 0.5f;
    public const float GoalHalfWidth = 3.66f;
    public const float GoalHeight = 2.44f;
    public const float BallRadius = 0.11f;
    public const float Gravity = -9.81f;

    public static float Clamp(float v, float a, float b) => v < a ? a : (v > b ? b : v);
    public static float Lerp(float a, float b, float t) => a + (b - a) * t;
    public static Vector3 Lerp(Vector3 a, Vector3 b, float t) => a + (b - a) * t;
    public static float Smooth(float t) => t * t * (3f - 2f * t);
    public static float Sign(float v) => v < 0 ? -1f : 1f;
    public static Vector3 Flat(Vector3 v) => new(v.X, 0f, v.Z);
    public static float FlatDist(Vector3 a, Vector3 b) => (Flat(a) - Flat(b)).Length();
    public static float FlatDist2(Vector3 a, Vector3 b) => (Flat(a) - Flat(b)).LengthSquared();
    public static Vector3 FlatDir(Vector3 from, Vector3 to)
    {
        Vector3 d = Flat(to - from);
        return d.LengthSquared() < 1e-6f ? Vector3.UnitX : Vector3.Normalize(d);
    }
    public static Vector3 Norm(Vector3 v) => v.LengthSquared() < 1e-8f ? Vector3.Zero : Vector3.Normalize(v);
    public static Vector3 MoveTowards(Vector3 from, Vector3 to, float maxDelta)
    {
        Vector3 d = to - from;
        float l = d.Length();
        return l <= maxDelta || l < 1e-6f ? to : from + d * (maxDelta / l);
    }
    public static float MoveTowards(float from, float to, float maxDelta) =>
        MathF.Abs(to - from) <= maxDelta ? to : from + MathF.Sign(to - from) * maxDelta;
    public static float Angle(Vector3 v) => MathF.Atan2(v.Z, v.X);
    public static Vector3 FromAngle(float a, float length = 1f) => new(MathF.Cos(a) * length, 0f, MathF.Sin(a) * length);
    public static float AngleDiff(float a, float b)
    {
        float d = (a - b) % (MathF.PI * 2f);
        if (d > MathF.PI) d -= MathF.PI * 2f;
        if (d < -MathF.PI) d += MathF.PI * 2f;
        return d;
    }
    public static Vector3 RotateY(Vector3 v, float angle)
    {
        float c = MathF.Cos(angle), s = MathF.Sin(angle);
        return new Vector3(v.X * c - v.Z * s, v.Y, v.X * s + v.Z * c);
    }
    public static bool IsFinite(Vector3 v) => float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z);
    public static string HexToRgb(string hex, out float r, out float g, out float b)
    {
        r = g = b = 1f;
        if (string.IsNullOrEmpty(hex)) return "#ffffff";
        string s = hex.TrimStart('#');
        if (s.Length == 3) s = string.Concat(s[0], s[0], s[1], s[1], s[2], s[2]);
        if (s.Length != 6) return "#ffffff";
        try
        {
            r = Convert.ToInt32(s[..2], 16) / 255f;
            g = Convert.ToInt32(s[2..4], 16) / 255f;
            b = Convert.ToInt32(s[4..6], 16) / 255f;
        }
        catch { r = g = b = 1f; }
        return "#" + s;
    }
}

/// <summary>Deterministic xorshift RNG: same seed => same match. Testable and replay friendly.</summary>
public sealed class Rng
{
    private uint _s;
    public Rng(int seed) { _s = seed == 0 ? 0x9E3779B9u : (uint)seed; }
    public uint NextUInt() { uint x = _s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; _s = x; return x; }
    public float Next() => (NextUInt() & 0xFFFFFF) / (float)0x1000000;
    public float Range(float a, float b) => a + (b - a) * Next();
    public int RangeInt(int a, int b) => a + (int)(Next() * (b - a + 1));
    public float Signed() => Next() * 2f - 1f;
    public Vector3 Cone(float spread) => new(Signed() * spread, 0f, Signed() * spread);
}
