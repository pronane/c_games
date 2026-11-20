using System;

namespace ArenaFC.Core.Animation;

/// <summary>Versioned feature contract shared by the offline baker and Core search.</summary>
public static class MotionFeatureLayout
{
    public const int SchemaVersion = 1;
    public static readonly string[] Names =
    {
        "foot_l_pos_x", "foot_l_pos_z", "foot_r_pos_x", "foot_r_pos_z",
        "foot_l_vel_x", "foot_l_vel_z", "foot_r_vel_x", "foot_r_vel_z",
        "root_vel_x", "root_vel_z", "yaw_rate",
        "traj_pos_0_x", "traj_pos_0_z", "traj_pos_1_x", "traj_pos_1_z",
        "traj_pos_2_x", "traj_pos_2_z",
        "traj_dir_0_x", "traj_dir_0_z", "traj_dir_1_x", "traj_dir_1_z",
        "traj_dir_2_x", "traj_dir_2_z",
    };
    public static readonly float[] TrajectoryTimes = { .2f, .4f, .6f };
    public static readonly float[] GroupWeights = CreateWeights();
    public static int Dimensions => Names.Length;

    public static bool Matches(string[] names)
    {
        if (names == null || names.Length != Names.Length) return false;
        for (int i = 0; i < Names.Length; i++)
            if (!string.Equals(names[i], Names[i], StringComparison.Ordinal)) return false;
        return true;
    }

    private static float[] CreateWeights()
    {
        var weights = new float[Names.Length];
        Array.Fill(weights, 1f);
        for (int i = 4; i < 8; i++) weights[i] = 1.3f; // foot velocity
        weights[8] = weights[9] = .8f;                // root velocity
        weights[10] = .7f;                            // yaw rate
        for (int i = 11; i < 17; i++) weights[i] = 1.5f; // trajectory position
        for (int i = 17; i < 23; i++) weights[i] = 1.2f; // trajectory facing
        return weights;
    }
}
