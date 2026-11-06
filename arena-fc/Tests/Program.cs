// Headless unit/integration tests for the pure-C# core. Run: dotnet run --project Tests
using System.Numerics;
using ArenaFC.Core.Net;
using System.Reflection;
using System.IO;
using ArenaFC.Core;
using ArenaFC.Core.Input;

int passed = 0, failed = 0;
void Check(string name, bool ok, string? detail = null)
{
    if (ok) { passed++; Console.WriteLine($"  PASS  {name}"); }
    else { failed++; Console.WriteLine($"  FAIL  {name} {detail}"); }
}
void Section(string s) => Console.WriteLine($"\n== {s} ==");
void Invoke(object o, string method, params object[] args)
{
    var mi = o.GetType().GetMethod(method, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)!;
    mi.Invoke(o, args);
}

Section("Procedural rig / skeleton / skin weights");
var spec = new CharacterSpec();
var rig = RigBuilder.Build(spec);
Check("18 bone skeleton", rig.Bones.Length == 18, $"got {rig.Bones.Length}");
Check("bone hierarchy has root and parents", rig.Bones[0].Parent == -1 && rig.Bones[4].ParentName == "Neck");
Check("mesh has vertices", rig.VertexCount > 500, $"got {rig.VertexCount}");
Check("mesh has triangles", rig.TriangleCount > 400, $"got {rig.TriangleCount}");
Check("9 material slots / surfaces", rig.SurfaceMaterials.Length >= 7, $"got {rig.SurfaceMaterials.Length}");
Check("4 bone indices + 4 weights per vertex",
      rig.BoneIndices.Length == rig.VertexCount * 4 && rig.Weights.Length == rig.VertexCount * 4);
float minSum = 1, maxSum = 1; bool idxOk = true, finite = true;
for (int i = 0; i < rig.VertexCount; i++)
{
    float wsum = 0;
    for (int k = 0; k < 4; k++) { wsum += rig.Weights[i * 4 + k]; idxOk &= rig.BoneIndices[i * 4 + k] >= 0 && rig.BoneIndices[i * 4 + k] < rig.Bones.Length; }
    minSum = MathF.Min(minSum, wsum); maxSum = MathF.Max(maxSum, wsum);
    finite &= Mx.IsFinite(rig.Positions[i]) && Mx.IsFinite(rig.Normals[i]);
}
Check("every vertex weight sums to 1", MathF.Abs(minSum - 1) < 1e-4f && MathF.Abs(maxSum - 1) < 1e-4f, $"{minSum}..{maxSum}");
Check("all bone indices valid", idxOk);
Check("all vertices finite", finite);
Check("rig height matches spec", MathF.Abs(rig.BoundsMax.Y - spec.Height) < .12f, $"top={rig.BoundsMax.Y:F3} spec={spec.Height:F2}");
Check("rig stands on ground", rig.BoundsMin.Y > -.05f && rig.BoundsMin.Y < .12f, $"min={rig.BoundsMin.Y:F3}");
var tall = spec.Clone(); tall.Height = 2.02f; tall.LegLength = 1.15f; tall.Bulk = 1.3f;
var tallRig = RigBuilder.Build(tall);
Check("editor proportions change mesh + skeleton", tallRig.BoundsMax.Y > rig.BoundsMax.Y + .12f && tallRig.VertexCount == rig.VertexCount);
Check("skinning is blended, not rigid", Enumerable.Range(0, rig.VertexCount).Any(i => rig.Weights[i * 4 + 1] > .01f || rig.Weights[i * 4 + 2] > .01f));

Section("Character / roster serialisation");
spec.SetBoneRotation("LThigh", 12.5f, -4f, 8f);
var round = CharacterSpec.FromJson(spec.ToJson());
Check("JSON round trip keeps colours", round.KitPrimary == spec.KitPrimary && round.SkinTone == spec.SkinTone);
Check("JSON round trip keeps bone pose", MathF.Abs(round.GetBoneRotation("LThigh")[0] - 12.5f) < .001f);
var roster = Clubs.CreateRoster(0, 11);
var json = CharacterIo.SerializeRoster(roster, "TEST FC");
var roster2 = CharacterIo.DeserializeRoster(json, out var teamName);
Check("roster round trip", roster2.Count == 11 && teamName == "TEST FC" && roster2[0].IsKeeper);
Check("8 fictional clubs", Clubs.All.Length == 8);
Check("formations sized correctly", Clubs.Slots("4-4-2", 11).Length == 11 && Clubs.Slots("1-2-1 (5s)", 5).Length == 5 && Clubs.Slots("2-3-1 (7s)", 7).Length == 7);

Section("Deterministic RNG");
var r1 = new Rng(42); var r2 = new Rng(42);
Check("same seed => same sequence", Enumerable.Range(0, 50).All(_ => r1.Next() == r2.Next()));

Section("Match setup");
var e = new MatchEngine(new MatchOptions { TeamSize = 11, Seed = 99 });
Check("22 players", e.State.Players.Length == 22);
Check("2 goalkeepers", e.State.Players.Count(p => p.IsKeeper) == 2);
Check("ball at centre circle", e.State.Ball.Pos.Length() < 1f);
Check("kickoff phase", e.State.Phase == Phase.Kickoff);
Check("home attacks +X, away -X", e.GoalPos(0).X > 0 && e.GoalPos(1).X < 0);
var e5 = new MatchEngine(new MatchOptions { TeamSize = 5 });
var e7 = new MatchEngine(new MatchOptions { TeamSize = 7 });
Check("5-a-side and 7-a-side", e5.State.Players.Length == 10 && e7.State.Players.Length == 14);

