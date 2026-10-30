using System;

namespace MarioKart64.Core
{
    public struct Vec2
    {
        public float X;
        public float Y;

        public Vec2(float x, float y)
        {
            X = x;
            Y = y;
        }

        public float Length
        {
            get { return (float)Math.Sqrt(X * X + Y * Y); }
        }

        public Vec2 Normalized()
        {
            float len = Length;
            if (len < 1e-6f) return new Vec2(0f, 0f);
            return new Vec2(X / len, Y / len);
        }

        public static Vec2 operator +(Vec2 a, Vec2 b) { return new Vec2(a.X + b.X, a.Y + b.Y); }
        public static Vec2 operator -(Vec2 a, Vec2 b) { return new Vec2(a.X - b.X, a.Y - b.Y); }
        public static Vec2 operator *(Vec2 a, float s) { return new Vec2(a.X * s, a.Y * s); }
    }

    public struct Vec3
    {
        public float X;
        public float Y;
        public float Z;

        public Vec3(float x, float y, float z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        public static readonly Vec3 Zero = new Vec3(0f, 0f, 0f);
        public static readonly Vec3 Up = new Vec3(0f, 1f, 0f);
        public static readonly Vec3 Forward = new Vec3(0f, 0f, 1f);
        public static readonly Vec3 Right = new Vec3(1f, 0f, 0f);

        public float Length
        {
            get { return (float)Math.Sqrt(X * X + Y * Y + Z * Z); }
        }

        public float LengthSq
        {
            get { return X * X + Y * Y + Z * Z; }
        }

        public float LengthXZ
        {
            get { return (float)Math.Sqrt(X * X + Z * Z); }
        }

        public Vec3 Normalized()
        {
            float len = Length;
            if (len < 1e-6f) return new Vec3(0f, 0f, 0f);
            float inv = 1.0f / len;
            return new Vec3(X * inv, Y * inv, Z * inv);
        }

        public Vec3 NormalizedXZ()
        {
            float len = LengthXZ;
            if (len < 1e-6f) return new Vec3(0f, 0f, 1f);
            float inv = 1.0f / len;
            return new Vec3(X * inv, 0f, Z * inv);
        }

        public static float Dot(Vec3 a, Vec3 b)
        {
            return a.X * b.X + a.Y * b.Y + a.Z * b.Z;
        }

        public static Vec3 Cross(Vec3 a, Vec3 b)
        {
            return new Vec3(
                a.Y * b.Z - a.Z * b.Y,
                a.Z * b.X - a.X * b.Z,
                a.X * b.Y - a.Y * b.X);
        }

        public static float Distance(Vec3 a, Vec3 b)
        {
            return (a - b).Length;
        }

        public static float DistanceXZ(Vec3 a, Vec3 b)
        {
            float dx = a.X - b.X;
            float dz = a.Z - b.Z;
            return (float)Math.Sqrt(dx * dx + dz * dz);
        }

        public static float DistanceXZSq(Vec3 a, Vec3 b)
        {
            float dx = a.X - b.X;
            float dz = a.Z - b.Z;
            return dx * dx + dz * dz;
        }

        public static Vec3 Lerp(Vec3 a, Vec3 b, float t)
        {
            return new Vec3(
                a.X + (b.X - a.X) * t,
                a.Y + (b.Y - a.Y) * t,
                a.Z + (b.Z - a.Z) * t);
        }

        public static Vec3 CatmullRom(Vec3 p0, Vec3 p1, Vec3 p2, Vec3 p3, float t)
        {
            float t2 = t * t;
            float t3 = t2 * t;
            return new Vec3(
                0.5f * ((2f * p1.X) + (-p0.X + p2.X) * t + (2f * p0.X - 5f * p1.X + 4f * p2.X - p3.X) * t2 + (-p0.X + 3f * p1.X - 3f * p2.X + p3.X) * t3),
                0.5f * ((2f * p1.Y) + (-p0.Y + p2.Y) * t + (2f * p0.Y - 5f * p1.Y + 4f * p2.Y - p3.Y) * t2 + (-p0.Y + 3f * p1.Y - 3f * p2.Y + p3.Y) * t3),
                0.5f * ((2f * p1.Z) + (-p0.Z + p2.Z) * t + (2f * p0.Z - 5f * p1.Z + 4f * p2.Z - p3.Z) * t2 + (-p0.Z + 3f * p1.Z - 3f * p2.Z + p3.Z) * t3)
            );
        }

        public static Vec3 operator +(Vec3 a, Vec3 b) { return new Vec3(a.X + b.X, a.Y + b.Y, a.Z + b.Z); }
        public static Vec3 operator -(Vec3 a, Vec3 b) { return new Vec3(a.X - b.X, a.Y - b.Y, a.Z - b.Z); }
        public static Vec3 operator -(Vec3 a) { return new Vec3(-a.X, -a.Y, -a.Z); }
        public static Vec3 operator *(Vec3 a, float s) { return new Vec3(a.X * s, a.Y * s, a.Z * s); }
        public static Vec3 operator *(float s, Vec3 a) { return new Vec3(a.X * s, a.Y * s, a.Z * s); }
    }

