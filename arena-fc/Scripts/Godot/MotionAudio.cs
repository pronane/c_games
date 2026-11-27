// Presentation-only: edge-triggered motion events -> ProceduralAudio.
// Does not touch MatchState / sim authority.
using ArenaFC.Core.Animation;
using Godot;

namespace ArenaFC.GodotGame;

public static class MotionAudio
{
    /// <summary>Play boot plant and soft contact backup sounds from MotionState edges.</summary>
    public static void Play(Node host, MotionState motion)
    {
        if (host == null || motion == null) return;
        var audio = host.GetNodeOrNull("/root/Audio");
        if (audio == null) return;

        if (motion.FootstepLeft || motion.FootstepRight)
            audio.Call("play_boot", "grass");

        if (!motion.ContactCrossed) return;
        // Soft backup when no MatchEvent raised for this contact frame.
        if (motion.LastIntent is PlayerIntent.Pass or PlayerIntent.ThroughBall)
            audio.Call("play_pass");
        else if (motion.LastIntent is PlayerIntent.Shoot)
            audio.Call("play_kick");
    }
}
