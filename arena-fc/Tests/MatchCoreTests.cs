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
for (int i = 0; i < 3600; i++)
{
    pos.Step(1f / 60f, PlayerCommand.None);
    int o = pos.State.Ball.Owner;
    if (o != prevOwner) { flips++; prevOwner = o; hold = 0; }
    else if (o >= 0) { hold++; longestHold = Math.Max(longestHold, hold); }
}
// Before the fix: flips=653, longestHold=376.  After: flips=33, longestHold=602.
Check("ball does not flip owner every few ticks", flips < 100, $"flips={flips}");
Check("a carrier can dribble for several seconds", longestHold > 180,
      $"longest={longestHold} ticks");
Check("an unattended AI match reaches a goal", pos.State.Score[0] + pos.State.Score[1] > 0,
      $"score={pos.State.Score[0]}-{pos.State.Score[1]}");

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

Console.WriteLine($"\nRESULT: {passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;