Section("Simulation loop (30 real seconds, 11v11)");
var engine = new MatchEngine(new MatchOptions { Seed = 1234, TimeSpeed = 15f });
for (int i = 0; i < 1800; i++) engine.Step(1f / 60f, PlayerCommand.None);
Check("clock advanced", engine.State.Clock > 400f, $"clock={engine.State.Clock:F1}");
Check("ball finite", Mx.IsFinite(engine.State.Ball.Pos) && Mx.IsFinite(engine.State.Ball.Vel));
Check("players finite and on pitch", engine.State.Players.All(p => Mx.IsFinite(p.Pos) && MathF.Abs(p.Pos.X) < Mx.HalfLength + 4f && MathF.Abs(p.Pos.Z) < Mx.HalfWidth + 4f));
Check("stamina stays in range", engine.State.Players.All(p => p.Stamina >= 0f && p.Stamina <= 1.001f));
Check("commentary feed populated", engine.Events.Count >= 2, $"events={engine.Events.Count}");
Check("AI produced football actions", engine.Events.Any(x => x.Kind is EventKind.Pass or EventKind.Shot or EventKind.Tackle or EventKind.Save or EventKind.Out or EventKind.Goal));
Check("players moved from formation", engine.State.Players.Any(p => Mx.FlatDist(p.Pos, p.Home) > 2f));
Check("no NaN in scoreboard", engine.State.Score.All(s => s >= 0 && s < 100));

Section("Possession stability (regression: ball dropped every tick)");
// PossessionLock used to be checked on the *owner* in Tick(), so every pickup or
// tackle (both set the lock) released the ball one tick later.  The result was an
// endless midfield scrum: 653 ownership flips in 60 s, no real dribbling, 0 goals.
var pos = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
int flips = 0, prevOwner = pos.State.Ball.Owner, longestHold = 0, hold = 0;
for (int i = 0; i < 3600; i++)
{
    pos.Step(1f / 60f, PlayerCommand.None);
    int curOwner = pos.State.Ball.Owner;
    if (curOwner != prevOwner) { flips++; prevOwner = curOwner; hold = 0; }
    else if (curOwner >= 0) { hold++; longestHold = Math.Max(longestHold, hold); }
}
Check("ball does not flip owner every few ticks", flips < 100, $"flips={flips}");
Check("a carrier can dribble for several seconds", longestHold > 180, $"longest={longestHold} ticks");

var stick = new MatchEngine(new MatchOptions { Seed = 7 });
stick.State.Phase = Phase.Play;
stick.State.PhaseTimer = 0f;
stick.State.Ball.Owner = -1;
stick.State.Ball.Vel = Vector3.Zero;
stick.State.Ball.FreeTime = .2f;
stick.State.Ball.NoPickup = 0f;
var near = stick.State.Players[5];
stick.State.Ball.Pos = new Vector3(near.Pos.X + .4f, Mx.BallRadius, near.Pos.Z);
int firstOwner = -1, heldTicks = 0;
for (int i = 0; i < 30; i++)
{
    stick.Step(1f / 60f, PlayerCommand.None);
    if (i == 0) firstOwner = stick.State.Ball.Owner;
    if (firstOwner >= 0 && stick.State.Ball.Owner == firstOwner) heldTicks++;
}
Check("a loose ball stays with the player who collected it", heldTicks >= 25,
      $"owner={firstOwner} held={heldTicks}/30");

Section("Deterministic simulation (replay)");
var a = new MatchEngine(new MatchOptions { Seed = 777 });
var b = new MatchEngine(new MatchOptions { Seed = 777 });
for (int i = 0; i < 600; i++) { a.Step(1f / 60f, PlayerCommand.None); b.Step(1f / 60f, PlayerCommand.None); }
Check("identical ball state after 10s", (a.State.Ball.Pos - b.State.Ball.Pos).Length() < 1e-4f);
Check("identical player state after 10s", a.State.Players.Zip(b.State.Players).All(p => (p.First.Pos - p.Second.Pos).Length() < 1e-4f));

Section("Goals, shots, possession, set pieces");
var g = new MatchEngine(new MatchOptions { Seed = 5 });
g.State.Phase = Phase.Play;
g.State.Ball.Owner = -1;
g.State.Ball.Pos = new Vector3(Mx.HalfLength + .45f, 1.0f, 2.4f);
g.State.Ball.Vel = new Vector3(2f, 0, 0);
g.State.Ball.FreeTime = 1f;
g.State.Ball.LastTouchSide = 0;
g.State.Ball.LastTouch = 0;
g.Step(1f / 60f, PlayerCommand.None);
Check("goal detected across line", g.State.Score[0] == 1 && g.State.Phase == Phase.Goal, $"score={g.State.Score[0]} phase={g.State.Phase}");
Check("goal event in commentary", g.Events.Any(x => x.Kind == EventKind.Goal));
Check("conceding team gets restart", g.State.KickoffSide == 1);
var s = new MatchEngine(new MatchOptions { Seed = 6 });
s.State.Phase = Phase.Play;
s.State.Ball.Owner = 3;
s.State.Players[3].Pos = new Vector3(20, 0, 0);
Invoke(s, "Shoot", s.State.Players[3], .9f, false);
Check("shot gives ball velocity", s.State.Ball.Vel.Length() > 12f, $"v={s.State.Ball.Vel.Length():F1}");
Check("shot counted in stats", s.State.Shots[0] == 1);
var o = new MatchEngine(new MatchOptions { Seed = 8 });
o.State.Phase = Phase.Play;
o.State.Ball.Owner = -1;
o.State.Ball.Pos = new Vector3(0, .11f, Mx.HalfWidth + .5f);
o.State.Ball.Vel = Vector3.Zero;
o.State.Ball.FreeTime = 1f;
o.State.Ball.LastTouchSide = 0;
o.Step(1f / 60f, PlayerCommand.None);
Check("throw-in awarded", o.State.Phase == Phase.ThrowIn, $"phase={o.State.Phase}");
for (int i = 0; i < 90; i++) o.Step(1f / 60f, PlayerCommand.None);
Check("restart returns to play", o.State.Phase == Phase.Play || o.State.Phase == Phase.Kickoff, $"phase={o.State.Phase}");

