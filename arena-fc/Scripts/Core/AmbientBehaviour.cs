// Arena FC — ambient off-ball behaviour (FC 26 "player humanisation").
// Off-ball players point, gesture, direct teammates, and react to play.
using System;

namespace ArenaFC.Core;

/// <summary>Ambient behaviour types for off-ball players.</summary>
public enum AmbientAction
{
    None,
    Point,        // point toward space / teammate
    Gesture,      // wave arms (call for ball)
    Direct,       // point and shout (direct a run)
    Celebrate,    // team scored
    Disappointed, // team conceded
    Stretch,      // pre-match warmup
    WalkBack,     // walk back to position after play
    LookAround,   // scan the pitch
}

/// <summary>
/// Manages ambient behaviour for off-ball players.
/// Players without the ball periodically perform ambient actions
/// to make the pitch feel alive (FC 26 "player humanisation").
/// </summary>
public class AmbientBehaviour
{
    private readonly Random _rng = new(42);
    private float _nextActionTime;
    private float _actionDuration;

    public AmbientAction Current { get; private set; } = AmbientAction.None;
    public bool IsActive => Current != AmbientAction.None;

    /// <summary>Update ambient behaviour. Returns current action.</summary>
    public AmbientAction Update(float dt, float time, bool hasBall,
                                bool isOffBall, float stamina)
    {
        if (IsActive)
        {
            _actionDuration -= dt;
            if (_actionDuration <= 0)
            {
                Current = AmbientAction.None;
                _nextActionTime = time + 3f + (float)_rng.NextDouble() * 5f;
            }
            return Current;
        }

        // Only trigger for off-ball players
        if (!isOffBall || hasBall) return AmbientAction.None;

        if (time >= _nextActionTime)
        {
            // Random ambient action
            int roll = _rng.Next(100);
            if (roll < 20) Current = AmbientAction.Point;
            else if (roll < 35) Current = AmbientAction.Gesture;
            else if (roll < 45) Current = AmbientAction.Direct;
            else if (roll < 55) Current = AmbientAction.LookAround;
            else if (roll < 60 && stamina < 0.3f) Current = AmbientAction.Stretch;
            else Current = AmbientAction.None;

            if (Current != AmbientAction.None)
            {
                _actionDuration = 1.5f + (float)_rng.NextDouble() * 2f;
            }
        }

        return Current;
    }

    /// <summary>React to a goal.</summary>
    public void OnGoal(bool scored)
    {
        Current = scored ? AmbientAction.Celebrate : AmbientAction.Disappointed;
        _actionDuration = 3f;
    }

    /// <summary>Get the animation clip name.</summary>
    public string ClipName => Current switch
    {
        AmbientAction.Point => "ambient_point",
        AmbientAction.Gesture => "ambient_gesture",
        AmbientAction.Direct => "ambient_direct",
        AmbientAction.Celebrate => "celebrate",
        AmbientAction.Disappointed => "disappointed",
        AmbientAction.Stretch => "ambient_stretch",
        AmbientAction.WalkBack => "walk",
        AmbientAction.LookAround => "ambient_look",
        _ => "idle",
    };
}
