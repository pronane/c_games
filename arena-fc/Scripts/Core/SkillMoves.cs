// Arena FC — skill moves via stick gestures (FC 26 / eFootball parity).
// Step-over, roulette, elastico, rainbow flick — triggered by stick patterns.
using System;

namespace ArenaFC.Core;

/// <summary>Skill move types.</summary>
public enum SkillMove
{
    None,
    StepOver,      // quick foot over ball
    Roulette,      // 360 spin
    Elastico,      // outside-in flick
    Rainbow,       // flick over head
    FakeShot,      // fake the shot, keep ball
    HeelToHeel,    // heel drag
    BallRoll,      // sole roll
}

/// <summary>
/// Detects skill moves from stick input patterns.
/// Each move has a gesture (stick direction sequence) and success chance
/// based on Dribbling skill and pressure.
/// </summary>
public static class SkillMoves
{
    /// <summary>Detect skill move from stick input.</summary>
    /// <param name="stickX">Current stick X (-1 to 1)</param>
    /// <param name="stickY">Current stick Y (-1 to 1)</param>
    /// <param name="prevStickX">Previous frame stick X</param>
    /// <param name="prevStickY">Previous frame stick Y</param>
    /// <param name="dribbling">Player dribbling skill (0-99)</param>
    /// <param name="pressure">Nearest opponent distance (metres)</param>
    public static SkillMove Detect(float stickX, float stickY,
                                    float prevStickX, float prevStickY,
                                    int dribbling, float pressure)
    {
        // Quick flick right then left = elastico
        if (stickX > 0.7f && prevStickX < 0.3f && stickY > -0.3f)
            return SkillMove.Elastico;

        // Quick flick left then right = step-over
        if (stickX < -0.7f && prevStickX > -0.3f && stickY > -0.3f)
            return SkillMove.StepOver;

        // Full circle (approximated by diagonal) = roulette
        if (Math.Abs(stickX) > 0.6f && Math.Abs(stickY) > 0.6f)
            return SkillMove.Roulette;

        // Flick up = rainbow
        if (stickY > 0.8f && prevStickY < 0.3f)
            return SkillMove.Rainbow;

        // Flick down = fake shot
        if (stickY < -0.8f && prevStickY > -0.3f)
            return SkillMove.FakeShot;

        return SkillMove.None;
    }

    /// <summary>Calculate success chance for a skill move.</summary>
    /// <param name="dribbling">Player dribbling skill (0.0–1.0 scale, e.g. Pace).</param>
    public static float SuccessChance(SkillMove move, float dribbling, float pressure)
    {
        float baseChance = move switch
        {
            SkillMove.StepOver => 0.65f,
            SkillMove.Roulette => 0.55f,
            SkillMove.Elastico => 0.60f,
            SkillMove.Rainbow => 0.45f,
            SkillMove.FakeShot => 0.70f,
            SkillMove.HeelToHeel => 0.75f,
            SkillMove.BallRoll => 0.80f,
            _ => 0f,
        };

        // Dribbling skill bonus (0.5 = neutral, 1.0 = +0.2, 0.0 = -0.2)
        float skillBonus = (dribbling - 0.5f) * 0.4f;

        // Pressure penalty (closer opponent = harder)
        float pressurePenalty = pressure < 2f ? (2f - pressure) * 0.15f : 0f;

        return Math.Clamp(baseChance + skillBonus - pressurePenalty, 0.1f, 0.95f);
    }

    /// <summary>Get the animation clip name for a skill move.</summary>
    public static string ClipName(SkillMove move) => move switch
    {
        SkillMove.StepOver => "skill_step_over",
        SkillMove.Roulette => "skill_roulette",
        SkillMove.Elastico => "skill_elastico",
        SkillMove.Rainbow => "skill_rainbow",
        SkillMove.FakeShot => "skill_fake_shot",
        SkillMove.HeelToHeel => "skill_heel_to_heel",
        SkillMove.BallRoll => "skill_ball_roll",
        _ => "dribble",
    };

    /// <summary>Duration of the skill move animation (seconds).</summary>
    public static float Duration(SkillMove move) => move switch
    {
        SkillMove.StepOver => 0.5f,
        SkillMove.Roulette => 0.8f,
        SkillMove.Elastico => 0.6f,
        SkillMove.Rainbow => 0.7f,
        SkillMove.FakeShot => 0.4f,
        SkillMove.HeelToHeel => 0.5f,
        SkillMove.BallRoll => 0.4f,
        _ => 0f,
    };
}
