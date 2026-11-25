// Arena FC - Simplified inertialization for Hypermotion-style transitions.
// Pure C#, deterministic, no Godot dependency. Stores per-bone pose offsets
// and decays them with a critically-damped exponential so transitions preserve
// momentum instead of popping/floaty linear blends.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core.Animation;

public sealed class InertializationBoneState
{
    public int BoneIndex;
    public Vector3 PositionOffset;
    public Quaternion RotationOffset = Quaternion.Identity;
    public Vector3 PositionVelocity;
    public Vector3 AngularVelocity; // axis * radians/sec
    public float HalfLife = 0.18f;
}

public sealed class InertializationBuffer
{
    public readonly List<InertializationBoneState> Bones = new();
    public bool Active;
    public float TimeSinceTransition;
    public float DefaultHalfLife = 0.18f;
    public float MaxPositionOffset = 0.12f;
    public float MaxAngularVelocity = 12f;

    public void Clear()
    {
        Bones.Clear();
        Active = false;
        TimeSinceTransition = 0f;
    }

    /// <summary>Capture transition offsets from old/new bone poses. Poses are local or global consistently.</summary>
    public void Capture(
        IReadOnlyDictionary<int, (Vector3 pos, Quaternion rot)> oldPoses,
        IReadOnlyDictionary<int, (Vector3 pos, Quaternion rot)> newPoses,
        IReadOnlyDictionary<int, (Vector3 posVel, Vector3 angVel)>? oldVelocities = null)
    {
        Bones.Clear();
        Active = true;
        TimeSinceTransition = 0f;
        foreach (var kv in oldPoses)
        {
            if (!newPoses.TryGetValue(kv.Key, out var nw)) continue;
            var old = kv.Value;
            var b = new InertializationBoneState { BoneIndex = kv.Key, HalfLife = DefaultHalfLife };
            b.PositionOffset = old.pos - nw.pos;
            if (b.PositionOffset.Length() > MaxPositionOffset)
                b.PositionOffset = Vector3.Normalize(b.PositionOffset) * MaxPositionOffset;
            b.RotationOffset = Quaternion.Normalize(old.rot * Quaternion.Inverse(nw.rot));
            if (oldVelocities != null && oldVelocities.TryGetValue(kv.Key, out var vel))
            {
                b.PositionVelocity = vel.posVel;
                b.AngularVelocity = vel.angVel;
                if (b.AngularVelocity.Length() > MaxAngularVelocity)
                    b.AngularVelocity = Vector3.Normalize(b.AngularVelocity) * MaxAngularVelocity;
            }
            Bones.Add(b);
        }
    }

    /// <summary>Advance decay and return current offsets. Caller applies them to sampled pose.</summary>
    public bool Update(float dt)
    {
        if (!Active) return false;
        dt = Math.Max(0f, dt);
        TimeSinceTransition += dt;
        bool any = false;
        foreach (var b in Bones)
        {
            float halfLife = MathF.Max(0.001f, b.HalfLife);
            float lambda = 0.69314718056f / halfLife;
            float decay = MathF.Exp(-lambda * dt);

            // Position: integrate velocity then decay.
            b.PositionOffset += b.PositionVelocity * dt;
            b.PositionVelocity *= decay;
            b.PositionOffset *= decay;
            if (b.PositionOffset.Length() > MaxPositionOffset)
                b.PositionOffset = Vector3.Normalize(b.PositionOffset) * MaxPositionOffset;

            // Rotation: integrate angular velocity then decay toward identity.
            float angLen = b.AngularVelocity.Length();
            if (angLen > 1e-6f)
            {
                float angle = angLen * dt;
                Vector3 axis = b.AngularVelocity / angLen;
                Quaternion deltaQ = Quaternion.CreateFromAxisAngle(axis, angle);
                b.RotationOffset = Quaternion.Normalize(deltaQ * b.RotationOffset);
            }
            b.RotationOffset = Quaternion.Slerp(b.RotationOffset, Quaternion.Identity, 1f - decay);
            b.AngularVelocity *= decay;

            bool significant = b.PositionOffset.Length() > 0.0008f
                               || b.PositionVelocity.Length() > 0.001f
                               || b.AngularVelocity.Length() > 0.01f
                               || MathF.Abs(b.RotationOffset.W) < 0.9995f;
            any |= significant;
        }
        if (!any || TimeSinceTransition > DefaultHalfLife * 7f)
        {
            Active = false;
        }
        return Active;
    }

    public bool TryGetOffset(int boneIndex, out Vector3 posOffset, out Quaternion rotOffset)
    {
        for (int i = 0; i < Bones.Count; i++)
        {
            var b = Bones[i];
            if (b.BoneIndex != boneIndex) continue;
            posOffset = b.PositionOffset;
            rotOffset = b.RotationOffset;
            return true;
        }
        posOffset = Vector3.Zero;
        rotOffset = Quaternion.Identity;
        return false;
    }
}
