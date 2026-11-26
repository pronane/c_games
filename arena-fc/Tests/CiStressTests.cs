// Deterministic multi-seed simulation stress runner for GitHub Actions.
// Usage: dotnet run --project Tests/CiStressTests.csproj -c Release -- --seeds 3 --seconds 30
using System;
using System.Globalization;
using System.Numerics;
using ArenaFC.Core;

static int ReadInt(string[] args, string name, int fallback)
{
    for (var i = 0; i + 1 < args.Length; i++)
        if (args[i] == name && int.TryParse(args[i + 1], NumberStyles.Integer,
                CultureInfo.InvariantCulture, out var value))
            return value;
    return fallback;
}

static bool Finite(Vector3 v) =>
    float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z);

static void ValidateFinite(MatchEngine engine, int teamSize, int seed, int tick)
{
    var state = engine.State;
    if (state.Players.Length != teamSize * 2)
        throw new InvalidOperationException($"seed={seed} team={teamSize} tick={tick}: player count changed");
    if (!Finite(state.Ball.Pos) || !Finite(state.Ball.Vel))
        throw new InvalidOperationException($"seed={seed} team={teamSize} tick={tick}: non-finite ball state");
    if (!float.IsFinite(state.Clock))
        throw new InvalidOperationException($"seed={seed} team={teamSize} tick={tick}: non-finite match clock");

    foreach (var p in state.Players)
    {
        if (!Finite(p.Pos) || !Finite(p.Vel) || !Finite(p.Facing) ||
            !float.IsFinite(p.Stamina) || !float.IsFinite(p.ActionTimer) ||
            !float.IsFinite(p.ActionDuration) || !float.IsFinite(p.ActionContactAt))
            throw new InvalidOperationException(
                $"seed={seed} team={teamSize} tick={tick} player={p.Index}: non-finite player state");
    }
}

static bool SameState(MatchEngine a, MatchEngine b)
{
    var x = a.State;
    var y = b.State;
    if (x.Phase != y.Phase || x.Clock != y.Clock ||
        x.Ball.Owner != y.Ball.Owner || x.Ball.Pos != y.Ball.Pos ||
        x.Ball.Vel != y.Ball.Vel || x.Score[0] != y.Score[0] ||
        x.Score[1] != y.Score[1] || x.Players.Length != y.Players.Length)
        return false;

    for (var i = 0; i < x.Players.Length; i++)
    {
        var p = x.Players[i];
        var q = y.Players[i];
        if (p.Pos != q.Pos || p.Vel != q.Vel || p.Facing != q.Facing ||
            p.Stamina != q.Stamina || p.Action != q.Action ||
            p.ActionTimer != q.ActionTimer || p.ActionContactAt != q.ActionContactAt ||
            p.Sprinting != q.Sprinting || p.Pressing != q.Pressing ||
            p.SentOff != q.SentOff)
            return false;
    }
    return true;
}

var seeds = Math.Clamp(ReadInt(args, "--seeds", 3), 1, 100);
var seconds = Math.Clamp(ReadInt(args, "--seconds", 30), 1, 600);
var totalScenarios = 0;
var totalTicks = 0;
var started = DateTime.UtcNow;

try
{
    foreach (var teamSize in new[] { 5, 7, 11 })
    {
        for (var offset = 0; offset < seeds; offset++)
        {
            var seed = 91000 + offset;
            var first = new MatchEngine(new MatchOptions
            {
                TeamSize = teamSize,
                Seed = seed,
                TimeSpeed = 15f
            });
            var second = new MatchEngine(new MatchOptions
            {
                TeamSize = teamSize,
                Seed = seed,
                TimeSpeed = 15f
            });

            var ticks = seconds * 60;
            for (var tick = 1; tick <= ticks; tick++)
            {
                first.Step(MatchEngine.Dt, PlayerCommand.None);
                second.Step(MatchEngine.Dt, PlayerCommand.None);

                ValidateFinite(first, teamSize, seed, tick);
                ValidateFinite(second, teamSize, seed, tick);

                if (!SameState(first, second))
                    throw new InvalidOperationException(
                        $"same-seed determinism mismatch: team={teamSize} seed={seed} tick={tick}");
            }

            totalScenarios++;
            totalTicks += ticks;
            Console.WriteLine(
                $"PASS team={teamSize} seed={seed} ticks={ticks} score={first.State.Score[0]}-{first.State.Score[1]}");
        }
    }

    var elapsed = DateTime.UtcNow - started;
    var rate = elapsed.TotalSeconds > 0 ? totalTicks / elapsed.TotalSeconds : 0;
    Console.WriteLine(
        $"RESULT: {totalScenarios} scenarios, {totalTicks} ticks per simulation, " +
        $"{totalScenarios * totalTicks * 2} engine-steps compared, {rate:F0} ticks/s per engine, 0 failures");
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine("FAIL: " + ex);
    return 1;
}
