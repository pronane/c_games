// Arena FC benchmarks: performance and gameplay, for comparing a change with its base.
//
//   dotnet run -c Release --project Tests/Benchmarks -- perf     --out perf.json     [--reps 7]
//   dotnet run -c Release --project Tests/Benchmarks -- gameplay --out gameplay.json [--matches 8]
//
// perf      CPU time of the match simulation (11v11, 3 seeds x 3,600 ticks) and of motion
//           matching (MotionDriver.UpdatePlayer for all 22 players every tick), median of
//           --reps runs after a warm-up run.  CPU time, not wall time, so other load on the
//           machine matters less; CI still runs base and head alternately on one runner.
// gameplay  --matches full 90-minute AI-vs-AI matches.  The simulation is deterministic, so these
//           numbers only change when the game changes: goals, shots, xG, passes, tackles, fouls,
//           possession, restarts, and motion-matching quality (clips used, transitions,
//           contact timing) per match.
//
// Tools/compare_benchmarks.py compares two runs against Tools/benchmark_targets.json.
using System.Diagnostics;
using System.Text.Json;
using ArenaFC.Core;
using ArenaFC.GodotGame;

static string Arg(string[] a, string name, string def)
{
    int i = Array.IndexOf(a, name);
    return i >= 0 && i + 1 < a.Length ? a[i + 1] : def;
}

static string RepoFile(string rel)
{
    // run from anywhere inside arena-fc
    var dir = AppContext.BaseDirectory;
    for (int up = 0; up < 8 && dir != null; up++, dir = Path.GetDirectoryName(dir))
        if (File.Exists(Path.Combine(dir, rel))) return Path.Combine(dir, rel);
    var cwd = Directory.GetCurrentDirectory();
    for (int up = 0; up < 8 && cwd != null; up++, cwd = Path.GetDirectoryName(cwd))
        if (File.Exists(Path.Combine(cwd, rel))) return Path.Combine(cwd, rel);
    throw new FileNotFoundException(rel);
}

static MotionDriver? LoadMotion(int players)
{
    try
    {
        var d = new MotionDriver();
        d.EnsureCapacity(players);
        if (!d.LoadManifest(File.ReadAllText(RepoFile("Data/clips/clip_manifest.json")))) return null;
        string features = RepoFile("Data/clips/motion_features.json");
        string man = "";
        try { man = File.ReadAllText(RepoFile("Data/soccer_player_manifest.json")); } catch (FileNotFoundException) { }
        d.LoadFeatures(File.ReadAllText(features), man);
        return d;
    }
    catch (Exception ex) { Console.Error.WriteLine($"motion matching unavailable: {ex.Message}"); return null; }
}

static void DriveMotion(MotionDriver d, MatchEngine e)
{
    var s = e.State;
    for (int i = 0; i < s.Players.Length; i++)
    {
        e.LastActionContracts.TryGetValue(i, out var contract);
        d.UpdatePlayer(i, s.Players[i], s.Ball, s.Ball.Owner == i, e.CurrentTick, contract);
    }
}

static double Median(List<double> v) { var a = v.OrderBy(x => x).ToList(); return a.Count == 0 ? 0 : a[a.Count / 2]; }

var argv = args;
string mode = argv.Length > 0 ? argv[0] : "perf";
string outPath = Arg(argv, "--out", mode + ".json");
var proc = Process.GetCurrentProcess();
double Cpu() { proc.Refresh(); return proc.TotalProcessorTime.TotalSeconds; }
var result = new Dictionary<string, object>();

