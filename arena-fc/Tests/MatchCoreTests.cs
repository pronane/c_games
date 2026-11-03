// Regression suite for the pure-C# match simulation.
//
// Bug this guards: Tick() used to release the ball whenever the *owner's*
// PossessionLock was greater than zero.  Both TryPossession() and
// AttemptTackle() set that lock when possession is gained, so the ball was
// dropped on the very next tick.  A 60-second unattended 11v11 match produced
// 653 ownership changes, an endless midfield scrum, and no goals.  This is
// what the 02.11.2026 screen recording showed (0-0, "X wins the ball!"
// repeating, the ball never leaving the centre circle for long).
//
// Run: dotnet run --project Tests/MatchCoreTests.csproj -c Release
using System.Numerics;
using ArenaFC.Core;

int passed = 0, failed = 0;
void Check(string name, bool ok, string? detail = null)
{
    if (ok) { passed++; Console.WriteLine($"  PASS  {name}"); }
    else { failed++; Console.WriteLine($"  FAIL  {name} {detail}"); }
}
void Section(string s) => Console.WriteLine($"\n== {s} ==");

Section("Possession stability (60 real seconds, 11v11, seed 2026)");
var pos = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
int flips = 0, prevOwner = pos.State.Ball.Owner, longestHold = 0, hold = 0;
int tackles = 0, nearTicks = 0, fouls = 0, nearBallTotal = 0;
string prevComment = pos.State.Commentary;
for (int i = 0; i < 3600; i++)
{
    pos.Step(1f / 60f, PlayerCommand.None);
    int o = pos.State.Ball.Owner;
    if (o != prevOwner) { flips++; prevOwner = o; hold = 0; }
    else if (o >= 0) { hold++; longestHold = Math.Max(longestHold, hold); }
    if (pos.State.Commentary != prevComment)
    {
        if (pos.State.Commentary.Contains("wins the ball!")) tackles++;
        if (pos.State.Commentary.StartsWith("Foul!")) fouls++;
        prevComment = pos.State.Commentary;
    }
    if (o >= 0)
    {
        var carrier = pos.State.Players[o];
        float nearest = 1e9f;
        foreach (var q in pos.State.Players)
            if (q.Team != carrier.Team && !q.IsKeeper)
                nearest = MathF.Min(nearest, Mx.FlatDist(q.Pos, carrier.Pos));
        if (nearest < 2f) nearTicks++;
    }
    foreach (var p in pos.State.Players)
        if (Mx.FlatDist(p.Pos, pos.State.Ball.Pos) < 4f) nearBallTotal++;
}
float avgNearBall = nearBallTotal / 3600f;
// Before the possession fix: flips=653, longestHold=376.
// Before the pressing fix: tackles=7, nearTicks=579.
// Before the spacing/foul fix: avgNearBall=2.62, fouls=4 with no visible contact.
Check("ball does not flip owner every few ticks", flips < 100, $"flips={flips}");
Check("a carrier can dribble for several seconds", longestHold > 180,
      $"longest={longestHold} ticks");
Check("opposition closes down the carrier", nearTicks > 400, $"nearTicks={nearTicks}");
Check("opposition wins the ball back", tackles >= 10, $"tackles={tackles}");
Check("free kicks are not handed out for invisible fouls", fouls <= 3, $"fouls={fouls}");
Check("players keep personal space around the ball", avgNearBall < 2.55f,
      $"avgWithin4m={avgNearBall:F3}");

Section("Gait joint sign convention");
// A leg bone points down; +X rotation sends it BEHIND the player (-Z).  Forward
// thigh swing must be negative, knee flexion positive.  See Scripts/Core/Gait.cs.
var runPose = Gait.Compute(6f, MathF.PI * .5f, 0f);
var idlePose = Gait.Compute(0f, 1f, 0f);
Check("the leading thigh swings forward (negative X)", runPose.HipL < -.3f,
      $"hipL={runPose.HipL:F3}");
Check("the trailing thigh swings back", runPose.HipR > .3f, $"hipR={runPose.HipR:F3}");
Check("both knees bend (positive X)", runPose.KneeL > .3f && runPose.KneeR > .05f,
      $"knees={runPose.KneeL:F3}/{runPose.KneeR:F3}");
Check("ankles counter-rotate so boots stay flat", runPose.FootL < 0f,
      $"footL={runPose.FootL:F3}");
Check("knees remain slightly bent when walking/standing", idlePose.KneeL > .05f,
      $"idleKnee={idlePose.KneeL:F3}");

Section("A collected loose ball stays collected");
var stick = new MatchEngine(new MatchOptions { Seed = 7 });
stick.State.Phase = Phase.Play;
stick.State.PhaseTimer = 0f;
stick.State.Ball.Owner = -1;
stick.State.Ball.Vel = Vector3.Zero;
stick.State.Ball.Spin = Vector3.Zero;
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
// Before the fix: held=4/30.  After: held=30/30.
Check("the player who collected the ball keeps it", heldTicks >= 25,
      $"owner={firstOwner} held={heldTicks}/30");

Section("A human who plays can shoot");
var human = new MatchEngine(new MatchOptions { Seed = 2026, TimeSpeed = 15f });
for (int i = 0; i < 3600; i++)
{
    var cmd = PlayerCommand.None;
    int ctrl = human.State.Controlled;
    if (ctrl >= 0)
    {
        var p = human.State.Players[ctrl];
        if (human.State.Ball.Owner == ctrl)
        {
            float distGoal = Mx.FlatDist(p.Pos, human.GoalPos(p.Team));
            if (distGoal < 24f) { cmd.Shoot = true; cmd.Charge = .8f; }
            else
            {
                var d = Mx.FlatDir(p.Pos, human.GoalPos(p.Team));
                cmd.Move = new Vector2(d.X, d.Z);
                cmd.Sprint = true;
            }
        }
        else
        {
            var d = Mx.FlatDir(p.Pos, human.State.Ball.Pos);
            cmd.Move = new Vector2(d.X, d.Z);
            cmd.Tackle = true;
        }
    }
    human.Step(1f / 60f, cmd);
}
Check("controlled player produces shots", human.State.Shots[0] + human.State.Shots[1] > 0,
      $"shots={human.State.Shots[0] + human.State.Shots[1]}");

Section("New defensive actions (slide / shield / first-touch pass)");
var actions = new MatchEngine(new MatchOptions { Seed = 33, TimeSpeed = 15f });
for (int i = 0; i < 600; i++)
{
    var c = new PlayerCommand
    {
        Move = new Vector2(MathF.Sin(i * .05f), MathF.Cos(i * .05f)),
        Slide = i % 90 == 0,
        Shield = i % 3 == 0,
        Pass = i % 120 == 0,
        Tackle = i % 150 == 0,
        Sprint = i % 4 == 0,
    };
    actions.Step(1f / 60f, c);
}
Check("slide/shield/tackle commands keep the match finite",
      Mx.IsFinite(actions.State.Ball.Pos) && Mx.IsFinite(actions.State.Ball.Vel)
      && actions.State.Players.All(p => Mx.IsFinite(p.Pos)));
Check("new commands do not corrupt the scoreboard",
      actions.State.Score.All(s => s >= 0 && s < 100));

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
