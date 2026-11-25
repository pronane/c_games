using System;
using System.Numerics;

namespace ArenaFC.Core.Football;

/// <summary>
/// Deterministic, football-specific perception measurements shared by AI,
/// ball prediction and animation contracts. Pure C# - no Godot dependency.
/// </summary>
public static class PlayerPerception
{
    public static float TimeToReach(Vector3 position, Vector3 velocity, Vector3 target,
        float maxSpeed, float acceleration)
    {
        Vector3 delta = target - position;
        delta.Y = 0f;
        float distance = delta.Length();
        if (distance < 0.05f) return 0f;
        Vector3 dir = delta / distance;
        float speed = Math.Clamp(Vector3.Dot(velocity, dir), 0f, maxSpeed);
        float accel = MathF.Max(0.1f, acceleration);
        maxSpeed = MathF.Max(0.5f, maxSpeed);
        float accelTime = MathF.Max(0f, (maxSpeed - speed) / accel);
        float accelDistance = speed * accelTime + 0.5f * accel * accelTime * accelTime;
        if (distance <= accelDistance)
        {
            float disc = speed * speed + 2f * accel * distance;
            return (-speed + MathF.Sqrt(MathF.Max(0f, disc))) / accel;
        }
        return accelTime + (distance - accelDistance) / maxSpeed;
    }

    public static float Pressure(Vector3 playerPos, Vector3 playerVel, Vector3[] oppPos, Vector3[] oppVel,
        float oppMaxSpeed, float oppAccel)
    {
        float best = float.MaxValue;
        for (int i = 0; i < oppPos.Length; i++)
        {
            float t = TimeToReach(oppPos[i], oppVel[i], playerPos, oppMaxSpeed, oppAccel);
            if (t < best) best = t;
        }
        if (best == float.MaxValue) return 0f;
        // 0..1, higher means more pressure (opponent can engage sooner)
        return Math.Clamp(1f - best / 2.5f, 0f, 1f);
    }

    public static float SpaceScore(Vector3 pos, Vector3[] oppPos, float radius = 8f)
    {
        if (oppPos.Length == 0) return 1f;
        float total = 0f;
        for (int i = 0; i < oppPos.Length; i++)
        {
            Vector3 d = pos - oppPos[i]; d.Y = 0f;
            float dist = d.Length();
            float w = Math.Clamp(1f - dist / radius, 0f, 1f);
            total += w * w;
        }
        return Math.Clamp(1f - total / 3f, 0f, 1f);
    }

    public static float LaneSafety(Vector3 from, Vector3 to, Vector3[] oppPos, Vector3[] oppVel,
        float ballSpeed, float oppMaxSpeed, float oppAccel)
    {
        Vector3 dir = to - from; dir.Y = 0f;
        float dist = dir.Length();
        if (dist < 1e-4f) return 0f;
        dir /= dist;
        float ballT = dist / MathF.Max(1f, ballSpeed);
        float safety = 1f;
        for (int i = 0; i < oppPos.Length; i++)
        {
            Vector3 rel = oppPos[i] - from; rel.Y = 0f;
            float along = Vector3.Dot(rel, dir);
            if (along < 0.5f || along > dist - 0.5f) continue;
            Vector3 closest = from + dir * along;
            Vector3 lateral = oppPos[i] - closest; lateral.Y = 0f;
            float latDist = lateral.Length();
            float tBallAt = along / MathF.Max(1f, ballSpeed);
            float tOpp = TimeToReach(oppPos[i], oppVel[i], closest, oppMaxSpeed, oppAccel);
            if (tOpp <= tBallAt + 0.05f)
            {
                float sev = Math.Clamp(1f - latDist / 2.0f, 0f, 1f);
                safety *= 1f - sev * 0.9f;
            }
            else if (latDist < 1.5f)
            {
                safety *= 0.85f;
            }
        }
        return Math.Clamp(safety, 0f, 1f);
    }

    public static float PassScore(float laneSafety, float forwardProgress01, float receiverSpace01,
        float distanceM, bool through, bool aimAligned)
    {
        float score = laneSafety * 5.0f + forwardProgress01 * 2.2f + receiverSpace01 * 1.5f;
        score -= MathF.Abs(distanceM - (through ? 22f : 12f)) * 0.03f;
        if (aimAligned) score += 0.8f;
        if (laneSafety < 0.25f) score -= 6f;
        return score;
    }
}