if (mode == "perf")
{
    int reps = int.Parse(Arg(argv, "--reps", "7"));
    var simUs = new List<double>();
    var motionUs = new List<double>();
    for (int rep = 0; rep <= reps; rep++)
    {
        long ticks = 0;
        double c0 = Cpu();
        foreach (int seed in new[] { 91000, 91001, 91002 })
        {
            var e = new MatchEngine(new MatchOptions { TeamSize = 11, Seed = seed, TimeSpeed = 15f });
            for (int t = 0; t < 3600; t++) { e.State.Controlled = -1; e.Step(MatchEngine.Dt, PlayerCommand.None); ticks++; }
        }
        double sim = (Cpu() - c0) / ticks * 1e6;

        // Motion matching: replay one simulated stretch, timing only the per-player updates.
        var m = new MatchEngine(new MatchOptions { TeamSize = 11, Seed = 91003, TimeSpeed = 15f });
        var driver = LoadMotion(m.State.Players.Length);
        double motionCpu = 0; long updates = 0;
        if (driver != null)
            for (int t = 0; t < 900; t++)
            {
                m.State.Controlled = -1;
                m.Step(MatchEngine.Dt, PlayerCommand.None);
                double c1 = Cpu();
                DriveMotion(driver, m);
                motionCpu += Cpu() - c1;
                updates++;
            }
        if (rep == 0) continue;   // warm-up (JIT, tiering)
        simUs.Add(sim);
        if (updates > 0) motionUs.Add(motionCpu / updates * 1e6);
    }
    result["sim_us_per_tick"] = Math.Round(Median(simUs), 3);
    result["sim_us_per_tick_runs"] = simUs.Select(x => Math.Round(x, 3)).ToArray();
    result["motion_us_per_frame_22_players"] = Math.Round(Median(motionUs), 2);
    result["motion_us_per_frame_runs"] = motionUs.Select(x => Math.Round(x, 2)).ToArray();
    result["machine"] = $"{Environment.ProcessorCount} cpus, {System.Runtime.InteropServices.RuntimeInformation.OSDescription}";
}
else if (mode == "gameplay")
{
    int matches = int.Parse(Arg(argv, "--matches", "8"));
    var per = new List<Dictionary<string, double>>();
    foreach (int seed in Enumerable.Range(4100, matches))
    {
        var e = new MatchEngine(new MatchOptions { TeamSize = 11, Seed = seed, HalfMinutes = 45 });
        var s = e.State;
        // Motion matching is driven for the first 15 game minutes of the first match only: it
        // costs ~5 ms per frame for 22 players, and the simulation numbers don't depend on it.
        var driver = seed == 4100 ? LoadMotion(s.Players.Length) : null;
        var kinds = new Dictionary<EventKind, int>();
        MatchEvent? seen = null;
        int ticks = 0, restarts = 0; Phase prev = s.Phase;
        while (s.Phase != Phase.FullTime && ticks < 60 * 60 * 30)
        {
            s.Controlled = -1;
            e.Step(MatchEngine.Dt, PlayerCommand.None);
            ticks++;
            // count every new event (the engine keeps only the last 250)
            for (int k = e.Events.Count - 1; k >= 0 && !ReferenceEquals(e.Events[k], seen); k--)
                kinds[e.Events[k].Kind] = kinds.GetValueOrDefault(e.Events[k].Kind) + 1;
            if (e.Events.Count > 0) seen = e.Events[^1];
            bool wasSet = prev is Phase.FreeKick or Phase.ThrowIn or Phase.Corner or Phase.GoalKick or Phase.Penalty;
            if (wasSet && s.Phase == Phase.Play) restarts++;
            prev = s.Phase;
            if (driver != null && ticks % 2 == 0 && ticks < 3600) DriveMotion(driver, e);   // the game draws at 30-60 fps
        }
        float poss = s.PossessionTime[0] + s.PossessionTime[1];
        var mm = driver?.Metrics;
        per.Add(new Dictionary<string, double>
        {
            ["goals"] = s.Score[0] + s.Score[1],
            ["shots"] = s.Shots[0] + s.Shots[1],
            ["shots_on_target"] = s.ShotsOnTarget[0] + s.ShotsOnTarget[1],
            ["xg"] = s.Xg[0] + s.Xg[1],
            ["passes"] = s.Passes[0] + s.Passes[1],
            ["tackles"] = kinds.GetValueOrDefault(EventKind.Tackle),
            ["fouls"] = s.Fouls[0] + s.Fouls[1],
            ["cards"] = s.YellowCards[0] + s.YellowCards[1] + s.RedCards[0] + s.RedCards[1],
            ["corners"] = s.Corners[0] + s.Corners[1],
            ["offsides"] = kinds.GetValueOrDefault(EventKind.Offside),
            ["restarts"] = restarts,
            ["possession_home_pct"] = poss > 0 ? 100.0 * s.PossessionTime[0] / poss : 50,
            ["finished"] = s.Phase == Phase.FullTime ? 1 : 0,
        });
        if (mm != null)
            result["motion_first_15_min"] = new Dictionary<string, double>
            {
                ["transitions"] = mm.TransitionEvents,
                ["contact_events"] = mm.ContactEvents,
                ["contact_frame_error"] = Math.Round(mm.AvgContactFrameError, 4),
                ["avg_transition_discontinuity"] = Math.Round(mm.AvgTransitionDiscontinuity, 4),
            };
    }
    var keys = per[0].Keys.ToList();
    result["matches"] = matches;
    result["per_match_mean"] = keys.ToDictionary(k => k, k => Math.Round(per.Average(m => m[k]), 3));
    result["per_match_min"] = keys.ToDictionary(k => k, k => Math.Round(per.Min(m => m[k]), 3));
    result["per_match_max"] = keys.ToDictionary(k => k, k => Math.Round(per.Max(m => m[k]), 3));
}
else
{
    Console.Error.WriteLine("usage: Bench (perf|gameplay) --out FILE");
    return 2;
}
File.WriteAllText(outPath, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(File.ReadAllText(outPath));
return 0;
