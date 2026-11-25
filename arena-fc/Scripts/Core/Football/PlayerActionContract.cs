using System.Numerics;

namespace ArenaFC.Core.Football;

/// <summary>
/// Simulation-to-animation action contract. The simulation remains authoritative;
/// animation executes this contract without deciding match outcomes.
/// </summary>
public sealed class PlayerActionContract
{
    public int PlayerIndex;
    public string Intent = "move";
    public Vector3 TargetPosition;
    public Vector3 FacingDirection;
    public Vector3 BallContactPosition;
    public float BallContactTime = -1f;
    public float DesiredSpeed;
    public float DesiredTurnRate;
    public bool RequiresFootPlant;
    public bool RequiresBallContact;
    public float SpeedLimit = 10f;
    public bool ShouldSprint;
    public bool Pressing;
    public string Role = "";
}