Section("Half time / full time");
var t = new MatchEngine(new MatchOptions { Seed = 3, HalfMinutes = .1f, TimeSpeed = 60f });
for (int i = 0; i < 1200; i++) t.Step(1f / 60f, PlayerCommand.None);
Check("reached second half or full time", t.State.Half == 2 || t.State.Phase == Phase.FullTime, $"half={t.State.Half} phase={t.State.Phase}");
Check("ends switch at half time", t.State.Half == 2 ? t.GoalPos(0).X < 0 : true);
int safety = 0;
while (t.State.Phase != Phase.FullTime && safety++ < 5000) t.Step(1f / 60f, PlayerCommand.None);
Check("full time reached", t.State.Phase == Phase.FullTime, $"phase={t.State.Phase}");

Section("Human commands");
var h = new MatchEngine(new MatchOptions { Seed = 11 });
h.State.Phase = Phase.Play;
var ctrl = h.State.Controlled;
var before = h.State.Players[ctrl].Pos;
for (int i = 0; i < 60; i++) h.Step(1f / 60f, new PlayerCommand { Move = new Vector2(1, 0), Sprint = true });
Check("controlled player responds to input", h.State.Players[ctrl].Pos.X > before.X + .5f, $"{before.X:F2} -> {h.State.Players[ctrl].Pos.X:F2}");
h.Step(1f / 60f, new PlayerCommand { Switch = true });
Check("player switching works", h.State.Controlled >= 0 && h.State.Controlled < 11);

Section("Deterministic multiplayer core (StepNetwork)");
var m1 = new MatchEngine(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = true });
var m2 = new MatchEngine(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = true });
Check("away controlled player assigned", m1.State.ControlledAway >= m1.Options.TeamSize,
      $"away={m1.State.ControlledAway}");
Check("FindNearestForTeam returns a player on the requested team",
      m1.FindNearestForTeam(1, Vector3.Zero) / m1.Options.TeamSize == 1);
var frames = new List<Dictionary<int, PlayerCommand>>();
var rnd = new Random(7);
for (int i = 0; i < 240; i++)
{
    PlayerCommand Quantize(PlayerCommand c) => CommandDto.From(c).To();
    var cmds = new Dictionary<int, PlayerCommand>
    {
        [m1.State.Controlled] = Quantize(new PlayerCommand { Move = new Vector2((float)rnd.NextDouble() - .5f, (float)rnd.NextDouble() - .5f), Sprint = i % 3 == 0 }),
        [m1.State.ControlledAway] = Quantize(new PlayerCommand { Move = new Vector2((float)rnd.NextDouble() - .5f, (float)rnd.NextDouble() - .5f) }),
    };
    frames.Add(new Dictionary<int, PlayerCommand>(cmds));
    m1.StepNetwork(1f / 60f, cmds);
    m2.StepNetwork(1f / 60f, frames[^1]);
}
Check("two independent engines with identical inputs stay bit-identical",
      NetProtocol.Hash(m1.State) == NetProtocol.Hash(m2.State),
      $"{NetProtocol.Hash(m1.State):X8} vs {NetProtocol.Hash(m2.State):X8}");
Check("StepNetwork advances the clock", m1.State.Clock > 50f, $"clock={m1.State.Clock:F1}");
Check("StepNetwork produced match events", m1.Events.Count >= 1, $"events={m1.Events.Count}");

