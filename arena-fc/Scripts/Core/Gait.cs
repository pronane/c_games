// Arena FC - pure-C# gait curve.  Kept Godot-free so both clients can share it and
// the headless core tests can assert the joint sign convention.
//
// Sign convention (Godot, right-handed rotation about X):
//   * a leg bone points DOWN (0,-1,0).  A POSITIVE X rotation moves it toward -Z,
//     i.e. BEHIND the player (local forward is +Z).  So a forward thigh swing needs
//     a NEGATIVE angle, and a knee flexion (lower leg folding back) needs a POSITIVE
//     angle.  The old code used positive thigh angles, which is why the legs came
//     out behind the player and the knees looked locked.
//
// The 06.11.2026 recording still looked "wooden": the old curve only moved thighs,
// knees and feet on one axis and the renderer wrote those angles straight into the
// skeleton every frame.  Added hip yaw/roll, shoulder counter-rotation, foot roll,
// sprint/dribble lean and a Lerp() so the rig can ease between poses.
using System;

namespace ArenaFC.Core;

public struct GaitPose
{
    public float HipL, HipR, KneeL, KneeR, FootL, FootR;
    public float HipYawL, HipYawR, HipRollL, HipRollR;
    public float FootRollL, FootRollR;
    public float ArmL, ArmR, ElbowL, ElbowR, ArmOut;
    public float ShoulderYaw, ShoulderRoll;
    public float Lean, Twist, Roll, Breathe, TurnLean, Stride;
    public float BobX, BobY;
}

public static class Gait
{
    public static GaitPose Compute(float speed, float phase, float time,
                                   bool sprint = false, bool dribble = false)
    {
        float amp = Math.Clamp(speed / 6f, 0f, 1f);
        float run = Math.Clamp(speed / 5.5f, 0f, 1f);
        float sprintBoost = sprint ? .15f : 0f;
        float dribbleBoost = dribble ? .18f : 0f;
        amp = Math.Clamp(amp + dribbleBoost, 0f, 1f);
        run = Math.Clamp(run + sprintBoost, 0f, 1f);
        float s = MathF.Sin(phase), c = MathF.Cos(phase), s2 = MathF.Sin(phase * 2f);
        float breathe = MathF.Sin(time * 1.6f) * .012f * (1f - amp);

        // Thighs swing FORWARD (negative X) with a second harmonic so the reversal
        // at the end of the stride is not a straight-line snap.
        float hipL = -(s * .66f + s2 * .10f) * amp;
        float hipR = -hipL;

        // Knees always bend, including when walking, and flex smoothly through the
        // swing phase (positive X = shin folds backwards).
        float flex = .35f + .65f * amp;
        float kneeL = (.14f + .80f * (.5f + .5f * MathF.Sin(phase + .40f)) + .10f * s2) * flex;
        float kneeR = (.14f + .80f * (.5f + .5f * MathF.Sin(phase + MathF.PI + .40f)) - .10f * s2) * flex;
        kneeL = MathF.Max(.05f, kneeL);
        kneeR = MathF.Max(.05f, kneeR);

        // Ankles counter-rotate so the boot stays roughly flat on the ground.
        float footL = -kneeL * .32f + hipL * .10f;
        float footR = -kneeR * .32f + hipR * .10f;

        // Small out-of-plane rotations stop the legs looking like a 2D hinge.
        float hipYawL = (s * .06f + (dribble ? MathF.Sin(phase * 2f) * .04f : 0f)) * amp;
        float hipYawR = -hipYawL;
        float hipRollL = (c * .035f + sprintBoost * .02f) * amp;
        float hipRollR = -hipRollL;
        float footRollL = -c * .12f * amp;
        float footRollR = c * .12f * amp;

        float armL = -hipL * .62f - .10f * run;   // arms counter-swing
        float armR = -armL;
        float elbowL = -.32f - .22f * run - .18f * MathF.Max(0f, -hipL);
        float elbowR = -.32f - .22f * run - .18f * MathF.Max(0f, -hipR);
        float armOut = .12f + .14f * run + (dribble ? .06f : 0f);
        float shoulderYaw = -s * .10f * amp;
        float shoulderRoll = c * .05f * amp;

        float lean = .04f + .10f * run + sprintBoost * .10f + (dribble ? .08f : 0f) + breathe;
        float twist = s * .075f * amp;
        float roll = s2 * .025f * amp;
        float turnLean = sprintBoost * .10f + (dribble ? .08f : 0f);
        float bobY = (.5f - .5f * MathF.Cos(phase * 2f)) * amp * .055f;
        float bobX = s * amp * .018f;

        return new GaitPose
        {
            HipL = hipL, HipR = hipR, KneeL = kneeL, KneeR = kneeR,
            FootL = footL, FootR = footR,
            HipYawL = hipYawL, HipYawR = hipYawR,
            HipRollL = hipRollL, HipRollR = hipRollR,
            FootRollL = footRollL, FootRollR = footRollR,
            ArmL = armL, ArmR = armR, ElbowL = elbowL, ElbowR = elbowR, ArmOut = armOut,
            ShoulderYaw = shoulderYaw, ShoulderRoll = shoulderRoll,
            Lean = lean, Twist = twist, Roll = roll, Breathe = breathe,
            TurnLean = turnLean, Stride = amp,
            BobX = bobX, BobY = bobY,
        };
    }

    private static float L(float a, float b, float t) => a + (b - a) * Math.Clamp(t, 0f, 1f);

    /// <summary>Frame-rate independent easing between gait poses.  Used by the
    /// renderer so a direction change or action clip no longer snaps joints.</summary>
    public static GaitPose Lerp(GaitPose a, GaitPose b, float t) => new()
    {
        HipL = L(a.HipL, b.HipL, t), HipR = L(a.HipR, b.HipR, t),
        KneeL = L(a.KneeL, b.KneeL, t), KneeR = L(a.KneeR, b.KneeR, t),
        FootL = L(a.FootL, b.FootL, t), FootR = L(a.FootR, b.FootR, t),
        HipYawL = L(a.HipYawL, b.HipYawL, t), HipYawR = L(a.HipYawR, b.HipYawR, t),
        HipRollL = L(a.HipRollL, b.HipRollL, t), HipRollR = L(a.HipRollR, b.HipRollR, t),
        FootRollL = L(a.FootRollL, b.FootRollL, t), FootRollR = L(a.FootRollR, b.FootRollR, t),
        ArmL = L(a.ArmL, b.ArmL, t), ArmR = L(a.ArmR, b.ArmR, t),
        ElbowL = L(a.ElbowL, b.ElbowL, t), ElbowR = L(a.ElbowR, b.ElbowR, t),
        ArmOut = L(a.ArmOut, b.ArmOut, t),
        ShoulderYaw = L(a.ShoulderYaw, b.ShoulderYaw, t),
        ShoulderRoll = L(a.ShoulderRoll, b.ShoulderRoll, t),
        Lean = L(a.Lean, b.Lean, t), Twist = L(a.Twist, b.Twist, t),
        Roll = L(a.Roll, b.Roll, t), Breathe = L(a.Breathe, b.Breathe, t),
        TurnLean = L(a.TurnLean, b.TurnLean, t), Stride = L(a.Stride, b.Stride, t),
        BobX = L(a.BobX, b.BobX, t), BobY = L(a.BobY, b.BobY, t),
    };
}
