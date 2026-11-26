using System;

namespace ArenaFC.Core.Animation;

/// <summary>
/// Lightweight in-engine animation quality metrics. Values are updated by
/// runtime/Godot instrumentation and can be sampled in tests/telemetry.
/// </summary>
public sealed class AnimationMetrics
{
    public int Samples;
    public float FootSlideAccum;
    public float ContactFrameErrorAccum;
    public float TransitionDiscontinuityAccum;
    public int ContactEvents;
    public int TransitionEvents;

    public float AvgFootSlide => Samples > 0 ? FootSlideAccum / Samples : 0f;
    public float AvgContactFrameError => ContactEvents > 0 ? ContactFrameErrorAccum / ContactEvents : 0f;
    public float AvgTransitionDiscontinuity => TransitionEvents > 0 ? TransitionDiscontinuityAccum / TransitionEvents : 0f;

    public void RecordSample(float footSlide, float transitionDiscontinuity, bool transition)
    {
        Samples++;
        FootSlideAccum += MathF.Max(0f, footSlide);
        if (transition)
        {
            TransitionEvents++;
            TransitionDiscontinuityAccum += MathF.Max(0f, transitionDiscontinuity);
        }
    }

    public void RecordContact(float frameError)
    {
        ContactEvents++;
        ContactFrameErrorAccum += MathF.Max(0f, frameError);
    }

    public void Reset()
    {
        Samples = 0; FootSlideAccum = 0f; ContactFrameErrorAccum = 0f; TransitionDiscontinuityAccum = 0f;
        ContactEvents = 0; TransitionEvents = 0;
    }
}