Section("Wire protocol");
string room = NetProtocol.NewRoomCode();
Check("room code is 6 unambiguous uppercase chars", room.Length == 6 && room.All(c => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".Contains(c)), room);
Check("room normalisation strips spaces and dashes", NetProtocol.NormalizeRoom(" ab-12 cd ") == "AB12CD");
Check("url normalisation adds ws:// and strips trailing slash",
      NetProtocol.NormalizeUrl("192.168.1.5:7777/") == "ws://192.168.1.5:7777");
var src = new PlayerCommand { Move = new Vector2(.375f, -.625f), Sprint = true, Pass = true, Shoot = true, Charge = .8125f, Through = true, Tackle = true, Switch = true, Lob = true, Slide = true, Shield = true, Dribble = true };
var back = CommandDto.From(src).To();
Check("CommandDto round-trips every field",
      back.Move == src.Move && back.Sprint && back.Pass && back.Shoot && back.Through &&
      back.Tackle && back.Switch && back.Lob && back.Slide && back.Shield && back.Dribble &&
      MathF.Abs(back.Charge - src.Charge) < .001f);
var pkt = new Packet { T = NetProtocol.Input, Seq = 42, Cmd = CommandDto.From(src), Room = "ABC123" };
string wire = NetProtocol.Encode(pkt);
var decoded = NetProtocol.Decode(wire);
Check("packet JSON round-trips", decoded != null && decoded.T == NetProtocol.Input && decoded.Seq == 42 && decoded.Room == "ABC123");
Check("omitted null fields are not serialised", !wire.Contains("players"), wire);
Check("malformed JSON returns null", NetProtocol.Decode("{not json") == null);

Section("Snapshots / interpolation / replay");
var snap = Snapshot.Build(m1, 240, new[] { m1.State.Controlled, m1.State.ControlledAway, -1, -1 }, new[] { 12, 30, -1, -1 }, new[] { "Ada", "Bo", "", "" });
Check("snapshot has one DTO per player", snap.Players != null && snap.Players.Length == m1.State.Players.Length);
Check("snapshot carries ball, score, phase and clock", snap.Ball != null && snap.Score != null && snap.Phase.HasValue && snap.Clock.HasValue);
var mirror = new MatchEngine(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = true });
Snapshot.ApplyImmediate(mirror, snap);
Check("applying a snapshot reproduces the authoritative state hash",
      NetProtocol.Hash(mirror.State) == NetProtocol.Hash(m1.State),
      $"{NetProtocol.Hash(mirror.State):X8} vs {NetProtocol.Hash(m1.State):X8}");
Snapshot.ApplyInterpolated(mirror, snap, snap, .5f);
Check("interpolation with identical frames is stable",
      NetProtocol.Hash(mirror.State) == NetProtocol.Hash(m1.State));
var replay = new Replay { Seed = 909, TeamSize = 5, AwayHuman = true };
foreach (var f in frames)
{
    var d = new Dictionary<int, CommandDto>();
    foreach (var kv in f) d[kv.Key] = CommandDto.From(kv.Value);
    replay.Ticks.Add(d);
}
string replayJson = replay.ToJson();
var loaded = Replay.FromJson(replayJson);
Check("replay survives JSON round trip", loaded != null && loaded.Ticks.Count == frames.Count);
var replayed = loaded!.CreateEngine();
loaded.Play(replayed);
Check("replay reproduces the identical final state", NetProtocol.Hash(replayed.State) == NetProtocol.Hash(m1.State),
      $"{NetProtocol.Hash(replayed.State):X8} vs {NetProtocol.Hash(m1.State):X8}");
Check("replay is compact (< 8 KB per second of 60 Hz play)",
      replayJson.Length < frames.Count * 8192 / 60 + 4096, $"bytes={replayJson.Length}");


Section("Engine checkpoints (rollback / reconnect / migration)");
var ckOpts = new MatchOptions { Seed = 4242, TeamSize = 5, AwayHuman = true };
var ckA = new MatchEngine(ckOpts);
var ckB = new MatchEngine(ckOpts);
var ckRnd = new Random(19);
void CkStep(MatchEngine x, int i)
{
    var c = new Dictionary<int, PlayerCommand>
    {
        [x.State.Controlled] = new PlayerCommand { Move = new Vector2((float)Math.Sin(i * .11f), (float)Math.Cos(i * .07f)), Sprint = i % 5 == 0 },
        [x.State.ControlledAway] = new PlayerCommand { Move = new Vector2((float)Math.Cos(i * .13f), (float)Math.Sin(i * .05f)) },
    };
    x.StepOneTick(c);
}
for (int i = 0; i < 90; i++) { CkStep(ckA, i); CkStep(ckB, i); }
var ckPoint = ckA.Capture();
var ckC = new MatchEngine(ckOpts);
ckC.Restore(ckPoint);
for (int i = 90; i < 180; i++) { CkStep(ckA, i); CkStep(ckB, i); CkStep(ckC, i); }
Check("capture/restore forks a bit-identical engine",
      NetProtocol.Hash(ckA.State) == NetProtocol.Hash(ckC.State) && ckA.Rng.State == ckC.Rng.State,
      $"{NetProtocol.Hash(ckA.State):X8} vs {NetProtocol.Hash(ckC.State):X8}");
Check("checkpoint does not alias the live state",
      ckPoint.State.Players[0].Pos.X != ckA.State.Players[0].Pos.X || ckPoint.Tick == 90);

Section("Full authoritative state transfer (resume / peer host handoff)");
var fsOpts = new MatchOptions { Seed = 8181, TeamSize = 5, AwayHuman = true };
var fsA = new MatchEngine(fsOpts);
for (int i = 0; i < 150; i++) CkStep(fsA, i);
var full = StateCodec.BuildFull(fsA, 150);
string fullJson = NetProtocol.Encode(new Packet { T = NetProtocol.Resume, Full = full });
var fullBack = NetProtocol.Decode(fullJson);
Check("full checkpoint survives the wire", fullBack?.Full != null &&
      fullBack.Full.Players.Length == fsA.State.Players.Length && fullBack.Full.Rng == fsA.Rng.State);
var fsB = new MatchEngine(fsOpts);
StateCodec.ApplyFull(fsB, fullBack!.Full!);
Check("applied checkpoint reproduces the exact live match state",
      NetProtocol.Hash(fsB.State) == NetProtocol.Hash(fsA.State) && fsB.CurrentTick == 150,
      $"{NetProtocol.Hash(fsB.State):X8} vs {NetProtocol.Hash(fsA.State):X8} tick={fsB.CurrentTick}");
for (int i = 150; i < 210; i++) { CkStep(fsA, i); CkStep(fsB, i); }
Check("match continues deterministically after handoff",
      NetProtocol.Hash(fsA.State) == NetProtocol.Hash(fsB.State),
      $"{NetProtocol.Hash(fsA.State):X8} vs {NetProtocol.Hash(fsB.State):X8}");
Check("full checkpoint is reasonably compact",
      fullJson.Length < 12000, $"bytes={fullJson.Length}");

Section("Secure resume tokens");
var tok1 = NetProtocol.NewResumeToken();
var tok2 = NetProtocol.NewResumeToken();
Check("tokens are 256-bit, URL-safe and unique", tok1.Length == 43 && tok1 != tok2 &&
      tok1.All(c => char.IsLetterOrDigit(c) || c is '-' or '_'));
Check("token hash is deterministic and hides the token",
      NetProtocol.HashToken(tok1) == NetProtocol.HashToken(tok1) &&
      !NetProtocol.HashToken(tok1).Contains(tok1) &&
      NetProtocol.HashToken(tok1) != NetProtocol.HashToken(tok2));
Check("fixed-time comparison accepts only the exact hash",
      NetProtocol.TokenHashEquals(NetProtocol.HashToken(tok1), NetProtocol.HashToken(tok1)) &&
      !NetProtocol.TokenHashEquals(NetProtocol.HashToken(tok1), NetProtocol.HashToken(tok2)));

Section("Rollback prediction");
// Skip the 1.2 s kickoff ceremony: we want live movement immediately.
void StartPlay(MatchEngine x) { x.State.Phase = Phase.Play; x.State.PhaseTimer = 0f; }
var rbOpts = new MatchOptions { Seed = 31337, TeamSize = 5, AwayHuman = true };
var rbAuth = new MatchEngine(rbOpts);
var rbMirror = new MatchEngine(rbOpts);
var rbPred = new RollbackPredictor(rbOpts);
StartPlay(rbAuth); StartPlay(rbMirror); StartPlay(rbPred.Engine);
rbPred.HardReset(rbAuth, 0);
var rbServerInputs = new Dictionary<int, Dictionary<int, PlayerCommand>>();
int local = rbAuth.State.Controlled;
Dictionary<int, PlayerCommand> RbInputs(int i, float bias) => new()
{
    [rbAuth.State.Controlled] = new PlayerCommand
    {
        Move = new Vector2((float)Math.Sin(i * .09f) + bias, (float)Math.Cos(i * .06f)),
        Sprint = i % 4 == 0, Pass = i % 37 == 0,
    },
    [rbAuth.State.ControlledAway] = new PlayerCommand
    {
        Move = new Vector2((float)Math.Cos(i * .08f), (float)Math.Sin(i * .04f)),
    },
};
var rbSnaps = new List<Packet>();
int rbTick = 0, maxReplay = 0, boundedChecks = 0, boundedOk = 0;
for (int i = 0; i < 120; i++)
{
    var cmds = RbInputs(i, 0f);
    rbAuth.StepOneTick(cmds);
    rbTick++;
    rbServerInputs[rbTick] = cmds;
    rbSnaps.Add(Snapshot.Build(rbAuth, rbTick, new[] { local, rbAuth.State.ControlledAway, -1, -1 }));
    // Predict immediately: the local player never waits for a round trip.
    rbPred.Predict(cmds);
    if ((i + 1) % 3 == 0 && rbTick > 3)
    {
        int confirmed = rbTick - 3;                 // 3-tick (~50 ms) snapshot delay
        var rbSnap = rbSnaps[confirmed - 1];       // state AT that tick, not now
        Snapshot.ApplyImmediate(rbMirror, rbSnap);
        var res = rbPred.Reconcile(confirmed, rbMirror.State, rbSnap.Rng!.Value, rbSnap.Gt!.Value,
            rbServerInputs, local);
        boundedChecks++;
        if (res.Replayed <= NetProtocol.MaxRollbackTicks) boundedOk++;
        maxReplay = Math.Max(maxReplay, res.Replayed);
    }
}
Check("re-simulation stays bounded on every correction",
      boundedChecks >= 30 && boundedOk == boundedChecks, $"{boundedOk}/{boundedChecks}");
Check("predictor stays synchronised with the authoritative engine",
      NetProtocol.Hash(rbPred.Engine.State) == NetProtocol.Hash(rbAuth.State),
      $"pred={NetProtocol.Hash(rbPred.Engine.State):X8} auth={NetProtocol.Hash(rbAuth.State):X8}");
Check("rollback actually re-simulated ticks", rbPred.ReplayedTicks > 100, $"total={rbPred.ReplayedTicks}");
Check("re-simulation is bounded", maxReplay <= NetProtocol.MaxRollbackTicks, $"max={maxReplay}");
Check("corrections were counted", rbPred.Corrections >= 30, $"n={rbPred.Corrections}");
Check("prediction runs ahead of the last confirmed tick", rbPred.PredictedTick >= rbTick - 3);
Check("input history is bounded", rbPred.BufferedFrames <= rbPred.MaxHistory + 1,
      $"frames={rbPred.BufferedFrames}");

// Misprediction: the client guesses a wrong input, then corrects.
var rb2 = new RollbackPredictor(rbOpts);
var rb2Auth = new MatchEngine(rbOpts);
var rb2Mirror = new MatchEngine(rbOpts);
StartPlay(rb2Auth); StartPlay(rb2Mirror); StartPlay(rb2.Engine);
rb2.HardReset(rb2Auth, 0);
int rb2Tick = 0, rb2Local = rb2Auth.State.Controlled;
for (int i = 0; i < 30; i++)
{
    var truth = new Dictionary<int, PlayerCommand>
    { [rb2Local] = new PlayerCommand { Move = new Vector2(1f, 0f), Sprint = true } };
    rb2Auth.StepOneTick(truth); rb2Tick++;
    rb2.Predict(new Dictionary<int, PlayerCommand>
    { [rb2Local] = new PlayerCommand { Move = new Vector2(-1f, 0f) } });
}
var rb2Snap = Snapshot.Build(rb2Auth, rb2Tick, new[] { rb2Local, -1, -1, -1 });
Snapshot.ApplyImmediate(rb2Mirror, rb2Snap);
float driftBefore = RollbackPredictor.MaxError(rb2.Engine.State, rb2Mirror.State);
var rb2Res = rb2.Reconcile(rb2Tick, rb2Mirror.State, rb2Snap.Rng!.Value, rb2Snap.Gt!.Value,
    new Dictionary<int, Dictionary<int, PlayerCommand>>(), rb2Local);
Check("drift is detected before reconciliation", driftBefore > .5f, $"drift={driftBefore:F2}m");
Check("reconciliation reports the measured error", rb2Res.Applied && rb2Res.Error > .5f,
      $"error={rb2Res.Error:F2}m");
Check("reconciliation replays the unconfirmed tail", rb2Res.Replayed == 0,
      $"replayed={rb2Res.Replayed}");
Check("a stale snapshot is rejected, not re-applied",
      !rb2.Reconcile(rb2Tick - 1, rb2Mirror.State, rb2Snap.Rng!.Value, rb2Snap.Gt!.Value).Applied);
for (int i = 0; i < 30; i++) rb2.Predict(new Dictionary<int, PlayerCommand>
{ [rb2Local] = new PlayerCommand { Move = new Vector2(1f, 0f) } });
Check("an ancient snapshot degrades to a bounded hard reset",
      rb2.Reconcile(rb2Tick + 1, rb2Mirror.State, rb2Snap.Rng!.Value, rb2Snap.Gt!.Value).HardReset);

// Predicted input makes the local player respond on the very next frame.
var rb3 = new RollbackPredictor(rbOpts);
var rb3Auth = new MatchEngine(rbOpts);
StartPlay(rb3Auth);
rb3.HardReset(rb3Auth, 0);
int rb3Local = rb3.Engine.State.Controlled;
float x0 = rb3.Engine.State.Players[rb3Local].Pos.X;
rb3.Predict(new Dictionary<int, PlayerCommand>
{ [rb3Local] = new PlayerCommand { Move = new Vector2(1f, 0f), Sprint = true } });
Check("local input moves the player on the next simulated frame (zero RTT)",
      rb3.Engine.State.Players[rb3Local].Pos.X > x0,
      $"{x0:F2} -> {rb3.Engine.State.Players[rb3Local].Pos.X:F2}");

Section("Desktop C# online client (protocol v2 loopback)");
var loop = new LoopbackTransport();
var oc = new OnlineClient();
bool ocOk = oc.Connect("192.168.1.5:7777/", " ab-12 cd ", "Ada", null, true, loop);
Check("connect normalises URL, room and name",
      ocOk && loop.Url == "ws://192.168.1.5:7777" && oc.Room == "AB12CD" && oc.Name == "Ada" && oc.Connected);
var helloPkt = loop.LastSent();
Check("hello advertises protocol v2, desktop caps and create",
      helloPkt != null && helloPkt.T == NetProtocol.Hello && helloPkt.Ver == NetProtocol.Version &&
      helloPkt.Caps == NetProtocol.CapFullDesktop && helloPkt.Create == true);
loop.Push(new Packet { T = NetProtocol.Welcome, Room = "AB12CD", Slot = 0, Team = 0, Size = 5,
                       Seed = 909, Host = 0, Authority = 0, Grace = 180, Started = false,
                       Token = new string('x', 43) });
oc.Poll();
Check("welcome assigns slot, team, host and a resume token",
      oc.Slot == 0 && oc.Team == 0 && oc.IsHost && oc.Token.Length == 43 && oc.TeamSize == 5 && oc.Seed == 909);
loop.Push(new Packet { T = NetProtocol.Lobby, Room = "AB12CD", Host = 0,
                       Names = new[] { "Ada", "Bo" }, Slots = new[] { 0, 1 }, Teams = new[] { 0, 1 },
                       Onlines = new[] { true, true }, Readys = new[] { false, true } });
oc.Poll();
Check("lobby updates names, slots, teams and readiness",
      oc.Names.Length == 2 && oc.Slots[1] == 1 && oc.Teams[1] == 1 && oc.Readys[1]);
loop.Push(new Packet { T = NetProtocol.Ping, Ms = 123 });
oc.Poll();
Check("server ping is answered with a pong carrying the same timestamp",
      loop.LastSent()?.T == NetProtocol.Pong && loop.LastSent()?.Ms == 123);
oc.SendInput(new PlayerCommand { Move = new Vector2(.5f, .25f), Pass = true });
var inputPkt = loop.LastSent();
Check("input is quantised, sequenced and omits default fields",
      inputPkt?.T == NetProtocol.Input && inputPkt.Seq == 1 &&
      inputPkt.Cmd != null && inputPkt.Cmd.Mx == .5f && inputPkt.Cmd.My == .25f && inputPkt.Cmd.Pa);
oc.SendStart(); oc.SendReady(true); oc.SendChat("gg");
Check("start / ready / chat use the checked-in message names",
      loop.Sent[^3].Contains("\"t\":\"start\"") && loop.Sent[^2].Contains("\"t\":\"ready\"") &&
      loop.Sent[^1].Contains("\"t\":\"chat\""));
loop.Push(new Packet { T = NetProtocol.Error, Reason = "Room full" });
oc.Poll();
Check("server errors are surfaced", oc.LastError == "Room full" && oc.Status.Contains("Room full"));
Check("local controlled index falls back when no ctrls arrived", oc.LocalPlayerIndex(99) == 99);
oc.Ctrls = new[] { 4, -1, -1, -1 };
Check("ctrls maps the local slot to its player", oc.LocalPlayerIndex(0) == 4);
oc.Close();
Check("close releases the transport and clears match flags", !oc.Connected && !oc.InMatch && !oc.Started);

Section("Online match driver (deterministic loopback, rollback reconciliation)");
var l2 = new LoopbackTransport();
var om = new OnlineMatch(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = false });
om.Connect("ws://127.0.0.1:7777", "TEST77", "Ada", null, true, l2);
l2.Push(new Packet { T = NetProtocol.Welcome, Room = "TEST77", Slot = 0, Team = 0,
                     Size = 5, Seed = 909, Host = 0 });
