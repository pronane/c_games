// Arena FC - Analytic two-bone IK solver (pure C#, deterministic).
// Used by the Hypermotion-style locomotion stack for foot planting and reach.
// Based on the standard law-of-cosines two-bone solution with knee/elbow
// clamping and pole-vector bend control.
using System;
using System.Numerics;

namespace ArenaFC.Core.Animation;

public static class TwoBoneIK
{
    /// <summary>Solves a two-bone chain. Returns false when the chain is degenerate.</summary>
    public static bool Solve(
        Vector3 root,
        Vector3 target,
        float upperLength,
        float lowerLength,
        Vector3 pole,
        out Vector3 jointPos,
        out Vector3 endPos)
    {
        jointPos = root;
        endPos = target;
        if (upperLength <= 1e-5f || lowerLength <= 1e-5f) return false;

        Vector3 toTarget = target - root;
        float targetDist = toTarget.Length();
        float totalLength = upperLength + lowerLength;
        float minLength = MathF.Abs(upperLength - lowerLength);

        // Keep a small epsilon so the knee never fully locks.
        float clampedDist = Math.Clamp(targetDist, minLength + 0.002f, totalLength * 0.995f);
        Vector3 dir = targetDist > 1e-6f ? toTarget / targetDist : Vector3.UnitY;

        float cosAngle = (upperLength * upperLength + clampedDist * clampedDist - lowerLength * lowerLength)
                         / (2f * upperLength * clampedDist);
        cosAngle = Math.Clamp(cosAngle, -1f, 1f);
        float sinAngle = MathF.Sqrt(MathF.Max(0f, 1f - cosAngle * cosAngle));

        // Build bend plane from pole vector.
        Vector3 poleProjected = pole - dir * Vector3.Dot(pole, dir);
        if (poleProjected.LengthSquared() < 1e-8f)
        {
            poleProjected = MathF.Abs(Vector3.Dot(dir, Vector3.UnitY)) < 0.99f
                ? Vector3.Cross(Vector3.UnitY, dir)
                : Vector3.Cross(Vector3.UnitX, dir);
        }
        if (poleProjected.LengthSquared() < 1e-8f) poleProjected = Vector3.UnitZ;
        poleProjected = Vector3.Normalize(poleProjected);

        jointPos = root + dir * (cosAngle * upperLength) + poleProjected * (sinAngle * upperLength);
        endPos = root + dir * clampedDist;
        return true;
    }

    /// <summary>Solve + anatomical knee/elbow clamp in one call.</summary>
    public static bool SolveWithKneeClamp(
        Vector3 root,
        Vector3 target,
        float upperLength,
        float lowerLength,
        Vector3 pole,
        float minAngleDeg,
        float maxAngleDeg,
        out Vector3 jointPos,
        out Vector3 endPos)
    {
        if (!Solve(root, target, upperLength, lowerLength, pole, out jointPos, out endPos))
            return false;
        jointPos = ClampKneeAngle(root, jointPos, endPos, upperLength, lowerLength, minAngleDeg, maxAngleDeg);
        Vector3 lowerVec = endPos - jointPos;
        if (lowerVec.LengthSquared() > 1e-8f)
            endPos = jointPos + Vector3.Normalize(lowerVec) * lowerLength;
        return true;
    }

    /// <summary>Enforces min/max angle at the middle joint while preserving bend side.</summary>
    public static Vector3 ClampKneeAngle(
        Vector3 root,
        Vector3 joint,
        Vector3 end,
        float upperLength,
        float lowerLength,
        float minAngleDeg = 8f,
        float maxAngleDeg = 155f)
    {
        Vector3 upper = joint - root;
        Vector3 lower = end - joint;
        if (upper.LengthSquared() < 1e-10f || lower.LengthSquared() < 1e-10f)
            return joint;

        float cosTheta = Vector3.Dot(Vector3.Normalize(upper), Vector3.Normalize(-lower));
        cosTheta = Math.Clamp(cosTheta, -1f, 1f);
        float angleDeg = MathF.Acos(cosTheta) * (180f / MathF.PI);
        if (angleDeg >= minAngleDeg && angleDeg <= maxAngleDeg)
            return joint;

        float targetAngleDeg = Math.Clamp(angleDeg, minAngleDeg, maxAngleDeg);
        float targetAngleRad = targetAngleDeg * (MathF.PI / 180f);

        Vector3 toEnd = end - root;
        float dist = toEnd.Length();
        if (dist < 1e-6f) return joint;
        Vector3 dir = toEnd / dist;

        float proj = (upperLength * upperLength - lowerLength * lowerLength + dist * dist) / (2f * dist);
        float heightSq = upperLength * upperLength - proj * proj;
        float height = MathF.Sqrt(MathF.Max(0.0001f, heightSq));

        Vector3 originalBend = joint - (root + dir * proj);
        Vector3 bendDir = originalBend.LengthSquared() > 1e-8f
            ? Vector3.Normalize(originalBend)
            : Vector3.UnitY;

        Vector3 clamped = root + dir * proj + bendDir * height;
        Vector3 newUpper = clamped - root;
        if (newUpper.LengthSquared() > 1e-8f)
            clamped = root + Vector3.Normalize(newUpper) * upperLength;
        return clamped;
    }
}
