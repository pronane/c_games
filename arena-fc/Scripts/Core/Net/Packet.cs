// Arena FC - packet + DTOs for protocol v2.  Every JSON name is explicit so the
// C# .NET server, the GDScript browser client and shared/netplay/server/arena/*.js
// all read and write byte-compatible messages.
using System;
using System.Collections.Generic;
using System.Numerics;
using System.Text.Json.Serialization;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

/// <summary>One command, quantised to 1/256 so every machine re-simulates identically.
/// Default fields are omitted on the wire, which keeps 60 Hz replay logs compact.</summary>
public sealed class CommandDto
{
    [JsonPropertyName("mx")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public float Mx { get; set; }
    [JsonPropertyName("my")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public float My { get; set; }
    [JsonPropertyName("sp")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sp { get; set; }
    [JsonPropertyName("pa")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Pa { get; set; }
    [JsonPropertyName("sh")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sh { get; set; }
    [JsonPropertyName("ch")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public float Ch { get; set; }
    [JsonPropertyName("th")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Th { get; set; }
    [JsonPropertyName("ta")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Ta { get; set; }
    [JsonPropertyName("sw")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sw { get; set; }
    [JsonPropertyName("lo")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Lo { get; set; }
    [JsonPropertyName("sl")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sl { get; set; }
    [JsonPropertyName("sd")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sd { get; set; }

    private static float Q(float v) => MathF.Round(Math.Clamp(v, -1f, 1f) * 256f) / 256f;

    public static CommandDto From(PlayerCommand c) => new()
    {
        Mx = Q(c.Move.X), My = Q(c.Move.Y), Sp = c.Sprint, Pa = c.Pass, Sh = c.Shoot,
        Ch = Q(c.Charge), Th = c.Through, Ta = c.Tackle, Sw = c.Switch, Lo = c.Lob,
        Sl = c.Slide, Sd = c.Shield || c.Dribble,
    };

    public PlayerCommand To() => new()
    {
        Move = new Vector2(Mx, My), Sprint = Sp, Pass = Pa, Shoot = Sh, Charge = Ch,
        Through = Th, Tackle = Ta, Switch = Sw, Lob = Lo, Slide = Sl,
        Shield = Sd, Dribble = Sd,
    };
}

/// <summary>Lightweight per-player snapshot. x/z in metres, y is always 0 for players.</summary>
public sealed class PlayerDto
{
    [JsonPropertyName("x")] public float X { get; set; }
    [JsonPropertyName("z")] public float Z { get; set; }
    [JsonPropertyName("vx")] public float Vx { get; set; }
    [JsonPropertyName("vz")] public float Vz { get; set; }
    [JsonPropertyName("fx")] public float Fx { get; set; }
    [JsonPropertyName("fz")] public float Fz { get; set; }
    [JsonPropertyName("a")] public string A { get; set; } = "idle";

    public static PlayerDto From(PlayerState p) => new()
    {
        X = p.Pos.X, Z = p.Pos.Z, Vx = p.Vel.X, Vz = p.Vel.Z,
        Fx = p.Facing.X, Fz = p.Facing.Z, A = p.Action,
    };
}

public sealed class BallDto
{
    [JsonPropertyName("x")] public float X { get; set; }
    [JsonPropertyName("y")] public float Y { get; set; }
    [JsonPropertyName("z")] public float Z { get; set; }
    [JsonPropertyName("vx")] public float Vx { get; set; }
    [JsonPropertyName("vy")] public float Vy { get; set; }
    [JsonPropertyName("vz")] public float Vz { get; set; }
    [JsonPropertyName("owner")] public int Owner { get; set; } = -1;

    public static BallDto From(BallState b) => new()
    {
        X = b.Pos.X, Y = b.Pos.Y, Z = b.Pos.Z,
        Vx = b.Vel.X, Vy = b.Vel.Y, Vz = b.Vel.Z, Owner = b.Owner,
    };
}

/// <summary>One authoritative tick of inputs, carried in snapshots for rollback.</summary>
public sealed class InputFrameDto
{
    [JsonPropertyName("t")] public int T { get; set; }
    [JsonPropertyName("c")] public Dictionary<int, CommandDto> C { get; set; } = new();
}

/// <summary>Full-fidelity player state for resume / peer-host handoff / checkpoints.</summary>
public sealed class FullPlayerDto
{
    [JsonPropertyName("x")] public float X { get; set; }
    [JsonPropertyName("z")] public float Z { get; set; }
    [JsonPropertyName("vx")] public float Vx { get; set; }
    [JsonPropertyName("vz")] public float Vz { get; set; }
    [JsonPropertyName("fx")] public float Fx { get; set; }
    [JsonPropertyName("fz")] public float Fz { get; set; }
    [JsonPropertyName("hx")] public float Hx { get; set; }
    [JsonPropertyName("hz")] public float Hz { get; set; }
    [JsonPropertyName("tx")] public float Tx { get; set; }
    [JsonPropertyName("tz")] public float Tz { get; set; }
    [JsonPropertyName("st")] public float St { get; set; }
    [JsonPropertyName("ap")] public float Ap { get; set; }
    [JsonPropertyName("at")] public float At { get; set; }
    [JsonPropertyName("dt")] public float Dt { get; set; }
    [JsonPropertyName("pl")] public float Pl { get; set; }
    [JsonPropertyName("tl")] public float Tl { get; set; }
    [JsonPropertyName("a")] public string A { get; set; } = "idle";
    [JsonPropertyName("ik")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Ik { get; set; }
    [JsonPropertyName("c")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public int C { get; set; }
    [JsonPropertyName("pr")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Pr { get; set; }
    [JsonPropertyName("sh")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Sh { get; set; }
    [JsonPropertyName("team")] public int Team { get; set; }
    [JsonPropertyName("slot")] public int Slot { get; set; }
    [JsonPropertyName("role")] public int Role { get; set; }

    public static FullPlayerDto From(PlayerState p) => new()
    {
        X = p.Pos.X, Z = p.Pos.Z, Vx = p.Vel.X, Vz = p.Vel.Z,
        Fx = p.Facing.X, Fz = p.Facing.Z, Hx = p.Home.X, Hz = p.Home.Z,
        Tx = p.Target.X, Tz = p.Target.Z, St = p.Stamina, Ap = p.AnimPhase,
        At = p.ActionTimer, Dt = p.DecisionTimer, Pl = p.PossessionLock, Tl = p.TackleLock,
        A = p.Action, Ik = p.IsKeeper, C = p.Cards, Pr = p.Pressing, Sh = p.Shielding,
        Team = p.Team, Slot = p.Slot, Role = (int)p.Role,
    };
}

public sealed class FullBallDto
{
    [JsonPropertyName("x")] public float X { get; set; }
    [JsonPropertyName("y")] public float Y { get; set; }
    [JsonPropertyName("z")] public float Z { get; set; }
    [JsonPropertyName("vx")] public float Vx { get; set; }
    [JsonPropertyName("vy")] public float Vy { get; set; }
    [JsonPropertyName("vz")] public float Vz { get; set; }
    [JsonPropertyName("sx")] public float Sx { get; set; }
    [JsonPropertyName("sy")] public float Sy { get; set; }
    [JsonPropertyName("sz")] public float Sz { get; set; }
    [JsonPropertyName("o")] public int O { get; set; } = -1;
    [JsonPropertyName("lt")] public int Lt { get; set; } = -1;
    [JsonPropertyName("lts")] public int Lts { get; set; } = -1;
    [JsonPropertyName("pf")] public int Pf { get; set; } = -1;
    [JsonPropertyName("pr")] public int Pr { get; set; } = -1;
    [JsonPropertyName("lx")] public float Lx { get; set; }
    [JsonPropertyName("ly")] public float Ly { get; set; }
    [JsonPropertyName("lz")] public float Lz { get; set; }
    [JsonPropertyName("px")] public float Px { get; set; }
    [JsonPropertyName("pz")] public float Pz { get; set; }
    [JsonPropertyName("ft")] public float Ft { get; set; }
    [JsonPropertyName("np")] public float Np { get; set; }

    public static FullBallDto From(BallState b) => new()
    {
        X = b.Pos.X, Y = b.Pos.Y, Z = b.Pos.Z,
        Vx = b.Vel.X, Vy = b.Vel.Y, Vz = b.Vel.Z,
        Sx = b.Spin.X, Sy = b.Spin.Y, Sz = b.Spin.Z,
        O = b.Owner, Lt = b.LastTouch, Lts = b.LastTouchSide, Pf = b.PassFrom, Pr = b.PassReceiver,
        Lx = b.LastTouchPos.X, Ly = b.LastTouchPos.Y, Lz = b.LastTouchPos.Z,
        Px = b.PassTarget.X, Pz = b.PassTarget.Z, Ft = b.FreeTime, Np = b.NoPickup,
    };
}

/// <summary>Complete, deterministic engine checkpoint (resume / peer host / rollback).</summary>
public sealed class FullStateDto
{
    [JsonPropertyName("tick")] public int Tick { get; set; }
    [JsonPropertyName("rng")] public uint Rng { get; set; }
    [JsonPropertyName("gt")] public float Gt { get; set; }
    [JsonPropertyName("acc")] public float Acc { get; set; }
    [JsonPropertyName("phase")] public int Phase { get; set; }
    [JsonPropertyName("pt")] public float Pt { get; set; }
    [JsonPropertyName("clock")] public float Clock { get; set; }
    [JsonPropertyName("half")] public int Half { get; set; }
    [JsonPropertyName("score")] public int[] Score { get; set; } = new int[2];
    [JsonPropertyName("shots")] public int[] Shots { get; set; } = new int[2];
    [JsonPropertyName("sot")] public int[] Sot { get; set; } = new int[2];
    [JsonPropertyName("passes")] public int[] Passes { get; set; } = new int[2];
    [JsonPropertyName("fouls")] public int[] Fouls { get; set; } = new int[2];
    [JsonPropertyName("corners")] public int[] Corners { get; set; } = new int[2];
    [JsonPropertyName("poss")] public float[] Poss { get; set; } = new float[2];
    [JsonPropertyName("players")] public FullPlayerDto[] Players { get; set; } = Array.Empty<FullPlayerDto>();
    [JsonPropertyName("ball")] public FullBallDto Ball { get; set; } = new();
    [JsonPropertyName("ctrl")] public int Ctrl { get; set; } = -1;
    [JsonPropertyName("ctrla")] public int CtrlA { get; set; } = -1;
    [JsonPropertyName("ks")] public int Ks { get; set; }
    [JsonPropertyName("rs")] public int Rs { get; set; }
    [JsonPropertyName("as")] public int As { get; set; }
    [JsonPropertyName("rx")] public float Rx { get; set; }
    [JsonPropertyName("rz")] public float Rz { get; set; }
    [JsonPropertyName("cl")] public float Cl { get; set; }
    [JsonPropertyName("com")] public string Com { get; set; } = "";
    [JsonPropertyName("gs")] public int Gs { get; set; } = -1;
    [JsonPropertyName("ev")] public string[] Ev { get; set; } = Array.Empty<string>();
    [JsonPropertyName("seed")] public int Seed { get; set; }
    [JsonPropertyName("size")] public int Size { get; set; }
    [JsonPropertyName("away")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool Away { get; set; }
}

/// <summary>Every protocol v2 message. Null fields are omitted on the wire.</summary>
public sealed class Packet
{
    [JsonPropertyName("t")] public string T { get; set; } = "";
    [JsonPropertyName("seq")] [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public int Seq { get; set; }
    [JsonPropertyName("room")] public string? Room { get; set; }
    [JsonPropertyName("name")] public string? Name { get; set; }
    [JsonPropertyName("ver")] public int? Ver { get; set; }
    [JsonPropertyName("caps")] public int? Caps { get; set; }
    [JsonPropertyName("create")] public bool? Create { get; set; }
    [JsonPropertyName("ready")] public bool? Ready { get; set; }
    [JsonPropertyName("token")] public string? Token { get; set; }
    [JsonPropertyName("slot")] public int? Slot { get; set; }
    [JsonPropertyName("team")] public int? Team { get; set; }
    [JsonPropertyName("kickSlot")] public int? KickSlot { get; set; }
    [JsonPropertyName("ms")] public int? Ms { get; set; }
    [JsonPropertyName("m")] public string? M { get; set; }
    [JsonPropertyName("cmd")] public CommandDto? Cmd { get; set; }
    [JsonPropertyName("reason")] public string? Reason { get; set; }
    [JsonPropertyName("com")] public string? Com { get; set; }
    [JsonPropertyName("mode")] public string? Mode { get; set; }
    [JsonPropertyName("error")] public string? ErrorText { get; set; }

    [JsonPropertyName("host")] public int? Host { get; set; }
    [JsonPropertyName("authority")] public int? Authority { get; set; }
    [JsonPropertyName("grace")] public int? Grace { get; set; }
    [JsonPropertyName("max")] public int? Max { get; set; }
    [JsonPropertyName("size")] public int? Size { get; set; }
    [JsonPropertyName("seed")] public int? Seed { get; set; }
    [JsonPropertyName("started")] public bool? Started { get; set; }
    [JsonPropertyName("tick")] public int? Tick { get; set; }
    [JsonPropertyName("half")] public int? Half { get; set; }
    [JsonPropertyName("halfMinutes")] public float? HalfMinutes { get; set; }
    [JsonPropertyName("timeSpeed")] public float? TimeSpeed { get; set; }
    [JsonPropertyName("difficulty")] public int? Difficulty { get; set; }
    [JsonPropertyName("homeClub")] public int? HomeClub { get; set; }
    [JsonPropertyName("awayClub")] public int? AwayClub { get; set; }
    [JsonPropertyName("homeFormation")] public string? HomeFormation { get; set; }
    [JsonPropertyName("awayFormation")] public string? AwayFormation { get; set; }
    [JsonPropertyName("cameraMode")] public int? CameraMode { get; set; }
    [JsonPropertyName("cameraZoom")] public float? CameraZoom { get; set; }
    [JsonPropertyName("awayHuman")] public bool? AwayHuman { get; set; }

    [JsonPropertyName("names")] public string[]? Names { get; set; }
    [JsonPropertyName("slots")] public int[]? Slots { get; set; }
    [JsonPropertyName("teams")] public int[]? Teams { get; set; }
    [JsonPropertyName("pings")] public int[]? Pings { get; set; }
    [JsonPropertyName("readys")] public bool[]? Readys { get; set; }
    [JsonPropertyName("onlines")] public bool[]? Onlines { get; set; }
    [JsonPropertyName("ctrls")] public int[]? Ctrls { get; set; }

    [JsonPropertyName("players")] public PlayerDto[]? Players { get; set; }
    [JsonPropertyName("ball")] public BallDto? Ball { get; set; }
    [JsonPropertyName("score")] public int[]? Score { get; set; }
    [JsonPropertyName("clock")] public float? Clock { get; set; }
    [JsonPropertyName("phase")] public int? Phase { get; set; }
    [JsonPropertyName("ev")] public string[]? Ev { get; set; }
    [JsonPropertyName("rng")] public uint? Rng { get; set; }
    [JsonPropertyName("gt")] public float? Gt { get; set; }
    [JsonPropertyName("inputs")] public InputFrameDto[]? Inputs { get; set; }
    [JsonPropertyName("full")] public FullStateDto? Full { get; set; }
}