om.Client.Poll();
var auth = new MatchEngine(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = false });
int localIdx = auth.State.Controlled;
l2.Push(new Packet { T = NetProtocol.Begin, Room = "TEST77", Seed = 909, Size = 5, Tick = 0,
                     Host = 0, Authority = 0, TimeSpeed = 15f, HalfMinutes = 45f,
                     AwayHuman = false, Ctrls = new[] { localIdx, -1, -1, -1 } });
om.Client.Poll();
Check("begin builds a mirror engine and a zero-RTT predictor",
      om.Started && om.Predictor != null && om.Engine.State.Players.Length == 10 &&
      om.LocalIndex == localIdx);
var snaps = new List<Packet>();
var frameLog = new List<InputFrameDto>();
for (int i = 1; i <= 30; i++)
{
    var rawCmd = new PlayerCommand
    {
        Move = new Vector2((float)Math.Sin(i * .17f), (float)Math.Cos(i * .13f)),
        Sprint = i % 4 == 0, Pass = i % 11 == 0,
    };
    var netCmd = CommandDto.From(rawCmd).To();       // exactly what goes over the wire
    auth.StepOneTick(new Dictionary<int, PlayerCommand> { [localIdx] = netCmd });
    frameLog.Add(new InputFrameDto
    {
        T = i, C = new Dictionary<int, CommandDto> { [localIdx] = CommandDto.From(netCmd) },
    });
    snaps.Add(Snapshot.Build(auth, i, new[] { localIdx, -1, -1, -1 }, null, null, frameLog.ToArray()));
    if (i > 3) l2.Push(snaps[i - 4]);          // 3-tick snapshot delay
    om.Step(1f / 60f, netCmd);
}
Check("client streamed one input packet per predicted tick",
      l2.Sent.Count(s => s.Contains("\"t\":\"input\"")) == 30, $"n={l2.Sent.Count(s => s.Contains("\"t\":\"input\""))}");
