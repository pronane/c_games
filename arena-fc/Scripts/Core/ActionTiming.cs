namespace ArenaFC.Core;

public static class ActionTiming
{
    public static float ContactAlignedPlaybackScale(float clipDuration, float contactFraction, float contactAt)
    {
        if (clipDuration <= 0f || contactFraction <= 0f || contactAt <= 0f) return 1f;
        return clipDuration * contactFraction / contactAt;
    }

    public static float ContactEnvelope(float elapsed, float duration, float contactAt)
    {
        if (duration <= 0f) return 0f;

        float progress = Math.Clamp(elapsed / duration, 0f, 1f);
        float contact = Math.Clamp(contactAt / duration, 0.05f, 0.95f);
        float halfPi = MathF.PI * 0.5f;
        float envelope = progress <= contact
            ? MathF.Sin(progress / contact * halfPi)
            : MathF.Cos((progress - contact) / (1f - contact) * halfPi);
        return Math.Clamp(envelope, 0f, 1f);
    }
}