    public struct Color4
    {
        public float R;
        public float G;
        public float B;
        public float A;

        public Color4(float r, float g, float b, float a)
        {
            R = r;
            G = g;
            B = b;
            A = a;
        }

        public Color4(float r, float g, float b)
        {
            R = r;
            G = g;
            B = b;
            A = 1.0f;
        }

        public static Color4 FromBytes(int r, int g, int b, int a)
        {
            return new Color4(r / 255f, g / 255f, b / 255f, a / 255f);
        }

        public static Color4 FromBytes(int r, int g, int b)
        {
            return new Color4(r / 255f, g / 255f, b / 255f, 1.0f);
        }

        public static Color4 Lerp(Color4 a, Color4 b, float t)
        {
            return new Color4(
                a.R + (b.R - a.R) * t,
                a.G + (b.G - a.G) * t,
                a.B + (b.B - a.B) * t,
                a.A + (b.A - a.A) * t);
        }

        public Color4 WithAlpha(float a)
        {
            return new Color4(R, G, B, a);
        }

        public Color4 ScaleRGB(float factor)
        {
            return new Color4(
                MathUtil.Clamp(R * factor, 0f, 1f),
                MathUtil.Clamp(G * factor, 0f, 1f),
                MathUtil.Clamp(B * factor, 0f, 1f),
                A);
        }

        public static Color4 Rainbow(float phase)
        {
            float r = 0.5f + 0.5f * (float)Math.Sin(phase);
            float g = 0.5f + 0.5f * (float)Math.Sin(phase + 2.094395f);
            float b = 0.5f + 0.5f * (float)Math.Sin(phase + 4.188790f);
            return new Color4(r, g, b, 1.0f);
        }
    }

    public static class MathUtil
    {
        public const float PI = 3.14159265358979323846f;
        public const float TWO_PI = 6.28318530717958647692f;
        public const float DEG2RAD = 0.017453292519943295f;
        public const float RAD2DEG = 57.29577951308232f;

        public static float Clamp(float v, float min, float max)
        {
            if (v < min) return min;
            if (v > max) return max;
            return v;
        }

        public static int ClampInt(int v, int min, int max)
        {
            if (v < min) return min;
            if (v > max) return max;
            return v;
        }

        public static float Lerp(float a, float b, float t)
        {
            return a + (b - a) * t;
        }

        public static float WrapAngle(float rad)
        {
            while (rad > PI) rad -= TWO_PI;
            while (rad < -PI) rad += TWO_PI;
            return rad;
        }

        public static float LerpAngle(float a, float b, float t)
        {
            float diff = WrapAngle(b - a);
            return WrapAngle(a + diff * t);
        }

        public static float MoveTowards(float current, float target, float maxDelta)
        {
            if (Math.Abs(target - current) <= maxDelta) return target;
            return current + Math.Sign(target - current) * maxDelta;
        }

        public static float CatmullRomScalar(float v0, float v1, float v2, float v3, float t)
        {
            float t2 = t * t;
            float t3 = t2 * t;
            return 0.5f * ((2f * v1) + (-v0 + v2) * t + (2f * v0 - 5f * v1 + 4f * v2 - v3) * t2 + (-v0 + 3f * v1 - 3f * v2 + v3) * t3);
        }

        public static float[] BuildLookAtMatrix(Vec3 eye, Vec3 center, Vec3 up)
        {
            Vec3 f = (center - eye).Normalized();
            if (f.LengthSq < 1e-6f) f = new Vec3(0f, 0f, -1f);
            Vec3 s = Vec3.Cross(f, up).Normalized();
            if (s.LengthSq < 1e-6f) s = new Vec3(1f, 0f, 0f);
            Vec3 u = Vec3.Cross(s, f);

            float[] m = new float[16];
            m[0] = s.X;  m[4] = s.Y;  m[8]  = s.Z;  m[12] = -Vec3.Dot(s, eye);
            m[1] = u.X;  m[5] = u.Y;  m[9]  = u.Z;  m[13] = -Vec3.Dot(u, eye);
            m[2] = -f.X; m[6] = -f.Y; m[10] = -f.Z; m[14] = Vec3.Dot(f, eye);
            m[3] = 0f;   m[7] = 0f;   m[11] = 0f;   m[15] = 1f;
            return m;
        }
    }
}
