// Arena FC - 20 Hz authoritative snapshot build + client-side application.
// The browser edition reads the same keys in BrowserBoot.net_apply_snapshots.
using System;
using System.Linq;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public static class Snapshot
{
    /// <summary>Build a lightweight snapshot Packet.  All the optional arguments are
    /// used by the .NET server; the core tests use the short overloads.</summary>
    public static Packet Build(MatchEngine e, int tick, int[]? ctrls = null,
                               int[]? pings = null, string[]? names = null,
                               InputFrameDto[]? inputs = null,
                               int authority = NetProtocol.AuthorityServer, int host = 0)
    {
        var s = e.State;
        return new Packet
        {
            T = NetProtocol.Snap,
            Tick = tick,
            Seed = e.Options.Seed,
            Size = e.Options.TeamSize,
            Score = (int[])s.Score.Clone(),
            Clock = s.Clock,
            Phase = (int)s.Phase,
            Half = s.Half,
            Players = s.Players.Select(PlayerDto.From).ToArray(),
            Ball = BallDto.From(s.Ball),
            Ctrls = ctrls ?? new[] { s.Controlled, s.ControlledAway, -1, -1 },
            Pings = pings,
            Names = names,
            Inputs = inputs,
            Authority = authority,
            Host = host,
            // Rollback data: RNG word, global time and trailing authoritative inputs.
            Rng = e.Rng.State,
            Gt = (float)(tick * MatchEngine.Dt),
            Ev = e.Events.TakeLast(6).Select(x => x.Text).ToArray(),
            Com = s.Commentary,
        };
    }

    public static void ApplyImmediate(MatchEngine e, Packet snap) => Apply(e, snap, snap, 0f);

    public static void ApplyInterpolated(MatchEngine e, Packet a, Packet b, float t) => Apply(e, a, b, t);

    private static void Apply(MatchEngine e, Packet a, Packet b, float t)
    {
        var s = e.State;
        float blend = Math.Clamp(t, 0f, 1f);
        if (a.Players != null)
        {
            int n = Math.Min(a.Players.Length, s.Players.Length);
            for (int i = 0; i < n; i++)
            {
                var pa = a.Players[i];
                var pb = b.Players != null && i < b.Players.Length ? b.Players[i] : pa;
                var p = s.Players[i];
                float x = Lerp(pa.X, pb.X, blend), z = Lerp(pa.Z, pb.Z, blend);
                float fx = Lerp(pa.Fx, pb.Fx, blend), fz = Lerp(pa.Fz, pb.Fz, blend);
                p.Pos = new System.Numerics.Vector3(x, 0f, z);
                p.Vel = new System.Numerics.Vector3(Lerp(pa.Vx, pb.Vx, blend), 0f,
                                                    Lerp(pa.Vz, pb.Vz, blend));
                if (fx * fx + fz * fz > 1e-6f) p.Facing = Mx.Norm(new System.Numerics.Vector3(fx, 0f, fz));
                p.Action = pa.A;
            }
        }
        if (a.Ball != null)
        {
            var ba = a.Ball;
            var bb = b.Ball ?? ba;
            s.Ball.Pos = new System.Numerics.Vector3(Lerp(ba.X, bb.X, blend),
                                                      Lerp(ba.Y, bb.Y, blend),
                                                      Lerp(ba.Z, bb.Z, blend));
            s.Ball.Vel = new System.Numerics.Vector3(Lerp(ba.Vx, bb.Vx, blend),
                                                      Lerp(ba.Vy, bb.Vy, blend),
                                                      Lerp(ba.Vz, bb.Vz, blend));
            s.Ball.Owner = ba.Owner;
        }
        if (a.Score != null && a.Score.Length >= 2) s.Score = (int[])a.Score.Clone();
        if (a.Clock.HasValue) s.Clock = a.Clock.Value;
        if (a.Phase.HasValue) s.Phase = (Phase)a.Phase.Value;
        if (a.Half.HasValue) s.Half = a.Half.Value;
        if (a.Ctrls != null)
        {
            if (a.Ctrls.Length > 0) s.Controlled = a.Ctrls[0];
            if (a.Ctrls.Length > 1) s.ControlledAway = a.Ctrls[1];
        }
        if (a.Com != null) s.Commentary = a.Com;
        if (a.Rng.HasValue) e.Rng.State = a.Rng.Value;
        if (a.Gt.HasValue || a.Rng.HasValue || a.Tick.HasValue)
            e.RestoreTiming(a.Rng ?? e.Rng.State, a.Gt ?? (float)(e.CurrentTick * MatchEngine.Dt),
                            a.Tick ?? e.CurrentTick);
    }

    private static float Lerp(float x, float y, float t) => x + (y - x) * t;
}