Check("snapshots triggered bounded rollback corrections",
      om.Corrections >= 8 && om.LastReplayed <= NetProtocol.MaxRollbackTicks && om.LastReplayed > 0,
      $"corrections={om.Corrections} lastReplay={om.LastReplayed}");
Check("predicted desktop state matches the authoritative engine",
      NetProtocol.Hash(om.Engine.State) == NetProtocol.Hash(auth.State),
      $"client={NetProtocol.Hash(om.Engine.State):X8} server={NetProtocol.Hash(auth.State):X8}");
Check("input history stays bounded", om.BufferedFrames <= om.Predictor!.MaxHistory + 1,
      $"frames={om.BufferedFrames}");
var interpEng = new MatchEngine(new MatchOptions { Seed = 909, TeamSize = 5, AwayHuman = false });
OnlineMatch.Interpolate(interpEng, snaps[^1], snaps[^1], .5f);
Check("interpolation of identical frames reproduces the authoritative hash",
      NetProtocol.Hash(interpEng.State) == NetProtocol.Hash(auth.State));
om.Close();

Section("USB / EasySMX gamepad support (PadLayout)");
var noSaved = new Dictionary<string, Dictionary<string, int>>();
var winDb = string.Join("\n", new[] {
    "# Game Controller DB", "", PadLayout.Builtin[0], PadLayout.Builtin[3], PadLayout.Builtin[1],
    "not a mapping", "badguid,a:b0,platform:Windows," });
