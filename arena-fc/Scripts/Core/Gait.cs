// Arena FC - pure-C# gait curve.  Kept Godot-free so both clients can share it and
// the headless core tests can assert the joint sign convention.
//
// Sign convention (Godot, right-handed rotation about X):
//   * a leg bone points DOWN (0,-1,0).  A POSITIVE X rotation moves it toward -Z,
//     i.e. BEHIND the player (local forward is +Z).  So a forward thigh swing needs
//     a NEGATIVE angle, and a knee flexion (lower leg folding back) needs a POSITIVE
//     angle.  The old code used positive thigh angles, which is why the legs came
//     out behind the player and the knees looked locked.
using System;

namespace ArenaFC.Core;

public struct GaitPose
{
    public float HipL, HipR, KneeL, KneeR, FootL, FootR;
    public float ArmL, ArmR, ElbowL, ElbowR, ArmOut;
    public float Lean, Twist, Roll, Breathe;
    public float BobX, BobY;
}

public static class Gait
{
    public static GaitPose Compute(float speed, float phase, float time)
    {
        float amp = Math.Clamp(speed / 6f, 0f, 1f);
        float run = Math.Clamp(speed / 5.5f, 0f, 1f);
        float s = MathF.Sin(phase), s2 = MathF.Sin(phase * 2f);
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

        float armL = -hipL * .62f - .10f * run;   // arms counter-swing
        float armR = -armL;
        float elbowL = -.32f - .22f * run - .18f * MathF.Max(0f, -hipL);
        float elbowR = -.32f - .22f * run - .18f * MathF.Max(0f, -hipR);
        float armOut = .12f + .14f * run;

        float lean = .04f + .10f * run + breathe;
        float twist = s * .075f * amp;
        float roll = s2 * .025f * amp;
        float bobY = (.5f - .5f * MathF.Cos(phase * 2f)) * amp * .055f;
        float bobX = s * amp * .018f;

        return new GaitPose
        {
            HipL = hipL, HipR = hipR, KneeL = kneeL, KneeR = kneeR,
            FootL = footL, FootR = footR,
            ArmL = armL, ArmR = armR, ElbowL = elbowL, ElbowR = elbowR, ArmOut = armOut,
            Lean = lean, Twist = twist, Roll = roll, Breathe = breathe,
            BobX = bobX, BobY = bobY,
        };
    }
}
