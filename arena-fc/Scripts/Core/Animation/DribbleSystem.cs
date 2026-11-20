// Deterministic timed-touch prototype for MatchEngine integration. The helper is
// deliberately not called by the live match yet; migrate the existing possession
// path behind a separately tested change rather than letting rendering affect play.
using System;
using System.Numerics;
using ArenaFC.Core;

namespace ArenaFC.Core.Animation;

public static class DribbleSystem
{
    public const float BaseTouchInterval = .28f;
    public const float MaxSeparationOpen = 1.15f;
    public const float MaxSeparationShield = .65f;

    /// <summary>Returns an updated visual/physics ball position using only a caller-owned
    /// deterministic RNG stream. Attribute arguments are normalized to 0..1.</summary>
    public static Vector3 Update(DribbleState state, int ownerId, Vector3 ballPosition,
        Vector3 playerPosition, Vector3 desiredDirection, float dribbling, float agility,
        float strength, bool wantsShield, float dt, Rng rng)
    {
        if (state == null) throw new ArgumentNullException(nameof(state));
        if (rng == null) throw new ArgumentNullException(nameof(rng));
        dt = Math.Max(0f, dt);
        state.OwnerId = ownerId;
        if (ownerId < 0) return ballPosition;

        float technical = Mx.Clamp(dribbling, 0f, 1f);
        float agile = Mx.Clamp(agility, 0f, 1f);
        float strong = Mx.Clamp(strength, 0f, 1f);
        state.TouchTimer -= dt;
        if (state.TouchTimer <= 0f)
        {
            Vector3 direction = Mx.Flat(desiredDirection);
            float error = (1f - technical) * .18f;
            direction += rng.Cone(error);
            direction = Mx.Norm(direction);
            if (direction.LengthSquared() < 1e-6f) direction = Vector3.UnitX;
            float impulse = .20f + .28f * technical;
            ballPosition += direction * impulse;
            state.LastTouchSpeed = impulse;
            state.TouchTimer = BaseTouchInterval * (1f - .45f * agile);
        }

        float maxSeparation = wantsShield ? MaxSeparationShield : MaxSeparationOpen;
        Vector3 offset = Mx.Flat(ballPosition - playerPosition);
        float distance = offset.Length();
        if (distance > maxSeparation && distance > 1e-5f)
        {
            float pull = (distance - maxSeparation) * .6f;
            ballPosition -= offset / distance * pull;
            offset = Mx.Flat(ballPosition - playerPosition);
            distance = offset.Length();
        }
        state.LocalOffsetX = offset.X;
        state.LocalOffsetZ = offset.Z;
        state.Separation = distance;
        state.Shielding = wantsShield;
        state.ShieldStrength = wantsShield ? Mx.Clamp(.25f + strong * .75f, 0f, 1f) : 0f;
        return ballPosition;
    }
}