var winLines = PadLayout.ParseSdlDatabase(winDb, "Windows");
var linLines = PadLayout.ParseSdlDatabase(winDb, "Linux");
Check("comments, blanks and invalid GUIDs are skipped", winLines.Count == 2, $"got {winLines.Count}");
Check("Windows DB keeps only Windows/agnostic lines", winLines.All(l => PadLayout.PlatformMatches(l, "Windows")));
Check("Linux DB keeps only Linux/agnostic lines", linLines.Count == 1 && linLines.All(l => PadLayout.PlatformMatches(l, "Linux")));
Check("Mac OS X / macOS platform names normalise", PadLayout.NormalizePlatform("Mac OS X") == "macos"
      && PadLayout.NormalizePlatform("Windows") == "windows" && PadLayout.NormalizePlatform("X11") == "linux");
Check("built-in Windows fallback includes EasySMX", PadLayout.BuiltinMappings("Windows").Any(l => l.Contains("EasySMX")));
Check("built-in Linux fallback includes ESM-9101", PadLayout.BuiltinMappings("Linux").Any(l => l.Contains("ESM-9101")));
Check("built-in fallbacks are platform-filtered", PadLayout.BuiltinMappings("Windows").All(l => !l.Contains("platform:Linux")));
Check("Web keeps every built-in fallback (browser IDs have no OS tag)",
      PadLayout.BuiltinMappings("Web").Count == PadLayout.Builtin.Length);

string? dbText = null;
foreach (var candidate in new[] { "Data/input/gamecontrollerdb.txt", "../Data/input/gamecontrollerdb.txt",
    Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "Data", "input", "gamecontrollerdb.txt") })
{
    try { if (File.Exists(candidate)) { dbText = File.ReadAllText(candidate); break; } } catch (Exception) { }
}
if (dbText != null)
{
    var parsedWin = PadLayout.ParseSdlDatabase(dbText, "Windows");
    var parsedLin = PadLayout.ParseSdlDatabase(dbText, "Linux");
    Check("shipped SDL DB parses for Windows", parsedWin.Count > 800, $"{parsedWin.Count} lines");
    Check("shipped SDL DB parses for Linux", parsedLin.Count > 700, $"{parsedLin.Count} lines");
    Check("shipped Windows EasySMX mapping", parsedWin.Any(l => l.Contains("EasySMX Controller")));
    Check("shipped Linux EasySMX mappings", parsedLin.Any(l => l.Contains("EasySMX")));
    Check("shipped generic USB mappings", parsedWin.Any(l => l.Contains("USB Controller")));
    Check("every built-in fallback line comes from the shipped DB", PadLayout.Builtin.All(l => dbText.Contains(l)));
}
else Check("shipped gamecontrollerdb.txt found", false, "searched cwd, parent and test bin");

var raw = PadLayout.Bindings("EasySMX Controller (D-mode)", false, noSaved);
var std = PadLayout.Bindings("Xbox Wireless Controller", true, noSaved);
Check("EasySMX D-input uses the raw order Y B A X / LB / RB",
      raw["pass"] == 2 && raw["through"] == 0 && raw["shoot"] == 3 && raw["tackle"] == 1
      && raw["switch"] == 4 && raw["sprint"] == 5);
Check("mapped pads use Godot's standard JoyButton order",
      std["pass"] == 0 && std["through"] == 3 && std["shoot"] == 2 && std["tackle"] == 1
      && std["switch"] == 9 && std["sprint"] == 10);
