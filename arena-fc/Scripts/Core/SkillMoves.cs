// Arena FC — skill moves via stick gestures (FC 26 / eFootball parity).
// Step-over, roulette, elastico, rainbow flick — triggered by stick patterns.
using System;

namespace ArenaFC.Core;

/// <summary>Explicit shot modifiers.</summary>
public enum ShotStyle { Auto, Finesse, Chip, Low, Trivela }

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
    // v11.42: Meshy-animated moves.  Appended so the wire values of the first eight stay the same.
    ReverseStepOver,
    DoubleStepOver,
    BodyFeint,
    ReverseElastico,
    DragBack,
    CruyffTurn,
    LaCroqueta,
    HeelChop,
    FakePass,
    BallHop,
    HeelFlick,
    ScoopTurn,
    SombreroFlick,
    BerbaSpin,
    SoleRollTurn,
    OutsideHook,
    InsideHook,
    HesitationBurst,
    KnockOnAndRun,
    LaneChange,
    TornadoSpin,
    BehindLegTurn,
    RabonaFake,
    FlairPass,
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
            SkillMove.ReverseStepOver => 0.62f,
            SkillMove.DoubleStepOver => 0.58f,
            SkillMove.BodyFeint => 0.72f,
            SkillMove.ReverseElastico => 0.55f,
            SkillMove.DragBack => 0.75f,
            SkillMove.CruyffTurn => 0.68f,
            SkillMove.LaCroqueta => 0.62f,
            SkillMove.HeelChop => 0.65f,
            SkillMove.FakePass => 0.70f,
            SkillMove.BallHop => 0.60f,
            SkillMove.HeelFlick => 0.50f,
            SkillMove.ScoopTurn => 0.62f,
            SkillMove.SombreroFlick => 0.42f,
            SkillMove.BerbaSpin => 0.55f,
            SkillMove.SoleRollTurn => 0.66f,
            SkillMove.OutsideHook => 0.72f,
            SkillMove.InsideHook => 0.72f,
            SkillMove.HesitationBurst => 0.66f,
            SkillMove.KnockOnAndRun => 0.60f,
            SkillMove.LaneChange => 0.70f,
            SkillMove.TornadoSpin => 0.45f,
            SkillMove.BehindLegTurn => 0.58f,
            SkillMove.RabonaFake => 0.50f,
            SkillMove.FlairPass => 0.60f,
            _ => 0f,
        };

        // Dribbling skill bonus (0.5 = neutral, 1.0 = +0.2, 0.0 = -0.2)
        float skillBonus = (dribbling - 0.5f) * 0.4f;

        // Pressure penalty (closer opponent = harder)
        float pressurePenalty = pressure < 2f ? (2f - pressure) * 0.15f : 0f;

        return Math.Clamp(baseChance + skillBonus - pressurePenalty, 0.1f, 0.95f);
    }

    /// <summary>Player-facing name ("Step-over", not "StepOver").</summary>
    public static string DisplayName(SkillMove move) => move switch
    {
        SkillMove.StepOver => "step-over",
        SkillMove.Roulette => "roulette",
        SkillMove.Elastico => "elastico",
        SkillMove.Rainbow => "rainbow flick",
        SkillMove.FakeShot => "fake shot",
        SkillMove.HeelToHeel => "drag-back",
        SkillMove.BallRoll => "ball roll",
        SkillMove.ReverseStepOver => "reverse step-over",
        SkillMove.DoubleStepOver => "double step-over",
        SkillMove.BodyFeint => "body feint",
        SkillMove.ReverseElastico => "reverse elastico",
        SkillMove.DragBack => "drag-back",
        SkillMove.CruyffTurn => "Cruyff turn",
        SkillMove.LaCroqueta => "la croqueta",
        SkillMove.HeelChop => "heel chop",
        SkillMove.FakePass => "fake pass",
        SkillMove.BallHop => "ball hop",
        SkillMove.HeelFlick => "heel flick",
        SkillMove.ScoopTurn => "scoop turn",
        SkillMove.SombreroFlick => "sombrero flick",
        SkillMove.BerbaSpin => "Berba spin",
        SkillMove.SoleRollTurn => "sole roll turn",
        SkillMove.OutsideHook => "outside hook",
        SkillMove.InsideHook => "inside hook",
        SkillMove.HesitationBurst => "stop and go",
        SkillMove.KnockOnAndRun => "knock-on and run",
        SkillMove.LaneChange => "lane change",
        SkillMove.TornadoSpin => "tornado spin",
        SkillMove.BehindLegTurn => "behind-the-leg turn",
        SkillMove.RabonaFake => "rabona fake",
        SkillMove.FlairPass => "flair pass",
        _ => "skill",
    };

    /// <summary>Right-stick flick direction, screen-relative.</summary>
    public enum Flick { None, Side, Up, Down }

    /// <summary>Classify a right-stick flick: the stick must go from near centre
    /// (&lt; 0.35) to near full (&gt; 0.75) between two reads.  Y is screen-down
    /// positive (Godot's joypad convention), so "up" is a negative Y.</summary>
    public static Flick DetectFlick(float x, float y, float prevMagnitude)
    {
        float mag = MathF.Sqrt(x * x + y * y);
        if (mag < 0.75f || prevMagnitude >= 0.35f) return Flick.None;
        if (MathF.Abs(x) >= MathF.Abs(y)) return Flick.Side;
        return y < 0f ? Flick.Up : Flick.Down;
    }

    /// <summary>The controller scheme taught in Training:
    /// RS flick side = step-over, down = drag-back, up = ball roll;
    /// with LT held: side = elastico, down = roulette, up = rainbow flick.
    /// The fake shot is "hold X (shoot) then tap A (pass)", handled by the input layer.</summary>
    public static SkillMove FromFlick(Flick flick, bool modifier) => (flick, modifier) switch
    {
        (Flick.Side, false) => SkillMove.StepOver,
        (Flick.Down, false) => SkillMove.HeelToHeel,
        (Flick.Up, false) => SkillMove.BallRoll,
        (Flick.Side, true) => SkillMove.Elastico,
        (Flick.Down, true) => SkillMove.Roulette,
        (Flick.Up, true) => SkillMove.Rainbow,
        _ => SkillMove.None,
    };

    /// <summary>Keyboard skill keys 1-7.</summary>
    public static SkillMove FromNumberKey(int n) => n switch
    {
        1 => SkillMove.StepOver,
        2 => SkillMove.HeelToHeel,
        3 => SkillMove.BallRoll,
        4 => SkillMove.Elastico,
        5 => SkillMove.Roulette,
        6 => SkillMove.Rainbow,
        7 => SkillMove.FakeShot,
        _ => SkillMove.None,
    };

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
        SkillMove.ReverseStepOver => "skill_reverse_stepover",
        SkillMove.DoubleStepOver => "skill_double_stepover",
        SkillMove.BodyFeint => "skill_body_feint",
        SkillMove.ReverseElastico => "skill_reverse_elastico",
        SkillMove.DragBack => "skill_drag_back",
        SkillMove.CruyffTurn => "skill_cruyff_turn",
        SkillMove.LaCroqueta => "skill_la_croqueta",
        SkillMove.HeelChop => "skill_heel_chop",
        SkillMove.FakePass => "skill_fake_pass",
        SkillMove.BallHop => "skill_ball_hop",
        SkillMove.HeelFlick => "skill_heel_flick",
        SkillMove.ScoopTurn => "skill_scoop_turn",
        SkillMove.SombreroFlick => "skill_sombrero_flick",
        SkillMove.BerbaSpin => "skill_berba_spin",
        SkillMove.SoleRollTurn => "skill_sole_roll_turn",
        SkillMove.OutsideHook => "skill_outside_hook",
        SkillMove.InsideHook => "skill_inside_hook",
        SkillMove.HesitationBurst => "skill_hesitation_burst",
        SkillMove.KnockOnAndRun => "skill_knock_on_and_run",
        SkillMove.LaneChange => "skill_lane_change",
        SkillMove.TornadoSpin => "skill_tornado_spin",
        SkillMove.BehindLegTurn => "skill_behind_leg_turn",
        SkillMove.RabonaFake => "skill_rabona_fake",
        SkillMove.FlairPass => "skill_flair_pass",
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
        SkillMove.ReverseStepOver => 0.55f,
        SkillMove.DoubleStepOver => 0.75f,
        SkillMove.BodyFeint => 0.45f,
        SkillMove.ReverseElastico => 0.60f,
        SkillMove.DragBack => 0.50f,
        SkillMove.CruyffTurn => 0.60f,
        SkillMove.LaCroqueta => 0.45f,
        SkillMove.HeelChop => 0.50f,
        SkillMove.FakePass => 0.45f,
        SkillMove.BallHop => 0.50f,
        SkillMove.HeelFlick => 0.50f,
        SkillMove.ScoopTurn => 0.60f,
        SkillMove.SombreroFlick => 0.75f,
        SkillMove.BerbaSpin => 0.80f,
        SkillMove.SoleRollTurn => 0.60f,
        SkillMove.OutsideHook => 0.45f,
        SkillMove.InsideHook => 0.45f,
        SkillMove.HesitationBurst => 0.70f,
        SkillMove.KnockOnAndRun => 0.75f,
        SkillMove.LaneChange => 0.45f,
        SkillMove.TornadoSpin => 0.80f,
        SkillMove.BehindLegTurn => 0.55f,
        SkillMove.RabonaFake => 0.60f,
        SkillMove.FlairPass => 0.45f,
        _ => 0f,
    };

    /// <summary>v11.42: each taught input has a family of related moves, as in modern football games.  The
    /// match picks one with its seeded RNG (so online peers agree); roll is in [0, 1).  The taught move itself
    /// comes up most often, and the training ground always plays it.</summary>
    public static readonly System.Collections.Generic.IReadOnlyDictionary<SkillMove, SkillMove[]> Families =
        new System.Collections.Generic.Dictionary<SkillMove, SkillMove[]>
        {
            // Members kept after reviewing every Meshy skill clip on the Arena player (v11.42 swift, v11.43 prime);
            // heel flick, sole roll, inside hook, behind-the-leg, rabona fake and flair pass stay callable by name only.
            [SkillMove.StepOver] = new[] { SkillMove.StepOver, SkillMove.StepOver, SkillMove.ReverseStepOver, SkillMove.DoubleStepOver, SkillMove.BodyFeint, SkillMove.LaneChange },
            [SkillMove.HeelToHeel] = new[] { SkillMove.HeelToHeel, SkillMove.HeelToHeel, SkillMove.DragBack, SkillMove.CruyffTurn, SkillMove.ScoopTurn, SkillMove.HeelChop },
            [SkillMove.BallRoll] = new[] { SkillMove.BallRoll, SkillMove.BallRoll, SkillMove.LaCroqueta, SkillMove.OutsideHook, SkillMove.HesitationBurst },
            [SkillMove.Elastico] = new[] { SkillMove.Elastico, SkillMove.Elastico, SkillMove.ReverseElastico, SkillMove.KnockOnAndRun },
            [SkillMove.Roulette] = new[] { SkillMove.Roulette, SkillMove.Roulette, SkillMove.TornadoSpin, SkillMove.BerbaSpin },
            [SkillMove.Rainbow] = new[] { SkillMove.Rainbow, SkillMove.Rainbow, SkillMove.HeelFlick, SkillMove.BallHop, SkillMove.SombreroFlick },
            [SkillMove.FakeShot] = new[] { SkillMove.FakeShot, SkillMove.FakeShot, SkillMove.FakePass },
        };

    /// <summary>The move actually played for an input: a member of its family (itself when it has none).</summary>
    public static SkillMove Variant(SkillMove taught, float roll)
    {
        if (!Families.TryGetValue(taught, out var fam) || fam.Length == 0) return taught;
        int i = (int)(Math.Clamp(roll, 0f, 0.9999f) * fam.Length);
        return fam[i];
    }
}
