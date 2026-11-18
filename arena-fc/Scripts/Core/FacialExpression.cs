// Arena FC — facial expression system for the Face bone.
// Drives emotion based on match state (goal, foul, injury, etc.).
using System;

namespace ArenaFC.Core;

/// <summary>Emotion states for player faces.</summary>
public enum Emotion
{
    Neutral,
    Happy,       // scored, won tackle
    Sad,         // conceded, missed chance
    Angry,       // fouled, lost ball
    Surprised,   // unexpected event
    Tired,       // low stamina
    Focused,     // about to shoot/pass
    Injured,     // after foul/injury
}

/// <summary>
/// Drives facial expressions from match events.
/// Maps emotion to Face bone rotation/position offsets.
/// </summary>
public class FacialExpression
{
    public Emotion Current { get; private set; } = Emotion.Neutral;
    private float _timer;
    private Emotion _previous = Emotion.Neutral;

    /// <summary>Set emotion with auto-revert after duration.</summary>
    public void Set(Emotion emotion, float duration = 2f)
    {
        _previous = Current;
        Current = emotion;
        _timer = duration;
    }

    /// <summary>Update and return face offset (yaw, pitch, roll).</summary>
    public (float yaw, float pitch, float roll) Update(float dt)
    {
        _timer -= dt;
        if (_timer <= 0 && Current != Emotion.Neutral)
        {
            Current = _previous;
            _previous = Emotion.Neutral;
        }

        return Current switch
        {
            Emotion.Happy => (0f, -0.1f, 0.05f),
            Emotion.Sad => (0f, 0.15f, -0.05f),
            Emotion.Angry => (0f, -0.05f, 0.1f),
            Emotion.Surprised => (0f, -0.2f, 0f),
            Emotion.Tired => (0f, 0.2f, 0f),
            Emotion.Focused => (0f, -0.05f, 0f),
            Emotion.Injured => (0f, 0.1f, 0.15f),
            _ => (0f, 0f, 0f),
        };
    }

    /// <summary>React to a match event.</summary>
    public void ReactToEvent(string eventType)
    {
        switch (eventType)
        {
            case "goal_scored": Set(Emotion.Happy, 3f); break;
            case "goal_conceded": Set(Emotion.Sad, 3f); break;
            case "fouled": Set(Emotion.Angry, 2f); break;
            case "injured": Set(Emotion.Injured, 4f); break;
            case "missed_chance": Set(Emotion.Sad, 2f); break;
            case "won_tackle": Set(Emotion.Happy, 1.5f); break;
            case "lost_ball": Set(Emotion.Angry, 1.5f); break;
            case "about_to_shoot": Set(Emotion.Focused, 1f); break;
            case "low_stamina": Set(Emotion.Tired, 5f); break;
            case "surprise": Set(Emotion.Surprised, 1f); break;
        }
    }
}