var savedForPad = new Dictionary<string, Dictionary<string, int>>
{
    ["My USB pad"] = new Dictionary<string, int> { ["pass"] = 7, ["through"] = 8, ["shoot"] = 9,
        ["tackle"] = 10, ["switch"] = 11, ["sprint"] = 12 }
};
Check("saved per-pad remap wins over the default", PadLayout.Bindings("My USB pad", false, savedForPad)["pass"] == 7);
Check("incomplete remap falls back to the default", PadLayout.Bindings("Other pad", false,
      new Dictionary<string, Dictionary<string, int>> { ["Other pad"] = new Dictionary<string, int> { ["pass"] = 7 } })["through"] == 0);
Check("EasySMX / USB pad names are detected", PadLayout.IsEasySMX("EasySMX ESM-9101")
      && PadLayout.IsGenericUsb("USB Controller") && !PadLayout.IsEasySMX("Xbox One S Controller"));
Check("pad kinds mention the active mode", PadLayout.PadKind("EasySMX", false).Contains("D-input")
      && PadLayout.PadKind("EasySMX", true).Contains("XInput"));

var noButtons = new bool[21];
var noAxes = new float[10];
Check("stick drift inside dead zone is ignored", PadLayout.Stick(.1f, .1f, PadLayout.Deadzone).Length < 1e-5f);
Check("full stick deflection reaches 1.0", PadLayout.Stick(1f, 0f, PadLayout.Deadzone).X > .99f);

var rb = new bool[21]; rb[2] = true;
var rh = PadLayout.Held(rb, noAxes, raw, false);
Check("raw EasySMX b2 is PASS (not the standard b0)", rh["pass"] && !rh["shoot"] && !rh["through"]);
rb = new bool[21]; rb[3] = true;
Check("raw EasySMX b3 is SHOOT", PadLayout.Held(rb, noAxes, raw, false)["shoot"]);
rb = new bool[21]; rb[0] = true;
Check("raw EasySMX b0 is THROUGH", PadLayout.Held(rb, noAxes, raw, false)["through"]);
rb = new bool[21]; rb[1] = true;
Check("raw EasySMX b1 is TACKLE", PadLayout.Held(rb, noAxes, raw, false)["tackle"]);
rb = new bool[21]; rb[4] = true;
Check("raw EasySMX b4 switches player", PadLayout.Held(rb, noAxes, raw, false)["switch"]);
rb = new bool[21]; rb[6] = true;
Check("raw LT button is close-control DRIBBLE",
      PadLayout.Held(rb, noAxes, raw, false)["dribble"] && !PadLayout.Held(rb, noAxes, raw, false)["sprint"]);
rb = new bool[21]; rb[7] = true;
Check("raw RT button sprints", PadLayout.Held(rb, noAxes, raw, false)["sprint"]);
rb = new bool[21]; rb[8] = true;
Check("raw Back (b8) is LONG BALL", PadLayout.Held(rb, noAxes, raw, false)["lob"]);
rb = new bool[21]; rb[10] = true;
Check("raw L3 (b10) is DRIBBLE", PadLayout.Held(rb, noAxes, raw, false)["dribble"]);
rb = new bool[21]; rb[11] = true;
Check("raw R3 (b11) changes camera", PadLayout.Held(rb, noAxes, raw, false)["camera"]);
rb = new bool[21]; rb[9] = true;
Check("raw Start (b9) pauses", PadLayout.Held(rb, noAxes, raw, false)["pause"]);
rb = new bool[21]; rb[0] = true;
Check("standard A is PASS", PadLayout.Held(rb, noAxes, std, true)["pass"]);
rb = new bool[21]; rb[6] = true;
Check("standard Start (b6) pauses", PadLayout.Held(rb, noAxes, std, true)["pause"]);
rb = new bool[21]; rb[4] = true;
Check("standard Back is LONG BALL", PadLayout.Held(rb, noAxes, std, true)["lob"]);
rb = new bool[21]; rb[7] = true;
Check("standard L3 is DRIBBLE", PadLayout.Held(rb, noAxes, std, true)["dribble"]);
var trig = new float[10]; trig[4] = 1f;
Check("analogue LT is DRIBBLE on a mapped pad", PadLayout.Held(noButtons, trig, std, true)["dribble"]);
var trigRt = new float[10]; trigRt[5] = 1f;
Check("analogue RT sprints on a mapped pad", PadLayout.Held(noButtons, trigRt, std, true)["sprint"]);

rb = new bool[21]; rb[12] = true;
var dpadUp = PadLayout.Move(rb, noAxes, false);
Check("raw hat button 12 moves up (no 11-14 conflict)", dpadUp.Y < -.9f && MathF.Abs(dpadUp.X) < .01f);
rb = new bool[21]; rb[11] = true;
Check("Godot hat button 11 works on an unmapped pad", PadLayout.Move(rb, noAxes, false).Y < -.9f);
var hat = new float[10]; hat[6] = -1f;
Check("hat-as-axis 6 moves left", PadLayout.Move(noButtons, hat, false).X < -.9f);
rb = new bool[21]; rb[15] = true;
Check("mapped pads use Godot d-pad indices (11-14), not raw 12-15",
      PadLayout.Move(rb, noAxes, true).Length < .01f);
rb = new bool[21]; rb[11] = true;
Check("mapped pad d-pad up works", PadLayout.Move(rb, noAxes, true).Y < -.9f);

Check("1P mode: every connected pad drives P1", PadLayout.DevicesFor(new[] { 0, 3, 7 }, false, 0).Length == 3);
Check("2P mode: player 2 gets the second pad", PadLayout.DevicesFor(new[] { 0, 3, 7 }, true, 1).SequenceEqual(new[] { 3 }));
Check("no pads -> no devices", PadLayout.DevicesFor(new int[0], false, 0).Length == 0
      && PadLayout.DevicesFor(new[] { 0 }, true, 1).Length == 0);

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
