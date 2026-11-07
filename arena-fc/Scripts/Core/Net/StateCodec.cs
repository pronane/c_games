// Arena FC - full-fidelity state codec for `resume` / peer-host handoff.
// The compact 20 Hz `snap` message only carries what a renderer needs; this one
// carries every deterministic engine word so a fresh process can continue the
// very same match tick-for-tick.
using System;
using System.Linq;
using System.Text.Json;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public static class StateCodec
{
    public static FullStateDto BuildFull(MatchEngine e, int tick)
    {
        var s = e.State;
        var t = e.Timing;
        return new FullStateDto
        {
            Tick = tick,
            Rng = t.Rng,
            Gt = t.Gt,
            Acc = t.Acc,
            Phase = (int)s.Phase,
            Pt = s.PhaseTimer,
            Clock = s.Clock,
            Half = s.Half,
            Score = (int[])s.Score.Clone(),
            Shots = (int[])s.Shots.Clone(),
            Sot = (int[])s.ShotsOnTarget.Clone(),
            Passes = (int[])s.Passes.Clone(),
            Fouls = (int[])s.Fouls.Clone(),
            Corners = (int[])s.Corners.Clone(),
            Poss = (float[])s.PossessionTime.Clone(),
            Players = s.Players.Select(FullPlayerDto.From).ToArray(),
            Ball = FullBallDto.From(s.Ball),
            Ctrl = s.Controlled,
            CtrlA = s.ControlledAway,
            Ks = s.KickoffSide,
            Rs = s.RestartSide,
            As = s.AttackSign,
            Rx = s.RestartPos.X,
            Rz = s.RestartPos.Z,
            Cl = s.ControlLock,
            Com = s.Commentary,
            Gs = s.GoalScorer,
            Ev = e.Events.TakeLast(20).Select(x => x.Text).ToArray(),
            Seed = e.Options.Seed,
            Size = e.Options.TeamSize,
            Away = e.Options.AwayHuman,
        };
    }

    public static void ApplyFull(MatchEngine e, FullStateDto f) => e.ApplyFull(f);

    public static string EncodeFull(FullStateDto f) => JsonSerializer.Serialize(f, NetProtocol.Json);

    public static FullStateDto? DecodeFull(string json)
    {
        try { return JsonSerializer.Deserialize<FullStateDto>(json, NetProtocol.Json); }
        catch (JsonException) { return null; }
    }

    /// <summary>8-char hex state hash, handy for logs and hash reports.</summary>
    public static string Hash(MatchState s) => NetProtocol.Hash(s).ToString("X8");

    public static string Hash(FullStateDto f) => f.Rng.ToString("X8");

    /// <summary>Hash the state part of a lightweight snapshot packet (server diagnostics).</summary>
    public static uint HashPacket(Packet p)
    {
        uint h = 2166136261u;
        void Mix(float v)
        {
            h ^= unchecked((uint)(int)MathF.Round(v * 1000f));
            h *= 16777619u;
        }
        if (p.Players != null)
            foreach (var d in p.Players) { Mix(d.X); Mix(d.Z); }
        if (p.Ball != null) { Mix(p.Ball.X); Mix(p.Ball.Y); Mix(p.Ball.Z); }
        if (p.Score != null && p.Score.Length >= 2)
        {
            h ^= (uint)(p.Score[0] * 7 + p.Score[1]);
            h *= 16777619u;
        }
        return h;
    }
}
